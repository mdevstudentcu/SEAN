"""The cell lookup over the whole committed table (#124).

Invariants rather than counts, so they survive a regenerated table; `analysis/lte_table_audit.py`
prints the counts. The tests on a reused pair need one pair of eNBs that reuse an (EARFCN, PCI)
less than 10 km apart: the committed table has 158 such pairs, the closest 1.26 km apart.
"""

import csv
from collections import defaultdict

import numpy as np
import pytest

from pnt.core.frames import enu_to_llh, llh_to_enu
from pnt.nav.cells import (
    CELL_TABLE,
    COLLISION,
    MATCHED,
    MAX_RANGE_KM,
    OUT_OF_RANGE,
    TRAVEL_KM,
    Cell,
    CellTable,
)

CARLETON = (45.3876, -75.6960, 70.0)  # the scenarios' session origin, the table's centre
RECEIVERS_ENU_M = [(0.0, 0.0), (0.0, 5000.0), (8000.0, 0.0), (-3000.0, -4000.0)]
RANGES_KM = (2.0, 5.0, MAX_RANGE_KM)


@pytest.fixture(scope="module")
def rows() -> list[Cell]:
    with open(CELL_TABLE, newline="") as f:
        return [
            Cell(
                int(r["earfcn"]),
                int(r["pci"]),
                int(r["enb_id"]),
                float(r["lat"]),
                float(r["lon"]),
                float(r["ant_height_agl_m"]),
            )
            for r in csv.DictReader(f)
        ]


@pytest.fixture(scope="module")
def table() -> CellTable:
    return CellTable.load()


def km(cell: Cell, origin) -> float:
    return float(np.hypot(*llh_to_enu([cell.lat, cell.lon, origin[2]], origin)[:2])) / 1e3


def receivers() -> list[tuple[float, float, float]]:
    return [(*enu_to_llh([e, n, 0.0], CARLETON)[:2], CARLETON[2]) for e, n in RECEIVERS_ENU_M]


def reused_pair(rows: list[Cell]) -> tuple[Cell, Cell]:
    """Two sectors of different eNBs on one (EARFCN, PCI), the closest such pair."""
    by_key: dict[tuple[int, int], list[Cell]] = defaultdict(list)
    for c in rows:
        by_key[c.earfcn, c.pci].append(c)
    pairs = [
        (km(a, (b.lat, b.lon, 0.0)), a, b)
        for cells in by_key.values()
        for i, a in enumerate(cells)
        for b in cells[i + 1 :]
        if a.enb_id != b.enb_id
    ]
    assert pairs, "the table has no reused (EARFCN, PCI); these tests need revisiting"
    _, a, b = min(pairs, key=lambda p: p[0])
    return a, b


def test_from_carleton_every_sector_resolves_to_its_own_enb_or_to_none(rows, table):
    for c in rows:
        status, got = table.associate(c.earfcn, c.pci, CARLETON)
        assert status in (MATCHED, COLLISION), c  # the table's radius is MAX_RANGE_KM
        if status == MATCHED:
            assert (got.enb_id, got.lat, got.lon) == (c.enb_id, c.lat, c.lon)


def test_the_status_follows_how_many_enbs_could_be_heard_on_the_cell(rows, table):
    """Collision: two or more eNBs within range plus travel (#138). Else matched if one is within
    range, out of range otherwise."""
    for origin in receivers():
        dist = {c: km(c, origin) for c in rows}
        by_key: dict[tuple[int, int], list[Cell]] = defaultdict(list)
        for c in rows:
            by_key[c.earfcn, c.pci].append(c)
        for max_range in RANGES_KM:
            for (earfcn, pci), cells in by_key.items():
                audible = {c.enb_id for c in cells if dist[c] <= max_range + TRAVEL_KM}
                near = {c.enb_id for c in cells if dist[c] <= max_range}
                status, got = table.associate(earfcn, pci, origin, max_range)
                if len(audible) > 1:
                    assert status == COLLISION
                elif not near:
                    assert status == OUT_OF_RANGE
                else:
                    assert status == MATCHED and got.enb_id in near


def test_a_cell_heard_within_max_range_never_resolves_to_another_enb(rows, table):
    for origin in receivers():
        for max_range in RANGES_KM:
            for c in rows:
                if km(c, origin) > max_range:
                    continue
                status, got = table.associate(c.earfcn, c.pci, origin, max_range)
                assert status == COLLISION or got.enb_id == c.enb_id, (c, origin, max_range)


def test_a_cell_heard_beyond_max_range_is_a_collision_not_the_near_enb(rows, table):
    """#138. The receiver has moved towards the far eNB, which is beyond the range from the
    origin, and hears it. Before, the near eNB was matched; without the travel margin it still
    is, so the margin is what keeps it out."""
    near, far = reused_pair(rows)
    origin = (near.lat, near.lon, CARLETON[2])
    max_range = km(far, origin) / 2  # the far eNB is heard, but lies beyond the range
    assert table.associate(far.earfcn, far.pci, origin, max_range) == (COLLISION, None)
    status, got = table.associate(far.earfcn, far.pci, origin, max_range, travel_km=0.0)
    assert status == MATCHED and got.enb_id == near.enb_id != far.enb_id


def test_from_the_table_centre_the_travel_margin_costs_no_cells(rows, table):
    """Every row is within MAX_RANGE_KM of Carleton, so every eNB on a PCI was already a candidate
    there. Observed on the committed table: 3752 of 4059 rows matched, with or without it."""
    for c in rows:
        assert table.associate(c.earfcn, c.pci, CARLETON) == table.associate(
            c.earfcn, c.pci, CARLETON, travel_km=0.0
        )


def test_the_lookup_still_resolves_most_cells_heard_within_5_km(rows, table):
    """Regression guard, not a requirement: at the four test receivers, of the rows within 5 km,
    observed 91.3 % to 93.8 % matched their own eNB with the travel margin (94.0 % to 98.4 %
    without it); a guard at 90 % catches a lookup that drops most cells to stay safe."""
    for origin in receivers():
        heard = [c for c in rows if km(c, origin) <= 5.0]
        right = 0
        for c in heard:
            status, got = table.associate(c.earfcn, c.pci, origin)
            right += status == MATCHED and got.enb_id == c.enb_id
        assert right / len(heard) >= 0.90, origin


def test_a_cell_missing_from_the_table_resolves_to_an_enb_that_reuses_its_pci(rows):
    near, far = reused_pair(rows)
    without_far = CellTable(c for c in rows if c.enb_id != far.enb_id)
    origin = (far.lat, far.lon, CARLETON[2])  # heard next to its own mast, as at the table's edge
    status, got = without_far.associate(far.earfcn, far.pci, origin)
    assert status == MATCHED and got.enb_id == near.enb_id
