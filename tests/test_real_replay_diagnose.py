"""`analysis/real_replay_diagnose.py` (#256). Synthetic records only; no session in git."""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Measurement

_PATH = Path(__file__).parents[1] / "analysis" / "real_replay_diagnose.py"
_spec = importlib.util.spec_from_file_location("real_replay_diagnose", _PATH)
rd = importlib.util.module_from_spec(_spec)
sys.modules["real_replay_diagnose"] = rd
_spec.loader.exec_module(rd)

T0 = 1_400_000_000_000_000_000
AMB = 2_997_924.58  # one 10 ms frame (m)


def _pr(t_s: float, cell: str, value: float, arc: int, flags=()) -> Measurement:
    return Measurement(
        t_ns=T0 + round(t_s * 1e9),
        source="lte",
        kind="pseudorange",
        value=(value,),
        sigma=(3.0,),
        emitter=cell,
        meta={"arc": arc, "ambiguity_m": AMB, "flags": list(flags), "rx_clock": "sdr_a"},
    )


def test_hdop_needs_three_cells_and_grows_as_they_bunch():
    u = [np.array([math.cos(a), math.sin(a)]) for a in np.deg2rad([0.0, 120.0, 240.0])]
    assert rd.hdop_2d(u[:2]) == math.inf
    spread = rd.hdop_2d(u)
    assert spread == pytest.approx(math.sqrt(4 / 3))  # 3 cells 120 deg apart, one clock
    bunched = [np.array([math.cos(a), math.sin(a)]) for a in np.deg2rad([0.0, 10.0, 20.0])]
    assert rd.hdop_2d(bunched) > 10 * spread
    assert rd.hdop_2d([u[0], u[0], u[0]]) == math.inf  # singular


def test_dd_segments_give_slope_wander_and_unwrap_frames():
    ref, other = {}, {}
    for b in range(400):  # 40 s of 0.1 s bins
        t = b * rd.BIN_S
        ref[b] = (100.0, 0)
        jump = AMB if b >= 200 else 0.0  # a whole frame inside the pair: not a step
        other[b] = (100.0 + 2.0 * t + jump, 0)
    segs = rd.dd_segments({"ref": ref, "c": other}, "ref", AMB)
    assert len(segs) == 1
    s = segs[0]
    assert s["slope_m_s"] == pytest.approx(2.0)
    assert s["wander_m"] == pytest.approx(2.0 * 39.9)
    assert s["std_about_line_m"] == pytest.approx(0.0, abs=1e-6)
    short = {b: v for b, v in other.items() if b < 100}  # 10 s: below MIN_SEGMENT_S
    assert rd.dd_segments({"ref": ref, "c": short}, "ref", AMB) == []


def test_arc_restarts_net_of_rate_and_mark_common_steps():
    recs = []
    for i in range(100):  # cell a: rate 100 m/s, new arc at 5 s stepping +30 m after the rate
        t = i * 0.1
        recs.append(_pr(t, "a", 1000.0 + 100.0 * t + (30.0 if t >= 5.0 else 0.0), int(t >= 5.0)))
    for i in range(100):  # cell b: new arc at 5.05 s stepping a whole frame plus 7 m
        t = i * 0.1 + 0.05
        recs.append(_pr(t, "b", 500.0 + (AMB + 7.0 if t >= 5.0 else 0.0), int(t >= 5.0),
                        flags=("sample_gap",) if t >= 5.0 else ()))  # fmt: skip
    out = rd.arc_restarts(recs, T0)
    assert [r["cell"] for r in out] == ["a", "b"]
    assert out[0]["step_m"] == pytest.approx(30.0)
    assert out[1]["step_m"] == pytest.approx(7.0)
    assert all(r["common"] for r in out)
    assert [r["sample_gap"] for r in out] == [False, True]
