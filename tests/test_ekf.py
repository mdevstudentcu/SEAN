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


def test_clock_is_estimated_and_its_sigma_is_honest():
    spec = load("nominal")
    run = generate(spec, seed=1)
    est = list(ekf.run(run.measurements, origin_llh=spec.get("origin_llh")))
    m = score(est, run.truth, spec, T0_NS)
    assert m.time_err_p95_us < 1.0
    assert m.time_1sigma_bound_frac > 0.6  # ~68 % expected for an honest 1-sigma


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
    est = list(ekf.run(meas))
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


@pytest.mark.parametrize("kind", sorted(ekf.MODELS))
def test_every_model_is_a_callable(kind):
    assert callable(ekf.MODELS[kind])
