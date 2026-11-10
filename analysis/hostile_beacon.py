"""Horizontal error over time with and without the hostile beacon (issue #93, ADR-0025).

Runs three estimators over each scenario, on the same seeds and so the same records (paired):
`ekf-mhss` (beacon ignored), `ekf-mhss-beacon`, and `ekf-mhss-beacon` with its weight cap off
(an ablation, not an estimator we offer: it shows what guardrail 3 does). Plots the 95th
percentile across seeds of the horizontal error at each epoch, one panel per scenario.

    python analysis/hostile_beacon.py hostile-beacon hostile-beacon-moves --runs 20 --out fig.png
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import numpy as np

from pnt.integrity.mhss import MHSS
from pnt.nav import ekf, estimate
from pnt.sim.scenario import T0_NS, generate, load

NO_CAP = 1e6  # cap_share so large the weight cap never binds (ablation only)
VARIANTS = {
    "no beacon (ekf-mhss)": partial(ekf.run, monitor=MHSS),
    "beacon (ekf-mhss-beacon)": partial(ekf.run, monitor=MHSS, hostile={}),
    "beacon, weight cap off (ablation)": partial(
        ekf.run, monitor=MHSS, hostile={"cap_share": NO_CAP}
    ),
}
COLORS = ("#2a78d6", "#eb6834", "#1baf7a")  # categorical slots 1-3, fixed order


def errors(scenario: str, seed: int) -> dict[str, np.ndarray]:
    """(t, horizontal error, HPL) per 0.1 s epoch for each variant."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    truth = {t.t_ns: np.asarray(t.pos_enu[:2]) for t in run.truth}
    out = {}
    for name, fn in VARIANTS.items():
        est = estimate(fn, run.measurements, origin_llh=spec["origin_llh"])
        out[name] = np.array(
            [
                [
                    (e.t_ns - T0_NS) / 1e9,
                    np.linalg.norm(np.asarray(e.pos_enu[:2]) - truth[e.t_ns]),
                    e.hpl_m,
                ]
                for e in est
                if e.t_ns in truth
            ]
        )
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scenarios", nargs="+")
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--out", required=True)
    p.add_argument("--caption", default="")
    args = p.parse_args(argv)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        1, len(args.scenarios), figsize=(6 * len(args.scenarios), 4.6), dpi=150, sharey=True
    )
    axes = np.atleast_1d(axes)
    with ProcessPoolExecutor(args.jobs) as pool:
        for ax, scenario in zip(axes, args.scenarios, strict=True):
            n = args.runs
            runs = list(pool.map(errors, [scenario] * n, range(n)))
            for (name, color) in zip(VARIANTS, COLORS, strict=True):
                k = min(len(r[name]) for r in runs)
                t = runs[0][name][:k, 0]
                err = np.stack([r[name][:k, 1] for r in runs])
                ax.plot(t, np.percentile(err, 95, axis=0), color=color, lw=2, label=name)
                late = t >= 120
                print(
                    f"{scenario:22s} {name:36s} p95 err after 120 s: "
                    f"{np.percentile(err[:, late], 95):7.1f} m, max {err[:, late].max():7.1f} m"
                )
            for f in load(scenario).get("faults", []):
                ax.axvline(f.get("start_s", 0.0), color="#888888", lw=1, ls="--")
            ax.set_title(scenario, fontsize=10)
            ax.set_xlabel("time (s); dashed: jammer on, then its fault")
            ax.grid(alpha=0.25)
    axes[0].set_ylabel(f"95th percentile horizontal error over {args.runs} seeds (m)")
    axes[0].legend(fontsize=8, loc="upper left")
    if args.caption:
        fig.text(0.01, 0.005, args.caption, fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(args.out)


if __name__ == "__main__":
    main()
