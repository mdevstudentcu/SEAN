import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.metrics import score
from pnt.nav import ESTIMATORS, baseline, ekf
from pnt.sim.scenario import T0_NS, generate, load

C = ekf.C


def M(t_ns, source, kind, value, sigma, emitter="", meta=None):  # noqa: N802
    return Measurement(
        t_ns=t_ns, source=source, kind=kind, value=value, sigma=sigma, emitter=emitter,
        meta=meta or {},
    )  # fmt: skip


def test_registered():
    assert ESTIMATORS["ekf"] is ekf.run


def test_without_receiver_clock_it_matches_the_baseline_position():
    # Same motion model and tower model, so the positions must agree; the extra clock states
    # only add time estimates
    spec = load("gps-outage")
    run = generate(spec, seed=0)
    o = spec.get("origin_llh")
    a = list(baseline.run(run.measurements, origin_llh=o))
    b = list(ekf.run(run.measurements, origin_llh=o, pseudorange_receiver_clock=False))
    assert len(a) == len(b)
    assert np.allclose([e.pos_enu for e in a], [e.pos_enu for e in b], atol=1e-6)


def test_no_time_source_means_no_clock_estimate():
    # nominal has no clock and no GNSS time: the clock must be reported as not estimated
    spec = load("nominal")
    run = generate(spec, seed=1)
    est = list(ekf.run(run.measurements, origin_llh=spec.get("origin_llh")))
    assert all(e.clock_sigma_s is None for e in est)


def test_towers_survive_a_drifting_clock():
    # The sim's towers carry no receiver clock; the default model must not reject them
    spec = load("time-spoof")
    run = generate(spec, seed=0)
    f = ekf.EKF(origin_llh=spec.get("origin_llh"))
    for m in run.measurements:
        f.process(m)
    assert f.last_used["lte"] > f.last_rejected.get("lte", -1)


def test_rejected_gnss_time_raises_an_alarm_even_when_position_is_accepted():
    spec = load("time-spoof")
    run = generate(spec, seed=0)
    est = list(ekf.run(run.measurements, origin_llh=spec.get("origin_llh")))
    m = score(est, run.truth, spec, T0_NS)
    assert any("time_spoof_suspected" in e.flags for e in est)
    assert m.spoof_detected == 1.0


def _synthetic(drift_s_per_s=2e-7, outage=(30.0, 60.0), seed=0):
    """Still receiver at the origin, three towers, a drifting receiver clock seen both in GNSS
    time and in every pseudorange (as a real radio sees it)."""
    rng = np.random.default_rng(seed)
    towers = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40]])
    tower_bias = rng.uniform(-500, 500, 3)
    meas = []
    for k in range(900):
        t = k * 0.1
        t_ns = int(t * 1e9)
        clock = 1e-5 + drift_s_per_s * t
        if not outage[0] <= t < outage[1]:
            meas.append(M(t_ns, "gnss", "position_enu", tuple(rng.normal(0, 2, 3)),
                                    (2.0, 2.0, 2.0)))  # fmt: skip
            meas.append(M(t_ns, "gnss", "time", (clock + rng.normal(0, 2e-8),), (2e-8,)))
        if k % 10 == 0:
            for i, e in enumerate(towers):
                rho = np.linalg.norm(e) + C * clock + tower_bias[i] + rng.normal(0, 5)
                meta = {"emitter_enu": e.tolist()}
                meas.append(M(t_ns, "lte", "pseudorange", (rho,), (5.0,), f"lte:{i}", meta))
    return meas, drift_s_per_s


def test_receiver_clock_carries_through_a_gnss_outage():
    meas, drift = _synthetic()
    f = ekf.EKF(pseudorange_receiver_clock=True)
    for m in meas:
        f.process(m)
    assert f.last_used["lte"] > 80e9  # towers still accepted at the end
    assert f.last_used["lte"] > f.last_rejected.get("lte", -1)
    est = list(ekf.run(meas, pseudorange_receiver_clock=True))
    mid = [e for e in est if 45e9 <= e.t_ns < 55e9]
    truth = np.array([1e-5 + drift * e.t_ns / 1e9 for e in mid])
    err = np.array([e.clock_bias_s for e in mid]) - truth
    assert np.max(np.abs(err)) < 1e-6
    # And position holds: the towers keep it, with the shared clock solved
    assert max(np.hypot(*e.pos_enu[:2]) for e in mid) < 30.0


def test_unknown_kinds_are_ignored():
    meas, _ = _synthetic()
    meas.insert(5, M(meas[5].t_ns, "vor", "bearing", (1.0,), (0.1,)))
    assert len(list(ekf.run(meas))) == len(list(ekf.run(_synthetic()[0])))


def test_clock_sigma_is_honest_while_gnss_time_is_available():
    meas, drift = _synthetic(outage=(1e9, 1e9))  # no outage
    est = [e for e in ekf.run(meas) if e.t_ns >= 10e9]  # after convergence
    err = np.array([e.clock_bias_s - (1e-5 + drift * e.t_ns / 1e9) for e in est])
    sigma = np.array([e.clock_sigma_s for e in est])
    assert np.max(np.abs(err)) < 1e-7
    assert 0.5 < np.mean(np.abs(err) < sigma) <= 1.0  # ~68 % for an honest 1-sigma


def _filter():
    f = ekf.EKF(pseudorange_receiver_clock=True)
    f.process(M(0, "gnss", "position_enu", (10.0, 20.0, 30.0), (1.0, 1.0, 1.0)))
    f.x[ekf.CLK] = 100.0
    return f


def test_altitude_model():
    f = _filter()
    y, H, R, gate = ekf.MODELS["altitude"](f, M(0, "baro", "altitude", (33.0,), (0.5,)))
    assert y == pytest.approx(3.0) and H[0, 2] == 1.0 and H.sum() == 1.0 and gate
    assert R[0, 0] == pytest.approx(0.25)


def test_time_model_and_other_time_sources_are_skipped():
    f = _filter()
    y, H, R, _ = ekf.MODELS["time"](f, M(0, "gnss", "time", (1e-6,), (1e-8,)))
    assert y == pytest.approx(C * 1e-6 - 100.0) and H[0, ekf.CLK] == 1.0 and H.sum() == 1.0
    assert R[0, 0] == pytest.approx((C * 1e-8) ** 2)
    assert ekf.MODELS["time"](f, M(0, "fm", "time", (18.0,), (1e-3,))) is None


def test_pseudorange_model_jacobian_matches_finite_differences():
    f = _filter()
    m = M(0, "lte", "pseudorange", (5000.0,), (5.0,), "lte:0", {"emitter_enu": [3000, 4000, 30]})
    ekf.MODELS["pseudorange"](f, m)  # first sight: adds the emitter's clock state
    x0 = f.x.copy()
    y0, H, _, gate = ekf.MODELS["pseudorange"](f, m)
    assert gate
    for j in range(len(x0)):
        f.x = x0.copy()
        f.x[j] += 1e-3
        y1 = ekf.MODELS["pseudorange"](f, m)[0]
        assert -(y1 - y0) / 1e-3 == pytest.approx(H[0, j], abs=1e-5)
