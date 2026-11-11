"""LTE antenna A/B table: the same front end on each antenna run, side by side (#200).

Runs the LTE front end on each run's `sdr_a.cu8` and tabulates, per run: cells tracked, their
SNR, seconds tracked and arcs, plus the capture's level (RMS and clipped fraction, since the
runs used the dongle's auto gain). Then compares pairs of runs on the cells both tracked.

The run label is the token after `-ant-` in the session name (`...-ant-A1-uhf-chair` -> `A1`).

The SNR is the front end's tracking estimate (`CellTrack.snr_db`): an average over the epochs
that passed detection only. A cell near the detection threshold therefore reads at or just
above it whatever its true SNR, so such values are marked `floor` and their differences are
lower bounds at best.

    python analysis/antenna_ab_table.py data/sessions/<run> [...] --pair A1:A2 --out DIR
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

FLOOR_MARGIN_DB = 3.0  # display mark: SNR within this of the detection threshold reads `floor`


def detection_floor_db() -> float:
    """The detection threshold on the scale `CellTrack.snr_db` is printed on (per resource
    element): the tracker's post-correlation threshold over the 2 x 62 PSS/SSS gain."""
    from pnt.frontends.lte import Config
    from pnt.frontends.lte import signals as sig

    return Config().detect_snr_db - 10 * math.log10(2 * sig.N_SYNC)


def label(session: str) -> str:
    m = re.search(r"-ant-([^-]+)", session)
    return m.group(1) if m else session


def level(cu8: Path, chunk: int = 1 << 24) -> dict:
    """RMS (LSB about mid-scale) and the fraction of I/Q values at 0 or 255."""
    n = clip = 0
    ss = 0.0
    with open(cu8, "rb") as f:
        while b := f.read(chunk):
            x = np.frombuffer(b, dtype=np.uint8)
            n += x.size
            clip += int(np.count_nonzero((x == 0) | (x == 255)))
            ss += float(np.sum((x.astype(np.float64) - 127.5) ** 2))
    return {
        "rms_lsb": math.sqrt(ss / n) if n else float("nan"),
        "clip_frac": clip / n if n else 0.0,
    }


def cell_rows(res) -> list[dict]:
    """One dict per cell from a front-end `Result` (5 ms epochs, as `frontend.summary`)."""
    return [
        {
            "pci": c.pci,
            "earfcn": c.earfcn,
            "snr_db": float(c.snr_db),
            "tracked_s": len(c.epochs) * 5 / 1000,
            "arcs": c.arc + 1,
        }
        for c in res.cells
    ]


def run(session_dir: Path) -> dict:
    from pnt.frontends.lte import frontend, open_capture

    cu8 = session_dir / "sdr_a.cu8"
    cap = open_capture(cu8)
    res = frontend.process_capture(cap)
    side = json.loads(cu8.with_suffix(".json").read_text())
    return {
        "label": label(session_dir.name),
        "session": session_dir.name,
        "capture_s": res.capture_s,
        "gain_mode": side.get("gain_mode"),
        "gain_db": side.get("gain_db"),
        **level(cu8),
        "cells": cell_rows(res),
    }


def is_floor(snr_db: float, floor_db: float) -> bool:
    return not snr_db >= floor_db + FLOOR_MARGIN_DB


def per_run(r: dict, floor_db: float) -> dict:
    """Totals for one run: tracked cells, best SNR, seconds and arcs summed over cells."""
    cells = [c for c in r["cells"] if c["tracked_s"] > 0]
    best = max((c["snr_db"] for c in cells), default=float("nan"))
    return {
        "cells": len(cells),
        "best_snr_db": best,
        "best_is_floor": bool(cells) and is_floor(best, floor_db),
        "tracked_s": sum(c["tracked_s"] for c in cells),
        "arcs": sum(c["arcs"] for c in cells),
        "above_floor": sum(not is_floor(c["snr_db"], floor_db) for c in cells),
    }


def compare(a: dict, b: dict) -> list[dict]:
    """b minus a on each PCI both runs tracked."""
    ca = {c["pci"]: c for c in a["cells"] if c["tracked_s"] > 0}
    cb = {c["pci"]: c for c in b["cells"] if c["tracked_s"] > 0}
    return [
        {
            "pci": p,
            "d_snr_db": cb[p]["snr_db"] - ca[p]["snr_db"],
            "d_tracked_s": cb[p]["tracked_s"] - ca[p]["tracked_s"],
            "a": ca[p],
            "b": cb[p],
        }
        for p in sorted(set(ca) & set(cb))
    ]


def _snr(x: float, floor_db: float) -> str:
    return f"{x:.1f}" + (" floor" if is_floor(x, floor_db) else "")


def table_md(runs: list[dict], pairs: list[tuple[str, str]], floor_db: float, stamp: str) -> str:
    pcis = sorted({c["pci"] for r in runs for c in r["cells"] if c["tracked_s"] > 0})
    out = [
        "# LTE antenna A/B, 2026-11-10 (#200)",
        "",
        f"`python analysis/antenna_ab_table.py <runs> --out <dir>` at `{stamp}`: the LTE front "
        "end on each run's `sdr_a.cu8`. Real sessions, statistics only. SNR is the front end's "
        f"tracking estimate (dB per resource element). The detection threshold is {floor_db:.1f} "
        "dB on this scale; the estimate averages only epochs above it, so `floor` (within "
        f"{FLOOR_MARGIN_DB:g} dB of it, a display mark) means the cell was marginal and its true "
        "SNR may be lower.",
        "",
        "## Per run",
        "",
        "| Run | Session | Cells | Above floor | Best SNR (dB) | Tracked (s, all cells) | Arcs "
        "| Capture (s) | RMS (LSB) | Clipped (%) | Gain |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        s = per_run(r, floor_db)
        best = _snr(s["best_snr_db"], floor_db) if s["cells"] else "none"
        gain = r["gain_mode"] if r["gain_db"] is None else f"{r['gain_db']} dB"
        out.append(
            f"| {r['label']} | {r['session']} | {s['cells']} | {s['above_floor']} | {best} | "
            f"{s['tracked_s']:.1f} | {s['arcs']} | {r['capture_s']:.1f} | {r['rms_lsb']:.1f} | "
            f"{100 * r['clip_frac']:.3f} | {gain} |"
        )
    out += [
        "",
        "## Per cell: SNR (dB) / tracked (s) / arcs",
        "",
        "| Run | " + " | ".join(f"PCI {p}" for p in pcis) + " |",
        "|---|" + "---|" * len(pcis),
    ]
    for r in runs:
        by = {c["pci"]: c for c in r["cells"] if c["tracked_s"] > 0}
        row = [
            f"{_snr(by[p]['snr_db'], floor_db)} / {by[p]['tracked_s']:.1f} / {by[p]['arcs']}"
            if p in by
            else "-"
            for p in pcis
        ]
        out.append(f"| {r['label']} | " + " | ".join(row) + " |")
    if pairs:
        out += [
            "",
            "## Pairs (second minus first, on cells both tracked)",
            "",
            "| Pair | PCI | SNR first -> second (dB) | ΔSNR (dB) | Δtracked (s) |",
            "|---|---|---|---|---|",
        ]
        by_label = {r["label"]: r for r in runs}
        for a, b in pairs:
            if a not in by_label or b not in by_label:
                continue
            d = compare(by_label[a], by_label[b])
            if not d:
                out.append(f"| {a} -> {b} | no cell in common | | | |")
            for x in d:
                out.append(
                    f"| {a} -> {b} | {x['pci']} | {_snr(x['a']['snr_db'], floor_db)} -> "
                    f"{_snr(x['b']['snr_db'], floor_db)} | {x['d_snr_db']:+.1f} | "
                    f"{x['d_tracked_s']:+.1f} |"
                )
    return "\n".join(out) + "\n"


_SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]  # fixed order
_MARKERS = ["o", "s", "^", "D", "v", "P"]


def plot(runs: list[dict], floor_db: float, stamp: str, path: Path) -> None:
    """SNR of each tracked cell per run, one series per PCI, with the detection floor."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pcis = sorted({c["pci"] for r in runs for c in r["cells"] if c["tracked_s"] > 0})
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ax.axhspan(-30, floor_db + FLOOR_MARGIN_DB, color="#e4e3dd", lw=0)
    ax.axhline(floor_db, color="#8a8980", lw=1, ls="--")
    offs = np.linspace(-0.15, 0.15, max(len(pcis), 1))
    for i, p in enumerate(pcis):
        xs, ys, ss = [], [], []
        for j, r in enumerate(runs):
            for c in r["cells"]:
                if c["pci"] == p and c["tracked_s"] > 0:
                    xs.append(j + offs[i])
                    ys.append(c["snr_db"])
                    ss.append(20 + 2 * c["tracked_s"])
        ax.scatter(xs, ys, s=ss, color=_SERIES[i % len(_SERIES)], marker=_MARKERS[i % 6],
                   edgecolor="#fcfcfb", lw=1.5, label=f"PCI {p}", zorder=3)  # fmt: skip
    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels([r["session"].split("-ant-", 1)[-1] for r in runs], rotation=25,
                       ha="right", fontsize=8)  # fmt: skip
    ax.set_xlim(-0.5, len(runs) - 0.5)
    ax.set_ylim(floor_db - 2, 18)
    ax.set_ylabel("tracking SNR (dB per RE)")
    note = (
        f"dashed: detection threshold ({floor_db:.1f} dB); shaded: within {FLOOR_MARGIN_DB:g} dB"
    )
    ax.set_xlabel(note + " of it (marginal)", fontsize=8, color="#55544e")
    ax.grid(axis="y", color="#e4e3dd", lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(title="cell (EARFCN 2460); area = s tracked", fontsize=8, title_fontsize=8,
              frameon=False, loc="upper right")  # fmt: skip
    ax.set_title(f"LTE antenna A/B, real sessions 2026-11-10, commit {stamp}", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("runs", nargs="+", help="session folders, each with sdr_a.cu8 + sidecar")
    p.add_argument("--pair", action="append", default=[], metavar="A:B", help="compare B to A")
    p.add_argument("--out", default="analysis/results/antenna-ab-20261110")
    a = p.parse_args()
    runs = [run(Path(d)) for d in a.runs]
    pairs = [tuple(x.split(":", 1)) for x in a.pair]
    floor_db = detection_floor_db()
    stamp = commit()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(table_md(runs, pairs, floor_db, stamp))
    summary = {"commit": stamp, "floor_db": floor_db, "pairs": pairs, "runs": runs}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    plot(runs, floor_db, stamp, out / "snr_per_run.png")
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
