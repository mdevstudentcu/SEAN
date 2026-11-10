"""The challenge benchmark set (#136, ADR-0030 Proposed): three legs, their own attack menus, the
records each leg makes, and run lengths that give the T1 and T3 outage slices a value. Sim only.
Nothing here is a requirement threshold."""

import copy
import math
import re
from collections import Counter

import numpy as np
import pytest

from pnt.core.measurement import Estimate
from pnt.metrics import gps_loss, score
from pnt.nav import cells
from pnt.nav.cells import COLLISION, MATCHED
from pnt.sim import scenario
from pnt.sim.lte_front_end import AMBIGUITY_M
from pnt.sim.scenario import T0_NS, attack_names, expand, generate, load, set_names

LEGS = ("challenge-drone", "challenge-timing", "challenge-approach")
FRONT_END_LEGS = ("challenge-drone", "challenge-timing")
SLICES = (
    "outage_h_p95_60s_m",
    "outage_h_p95_120s_m",
    "outage_h_p95_300s_m",
    "outage_hpl_bound_300s",
    "outage_time_err_600s_us",
    "outage_time_sigma_bound_600s",
)
SHORT_S = 240.0  # long enough for every fault to start (the latest starts at 180 s)


def _short(name: str, duration_s: float = SHORT_S) -> dict:
    spec = copy.deepcopy(load(name))
    spec["duration_s"] = duration_s
    return spec


def _seconds(m) -> float:
    return (m.t_ns - T0_NS) / 1e9


def _own(leg: str) -> dict:
    return scenario._own_attacks(leg)


def test_the_three_legs_are_environments():
    assert set(LEGS) <= set(set_names())


@pytest.mark.parametrize("leg", LEGS)
def test_every_attack_of_a_leg_composes_and_takes_effect(leg):
    names = expand(leg)
    assert names == [f"{leg}-{a}" for a in _own(leg)]
    nominal = {}
    for name in names:
        spec = load(name)
        attack = name[len(leg) + 1 :]
        assert spec["name"] == name and spec["faults"] == (_own(leg)[attack] or [])
        assert "attacks" not in spec and "shared_attacks" not in spec
        if attack == "nominal":
            continue
        # A jamming zone acts by place, not time: the approach reaches its zone after 500 s
        length = spec["duration_s"] if attack == "jamming-zone" else SHORT_S
        if length not in nominal:
            nominal[length] = generate(_short(f"{leg}-nominal", length), seed=0).measurements
        run = generate(_short(name, length), seed=0)
        assert len(run.events) >= len(spec["faults"]), name  # each fault reports its start
        assert run.measurements != nominal[length], name  # and each changes the records


@pytest.mark.parametrize("leg", LEGS)
def test_the_shared_menu_is_not_applied_to_a_challenge_leg(leg):
    assert load(f"{leg}-nominal")["description"]  # loads through the set machinery
    for shared_only in set(attack_names()) - set(_own(leg)):  # e.g. tower-loss, gps-no-fix
        with pytest.raises(FileNotFoundError):
            load(f"{leg}-{shared_only}")


@pytest.mark.parametrize("env", ["easy", "realistic", "realistic-with-base", "worst"])
def test_existing_sets_keep_the_shared_menu(env):
    shared = [f"{env}-{a}" for a in attack_names()]
    names = expand(env)
    assert names[: len(shared)] == shared
    assert names[len(shared) :] == [f"{env}-{a}" for a in _own(env)]


def test_shared_attacks_must_be_true_or_false(tmp_path, monkeypatch):
    (tmp_path / "own-only.yaml").write_text(
        "shared_attacks: false\nattacks: {calm: [], lost: [{type: outage, start_s: 1}]}\n"
    )
    (tmp_path / "bad.yaml").write_text("shared_attacks: 'no'\n")
    monkeypatch.setattr(scenario, "SET_DIR", tmp_path)
    assert expand("own-only") == ["own-only-calm", "own-only-lost"]
    with pytest.raises(ValueError, match="shared_attacks"):
        expand("bad")


@pytest.mark.parametrize("leg", FRONT_END_LEGS)
def test_front_end_legs_make_front_end_records_that_go_through_the_lookup(leg):
    run = generate(_short(f"{leg}-nominal"), seed=0)
    lte = [m for m in run.measurements if m.source == "lte"]
    assert lte
    for m in lte:
        assert re.fullmatch(r"lte:2460:\d+", m.emitter)
        assert not {"emitter_llh", "emitter_enu", "site"} & set(m.meta)  # placed by the lookup
        assert m.meta["rx_clock"] == "rtl0" and m.meta["ambiguity_m"] == AMBIGUITY_M
        assert 0.0 <= m.value[0] < AMBIGUITY_M
        assert m.sigma == (2.0,)  # the reported sigma, not the true 50 m
    counts = Counter()
    placed = list(cells.attach(lte, run.spec["origin_llh"], counts=counts))
    assert counts[MATCHED] == len(placed) > 0
    assert counts[MATCHED] + counts[COLLISION] == len(lte)
    assert all(m.meta["site"].startswith("enb:") for m in placed)


def test_the_timing_leg_is_the_drone_legs_radio_environment_standing_still():
    drone, timing = load("challenge-drone-nominal"), load("challenge-timing-nominal")
    for key in ("origin_llh", "duration_s", "dt_s", "clock", "sources", "tower_clocks"):
        assert timing[key] == drone[key], key
    run = generate(_short("challenge-timing-nominal", 20.0), seed=0)
    pos = np.array([t.pos_enu for t in run.truth])
    assert np.ptp(pos, axis=0).max() == 0.0
    assert all(t.vel_enu == (0.0, 0.0, 0.0) for t in run.truth)


def test_the_approach_leg_is_on_synthetic_towers_and_says_so():
    spec = load("challenge-approach-nominal")
    assert "synthetic" in spec["description"].lower()
    assert spec["provenance"]["lte_geometry"] == "TBC"
    run = generate(_short("challenge-approach-nominal", 20.0), seed=0)
    lte = [m for m in run.measurements if m.source == "lte"]
    assert lte and {m.emitter for m in lte} <= {f"lte:sim{i}" for i in range(6)}
    assert all("emitter_llh" in m.meta or "emitter_enu" in m.meta for m in lte)


@pytest.mark.parametrize("leg", LEGS)
def test_run_lengths_give_both_outage_slices_a_value(leg):
    """Every slice is a number, scored on stand-in estimates (truth plus 1 m east)."""
    spec = load(f"{leg}-outage")
    start, end = gps_loss(spec, T0_NS)
    assert (end - start) / 1e9 == 600.0
    run = generate(spec, seed=0)
    est = [
        Estimate(
            t_ns=t.t_ns,
            pos_enu=(t.pos_enu[0] + 1.0, t.pos_enu[1], t.pos_enu[2]),
            vel_enu=t.vel_enu,
            pos_cov=(4.0, 0, 0, 0, 4.0, 0, 0, 0, 4.0),
            clock_bias_s=t.clock_bias_s + 1e-7,
            clock_sigma_s=2e-7,
            hpl_m=10.0,
        )
        for t in run.truth
    ]
    m = score(est, run.truth, spec, T0_NS).as_dict()
    assert all(math.isfinite(m[k]) for k in SLICES), {k: m[k] for k in SLICES}
    assert m["outage_h_p95_300s_m"] == pytest.approx(1.0)
    assert m["outage_time_err_600s_us"] == pytest.approx(0.1)
    assert m["recovery_tested"] == 1.0  # GPS is back for the last 60 s


@pytest.mark.parametrize("leg", FRONT_END_LEGS)
def test_tower_faults_hit_a_real_emitter_of_a_front_end_leg(leg):
    outage = generate(_short(f"{leg}-outage"), seed=0)
    base = {(m.t_ns, m.emitter): m.value[0] for m in outage.measurements if m.source == "lte"}

    step = generate(_short(f"{leg}-outage-tower-clock-step"), seed=0)
    moved = Counter()
    for m in step.measurements:
        if m.source == "lte":
            d = m.value[0] - base[(m.t_ns, m.emitter)]
            hit = m.emitter == "lte:2460:300" and _seconds(m) >= 180.0
            assert d == pytest.approx(300.0 if hit else 0.0, abs=1e-9)
            moved[hit] += 1
    assert moved[True] > 0  # the stepped cell is heard after the step

    hold = generate(_short(f"{leg}-outage-tower-holdover"), seed=0)
    lte = [m for m in hold.measurements if m.source == "lte"]
    diff = [(m, m.value[0] - base[(m.t_ns, m.emitter)]) for m in lte]
    assert all(d == 0.0 for m, d in diff if _seconds(m) <= 180.0)
    assert any(abs(d) > 0.0 for m, d in diff if _seconds(m) > 181.0)
