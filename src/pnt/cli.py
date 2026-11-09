"""`pnt` command line: sim, eval, replay, viz, results, live."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

from pnt import experiments
from pnt.core.measurement import Measurement
from pnt.core.time import s_to_ns
from pnt.integrity import taxonomy
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_session
from pnt.metrics import (
    ALERT_LIMIT_M,
    NO_DEGRADATION_RATIO,
    RECOVERY_SETTLE_S,
    TIME_ALERT_LIMIT_S,
    score,
    summarize,
)
from pnt.nav import ESTIMATORS, estimate
from pnt.sim.scenario import T0_NS, expand, generate, load, load_named, scenario_names
from pnt.viz import default_output, write_viz

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "data" / "sessions"
VERIFICATION = REPO / "systems" / "verification.md"


def _commit() -> str:
    try:
        return (
            subprocess.run(
                ["git", "describe", "--always", "--dirty", "--abbrev=7"],
                cwd=REPO,
                capture_output=True,
                text=True,
            ).stdout.strip()
            or "uncommitted"
        )
    except OSError:
        return "unknown"


def _fmt(metrics: dict) -> str:
    return "\n".join(
        f"  {k:<22} {v:10.3f}" if isinstance(v, float) else f"  {k:<22} {v}"
        for k, v in metrics.items()
    )


def cmd_sim(args) -> None:
    if args.dash:
        return _dash_sim(args)
    spec = load(args.scenario)
    run = generate(spec, seed=args.seed)
    estimates = list(
        estimate(
            args.estimator,
            run.measurements,
            origin_llh=spec.get("origin_llh"),
            reference=run.reference,
        )
    )
    m = score(estimates, run.truth, spec, T0_NS)

    SESSIONS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # A session folder (ICD-session) unless --out names a bare .mcap file. Never overwrite
    # an existing session: real recordings can't be regenerated.
    if args.out:
        out = Path(args.out)
        if _holds_data(out) and not args.force:
            raise SystemExit(f"{out} already holds data; choose another --out or pass --force")
    else:
        out = _unique(SESSIONS / f"sim-{spec['name']}-{stamp}")
    if out.suffix != ".mcap":
        out.mkdir(parents=True, exist_ok=True)
        session.write_meta(out, {
            "name": out.name, "platform": "sim", "origin_llh": spec.get("origin_llh"),
            "simulated": True, "scenario": spec["name"], "seed": args.seed,
            "commit": _commit(), "hardware": [], "reference": run.reference,
            "notes": spec.get("description", ""),
        })  # fmt: skip
        mcap = out / session.MCAP_NAME
    else:
        mcap = out
    meta = {
        "platform": "sim",
        "simulated": True,
        "scenario": spec["name"],
        "seed": args.seed,
        "commit": _commit(),
        "origin_llh": spec.get("origin_llh"),
    }
    if run.reference is not None:  # MCAP metadata are strings: leave it out rather than "None"
        meta["reference"] = run.reference
    with SessionWriter(mcap, metadata=meta) as w:
        for t in run.truth:
            w.write("/truth", t)
        for meas in run.measurements:
            w.write(f"/meas/{meas.source}", meas)
        for e in estimates:
            w.write(f"/nav/{args.estimator}", e)
    print(
        f"scenario {spec['name']} (seed {args.seed}): {len(run.measurements)} measurements, "
        f"{len(estimates)} estimates"
    )
    for t, text in run.events:
        print(f"  event @ {(t - T0_NS) / 1e9:6.1f} s: {text}")
    print(_fmt(m.as_dict()))
    print(f"wrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")


def _holds_data(path: Path) -> bool:
    """An existing file, or a folder with anything in it."""
    return path.is_file() or (path.is_dir() and any(path.iterdir()))


def _unique(path: Path) -> Path:
    """`path`, or `path-2`, `path-3`... if it is taken (two runs in the same second)."""
    n, candidate = 2, path
    while candidate.exists():
        candidate, n = path.with_name(f"{path.name}-{n}"), n + 1
    return candidate


def _eval_runs(scenario: str, seeds: list[int], estimator: str) -> list:
    spec = load(scenario)
    results = []
    for seed in seeds:
        run = generate(spec, seed=seed)
        estimates = estimate(
            estimator, run.measurements, origin_llh=spec.get("origin_llh"), reference=run.reference
        )
        results.append(score(list(estimates), run.truth, spec, T0_NS))
    return results


def _eval(scenario: str, runs: int, estimator: str, jobs: int = 1) -> dict:
    """Monte Carlo over seeds 0..runs-1. With `jobs` > 1 the seeds run in that many processes.
    Each seed is independent and the results keep seed order, so the summary is identical to a
    serial run."""
    seeds = list(range(runs))
    jobs = max(1, min(jobs, runs))
    if jobs == 1:
        return summarize(_eval_runs(scenario, seeds, estimator))
    with ProcessPoolExecutor(jobs) as pool:
        parts = pool.map(_eval_runs, [scenario] * runs, [[s] for s in seeds], [estimator] * runs)
        return summarize([r for part in parts for r in part])


def cmd_eval(args) -> None:
    summaries = {}
    for name in expand(args.scenario):
        summaries[name] = _eval(name, args.runs, args.estimator, args.jobs)
        print(f"scenario {name}, estimator {args.estimator}, {args.runs} runs")
        print(_fmt(summaries[name]))
    if args.json:
        data = summaries[args.scenario] if args.scenario in summaries else summaries
        Path(args.json).write_text(json.dumps(data, indent=2))


def _replay_spec(path: str) -> dict:
    """The scenario a simulated session came from, so replay scores its fault windows too."""
    name = session.read_meta(path).get("scenario")
    if not name:
        return {"faults": []}
    try:
        return load_named(name)
    except (ValueError, FileNotFoundError) as exc:
        print(f"{exc}: scoring without fault windows")
        return {"faults": []}


def cmd_replay(args) -> None:
    mcap = session.mcap_path(args.path)
    meas = (r for _, r in read_session(mcap, topics=["/meas/"]) if isinstance(r, Measurement))
    meta = session.read_meta(args.path)
    origin, reference = meta.get("origin_llh"), meta.get("reference")
    estimates = list(estimate(args.estimator, meas, origin_llh=origin, reference=reference))
    truth = [r for _, r in read_session(mcap, topics=["/truth"])]
    print(f"replayed {args.path}: {len(estimates)} estimates")
    if truth:
        print(_fmt(score(estimates, truth, _replay_spec(args.path), T0_NS).as_dict()))


def cmd_viz(args) -> None:
    out = Path(args.out) if args.out else default_output(args.session)
    try:
        windows = [
            (
                T0_NS + s_to_ns(f.get("start_s", 0.0)),
                T0_NS + s_to_ns(f["end_s"]) if "end_s" in f else None,
            )
            for f in _replay_spec(args.session).get("faults", [])
        ]
        counts = write_viz(
            args.session, out, estimator=args.estimator, fault_windows=windows, force=args.force
        )
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        raise SystemExit(f"viz: {exc}") from exc
    source = "re-run over the measurements" if counts["recomputed"] else "as logged"
    print(
        f"wrote {out}: {counts['estimates']} {args.estimator} estimates ({source}), "
        f"{counts['towers']} towers"
    )
    print("open it alone in Foxglove, then import analysis/foxglove-layout.json")


def _nan(x: float) -> bool:
    return x != x


def _report_card_row(name: str, s: dict) -> str:
    """One row of the report card (I5, I6): integrity and resilience for one scenario."""
    faults = load(name).get("faults", [])
    classes = sorted({taxonomy.classify(f).cls for f in faults}) or ["none"]
    tpl_txt = (
        "—" if _nan(s["min_time_pl_bound_frac"]) else f"{100 * s['min_time_pl_bound_frac']:.1f} %"
    )
    t_mis = (
        "—"
        if _nan(s["time_pl_bound_frac"])
        else f"{s['time_misleading_epochs']:.0f} / {s['time_hazardous_epochs']:.0f}"
    )
    if _nan(s["alerted"]):
        tta = "—"
    elif _nan(s["tta_median_s"]):
        tta = "never (0 % of runs)"
    else:
        tta = (
            f"{s['tta_median_s']:.1f} / {s['tta_worst_s']:.1f} "
            f"({100 * s['alerted']:.0f} % of runs)"
        )
    if _nan(s["resilience_level_worst"]):
        level_txt = "—"
    else:
        part = [
            "—" if _nan(s[k]) else f"{s[k]:.0f}" for k in ("pos_level_worst", "time_level_worst")
        ]
        level_txt = f"{s['resilience_level_worst']:.0f} ({part[0]} / {part[1]})"
        if s["recovery_tested"] != 1:
            level_txt += ", recovery untested"
    return (
        f"| `{name}` | {', '.join(classes)} | {s['hazardous_epochs']:.0f} | {tpl_txt} | {t_mis} "
        f"| {tta} | {level_txt} |"
    )


def cmd_results(args) -> None:
    """Re-run every scenario's Monte Carlo and rewrite the results block in verification.md."""
    card = [
        "| Scenario | Fault class | Hazardous epochs (mean) | Time PL bounds error "
        "(worst run) | Time misleading / hazardous (mean) | Time-to-alert median / worst (s) "
        "| Resilience level, worst run (position / time) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = [
        "| Scenario | Runs | H RMSE (m) | Fault H p95 (m) | Fault H max (m) | "
        "HPL bounds error | Misleading epochs | Spoof detect (s) | False alarms (/h) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in scenario_names():
        s = _eval(name, args.runs, args.estimator, args.jobs)
        detect = s["detect_delay_s"]
        rate = s["spoof_detected"]
        # nan -> no spoof in the scenario, or never detected
        detect_txt = "—" if detect != detect else f"{detect:.1f} ({100 * rate:.0f} % of runs)"
        rows.append(
            f"| `{name}` | {s['runs']} | {s['h_rmse_m']:.1f} | {s['fault_h_p95_m']:.1f} "
            f"| {s['worst_fault_h_max_m']:.1f} | {100 * s['min_hpl_bound_frac']:.1f} % "
            f"(worst run) | {s['misleading_epochs']:.0f} (mean) | {detect_txt} "
            f"| {s['false_alarms_per_h']:.1f} |"
        )
        card.append(_report_card_row(name, s))
    notes = (
        f"Report card. Alert limits (TBC): position {ALERT_LIMIT_M:g} m, time "
        f"{TIME_ALERT_LIMIT_S * 1e6:g} µs. Hazardous: error over the alert limit while the "
        "protection level is within it. Time PL is our definition (`pnt.integrity.protection.tpl`)"
        ". Time-to-alert: first alert after the fault starts, over the runs that alerted. "
        "Resilience level: our TBC mapping onto the DHS/CISA levels 1-4 (`pnt.metrics."
        "resilience_level`), judged for each part the fault corrupts, overall the worse; 0 means "
        "not even level 1 (or no clock under a time fault). Our level 2 is stricter than DHS's: "
        "it needs no hazardously misleading epoch, not just a solution. Recovery is judged "
        f"{RECOVERY_SETTLE_S:g} s after the fault ends; no degradation means fault-window p95 "
        f"within {NO_DEGRADATION_RATIO:g}x the pre-fault p95."
    )
    block = (
        f"Estimator: `{args.estimator}`. Commit `{_commit()}`, "
        f"{datetime.now():%Y-%m-%d %H:%M}. Regenerate with `just results`.\n\n"
        + "\n".join(rows)
        + f"\n\n{notes}\n\n"
        + "\n".join(card)
        + "\n\nFault taxonomy:\n\n"
        + taxonomy.markdown()
    )
    text = VERIFICATION.read_text()
    text = re.sub(
        r"(<!-- results:start -->\n).*?(\n<!-- results:end -->)",
        lambda m: m.group(1) + block + m.group(2),
        text,
        flags=re.S,
    )
    VERIFICATION.write_text(text)
    print(block)


def cmd_plot(args) -> None:
    from pnt import plots  # needs matplotlib (ground extra)

    name = session.session_name(args.path)
    out = Path(args.out) if args.out else REPO / "analysis" / "results" / name
    written = plots.save_all(
        args.path,
        out,
        estimator=args.estimator,
        alert_limit_m=args.alert_limit,
        time_alert_limit_s=args.time_alert_limit * 1e-6,
    )
    for w in written:
        print(f"wrote {w.relative_to(REPO) if w.is_relative_to(REPO) else w}")


def cmd_experiment(args) -> None:
    run = experiments.towers if args.name == "towers" else experiments.grid
    rows = run(args.scenario, runs=args.runs, estimator=args.estimator, jobs=args.jobs)
    commit = _commit()
    print(
        f"{args.name} experiment, scenario {args.scenario}, estimator {args.estimator}, "
        f"{args.runs} runs, {commit}"
    )
    print(experiments.markdown(rows))
    if args.json:
        meta = {"experiment": args.name, "scenario": args.scenario, "estimator": args.estimator}
        out = {**meta, "runs": args.runs, "commit": commit, "rows": rows}
        Path(args.json).write_text(json.dumps(out, indent=2))


def _serve_dash(feed, args) -> None:
    from pnt.dashboard.server import create_app, serve  # needs fastapi (ground extra)

    app = create_app(
        feed,
        speed=args.speed,
        alert_limit_m=args.alert_limit,
        time_alert_limit_s=args.time_alert_limit * 1e-6,
        host=args.host,
    )
    serve(app, host=args.host, port=args.port)


def _dash_sim(args) -> None:
    """`pnt sim <scenario> --dash`: the scenario straight onto the panel, nothing recorded."""
    from pnt.dashboard.feed import sim_feed

    feed = sim_feed(
        args.scenario,
        args.seed,
        args.estimator,
        preflight=not args.no_preflight,
        alert_limit_m=args.alert_limit,
    )
    _serve_dash(feed, args)


def cmd_dash(args) -> None:
    from pnt.dashboard.feed import replay_feed

    feed = replay_feed(
        args.session,
        args.estimator,
        preflight=not args.no_preflight,
        alert_limit_m=args.alert_limit,
    )
    _serve_dash(feed, args)


def cmd_preflight(args) -> None:
    from pnt.integrity import preflight

    p = preflight.predict(args.scenario, args.seed, args.estimator, args.alert_limit)
    hpl = p.hpl_m[p.t_s >= args.settle]
    print(
        f"pre-flight {p.scenario} (seed {args.seed}), estimator {p.estimator}, {_commit()}: "
        f"{len(p.t_s)} epochs"
    )
    print(f"  planned faults kept     {', '.join(p.kept_faults) or 'none'}")
    print(f"  unplanned faults left   {', '.join(p.dropped_faults) or 'none'}")
    if p.availability:
        print(f"  tower availability      {p.availability} (sigma / sqrt(availability))")
    if p.passthrough:
        print(f"  kinds fed as recorded   {p.passthrough}")
    print(
        f"  HPL after {args.settle:g} s: median {np.nanmedian(hpl):.1f} m, "
        f"max {np.nanmax(hpl):.1f} m"
    )
    windows = [w for w in p.unavailable() if w[1] > args.settle]
    print(f"  HPL over the {p.alert_limit_m:g} m alert limit (TBC): {'' if windows else 'never'}")
    for a, b in windows:
        print(f"    {a:.1f} s to {b:.1f} s")
    out = {"prediction": p.as_dict()}
    if args.compare:
        seeds = list(range(args.compare))
        tasks = [(args.scenario, s, args.estimator, args.alert_limit, args.settle) for s in seeds]
        rows = experiments._map(preflight.compare_one, tasks, args.jobs)  # forkserver pool
        summary = preflight.summarize(rows, args.alert_limit)
        print(f"  against real runs, seeds 0-{len(seeds) - 1} (real / predicted HPL):")
        print(_fmt(summary))
        out["comparison"] = summary
        if args.plot:
            preflight.plot(p, rows, summary, args.plot)
            print(f"wrote {args.plot}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))


def cmd_live(args) -> None:
    raise SystemExit("live: not built yet (ADR-0009). Use `pnt replay` on a recorded session.")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="pnt", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_estimator(parser) -> None:
        parser.add_argument("--estimator", choices=sorted(ESTIMATORS), default="baseline")

    def add_dash(parser) -> None:
        """Options of the operator panel (pnt.dashboard)."""
        parser.add_argument("--speed", type=float, default=1.0, help="x real time (inf: no hold)")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8050)
        parser.add_argument(
            "--alert-limit", type=float, default=ALERT_LIMIT_M, help="m, TBC (REQ-01/02)"
        )
        parser.add_argument(
            "--time-alert-limit",
            type=float,
            default=TIME_ALERT_LIMIT_S * 1e6,
            help="µs, TBC (REQ-03)",
        )
        parser.add_argument(
            "--no-preflight", action="store_true", help="skip the predicted HPL strip"
        )

    s = sub.add_parser("sim", help="run one simulated scenario, write an MCAP, print metrics")
    s.add_argument("scenario")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", help="session folder (default: data/sessions/sim-<scenario>-<time>)")
    s.add_argument("--force", action="store_true", help="overwrite an existing --out")
    add_estimator(s)
    add_dash(s)
    s.add_argument("--dash", action="store_true", help="show it on the panel; record nothing")
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("eval", help="Monte Carlo over a scenario")
    s.add_argument("scenario")
    s.add_argument("--runs", type=int, default=50)
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="worker processes")
    s.add_argument("--json")
    add_estimator(s)
    s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("replay", help="re-run the estimator over a recorded MCAP")
    s.add_argument("path")
    add_estimator(s)
    s.set_defaults(fn=cmd_replay)

    s = sub.add_parser("viz", help="write a companion file that Foxglove can draw on a map")
    s.add_argument("session", help="session folder or .mcap file")
    s.add_argument("--out", help="default: <folder>.viz.mcap or <file>.viz.mcap beside it")
    s.add_argument("--force", action="store_true", help="overwrite an existing --out")
    add_estimator(s)
    s.set_defaults(fn=cmd_viz)

    s = sub.add_parser("results", help="regenerate the results table in systems/verification.md")
    s.add_argument("--runs", type=int, default=50)
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="worker processes")
    add_estimator(s)
    s.set_defaults(fn=cmd_results)

    s = sub.add_parser("plot", help="error, Stanford, trust and clock figures for a session")
    s.add_argument("path")
    s.add_argument("--estimator", help="which /nav/<name> topic to plot (default: the first)")
    s.add_argument("--out", help="output folder (default: analysis/results/<session>)")
    s.add_argument("--alert-limit", type=float, default=ALERT_LIMIT_M, help="m, TBC (REQ-01/02)")
    s.add_argument(
        "--time-alert-limit",
        type=float,
        default=TIME_ALERT_LIMIT_S * 1e6,
        help="µs, TBC (REQ-03)",
    )
    s.set_defaults(fn=cmd_plot)

    s = sub.add_parser("experiment", help="tower-removal or sensitivity-grid experiment")
    s.add_argument("name", choices=["towers", "grid"])
    s.add_argument("scenario")
    s.add_argument("--runs", type=int, default=10)
    s.add_argument("--jobs", type=int, help="worker processes (default: all cores)")
    s.add_argument("--json")
    add_estimator(s)
    s.set_defaults(fn=cmd_experiment)

    s = sub.add_parser("dash", help="replay a session on the operator panel (browser)")
    s.add_argument("session", help="session folder or .mcap file")
    s.add_argument("--estimator", choices=sorted(ESTIMATORS), default="ekf")
    add_dash(s)
    s.set_defaults(fn=cmd_dash)

    s = sub.add_parser("preflight", help="predict protection levels along a scenario's route")
    s.add_argument("scenario")
    s.add_argument("--seed", type=int, default=0, help="names the world (synthetic towers)")
    s.add_argument("--estimator", choices=sorted(ESTIMATORS), default="ekf")
    s.add_argument("--alert-limit", type=float, default=ALERT_LIMIT_M, help="m, TBC (REQ-02)")
    s.add_argument("--settle", type=float, default=10.0, help="s of start-up left out of stats")
    s.add_argument("--compare", type=int, default=0, help="also run seeds 0..N-1 for real")
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="worker processes")
    s.add_argument("--plot", help="PNG of prediction against real runs (needs --compare)")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_preflight)

    s = sub.add_parser("live", help="run on the payload's live stream (not built yet)")
    s.set_defaults(fn=cmd_live)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
