"""The model-mismatch study (analysis/model_mismatch.py, #118): its worlds and injected multipath.

Statistical bounds are regression guards with margin for the seeds used, not targets.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.sim.scenario import load

_PATH = Path(__file__).parents[1] / "analysis" / "model_mismatch.py"
_SPEC = importlib.util.spec_from_file_location("model_mismatch", _PATH)
mm = importlib.util.module_from_spec(_SPEC)
sys.modules["model_mismatch"] = mm
_SPEC.loader.exec_module(mm)


def test_tuning_and_report_seeds_are_disjoint():
    assert not set(mm.TUNING_SEEDS) & set(mm.REPORT_SEEDS)
    assert len(mm.REPORT_SEEDS) == len(mm.TUNING_SEEDS) == 50


@pytest.mark.parametrize("form", mm.FORMS)
def test_multipath_forms_keep_the_size(form):
    rng = np.random.default_rng(0)
    t = np.arange(0.0, 360.0, 1.0)
    first = np.array([mm.multipath(rng, t, form, 50.0, 30.0)[0] for _ in range(2000)])
    assert np.std(first) == pytest.approx(50.0, rel=0.1)  # every form starts at the GM's size


def test_bias_step_holds_then_jumps_and_white_does_not_hold():
    rng = np.random.default_rng(1)
    t = np.arange(0.0, 3600.0, 1.0)
    step = mm.multipath(rng, t, "bias-step", 50.0, 30.0)
    jumps = np.count_nonzero(np.diff(step))
    assert 60 < jumps < 180  # about 3600 / 30 redraws
    white = mm.multipath(rng, t, "white", 50.0, 30.0)
    assert abs(np.corrcoef(white[:-1], white[1:])[0, 1]) < 0.1


def test_random_walk_grows_past_the_gauss_markov_size():
    rng = np.random.default_rng(2)
    t = np.arange(0.0, 360.0, 1.0)
    end = np.array([mm.multipath(rng, t, "random-walk", 50.0, 30.0)[-1] for _ in range(500)])
    # var = sigma^2 (1 + 2 T / tau): about 50 * 5 m after 360 s
    assert np.std(end) == pytest.approx(50.0 * np.sqrt(1 + 2 * 359 / 30), rel=0.15)


def test_unknown_form_is_refused():
    with pytest.raises(ValueError, match="form"):
        mm.multipath(np.random.default_rng(0), np.arange(3.0), "pink", 1.0, 1.0)


def test_worlds_change_only_their_parameter():
    base = load(mm.SCENARIO)
    by_label = {c[1]: c for c in mm.CASES}
    spec, inj = mm.world(base, by_label["multipath sigma x4"][3])
    assert inj is None
    assert (
        spec["sources"]["lte"]["multipath"]["sigma_m"]
        == 4 * base["sources"]["lte"]["multipath"]["sigma_m"]
    )
    assert (
        spec["sources"]["lte"]["multipath"]["tau_s"]
        == base["sources"]["lte"]["multipath"]["tau_s"]
    )
    spec, _ = mm.world(base, by_label["tower clock drift rw x5"][3])
    for level in ("builder", "site"):
        assert spec["tower_clocks"][level]["drift_rw_mps"] == pytest.approx(
            5 * base["tower_clocks"][level]["drift_rw_mps"]
        )
    spec, inj = mm.world(base, by_label["multipath white"][3])
    assert "multipath" not in spec["sources"]["lte"]
    assert inj == {"form": "white", **base["sources"]["lte"]["multipath"]}
    assert "multipath" in base["sources"]["lte"]  # the loaded spec is left alone


def test_inject_moves_only_lte_pseudoranges():
    from pnt.sim.scenario import generate

    spec = {**load("realistic-nominal"), "duration_s": 20}
    meas = generate(spec, seed=0).measurements
    out = mm.inject(meas, {"form": "bias-step", "sigma_m": 50.0, "tau_s": 30.0}, seed=0)
    assert len(out) == len(meas)
    moved = [(a, b) for a, b in zip(meas, out, strict=True) if a.value != b.value]
    assert moved and all(a.source == "lte" and a.kind == "pseudorange" for a, _ in moved)
    assert all(a.t_ns == b.t_ns and a.emitter == b.emitter for a, b in moved)
    # one level per tower over 20 s of a 30 s hold, mostly: the shifts repeat within a tower
    first = {}
    for a, b in moved:
        first.setdefault(a.emitter, []).append(b.value[0] - a.value[0])
    assert any(len(set(np.round(v, 6))) < len(v) for v in first.values())


def test_case_metrics_scores_both_estimators_on_the_same_run():
    spec = {**load("realistic-nominal"), "duration_s": 20}
    inj = {"form": "white", "sigma_m": 50.0, "tau_s": 30.0}
    out = mm.case_metrics(spec, inj, seed=0, config={"multipath_ratio": 2.0})
    assert set(out) == set(mm.ESTIMATORS)
    assert out["ekf"].n == out["ekf-calibrated"].n > 0
