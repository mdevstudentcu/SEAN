"""Which real LTE cells a recorded session heard, and the ISED-registered site each fits (#28).

    python deploy/demo/cells.py data/sessions/<name>-lte

Reads the `/meas/lte` records that `pnt frontend lte` wrote and, for each cell heard, prints how
often the front end tracked it, its signal-to-noise ratio and the reported range sigma, then the
registered site it is consistent with under the same rule the estimators use (`pnt.nav.cells`,
ADR-0023). A match is a hypothesis, not an identification: see the next paragraph.
No position is computed: the real sessions recorded so far have no GPS fix, so no origin and no
first fix for the filter.

The registry match needs a point the receiver is within `MAX_RANGE_KM` of. A session without an
origin is matched around `--near` (default: the repo's Carleton session origin), which says only
that the capture was made in Ottawa; it is not the receiver's position.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import string
from collections import defaultdict

from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.nav.cells import CELL_TABLE, MATCHED, CellTable

CARLETON = (45.3876, -75.6960, 70.0)  # the committed scenarios' session origin


def registry_rows() -> dict[tuple[int, int, int], dict]:
    """(earfcn, pci, enb_id) -> the table row, for the licensee and site name."""
    with open(CELL_TABLE, newline="") as f:
        return {(int(r["earfcn"]), int(r["pci"]), int(r["enb_id"])): r for r in csv.DictReader(f)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", help="session folder or .mcap with /meas/lte records")
    p.add_argument("--near", help="lat,lon,h to match around (default: the session origin, "
                   "else Carleton)")  # fmt: skip
    args = p.parse_args()

    meta = session.read_meta(args.session)
    if args.near:
        near, why = tuple(float(v) for v in args.near.split(",")), "--near"
    elif meta.get("origin_llh"):
        near, why = tuple(meta["origin_llh"]), "the session origin"
    else:
        near, why = CARLETON, "Carleton (the session has no origin; Ottawa capture)"

    by_cell: dict[str, list] = defaultdict(list)
    t = []
    for _, m in read_session(session.mcap_path(args.session), topics=["/meas/lte"]):
        if m.kind == "pseudorange":
            by_cell[m.emitter].append(m)
            t.append(m.t_ns)
    name = session.session_name(args.session)
    if not t:
        raise SystemExit(f"{name}: no LTE pseudoranges (run `pnt frontend lte` on its capture)")
    span = (max(t) - min(t)) / 1e9

    table, rows = CellTable.load(), registry_rows()
    print(f"session {name} (commit {meta.get('commit') or '?'}, real capture, "
          f"{len(by_cell)} cells over {span:.0f} s)")  # fmt: skip
    print(f"registry match around {why}\n")
    print(f"{'cell':<15} {'records':>7} {'per s':>6} {'SNR dB':>7} {'sigma m':>8}  registry")
    for cell, ms in sorted(by_cell.items(), key=lambda kv: -len(kv[1])):
        _, earfcn, pci = cell.split(":")
        status, c = table.associate(int(earfcn), int(pci), near)
        if status == MATCHED:
            r = rows[(c.earfcn, c.pci, c.enb_id)]
            reg = f"eNB {c.enb_id}, {r['licensee'].split()[0]}, {string.capwords(r['location'])}"
        else:
            reg = f"not matched ({status})"
        snr = statistics.median(m.meta["snr_db"] for m in ms)
        sig = statistics.median(m.sigma[0] for m in ms)
        print(f"{cell:<15} {len(ms):>7} {len(ms) / span:>6.1f} {snr:>7.1f} {sig:>8.1f}  {reg}")


if __name__ == "__main__":
    main()
