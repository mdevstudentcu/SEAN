"""Shared tower clocks in the sim (ADR-0022, Proposed; issue #77): builder + site + sector
clocks, how towers are grouped, and that scenarios without `tower_clocks:` are unchanged."""

import copy

import numpy as np
import pytest

from pnt.sim import models
from pnt.sim.scenario import BUILDERS, builder_of, generate, load, scenario_names, tower_groups

# Numeric limits in this file are regression guards, not requirements.
RUNS = 300


def _spec(tower_clocks: dict, duration_s: float = 60.0, **lte) -> dict:
    """gps-outage, shortened, with the per-tower clock replaced by `tower_clocks`."""
    spec = copy.deepcopy(load("gps-outage"))
    spec.update(duration_s=duration_s, faults=[], tower_clocks=tower_clocks)
    for key in ("clock_rw_m", "init_bias_m"):
        del spec["sources"]["lte"][key]
    spec["sources"]["lte"].update(lte)
    return spec


def _clocks_only(spec: dict) -> dict:
    """`spec` with only its LTE source, at a low rate: the tower clocks come from their own
    random stream on the truth timeline, so they are identical, about 35x faster."""
    spec = copy.deepcopy(spec)
    spec["sources"] = {"lte": {**spec["sources"]["lte"], "rate_hz": 0.1}}
    return spec


def _drift(clock: np.ndarray, duration_s: float = 60.0) -> float:
    return float(clock[-1] - clock[0]) / duration_s


def test_default_is_unchanged():
    """No `tower_clocks:` keeps the per-tower clock: these are main's values (3949f4c)."""
    base = [n for n in scenario_names() if not n.startswith(("realistic-", "worst-"))]
    assert not any(load(n).get("tower_clocks") for n in base)
    run = generate(load("gps-outage"), seed=0)
    pr = [m for m in run.measurements if m.kind == "pseudorange"]
    assert len(pr) == 2160
    assert pr[0].value[0] == pytest.approx(1068.8489306340234, abs=1e-9)
    assert pr[1].value[0] == pytest.approx(3421.055453474436, abs=1e-9)
    assert sum(m.value[0] for m in pr) == pytest.approx(3713620.926340288, abs=1e-6)
    assert run.tower_clocks == {}
    off = copy.deepcopy(load("gps-outage"))
    off["tower_clocks"] = None
    assert generate(off, seed=0).measurements == run.measurements


def test_same_builder_shares_its_clock_and_different_builders_do_not():
    """Builder clock only: towers of one builder read the same clock, others differ."""
    for seed in range(5):
        run = generate(_spec({"builder": {"offset_m": 500.0, "drift_mps": 0.5}}), seed=seed)
        sites, builders = tower_groups(run.spec, seed)
        for a in run.tower_clocks:
            for b in run.tower_clocks:
                same = builders[sites[a]] == builders[sites[b]]
                assert np.array_equal(run.tower_clocks[a], run.tower_clocks[b]) == same


def test_drift_is_correlated_within_a_builder_and_independent_across():
    """Builder and site drift of equal size: correlation 0.5 within a builder, 0 across."""
    level = {"drift_mps": 0.5}
    within, across = [], []
    for seed in range(RUNS):
        run = generate(_clocks_only(_spec({"builder": level, "site": level})), seed=seed)
        sites, builders = tower_groups(run.spec, seed)
        em = sorted(run.tower_clocks)
        for i, a in enumerate(em):
            for b in em[i + 1 :]:
                pair = (_drift(run.tower_clocks[a]), _drift(run.tower_clocks[b]))
                same = builders[sites[a]] == builders[sites[b]]
                (within if same else across).append(pair)
    assert np.corrcoef(np.array(within).T)[0, 1] == pytest.approx(0.5, abs=0.1)
    assert np.corrcoef(np.array(across).T)[0, 1] == pytest.approx(0.0, abs=0.1)


def test_deterministic_for_a_seed():
    spec = _spec({"builder": {"drift_mps": 0.1}, "site": {"offset_m": 1000.0}})
    a, b = generate(spec, seed=7), generate(spec, seed=7)
    assert a.measurements == b.measurements
    assert tower_groups(spec, 7) == tower_groups(spec, 7)
    assert all(np.array_equal(a.tower_clocks[e], b.tower_clocks[e]) for e in a.tower_clocks)
    # synthetic towers draw their builders from the seed
    assert len({tuple(tower_groups(spec, s)[1].values()) for s in range(10)}) > 1


def test_pseudorange_carries_the_tower_clock():
    spec = _spec({"builder": {"drift_mps": 0.5}, "site": {"offset_m": 1000.0}}, sigma_m=0.0)
    run = generate(spec, seed=1)
    pos = {t.t_ns: np.array(t.pos_enu) for t in run.truth}
    t0 = run.truth[0].t_ns
    for m in run.measurements:
        if m.kind == "pseudorange":
            k = round((m.t_ns - t0) / 1e8)  # truth every 0.1 s
            rng = np.linalg.norm(pos[m.t_ns] - np.array(run.emitters[m.emitter]))
            assert m.value[0] - rng == pytest.approx(run.tower_clocks[m.emitter][k], abs=1e-6)


def test_real_towers_take_their_builder_from_the_carrier():
    sites, builders = tower_groups(load("realistic-nominal"))
    assert set(builders.values()) == {"telus-built"}
    assert sites == {e: e for e in sites}  # registry sites, one emitter each
    for carrier, builder in [
        ("TELUS Communications Inc.", "telus-built"),
        ("Bell Mobility Inc.", "telus-built"),
        ("Rogers Communications Canada Inc.", "rogers"),
        ("Vidéotron ltée", "videotron"),
        ("Freedom Mobile Inc.", "videotron"),
    ]:
        assert builder_of(carrier) == builder
    assert set(BUILDERS) == {"telus-built", "rogers", "videotron"}


def test_co_located_towers_of_one_builder_are_one_site():
    spec = load("realistic-nominal")
    spec["sources"]["lte2"] = copy.deepcopy(spec["sources"]["lte"])
    sites, builders = tower_groups(spec)
    assert all(sites[f"lte2:sim{i}"] == f"lte:sim{i}" for i in range(4))
    assert len(builders) == 4


def test_tower_clocks_replace_the_per_tower_clock():
    spec = _spec({"site": {"offset_m": 1000.0}}, clock_rw_m=0.2)
    with pytest.raises(ValueError, match="replaces"):
        generate(spec, seed=0)


def test_oscillator_spread_grows_as_the_two_state_model_says():
    """Offset variance at T from white (S1) and random-walk (S2) frequency noise:
    S1 T + S2 T^3 / 3."""
    t = np.arange(0.0, 100.0, 0.5)
    rng = np.random.default_rng(0)
    end = np.array(
        [models.oscillator(rng, t, offset_rw_m=0.2, drift_rw_mps=0.01)[-1] for _ in range(4000)]
    )
    T = t[-1]
    assert np.var(end) == pytest.approx(0.2**2 * T + 0.01**2 * T**3 / 3, rel=0.1)
    assert np.array_equal(models.oscillator(rng, t), np.zeros(len(t)))
