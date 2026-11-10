"""Range rate (`doppler`) in the EKF (#13): its model, its Jacobian, and what it buys in a GNSS
outage. Sim evidence only."""

import numpy as np
import pytest

from pnt import metrics, nav
from pnt.core.measurement import Measurement
from pnt.nav import ekf
from pnt.nav.ekf import CLK, MODELS, POS, VEL
from pnt.sim.scenario import T0_NS, generate, load

SAT = {"emitter_enu": [300e3, -200e3, 700e3], "emitter_vel_enu": [-5000.0, 4500.0, 300.0]}


def started(**config) -> ekf.EKF:
    f = ekf.EKF(**config)
    f.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=(10.0, -20.0, 30.0),
                          sigma=(1.0, 1.0, 1.0)))  # fmt: skip
    f.x[VEL] = [6.0, -3.0, 0.5]
    return f


def predicted(f: ekf.EKF, m: Measurement) -> float:
    y, *_ = MODELS["doppler"](f, m)
    return m.value[0] - float(np.atleast_1d(y)[0])


@pytest.mark.parametrize(
    ("meta", "config"),
    [
        (SAT, {}),  # a satellite, no clock in the record
        ({**SAT, "rx_clock": "rtl0"}, {}),  # a radio's own clock
        ({"emitter_enu": [1500.0, 800.0, 40.0]}, {"pseudorange_receiver_clock": True}),  # tower
    ],
)
def test_jacobian_matches_numerical_differentiation(meta, config):
    f = started(**config)
    m = Measurement(t_ns=0, source="leo", kind="doppler", emitter="leo:SAT1", value=(0.0,),
                    sigma=(1.0,), meta=meta)  # fmt: skip
    _, H, _, gate = MODELS["doppler"](f, m)
    assert gate
    x0 = f.x.copy()
    numeric = np.zeros(len(x0))
    for i in range(len(x0)):
        for sign in (1, -1):
            f.x = x0.copy()
            f.x[i] += sign * 1e-4
            numeric[i] += sign * predicted(f, m) / 2e-4
    f.x = x0
    assert np.allclose(H[0], numeric, rtol=1e-5, atol=1e-8)
    # The receiver's clock drift enters when a clock is named or modelled, never otherwise
    clock = (CLK + 1) if "rx_clock" not in meta else f.rx_idx["rtl0"] + 1
    assert H[0, clock] == (1.0 if "rx_clock" in meta or config else 0.0)


def test_range_rate_of_a_static_tower_is_the_velocity_along_the_line_of_sight():
    f = started()
    tower = np.array([1010.0, -20.0, 30.0])  # due east of the receiver
    m = Measurement(t_ns=0, source="lte", kind="doppler", emitter="lte:1:1", value=(0.0,),
                    sigma=(0.1,), meta={"emitter_enu": list(tower)})  # fmt: skip
    # Line of sight from the tower to the receiver points west, so going east closes the range
    assert predicted(f, m) == pytest.approx(-6.0)
    assert np.allclose(f.x[POS], [10.0, -20.0, 30.0])


def test_doppler_holds_the_position_through_a_gnss_outage():
    """iridium-outage, seed 0: the same records with and without the satellites' Doppler.
    Regression guard, not a requirement: measured 23.3 m against 9.8 m p95 in the outage. The
    50-run paired comparison is in the PR."""
    spec = load("iridium-outage")
    run = generate(spec, seed=0)
    scores = {}
    for keep in (False, True):
        meas = [m for m in run.measurements if keep or m.kind != "doppler"]
        est = list(nav.estimate("ekf", meas, origin_llh=spec["origin_llh"]))
        scores[keep] = metrics.score(est, run.truth, spec, T0_NS)
    assert scores[True].fault_h_p95_m < 0.6 * scores[False].fault_h_p95_m
    assert scores[True].misleading_epochs == 0
    assert scores[True].hpl_bound_frac == 1.0


def test_a_learned_tower_clock_drift_enters_its_doppler():
    """Calibrated model: a tower seen in pseudoranges has a site clock with a drift, and the
    Doppler of the same emitter carries that drift, as the pseudorange's rate does."""
    f = started(clock_model="calibrated", pseudorange_receiver_clock=True)
    meta = {"emitter_enu": [1500.0, 800.0, 40.0]}
    f.process(Measurement(t_ns=100_000_000, source="lte", kind="pseudorange", emitter="lte:1:1",
                          value=(3000.0,), sigma=(5.0,), meta=meta))  # fmt: skip
    m = Measurement(t_ns=100_000_000, source="lte", kind="doppler", emitter="lte:1:1",
                    value=(0.0,), sigma=(0.1,), meta=meta)  # fmt: skip
    _, H, _, _ = MODELS["doppler"](f, m)
    site = f.clock_idx["site:lte:1:1"]
    assert H[0, site] == 0.0 and H[0, site + 1] == 1.0  # its drift, not its offset
    assert H[0, CLK] == 0.0 and H[0, CLK + 1] == 1.0
