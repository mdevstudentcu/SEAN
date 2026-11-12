"""Why the LTE filters do or do not help on a real static session with GPS cut (#256).

    python analysis/real_replay_diagnose.py <session>-lte [--cuts 99 149 199 249 299]
        --out analysis/results/real-replay-256/<session>/diagnosis.json

Truth is the mean of the session's GPS fixes (a static receiver). Reads the records after
`pnt frontend lte` and reports, as relative numbers only (no position, range or bearing):

- cells: records, arcs, SNR, the sigma the filter retells (ADR-0050) and the front end's own;
- geometry: the share of seconds with at least 3 cells heard (a 2-D fix with our clock unknown
  needs 3) and the HDOP of those seconds, over the session and over 300 s after each cut;
- consistency: double differences against the most-heard cell (our clock cancels), each a
  pseudorange minus its distance from truth, in 0.1 s bins, per pair of arcs overlapping
  >= `MIN_SEGMENT_S`: spread, slope (m/s) and wander (max - min);
- arc restarts: time, the gap before it, `sample_gap`, whether another cell restarted within
  `COMMON_S` (a common step: our timing, not the cell), and the step net of the cell's in-arc
  rate with whole frames wrapped out;
- per filter and cut: its horizontal speed 30 to 300 s after the cut (truth: 0) and, for the
  learned-noise filters, the range sigma each cell has learned at the end of the run.

Uses `analysis/real_gps_cut.py`'s loading, cut, variants and rows. Replay of a real session.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from pnt import nav
from pnt.core.measurement import Measurement
from pnt.nav import cells as cell_table
from pnt.nav import ekf as ekf_module
from pnt.nav import told_sigma

HERE = Path(__file__).resolve().parent
BIN_S = 0.1  # s: double differences are formed in bins of one 10 Hz record
MIN_SEGMENT_S = 20.0  # s: shortest overlap of two arcs that is scored
COMMON_S = 1.5  # s: restarts of two cells this close together count as one common step
ROWS = ("ekf", "ekf-learned-noise", "ekf-honest", "ekf-as-told")


def cut_module():
    spec = importlib.util.spec_from_file_location("real_gps_cut", HERE / "real_gps_cut.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hdop_2d(los: list[np.ndarray]) -> float:
    """HDOP of horizontal unit lines of sight with one clock unknown; inf below 3 or singular."""
    if len(los) < 3:
        return math.inf
    G = np.array([[u[0], u[1], 1.0] for u in los])
    try:
        Q = np.linalg.inv(G.T @ G)
    except np.linalg.LinAlgError:
        return math.inf
    return float(np.sqrt(Q[0, 0] + Q[1, 1]))


def dd_segments(
    res: dict[str, dict[int, tuple[float, object]]], ref: str, ambiguity_m: float | None
) -> list[dict]:
    """Double differences against `ref`: `res[cell][bin] = (residual m, arc)`. One entry per pair
    of arcs (the cell's, ref's) sharing at least `MIN_SEGMENT_S` of bins, with whole frames
    unwrapped inside the pair."""
    out = []
    min_bins = round(MIN_SEGMENT_S / BIN_S)
    for cell, bins in res.items():
        if cell == ref:
            continue
        seg: dict[tuple, list] = defaultdict(list)
        for b, (v, arc) in sorted(bins.items()):
            if b in res[ref]:
                rv, rarc = res[ref][b]
                seg[(arc, rarc)].append((b * BIN_S, v - rv))
        for arcs, pts in seg.items():
            if len(pts) < min_bins:
                continue
            t, d = np.array(pts, dtype=float).T
            if ambiguity_m:
                d = (d - d[0] + ambiguity_m / 2) % ambiguity_m - ambiguity_m / 2 + d[0]
            line = np.polyfit(t - t[0], d, 1)
            out.append({
                "cell": cell,
                "arcs": [str(a) for a in arcs],
                "from_s": float(t[0]),
                "to_s": float(t[-1]),
                "std_m": float(np.std(d)),
                "slope_m_s": float(line[0]),
                "wander_m": float(np.ptp(d)),
                "std_about_line_m": float(np.std(d - np.polyval(line, t - t[0]))),
            })  # fmt: skip
    return out


def arc_restarts(lte: list[Measurement], t0: int) -> list[dict]:
    """Each new arc of a cell already seen: when, after what gap, flagged `sample_gap` or not,
    shared with another cell's restart within `COMMON_S`, and its step from the cell's last
    record net of the cell's median in-arc rate times the gap (whole frames wrapped out)."""
    by: dict[str, list[Measurement]] = defaultdict(list)
    for m in lte:
        by[m.emitter].append(m)
    out = []
    for cell, recs in by.items():
        recs.sort(key=lambda m: m.t_ns)
        pairs = list(zip(recs, recs[1:], strict=False))
        rates = [(b.value[0] - a.value[0]) / ((b.t_ns - a.t_ns) / 1e9) for a, b in pairs
                 if a.meta.get("arc") == b.meta.get("arc") and b.t_ns > a.t_ns]  # fmt: skip
        rate = float(np.median(rates)) if rates else 0.0
        for a, b in pairs:
            if a.meta.get("arc") == b.meta.get("arc"):
                continue
            gap = (b.t_ns - a.t_ns) / 1e9
            step = b.value[0] - a.value[0] - rate * gap
            amb = b.meta.get("ambiguity_m")
            if amb:
                step = (step + amb / 2) % amb - amb / 2
            out.append({
                "t_s": (b.t_ns - t0) / 1e9,
                "cell": cell,
                "gap_s": gap,
                "sample_gap": "sample_gap" in (b.meta.get("flags") or []),
                "step_m": float(step),
            })  # fmt: skip
    out.sort(key=lambda r: r["t_s"])
    for r in out:
        r["common"] = any(
            o["cell"] != r["cell"] and abs(o["t_s"] - r["t_s"]) <= COMMON_S for o in out
        )
    return out


def learned_sigma(ekf, m: Measurement) -> float | None:
    """The range sigma `ekf` has learned for `m`'s cell (prior and samples), None if it learns
    none. Without the record's own sigma or floor, unlike `range_variance`."""
    acc = getattr(ekf, "_noise", {}).get(m.emitter)
    if not ekf.noise_tau_ns or acc is None:
        return None
    if ekf._sigma_model(m):
        m = told_sigma.retold(m, ekf._sigma_model(m))
    var = (ekf.noise_prior_variance(m) + acc[2]) / (1.0 + acc[1])
    return float(math.sqrt(var)) if var > 0 else None


def diagnose(path: str, cuts: list[float], rows=ROWS) -> dict:
    cut = cut_module()
    meas, t0, origin = cut.load(path)
    fix_t, fix_pos = cut.gps_fixes(meas)
    truth = fix_pos.mean(axis=0)
    lte = [m for m in cell_table.attach([m for m in meas if m.source == "lte"], origin)
           if m.kind == "pseudorange"]  # fmt: skip
    span = int((meas[-1].t_ns - t0) / 1e9)
    los, res, by = {}, defaultdict(dict), defaultdict(list)
    for m in lte:
        e = ekf_module.emitter_enu(m.meta, origin)
        if e is None:
            continue
        d = truth - e
        los.setdefault(m.emitter, d[:2] / np.linalg.norm(d[:2]))
        res[m.emitter][round((m.t_ns - t0) / 1e9 / BIN_S)] = (
            m.value[0] - float(np.linalg.norm(d)), m.meta.get("arc"))  # fmt: skip
        by[m.emitter].append(m)
    cells = {}
    for c, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        snr = np.array([float(m.meta.get("snr_db", np.nan)) for m in rs])
        cells[c] = {
            "records": len(rs),
            "seconds_with_records": len({int((m.t_ns - t0) / 1e9) for m in rs}),
            "arcs": len({m.meta.get("arc") for m in rs}),
            "snr_median_db": float(np.nanmedian(snr)),
            "retold_sigma_median_m": float(
                np.median([told_sigma.retold(m, "adr0036").sigma[0] for m in rs])
            ),  # fmt: skip
            "own_sigma_median_m": float(np.median([m.sigma[0] for m in rs])),
        }
    sec = defaultdict(set)
    for m in lte:
        sec[int((m.t_ns - t0) / 1e9)].add(m.emitter)
    h = np.array([hdop_2d([los[c] for c in sorted(sec.get(s, ())) if c in los])
                  for s in range(span)])  # fmt: skip
    fin = h[np.isfinite(h)]
    geometry = {
        "share_3_cells": float(np.mean(np.isfinite(h))),
        "hdop_median": float(np.median(fin)) if fin.size else math.nan,
        "cells_per_second": {
            str(k): float(np.mean([len(sec.get(s, ())) == k for s in range(span)]))
            for k in range(6)
        },  # fmt: skip
        "after_cut": {
            f"{c:g}": float(np.mean(np.isfinite(h[int(c) : int(c) + 300]))) for c in cuts
        },  # fmt: skip
    }
    ref = next(iter(cells))
    amb = next((m.meta.get("ambiguity_m") for m in lte if m.meta.get("ambiguity_m")), None)
    filters: dict = {}
    for name in rows:
        speed, learned = [], defaultdict(list)
        for c in cuts:
            cut_ns = t0 + round(c * 1e9)
            fed = cut.lte_variant(cut.cut_gnss(meas, t0, c), "told-pr")
            holder = {}
            orig = ekf_module.EKF.estimate

            def hook(self, _orig=orig, _holder=holder):
                _holder["ekf"] = self
                return _orig(self)

            ekf_module.EKF.estimate = hook
            try:
                est = list(nav.estimate(cut.estimator_fn(name), fed, origin_llh=origin))
            finally:
                ekf_module.EKF.estimate = orig
            v = [math.hypot(*e.vel_enu[:2]) for e in est
                 if cut_ns + 30e9 <= e.t_ns <= cut_ns + 300e9]  # fmt: skip
            speed.append({"median_m_s": float(np.median(v)), "max_m_s": float(np.max(v))})
            k = holder["ekf"]
            for cell, rs in by.items():
                s = learned_sigma(k, rs[-1])
                if s is not None:
                    learned[cell].append(s)
        filters[name] = {"speed_after_cut": speed, "learned_sigma_m": dict(learned)}
    return {
        "session": Path(path).name,
        "cuts_s": list(cuts),
        "cells": cells,
        "geometry": geometry,
        "dd_reference": ref,
        "dd_segments": dd_segments(res, ref, amb),
        "arc_restarts": arc_restarts(lte, t0),
        "filters": filters,
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session", help="real session after `pnt frontend lte`")
    ap.add_argument("--cuts", type=float, nargs="+", default=[99.0, 149.0, 199.0, 249.0, 299.0])
    ap.add_argument("--out", required=True, help="diagnosis.json")
    args = ap.parse_args(argv)
    out = diagnose(str(args.session), args.cuts)
    out["commit"] = cut_module()._commit()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
