"""`analysis/lte_gps_truth.py`: LTE pseudorange error against GPS truth (#21). Synthetic
records with known towers, clocks and noise; no session data."""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "lte_gps_truth.py"
_spec = importlib.util.spec_from_file_location("lte_gps_truth", _PATH)
truth = importlib.util.module_from_spec(_spec)
sys.modules["lte_gps_truth"] = truth
_spec.loader.exec_module(truth)

F = truth.FRAME_M


def _series(emitter, k, v, arc, snr=5.0):
    return truth.Series(
        emitter=emitter,
        rx_clock="rtl0",
        earfcn=2460,
        pci=int(emitter.split(":")[-1]),
        k=k,
        v=v,
        sig=np.full(k.size, 1.5),
        snr=np.full(k.size, snr),
        arc=arc,
    )


def _two_cells(seed=0, offset_m=150.0, drift_mps=0.02, sigma=1.0, jump_arc_m=0.0):
    """Two cells on one dongle over 600 s at 10 Hz. Each value is range + dongle clock (which
    jumps at a sample gap) + its tower's frame timing + white noise, known modulo one frame,
    and each arc lands on a different whole number of frames."""
    rng = np.random.default_rng(seed)
    k = np.arange(6000)
    t = k * truth.DT
    clock = 300.0 * t + np.where(t > 200, 5e4, 0.0)  # drift, then a jump at a sample gap
    arc = (t > 350).astype(np.int64)
    rho_ref, rho_cell = 4321.0, 7890.0
    ref = rho_ref + clock + rng.normal(0, sigma, k.size) + 3 * F * arc
    cell = (
        rho_cell + clock + offset_m + drift_mps * t + rng.normal(0, sigma, k.size)
        - 7 * F * arc + jump_arc_m * arc
    )  # fmt: skip
    return (
        _series("lte:2460:1", k, ref % F, arc),
        _series("lte:2460:2", k, cell % F, arc),
        rho_ref,
        rho_cell,
    )


def test_wrap_puts_values_within_half_a_frame():
    x = truth.wrap(np.array([0.0, F / 2 - 1, F / 2 + 1, -F / 2 - 1, 5 * F + 3]))
    assert np.all((x >= -F / 2) & (x < F / 2))
    assert x[2] == pytest.approx(-F / 2 + 1)
    assert x[4] == pytest.approx(3.0, abs=1e-6)


def test_pair_recovers_offset_white_noise_and_drift_through_clock_jumps_and_frames():
    ref, cell, r_ref, r_cell = _two_cells()
    p = truth.pair(ref, cell, r_ref, r_cell)
    # offset after truth: 150 m plus the mean of the drift term over the capture
    assert p["offset_m"] == pytest.approx(150.0 + 0.02 * 300, abs=1.0)
    assert p["offset_us"] == pytest.approx(p["offset_m"] / truth.C * 1e6)
    assert p["white_m"] == pytest.approx(math.sqrt(2), rel=0.1)  # two cells' white noise
    assert p["S_m"][100.0] == pytest.approx(math.sqrt(2), rel=0.2)  # drift is removed by S(τ)
    assert p["drift"]["slope_mps"] == pytest.approx(0.02, abs=3 * p["drift"]["se_mps"])
    assert p["arcs"] == 2 and p["arcs_jumped"] == 0


def test_pair_flags_an_arc_that_reacquires_on_another_timing():
    ref, cell, r_ref, r_cell = _two_cells(drift_mps=0.0, jump_arc_m=500.0)
    p = truth.pair(ref, cell, r_ref, r_cell)
    assert p["arcs_jumped"] == 1
    assert p["epochs_in_jumped_arcs"] == np.count_nonzero(cell.arc == 1)
    # the remaining arc is clean
    assert p["resid_sigma_m"] == pytest.approx(math.sqrt(2), rel=0.1)


def test_pair_needs_common_epochs():
    ref, cell, r_ref, r_cell = _two_cells()
    cell.k = cell.k + 10_000
    assert truth.pair(ref, cell, r_ref, r_cell) is None


def test_gauss_markov_fit_recovers_its_parameters():
    taus = np.array(truth.TAUS)
    s = truth.gm_structure(taus, 2.0, 10.0, 3.0)
    fit = truth.fit_gm(dict(zip(taus.tolist(), s.tolist(), strict=True)))
    assert fit["white_m"] == pytest.approx(2.0, rel=0.1)
    assert fit["corr_m"] == pytest.approx(10.0, rel=0.1)
    assert fit["corr_tau_s"] == pytest.approx(3.0, rel=0.15)


def test_structure_of_white_noise_is_flat():
    rng = np.random.default_rng(3)
    k = np.arange(5000)
    s = truth.structure(k, rng.normal(0, 2.0, k.size), np.zeros(k.size, np.int64))
    assert all(v == pytest.approx(2.0, rel=0.15) for v in s.values())


def test_adr36_white_follows_its_fit_and_stops_below_its_range():
    assert truth.adr36_white(10.0) == pytest.approx(math.hypot(0.64, 2.28 / math.sqrt(10)))
    assert math.isnan(truth.adr36_white(-9.0))


def test_analyse_pairs_only_matched_cells_against_the_strongest():
    ref, cell, r_ref, r_cell = _two_cells()
    other = _series("lte:2460:3", cell.k.copy(), cell.v.copy(), cell.arc.copy(), snr=-3.0)
    info = {
        ref.emitter: {"status": "matched", "enb": 1, "range_m": r_ref},
        cell.emitter: {"status": "matched", "enb": 2, "range_m": r_cell},
        other.emitter: {"status": "unknown", "enb": None, "range_m": None},
    }
    res = truth.analyse([ref, cell, other], info, capture_s=600.0)
    assert [c["status"] for c in res["cells"]] == ["matched", "matched", "unknown"]
    assert len(res["pairs"]) == 1
    p = res["pairs"][0]
    assert {p["emitter"], p["ref"]} == {ref.emitter, cell.emitter}
    assert p["same_enb"] is False
    assert p["tracked"] == pytest.approx(1.0)
    md = truth.markdown(res, "synthetic", "abc1234", 600)
    assert "withheld for privacy" in md
    assert str(r_ref) not in md and str(r_cell) not in md  # no true range is written
