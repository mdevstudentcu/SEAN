"""The opt-in sim error terms of #278: each is off in every committed scenario, does what it says
when on, and leaves every other draw as it was (its own random stream). Sim evidence only."""

import copy

import numpy as np
import pytest

from pnt.sim import lte_front_end, models, sensors
from pnt.sim.lte_front_end import AMBIGUITY_M
from pnt.sim.scenario import T0_NS, generate, load, scenario_names

# Numeric limits in this file are regression guards or follow from the model's definition, not
# requirements.
SITE = {"offset_m": 1000.0, "offset_rw_m": 0.2}


def _spec(duration_s: float = 60.0, imu: bool = False, **extra) -> dict:
    """gps-outage cut short, without faults, its tower clocks grouped per site (ADR-0022)."""
    spec = copy.deepcopy(load("gps-outage"))
    spec.update(duration_s=duration_s, faults=[], tower_clocks={"site": dict(SITE)}, **extra)
    for key in ("clock_rw_m", "init_bias_m"):
        del spec["sources"]["lte"][key]
    if not imu:
        spec["sources"].pop("imu")
    return spec


def _front_end(duration_s: float = 120.0, **lte) -> dict:
    """The UC-01 circuit cut short with front-end LTE records heard within 3 km, no IMU."""
    spec = copy.deepcopy(load("uc01-drone-circuit"))
    spec.update(duration_s=duration_s, faults=[])
    spec["tower_clocks"] = {"site": {"offset_m": AMBIGUITY_M / 2, "offset_rw_m": 0.2}}
    spec["sources"].pop("imu")
    spec["sources"]["lte"] = {
        "model": "pseudorange",
        "record_shape": "front_end",
        "rate_hz": 1,
        "cells_from": {"file": "lte-cells-ottawa.csv", "earfcn": 2460},
        "hearing": {"model": "range", "hearing_km": 3.0},
        "sigma_m": 20.0,
        **lte,
    }
    return spec


def _by_key(run, source=None):
    return {
        (m.t_ns, m.source, m.kind, m.emitter): m
        for m in run.measurements
        if source is None or m.source == source
    }


def _others_identical(a, b, source):
    assert [m for m in a.measurements if m.source != source] == [
        m for m in b.measurements if m.source != source
    ]


def _walk(spec: dict):
    """Every mapping in a spec, nested ones and those in lists included."""
    if isinstance(spec, dict):
        yield spec
        for v in spec.values():
            yield from _walk(v)
    elif isinstance(spec, list):
        for v in spec:
            yield from _walk(v)


def test_no_committed_scenario_turns_a_278_term_on():
    keys = {"troposphere", "arcs", "board_temperature", "gyro_temp_dps_per_k", "temp_m_per_k"}
    for name in scenario_names():
        spec = load(name)
        for d in _walk(spec):
            assert not keys & set(d), (name, keys & set(d))
            assert "steering" not in (spec.get("tower_clocks") or {}), name
            if d.get("type") == "tower_holdover":
                assert d.get("grade", "ocxo") != "mixture", name
                assert "reach_probability" not in d, name
        sector = (spec.get("tower_clocks") or {}).get("sector")
        assert not sector, name


def test_troposphere_adds_its_delay_per_km_of_range_and_nothing_else():
    off = generate(_spec(), seed=3)
    on_spec = _spec()
    on_spec["sources"]["lte"]["troposphere"] = {"m_per_km": [0.3, 0.4]}
    on = generate(on_spec, seed=3)
    _others_identical(on, off, "lte")
    a, b = _by_key(on, "lte"), _by_key(off, "lte")
    assert a.keys() == b.keys()
    truth = {g.t_ns: np.array(g.pos_enu) for g in off.truth}
    per_km: dict[str, list[float]] = {}
    for k, m in a.items():
        rng = np.linalg.norm(truth[m.t_ns] - np.array(off.emitters[m.emitter]))
        per_km.setdefault(m.emitter, []).append((m.value[0] - b[k].value[0]) / rng * 1e3)
    for emitter, ks in per_km.items():
        assert np.ptp(ks) < 1e-6, emitter  # one value per tower
        assert 0.3 <= ks[0] <= 0.4, emitter
    assert len({round(ks[0], 6) for ks in per_km.values()}) == len(per_km)  # differs per tower


def test_troposphere_constant_is_the_same_on_every_tower():
    assert np.array_equal(models.troposphere(np.random.default_rng(0), 4, 0.35), [0.35] * 4)
    with pytest.raises(ValueError, match="low <= high"):
        models.troposphere(np.random.default_rng(0), 4, [0.4, 0.3])


def test_sector_offset_is_one_constant_bias_per_sector():
    base = _spec()
    off = generate(base, seed=1)
    spec = copy.deepcopy(base)
    spec["tower_clocks"]["sector"] = {"offset_m": 50.0}
    on = generate(spec, seed=1)
    for emitter, clock in on.tower_clocks.items():
        d = clock - off.tower_clocks[emitter]
        assert np.ptp(d) < 1e-9 and abs(d[0]) <= 50.0, emitter
    assert (
        len({round(float(c[0] - off.tower_clocks[e][0]), 6) for e, c in on.tower_clocks.items()})
        > 1
    )


def test_steering_drift_jumps_about_once_a_minute_within_its_bound():
    t = np.arange(0.0, 3600.0, 0.5)
    drift_mps = 1e-9 * models.C_MPS  # 1 ppb
    x = models.steering(np.random.default_rng(7), t, 1.0 / 60.0, drift_mps)
    assert x[0] == 0.0
    rate = np.diff(x) / np.diff(t)
    assert np.abs(rate).max() <= drift_mps + 1e-9
    # a jump inside a sample interval blends that interval's rate: two changes per jump
    changes = int(np.sum(np.abs(np.diff(rate)) > 1e-9))
    assert 35 <= changes / 2 <= 90  # 60 jumps expected in an hour; Poisson
    assert np.abs(x).max() < 200.0  # steered back: a free 1 ppb drift would reach 1,079 m
    assert not models.steering(np.random.default_rng(7), t, 0.0, drift_mps).any()


def test_steering_adds_to_each_site_clock_and_leaves_other_draws():
    base = _spec()
    off = generate(base, seed=2)
    spec = copy.deepcopy(base)
    spec["tower_clocks"]["steering"] = {"jump_rate_hz": 1.0 / 60.0, "drift_ppb": 1.0}
    on = generate(spec, seed=2)
    _others_identical(on, off, "lte")
    for emitter, clock in on.tower_clocks.items():
        d = clock - off.tower_clocks[emitter]
        assert d[0] == 0.0 and np.abs(d).max() > 0.0, emitter
    with pytest.raises(ValueError, match="jump_rate_hz and drift_ppb"):
        spec["tower_clocks"]["steering"] = {"drift_ppb": 1.0}
        generate(spec, seed=2)


def test_board_temperature_starts_at_zero_and_approaches_its_change():
    t = np.array([0.0, 300.0, 3000.0])
    dT = models.board_temperature(t, change_k=-8.0, tau_s=300.0)
    assert dT[0] == 0.0 and dT[1] == pytest.approx(-8.0 * (1 - np.exp(-1)))
    assert dT[2] == pytest.approx(-8.0, abs=1e-3)


def test_baro_tracks_board_temperature_when_on():
    base = _spec(board_temperature={"change_k": -7.7, "tau_s": 300.0})
    off = generate(base, seed=4)
    spec = copy.deepcopy(base)
    spec["sources"]["baro"]["temp_m_per_k"] = -10.5
    on = generate(spec, seed=4)
    _others_identical(on, off, "baro")
    a, b = _by_key(on, "baro"), _by_key(off, "baro")
    t = np.array([(k[0] - T0_NS) / 1e9 for k in a])
    d = np.array([a[k].value[0] - b[k].value[0] for k in a])
    expect = -10.5 * models.board_temperature(t, -7.7, 300.0)
    assert np.allclose(d, expect, atol=1e-9)
    spec.pop("board_temperature")
    with pytest.raises(ValueError, match="board_temperature"):
        generate(spec, seed=4)


def test_gyro_bias_follows_board_temperature_and_accel_is_untouched():
    t = np.arange(0.0, 60.0, 0.01)
    f = np.tile([0.0, 0.0, 9.8], (len(t), 1))
    w = np.zeros((len(t), 3))
    dT = models.board_temperature(t, -7.7, 300.0)
    params = sensors.MPU6050.__class__(
        **{**sensors.MPU6050.__dict__, "gyro_temp_dps_per_k": 0.015, "gyro_lsb_dps": 1e-9}
    )
    flat = sensors.MPU6050.__class__(**{**sensors.MPU6050.__dict__, "gyro_lsb_dps": 1e-9})
    a_on, g_on = sensors.imu(
        t, f, w, np.random.default_rng(5), params, dT, np.random.default_rng(9)
    )
    a_off, g_off = sensors.imu(t, f, w, np.random.default_rng(5), flat)
    assert np.array_equal(a_on, a_off)
    coeff = np.random.default_rng(9).normal(0.0, 0.015 * sensors.DEG, 3)
    assert np.allclose(g_on - g_off, dT[:, None] * coeff, atol=1e-8)
    with pytest.raises(ValueError, match="temperature_k"):
        sensors.imu(t, f, w, np.random.default_rng(5), params)


def test_gyro_temperature_in_a_scenario_needs_board_temperature():
    spec = _spec(duration_s=5.0, imu=True)
    spec["sources"]["imu"]["gyro_temp_dps_per_k"] = 0.015
    with pytest.raises(ValueError, match="board_temperature"):
        generate(spec, seed=0)
    spec["board_temperature"] = {"change_k": -7.7, "tau_s": 300.0}
    off_spec = _spec(duration_s=5.0, imu=True, board_temperature=spec["board_temperature"])
    on, off = generate(spec, seed=0), generate(off_spec, seed=0)
    _others_identical(on, off, "imu")
    assert _by_key(on, "imu").keys() == _by_key(off, "imu").keys()


def _hold(**kw) -> dict:
    return {"type": "tower_holdover", "source": "lte", "start_s": 10.0, **kw}


def _holdover_errors(fault: dict, seed: int = 0, builders: bool = False) -> dict:
    """{emitter: the holdover's added error per record (m)}."""
    base = _spec()
    if builders:
        base["tower_clocks"]["builder"] = {"drift_mps": 0.0354}
    off = generate(base, seed=seed)
    spec = copy.deepcopy(base)
    spec["faults"] = [fault]
    on = generate(spec, seed=seed)
    a, b = _by_key(on, "lte"), _by_key(off, "lte")
    out: dict[str, list[float]] = {}
    for k in a:
        out.setdefault(k[3], []).append(a[k].value[0] - b[k].value[0])
    return {e: np.array(v) for e, v in out.items()}


def test_holdover_mixture_network_sites_share_one_clock_per_builder():
    err = _holdover_errors(_hold(grade="mixture", network_share=1.0), builders=True)
    from pnt.sim.scenario import tower_groups

    sites, builders = tower_groups(_spec(), 0)
    for b in set(builders.values()):
        mine = [e for e in err if builders[sites[e]] == b]
        # every network-held site of one builder moves alike (records where all are heard)
        n = min(len(err[e]) for e in mine)
        for e in mine[1:]:
            assert np.allclose(err[e][-n:], err[mine[0]][-n:], atol=1e-6) or len(mine) == 1


def test_holdover_mixture_local_sites_drift_alone_and_faster():
    local = _holdover_errors(_hold(grade="mixture", network_share=0.0), seed=4)
    net = _holdover_errors(_hold(grade="mixture", network_share=1.0), seed=4)
    assert len({round(float(v[-1]), 6) for v in local.values()}) == len(local)
    assert np.mean([abs(v[-1]) for v in local.values()]) > np.mean(
        [abs(v[-1]) for v in net.values()]
    )


def test_holdover_that_does_not_reach_the_towers_changes_nothing():
    err = _holdover_errors(_hold(reach_probability=0.0))
    assert all(not v.any() for v in err.values())
    with pytest.raises(ValueError, match="network_share"):
        _holdover_errors(_hold(network_share=0.5))


def test_arcs_restart_with_their_own_offsets_when_on():
    off = generate(_front_end(), seed=0)
    on = generate(_front_end(arcs={"rate_hz": 0.05}), seed=0)
    _others_identical(on, off, "lte")
    assert all(m.meta["arc"] == 0 for m in off.measurements if m.source == "lte")
    a, b = _by_key(on, "lte"), _by_key(off, "lte")
    assert a.keys() == b.keys()
    per_arc: dict[tuple, list[float]] = {}
    for k, m in a.items():
        d = (m.value[0] - b[k].value[0] + AMBIGUITY_M / 2) % AMBIGUITY_M - AMBIGUITY_M / 2
        per_arc.setdefault((k[3], m.meta["arc"]), []).append(d)
    assert max(arc for _, arc in per_arc) >= 2
    assert all(np.ptp(v) < 1e-6 for v in per_arc.values())  # one offset per arc
    with pytest.raises(ValueError, match="arcs has no"):
        generate(_front_end(arcs={"size_m": 1.0}), seed=0)


def test_arc_defaults_come_from_the_measured_restarts():
    arcs = lte_front_end.Arcs()
    assert 1.0 / arcs.rate_hz == pytest.approx(43.1, abs=0.1)  # 250 arcs in 10,780 s
    assert arcs.far_share == pytest.approx(0.094, abs=0.001)
    assert arcs.near_sigma_m == pytest.approx(8.0, abs=0.1)


def test_front_end_troposphere_is_per_enb():
    off = generate(_front_end(duration_s=30.0), seed=0)
    on = generate(_front_end(duration_s=30.0, troposphere={"m_per_km": 0.35}), seed=0)
    _others_identical(on, off, "lte")
    a, b = _by_key(on, "lte"), _by_key(off, "lte")
    d = [(a[k].value[0] - b[k].value[0]) % AMBIGUITY_M for k in a]
    assert 0.0 < min(d) and max(d) < 0.35 * 10.0  # 0.35 m/km within the 3 km heard, plus height
