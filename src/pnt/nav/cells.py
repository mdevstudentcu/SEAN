"""Real LTE records -> what the filter needs (ADR-0023, #121).

The LTE front end names a heard cell `lte:<earfcn>:<pci>` and knows nothing of where it is. This
step, between any `Source` and the estimators (ADR-0004), looks each cell up in the committed
table and adds `meta.emitter_llh` and `meta.site`. Records that already carry a position (the
simulator's) pass through untouched.

- **Association is a hypothesis.** An (EARFCN, PCI) maps to a registered eNB only if exactly one
  eNB that the receiver could hear has it. Unknown cells and collisions are left out and counted,
  never guessed: a wrong tower position is worse than one tower fewer. The mapper for those cells
  is not built.
- **Which eNBs could be heard:** the lookup knows the session origin, not where the receiver is
  now. A receiver up to `travel_km` from the origin hears up to `max_range_km` from itself, so
  every registered eNB within their sum of the origin could be the one heard: two or more of
  them on one (EARFCN, PCI) is a collision (#138). Ranging from the origin alone matched a near
  eNB when a far one on the same PCI was heard. A match still needs the eNB within
  `max_range_km` of the origin, as before: the margin only ever turns a match into a collision,
  so a cell missing from the table is never matched to an eNB further away than before.
- **Cells missing from the table** can't be caught here: a heard cell that the table lacks still
  matches a registered eNB that reuses its PCI (the table's edge, unfiled or moved cells). The
  filter has to catch those through its residuals (ADR-0023).
- **Site:** the eNB. Sectors of one eNB share a clock (ADR-0022).
- **Height:** the table has antenna height above ground and no ground elevation, so the height
  is the session origin's plus the antenna's (flat ground, TBC). At kilometre ranges a 20 m
  error moves the range by centimetres.
- **Frame ambiguity:** a pseudorange is known only modulo one 10 ms frame (`meta.ambiguity_m`).
  Values are moved by whole frames to sit next to the last value of the same site, so sectors
  that wrapped differently can share one site clock, and a new arc continues the old one.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import msgspec
import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement

CELL_TABLE = Path(__file__).resolve().parents[3] / "data" / "reference" / "lte-cells-ottawa.csv"
MAX_RANGE_KM = 10.0  # the table's own radius; narrow it once a capture shows real link range (TBC)
# How far the receiver may be from the session origin, for collisions only (TBC: systems/ sets no
# mission extent). No registered eNB is matched in place of another while hearing range plus the
# receiver's distance from the origin is within MAX_RANGE_KM + TRAVEL_KM. One table radius; from
# Carleton it changes nothing, as every row is within 9.85 km (analysis/lte_table_audit.py).
TRAVEL_KM = 10.0
MATCHED, UNKNOWN, COLLISION, OUT_OF_RANGE = "matched", "unknown", "collision", "out_of_range"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cell:
    """One registered sector."""

    earfcn: int
    pci: int
    enb_id: int
    lat: float
    lon: float
    height_agl_m: float

    @property
    def site(self) -> str:
        return f"enb:{self.enb_id}"


class CellTable:
    """(EARFCN, PCI) -> registered sectors."""

    def __init__(self, cells: Iterable[Cell]):
        self._cells: dict[tuple[int, int], list[Cell]] = {}
        for c in cells:
            self._cells.setdefault((c.earfcn, c.pci), []).append(c)

    @classmethod
    def load(cls, path: str | Path | None = None) -> CellTable:
        path = Path(path) if path is not None else CELL_TABLE
        try:
            with open(path, newline="") as f:
                return cls(
                    Cell(
                        int(r["earfcn"]),
                        int(r["pci"]),
                        int(r["enb_id"]),
                        float(r["lat"]),
                        float(r["lon"]),
                        float(r["ant_height_agl_m"]),
                    )
                    for r in csv.DictReader(f)
                )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"{path} is missing: real LTE records need the cell table (#87, #110)"
            ) from None

    def associate(
        self,
        earfcn: int,
        pci: int,
        origin_llh: Sequence[float],
        max_range_km: float = MAX_RANGE_KM,
        travel_km: float = TRAVEL_KM,
    ) -> tuple[str, Cell | None]:
        """(status, cell); see the module docstring. A collision if two or more eNBs are within
        `max_range_km` + `travel_km` of the origin; else matched if one is within `max_range_km`,
        and the cell is its nearest sector."""
        cells = self._cells.get((earfcn, pci))
        if not cells:
            return UNKNOWN, None
        reach = (max_range_km + travel_km) * 1e3
        ranged = []
        for c in cells:
            d = float(np.linalg.norm(llh_to_enu([c.lat, c.lon, origin_llh[2]], origin_llh)[:2]))
            if d <= reach:
                ranged.append((d, c))
        if len({c.enb_id for _, c in ranged}) > 1:
            return COLLISION, None
        ranged = [(d, c) for d, c in ranged if d <= max_range_km * 1e3]
        if not ranged:
            return OUT_OF_RANGE, None
        return MATCHED, min(ranged, key=lambda item: item[0])[1]


def _parse(emitter: str) -> tuple[int, int] | None:
    """`lte:<earfcn>:<pci>` -> (earfcn, pci); None if the EARFCN is unknown (`lte::<pci>`)."""
    parts = emitter.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


def attach(
    measurements: Iterable[Measurement],
    origin_llh: Sequence[float] | None,
    table: CellTable | None = None,
    counts: Counter | None = None,
) -> Iterator[Measurement]:
    """Yield `measurements` with LTE records resolved to registered towers; see the module
    docstring. Records of unresolved cells are dropped and counted in `counts` (by status) and
    in a warning when the stream ends. The table is read only if a record needs it."""
    counts = Counter() if counts is None else counts
    resolved: dict[str, tuple[str, Cell | None]] = {}
    last: dict[str, float] = {}  # site -> last pseudorange, after alignment
    try:
        for m in measurements:
            if m.source != "lte" or "emitter_llh" in m.meta or "emitter_enu" in m.meta:
                yield m
                continue
            if origin_llh is None:
                raise ValueError("real LTE records need the session's origin_llh")
            if m.emitter not in resolved:
                if table is None:
                    table = CellTable.load()
                key = _parse(m.emitter)
                resolved[m.emitter] = (
                    (UNKNOWN, None) if key is None else table.associate(*key, origin_llh)
                )
            status, cell = resolved[m.emitter]
            if cell is None:
                counts[status] += 1
                continue
            counts[status] += 1
            llh = [cell.lat, cell.lon, float(origin_llh[2]) + cell.height_agl_m]
            meta = {**m.meta, "emitter_llh": llh, "site": cell.site}
            value = m.value
            frame = m.meta.get("ambiguity_m")
            if m.kind == "pseudorange" and frame:
                near = last.get(cell.site, m.value[0])
                aligned = m.value[0] + round((near - m.value[0]) / frame) * frame
                last[cell.site] = aligned
                value = (aligned, *m.value[1:])
            yield msgspec.structs.replace(m, meta=meta, value=value)
    finally:
        dropped = {s: n for s, n in sorted(counts.items()) if s != MATCHED}
        if dropped:
            log.warning("LTE cells: used %d records, dropped %s", counts[MATCHED], dropped)
