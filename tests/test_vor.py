"""VOR bearings (#11) and the EKF's bearing update (#13)."""

import numpy as np
import pytest

from pnt.core.measurement import Measurement, validate
from pnt.nav import ekf as ekf_mod
from pnt.nav import estimate
from pnt.sim import models
from pnt.sim.scenario import generate, load

STATION = np.array([[0.0, 0.0, 0.0]])


def _bearings(pos, **kw):
    pos = np.asarray(pos, float)
    ts = np.arange(len(pos), dtype=np.int64) * 1_000_000_000
    args = {"sigma_deg": 0.0, **kw}
    return models.bearings(ts, pos, np.random.default_rng(0), "vor", STATION, **args)


def test_bearing_is_clockwise_from_north_and_from_the_station():
    out = _bearings([[0, 1000, 0], [1000, 0, 0], [0, -1000, 0], [-1000, 0, 0]])
    assert [m.kind for m in out] == ["bearing"] * 4
    np.testing.assert_allclose(
        [m.value[0] for m in out], [0.0, np.pi / 2, np.pi, 3 * np.pi / 2], atol=1e-12
    )
    for m in out:
        validate(m)
        assert m.meta["emitter_enu"] == [0.0, 0.0, 0.0] and m.emitter == "vor:sim0"


def test_range_and_cone_of_confusion_drop_records():
    out = _bearings(
        [[0, 1000, 100], [0, 90_000, 100], [0, 100, 1000]], max_range_m=75_000, cone_deg=60
    )
    assert len(out) == 1  # too far, then above the station
    assert out[0].t_ns == 0


def test_bias_is_fixed_per_station_and_sigma_is_the_white_noise():
    pos = np.tile([5000.0, 5000.0, 300.0], (4000, 1))
    out = _bearings(pos, sigma_deg=1.0, bias_deg=2.0)
    err = np.degrees(np.array([m.value[0] for m in out]) - np.pi / 4)
    assert np.std(err) == pytest.approx(1.0, rel=0.05)
    assert abs(np.mean(err)) > 0.05  # one bias draw, not averaged away
    assert out[0].sigma[0] == pytest.approx(np.deg2rad(1.0))


def _filter_at(x):
    f = ekf_mod.EKF(origin_llh=(45.0, -75.0, 70.0))
    f._init(
        Measurement(t_ns=0, source="gnss", kind="position_enu", value=tuple(x), sigma=(1, 1, 1))
    )
    return f


def _meas(theta):
    return Measurement(
        t_ns=0, source="vor", kind="bearing", value=(theta,), sigma=(0.02,), emitter="vor:sim0",
        meta={"emitter_enu": [0.0, 0.0, 0.0]},
    )  # fmt: skip


def test_ekf_bearing_jacobian_matches_finite_differences():
    x = np.array([3000.0, 4000.0, 200.0])
    f = _filter_at(x)
    y0, H, R, gate = ekf_mod._bearing(f, _meas(0.6))
    assert gate and R[0, 0] == pytest.approx(0.02**2)
    for k in (0, 1, 2):
        step = np.zeros(3)
        step[k] = 0.01
        g = _filter_at(x + step)
        y1 = ekf_mod._bearing(g, _meas(0.6))[0]
        assert -(y1 - y0) / 0.01 == pytest.approx(H[0, k], abs=1e-9)
    b = f.bearing_bias_idx["vor:sim0"]  # the station's bias state, added on first sight
    assert H[0, b] == 1.0 and f.P[b, b] == pytest.approx(ekf_mod.BEARING_BIAS_SIGMA_RAD**2)
    f.x[b] = 0.01
    assert ekf_mod._bearing(f, _meas(0.6))[0] == pytest.approx(y0 - 0.01)


def test_ekf_bearing_innovation_wraps_and_skips_the_station():
    f = _filter_at([-1.0, 5000.0, 0.0])  # just west of due north
    y = ekf_mod._bearing(f, _meas(np.deg2rad(1.0)))[0]
    assert abs(y) < np.deg2rad(2.0)  # 359.99 deg predicted, 1 deg measured: a small step
    assert ekf_mod._bearing(_filter_at([10.0, 10.0, 0.0]), _meas(0.0)) is None


def test_scenario_feeds_vor_to_the_ekf():
    spec = load("uc02-yow-approach-vor")
    run = generate(spec, seed=0)
    vor = [m for m in run.measurements if m.source == "vor"]
    assert vor and {m.kind for m in vor} == {"bearing"}
    est = list(estimate("ekf", run.measurements, origin_llh=spec["origin_llh"]))
    assert est and np.all(np.isfinite([e.pos_enu for e in est]))
