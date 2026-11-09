"""What the T1 miss depends on: one-at-a-time sensitivity of the 300 s outage error (issue #128).

Reads the JSON of `pnt experiment sweep ... --json FILE`, or runs the sweep itself, and draws one
panel per parameter: the mean over paired seeds of `outage_h_p95_300s_m` (p95 horizontal error
over the first 300 s after GPS loss, T1) against the value relative to the committed one.

    pnt experiment sweep realistic-long-outage --estimator ekf-calibrated --runs 10 --json s.json
    python analysis/sensitivity.py --json s.json --out sensitivity.png
    python analysis/sensitivity.py --scenario realistic-long-outage --estimator ekf-calibrated \\
        --runs 10 --jobs 8 --out sensitivity.png

The estimator keeps its own model in every row, so off-baseline rows show how a fixed filter
copes with a different world, not what a filter retuned to it would do.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from pnt.cli import _commit
from pnt.experiments import sweep

T1_M = 25.0  # TBC: T1 in systems/plan.md, 95 % horizontal error for >= 300 s after GPS loss
METRIC = "outage_p95_300s_m"
# Categorical slots 1 and 2 and recessive ink, as in analysis/figures.py
BLUE, ORANGE, INK, GRID = "#2a78d6", "#eb6834", "#52514e", "#e4e3df"


def plot(data: dict, out: Path, caption: str = "") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data["rows"]
    base = next(r for r in rows if r["parameter"].startswith("baseline"))
    params = list(dict.fromkeys(r["parameter"] for r in rows if r is not base))
    ys = [r[METRIC] for r in rows if not math.isnan(r[METRIC])]
    if not ys:
        raise SystemExit(f"no {METRIC} in the sweep: the scenario has no 300 s outage")
    ncol = 3
    nrow = math.ceil(len(params) / ncol)
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(11, 2.9 * nrow), dpi=130, sharey=True, squeeze=False
    )
    lo, hi = min([*ys, T1_M]) / 1.5, max(ys) * 1.5
    for ax, name in zip(axes.flat, params, strict=False):
        pts = sorted(
            [(r["relative"], r[METRIC]) for r in rows if r["parameter"] == name]
            + [(1.0, base[METRIC])]
        )
        ax.plot(*zip(*pts, strict=True), "o-", color=BLUE, lw=2, ms=6, label="swept value")
        ax.plot(1.0, base[METRIC], "o", color=ORANGE, ms=9, label="as committed", zorder=3)
        ax.axhline(T1_M, color=INK, lw=1, ls=":", label=f"T1 target {T1_M:.0f} m (TBC)")
        ax.set_xscale("log", base=2)
        ax.set_xticks([x for x, _ in pts], [f"×{x:.3g}" for x, _ in pts])
        ax.minorticks_off()
        ax.set_yscale("log")
        ax.set_ylim(lo, hi)
        ax.set_title(name, fontsize=9, loc="left")
        ax.set_xlabel("value / committed value", fontsize=8)
        ax.grid(True, which="major", color=GRID, lw=0.6)
        ax.tick_params(labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("p95 horiz. error, 300 s\nafter GPS loss (m)", fontsize=8)
    for ax in list(axes.flat)[len(params) :]:
        ax.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(0.005, 0.965),
        ncol=3,
        fontsize=8,
        frameon=False,
    )
    fig.suptitle(
        f"T1 sensitivity, one parameter at a time: {data['scenario']}, {data['estimator']}, "
        f"{data['runs']} paired seeds, {data['commit']} (sim)",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    if caption:
        fig.text(0.01, 0.005, caption, fontsize=7, color=INK)
    fig.tight_layout(rect=(0, 0.02, 1, 0.93))
    fig.savefig(out)
    print(f"wrote {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--json", help="output of `pnt experiment sweep --json`")
    p.add_argument("--scenario", help="run the default sweep on this scenario instead")
    p.add_argument("--estimator", default="ekf-calibrated")
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--out", required=True)
    p.add_argument("--caption", default="")
    args = p.parse_args(argv)
    if bool(args.json) == bool(args.scenario):
        p.error("give one of --json or --scenario")
    if args.json:
        data = json.loads(Path(args.json).read_text())
    else:
        rows = sweep(args.scenario, None, args.runs, args.estimator, args.jobs)
        data = {
            "scenario": args.scenario,
            "estimator": args.estimator,
            "runs": args.runs,
            "commit": _commit(),
            "rows": rows,
        }
    plot(data, Path(args.out), args.caption)


if __name__ == "__main__":
    main()
