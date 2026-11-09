"""One-at-a-time sensitivity sweep (issue #128)."""

import copy

import numpy as np
import pytest

from pnt.cli import main
from pnt.experiments import TOWERS, default_params, get_param, set_param, sweep
from pnt.sim.scenario import load

METRICS = ("fault_p95_m", "outage_p95_300s_m", "hpl_bound_worst", "hazardous_epochs")


@pytest.fixture(scope="module")
def short():
    """realistic-outage cut to 40 s, GPS lost at 20 s, so a sweep runs in seconds."""
    spec = load("realistic-outage")
    spec.update(duration_s=40, faults=[{"type": "outage", "source": "gnss", "start_s": 20}])
    return spec


def test_set_param_changes_only_the_named_value(short):
    before = copy.deepcopy(short)
    changed = set_param(short, "sources.lte.multipath.tau_s", 7.0)
    assert short == before  # the committed spec is untouched
    assert changed["sources"]["lte"]["multipath"]["tau_s"] == 7.0
    tau = before["sources"]["lte"]["multipath"]["tau_s"]
    assert set_param(changed, "sources.lte.multipath.tau_s", tau) == before
    towers = set_param(short, TOWERS, 6)
    assert get_param(towers, TOWERS) == 6 and get_param(short, TOWERS) == 4


@pytest.mark.parametrize("path", ["sources.lte.nope", "clock.drift_ppb.x", "sources.lte"])
def test_a_path_that_is_not_a_number_in_the_spec_is_an_error_naming_it(short, path):
    with pytest.raises(ValueError, match=path.replace(".", r"\.")):
        sweep(short, {path: [1.0]}, runs=1)


def test_sweep_rows_are_paired_and_change_one_value(short):
    path = "sources.lte.sigma_m"
    committed = get_param(short, path)
    rows = sweep(short, {path: [committed, 4 * committed]}, runs=2, estimator="baseline")
    assert [(r["parameter"], r["relative"]) for r in rows] == [
        ("baseline (as committed)", 1.0),
        (path, 1.0),
        (path, 4.0),
    ]
    # Same seeds: the committed value reproduces the baseline row exactly (the 40 s run has no
    # 300 s slice, so that one is nan in both), and a real change moves it
    assert np.array_equal(
        [rows[1][k] for k in METRICS], [rows[0][k] for k in METRICS], equal_nan=True
    )
    assert rows[2]["fault_p95_m"] != rows[0]["fault_p95_m"]


def test_default_sweep_brackets_what_the_scenario_has():
    realistic = default_params(load("realistic-long-outage"))
    assert realistic["sources.lte.sigma_m"] == [12.5, 25.0, 100.0, 200.0]  # committed 50 m
    assert TOWERS in realistic and "tower_clocks.site.drift_rw_mps" in realistic
    synthetic = default_params(load("gps-outage"))  # no multipath, dropout or tower clocks
    assert "sources.lte.multipath.sigma_m" not in synthetic
    assert "tower_clocks.site.drift_rw_mps" not in synthetic
    assert synthetic[TOWERS] == [2, 3, 6, 8]


def test_command_line_rejects_a_malformed_param():
    with pytest.raises(SystemExit, match="PATH=v1"):
        main(["experiment", "sweep", "gps-outage", "--param", "sources.lte.sigma_m"])
    with pytest.raises(SystemExit, match="only for the sweep"):
        main(["experiment", "grid", "gps-outage", "--param", "towers=3"])
