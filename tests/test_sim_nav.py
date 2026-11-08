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
