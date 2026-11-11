"""The results figures' scoring (analysis/figures.py, #27): T1 as ADR-0034's amendment takes it."""

import importlib.util
import sys
from pathlib import Path

import numpy as np

_PATH = Path(__file__).parents[1] / "analysis" / "figures.py"
_SPEC = importlib.util.spec_from_file_location("results_figures", _PATH)
fg = importlib.util.module_from_spec(_SPEC)
sys.modules["results_figures"] = fg
_SPEC.loader.exec_module(fg)


def _runs(err_of_t, n=20, loss=60.0, end=360.0):
    """n runs at 10 Hz; run i has error err_of_t(t since loss, i)."""
    t = np.round(np.arange(0.0, end + 1e-9, 0.1), 1)
    return [{"t_s": t, "err": err_of_t(t - loss, i).astype(np.float32)} for i in range(n)]


def test_per_second_p95_is_taken_across_runs():
    runs = _runs(lambda dt, i: np.full(dt.shape, float(i)))
    p95 = fg.per_second_p95(runs, 60.0, 300)
    assert p95.shape == (301,)
    assert np.allclose(p95, np.percentile(np.arange(20.0), 95))


def test_the_worst_second_decides_not_the_pooled_window():
    # error 0 until the last 10 s of T1's window, then 26 m in every run: pooled over the window
    # the 95th percentile is 0, but the per-second curve passes 25 m, so T1 is missed (ADR-0034)
    runs = _runs(lambda dt, i: np.where(dt >= 290.0, 26.0, 0.0))
    p95 = fg.per_second_p95(runs, 60.0, 300)
    st = fg.t1_statistic(p95, fg.T1_M, fg.T1_WINDOW_S)
    assert not st["met"] and st["worst_p95_m"] == 26.0 and st["worst_at_s"] == 290
    fb = fg.t1_statistic(p95, fg.FALLBACK_M, fg.FALLBACK_WINDOW_S)
    assert fb["met"] and fb["worst_p95_m"] == 0.0  # the fallback's window ends at 120 s


def test_real_sessions_are_a_placeholder_without_numbers():
    rows = fg.REAL_SESSIONS
    assert {r["result"] for r in rows} == {"TBD"}
    assert all("#21" in r["waiting_on"] or "#30" in r["waiting_on"] for r in rows)
