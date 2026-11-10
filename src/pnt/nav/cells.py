"""Real LTE records -> what the filter needs (ADR-0023, #121).

The LTE front end names a heard cell `lte:<earfcn>:<pci>` and knows nothing of where it is. This
step, between any `Source` and the estimators (ADR-0004), looks each cell up in the committed
table and adds `meta.emitter_llh` and `meta.site`. Records that already carry a position (the
simulator's) pass through untouched.

- **Association is a hypothesis.** An (EARFCN, PCI) maps to a registered eNB only if exactly one
  eNB in the whole table has it, and that eNB is within range of the origin. The lookup runs
  before the estimator and does not know where the receiver is: a receiver that has travelled
  from the origin can hear an eNB beyond the range, so any registered eNB on the PCI could be
  the one heard (#138). Unknown cells, collisions and cells out of range are left out and
  counted, never guessed: a wrong tower position is worse than one tower fewer. The mapper for
  those cells is not built. An eNB missing from the table can still be matched to one in it
  that reuses its PCI; the lookup cannot see that case.
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
    ) -> tuple[str, Cell | None]:
        """(status, cell). The cell is the nearest sector of the table's one eNB on this
        (EARFCN, PCI), when matched. OUT_OF_RANGE: no eNB on it within `max_range_km` of the
        origin. COLLISION: some are, and more than one eNB in the table uses it, wherever the
        others are, since the receiver need not be at the origin (#138)."""
        cells = self._cells.get((earfcn, pci))
        if not cells:
            return UNKNOWN, None
        ranged = []
        for c in cells:
            d = float(np.linalg.norm(llh_to_enu([c.lat, c.lon, origin_llh[2]], origin_llh)[:2]))
            if d <= max_range_km * 1e3:
                ranged.append((d, c))
        if not ranged:
            return OUT_OF_RANGE, None
        if len({c.enb_id for c in cells}) > 1:
            return COLLISION, None
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
