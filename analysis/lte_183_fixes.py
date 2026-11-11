"""What the #183 front-end fixes do on real LTE captures: per-cell stats, before against after.

    # once per front end, that front end's src first on PYTHONPATH (<main> a worktree at main)
    PYTHONPATH=<main>/src python analysis/lte_183_fixes.py run <sdr_a.cu8>... --out <before>
    PYTHONPATH=src python analysis/lte_183_fixes.py run <sdr_a.cu8>... --out <after>
    python analysis/lte_183_fixes.py compare <before> <after> --out analysis/results/lte-183-fixes

`run` writes one JSON per capture (named after its session folder). Per cell: the median SNR of
its 10 Hz records, the mean carrier offset of its 5 ms epochs, the code rate (slope of the
measured frame boundary against the sample index, per arc of at least 1 s, weighted by length),
5 ms epochs tracked, those at SNR >= -8 dB per resource element, arcs, and each arc-to-arc
timing jump (the new arc's first boundary against the old arc's last, extrapolated at its rate,
wrapped to one half-frame). The code rate is the dongle's sample clock (tower clock errors are
ppb), and the tuner shares the crystal, so a right carrier offset has -CFO/fc equal to it within
the towers' 0.05 ppm (TS 36.104) plus Doppler (0 at rest).

Reads only what the front end derives from PSS and SSS (REQ-08). Writes no position, distance or
bearing: the captures carry no fix in the front end's output, and none is computed here.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

OFF_PPM = 0.1  # TBC: a CFO is "off" if -CFO/fc misses the code rate by more than this
GOOD_SNR_DB = -8.0  # TBC: the white-sigma fit's lower edge (ADR-0036)


def cell_stats(path: str) -> dict:
    from pnt.frontends.lte import process_file
    from pnt.frontends.lte import signals as sig

    r = process_file(path)
    fs = 1.92e6
    L = sig.half_frame_length(fs)
    rows = []
    for c in r.cells:
        ep = sorted(c.epochs, key=lambda e: (e.arc, e.k))
        cfo, arcs, code_ppm, jumps = float("nan"), [], float("nan"), []
        if ep:
            cfo = -float(np.mean([e.nu for e in ep])) * c.fc
            arcs = sorted({e.arc for e in ep})
            rates, wts, prev = [], [], None
            for a in arcs:
                ea = [e for e in ep if e.arc == a]
                n = np.array([e.n0 + e.k * L for e in ea])
                th = np.array([e.theta_meas for e in ea])
                if len(ea) >= 200:
                    rates.append(np.polyfit(n, th, 1)[0])
                    wts.append(len(ea))
                if prev is not None:
                    pn, pth, pnu = prev
                    pred = pn + pth + (1 + pnu) * (n[0] - pn)
                    d = ((n[0] + th[0]) - pred) % (2 * L)
                    jumps.append(((d + L) % (2 * L) - L) / fs * 1e6)  # µs
                prev = (n[-1], th[-1], ea[-1].nu)
            if rates:
                code_ppm = float(np.average(rates, weights=wts)) * 1e6
        em = f"lte:{c.earfcn}:{c.pci}"
        snr = [
            m.meta["snr_db"] for m in r.measurements if m.emitter == em and m.kind == "pseudorange"
        ]
        # per resource element; front ends before #183 combine 124 elements
        good = sum(
            e.snr_post / getattr(e, "n_sync", 124.0) >= 10 ** (GOOD_SNR_DB / 10) for e in ep
        )
        rows.append(
            {
                "emitter": em,
                "snr_db": round(float(np.median(snr)), 1) if snr else float("nan"),
                "cfo_hz": round(cfo, 1),
                "cfo_ppm": round(cfo / c.fc * 1e6, 3),
                "code_rate_ppm": round(code_ppm, 3),
                "tracked_s": round(len(ep) * 0.005, 1),
                "good_s": round(0.005 * good, 1),
                "arcs": len(arcs),
                "jumps_us": [round(j, 2) for j in jumps],
            }
        )
    found: dict[int, list[float]] = {}
    for _, f in r.found:
        found.setdefault(f.pci, []).append(f.snr_db)
    return {
        "capture_s": round(r.capture_s, 1),
        "cells": rows,
        "found": {k: (len(v), float(np.median(v))) for k, v in found.items()},
        "gaps": [(g.at, g.n, g.ambiguous) for g in r.gaps],
    }


def summ(r: dict) -> dict:
    cells = [c for c in r["cells"] if c["tracked_s"] > 0]
    jumps = [abs(j) for c in cells for j in c["jumps_us"]]
    off = [
        c
        for c in cells
        if not math.isnan(c["code_rate_ppm"]) and abs(c["cfo_ppm"] + c["code_rate_ppm"]) > OFF_PPM
    ]
    return {
        "found": len(r["found"]),
        "tracked": len(cells),
        "sec": sum(c["tracked_s"] for c in cells),
        "good": sum(c["good_s"] for c in cells),
        "arcs": sum(c["arcs"] for c in cells),
        "jumps": len(jumps),
        "jmed": float(np.median(jumps)) if jumps else float("nan"),
        "off": len(off),
        "cap": r["capture_s"],
    }


def compare(before: Path, after: Path, out: Path) -> None:
    names = sorted(p.stem for p in before.glob("*.json"))
    load = lambda d, n: json.loads((d / f"{n}.json").read_text())  # noqa: E731
    rows = [
        "| Session | IQ (s) | Cells found | Cells tracked | Seconds tracked "
        "| of which SNR ≥ −8 dB | Arcs | Re-find jumps, median \\|jump\\| (µs) "
        "| CFO off the code rate (> 0.1 ppm) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    keys = ("found", "tracked", "sec", "good", "arcs", "jumps", "off")
    tot = {k: [0.0, 0.0] for k in keys}
    for n in names:
        b, a = summ(load(before, n)), summ(load(after, n))
        for k in keys:
            tot[k][0] += b[k]
            tot[k][1] += a[k]
        jm = lambda s: "–" if math.isnan(s["jmed"]) else f"{s['jmed']:.1f}"  # noqa: E731

        def f(k, fmt="{:g}", b=b, a=a):
            return f"{fmt.format(b[k])} → {fmt.format(a[k])}"

        jumps = f"{b['jumps']}, {jm(b)} → {a['jumps']}, {jm(a)}"
        rows.append(
            f"| {n} | {b['cap']:.0f} | {f('found')} | {f('tracked')} | {f('sec', '{:.1f}')} | "
            f"{f('good', '{:.1f}')} | {f('arcs')} | {jumps} | {f('off')} |"
        )
    t = {k: f"{v[0]:g} → {v[1]:g}" for k, v in tot.items()}
    t["sec"] = f"{tot['sec'][0]:.1f} → {tot['sec'][1]:.1f}"
    t["good"] = f"{tot['good'][0]:.1f} → {tot['good'][1]:.1f}"
    rows.append(
        f"| **all {len(names)}** | | {t['found']} | {t['tracked']} | {t['sec']} | {t['good']} | "
        f"{t['arcs']} | {t['jumps']} | {t['off']} |"
    )
    cell_rows = [
        "| Session | Cell | SNR (dB) | Tracked (s) | SNR ≥ −8 dB (s) | Arcs | CFO (ppm) "
        "| Code rate (ppm) | −CFO/fc − code (ppm) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    cells = []
    fields = ("snr_db", "cfo_ppm", "code_rate_ppm", "tracked_s", "good_s", "arcs")
    for n in names:
        rb, ra = load(before, n), load(after, n)
        for e in sorted({c["emitter"] for c in rb["cells"]} | {c["emitter"] for c in ra["cells"]}):
            cb = next((c for c in rb["cells"] if c["emitter"] == e), None)
            ca = next((c for c in ra["cells"] if c["emitter"] == e), None)

            def g(c, k, fmt):
                v = None if c is None else c[k]
                return (
                    "–" if v is None or (isinstance(v, float) and math.isnan(v)) else fmt.format(v)
                )

            def d(c):
                if c is None or math.isnan(c["code_rate_ppm"]) or math.isnan(c["cfo_ppm"]):
                    return "–"
                return f"{-c['cfo_ppm'] - c['code_rate_ppm']:+.3f}"

            cell_rows.append(
                f"| {n} | {e} | {g(cb, 'snr_db', '{:.1f}')} → {g(ca, 'snr_db', '{:.1f}')} | "
                f"{g(cb, 'tracked_s', '{:.1f}')} → {g(ca, 'tracked_s', '{:.1f}')} | "
                f"{g(cb, 'good_s', '{:.1f}')} → {g(ca, 'good_s', '{:.1f}')} | "
                f"{g(cb, 'arcs', '{}')} → {g(ca, 'arcs', '{}')} | "
                f"{g(cb, 'cfo_ppm', '{:+.3f}')} → {g(ca, 'cfo_ppm', '{:+.3f}')} | "
                f"{g(cb, 'code_rate_ppm', '{:+.3f}')} → {g(ca, 'code_rate_ppm', '{:+.3f}')} | "
                f"{d(cb)} → {d(ca)} |"
            )
            cells.append(
                {
                    "session": n,
                    "emitter": e,
                    "before": {k: cb[k] for k in fields} if cb else None,
                    "after": {k: ca[k] for k in fields} if ca else None,
                }
            )
    out.mkdir(parents=True, exist_ok=True)
    (out / "table.md").write_text("\n".join(rows) + "\n\n" + "\n".join(cell_rows) + "\n")
    sessions = {n: {"before": summ(load(before, n)), "after": summ(load(after, n))} for n in names}
    (out / "cells.json").write_text(json.dumps({"sessions": sessions, "cells": cells}, indent=1))
    figure(cells, out / "before_after.png")
    print("\n".join(rows))


def figure(cells: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, grid, before_c, after_c = "#52514e", "#e4e3df", "#eb6834", "#2a78d6"
    short = {
        "20261110-1305-lte-outside": "1305",
        "20261110-lte-outside-5145": "5145",
        "20261110-lte-outside-5255": "5255",
        "20261111-0040-static-fullsuite": "fullsuite",
        "20261111-0151-static-fullsuite2": "fullsuite2",
        "20261111-0233-static-lte-1h": "lte-1h",
    }

    def lab(c):
        s = short.get(c["session"], "ant-" + c["session"].split("-static-ant-")[-1].split("-")[0])
        return f"{s}  {c['emitter'].split(':', 1)[1]}"

    def val(c, w, k):
        x = c[w]
        if x is None:
            return float("nan")
        if k == "res":
            return -x["cfo_ppm"] - x["code_rate_ppm"]
        return float(x[k])

    y = np.arange(len(cells))[::-1]
    fig, ax = plt.subplots(1, 3, figsize=(13, 0.28 * len(cells) + 1.6), sharey=True)
    panels = [
        ("good_s", "Seconds tracked at SNR ≥ −8 dB"),
        ("arcs", "Arcs (log)"),
        ("res", "−CFO/fc − code rate (ppm)"),
    ]
    for a, (k, title) in zip(ax, panels, strict=True):
        for c, yy in zip(cells, y, strict=True):
            b, f = val(c, "before", k), val(c, "after", k)
            if k == "res":
                b, f = float(np.clip(b, -1.0, 1.0)), float(np.clip(f, -1.0, 1.0))
            if not (math.isnan(b) or math.isnan(f)):
                a.plot([b, f], [yy, yy], color=grid, lw=2, zorder=1)
        for w, col, name in (
            ("before", before_c, "origin/main"),
            ("after", after_c, "#183 branch"),
        ):
            v = np.array([val(c, w, k) for c in cells])
            if k == "res":  # off-scale values sit on the edge, labelled
                for x, yy in zip(v, y, strict=True):
                    if abs(x) > 1.0:
                        a.annotate(
                            f"{x:+.1f}",
                            (math.copysign(1.0, x), yy),
                            xytext=(-4, 4),
                            textcoords="offset points",
                            ha="right",
                            fontsize=7,
                            color=ink,
                        )
                v = np.clip(v, -1.0, 1.0)
            a.scatter(
                v, y, s=28, color=col, zorder=3, label=name, edgecolors="white", linewidths=0.8
            )
        if k == "res":
            a.axvspan(-OFF_PPM, OFF_PPM, color="#f3f2ee", zorder=0)
            a.set_xlim(-1.05, 1.05)
        if k == "arcs":
            a.set_xscale("log")
        a.set_title(title, color=ink, fontsize=10, loc="left")
        a.grid(axis="x", color=grid, lw=0.8)
        a.set_axisbelow(True)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            a.spines[sp].set_color(grid)
        a.tick_params(colors=ink, labelsize=8)
    ax[0].set_yticks(y, [lab(c) for c in cells], fontsize=7.5)
    ax[0].legend(loc="lower right", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("captures", nargs="+")
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("before", type=Path)
    c.add_argument("after", type=Path)
    c.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.cmd == "run":
        a.out.mkdir(parents=True, exist_ok=True)
        for cap in a.captures:
            res = cell_stats(cap)
            (a.out / f"{Path(cap).parent.name}.json").write_text(json.dumps(res))
            print(
                Path(cap).parent.name,
                [(x["emitter"], x["tracked_s"], x["arcs"]) for x in res["cells"]],
            )
    else:
        compare(a.before, a.after, a.out)


if __name__ == "__main__":
    main()
