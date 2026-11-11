"""The stacked-fixes study (#218): its statistic, its rows and its clean-tree rule. No sim run."""

import math
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


# --- the measured-sizes variant (#257) ---------------------------------------------------------
def _lte(t_s: float, snr_db: float, pci: int = 7, earfcn: int = 2460, n_epochs: int = 200):
    from pnt.core.measurement import Measurement

    return Measurement(
        t_ns=study.T0_NS + int(round(t_s * 1e9)), source="lte", kind="pseudorange",
        emitter=f"lte:{earfcn}:{pci}", value=(1000.0,), sigma=(2.0,),
        meta={"snr_db": snr_db, "n_epochs": n_epochs, "earfcn": earfcn, "pci": pci, "arc": 0},
    )  # fmt: skip


def _spec():
    return {"duration_s": 720.0, "sources": {"lte": {"multipath": {"sigma_m": 50.0}}}}


def test_measured_white_noise_follows_adr0036_by_snr_and_is_paired_across_variants():
    from pnt.nav import told_sigma

    strong = [_lte(t, 10.0, pci=1) for t in range(700)]
    weak = [_lte(t, -12.0, pci=2) for t in range(700)]
    out = study.measured_records(strong + weak, 3, _spec())
    for recs, snr in ((out[:700], 10.0), (out[700:], -12.0)):
        dev = np.array([m.value[0] for m in recs]) - 1000.0
        want = told_sigma.white_sigma_m(snr, 200)
        assert np.std(dev) == pytest.approx(want, rel=0.1)
        assert all(m.sigma == (2.0,) for m in recs)  # told as generated
    # Same seed, other variant: the same white draw on every record it keeps
    told = study.measured_records(strong, 3, _spec(), true_told=True)
    assert [m.value for m in told] == [m.value for m in out[:700]]
    assert told[0].sigma[0] == pytest.approx(math.hypot(told_sigma.white_sigma_m(10.0, 200), 50))
    kept = study.measured_records(strong, 3, _spec(), hop_loss=study.HOP_LOSS)
    assert 0.4 < len(kept) / len(strong) < 0.6
    assert {m.t_ns: m.value for m in kept}.items() <= {m.t_ns: m.value for m in out[:700]}.items()


def test_arc_model_reproduces_the_measured_reacquisition_steps():
    # The model is sized from lte-reacq-steps (after the fix); its steps must land where those
    # two sessions' do: median about 10 m, 16 to 17 % over 100 m, p90 between their 462 and
    # 1,033 m. Bounds are the measured spread, not a target.
    rng = np.random.default_rng(0)
    steps, n_arcs, span = [], 0, 0.0
    for _ in range(3000):
        starts, off = study.arc_offsets(rng, 720.0)
        steps += list(np.abs(np.diff(off)))
        n_arcs += len(starts)
        span += 720.0
    steps = np.array(steps)
    assert n_arcs / span == pytest.approx(study.ARC_RATE_HZ, rel=0.03)
    assert 9.0 < np.median(steps) < 11.5
    shares = [r["steps_over_100m"] for r in study.REACQ_AFTER.values()]
    assert min(shares) < np.mean(steps > 100) < max(shares)
    lo = min(r["step_p90_m"] for r in study.REACQ_AFTER.values())
    hi = max(r["step_p90_m"] for r in study.REACQ_AFTER.values())
    assert lo < np.percentile(steps, 90) < hi


def test_arc_steps_move_the_range_and_count_arcs():
    recs = [_lte(t, 10.0) for t in range(720)]
    plain = study.measured_records(recs, 5, _spec())
    arcs = study.measured_records(recs, 5, _spec(), arcs=True)
    k = np.array([m.meta["arc"] for m in arcs])
    assert k[0] == 0 and np.all(np.diff(k) >= 0) and k[-1] > 5
    jump = np.array([a.value[0] - p.value[0] for a, p in zip(arcs, plain, strict=True)])
    assert np.allclose(jump[k == k[0]], jump[0])  # one offset per arc


def test_measured_rows_pair_assumed_and_measured_and_change_no_committed_entry():
    rs = study.measured_rows()
    for fam in study.FAMILIES:
        mine = [r for r in rs if r["family"] == fam]
        for r in mine:
            assert r["spec"] in study.STUDIES["measured"][1]
            assert r["estimator"] in study.ESTIMATORS or r["estimator"] in study.COMBOS
        assumed = {r["ladder"]: r for r in mine if r["sizes"] == "assumed"}
        measured = {r["ladder"]: r for r in mine if r["sizes"] == "measured"}
        assert assumed.keys() == measured.keys() == {1, 2, 3, 4, 5}
        for i in assumed:
            assert assumed[i]["estimator"] == measured[i]["estimator"]
            assert measured[i]["spec"] == "m-" + assumed[i]["spec"]
    # The variant moves only what it says: white noise off in the generated spec, one size each
    base = study.spec_of("13c")["sources"]["lte"]
    m = study.spec_of("m-13c")["sources"]["lte"]
    assert m["sigma_m"] == 0.0 and {k: v for k, v in m.items() if k != "sigma_m"} == {
        k: v for k, v in base.items() if k != "sigma_m"
    }
    assert study.spec_of("m-13c-tp20")["sources"]["lte"]["told_position_sigma_m"] == 20.0
    assert study.spec_of("13c")["sources"]["lte"]["sigma_m"] == 50.0  # committed entry intact


def test_a_family_run_later_merges_into_the_same_results():
    old = {"study": "measured", "commit": "abc1234", "seeds": [0, 1],
           "rows": [{"key": "ekf:both:no-lte", "family": "ekf"}],
           "parts": [{"families": ["ekf"]}]}  # fmt: skip
    new = {**old, "rows": [{"key": "ekf-calibrated:both:no-lte", "family": "ekf-calibrated"}],
           "parts": [{"families": ["ekf-calibrated"]}]}  # fmt: skip
    both = study.merged(old, new)
    assert [r["family"] for r in both["rows"]] == ["ekf", "ekf-calibrated"]
    assert len(both["parts"]) == 2
    assert study.merged({**old, "commit": "fff0000"}, new)["rows"] == new["rows"]
