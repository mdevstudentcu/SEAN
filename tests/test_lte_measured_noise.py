"""The structure function of analysis/lte_measured_noise.py against closed forms (#173).

Seeded synthetic series only. Tolerances are regression guards on estimators of known
statistics, not requirements.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lte_measured_noise", REPO / "analysis" / "lte_measured_noise.py"
)
lmn = importlib.util.module_from_spec(spec)
sys.modules["lte_measured_noise"] = lmn  # dataclasses look their module up by name
spec.loader.exec_module(lmn)

N = 20_000


def _s(series, label=None, taus=(0.1, 1.0, 10.0)):
    k = np.arange(series.size)
    lab = np.zeros(series.size, np.int64) if label is None else label
    return {r["tau_s"]: r for r in lmn.structure(k, series, lab, list(taus))}


def test_white_noise_gives_sigma_at_every_tau_with_drift_and_offset_removed():
    rng = np.random.default_rng(0)
    x = 1e5 + 90.0 * np.arange(N) * lmn.DT + rng.normal(0, 3.0, N)  # offset + 90 m/s drift
    for r in _s(x).values():
        assert abs(r["S_m"] - 3.0) < 0.15
        assert abs(r["S_robust_m"] - 3.0) < 0.2


def test_random_walk_and_gauss_markov_follow_their_closed_forms():
    rng = np.random.default_rng(1)
    q = 0.5**2  # m^2/s
    rw = np.cumsum(rng.normal(0, np.sqrt(q * lmn.DT), N))
    s, T = 10.0, 5.0
    phi = np.exp(-lmn.DT / T)
    gm = np.zeros(N)
    for i in range(1, N):
        gm[i] = phi * gm[i - 1] + rng.normal(0, s * np.sqrt(1 - phi**2))
    for tau, r in _s(rw).items():
        assert abs(r["S_m"] ** 2 / lmn.s_clock(tau, q, 0.0) - 1) < 0.15
    for tau, r in _s(gm).items():
        assert abs(r["S_m"] ** 2 / lmn.s_gm(tau, s, T) - 1) < 0.25


def test_no_triplet_crosses_an_arc():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1.0, N)
    arc = (np.arange(N) // 500).astype(np.int64)
    x = x + 1e4 * arc  # each arc its own constant, as the front end's arcs carry
    for r in _s(x, arc).values():
        assert r["S_m"] < 1.1


def test_drift_fit_recovers_a_tower_pair_drift():
    rng = np.random.default_rng(3)
    t = np.arange(600) * lmn.DT
    x = 2.0 * t + rng.normal(0, 3.0, t.size)  # 2 m/s, about 6.7 ppb
    fit = lmn.drift_fit(np.arange(t.size), x, np.zeros(t.size, np.int64))
    assert abs(fit["slope_mps"] - 2.0) < 3 * fit["se_mps"]


def test_frequency_allan_of_white_frequency_noise_falls_as_one_over_root_tau_with_gaps():
    rng = np.random.default_rng(4)
    sec = np.arange(3000)
    y = rng.normal(0, 1e-9, sec.size)
    keep = rng.random(sec.size) > 0.05  # 5 % of seconds missing
    rows = {r["tau_s"]: r for r in lmn.allan_freq(sec[keep], y[keep], [1, 10, 100])}
    for tau, r in rows.items():
        assert abs(r["adev"] / (1e-9 / np.sqrt(tau)) - 1) < 0.2


def test_white_fit_ignores_bins_below_its_snr_threshold():
    """Weak bins sit far above the law; the fit must neither use them nor be pulled by them."""
    floor, term, thr = 0.6, 2.3, -8.0  # thr: the TBC threshold of ADR-0036

    def law(snr_db):
        return float(np.sqrt(floor**2 + term**2 / 10 ** (snr_db / 10)))

    edges = lmn.SNR_EDGES
    bins = [
        {
            "snr_lo": lo,
            "snr_hi": hi,
            "n": 2000,
            "snr_median_db": (lo + hi) / 2,
            # weak bins well above the law, as the real captures' weak bins read
            "white_robust_m": law((lo + hi) / 2) * (3.0 if lo < thr else 1.0),
        }
        for lo, hi in zip(edges[:-1], edges[1:], strict=True)
    ]
    assert any(b["snr_lo"] < thr for b in bins)
    fit = lmn.fit_white(bins)
    assert abs(fit["floor_m"] - floor) < 0.01
    assert abs(fit["snr_term_m"] - term) < 0.01
    assert fit["snr_min_db"] == thr == lmn.FIT_MIN_SNR_DB
