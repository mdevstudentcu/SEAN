"""Switched modes of our clock in the tower ranges (`pseudorange_receiver_clock`, #228)."""

import copy

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import ekf

TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
CLOCK_S = (1e-6, 2e-8)  # our clock: offset (s) and drift (s/s), the realistic set's drift


def M(t_ns, source, kind, value, sigma, emitter="", meta=None):  # noqa: N802
    return Measurement(
        t_ns=t_ns, source=source, kind=kind, value=value, sigma=sigma, emitter=emitter,
        meta=meta or {},
    )  # fmt: skip


def _run(gnss_time: bool, duration=200.0, outage_from=100.0, seed=0):
    """Receiver circling the origin; four towers whose readings carry our clock. GNSS position
    (and, if asked, GNSS time) at 5 Hz until `outage_from`, towers at 1 Hz throughout."""
    rng = np.random.default_rng(seed)
    offsets = rng.uniform(-500, 500, len(TOWERS))
    meas = []
    for k in range(int(duration * 10)):
        t = k / 10
        t_ns = int(round(t * 1e9))
        pos = np.array([100 * np.cos(0.05 * t), 100 * np.sin(0.05 * t), 30.0])
        clock_s = CLOCK_S[0] + CLOCK_S[1] * t
        if k % 2 == 0 and t < outage_from:
            meas.append(
                M(t_ns, "gnss", "position_enu", tuple(pos + rng.normal(0, 2, 3)), (2,) * 3)
            )
            if gnss_time:
                meas.append(M(t_ns, "gnss", "time", (clock_s + rng.normal(0, 2e-8),), (2e-8,)))
        if k % 10 == 0:
            for i, e in enumerate(TOWERS):
                rho = np.linalg.norm(pos - e) + offsets[i] + ekf.C * clock_s + rng.normal(0, 5)
                meta = {"emitter_enu": [float(x) for x in e]}
                meas.append(M(t_ns, "lte", "pseudorange", (rho,), (5.0,), f"lte:{i}", meta))
    return meas


@pytest.mark.parametrize("model", ["independent", "calibrated"])
def test_switching_our_clock_in_leaves_the_predicted_range_unchanged(model):
    """`gnss_out` turns the term on when GNSS position is lost. The switch re-references the
    tower clocks, so the predicted range and its variance are the same with the term off and on."""
    meas = _run(gnss_time=True)
    f = ekf.EKF(pseudorange_receiver_clock="gnss_out", clock_model=model)
    for m in meas:
        if m.t_ns >= 101.5e9:  # GNSS last used at 99.8 s: the term is still off
            break
        f.process(m)
    f.predict(int(102.5e9))  # past gnss_timeout_s: the next tower reading turns it on
    assert not f.pr_rx_clock
    off = copy.deepcopy(f)
    off.rx_mode = False
    m = next(m for m in meas if m.kind == "pseudorange" and m.t_ns >= 103e9)
    y_on, H_on, R_on, _ = ekf.MODELS["pseudorange"](f, m)
    y_off, H_off, R_off, _ = ekf.MODELS["pseudorange"](off, m)
    assert f.pr_rx_clock and not off.pr_rx_clock
    assert y_on == pytest.approx(y_off, abs=1e-6)
    s_on = (H_on @ f.P @ H_on.T + R_on).item()
    s_off = (H_off @ off.P @ H_off.T + R_off).item()
    assert s_on == pytest.approx(s_off, rel=1e-9)


def test_observed_mode_matches_off_without_a_time_source_and_on_with_one():
    def pos(meas, mode):
        return np.array([e.pos_enu for e in ekf.run(meas, pseudorange_receiver_clock=mode)])

    no_time = _run(gnss_time=False)
    np.testing.assert_array_equal(pos(no_time, "observed"), pos(no_time, False))
    timed = _run(gnss_time=True)
    np.testing.assert_array_equal(pos(timed, "observed"), pos(timed, True))


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        ekf.EKF(pseudorange_receiver_clock="sometimes")
