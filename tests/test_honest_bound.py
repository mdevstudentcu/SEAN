"""analysis/honest_bound.py (#226): scenario keys, the per-epoch collection and the statistics."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

import honest_bound as hb  # noqa: E402

from pnt.sim.scenario import T0_NS  # noqa: E402


def test_scenario_keys_name_the_committed_entries():
    one = hb.spec_of("drone/outage/1c")
    assert one["sources"]["lte"]["cells_from"]["earfcn"] == 2460
    six = hb.spec_of("drone/spoof-jump/6c")
    assert len(six["sources"]["lte"]["cells_from"]["earfcn"]) == 6
    assert [f["type"] for f in six["faults"]] == ["spoof_jump"]
    assert len(hb.spec_of("drone/outage/13c")["sources"]["lte"]["cells_from"]["earfcn"]) == 13
    assert hb.spec_of("timing/outage")["faults"][0]["type"] == "outage"


@pytest.mark.parametrize("k", [0.5, 2.0])
def test_mismatch_scales_the_truth_not_what_the_records_report(k):
    base = hb.spec_of("drone/outage/1c")["sources"]["lte"]
    lte = hb.spec_of(f"drone/outage/1c/lte*{k:g}")["sources"]["lte"]
    assert lte["sigma_m"] == k * base["sigma_m"]
    assert lte["multipath"]["sigma_m"] == k * base["multipath"]["sigma_m"]
    assert lte["multipath"]["tau_s"] == base["multipath"]["tau_s"]
    assert lte["told_sigma_m"] == base["told_sigma_m"]


def test_per_second_takes_the_epoch_on_each_whole_second():
    t = T0_NS + np.arange(0, 30) * 100_000_000  # 0.0 .. 2.9 s
    x = np.arange(30, dtype=float)
    out = hb.per_second(t, x, 4)
    assert out[:3].tolist() == [0.0, 10.0, 20.0] and np.isnan(out[3])


def _run(seed, err, hpl, loss_s=0.0):
    n = len(err)
    err_s = np.asarray(err, np.float32)
    hpl_s = np.asarray(hpl, np.float32)
    return {
        "seed": seed, "n": n, "n_win": n, "above": int(np.sum(err_s > hpl_s)),
        "above_win": int(np.sum(err_s > hpl_s)), "hazardous": 0, "hazardous_runs": 0,
        "misleading": 0, "under_al_win": int(np.sum(hpl_s <= 50)), "false_alarms_per_h": 0.0,
        "run_s": 1.0, "err_s": err_s, "hpl_s": hpl_s, "loss_s": loss_s, "start_s": loss_s,
        "first_unsafe_s": float("nan"), "nees_sum_win": 2.0 * n, "nees_over_k2_win": 0,
    }  # fmt: skip


def test_tightness_is_median_hpl_over_p95_error_per_second():
    n = hb.TIGHT_WINDOW_S + 1
    # 20 runs: error 1..20 m at every second, HPL 30 m: p95 over runs = 19.05, ratio 30 / 19.05
    runs = [_run(s, [s + 1.0] * n, [30.0] * n) for s in range(20)]
    c = hb.cell(runs)
    assert c["tightness"] == pytest.approx(30.0 / np.percentile(np.arange(1, 21), 95))
    assert c["above_win"] == 0.0 and c["worst_run"] == 0.0
    assert c["nees_mean_win"] == pytest.approx(2.0)


def test_worst_run_is_the_largest_share_above():
    n = 10
    runs = [_run(0, [1.0] * n, [2.0] * n), _run(1, [3.0] * 3 + [1.0] * 7, [2.0] * n)]
    c = hb.cell(runs)
    assert c["above_win"] == pytest.approx(3 / 20)
    assert c["worst_run"] == pytest.approx(0.3) and c["worst_seed"] == 1


def test_the_stress_plan_covers_every_drone_entry_on_three_carrier_counts():
    tasks = hb.plan_stress(list(range(3)))
    keys = {t[0] for t in tasks}
    for entry in hb.DRONE_ENTRIES:
        for n in (1, 6, 13):
            assert f"drone/{entry}/{n}c" in keys
    jump = [t for t in tasks if t[0] == "drone/spoof-jump/1c"][0]
    assert "ekf-honest-guard" in jump[2] and "ekf-learned-noise+guard" in jump[2]
