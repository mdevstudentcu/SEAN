"""Weak LTE cells sliding inside one arc (#214): range error against GPS truth, before and after.

    python analysis/weak_cell_wander.py <session> --lte LABEL=DIR [LABEL=DIR ...] [--static]
        [--out FILE.md]

Needs `analysis/walk_gps_cut.py` (#214, #299) beside it, as `real_walk_lte.py` does.

Each `--lte` is a session the LTE front end wrote from the same capture (`pnt frontend lte`), e.g.
one at origin/main and one with a change. Per record, the range error is

    e = pseudorange - |truth - tower| - dongle clock

with truth the good GPS fixes (`walk_gps_cut.truth`), linear between fixes (`--static`: their
mean), and the dongle clock from a GPS-on `ekf` replay of that session (`real_walk_lte`): each
session's own, because the sample gaps the front end finds step the dongle's timing and can
differ between front ends. Each arc's median is removed (ADR-0050 gives every arc its own bias),
wrapped to the 10 ms frame.

Reported per session: |e| by SNR bin; the structure function sqrt(mean (e(t + tau) - e(t))^2 / 2)
of the 1 s means within one arc, per cell and pooled, at 1, 10 and 100 s; records, and arcs per
minute of capture (all cells together).

Privacy: errors, counts, SNR and cell names only. No position, track, origin, range or bearing.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import real_walk_lte as R  # noqa: E402
import walk_gps_cut as W  # noqa: E402

from pnt.core.frames import emitter_enu  # noqa: E402
from pnt.nav import cells  # noqa: E402

C = 299_792_458.0
FRAME_M = C * 0.010  # pseudorange ambiguity (meta.ambiguity_m)
TAUS = (1, 10, 100)  # s
SNR_BINS = (-99.0, -10.0, -8.0, -6.0, -3.0, 0.0, 99.0)  # dB per resource element
MIN_PAIRS = 20  # fewer differences than this: no structure function value


def errors(raw: str, lte: str, clk: np.ndarray, static: bool) -> dict:
    """Per pseudorange record of `lte`: time, cell, arc, SNR, error less its arc's median."""
    d, lt = W.load(raw), W.load(lte)
    tr = W.truth(raw, W.HDOP_MAX, W.MIN_SATS)
    recs = [
        m
        for m in cells.attach([m for m in lt["meas"] if m.source == "lte"], d["origin"])
        if m.kind == "pseudorange"
    ]
    t = np.array([m.t_ns for m in recs], dtype=np.int64)
    if static:
        pos, ok = np.tile(tr["pos"].mean(axis=0), (len(t), 1)), np.ones(len(t), bool)
    else:
        pos, ok = W.interpolate(tr["t"], tr["pos"], t)
    rx = np.interp(t, clk[:, 0], clk[:, 1])
    z = np.full(len(recs), np.nan)
    emit: dict = {}
    for i, m in enumerate(recs):
        if ok[i] and ("emitter_llh" in m.meta or "emitter_enu" in m.meta):
            e = emit.setdefault(m.emitter, emitter_enu(m.meta, d["origin"]))
            z[i] = m.value[0] - float(np.linalg.norm(pos[i] - e)) - rx[i]
    cell = np.array([m.emitter for m in recs])
    arc = np.array([m.meta.get("arc", 0) for m in recs])
    snr = np.array([m.meta.get("snr_db", np.nan) for m in recs], dtype=float)
    r = np.full(len(recs), np.nan)
    for c in np.unique(cell):
        for a in np.unique(arc[cell == c]):
            q = (cell == c) & (arc == a) & np.isfinite(z)
            if q.sum() < 5:
                continue
            w = ((z[q] - z[q][0] + FRAME_M / 2) % FRAME_M) - FRAME_M / 2
            r[q] = w - np.median(w)
    span_s = (t.max() - t.min()) / 1e9 if len(t) else math.nan
    return {"t": t, "t0": d["t0"], "cell": cell, "arc": arc, "snr": snr, "r": r, "span_s": span_s}


def structure(e: dict, cell: str | None = None) -> dict[int, float]:
    """RMS structure function of the 1 s means within one arc, at each lag in TAUS."""
    sec = (e["t"] - e["t0"]) // 1_000_000_000
    dif: dict[int, list] = {x: [] for x in TAUS}
    for c in [cell] if cell else np.unique(e["cell"]):
        s = (e["cell"] == c) & np.isfinite(e["r"])
        for a in np.unique(e["arc"][s]):
            q = s & (e["arc"] == a)
            u, inv = np.unique(sec[q], return_inverse=True)
            means = np.bincount(inv, e["r"][q]) / np.bincount(inv)
            mean = dict(zip(u.tolist(), means, strict=True))
            for x in TAUS:
                dif[x] += [mean[k + x] - v for k, v in mean.items() if k + x in mean]
    return {
        x: math.sqrt(np.mean(np.square(v)) / 2) if len(v) >= MIN_PAIRS else math.nan
        for x, v in dif.items()
    }


def _f(x: float) -> str:
    return "–" if x != x else f"{x:,.0f}"


def report(name: str, runs: dict[str, dict]) -> str:
    labels = list(runs)
    out = [f"# Weak-cell wander on `{name}` (#214)", ""]
    out += [
        "## Records and arcs",
        "",
        "| LTE session | Records | Cells | Arcs | Arcs per minute |",
        "|---|---|---|---|---|",
    ]
    for k, e in runs.items():
        n_arcs = sum(len(np.unique(e["arc"][e["cell"] == c])) for c in np.unique(e["cell"]))
        out.append(f"| {k} | {len(e['t'])} | {len(np.unique(e['cell']))} | {n_arcs} | "
                   f"{n_arcs / (e['span_s'] / 60):.2f} |")  # fmt: skip
    out += [
        "",
        "## |error| by SNR (m), arc median removed: records, p50 / p95",
        "",
        "| SNR (dB) | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]
    for lo, hi in zip(SNR_BINS[:-1], SNR_BINS[1:], strict=True):
        row = []
        for e in runs.values():
            q = (e["snr"] >= lo) & (e["snr"] < hi) & np.isfinite(e["r"])
            a = np.abs(e["r"][q])
            row.append(f"{q.sum()}: {_f(np.median(a))} / {_f(np.percentile(a, 95))}"
                       if q.any() else "–")  # fmt: skip
        out.append(f"| {lo:g} to {hi:g} | " + " | ".join(row) + " |")
    out += ["", "## Structure function within one arc (m), " + " / ".join(labels), "",
            "| Cell | SNR p50 (dB) | " + " | ".join(f"{x} s" for x in TAUS) + " |",
            "|---|---|" + "---|" * len(TAUS)]  # fmt: skip
    first = runs[labels[0]]
    names = sorted(set().union(*(set(e["cell"]) for e in runs.values())),
                   key=lambda c: -np.sum(first["cell"] == c))  # fmt: skip
    for c in [*names, None]:
        sfs = [structure(e, c) if c is None or c in set(e["cell"]) else {} for e in runs.values()]
        mine = first["cell"] == c
        snr = np.nanmedian(first["snr"][mine]) if mine.any() else math.nan
        cols = [" / ".join(_f(s.get(x, math.nan)) for s in sfs) for x in TAUS]
        label = f"`{c}`" if c else "all cells"
        out.append(f"| {label} | {'' if c is None else f'{snr:.1f}'} | " + " | ".join(cols) + " |")
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--lte", nargs="+", required=True, help="LABEL=DIR")
    ap.add_argument("--static", action="store_true", help="truth: the mean of the good fixes")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    raw = str(W.resolve(args.session))
    pairs = [x.split("=", 1) for x in args.lte]
    runs = {k: errors(raw, v, R.gps_on_replay(raw, v)[1], args.static) for k, v in pairs}
    text = report(Path(raw).name, runs)
    print(text)
    if args.out:
        Path(args.out).write_text(text)


if __name__ == "__main__":
    main()
