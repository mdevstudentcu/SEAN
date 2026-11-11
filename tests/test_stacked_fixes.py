"""The stacked-fixes study (#218): its statistic, its rows and its clean-tree rule. No sim run."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

import stacked_fixes as study  # noqa: E402

from pnt.nav import ESTIMATORS  # noqa: E402


def test_p95_is_taken_across_runs_at_each_second():
    # 20 runs, 3 seconds: run i has error i at every second, except one large run at second 2
    curves = np.tile(np.arange(20.0)[:, None], (1, 3))
    curves[0, 2] = 1000.0
    p = study.p95_by_second(curves)
    assert p[0] == pytest.approx(np.percentile(np.arange(20.0), 95))
    assert p[2] > p[0]  # one run in 20 moves the 95th percentile, via interpolation


def test_worst_in_takes_the_whole_window_including_its_last_second():
    curve = np.array([1.0, 2.0, 9.0, 3.0, 50.0])
    assert study.worst_in(curve, 2) == 9.0
    assert study.worst_in(curve, 3) == 9.0
    assert study.worst_in(curve, 4) == 50.0
    assert study.worst_second(curve, 3) == 2


def test_every_row_uses_an_existing_estimator_and_spec():
    for row in study.rows():
        if row["estimator"] not in study.COMBOS:
            assert row["estimator"] in ESTIMATORS
        assert row["spec"] in study.SPECS
    # The combinations are the registered pieces' own hooks, not new filters
    for fn in study.COMBOS.values():
        assert fn.keywords["jump_guard"] is ESTIMATORS["ekf-guard"].keywords["jump_guard"]
    assert (
        study.COMBOS["ekf-learned-noise+guard"].keywords["noise_tau_s"]
        == ESTIMATORS["ekf-learned-noise"].keywords["noise_tau_s"]
    )


def test_the_ladder_has_at_most_eight_rows_per_family():
    for fam in study.FAMILIES:
        places = [
            r["ladder"] for r in study.rows() if r["family"] == fam and r["ladder"] is not None
        ]
        assert sorted(places) == list(range(len(places))) and len(places) <= 8


def test_seeds_parse_ranges_and_lists():
    assert study.parse_seeds("0-3") == [0, 1, 2, 3]
    assert study.parse_seeds("100-101,7") == [100, 101, 7]


def test_committed_results_refuse_a_dirty_tree():
    assert study._clean("ab12cd3")
    assert not study._clean("ab12cd3-dirty")
    assert not study._clean("uncommitted")
    assert not study._clean("ab12cd3", "?? analysis/new_script.py")
