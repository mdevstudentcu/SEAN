"""Headline numbers (#27): the spoof-defended filters and the base station beside plain `ekf`.

    python analysis/headline.py --runs 50 --jobs 3

Writes to `--out` (default `analysis/results/headline/`): `summary.json`, the tables of
`summary.md` (between its `tables` markers, so the hand-written recommendation around them
stays) and `error_after_loss.png`. Every number is sim, placeholder error models (the *Sim
validity* table of `systems/verification.md`), seeds 0..runs-1, at the commit the files name.

No new estimator and no new scoring. Every filter is one registered on `main`; each run is
`analysis/figures.py`'s `run_one` (scored by `pnt.metrics.score`, the same as `pnt eval` and
`pnt results`), the T1 statistic is that script's `per_second_p95` / `t1_statistic` (ADR-0034's
amendment), and the Stanford regions are `pnt.plots.stanford_counts` (as in `just results`).

- Part 1, spoofing: `--estimators` over the `realistic` set.
- Part 2, the base station (ADR-0020, sim only): `--base-estimators` over the
  `realistic-with-base` set, and `ekf` on the `--check` scenarios of that set, which must equal
  its `realistic` runs exactly (the payload's records are identical, seed for seed).

Per-key results are cached under `analysis/results/runs/headline/` (git-ignored) so a stopped run
resumes; the cache key holds the commit, so a new commit recomputes.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figures import (  # noqa: E402  (analysis/ is not a package)
    BLUE,
    FALLBACK_M,
    FALLBACK_WINDOW_S,
    GRID,
    INK,
    ORANGE,
    T1_M,
    T1_WINDOW_S,
    gps_loss_s,
    per_second_p95,
    run_one,
    t1_statistic,
)

from pnt import plots  # noqa: E402
from pnt.cli import _commit  # noqa: E402
from pnt.experiments import _map  # noqa: E402
from pnt.metrics import ALERT_LIMIT_M, summarize  # noqa: E402
from pnt.sim.scenario import expand, load  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
AQUA = "#1baf7a"  # categorical slot 3, after figures.py's slots 1 and 2

SPOOF_ESTIMATORS = [
    "ekf",
    "ekf-guard",
    "ekf-mhss",
    "ekf-calibrated-guard",
    "ekf-imu-guard",
    "ekf-honest-guard",
]
BASE_ESTIMATORS = ["ekf-base", "ekf-base-imu"]
OUTAGE = "long-outage"
SPOOF = "spoof-jump"  # the second panel: error after the spoof starts
CHECK = ["long-outage", "spoof-jump"]
SPOOF_SCENARIOS = ["spoof-ramp", "spoof-jump", "gps-return", "meaconing", "time-spoof"]
FALSE_ALARM_SCENARIOS = ["nominal", "gps-low-sats", "capture-pi4b"]
CURVE_S = 300  # seconds after the loss (or the spoof) drawn and stored


def one(scenario: str, seed: int, estimator: str, curve_from: float | None) -> dict:
    """One seed: its metrics, its Stanford counts and, if `curve_from` is set, its error at each
    whole second from then on (per_second_p95 over this run alone is just its own error)."""
    r = run_one(scenario, seed, estimator)
    out = {
        "metrics": r["metrics"],
        "stanford": plots.stanford_counts(
            np.asarray(r["err"], float), np.asarray(r["hpl"], float), ALERT_LIMIT_M
        ),
    }
    if curve_from is not None:
        out["curve"] = per_second_p95([r], curve_from, CURVE_S).astype(np.float32)
        out["hpl_curve"] = per_second_p95(
            [{"t_s": r["t_s"], "err": r["hpl"]}], curve_from, CURVE_S
        ).astype(np.float32)
    return out


def spoof_start_s(spec: dict) -> float | None:
    starts = [f["start_s"] for f in spec.get("faults", []) if f["type"].startswith("spoof")]
    return min(starts) if starts else None


def curve_from(scenario: str) -> float | None:
    spec = load(scenario)
    if scenario.endswith(OUTAGE):
        return gps_loss_s(spec)
    if scenario.endswith("-" + SPOOF):
        return spoof_start_s(spec)
    return None


def run_keys(keys: list[tuple[str, str]], runs: int, jobs: int, cache: Path, commit: str) -> dict:
    """{(scenario, estimator): [one() per seed]}, from the cache where it has the key."""
    out, todo = {}, []
    for k in keys:
        f = cache / f"{commit}-{runs}-{k[1]}-{k[0]}.pkl"
        if f.exists() and "dirty" not in commit:
            out[k] = pickle.loads(f.read_bytes())
        else:
            todo.append(k)
    for k in todo:  # one key at a time, so each lands in the cache as soon as it is done
        scn, est = k
        start = curve_from(scn)
        out[k] = _map(one, [(scn, s, est, start) for s in range(runs)], jobs)
        if "dirty" not in commit:
            (cache / f"{commit}-{runs}-{est}-{scn}.pkl").write_bytes(pickle.dumps(out[k]))
        print(f"done {scn} {est}", flush=True)
    return out


def attack(scenario: str) -> str:
    """`realistic-with-base-spoof-jump` and `realistic-spoof-jump` -> `spoof-jump`."""
    return scenario.removeprefix("realistic-with-base-").removeprefix("realistic-")


def stanford_total(rows: list[dict]) -> dict:
    keys = ("epochs", "nominal", "misleading", "hazardous", "unavailable")
    return {k: int(sum(r[k] for r in rows)) for k in keys}


def block(results: dict, scenarios: list[str], est: str, shared: list[str]) -> dict:
    """Every number the summary reports for one estimator over one set. `shared`: the attacks
    every environment has, whose pooled Stanford counts compare across sets."""
    per = {}
    for n in scenarios:
        rs = results[(n, est)]
        st = stanford_total([r["stanford"] for r in rs])
        per[n] = {
            "summary": summarize([r["metrics"] for r in rs]),
            "stanford": st,
            "runs_with_hazardous": int(sum(r["stanford"]["hazardous"] > 0 for r in rs)),
        }
    out = {
        "scenarios": per,
        "stanford_total": stanford_total([p["stanford"] for p in per.values()]),
        "stanford_shared": stanford_total(
            [p["stanford"] for n, p in per.items() if attack(n) in shared]
        ),
    }
    out["min_hpl_bound_frac"] = min(p["summary"]["min_hpl_bound_frac"] for p in per.values())
    outage = next(n for n in scenarios if n.endswith("-" + OUTAGE))
    curve = np.nanpercentile(np.stack([r["curve"] for r in results[(outage, est)]]), 95, axis=0)
    out["t1"] = t1_statistic(curve, T1_M, T1_WINDOW_S)
    out["fallback"] = t1_statistic(curve, FALLBACK_M, FALLBACK_WINDOW_S)
    return out


def _cell(x, fmt="{:.1f}") -> str:
    return "—" if x is None or x != x else fmt.format(x)


def tables(s: dict) -> str:
    runs = s["runs"]
    lines = [
        f"Commit `{s['commit']}`, seeds 0-{runs - 1} ({runs} runs per scenario), sim, placeholder "
        "error models. Regenerate with `python analysis/headline.py --runs "
        f"{runs}` from a clean tree.",
        "",
    ]

    def rows(group: str, set_name: str) -> list[str]:
        out = [
            "| Estimator | T1 worst second p95 (m) | Fallback | HPL bounds error, worst run "
            "| Stanford nominal / misleading / hazardous / unavailable (epochs) "
            "| Runs with hazardous, spoof-ramp / spoof-jump | Spoof detected, ramp / jump / "
            "gps-return (% runs, mean delay s) | False alarms /h, nominal |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for est, b in s[group].items():
            sc = b["scenarios"]
            st = b["stanford_shared"]

            def det(n, sc=sc):
                m = sc[f"{set_name}-{n}"]["summary"]
                return f"{100 * m['spoof_detected']:.0f} % ({_cell(m['detect_delay_s'])})"

            out.append(
                f"| `{est}` | {b['t1']['worst_p95_m']:.1f} at +{b['t1']['worst_at_s']} s, "
                f"{'met' if b['t1']['met'] else 'missed'} "
                f"| {'met' if b['fallback']['met'] else 'missed'} "
                f"| {100 * b['min_hpl_bound_frac']:.1f} % "
                f"| {st['nominal']} / {st['misleading']} / **{st['hazardous']}** / "
                f"{st['unavailable']} "
                f"| {sc[f'{set_name}-spoof-ramp']['runs_with_hazardous']}/{runs} / "
                f"{sc[f'{set_name}-spoof-jump']['runs_with_hazardous']}/{runs} "
                f"| {det('spoof-ramp')} / {det('spoof-jump')} / {det('gps-return')} "
                f"| {sc[f'{set_name}-nominal']['summary']['false_alarms_per_h']:.1f} |"
            )
        return out

    lines += ["### Spoofing: `realistic` set (15 scenarios)", "", *rows("spoof", "realistic")]
    lines += [
        "",
        "Stanford counts are pooled over the 15 attacks of the `realistic` set (in either "
        "environment) and all seeds (0.1 s epochs; "
        f"alert limit {ALERT_LIMIT_M:g} m, TBC). T1: ≤ {T1_M:g} m for {T1_WINDOW_S:g} s after "
        f"GPS loss on `realistic-long-outage`; fallback ≤ {FALLBACK_M:g} m for "
        f"{FALLBACK_WINDOW_S:g} s; both TBC, scored as ADR-0034's amendment.",
        "",
        "### Per scenario: what each defence costs",
        "",
        "| Scenario | Estimator | Hazardous | Unavailable | Misleading | Fault-window p95 (m) "
        "| Worst run max (m) | Resilience level, worst run |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for n in ["spoof-ramp", "spoof-jump", "gps-return", "meaconing", "long-outage", "nominal"]:
        for est, b in s["spoof"].items():
            p = b["scenarios"][f"realistic-{n}"]
            m, st = p["summary"], p["stanford"]
            lines.append(
                f"| `{n}` | `{est}` | {st['hazardous']} | {st['unavailable']} "
                f"| {st['misleading']} | {_cell(m['fault_h_p95_m'])} "
                f"| {_cell(m['worst_fault_h_max_m'])} "
                f"| {_cell(m['resilience_level_worst'], '{:.0f}')} |"
            )
    lines += [
        "",
        "### Base station: `realistic-with-base` set (19 scenarios), sim only (ADR-0020)",
        "",
        *rows("base", "realistic-with-base"),
        "",
        "`ekf` on `realistic-with-base-*` is its `realistic-*` run: the payload's records are "
        f"identical. Checked here on {', '.join(s['check']['scenarios'])}: "
        f"{'every estimate equal' if s['check']['equal'] else 'NOT EQUAL'} over all seeds.",
        "",
        "| Scenario | Estimator | Hazardous | Unavailable | Fault-window p95 (m) "
        "| Worst run max (m) | Time error p95 in fault window (µs) "
        "| Time PL bounds error, worst run |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    base_rows = ["long-outage", "spoof-ramp", "spoof-jump", "nominal"] + [
        n.removeprefix("realistic-with-base-")
        for n in s["base_scenarios"]
        if "base-" in n.removeprefix("realistic-with-base-") or n.endswith("tower-clock-step")
    ]
    for n in base_rows:
        for est in ["ekf", *s["base"]]:
            src = s["spoof"]["ekf"] if est == "ekf" else s["base"][est]
            key = f"realistic-{n}" if est == "ekf" else f"realistic-with-base-{n}"
            if key not in src["scenarios"]:
                continue
            p = src["scenarios"][key]
            m, st = p["summary"], p["stanford"]
            lines.append(
                f"| `{n}` | `{est}` | {st['hazardous']} | {st['unavailable']} "
                f"| {_cell(m['fault_h_p95_m'])} | {_cell(m['worst_fault_h_max_m'])} "
                f"| {_cell(m['fault_time_err_p95_us'], '{:.3f}')} "
                f"| {_cell(100 * m['min_time_pl_bound_frac'], '{:.1f} %')} |"
            )
    return "\n".join(lines)


def figure(s: dict, curves: dict, out: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=150, sharey=True)
    for ax, (key, xlabel) in zip(
        axes,
        (
            (OUTAGE, f"time since GPS loss (s), {OUTAGE}"),
            (SPOOF, f"time since the spoof starts (s), {SPOOF} (300 m, held)"),
        ),
        strict=True,
    ):
        for (label, color), c in zip(
            ((s["fig_names"][0], BLUE), (s["fig_names"][1], ORANGE), (s["fig_names"][2], AQUA)),
            curves[key],
            strict=True,
        ):
            ls = "--" if label == s["fig_names"][1] else "-"
            ax.plot(np.arange(len(c)), c, color=color, lw=2, ls=ls, label=label)
        ax.axhline(ALERT_LIMIT_M, color=INK, lw=1, ls="-.")
        ax.text(0.99, ALERT_LIMIT_M * 1.08, f"alert limit {ALERT_LIMIT_M:g} m (TBC)", color=INK,
                fontsize=8, ha="right", transform=ax.get_yaxis_transform())  # fmt: skip
        if key == OUTAGE:
            ax.plot([0, T1_WINDOW_S], [T1_M, T1_M], color=INK, lw=1.5, ls=":")
            ax.text(2, T1_M * 0.8, f"T1 ≤ {T1_M:g} m for {T1_WINDOW_S:g} s (TBC)", color=INK,
                    fontsize=8, va="top")  # fmt: skip
        ax.set_yscale("log")
        ax.set_xlabel(xlabel)
        ax.grid(True, which="major", color=GRID, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("horizontal error, 95th percentile across runs each second (m)")
    axes[0].legend(fontsize=8, frameon=False, loc="lower right")
    fig.suptitle(
        f"Error after GPS loss and after a spoof: per-second p95 over {s['runs']} runs",
        fontsize=10,
    )
    fig.text(
        0.01,
        0.01,
        f"realistic-* / realistic-with-base-* · seeds 0-{s['runs'] - 1} · commit {s['commit']} · "
        "sim, placeholder error models (systems/verification.md, Sim validity) · "
        f"{s['fig_names'][2]}: base station in sim only, link always up, base surveyed (ADR-0020)",
        fontsize=7,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path = out / "error_after_loss.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--estimators", nargs="+", default=SPOOF_ESTIMATORS)
    p.add_argument("--base-estimators", nargs="+", default=BASE_ESTIMATORS)
    p.add_argument("--guarded", default="ekf-guard", help="the guarded filter drawn in the figure")
    p.add_argument("--out", default=str(REPO / "analysis" / "results" / "headline"))
    args = p.parse_args(argv)

    commit = _commit()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = REPO / "analysis" / "results" / "runs" / "headline"
    cache.mkdir(parents=True, exist_ok=True)

    realistic = expand("realistic")
    with_base = expand("realistic-with-base")
    check = [f"realistic-with-base-{n}" for n in CHECK]
    shared = [attack(n) for n in realistic]
    keys = [(n, e) for e in args.estimators for n in realistic]
    keys += [(n, e) for e in args.base_estimators for n in with_base]
    keys += [(n, "ekf") for n in check]
    res = run_keys(keys, args.runs, args.jobs, cache, commit)

    equal = all(
        np.array_equal(a["curve"], b["curve"], equal_nan=True)
        and a["metrics"].as_dict().__repr__() == b["metrics"].as_dict().__repr__()
        for n in check
        for a, b in zip(
            res[(n, "ekf")], res[(n.replace("realistic-with-base-", "realistic-"), "ekf")],
            strict=True,
        )
    )  # fmt: skip
    s = {
        "commit": commit,
        "runs": args.runs,
        "kind": "sim; placeholder error models (systems/verification.md, Sim validity)",
        "alert_limit_m": ALERT_LIMIT_M,
        "spoof": {e: block(res, realistic, e, shared) for e in args.estimators},
        "base": {e: block(res, with_base, e, shared) for e in args.base_estimators},
        "base_scenarios": with_base,
        "check": {"scenarios": check, "equal": bool(equal)},
        "fig_names": ["ekf", args.guarded, args.base_estimators[0]],
    }

    def p95(scn: str, est: str, field: str = "curve") -> np.ndarray:
        return np.nanpercentile(np.stack([r[field] for r in res[(scn, est)]]), 95, axis=0)

    curves = {
        key: [
            p95(f"realistic-{key}", "ekf"),
            p95(f"realistic-{key}", args.guarded),
            p95(f"realistic-with-base-{key}", args.base_estimators[0]),
        ]
        for key in (OUTAGE, SPOOF)
    }
    s["curves"] = {
        key: {
            name: [round(float(x), 2) for x in c]
            for name, c in zip(s["fig_names"], cs, strict=True)
        }
        for key, cs in curves.items()
    }
    png = figure(s, curves, out)
    (out / "summary.json").write_text(json.dumps(s, indent=2, default=float))
    md = out / "summary.md"
    body = tables(s)
    empty = "# Headline numbers\n\n<!-- tables:start -->\n<!-- tables:end -->\n"
    text = md.read_text() if md.exists() else empty
    text = re.sub(
        r"(<!-- tables:start -->\n).*?(<!-- tables:end -->)",
        lambda m: m.group(1) + body + "\n" + m.group(2),
        text,
        flags=re.S,
    )
    md.write_text(text)
    for w in (png, md, out / "summary.json"):
        print(f"wrote {w.relative_to(REPO) if w.is_relative_to(REPO) else w}")


if __name__ == "__main__":
    main()
