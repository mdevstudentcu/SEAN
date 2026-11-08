"""`pnt` command line: sim, eval, replay, results, live."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from pnt.core.measurement import Measurement
from pnt.io.mcap_log import SessionWriter, read_session
from pnt.metrics import score, summarize
from pnt.nav import baseline
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
    estimates = list(baseline.run(run.measurements))
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
            w.write("/nav/baseline", e)
    print(
        f"scenario {spec['name']} (seed {args.seed}): {len(run.measurements)} measurements, "
        f"{len(estimates)} estimates"
    )
    for t, text in run.events:
        print(f"  event @ {(t - T0_NS) / 1e9:6.1f} s: {text}")
    print(_fmt(m.as_dict()))
    print(f"wrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")


def _eval(scenario: str, runs: int) -> dict:
    spec = load(scenario)
    results = []
    for seed in range(runs):
        run = generate(spec, seed=seed)
        results.append(score(list(baseline.run(run.measurements)), run.truth, spec, T0_NS))
    return summarize(results)


def cmd_eval(args) -> None:
    s = _eval(args.scenario, args.runs)
    print(f"scenario {args.scenario}, estimator baseline, {args.runs} runs")
    print(_fmt(s))
    if args.json:
        Path(args.json).write_text(json.dumps(s, indent=2))


def cmd_replay(args) -> None:
    meas = (r for _, r in read_session(args.path, topics=["/meas/"]) if isinstance(r, Measurement))
    estimates = list(baseline.run(meas))
    truth = [r for _, r in read_session(args.path, topics=["/truth"])]
    print(f"replayed {args.path}: {len(estimates)} estimates")
    if truth:
        spec = {"faults": []}
        print(_fmt(score(estimates, truth, spec, T0_NS).as_dict()))


def cmd_results(args) -> None:
    """Re-run every scenario's Monte Carlo and rewrite the results block in verification.md."""
    rows = [
        "| Scenario | Runs | H RMSE (m) | Fault H p95 (m) | Fault H max (m) | "
        "HPL bounds error | Misleading epochs | Spoof detect (s) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in sorted(SCENARIO_DIR.glob("*.yaml")):
        s = _eval(p.stem, args.runs)
        detect = s["detect_delay_s"]
        detect_txt = "—" if detect != detect else f"{detect:.1f}"  # nan -> not detected
        rows.append(
            f"| `{p.stem}` | {s['runs']} | {s['h_rmse_m']:.1f} | {s['fault_h_p95_m']:.1f} "
            f"| {s['worst_fault_h_max_m']:.1f} | {100 * s['min_hpl_bound_frac']:.1f} % "
            f"(worst run) | {s['misleading_epochs']:.0f} (mean) | {detect_txt} |"
        )
    block = (
        f"Estimator: `baseline`. Commit `{_commit()}`, "
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


def cmd_live(args) -> None:
    raise SystemExit("live: not built yet (ADR-0009). Use `pnt replay` on a recorded session.")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="pnt", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sim", help="run one simulated scenario, write an MCAP, print metrics")
    s.add_argument("scenario")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("eval", help="Monte Carlo over a scenario")
    s.add_argument("scenario")
    s.add_argument("--runs", type=int, default=50)
    s.add_argument("--json")
    s.set_defaults(fn=cmd_eval)

    s = sub.add_parser("replay", help="re-run the estimator over a recorded MCAP")
    s.add_argument("path")
    s.set_defaults(fn=cmd_replay)

    s = sub.add_parser("results", help="regenerate the results table in systems/verification.md")
    s.add_argument("--runs", type=int, default=50)
    s.set_defaults(fn=cmd_results)

    s = sub.add_parser("live", help="run on the payload's live stream (not built yet)")
    s.set_defaults(fn=cmd_live)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
