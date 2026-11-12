"""Heading at GPS loss (#276): S-turns before the loss, the magnetometer's `heading` records
(ADR-0051 Proposed) in the sim and in the opt-in `ekf-imu-mag`, and the study script."""

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import KINDS, SOURCES, Measurement
from pnt.nav import ESTIMATORS, ekf, estimate
from pnt.nav.imu import GRAVITY, rotation
from pnt.sim import sensors, trajectory
from pnt.sim.scenario import T0_NS, generate, load

TURNS = {"start_s": 5.0, "end_s": 55.0, "accel_mps2": 2.0, "period_s": 15.0}
CIRCUIT = load("uc01-drone-circuit")["trajectory"]
TURN = {"type": "loop", "radius_m": 40, "speed_mps": 10, "altitude_m": 30}


def _study():
    path = Path(__file__).resolve().parents[1] / "analysis" / "heading_at_loss.py"
    spec = importlib.util.spec_from_file_location("heading_at_loss", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- S-turns (sim/trajectory.py `manoeuvres`) ---------------------------------------------------
def test_s_turns_add_the_asked_sideways_acceleration_only_inside_their_window():
    t = np.arange(0.0, 70.0, 0.05)
    plain = trajectory.kinematics(CIRCUIT, t)
    k = trajectory.kinematics({**CIRCUIT, "manoeuvres": TURNS}, t)
    extra = np.hypot(*(k.acc - plain.acc)[:, :2].T)
    outside = (t < TURNS["start_s"]) | (t > TURNS["end_s"])
    assert np.all(extra[outside] < 1e-6)
    assert np.all(np.abs(k.pos - plain.pos)[outside] < 1e-9)
    # About the asked peak, and alternating: the sideways force changes side every half period
    assert 1.8 <= extra.max() <= 2.6
    side = np.einsum(
        "ij,ij->i", (k.acc - plain.acc)[:, :2], np.c_[-plain.vel[:, 1], plain.vel[:, 0]]
    )
    flips = np.sum(np.diff(np.sign(side[(t > 10) & (t < 50)])) != 0)
    assert flips >= 4


def test_s_turn_kinematics_integrate_back_to_the_truth():
    """An ideal IMU on the S-turn path, integrated from the true start, stays on the path: the
    offset's derivatives and the attitude agree (strapdown, 100 Hz, 60 s)."""
    traj = {**CIRCUIT, "manoeuvres": TURNS}
    t = np.arange(0.0, 60.0, 0.01)
    k = trajectory.kinematics(traj, t)
    R, p, v = k.rot[0].copy(), k.pos[0].copy(), k.vel[0].copy()
    for i in range(len(t) - 1):
        a = R @ k.specific_force_b[i] + GRAVITY
        p, v = p + v * 0.01 + 0.5 * a * 1e-4, v + a * 0.01
        R = R @ rotation(k.omega_b[i] * 0.01)
    assert np.linalg.norm(p - k.pos[-1]) < 0.5
    d = R @ k.rot[-1].T
    assert abs(math.degrees(math.atan2(d[1, 0], d[0, 0]))) < 0.05
    # `make` (measurement geometry) and `kinematics` (truth for the IMU) agree
    pos, vel = trajectory.make(traj, t)
    assert np.allclose(pos, k.pos) and np.allclose(vel, k.vel)


def test_s_turns_refuse_an_empty_window():
    with pytest.raises(ValueError):
        trajectory.make({**CIRCUIT, "manoeuvres": {**TURNS, "end_s": 5.0}}, np.arange(0.0, 1.0))


# --- the magnetometer in the sim ---------------------------------------------------------------
def test_icd_has_the_mag_source_and_heading_kind():
    assert "mag" in SOURCES and "heading" in KINDS
    icd = (Path(__file__).resolve().parents[1] / "systems" / "icd" / "measurement.md").read_text()
    assert "| `heading` |" in icd and "`mag`" in icd


def test_heading_of_is_clockwise_from_north():
    east = np.eye(3)[None]  # body x along east
    north = np.array([[[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]])  # body x north
    assert sensors.heading_of(east)[0] == pytest.approx(math.pi / 2)
    assert sensors.heading_of(north)[0] == pytest.approx(0.0)


def _with_mag(name="challenge-drone-outage", **mag):
    spec = load(name)
    spec["duration_s"] = 30.0
    plain = generate(spec, seed=3)
    spec["sources"] = {**spec["sources"], "mag": {"rate_hz": 10, **mag}}
    return spec, plain, generate(spec, seed=3)


def test_mag_records_are_truth_plus_one_bias_and_leave_every_other_record_alone():
    spec, plain, run = _with_mag(noise_deg=0.5)
    mag = [m for m in run.measurements if m.source == "mag"]
    assert mag and all(m.kind == "heading" for m in mag)
    assert [m for m in run.measurements if m.source != "mag"] == plain.measurements
    traj = {**spec["trajectory"], "_origin_llh": spec["origin_llh"]}
    t = np.array([(m.t_ns - T0_NS) / 1e9 for m in mag])
    res = np.array([m.value[0] for m in mag]) - sensors.heading_of(
        trajectory.kinematics(traj, t).rot
    )
    res = (res + math.pi) % (2 * math.pi) - math.pi
    # one constant per flight, plus white noise of the asked size
    assert np.std(res) == pytest.approx(math.radians(0.5), rel=0.15)
    assert abs(np.mean(res)) < math.radians(30.0)


def test_mag_bias_is_heavy_tailed_per_flight():
    rot = np.repeat(np.eye(3)[None], 3, axis=0)
    params = sensors.MagParams(noise_deg=0.0)
    biases = [
        math.degrees(sensors.magnetometer(rot, np.random.default_rng(s), params)[1])
        for s in range(2000)
    ]
    b = np.abs(biases)
    # Student-t with 4 dof, scale 2.5 deg: median |b| 1.85 deg; 2 % beyond 3.75 x scale
    assert np.median(b) == pytest.approx(1.85, rel=0.1)
    assert np.mean(b > 2.5 * 3.75) == pytest.approx(0.02, abs=0.008)


# --- the filter --------------------------------------------------------------------------------
def test_ekf_imu_mag_is_registered_opt_in_and_needs_the_imu():
    assert ESTIMATORS["ekf-imu-mag"].keywords == {"motion": "imu", "magnetometer": {}}
    assert "magnetometer" not in ESTIMATORS["ekf-imu"].keywords
    with pytest.raises(ValueError):
        ekf.EKF(magnetometer={})


def test_every_other_filter_ignores_heading_records():
    # 7 Hz: off the 10 Hz epochs, so a stray prediction at a heading record would show
    spec, plain, run = _with_mag(rate_hz=7)
    for name in ("ekf", "ekf-imu", "ekf-imu-guard"):
        a = list(estimate(name, plain.measurements, origin_llh=spec["origin_llh"]))
        b = list(estimate(name, run.measurements, origin_llh=spec["origin_llh"]))
        assert a == b, name
    # The baseline predicts to every record it is given, of any kind it then ignores (as for
    # `bearing` today): the same constant-velocity prediction in more steps, so rounding only
    a, b = (
        np.array([e.pos_enu for e in estimate("baseline", r.measurements, spec["origin_llh"])])
        for r in (plain, run)
    )
    assert np.allclose(a, b, atol=1e-6)


def _aligned_filter():
    """An EKF with the IMU forced aligned at a known attitude: tilted 10 deg, heading 30 deg."""
    f = ekf.EKF(motion="imu", magnetometer={})
    f.process(Measurement(t_ns=T0_NS, source="gnss", kind="position_enu", value=(0.0, 0.0, 0.0),
                          sigma=(1.0, 1.0, 1.0)))  # fmt: skip
    f.imu.R = rotation([0.0, 0.0, math.radians(60.0)]) @ rotation([math.radians(10.0), 0, 0])
    return f


def test_heading_jacobian_matches_numerical_differentiation():
    f = _aligned_filter()
    m = Measurement(t_ns=T0_NS, source="mag", kind="heading", value=(0.5,), sigma=(0.01,))
    y0, H, _, _ = ekf._heading(f, m)
    att = f.imu.att
    for i in range(3):
        f.x[att] = 0.0
        f.x[att.start + i] = 1e-6
        y1 = ekf._heading(f, m)[0]
        assert -(y1 - y0) / 1e-6 == pytest.approx(H[0, att.start + i], abs=1e-4)
    assert H[0, f.mag_bias_idx] == 1.0


def test_magnetometer_pulls_a_wrong_heading_back():
    """Aligned 90 deg off, then only heading records: the filter turns to them (the innovation
    is wrapped, and the attitude fold is exact for a large correction)."""
    f = _aligned_filter()
    truth = sensors.heading_of(f.imu.R[None])[0]
    f.imu.R = rotation([0.0, 0.0, math.radians(90.0)]) @ f.imu.R
    yaw = f.imu.att.start + 2
    f.P[yaw, yaw] = math.radians(120.0) ** 2  # as wide as an alignment the default accepts
    rng = np.random.default_rng(0)
    for k in range(1, 300):
        psi = truth + rng.normal(0.0, math.radians(1.0))
        f.process(Measurement(t_ns=T0_NS + k * 10_000_000, source="mag", kind="heading",
                              value=(psi,), sigma=(math.radians(1.0),)))  # fmt: skip
    R = rotation(f.x[f.imu.att]) @ f.imu.R
    err = (sensors.heading_of(R[None])[0] - truth + math.pi) % (2 * math.pi) - math.pi
    assert abs(math.degrees(err)) < 5.0  # heading plus bias equals the reading; bias prior 3 deg


# --- the study script ------------------------------------------------------------------------
def test_probed_run_is_the_registry_run():
    """The study reads the filter's attitude through its own copy of `ekf.run`'s loop: it must
    give the registry's estimates exactly."""
    h = _study()
    spec, _, run = _with_mag()
    for name in ("ekf-imu", "ekf-imu-mag"):
        ref = list(estimate(name, run.measurements, origin_llh=spec["origin_llh"]))
        got = h.probed(name, run.measurements, spec["origin_llh"], T0_NS + 29 * 10**9)
        assert got[0] == ref, name
        assert got[1] is not None  # aligned by 29 s on this leg


def test_study_ablation_names_the_aid_whose_loss_costs_more():
    h = _study()
    row = {"fallback_worst_m": 1.0}
    summary = {
        "plain / LTE / ekf-imu-mag": {**row, "t1_worst_m": 10.0},
        "plain / no LTE / ekf-imu-mag": {**row, "t1_worst_m": 30.0},
        "plain / LTE / ekf-imu": {**row, "t1_worst_m": 15.0},
    }
    assert h.ablation(summary)[-1].endswith("| LTE | met |")
    summary["plain / LTE / ekf-imu"]["t1_worst_m"] = 40.0
    assert h.ablation(summary)[-1].endswith("| heading (magnetometer) | not met |")
