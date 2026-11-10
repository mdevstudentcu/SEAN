"""Horizontal error over time with and without the residual map (issue #95, ADR-0032).

Runs `ekf` and `ekf-map` over each scenario on the same seeds, so the same records (paired), and
plots the 95th percentile across seeds of the horizontal error at each epoch, one panel per
scenario. `residual-map` has a place-dependent tower error; `gps-outage` has none (the map must
not make it worse).

    python analysis/residual_map.py residual-map gps-outage --runs 50 --out fig.png
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

ESTIMATORS = {"ekf": "#2a78d6", "ekf-map": "#eb6834"}  # categorical slots 1, 2


def errors(scenario: str, seed: int) -> dict[str, np.ndarray]:
    """(t, horizontal error) per 0.1 s epoch for each estimator."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    truth = {t.t_ns: np.asarray(t.pos_enu[:2]) for t in run.truth}
    out = {}
    for name in ESTIMATORS:
        est = estimate(name, run.measurements, origin_llh=spec["origin_llh"])
        out[name] = np.array(
            [
                [(e.t_ns - T0_NS) / 1e9, np.linalg.norm(np.asarray(e.pos_enu[:2]) - truth[e.t_ns])]
                for e in est
                if e.t_ns in truth
            ]
        )
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scenarios", nargs="+")
    p.add_argument("--runs", type=int, default=50)
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
            runs = list(pool.map(errors, [scenario] * args.runs, range(args.runs)))
            for name, color in ESTIMATORS.items():
                k = min(len(r[name]) for r in runs)
                t = runs[0][name][:k, 0]
                err = np.stack([r[name][:k, 1] for r in runs])
                ax.plot(t, np.percentile(err, 95, axis=0), color=color, lw=2, label=name)
            for f in load(scenario).get("faults", []):
                ax.axvspan(
                    f.get("start_s", 0.0), f.get("end_s", t[-1]), color="#888888", alpha=0.12
                )
            ax.set_title(scenario, fontsize=10)
            ax.set_xlabel("time (s); shaded: GPS outage")
            ax.grid(alpha=0.25)
    axes[0].set_ylabel(f"95th percentile horizontal error over {args.runs} seeds (m)")
    axes[0].legend(fontsize=8, loc="upper left")
    if args.caption:
        fig.text(0.01, 0.005, args.caption, fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(args.out)


if __name__ == "__main__":
    main()
