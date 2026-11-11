"""Which LTE cells a set of captures heard, and which registered eNB each could be (#87).

Runs the LTE front end on each `.cu8` capture and lists every cell it found: PCI, seconds
tracked, SNR, CFO, arcs. Each (EARFCN, PCI) is then looked up in the committed cell table
(`data/reference/lte-cells-ottawa.csv`, every registered sector within 10 km of Carleton):

- `unique`: one eNB in the table uses it. Still a hypothesis: an eNB more than 10 km from
  Carleton, or one missing from the registry, can use the same PCI.
- `collision`: more than one eNB in the table uses it; the receiver's position would be needed
  to choose, and none is given.
- `not in table`: no registered sector within 10 km uses it.

The distance from the receiver is given only with `--receiver-llh`; without it, "position
unknown". The table's own distance (from Carleton) is listed beside each eNB.

    python analysis/lte_scan_table.py data/sessions/<a>/sdr_a.cu8 [...] --out DIR
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.nav.cells import CELL_TABLE

TITLE = "LTE scan, 2026-11-10 captures (#87)"


def load_table(path: str | Path = CELL_TABLE) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def lookup(rows: list[dict], earfcn: int, pci: int, receiver_llh=None) -> dict:
    """The registered eNBs on (EARFCN, PCI): status and one entry per eNB (nearest sector to
    the receiver when its position is given, else the table's first)."""
    hits = [r for r in rows if int(r["earfcn"]) == earfcn and int(r["pci"]) == pci]
    enbs: dict[int, dict] = {}
    for r in hits:
        enb = int(r["enb_id"])
        d = None
        if receiver_llh is not None:
            e, n, _ = llh_to_enu((float(r["lat"]), float(r["lon"]), receiver_llh[2]), receiver_llh)
            d = float(np.hypot(e, n)) / 1e3
        cur = enbs.get(enb)
        if cur is None or (d is not None and d < cur["distance_km"]):
            enbs[enb] = {
                "enb_id": enb,
                "licensee": r["licensee"],
                "location": r["location"],
                "sectors": 0,
                "carleton_km": float(r["dist_km"]),
                "distance_km": d,
            }
    for r in hits:
        enbs[int(r["enb_id"])]["sectors"] += 1
    status = {0: "not in table", 1: "unique"}.get(len(enbs), "collision")
    return {"status": status, "enbs": sorted(enbs.values(), key=lambda x: x["carleton_km"])}


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def scan(capture: Path) -> dict:
    from pnt.frontends.lte import frontend, open_capture

    cap = open_capture(capture)
    res = frontend.process_capture(cap)
    cells = []
    for c in res.cells:
        cfo = -np.mean([e.nu for e in c.epochs]) * 1e6 if c.epochs else float("nan")
        cells.append(
            {
                "earfcn": c.earfcn,
                "pci": c.pci,
                "tracked_s": len(c.epochs) * 5 / 1000,  # 5 ms epochs, as frontend.summary
                "snr_db": float(c.snr_db),
                "cfo_ppm": None if np.isnan(cfo) else float(cfo),
                "arcs": c.arc + 1,
            }
        )
    return {
        "session": capture.parent.name,
        "earfcn": cap.segments[0].earfcn if cap.segments else None,
        "capture_s": res.capture_s,
        "cells": cells,
    }


def _ppm(x) -> str:
    return "" if x is None else f"{x:+.3f}"


def _km(x) -> str:
    return "position unknown" if x is None else f"{x:.2f}"


def table_md(
    scans: list[dict], rows: list[dict], receiver_llh, stamp: str, title: str = TITLE
) -> str:
    where = (
        "the receiver position is not given (`--receiver-llh`), so no distance from it is listed"
        if receiver_llh is None
        else "distances from the receiver use the position given with `--receiver-llh`"
    )
    out = [
        f"# {title}",
        "",
        f"`python analysis/lte_scan_table.py <captures> --out <dir>` at `{stamp}`, LTE front end "
        "on each `sdr_a.cu8`, cells looked up in `data/reference/lte-cells-ottawa.csv`. Real "
        f"sessions; {where}. A `unique` match is a hypothesis: eNBs beyond the table's 10 km "
        "can reuse a PCI.",
        "",
        "| Session | EARFCN | PCI | Tracked (s) | SNR (dB) | CFO (ppm) | Arcs | Table "
        "| eNB (sectors on this PCI) | Licensee | Location | km from Carleton "
        "| km from receiver |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scans:
        if not s["cells"]:
            out.append(
                f"| {s['session']} | {s['earfcn']} | none found in {s['capture_s']:.1f} s "
                "| | | | | | | | | | |"
            )
        for c in s["cells"]:
            m = lookup(rows, c["earfcn"], c["pci"], receiver_llh)
            enbs = m["enbs"] or [None]
            for i, e in enumerate(enbs):
                head = (
                    f"| {s['session']} | {c['earfcn']} | {c['pci']} | {c['tracked_s']:.1f} | "
                    f"{c['snr_db']:.1f} | {_ppm(c['cfo_ppm'])} | {c['arcs']} | {m['status']} "
                    if i == 0
                    else "| | | | | | | | "
                )
                if e is None:
                    out.append(head + "| | | | | |")
                else:
                    out.append(
                        head + f"| {e['enb_id']} ({e['sectors']}) | {e['licensee']} | "
                        f"{e['location']} | {e['carleton_km']:.2f} | {_km(e['distance_km'])} |"
                    )
    out += [
        "",
        "Tracked = number of 5 ms epochs × 5 ms; a cell found by the search but never tracked "
        "shows 0.0 s and no CFO. SNR is the front end's acquisition estimate.",
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("captures", nargs="+", help="sdr_a.cu8 files, each with its sidecar")
    p.add_argument("--receiver-llh", type=float, nargs=3, metavar=("LAT", "LON", "H"))
    p.add_argument("--out", default="analysis/results/lte-scan-20261110")
    p.add_argument("--title", default=TITLE, help="the summary's heading")
    a = p.parse_args()
    rows = load_table()
    scans = [scan(Path(c)) for c in a.captures]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = commit()
    (out / "summary.md").write_text(table_md(scans, rows, a.receiver_llh, stamp, a.title))
    for s in scans:
        for c in s["cells"]:
            c["table"] = lookup(rows, c["earfcn"], c["pci"], a.receiver_llh)
    (out / "summary.json").write_text(json.dumps({"commit": stamp, "scans": scans}, indent=2))
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
