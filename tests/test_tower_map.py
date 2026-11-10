"""The tower map hand-off (P12, issue #96): the ground user in the sim, and the map's export,
JSON form, propagation and use as a filter's prior."""

import copy

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.core.time import s_to_ns
from pnt.metrics import gps_loss
from pnt.nav import ekf, tower_map
from pnt.nav.ekf import CALIBRATED, EKF, _two_state_q
from pnt.sim.scenario import T0_NS, generate, load

C = 299_792_458.0


def _short(clean: bool = False) -> dict:
    """The P12 scenario cut to 150 s: the user switches on at 60 s and loses GPS at 70 s."""
    spec = load("p12-drone-map-handoff")
    spec["duration_s"] = 150
    user = spec["ground_user"]
    user["start_s"] = 60
    user["faults"] = [{"type": "outage", "source": "gnss", "start_s": 70}]
    if clean:  # every random error off, so ranges can be checked
        for lte in (spec["sources"]["lte"], user["sources"]["lte"]):
            lte.update(sigma_m=1e-9)
            for k in ("multipath", "dropout", "told_position_sigma_m"):
                lte.pop(k, None)
    return spec


def _pr(meas):
    return {(m.t_ns, m.emitter): m for m in meas if m.kind == "pseudorange"}


def test_adding_the_ground_user_leaves_every_drone_record_unchanged_req10():
    spec = _short()
    without = copy.deepcopy(spec)
    del without["ground_user"]
    for seed in (0, 3):
        a, b = generate(spec, seed=seed), generate(without, seed=seed)
        assert a.measurements == b.measurements
        assert b.ground_user is None
        assert a.ground_user.measurements == generate(spec, seed=seed).ground_user.measurements


def test_the_user_hears_the_same_towers_and_clocks_from_its_own_place():
    run = generate(_short(clean=True), seed=2)
    user = run.ground_user
    drone, ground = _pr(run.measurements), _pr(user.measurements)
    both = sorted(set(drone) & set(ground))
    assert len(both) > 300  # 4 towers, 1 Hz, 90 s
    t_idx = {t.t_ns: i for i, t in enumerate(run.truth)}
    for key in both[::37]:
        d, g = drone[key], ground[key]
        assert d.meta == g.meta  # the same told tower position
        i = t_idx[key[0]]
        e = np.asarray(run.emitters[key[1]])
        rd = np.linalg.norm(np.asarray(run.truth[i].pos_enu) - e)
        rg = np.linalg.norm(np.asarray(user.truth[i].pos_enu) - e)
        clocks = C * (run.truth[i].clock_bias_s - user.truth[i].clock_bias_s)
        # The tower clock is in both readings, so it cancels in the difference
        assert d.value[0] - g.value[0] == pytest.approx(rd - rg + clocks, abs=1e-3)
    assert user.tower_clocks is run.tower_clocks


def test_the_user_switches_on_late_and_loses_gps():
    spec = _short()
    user = generate(spec, seed=0).ground_user
    t = np.array([m.t_ns for m in user.measurements])
    assert t.min() >= T0_NS + s_to_ns(60)
    fixes = [m.t_ns for m in user.measurements if m.kind == "position_enu"]
    assert fixes and max(fixes) < T0_NS + s_to_ns(70)
    assert gps_loss(user.spec, T0_NS)[0] == T0_NS + s_to_ns(70)
    assert {m.receiver for m in user.measurements} == {"payload"}  # no new receiver (ICD)


def _map(t_ns: int = 0, with_positions: bool = True) -> tower_map.TowerMap:
    rng = np.random.default_rng(0)
    n = 8 if with_positions else 4
    a = rng.normal(size=(n, n))
    return tower_map.TowerMap(
        t_ns=t_ns,
        clocks=("site:a", "site:b"),
        positions=(("a", (0.6, 0.8)), ("b", (-1.0, 0.0))) if with_positions else (),
        mean=rng.normal(0, 100, n),
        cov=a @ a.T + np.eye(n),
        sites={"lte:a": "a"},
    )


def _fix(t_ns: int) -> Measurement:
    return Measurement(
        t_ns=t_ns, source="gnss", kind="position_enu", value=(1.0, 2.0, 3.0), sigma=(2.5,) * 3
    )


def test_the_map_round_trips_through_json():
    m = _map(t_ns=T0_NS)
    back = tower_map.TowerMap.from_json(m.to_json())
    assert back.t_ns == m.t_ns and back.clocks == m.clocks and back.positions == m.positions
    assert np.array_equal(back.mean, m.mean) and np.array_equal(back.cov, m.cov)
    assert back.sites == m.sites and back.builders == m.builders


def test_the_map_is_the_prior_of_the_right_states():
    m = _map(t_ns=T0_NS)
    f = EKF(**CALIBRATED, tower_map=m)
    f.process(_fix(T0_NS))
    n = f.n_core
    assert f.clock_idx == {"site:a": n, "site:b": n + 2}
    assert f.position_idx["a"][0] == n + 4 and f.position_idx["b"][0] == n + 6
    assert np.array_equal(f.position_idx["a"][1], [0.6, 0.8])
    assert np.allclose(f.x[n:], m.mean)
    assert np.allclose(f.P[n:, n:], m.cov)
    assert not f.P[:n, n:].any()  # independent of the user's own states
    assert f.sites["lte:a"] == "a"
    # A mapped site is known at its first reading, so that reading is gated like any other
    assert f.clock_offsets("lte:a", 0.0) == ([n], False)
    assert f.clock_offsets("lte:new", 0.0)[1] is True


def test_the_map_is_carried_to_the_users_time_on_the_drift():
    m = _map(t_ns=T0_NS)
    dt = 120.0
    later = m.propagated(T0_NS + s_to_ns(dt), (0.04, 7e-8))
    for j in (0, 2):
        assert later.mean[j] == pytest.approx(m.mean[j] + dt * m.mean[j + 1])
        assert later.mean[j + 1] == m.mean[j + 1]
    assert np.array_equal(later.mean[4:], m.mean[4:])  # told-position errors are constant
    F = np.eye(8)
    F[0, 1] = F[2, 3] = dt
    Q = np.zeros((8, 8))
    Q[0:2, 0:2] = Q[2:4, 2:4] = _two_state_q(0.04, 7e-8, dt)
    assert np.allclose(later.cov, F @ m.cov @ F.T + Q)
    # A filter that starts later takes the map carried on its own coast model
    f = EKF(**CALIBRATED, tower_map=m)
    f.process(_fix(T0_NS + s_to_ns(dt)))
    want = m.propagated(f.t_ns, f.s_tower)
    assert np.allclose(f.x[f.n_core :], want.mean)
    assert np.allclose(f.P[f.n_core :, f.n_core :], want.cov)
    with pytest.raises(ValueError, match="back in time"):
        m.propagated(T0_NS - 1, (0.04, 7e-8))


def test_the_map_needs_the_tower_model_it_was_learned_with():
    with pytest.raises(ValueError, match="calibrated"):
        EKF(tower_map=_map(T0_NS)).process(_fix(T0_NS))
    with pytest.raises(ValueError, match="told-position"):
        cfg = {**CALIBRATED, "tower_position_sigma_m": 0.0}
        EKF(**cfg, tower_map=_map(T0_NS)).process(_fix(T0_NS))
    EKF(**{**CALIBRATED, "tower_position_sigma_m": 0.0}, tower_map=_map(T0_NS, False)).process(
        _fix(T0_NS)
    )


def test_a_drone_map_hands_off_to_the_ground_user():
    spec = _short()
    run = generate(spec, seed=1)
    start = T0_NS + s_to_ns(60)
    learned = tower_map.learn(run.measurements, start, origin_llh=spec["origin_llh"])
    assert learned.t_ns == start
    assert set(learned.clocks) == {f"site:lte:sim{i}" for i in range(4)}
    assert {s for s, _ in learned.positions} == {f"lte:sim{i}" for i in range(4)}
    sd = np.sqrt(np.diag(learned.cov))
    assert np.all(sd[1:8:2] < 1.0)  # drift learned below its 1 m/s prior (regression guard)
    user = run.ground_user.measurements
    plain = list(ekf.run_calibrated(user, origin_llh=spec["origin_llh"]))
    # No map: the path is the one without the option
    assert plain == list(ekf.run_calibrated(user, origin_llh=spec["origin_llh"], tower_map=None))
    aided = list(ekf.run_calibrated(user, origin_llh=spec["origin_llh"], tower_map=learned))
    assert len(aided) == len(plain) > 800
