"""Truth trajectories in local ENU (issue #14).

Two layers:
- `make(spec, t)` -> (pos, vel): what scenarios use for truth and measurement geometry.
- `kinematics(spec, t)` -> Kinematics: adds acceleration, attitude and body rates, which the
  IMU model (#9) needs.

Types:
- `loop`: constant-speed circle (analytic).
- `square`: instant 90-degree turns. Fine for position-only scenarios; refused by
  `kinematics` because its corners would need infinite acceleration.
- `waypoints`: a smooth spline through waypoints flown at constant speed, given in ENU
  (`points`) or lat/lon/height (`points_llh`, converted with the scenario origin).
  `closed: true` loops; open paths stop at the last point. `corner_radius_m` keeps straight
  legs straight and rounds only the corners. `vehicle` sets the attitude rule:
  - multirotor: tilts so the thrust axis carries the needed acceleration
  - fixedwing: nose along the velocity, banked so lift carries the turn (coordinated flight)
  - ground: nose along the velocity, no bank

Frames: world ENU; body FLU (x forward, y left, z up). Quaternions are body-to-world,
scalar first (w, x, y, z).

Not yet: ArduPilot SITL trajectories (needs a SITL install).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from pnt.core.frames import llh_to_enu

GRAVITY = np.array([0.0, 0.0, -9.80665])  # m/s^2 in ENU


def loop(t: np.ndarray, radius_m: float, speed_mps: float, altitude_m: float) -> tuple:
    """Constant-speed circle centred on the origin. Returns (pos[N,3], vel[N,3])."""
    w = speed_mps / radius_m
    pos = np.stack(
        [radius_m * np.cos(w * t), radius_m * np.sin(w * t), np.full_like(t, altitude_m)], axis=1
    )
    vel = np.stack(
        [-radius_m * w * np.sin(w * t), radius_m * w * np.cos(w * t), np.zeros_like(t)], axis=1
    )
    return pos, vel


def square(t: np.ndarray, side_m: float, speed_mps: float, altitude_m: float) -> tuple:
    """Square centred on the origin, flown counter-clockwise at constant speed."""
    perimeter = 4 * side_m
    s = (speed_mps * t) % perimeter
    half = side_m / 2
    corners = np.array([[-half, -half], [half, -half], [half, half], [-half, half]])
    dirs = np.array([[1, 0], [0, 1], [-1, 0], [0, -1]], dtype=float)
    leg = np.minimum((s // side_m).astype(int), 3)
    along = s - leg * side_m
    xy = corners[leg] + dirs[leg] * along[:, None]
    vxy = dirs[leg] * speed_mps
    pos = np.column_stack([xy, np.full_like(t, altitude_m)])
    vel = np.column_stack([vxy, np.zeros_like(t)])
    return pos, vel


@dataclass
class Kinematics:
    t: np.ndarray  # s, (N,)
    pos: np.ndarray  # ENU m, (N, 3)
    vel: np.ndarray  # ENU m/s, (N, 3)
    acc: np.ndarray  # ENU m/s^2, (N, 3)
    rot: np.ndarray  # body-to-ENU rotation matrices, (N, 3, 3)
    omega_b: np.ndarray  # body angular rate rad/s, (N, 3)

    @property
    def quat(self) -> np.ndarray:
        """Body-to-ENU quaternions, scalar first, (N, 4)."""
        from scipy.spatial.transform import Rotation

        return Rotation.from_matrix(self.rot).as_quat(scalar_first=True)

    @property
    def specific_force_b(self) -> np.ndarray:
        """What an ideal accelerometer reads: (a - g) in the body frame, (N, 3)."""
        return np.einsum("nji,nj->ni", self.rot, self.acc - GRAVITY)


# --- smooth waypoint paths ---------------------------------------------------------------
class _Path:
    """Cubic spline through waypoints, reparameterised by arc length."""

    def __init__(self, points: np.ndarray, closed: bool):
        from scipy.interpolate import CubicSpline

        pts = np.asarray(points, float)
        if closed:
            pts = np.vstack([pts, pts[:1]])
        chord = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        if np.any(np.diff(chord) <= 0):
            raise ValueError("waypoints must not repeat consecutively")
        self.spline = CubicSpline(chord, pts, bc_type="periodic" if closed else "natural")
        u = np.linspace(0.0, chord[-1], 40 * len(pts) + 2000)
        ds = np.linalg.norm(self.spline(u, 1), axis=1)
        s = np.r_[0.0, np.cumsum(0.5 * (ds[1:] + ds[:-1]) * np.diff(u))]
        self.u_of_s = (s, u)
        self.length = float(s[-1])
        self.closed = closed

    def at(self, t: np.ndarray, speed: float):
        """Position, velocity and acceleration at times t for constant speed along the path."""
        s = speed * np.asarray(t, float)
        moving = np.ones_like(s, bool)
        if self.closed:
            s = np.mod(s, self.length)
        else:
            moving = s < self.length
            s = np.clip(s, 0.0, self.length)
        u = np.interp(s, *self.u_of_s)
        p0, p1, p2 = self.spline(u), self.spline(u, 1), self.spline(u, 2)
        n1 = np.linalg.norm(p1, axis=1)
        ud = speed / n1  # du/dt for constant speed
        udd = -np.einsum("ij,ij->i", p1, p2) * ud**2 / n1**2
        vel = p1 * ud[:, None]
        acc = p2 * (ud**2)[:, None] + p1 * udd[:, None]
        vel[~moving] = 0.0
        acc[~moving] = 0.0
        return p0, vel, acc


def _round_corners(points: np.ndarray, radius: float, closed: bool) -> np.ndarray:
    """Replace each corner by two points `radius` along its legs, so the spline keeps the legs
    straight and only rounds the corners."""
    if radius <= 0:
        return points
    out = []
    n = len(points)
    for i in range(n):
        if not closed and i in (0, n - 1):
            out.append(points[i])
            continue
        prev, cur, nxt = points[i - 1], points[i], points[(i + 1) % n]
        a, b = prev - cur, nxt - cur
        ra, rb = min(radius, np.linalg.norm(a) / 2), min(radius, np.linalg.norm(b) / 2)
        out += [cur + a / np.linalg.norm(a) * ra, cur + b / np.linalg.norm(b) * rb]
    return np.array(out)


_PATHS: dict[str, _Path] = {}


def _waypoint_path(spec: dict) -> _Path:
    key = json.dumps(spec, sort_keys=True, default=str)
    if key not in _PATHS:
        if "points_llh" in spec:
            origin = spec.get("_origin_llh")
            if origin is None:
                raise ValueError("points_llh needs the scenario origin_llh")
            pts = np.array([llh_to_enu(p, origin) for p in spec["points_llh"]])
        else:
            pts = np.asarray(spec["points"], float)
        closed = bool(spec.get("closed", False))
        pts = _round_corners(pts, float(spec.get("corner_radius_m", 0.0)), closed)
        _PATHS[key] = _Path(pts, closed)
    return _PATHS[key]


def waypoints(t: np.ndarray, **spec) -> tuple:
    pos, vel, _ = _waypoint_path(spec).at(t, float(spec["speed_mps"]))
    return pos, vel


# --- attitude -----------------------------------------------------------------------------
def _attitude(vel: np.ndarray, acc: np.ndarray, vehicle: str) -> np.ndarray:
    """Body-to-ENU rotation for each sample from velocity, acceleration and vehicle type."""
    n = len(vel)
    up = np.tile([0.0, 0.0, 1.0], (n, 1))
    heading = vel.copy()
    heading[:, 2] = 0.0 if vehicle == "multirotor" else heading[:, 2]
    # Hold the last heading while stopped (and start facing east if never moving)
    norm = np.linalg.norm(heading, axis=1)
    last = np.array([1.0, 0.0, 0.0])
    for i in range(n):
        if norm[i] > 1e-6:
            last = heading[i] / norm[i]
        heading[i] = last
    f = acc - GRAVITY  # specific force: what thrust or lift must supply
    if vehicle == "multirotor":
        z = f / np.linalg.norm(f, axis=1)[:, None]
        x = heading - np.einsum("ij,ij->i", heading, z)[:, None] * z
    elif vehicle in ("fixedwing", "ground"):
        x = heading
        ref = f if vehicle == "fixedwing" else up  # lift carries the turn; a car stays level
        z = ref - np.einsum("ij,ij->i", ref, x)[:, None] * x
        z /= np.linalg.norm(z, axis=1)[:, None]
    else:
        raise ValueError(f"unknown vehicle {vehicle!r} (multirotor, fixedwing, ground)")
    x /= np.linalg.norm(x, axis=1)[:, None]
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=2)  # columns are the body axes in ENU


def _pva(spec: dict, t: np.ndarray):
    kind = spec["type"]
    if kind == "loop":
        r, v = float(spec["radius_m"]), float(spec["speed_mps"])
        pos, vel = loop(t, r, v, float(spec["altitude_m"]))
        acc = -((v / r) ** 2) * np.column_stack([pos[:, 0], pos[:, 1], np.zeros_like(t)])
        return pos, vel, acc, "multirotor"
    if kind == "waypoints":
        body = {k: v for k, v in spec.items() if k != "type"}
        pos, vel, acc = _waypoint_path(body).at(t, float(spec["speed_mps"]))
        return pos, vel, acc, spec.get("vehicle", "multirotor")
    if kind == "square":
        raise ValueError("square has instant turns (infinite acceleration); use type: waypoints")
    raise ValueError(f"unknown trajectory type {kind!r}")


def kinematics(spec: dict, t: np.ndarray, h: float = 1e-3) -> Kinematics:
    """Full motion at times t. Body rates come from the attitude at t +/- h."""
    t = np.asarray(t, float)
    pos, vel, acc, vehicle = _pva(spec, t)
    rot = _attitude(vel, acc, vehicle)
    _, vp, ap, _ = _pva(spec, t + h)
    _, vm, am, _ = _pva(spec, t - h)
    rdot = (_attitude(vp, ap, vehicle) - _attitude(vm, am, vehicle)) / (2 * h)
    skew = np.einsum("nji,njk->nik", rot, rdot)  # R^T Rdot = [omega_b]x
    omega_b = np.stack([skew[:, 2, 1], skew[:, 0, 2], skew[:, 1, 0]], axis=1)
    return Kinematics(t, pos, vel, acc, rot, omega_b)


TRAJECTORIES = {"loop": loop, "square": square, "waypoints": waypoints}


def make(spec: dict, t: np.ndarray) -> tuple:
    spec = dict(spec)
    kind = spec.pop("type")
    if kind != "waypoints":
        spec.pop("_origin_llh", None)
    return TRAJECTORIES[kind](t, **spec)
