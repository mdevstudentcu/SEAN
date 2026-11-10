"""The arithmetic of the UC-01 accuracy budget (analysis/accuracy_budget.py, REQ-01).

Each test checks one step of the budget against a closed-form result a reader can do by hand:
the 2-D 95 % radius, least-squares drift learning, multipath decorrelation, the constant-velocity
filter's steady state, the geometry, and the IMU error growth formulas. No Monte Carlo here.
"""

import importlib.util
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "accuracy_budget.py"
_SPEC = importlib.util.spec_from_file_location("accuracy_budget", _PATH)
ab = importlib.util.module_from_spec(_SPEC)
sys.modules["accuracy_budget"] = ab  # dataclasses look their module up by name
_SPEC.loader.exec_module(ab)


def test_r95_circular_is_2_45_sigma():
    assert ab.Z95_2D == pytest.approx(2.4477, abs=1e-4)
    assert ab.r95_gaussian(9.0 * np.eye(2)) == pytest.approx(3.0 * ab.Z95_2D, rel=1e-6)


def test_r95_of_a_line_is_1_96_sigma():
    assert ab.r95_gaussian(np.diag([4.0, 0.0])) == pytest.approx(2.0 * 1.96, rel=1e-3)


def test_r95_mixture_matches_the_exact_cdf():
    # 90 % of runs at sigma 1, 10 % at sigma 10 (circular): solve the CDF by bisection
    def cdf(r):
        return 0.9 * (1 - math.exp(-(r**2) / 2)) + 0.1 * (1 - math.exp(-(r**2) / 200))

    lo, hi = 0.0, 100.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < 0.95 else (lo, mid)
    got = ab.r95_mixture([0.9, 0.1], np.zeros((2, 2)), [np.eye(2), 100 * np.eye(2)])
    assert got == pytest.approx(lo, rel=0.03)  # 4000 fixed points: about 1 % sampling error
    ellipse = np.diag([4.0, 1.0])
    assert ab.r95_mixture([1.0], [[0.0, 0.0]], [ellipse]) == pytest.approx(
        ab.r95_gaussian(ellipse), rel=0.03
    )


def test_cv_steady_state_tends_to_the_continuous_result():
    q, sigma, dt = 1.0, 3.0, 0.01  # readings every 10 ms: far shorter than the filter's memory
    p = ab.cv_steady(q, sigma**2, dt)
    assert p[0, 0] == pytest.approx(math.sqrt(2) * q**0.25 * (sigma**2 * dt) ** 0.75, rel=0.03)
    assert p[1, 1] == pytest.approx(math.sqrt(2) * q**0.75 * (sigma**2 * dt) ** 0.25, rel=0.03)


def _one_tower(**env):
    base = dict(
        sigma_m=10.0,
        told_sigma_m=10.0,
        rate_hz=1.0,
        mp_sigma=0.0,
        mp_tau=1.0,
        availability=1.0,
        block_s=1e9,
        pos_sigma=0.0,
        site_offset_sigma=100.0,
        site_offset_rw=0.0,
        site_drift=1.0,
        site_drift_rw=0.0,
        builder_drift=0.0,
        builder_drift_rw=0.0,
        rx_in_ranges=False,
        rx_drift=0.0,
        rx_rw=0.0,
        gnss_time_sigma_m=None,
        gnss_rate_hz=5.0,
        gnss_sigma_m=2.5,
    )
    return ab.Env(**{**base, **env})


def _matched_filter(env, **over):
    """A filter whose clock model is the truth: offset and drift, no extra noise."""
    fm = replace(
        ab.filter_model("ekf-calibrated", env),
        offset_q=0.0,
        drift_q=0.0,
        calib_offset_q=0.0,
        calib_drift_q=0.0,
        init_offset_sigma=1e5,
        init_drift_sigma=1e3,
        mp_sigma=0.0,
        pos_sigma=0.0,
        rx_in_ranges=False,
    )
    return replace(fm, **over)


def test_drift_learned_from_calibration_matches_least_squares():
    # A clock read N times at 1 s (sigma 10 m) with a flat prior is a straight-line fit: the
    # prediction t s after the last reading has variance sigma^2 (1/N + (t - tbar)^2 / Sxx)
    env = _one_tower()
    fm = _matched_filter(env)
    n, horizon = 100, 120
    los = np.tile([[[1.0, 0.0, 0.0]]], (n + horizon + 1, 1, 1))
    _, cov, _ = ab.clock_analysis(env, fm, los, n, horizon)
    tbar, sxx = (n + 1) / 2, n * (n**2 - 1) / 12
    for j in (0, 60, 120):
        want = env.sigma_m**2 * (1 / n + (n + j - tbar) ** 2 / sxx)
        assert cov["noise"][j][0, 0] == pytest.approx(want, rel=0.02)
        assert cov["tower clocks"][j][0, 0] < 1e-3 * want  # the prior is forgotten


def test_multipath_decorrelates_after_handover():
    # Multipath known at handover (no noise, matched model), then sigma^2 (1 - exp(-2 t / tau))
    env = _one_tower(sigma_m=0.01, told_sigma_m=0.01, mp_sigma=20.0, mp_tau=30.0)
    env = replace(env, site_offset_sigma=0.0, site_drift=0.0)
    fm = _matched_filter(env, mp_sigma=20.0, mp_tau=30.0, init_offset_sigma=1e-3)
    fm = replace(fm, init_drift_sigma=1e-6)
    los = np.tile([[[1.0, 0.0, 0.0]]], (200, 1, 1))
    _, cov, _ = ab.clock_analysis(env, fm, los, 100, 99)
    for t in (10, 30, 90):
        want = 20.0**2 * (1 - math.exp(-2 * t / 30.0))
        assert cov["multipath"][t][0, 0] == pytest.approx(want, rel=0.02)


def test_geometry_square_and_the_clock_column():
    # Four towers at 90 deg, unit noise: per-axis variance 1/2 (HDOP 1). A shared clock costs
    # nothing for a symmetric set and costs geometry for a lopsided one.
    sq = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [0.0, -1.0]])
    common = 1e8 * np.ones((4, 4))
    _, p = ab.fix(sq, np.eye(4))
    assert np.allclose(p, 0.5 * np.eye(2))
    _, p = ab.fix(sq, np.eye(4) + common)
    assert np.allclose(p, 0.5 * np.eye(2), rtol=1e-4)
    a = np.radians([0.0, 40.0, 80.0, 120.0])
    lop = np.column_stack([np.cos(a), np.sin(a)])
    _, free = ab.fix(lop, np.eye(4))
    _, clock = ab.fix(lop, np.eye(4) + common)
    assert np.trace(clock) > 2 * np.trace(free)
    # The gain maps a common range error to zero position error when the clock is estimated
    gain, _ = ab.fix(lop, np.eye(4) + common)
    assert np.allclose(gain @ np.ones(4), 0.0, atol=1e-4)


def test_imu_growth_terms_are_the_textbook_formulas():
    g, t = 9.80665, 60.0
    got = ab.imu_growth(t, v0_sigma=0.1, turn_accel=1.0)
    assert got["velocity at handover"] == pytest.approx(6.0)
    assert got["accel bias wander"] == pytest.approx(0.5 * 280e-6 * g * t**2)  # 4.94 m
    assert got["accel noise"] == pytest.approx(240e-6 * g * t**1.5 / math.sqrt(3))
    assert got["gyro bias wander"] == pytest.approx(g * math.radians(16 / 3600) * t**3 / 6)
    assert got["gyro noise"] == pytest.approx(g * math.radians(0.005) * t**2.5 / math.sqrt(20))
    assert got["heading x turn acceleration"] == pytest.approx(0.5 * math.radians(3) * t**2)


def test_budget_reads_the_scenario_and_the_filter():
    spec = ab.spec_for("uc01-realistic", 60.0)
    assert spec["faults"] == [{"type": "outage", "source": "gnss", "start_s": 60.0}]
    assert spec["sources"]["imu"]["accel_noise_ug_rthz"] == 240.0
    env = ab.env_from_spec(spec)
    assert (env.sigma_m, env.availability, env.pos_sigma) == (50.0, 0.75, 100.0)
    assert env.rx_in_ranges and env.rx_drift == pytest.approx(5.996, rel=1e-3)
    cal, plain = ab.filter_model("ekf-calibrated", env), ab.filter_model("ekf", env)
    assert cal.rx_in_ranges and cal.calibrated and cal.pos_sigma == 100.0
    assert not plain.rx_in_ranges and not plain.calibrated and plain.mp_sigma == 0.0
    assert ab.filter_model("ekf-imu", env).motion == "imu"


def test_a_target_holds_over_its_whole_window():
    # "<= 25 m for >= 300 s" fails if any second in the window is over, even if +300 s is not
    curve = np.full(301, 20.0)
    curve[150] = 30.0
    assert ab.worst_in(curve, 300) == 30.0 and ab.worst_in(curve, 120) == 20.0
    curves = {30.0: curve, 60.0: np.full(301, 24.0), 120.0: np.full(301, 10.0)}
    assert ab.min_tcal(curves, 300, 25.0) == 60.0
    assert ab.min_tcal(curves, 120, 25.0) == 30.0
    assert ab.min_tcal({30.0: curve}, 300, 5.0) is None
