"""`analysis/drag_with_hopping.py` (#221, #258): which scenario each case runs, the rule-before
estimator, the clean-tree guard and the criterion line. Synthetic rows only; no scenario is
run."""

import importlib.util
import math
import sys
from pathlib import Path

import pytest

from pnt.core.measurement import Measurement

_DIR = Path(__file__).parents[1] / "analysis"
sys.path.insert(0, str(_DIR))  # it imports spoof_detection and hopping_study as siblings
_spec = importlib.util.spec_from_file_location("drag_with_hopping", _DIR / "drag_with_hopping.py")
dh = importlib.util.module_from_spec(_spec)
sys.modules["drag_with_hopping"] = dh
_spec.loader.exec_module(dh)

NAN = math.nan


def test_cases_take_the_committed_entries_and_vary_only_the_carriers():
    hop = dh.load("challenge-drone-hop-spoof-ramp")
    scan = hop["sources"]["lte"]["cells_from"]["earfcn"]
    one = dh.spec_of(dh.case_id(1, "spoof-ramp"))
    six = dh.spec_of(dh.case_id(6, "spoof-ramp"))
    all_ = dh.spec_of(dh.case_id(13, "spoof-ramp"))
    assert one["sources"]["lte"] == dh.load("challenge-drone-spoof-ramp")["sources"]["lte"]
    assert six["sources"]["lte"]["cells_from"]["earfcn"] == scan[:6]
    assert all_["sources"]["lte"] == hop["sources"]["lte"]
    for s in (one, six, all_):  # the same 2 m/s ramp on every leg
        assert s["faults"] == hop["faults"]
    assert (
        dh.spec_of(dh.case_id(13, "outage"))["faults"]
        == dh.load("challenge-drone-hop-outage")["faults"]
    )
    with pytest.raises(ValueError):
        dh.spec_of(dh.case_id(14, "nominal"))


def test_stress_cases_change_only_the_dwell_or_the_ramp_rate():
    hop = dh.load("challenge-drone-hop-spoof-ramp")
    slow = dh.spec_of("13-carrier:spoof-ramp@0.5")
    assert slow["faults"] == [{**hop["faults"][0], "rate_mps": 0.5}]
    assert slow["sources"] == hop["sources"]
    dwell = dh.spec_of("13-carrier/dwell2:nominal")
    assert dwell["sources"]["lte"]["hop"] == {**hop["sources"]["lte"]["hop"], "dwell_s": 2.0}
    assert dwell["faults"] == []
    jump = dh.spec_of("13-carrier:spoof-jump")["faults"]
    assert jump[0]["type"] == "spoof_jump" and "end_s" not in jump[0]  # held to the end
    with pytest.raises(ValueError):
        dh.spec_of("13-carrier:nominal@1")
    assert all(dh.parse(c)[0] == 13 for c in dh.STRESS)


def test_rule_before_drops_the_carrier_so_every_reading_is_one_carrier():
    """`towers_test` treats rows without a carrier as one carrier, the rule before #258."""
    assert dh.BEFORE in dh.ESTIMATORS and dh.CALIBRATED[1] in dh.ESTIMATORS
    assert dh.ESTIMATORS[dh.BEFORE].keywords["monitor"] is dh.EveryEpochMonitor

    class Main:
        x = [0.0] * 6
        origin_llh = (45.0, -75.0, 70.0)
        spoof_alarm = False

    mon = dh.EveryEpochMonitor(Main())
    mon._fix = (0, [0.0, 0.0, 0.0])
    mon._emitters["lte:2460:1"] = [1000.0, 0.0, 0.0]
    meta = {"earfcn": 2460, "site": "enb:1"}
    rec = Measurement(t_ns=0, source="lte", kind="pseudorange", emitter="lte:2460:1",
                      value=(1000.0,), sigma=(1.0,), meta=meta)  # fmt: skip
    mon._tower_reading(rec)
    assert len(mon._rows) == 1 and len(mon._rows[0]) == 5
    plain = dh.SpoofMonitor(Main())
    plain._fix, plain._emitters = mon._fix, mon._emitters
    plain._tower_reading(rec)
    assert plain._rows[0] == (*mon._rows[0], 2460)


def test_refuses_committed_results_from_a_dirty_tree_req10(monkeypatch):
    monkeypatch.setattr(dh, "_commit", lambda: "abc1234-dirty")
    monkeypatch.setattr(dh, "_map", lambda *_: pytest.fail("ran the study"))
    with pytest.raises(SystemExit, match="abc1234-dirty"):
        dh.main(["--seeds", "1"])


def _row(n, entry, est, seed, delay=NAN, fa=0.0):
    return {"case": dh.case_id(n, entry), "estimator": est, "seed": seed, "detect_delay_s": delay,
            "false_alarms_per_h": fa, "hazardous_epochs": 0, "misleading_epochs": 0,
            "err_at_alert": 10.0, "masts_10s": 20.0, "tower_test_30/10_sigma_med_m": 20.0,
            "tower_test_120/20_sigma_med_m": 40.0, "tower_test_30/10_thr_med": 12.5}  # fmt: skip


def _runs(detected: int, added_fa: bool):
    runs = []
    for s in range(50):
        for est in dh.PLAIN:
            mon = est == "ekf-spoof"
            runs.append(_row(13, "spoof-ramp", est, s, 100.0 + s if mon and s < detected else NAN))
            for entry in ("nominal", "outage"):
                runs.append(_row(13, entry, est, s, fa=5.0 if mon and added_fa and s == 3 else 0))
    return runs


def test_criterion_needs_45_seeds_and_no_added_false_alarm():
    assert "criterion" in dh.verdict(_runs(45, False), 50)[0]
    assert ": met." in dh.verdict(_runs(45, False), 50)[0]
    assert "not met" in dh.verdict(_runs(44, False), 50)[0]
    assert "not met" in dh.verdict(_runs(50, True), 50)[0]
    pairs = [dh.case_id(13, "nominal"), dh.case_id(13, "outage")]
    assert dh.added_false_alarms(_runs(50, True), pairs, "ekf-spoof", "ekf") == (
        [("nominal", 3), ("outage", 3)],
        100,
    )
    # T4's 30 s: 60 m moved against the 30 s test's 20 m sigma, said with the numbers
    line = dh.verdict(_runs(45, False), 50)[1]
    assert "not met" in line and "60 m is 3.0 sigma" in line and "about 5.0 sigma" in line


def test_summary_and_same_as_before_on_synthetic_rows():
    runs = _runs(45, False)
    assert dh.same_as_before(runs, 13) == (5 * 0 + 50 * 2 + 5, 150)  # ramp seeds 45-49 agree
    text = dh.summary({"runs": runs, "meta": {"commit": "abc1234", "command": "x", "seeds": 50,
                                              "minutes": 1.0, "host": "h"}})  # fmt: skip
    assert "| 13 (20.0) | `ekf-spoof` | 45/50 |" in text
    assert "0 of 100" in text
