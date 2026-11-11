"""VOR ablation on the UC-02 approach (#13, #94): the same runs with and without the bearings.

    python analysis/vor_ablation.py --runs 50 --jobs 3 --out analysis/results/vor-ablation

Each seed generates `uc02-yow-approach-vor` once. Its GNSS, barometer and tower records are the
ones `uc02-yow-approach` draws for that seed (the `vor` block comes last; tests check it), so the
two conditions share every non-VOR draw:
- towers: the run with its `vor` records dropped (= `uc02-yow-approach`)
- +VOR: the run with all its records (bearings from the real VORs in data/reference/navaids.csv;
  only YOW is in range on this approach)

Per estimator and condition: GPS-outage p95 horizontal error (`fault_h_p95_m`; the outage runs
from 60 s to the end), the worst run, the share of epochs with HPL >= the error, misleading
epochs and horizontal NEES; and, paired by seed, the change in outage p95 that VOR brings.
`uc02-yow-approach` has no IMU records, so `ekf-imu` predicts as `ekf` does there.

Writes summary.json, summary.md and vor_ablation.png into `--out`.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pnt import metrics, nav
from pnt.sim.scenario import T0_NS, generate, load

SCENARIO = "uc02-yow-approach-vor"
CONDITIONS = ("towers", "+VOR")
ESTIMATORS = ("ekf", "ekf-imu", "ekf-mhss")
KEYS = (
    "fault_h_p95_m",
    "fault_h_max_m",
    "h_rmse_m",
    "hpl_bound_frac",
    "misleading_epochs",
    "h_nees_mean",
)
STEP_S = 1.0  # error curves: the worst error in each second
COLORS = {"towers": "#7a7974", "+VOR": "#2a78d6"}  # gray: the reference condition


def arms(measurements) -> dict[str, list]:
    """The two conditions' records from one `uc02-yow-approach-vor` run."""
    return {
        "towers": [m for m in measurements if m.source != "vor"],
        "+VOR": list(measurements),
    }


def _curve(estimates, truth) -> np.ndarray:
    tmap = {t.t_ns: t.pos_enu for t in truth}
    t = np.array([(e.t_ns - T0_NS) / 1e9 for e in estimates if e.t_ns in tmap])
    err = np.array(
        [np.hypot(*np.subtract(e.pos_enu, tmap[e.t_ns])[:2]) for e in estimates if e.t_ns in tmap]
    )
    bins = np.floor(t / STEP_S).astype(int)
    out = np.full(bins.max() + 1, np.nan)
    np.fmax.at(out, bins, err)
    return out


def one_seed(seed: int, estimators: tuple[str, ...]) -> dict:
    run = generate(load(SCENARIO), seed=seed)
    out: dict = {}
    for cond, meas in arms(run.measurements).items():
        for est_name in estimators:
            est = list(nav.estimate(est_name, meas, origin_llh=run.spec["origin_llh"]))
            score = metrics.score(est, run.truth, run.spec, T0_NS)
            out[(est_name, cond)] = {
                "metrics": {k: float(getattr(score, k)) for k in KEYS},
                "curve": _curve(est, run.truth),
            }
    return out


def summarize(results: list[dict], estimators, seeds) -> dict:
    """Per estimator and condition over the seeds in `results` (in `seeds` order), and the paired
    change in outage p95 (+VOR minus towers, same seed)."""
    out: dict = {}
    for est in estimators:
        towers = np.array([r[(est, "towers")]["metrics"]["fault_h_p95_m"] for r in results])
        for cond in CONDITIONS:
            ms = [r[(est, cond)]["metrics"] for r in results]
            p95 = np.array([m["fault_h_p95_m"] for m in ms])
            fmax = np.array([m["fault_h_max_m"] for m in ms])
            hpl = np.array([m["hpl_bound_frac"] for m in ms])
            row = {
                "runs": len(ms),
                "fault_h_p95_m_median": float(np.median(p95)),
                "fault_h_p95_m_worst": float(np.max(p95)),
                "fault_h_p95_m_worst_seed": int(seeds[int(np.argmax(p95))]),
                "fault_h_max_m_worst": float(np.max(fmax)),
                "fault_h_max_m_worst_seed": int(seeds[int(np.argmax(fmax))]),
                "h_rmse_m_median": float(np.median([m["h_rmse_m"] for m in ms])),
                "hpl_bound_frac_mean": float(np.mean(hpl)),
                "hpl_bound_frac_min": float(np.min(hpl)),
                "misleading_epochs_total": int(np.sum([m["misleading_epochs"] for m in ms])),
                "h_nees_mean_median": float(np.median([m["h_nees_mean"] for m in ms])),
            }
            if cond != "towers":
                d = p95 - towers
                row.update(
                    {
                        "p95_change_m_median": float(np.median(d)),
                        "p95_change_m_min": float(np.min(d)),
                        "p95_change_m_max": float(np.max(d)),
                        "seeds_better": int(np.sum(d < 0)),
                        "seeds_worse": int(np.sum(d > 0)),
                        "sign_test_p": sign_test_p(int(np.sum(d < 0)), int(np.sum(d > 0))),
                    }
                )
            out[f"{est} {cond}"] = row
    return out


def sign_test_p(better: int, worse: int) -> float:
    """Two-sided exact sign test: how likely a split at least this uneven is if VOR changed
    nothing (ties dropped)."""
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2.0**n)


def same_as(conditions: dict, estimators, ref: str = "ekf", rtol: float = 1e-9) -> list[str]:
    """The estimators whose every summary number equals `ref`'s to `rtol`, in both conditions
    (an estimator with extra, unused states differs from `ref` in rounding only)."""

    def close(a: dict | None, b: dict | None) -> bool:
        return (
            a is not None
            and b is not None
            and a.keys() == b.keys()
            and all(np.isclose(a[k], b[k], rtol=rtol, atol=0.0) for k in a)
        )

    return [
        e
        for e in estimators
        if e != ref
        and all(
            close(conditions.get(f"{e} {c}"), conditions.get(f"{ref} {c}")) for c in CONDITIONS
        )
    ]


def table(conditions: dict) -> str:
    head = (
        "| Estimator | Condition | Outage p95, median / worst (seed) (m) | Outage max, worst "
        "(seed) (m) | HPL >= error, mean / min | Misleading epochs | NEES median | "
        "p95 change with VOR, median [min, max] (m) | Seeds better / worse (sign test p) |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for name, s in conditions.items():
        est, cond = name.split(" ", 1)
        paired = (
            f"{s['p95_change_m_median']:+.1f} [{s['p95_change_m_min']:+.1f}, "
            f"{s['p95_change_m_max']:+.1f}] | {s['seeds_better']} / {s['seeds_worse']} "
            f"({s['sign_test_p']:.2f})"
            if "p95_change_m_median" in s
            else "- | -"
        )
        rows.append(
            f"| `{est}` | {cond} | {s['fault_h_p95_m_median']:.1f} / "
            f"{s['fault_h_p95_m_worst']:.1f} ({s['fault_h_p95_m_worst_seed']}) | "
            f"{s['fault_h_max_m_worst']:.1f} ({s['fault_h_max_m_worst_seed']}) | "
            f"{s['hpl_bound_frac_mean']:.3f} / {s['hpl_bound_frac_min']:.3f} | "
            f"{s['misleading_epochs_total']} | {s['h_nees_mean_median']:.2f} | {paired} |"
        )
    return head + "\n".join(rows) + "\n"


def plot(results, estimators, spec, path: Path) -> None:
    """Left: `ekf` horizontal error over time, median to p95 across seeds, per condition.
    Right: per seed, the change in outage p95 that VOR brings, per estimator."""
    import matplotlib.pyplot as plt

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.4, 3.8), gridspec_kw={"width_ratios": [1.6, 1]})
    outage = next(f for f in spec["faults"] if f["type"] == "outage")
    ax.axvspan(
        outage["start_s"], outage.get("end_s", spec["duration_s"]), color="0.5", alpha=0.08, lw=0
    )
    est = estimators[0]
    for cond in CONDITIONS:
        curves = [r[(est, cond)]["curve"] for r in results]
        n = min(len(c) for c in curves)
        c = np.array([x[:n] for x in curves])
        t = np.arange(n) * STEP_S
        ax.fill_between(
            t,
            np.nanpercentile(c, 50, 0),
            np.nanpercentile(c, 95, 0),
            color=COLORS[cond],
            alpha=0.15,
            lw=0,
        )
        ax.plot(t, np.nanmedian(c, 0), color=COLORS[cond], lw=2, label=cond)
    ax.set_title(f"{est}: median (line) to p95 (band), {len(results)} seeds", fontsize=9)
    ax.set_xlabel("time (s); GPS outage shaded")
    ax.set_ylabel("horizontal error (m), worst per second")
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    rng = np.random.default_rng(0)  # jitter only
    for i, e in enumerate(estimators):
        d = np.array(
            [
                r[(e, "+VOR")]["metrics"]["fault_h_p95_m"]
                - r[(e, "towers")]["metrics"]["fault_h_p95_m"]
                for r in results
            ]
        )
        x = i + rng.uniform(-0.18, 0.18, len(d))
        bx.plot(x, d, "o", ms=4, color=COLORS["+VOR"], alpha=0.7, mec="none")
        bx.plot([i - 0.28, i + 0.28], [np.median(d)] * 2, color="0.15", lw=2)
    bx.axhline(0, color="0.5", lw=0.8)
    bx.set_xticks(range(len(estimators)), estimators, fontsize=8)
    bx.set_ylabel("outage p95: +VOR minus towers (m)")
    bx.set_title("paired by seed (bar: median); below 0 = VOR helps", fontsize=9)
    for a in (ax, bx):
        a.grid(True, axis="y", color="0.9", lw=0.6)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--estimators", default=",".join(ESTIMATORS))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    estimators = tuple(args.estimators.split(","))
    args.out.mkdir(parents=True, exist_ok=True)
    seeds = list(range(args.runs))
    with ProcessPoolExecutor(max(1, args.jobs)) as pool:
        results = list(pool.map(one_seed, seeds, [estimators] * len(seeds)))
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=12"], capture_output=True, text=True
    ).stdout.strip()
    conditions = summarize(results, estimators, seeds)
    same = [f"`{e}`" for e in same_as(conditions, estimators)]
    summary = {"commit": commit, "scenario": SCENARIO, "seeds": seeds, "conditions": conditions}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out / "summary.md").write_text(
        f"# VOR ablation, {SCENARIO}\n\nSim, every error value `TBC`. Commit `{commit}`, "
        f"`python analysis/vor_ablation.py --runs {args.runs} --jobs {args.jobs} "
        f"--out {args.out}`. Seeds "
        f"0-{args.runs - 1}, paired: towers = the same run with its `vor` records dropped. "
        f"The scenario has no IMU records, so `ekf-imu` predicts as `ekf` does. Every summary "
        f"number equal to `ekf`'s (to 1e-9, relative): {', '.join(same) or 'none'}.\n\n"
        + table(conditions)
    )
    plot(results, estimators, load(SCENARIO), args.out / "vor_ablation.png")
    print(table(conditions))
    print(f"commit {commit} -> {args.out}")


if __name__ == "__main__":
    main()
