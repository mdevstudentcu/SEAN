"""`analysis/spoof_detection.py` (#173, #189): the clean-tree guard, the alarm-at-onset note and
the summary header. Synthetic rows only; no scenario is run."""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "spoof_detection.py"
_spec = importlib.util.spec_from_file_location("spoof_detection", _PATH)
sd = importlib.util.module_from_spec(_spec)
sys.modules["spoof_detection"] = sd
_spec.loader.exec_module(sd)

NAN = math.nan


def _no_run(*_):
    raise AssertionError("ran the study")


def test_clean_commit():
    assert sd.clean_commit("97795d8")
    assert not sd.clean_commit("97795d8-dirty")
    assert not sd.clean_commit("uncommitted")


def test_refuses_committed_results_from_a_dirty_tree_req10(monkeypatch):
    monkeypatch.setattr(sd, "_commit", lambda: "abc1234-dirty")
    monkeypatch.setattr(sd, "_map", _no_run)
    with pytest.raises(SystemExit, match="abc1234-dirty"):
        sd.main(["--seeds", "1", "--mhss-seeds", "0"])


def test_dirty_tree_may_write_elsewhere_or_redraw(monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "_commit", lambda: "abc1234-dirty")
    monkeypatch.setattr(sd, "plan", lambda *_: [])
    monkeypatch.setattr(sd, "_map", lambda tasks, jobs: [])
    drawn = []
    monkeypatch.setattr(sd, "write", lambda data, out: drawn.append((data["meta"], out)))
    runs = tmp_path / "runs.json"
    sd.main(["--seeds", "1", "--mhss-seeds", "0", "--out", str(tmp_path), "--runs", str(runs)])
    assert drawn[-1][0]["commit"] == "abc1234-dirty"
    sd.main(["--redraw", "--runs", str(runs)])  # redraw into the committed folder: no new runs
    assert drawn[-1][1] == sd.OUT


def test_alarm_context():
    t = np.round(np.arange(0.1, 720.0, 0.1), 1)
    alarm = (t >= 1.5) & ~((t >= 682.1) & (t < 682.5))  # on before 150 s, off for 0.4 s
    never = np.zeros(len(t), bool)
    ctx = sd.alarm_context(t, alarm, never, 150.0)
    assert ctx["alarm_since_s"] == pytest.approx(1.5)
    assert ctx["alarm_clear_s"] == pytest.approx(532.1)
    assert ctx["suspected_s"] is None
    ctx = sd.alarm_context(t, t >= 151.1, t >= 161.0, 150.0)  # off at the attack's start
    assert ctx["alarm_since_s"] is None and ctx["alarm_clear_s"] is None
    assert ctx["suspected_s"] == pytest.approx(11.0)


def _row(est, delay, since, clear=NAN, suspected=NAN, seed=36):
    return {"case": "drone-many:spoof-jump", "estimator": est, "seed": seed,
            "detect_delay_s": delay, "attack_start_s": 150.0, "alarm_since_s": since,
            "alarm_clear_s": clear, "suspected_s": suspected}  # fmt: skip


def test_note_explains_a_detection_counted_only_after_an_alarm_restart():
    lines = sd.during_alarm(
        [
            _row("ekf-calibrated", 533.5, 1.5, clear=532.1),
            _row("ekf-calibrated-spoof", NAN, 1.5, suspected=11.0),
        ]
    )
    text = "\n".join(lines)
    assert "| drone-many | spoof-jump | `ekf-calibrated` | 36 | 1.5 | 533.5 | 532.1 | – |" in text
    assert "that restart is its 533.5 s detection" in text
    assert "`spoof_suspected` 11.0 s after" in text
    assert "no detection was lost" in text


def test_note_flags_a_lost_detection_as_a_defect():
    text = "\n".join(
        sd.during_alarm(
            [
                _row("ekf", 1.1, NAN),
                _row("ekf-spoof", NAN, NAN),
                _row("ekf-calibrated", NAN, 1.5),
            ]
        )
    )
    assert "`ekf-spoof` misses an attack `ekf` detects" in text and "defect" in text


def test_header_without_mhss_seeds():
    meta = {"commit": "abc1234", "command": "x", "minutes": 1.0, "seeds": 1, "mhss_seeds": 0}
    head = sd.summary({"meta": meta, "runs": []}).splitlines()[2]
    assert "`ekf-mhss` not run" in head and "0–-1" not in head


def test_monitor_adding_a_detection_is_not_a_defect():
    lines = sd.during_alarm([_row("ekf", NAN, NAN), _row("ekf-spoof", 131.0, NAN)])
    assert lines == []
