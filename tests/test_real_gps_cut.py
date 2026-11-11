"""`analysis/real_gps_cut.py` (#214). Synthetic records only; no session in git."""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import SessionWriter

_PATH = Path(__file__).parents[1] / "analysis" / "real_gps_cut.py"
_spec = importlib.util.spec_from_file_location("real_gps_cut", _PATH)
rgc = importlib.util.module_from_spec(_spec)
sys.modules["real_gps_cut"] = rgc
_spec.loader.exec_module(rgc)

T0 = 1_400_000_000_000_000_000
S = 1_000_000_000


def _fix(t_s: float, east: float = 0.0) -> Measurement:
    return Measurement(
        t_ns=T0 + round(t_s * S),
        source="gnss",
        kind="position_enu",
        value=(east, 0.0, 0.0),
        sigma=(2.0, 2.0, 3.0),
    )


def _lte(t_s: float, kind: str, snr: float, sigma: float = 20.0) -> Measurement:
    return Measurement(
        t_ns=T0 + round(t_s * S),
        source="lte",
        kind=kind,
        value=(1000.0,),
        sigma=(sigma,),
        emitter="lte:2460:92",
        meta={"snr_db": snr, "rx_clock": "sdr_a"},
    )


def test_adr36_sigma_follows_the_fit_and_the_bins():
    # the fit at SNR >= -8 dB: sqrt(0.64^2 + 2.28^2 / SNR_lin)
    assert rgc.adr36_sigma(10.0) == pytest.approx(math.sqrt(0.64**2 + 2.28**2 / 10))
    assert rgc.adr36_sigma(-8.0) == pytest.approx(math.sqrt(0.64**2 + 2.28**2 / 10**-0.8))
    # the measured bins below the fit, and nothing below -14 dB (TBD in ADR-0036)
    assert rgc.adr36_sigma(-8.01) == 12.4
    assert rgc.adr36_sigma(-11.0) == 12.4
    assert rgc.adr36_sigma(-11.01) == 24.7
    assert rgc.adr36_sigma(-14.0) == 24.7
    assert rgc.adr36_sigma(-14.01) is None


def test_lte_variants_keep_or_resize_only_lte_records():
    gnss = _fix(0.0)
    strong_pr, weak_pr = _lte(1, "pseudorange", 5.0), _lte(2, "pseudorange", -10.0)
    lost_pr, dop = _lte(3, "pseudorange", -20.0), _lte(4, "doppler", 5.0, 0.01)
    meas = [gnss, strong_pr, weak_pr, lost_pr, dop]
    assert rgc.lte_variant(meas, "none") == [gnss]
    assert rgc.lte_variant(meas, "told") == meas
    assert rgc.lte_variant(meas, "told-pr") == [gnss, strong_pr, weak_pr, lost_pr]
    adr36 = rgc.lte_variant(meas, "adr36")
    assert [m.t_ns for m in adr36] == [gnss.t_ns, strong_pr.t_ns, weak_pr.t_ns]
    assert adr36[0] is gnss
    assert adr36[1].sigma == (pytest.approx(rgc.adr36_sigma(5.0)),)
    assert adr36[2].sigma == (12.4,)
    assert adr36[1].value == strong_pr.value and adr36[1].meta == strong_pr.meta
    cut8 = rgc.lte_variant(meas, "adr36-cut8")
    assert [m.t_ns for m in cut8] == [gnss.t_ns, strong_pr.t_ns]
    with pytest.raises(ValueError):
        rgc.lte_variant(meas, "made-up")


def test_cut_removes_gnss_from_the_cut_on_and_nothing_else():
    meas = [_fix(t) for t in range(10)] + [_lte(t + 0.5, "pseudorange", 0.0) for t in range(10)]
    meas.sort(key=lambda m: m.t_ns)
    out = rgc.cut_gnss(meas, T0, 5.0)
    gnss_t = [(m.t_ns - T0) / S for m in out if m.source == "gnss"]
    assert gnss_t == [0, 1, 2, 3, 4]
    assert [m for m in out if m.source == "lte"] == [m for m in meas if m.source == "lte"]


def test_score_cut_reads_errors_bound_and_slices():
    cut = T0 + 10 * S
    fix_t = T0 + np.arange(0, 400) * S
    fix_pos = np.zeros((400, 3))
    est_t = T0 + np.arange(0, 4000) * (S // 10)
    after = (est_t - cut) / S
    est_pos = np.zeros((4000, 3))
    est_pos[:, 0] = np.clip(after, 0, None)  # 1 m of error per second after the cut
    est_hpl = np.full(4000, 100.0)  # bounds the first 100 s only
    out = rgc.score_cut(est_t, est_pos, est_hpl, fix_t, fix_pos, cut, horizon_s=300.0)
    assert out["n_fixes"] == 301
    assert out["err_30s_m"] == pytest.approx(30.0)
    assert out["err_300s_m"] == pytest.approx(300.0)
    assert out["p95_60s_m"] == pytest.approx(np.percentile(np.arange(60), 95))
    assert out["max_m"] == pytest.approx(300.0)
    assert out["hpl_bound"] == pytest.approx(101 / 301)
    assert out["misleading"] == 200


def test_hold_last_fix_scores_the_last_fix_before_the_cut():
    fix_t = T0 + np.arange(0, 400) * S
    fix_pos = np.zeros((400, 3))
    fix_pos[:, 0] = np.arange(400) * 0.01  # a slow walk of 1 cm/s
    out = rgc.hold_last_fix(fix_t, fix_pos, T0 + 50 * S)
    assert out["err_30s_m"] == pytest.approx(0.31)  # fix 80 against fix 49
    assert math.isnan(out["hpl_bound"])


def _session(tmp_path: Path) -> Path:
    """400 s static: GNSS 1 Hz and baro 10 Hz. From 60 s the fixes sit 100 m east, so a filter
    that never saw them is 100 m from them."""
    out = tmp_path / "static-lte"
    out.mkdir()
    session.write_meta(out, {"name": out.name, "commit": "test"})
    with SessionWriter(out / session.MCAP_NAME) as w:
        for t in range(400):
            w.write("/meas/gnss", _fix(t, 100.0 if t >= 60 else 0.0))
            for k in range(10):
                baro = Measurement(
                    t_ns=T0 + t * S + k * S // 10 + 1,
                    source="baro",
                    kind="altitude",
                    value=(0.0,),
                    sigma=(0.3,),
                )
                w.write("/meas/baro", baro)
    return out


def test_run_one_scores_against_the_withheld_fixes(tmp_path):
    path = _session(tmp_path)
    rgc.load.cache_clear()
    row = rgc.run_one(str(path), "ekf", "none", 60.0)
    assert row["n_fixes"] == 301
    # the filter holds where the fed fixes were; the withheld ones are 100 m away
    for s in rgc.AT_S:
        assert row[f"err_{s:g}s_m"] == pytest.approx(100.0, abs=1.0)
    assert row["pre_p95_m"] < 1.0
    assert row["n_lte"] == 0
    rgc.load.cache_clear()


def test_arc_steps_take_off_the_drift_and_split_at_minus_8_db():
    def pr(t_s, value, arc, snr):
        m = _lte(t_s, "pseudorange", snr)
        meta = {**m.meta, "arc": arc, "ambiguity_m": 2997924.58}
        return Measurement(**{**{f: getattr(m, f) for f in m.__struct_fields__}, "meta": meta,
                              "value": (value,)})  # fmt: skip

    rate = 100.0  # m/s: dongle against tower
    recs = [pr(t / 10, 5000.0 + rate * t / 10, 0, 5.0) for t in range(10)]
    recs.append(pr(1.2, 5000.0 + rate * 1.2 - 1500.0, 1, 0.0))  # a new arc 1.5 km short
    recs += [pr(1.3 + t / 10, 3500.0 + rate * (1.3 + t / 10), 1, 0.0) for t in range(5)]
    recs.append(pr(2.0, 3500.0 + rate * 2.0 + 5.0, 2, -10.0))  # a new arc 5 m off, weak
    recs.append(pr(9.0, 0.0, 3, 0.0))  # after a 7 s gap: not judged
    out = rgc.arc_steps(recs)
    assert out["above"]["arcs"] == 1 and out["above"]["over_100m"] == 1
    assert out["above"]["median_jump_m"] == pytest.approx(1500.0, abs=1.0)
    assert out["below"]["arcs"] == 1 and out["below"]["over_100m"] == 0
    assert math.isnan(out["below"]["median_jump_m"])


def test_main_writes_the_summary_and_figure(tmp_path):
    path = _session(tmp_path)
    out = tmp_path / "out"
    rgc.load.cache_clear()
    rgc.main([str(path), "--cuts", "60", "--estimators", "ekf", "--variants", "none", "--out",
              str(out)])  # fmt: skip
    rgc.load.cache_clear()
    text = (out / "summary.md").read_text()
    assert "| ekf | none |" in text
    agg = json.loads((out / "summary.json").read_text())["aggregate"]["ekf|none"]
    assert agg["err_30s_m"]["median"] == pytest.approx(100.0, abs=1.0)  # the withheld fixes
    assert "## HPL at the same instants" in text and "| hold | last fix |" in text
    assert (out / "error_after_cut.png").stat().st_size > 0


def test_dash_session_cuts_gnss_and_gives_truth_on_every_epoch(tmp_path):
    from pnt.io.mcap_log import read_session

    path = _session(tmp_path)
    out = tmp_path / "dash"
    rgc.load.cache_clear()
    rgc.write_dash_session(str(path), out, 60.0)
    rgc.load.cache_clear()
    recs = list(read_session(out / session.MCAP_NAME))
    gnss = [r.t_ns for topic, r in recs if topic == "/meas/gnss"]
    truth = [r for topic, r in recs if topic == "/truth"]
    assert max(gnss) < T0 + 60 * S and len(gnss) == 60
    assert len(truth) == 3991 and all(t.t_ns % (S // 10) == 0 for t in truth)
    # halfway between the fix at 59 s (0 m) and at 60 s (100 m east)
    mid = next(t for t in truth if t.t_ns == T0 + 59 * S + S // 2)
    assert mid.pos_enu[0] == pytest.approx(50.0)
