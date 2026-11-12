"""The opt-in field settings of #286 (`nav/ekf.py`): each is off by default, and each does what
its docstring says on synthetic records. Thresholds are regression guards, not requirements.

No committed scenario starts at rest and then moves after GPS loss (`challenge-timing` is static
throughout, the drone legs never stop), so the stationary hold's disarm path is covered only
here, with a synthetic IMU.
"""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import ekf

S = 1_000_000_000
G = 9.80665
HOLD = {"hold_rest_s": 30.0, "hold_speed_mps": 0.5, "hold_k": 3.0}


def _imu_and_gnss(move_at_s=None, speed_mps=0.0, gnss_until_s=60.0, end_s=120.0, seed=0):
    """Receiver at the origin (or moving east at `speed_mps` throughout); GNSS at 1 Hz until
    `gnss_until_s`, barometer at 10 Hz, a 100 Hz IMU with white noise. From `move_at_s` the IMU
    shows a walk: 0.5 m/s^2 of horizontal specific force swinging at 1 Hz."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(int(end_s * 100)):
        t = k / 100
        t_ns = round(t * S)
        f = np.array([0.0, 0.0, G]) + rng.normal(0, 0.015, 3)
        w = rng.normal(0, 0.0006, 3)
        if move_at_s is not None and t >= move_at_s:
            f[0] += 0.5 * np.sin(2 * np.pi * t)
            w[2] += 0.05 * np.cos(2 * np.pi * t)
        out.append(Measurement(t_ns=t_ns, source="imu", kind="accel_gyro",
                               value=(*f, *w), sigma=(0.03,) * 3 + (0.0006,) * 3))  # fmt: skip
        if k % 10 == 0:
            out.append(Measurement(t_ns=t_ns, source="baro", kind="altitude",
                                   value=(rng.normal(0, 0.3),), sigma=(0.5,)))  # fmt: skip
        if k % 100 == 0 and t < gnss_until_s:
            pos = (speed_mps * t + rng.normal(0, 1.0), rng.normal(0, 1.0), rng.normal(0, 1.5))
            out.append(Measurement(t_ns=t_ns, source="gnss", kind="position_enu", value=pos,
                                   sigma=(2.0, 2.0, 3.0)))  # fmt: skip
    return out


def _run(records, **config):
    k = ekf.EKF(**{**ekf.HONEST, **config})
    est = []
    for m in records:
        k.process(m)
        if m.kind == "accel_gyro" and m.t_ns % S == 0 and k.x is not None:
            est.append(k.estimate())
    return k, est


def test_every_field_option_is_off_by_default():
    k = ekf.EKF()
    assert (k.lte_min_cells, k.lte_max_hdop, k.lte_huber_k, k.common_step_ns) == (0, None, 0, 0)
    assert (k.zupt_sigma, k.lte_consistency_ns, k.hold_rest_ns) == (0.0, 0, 0)
    assert not (k.noise_freeze_gnss or k.curvature_inflate or k._slow_fixed())


def test_the_hold_arms_at_rest_and_keeps_the_velocity_at_zero():
    k, est = _run(_imu_and_gnss(), **HOLD)
    assert len(k.hold_armed_at) == 1 and not k.hold_disarmed_at
    assert k.hold_updates >= 55  # one a second from the loss (about 62 s) to 120 s
    assert max(np.hypot(*e.vel_enu[:2]) for e in est[-30:]) < 0.05
    _, free = _run(_imu_and_gnss())
    # without the hold the constant-velocity filter's velocity sigma grows unchecked
    assert est[-1].hpl_m < free[-1].hpl_m / 10


def test_the_hold_disarms_on_the_first_motion_and_does_not_rearm_without_gnss():
    k, _ = _run(_imu_and_gnss(move_at_s=90.0), **HOLD)
    assert len(k.hold_armed_at) == 1
    assert len(k.hold_disarmed_at) == 1
    assert 90 * S <= k.hold_disarmed_at[0] <= 92 * S  # within the first two 1 s tests
    updates = k.hold_updates
    assert 25 <= updates <= 30  # from the loss to the walk, and none after


def test_a_platform_moving_at_the_loss_never_arms_and_is_the_control_exactly():
    records = _imu_and_gnss(speed_mps=5.0)
    k, est = _run(records, **HOLD)
    assert not k.hold_armed_at and k.hold_updates == 0
    _, control = _run(records)
    assert est == control


def test_without_imu_records_the_hold_never_arms():
    records = [m for m in _imu_and_gnss() if m.kind != "accel_gyro"]
    k = ekf.EKF(**{**ekf.HONEST, **HOLD})
    for m in records:
        k.process(m)
    assert not k.hold_armed_at


@pytest.mark.parametrize("mode", ["skip", "clock"])
def test_too_few_cells_hold_a_radio_record_back(mode):
    k = ekf.EKF(**ekf.HONEST, lte_min_cells=3, lte_gate_mode=mode)
    k.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=(0.0, 0.0, 0.0),
                          sigma=(2.0, 2.0, 3.0)))  # fmt: skip
    towers = [(2000.0, 0.0, 30.0), (0.0, 2000.0, 30.0), (-2000.0, 0.0, 30.0)]
    for n, e in enumerate(towers):
        m = Measurement(t_ns=(n + 1) * 100_000_000, source="lte", kind="pseudorange",
                        emitter=f"lte:{n}", value=(float(np.linalg.norm(e)),), sigma=(50.0,),
                        meta={"emitter_enu": list(e), "rx_clock": "a"})  # fmt: skip
        assert k.geometry_hold(m, np.array(e)) == (mode if n < 2 else None)
