"""The filter changes of ADR-0048 on real LTE records (#214, #246), each alone and combined:
a real static session replayed with GPS cut in software, scored against the withheld fixes.

    python analysis/real_lte_filter.py NAME=<session>-lte ... [--configs ...] [--jobs 3]
        --out analysis/results/real-lte-filter/summary.json

Uses `analysis/real_gps_cut.py`'s cut and scoring (LTE pseudoranges only, `told-pr`). Cuts as
the runs it is compared with (`lte-reacq-steps`): 100 to 300 s by 50 s on a session under
1,000 s, 600 to 3,000 s by 600 s on a longer one. Each run stops 301 s after its cut: nothing
after that is scored. Errors, HPL and flags only: no position, range or bearing is written.

Configurations (`CONFIGS`), all `ekf` (`ekf-imu` where named), on top of `MAIN` = main's `ekf`
(the front end's own sigma for a real capture's records):
- a: ADR-0036's sigma for a real capture's records (`capture_sigma_model`, the new default)
- b: GNSS re-admission when the towers are unfit to refute it (`gnss_readmit`)
- c: a new arc starts a new range bias (`arc_bias`)
- d: a heard cell bounds the position to `heard_cell_radius_m` of its site
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

from pnt import experiments, nav
from pnt.integrity.gnss_readmit import GnssReadmit
from pnt.nav import ekf

HERE = Path(__file__).resolve().parent
RADIUS_M = 10_000.0  # d: cells.MAX_RANGE_KM, the lookup's own assumption (ADR-0048, TBC)

MAIN = {"capture_sigma_model": None}
A = {"capture_sigma_model": "adr0036"}
B = {"gnss_readmit": GnssReadmit}
C = {"arc_bias": True}
D = {"heard_cell_radius_m": RADIUS_M}
CONFIGS = {
    "no LTE": ("ekf", {}, "none"),
    "main": ("ekf", MAIN, "told-pr"),
    "a": ("ekf", A, "told-pr"),
    "b": ("ekf", {**MAIN, **B}, "told-pr"),
    "c": ("ekf", {**MAIN, **C}, "told-pr"),
    "d": ("ekf", {**MAIN, **D}, "told-pr"),
    "a+b": ("ekf", {**A, **B}, "told-pr"),
    "a+c": ("ekf", {**A, **C}, "told-pr"),
    "a+d": ("ekf", {**A, **D}, "told-pr"),
    "a+b+c+d": ("ekf", {**A, **B, **C, **D}, "told-pr"),
    "imu main": ("ekf-imu", MAIN, "told-pr"),
    "imu a": ("ekf-imu", A, "told-pr"),
    "imu a+b+c+d": ("ekf-imu", {**A, **B, **C, **D}, "told-pr"),
}
KEEP = ("err_60s_m", "err_300s_m", "p95_300s_m", "max_m", "hpl_bound", "misleading",
        "n_fixes", "pre_gnss_excluded", "pre_p95_m")  # fmt: skip
_CUT = None


def cut_module():
    """`analysis/real_gps_cut.py`, loaded by path (analysis/ is not a package)."""
    global _CUT
    if _CUT is None:
        spec = importlib.util.spec_from_file_location("real_gps_cut", HERE / "real_gps_cut.py")
        _CUT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_CUT)
    return _CUT


def cuts_for(duration_s: float) -> list[float]:
    if duration_s < 1000:
        return [100.0, 150.0, 200.0, 250.0, 300.0]
    return [600.0, 1200.0, 1800.0, 2400.0, 3000.0]


def estimator(name: str):
    base, config, _ = CONFIGS[name]
    fn = nav.ESTIMATORS[base]
    keywords = dict(getattr(fn, "keywords", {}))
    return nav.configured(ekf.run, **{**keywords, **config})


def run_one(session: str, path: str, name: str, cut_s: float) -> dict:
    """One replay with GNSS cut at `cut_s`, stopped `HORIZON_S` + 1 s after it, scored."""
    cut = cut_module()
    meas, t0, origin = cut.load(path)
    end = t0 + round((cut_s + cut.HORIZON_S + 1.0) * 1e9)
    fed = cut.lte_variant(cut.cut_gnss([m for m in meas if m.t_ns <= end], t0, cut_s),
                          CONFIGS[name][2])  # fmt: skip
    fix_t, fix_pos = cut.gps_fixes(meas)
    cut_ns = t0 + round(cut_s * 1e9)
    est = list(nav.estimate(estimator(name), fed, origin_llh=origin))
    est_t = np.array([e.t_ns for e in est], dtype=np.int64)
    est_pos = np.array([e.pos_enu for e in est], dtype=float)
    est_hpl = np.array([e.hpl_m for e in est], dtype=float)
    out = cut.score_cut(est_t, est_pos, est_hpl, fix_t, fix_pos, cut_ns)
    settled = [e for e in est if t0 + cut.SETTLE_S * 1e9 <= e.t_ns < cut_ns]
    out["pre_gnss_excluded"] = float(np.mean(["gnss_excluded" in e.flags for e in settled]))
    pre = (fix_t >= t0 + round(cut.SETTLE_S * 1e9)) & (fix_t < cut_ns)
    i = np.searchsorted(est_t, fix_t[pre])
    on = (i < len(est_t)) & (est_t[np.minimum(i, len(est_t) - 1)] == fix_t[pre])
    pre_err = np.hypot(*(est_pos[i[on], :2] - fix_pos[pre][on, :2]).T)
    out["pre_p95_m"] = float(np.percentile(pre_err, 95)) if pre_err.size else math.nan
    row = {"session": session, "config": name, "cut_s": cut_s}
    row.update({k: out[k] for k in KEEP})
    row["err_m"], row["hpl_m"] = out["err_m"], out["hpl_m"]
    return row


def summarise(rows: list[dict]) -> dict:
    """Per session and configuration: median and worst over the cuts at 60 and 300 s, the HPL
    bound rate pooled over every withheld fix, misleading fixes, GNSS excluded before the cut."""
    by: dict = {}
    for r in rows:
        by.setdefault(r["session"], {}).setdefault(r["config"], []).append(r)
    out: dict = {}
    for s, configs in by.items():
        for c, rs in configs.items():
            a: dict = {"cuts": [r["cut_s"] for r in rs]}
            for k in ("err_60s_m", "err_300s_m", "p95_300s_m", "max_m"):
                x = np.array([r[k] for r in rs], float)
                a[k] = {"median": float(np.nanmedian(x)), "worst": float(np.nanmax(x))}
            err = np.concatenate([r["err_m"] for r in rs])
            hpl = np.concatenate([r["hpl_m"] for r in rs])
            a["hpl_bound"] = float(np.mean(hpl >= err))
            a["misleading"] = int(np.sum(err > hpl))
            a["fixes"] = int(err.size)
            a["pre_gnss_excluded"] = float(np.mean([r["pre_gnss_excluded"] for r in rs]))
            a["pre_p95_m"] = float(np.nanmedian([r["pre_p95_m"] for r in rs]))
            out.setdefault(s, {})[c] = a
    return out


def _fmt(x: float) -> str:
    if x != x:
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


def markdown(summary: dict) -> str:
    lines = [
        "| Session | Config | 60 s | 300 s | HPL ≥ error | Error > HPL (fixes) | "
        "Before cut: GNSS excluded | Before cut: p95 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s, configs in summary.items():
        for c, a in configs.items():
            e60, e300 = a["err_60s_m"], a["err_300s_m"]
            lines.append(
                f"| {s} | {c} | {_fmt(e60['median'])} ({_fmt(e60['worst'])}) | "
                f"{_fmt(e300['median'])} ({_fmt(e300['worst'])}) | {a['hpl_bound']:.0%} | "
                f"{a['misleading']} / {a['fixes']} | {a['pre_gnss_excluded']:.0%} | "
                f"{_fmt(a['pre_p95_m'])} |"
            )
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+", help="NAME=<session>-lte")
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS))
    ap.add_argument("--jobs", type=int, default=1, help="worker processes (<= 3 on this laptop)")
    ap.add_argument("--out", required=True, help="summary JSON")
    args = ap.parse_args(argv)
    cut = cut_module()
    tasks = []
    for spec in args.sessions:
        name, path = spec.split("=", 1)
        meas, t0, _ = cut.load(path)
        for c in args.configs:
            tasks += [(name, path, c, t) for t in cuts_for((meas[-1].t_ns - t0) / 1e9)]
    rows = experiments._map(run_one, tasks, args.jobs)
    summary = summarise(rows)
    runs = [{k: v for k, v in r.items() if k not in ("err_m", "hpl_m")} for r in rows]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {"commit": cut._commit(), "summary": summary, "runs": runs}
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(markdown(summary))


if __name__ == "__main__":
    main()
