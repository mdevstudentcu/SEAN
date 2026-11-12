"""Why LTE still hurts a moving GPS cut (#214): the same cuts as `walk_gps_cut.py`, with the LTE
records or the filter changed one thing at a time, some of them with truth put in (oracles).

    python analysis/walk_lte_cut_oracle.py <session> --lte-session DIR --cut-at S ...
        [--variants ...] [--opt JSON] [--bias] [--jobs 3] [--out FILE.md]

Needs `analysis/walk_gps_cut.py` (#214, #299) beside it: loading, truth, the GNSS cut and the
score are its own. Every run is `ekf` (with `--opt`, `ekf` with those options on top).

Variants of the LTE records fed (`VARIANTS`):
- `no-lte`: none. `lte`: as recorded. `lte-before-cut`: none from the cut on.
- `arcs-merged`: every record of a cell on one arc, so ADR-0050's bias per arc never resets.
- `arcs-aligned`: each later arc shifted by its truth-implied offset from the cell's first arc,
  then merged (an oracle for the arc steps).
- `less-clock`: each record less the dongle clock a GPS-on replay estimated (an oracle clock);
  `less-clock-aligned`: the same with `arcs-aligned`'s shifts.
- `perfect`: each record replaced by the truth range plus that GPS-on dongle clock plus a constant
  per cell; arcs merged. `perfect-const-clock`: the same without the clock.
- `perfect-w78`: `perfect` plus white noise at 78 m, ADR-0036's sigma for a 10 Hz record.

The truth-implied range of a record is its pseudorange less the range from the GPS truth (the
good fixes, interpolated) to its tower. The GPS-on replay is `ekf` with every record, GPS on
throughout, as `real_walk_lte.py`.

`--bias`: per cut, at the cut and 30, 60 and 120 s after it (each over the 2 s before), the
`lte` run's position error and, per cell, the truth-implied range residual less the filter's
clock and bias terms (dongle clock + site clock + arc bias), with the filter's sigma of those
terms. Also the dongle clock's drift change and its offset change beyond the drift, from the
GPS-on replay, and the share of 10 s windows in which the cells heard give a 2-D fix with
our clock unknown (3 or more tower positions, HDOP <= 3 from the truth geometry).

Privacy: errors, sigma, times, counts and cell names only. No position, track, origin, range
or bearing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from msgspec.structs import replace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import walk_gps_cut as W  # noqa: E402

from pnt import nav  # noqa: E402
from pnt.core.frames import emitter_enu  # noqa: E402
from pnt.nav import cells  # noqa: E402
from pnt.nav import ekf as ekf_mod  # noqa: E402

VARIANTS = (
    "no-lte",
    "lte",
    "lte-before-cut",
    "arcs-merged",
    "arcs-aligned",
    "less-clock",
    "less-clock-aligned",
    "perfect",
    "perfect-w78",
    "perfect-const-clock",
)
ORACLE = ("arcs-aligned", "less-clock", "less-clock-aligned", "perfect", "perfect-w78",
          "perfect-const-clock")  # fmt: skip
BIAS_AT_S = (0, 30, 60, 120)
_G: dict = {}  # per worker: raw, lte, options, oracle tables


def gps_on_clock(raw: str, lte: str) -> np.ndarray:
    """(t_ns, offset m, drift m/s) of the dongle clock every 0.1 s, GPS on throughout."""
    d, L = W.load(raw), W.load(lte)
    clk: list = []
    proc = ekf_mod.EKF.process

    def _process(self, m):
        proc(self, m)
        if self.rx_idx and (not clk or m.t_ns - clk[-1][0] >= 100_000_000):
            i = next(iter(self.rx_idx.values()))
            clk.append((m.t_ns, float(self.x[i]), float(self.x[i + 1])))

    ekf_mod.EKF.process = _process
    try:
        for _ in nav.estimate("ekf", L["meas"], origin_llh=d["origin"]):
            pass
    finally:
        ekf_mod.EKF.process = proc
    return np.array(clk)


def oracle_tables(raw: str, lte: str, clk: np.ndarray) -> dict:
    """Per (cell, t_ns): the record's truth-implied range less the GPS-on clock (`e`), the
    clock; per (cell, arc): the arc's offset from the cell's first arc (medians of `e`)."""
    d, L = W.load(raw), W.load(lte)
    tr = W.truth(raw, W.HDOP_MAX, W.MIN_SATS)
    recs = [m for m in cells.attach([m for m in L["meas"] if m.source == "lte"], d["origin"])
            if m.kind == "pseudorange"]  # fmt: skip
    t = np.array([m.t_ns for m in recs], dtype=np.int64)
    pos, ok = W.interpolate(tr["t"], tr["pos"], t)
    rx = np.interp(t, clk[:, 0], clk[:, 1])
    em: dict = {}
    e = np.full(len(recs), np.nan)
    for i, m in enumerate(recs):
        if ok[i]:
            p = em.setdefault(m.emitter, emitter_enu(m.meta, d["origin"]))
            e[i] = m.value[0] - float(np.linalg.norm(pos[i] - p)) - rx[i]
    cell = np.array([m.emitter for m in recs])
    arc = np.array([m.meta.get("arc", 0) for m in recs])
    off, const = {}, {}
    for c in set(cell):
        s = (cell == c) & np.isfinite(e)
        if not s.any():
            continue
        first = None
        for a in sorted(set(arc[s])):
            med = float(np.median(e[s & (arc == a)]))
            first = med if first is None else first
            off[(c, int(a))] = med - first
        const[c] = first
    rec = {(c, int(tt)): (float(ee), float(r)) for c, tt, ee, r in zip(cell, t, e, rx, strict=True)
           if math.isfinite(ee)}  # fmt: skip
    return {"rec": rec, "off": off, "const": const}


def fed_for(variant: str, meas: list, cut_ns: int, seed: int) -> list:
    """The records a run is fed (before the GNSS cut), per `variant`."""
    if variant == "no-lte":
        return [m for m in meas if m.source != "lte"]
    if variant == "lte":
        return meas
    if variant == "lte-before-cut":
        return [m for m in meas if m.source != "lte" or m.t_ns < cut_ns]
    if variant == "arcs-merged":
        return [replace(m, meta={**m.meta, "arc": 0}) if m.source == "lte" else m for m in meas]
    o = _G["oracle"]
    rng = np.random.default_rng(seed)
    out = []
    for m in meas:
        if m.source != "lte" or m.kind != "pseudorange":
            out.append(m)
            continue
        k = (m.emitter, m.t_ns)
        if k not in o["rec"]:
            continue  # no truth for this record: an oracle can't give it
        e, rx = o["rec"][k]
        shift = o["off"].get((m.emitter, m.meta.get("arc", 0)), 0.0)
        truth_range = m.value[0] - e - rx
        if variant == "arcs-aligned":
            v = m.value[0] - shift
        elif variant == "less-clock":
            v = m.value[0] - rx
        elif variant == "less-clock-aligned":
            v = m.value[0] - rx - shift
        else:  # perfect*
            v = truth_range + o["const"][m.emitter]
            if variant != "perfect-const-clock":
                v += rx
            if variant == "perfect-w78":
                v += float(rng.normal(0.0, 78.0))
        meta = m.meta if variant == "less-clock" else {**m.meta, "arc": 0}
        out.append(replace(m, value=(v,), meta=meta))
    return out


def estimator():
    if not _G["opt"]:
        return "ekf"
    fn = nav.ESTIMATORS["ekf"]
    kw = dict(getattr(fn, "keywords", {}))
    return nav.configured(getattr(fn, "func", fn), **{**kw, **_G["opt"]})


def run(job: tuple[str, float]) -> dict:
    variant, cut_s = job
    raw, lte = _G["raw"], _G["lte"]
    d = W.load(raw)
    tr = W.truth(raw, W.HDOP_MAX, W.MIN_SATS)
    t0 = d["t0"]
    cut_ns = t0 + round(cut_s * 1e9)
    end = cut_ns + round((W.HORIZON_S + 1.0) * 1e9)
    meas = [m for m in W.load(lte)["meas"] if m.t_ns <= end]
    fed = W.cut_gnss(fed_for(variant, meas, cut_ns, round(cut_s)), t0, cut_s)
    est = list(nav.estimate(estimator(), fed, origin_llh=d["origin"]))
    et = np.array([e.t_ns for e in est], dtype=np.int64)
    ep = np.array([e.pos_enu for e in est], dtype=float)
    eh = np.array([np.nan if e.hpl_m is None else e.hpl_m for e in est], dtype=float)
    s = W.score(et, ep, eh, tr["t"], tr["pos"], cut_ns)
    pre = (et >= t0 + round(W.SETTLE_S * 1e9)) & (et < cut_ns)
    ref, ok = W.interpolate(tr["t"], tr["pos"][:, :2], et[pre])
    return {
        "variant": variant,
        "cut_s": cut_s,
        **{k: s[k] for k in ("err_60s_m", "err_120s_m", "err_300s_m", "hpl_bound")},
        "pre_p95_m": W._p95(np.hypot(*(ep[pre][ok, :2] - ref[ok]).T)),
    }


def bias_rows(raw: str, lte: str, cut_s: float) -> list[str]:
    """`--bias` for one cut (module docstring)."""
    d, L = W.load(raw), W.load(lte)
    tr = W.truth(raw, W.HDOP_MAX, W.MIN_SATS)
    t0 = d["t0"]
    cut_ns = t0 + round(cut_s * 1e9)
    end = cut_ns + round((max(BIAS_AT_S) + 5) * 1e9)
    fed = W.cut_gnss([m for m in L["meas"] if m.t_ns <= end], t0, cut_s)
    rows, em = [], {}
    proc = ekf_mod.EKF.process

    def _process(self, m):
        dt = (m.t_ns - cut_ns) / 1e9
        if (
            m.source == "lte" and m.kind == "pseudorange" and "rx_clock" in m.meta
            and self.rx_idx and any(a - 2 <= dt < a for a in BIAS_AT_S)
        ):  # fmt: skip
            k = self.clock_idx.get(f"site:{self.sites.get(m.emitter, m.emitter)}")
            pos, ok = W.interpolate(tr["t"], tr["pos"], np.array([m.t_ns]))
            if k is not None and ok[0]:
                arc = self._arc_idx.get(m.emitter)
                idx = [self.rx_idx[m.meta["rx_clock"]], k]
                if arc and arc[1] is not None and arc[0] == m.meta.get("arc"):
                    idx.append(arc[1])
                one = np.ones(len(idx))
                p = em.setdefault(m.emitter, emitter_enu(m.meta, d["origin"]))
                z = m.value[0] - float(np.linalg.norm(pos[0] - p)) - float(self.x[idx].sum())
                sd = math.sqrt(float(one @ self.P[np.ix_(idx, idx)] @ one))
                rows.append((dt, m.emitter, z, sd, float(np.hypot(*(self.x[:2] - pos[0][:2])))))
        proc(self, m)

    ekf_mod.EKF.process = _process
    try:
        for _ in nav.estimate("ekf", fed, origin_llh=d["origin"]):
            pass
    finally:
        ekf_mod.EKF.process = proc
    out = []
    for a in BIAS_AT_S:
        rs = [r for r in rows if a - 2 <= r[0] < a]
        by: dict = {}
        for r in rs:
            by.setdefault(r[1], []).append(r)
        cellcol = ", ".join(
            f"`{c.split(':')[-1]}` {np.median([x[2] for x in v]):+.0f} "
            f"± {np.median([x[3] for x in v]):.0f}"
            for c, v in sorted(by.items())
        )
        err = f"{np.median([r[4] for r in rs]):.0f}" if rs else "–"
        out.append(f"| {cut_s:g} | +{a} | {err} | {cellcol} |")
    return out


def site_rows(raw: str, lte: str) -> list[str]:
    """Share of 10 s windows (with truth) in which the cells heard give a 2-D fix with our clock
    unknown: at least 3 tower positions and HDOP <= 3 from the truth geometry."""
    d, L = W.load(raw), W.load(lte)
    tr = W.truth(raw, W.HDOP_MAX, W.MIN_SATS)
    recs = [m for m in cells.attach([m for m in L["meas"] if m.source == "lte"], d["origin"])
            if m.kind == "pseudorange"]  # fmt: skip
    t = np.array([m.t_ns for m in recs], dtype=np.int64)
    cell = np.array([m.emitter for m in recs])
    em = {m.emitter: emitter_enu(m.meta, d["origin"]) for m in recs}
    n, ok3, okh = 0, 0, 0
    for a in range(int(t.min()), int(t.max()), 10_000_000_000):
        pos, ok = W.interpolate(tr["t"], tr["pos"], np.array([a + 5_000_000_000]))
        if not ok[0]:
            continue
        n += 1
        heard = set(cell[(t >= a) & (t < a + 10_000_000_000)])
        sites = {tuple(np.round(em[c][:2], 0)) for c in heard}
        if len(sites) < 3:
            continue
        ok3 += 1
        G = []
        for x in sites:
            u = pos[0][:2] - np.array(x)
            G.append([*(u / np.linalg.norm(u)), 1.0])
        G = np.array(G)
        q = np.linalg.pinv(G.T @ G)
        okh += bool(np.linalg.matrix_rank(G) == 3 and q[0, 0] + q[1, 1] <= 9.0)
    return [
        "",
        f"Of {n} windows of 10 s with truth, {100 * ok3 / n:.0f} % heard 3 or more tower "
        f"positions"
        f" and {100 * okh / n:.0f} % had them at HDOP ≤ 3 (clock unknown, truth geometry).",
    ]


def clock_rows(clk: np.ndarray) -> list[str]:
    g = np.arange(clk[0, 0], clk[-1, 0], 1e9)
    off, dr = np.interp(g, clk[:, 0], clk[:, 1]), np.interp(g, clk[:, 0], clk[:, 2])
    out = ["| τ (s) | Drift change, std (m/s) | Offset change beyond the drift, std (m) |",
           "|---|---|---|"]  # fmt: skip
    for tau in (1, 10, 30, 100):
        dd = dr[tau:] - dr[:-tau]
        oo = (off[tau:] - off[:-tau]) - dr[:-tau] * tau
        out.append(f"| {tau} | {np.std(dd):.1f} | {np.std(oo):.0f} |")
    p5, p95 = np.percentile(dr, [5, 95])
    out.append("")
    out.append(f"Drift over the session: 5th to 95th percentile {p5:.0f} to {p95:.0f} m/s.")
    return out


def init(g: dict) -> None:
    _G.update(g)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--lte-session", required=True)
    ap.add_argument("--cut-at", type=float, nargs="+", required=True)
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--opt", default="{}", help="ekf options as JSON, for every run")
    ap.add_argument("--bias", action="store_true")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    raw, lte = str(W.resolve(args.session)), str(Path(args.lte_session))
    g = {"raw": raw, "lte": lte, "opt": json.loads(args.opt), "oracle": None}
    need_clock = args.bias or any(v in ORACLE for v in args.variants)
    clk = gps_on_clock(raw, lte) if need_clock else None
    if any(v in ORACLE for v in args.variants):
        g["oracle"] = oracle_tables(raw, lte, clk)
    jobs = [(v, c) for v in args.variants for c in args.cut_at]
    with Pool(args.jobs, initializer=init, initargs=(g,)) as pool:
        res = pool.map(run, jobs)
    opt = f", options `{args.opt}`" if g["opt"] else ""
    lines = [
        f"# LTE on a moving GPS cut, one change at a time: `{Path(raw).name}` (#214)",
        "",
        f"LTE records: `{Path(lte).name}`. `ekf`{opt}. Cuts at "
        + ", ".join(f"{c:g}" for c in args.cut_at)
        + " s. Median over the cuts, worst cut in brackets (m).",
        "",
        "| Variant | 60 s | 120 s | 300 s | HPL ≥ error | p95 before the cut "
        "| Per cut, 60 / 120 / 300 s |",
        "|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    for v in args.variants:
        rs = sorted((r for r in res if r["variant"] == v), key=lambda r: r["cut_s"])

        def col(k, rs=rs):
            x = [r[k] for r in rs]
            return f"{np.nanmedian(x):,.0f} ({np.nanmax(x):,.0f})"

        per = "; ".join(
            f"{r['err_60s_m']:,.0f} / {r['err_120s_m']:,.0f} / {r['err_300s_m']:,.0f}" for r in rs
        )
        lines.append(
            f"| `{v}` | {col('err_60s_m')} | {col('err_120s_m')} | {col('err_300s_m')} "
            f"| {100 * np.nanmedian([r['hpl_bound'] for r in rs]):.0f} % "
            f"| {np.nanmedian([r['pre_p95_m'] for r in rs]):.1f} | {per} |"
        )
    if args.bias:
        lines += [
            "",
            "## The `lte` run's clock and bias terms against truth",
            "",
            "Per cell: the truth-implied range residual less the filter's dongle clock, site "
            "clock and arc bias, median over the 2 s before each time, ± the filter's sigma of "
            "those terms (m). Zero if the filter knows them.",
            "",
            "| Cut (s) | Time after (s) | Position error (m) | Per cell |",
            "|---|---|---|---|",
        ]
        for c in args.cut_at:
            lines += bias_rows(raw, lte, c)
        lines += ["", "## The dongle clock, GPS on (1 s samples)", ""] + clock_rows(clk)
        lines += site_rows(raw, lte)
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        Path(args.out).write_text(text)


if __name__ == "__main__":
    main()
