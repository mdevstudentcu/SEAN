"""#147: what the filter should believe about a radio's LTE records, compared on paired sim runs.

LTE records shaped as the front end writes them report 2 m (`told_sigma_m`, `challenge-*`); the
sim's true error is 50 m white plus 50 m multipath (placeholders, ADR-0015). Variants, each for
`ekf` and `ekf-calibrated`, on the same records of each seed:

- `default`: the reported sigma (`ekf`, `ekf-calibrated`).
- `A`: learn each cell's range noise from its innovations (ADR-0039, #156:
  `ekf-learned-noise`, `ekf-calibrated-learned-noise`).
- `B`: ADR-0036's measured sigma from each record's SNR (`nav/told_sigma.py`:
  `ekf-measured-sigma`, `ekf-calibrated-measured-sigma`).
- `B+A`: B's sigma as the reported one, then A's learning on top.
- `no LTE`: the same run with every LTE record removed (a reference, not a fix).

A and B+A need #156's code in the `src/` under test; on a tree without it they are skipped and
the output says so. Run with PYTHONPATH at that `src/`:

    python analysis/told_sigma_147.py --seeds 200-249 --jobs 3 --out <dir>

Metrics per leg and variant, over the runs (seeds), from the first GPS loss (`metrics.gps_loss`):
- T1 (ADR-0034): the 95th percentile across runs of the horizontal error at each second after
  the loss; its worst second over 0-300 s. A second with no estimate counts as failing.
- Per run (`metrics.score`): the 300 s p95, the HPL bound rate over the first 300 s, misleading
  and hazardous epochs (the whole run), and the 600 s time error p95 (T3).
- NEES: the mean horizontal NEES over the first 300 s after the loss (2 when honest), per run.

Seeds 200 on are fresh: A was tuned on 100-149 (#156), B on none. Every value is TBC; the sim's
LTE model is `placeholder` (`verification.md`, *Sim validity*), so these numbers compare the
variants with each other, they don't predict a real flight.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np

from pnt.experiments import _map
from pnt.metrics import gps_loss, score
from pnt.nav import configured, ekf, estimate
from pnt.sim.scenario import T0_NS, generate, load

T1_LEGS = ("challenge-drone-outage", "challenge-timing-outage")
OTHER_LEGS = ("challenge-drone-outage-tower-clock-step", "challenge-drone-spoof-jump")
WINDOW_S = 300  # T1: the first 300 s after the loss (ADR-0034)
NO_OUTPUT_M = 1e6  # a second with no estimate: fails every target
CURVE_STEP_S = 5  # summary.json keeps the p95 curves at this step
FAMILIES = {"ekf": ekf.run, "ekf-calibrated": ekf.run_calibrated}
VARIANTS = ("default", "A", "B", "B+A", "no LTE")
FIELDS = (
    "outage_h_p95_300s_m",
    "outage_hpl_bound_300s",
    "misleading_epochs",
    "hazardous_epochs",
    "outage_time_err_600s_us",
    "time_hazardous_epochs",
    "false_alarms_per_h",
)


def has_learning() -> bool:
    """Whether the `src/` under test has #156's learned noise (`noise_tau_s`)."""
    return "noise_tau_s" in inspect.signature(ekf.EKF).parameters


def config(family: str, variant: str) -> dict | None:
    """The EKF options of a variant; None when the source under test lacks them."""
    tau = {"ekf": "NOISE_TAU_S", "ekf-calibrated": "CALIBRATED_NOISE_TAU_S"}[family]
    learn = {"noise_tau_s": getattr(ekf, tau)} if has_learning() else None
    told = {"told_sigma_model": "adr0036"}
    return {
        "default": {},
        "no LTE": {},
        "A": learn,
        "B": told,
        "B+A": None if learn is None else told | learn,
    }[variant]


def error_curve(estimates, truth, loss_ns: int) -> np.ndarray:
    """Horizontal error (m) at each second 0..WINDOW_S after the loss: the first estimate at or
    after that second; NaN where there is none."""
    true = {g.t_ns: g.pos_enu for g in truth}
    t = np.array([e.t_ns for e in estimates if e.t_ns in true])
    err = np.array([math.dist(e.pos_enu[:2], true[e.t_ns][:2]) for e in estimates
                    if e.t_ns in true])  # fmt: skip
    want = loss_ns + np.arange(WINDOW_S + 1) * 1_000_000_000
    i = np.searchsorted(t, want)
    out = np.full(WINDOW_S + 1, np.nan)
    ok = i < len(t)
    out[ok] = err[i[ok]]
    return out


def outage_nees(estimates, truth, loss_ns: int) -> float:
    """Mean horizontal NEES over the first WINDOW_S s after the loss."""
    true = {g.t_ns: g.pos_enu for g in truth}
    end = loss_ns + WINDOW_S * 1_000_000_000
    vals = []
    for e in estimates:
        if loss_ns <= e.t_ns < end and e.t_ns in true:
            d = np.subtract(e.pos_enu, true[e.t_ns])[:2]
            vals.append(float(d @ np.linalg.solve(np.reshape(e.pos_cov, (3, 3))[:2, :2], d)))
    return float(np.mean(vals)) if vals else float("nan")


def job(leg: str, seed: int) -> list[dict]:
    """Every family x variant on one seed of one leg; the same records for each."""
    spec = load(leg)
    run = generate(spec, seed=seed)
    loss = gps_loss(spec, T0_NS)
    no_lte = [m for m in run.measurements if m.source != "lte"]
    rows = []
    for family, fn in FAMILIES.items():
        for variant in VARIANTS:
            cfg = config(family, variant)
            if cfg is None:
                continue
            records = no_lte if variant == "no LTE" else run.measurements
            t = time.time()
            out = list(estimate(configured(fn, **cfg), records, origin_llh=spec.get("origin_llh")))
            m = score(out, run.truth, spec, T0_NS).as_dict()
            row = {"leg": leg, "seed": seed, "family": family, "variant": variant,
                   "run_s": round(time.time() - t, 2)} | {f: m[f] for f in FIELDS}  # fmt: skip
            if loss is not None:
                row["curve_m"] = [None if np.isnan(x) else round(float(x), 2)
                                  for x in error_curve(out, run.truth, loss[0])]  # fmt: skip
                row["outage_nees"] = outage_nees(out, run.truth, loss[0])
            rows.append(row)
    return rows


def t1(curves: np.ndarray) -> tuple[np.ndarray, float]:
    """ADR-0034's statistic: the p95 across runs at each second, and its worst second."""
    p95 = np.percentile(np.where(np.isnan(curves), NO_OUTPUT_M, curves), 95, axis=0)
    return p95, float(np.max(p95))


def collect(rows: list[dict]) -> list[dict]:
    """One summary per (leg, family, variant)."""
    out = []
    keys = sorted({(r["leg"], r["family"], r["variant"]) for r in rows},
                  key=lambda k: (k[0], k[1], VARIANTS.index(k[2])))  # fmt: skip
    for leg, family, variant in keys:
        rs = [r for r in rows if (r["leg"], r["family"], r["variant"]) == (leg, family, variant)]
        s = {"leg": leg, "family": family, "variant": variant, "runs": len(rs)}

        def col(f, rs=rs):
            return np.array([np.nan if r[f] is None else r[f] for r in rs], float)

        if "curve_m" in rs[0]:
            curves = np.array([[np.nan if x is None else x for x in r["curve_m"]] for r in rs])
            p95, worst = t1(curves)
            s |= {"t1_worst_m": worst, "p95_curve_m": [round(float(x), 1)
                                                       for x in p95[::CURVE_STEP_S]]}  # fmt: skip
            s["nees_median"] = float(np.nanmedian(col("outage_nees")))
            s["nees_p95"] = float(np.nanpercentile(col("outage_nees"), 95))
            s["p95_300s_median_m"] = float(np.nanmedian(col("outage_h_p95_300s_m")))
            s["hpl_bound_mean"] = float(np.nanmean(col("outage_hpl_bound_300s")))
            s["hpl_bound_worst"] = float(np.nanmin(col("outage_hpl_bound_300s")))
            s["time_err_600s_us_median"] = float(np.nanmedian(col("outage_time_err_600s_us")))
        for f in ("misleading_epochs", "hazardous_epochs", "time_hazardous_epochs"):
            s[f] = int(np.nansum(col(f)))
            s[f + "_runs"] = int(np.sum(col(f) > 0))
        s["false_alarms_per_h_mean"] = float(np.nanmean(col("false_alarms_per_h")))
        s["run_s_median"] = float(np.median(col("run_s")))
        out.append(s)
    return out


def _seeds(text: str) -> list[int]:
    a, b = text.split("-")
    return list(range(int(a), int(b) + 1))


def _git(src: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=True,
                          check=False).stdout.strip()  # fmt: skip


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--legs", nargs="+", default=list(T1_LEGS))
    ap.add_argument("--seeds", default="200-249")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", type=Path, required=True, help="directory for rows.json")
    ap.add_argument("--tag", default="", help="suffix of the output file names")
    a = ap.parse_args(argv)
    import pnt

    src = Path(pnt.__file__).resolve().parents[1]
    tasks = [(leg, seed) for leg in a.legs for seed in _seeds(a.seeds)]
    t0 = time.time()
    rows = [r for rs in _map(job, tasks, a.jobs) for r in rs]
    meta = {"src": src.name, "commit": _git(src, "rev-parse", "--short", "HEAD"),
            "dirty": _git(src, "status", "--porcelain") != "", "seeds": a.seeds,
            "legs": a.legs, "learning": has_learning(),
            "wall_s": round(time.time() - t0)}  # fmt: skip
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"rows{a.tag}.json").write_text(json.dumps({"meta": meta, "rows": rows}))
    (a.out / f"summary{a.tag}.json").write_text(
        json.dumps({"meta": meta, "summary": collect(rows)}, indent=1)
    )
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
