"""`ekf-calibrated-measured` against `ekf` and `ekf-calibrated`, paired, and its mismatch (#118).

`ekf-calibrated` takes its multipath, told-position and clock values from the `realistic` set
(`nav.ekf.CALIBRATED`), so its consistency there is self-consistency. `ekf-calibrated-measured`
(`nav.ekf.CALIBRATED_MEASURED`, ADR-0043 Proposed) keeps the calibrated model but takes no value
from a sim set: its correlated LTE error is ADR-0036's, measured on the 20261110 static sessions,
and the rest are the filter's own defaults or TBD (see `CALIBRATED_MEASURED`).

`paired`: the three estimators on the same generated run per seed (SCENARIOS x REPORT_SEEDS):
- NEES: horizontal, 2 if honest. The mean over every epoch of every run, and over the T1 window.
- T1 (ADR-0034 amendment): at each second after GPS loss the 95th percentile of horizontal error
  across the runs; the worst second of the window decides. The window is 300 s (T1) where the
  outage lasts that long, else the outage (ottawa-sionna: 120 s, the fallback's window).
- HPL bound rate: fraction of epochs with HPL >= error; the mean run and the worst run, over the
  whole run and over the T1 window.
- Misleading epochs: error > HPL while not flagged unsafe, per run (mean) and in all runs.
- Paired wins: seeds on which `ekf-calibrated-measured`'s T1-window p95 is below the other's.

`mismatch`: on MISMATCH_SCENARIO, `ekf-calibrated-measured`'s own model changed (FILTER_CASES:
correlation time, model form and size), and the world's multipath changed under both calibrated
filters (WORLD_CASES from `model_mismatch.py`: correlation time and form, same size).

Seeds. Reported numbers use REPORT_SEEDS (0-49, as `pnt eval`). TUNING_SEEDS (1000-1049, as
`model_mismatch.py`) are for trying values; none of CALIBRATED_MEASURED was chosen on any seed
(each comes from ADR-0036 or a default), and runs on TUNING_SEEDS are never reported.

    python analysis/calibrated_measured.py paired --runs 50 --jobs 3 --json paired.json
    python analysis/calibrated_measured.py mismatch --runs 50 --jobs 3 --json mismatch.json
    python analysis/calibrated_measured.py plot --json paired.json --mismatch mismatch.json \\
        --out-dir analysis/results/calibrated-measured

Sim only, placeholder environments (ADR-0015): the filter's values are measured, the worlds are
not, so this ranks how the filters cope with the sets, not with the real world.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.experiments import _map
from pnt.metrics import gps_loss, score
from pnt.nav import configured, estimate
from pnt.nav.ekf import CALIBRATED_MEASURED, run_calibrated_measured
from pnt.sim.scenario import T0_NS, generate, load

REPORT_SEEDS = range(0, 50)  # seeds behind every reported number
TUNING_SEEDS = range(1000, 1050)  # seeds for trying values; never reported
SCENARIOS = ("realistic-long-outage", "worst-long-outage", "ottawa-sionna")
ESTIMATORS = ("ekf", "ekf-calibrated", "ekf-calibrated-measured")
MEASURED = "ekf-calibrated-measured"
T1_WINDOW_S = 300  # s after GPS loss (ADR-0034)
T1_M, T1_FALLBACK_M = 25.0, 50.0  # ADR-0034: requirement, fallback (fallback window 120 s)
MISMATCH_SCENARIO = "realistic-long-outage"

_MM = Path(__file__).with_name("model_mismatch.py")


def _model_mismatch():
    """`analysis/model_mismatch.py` as a module (its worlds and injected multipath forms)."""
    if "model_mismatch" not in sys.modules:
        spec = importlib.util.spec_from_file_location("model_mismatch", _MM)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["model_mismatch"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["model_mismatch"]


# ekf-calibrated-measured's own model departs from ADR-0036, one change at a time:
# (family, label, config over CALIBRATED_MEASURED)
_TAU, _SIG = CALIBRATED_MEASURED["multipath_tau_s"], CALIBRATED_MEASURED["multipath_sigma_m"]
FILTER_CASES: tuple[tuple[str, str, dict], ...] = (
    ("as committed", "as committed (10 m, 3 s)", {}),
    *(
        ("corr. time", f"tau x{k:g} ({_TAU * k:g} s)", {"multipath_tau_s": _TAU * k})
        for k in (0.2, 3.0, 10.0)
    ),
    ("model form", "white only (no corr. state)", {"multipath_sigma_m": 0.0}),
    (
        "model form",
        "+ told-position state 100 m",
        {"tower_position_sigma_m": 100.0},  # the realistic set's value: a sensitivity only
    ),
    *(
        ("corr. size", f"sigma x{k:g} ({_SIG * k:g} m)", {"multipath_sigma_m": _SIG * k})
        for k in (0.5, 3.0)
    ),
)
WORLD_KEYS = ("as committed", "multipath tau", "multipath white", "random-walk", "bias-step")
WORLD_ESTIMATORS = ("ekf-calibrated", MEASURED)


def t1_window(spec: dict) -> tuple[int, int] | None:
    """(GPS loss, window length in whole seconds): T1_WINDOW_S, or less if the outage or the run
    ends first. None if the scenario never loses GPS."""
    loss = gps_loss(spec, T0_NS)
    if loss is None:
        return None
    start, end = loss
    run_end = T0_NS + int(round(float(spec["duration_s"]) * 1e9))
    end = run_end if end is None else min(end, run_end)
    return start, int(min(T1_WINDOW_S, (end - start) // 1_000_000_000))


def per_run(estimates, truth, spec: dict) -> dict:
    """One run's numbers: `score`'s, plus the horizontal error at each whole second of the T1
    window (for the across-run percentile) and NEES and HPL bound over that window."""
    m = score(estimates, truth, spec, T0_NS)
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    t = np.array([e.t_ns for e, _ in pairs])
    eh = np.array([np.subtract(e.pos_enu, g.pos_enu)[:2] for e, g in pairs])
    err = np.hypot(eh[:, 0], eh[:, 1])
    cov = np.array([np.reshape(e.pos_cov, (3, 3))[:2, :2] for e, _ in pairs])
    nees = np.einsum("ij,ij->i", eh, np.linalg.solve(cov, eh[..., None])[..., 0])
    hpl = np.array([e.hpl_m for e, _ in pairs])
    out = {
        "nees": float(np.mean(nees)),
        "hpl_bound": m.hpl_bound_frac,
        "misleading": m.misleading_epochs,
        "hazardous": m.hazardous_epochs,
        "time_misleading": m.time_misleading_epochs,
        "fault_p95_m": m.fault_h_p95_m,
    }
    win = t1_window(spec)
    if win is not None:
        start, n_s = win
        w = (t >= start) & (t < start + n_s * 1_000_000_000)
        secs = start + np.arange(n_s, dtype=np.int64) * 1_000_000_000
        idx = np.searchsorted(t, secs)
        if (idx >= len(t)).any() or (t[np.minimum(idx, len(t) - 1)] != secs).any():
            raise ValueError("an estimate is missing at a whole second of the T1 window")
        out |= {
            "err_per_s": err[idx].tolist(),
            "win_p95_m": float(np.percentile(err[w], 95)),
            "win_nees": float(np.mean(nees[w])),
            "win_hpl_bound": float(np.mean(hpl[w] >= err[w])),
        }
    return out


def _estimator(name: str, config: dict | None):
    if name == MEASURED and config:
        return configured(run_calibrated_measured, **config)
    return name


def paired_run(spec: dict, seed: int, estimators, config=None, inj=None) -> dict:
    """Every estimator on one generated run (the same draws for each)."""
    run = generate(spec, seed=seed)
    meas = run.measurements
    if inj:
        meas = _model_mismatch().inject(meas, inj, seed)
    out = {}
    for name in estimators:
        est = estimate(
            _estimator(name, config),
            meas,
            origin_llh=spec.get("origin_llh"),
            reference=run.reference,
        )
        out[name] = per_run(list(est), run.truth, spec)
    return out


def aggregate(runs: list[dict], seeds: list[int]) -> dict:
    """Across runs of one estimator: the T1 statistic and the means and worst cases."""
    a = {
        "runs": len(runs),
        "nees_mean": float(np.mean([r["nees"] for r in runs])),
        "nees_median_run": float(np.median([r["nees"] for r in runs])),
        "hpl_bound_mean": float(np.mean([r["hpl_bound"] for r in runs])),
        "hpl_bound_worst": float(min(r["hpl_bound"] for r in runs)),
        "misleading_mean": float(np.mean([r["misleading"] for r in runs])),
        "misleading_total": int(sum(r["misleading"] for r in runs)),
        "hazardous_total": int(sum(r["hazardous"] for r in runs)),
        "time_misleading_mean": float(np.mean([r["time_misleading"] for r in runs])),
        "fault_p95_mean_m": float(np.nanmean([r["fault_p95_m"] for r in runs])),
    }
    if "err_per_s" in runs[0]:
        err = np.array([r["err_per_s"] for r in runs])  # runs x seconds
        curve = np.percentile(err, 95, axis=0)
        a |= {
            "t1_window_s": int(err.shape[1]),
            "t1_worst_p95_m": float(curve.max()),
            "t1_worst_second": int(curve.argmax()),
            "t1_p95_curve_m": [round(float(v), 2) for v in curve],
            "win_nees_mean": float(np.mean([r["win_nees"] for r in runs])),
            "win_hpl_bound_mean": float(np.mean([r["win_hpl_bound"] for r in runs])),
            "win_hpl_bound_worst": float(min(r["win_hpl_bound"] for r in runs)),
            "win_p95_by_seed": {
                s: round(r["win_p95_m"], 2) for s, r in zip(seeds, runs, strict=True)
            },
        }
    return a


def paired(scenarios=SCENARIOS, seeds=REPORT_SEEDS, jobs: int = 1, estimators=ESTIMATORS):
    seeds = list(seeds)
    specs = {s: load(s) for s in scenarios}
    tasks = [(specs[s], seed, tuple(estimators)) for s in scenarios for seed in seeds]
    results = _map(paired_run, tasks, jobs)
    out = {}
    for i, sc in enumerate(scenarios):
        runs = results[i * len(seeds) : (i + 1) * len(seeds)]
        out[sc] = {name: aggregate([r[name] for r in runs], seeds) for name in estimators}
        if MEASURED in estimators:
            mine = out[sc][MEASURED].get("win_p95_by_seed")
            for other in estimators:
                if other != MEASURED and mine:
                    theirs = out[sc][other]["win_p95_by_seed"]
                    out[sc][MEASURED][f"wins_vs_{other}"] = sum(mine[s] < theirs[s] for s in seeds)
    return out


def world_cases():
    """model_mismatch's correlation-time and form cases (same multipath size), and its base."""
    mm = _model_mismatch()
    return [c for c in mm.CASES if any(k in c[1] for k in WORLD_KEYS)]


def mismatch(scenario=MISMATCH_SCENARIO, seeds=REPORT_SEEDS, jobs: int = 1) -> dict:
    """Filter-side cases (ekf-calibrated-measured only) and world-side cases (both calibrated
    filters), every case on the same seeds."""
    mm = _model_mismatch()
    seeds = list(seeds)
    base = load(scenario)
    tasks = [(base, s, (MEASURED,), cfg) for _, _, cfg in FILTER_CASES for s in seeds]
    worlds = [mm.world(base, c[3]) for c in world_cases()]
    tasks += [(spec, s, WORLD_ESTIMATORS, None, inj) for spec, inj in worlds for s in seeds]
    results = _map(paired_run, tasks, jobs)
    n = len(seeds)
    filt = []
    for i, (family, label, cfg) in enumerate(FILTER_CASES):
        runs = [r[MEASURED] for r in results[i * n : (i + 1) * n]]
        filt.append({"family": family, "case": label, "config": cfg} | _brief(runs, seeds))
    world = []
    off = len(FILTER_CASES) * n
    for j, c in enumerate(world_cases()):
        chunk = results[off + j * n : off + (j + 1) * n]
        for name in WORLD_ESTIMATORS:
            world.append(
                {"family": c[0], "case": c[1], "estimator": name}
                | _brief([r[name] for r in chunk], seeds)
            )
    return {"filter": filt, "world": world}


def _brief(runs, seeds) -> dict:
    a = aggregate(runs, seeds)
    keep = (
        "t1_worst_p95_m",
        "nees_mean",
        "win_nees_mean",
        "win_hpl_bound_mean",
        "hpl_bound_worst",
        "misleading_mean",
        "time_misleading_mean",
    )
    return {k: a[k] for k in keep}


def paired_markdown(data: dict) -> str:
    lines = [
        "| Scenario | Estimator | NEES all / T1 window | T1: worst-second p95 (m), window "
        "| HPL >= error: mean run / worst run (all epochs) | same, T1 window "
        "| Misleading /run (total) | Time-misleading /run | Fault-window p95 (m, mean run) "
        "| Measured's lower window p95, seeds |",
        "|" + " --- |" * 10,
    ]
    for sc, by in data["paired"].items():
        for name, a in by.items():
            wins = ", ".join(
                f"vs {k[len('wins_vs_') :]}: {v}/{a['runs']}"
                for k, v in a.items()
                if k.startswith("wins_vs_")
            )
            lines.append(
                f"| {sc} | {name} | {a['nees_mean']:.1f} / {a['win_nees_mean']:.1f} "
                f"| {a['t1_worst_p95_m']:.0f} (0-{a['t1_window_s']} s, worst at "
                f"{a['t1_worst_second']} s) "
                f"| {100 * a['hpl_bound_mean']:.1f} / {100 * a['hpl_bound_worst']:.1f} % "
                f"| {100 * a['win_hpl_bound_mean']:.1f} / {100 * a['win_hpl_bound_worst']:.1f} % "
                f"| {a['misleading_mean']:.1f} ({a['misleading_total']}) "
                f"| {a['time_misleading_mean']:.1f} | {a['fault_p95_mean_m']:.0f} "
                f"| {wins or '—'} |"
            )
    return "\n".join(lines)


def mismatch_markdown(data: dict) -> str:
    cols = (
        "T1: worst-second p95 (m) | NEES all / T1 window | HPL >= error, T1 window: mean run "
        "| worst run, all epochs | Misleading /run | Time-misleading /run |"
    )

    def cells(r):
        return (
            f"{r['t1_worst_p95_m']:.0f} | {r['nees_mean']:.1f} / {r['win_nees_mean']:.1f} "
            f"| {100 * r['win_hpl_bound_mean']:.1f} % | {100 * r['hpl_bound_worst']:.1f} % "
            f"| {r['misleading_mean']:.1f} | {r['time_misleading_mean']:.1f} |"
        )

    lines = [f"Filter side ({MEASURED}'s model changed; the world as committed):", ""]
    lines += [f"| Filter model | {cols}", "|" + " --- |" * 7]
    lines += [f"| {r['case']} | {cells(r)}" for r in data["mismatch"]["filter"]]
    lines += ["", "World side (the world's multipath changed; the filters as committed):", ""]
    lines += [f"| World multipath | Estimator | {cols}", "|" + " --- |" * 8]
    lines += [f"| {r['case']} | {r['estimator']} | {cells(r)}" for r in data["mismatch"]["world"]]
    return "\n".join(lines)


# Categorical slots 1-3 and recessive ink, as in analysis/figures.py and model_mismatch.py
INK, GRID = "#52514e", "#e4e3df"
COLORS = {"ekf": "#2a78d6", "ekf-calibrated": "#eb6834", MEASURED: "#1baf7a"}


def plot_t1(data: dict, out: Path) -> None:
    """The T1 curve per scenario: 95th percentile across runs at each second after GPS loss."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scs = list(data["paired"])
    fig, axes = plt.subplots(1, len(scs), figsize=(4.2 * len(scs), 4.0), dpi=130)
    for ax, sc in zip(np.atleast_1d(axes), scs, strict=True):
        for name, a in data["paired"][sc].items():
            curve = a["t1_p95_curve_m"]
            ax.plot(range(len(curve)), curve, color=COLORS[name], lw=2, label=name)
            ax.annotate(
                f"{a['t1_worst_p95_m']:.0f} m",
                (len(curve) - 1, curve[-1]),
                xytext=(3, 0),
                textcoords="offset points",
                fontsize=7,
                color=INK,
                va="center",
            )
        ax.axhline(T1_M, color=INK, lw=0.8, ls=":")
        ax.axhline(T1_FALLBACK_M, color=INK, lw=0.8, ls="--")
        ax.set_yscale("log")
        ax.set_title(sc, fontsize=9, loc="left")
        ax.set_xlabel("time since GPS loss (s)", fontsize=8)
        ax.grid(True, which="major", color=GRID, lw=0.6)
        ax.tick_params(labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("95th pct. across runs of horiz. error (m, log)", fontsize=8)
    np.atleast_1d(axes)[0].legend(fontsize=7, frameon=False, loc="upper left")
    s = data["seeds"]
    fig.suptitle(
        f"T1 statistic (ADR-0034): {len(s)} paired runs, seeds {s[0]}-{s[-1]}, {data['commit']} "
        "(sim, placeholder worlds). Dotted: T1 25 m; dashed: fallback 50 m",
        fontsize=8,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out)
    print(f"wrote {out}")


def plot_mismatch(data: dict, out: Path) -> None:
    """Filter-side cases: T1 worst-second p95 and T1-window NEES, one bar each."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data["mismatch"]["filter"]
    labels = [r["case"] for r in rows]
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.2), dpi=130, sharex=True)
    for ax, key, lab, honest in (
        (axes[0], "t1_worst_p95_m", "T1: worst-second p95 (m, log)", T1_M),
        (axes[1], "win_nees_mean", "NEES in the T1 window\n(2 if honest, log)", 2.0),
    ):
        ys = [r[key] for r in rows]
        ax.bar(range(len(rows)), ys, 0.6, color=COLORS[MEASURED])
        ax.axhline(ys[0], color=COLORS[MEASURED], lw=1, ls=":", zorder=0)
        ax.axhline(honest, color=INK, lw=0.8)
        for i, y in enumerate(ys):
            ax.annotate(
                f"{y:.0f}" if y >= 10 else f"{y:.1f}",
                (i, y),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                fontsize=7,
                color=INK,
            )
        ax.set_yscale("log")
        ax.set_ylabel(lab, fontsize=8)
        ax.grid(True, axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[1].set_xticks(range(len(rows)), labels, fontsize=8, rotation=25, ha="right")
    s = data["seeds"]
    fig.suptitle(
        f"{MEASURED}'s own model changed: {data['scenario']}, {len(s)} runs, "
        f"seeds {s[0]}-{s[-1]}, "
        f"{data['commit']} (sim). Dotted: as committed; solid: T1 25 m / NEES 2",
        fontsize=8,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out)
    print(f"wrote {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("what", choices=("paired", "mismatch", "plot"))
    p.add_argument("--runs", type=int, default=len(REPORT_SEEDS))
    p.add_argument("--seed-start", type=int, default=REPORT_SEEDS.start)
    p.add_argument("--scenarios", default=",".join(SCENARIOS))
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--json", required=True, help="write results (paired, mismatch) or read (plot)")
    p.add_argument("--mismatch", help="plot: the mismatch JSON")
    p.add_argument("--out-dir", help="plot: where the figures go")
    args = p.parse_args(argv)
    seeds = list(range(args.seed_start, args.seed_start + args.runs))
    meta = {"seeds": seeds, "commit": _commit(), "config": CALIBRATED_MEASURED}
    if args.what == "paired":
        data = meta | {"paired": paired(args.scenarios.split(","), seeds, args.jobs)}
        print(paired_markdown(data))
        Path(args.json).write_text(json.dumps(data, indent=1))
    elif args.what == "mismatch":
        data = meta | {
            "scenario": MISMATCH_SCENARIO,
            "mismatch": mismatch(seeds=seeds, jobs=args.jobs),
        }
        print(mismatch_markdown(data))
        Path(args.json).write_text(json.dumps(data, indent=1))
    else:
        out = Path(args.out_dir or ".")
        data = json.loads(Path(args.json).read_text())
        print(paired_markdown(data))
        plot_t1(data, out / "t1-paired.png")
        if args.mismatch:
            mis = json.loads(Path(args.mismatch).read_text())
            print(mismatch_markdown(mis))
            plot_mismatch(mis, out / "mismatch-filter.png")


if __name__ == "__main__":
    main()
