"""GPS-cut replay of the real static sessions with this branch's LTE records (read-only use of
`analysis/real_gps_cut.py` from the integration branch, which has #147's `ekf-measured-sigma`).

    PYTHONPATH=<integration worktree>/src python gps_cut.py --cut-script \
        <integration worktree>/analysis/real_gps_cut.py <name>=<session>-lte ... --out runs.json

Per session, the cuts of `real-gps-cut-combined-20261111` (100 to 300 s by 50 s on the 600 s
session) or of `real-lte-root-cause-20261111` (600 to 3000 s by 600 s on the 1 h one), each run:
`no LTE` (`ekf`, LTE dropped), `ekf` and `B` (`ekf-measured-sigma`) on pseudoranges only
(`told-pr`). Errors and HPL only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np

RUNS = (
    ("no LTE", "ekf", "none"),
    ("ekf", "ekf", "told-pr"),
    ("B", "ekf-measured-sigma", "told-pr"),
)
KEEP = ("err_60s_m", "err_300s_m", "hpl_60s_m", "hpl_300s_m", "p95_300s_m", "max_m",
        "hpl_bound", "pre_gnss_excluded", "n_lte")  # fmt: skip
CUT = None


def _load(path: str):
    global CUT
    if CUT is None:
        spec = importlib.util.spec_from_file_location("real_gps_cut", path)
        CUT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(CUT)
    return CUT


def cuts_for(duration_s: float) -> list[float]:
    if duration_s < 1000:
        return [100.0, 150.0, 200.0, 250.0, 300.0]
    return [600.0, 1200.0, 1800.0, 2400.0, 3000.0]


def job(script: str, name: str, path: str, label: str, est: str, variant: str, cut: float):
    out = _load(script).run_one(path, est, variant, cut)
    return {"session": name, "run": label, "cut_s": cut, **{k: out.get(k) for k in KEEP}}


def summarise(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        out.setdefault(r["session"], {}).setdefault(r["run"], []).append(r)
    for by in out.values():
        for run, rs in by.items():
            agg = {"cuts": len(rs)}
            for k in ("err_60s_m", "err_300s_m"):
                x = np.array([r[k] for r in rs], float)
                agg[k + "_median"] = float(np.nanmedian(x))
                agg[k + "_worst"] = float(np.nanmax(x))
            agg["hpl_bound"] = float(np.mean([r["hpl_bound"] for r in rs]))
            agg["pre_gnss_excluded"] = float(np.mean([r["pre_gnss_excluded"] for r in rs]))
            by[run] = agg
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cut-script", required=True)
    p.add_argument("sessions", nargs="+", help="name=path")
    p.add_argument("--out", required=True)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--lte-only", nargs="*", default=[], help="names run without `no LTE`")
    a = p.parse_args(argv)
    cut = _load(a.cut_script)
    tasks = []
    for spec in a.sessions:
        name, path = spec.split("=", 1)
        meas, t0, _ = cut.load(path)
        dur = (meas[-1].t_ns - t0) / 1e9
        runs = [r for r in RUNS if not (name in a.lte_only and r[2] == "none")]
        tasks += [(a.cut_script, name, path, *r, c) for r in runs for c in cuts_for(dur)]
    with ProcessPoolExecutor(min(a.jobs, 3)) as pool:
        rows = list(pool.map(job, *zip(*tasks, strict=True)))
    res = {"rows": rows, "summary": summarise(rows)}
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1, default=lambda o: None if o is None else float(o))
    for s, by in res["summary"].items():
        for run, g in by.items():
            print(
                f"{s:8s} {run:7s} 60 s {g['err_60s_m_median']:9.1f} ({g['err_60s_m_worst']:9.1f})"
                f"  300 s {g['err_300s_m_median']:9.1f} ({g['err_300s_m_worst']:9.1f})"
                f"  HPL>=err {g['hpl_bound']:.0%}  GNSS excl {g['pre_gnss_excluded']:.0%}"
            )


if __name__ == "__main__":
    main()
