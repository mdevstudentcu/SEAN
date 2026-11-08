import numpy as np
import pytest

from pnt.core.frames import llh_to_enu
from pnt.metrics import score
from pnt.nav import baseline
from pnt.sim import trajectory as tr
from pnt.sim.scenario import T0_NS, generate, load

G = 9.80665
LOOP = {"type": "loop", "radius_m": 150, "speed_mps": 8, "altitude_m": 30}
CIRCUIT = {
    "type": "waypoints", "closed": True, "speed_mps": 8, "corner_radius_m": 40,
    "points": [[0, 0, 40], [250, 50, 40], [300, 300, 45], [0, 350, 40], [-200, 150, 40]],
}  # fmt: skip


def test_loop_kinematics_match_circular_motion():
    k = tr.kinematics(LOOP, np.linspace(0, 60, 601))
    a = 8**2 / 150
    assert np.allclose(np.linalg.norm(k.acc, axis=1), a)
    tilt = np.degrees(np.arccos(k.rot[:, 2, 2]))
    assert np.allclose(tilt, np.degrees(np.arctan(a / G)), atol=1e-6)  # multirotor leans in
    # Body z is tilted, so it sees the world yaw rate scaled by cos(tilt)
    assert np.allclose(k.omega_b[:, 2], 8 / 150 * np.cos(np.arctan(a / G)), rtol=1e-6)


def test_accelerometer_reads_thrust_along_body_z_for_a_multirotor():
    k = tr.kinematics(LOOP, np.linspace(0, 30, 301))
    f = k.specific_force_b
    assert np.allclose(f[:, :2], 0.0, atol=1e-9)
    assert np.allclose(f[:, 2], np.hypot(G, 8**2 / 150))


def test_waypoint_path_flies_at_constant_speed_and_stays_smooth():
    k = tr.kinematics(CIRCUIT, np.linspace(0, 300, 3001))
    assert np.allclose(np.linalg.norm(k.vel, axis=1), 8.0, atol=1e-6)
    assert np.linalg.norm(k.acc, axis=1).max() < 2.0  # no corner spikes
    eye = np.einsum("nij,nik->njk", k.rot, k.rot)
    assert np.allclose(eye, np.eye(3), atol=1e-12)
    assert np.allclose(np.linalg.norm(k.quat, axis=1), 1.0)


def test_waypoint_path_passes_close_to_its_corners():
    k = tr.kinematics(CIRCUIT, np.linspace(0, 400, 40001))
    for p in CIRCUIT["points"]:
        assert np.min(np.linalg.norm(k.pos - p, axis=1)) < 40  # within the corner radius


def test_open_path_stops_at_the_last_waypoint():
    spec = {"type": "waypoints", "speed_mps": 10, "points": [[0, 0, 0], [100, 0, 0]]}
    pos, vel = tr.make(spec, np.array([5.0, 20.0, 30.0]))
    assert np.allclose(pos[1:], [100, 0, 0]) and np.allclose(vel[1:], 0)


def test_fixed_wing_glide_path_pitch_and_ground_vehicle_stays_level():
    spec = load("uc02-yow-approach")
    traj = {**spec["trajectory"], "_origin_llh": spec["origin_llh"]}
    k = tr.kinematics(traj, np.linspace(1, 100, 100))
    pitch = np.degrees(np.arcsin(k.rot[:, 2, 0]))  # body x elevation in ENU
    assert np.allclose(pitch, -3.0, atol=0.1)
    car = {**load("vehicle-street-grid")["trajectory"]}
    kc = tr.kinematics(car, np.linspace(0, 200, 2001))
    assert np.allclose(kc.rot[:, :, 2], [0, 0, 1], atol=1e-9)  # body z stays up: no bank


def test_points_llh_use_the_scenario_origin():
    o = [45.3876, -75.6960, 70.0]
    llh = [[45.39, -75.69, 80.0], [45.40, -75.69, 80.0]]
    spec = {"type": "waypoints", "speed_mps": 10, "points_llh": llh, "_origin_llh": o}
    pos, _ = tr.make(spec, np.array([0.0]))
    assert np.allclose(pos[0], llh_to_enu(llh[0], o), atol=1e-6)
    with pytest.raises(ValueError, match="origin"):
        tr.make({k: v for k, v in spec.items() if k != "_origin_llh"}, np.array([0.0]))


def test_square_is_refused_for_imu_kinematics_but_still_makes_positions():
    sq = {"type": "square", "side_m": 200, "speed_mps": 8, "altitude_m": 30}
    with pytest.raises(ValueError, match="instant turns"):
        tr.kinematics(sq, np.array([0.0]))
    assert tr.make(sq, np.array([0.0]))[0].shape == (1, 3)


@pytest.mark.parametrize(
    "name", ["uc01-drone-circuit", "uc02-yow-approach", "vehicle-street-grid"]
)
def test_use_case_scenarios_run_and_baseline_does_not_lock_out(name):
    spec = load(name)
    run = generate(spec, seed=0)
    est = list(baseline.run(run.measurements, origin_llh=spec["origin_llh"]))
    m = score(est, run.truth, spec, T0_NS)
    # Loose guard: the YOW approach used to diverge to km-level error (GNSS gate lockout)
    assert m.h_rmse_m < 60 and m.hpl_bound_frac > 0.9
