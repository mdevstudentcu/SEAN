"""The IMU motion model (issue #12, stage 2): `EKF(motion="imu")`, nav/imu.py."""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import ESTIMATORS, base_rover, ekf, estimate
from pnt.nav.imu import MPU6050, rotation, rotations, wahba
from pnt.sim import sensors, trajectory
from pnt.sim.scenario import T0_NS, generate, load

LOOP = {"type": "loop", "radius_m": 150, "speed_mps": 8, "altitude_m": 30}
CIRCUIT = load("uc01-drone-circuit")["trajectory"]
MPU6050_SIM = sensors.MPU6050  # the sim's truth model, not the filter's ImuSpec


def session(traj, duration_s, gnss_until_s, seed=0, imu_gap=None, params=None):
    """GNSS fixes (5 Hz, 1 m) until `gnss_until_s`, and IMU samples (100 Hz) throughout, with
    none inside `imu_gap` (start_s, end_s). Returns (measurements, truth kinematics at 10 Hz)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, duration_s, 0.01)
    k = trajectory.kinematics(traj, t)
    accel, gyro = sensors.imu(t, k.specific_force_b, k.omega_b, rng, params or MPU6050_SIM)
    keep = np.ones(len(t), bool) if imu_gap is None else (t < imu_gap[0]) | (t >= imu_gap[1])
    ts_ns = T0_NS + np.round(t * 1e9).astype(np.int64)
    meas = sensors.imu_measurements(ts_ns[keep], accel[keep], gyro[keep])
    for i in range(0, len(t), 20):
        if t[i] < gnss_until_s:
            p = k.pos[i] + rng.normal(0.0, 1.0, 3)
            meas.append(Measurement(t_ns=int(ts_ns[i]), source="gnss", kind="position_enu",
                                    value=tuple(p), sigma=(1.0, 1.0, 1.5)))  # fmt: skip
    meas.sort(key=lambda m: (m.t_ns, m.source))
    return meas, k


def errors_at(estimates, k, t_s):
    est = {e.t_ns: e for e in estimates}
    i = int(round(t_s / 0.01))
    e = est[T0_NS + int(round(t_s * 1e9))]
    return np.subtract(e.pos_enu, k.pos[i]), e


def test_registered_and_opt_in():
    assert "ekf-imu" in ESTIMATORS and "ekf-base-imu" in ESTIMATORS
    assert ESTIMATORS["ekf-base-imu"].receivers == base_rover.run.receivers
    with pytest.raises(ValueError):
        ekf.EKF(motion="ins")


def test_the_default_ekf_ignores_imu_records():
    """motion="cv" stays the default, and IMU records change nothing in it."""
    spec = load("gps-outage")
    meas = [m for m in generate(spec, seed=0).measurements if m.t_ns < T0_NS + 150e9]
    no_imu = [m for m in meas if m.source != "imu"]
    o = spec["origin_llh"]
    assert list(ekf.run(meas, origin_llh=o)) == list(ekf.run(no_imu, origin_llh=o))


def test_rotation_helpers():
    phi = np.random.default_rng(0).normal(0.0, 0.5, (4, 3))
    phi[0] = 0.0
    batch = rotations(phi)
    for p, R in zip(phi, batch, strict=True):
        assert np.allclose(R, rotation(p))
        assert np.allclose(R @ R.T, np.eye(3))
    u = np.random.default_rng(1).normal(size=(6, 3))
    assert np.allclose(wahba(u, u @ batch[2].T), batch[2])


def test_imu_carries_position_through_a_gnss_gap_better_than_constant_velocity():
    """Drone circuit with the sim's MPU6050: GPS for 60 s, then 20 s without anything else.
    Regression guard, not a requirement: the IMU holds the position to a few metres where
    constant velocity, missing the curve, does far worse."""
    meas, k = session(CIRCUIT, 80.0, gnss_until_s=60.0)
    imu = list(ekf.run(meas, motion="imu"))
    cv = list(ekf.run(meas))
    e_imu, est = errors_at(imu, k, 79.9)
    e_cv, _ = errors_at(cv, k, 79.9)
    assert np.hypot(*e_imu[:2]) < 10.0
    assert np.hypot(*e_imu[:2]) < 0.5 * np.hypot(*e_cv[:2])
    assert est.trust.get("imu") == 1.0
    # Honest: the reported horizontal 1-sigma covers the error to within 3 sigma
    P = np.reshape(est.pos_cov, (3, 3))[:2, :2]
    assert e_imu[:2] @ np.linalg.solve(P, e_imu[:2]) < 3.0**2 * 2


def test_imu_dropout_falls_back_to_constant_velocity():
    """No IMU for 5 s while GPS is out: the filter keeps going on constant velocity, with a
    covariance that grows as constant velocity's does."""
    meas, k = session(LOOP, 70.0, gnss_until_s=60.0, imu_gap=(62.0, 67.0))
    est = list(ekf.run(meas, motion="imu"))
    by_t = {e.t_ns: e for e in est}

    def sigma(t_s):
        return np.sqrt(np.trace(np.reshape(by_t[T0_NS + int(t_s * 1e9)].pos_cov, (3, 3))[:2, :2]))

    assert est[-1].t_ns >= T0_NS + int(69.9e9)
    assert sigma(66.9) - sigma(62.0) > 5 * (sigma(61.9) - sigma(60.0))  # CV grows much faster
    assert by_t[T0_NS + int(66.0e9)].trust["imu"] == 0.0  # gnss_timeout_s without IMU use
    e, _ = errors_at(est, k, 69.9)
    assert np.all(np.isfinite(e))


def test_ekf_base_takes_the_imu_through_config():
    spec = load("uc01-drone-circuit-with-base")
    run = generate(spec, seed=0)
    meas = [m for m in run.measurements if m.t_ns < T0_NS + 60e9]
    est = list(estimate("ekf-base-imu", meas, origin_llh=spec["origin_llh"],
                        reference=run.reference))  # fmt: skip
    assert est and est[-1].trust.get("imu") == 1.0
    assert est[-1].trust.get("reference") == 1.0


def test_imu_states_sit_before_the_clocks_so_rollback_keeps_them():
    """Calibrated tower clocks roll back by state index: the IMU states must stay out of it."""
    f = ekf.EKF(motion="imu", clock_model="calibrated")
    f.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=(0.0, 0.0, 0.0),
                          sigma=(1.0, 1.0, 1.0)))  # fmt: skip
    assert f.n_core == ekf.N_CORE + 9 == len(f.x)
    assert f.imu.bg.stop == f.n_core


def test_worse_grade_spec_scales_every_term():
    worse = MPU6050.scaled(3.0)
    assert worse.accel_noise == pytest.approx(3 * MPU6050.accel_noise)
    assert worse.gyro_extra == pytest.approx(3 * MPU6050.gyro_extra)
