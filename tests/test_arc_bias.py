"""A front end that loses a cell and finds it again starts a new arc (`meta.arc`), and the range
may step there by hundreds of metres (#214's real GPS cut). With `arc_bias` (opt-in, #147) each
new arc of a radio cell gets a range bias state of its own, so the step is absorbed instead of
pulling the position; the sim's records, whose arc never changes, are untouched.

Thresholds are regression guards with the observed values in comments, not requirements.
"""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import configured, ekf, estimate

TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
OUTAGE_S = (90.0, 270.0)
STEPS = {0: (150.0, 800.0), 1: (200.0, -600.0)}  # tower: (time s, range step m) at a new arc


def stream(steps: dict, seed=1):
    """Receiver circling the origin; GNSS at 5 Hz outside the outage, baro at 10 Hz; every tower
    at 1 Hz from a front end (`rx_clock`, `arc`), white 10 m noise told 10 m. At each tower's
    time in `steps` its range steps and its arc goes up by one."""
    rng = np.random.default_rng(seed)
    offsets = rng.uniform(-500, 500, len(TOWERS))
    meas, truth = [], {}
    for k in range(int(OUTAGE_S[1] * 10)):
        t, t_ns = k / 10, k * 100_000_000
        a = 0.05 * t
        pos = np.array([100 * np.cos(a), 100 * np.sin(a), 30.0])
        truth[t_ns] = pos
        meas.append(Measurement(t_ns=t_ns, source="baro", kind="altitude",
                                value=(30.0 + rng.normal(0, 0.5),), sigma=(0.5,)))  # fmt: skip
        if k % 2 == 0 and not OUTAGE_S[0] <= t:
            fix = tuple(pos + rng.normal(0, 2, 3))
            meas.append(Measurement(t_ns=t_ns, source="gnss", kind="position_enu", value=fix,
                                    sigma=(2.0, 2.0, 2.0)))  # fmt: skip
        if k % 10 == 0:
            for i, e in enumerate(TOWERS):
                after = i in steps and t >= steps[i][0]
                rho = np.linalg.norm(pos - e) + offsets[i] + 40.0 * t + rng.normal(0, 10.0)
                rho += steps[i][1] if after else 0.0
                meta = {"emitter_enu": [float(x) for x in e], "rx_clock": "rtl0",
                        "arc": int(after)}  # fmt: skip
                meas.append(Measurement(t_ns=t_ns, source="lte", kind="pseudorange",
                                        emitter=f"lte:{i}", value=(float(rho),), sigma=(10.0,),
                                        meta=meta))  # fmt: skip
    return meas, truth


def worst_outage_error(estimates, truth) -> float:
    return max(
        float(np.linalg.norm(np.subtract(e.pos_enu, truth[e.t_ns])[:2]))
        for e in estimates
        if e.t_ns / 1e9 >= OUTAGE_S[0] and e.t_ns in truth
    )


@pytest.mark.parametrize(
    ("run", "observed"),
    [
        # worst horizontal error in the outage (m), seed 1: arc_bias on / off
        (ekf.run, (17.5, 760.1)),
        (ekf.run_calibrated, (14.9, 669.2)),
    ],
)
def test_a_new_arc_does_not_drag_the_position(run, observed):
    meas, truth = stream(STEPS)
    on = worst_outage_error(list(estimate(configured(run, arc_bias=True), meas)), truth)
    off = worst_outage_error(list(estimate(run, meas)), truth)
    assert on < 50.0  # regression guard
    assert off > 3 * on  # regression guard: the steps pull the default


@pytest.mark.parametrize("run", [ekf.run, ekf.run_calibrated])
def test_records_whose_arc_never_changes_are_untouched(run):
    """The sim's front-end records (arc always 0): the same output with and without arc_bias."""
    meas, _ = stream({})
    a = list(estimate(configured(run, arc_bias=True), meas))
    b = list(estimate(run, meas))
    assert [(e.pos_enu, e.pos_cov, e.hpl_m) for e in a] == [(e.pos_enu, e.pos_cov, e.hpl_m)
                                                             for e in b]  # fmt: skip
