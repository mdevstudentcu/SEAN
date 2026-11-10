"""The challenge baseline script (#150) end to end on one short case: one entry, one seed, one
estimator, into a temporary directory. REQ-10: the summary names its commit and seeds."""

import importlib.util
import json
import sys
from pathlib import Path

from pnt.cli import _commit

_PATH = Path(__file__).parents[1] / "analysis" / "challenge_baseline.py"
_SPEC = importlib.util.spec_from_file_location("challenge_baseline", _PATH)
cb = importlib.util.module_from_spec(_SPEC)
sys.modules["challenge_baseline"] = cb
_SPEC.loader.exec_module(cb)


def test_one_entry_one_seed_names_commit_and_seeds_req10(tmp_path):
    args = ["--legs", "drone", "--entries", "outage", "--estimators", "ekf"]
    args += ["--seeds", "1", "--jobs", "1", "--out", str(tmp_path)]
    cb.main(args)

    summary = (tmp_path / "summary.md").read_text()
    assert f"**Commit:** `{_commit()}`" in summary
    assert "**Seeds:** 0" in summary
    assert "| T1 | drone, `outage` |" in summary
    assert "`ekf-base`: not run" in summary  # the legs have no reference station
    data = json.loads((tmp_path / "runs.json").read_text())
    run = data["runs"]["challenge-drone-outage"]["ekf"]["0"]
    assert isinstance(run, list) and len(run) == len(cb.FIELDS)
    assert data["errors"] == {}
    assert (tmp_path / "t1_drone.png").stat().st_size > 0

    # --redraw rewrites the same summary from runs.json without running
    (tmp_path / "summary.md").unlink()
    cb.main(["--redraw", "--out", str(tmp_path)])
    assert (tmp_path / "summary.md").read_text() == summary
