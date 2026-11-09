"""The four results figures for D1 and verification.md (issue #27), for one estimator.

    python analysis/figures.py --estimator ekf --runs 50          (or: just figures ekf 50)

Writes to `--out` (default `analysis/results/figures-<estimator>/`):
- error_after_gps_loss.png: horizontal error (median, 95th percentile) and HPL (median) across
  seeds against time since GPS loss (REQ-01, T1)
- stanford.png: HPL against true error, pooled over every seed of the `--stanford` scenarios
  (REQ-02); the default `realistic` set includes its fault-free `realistic-nominal` entry
- ablation.png: fault-window p95 error with each source removed, paired seeds (REQ-06)
- holdover.png: |clock error| (median, 95th percentile) and time protection level (median)
  against time since GPS loss (REQ-03, T3). Skipped if the estimator has no clock state
- summary.md and summary.json: the numbers behind each figure, the commit and the seeds

Every run is a committed scenario at seeds 0..runs-1, so every variant sees the same draws
(paired, `systems/quality.md`) and every number is reproducible from the commit (REQ-10).
Scoring is `pnt.metrics.score`/`summarize` and the per-epoch series is `pnt.plots.series`, the
same code as `pnt eval` and `pnt plot`.

Real sessions: none exist yet. Their results are a placeholder in summary.md until the first
captures (#30) can be replayed and scored.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pnt import plots
from pnt.cli import _commit
from pnt.experiments import _map
from pnt.metrics import ALERT_LIMIT_M, TIME_ALERT_LIMIT_S, score, summarize
from pnt.nav import ESTIMATORS, estimate
from pnt.sim.scenario import T0_NS, expand, generate, load

REPO = Path(__file__).resolve().parents[1]

# TBC: T1 in systems/plan.md, 95 % horizontal error for >= 300 s after GPS loss (REQ-01)
T1_M = 25.0
T1_WINDOW_S = 300.0
# Communication signals of opportunity (REQ-06, ICD source registry). REQ-06's ablation removes
# all of these together and compares that with removing any single other aid. GNSS is never
# removed: it is what the scenario takes away.
SOOP_SOURCES = frozenset({"lte", "nr", "wifi", "ble", "fm", "adsb", "vor", "leo"})
NEVER_ABLATED = frozenset({"gnss"})

# Categorical slots 1 and 2 and recessive ink, as in analysis/base_rover_error.py
BLUE, ORANGE, INK, GRID = "#2a78d6", "#eb6834", "#52514e", "#e4e3df"


def run_one(scenario: str, seed: int, estimator: str, drop: tuple[str, ...] = ()) -> dict:
    """One seed of one scenario with the sources in `drop` removed (from both receivers)."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    meas = [m for m in run.measurements if m.source not in drop]
    est = list(
        estimate(estimator, meas, origin_llh=spec.get("origin_llh"), reference=run.reference)
    )
    s = plots.series(plots.RunData(scenario, {}, spec, run.truth, {estimator: est}), estimator)
    return {
        "t_s": np.round((np.array([e.t_ns for e in est]) - T0_NS) / 1e9, 1),
        "err": s.err_h.astype(np.float32),
        "hpl": s.hpl.astype(np.float32),
        "clock_err": s.clock_err,
        "time_pl": s.time_pl,
        "metrics": score(est, run.truth, spec, T0_NS),
        "sources": sorted({m.source for m in run.measurements}),
    }


def gps_loss_s(spec: dict) -> float | None:
    """When the scenario first takes GNSS away (an outage of the GNSS source)."""
    starts = [
        f.get("start_s", 0.0)
        for f in spec.get("faults", [])
        if f["type"] == "outage" and f.get("source", "gnss") == "gnss"
    ]
    return min(starts) if starts else None


def stack(runs: list[dict], key: str) -> tuple[np.ndarray, np.ndarray]:
    """(times, seeds x times) of `key` over every run's epochs; nan where a run has none."""
    t = np.unique(np.concatenate([r["t_s"] for r in runs]))
    out = np.full((len(runs), len(t)), np.nan)
    for i, r in enumerate(runs):
        out[i, np.searchsorted(t, r["t_s"])] = r[key]
    return t, out


def _style(ax) -> None:
    ax.grid(True, which="major", color=GRID, lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _caption(fig, text: str) -> None:
    fig.text(0.01, 0.01, text, fontsize=7, color=INK, ha="left", va="bottom")


def fig_error(runs: list[dict], loss: float, title: str, caption: str):
    import matplotlib.pyplot as plt

    t, err = stack(runs, "err")
    _, hpl = stack(runs, "hpl")
    keep = t >= loss - 30
    x = t[keep] - loss
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    ax.plot(x, np.nanmedian(err[:, keep], axis=0), color=BLUE, lw=2, label="error: median")
    ax.plot(
        x,
        np.nanpercentile(err[:, keep], 95, axis=0),
        color=BLUE,
        lw=1.2,
        ls="--",
        label="error: 95th percentile",
    )
    ax.plot(x, np.nanmedian(hpl[:, keep], axis=0), color=ORANGE, lw=2, label="HPL: median")
    for y, text, ls in (
        (T1_M, f"T1 {T1_M:g} m (TBC)", ":"),
        (ALERT_LIMIT_M, f"alert limit {ALERT_LIMIT_M:g} m (TBC)", "-."),
    ):
        ax.axhline(y, color=INK, lw=1, ls=ls)
        ax.text(x[-1], y * 1.08, text, color=INK, fontsize=8, ha="right")
    ax.axvline(0, color=INK, lw=1)
    ax.text(2, 1.2, "GPS lost", color=INK, fontsize=8)
    ax.set_yscale("log")
    ax.set(xlabel="time since GPS loss (s)", ylabel="metres")
    ax.set_title(title, fontsize=10)
    _style(ax)
    ax.legend(fontsize=8, frameon=False, loc="lower right", ncol=3)
    _caption(fig, caption)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def fig_holdover(runs: list[dict], loss: float, title: str, caption: str):
    import matplotlib.pyplot as plt

    t, cerr = stack(runs, "clock_err")
    _, tpl = stack(runs, "time_pl")
    if np.isnan(cerr).all():
        return None
    keep = t >= loss - 30
    x = t[keep] - loss
    us = np.abs(cerr[:, keep]) * 1e6
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    ax.plot(x, np.nanmedian(us, axis=0), color=BLUE, lw=2, label="|clock error|: median")
    ax.plot(
        x,
        np.nanpercentile(us, 95, axis=0),
        color=BLUE,
        lw=1.2,
        ls="--",
        label="|clock error|: 95th percentile",
    )
    ax.plot(
        x, np.nanmedian(tpl[:, keep], axis=0) * 1e6, color=ORANGE, lw=2, label="time PL: median"
    )
    al = TIME_ALERT_LIMIT_S * 1e6
    ax.axhline(al, color=INK, lw=1, ls="-.")
    ax.text(
        x[-1],
        al * 1.08,
        f"T3 / time alert limit {al:g} µs (TBC)",
        color=INK,
        fontsize=8,
        ha="right",
    )
    ax.axvline(0, color=INK, lw=1)
    ax.set_yscale("log")
    ax.set(xlabel="time since GPS loss (s)", ylabel="µs")
    ax.set_title(title, fontsize=10)
    _style(ax)
    ax.legend(fontsize=8, frameon=False, loc="lower right", ncol=3)
    _caption(fig, caption)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def fig_ablation(rows: list[dict], title: str, caption: str):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 1.6 + 0.55 * len(rows)), dpi=150)
    y = np.arange(len(rows))[::-1]
    mean = np.array([r["mean_m"] for r in rows])
    se = np.array([r["se_m"] for r in rows])
    ax.barh(
        y,
        mean,
        xerr=se,
        height=0.6,
        color=BLUE,
        ecolor=INK,
        capsize=3,
        label="mean of per-run p95 (± standard error)",
    )
    ax.plot([r["worst_m"] for r in rows], y, "o", ms=6, mfc="none", mec=INK, label="worst run")
    for yi, r in zip(y, rows, strict=True):
        ax.text(r["mean_m"], yi + 0.33, f" {r['mean_m']:.1f} m", fontsize=8, color=INK)
    ax.set_yticks(y, [r["variant"] for r in rows])
    ax.axvline(T1_M, color=INK, lw=1, ls=":", label=f"T1 {T1_M:g} m (TBC)")
    ax.set_xscale("log")
    ax.set_xlabel("horizontal error p95 in the fault window (m)")
    ax.set_title(title, fontsize=10)
    _style(ax)
    ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3)
    _caption(fig, caption)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def ablation_variants(sources: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    """(label, sources dropped): all, all SoOP together, then each other aid on its own."""
    soop = tuple(s for s in sources if s in SOOP_SOURCES)
    others = [s for s in sources if s not in SOOP_SOURCES and s not in NEVER_ABLATED]
    out = [("all sources", ())]
    if soop:
        out.append((f"no SoOP ({', '.join(soop)})", soop))
    if len(soop) > 1:
        out += [(f"no {s}", (s,)) for s in soop]
    out += [(f"no {s}", (s,)) for s in others]
    return out


def ablation_rows(variants, metrics: dict) -> list[dict]:
    """Per variant: mean, standard error and worst of the per-run fault-window p95, and the
    paired difference against all sources (same seeds)."""
    ref = np.array([m.fault_h_p95_m for m in metrics[()]])
    rows = []
    for label, drop in variants:
        v = np.array([m.fault_h_p95_m for m in metrics[drop]])
        d = v - ref
        rows.append(
            {
                "variant": label,
                "dropped": list(drop),
                "mean_m": float(np.mean(v)),
                "se_m": float(np.std(v, ddof=1) / np.sqrt(len(v))) if len(v) > 1 else 0.0,
                "worst_m": float(np.max(v)),
                "added_m": float(np.mean(d)),
                "added_se_m": float(np.std(d, ddof=1) / np.sqrt(len(d))) if len(d) > 1 else 0.0,
            }
        )
    return rows


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--estimator", choices=sorted(ESTIMATORS), default="ekf")
    p.add_argument("--runs", type=int, default=50, help="seeds 0..runs-1")
    p.add_argument("--jobs", type=int, help="worker processes (default: every core)")
    p.add_argument(
        "--outage",
        default="realistic-long-outage",
        help="scenario for error after GPS loss, the ablation and holdover",
    )
    p.add_argument(
        "--stanford",
        nargs="+",
        default=["realistic"],
        help="scenarios or sets pooled into the Stanford plot",
    )
    p.add_argument("--out", help="default: analysis/results/figures-<estimator>")
    args = p.parse_args(argv)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    commit = _commit()
    out = (
        Path(args.out) if args.out else REPO / "analysis" / "results" / f"figures-{args.estimator}"
    )
    out.mkdir(parents=True, exist_ok=True)
    seeds = list(range(args.runs))
    spec = load(args.outage)
    loss = gps_loss_s(spec)
    if loss is None:
        raise SystemExit(f"{args.outage} never takes GNSS away; pick an outage scenario")
    stanford = [n for name in args.stanford for n in expand(name)]
    sources = run_one(args.outage, 0, args.estimator)["sources"]
    variants = ablation_variants(sources)

    # Every (scenario, sources dropped) needed, each over the same seeds, run once
    keys = [(args.outage, drop) for _, drop in variants]
    keys += [(n, ()) for n in stanford if (n, ()) not in keys]
    tasks = [(scn, s, args.estimator, drop) for scn, drop in keys for s in seeds]
    results = _map(run_one, tasks, args.jobs)
    by_key = {k: results[i * len(seeds) : (i + 1) * len(seeds)] for i, k in enumerate(keys)}
    base = by_key[(args.outage, ())]

    kind = "sim; model status in systems/verification.md, Sim validity"
    seeds_txt = f"seeds 0-{args.runs - 1}"

    def cap(scn: str) -> str:
        return f"{scn} · estimator {args.estimator} · {seeds_txt} · commit {commit} · {kind}"

    written = []

    def save(fig, name: str) -> None:
        if fig is None:
            return
        path = out / name
        fig.savefig(path)
        plt.close(fig)
        written.append(path)

    # 1. Error after GPS loss
    save(
        fig_error(
            base,
            loss,
            f"Horizontal error after GPS loss: {args.outage}, {args.estimator}, {args.runs} seeds",
            cap(args.outage),
        ),
        "error_after_gps_loss.png",
    )
    t, err = stack(base, "err")
    window = (t >= loss) & (t < loss + T1_WINDOW_S)
    t1_pooled = float(np.nanpercentile(err[:, window], 95))
    t1_runs = int(np.sum(np.nanpercentile(err[:, window], 95, axis=1) <= T1_M))

    # 2. Stanford plot, pooled over every scenario in --stanford (fault-free entries included)
    err_all = np.concatenate([r["err"] for n in stanford for r in by_key[(n, ())]])
    hpl_all = np.concatenate([r["hpl"] for n in stanford for r in by_key[(n, ())]])
    pooled = f"{len(stanford)} scenarios ({', '.join(args.stanford)})"
    # plots._stanford is `pnt plot`'s own Stanford figure; reused so both count regions alike
    fig = plots._stanford(
        f"{seeds_txt} · commit {commit}\n{pooled}\n{kind}",
        err_all,
        hpl_all,
        ALERT_LIMIT_M,
        "m",
        "HPL",
        (
            "horizontal error",
            f"Stanford plot: {args.estimator}, AL {ALERT_LIMIT_M:g} m (TBC)\n{pooled}",
        ),
    )
    fig.set_size_inches(7.5, 7)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, "stanford.png")
    stanford_rows = []
    for n in stanford:
        rs = by_key[(n, ())]
        c = plots.stanford_counts(
            np.concatenate([r["err"] for r in rs]),
            np.concatenate([r["hpl"] for r in rs]),
            ALERT_LIMIT_M,
        )
        stanford_rows.append({"scenario": n, **c})

    # 3. Ablation (REQ-06)
    rows = ablation_rows(
        variants,
        {drop: [r["metrics"] for r in by_key[(args.outage, drop)]] for _, drop in variants},
    )
    save(
        fig_ablation(
            rows,
            f"Ablation (REQ-06): {args.outage}, {args.estimator}, {args.runs} paired seeds",
            cap(args.outage),
        ),
        "ablation.png",
    )

    # 4. Timing holdover
    hold = fig_holdover(
        base,
        loss,
        f"Clock error after GPS loss: {args.outage}, {args.estimator}, {args.runs} seeds",
        cap(args.outage),
    )
    save(hold, "holdover.png")

    outage_summary = summarize([r["metrics"] for r in base])
    summary = {
        "commit": commit,
        "estimator": args.estimator,
        "runs": args.runs,
        "outage_scenario": args.outage,
        "gps_loss_s": loss,
        "t1": {
            "pooled_p95_m": t1_pooled,
            "window_s": T1_WINDOW_S,
            "target_m": T1_M,
            "runs_meeting": t1_runs,
        },
        "outage_summary": outage_summary,
        "ablation": rows,
        "stanford": stanford_rows,
        "holdover": None
        if hold is None
        else {
            k: outage_summary[k]
            for k in (
                "time_err_p95_us",
                "fault_time_err_p95_us",
                "time_1sigma_bound_frac",
                "min_time_pl_bound_frac",
            )
        },
        "real_sessions": None,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    (out / "summary.md").write_text(markdown(summary, written, out))
    for w in written + [out / "summary.md", out / "summary.json"]:
        print(f"wrote {w.relative_to(REPO) if w.is_relative_to(REPO) else w}")


def markdown(s: dict, written: list[Path], out: Path) -> str:
    """The numbers behind the figures, in the form systems/verification.md takes them."""
    lines = [
        f"# Results figures: `{s['estimator']}`",
        "",
        f"Commit `{s['commit']}`, seeds 0-{s['runs'] - 1}, sim (each model's status is in the "
        "*Sim validity* table of `systems/verification.md`). Regenerate with `just figures "
        f"{s['estimator']} {s['runs']}`.",
        "",
        "Figures: " + ", ".join(f"`{w.name}`" for w in written),
        "",
        f"## Error after GPS loss (REQ-01): `{s['outage_scenario']}`",
        "",
        f"- p95 horizontal error over the {s['t1']['window_s']:g} s after GPS loss, pooled over "
        f"seeds: {s['t1']['pooled_p95_m']:.1f} m (T1 target {s['t1']['target_m']:g} m, TBC)",
        f"- runs whose own p95 meets T1: {s['t1']['runs_meeting']} of {s['runs']}",
        f"- worst run's maximum error in the fault window: "
        f"{s['outage_summary']['worst_fault_h_max_m']:.1f} m",
        "",
        "## Ablation (REQ-06)",
        "",
        "| Variant | Mean p95 (m) | ± SE | Worst run (m) | Added vs all sources (paired, m) |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {r['variant']} | {r['mean_m']:.1f} | {r['se_m']:.1f} | {r['worst_m']:.1f} "
        f"| {r['added_m']:+.1f} ± {r['added_se_m']:.1f} |"
        for r in s["ablation"]
    ]
    lines += [
        "",
        "## Stanford plot (REQ-02), per scenario",
        "",
        "| Scenario | Epochs | Nominal | Misleading | Hazardous | Unavailable |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| `{r['scenario']}` | {r['epochs']} | {r['nominal']} | {r['misleading']} "
        f"| {r['hazardous']} | {r['unavailable']} |"
        for r in s["stanford"]
    ]
    lines += ["", "## Timing holdover (REQ-03)", ""]
    h = s["holdover"]
    if h is None:
        lines.append(f"`{s['estimator']}` does not estimate the clock: no holdover figure.")
    else:
        lines += [
            f"- clock error p95 in the fault window: {h['fault_time_err_p95_us']:.3f} µs "
            "(T3: 1.5 µs after 10 min, TBC; the default realistic-long-outage lasts only 300 s)",
            f"- 1-sigma bounds the clock error in {100 * h['time_1sigma_bound_frac']:.1f} % of "
            "epochs (mean over runs; T3 asks for ≥ 68 %)",
            f"- time PL bounds the clock error in {100 * h['min_time_pl_bound_frac']:.1f} % of "
            "epochs in the worst run",
        ]
    lines += [
        "",
        "## Real sessions",
        "",
        "**Placeholder: no real session has been recorded yet.** When the first captures exist "
        "(#30), their replayed results (`pnt replay <session>`, named session plus commit, "
        "REQ-10) go here beside the sim numbers above.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
