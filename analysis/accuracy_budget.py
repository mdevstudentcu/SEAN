"""Accuracy budget for UC-01 after GPS loss, checked against Monte Carlo (REQ-01, T1).

    uv run python analysis/accuracy_budget.py --runs 50

The write-up is `systems/accuracy-budget.md`. This script computes every number in it.

What it predicts: the 95 % horizontal error against time since GPS loss, for each estimator, from
the error terms of the scenario (YAML) and the filter's own model (`pnt.nav.ekf`), with no
simulation of the filter itself. Then it runs the filter on the same scenario over seeds
0..runs-1 and overlays the two.

The calculation, in four steps (`systems/accuracy-budget.md` gives the formulas in words):
1. Tower clocks at handover (`clock_analysis`). While GPS is good, the position is known, so each
   tower range is a direct reading of that tower's clock (plus our clock, multipath and noise).
   The filter learns the clocks from those readings. A linear covariance analysis of the filter's
   own clock model, run against the true error model, gives what it gets wrong at the moment GPS
   is lost and how that grows once it coasts: offset error, drift error times t, oscillator wander,
   multipath decorrelating, the told-position error as the line of sight turns. The filter's
   gains come from its own model, the truth from the scenario, so a filter that models the wrong
   thing (no drift state, no receiver clock) is scored as it is, not as it should be.
2. Position from the towers heard (`fix`). Each epoch's fix is the weighted least-squares
   solution of the heard ranges, weighted as the filter weights them. Position error = L x range
   prediction error, where L is the gain of that solution (the geometry: HDOP, the receiver clock
   column). White noise is then averaged by the filter's motion model (`cv_steady`), and a
   constant-velocity filter lags in the turns (`cv_lag`).
3. Dropouts (`position_budget`): every pattern of towers heard, weighted by its probability.
   With fewer than two towers, or a fix too weak to steer, the filter coasts: on constant
   velocity (it misses the turns) or on the IMU (`imu_growth`, our measured MPU6050).
4. The 95 % radius of that mixture of 2-D Gaussians (`r95_mixture`). For one circular Gaussian
   it is 2.45 sigma per axis (`Z95_2D`).

Approximations, all named in the write-up: the tower clocks are not re-learned after handover
(the filter does refine them a little from the redundant tower: the budget is conservative
there), GPS position error during calibration and altitude are ignored, dropouts during
calibration are counted as lost information on average, the builder's shared clock is counted
per tower.

Every value used is in the terms table (`terms`), with its source: measured, datasheet,
literature, scenario (TBC) or filter tuning. Seeds 0..runs-1 (paired across estimators and
calibration times). Every number is reproducible from the commit (REQ-10).
"""

from __future__ import annotations

import argparse
import copy
import inspect
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pnt import plots
from pnt.cli import _commit
from pnt.experiments import _map
from pnt.nav import estimate
from pnt.nav.ekf import CALIBRATED, EKF, C
from pnt.nav.imu import MPU6050 as FILTER_IMU
from pnt.sim import trajectory
from pnt.sim.scenario import T0_NS, generate, load

REPO = Path(__file__).resolve().parents[1]
G = 9.80665
DEG = math.pi / 180.0

# 95 % radius of a circular 2-D Gaussian, per-axis sigmas: P(R <= k sigma) = 1 - exp(-k^2 / 2)
Z95_2D = math.sqrt(-2.0 * math.log(0.05))  # 2.4477

# Our MPU6050, still on the bench overnight; the same values as main's sim model (sensors.MPU6050).
# The Monte Carlo sets the sim's IMU to these values, so the sim and the budget agree.
IMU_SESSION = "20261110-0306-static-bench-overnight, 1800-18000 s"
IMU_MEASURED = {
    "accel_noise_ug_rthz": 240.0,
    "accel_instability_ug": 280.0,
    "gyro_noise_dps_rthz": 0.005,
    "gyro_instability_dph": 16.0,
}
HEADING_SIGMA_DEG = 3.0  # TBC: heading 1-sigma at handover, the IMU filter's floor (nav/imu.py)
COAST_SIGMA_M = 500.0  # TBC: a fix weaker than this (believed, per axis) is not steering
ESTIMATORS = ("ekf", "ekf-calibrated", "ekf-imu")
ENVIRONMENTS = ("uc01", "uc01-realistic")
TCALS = (30.0, 60.0, 120.0, 300.0)  # s of good GPS before it is lost (Monte Carlo)
TCAL_FINE = tuple(float(t) for t in range(30, 301, 15))  # budget only
HORIZON_S = 300  # T1 asks for >= 300 s (systems/plan.md)
# What the budget is judged against, first to last (TBC):
# - T1, our goal (ADR-0034, Proposed): 95 % horizontal error <= 25 m for >= 300 s after GPS loss
# - the fallback, the mentors' figure (2026-11-10): <= 50 m for ~2 min, "OK-ish"
TARGETS = {"T1": (25.0, 300.0), "fallback": (50.0, 120.0)}
REPORT_AT = (30, 60, 120, 300)

# Categorical slots (dataviz reference palette), fixed order: one per estimator; ink for the rest
COLORS = {"ekf": "#2a78d6", "ekf-calibrated": "#eb6834", "ekf-imu": "#1baf7a"}
# Thinner on top, so a budget line another estimator shares stays visible beneath it
WIDTHS = {"ekf": 3.0, "ekf-calibrated": 2.0, "ekf-imu": 1.3}
TERM_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6")
INK, GRID = "#52514e", "#e4e3df"


# --- scenario ------------------------------------------------------------------------------
def spec_for(environment: str, t_cal: float, horizon: float = HORIZON_S) -> dict:
    """The scenario the budget and the Monte Carlo share: GPS good for `t_cal` s, then lost for
    the rest of the run (`horizon` s), with our measured IMU.
    - `uc01`: src/pnt/sim/scenarios/uc01-drone-circuit.yaml as committed (synthetic towers).
    - `uc01-realistic`: the UC-01 circuit flown in the `realistic` environment
      (sets/realistic.yaml: four real TELUS sites, our clock in the ranges, tower clocks,
      multipath, dropouts, told-position error)."""
    if environment == "uc01":
        spec = copy.deepcopy(load("uc01-drone-circuit"))
    elif environment == "uc01-realistic":
        spec = copy.deepcopy(load("realistic-nominal"))
        spec["trajectory"] = copy.deepcopy(load("uc01-drone-circuit")["trajectory"])
        spec["name"] = "uc01-realistic"
    else:
        raise ValueError(f"unknown environment {environment!r}")
    spec["sources"]["imu"] = {**spec["sources"].get("imu", {"rate_hz": 100}), **IMU_MEASURED}
    spec["duration_s"] = float(t_cal) + float(horizon) + 1.0
    spec["faults"] = [{"type": "outage", "source": "gnss", "start_s": float(t_cal)}]
    return spec


@dataclass(frozen=True)
class Env:
    """The error model of a scenario's tower ranges and clocks (truth), read from its YAML."""

    sigma_m: float  # white range noise, per reading
    told_sigma_m: float  # the sigma each reading reports
    rate_hz: float
    mp_sigma: float  # multipath (Gauss-Markov) steady-state sigma, m; 0: none
    mp_tau: float
    availability: float  # share of 30 s blocks a tower is heard
    block_s: float
    pos_sigma: float  # told tower position error per horizontal axis, m
    site_offset_sigma: float  # tower clock offset at start, m (uniform -> sigma)
    site_offset_rw: float  # m/sqrt(s)
    site_drift: float  # m/s, 1-sigma
    site_drift_rw: float  # m/s/sqrt(s)
    builder_drift: float  # shared by every tower of one network builder
    builder_drift_rw: float
    rx_in_ranges: bool  # our clock in every range
    rx_drift: float  # m/s, deterministic (scenario `clock.drift_ppb`)
    rx_rw: float  # m/sqrt(s), white frequency noise of our clock
    gnss_time_sigma_m: float | None  # GNSS time solution, m; None: none
    gnss_rate_hz: float
    gnss_sigma_m: float


def env_from_spec(spec: dict) -> Env:
    lte = spec["sources"]["lte"]
    tc = spec.get("tower_clocks") or {}
    site, builder = tc.get("site") or {}, tc.get("builder") or {}
    clock = spec.get("clock") or {}
    gnss = spec["sources"]["gnss"]
    mp = lte.get("multipath") or {}
    drop = lte.get("dropout") or {}
    if tc:
        off, off_rw, drift, drift_rw = (
            site.get("offset_m", 0.0),
            site.get("offset_rw_m", 0.0),
            site.get("drift_mps", 0.0),
            site.get("drift_rw_mps", 0.0),
        )
    else:
        off, off_rw = lte["init_bias_m"], lte["clock_rw_m"]
        drift, drift_rw = lte.get("drift_sigma_mps", 0.0), 0.0
    t_sigma = gnss.get("time_sigma_ns")
    return Env(
        sigma_m=float(lte["sigma_m"]),
        told_sigma_m=float(lte.get("told_sigma_m", lte["sigma_m"])),
        rate_hz=float(lte["rate_hz"]),
        mp_sigma=float(mp.get("sigma_m", 0.0)),
        mp_tau=float(mp.get("tau_s", 1.0)),
        availability=float(drop.get("availability", 1.0)),
        block_s=float(drop.get("block_s", 1e9)),
        pos_sigma=float(lte.get("told_position_sigma_m", 0.0)),
        site_offset_sigma=float(off) / math.sqrt(3.0),
        site_offset_rw=float(off_rw),
        site_drift=float(drift),
        site_drift_rw=float(drift_rw),
        builder_drift=float(builder.get("drift_mps", 0.0)),
        builder_drift_rw=float(builder.get("drift_rw_mps", 0.0)),
        rx_in_ranges=bool(lte.get("receiver_clock", False)),
        rx_drift=C * clock.get("drift_ppb", 0.0) * 1e-9,
        rx_rw=C * clock.get("rw_ns", 0.0) * 1e-9,
        gnss_time_sigma_m=None if t_sigma is None or not clock else C * t_sigma * 1e-9,
        gnss_rate_hz=float(gnss["rate_hz"]),
        gnss_sigma_m=float(gnss["sigma_m"]),
    )


@dataclass(frozen=True)
class FilterModel:
    """What an estimator assumes about the tower clocks and its motion (pnt.nav.ekf)."""

    name: str
    motion: str  # cv or imu
    calibrated: bool  # offset and drift per tower clock; else offset only (random walk)
    rx_in_ranges: bool
    offset_q: float  # m^2/s
    drift_q: float  # m^2/s^3
    calib_offset_q: float  # added while calibrating
    calib_drift_q: float
    calib_gate_s: float
    init_offset_sigma: float
    init_drift_sigma: float
    mp_sigma: float
    mp_tau: float
    pos_sigma: float
    rx_offset_q: float
    rx_drift_q: float
    rx_init_sigma: float
    rx_init_drift: float
    q_accel: float


CONFIGS = {"ekf": {}, "ekf-calibrated": CALIBRATED, "ekf-imu": {"motion": "imu"}}


def filter_model(estimator: str, env: Env) -> FilterModel:
    """The estimator's settings, read from `EKF`'s defaults and its registry configuration."""
    cfg = {k: p.default for k, p in inspect.signature(EKF).parameters.items()}
    cfg.update(CONFIGS[estimator])
    cal = cfg["clock_model"] == "calibrated"
    return FilterModel(
        name=estimator,
        motion=cfg["motion"],
        calibrated=cal,
        rx_in_ranges=bool(cfg["pseudorange_receiver_clock"]),
        offset_q=C**2 * cfg["tower_h0"] / 2.0 if cal else cfg["q_emitter"] ** 2,
        drift_q=C**2 * 2.0 * math.pi**2 * cfg["tower_h_2"] if cal else 0.0,
        calib_offset_q=cfg["calib_q_offset"] ** 2 if cal else 0.0,
        calib_drift_q=cfg["calib_q_drift"] ** 2 if cal else 0.0,
        calib_gate_s=float(cfg["calib_gate_s"]),
        init_offset_sigma=float(cfg["init_emitter_sigma"]),
        init_drift_sigma=float(cfg["init_tower_drift_sigma"]) if cal else 0.0,
        mp_sigma=float(cfg["multipath_ratio"]) * env.told_sigma_m,
        mp_tau=float(cfg["multipath_tau_s"]),
        pos_sigma=float(cfg["tower_position_sigma_m"]),
        rx_offset_q=C**2 * cfg["h0"] / 2.0,
        rx_drift_q=C**2 * 2.0 * math.pi**2 * cfg["h_2"],
        rx_init_sigma=C * cfg["init_clock_sigma_s"],
        rx_init_drift=C * cfg["init_drift_sigma"],
        q_accel=float(cfg["q_accel"]),
    )


# --- 95 % radius ------------------------------------------------------------------------------
def r95_gaussian(cov) -> float:
    """95 % radius of a zero-mean 2-D Gaussian with covariance `cov` (exact, by quadrature).

    P(R <= r) = 1/(2 pi sqrt(l1 l2)) * integral over theta of (1 - exp(-r^2 a / 2)) / a,
    a = cos^2/l1 + sin^2/l2, with l1, l2 the eigenvalues. Circular: 2.4477 sigma."""
    lam = np.clip(np.linalg.eigvalsh(np.asarray(cov, float)), 0.0, None)
    if lam[1] <= 0:
        return 0.0
    if lam[0] < 1e-12 * lam[1]:  # a line: 1-D, 1.96 sigma
        return 1.959964 * math.sqrt(lam[1])
    th = np.linspace(0.0, np.pi / 2, 91)  # a quarter: the integrand is symmetric
    a = np.cos(th) ** 2 / lam[1] + np.sin(th) ** 2 / lam[0]
    norm = 1.0 / math.sqrt(lam[0] * lam[1])

    def cdf(r):
        return norm * np.trapezoid((1.0 - np.exp(-(r**2) * a / 2.0)) / a, th) / (np.pi / 2)

    lo, hi = 0.0, 4.0 * math.sqrt(lam[1])
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < 0.95 else (lo, mid)
    return (lo + hi) / 2


_Z = np.random.default_rng(20261110).standard_normal((4000, 2))


def r95_mixture(weights, means, covs, z: np.ndarray = _Z) -> float:
    """95 % radius of a mixture of 2-D Gaussians (weights, means (k, 2), covs (k, 2, 2)), from a
    fixed set of standard normal points (seeded: deterministic). Mean offsets (a lag, a drift
    every run shares) count as offsets, not as extra spread."""
    w = np.asarray(weights, float)
    w = w / w.sum()
    covs = np.asarray(covs, float)
    means = np.asarray(means, float)
    # Cholesky with a floor, so a rank-deficient (1-D) covariance is fine
    vals, vecs = np.linalg.eigh(covs)
    root = vecs * np.sqrt(np.clip(vals, 0.0, None))[:, None, :]
    pts = means[:, None, :] + np.einsum("kij,nj->kni", root, z)
    r = np.hypot(pts[..., 0], pts[..., 1]).ravel()
    wt = np.repeat(w / len(z), len(z))
    order = np.argsort(r)
    c = np.cumsum(wt[order])
    return float(r[order][np.searchsorted(c, 0.95)])


# --- the filter's smoothing ---------------------------------------------------------------
def cv_steady(q: float, r: float, dt: float = 1.0) -> np.ndarray:
    """Steady-state posterior covariance [[pos, .], [., vel]] of a per-axis constant-velocity
    Kalman filter: white acceleration PSD q (m^2/s^3), position readings of variance r every dt.
    For dt much shorter than the filter's memory it tends to the classical continuous result,
    pos variance sqrt(2) q^(1/4) (r dt)^(3/4)."""
    from scipy.linalg import solve_discrete_are

    F = np.array([[1.0, dt], [0.0, 1.0]])
    Q = q * np.array([[dt**3 / 3, dt**2 / 2], [dt**2 / 2, dt]])
    H = np.array([[1.0, 0.0]])
    Pp = solve_discrete_are(F.T, H.T, Q, np.array([[r]]))  # prior, steady state
    k = Pp[:, 0] / (Pp[0, 0] + r)
    return Pp - np.outer(k, Pp[0])


def imu_q(r: float, spec=FILTER_IMU, dt: float = 1.0) -> float:
    """The acceleration PSD an IMU-driven filter effectively runs on (m^2/s^3): its accelerometer
    noise, plus g times the attitude random walk it allows (gyro noise and its `gyro_extra`)
    over its own averaging window T: q = a_n^2 + g^2 N_theta^2 T^2 / 3. T is found by iteration
    (T = dt * r / pos variance)."""
    a2 = spec.accel_noise**2 + spec.accel_extra**2
    n2 = spec.gyro_noise**2 + spec.gyro_extra**2
    window = dt
    for _ in range(50):
        q = a2 + G**2 * n2 * window**2 / 3.0
        window = dt * r / cv_steady(q, r, dt)[0, 0]
    return a2 + G**2 * n2 * window**2 / 3.0


def motion_q(fm: FilterModel, r: float) -> float:
    return fm.q_accel**2 if fm.motion == "cv" else imu_q(r)


def cv_lag(pos: np.ndarray, vel: np.ndarray, q: float, r: float, dt: float = 1.0) -> np.ndarray:
    """Error of a steady-state constant-velocity filter fed the true horizontal positions with no
    noise, started exact: how far it lags in the turns (n, 2). Deterministic for a route."""
    P = cv_steady(q, r, dt)
    F = np.array([[1.0, dt], [0.0, 1.0]])
    Pp = F @ P @ F.T + q * np.array([[dt**3 / 3, dt**2 / 2], [dt**2 / 2, dt]])
    k = Pp[:, 0] / (Pp[0, 0] + r)
    x = np.stack([pos[0, :2], vel[0, :2]])  # (pos, vel) x (e, n)
    out = np.zeros((len(pos), 2))
    for i in range(1, len(pos)):
        x = F @ x
        x = x + np.outer(k, pos[i, :2] - x[0])
        out[i] = x[0] - pos[i, :2]
    return out


# --- IMU coasting -------------------------------------------------------------------------
def imu_growth(t, v0_sigma: float, turn_accel: float, imu: dict = IMU_MEASURED) -> dict:
    """Per-axis horizontal position sigma (m) of the IMU alone, t s after the last fix, by term
    (Groves 2013, ch. 14; Titterton & Weston 2004): what each sensor error does when integrated.
    - velocity at the last fix: v0 t
    - accelerometer bias (its wander: the part calibration can't remove): b t^2 / 2. The tilt
      left at handover is the part of this bias that tilt absorbs, so it is not counted again.
    - accelerometer white noise (velocity random walk): N t^1.5 / sqrt(3)
    - gyro bias (wander) tilts the platform: g b t^3 / 6
    - gyro white noise (angle random walk): g N t^2.5 / sqrt(20)
    - heading error times the turn acceleration: a psi t^2 / 2 (TBC heading)"""
    t = np.asarray(t, float)
    ba = imu["accel_instability_ug"] * 1e-6 * G
    na = imu["accel_noise_ug_rthz"] * 1e-6 * G
    bg = imu["gyro_instability_dph"] * DEG / 3600.0
    ng = imu["gyro_noise_dps_rthz"] * DEG
    return {
        "velocity at handover": v0_sigma * t,
        "accel bias wander": 0.5 * ba * t**2,
        "accel noise": na * t**1.5 / math.sqrt(3.0),
        "gyro bias wander": G * bg * t**3 / 6.0,
        "gyro noise": G * ng * t**2.5 / math.sqrt(20.0),
        "heading x turn acceleration": 0.5 * turn_accel * HEADING_SIGMA_DEG * DEG * t**2,
    }


def gps_velocity_sigma(env: Env) -> float:
    """Per-axis velocity sigma at handover of the IMU filter while GPS steers it (steady state)."""
    dt = 1.0 / env.gnss_rate_hz
    r = env.gnss_sigma_m**2
    return math.sqrt(cv_steady(imu_q(r, dt=dt), r, dt)[1, 1])


def imu_sigma(t, v0_sigma: float, turn_accel: float) -> np.ndarray:
    return np.sqrt(sum(v**2 for v in imu_growth(t, v0_sigma, turn_accel).values()))


# --- step 1: tower clocks at handover ----------------------------------------------------
W = 5  # states per tower: clock offset (with the constant part of the told-position error),
# clock drift, multipath, told-position error east, north. Then our clock (offset, drift) and
# the network builder's clock (offset, drift).
SOURCES = ("tower clocks", "multipath", "told tower position", "receiver clock", "noise")


def _two_state_q(s_off: float, s_drift: float, dt: float) -> np.ndarray:
    return np.array(
        [
            [s_off * dt + s_drift * dt**3 / 3, s_drift * dt**2 / 2],
            [s_drift * dt**2 / 2, s_drift * dt],
        ]
    )


def clock_analysis(env: Env, fm: FilterModel, los: np.ndarray, t_cal: int, horizon: int):
    """Linear covariance analysis of the filter's tower clocks (step 1), at 1 s steps.

    `los` (t_cal + horizon + 1, towers, 3): line of sight, tower to receiver, at each second.
    Returns per source in SOURCES (independent, so they add): the mean (horizon + 1, towers) and
    covariance (horizon + 1, towers, towers) of each tower's range prediction error after GPS
    loss, and the filter's own belief of it, S (horizon + 1, towers, towers), with the
    reported noise included."""
    n = los.shape[1]
    size = W * n + 4
    c = W * n  # our clock offset; c + 1 drift; c + 2, c + 3 builder offset and drift
    dt = 1.0
    u0 = los[0, :, :2]
    phi_t = math.exp(-dt / env.mp_tau) if env.mp_sigma else 0.0
    phi_f = math.exp(-dt / fm.mp_tau) if fm.mp_sigma else 1.0

    F_t = np.eye(size)
    F_f = np.eye(size)
    for i in range(n):
        o = W * i
        F_t[o, o + 1] = F_f[o, o + 1] = dt
        F_t[o + 2, o + 2], F_f[o + 2, o + 2] = phi_t, phi_f
    F_t[c, c + 1] = F_f[c, c + 1] = dt
    F_t[c + 2, c + 3] = dt

    def tower_blocks(M, i, block):
        o = W * i
        M[o : o + 2, o : o + 2] = block

    # Truth: process noise, start covariance and mean, by source
    Qt = {s: np.zeros((size, size)) for s in SOURCES}
    P0 = {s: np.zeros((size, size)) for s in SOURCES}
    m0 = {s: np.zeros(size) for s in SOURCES}
    for i in range(n):
        o = W * i
        tower_blocks(
            Qt["tower clocks"], i, _two_state_q(env.site_offset_rw**2, env.site_drift_rw**2, dt)
        )
        P0["tower clocks"][o, o] = env.site_offset_sigma**2
        P0["tower clocks"][o + 1, o + 1] = env.site_drift**2
        Qt["multipath"][o + 2, o + 2] = env.mp_sigma**2 * (1 - phi_t**2)
        P0["multipath"][o + 2, o + 2] = env.mp_sigma**2
        # Told position: range error u(t).dp = u0.dp + (u(t) - u0).dp; the first part is a
        # constant the clock offset carries (as the filter models it)
        s2 = env.pos_sigma**2
        P0["told tower position"][o + 3 : o + 5, o + 3 : o + 5] = s2 * np.eye(2)
        P0["told tower position"][o, o] = s2 * float(u0[i] @ u0[i])
        P0["told tower position"][o, o + 3 : o + 5] = s2 * u0[i]
        P0["told tower position"][o + 3 : o + 5, o] = s2 * u0[i]
    Qt["tower clocks"][c + 2 : c + 4, c + 2 : c + 4] = _two_state_q(
        0.0, env.builder_drift_rw**2, dt
    )
    P0["tower clocks"][c + 3, c + 3] = env.builder_drift**2
    Qt["receiver clock"][c : c + 2, c : c + 2] = _two_state_q(env.rx_rw**2, 0.0, dt)
    m0["receiver clock"][c + 1] = env.rx_drift

    # Filter: its own process noise (coasting / calibrating) and start covariance
    def filter_q(calibrating: bool) -> np.ndarray:
        Q = np.zeros((size, size))
        extra = (fm.calib_offset_q, fm.calib_drift_q) if calibrating else (0.0, 0.0)
        for i in range(n):
            o = W * i
            if fm.calibrated:
                q = _two_state_q(fm.offset_q + extra[0], fm.drift_q + extra[1], dt)
                tower_blocks(Q, i, q)
            else:
                Q[o, o] = fm.offset_q * dt
            Q[o + 2, o + 2] = fm.mp_sigma**2 * (1 - phi_f**2)
        Q[c : c + 2, c : c + 2] = _two_state_q(fm.rx_offset_q, fm.rx_drift_q, dt)
        return Q

    Pf = np.zeros((size, size))
    for i in range(n):
        o = W * i
        Pf[o, o] = fm.init_offset_sigma**2
        Pf[o + 1, o + 1] = fm.init_drift_sigma**2
        Pf[o + 2, o + 2] = fm.mp_sigma**2
        Pf[o + 3 : o + 5, o + 3 : o + 5] = fm.pos_sigma**2 * np.eye(2)
    Pf[c, c] = fm.rx_init_sigma**2
    Pf[c + 1, c + 1] = fm.rx_init_drift**2

    def rows(k: int) -> tuple[np.ndarray, np.ndarray]:
        Ht = np.zeros((n, size))
        Hf = np.zeros((n, size))
        du = los[k, :, :2] - u0
        for i in range(n):
            o = W * i
            Ht[i, o] = Ht[i, o + 2] = 1.0
            Ht[i, o + 3 : o + 5] = du[i]
            Ht[i, c] = 1.0 if env.rx_in_ranges else 0.0
            Ht[i, c + 2] = 1.0
            Hf[i, o] = 1.0
            Hf[i, o + 2] = 1.0 if fm.mp_sigma else 0.0
            Hf[i, o + 3 : o + 5] = du[i] if fm.pos_sigma else 0.0
            Hf[i, c] = 1.0 if fm.rx_in_ranges else 0.0
        return Ht, Hf

    # Joint state [truth; estimate] per source: covariance Z and mean
    Z = {s: np.zeros((2 * size, 2 * size)) for s in SOURCES}
    zm = {s: np.zeros(2 * size) for s in SOURCES}
    for s in SOURCES:
        Z[s][:size, :size] = P0[s]
        zm[s][:size] = m0[s]
    A_pred = np.zeros((2 * size, 2 * size))
    A_pred[:size, :size], A_pred[size:, size:] = F_t, F_f

    info = env.availability * env.rate_hz  # readings per second, on average (dropouts)
    r_t = env.sigma_m**2 / info
    r_f = env.told_sigma_m**2 / info
    has_time = env.gnss_time_sigma_m is not None
    eye = np.eye(size)

    out_mean = {s: np.zeros((horizon + 1, n)) for s in SOURCES}
    out_cov = {s: np.zeros((horizon + 1, n, n)) for s in SOURCES}
    out_s = np.zeros((horizon + 1, n, n))

    def record(j: int, k: int) -> None:
        Ht, Hf = rows(k)
        E = np.hstack([Ht, -Hf])
        for s in SOURCES:
            out_mean[s][j] = E @ zm[s]
            out_cov[s][j] = E @ Z[s] @ E.T
        out_s[j] = Hf @ Pf @ Hf.T + env.told_sigma_m**2 * np.eye(n)

    for k in range(1, t_cal + horizon + 1):
        calibrating = fm.calibrated and fm.calib_gate_s <= k - 1 < t_cal
        Qf = filter_q(calibrating)
        for s in SOURCES:
            Z[s] = A_pred @ Z[s] @ A_pred.T
            Z[s][:size, :size] += Qt[s]
            zm[s] = A_pred @ zm[s]
        Pf = F_f @ Pf @ F_f.T + Qf
        if k <= t_cal:  # GPS good: position known, every range reads the clocks
            Ht, Hf = rows(k)
            Rt, Rf = np.full(n, r_t), np.full(n, r_f)
            if has_time:
                row = np.zeros((1, size))
                row[0, c] = 1.0
                Ht, Hf = np.vstack([Ht, row]), np.vstack([Hf, row])
                rt = env.gnss_time_sigma_m**2 / env.gnss_rate_hz
                Rt, Rf = np.append(Rt, rt), np.append(Rf, rt)
            Sf = Hf @ Pf @ Hf.T + np.diag(Rf)
            K = np.linalg.solve(Sf, Hf @ Pf).T
            IKH = eye - K @ Hf
            A = np.zeros((2 * size, 2 * size))
            A[:size, :size] = eye
            A[size:, :size] = K @ Ht
            A[size:, size:] = IKH
            B = np.vstack([np.zeros((size, len(Rt))), K])
            noise = {s: np.zeros(len(Rt)) for s in SOURCES}
            noise["noise"][:n] = Rt[:n]
            if has_time:
                noise["receiver clock"][n] = Rt[n]
            for s in SOURCES:
                Z[s] = A @ Z[s] @ A.T + (B * noise[s]) @ B.T
                zm[s] = A @ zm[s]
            Pf = IKH @ Pf @ IKH.T + (K * Rf) @ K.T
        if k >= t_cal:
            record(k - t_cal, k)
    return out_mean, out_cov, out_s


# --- step 2: position from the towers heard ---------------------------------------------------
def fix(U: np.ndarray, S: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gain L (2 x heard) of the weighted least-squares fix the filter makes from the heard
    ranges, and its believed covariance. U: horizontal line-of-sight rows (heard x 2); S: the
    filter's belief of the range prediction errors (heard x heard: clock, multipath and noise).
    A clock common to every range is a large common term in S, which costs geometry as a fourth
    satellite costs a GNSS receiver."""
    Si = np.linalg.inv(S)
    info = U.T @ Si @ U
    P = np.linalg.inv(info)
    return P @ U.T @ Si, P


# --- step 3: dropouts, coasting, and the mixture -------------------------------------------
def _patterns(n: int, availability: float) -> list[tuple[np.ndarray, float]]:
    if availability >= 1.0:
        return [(np.ones(n, bool), 1.0)]
    out = []
    for bits in itertools.product((True, False), repeat=n):
        heard = np.array(bits)
        k = int(heard.sum())
        out.append((heard, availability**k * (1 - availability) ** (n - k)))
    return out


@dataclass
class Geometry:
    los: np.ndarray  # (t_cal + horizon + 1, towers, 3)
    pos: np.ndarray  # (t_cal + horizon + 1, 3) true position at each second
    vel: np.ndarray
    turn_accel: float  # rms horizontal acceleration along the route, m/s^2


def geometry(spec: dict, emitters: np.ndarray, t_cal: int, horizon: int) -> Geometry:
    ts = np.arange(0.0, t_cal + horizon + 1.0)
    traj = {**spec["trajectory"], "_origin_llh": spec.get("origin_llh")}
    pos, vel = trajectory.make(traj, ts)
    d = pos[:, None, :] - emitters[None, :, :]
    los = d / np.linalg.norm(d, axis=2)[..., None]
    k = trajectory.kinematics(traj, np.arange(0.0, 400.0, 0.1))
    turn = float(np.sqrt(np.mean(np.sum(k.acc[:, :2] ** 2, axis=1))))
    return Geometry(los, pos, vel, turn)


def emitters_for(spec: dict, seed: int) -> np.ndarray:
    """The towers a seed's run hears (true positions), as the sim draws them. The IMU is left
    out: it has its own random stream, so the towers are the same and it is quicker."""
    s = copy.deepcopy(spec)
    s["sources"] = {k: v for k, v in s["sources"].items() if k != "imu"}
    s["duration_s"] = 2.0
    run = generate(s, seed=seed)
    return np.array([v for k, v in run.emitters.items() if k.startswith("lte:")])


def position_budget(
    env: Env, fm: FilterModel, geo: Geometry, t_cal: int, horizon: int, detail: bool = True
) -> dict:
    """95 % horizontal error at each second after GPS loss (steps 2-4), and by term with every
    tower heard. Returns {"t", "total", "all_heard", "terms": {name: r95}, "coast_share",
    "per_axis": {name: per-axis sigma}}."""
    mean, cov, S = clock_analysis(env, fm, geo.los, t_cal, horizon)
    n = geo.los.shape[1]
    tot_mean = sum(mean.values())
    tot_cov = sum(cov.values())
    pats = _patterns(n, env.availability)
    allheard = np.ones(n, bool)

    # The filter's averaging of white noise and its velocity error, from the all-heard fix
    def white_snapshot(j, heard):
        k = t_cal + j
        L, Pb = fix(geo.los[k][heard][:, :2], S[j][np.ix_(heard, heard)])
        return L, Pb, env.sigma_m**2 * (L @ L.T)

    s2 = np.array([np.trace(white_snapshot(j, allheard)[2]) / 2 for j in range(horizon + 1)])
    r_med = float(np.median(s2))
    q = motion_q(fm, r_med)
    Pss = cv_steady(q, r_med)
    v_sigma = math.sqrt(Pss[1, 1])
    seg = slice(t_cal, t_cal + horizon + 1)
    lag = (
        cv_lag(geo.pos[seg], geo.vel[seg], q, r_med)
        if fm.motion == "cv"
        else np.zeros((horizon + 1, 2))
    )

    t = np.arange(horizon + 1)
    total = np.zeros(horizon + 1)
    all_heard = np.zeros(horizon + 1)
    coast_share = np.zeros(horizon + 1)
    term_names = [*SOURCES[:-1], "noise during calibration", "noise after handover"]
    if fm.motion == "cv":
        term_names.append("lag in turns")
    terms = {name: np.zeros(horizon + 1) for name in term_names}
    per_axis = {name: np.zeros(horizon + 1) for name in term_names}
    fixed_cov = np.zeros((horizon + 1, 2, 2))  # all-heard total, the start of a coast
    for j in range(horizon + 1):
        k = t_cal + j
        L, _, wsnap = white_snapshot(j, allheard)
        f = cv_steady(q, np.trace(wsnap) / 2)[0, 0] / (np.trace(wsnap) / 2)
        parts = {s: (L @ mean[s][j], L @ cov[s][j] @ L.T) for s in SOURCES}
        parts["noise during calibration"] = parts.pop("noise")
        parts["noise after handover"] = (np.zeros(2), f * wsnap)
        if fm.motion == "cv":
            parts["lag in turns"] = (lag[j], np.zeros((2, 2)))
        m_all = sum(p[0] for p in parts.values())
        c_all = sum(p[1] for p in parts.values())
        fixed_cov[j] = c_all
        for name, (mu, cv) in parts.items() if detail else ():
            zero = not np.any(mu)
            terms[name][j] = r95_gaussian(cv) if zero else r95_mixture([1.0], [mu], [cv])
            per_axis[name][j] = math.sqrt(max(np.trace(cv) / 2 + mu @ mu / 2, 0.0))
        all_heard[j] = r95_mixture([1.0], [m_all], [c_all])

        # Every pattern of towers heard in this 30 s block
        t_abs = t_cal + j
        start = max(math.floor(t_abs / env.block_s) * env.block_s - t_cal, 0) if pats[1:] else j
        dt = j - int(start)
        ws, ms, cs = [], [], []
        coast = 0.0
        for heard, w in pats:
            ok = heard.sum() >= 2
            if ok:
                Lh, Pb, wh = white_snapshot(j, heard)
                ok = np.linalg.eigvalsh(Pb)[-1] < COAST_SIGMA_M**2
            if ok:
                fh = cv_steady(q, np.trace(wh) / 2)[0, 0] / (np.trace(wh) / 2)
                mu = Lh @ tot_mean[j][heard] + lag[j]
                cv = Lh @ tot_cov[j][np.ix_(heard, heard)] @ Lh.T + fh * wh
            else:  # coasting since the block started
                coast += w
                cv = fixed_cov[int(start)] + (v_sigma * dt) ** 2 * np.eye(2)
                if fm.motion == "cv":  # misses the turns: true path minus straight line
                    k0 = t_cal + int(start)
                    mu = geo.pos[k, :2] - geo.pos[k0, :2] - geo.vel[k0, :2] * dt
                else:
                    mu = np.zeros(2)
                    cv = cv + imu_sigma(dt, 0.0, geo.turn_accel) ** 2 * np.eye(2)
            ws.append(w)
            ms.append(mu)
            cs.append(cv)
        total[j] = r95_mixture(ws, ms, cs)
        coast_share[j] = coast
    return {
        "t": t,
        "total": total,
        "all_heard": all_heard,
        "terms": terms,
        "per_axis": per_axis,
        "coast_share": coast_share,
        "white_window_s": float(r_med / Pss[0, 0]),
        "velocity_sigma_mps": v_sigma,
        "turn_accel": geo.turn_accel,
    }


def budget_job(
    environment: str, estimator: str, t_cal: float, seed: int, horizon: int, detail: bool = True
) -> dict:
    """The budget for one environment, estimator, calibration time and tower geometry (seed)."""
    spec = spec_for(environment, t_cal, horizon)
    env = env_from_spec(spec)
    fm = filter_model(estimator, env)
    geo = geometry(spec, emitters_for(spec, seed), int(t_cal), horizon)
    return position_budget(env, fm, geo, int(t_cal), horizon, detail)


def combine(budgets: list[dict]) -> dict:
    """Budgets over several tower geometries (synthetic towers differ per seed): the 95 % of the
    pooled error is not the mean of 95 %s, so each geometry's total is treated as a 2-D circular
    Gaussian of that R95 and the pooled 95 % is taken over the mixture."""
    if len(budgets) == 1:
        return budgets[0]
    out = dict(budgets[0])
    sig = np.array([b["total"] for b in budgets]) / Z95_2D
    eye = np.eye(2)
    out["total"] = np.array(
        [
            r95_mixture(
                np.ones(len(sig)), np.zeros((len(sig), 2)), (sig[:, j] ** 2)[:, None, None] * eye
            )
            for j in range(sig.shape[1])
        ]
    )
    for key in ("terms", "per_axis"):
        out[key] = {
            name: np.sqrt(np.mean([b[key][name] ** 2 for b in budgets], axis=0))
            for name in budgets[0][key]
        }
    for key in ("all_heard", "coast_share"):
        out[key] = np.mean([b[key] for b in budgets], axis=0)
    return out


# --- Monte Carlo ------------------------------------------------------------------------------
def mc_job(environment: str, estimator: str, t_cal: float, seed: int, horizon: int) -> np.ndarray:
    """Horizontal error at each whole second after GPS loss for one seed (sim)."""
    spec = spec_for(environment, t_cal, horizon)
    run = generate(spec, seed=seed)
    est = list(estimate(estimator, run.measurements, origin_llh=spec.get("origin_llh")))
    s = plots.series(plots.RunData(spec["name"], {}, spec, run.truth, {estimator: est}), estimator)
    t = (np.array([e.t_ns for e in est]) - T0_NS) / 1e9
    idx = np.searchsorted(t, t_cal + np.arange(horizon + 1) - 1e-6)
    return s.err_h[np.clip(idx, 0, len(t) - 1)].astype(np.float32)


# --- terms table ----------------------------------------------------------------------------
def terms(environment: str) -> list[dict]:
    """Every value the budget uses, with its source (ADR-0015 labels)."""
    env = env_from_spec(spec_for(environment, 120.0))
    real = environment == "uc01-realistic"
    scen = (
        "scenario, TBC (sets/realistic.yaml)"
        if real
        else "scenario, TBC (uc01-drone-circuit.yaml)"
    )
    rows = [
        ("Tower range noise", f"{env.sigma_m:g} m per reading at {env.rate_hz:g} Hz", scen),
        (
            "Tower geometry",
            "4 TELUS sites, 0.6-1.7 km" if real else "6 towers, 0.8-3 km ring, per seed",
            "literature (ISED registry)" if real else "synthetic",
        ),
        (
            "Multipath",
            f"{env.mp_sigma:g} m, {env.mp_tau:g} s correlation" if env.mp_sigma else "none",
            scen,
        ),
        (
            "Tower heard",
            f"{env.availability:.0%} of {env.block_s:g} s blocks"
            if env.availability < 1
            else "always",
            scen,
        ),
        (
            "Told tower position",
            f"{env.pos_sigma:g} m per axis" if env.pos_sigma else "exact",
            scen,
        ),
        (
            "Tower clock offset",
            f"{env.site_offset_sigma:.0f} m (uniform), wander {env.site_offset_rw:g} m/sqrt(s)",
            scen,
        ),
        (
            "Tower clock drift",
            f"{math.hypot(env.site_drift, env.builder_drift):.3f} m/s, wander "
            f"{math.hypot(env.site_drift_rw, env.builder_drift_rw):.1e} m/s/sqrt(s)"
            if env.site_drift or env.builder_drift
            else "none",
            "form: literature (Shamaei et al. 2018); size TBC" if real else scen,
        ),
        (
            "Our clock in the ranges",
            f"yes: {env.rx_drift:.1f} m/s drift, {env.rx_rw:.1f} m/sqrt(s)"
            if env.rx_in_ranges
            else "no",
            scen,
        ),
        (
            "GNSS time while GPS is good",
            f"{env.gnss_time_sigma_m:.1f} m at {env.gnss_rate_hz:g} Hz"
            if env.gnss_time_sigma_m
            else "none",
            scen,
        ),
        (
            "Accel white noise",
            f"{IMU_MEASURED['accel_noise_ug_rthz']:g} ug/sqrt(Hz)",
            f"measured ({IMU_SESSION}); datasheet 400",
        ),
        (
            "Accel bias wander",
            f"{IMU_MEASURED['accel_instability_ug']:g} ug",
            f"measured ({IMU_SESSION})",
        ),
        (
            "Gyro white noise",
            f"{IMU_MEASURED['gyro_noise_dps_rthz']:g} deg/s/sqrt(Hz)",
            f"measured ({IMU_SESSION}); datasheet 0.005",
        ),
        (
            "Gyro bias wander",
            f"{IMU_MEASURED['gyro_instability_dph']:g} deg/h",
            f"measured ({IMU_SESSION})",
        ),
        (
            "Heading at handover",
            f"{HEADING_SIGMA_DEG:g} deg",
            "TBC (the IMU filter's floor, nav/imu.py)",
        ),
        (
            "Filter motion noise (CV)",
            f"{inspect.signature(EKF).parameters['q_accel'].default:g} m/s^2/sqrt(Hz)",
            "filter tuning (nav/ekf.py)",
        ),
    ]
    return [{"term": a, "value": b, "source": c} for a, b, c in rows]


# --- figures ----------------------------------------------------------------------------------
def _style(ax) -> None:
    ax.grid(True, which="major", color=GRID, lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _target(ax, x_end) -> None:
    for (name, (m, s)), ls in zip(TARGETS.items(), (":", "-."), strict=True):
        ax.axhline(m, color=INK, lw=1, ls=ls)
        label = f"{name}: {m:g} m for {s:g} s (TBC)"
        ax.text(x_end, m * 1.08, label, color=INK, fontsize=7, ha="right")


def fig_terms(budgets: dict, imu_line: dict, caption: str):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(budgets), figsize=(16, 4.8), dpi=150, sharey=True)
    for ax, (title, b) in zip(np.atleast_1d(axes), budgets.items(), strict=True):
        t = b["t"]
        for (name, r), col in zip(b["terms"].items(), TERM_COLORS, strict=False):
            ax.plot(t[1:], r[1:], color=col, lw=1.4, label=name)
        ax.plot(
            t[1:], b["all_heard"][1:], color="#0b0b0b", lw=2.2, label="total, every tower heard"
        )
        ax.plot(
            t[1:], b["total"][1:], color="#0b0b0b", lw=2.2, ls="--", label="total with dropouts"
        )
        ax.plot(
            t[1:], imu_line[title][1:], color=INK, lw=1.2, ls=":", label="IMU alone (no towers)"
        )
        _target(ax, t[-1])
        for _, s in TARGETS.values():
            ax.axvline(s, color=GRID, lw=1)
        ax.set_yscale("log")
        ax.set_ylim(0.3, 3000)
        ax.set(xlabel="time since GPS loss (s)", title=title)
        _style(ax)
    np.atleast_1d(axes)[0].set_ylabel("95 % horizontal error, m (each term alone)")
    np.atleast_1d(axes)[-1].legend(
        fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0)
    )
    fig.text(0.01, 0.01, caption, fontsize=7, color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def fig_overlay(pred: dict, meas: dict, caption: str):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(ENVIRONMENTS), figsize=(12, 4.8), dpi=150, sharey=True)
    for ax, envn in zip(axes, ENVIRONMENTS, strict=True):
        for est in ESTIMATORS:
            p, m = pred[envn][est], meas[envn][est]
            t = np.arange(len(p))
            ax.plot(t, p, color=COLORS[est], lw=WIDTHS[est], label=f"{est}: budget")
            ax.plot(t, m, color=COLORS[est], lw=1.2, ls="--", label=f"{est}: Monte Carlo p95")
        _target(ax, t[-1])
        for _, s in TARGETS.values():
            ax.axvline(s, color=GRID, lw=1)
        ax.set_yscale("log")
        ax.set_ylim(1, 20000)
        ax.set(xlabel="time since GPS loss (s)", title=f"{envn}, GPS good for 120 s first")
        _style(ax)
    axes[0].set_ylabel("95 % horizontal error (m)")
    axes[-1].legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.text(0.01, 0.01, caption, fontsize=7, color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def fig_handover(fine: dict, sweep: dict, caption: str):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 4, figsize=(16.5, 4.4), dpi=150, sharey=True)
    panels = [(e, s) for e in ENVIRONMENTS for _, s in TARGETS.values()]
    for ax, (envn, h) in zip(axes, panels, strict=True):
        for est in ESTIMATORS:
            x = np.array(TCAL_FINE)
            ax.plot(
                x,
                [worst_in(fine[envn][est][tc], h) for tc in TCAL_FINE],
                color=COLORS[est],
                lw=WIDTHS[est],
                label=f"{est}: budget",
            )
            ax.plot(
                TCALS,
                [worst_in(sweep[envn][est][tc], h) for tc in TCALS],
                "o",
                ms=8,
                mfc="none",
                mec=COLORS[est],
                mew=1.6,
                label=f"{est}: Monte Carlo p95",
            )
        _target(ax, 300)
        ax.set_yscale("log")
        ax.set_ylim(3, 20000)
        ax.set(xlabel="GPS good before loss (s)", title=f"{envn}: worst of first {h:g} s")
        _style(ax)
    axes[0].set_ylabel("95 % horizontal error (m)")
    axes[-1].legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.text(0.01, 0.01, caption, fontsize=7, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


# --- main -------------------------------------------------------------------------------------
def _budget_seeds(environment: str, runs: int) -> list[int]:
    """Real towers are the same in every seed; synthetic ones are drawn per seed."""
    real = "towers_from" in spec_for(environment, 120.0)["sources"]["lte"]
    return [0] if real else list(range(runs))


def worst_in(curve: np.ndarray, window_s: float) -> float:
    """The largest 95 % error in the first `window_s` s after GPS loss: a target "<= X m for
    >= T s" holds only if the whole window is within X."""
    return float(np.max(curve[: int(window_s) + 1]))


def time_to(curve: np.ndarray, limit: float) -> int | None:
    """First whole second after GPS loss at which a 95 % error curve is over `limit`: how long
    that error, on its own, stays within it. None if it stays within it over the whole curve."""
    over = np.flatnonzero(np.asarray(curve) > limit)
    return int(over[0]) if len(over) else None


def min_tcal(curves: dict, window_s: float, limit: float) -> float | None:
    """Least calibration time that meets `limit` over the first `window_s` s, with every longer
    one meeting it too; None if none does."""
    ok = None
    for tc in sorted(curves, reverse=True):
        if worst_in(curves[tc], window_s) <= limit:
            ok = tc
        else:
            break
    return ok


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=None, help="worker processes (default: all)")
    ap.add_argument("--out", type=Path, default=REPO / "analysis" / "results" / "accuracy-budget")
    args = ap.parse_args(argv)
    commit = _commit()
    H = HORIZON_S
    seeds = list(range(args.runs))

    # Budget: every environment x estimator x calibration time (fine grid and the MC grid)
    tcals = sorted(set(TCAL_FINE) | set(TCALS))
    keys = [(e, est, tc) for e in ENVIRONMENTS for est in ESTIMATORS for tc in tcals]
    tasks = [
        (e, est, tc, s, H, tc == 120.0) for e, est, tc in keys for s in _budget_seeds(e, args.runs)
    ]
    res = _map(budget_job, tasks, args.jobs)
    by_key: dict = {}
    for (e, est, tc, *_), r in zip(tasks, res, strict=True):
        by_key.setdefault((e, est, tc), []).append(r)
    budget = {k: combine(v) for k, v in by_key.items()}

    # Monte Carlo: same grid of calibration times, seeds 0..runs-1
    mtasks = [
        (e, est, tc, s, H)
        for e in ENVIRONMENTS
        for est in ESTIMATORS
        for tc in TCALS
        for s in seeds
    ]
    mres = _map(mc_job, mtasks, args.jobs)
    runs: dict = {}
    for (e, est, tc, _, _), r in zip(mtasks, mres, strict=True):
        runs.setdefault((e, est, tc), []).append(r)
    p95 = {k: np.nanpercentile(np.array(v, float), 95, axis=0) for k, v in runs.items()}
    worst = {k: np.nanmax(np.array(v, float), axis=0) for k, v in runs.items()}

    args.out.mkdir(parents=True, exist_ok=True)
    cap = (
        f"Sim, seeds 0-{args.runs - 1}, commit {commit}. uc01: uc01-drone-circuit.yaml; "
        "uc01-realistic: the UC-01 circuit in sets/realistic.yaml. GPS lost for good after the "
        "calibration time; IMU set to our measured MPU6050. analysis/accuracy_budget.py"
    )
    # 1: terms, for the estimator closest to T1 on uc01 (ekf), the one that learns drifts
    # (ekf-calibrated), and the only one that models the realistic set's receiver clock
    panels = [("uc01", "ekf"), ("uc01", "ekf-calibrated"), ("uc01-realistic", "ekf-calibrated")]
    tb = {f"{e}, {est}, 120 s of GPS": budget[(e, est, 120.0)] for e, est in panels}
    imu_line = {}
    for (title, b), (e, _) in zip(tb.items(), panels, strict=True):
        v0 = gps_velocity_sigma(env_from_spec(spec_for(e, 120.0)))
        imu_line[title] = Z95_2D * imu_sigma(b["t"], v0, b["turn_accel"])
    fig = fig_terms(tb, imu_line, cap)
    fig.savefig(args.out / "budget_terms.png")
    # 2: budget vs Monte Carlo at 120 s of GPS
    pred = {e: {est: budget[(e, est, 120.0)]["total"] for est in ESTIMATORS} for e in ENVIRONMENTS}
    meas = {e: {est: p95[(e, est, 120.0)] for est in ESTIMATORS} for e in ENVIRONMENTS}
    fig_overlay(pred, meas, cap).savefig(args.out / "budget_vs_monte_carlo.png")
    # 3: handover: worst 95 % error over each target's window against calibration time
    fine = {
        e: {est: {tc: budget[(e, est, tc)]["total"] for tc in tcals} for est in ESTIMATORS}
        for e in ENVIRONMENTS
    }
    sweep = {
        e: {est: {tc: p95[(e, est, tc)] for tc in TCALS} for est in ESTIMATORS}
        for e in ENVIRONMENTS
    }
    fig_handover(fine, sweep, cap).savefig(args.out / "handover.png")

    summary = {
        "commit": commit,
        "runs": args.runs,
        "seeds": [0, args.runs - 1],
        "imu": {"values": IMU_MEASURED, "session": IMU_SESSION},
        "terms": {e: terms(e) for e in ENVIRONMENTS},
        "targets": {k: {"m": m, "s": t} for k, (m, t) in TARGETS.items()},
        "table": {},
        "curves": {},
        "min_tcal": {},
        "imu_alone_r95": {
            str(t): float(next(iter(imu_line.values()))[t]) for t in (10, 20, 30, 60, 120)
        },
        # The mentors (2026-11-10): how long each error, on its own, takes to reach the limits
        "time_to": {},
    }
    limits = sorted({m for m, _ in TARGETS.values()})
    for (title, line), (e, _) in zip(imu_line.items(), panels, strict=True):
        v0 = gps_velocity_sigma(env_from_spec(spec_for(e, 120.0)))
        t_imu = np.arange(H + 1)
        parts = imu_growth(t_imu, v0, tb[title]["turn_accel"])
        summary["time_to"][f"imu alone ({e})"] = {
            name: {f"{m:g}": time_to(Z95_2D * v, m) for m in limits} for name, v in parts.items()
        } | {"all together": {f"{m:g}": time_to(line, m) for m in limits}}
    for e in ENVIRONMENTS:
        for est in ESTIMATORS:
            b = budget[(e, est, 120.0)]
            curves = {**b["terms"], "total, every tower heard": b["all_heard"]}
            curves["total with dropouts"] = b["total"]
            summary["time_to"][f"{e}/{est}"] = {
                name: {f"{m:g}": time_to(v, m) for m in limits} for name, v in curves.items()
            }
    for e in ENVIRONMENTS:
        for est in ESTIMATORS:
            b = budget[(e, est, 120.0)]
            summary["table"][f"{e}/{est}"] = {
                str(t): {
                    name: {
                        "r95_m": float(b["terms"][name][t]),
                        "per_axis_sigma_m": float(b["per_axis"][name][t]),
                    }
                    for name in b["terms"]
                }
                | {
                    "total, every tower heard": float(b["all_heard"][t]),
                    "total with dropouts": float(b["total"][t]),
                    "coasting share": float(b["coast_share"][t]),
                }
                for t in (120, 300)
            } | {
                "white window s": b["white_window_s"],
                "velocity sigma m/s": b["velocity_sigma_mps"],
            }
        for est in ESTIMATORS:
            for tc in tcals:
                row = {
                    "budget": {str(t): float(budget[(e, est, tc)]["total"][t]) for t in REPORT_AT}
                }
                row["budget_worst_in"] = {
                    k: worst_in(budget[(e, est, tc)]["total"], t) for k, (_, t) in TARGETS.items()
                }
                if tc in TCALS:
                    row["mc_p95"] = {str(t): float(p95[(e, est, tc)][t]) for t in REPORT_AT}
                    row["mc_worst_run"] = {
                        str(t): float(worst[(e, est, tc)][t]) for t in REPORT_AT
                    }
                    row["mc_p95_worst_in"] = {
                        k: worst_in(p95[(e, est, tc)], t) for k, (_, t) in TARGETS.items()
                    }
                summary["curves"][f"{e}/{est}/{tc:g}"] = row
            summary["min_tcal"][f"{e}/{est}"] = {
                k: {
                    "budget": min_tcal(fine[e][est], t, m),
                    "mc": min_tcal(sweep[e][est], t, m),
                }
                for k, (m, t) in TARGETS.items()
            }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(
        json.dumps(
            {k: summary[k] for k in ("commit", "min_tcal", "imu_alone_r95")},
            indent=1,
        )
    )
    for k, row in summary["curves"].items():
        if "mc_p95" in row:
            b, m = row["budget"], row["mc_p95"]
            print(
                k,
                "budget",
                [round(b[str(t)]) for t in REPORT_AT],
                "mc",
                [round(m[str(t)]) for t in REPORT_AT],
            )


if __name__ == "__main__":
    main()
