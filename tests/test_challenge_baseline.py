"""The challenge baseline script (#150) end to end on one short case: one entry, one seed, one
estimator, into a temporary directory. REQ-10: the summary names its commit and seeds. Also
ADR-0034's T1 statistic (amendment of 2026-11-10) through its two helpers."""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

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
    # each run keeps its horizontal error at every second 0..300 s after GPS loss
    curve = data["curves"]["challenge-drone-outage"]["ekf"]["0"]
    assert len(curve) == cb.CURVE_S + 1 and None not in curve
    assert data["errors"] == {}
    assert (tmp_path / "t1_drone.png").stat().st_size > 0
    assert json.loads((tmp_path / "t1_curves.json").read_text())["curves"]["ekf"]["runs"] == 1

    # --redraw rewrites the same summary from runs.json without running
    (tmp_path / "summary.md").unlink()
    cb.main(["--redraw", "--out", str(tmp_path)])
    assert (tmp_path / "summary.md").read_text() == summary


def test_t1_is_the_worst_second_of_the_p95_across_runs_adr0034():
    # 20 runs, 4 seconds: at each second the 95th percentile across runs, then the worst second
    runs = [[float(i), 1.0, 2.0 * i, 0.0] for i in range(20)]
    p95 = cb.across_run_p95(runs)
    assert np.allclose(p95, np.percentile(np.array(runs), 95, axis=0))
    # second 2 (p95 of 0, 2, ..., 38) is the worst within 0..3 s; within 0..1 s it is second 0
    assert cb.worst_in(p95, 3) == (float(p95[2]), 2)
    assert cb.worst_in(p95, 1) == (float(p95[0]), 0)
    # not the per-run p95: one run far out at one second lifts that second's curve, and that
    # second decides even though each run's own p95 over time hides it
    runs = [[1.0] * 20 for _ in range(19)] + [[1.0] * 19 + [500.0]]
    assert np.percentile(runs[-1], 95, method="lower") == 1.0
    assert cb.worst_in(cb.across_run_p95(runs), 19)[1] == 19


def test_t1_window_not_covered_is_not_scored():
    # a second of the window with no value (the run or the outage ended) gives no verdict
    assert math.isnan(cb.worst_in(np.array([1.0, np.nan, 2.0]), 2)[0])
    assert math.isnan(cb.worst_in(np.array([1.0, 2.0]), 2)[0])


def test_bound_figure_shares_are_the_t5_metrics_req02(tmp_path):
    # --bound re-runs only the T5 bound figure's runs, checks them against runs.json, and keeps
    # every epoch's error and HPL: the shares drawn come from the epochs T5 scores
    args = ["--legs", "drone", "--entries", "outage", "spoof-jump", "--estimators", "ekf"]
    cb.main([*args, "--seeds", "1", "--jobs", "1", "--out", str(tmp_path)])
    cb.main(["--bound", "--jobs", "1", "--out", str(tmp_path)])

    data = json.loads((tmp_path / "runs.json").read_text())
    epochs, meta = cb.load_bound(tmp_path / cb.BOUND_FILE)
    assert meta["commit"] == _commit()
    for entry in ("outage", "spoof-jump"):
        scn = f"challenge-drone-{entry}"
        st = cb.bound_stats(epochs[scn]["ekf"])
        run = data["runs"][scn]["ekf"]["0"]
        assert st["worst_bound"] == pytest.approx(run[cb.FIELDS.index("hpl_bound_frac")], abs=1e-5)
        assert st["above"] == pytest.approx(1 - st["worst_bound"])  # one run
        assert st["hazardous"] == run[cb.FIELDS.index("hazardous_epochs")]
    png = (tmp_path / "t5_bound.png").read_bytes()
    assert "t5_bound.png" in (tmp_path / "summary.md").read_text()
    cb.main(["--redraw", "--out", str(tmp_path)])
    assert (tmp_path / "t5_bound.png").read_bytes() == png  # byte for byte
