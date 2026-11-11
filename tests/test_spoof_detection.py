"""`analysis/spoof_detection.py` (#173, #189): the clean-tree guard. No scenario is run."""

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "spoof_detection.py"
_spec = importlib.util.spec_from_file_location("spoof_detection", _PATH)
sd = importlib.util.module_from_spec(_spec)
sys.modules["spoof_detection"] = sd
_spec.loader.exec_module(sd)


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
