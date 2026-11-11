"""`analysis/drag_with_hopping.py` (#221): which scenario each case runs, the clean-tree guard
and the criterion line. Synthetic rows only; no scenario is run."""

import importlib.util
import math
import sys
from pathlib import Path

import pytest

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


def test_refuses_committed_results_from_a_dirty_tree_req10(monkeypatch):
    monkeypatch.setattr(dh, "_commit", lambda: "abc1234-dirty")
    monkeypatch.setattr(dh, "_map", lambda *_: pytest.fail("ran the study"))
    with pytest.raises(SystemExit, match="abc1234-dirty"):
        dh.main(["--seeds", "1"])


def _row(n, entry, est, seed, delay=NAN, fa=0.0):
    return {"case": dh.case_id(n, entry), "estimator": est, "seed": seed, "detect_delay_s": delay,
            "false_alarms_per_h": fa, "hazardous_epochs": 0, "err_at_alert": 10.0,
            "masts_10s": 20.0}  # fmt: skip


def _runs(detected: int, added_fa: bool):
    runs = []
    for s in range(50):
        for base, mon in dh.PAIRS:
            runs.append(_row(13, "spoof-ramp", base, s))
            runs.append(_row(13, "spoof-ramp", mon, s, 100.0 + s if s < detected else NAN))
            for entry in ("nominal", "outage"):
                runs.append(_row(13, entry, base, s))
                runs.append(_row(13, entry, mon, s, fa=5.0 if added_fa and s == 3 else 0.0))
    return runs


def test_criterion_needs_45_seeds_and_no_added_false_alarm():
    assert "criterion" in dh.verdict(_runs(45, False), 50)[0]
    assert ": met." in dh.verdict(_runs(45, False), 50)[0]
    assert "not met" in dh.verdict(_runs(44, False), 50)[0]
    assert "not met" in dh.verdict(_runs(50, True), 50)[0]
    assert dh.added_false_alarms(_runs(50, True), 13, "ekf-spoof", "ekf") == [
        ("nominal", 3),
        ("outage", 3),
    ]
    assert any("does not rescue" in x for x in dh.verdict(_runs(24, False), 50))
