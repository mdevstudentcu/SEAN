"""Real tower geometry and wrong cell tables, through the lookup and the filter (#124).

Short runs of `analysis/lte_real_geometry.py`: the UC-01 circuit, simulated GNSS, barometer and
IMU, and LTE records generated from real Rogers eNB positions in the committed table, shaped as
the front end writes them. Sim over real positions, not real signals. Every bound is a
regression guard set from observed runs with margin, not a target. Known limits are asserted as
observed and named as such; they are not passes.
"""

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from pnt import nav
from pnt.core.frames import llh_to_enu
from pnt.nav import cells
from pnt.nav.cells import COLLISION, MATCHED, UNKNOWN, CellTable
from pnt.sim import scenario

_PATH = Path(__file__).parents[1] / "analysis" / "lte_real_geometry.py"
_SPEC = importlib.util.spec_from_file_location("lte_real_geometry", _PATH)
g = importlib.util.module_from_spec(_SPEC)
sys.modules["lte_real_geometry"] = g  # dataclasses look their module up by name
_SPEC.loader.exec_module(g)

# 8 eNBs within 2 km of the circuit, 60 s of outage: about a second per ekf run
SHORT = g.World(hearing_km=2.0, gps_off_s=90.0, outage_s=60.0, tail_s=0.0)


def _attached(w, seed=0, case=None, counts=None):
    spec = g.spec_for(w)
    records = g.lte_records(w, spec, seed, case or g.Case())
    return spec, records, list(cells.attach(records, spec["origin_llh"], CellTable.load(), counts))


def test_records_are_shaped_as_the_front_end_writes_them():
    spec = g.spec_for(SHORT)
    records = g.lte_records(SHORT, spec, 0, g.Case())
    assert records
    for m in records:
        assert (m.source, m.kind) == ("lte", "pseudorange")
        assert re.fullmatch(r"lte:2460:\d+", m.emitter)
        assert "emitter_llh" not in m.meta and "emitter_enu" not in m.meta
        assert m.meta["rx_clock"] == "rtl0"
        assert m.meta["ambiguity_m"] == pytest.approx(299792458.0 * 0.01)
        assert 0.0 <= m.value[0] < m.meta["ambiguity_m"]  # known only modulo one frame


def test_the_lookup_drops_colliding_pcis_and_lines_up_each_sites_sectors():
    counts = Counter()
    spec, records, attached = _attached(SHORT, counts=counts)
    assert counts[COLLISION] > 0  # real PCI reuse on this carrier, left to the lookup to drop
    assert counts[UNKNOWN] == 0 and counts[MATCHED] == len(attached)
    assert counts[MATCHED] + counts[COLLISION] == len(records)
    # After alignment, a site's sectors at one epoch differ only by noise: real positions are
    # used, and sectors that wrapped differently share one site clock
    ts = g._times(SHORT, spec)
    track = g._track(SHORT, spec, ts)
    by: dict = {}
    for m in attached:
        k = int(round((m.t_ns - scenario.T0_NS) / 1e9 * SHORT.rate_hz))
        e = llh_to_enu(m.meta["emitter_llh"], spec["origin_llh"])
        by.setdefault((m.meta["site"], k), []).append(m.value[0] - np.linalg.norm(track[k] - e))
    spreads = [np.ptp(v) for v in by.values() if len(v) > 1]
    assert spreads and max(spreads) < 8 * SHORT.sigma_m


def test_the_victim_is_matched_by_every_sector_and_heard_the_whole_run():
    enb, pcis = g.victim(SHORT)
    spec = g.spec_for(SHORT)
    table = CellTable.load()
    for pci in pcis:
        status, cell = table.associate(SHORT.earfcn, pci, spec["origin_llh"])
        assert status == MATCHED and cell.enb_id == enb
    n_epochs = len(g._times(SHORT, spec))
    heard = Counter(m.emitter for m in g.lte_records(SHORT, spec, 0, g.Case()))
    assert all(heard[f"lte:{SHORT.earfcn}:{pci}"] == n_epochs for pci in pcis)


def _matched_positions(table, spec):
    """PCI -> (eNB, east and north) of every cell the lookup matches on the carrier."""
    out = {}
    for pci in range(504):  # every LTE PCI
        status, cell = table.associate(SHORT.earfcn, pci, spec["origin_llh"])
        if status == MATCHED:
            e = llh_to_enu([cell.lat, cell.lon, spec["origin_llh"][2]], spec["origin_llh"])
            out[pci] = (cell.enb_id, np.array(e[:2]))
    return out


def test_a_moved_tower_moves_only_that_enb_by_the_offset(tmp_path):
    spec = g.spec_for(SHORT)
    enb, pcis = g.victim(SHORT)
    table = g.edited_table(SHORT, g.Case("m", "move", 200.0), 0, str(tmp_path))
    before, after = _matched_positions(CellTable.load(), spec), _matched_positions(table, spec)
    assert before.keys() == after.keys()
    moved = {p for p in before if np.linalg.norm(after[p][1] - before[p][1]) > 1e-3}
    assert moved == set(pcis) and all(before[p][0] == enb for p in moved)
    for p in moved:
        assert np.linalg.norm(after[p][1] - before[p][1]) == pytest.approx(200.0, abs=0.1)


def test_position_jitter_moves_every_enb_and_keeps_its_sectors_together(tmp_path):
    spec = g.spec_for(SHORT)
    table = g.edited_table(SHORT, g.Case("j", "jitter", 30.0), 0, str(tmp_path))
    before, after = _matched_positions(CellTable.load(), spec), _matched_positions(table, spec)
    shifts: dict = {}
    for pci, (enb, p) in before.items():
        shifts.setdefault(enb, []).append(after[pci][1] - p)
    assert len(shifts) > 50
    for v in shifts.values():
        assert np.ptp(np.array(v), axis=0).max() < 0.1  # the file holds 1e-7 degrees
        assert np.linalg.norm(v[0]) > 1e-3


def test_a_rogue_replaces_the_registered_sector_and_leaves_the_others_alone():
    spec = g.spec_for(SHORT)
    _, pcis = g.victim(SHORT)
    rogue_pci = f"lte:{SHORT.earfcn}:{pcis[0]}"
    clean = g.lte_records(SHORT, spec, 0, g.Case())
    rogue = g.lte_records(SHORT, spec, 0, g.Case("r", "rogue", "one"))

    def others(records):
        return [(m.t_ns, m.emitter, m.value) for m in records if m.emitter != rogue_pci]

    assert others(clean) == others(rogue)
    a = {m.t_ns: m.value[0] for m in clean if m.emitter == rogue_pci}
    b = {m.t_ns: m.value[0] for m in rogue if m.emitter == rogue_pci}
    assert b  # heard, under the registered PCI
    assert all(a[t] != v for t, v in b.items() if t in a)


def test_nav_estimate_runs_the_same_lookup_as_the_harness():
    w = g.World(hearing_km=2.0, gps_off_s=30.0, outage_s=20.0, tail_s=0.0)
    spec, _, _ = _attached(w)
    sim = scenario.generate(spec, 0)
    stream = g._stream(w, spec, sim, 0, g.Case())
    attached = list(cells.attach(stream, spec["origin_llh"], CellTable.load()))
    direct = list(nav.estimate("ekf", stream, origin_llh=spec["origin_llh"]))
    harness = list(nav.estimate("ekf", attached, origin_llh=spec["origin_llh"]))
    assert len(direct) == len(harness) > 400
    assert all(
        a.pos_enu == b.pos_enu and a.hpl_m == b.hpl_m for a, b in zip(direct, harness, strict=True)
    )


def test_ekf_on_real_geometry_holds_a_short_outage():
    row = g.run_job(g.Job(SHORT, g.Case(), "ekf", 0))
    assert not row.error
    assert row.outage.h_p95_m < 20.0  # regression guard: observed 11.5 m (seed 0)
    assert row.outage.hazardous_epochs == 0
    assert row.outage.hpl_bound_frac == 1.0  # observed on this short run only


def test_a_missing_tower_is_dropped_counted_and_equals_never_hearing_it():
    missing = g.run_job(g.Job(SHORT, g.Case("m", "missing", "enb"), "ekf", 0))
    control = g.run_job(g.Job(SHORT, g.Case("c", "missing-control", "enb"), "ekf", 0))
    assert not missing.error and not control.error
    assert missing.counts[UNKNOWN] > 0
    assert missing.counts[MATCHED] == control.counts[MATCHED]
    assert UNKNOWN not in control.counts
    np.testing.assert_array_equal(missing.outage_err, control.outage_err)
