"""Truth trajectories in local ENU.

Kept simple on purpose. Later: replace with SITL-generated trajectories (flight/sitl/) for
realistic drone motion and IMU data.
"""

from __future__ import annotations

import numpy as np


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


TRAJECTORIES = {"loop": loop, "square": square}


def make(spec: dict, t: np.ndarray) -> tuple:
    spec = dict(spec)
    kind = spec.pop("type")
    return TRAJECTORIES[kind](t, **spec)
