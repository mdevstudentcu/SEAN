"""Attacks for the challenge set (issue #127): towers drifting in holdover with GNSS, and IMU
degradation. Both are software fault injection only (ADR-0001)."""

import copy

import numpy as np
import pytest

from pnt.sim import attacks
from pnt.sim.scenario import T0_NS, generate, load, tower_groups

# Numeric limits in this file are regression guards, not requirements.
START_S, END_S = 30.0, 60.0


def _spec(name: str = "gps-outage", duration_s: float = 90.0, faults=None) -> dict:
    spec = copy.deepcopy(load(name))
    spec.update(duration_s=duration_s, faults=faults or [])
    return spec


def _grouped(faults=None) -> dict:
    """gps-outage with tower clocks grouped by builder (ADR-0022) instead of per-tower clocks."""
    spec = _spec(faults=faults)
    for key in ("clock_rw_m", "init_bias_m"):
        del spec["sources"]["lte"][key]
    spec["tower_clocks"] = {"site": {"offset_m": 1000.0, "offset_rw_m": 0.2}}
    return spec


def _t(m) -> float:
    return (m.t_ns - T0_NS) / 1e9


def _key(m):
    return (m.t_ns, m.source, m.kind, m.emitter, m.receiver)


def _diff(attacked, clean, kind="pseudorange"):
    """{key: attacked value - clean value} for records of `kind` present in both runs."""
    a = {_key(m): m for m in attacked.measurements if m.kind == kind}
    c = {_key(m): m for m in clean.measurements if m.kind == kind}
    assert a.keys() == c.keys()
    return {k: np.subtract(a[k].value, c[k].value) for k in a}


def _others_identical(attacked, clean, changed):
    """Records outside `changed(m)` are bit-identical, in the same order."""
    a = [m for m in attacked.measurements if not changed(m)]
    c = [m for m in clean.measurements if not changed(m)]
    assert a == c


def _close(a, b) -> bool:
    """Equal but for the rounding of (range + error) - range, ranges being km."""
    return bool(np.allclose(a, b, rtol=0.0, atol=1e-9))


def _holdover(**kw) -> dict:
    return {"type": "tower_holdover", "start_s": START_S, **kw}


def _by_emitter(diff: dict) -> dict[str, np.ndarray]:
    out: dict[str, list] = {}
    for k in sorted(diff):
        out.setdefault(k[3], []).append(diff[k][0])
    return {e: np.array(v) for e, v in out.items()}


def test_new_attacks_are_registered_and_kept_off_the_shared_menu():
    assert {"tower_holdover", "imu_degradation"} <= set(attacks._ATTACKS)
    menu = load("realistic-outage")  # composing any set scenario reads the shared menu
    assert all(f["type"] not in {"tower_holdover", "imu_degradation"} for f in menu["faults"])
    from pnt.sim.scenario import ATTACK_MENU

    assert "tower_holdover" not in ATTACK_MENU.read_text()
    assert "imu_degradation" not in ATTACK_MENU.read_text()


def test_holdover_is_continuous_at_onset_grows_after_and_touches_nothing_else():
    clean = generate(_spec(), seed=1)
    attacked = generate(_spec(faults=[_holdover()]), seed=1)
    diff = _diff(attacked, clean)
    for k, d in diff.items():
        t = (k[0] - T0_NS) / 1e9
        if t <= START_S:  # before onset untouched; at onset (1 Hz on whole seconds) no step
            assert d[0] == 0.0
    err = _by_emitter(diff)
    assert len(err) == 6
    for e in err.values():
        after = e[e != 0.0]
        assert np.abs(after[-10:]).mean() > np.abs(after[:10]).mean()  # grows
        assert np.abs(after[0]) < 1.0  # one second in: no step (regression guard)
    _others_identical(attacked, clean, lambda m: m.kind == "pseudorange" and _t(m) > START_S)
    assert attacked.events == [(T0_NS + int(START_S * 1e9), "6 lte towers drift in ocxo holdover")]


def test_holdover_holds_its_error_after_end():
    clean = generate(_spec(), seed=2)
    attacked = generate(_spec(faults=[_holdover(end_s=END_S)]), seed=2)
    diff = _diff(attacked, clean)
    late = [k for k in diff if (k[0] - T0_NS) / 1e9 >= END_S]
    assert late
    for k in late:
        at_end = diff.get((T0_NS + int(END_S * 1e9), *k[1:]))
        if at_end is not None:  # the tower may be in a dropout at end_s
            assert diff[k][0] == at_end[0] != 0.0


def test_towers_left_out_by_emitters_or_fraction_are_bit_identical():
    clean = generate(_spec(), seed=3)
    picked = generate(_spec(faults=[_holdover(emitters=["lte:sim0", "lte:sim2"])]), seed=3)
    moved = {e for e, d in _by_emitter(_diff(picked, clean)).items() if np.any(d)}
    assert moved == {"lte:sim0", "lte:sim2"}
    _others_identical(picked, clean, lambda m: m.emitter in moved)

    half = generate(_spec(faults=[_holdover(fraction=0.5)]), seed=3)
    moved = {e for e, d in _by_emitter(_diff(half, clean)).items() if np.any(d)}
    assert len(moved) == 3
    _others_identical(half, clean, lambda m: m.emitter in moved)

    with pytest.raises(ValueError, match="no lte emitters"):
        generate(_spec(faults=[_holdover(emitters=["lte:sim99"])]), seed=3)


def test_towers_of_one_builder_share_the_builder_term_when_the_scenario_groups_them():
    seed = 4
    clean = generate(_grouped(), seed=seed)
    sites, builders = tower_groups(clean.spec, seed)
    builder = {e: builders[s] for e, s in sites.items()}
    assert len(set(builder.values())) > 1  # the draw gives more than one builder

    shared = _by_emitter(_diff(generate(_grouped([_holdover(builder_share=1.0)]), seed), clean))
    split = _by_emitter(_diff(generate(_grouped([_holdover()]), seed), clean))
    alone = _by_emitter(_diff(generate(_spec(faults=[_holdover(builder_share=1.0)]), seed), clean))
    for a in shared:
        for b in shared:
            if a == b:
                continue
            same = builder[a] == builder[b]
            assert _close(shared[a], shared[b]) == same  # builder term only
            assert not _close(split[a], split[b])  # each site adds its own
            assert not _close(alone[a], alone[b])  # ungrouped: builder_share unused


def test_both_receivers_see_the_same_holdover_error():
    spec = _spec("uc01-drone-circuit-with-base", duration_s=60.0)
    clean = generate(spec, seed=5)
    attacked = generate({**spec, "faults": [_holdover()]}, seed=5)
    diff = _diff(attacked, clean)
    pairs = [(k, (*k[:4], "reference")) for k in diff if k[4] == "payload"]
    both = [(diff[p][0], diff[r][0]) for p, r in pairs if r in diff and diff[p][0] != 0.0]
    assert both and _close(*np.array(both).T)


def test_holdover_same_seed_same_result_other_seed_differs():
    fault = [_holdover(fraction=0.5, grade="rubidium")]
    six = generate(_spec(faults=fault), seed=6)
    assert six.measurements == generate(_spec(faults=fault), seed=6).measurements
    d6 = _by_emitter(_diff(six, generate(_spec(), seed=6)))
    d7 = _by_emitter(_diff(generate(_spec(faults=fault), seed=7), generate(_spec(), seed=7)))
    assert any(not np.array_equal(d6[e], d7[e]) for e in d6)  # a different holdover drawn


def test_holdover_rejects_an_unknown_grade():
    with pytest.raises(ValueError, match="grade"):
        generate(_spec(faults=[_holdover(grade="sundial")]), seed=0)


def _imu(**kw) -> dict:
    return {"type": "imu_degradation", "start_s": START_S, "end_s": END_S, **kw}


def _in_window(m) -> bool:
    return m.kind == "accel_gyro" and START_S <= _t(m) < END_S


def _imu_runs(seed=8, **kw):
    clean = generate(_spec(duration_s=75.0), seed=seed)
    return generate(_spec(duration_s=75.0, faults=[_imu(**kw)]), seed=seed), clean


def _imu_pairs(attacked, clean):
    a = [m for m in attacked.measurements if _in_window(m)]
    c = [m for m in clean.measurements if _in_window(m)]
    assert [(m.t_ns, m.sigma, m.meta, m.receiver) for m in a] == [
        (m.t_ns, m.sigma, m.meta, m.receiver) for m in c
    ]  # same count, timestamps, sigma and meta: nothing tells the estimator
    assert all(len(m.value) == 6 for m in a)
    return np.array([m.value for m in a]), np.array([m.value for m in c])


@pytest.mark.parametrize(
    "mode",
    [
        {"mode": "bias", "sensor": "gyro", "axes": [2], "gyro_step_dps": 2.0},
        {"mode": "bias", "sensor": "accel", "accel_step_mg": 0.0, "accel_rate_mg_per_s": 1.0},
        {"mode": "noise", "sensor": "accel", "noise_scale": 3.0},
        {"mode": "stuck"},
        {"mode": "dropout"},
    ],
)
def test_imu_mode_changes_only_imu_records_inside_the_window(mode):
    attacked, clean = _imu_runs(**mode)
    _others_identical(attacked, clean, _in_window)
    if mode["mode"] == "dropout":
        assert not any(_in_window(m) for m in attacked.measurements)
        assert any(_in_window(m) for m in clean.measurements)
        return
    a, c = _imu_pairs(attacked, clean)
    assert not np.array_equal(a, c)


def test_imu_bias_step_moves_only_the_chosen_axis_by_the_step():
    a, c = _imu_pairs(*_imu_runs(mode="bias", sensor="gyro", axes=[2], gyro_step_dps=2.0))
    d = a - c
    assert np.allclose(d[:, 5], np.radians(2.0), rtol=0, atol=1e-12)
    assert np.all(d[:, :5] == 0.0)


def test_imu_bias_ramp_grows_with_time_since_start():
    attacked, clean = _imu_runs(
        mode="bias", sensor="accel", accel_step_mg=0.0, accel_rate_mg_per_s=1.0
    )
    a, c = _imu_pairs(attacked, clean)
    t = np.array([_t(m) - START_S for m in attacked.measurements if _in_window(m)])
    expected = 1e-3 * 9.80665 * t
    assert np.allclose(a[:, :3] - c[:, :3], expected[:, None], rtol=0, atol=1e-9)
    assert np.all(a[:, 3:] == c[:, 3:])


def test_imu_noise_scales_the_white_noise_and_keeps_the_reported_sigma():
    attacked, clean = _imu_runs(mode="noise", sensor="accel", noise_scale=3.0)
    a, c = _imu_pairs(attacked, clean)
    sigma = next(m for m in clean.measurements if m.kind == "accel_gyro").sigma[0]
    added = (a - c)[:, :3].std()
    assert added == pytest.approx(np.sqrt(8.0) * sigma, rel=0.05)  # sqrt(3^2 - 1)
    assert np.all(a[:, 3:] == c[:, 3:])


def test_imu_stuck_repeats_the_last_reading_before_the_window():
    attacked, clean = _imu_runs(mode="stuck")
    a, _ = _imu_pairs(attacked, clean)
    last = [m for m in clean.measurements if m.kind == "accel_gyro" and _t(m) < START_S][-1]
    assert np.all(a == np.array(last.value))


def test_imu_degradation_same_seed_same_result():
    one, _ = _imu_runs(mode="noise")
    two, _ = _imu_runs(mode="noise")
    assert one.measurements == two.measurements


def test_imu_degradation_rejects_an_unknown_mode():
    with pytest.raises(ValueError, match="mode"):
        _imu_runs(mode="melted")
