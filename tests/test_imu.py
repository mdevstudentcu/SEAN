"""The IMU motion model (issue #12, stage 2): `EKF(motion="imu")`, nav/imu.py."""

import dataclasses
import math

import msgspec
import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.integrity.jump_guard import JumpGuard
from pnt.nav import ESTIMATORS, base_rover, ekf, estimate
from pnt.nav.imu import MPU6050, rotation, rotations, wahba
from pnt.sim import sensors, trajectory
from pnt.sim.scenario import T0_NS, generate, load

LOOP = {"type": "loop", "radius_m": 150, "speed_mps": 8, "altitude_m": 30}
TURN = {"type": "loop", "radius_m": 40, "speed_mps": 10, "altitude_m": 30}  # about 14 deg of tilt
CIRCUIT = load("uc01-drone-circuit")["trajectory"]
MPU6050_SIM = sensors.MPU6050  # the sim's truth model, not the filter's ImuSpec


def session(
    traj, duration_s, gnss_until_s, seed=0, imu_gap=None, params=None, start_s=0.0, gnss_sigma=1.0
):
    """GNSS fixes (5 Hz, 1 m unless `gnss_sigma`) until `gnss_until_s`, and IMU samples (100 Hz)
    throughout, with none inside `imu_gap` (start_s, end_s). The session starts `start_s` into
    the trajectory. Returns (measurements, truth kinematics at 10 Hz)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, duration_s, 0.01)
    k = trajectory.kinematics(traj, t + start_s)
    accel, gyro = sensors.imu(t, k.specific_force_b, k.omega_b, rng, params or MPU6050_SIM)
    keep = np.ones(len(t), bool) if imu_gap is None else (t < imu_gap[0]) | (t >= imu_gap[1])
    ts_ns = T0_NS + np.round(t * 1e9).astype(np.int64)
    meas = sensors.imu_measurements(ts_ns[keep], accel[keep], gyro[keep])
    for i in range(0, len(t), 20):
        if t[i] < gnss_until_s:
            p = k.pos[i] + rng.normal(0.0, gnss_sigma, 3)
            meas.append(Measurement(t_ns=int(ts_ns[i]), source="gnss", kind="position_enu",
                                    value=tuple(p),
                                    sigma=(gnss_sigma, gnss_sigma, 1.5 * gnss_sigma)))  # fmt: skip
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
    """Drone circuit with the sim's MPU6050: GPS for 60 s, then 10 s without anything else.
    Regression guard, not a requirement: the IMU holds the position far better than constant
    velocity, which misses the curve (seed 0: about 6 m against 27 m)."""
    meas, k = session(CIRCUIT, 70.0, gnss_until_s=60.0)
    imu = list(ekf.run(meas, motion="imu"))
    cv = list(ekf.run(meas))
    e_imu, est = errors_at(imu, k, 69.9)
    e_cv, _ = errors_at(cv, k, 69.9)
    assert np.hypot(*e_imu[:2]) < 15.0
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
    # Regression guard, not a requirement: constant velocity grows the sigma much faster (the
    # ratio measures about 11 on seeds 0-2; 5 leaves room)
    assert sigma(66.9) - sigma(62.0) > 5 * (sigma(61.9) - sigma(60.0))
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

    # One tower, then a rollback past a corrupted clock: the clock comes back, the IMU stays
    f.process(Measurement(t_ns=1_000_000_000, source="lte", kind="pseudorange", emitter="lte:1:1",
                          value=(1000.0,), sigma=(5.0,),
                          meta={"emitter_enu": [1000.0, 0.0, 0.0]}))  # fmt: skip
    f.predict(2_000_000_000)  # the snapshot the rollback restores
    i = f.n_core
    assert list(f.clock_idx.values()) == [i]
    offset, drift = f.x[i], f.x[i + 1]
    f.predict(4_000_000_000)
    f.x[f.imu.att.start : f.imu.bg.stop] = np.arange(1.0, 10.0) * 1e-3  # distinct IMU states
    f.x[i] += 500.0
    core_x, core_P = f.x[:i].copy(), f.P[:i, :i].copy()

    f.rollback(13_000_000_000)  # target: 3 s, so the snapshot at 2 s

    assert f.rollbacks == [(13_000_000_000, 2_000_000_000)]
    assert f.x[i] == pytest.approx(offset + 2.0 * drift)
    assert np.array_equal(f.x[:i], core_x)
    assert np.array_equal(f.P[:i, :i], core_P)


ATTITUDE = rotation([0.2, -0.3, 1.1])
PREDICT_NS = 350_000_000  # three covariance chunks of `max_step_s`


def motion_samples(gap):
    """100 Hz samples with strongly varying force and rate, none inside `gap` (start_s, end_s)."""
    out = []
    for i in range(36):
        t = i * 0.01
        if gap is None or not gap[0] <= t < gap[1]:
            f = (1.5 + 2.0 * math.sin(3.0 * t), -1.0 + math.cos(2.0 * t), 9.5 + 0.8 * t)
            w = (0.4 + 0.5 * t, -0.3 + math.sin(5.0 * t), 0.6)
            out.append(Measurement(t_ns=i * 10_000_000, source="imu", kind="accel_gyro",
                                   value=(*f, *w), sigma=(1.0,) * 6))  # fmt: skip
    return out


def aligned_filter(samples, dx=None):
    """A filter at t=0, already aligned to ATTITUDE, with `samples` buffered; `dx` is added to
    its (position, velocity, attitude error, accel bias, gyro bias)."""
    f = ekf.EKF(motion="imu")
    f.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=(0.0, 0.0, 0.0),
                          sigma=(1.0, 1.0, 1.0)))  # fmt: skip
    f.imu.R = ATTITUDE.copy()
    nominal = [10.0, -5.0, 30.0, 3.0, -2.0, 0.5, 0.0, 0.0, 0.0]
    f.x[f.imu.nav] = [*nominal, 0.05, -0.03, 0.02, 0.002, -0.001, 0.003]
    if dx is not None:
        f.x[f.imu.nav] += dx
    for s in samples:
        f.process(s)
    return f


def propagated(samples, attitude_ref, dx):
    """The real prediction (`EKF.predict`) from a perturbed start, as the state vector with the
    attitude error written as the small rotation from `attitude_ref`."""
    f = aligned_filter(samples, dx)
    f.predict(PREDICT_NS)
    out = f.x[f.imu.nav].copy()
    d = f.imu.R @ attitude_ref.T
    out[6:9] = np.array([d[2, 1] - d[1, 2], d[0, 2] - d[2, 0], d[1, 0] - d[0, 1]]) / 2.0
    return out


@pytest.mark.parametrize("gap, bg_tol", [(None, 0.05), ((0.1, 0.3), 0.4)])
def test_transition_matches_numerical_differentiation_of_the_prediction(gap, bg_tol):
    """The transition `ImuMotion.propagate` gives `EKF.predict`, against central differences of
    the prediction itself, over several chunks and across an IMU gap.

    Regression guard, not a requirement: the transition is first order in the chunk length, and
    the rates here are far above a drone's. Measured worst error per block: 0.4 % (gyro-bias
    columns 4.3 %). With the gap, one chunk takes a whole held sample and reaches 0.19 s, so the
    gyro-bias columns are off by up to 35 %. A sign or factor error is 100 % or more."""
    samples = motion_samples(gap)
    nominal = aligned_filter(samples)
    nominal.predict(PREDICT_NS)
    reference = nominal.imu.R.copy()

    f = aligned_filter(samples)
    F, Q = np.eye(len(f.x)), np.zeros((len(f.x), len(f.x)))
    f.imu.propagate(f, PREDICT_NS, F, Q)
    analytic = F[np.ix_(f.imu.nav, f.imu.nav)]

    h = 1e-6
    numeric = np.zeros((15, 15))
    for i in range(15):
        dx = h * np.eye(15)[i]
        numeric[:, i] = propagated(samples, reference, dx) - propagated(samples, reference, -dx)
        numeric[:, i] /= 2 * h

    for row in range(0, 15, 3):
        for col in range(0, 15, 3):
            a, n = analytic[row : row + 3, col : col + 3], numeric[row : row + 3, col : col + 3]
            tol = bg_tol if col == 12 else 0.01
            assert np.linalg.norm(a - n) <= tol * np.linalg.norm(n) + 1e-6, (row, col)


@pytest.mark.parametrize("start_s", [0.0, 8.0, 16.0])  # true heading about -112, 2 and 117 deg
def test_alignment_recovers_a_known_heading_on_a_turn(start_s):
    """In-flight alignment on a hard turn. GNSS is near-perfect here so the filter's velocity
    tracks the truth and only the alignment itself is under test.

    Regression guard, not a requirement: measured under 1 deg of heading and 0.3 deg of tilt.
    With 1 m GNSS see `test_heading_sigma_bounds_the_error_on_a_hard_turn_issue_119`."""
    meas, k = session(TURN, 30.0, gnss_until_s=30.0, start_s=start_s, gnss_sigma=0.01)
    f = ekf.EKF(motion="imu")
    for m in meas:
        f.process(m)
        if f.imu.R is not None:
            break
    assert f.imu.aligned_at is not None
    d = f.imu.R @ k.rot[round((f.imu.aligned_at - T0_NS) / 1e7)].T
    assert abs(math.degrees(math.atan2(d[1, 0], d[0, 0]))) < 5.0
    assert math.degrees(math.acos(min(d[2, 2], 1.0))) < 1.0


HOVER = {"type": "loop", "radius_m": 1.0, "speed_mps": 0.0, "altitude_m": 30}


def heading_at_alignment(traj, seed, gnss_sigma=1.0, start_s=0.0, gyro=1.0, spoof=None, **config):
    """(heading error, reported heading 1-sigma) in degrees when the filter aligns within 60 s of
    GNSS, or None if it never does. `gyro` scales the gyro's noise and biases, in the sim and in
    what the filter is told alike; `spoof(t_s)` is added to every GNSS fix; `config` goes to the
    filter."""
    sim = dataclasses.replace(
        MPU6050_SIM,
        gyro_noise_dps_rthz=gyro * MPU6050_SIM.gyro_noise_dps_rthz,
        gyro_bias_dps=gyro * MPU6050_SIM.gyro_bias_dps,
        gyro_instability_dph=gyro * MPU6050_SIM.gyro_instability_dph,
    )
    told = dataclasses.replace(
        MPU6050,
        gyro_noise=gyro * MPU6050.gyro_noise,
        gyro_bias=gyro * MPU6050.gyro_bias,
        gyro_bias_rw=gyro * MPU6050.gyro_bias_rw,
    )
    meas, k = session(traj, 60.0, 60.0, seed, params=sim, start_s=start_s, gnss_sigma=gnss_sigma)
    if spoof is not None:
        meas = [
            msgspec.structs.replace(m, value=tuple(np.add(m.value, spoof((m.t_ns - T0_NS) / 1e9))))
            if m.source == "gnss"
            else m
            for m in meas
        ]
    f = ekf.EKF(motion="imu", imu={"spec": told}, **config)
    for m in meas:
        f.process(m)
        if f.imu.R is not None:
            break
    if f.imu.aligned_at is None:
        return None
    d = f.imu.R @ k.rot[round((f.imu.aligned_at - T0_NS) / 1e7)].T
    sigma = math.sqrt(f.P[f.imu.att.start + 2, f.imu.att.start + 2])
    assert sigma == pytest.approx(f.imu.yaw_sigma)
    return math.degrees(math.atan2(d[1, 0], d[0, 0])), math.degrees(sigma)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("start_s", [0.0, 8.0, 16.0])
def test_heading_sigma_bounds_the_error_on_a_hard_turn_issue_119(start_s, seed):
    """1 m GNSS on a 14 deg-tilt turn. The constant-velocity filter's velocity lags the turn;
    before #119 that biased heading by -6 to -22 deg while the filter reported 3 deg."""
    err, sigma = heading_at_alignment(TURN, seed, start_s=start_s)
    assert abs(err) <= 3.0 * sigma
    # Regression guards, not requirements: measured under 9 deg of error and 10.5 to 11.2 deg
    # of sigma on these runs, so the bound is not met by a sigma too wide to use
    assert abs(err) < 12.0
    assert sigma < 15.0


@pytest.mark.parametrize("gyro", [1.0, 3.0, 10.0])
def test_hover_never_aligns_issue_119(gyro):
    """Heading is unobservable in a hover, however noisy the gyro: alignment is refused."""
    for seed in range(3):
        assert heading_at_alignment(HOVER, seed, gyro=gyro) is None


SPOOFS = {  # added to every GNSS fix during the alignment window (m, ENU)
    "jump 30 m at 4 s": lambda t: (30.0 * (t >= 4.0), 0.0, 0.0),
    "ramp 2 m/s from 3 s": lambda t: (2.0 * max(t - 3.0, 0.0), 0.0, 0.0),
    "accelerating 0.5 m/s^2 east": lambda t: (0.25 * max(t - 3.0, 0.0) ** 2, 0.0, 0.0),
    "accelerating 0.5 m/s^2 north": lambda t: (0.0, 0.25 * max(t - 3.0, 0.0) ** 2, 0.0),
}


@pytest.mark.parametrize("spoof", SPOOFS, ids=list(SPOOFS))
@pytest.mark.parametrize(
    ("traj", "gnss_sigma"), [(TURN, 1.0), (CIRCUIT, 2.5)], ids=["turn", "uc01"]
)
def test_heading_sigma_bounds_the_error_with_gnss_spoofed_during_alignment_issue_119(
    spoof, traj, gnss_sigma
):
    """On the hard turn and on the gentle UC-01 circuit, where heading is barely observable in
    one window (sigma tens of degrees). Seeds 0-2: every one aligns. Without the opt-in jump
    guard (#184): with it the jump is refused and the filter never aligns (checked below)."""
    for seed in range(3):
        err, sigma = heading_at_alignment(traj, seed, gnss_sigma, spoof=SPOOFS[spoof])
        assert abs(err) <= 3.0 * sigma, seed


@pytest.mark.parametrize(
    ("traj", "gnss_sigma"), [(TURN, 1.0), (CIRCUIT, 2.5)], ids=["turn", "uc01"]
)
def test_a_gnss_jump_during_alignment_is_refused_not_aligned_on_issue_184(traj, gnss_sigma):
    for seed in range(3):
        spoof = SPOOFS["jump 30 m at 4 s"]
        guarded = heading_at_alignment(traj, seed, gnss_sigma, spoof=spoof, jump_guard=JumpGuard)
        assert guarded is None, seed


def test_worse_grade_spec_scales_every_term():
    worse = MPU6050.scaled(3.0)
    assert worse.accel_noise == pytest.approx(3 * MPU6050.accel_noise)
    assert worse.gyro_extra == pytest.approx(3 * MPU6050.gyro_extra)
