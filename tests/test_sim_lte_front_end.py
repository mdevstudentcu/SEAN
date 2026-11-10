"""Sim LTE records shaped as the front end writes them (#134): same fields as a capture's, the
same lookup, a dongle clock of their own, and the hearing models. Sim evidence only."""

import copy
import re
from collections import Counter

import numpy as np
import pytest

from pnt.core.frames import llh_to_enu
from pnt.frontends.lte import capture, process_file, synth
from pnt.nav import cells
from pnt.nav.cells import COLLISION, MATCHED, CellTable
from pnt.sim import lte_front_end, scenario
from pnt.sim.lte_front_end import AMBIGUITY_M, LinkBudget
from pnt.sim.scenario import T0_NS, generate, load

EARFCN = 2460
# Site clocks in the realistic set's form, with the frame timing anywhere in the frame (FDD)
TOWER_CLOCKS = {
    "builder": {"drift_mps": 0.0354, "drift_rw_mps": 2.7e-4},
    "site": {"offset_m": AMBIGUITY_M / 2, "drift_mps": 0.0354, "offset_rw_m": 0.2},
}


def spec(duration_s=40.0, hearing=None, **lte) -> dict:
    """The UC-01 circuit cut short, without the IMU (slow) and faults, with front-end LTE records
    (`lte` overrides). No error terms but white noise unless a test adds them."""
    s = copy.deepcopy(load("uc01-drone-circuit"))
    s.update(duration_s=duration_s, faults=[], tower_clocks=copy.deepcopy(TOWER_CLOCKS))
    s["clock"] = {"drift_ppb": 20.0, "rw_ns": 2.0}
    s["sources"].pop("imu")
    s["sources"]["gnss"]["time_sigma_ns"] = 20.0
    s["sources"]["lte"] = {
        "model": "pseudorange",
        "record_shape": "front_end",
        "rate_hz": 1,
        "cells_from": {"file": "lte-cells-ottawa.csv", "earfcn": EARFCN},
        "hearing": hearing or {"model": "range", "hearing_km": 3.0},
        "sigma_m": 20.0,
        **lte,
    }
    return s


def lte_of(run) -> list:
    return [m for m in run.measurements if m.source == "lte"]


def wrapped(x):
    """x moved by whole frames into [-frame/2, frame/2)."""
    return (np.asarray(x) + AMBIGUITY_M / 2) % AMBIGUITY_M - AMBIGUITY_M / 2


def clean_range(run, m) -> float:
    """What a record holds before noise: true range + its site clock + the dongle clock (m)."""
    t = (m.t_ns - T0_NS) / 1e9
    t_truth = np.array([(x.t_ns - T0_NS) / 1e9 for x in run.truth])
    pos = np.array(run.truth[int(round(t / run.spec["dt_s"]))].pos_enu)
    sector = {s.emitter: s for s in _sectors() if not s.collides}[m.emitter]
    rng = np.linalg.norm(pos - np.array(run.emitters[m.emitter]))
    site = np.interp(t, t_truth, run.tower_clocks[sector.key])
    rx = np.interp(t, t_truth, run.rx_clocks[m.meta["rx_clock"]])
    return float(rng + site + rx)


def _sectors():
    return lte_front_end.sectors(scenario.REFERENCE_DIR / "lte-cells-ottawa.csv", EARFCN)


def test_sim_record_carries_the_same_fields_as_a_front_end_record(tmp_path):
    unique = next(s for s in _sectors() if not s.collides)
    x = synth.synthesize([synth.Tower(pci=unique.pci, delay_s=3e-3)], 0.5, clock_ppm=0.4, seed=1)
    sidecar = {"sample_rate_hz": 1.92e6, "center_freq_hz": 875e6, "t_ns": T0_NS}
    path = capture.write_capture(tmp_path / "c.cu8", capture.complex_to_cu8(x), sidecar)
    real = next(
        m for m in process_file(path, earfcn=EARFCN).measurements if m.kind == "pseudorange"
    )
    sim = lte_of(generate(spec(10.0), seed=0))[0]

    assert (sim.source, sim.kind, sim.receiver) == (real.source, real.kind, real.receiver)
    assert re.fullmatch(r"lte:\d+:\d+", sim.emitter) and re.fullmatch(r"lte:\d+:\d+", real.emitter)
    # `sample_index` indexes the capture file; a sim record has no file. Nothing else differs.
    assert set(sim.meta) == set(real.meta) - {"sample_index"}
    assert sim.meta["ambiguity_m"] == real.meta["ambiguity_m"]
    assert {type(sim.meta[k]) for k in ("earfcn", "pci", "arc")} == {int}
    for m in (sim, real):  # no position: the lookup must place both
        assert not {"emitter_llh", "emitter_enu", "site"} & set(m.meta)
    (placed_real,) = cells.attach([real], spec()["origin_llh"])
    assert placed_real.meta["site"] == unique.site


def test_records_go_through_the_lookup_with_collisions_dropped_and_counted():
    run = generate(spec(), seed=0)
    lte = lte_of(run)
    assert all(0.0 <= m.value[0] < AMBIGUITY_M for m in lte)
    colliding = {s.emitter for s in _sectors() if s.collides}
    heard_colliding = sum(m.emitter in colliding for m in lte)
    assert heard_colliding > 0  # the test means something only if a reused PCI is heard

    counts = Counter()
    out = list(cells.attach(lte, run.spec["origin_llh"], counts=counts))
    assert counts == Counter({MATCHED: len(lte) - heard_colliding, COLLISION: heard_colliding})
    by_pci = {s.emitter: s for s in _sectors() if not s.collides}
    for m in out:
        s = by_pci[m.emitter]
        assert m.meta["site"] == s.site and m.meta["emitter_llh"][:2] == [s.lat, s.lon]
    # One record per cell per epoch, as the front end tracks one cell per PCI
    assert len({(m.t_ns, m.emitter) for m in lte}) == len(lte)


def test_values_align_across_the_frame_ambiguity():
    # A dongle drifting this fast moves every range through a whole frame in the run, so every
    # value wraps; the lookup must still align each site's values onto one constant
    s = spec(30.0, dongle={"name": "rtl0", "drift_ppm": 300.0}, sigma_m=0.0)
    run = generate(s, seed=0)
    lte = lte_of(run)
    raw = {}
    for m in lte:
        raw.setdefault(m.emitter, []).append(m.value[0])
    assert any(np.abs(np.diff(v)).max() > AMBIGUITY_M / 2 for v in raw.values())

    out = [m for m in cells.attach(lte, s["origin_llh"])]
    offsets: dict[str, list[float]] = {}
    for m in out:
        offsets.setdefault(m.meta["site"], []).append(m.value[0] - clean_range(run, m))
    for site, off in offsets.items():
        off = np.array(off)
        assert np.ptp(off) < 1e-3, site  # one whole number of frames for the whole site
        assert abs(wrapped(off[0])) < 1e-3


def test_reported_sigma_is_apart_from_the_true_noise():
    run = generate(spec(sigma_m=30.0, told_sigma_m=1.5), seed=0)
    lte = [m for m in lte_of(run) if m.emitter in run.emitters]
    err = wrapped([m.value[0] - clean_range(run, m) for m in lte])
    assert {m.sigma[0] for m in lte} == {1.5} and {m.meta["sigma_crb_m"] for m in lte} == {1.5}
    assert 27.0 < np.std(err) < 33.0  # regression guard on the drawn noise, not a target


def test_multipath_and_dropout_are_shared_by_the_sectors_of_one_enb():
    s = spec(
        200.0,
        sigma_m=0.0,
        multipath={"sigma_m": 50.0, "tau_s": 30.0},
        dropout={"availability": 0.5, "block_s": 20.0},
    )
    run = generate(s, seed=1)
    by = {}
    for m in lte_of(run):
        if m.emitter in run.emitters:
            by.setdefault(m.emitter, {})[m.t_ns] = wrapped(m.value[0] - clean_range(run, m))
    sector_of = {x.emitter: x for x in _sectors() if not x.collides}
    pairs = 0
    for a in by:
        for b in by:
            if a < b and sector_of[a].enb_id == sector_of[b].enb_id:
                assert by[a].keys() == by[b].keys()  # heard and lost together
                assert all(abs(by[a][t] - by[b][t]) < 1e-6 for t in by[a])  # one multipath
                pairs += 1
    assert pairs > 0
    assert np.std([v for e in by.values() for v in e.values()]) > 10.0  # multipath is on


def test_dongle_clock_is_apart_from_the_payload_clock():
    def lte_and_clock(**changes):
        s = spec(20.0)
        s.update(changes)
        run = generate(s, seed=2)
        gnss_time = [m for m in run.measurements if m.kind == "time"]
        return lte_of(run), run.rx_clocks["rtl0"], [t.clock_bias_s for t in run.truth], gnss_time

    base = lte_and_clock()
    other_clock = lte_and_clock(clock={"drift_ppb": 500.0, "rw_ns": 50.0})
    assert other_clock[0] == base[0] and np.array_equal(other_clock[1], base[1])
    assert other_clock[2] != base[2]
    # No payload clock at all draws nothing from the run's stream: the dongle doesn't notice
    no_clock = spec(20.0)
    no_clock.pop("clock")
    no_clock["sources"]["gnss"].pop("time_sigma_ns")
    run = generate(no_clock, seed=2)
    assert lte_of(run) == base[0] and np.array_equal(run.rx_clocks["rtl0"], base[1])

    s = spec(20.0)
    s["sources"]["lte"]["dongle"] = {"name": "rtl0", "drift_ppm": 2.0, "drift_rw_mps": 1.0}
    run = generate(s, seed=2)
    assert [t.clock_bias_s for t in run.truth] == base[2]
    assert [m for m in run.measurements if m.kind == "time"] == base[3]
    assert not np.array_equal(run.rx_clocks["rtl0"], base[1])
    assert {m.meta["rx_clock"] for m in lte_of(run)} == {"rtl0"}


def test_range_hearing_follows_the_truth():
    run = generate(spec(120.0, hearing={"model": "range", "hearing_km": 2.0}), seed=0)
    pos = {t.t_ns: np.array(t.pos_enu) for t in run.truth}
    origin = run.spec["origin_llh"]
    secs = _sectors()
    enu = lte_front_end.table_enu(secs, origin)
    heard_sets = []
    for t_ns in sorted({m.t_ns for m in lte_of(run)}):
        near = np.linalg.norm(enu[:, :2] - pos[t_ns][:2], axis=1) <= 2000.0
        expected = {s.emitter for s, n in zip(secs, near, strict=True) if n}
        heard = {m.emitter for m in lte_of(run) if m.t_ns == t_ns}
        assert heard == expected
        heard_sets.append(frozenset(heard))
    assert len(set(heard_sets)) > 1  # the circuit brings cells in and out of range


def test_link_budget_drops_a_cell_below_the_floor_and_keeps_it_when_the_stronger_is_gone():
    b = LinkBudget()
    noise = b.noise_dbm() + b.min_snr_db
    power = np.array(
        [
            [-50.0, -70.0],  # 20 dB under the strongest: below the -13 dB floor
            [-60.0, -70.0],  # 10 dB under: heard
            [noise - 1.0, -70.0],  # the strong one under the noise floor: no longer the reference
        ]
    )
    heard = lte_front_end.heard_by_link_budget(power, np.ones_like(power, bool), b)
    assert heard.tolist() == [[True, False], [True, True], [False, True]]
    blocked = np.array([[False, True]] * 3)  # a dropped-out eNB sets no floor either
    assert lte_front_end.heard_by_link_budget(power, blocked, b)[:, 1].all()


def test_link_budget_follows_the_sector_pattern():
    b = LinkBudget()
    sector = next(s for s in _sectors() if s.beamwidth_deg)
    at = lte_front_end.table_enu([sector], [sector.lat, sector.lon, 0.0])[0]
    az = np.radians(sector.azimuth_deg)
    ahead = at + 1000.0 * np.array([np.sin(az), np.cos(az), 0.0])
    behind = at - 1000.0 * np.array([np.sin(az), np.cos(az), 0.0])
    p = lte_front_end.rx_power_dbm([sector], at[None, :], np.array([ahead, behind]), b)
    assert p[0, 0] - p[1, 0] == pytest.approx(b.front_to_back_db)


def test_link_budget_scenario_hears_only_cells_near_the_strongest():
    run = generate(spec(60.0, hearing={"model": "link_budget"}), seed=0)
    per_epoch = Counter(m.t_ns for m in lte_of(run))
    n_sectors = len(_sectors())
    assert 0 < max(per_epoch.values()) < n_sectors
    assert all(m.meta["snr_db"] is not None for m in lte_of(run))


def test_same_seed_same_records_and_other_sources_untouched():
    s = spec(30.0, multipath={"sigma_m": 50.0, "tau_s": 30.0})
    a, b = generate(s, seed=4), generate(s, seed=4)
    assert a.measurements == b.measurements
    assert lte_of(generate(s, seed=5)) != lte_of(a)

    without = copy.deepcopy(s)
    without["sources"].pop("lte")
    assert [m for m in a.measurements if m.source != "lte"] == generate(without, 4).measurements


def test_record_shape_sim_is_the_default():
    s = load("realistic-outage")
    explicit = copy.deepcopy(s)
    explicit["sources"]["lte"]["record_shape"] = "sim"
    assert generate(s, 0).measurements == generate(explicit, 0).measurements
    assert scenario.tower_groups(s, 0) == scenario.tower_groups(explicit, 0)


def test_attacks_find_the_front_end_emitters():
    s = spec(30.0)
    run = generate(s, seed=0)
    secs = _sectors()
    assert set(run.emitters) == {x.emitter for x in secs if not x.collides}
    sites, builders = scenario.tower_groups(s, 0)
    assert all(sites[x.key] == x.site for x in secs)
    assert set(builders.values()) == {"rogers"}

    target = Counter(m.emitter for m in lte_of(run) if m.emitter in run.emitters).most_common(1)
    emitter = target[0][0]
    step = {"type": "tower_clock_step", "source": "lte", "emitter": emitter}
    s["faults"] = [{**step, "start_s": 10.0, "offset_m": 300.0}]
    stepped = generate(s, seed=0)
    diff = {
        (m.t_ns, m.emitter): b.value[0] - m.value[0]
        for m, b in zip(lte_of(run), lte_of(stepped), strict=True)
    }
    moved = {k for k, v in diff.items() if v}
    assert moved and all(k[1] == emitter and k[0] >= T0_NS + 10 * 10**9 for k in moved)
    assert all(diff[k] == pytest.approx(300.0) for k in moved)


def test_front_end_options_are_checked():
    with pytest.raises(ValueError, match="cells_from"):
        generate(spec(5.0, cells_from={"file": "lte-cells-ottawa.csv"}), 0)
    with pytest.raises(ValueError, match="no \\['n_emitters'\\]"):
        generate(spec(5.0, n_emitters=4), 0)
    with pytest.raises(ValueError, match="hearing model"):
        generate(spec(5.0, hearing={"model": "magic"}), 0)
    no_clocks = spec(5.0)
    no_clocks.pop("tower_clocks")
    with pytest.raises(ValueError, match="tower_clocks"):
        generate(no_clocks, 0)


def test_sim_and_lookup_agree_on_which_pcis_collide():
    """A capture-free check that the sim's table and the lookup's agree: every non-colliding
    emitter the sim names resolves to the eNB it was generated from."""
    table = CellTable.load()
    origin = spec()["origin_llh"]
    for s in _sectors():
        status, cell = table.associate(s.earfcn, s.pci, origin)
        if s.collides:
            assert status == COLLISION
        else:
            assert status == MATCHED and cell.enb_id == s.enb_id
            got = llh_to_enu([cell.lat, cell.lon, origin[2] + cell.height_agl_m], origin)
            assert np.allclose(got, lte_front_end.table_enu([s], origin)[0])
