"""Why LTE pulls a moving real session off (#214): each cell's range error against GPS truth.

    python analysis/real_walk_lte.py <session> [--lte-session DIR] [--out FILE.md]

Needs `analysis/walk_gps_cut.py` (#214) beside it for the session, truth and LTE loading.

1. A replay with GPS on throughout (`ekf`, LTE fed): per cell, the share of its records the
   filter's gate rejects, the size of the accepted innovations and their mean NIS, still and
   moving; the dongle clock's drift (common to every cell) and how much it changes a second.
2. Each record's range error: its pseudorange less the range from the GPS truth (the good fixes,
   interpolated) and the dongle clock offset that replay estimated. Within one arc (the front
   end's own unbroken track, so ADR-0050's per-arc bias does not apply), the structure function
   sqrt(mean (e(t + tau) - e(t))^2 / 2) of the 1 s means, at lags of 1 to 300 s, still and
   moving: ADR-0036 told the filter 10 m with a 3 s correlation time (static captures).

Privacy: errors, innovations, counts, times and cell names only; no position, track, origin,
range or bearing.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import walk_gps_cut as W  # noqa: E402

from pnt import nav  # noqa: E402
from pnt.core.frames import emitter_enu  # noqa: E402
from pnt.nav import cells  # noqa: E402
from pnt.nav import ekf as ekf_mod  # noqa: E402

TAUS = (1, 3, 10, 30, 100, 300)  # s: structure function lags


def gps_on_replay(raw: str, lte: str) -> tuple[dict, np.ndarray, dict]:
    """Per-LTE-update innovations and the dongle clock at each GNSS fix, GPS on throughout."""
    d, L = W.load(raw), W.load(lte)
    rows, clk, cur = [], [], {}
    upd, proc = ekf_mod.EKF._update, ekf_mod.EKF.process

    def _update(self, key, t_ns, y, H, R, gate=True):
        ok = upd(self, key, t_ns, y, H, R, gate)
        if key == "lte":
            y_, S, _ = self._last_innov
            rows.append((t_ns, cur["em"], float(y_[0]), math.sqrt(float(S[0, 0])), ok, gate))
        return ok

    def _process(self, m):
        if m.source == "lte":
            cur["em"] = m.emitter
        proc(self, m)
        if m.source == "gnss" and self.rx_idx:
            i = next(iter(self.rx_idx.values()))
            clk.append((m.t_ns, float(self.x[i]), float(self.x[i + 1])))

    ekf_mod.EKF._update, ekf_mod.EKF.process = _update, _process
    try:
        est = list(nav.estimate("ekf", L["meas"], origin_llh=d["origin"]))
    finally:
        ekf_mod.EKF._update, ekf_mod.EKF.process = upd, proc
    return {"rows": rows, "est": est}, np.array(clk), d


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--lte-session")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    raw = W.resolve(args.session)
    lte = Path(args.lte_session) if args.lte_session else raw.parent / f"{raw.name}-lte"
    raw, lte = str(raw), str(lte)
    tr = W.truth(raw, W.HDOP_MAX, W.MIN_SATS)
    v = W.speeds(tr["t"], tr["pos"])
    moving = np.nan_to_num(v, nan=0.0) >= W.MOVING_MPS
    out = [f"# LTE range error on `{Path(raw).name}` against GPS truth (#214)", ""]

    run, clk, d = gps_on_replay(raw, lte)
    t0 = d["t0"]
    r = run["rows"]
    t = np.array([x[0] for x in r], dtype=np.int64)
    cell = np.array([x[1] for x in r])
    y, sS = np.array([x[2] for x in r]), np.array([x[3] for x in r])
    acc, gated = np.array([x[4] for x in r]), np.array([x[5] for x in r])
    mv = W.moving_at(tr["t"], moving, t)
    est = run["est"]
    et = np.array([e.t_ns for e in est], dtype=np.int64)
    ep = np.array([e.pos_enu for e in est], dtype=float)
    ref, ok = W.interpolate(tr["t"], tr["pos"][:, :2], et)
    err = np.hypot(*(ep[ok, :2] - ref[ok]).T)
    out += [
        "## 1. GPS on throughout, `ekf` with LTE",
        "",
        f"Horizontal error p50 {np.median(err):.2f} m, p95 {np.percentile(err, 95):.2f} m. "
        "Rejected: share of a cell's gated records the gate refused. NIS: mean y²/S of the "
        "accepted ones (1 if the filter's model fits).",
        "",
        "| Cell | Records | Rejected (still / moving) | Accepted \\|y\\| p50 / p95 (m) "
        "| NIS (still / moving) |",
        "|---|---|---|---|---|",
    ]
    for c in sorted(set(cell), key=lambda c: -np.sum(cell == c)):
        s = cell == c
        a = s & acc

        def rej(q):
            return f"{100 * np.mean(~acc[q]):.0f} %" if q.any() else "–"

        def nis(q):
            return f"{np.mean((y[q] / sS[q]) ** 2):.2f}" if q.any() else "–"

        out.append(
            f"| `{c}` | {s.sum()} | {rej(s & gated)} ({rej(s & gated & ~mv)} / "
            f"{rej(s & gated & mv)}) | {np.median(np.abs(y[a])):.0f} / "
            f"{np.percentile(np.abs(y[a]), 95):.0f} | {nis(a & ~mv)} / {nis(a & mv)} |"
        )
    cm = W.moving_at(tr["t"], moving, clk[:, 0].astype(np.int64))
    dd = np.diff(clk[:, 2])
    out += [
        "",
        f"Dongle clock drift: median {np.median(clk[~cm, 2]):.1f} m/s still, "
        f"{np.median(clk[cm, 2]):.1f} m/s moving; its change between fixes, std "
        f"{np.std(dd[~cm[1:]]):.2f} m/s still, {np.std(dd[cm[1:]]):.2f} m/s moving.",
        "",
    ]

    L = W.load(lte)
    recs = [
        m
        for m in cells.attach([m for m in L["meas"] if m.source == "lte"], d["origin"])
        if m.kind == "pseudorange"
    ]
    t = np.array([m.t_ns for m in recs], dtype=np.int64)
    pos, ok = W.interpolate(tr["t"], tr["pos"], t)
    rx = np.interp(t, clk[:, 0], clk[:, 1])
    mv = W.moving_at(tr["t"], moving, t)
    emit: dict = {}
    z = np.full(len(recs), np.nan)
    for i, (m, p, k) in enumerate(zip(recs, pos, ok, strict=True)):
        if k:
            e = emit.setdefault(m.emitter, emitter_enu(m.meta, d["origin"]))
            z[i] = m.value[0] - float(np.linalg.norm(p - e)) - rx[i]
    cell = np.array([m.emitter for m in recs])
    arc = np.array([m.meta.get("arc", 0) for m in recs])
    snr = np.array([m.meta.get("snr_db", np.nan) for m in recs])
    sec = (t - t0) // 1_000_000_000
    out += [
        "## 2. Range error within one arc: structure function (m), still / moving",
        "",
        "ADR-0036 (static captures): 10 m, correlation time 3 s. RMS over every pair; the last "
        "row is robust (1.4826 MAD / sqrt 2).",
        "",
        "| Cell | SNR p50 (dB) | " + " | ".join(f"{x} s" for x in TAUS) + " |",
        "|---|---|" + "---|" * len(TAUS),
    ]
    pooled: dict = {x: {False: [], True: []} for x in TAUS}
    for c in sorted(set(cell), key=lambda c: -np.sum(cell == c)):
        s = (cell == c) & np.isfinite(z)
        ser: dict = {}
        for a in np.unique(arc[s]):
            q = s & (arc == a)
            for sc in np.unique(sec[q]):
                k = q & (sec == sc)
                ser.setdefault(a, {})[int(sc)] = (float(z[k].mean()), bool(mv[k].mean() > 0.5))
        cols = []
        for x in TAUS:
            dif: dict = {False: [], True: []}
            for dd_ in ser.values():
                for sc, (val, m_) in dd_.items():
                    if sc + x in dd_ and dd_[sc + x][1] == m_:
                        dif[m_].append(dd_[sc + x][0] - val)
            for k_ in dif:
                pooled[x][k_] += dif[k_]
            cols.append(
                "/".join(
                    f"{math.sqrt(np.mean(np.square(dif[k_])) / 2):.0f}"
                    if len(dif[k_]) > 20
                    else "–"
                    for k_ in (False, True)
                )
            )
        out.append(f"| `{c}` | {np.nanmedian(snr[cell == c]):.1f} | " + " | ".join(cols) + " |")

    def rms(a):
        return math.sqrt(np.mean(np.square(a)) / 2) if len(a) else math.nan

    def rob(a):
        return 1.4826 * float(np.median(np.abs(a))) / math.sqrt(2) if len(a) else math.nan

    for name, f in (("all cells, RMS", rms), ("all cells, robust", rob)):
        cols = [f"{f(pooled[x][False]):.0f}/{f(pooled[x][True]):.0f}" for x in TAUS]
        out.append(f"| {name} | | " + " | ".join(cols) + " |")
    text = "\n".join(out) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text)


if __name__ == "__main__":
    main()
