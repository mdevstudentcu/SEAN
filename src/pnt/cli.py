"""`pnt` command line: sim, eval, replay, results, live."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import yaml

from pnt.core.measurement import Measurement
from pnt.io.mcap_log import SessionWriter, read_metadata, read_session
from pnt.metrics import score, summarize
from pnt.nav import ESTIMATORS
from pnt.sim.scenario import SCENARIO_DIR, T0_NS, generate, load

REPO = Path(__file__).resolve().parents[2]
SESSIONS = REPO / "data" / "sessions"
VERIFICATION = REPO / "systems" / "verification.md"


def _commit() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True
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
    out = Path(args.out) if args.out else SESSIONS / f"sim-{spec['name']}-{stamp}.mcap"
    meta = {
        "platform": "sim",
        "simulated": True,
        "scenario": spec["name"],
        "seed": args.seed,
        "commit": _commit(),
        "origin_llh": spec.get("origin_llh"),
    }
    with SessionWriter(out, metadata=meta) as w:
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
    name = read_metadata(path).get("scenario")
    if not name:
        return {"faults": []}
    try:
        return load(name)
    except FileNotFoundError:
        print(f"scenario {name!r} not found: scoring without fault windows")
        return {"faults": []}


def cmd_replay(args) -> None:
    meas = (r for _, r in read_session(args.path, topics=["/meas/"]) if isinstance(r, Measurement))
    origin = yaml.safe_load(read_metadata(args.path).get("origin_llh", "null"))
    estimates = list(ESTIMATORS[args.estimator](meas, origin_llh=origin))
    truth = [r for _, r in read_session(args.path, topics=["/truth"])]
    print(f"replayed {args.path}: {len(estimates)} estimates")
    if truth:
        print(_fmt(score(estimates, truth, _replay_spec(args.path), T0_NS).as_dict()))


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

    path = Path(args.path)
    out = Path(args.out) if args.out else REPO / "analysis" / "results" / path.stem
    written = plots.save_all(path, out, estimator=args.estimator, alert_limit_m=args.alert_limit)
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
    s.add_argument("--out")
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
