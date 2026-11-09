"""`pnt` command line: sim, eval, replay, viz, results, live."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from pnt.core.measurement import Measurement
from pnt.core.time import s_to_ns
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_session
from pnt.metrics import score, summarize
from pnt.nav import ESTIMATORS
from pnt.sim.scenario import SCENARIO_DIR, T0_NS, generate, load, load_named
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
    spec = load(args.scenario)
    run = generate(spec, seed=args.seed)
    estimator = ESTIMATORS[args.estimator]
    estimates = list(estimator(run.measurements, origin_llh=spec.get("origin_llh")))
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
            "commit": _commit(), "hardware": [], "notes": spec.get("description", ""),
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


def _eval(scenario: str, runs: int, estimator: str) -> dict:
    spec = load(scenario)
    results = []
    for seed in range(runs):
        run = generate(spec, seed=seed)
        estimates = ESTIMATORS[estimator](run.measurements, origin_llh=spec.get("origin_llh"))
        results.append(score(list(estimates), run.truth, spec, T0_NS))
    return summarize(results)


def cmd_eval(args) -> None:
    s = _eval(args.scenario, args.runs, args.estimator)
    print(f"scenario {args.scenario}, estimator {args.estimator}, {args.runs} runs")
    print(_fmt(s))
    if args.json:
        Path(args.json).write_text(json.dumps(s, indent=2))


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
    origin = session.read_meta(args.path).get("origin_llh")
    estimates = list(ESTIMATORS[args.estimator](meas, origin_llh=origin))
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


def cmd_results(args) -> None:
    """Re-run every scenario's Monte Carlo and rewrite the results block in verification.md."""
    rows = [
        "| Scenario | Runs | H RMSE (m) | Fault H p95 (m) | Fault H max (m) | "
        "HPL bounds error | Misleading epochs | Spoof detect (s) | False alarms (/h) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in sorted(SCENARIO_DIR.glob("*.yaml")):
        s = _eval(p.stem, args.runs, args.estimator)
        detect = s["detect_delay_s"]
        rate = s["spoof_detected"]
        # nan -> no spoof in the scenario, or never detected
        detect_txt = "—" if detect != detect else f"{detect:.1f} ({100 * rate:.0f} % of runs)"
        rows.append(
            f"| `{p.stem}` | {s['runs']} | {s['h_rmse_m']:.1f} | {s['fault_h_p95_m']:.1f} "
            f"| {s['worst_fault_h_max_m']:.1f} | {100 * s['min_hpl_bound_frac']:.1f} % "
            f"(worst run) | {s['misleading_epochs']:.0f} (mean) | {detect_txt} "
            f"| {s['false_alarms_per_h']:.1f} |"
        )
    block = (
        f"Estimator: `{args.estimator}`. Commit `{_commit()}`, "
        f"{datetime.now():%Y-%m-%d %H:%M}. Regenerate with `just results`.\n\n" + "\n".join(rows)
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
        args.path, out, estimator=args.estimator, alert_limit_m=args.alert_limit
    )
    for w in written:
        print(f"wrote {w.relative_to(REPO) if w.is_relative_to(REPO) else w}")


def cmd_live(args) -> None:
    raise SystemExit("live: not built yet (ADR-0009). Use `pnt replay` on a recorded session.")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="pnt", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_estimator(parser) -> None:
        parser.add_argument("--estimator", choices=sorted(ESTIMATORS), default="baseline")

    s = sub.add_parser("sim", help="run one simulated scenario, write an MCAP, print metrics")
    s.add_argument("scenario")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out", help="session folder (default: data/sessions/sim-<scenario>-<time>)")
    s.add_argument("--force", action="store_true", help="overwrite an existing --out")
    add_estimator(s)
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("eval", help="Monte Carlo over a scenario")
    s.add_argument("scenario")
    s.add_argument("--runs", type=int, default=50)
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
    add_estimator(s)
    s.set_defaults(fn=cmd_results)

    s = sub.add_parser("plot", help="error, Stanford, trust and clock figures for a session")
    s.add_argument("path")
    s.add_argument("--estimator", help="which /nav/<name> topic to plot (default: the first)")
    s.add_argument("--out", help="output folder (default: analysis/results/<session>)")
    s.add_argument("--alert-limit", type=float, default=50.0, help="m, TBC (REQ-01/02)")
    s.set_defaults(fn=cmd_plot)

    s = sub.add_parser("live", help="run on the payload's live stream (not built yet)")
    s.set_defaults(fn=cmd_live)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
