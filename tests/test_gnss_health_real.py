"""`analysis/gnss_health_real.py` (#22, ADR-0031). Synthetic records only; no session in git."""

import importlib.util
import sys
from pathlib import Path

import pytest

from pnt.frontends import gnss
from pnt.io.mcap_log import SessionWriter

_PATH = Path(__file__).parents[1] / "analysis" / "gnss_health_real.py"
_spec = importlib.util.spec_from_file_location("gnss_health_real", _PATH)
gh = importlib.util.module_from_spec(_spec)
sys.modules["gnss_health_real"] = gh
_spec.loader.exec_module(gh)

SKIES = [
    {"snr": {"1": 42.0, "2": 41.0, "3": 40.0, "4": 39.0, "5": 20.0}, "n_used": 5, "hdop": 1.1,
     "n_seen": 9, "listed": True},
    {"snr": {"1": 36.0, "2": 35.0, "3": 0, "4": None}, "n_used": 2, "hdop": None, "n_seen": 4,
     "listed": True},
    {"snr": {}, "n_used": 0, "hdop": None, "n_seen": 0, "listed": True},
]  # fmt: skip


def _records():
    return [gnss.health(1_000_000_000 * (i + 1), s) for i, s in enumerate(SKIES)]


def test_top_k_cn0_is_the_s_that_the_indicator_scales():
    for m in _records():
        s = gh.top_k_cn0(m.meta["snr"])
        ref, low = gnss.REF_CN0_DBHZ, gnss.LOW_CN0_DBHZ
        assert m.value[0] == pytest.approx(min(1.0, max(0.0, (ref - s) / (ref - low))))
    # two tracked, two missing counted at the loss level
    assert gh.top_k_cn0({"1": 36.0, "2": 35.0, "3": 0}) == pytest.approx(
        (36 + 35 + 2 * gnss.LOW_CN0_DBHZ) / 4
    )


def test_summary_counts_no_fix_and_tracked_satellites():
    s = gh.summarize(_records())
    assert s["records"] == 3 and s["span_s"] == pytest.approx(2.0)
    assert s["no_fix_records"] == 2
    assert s["n_tracked"]["max"] == 5 and s["n_tracked"]["min"] == 0
    assert s["all_cn0_dbhz"]["n"] == 7  # 5 + 2 tracked values; 0 and None are not tracked
    assert s["jam_indicator"]["min"] == 0.0 and s["jam_indicator"]["max"] == 1.0
    assert s["jam_above_zero_frac"] == pytest.approx(2 / 3)
    md = gh.table_md("x-gnss", s, "abc1234")
    assert "abc1234" in md and "3 records over 2.0 s; 2 without a fix" in md


def test_load_reads_only_gnss_health_from_a_session(tmp_path):
    folder = tmp_path / "s-gnss"
    folder.mkdir()
    recs = _records()
    with SessionWriter(folder / "session.mcap") as w:
        for m in recs:
            w.write("/meas/gnss", m)
    got = gh.load(folder)
    assert [m.t_ns for m in got] == [m.t_ns for m in recs]
    gh.plot(got, "s-gnss", "abc1234", tmp_path / "p.png")
    assert (tmp_path / "p.png").read_bytes()[:4] == b"\x89PNG"
