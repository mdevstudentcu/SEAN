import numpy as np

from pnt.io.mcap_log import SessionWriter, read_session
from pnt.metrics import score
from pnt.nav import baseline
from pnt.sim.scenario import T0_NS, generate, load
from pnt.sources.replay import ReplaySource


def test_scenarios_are_reproducible():
    a = generate(load("gps-outage"), seed=3).measurements[:50]
    b = generate(load("gps-outage"), seed=3).measurements[:50]
    assert a == b


def test_outage_removes_gnss_in_window_only():
    run = generate(load("gps-outage"), seed=0)
    gnss_t = np.array([(m.t_ns - T0_NS) / 1e9 for m in run.measurements if m.source == "gnss"])
    assert not np.any((gnss_t >= 120) & (gnss_t < 240))
    assert np.any(gnss_t < 120) and np.any(gnss_t >= 240)


def test_baseline_stays_bounded_through_outage():
    spec = load("gps-outage")
    run = generate(spec, seed=0)
    m = score(list(baseline.run(run.measurements)), run.truth, spec, T0_NS)
    assert m.h_rmse_m < 20  # loose regression guard, not a requirement
    assert m.hpl_bound_frac > 0.95


def test_replay_matches_sim(tmp_path):
    spec = load("gps-outage")
    run = generate(spec, seed=1)
    path = tmp_path / "s.mcap"
    with SessionWriter(path) as w:
        for t in run.truth:
            w.write("/truth", t)
        for meas in run.measurements:
            w.write(f"/meas/{meas.source}", meas)
    replayed = list(ReplaySource(path))
    assert replayed == run.measurements
    assert sum(1 for _ in read_session(path, topics=["/truth"])) == len(run.truth)


def test_replay_can_hide_a_source(tmp_path):
    run = generate(load("gps-outage"), seed=0)
    path = tmp_path / "s.mcap"
    with SessionWriter(path) as w:
        for meas in run.measurements:
            w.write(f"/meas/{meas.source}", meas)
    hidden = list(ReplaySource(path, hide={"gnss": (T0_NS, None)}))
    assert all(m.source != "gnss" for m in hidden)


def test_imu_records_leave_every_other_record_unchanged():
    """The IMU draws from its own stream, so a scenario with it is the same run plus IMU records,
    and an estimator that ignores the IMU gives the same estimates."""
    spec = load("gps-outage")
    without = {**spec, "sources": {k: v for k, v in spec["sources"].items() if k != "imu"}}
    a = generate(spec, seed=2).measurements
    b = generate(without, seed=2).measurements
    imu = [m for m in a if m.source == "imu"]
    assert [m for m in a if m.source != "imu"] == b
    assert {m.kind for m in imu} == {"accel_gyro"}
    assert set(np.diff([m.t_ns for m in imu])) == {10_000_000}  # 100 Hz
    f = np.array([m.value[:3] for m in imu])
    assert abs(np.linalg.norm(f, axis=1).mean() - 9.81) < 0.2  # hovering-ish: about 1 g
    assert list(baseline.run(a)) == list(baseline.run(b))
