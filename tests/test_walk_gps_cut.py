"""The moving-session GPS cut (analysis/walk_gps_cut.py, #214): truth from the withheld fixes,
interpolated to each estimate, the good-fix gate, and where the cuts go. Synthetic fixes only.

The thresholds (HDOP, satellites, speed, spacing) are the script's TBC values, not targets.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "walk_gps_cut.py"
_SPEC = importlib.util.spec_from_file_location("walk_gps_cut", _PATH)
wc = importlib.util.module_from_spec(_SPEC)
sys.modules["walk_gps_cut"] = wc
_SPEC.loader.exec_module(wc)

S = 1_000_000_000  # ns
T0 = 1_478_415_091 * S


def _walk(static_s=150, walk_s=1200, end_s=150, speed=1.4):
    """1 Hz fixes: static, then walking east at `speed`, then static where it stopped."""
    n = static_s + walk_s + end_s
    t = T0 + np.arange(n) * S
    x = np.clip(np.arange(n) - static_s, 0, walk_s) * speed
    return t, np.column_stack([x, np.zeros(n), np.zeros(n)])


def test_truth_interpolates_between_fixes_and_is_the_fix_on_one():
    t = T0 + np.array([0, 1, 2]) * S
    pos = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 0.0], [3.0, 2.0, 0.0]])
    q = np.array([T0, T0 + S // 4, T0 + S, T0 + 3 * S // 2, T0 + 2 * S])
    out, ok = wc.interpolate(t, pos, q)
    assert ok.all()
    np.testing.assert_allclose(out[:, :2], [[0, 0], [0.25, 0.5], [1, 2], [2, 2], [3, 2]])


def test_truth_has_no_value_outside_the_fixes_or_across_a_gap():
    t = T0 + np.array([0, 1, 5]) * S  # 4 s gap between the 2nd and 3rd fix
    pos = np.zeros((3, 3))
    q = np.array([T0 - S // 10, T0 + S // 2, T0 + 3 * S, T0 + 5 * S, T0 + 6 * S])
    _, ok = wc.interpolate(t, pos, q)
    assert ok.tolist() == [False, True, False, True, False]


def test_good_fixes_need_3d_low_hdop_and_enough_satellites():
    mode = np.array([3, 3, 3, 2])
    hdop = np.array([0.9, 3.0, 0.9, 0.9])
    nsat = np.array([9, 9, 4, 9])
    assert wc.good_fixes(np.arange(4), mode, hdop, nsat, True).tolist() == [1, 0, 0, 0]
    # no SKY reports (a sim session): the 3D fix alone
    assert wc.good_fixes(np.arange(4), mode, hdop, nsat, False).tolist() == [1, 1, 1, 0]


def test_fix_quality_takes_the_latest_sky_report_and_listed_satellites_only():
    fix_t = T0 + np.array([0, 10, 20]) * S
    sky = [
        {"t_ns": T0 + S // 2, "hdop": 0.8, "listed": True, "n_used": 9},  # just after fix 0
        {"t_ns": T0 + 6 * S, "hdop": 1.2, "listed": True, "n_used": 7},
        {"t_ns": T0 + 9 * S, "hdop": 1.5, "listed": False, "n_used": 0},  # no satellite list
    ]
    hdop, nsat = wc.fix_quality(fix_t, sky)
    assert hdop[0] == 0.8 and nsat[0] == 9
    assert hdop[1] == 1.5 and nsat[1] == 7  # satellites from the listed report 4 s back
    assert np.isnan(hdop[2]) and np.isnan(nsat[2])  # 11 s old: says nothing about the fix


def test_cuts_fall_only_in_the_moving_part_with_a_minute_of_walking_before():
    t, pos = _walk()
    cuts = wc.select_cuts(t, pos, T0, n=5)
    assert len(cuts) == 5
    # walking >= MIN_MOVING of WALK_BEFORE_S before (speed is a 10 s centred difference: 5 s slack)
    assert min(cuts) >= 150 + wc.MIN_MOVING * wc.WALK_BEFORE_S - 5
    assert max(cuts) <= 150 + 1200 - wc.MIN_MOVING * wc.HORIZON_S + 1  # still walking after
    assert np.all(np.diff(cuts) >= wc.MIN_SPACING_S)
    assert cuts == sorted(cuts)


def test_a_static_session_has_no_cut():
    t, pos = _walk(static_s=600, walk_s=0, end_s=0)
    assert wc.select_cuts(t, pos, T0) == []


def test_cuts_need_truth_at_the_horizon():
    t, pos = _walk(static_s=0, walk_s=500, end_s=0)  # walking for 500 s, then the log ends
    cuts = wc.select_cuts(t, pos, T0, n=5)
    assert cuts and max(cuts) + wc.HORIZON_S <= 499
    assert min(cuts) >= wc.MIN_MOVING * wc.WALK_BEFORE_S - 5
    assert wc.select_cuts(*_walk(static_s=0, walk_s=300, end_s=0), T0) == []


def test_score_takes_each_estimate_against_the_interpolated_truth():
    t, pos = _walk(static_s=0, walk_s=400, end_s=0)
    est_t = T0 + np.arange(0, 4000) * (S // 10)
    truth, _ = wc.interpolate(t, pos, est_t)
    est = truth + np.array([3.0, 4.0, 0.0])  # 5 m off everywhere
    hpl = np.full(len(est_t), 6.0)
    hpl[est_t >= T0 + 100 * S] = 4.0  # fails to bound from 60 s after the cut
    out = wc.score(est_t, est, hpl, t, pos, T0 + 40 * S, horizon_s=300.0)
    assert out["err_60s_m"] == pytest.approx(5.0) and out["err_300s_m"] == pytest.approx(5.0)
    assert out["n_scored"] == 3001
    assert out["hpl_bound"] == pytest.approx(600 / 3001)
    assert out["misleading"] == 2401
