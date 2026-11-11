"""analysis/vor_ablation.py (#13, #94): the paired VOR ablation's logic."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Measurement

_SPEC = importlib.util.spec_from_file_location(
    "vor_ablation", Path(__file__).resolve().parents[1] / "analysis" / "vor_ablation.py"
)
ablation = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ablation)


def _m(source, kind):
    return Measurement(t_ns=0, source=source, kind=kind, value=(0.0,), sigma=(1.0,))


def test_arms_drop_only_the_vor_records():
    meas = [_m("gnss", "position_enu"), _m("vor", "bearing"), _m("lte", "pseudorange")]
    a = ablation.arms(meas)
    assert a["+VOR"] == meas
    assert [m.source for m in a["towers"]] == ["gnss", "lte"]


def _result(p95_towers, p95_vor, hpl=1.0):
    def cell(p95):
        return {
            "metrics": {
                "fault_h_p95_m": p95,
                "fault_h_max_m": p95 + 10,
                "h_rmse_m": p95 / 2,
                "hpl_bound_frac": hpl,
                "misleading_epochs": 0.0 if hpl == 1.0 else 2.0,
                "h_nees_mean": 2.0,
            },
            "curve": np.array([p95]),
        }

    return {("ekf", "towers"): cell(p95_towers), ("ekf", "+VOR"): cell(p95_vor)}


def test_summary_pairs_by_seed_and_names_the_worst_run():
    results = [_result(40, 30), _result(50, 55), _result(30, 30, hpl=0.9)]
    s = ablation.summarize(results, ("ekf",), seeds=[7, 8, 9])
    t, v = s["ekf towers"], s["ekf +VOR"]
    assert t["fault_h_p95_m_median"] == 40 and v["fault_h_p95_m_median"] == 30
    assert t["fault_h_p95_m_worst"] == 50 and t["fault_h_p95_m_worst_seed"] == 8
    assert v["fault_h_max_m_worst"] == 65 and v["fault_h_max_m_worst_seed"] == 8
    # paired change: -10, +5, 0 -> one better, one worse, one tied
    assert v["p95_change_m_median"] == 0 and v["p95_change_m_min"] == -10
    assert v["p95_change_m_max"] == 5
    assert (v["seeds_better"], v["seeds_worse"]) == (1, 1)
    assert v["hpl_bound_frac_min"] == pytest.approx(0.9)
    assert v["hpl_bound_frac_mean"] == pytest.approx(2.9 / 3)
    assert v["misleading_epochs_total"] == 2
    assert "p95_change_m_median" not in t
    md = ablation.table(s)
    assert "| `ekf` | +VOR | 30.0 / 55.0 (8) |" in md and "| 1 / 1 |" in md


def test_one_seed_towers_arm_scores_the_plain_approach():
    from pnt import metrics, nav
    from pnt.sim.scenario import T0_NS, generate, load

    out = ablation.one_seed(0, ("ekf",))
    run = generate(load("uc02-yow-approach"), seed=0)
    est = list(nav.estimate("ekf", run.measurements, origin_llh=run.spec["origin_llh"]))
    plain = metrics.score(est, run.truth, run.spec, T0_NS)
    assert out[("ekf", "towers")]["metrics"]["fault_h_p95_m"] == plain.fault_h_p95_m
    assert out[("ekf", "+VOR")]["metrics"]["fault_h_p95_m"] != plain.fault_h_p95_m
