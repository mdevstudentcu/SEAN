"""How `ekf-calibrated` copes when the world departs from its calibrated error model (#118).

`ekf-calibrated` takes its multipath, told-position and clock values from the `realistic` set
(`nav.ekf.CALIBRATED`), so its consistency on that set is mostly self-consistency. Here the
environment changes while the filter keeps its values, one departure at a time, and `ekf` and
`ekf-calibrated` run on the same draws (both estimators on one generated run per seed):

- multipath size x0.5, x2, x4 and correlation time x0.2, x5 (the sim's Gauss-Markov model)
- multipath model form, same size: white; random walk with the Gauss-Markov's short-term
  increments (no mean reversion); bias steps (per-tower constant, redrawn at Poisson times with
  mean interval tau, so the same autocorrelation as the Gauss-Markov but a jumpy path)
- tower clock frequency wander (builder and site `drift_rw_mps`) x5
- told tower position error x3

Seeds. Reported results use REPORT_SEEDS (0-49, as `pnt eval`). Anything tuned from this study
(a change to CALIBRATED) is chosen on TUNING_SEEDS (1000-1049) and only then reported on
REPORT_SEEDS, so the reported numbers are not fitted to their own draws. `--seed-start` picks
the block; the JSON records which seeds ran.

    python analysis/model_mismatch.py --runs 50 --jobs 8 --json mismatch.json --out mismatch.png
    python analysis/model_mismatch.py --json mismatch.json --out mismatch.png   # re-plot only
    python analysis/model_mismatch.py --runs 50 --seed-start 1000 \\
        --config '{"multipath_ratio": 1.5}' --json tune.json   # a candidate, on tuning seeds

Sim only, placeholder models (ADR-0015): this ranks how fragile the calibrated values are, it
does not measure the real world.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.experiments import _map, get_param, set_param
from pnt.metrics import score, summarize
from pnt.nav import configured, estimate
from pnt.nav.ekf import run_calibrated
from pnt.sim.scenario import T0_NS, generate, load

REPORT_SEEDS = range(0, 50)  # seeds behind every reported number (paired with `pnt eval`)
TUNING_SEEDS = range(1000, 1050)  # seeds any CALIBRATED change is chosen on; never reported
SCENARIO = "realistic-long-outage"  # the calibrated set, GPS lost for the last 300 s
ESTIMATORS = ("ekf", "ekf-calibrated")
MP = "sources.lte.multipath"
CLOCK_RW = ("tower_clocks.builder.drift_rw_mps", "tower_clocks.site.drift_rw_mps")
TOLD_POS = "sources.lte.told_position_sigma_m"
FORMS = ("white", "random-walk", "bias-step")
INJECT_STREAM = 118  # the injected multipath draws from its own stream: rng([INJECT_STREAM, seed])

# (family, label, factor, change). change: ("scale", paths, factor) or ("form", name)
CASES: tuple[tuple[str, str, float, tuple], ...] = (
    ("as committed", "as committed", 1.0, ("scale", (), 1.0)),
    *(
        ("multipath sigma", f"multipath sigma x{k:g}", k, ("scale", (f"{MP}.sigma_m",), k))
        for k in (0.5, 2.0, 4.0)
    ),
    *(
        ("multipath tau", f"multipath tau x{k:g}", k, ("scale", (f"{MP}.tau_s",), k))
        for k in (0.2, 5.0)
    ),
    *(("multipath form", f"multipath {f}", 1.0, ("form", f)) for f in FORMS),
    ("tower clock wander", "tower clock drift rw x5", 5.0, ("scale", CLOCK_RW, 5.0)),
    ("told position", "told position sigma x3", 3.0, ("scale", (TOLD_POS,), 3.0)),
)


def world(base: dict, change: tuple) -> tuple[dict, dict | None]:
    """The scenario for one case, and the multipath to inject after generation (None: the sim's
    own Gauss-Markov). A form case removes the sim's multipath and injects its own, same size."""
    if change[0] == "scale":
        spec = base
        for path in change[1]:
            spec = set_param(spec, path, get_param(base, path) * change[2])
        return spec, None
    spec = copy.deepcopy(base)
    mp = spec["sources"]["lte"].pop("multipath")
    return spec, {"form": change[1], "sigma_m": mp["sigma_m"], "tau_s": mp["tau_s"]}


def multipath(rng, t_s: np.ndarray, form: str, sigma_m: float, tau_s: float) -> np.ndarray:
    """One tower's multipath (m) at times t_s, in one of FORMS, with steady size sigma_m."""
    n = len(t_s)
    if form == "white":
        return rng.normal(0.0, sigma_m, n)
    dt = np.diff(t_s, prepend=t_s[0])
    if form == "random-walk":  # the Gauss-Markov's increments over short dt, never pulled back
        steps = rng.normal(0.0, 1.0, n) * sigma_m * np.sqrt(2.0 * dt / tau_s)
        return rng.normal(0.0, sigma_m) + np.cumsum(steps)
    if form == "bias-step":  # redrawn with probability 1 - exp(-dt/tau) each sample
        redraw = rng.random(n) < -np.expm1(-dt / tau_s)
        redraw[0] = True
        levels = rng.normal(0.0, sigma_m, int(redraw.sum()))
        return levels[np.cumsum(redraw) - 1]
    raise ValueError(f"multipath form must be one of {FORMS}, not {form!r}")


def inject(measurements: list, cfg: dict, seed: int) -> list:
    """`measurements` with multipath added to every LTE pseudorange, per (receiver, emitter)."""
    rng = np.random.default_rng([INJECT_STREAM, seed])
    keys = sorted(
        {(m.receiver, m.emitter) for m in measurements if m.source == "lte" and m.kind == "pseudorange"}
    )
    add: dict[tuple[str, str, int], float] = {}
    for key in keys:
        ts = np.array(
            sorted(m.t_ns for m in measurements if (m.receiver, m.emitter) == key), np.int64
        )
        err = multipath(rng, (ts - ts[0]) / 1e9, cfg["form"], cfg["sigma_m"], cfg["tau_s"])
        add.update({(*key, int(t)): float(e) for t, e in zip(ts, err, strict=True)})
    out = []
    for m in measurements:
        e = add.get((m.receiver, m.emitter, m.t_ns))
        if e is None or m.source != "lte" or m.kind != "pseudorange":
            out.append(m)
        else:
            out.append(m.__class__(**{**_fields(m), "value": (m.value[0] + e, *m.value[1:])}))
    return out


def _fields(m) -> dict:
    return {k: getattr(m, k) for k in m.__struct_fields__}


def _estimator(name: str, config: dict | None):
    """A registry name, or `ekf-calibrated` with `config` over CALIBRATED."""
    if name == "ekf-calibrated" and config:
        return configured(run_calibrated, **config)
    return name


def case_metrics(spec: dict, inj: dict | None, seed: int, config: dict | None) -> dict:
    """Every estimator's metrics on one generated run: the same draws for each (paired)."""
    run = generate(spec, seed=seed)
    meas = inject(run.measurements, inj, seed) if inj else run.measurements
    out = {}
    for name in ESTIMATORS:
        est = estimate(
            _estimator(name, config),
            meas,
            origin_llh=spec.get("origin_llh"),
            reference=run.reference,
        )
        out[name] = score(list(est), run.truth, spec, T0_NS)
    return out


ROW_KEYS = {  # reported name -> summarize() key
    "fault_p95_m": "fault_h_p95_m",
    "hpl_bound_worst": "min_hpl_bound_frac",
    "nees": "h_nees_mean",
    "misleading": "misleading_epochs",
    "hazardous": "hazardous_epochs",
    "time_misleading": "time_misleading_epochs",
}


def study(
    scenario: str = SCENARIO,
    seeds=REPORT_SEEDS,
    config: dict | None = None,
    cases=CASES,
    jobs: int | None = 1,
) -> list[dict]:
    """One row per (case, estimator). Counts are per run (mean over seeds); `hpl_bound_worst` is
    the worst run's fraction of epochs with HPL >= error. Every case runs the same seeds."""
    base = load(scenario)
    worlds = [world(base, c[3]) for c in cases]
    seeds = list(seeds)
    tasks = [(spec, inj, s, config) for spec, inj in worlds for s in seeds]
    results = _map(case_metrics, tasks, jobs)
    rows = []
    for i, (family, label, factor, _) in enumerate(cases):
        runs = results[i * len(seeds) : (i + 1) * len(seeds)]
        for name in ESTIMATORS:
            s = summarize([r[name] for r in runs])
            rows.append(
                {"family": family, "case": label, "factor": factor, "estimator": name}
                | {k: s[v] for k, v in ROW_KEYS.items()}
            )
    return rows


def markdown(rows: list[dict]) -> str:
    """Rows as a Markdown table, one line per case with both estimators side by side."""
    head = (
        "| case | fault p95 m (ekf / cal) | worst-run HPL bound | NEES "
        "| misleading /run | hazardous /run | time-misleading /run |"
    )
    lines = [head, "| --- | --- | --- | --- | --- | --- | --- |"]
    by_case: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_case.setdefault(r["case"], {})[r["estimator"]] = r
    for case, pair in by_case.items():
        a, b = pair["ekf"], pair["ekf-calibrated"]
        cell = {
            "fault_p95_m": lambda v: f"{v:.0f}",
            "hpl_bound_worst": lambda v: f"{100 * v:.1f} %",
            "nees": lambda v: f"{v:.1f}",
            "misleading": lambda v: f"{v:.1f}",
            "hazardous": lambda v: f"{v:.1f}",
            "time_misleading": lambda v: f"{v:.1f}",
        }
        parts = [f"{f(a[k])} / {f(b[k])}" for k, f in cell.items()]
        lines.append(f"| {case} | " + " | ".join(parts) + " |")
    return "\n".join(lines)


# Categorical slots 1 and 2 and recessive ink, as in analysis/figures.py
BLUE, ORANGE, INK, GRID = "#2a78d6", "#eb6834", "#52514e", "#e4e3df"
COLORS = {"ekf": BLUE, "ekf-calibrated": ORANGE}


def plot(data: dict, out: Path) -> None:
    """Two rows (fault-window p95, worst-run HPL bound rate) by one column per case; each panel
    has ekf and ekf-calibrated side by side, the committed world as a reference line."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data["rows"]
    cases = list(dict.fromkeys(r["case"] for r in rows))
    get = {(r["case"], r["estimator"]): r for r in rows}
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.4), dpi=130, sharex=True)
    x = np.arange(len(cases))
    w = 0.38
    metrics = (
        ("fault_p95_m", "fault-window p95\nhoriz. error (m, log)", True),
        ("hpl_bound_worst", "worst run: epochs\nwith HPL >= error (%)", False),
    )
    for ax, (key, label, log) in zip(axes, metrics, strict=True):
        for j, name in enumerate(ESTIMATORS):
            ys = [get[(c, name)][key] * (1 if log else 100) for c in cases]
            ax.bar(x + (j - 0.5) * w, ys, w * 0.92, color=COLORS[name], label=name)
            ref = get[(cases[0], name)][key] * (1 if log else 100)
            ax.axhline(ref, color=COLORS[name], lw=1, ls=":", zorder=0)
        if log:
            ax.set_yscale("log")
        else:
            ax.set_ylim(0, 105)
            ax.axhline(100, color=INK, lw=0.8)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(True, axis="y", which="major", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[1].set_xticks(x, [c.replace("multipath ", "multipath\n") for c in cases], fontsize=8)
    for t in axes[1].get_xticklabels():
        t.set_rotation(30)
        t.set_ha("right")
    axes[0].legend(fontsize=8, frameon=False, ncol=2, loc="upper left")
    seeds = data["seeds"]
    cfg = f", ekf-calibrated config {data['config']}" if data.get("config") else ""
    fig.suptitle(
        f"Environment departs from ekf-calibrated's model: {data['scenario']}, seeds "
        f"{seeds[0]}-{seeds[-1]} ({len(seeds)} paired runs), {data['commit']} (sim, placeholder "
        f"models){cfg}",
        fontsize=9,
        x=0.01,
        ha="left",
    )
    fig.text(
        0.01,
        0.005,
        "Dotted lines: each estimator as committed. Filter values stay fixed in every case.",
        fontsize=7,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(out)
    print(f"wrote {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--scenario", default=SCENARIO)
    p.add_argument("--runs", type=int, help="run this many seeds (omit to re-plot --json)")
    p.add_argument("--seed-start", type=int, default=REPORT_SEEDS.start)
    p.add_argument("--config", help="JSON overrides of ekf-calibrated's CALIBRATED values")
    p.add_argument("--cases", help="comma-separated substrings: run only matching cases")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--json", help="write results here (or read them, without --runs)")
    p.add_argument("--out", help="figure path")
    args = p.parse_args(argv)
    if args.runs is None:
        if not (args.json and args.out):
            p.error("without --runs, give --json to read and --out to plot")
        data = json.loads(Path(args.json).read_text())
    else:
        cases = CASES
        if args.cases:
            keys = args.cases.split(",")
            cases = tuple(c for c in CASES if any(k in c[1] for k in keys))
        config = json.loads(args.config) if args.config else None
        seeds = list(range(args.seed_start, args.seed_start + args.runs))
        rows = study(args.scenario, seeds, config, cases, args.jobs)
        data = {
            "scenario": args.scenario,
            "seeds": seeds,
            "config": config,
            "commit": _commit(),
            "rows": rows,
        }
        print(
            f"{args.scenario}, seeds {seeds[0]}-{seeds[-1]}, {data['commit']}"
            + (f", config {config}" if config else "")
        )
        print(markdown(rows))
        if args.json:
            Path(args.json).write_text(json.dumps(data, indent=2))
    if args.out:
        plot(data, Path(args.out))


if __name__ == "__main__":
    main()
