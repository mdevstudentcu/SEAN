"""The tower-count study (analysis/tower_count.py, #208): its statistic, tower choice and filters.

Counts of the real cell table are regression guards on the committed table, not targets.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.sim.scenario import load

_PATH = Path(__file__).parents[1] / "analysis" / "tower_count.py"
_SPEC = importlib.util.spec_from_file_location("tower_count", _PATH)
tc = importlib.util.module_from_spec(_SPEC)
sys.modules["tower_count"] = tc
_SPEC.loader.exec_module(tc)


def test_t1_takes_the_p95_across_runs_at_each_second_and_the_worst_second():
    # 20 runs; run k's error is k m everywhere, plus a 40 m spike in run 19 at second 10 only.
    errors = np.tile(np.arange(20.0)[:, None], (1, 301))
    errors[19, 10] = 40.0
    stat = tc.t1(errors)
    # Across-runs p95 of 0..19 is 18.05; with the spike, 18 + 0.05 * (40 - 18) = 19.1
    assert stat["p95"][0] == pytest.approx(np.percentile(np.arange(20.0), 95))
    assert stat["worst_m"] == pytest.approx(19.1) == stat["p95"][10]
    assert stat["holds_25m_s"] == 300 and stat["holds_50m_s"] == 300 and stat["fallback_met"]


def test_t1_holds_until_the_first_second_over_the_target():
    errors = np.tile(np.arange(301.0) / 5.0, (20, 1))  # 0.2 m/s for every run
    stat = tc.t1(errors)
    assert stat["holds_25m_s"] == 126  # 25.2 m at 126 s is the first over 25 m
    assert stat["holds_50m_s"] == 251
    assert stat["fallback_met"]  # 24 m at 120 s


def test_t1_counts_a_second_without_an_estimate_as_failing():
    errors = np.ones((20, 301))
    errors[:, 200:] = np.nan
    stat = tc.t1(errors)
    assert stat["holds_25m_s"] == 200 and stat["worst_m"] >= tc.NO_OUTPUT_M
    assert tc._m(stat["worst_m"]) is None


def test_leg_spec_changes_only_the_studys_keys():
    committed = load(tc.LEG)
    spec = tc.leg_spec("committed")
    assert spec["duration_s"] == tc.DURATION_S
    assert spec["sources"]["lte"]["hearing"] == tc.HEARING
    assert spec["sources"]["lte"]["told_sigma_m"] == committed["sources"]["lte"]["told_sigma_m"]
    assert committed["sources"]["lte"]["hearing"] == {"model": "link_budget"}  # not mutated
    honest = tc.leg_spec("honest")["sources"]["lte"]
    assert "told_sigma_m" not in honest and honest["sigma_m"] == 50.0
    clean = tc.leg_spec("clean")["sources"]["lte"]
    assert clean["sigma_m"] == 5.0 and "multipath" not in clean
    assert clean["told_position_sigma_m"] == 0.0
    with pytest.raises(ValueError):
        tc.leg_spec("rosy")


def _info():
    # Three sites within 3 km and one beyond, powers in a known order
    return {
        1: {"emitters": ["lte:1:1"], "km": 0.5, "power_dbm": -50.0, "enu": np.zeros(3)},
        2: {"emitters": ["lte:1:2"], "km": 1.0, "power_dbm": -40.0, "enu": np.zeros(3)},
        3: {"emitters": ["lte:1:3"], "km": 2.0, "power_dbm": -60.0, "enu": np.zeros(3)},
        4: {"emitters": ["lte:1:4"], "km": 5.0, "power_dbm": -45.0, "enu": np.zeros(3)},
    }


def test_choose_strongest_all_and_random():
    info = _info()
    assert tc.choose(info, "strongest", 2) == [2, 4]
    assert tc.choose(info, "strongest", "all") == [1, 2, 3]  # within 3 km only
    a = tc.choose(info, "random", 2, seed=5)
    assert a == tc.choose(info, "random", 2, seed=5) and set(a) <= {1, 2, 3}
    assert {tuple(tc.choose(info, "random", 2, seed=s)) for s in range(20)} != {tuple(a)}
    with pytest.raises(ValueError):
        tc.choose(info, "random", 4)


def _m(source, emitter="", kind="pseudorange"):
    return Measurement(t_ns=0, source=source, kind=kind, emitter=emitter, value=(0.0,), sigma=(1,))


def test_keep_filters_towers_baro_and_imu():
    ms = [
        _m("lte", "lte:1:1"),
        _m("lte", "lte:1:2"),
        _m("baro", kind="altitude"),
        _m("imu", kind="accel_gyro"),
        _m("gnss", kind="position"),
    ]
    kept = tc.keep(ms, {"lte:1:2"}, baro=False, imu=True)
    assert [(m.source, m.emitter) for m in kept] == [
        ("lte", "lte:1:2"),
        ("imu", ""),
        ("gnss", ""),
    ]
    assert len(tc.keep(ms, set(), baro=True, imu=False)) == 2


def test_dops_need_as_many_sites_as_unknowns():
    rx = np.array([[0.0, 0.0, 40.0]])
    two = np.array([[1000.0, 0.0, 40.0], [0.0, 1000.0, 40.0]])
    three = np.vstack([two, [[-800.0, -600.0, 40.0]]])
    d2, d3 = tc.dops(two, rx), tc.dops(three, rx)
    assert np.isnan(d2["baro"][0]) and np.isnan(d2["no_baro"][0])
    assert d2["baro_held_clock"][0] == pytest.approx(np.sqrt(2))  # two orthogonal ranges
    assert np.isfinite(d3["baro"][0]) and np.isnan(d3["no_baro"][0])


def test_sites_on_the_committed_table():
    info = tc.sites(tc.leg_spec("committed"))
    assert len(info) == 86  # matched eNBs on Rogers EARFCN 2460 (regression guard)
    assert len(tc.choose(info, "strongest", "all")) == 17
    assert tc.choose(info, "strongest", 1) == [30018]  # the strongest at Carleton (PR #133)
