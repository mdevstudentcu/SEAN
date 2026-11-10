"""One dongle hopping LTE carriers in the sim (#173): which carrier is heard when, the dead time
after a retune, one dongle clock and one site clock per eNB across carriers, and the lookup on
every carrier. Sim evidence only; nothing here is a requirement threshold."""

import copy
from collections import Counter

import numpy as np
import pytest

from pnt.nav import cells
from pnt.nav.cells import MATCHED
from pnt.sim import lte_front_end, scenario
from pnt.sim.lte_front_end import AMBIGUITY_M
from pnt.sim.scenario import T0_NS, generate, load

# Rogers 2460 and 5035 share most eNBs; TELUS 2560 has no site within 3 km of Carleton
HOP = [2460, 5035, 2560]
TOWER_CLOCKS = {
    "builder": {"drift_mps": 0.0354, "drift_rw_mps": 2.7e-4},
    "site": {"offset_m": AMBIGUITY_M / 2, "drift_mps": 0.0354, "offset_rw_m": 0.2},
}


def spec(duration_s=30.0, earfcn=None, hop=None, hearing=None, **lte) -> dict:
    """The UC-01 circuit cut short, without the IMU and faults, hopping HOP by default. No error
    terms but white noise unless a test adds them."""
    s = copy.deepcopy(load("uc01-drone-circuit"))
    s.update(duration_s=duration_s, faults=[], tower_clocks=copy.deepcopy(TOWER_CLOCKS))
    s["clock"] = {"drift_ppb": 20.0, "rw_ns": 2.0}
    s["sources"].pop("imu")
    earfcn = HOP if earfcn is None else earfcn
    s["sources"]["lte"] = {
        "model": "pseudorange",
        "record_shape": "front_end",
        "rate_hz": 1,
        "cells_from": {"file": "lte-cells-ottawa.csv", "earfcn": earfcn},
        "hearing": hearing or {"model": "range", "hearing_km": 6.0},
        "sigma_m": 20.0,
        **lte,
    }
    if hop is not False:
        s["sources"]["lte"]["hop"] = hop or {"dwell_s": 1.0, "reacquire_s": 0.15}
    return s


def lte_of(run) -> list:
    return [m for m in run.measurements if m.source == "lte"]


def seconds(m) -> float:
    return (m.t_ns - T0_NS) / 1e9


def sectors(earfcns=HOP):
    return lte_front_end.sectors_of(scenario.REFERENCE_DIR / "lte-cells-ottawa.csv", earfcns)


def test_only_the_dwelled_carrier_is_heard_at_any_epoch():
    run = generate(spec(30.0), seed=0)
    lte = lte_of(run)
    dwelled = {m.t_ns: HOP[int(seconds(m) // 1.0) % len(HOP)] for m in lte}
    assert all(m.meta["earfcn"] == dwelled[m.t_ns] for m in lte)
    assert {m.meta["earfcn"] for m in lte} == set(HOP)
    for m in lte:
        assert m.emitter == f"lte:{m.meta['earfcn']}:{m.meta['pci']}"
        fc = {s.earfcn: s.fc_hz for s in sectors()}[m.meta["earfcn"]]
        assert m.meta["fc_hz"] == fc


def test_the_near_far_floor_applies_within_the_dwelled_carrier():
    """Link budget, no dead time and no draws that move hearing: at each epoch the hopping
    dongle hears what a dongle parked on that carrier hears at that epoch, no more, no less."""
    quiet = {"hearing": {"model": "link_budget"}, "told_position_sigma_m": 0.0}
    hopped = generate(spec(30.0, hop={"dwell_s": 1.0, "reacquire_s": 0.0}, **quiet), seed=0)
    heard = Counter((m.t_ns, m.emitter) for m in lte_of(hopped))
    for i, earfcn in enumerate(HOP):
        alone = generate(spec(30.0, earfcn=earfcn, hop=False, **quiet), seed=0)
        mine = {(m.t_ns, m.emitter) for m in lte_of(alone) if round(seconds(m)) % len(HOP) == i}
        theirs = {k for k in heard if k[1].startswith(f"lte:{earfcn}:")}
        assert mine == theirs and mine


def test_no_record_in_the_dead_time_after_a_retune():
    run = generate(spec(30.0, hop={"dwell_s": 2.0, "reacquire_s": 0.4}), seed=0)
    into_dwell = np.array([seconds(m) % 2.0 for m in lte_of(run)])
    assert len(into_dwell) and into_dwell.min() == pytest.approx(0.4)
    # 1 Hz within each dwell: at 0.4 s and 1.4 s into it
    assert set(np.round(into_dwell, 6)) == {0.4, 1.4}
    assert {m.meta["n_epochs"] for m in lte_of(run)} == {200}  # 1 s of 5 ms epochs per record
    short = generate(spec(10.0, hop={"dwell_s": 0.5, "reacquire_s": 0.15}), seed=0)
    assert {m.meta["n_epochs"] for m in lte_of(short)} == {70}  # what is left of the dwell


def test_one_dongle_clock_across_carriers_and_one_site_clock_per_enb():
    """With almost no noise, every record of every carrier is true range + its eNB's clock +
    the one dongle clock, and the lookup aligns each eNB's values across carriers and dwells."""
    run = generate(spec(60.0, sigma_m=1e-3), seed=2)
    lte = lte_of(run)
    assert {m.meta["rx_clock"] for m in lte} == {"rtl0"} and set(run.rx_clocks) == {"rtl0"}
    t_truth = np.array([(x.t_ns - T0_NS) / 1e9 for x in run.truth])
    traj = {**run.spec["trajectory"], "_origin_llh": run.spec["origin_llh"]}
    secs = {s.emitter: s for s in sectors() if not s.collides}

    def clean(m) -> float:
        pos = scenario.trajectory.make(traj, np.array([seconds(m)]))[0][0]
        rng = np.linalg.norm(pos - np.array(run.emitters[m.emitter]))
        site = np.interp(seconds(m), t_truth, run.tower_clocks[secs[m.emitter].key])
        return float(rng + site + np.interp(seconds(m), t_truth, run.rx_clocks["rtl0"]))

    placed = [m for m in cells.attach(lte, run.spec["origin_llh"]) if m.emitter in secs]
    frames = {}
    for m in placed:
        k = (m.value[0] - clean(m)) / AMBIGUITY_M
        assert abs(k - round(k)) * AMBIGUITY_M < 0.05
        frames.setdefault(m.meta["site"], set()).add(round(k))
    assert all(len(f) == 1 for f in frames.values())  # aligned across carriers and dwells
    carriers_of_site = Counter(
        site for site, _ in {(m.meta["site"], m.meta["earfcn"]) for m in placed}
    )
    assert max(carriers_of_site.values()) >= 2  # an eNB heard on two carriers: the case tested

    sites, builders = scenario.tower_groups(run.spec, 2)
    for a in sectors():
        for b in sectors():
            if a.enb_id == b.enb_id:
                assert sites[a.key] == sites[b.key] == a.site
                assert np.array_equal(run.tower_clocks[a.key], run.tower_clocks[b.key])
    assert set(builders.values()) == {"rogers", "telus-built"}


def test_same_seed_same_records():
    s = spec(30.0, multipath={"sigma_m": 50.0, "tau_s": 30.0})
    a, b = generate(s, seed=4), generate(s, seed=4)
    assert a.measurements == b.measurements
    assert lte_of(generate(s, seed=5)) != lte_of(a)


def test_a_single_carrier_scenario_is_unchanged():
    """One carrier means no retune: the list form and a hop block change nothing."""
    s = spec(40.0, earfcn=2460, hop=False, hearing={"model": "link_budget"})
    s["sources"]["lte"].update(
        multipath={"sigma_m": 50.0, "tau_s": 30.0}, dropout={"availability": 0.75, "block_s": 30.0}
    )
    base = generate(s, seed=1)
    for earfcn, hop in (([2460], None), (2460, {"dwell_s": 0.5, "reacquire_s": 0.2})):
        other = copy.deepcopy(s)
        other["sources"]["lte"]["cells_from"]["earfcn"] = earfcn
        if hop:
            other["sources"]["lte"]["hop"] = hop
        assert generate(other, seed=1).measurements == base.measurements
        assert scenario.tower_groups(other, 1) == scenario.tower_groups(s, 1)


def test_the_lookup_matches_cells_of_every_hopped_carrier():
    spec_ = copy.deepcopy(load("challenge-drone-hop-nominal"))
    spec_["duration_s"] = 60.0
    spec_["sources"].pop("imu")
    run = generate(spec_, seed=0)
    hop = spec_["sources"]["lte"]["cells_from"]["earfcn"]
    lte = lte_of(run)
    counts = Counter()
    placed = list(cells.attach(lte, spec_["origin_llh"], counts=counts))
    assert counts[MATCHED] == len(placed) > 0
    assert {m.meta["earfcn"] for m in placed} == set(hop)
    # every heard emitter that one eNB alone uses can be found by an attack and has a site clock
    secs = sectors(tuple(hop))
    sites, _ = scenario.tower_groups(spec_, 0)
    assert set(run.emitters) == {s.emitter for s in secs if not s.collides}
    assert set(sites) == {s.key for s in secs}
    assert {m.emitter for m in placed} <= set(run.emitters)


def test_hop_options_are_checked():
    with pytest.raises(ValueError, match="hop: block"):
        generate(spec(5.0, hop=False), 0)
    with pytest.raises(ValueError, match="reacquire_s < dwell_s"):
        generate(spec(5.0, hop={"dwell_s": 1.0, "reacquire_s": 1.0}), 0)
    with pytest.raises(ValueError, match="dwell_s and reacquire_s"):
        generate(spec(5.0, hop={"dwell_s": 1.0}), 0)
    with pytest.raises(ValueError, match="distinct carriers"):
        generate(spec(5.0, earfcn=[2460, 2460]), 0)
