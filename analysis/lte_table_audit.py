"""Whole-table audit of the LTE cell lookup (#124): does it ever pick the wrong site?

Every row of `lte-cells-ottawa.csv` goes through the public `CellTable.associate`, from Carleton
and from a grid of receivers used as session origins, then with the receiver away from the
origin under several lookup settings (#138). Prints a markdown summary; `--out` also writes a
figure.

    python analysis/lte_table_audit.py --out /tmp/lte-table-audit.png

Registry geometry only, no radio: a cell is "heard" if it is within a hearing distance, with no
terrain, beam pattern, power or interference. The PCIs are as filed; nothing here checks them
against what the towers broadcast. It shows what the lookup does with the table, not how many
cells a real capture will resolve (#87).
"""

import argparse
import csv
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pnt.core.frames import ecef_to_enu, enu_to_llh, llh_to_ecef, llh_to_enu
from pnt.nav.cells import (
    CELL_TABLE,
    COLLISION,
    MATCHED,
    MAX_RANGE_KM,
    OUT_OF_RANGE,
    TRAVEL_KM,
    UNKNOWN,
    Cell,
    CellTable,
)

CARLETON = (45.3876, -75.6960, 70.0)  # the scenarios' session origin
TABLE_RADIUS_KM = 10.0  # analysis/extract_lte_cells.py RADIUS_KM
WRONG = "wrong_enb"  # a MATCHED whose eNB is not the one that was heard

GEOMETRY_RADII_KM = (1.0, 2.0, 3.0, 5.0)
GRID_STEP_KM = 1.0  # TBC
GRID_EXTENT_KM = 8.0  # TBC
HEARING_KM = (2.0, 3.0, 5.0)  # TBC: link range is not measured yet (#87)
MAX_RANGES_KM = (2.0, 3.0, 5.0, 10.0)  # TBC: 10 is today's MAX_RANGE_KM
HOLDOUT_KM = (6.0, 8.0)  # TBC: where the table is pretended to stop
EDGE_RINGS_KM = ((0.0, 3.0), (3.0, 5.0), (5.0, 7.0), (7.0, 8.0))  # TBC
# Receiver away from the origin (#138): origins every ORIGIN_STEP_KM on the grid, receivers on the
# grid ring AWAY_KM (+-0.5) from each. All TBC.
ORIGIN_STEP_KM = 2.0
AWAY_KM = (2.0, 5.0, 8.0, 13.0)  # 13: the distance in #138's reproduction
# Lookup settings compared: (label, max_range_km, travel_km). travel 0 is the lookup before #138;
# "range 20" widens the match range instead, which also matches a lone eNB up to 20 km away.
SETTINGS = (
    ("before #138: range 10, travel 0", MAX_RANGE_KM, 0.0),
    ("travel 2", MAX_RANGE_KM, 2.0),
    ("travel 5", MAX_RANGE_KM, 5.0),
    ("travel 10", MAX_RANGE_KM, 10.0),
    ("range 20, travel 0", 2 * MAX_RANGE_KM, 0.0),
)


@dataclass(frozen=True)
class Row:
    cell: Cell
    carrier: tuple[int, str]  # (EARFCN, licensee's first word)
    flags: str


def load_rows() -> list[Row]:
    with open(CELL_TABLE, newline="") as f:
        return [
            Row(
                Cell(
                    int(r["earfcn"]),
                    int(r["pci"]),
                    int(r["enb_id"]),
                    float(r["lat"]),
                    float(r["lon"]),
                    float(r["ant_height_agl_m"]),
                ),
                (int(r["earfcn"]), r["licensee"].split()[0]),
                r["flags"],
            )
            for r in csv.DictReader(f)
        ]


def horizontal_enu_km(lat: np.ndarray, lon: np.ndarray, origin) -> np.ndarray:
    """(2, N) east and north in km, the horizontal distance `associate` measures."""
    o = llh_to_ecef(origin)
    rot = np.column_stack([ecef_to_enu(o + e, origin) for e in np.eye(3)])
    enu = rot @ (llh_to_ecef([lat, lon, origin[2]]) - o[:, None])
    return enu[:2] / 1e3


def outcome(table: CellTable, row: Row, origin, max_range_km: float) -> tuple[str, Cell | None]:
    status, cell = table.associate(row.cell.earfcn, row.cell.pci, origin, max_range_km)
    if status == MATCHED and cell.enb_id != row.cell.enb_id:
        return WRONG, cell
    return status, cell


def separation_km(a: Cell, b: Cell) -> float:
    return float(np.hypot(*llh_to_enu([a.lat, a.lon, 0.0], [b.lat, b.lon, 0.0])[:2])) / 1e3


def hdop(east_north_km: np.ndarray) -> float:
    """Horizontal DOP with one extra clock unknown and height known (baro). NaN if unsolvable."""
    if east_north_km.shape[0] < 3:
        return float("nan")
    u = east_north_km / np.linalg.norm(east_north_km, axis=1, keepdims=True)
    g = np.column_stack([-u, np.ones(len(u))])
    if np.linalg.matrix_rank(g) < 3:
        return float("nan")
    q = np.linalg.inv(g.T @ g)
    return float(np.sqrt(q[0, 0] + q[1, 1]))


def receivers(limit_km: float = GRID_EXTENT_KM) -> list[tuple[tuple[float, float, float], float]]:
    """(origin_llh, km from Carleton) for each grid point within `limit_km`."""
    n = int(GRID_EXTENT_KM / GRID_STEP_KM)
    axis = np.arange(-n, n + 1) * GRID_STEP_KM
    out = []
    for e in axis:
        for north in axis:
            d = float(np.hypot(e, north))
            if d <= limit_km:
                lat, lon, _ = enu_to_llh([e * 1e3, north * 1e3, 0.0], CARLETON)
                out.append(((float(lat), float(lon), CARLETON[2]), d))
    return out


def table_md(header: list[str], lines: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    out += ["| " + " | ".join(str(v) for v in line) + " |" for line in lines]
    return "\n".join(out)


def pct(n: float, total: float) -> str:
    return f"{100.0 * n / total:.2f}" if total else "n/a"


@dataclass
class Audit:
    rows: list[Row]
    lat: np.ndarray
    lon: np.ndarray
    table: CellTable


def enb_fate(statuses: set[str]) -> str:
    """An eNB counts as usable if any of its sectors resolves."""
    for s in (MATCHED, WRONG, COLLISION, OUT_OF_RANGE, UNKNOWN):
        if s in statuses:
            return s
    raise ValueError(statuses)


def carleton(a: Audit) -> dict:
    """The status of every row from Carleton at the default range."""
    results = [outcome(a.table, r, CARLETON, MAX_RANGE_KM) for r in a.rows]
    east, north = horizontal_enu_km(a.lat, a.lon, CARLETON)
    return {"status": [s for s, _ in results], "en": np.column_stack([east, north])}


def carrier_order(a: Audit, c: dict) -> list[tuple[int, str]]:
    """Most matched eNBs within 3 km first, the order the scan list cares about."""
    near: dict[tuple[int, str], set[int]] = defaultdict(set)
    total: dict[tuple[int, str], set[int]] = defaultdict(set)
    for r, s, en in zip(a.rows, c["status"], c["en"], strict=True):
        total[r.carrier].add(r.cell.enb_id)
        if s == MATCHED and np.hypot(*en) <= 3.0:
            near[r.carrier].add(r.cell.enb_id)
    return sorted(total, key=lambda k: (-len(near[k]), -len(total[k]), k))


def collision_separations_km(a: Audit) -> list[float]:
    """Distance between every two eNBs that share an (EARFCN, PCI), one entry per pair."""
    sites: dict[tuple[int, int], dict[int, Cell]] = defaultdict(dict)
    for r in a.rows:
        sites[r.cell.earfcn, r.cell.pci][r.cell.enb_id] = r.cell
    return [
        separation_km(x, y)
        for enbs in sites.values()
        for i, x in enumerate(enbs.values())
        for y in list(enbs.values())[i + 1 :]
    ]


def status_section(a: Audit, c: dict, order: list[tuple[int, str]]) -> str:
    lines = []
    totals = Counter()
    for carrier in order:
        idx = [i for i, r in enumerate(a.rows) if r.carrier == carrier]
        sectors = Counter(c["status"][i] for i in idx)
        per_enb: dict[int, set[str]] = defaultdict(set)
        for i in idx:
            per_enb[a.rows[i].cell.enb_id].add(c["status"][i])
        enbs = Counter(enb_fate(v) for v in per_enb.values())
        lines.append(
            [
                carrier[0],
                carrier[1],
                len(idx),
                sectors[MATCHED],
                sectors[COLLISION],
                sectors[OUT_OF_RANGE],
                sectors[WRONG],
                len(per_enb),
                enbs[MATCHED],
                enbs[COLLISION],
                enbs[OUT_OF_RANGE],
            ]
        )
        totals.update(sectors)
    n_wrong = totals[WRONG]
    seps = collision_separations_km(a)
    head = (
        f"## From Carleton, `max_range_km` = {MAX_RANGE_KM:g}\n\n"
        f"{len(a.rows)} rows: {totals[MATCHED]} matched their own eNB, "
        f"{totals[COLLISION]} lost to collision, {totals[OUT_OF_RANGE]} out of range, "
        f"{totals[UNKNOWN]} unknown. **Rows matched to another eNB: {n_wrong}.** "
        "An eNB counts as matched if any of its sectors on that carrier matched. "
        f"{len(seps)} pairs of eNBs share an (EARFCN, PCI); their separation is "
        f"{min(seps):.2f} km at least, {np.median(seps):.1f} km median, {max(seps):.1f} km at "
        "most.\n"
    )
    return (
        head
        + "\n"
        + table_md(
            [
                "EARFCN",
                "licensee",
                "sectors",
                "matched",
                "collision",
                "out of range",
                "wrong eNB",
                "eNBs",
                "eNBs matched",
                "eNBs collision",
                "eNBs out of range",
            ],
            lines,
        )
    )


def geometry(a: Audit, c: dict, carrier: tuple[int, str] | None) -> dict[float, tuple]:
    """radius -> (eNBs, masts, HDOP over eNBs, HDOP over masts), matched eNBs only."""
    enbs: dict[int, np.ndarray] = {}
    for r, s, en in zip(a.rows, c["status"], c["en"], strict=True):
        if s == MATCHED and carrier in (None, r.carrier):
            enbs[r.cell.enb_id] = en
    out = {}
    all_en = np.array(list(enbs.values())).reshape(-1, 2)
    for radius in GEOMETRY_RADII_KM:
        inside = all_en[np.hypot(*all_en.T) <= radius]
        masts = np.unique(np.round(inside, 6), axis=0)
        out[radius] = (len(inside), len(masts), hdop(inside), hdop(masts))
    return out


def geometry_section(a: Audit, c: dict, order: list[tuple[int, str]]) -> tuple[str, dict]:
    def fmt(v: float) -> str:
        return "-" if np.isnan(v) else f"{v:.2f}"

    all_geo = {carrier: geometry(a, c, carrier) for carrier in order}
    all_geo[None] = geometry(a, c, None)
    registered: dict[tuple[int, str] | None, set[int]] = defaultdict(set)
    for r, en in zip(a.rows, c["en"], strict=True):
        if np.hypot(*en) <= 3.0:
            registered[r.carrier].add(r.cell.enb_id)
            registered[None].add(r.cell.enb_id)
    lines = []
    for carrier in [*order, None]:
        name = [carrier[0], carrier[1]] if carrier else ["all", "union"]
        name.append(len(registered[carrier]))
        cells = [
            f"{n} / {m} / {fmt(h)} / {fmt(hm)}"
            for n, m, h, hm in (all_geo[carrier][r] for r in GEOMETRY_RADII_KM)
        ]
        lines.append(name + cells)
    text = (
        "## Usable geometry at Carleton\n\n"
        "Each cell: matched eNBs / distinct masts / HDOP over eNBs / HDOP over masts. eNBs on one "
        "mast count as separate ranges in the first HDOP and once in the second. HDOP has one "
        "clock unknown and height known from the baro; `-` means fewer than 3 or degenerate. "
        "`all` assumes one clock across carriers, which separate dongles would not share.\n\n"
        + table_md(
            [
                "EARFCN",
                "licensee",
                "eNBs registered within 3 km",
                *[f"within {r:g} km" for r in GEOMETRY_RADII_KM],
            ],
            lines,
        )
    )
    return text, all_geo


def sweep_grid(a: Audit) -> dict:
    """The fate of every heard (receiver, row) pair, for each hearing range and `max_range_km`."""
    rx = receivers()
    stats: dict[tuple[float, float], Counter] = defaultdict(Counter)
    errors: dict[tuple[float, float], list[float]] = defaultdict(list)
    pairs: dict[tuple[float, float], set] = defaultdict(set)
    per_rx = {k: np.zeros(len(rx)) for k in _sweep_keys()}
    carriers: dict[tuple[float, float], Counter] = defaultdict(Counter)
    for i, (origin, _) in enumerate(rx):
        d = np.hypot(*horizontal_enu_km(a.lat, a.lon, origin))
        for j in np.flatnonzero(d <= max(HEARING_KM)):
            for max_range in MAX_RANGES_KM:
                status, cell = outcome(a.table, a.rows[j], origin, max_range)
                for hear in HEARING_KM:
                    if d[j] > hear:
                        continue
                    key = (hear, max_range)
                    stats[key][status] += 1
                    if status == WRONG:
                        row = a.rows[j].cell
                        errors[key].append(separation_km(row, cell))
                        pairs[key].add((row.earfcn, row.pci, row.enb_id, cell.enb_id))
                        per_rx[key][i] += 1
                        carriers[key][a.rows[j].carrier] += 1
    return {
        "stats": stats,
        "errors": errors,
        "pairs": pairs,
        "per_rx": per_rx,
        "carriers": carriers,
        "rx": rx,
    }


def _sweep_keys() -> list[tuple[float, float]]:
    return [(h, m) for h in HEARING_KM for m in MAX_RANGES_KM]


def grid_section(g: dict) -> str:
    lines = []
    for hear, max_range in _sweep_keys():
        s = g["stats"][hear, max_range]
        n = sum(s.values())
        err = g["errors"][hear, max_range]
        lines.append(
            [
                f"{hear:g}",
                f"{max_range:g}",
                n,
                pct(s[MATCHED], n),
                pct(s[COLLISION], n),
                pct(s[OUT_OF_RANGE], n),
                f"**{pct(s[WRONG], n)}** ({s[WRONG]})",
                f"{int(np.count_nonzero(g['per_rx'][hear, max_range]))}/{len(g['rx'])}",
                len(g["pairs"][hear, max_range]),
                f"{np.median(err):.1f} / {max(err):.1f}" if err else "-",
            ]
        )
    text = (
        f"## Receiver grid\n\n{len(g['rx'])} receivers, every {GRID_STEP_KM:g} km out to "
        f"{GRID_EXTENT_KM:g} km from Carleton (TBC), each used as the session origin. Heard = "
        "within the hearing range (TBC), all in the table. Percentages are of heard "
        "(receiver, sector) pairs. Site error is the distance from the sector actually heard to "
        "the site the lookup returned.\n\n"
        + table_md(
            [
                "hearing km",
                "`max_range_km`",
                "heard",
                "right eNB %",
                "collision %",
                "out of range %",
                "WRONG eNB % (n)",
                "receivers with a wrong eNB",
                "distinct wrong (cell, eNB) pairs",
                "site error median / max km",
            ],
            lines,
        )
    )
    worst = max(_sweep_keys(), key=lambda k: g["stats"][k][WRONG])
    if g["stats"][worst][WRONG]:
        by_carrier = ", ".join(f"{c[0]} {c[1]} {n}" for c, n in g["carriers"][worst].most_common())
        text += (
            f"\n\nWrong eNBs by carrier, at hearing {worst[0]:g} km and `max_range_km` "
            f"{worst[1]:g}: {by_carrier}."
        )
    return text


def holdout(a: Audit, stop_km: float) -> dict:
    """Pretend the table stops at `stop_km`: heard cells beyond it play cells it lacks."""
    from_carleton = np.hypot(*horizontal_enu_km(a.lat, a.lon, CARLETON))
    kept = CellTable(r.cell for r, d in zip(a.rows, from_carleton, strict=True) if d <= stop_km)
    stats: dict[tuple[float, float], Counter] = defaultdict(Counter)
    errors: dict[tuple[float, float], list[float]] = defaultdict(list)
    rx = receivers(stop_km)
    for origin, _ in rx:
        d = np.hypot(*horizontal_enu_km(a.lat, a.lon, origin))
        for j in np.flatnonzero((d <= max(HEARING_KM)) & (from_carleton > stop_km)):
            for max_range in MAX_RANGES_KM:
                status, cell = outcome(kept, a.rows[j], origin, max_range)
                assert status != MATCHED  # an eNB's rows share one position, so it was cut whole
                for hear in HEARING_KM:
                    if d[j] <= hear:
                        key = (hear, max_range)
                        stats[key][status] += 1
                        if status == WRONG:
                            errors[key].append(separation_km(a.rows[j].cell, cell))
    return {"stats": stats, "errors": errors, "rx": rx}


def circle_outside_fraction(d: float, r: float, big_r: float) -> float:
    """Share of a disk of radius `r`, `d` from the centre of the table disk, outside the table."""
    if d + r <= big_r:
        return 0.0
    area = (
        r**2 * np.arccos((d**2 + r**2 - big_r**2) / (2 * d * r))
        + big_r**2 * np.arccos((d**2 + big_r**2 - r**2) / (2 * d * big_r))
        - 0.5 * np.sqrt((-d + r + big_r) * (d + r - big_r) * (d - r + big_r) * (d + r + big_r))
    )
    return float(1.0 - area / (np.pi * r**2))


def edge_section(a: Audit, g: dict, holdouts: dict[float, dict]) -> str:
    from_carleton = np.hypot(*horizontal_enu_km(a.lat, a.lon, CARLETON))
    outer = np.count_nonzero((from_carleton > 8.0) & (from_carleton <= TABLE_RADIUS_KM))
    density = outer / (np.pi * (TABLE_RADIUS_KM**2 - 8.0**2))  # sectors per km^2, 8-10 km
    rx_to_rows = np.array([np.hypot(*horizontal_enu_km(a.lat, a.lon, o)) for o, _ in g["rx"]])
    dists = np.array([d for _, d in g["rx"]])
    lines = []
    for low, high in EDGE_RINGS_KM:
        ring = (dists > low if low else dists >= 0.0) & (dists <= high)
        for hear in HEARING_KM:
            frac = np.array(
                [circle_outside_fraction(float(d), hear, TABLE_RADIUS_KM) for d in dists[ring]]
            )
            area = frac * np.pi * hear**2
            heard = np.count_nonzero(rx_to_rows[ring] <= hear, axis=1)
            lines.append(
                [
                    f"{low:g}-{high:g}",
                    int(np.count_nonzero(ring)),
                    f"{hear:g}",
                    f"{100.0 * frac.mean():.1f}",
                    f"{heard.mean():.0f}",
                    f"{(area * density).mean():.0f}",
                ]
            )
    text = (
        "## Table edge\n\n"
        f"The table stops at {TABLE_RADIUS_KM:g} km. A receiver near the edge can hear cells that "
        "are not in it, and the lookup cannot tell: such a cell is left out only if no table row "
        "in range reuses its (EARFCN, PCI). Sectors unseen is the outside area times the "
        f"table's density in its outer ring, 8-10 km ({density:.1f} sectors/km², `TBC`): an "
        "extrapolation, not a count.\n\n"
        + table_md(
            [
                "receiver km from Carleton",
                "receivers",
                "hearing km",
                "hearing disk outside table %",
                "in-table sectors heard, mean",
                "sectors unseen, mean (TBC)",
            ],
            lines,
        )
    )
    h_lines = []
    for stop, h in holdouts.items():
        for hear, max_range in _sweep_keys():
            s = h["stats"][hear, max_range]
            n = sum(s.values())
            err = h["errors"][hear, max_range]
            h_lines.append(
                [
                    f"{stop:g}",
                    len(h["rx"]),
                    f"{hear:g}",
                    f"{max_range:g}",
                    n,
                    pct(s[UNKNOWN], n),
                    pct(s[OUT_OF_RANGE], n),
                    pct(s[COLLISION], n),
                    f"**{pct(s[WRONG], n)}** ({s[WRONG]})",
                    f"{np.median(err):.1f} / {max(err):.1f}" if err else "-",
                ]
            )
    text += (
        "\n\n**Holdout on real PCIs.** The table is cut at a smaller radius (TBC), keeping the "
        "real PCI plan; receivers stay inside the cut. Each heard cell beyond the cut plays a "
        "cell missing from the table, so any match is to a wrong eNB. Rates are of those heard "
        "cells only.\n\n"
        + table_md(
            [
                "table cut km",
                "receivers",
                "hearing km",
                "`max_range_km`",
                "heard beyond cut",
                "unknown %",
                "out of range %",
                "collision %",
                "WRONG eNB % (n)",
                "site error median / max km",
            ],
            h_lines,
        )
    )
    text += (
        "\n\n**What this audit cannot see:** cells beyond 10 km and any unfiled, moved or "
        "retired cell; whether a filed PCI or EARFCN is what the tower broadcasts; which cells "
        "are really audible (hearing is a disk, no terrain, beam or power). Here each receiver "
        "is the origin; *Receiver away from the origin* below covers a receiver that has moved "
        "from it. The holdout's PCI plan is denser than the real edge's may be, so its rate is an "
        "indication for the 10 km edge, not a measurement of it."
    )
    return text


def away(a: Audit) -> dict:
    """The fate of every heard (receiver, row) pair when the receiver is AWAY_KM from the session
    origin, for each of SETTINGS. A lookup result depends only on the origin, so it is computed
    once per (origin, cell) and shared by that origin's receivers."""
    keys = sorted({(r.cell.earfcn, r.cell.pci) for r in a.rows})
    key_of = {k: i for i, k in enumerate(keys)}
    row_key = np.array([key_of[r.cell.earfcn, r.cell.pci] for r in a.rows])
    row_enb = np.array([r.cell.enb_id for r in a.rows])
    row_en = np.column_stack(horizontal_enu_km(a.lat, a.lon, CARLETON))
    rx = receivers(GRID_EXTENT_KM)
    rx_en = np.array([horizontal_enu_km(np.array([o[0]]), np.array([o[1]]), CARLETON)[:, 0]
                      for o, _ in rx])  # fmt: skip
    rx_to_row = np.hypot(*(rx_en[:, None, :] - row_en[None, :, :]).transpose(2, 0, 1))
    step = int(round(ORIGIN_STEP_KM / GRID_STEP_KM))
    n = int(GRID_EXTENT_KM / GRID_STEP_KM)
    on_step = np.all(np.round(rx_en / GRID_STEP_KM + n) % step == 0, axis=1)
    origins = np.flatnonzero(on_step).tolist()  # every ORIGIN_STEP_KM on the grid
    codes = [MATCHED, WRONG, COLLISION, OUT_OF_RANGE, UNKNOWN]
    stats: dict[tuple, Counter] = defaultdict(Counter)
    worst: dict[tuple, float] = defaultdict(float)
    for o in origins:
        origin = rx[o][0]
        o_to_rx = np.hypot(*(rx_en - rx_en[o]).T)
        for label, max_range, travel in SETTINGS:
            status = np.empty(len(keys), int)
            got_en = np.full((len(keys), 2), np.nan)
            got_enb = np.full(len(keys), -1)
            for k, (earfcn, pci) in enumerate(keys):
                s, cell = a.table.associate(earfcn, pci, origin, max_range, travel)
                status[k] = codes.index(s)
                if cell is not None:
                    got_enb[k] = cell.enb_id
                    got_en[k] = horizontal_enu_km(np.array([cell.lat]), np.array([cell.lon]),
                                                  CARLETON)[:, 0]  # fmt: skip
            fate = status[row_key].copy()
            fate[(fate == 0) & (got_enb[row_key] != row_enb)] = codes.index(WRONG)
            err = np.hypot(*(got_en[row_key] - row_en).T)
            for d in AWAY_KM:
                for r in np.flatnonzero(np.abs(o_to_rx - d) <= 0.5 * GRID_STEP_KM):
                    for hear in HEARING_KM:
                        heard = rx_to_row[r] <= hear
                        counts = np.bincount(fate[heard], minlength=len(codes))
                        key = (d, hear, label)
                        stats[key].update(dict(zip(codes, counts.tolist(), strict=True)))
                        stats[key]["receivers"] += 1
                        wrong = heard & (fate == 1)
                        if wrong.any():
                            worst[key] = max(worst[key], float(err[wrong].max()))
    return {"stats": stats, "worst": worst, "origins": len(origins)}


def holdout_settings(a: Audit, stop_km: float) -> dict[tuple[float, str], Counter]:
    """`holdout` for each of SETTINGS: (hearing, label) -> fates of heard cells beyond the cut."""
    from_carleton = np.hypot(*horizontal_enu_km(a.lat, a.lon, CARLETON))
    kept = CellTable(r.cell for r, d in zip(a.rows, from_carleton, strict=True) if d <= stop_km)
    stats: dict[tuple[float, str], Counter] = defaultdict(Counter)
    for origin, _ in receivers(stop_km):
        d = np.hypot(*horizontal_enu_km(a.lat, a.lon, origin))
        for j in np.flatnonzero((d <= max(HEARING_KM)) & (from_carleton > stop_km)):
            row = a.rows[j].cell
            for label, max_range, travel in SETTINGS:
                status, cell = kept.associate(row.earfcn, row.pci, origin, max_range, travel)
                status = WRONG if status == MATCHED else status  # its own eNB was cut
                for hear in HEARING_KM:
                    if d[j] <= hear:
                        stats[hear, label][status] += 1
    return stats


def _setting(label: str, max_range: float, travel: float) -> str:
    default = (max_range, travel) == (MAX_RANGE_KM, TRAVEL_KM)
    return label + (" (default)" if default else "")


def away_section(w: dict, holdouts: dict[float, dict]) -> str:
    lines = []
    for d in AWAY_KM:
        for hear in HEARING_KM:
            for label, max_range, travel in SETTINGS:
                s = w["stats"][d, hear, label]
                n = sum(s[k] for k in (MATCHED, WRONG, COLLISION, OUT_OF_RANGE, UNKNOWN))
                worst = w["worst"].get((d, hear, label))
                lines.append(
                    [
                        f"{d:g}",
                        f"{hear:g}",
                        _setting(label, max_range, travel),
                        s["receivers"],
                        n,
                        pct(s[MATCHED], n),
                        pct(s[COLLISION], n),
                        pct(s[OUT_OF_RANGE], n),
                        f"**{pct(s[WRONG], n)}** ({s[WRONG]})",
                        f"{worst:.1f}" if worst else "-",
                    ]
                )
    h_lines = []
    for stop, h in holdouts.items():
        for hear in HEARING_KM:
            for label, max_range, travel in SETTINGS:
                s = h[hear, label]
                n = sum(s.values())
                h_lines.append(
                    [
                        f"{stop:g}",
                        f"{hear:g}",
                        _setting(label, max_range, travel),
                        n,
                        pct(s[OUT_OF_RANGE] + s[UNKNOWN], n),
                        pct(s[COLLISION], n),
                        f"**{pct(s[WRONG], n)}** ({s[WRONG]})",
                    ]
                )
    return (
        "## Receiver away from the origin\n\n"
        f"Origins every {ORIGIN_STEP_KM:g} km on the grid ({w['origins']}), receivers on the grid "
        f"points about the given distance (+-{0.5 * GRID_STEP_KM:g} km) from each, all within "
        f"{GRID_EXTENT_KM:g} km of Carleton. Lookup settings: `max_range_km` (range) and "
        "`travel_km` (travel, how far the receiver may be from the origin; collisions only). "
        "Heard = within the hearing range (TBC), all in the table. Percentages are of heard "
        "(receiver, sector) pairs.\n\n"
        + table_md(
            [
                "receiver km from origin",
                "hearing km",
                "lookup",
                "(origin, receiver) pairs",
                "heard",
                "right eNB %",
                "collision %",
                "out of range %",
                "WRONG eNB % (n)",
                "worst site error km",
            ],
            lines,
        )
        + "\n\n**The same settings on the holdout** (as above: the table cut short, receivers "
        "inside the cut, the origin at the receiver). Every match here is to a wrong eNB.\n\n"
        + table_md(
            [
                "table cut km",
                "hearing km",
                "lookup",
                "heard beyond cut",
                "left out (unknown or out of range) %",
                "collision %",
                "WRONG eNB % (n)",
            ],
            h_lines,
        )
    )


def flags_section(a: Audit, c: dict, order: list[tuple[int, str]]) -> str:
    lines = []
    matched_total = 0
    flagged_total = 0
    near_total = 0
    near_flagged = 0
    enb_any: set[int] = set()
    enb_unflagged: set[int] = set()
    for carrier in order:
        by_flag = Counter()
        near = 0
        for r, s, en in zip(a.rows, c["status"], c["en"], strict=True):
            if r.carrier != carrier or s != MATCHED:
                continue
            by_flag[r.flags or "none"] += 1
            near += int(np.hypot(*en) <= 3.0)
            enb_any.add(r.cell.enb_id)
            if not r.flags:
                enb_unflagged.add(r.cell.enb_id)
            flagged_total += int(bool(r.flags))
            near_flagged += int(bool(r.flags) and np.hypot(*en) <= 3.0)
        total = sum(by_flag.values())
        matched_total += total
        near_total += near
        lines.append(
            [
                carrier[0],
                carrier[1],
                total,
                near,
                ", ".join(f"{k}: {v}" for k, v in by_flag.most_common()),
            ]
        )
    return (
        "## Flags among the matched sectors, from Carleton\n\n"
        f"Flagged rows: {flagged_total} of {matched_total} matched sectors "
        f"({pct(flagged_total, matched_total)} %), {near_flagged} of {near_total} within 3 km "
        f"({pct(near_flagged, near_total)} %). Matched eNBs with at least one unflagged sector: "
        f"{len(enb_unflagged)} of {len(enb_any)}. The lookup ignores flags.\n\n"
        + table_md(["EARFCN", "licensee", "matched", "within 3 km", "by flag"], lines)
    )


def _rates(stats: dict, hear: float, status: str) -> list[float]:
    return [100.0 * stats[hear, m][status] / sum(stats[hear, m].values()) for m in MAX_RANGES_KM]


def figure(
    path: str,
    g: dict,
    holdouts: dict[float, dict],
    geo: dict,
    order: list[tuple[int, str]],
    commit: str,
) -> None:
    import matplotlib.pyplot as plt

    hues = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # categorical slots 1-4, fixed order
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    (a_wrong, a_right, a_map), (*a_holdouts, a_hdop) = axes
    panels = [
        (a_wrong, g["stats"], WRONG, "heard cells in the table, WRONG eNB (%)",
         "Hazard, cells in the table"),
        (a_right, g["stats"], MATCHED, "heard cells, right eNB (%)", "Yield, cells in the table"),
    ] + [
        (ax, h["stats"], WRONG, "heard cells missing from the table, WRONG eNB (%)",
         f"Hazard, cells missing: table cut at {stop:g} km")
        for ax, (stop, h) in zip(a_holdouts, holdouts.items(), strict=True)
    ]  # fmt: skip
    for ax, stats, status, ylabel, title in panels:
        for color, hear in zip(hues, HEARING_KM, strict=False):
            ax.plot(MAX_RANGES_KM, _rates(stats, hear, status), "o-", color=color, lw=2, ms=6,
                    label=f"hearing {hear:g} km")  # fmt: skip
        ax.set(xlabel="max_range_km", ylabel=ylabel, title=title, xticks=MAX_RANGES_KM)
        ax.set_ylim(bottom=0)
    a_right.set_ylim(0, 100)
    worst = max(_sweep_keys(), key=lambda k: g["stats"][k][WRONG])
    lat = np.array([o[0] for o, _ in g["rx"]])
    lon = np.array([o[1] for o, _ in g["rx"]])
    east, north = horizontal_enu_km(lat, lon, CARLETON)
    scatter = a_map.scatter(east, north, c=g["per_rx"][worst], cmap="Blues", s=40,
                            edgecolors="0.6", linewidths=0.4)  # fmt: skip
    a_map.add_patch(plt.Circle((0, 0), TABLE_RADIUS_KM, fill=False, color="0.4", ls="--"))
    a_map.text(0, TABLE_RADIUS_KM + 0.3, "table edge", ha="center", color="0.3", fontsize=9)
    a_map.plot(0, 0, marker="+", color="0.1", ms=10)
    a_map.set(
        xlim=(-11, 11),
        ylim=(-11, 11),
        aspect="equal",
        xlabel="east of Carleton (km)",
        ylabel="north of Carleton (km)",
        title=f"Wrong eNBs per receiver (hearing {worst[0]:g}, max_range {worst[1]:g} km)",
    )
    fig.colorbar(scatter, ax=a_map, label="wrong-eNB matches")
    best = {}
    for carrier in order:  # the best carrier of each licensee with any geometry
        if carrier[1] not in best and geo[carrier][3.0][1] >= 3:
            best[carrier[1]] = carrier
    for color, carrier in zip(hues, [*best.values(), None], strict=False):
        name = f"{carrier[0]} {carrier[1]}" if carrier else "all carriers, one clock"
        values = [geo[carrier][r][3] for r in GEOMETRY_RADII_KM]
        a_hdop.plot(GEOMETRY_RADII_KM, values, "o-", color=color, lw=2, ms=6, label=name)
    a_hdop.set(xlabel="matched eNBs within (km of Carleton)", ylabel="HDOP over distinct masts",
               title="Geometry at Carleton", xticks=GEOMETRY_RADII_KM)  # fmt: skip
    a_hdop.set_ylim(bottom=0)
    for ax in (a_wrong, a_right, *a_holdouts, a_hdop):
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle(f"LTE cell lookup audit: registry geometry only, no radio. Commit {commit}")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f"\nwrote {path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", help="write a figure to this .png")
    args = p.parse_args()
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=7"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent,
    ).stdout.strip()
    rows = load_rows()
    audit = Audit(
        rows,
        np.array([r.cell.lat for r in rows]),
        np.array([r.cell.lon for r in rows]),
        CellTable.load(),
    )
    print(f"# LTE cell table audit, commit {commit}\n")
    print(f"Lookup defaults: `max_range_km` {MAX_RANGE_KM:g}, `travel_km` {TRAVEL_KM:g}.\n")
    print(f"{len(rows)} sectors, {len({r.cell.enb_id for r in rows})} eNBs, "
          f"{len({r.cell.earfcn for r in rows})} EARFCNs, "
          f"{len({r.carrier for r in rows})} carriers (EARFCN + licensee). "
          "Registry geometry through the public lookup; no radio.\n")  # fmt: skip
    c = carleton(audit)
    order = carrier_order(audit, c)
    print(status_section(audit, c, order), "\n")
    geo_text, geo = geometry_section(audit, c, order)
    print(geo_text, "\n")
    g = sweep_grid(audit)
    print(grid_section(g), "\n")
    holdouts = {stop: holdout(audit, stop) for stop in HOLDOUT_KM}
    print(edge_section(audit, g, holdouts), "\n")
    holdouts_by_setting = {stop: holdout_settings(audit, stop) for stop in HOLDOUT_KM}
    print(away_section(away(audit), holdouts_by_setting), "\n")
    print(flags_section(audit, c, order))
    if args.out:
        figure(args.out, g, holdouts, geo, order, commit)


if __name__ == "__main__":
    main()
