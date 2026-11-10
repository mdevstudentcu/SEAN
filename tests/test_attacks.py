import numpy as np
import pytest

from pnt.core.frames import llh_to_enu
from pnt.sim import attacks, trajectory
from pnt.sim.scenario import T0_NS, generate, load


def _gnss(run, kind):
    return [m for m in run.measurements if m.source == "gnss" and m.kind == kind]


def _clean(name, seed=0):
    spec = load(name)
    spec["faults"] = []
    return generate(spec, seed=seed)


def _t(m):
    return (m.t_ns - T0_NS) / 1e9


def test_every_documented_attack_is_registered_and_unknown_fails():
    assert set(attacks._ATTACKS) == {
        "outage", "spoof_ramp", "spoof_jump", "time_spoof", "meaconing", "jamming_zone",
        "tower_clock_step", "gps_no_fix", "gps_low_sats", "baro_drift", "reference_moved",
        "reference_clock_step", "tower_holdover", "imu_degradation", "spoof_zone",
        "hostile_power", "hostile_moves",
    }  # fmt: skip
    spec = load("spoof-jump")
    spec["faults"] = [{"type": "teleport", "start_s": 1}]
    with pytest.raises(ValueError, match="unknown fault type"):
        generate(spec)


def test_spoof_jump_offsets_position_only_after_start():
    attacked, clean = generate(load("spoof-jump"), seed=1), _clean("spoof-jump", seed=1)
    for a, c in zip(_gnss(attacked, "position_enu"), _gnss(clean, "position_enu"), strict=True):
        expected = [300.0, 0.0, 0.0] if _t(a) >= 150 else [0.0, 0.0, 0.0]
        assert np.allclose(np.subtract(a.value, c.value), expected)


def test_time_spoof_ramps_time_and_leaves_position_alone():
    attacked, clean = generate(load("time-spoof"), seed=2), _clean("time-spoof", seed=2)
    assert _gnss(attacked, "position_enu") == _gnss(clean, "position_enu")
    for a, c in zip(_gnss(attacked, "time"), _gnss(clean, "time"), strict=True):
        expected = max(0.0, _t(a) - 150) * 50e-9
        assert a.value[0] - c.value[0] == pytest.approx(expected, abs=1e-15)


def test_meaconing_reports_where_you_were():
    spec = load("meaconing")
    run = generate(spec, seed=3)
    late = [m for m in _gnss(run, "position_enu") if _t(m) >= 150]
    t = np.array([_t(m) for m in late])
    pos = np.array([m.value for m in late])
    then = trajectory.make(spec["trajectory"], t - 5.0)[0]
    now = trajectory.make(spec["trajectory"], t)[0]
    assert np.median(np.linalg.norm((pos - then)[:, :2], axis=1)) < 6  # noise only
    assert np.median(np.linalg.norm((pos - now)[:, :2], axis=1)) > 35  # ~40 m behind
    times = {m.t_ns: m.value[0] for m in _gnss(run, "time")}
    clean_times = {m.t_ns: m.value[0] for m in _gnss(_clean("meaconing", seed=3), "time")}
    after = [k for k in times if (k - T0_NS) / 1e9 >= 150]
    assert all(times[k] - clean_times[k] == pytest.approx(5.0) for k in after)


def test_jamming_zone_degrades_then_drops_gnss_near_the_jammer():
    spec = load("jamming-zone")
    run = generate(spec, seed=4)
    f = spec["faults"][0]
    center = llh_to_enu(f["center_llh"], spec["origin_llh"])

    def dist(m):
        p = trajectory.make(spec["trajectory"], np.array([_t(m)]))[0][0]
        return np.hypot(*(p[:2] - center[:2]))

    fixes = _gnss(run, "position_enu")
    assert fixes and all(dist(m) >= f["radius_m"] for m in fixes)  # lost inside
    near = [m for m in fixes if dist(m) < f["onset_m"]]
    far = [m for m in fixes if dist(m) >= f["onset_m"]]
    assert near and all(m.sigma[0] > far[0].sigma[0] for m in near)  # honest, larger sigma
    health = _gnss(run, "gnss_health")
    inside = [h for h in health if dist(h) < f["radius_m"]]
    assert inside and all(h.value[0] == 1.0 and h.value[1] == 0 for h in inside)
    assert all(h.value == attacks.NOMINAL_HEALTH for h in health if dist(h) >= f["onset_m"])


def test_time_measurements_need_a_clock_model():
    spec = load("time-spoof")
    del spec["clock"]
    with pytest.raises(ValueError, match="clock"):
        generate(spec)


def test_truth_carries_the_receiver_clock():
    run = generate(load("time-spoof"), seed=5)
    drift = (run.truth[-1].clock_bias_s - run.truth[0].clock_bias_s) / 360
    assert drift == pytest.approx(50e-9, rel=0.2)  # 50 ppb drift in the scenario
