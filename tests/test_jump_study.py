"""The location-jump study's fault composition and scoring helpers (REQ-04, T4).

`analysis/jump_study.py` composes existing fault types (spoof_jump, then spoof_ramp) rather than
adding one, so these check that the composition puts the intended offset into the GNSS records,
and that the helpers turning runs into the study's numbers say what their names say.
"""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Estimate, Truth
from pnt.core.time import s_to_ns
from pnt.sim.scenario import T0_NS, generate

_PATH = Path(__file__).parents[1] / "analysis" / "jump_study.py"
_SPEC = importlib.util.spec_from_file_location("jump_study", _PATH)
js = importlib.util.module_from_spec(_SPEC)
sys.modules["jump_study"] = js
_SPEC.loader.exec_module(js)


def _gnss(run):
    return {m.t_ns: np.array(m.value) for m in run.measurements if m.kind == "position_enu"}


@pytest.mark.parametrize("rate", [0.0, 1.5])
def test_jump_then_drift_offsets_gnss_by_jump_plus_ramp_req04(rate):
    spec = js.environment("uc01")
    clean = _gnss(generate(spec, seed=3))
    spec["faults"] = js.jump_faults(20.0, 135.0, rate, start_s=100.0)
    spoofed = _gnss(generate(spec, seed=3))
    u = js.unit(135.0)
    start = T0_NS + s_to_ns(100.0)
    for t, v in spoofed.items():
        since = max(0.0, (t - start) / 1e9)
        want = (20.0 + rate * since) * u if t >= start else np.zeros(3)
        np.testing.assert_allclose(v - clean[t], want, atol=1e-9)


def test_environments_drop_their_own_faults():
    for name in js.ENVIRONMENTS:
        assert js.environment(name)["faults"] == []
    real = js.environment("realistic-uc01")
    assert real["trajectory"] == js.load("uc01-drone-circuit")["trajectory"]
    assert real["sources"]["lte"]["receiver_clock"] is True  # the realistic set's error model
    with pytest.raises(ValueError):
        js.environment("nowhere")


def _track(errors, start_s=10.0, dt_s=1.0, status="nominal"):
    """Truth at rest at the origin; estimates offset by `errors` (east, north), one per epoch."""
    est, truth = [], []
    for i, (e, n) in enumerate(errors):
        t = T0_NS + s_to_ns(i * dt_s)
        truth.append(Truth(t_ns=t, pos_enu=(0.0, 0.0, 0.0), vel_enu=(0.0, 0.0, 0.0)))
        est.append(
            Estimate(
                t_ns=t,
                pos_enu=(e, n, 0.0),
                vel_enu=(0.0, 0.0, 0.0),
                pos_cov=(1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0),
                status=status if i * dt_s < start_s else "nominal",
            )
        )
    return est, truth, T0_NS + s_to_ns(start_s)


def test_jump_response_absorbed_follows_the_spoof():
    # 100 m east jump at 10 s; the estimate holds 5 s, then sits on the spoofed position
    errs = [(0.0, 0.0)] * 15 + [(100.0, 0.0)] * 45
    est, truth, start = _track(errs, status="unsafe")
    r = js.jump_response(est, truth, start, 90.0, 100.0, tail_s=20.0)
    assert r["pull"] == pytest.approx(1.0)
    assert r["absorbed"] == 1.0
    assert r["follow_s"] == pytest.approx(5.0)
    assert r["avail_pre"] == 0.0  # every pre-jump epoch was unsafe


def test_jump_response_held_and_off_axis_error_is_not_pull():
    # The estimate wanders 100 m north while the jump is east: not following the spoof
    est, truth, start = _track([(0.0, 0.0)] * 10 + [(1.0, 100.0)] * 50)
    r = js.jump_response(est, truth, start, 90.0, 100.0, tail_s=20.0)
    assert r["pull"] == pytest.approx(0.01)
    assert r["absorbed"] == 0.0
    assert math.isnan(r["follow_s"])
    assert r["avail_pre"] == 1.0


def test_jump_response_scales_by_the_drifting_offset():
    # Jump 10 m north then 2 m/s: an estimate on the spoofed track has pull 1 throughout
    errs = [(0.0, 0.0)] * 10 + [(0.0, 10.0 + 2.0 * k) for k in range(50)]
    est, truth, start = _track(errs)
    r = js.jump_response(est, truth, start, 0.0, 10.0, rate_mps=2.0, tail_s=20.0)
    assert r["pull"] == pytest.approx(1.0)
    assert r["follow_s"] == 0.0


def _summary(p_detect, worst, hmi, missed=None):
    rows = [{"env": "e", "estimator": "ekf", "kind": "clean", "size_m": None, "rate_mps": 0.0}]
    missed = worst if missed is None else missed
    for z, p, w, h, m in zip(js.SIZES_M[:4], p_detect, worst, hmi, missed, strict=True):
        rows.append(
            {
                "env": "e",
                "estimator": "ekf",
                "kind": "jump",
                "size_m": z,
                "rate_mps": 0.0,
                "p_detect": p,
                "worst_max_m": w,
                "missed_worst_m": m,
                "hmi_runs": h,
            }
        )
    return rows


def test_smallest_reliable_needs_every_larger_size_detected():
    # 5, 10, 15, 20 m: detected 0, 0.96, 0.9, 1.0 -> only 20 m and up is reliable
    s = _summary([0.0, 0.96, 0.9, 1.0], [8, 12, 60, 25], [0, 0, 1, 0])
    assert js.smallest_reliable(s, "e", "ekf") == 20
    assert js.smallest_reliable(_summary([0, 0, 0, 0.5], [1] * 4, [0] * 4), "e", "ekf") is None


def test_bands_split_undetected_harm_from_hazardous_epochs():
    s = _summary([0.0, 0.96, 0.9, 1.0], [8, 12, 60, 25], [0, 0, 1, 2])
    b = js.bands(s, "e", "ekf")
    assert b["undetected"] == [15]  # missed in over 5 % of runs and over 50 m in one
    assert b["hazardous"] == [15, 20]
    # Over 50 m only in runs that caught the jump: not an undetected harm
    s = _summary([0.0, 0.96, 0.9, 1.0], [8, 12, 60, 25], [0, 0, 0, 0], missed=[8, 12, 20, 25])
    assert js.bands(s, "e", "ekf")["undetected"] == []
