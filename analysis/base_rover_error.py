"""Horizontal error over time, with and without the ground reference station (issue #81).

Runs `ekf-base` over a with-base scenario twice per seed: once with both receivers and the
session's `reference` block, once with the payload's records only (its single-receiver fallback,
which is `ekf` with the payload clock in the tower readings). Same seeds, same payload records,
so the two curves are paired. Plots the median and 95th percentile across seeds at each epoch.

    python analysis/base_rover_error.py realistic-with-base-long-outage --runs 50 --out fig.png
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

ALERT_LIMIT_M = 50.0  # TBC: REQ-01/REQ-02 (same placeholder as the estimators)
T1_M = 25.0  # TBC: T1 in systems/plan.md, 95 % horizontal error for >= 300 s after GPS loss


def errors(scenario: str, seed: int) -> dict[str, np.ndarray]:
    """Horizontal error per 0.1 s epoch, with and without the base."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    truth = {t.t_ns: np.asarray(t.pos_enu[:2]) for t in run.truth}
    payload = [m for m in run.measurements if m.receiver == "payload"]
    out = {}
    for name, meas, ref in (("with base", run.measurements, run.reference),
                            ("without base", payload, None)):  # fmt: skip
        est = estimate("ekf-base", meas, origin_llh=spec["origin_llh"], reference=ref)
        out[name] = np.array(
            [
                [(e.t_ns - T0_NS) / 1e9, np.linalg.norm(np.asarray(e.pos_enu[:2]) - truth[e.t_ns])]
                for e in est
                if e.t_ns in truth
            ]
        )
    return out


def gps_loss_s(spec: dict) -> float | None:
    starts = [
        f.get("start_s", 0.0)
        for f in spec.get("faults", [])
        if f["type"] == "outage" and f.get("source", "gnss") == "gnss"
    ]
    return min(starts) if starts else None


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scenario")
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--jobs", type=int, default=5)
    p.add_argument("--out", required=True)
    p.add_argument("--caption", default="")
    args = p.parse_args(argv)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with ProcessPoolExecutor(args.jobs) as pool:
        runs = list(pool.map(errors, [args.scenario] * args.runs, range(args.runs)))
    spec = load(args.scenario)
    loss = gps_loss_s(spec)

    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    colors = {"with base": "#2a78d6", "without base": "#eb6834"}  # categorical slots 1, 2
    for name, color in colors.items():
        n = min(len(r[name]) for r in runs)
        t = runs[0][name][:n, 0]
        err = np.stack([r[name][:n, 1] for r in runs])
        med, p95 = np.median(err, axis=0), np.percentile(err, 95, axis=0)
        ax.plot(t, med, color=color, lw=2, label=f"{name}: median")
        ax.plot(t, p95, color=color, lw=1.2, ls="--", label=f"{name}: 95th percentile")
        if loss is not None:
            window = (t >= loss) & (t < loss + 300)
            pooled = np.percentile(err[:, window], 95)
            print(f"{name}: pooled p95 over the 300 s after GPS loss = {pooled:.1f} m")
    ax.axhline(T1_M, color="#52514e", lw=1, ls=":")
    ax.text(t[0] + 2, T1_M * 1.08, f"T1 {T1_M:.0f} m (TBC)", color="#52514e", fontsize=8)
    ax.axhline(ALERT_LIMIT_M, color="#52514e", lw=1, ls="-.")
    ax.text(t[0] + 2, ALERT_LIMIT_M * 1.08, f"alert limit {ALERT_LIMIT_M:.0f} m (TBC)",
            color="#52514e", fontsize=8)  # fmt: skip
    if loss is not None:
        ax.axvline(loss, color="#52514e", lw=1)
        ax.text(loss + 2, 1.2, "GPS lost", color="#52514e", fontsize=8)
    ax.set_yscale("log")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("horizontal error (m)")
    ax.set_title(f"{args.scenario}, ekf-base, {args.runs} seeds (sim)", fontsize=10)
    ax.grid(True, which="major", color="#e4e3df", lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="lower right", ncol=2)
    if args.caption:
        fig.text(0.01, 0.01, args.caption, fontsize=7, color="#52514e")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
