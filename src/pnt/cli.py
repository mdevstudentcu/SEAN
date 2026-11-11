"""`pnt` command line: sim, eval, replay, viz, results, live."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import re
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np

from pnt import compare, experiments
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
    """The commit outputs name (REQ-10). `PNT_COMMIT` overrides it: `just results` checks the tree
    is clean, then sets it, so its second step is not marked dirty by the first step's output."""
    if os.environ.get("PNT_COMMIT"):
        return os.environ["PNT_COMMIT"]
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
        f"  {k:<28} {v:10.3f}" if isinstance(v, float) else f"  {k:<28} {v}"
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


def _worker_pool(jobs: int) -> ProcessPoolExecutor:
    """Monte Carlo workers with one BLAS thread each, unless the caller's environment says
    otherwise (#255, ADR-0054): the filter's matrices are small, and every worker starting a BLAS
    thread per core makes them slower. BLAS reads the setting when numpy loads, so the workers
    come from a forkserver started with it, not forked from this process, whose BLAS has its
    threads already."""
    for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(var, "1")
    return ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("forkserver"))


def _eval(scenario: str, runs: int, estimator: str, jobs: int = 1) -> dict:
    """Monte Carlo over seeds 0..runs-1. With `jobs` > 1 the seeds run in that many processes.
    Each seed is independent and the results keep seed order, so the summary is identical to a
    serial run."""
    seeds = list(range(runs))
    jobs = max(1, min(jobs, runs))
    if jobs == 1:
        return summarize(_eval_runs(scenario, seeds, estimator))
    with _worker_pool(jobs) as pool:
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


def _inject_spec(name: str) -> dict:
    """A bundled scenario by name, or a scenario YAML file the user named, for its faults."""
    return load(name) if Path(name).suffix in (".yaml", ".yml") else load_named(name)


def _write_injected(args, meas: list[Measurement], truth: list, meta: dict) -> None:
    """Save a session with faults injected (ADR-0015) as a new session folder."""
    out = Path(args.out)
    if _holds_data(out):
        raise SystemExit(f"{out} already holds data; choose another --out")
    out.mkdir(parents=True)
    note = (
        f"faults from {args.inject} (seed {args.seed}) injected into "
        f"{session.session_name(args.path)} at {_commit()}; fault times count from its first "
        "measurement"
    )
    session.write_meta(out, {
        **{k: meta.get(k) for k in session.META_KEYS},
        "name": out.name, "scenario": None, "seed": args.seed, "commit": _commit(),
        "notes": f"{meta.get('notes') or ''}\n{note}".strip(),
    })  # fmt: skip
    with SessionWriter(out / session.MCAP_NAME, metadata={"injected": note}) as w:
        for t in truth:
            w.write("/truth", t)
        for m in meas:
            w.write(f"/meas/{m.source}", m)
    print(f"wrote {out}")


def cmd_replay(args) -> None:
    mcap = session.mcap_path(args.path)
    meta = session.read_meta(args.path)
    origin, reference = meta.get("origin_llh"), meta.get("reference")
    truth = [r for _, r in read_session(mcap, topics=["/truth"])]
    if args.inject:
        spec = _inject_spec(args.inject)
        meas, t0, events = compare.inject(args.path, spec.get("faults", []), seed=args.seed)
        print(f"injected the faults of {spec['name']} (seed {args.seed}): {len(meas)} records")
        for t, text in events:
            print(f"  event @ {(t - t0) / 1e9:6.1f} s: {text}")
        if args.out:
            _write_injected(args, meas, truth, meta)
    else:
        if args.out:
            raise SystemExit("replay: --out saves an injected session; it needs --inject")
        spec, t0 = _replay_spec(args.path), T0_NS
        meas = (r for _, r in read_session(mcap, topics=["/meas/"]) if isinstance(r, Measurement))
    estimates = list(estimate(args.estimator, meas, origin_llh=origin, reference=reference))
    print(f"replayed {args.path}: {len(estimates)} estimates")
    if truth:
        print(_fmt(score(estimates, truth, spec, t0).as_dict()))


def cmd_compare(args) -> None:
    print(compare.table(args.simulated, args.real, args.source, args.first_s))
    if args.out:
        out = compare.plot(args.simulated, args.real, args.source, args.out, args.first_s)
        print(f"wrote {out}")


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


def _sweep_params(items: list[str] | None) -> dict[str, list[float]] | None:
    """`--param PATH=v1,v2,...` options as {path: values}; None if there are none."""
    if not items:
        return None
    out = {}
    for item in items:
        path, sep, values = item.partition("=")
        try:
            if not sep or not path:
                raise ValueError
            out[path] = [float(v) for v in values.split(",")]
        except ValueError:
            raise SystemExit(f"--param wants PATH=v1,v2,..., not {item!r}") from None
    return out


def _fmt_cell(v) -> str:
    if isinstance(v, float):
        return "—" if v != v else f"{v:.4g}"
    return str(v)


def cmd_experiment(args) -> None:
    if args.name == "sweep":
        return _cmd_sweep(args)
    if args.param:
        raise SystemExit("--param is only for the sweep experiment")
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


def _cmd_sweep(args) -> None:
    try:
        params = _sweep_params(args.param)
        rows = experiments.sweep(
            args.scenario, params, runs=args.runs, estimator=args.estimator, jobs=args.jobs
        )
    except ValueError as exc:
        raise SystemExit(f"sweep: {exc}") from exc
    commit = _commit()
    print(
        f"sweep experiment, scenario {args.scenario}, estimator {args.estimator}, {args.runs} "
        f"runs per row (seeds 0..{args.runs - 1}, paired), {commit}. One value changed per row. "
        "The filter is told the committed values, except in told_sigma_m rows, which change the "
        "noise it is told, and told_position_sigma_m rows, which put that error in the tower "
        "positions it is told; gnss and baro sigma_m rows change both truth and told. Means over "
        "runs; hpl_bound_worst is the worst run, hazardous_epochs the total."
    )
    print(experiments.markdown(rows, fmt=_fmt_cell))
    if args.json:
        meta = {"experiment": "sweep", "scenario": args.scenario, "estimator": args.estimator}
        out = {**meta, "runs": args.runs, "seeds": list(range(args.runs)), "commit": commit}
        Path(args.json).write_text(json.dumps({**out, "rows": rows}, indent=2))


def _serve_dash(feed, args) -> None:
    from pnt.dashboard.server import create_app, serve  # needs fastapi (ground extra)

    app = create_app(
        feed,
        speed=getattr(args, "speed", 1.0),  # `pnt live` has none: a live feed is not paced
        alert_limit_m=args.alert_limit,
        time_alert_limit_s=args.time_alert_limit * 1e-6,
        host=args.host,
        banner=getattr(args, "banner", None),  # `pnt live` has none
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
        hide_origin=args.hide_origin,
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


def cmd_frontend_lte(args) -> None:
    """LTE front end (#23): RTL-SDR capture -> /meas/lte records in a new session."""
    from pnt.frontends.lte import Config, frontend, open_capture

    cap = open_capture(args.capture, args.sidecar, args.earfcn)
    src = cap.path.parent if (cap.path.parent / session.MCAP_NAME).exists() else None
    if args.out:
        out = Path(args.out)
    elif src is not None:
        out = _unique(src.with_name(f"{src.name}-lte"))
    else:
        out = _unique(SESSIONS / f"lte-{cap.path.stem}-{datetime.now():%Y%m%d-%H%M%S}")
    if _holds_data(out) and not args.force:
        raise SystemExit(f"{out} already holds data; choose another --out or pass --force")
    result = frontend.process_capture(cap, receiver=args.receiver)
    print(frontend.summary(result, cap))
    if not result.measurements:
        raise SystemExit(
            f"{args.capture}: no LTE cells found in {result.capture_s:.3f} s of samples "
            f"(one search needs {Config().acq_ms:g} ms); nothing written"
        )
    frontend.write_session(result, cap, out, _commit(), copy_from=None if args.no_copy else src)
    print(f"wrote {out}")


def cmd_frontend_gnss(args) -> None:
    """GNSS front end (#22): a session's gpsd SKY events -> /meas/gnss gnss_health records."""
    from pnt.frontends import gnss

    src = session.mcap_path(args.session).parent
    out = Path(args.out) if args.out else _unique(src.with_name(f"{src.name}-gnss"))
    if _holds_data(out) and not args.force:
        raise SystemExit(f"{out} already holds data; choose another --out or pass --force")
    if out.resolve() == src.resolve():
        raise SystemExit("--out must be a new folder: a front end never rewrites its input")
    given = {"ref": args.ref_cn0, "low": args.low_cn0, "k": args.top_k}
    params = {k: v for k, v in given.items() if v is not None}
    new = gnss.derive_session(src, out, _commit(), **params)
    print(gnss.summary(new))
    print(f"wrote {out}")


def _key_dir(args) -> Path:
    from pnt.io import linkauth

    return Path(args.keys).expanduser() if args.keys else linkauth.default_dir()


def _link_auth(args, make):
    """ADR-0026: the stream is authenticated unless `--insecure`; when it cannot be, refuse and
    say why. `make(key_dir)` builds the keys; returns None for a plaintext stream."""
    from pnt.io import linkauth

    if args.insecure:
        print(
            "WARNING: --insecure: the stream is neither authenticated nor encrypted. Anyone on "
            "the network can read it or forge records. Use a private link only (ADR-0026)."
        )
        return None
    try:
        return make(_key_dir(args))
    except linkauth.LinkSecurityError as e:
        raise SystemExit(f"{args.cmd}: {e}") from None


def cmd_keys(args) -> None:
    """CurveZMQ keys for the ground links (ADR-0026, #89)."""
    from pnt.io import linkauth

    key_dir = _key_dir(args)
    try:
        if args.keys_cmd == "gen":
            pub = linkauth.generate(args.role, key_dir, force=args.force)
            print(f"wrote {key_dir / (args.role + linkauth.SECRET_SUFFIX)} (secret, mode 600)")
            print(f"public key of {args.role} (id {linkauth.key_id(pub)}); on each peer run:")
            print(f"  pnt keys trust {args.role} -- '{pub.decode()}'")  # z85 may start with -
            print(f"or copy {key_dir / (args.role + linkauth.PUBLIC_SUFFIX)} and trust the file")
        elif args.keys_cmd == "trust":
            pub = linkauth.trust(args.name, args.key, key_dir, force=args.force)
            print(f"trusted {args.name}: {pub.decode()} (id {linkauth.key_id(pub)})")
        else:
            print(linkauth.show(key_dir))
    except linkauth.LinkSecurityError as e:
        raise SystemExit(f"keys: {e}") from None


def cmd_record(args) -> None:
    """Capture a real session on the Pi (payload or reference station, #19)."""
    import signal
    import threading

    from pnt.payload import config
    from pnt.payload.devices import clock_status
    from pnt.payload.recorder import Recorder, session_name
    from pnt.payload.survey import load_reference

    folder = Path(args.out) if args.out else SESSIONS / session_name(args.platform, args.place)
    reference = load_reference(args.reference) if args.reference else None
    streamer = None
    if not args.no_stream:
        from pnt.io import linkauth
        from pnt.payload.streamer import Streamer

        auth = _link_auth(args, lambda d: linkauth.server_auth(args.receiver, d))
        streamer = Streamer(args.stream, auth=auth)
    rec = Recorder(
        folder,
        config.build(args),
        platform=args.platform,
        receiver=args.receiver,
        origin_llh=config.parse_llh(args.origin),
        reference=reference,
        notes=args.notes,
        streamer=streamer,
    )
    stop = threading.Event()
    # Ctrl-C (any number of times), a dropped ssh and `kill` all end the recording the same way:
    # stop the devices and finish the files. Only SIGKILL or power loss can cut it off.
    caught = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    before = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in caught}
    print(f"recording {folder} (Ctrl-C to stop)")
    clock = clock_status()
    if "NOT locked" in clock:
        print(f"WARNING: {clock}: timestamps are not GPS time yet (wait for chrony, RUNBOOK A4)")
    if streamer:
        print(f"streaming on {streamer.endpoint}; {streamer.describe()}")
    try:
        meta = rec.run(args.duration, stop)
    finally:
        for sig, handler in before.items():
            signal.signal(sig, handler)
    if streamer:
        if streamer.refused:
            print(f"stream: {streamer.refused} connection(s) refused: client key not trusted")
        streamer.close()
    print(f"wrote {folder}")
    for line in meta["notes"].splitlines():
        print(f"  {line}")
    print(f"  captured: {', '.join(meta['hardware']) or 'nothing'}; records: {rec.counts}")


def cmd_survey(args) -> None:
    """Average a reference-station session's GPS fixes into its surveyed position (#85)."""
    from pnt.payload.survey import survey_session, write_survey

    try:
        result = survey_session(args.session, batch_s=args.batch_s)
    except ValueError as e:  # no fixes, or no origin to place them: say so, no traceback
        raise SystemExit(f"survey: {e}") from None
    out = Path(args.out) if args.out else Path(args.session).with_suffix(".survey.yaml")
    write_survey(result, out)
    print(json.dumps(result, indent=2))
    if result["duration_s"] < 3600:
        print(f"note: {result['duration_s']:.0f} s of fixes; ADR-0020 asks for at least 1 h (TBC)")
    print(f"wrote {out}")


def cmd_day1(args) -> None:
    """Day-1 numbers from a recorded session (#88)."""
    from pnt.payload import day1

    r = day1.report(args.session, usb_current_a=args.usb_current_a)
    out = Path(args.out) if args.out else Path(args.session).with_suffix(".day1.md")
    out.write_text(day1.to_markdown(r))
    out.with_suffix(".json").write_text(json.dumps(r, indent=2, default=str))
    print(day1.to_markdown(r))
    print(f"wrote {out} and {out.with_suffix('.json')}")


def cmd_pps_check(args) -> None:
    """ppstest and chrony checks of the PPS time base (#17, RSK-05). Run on the Pi."""
    from pnt.payload import day1

    r = day1.pps_check(args.seconds, args.device)
    text = json.dumps(r, indent=2, default=str)
    print(text)
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")


def cmd_live(args) -> None:
    """Run an estimator on the payload's (and base's) live stream (ADR-0009)."""
    import threading

    from pnt.io import linkauth
    from pnt.payload.config import parse_llh
    from pnt.payload.survey import load_reference
    from pnt.sources.live import LiveSource

    # --connect [ROLE=]ENDPOINT; without a role the first is the payload, the second the base
    roles = {}
    for i, c in enumerate(args.connect or ["tcp://pnt.local:5556"]):
        role, sep, ep = c.partition("=")
        if not sep:
            role, ep = (linkauth.SERVER_ROLES[i] if i < 2 else ""), c
        if role not in linkauth.SERVER_ROLES:
            raise SystemExit(f"live: give the role of {c!r}: payload=ENDPOINT or reference=...")
        roles[ep] = role
    auth = _link_auth(args, lambda d: linkauth.client_auth(roles, d))
    src = LiveSource(list(roles), reorder_s=args.reorder, auth=auth)
    origin = parse_llh(args.origin)
    if origin is None:
        print("waiting for the payload's session origin (or give --origin) ...")
        deadline = datetime.now().timestamp() + args.wait
        while origin is None and datetime.now().timestamp() < deadline:
            origin = (src.wait_for_meta("payload", timeout_s=1.0) or {}).get("origin_llh")
            if origin is None:
                src.meta.pop("payload", None)  # no fix yet on the Pi: wait for a newer one
        if origin is None:
            hint = "" if auth is None else (
                " If the Pi is recording, check that the keys match: a wrong pinned key or a "
                "laptop key the Pi does not trust fails the handshake silently (`pnt keys show` "
                "on both)")  # fmt: skip
            raise SystemExit(f"no origin from the payload stream; give --origin lat,lon,h.{hint}")
    reference = load_reference(args.reference) if args.reference else None
    if args.duration:
        threading.Timer(args.duration, src.stop).start()
    writer = None

    def live_meta(out: Path) -> dict:
        """What is known of the payload so far; with `--origin` that starts as nothing."""
        pi = src.meta.get("payload") or {}
        notes = f"live stream recorded on the laptop from {', '.join(src.endpoints)}; "
        notes += f"payload commit {pi.get('commit') or 'unknown'}"
        if not pi:
            notes += " (the payload sent no session metadata)"
        notes += "\n" + src.describe()
        return {"name": out.name, "platform": pi.get("platform") or "unknown",
                "origin_llh": list(origin), "simulated": False, "commit": _commit(),
                "hardware": pi.get("hardware") or ["unknown"], "reference": reference,
                "notes": notes}  # fmt: skip

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True)
        session.write_meta(out, live_meta(out))
        writer = SessionWriter(out / session.MCAP_NAME)

    lock = threading.Lock()  # with --dash the panel's thread writes; this one closes

    def tee():
        for m in src:
            with lock:
                if writer:
                    writer.write(f"/meas/{m.source}", m)
            yield m

    if args.dash:
        from pnt.dashboard.feed import live_feed

        name = f"live from {', '.join(src.endpoints)}"
        feed = live_feed(tee(), name, args.estimator, origin, reference, [src.describe()])
        try:
            _serve_dash(feed, args)  # until Ctrl-C; the panel runs the estimator
        finally:
            src.stop()
            with lock:
                if writer:
                    writer.close()
                    session.write_meta(out, live_meta(out))
                    writer = None
        print(f"live: stream {src.stats}")
        return

    last = 0
    n = 0
    try:
        for e in estimate(args.estimator, tee(), origin_llh=origin, reference=reference):
            n += 1
            if writer:
                writer.write(f"/nav/{args.estimator}", e)
            if e.t_ns - last >= 1_000_000_000:
                last = e.t_ns
                hpl = "-" if e.hpl_m is None else f"{e.hpl_m:.1f}"
                print(f"t={e.t_ns / 1e9:.1f} enu=({e.pos_enu[0]:.1f}, {e.pos_enu[1]:.1f}, "
                      f"{e.pos_enu[2]:.1f}) hpl={hpl} {e.status} {','.join(e.flags)}")  # fmt: skip
    except KeyboardInterrupt:
        pass
    finally:
        if writer:
            writer.close()
            session.write_meta(out, live_meta(out))  # the payload's meta has arrived by now
    print(f"live: {n} estimates; stream {src.stats}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="pnt", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_estimator(parser) -> None:
        parser.add_argument("--estimator", choices=sorted(ESTIMATORS), default="baseline")

    def add_keys_dir(parser) -> None:
        parser.add_argument("--keys", help="key folder (default: ~/.config/pnt/keys)")

    def add_link(parser) -> None:  # ADR-0026, #89
        add_keys_dir(parser)
        parser.add_argument(
            "--insecure",
            action="store_true",
            help="plaintext, unauthenticated stream (private link only); else keys are required",
        )

    def add_dash(parser) -> None:
        """Options of the operator panel (pnt.dashboard) on a sim run or a replay."""
        parser.add_argument("--speed", type=float, default=1.0, help="x real time (inf: no hold)")
        add_panel(parser)
        parser.add_argument(
            "--no-preflight", action="store_true", help="skip the predicted HPL strip"
        )
        parser.add_argument(
            "--banner", help="one sentence shown under the panel's top bar (e.g. a demo's label)"
        )

    def add_panel(parser) -> None:
        """Options of the operator panel that a live stream shares."""
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
    s.add_argument(
        "--inject",
        help="apply this scenario's faults to the recording (ADR-0015): a bundled scenario name "
        "or a .yaml file; fault times count from the recording's first measurement",
    )
    s.add_argument("--seed", type=int, default=0, help="for random faults with --inject")
    s.add_argument("--out", help="with --inject: also save the injected session to this folder")
    add_estimator(s)
    s.set_defaults(fn=cmd_replay)

    s = sub.add_parser("compare", help="compare a simulated session with a real one (ADR-0015)")
    s.add_argument("simulated", help="session folder or .mcap file")
    s.add_argument("real", help="session folder or .mcap file")
    s.add_argument("--source", default="lte", help="lte, gnss or baro")
    s.add_argument("--first-s", type=float, help="compare only each session's first seconds")
    s.add_argument("--out", help="also save both residual distributions as a figure")
    s.set_defaults(fn=cmd_compare)

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

    s = sub.add_parser("experiment", help="tower-removal, sensitivity-grid or sweep experiment")
    s.add_argument("name", choices=["towers", "grid", "sweep"])
    s.add_argument("scenario")
    s.add_argument("--runs", type=int, default=10)
    s.add_argument("--jobs", type=int, help="worker processes (default: all cores)")
    s.add_argument("--json")
    s.add_argument(
        "--param",
        action="append",
        metavar="PATH=v1,v2,...",
        help="sweep only: a dotted path into the scenario (or `towers`) and its values; "
        "repeat for more (default: experiments.DEFAULT_SWEEP)",
    )
    add_estimator(s)
    s.set_defaults(fn=cmd_experiment)

    s = sub.add_parser("dash", help="replay a session on the operator panel (browser)")
    s.add_argument("session", help="session folder or .mcap file")
    s.add_argument("--estimator", choices=sorted(ESTIMATORS), default="ekf")
    s.add_argument(
        "--hide-origin",
        action="store_true",
        help="keep the session origin and the towers off the panel (a real capture's location)",
    )
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

    s = sub.add_parser("frontend", help="turn raw captures into measurements")
    fe = s.add_subparsers(dest="frontend", required=True)
    s = fe.add_parser("lte", help="RTL-SDR .cu8 capture -> LTE pseudorange and doppler")
    s.add_argument("capture", help=".cu8 file; its .json sidecar sits beside it")
    s.add_argument("--sidecar", help="sidecar .json (default: beside the capture)")
    s.add_argument("--earfcn", type=int, help="override the EARFCN computed from the frequency")
    s.add_argument("--out", help="new session folder or .mcap (default: <session>-lte)")
    s.add_argument("--force", action="store_true", help="overwrite an existing --out")
    s.add_argument("--receiver", choices=["payload", "reference"], default="payload")
    s.add_argument("--no-copy", action="store_true", help="don't copy the capture's session")
    s.set_defaults(fn=cmd_frontend_lte)
    s = fe.add_parser("gnss", help="a session's gpsd SKY reports -> gnss_health (ADR-0031)")
    s.add_argument("session", help="session folder or its session.mcap")
    s.add_argument("--out", help="new session folder (default: <session>-gnss)")
    s.add_argument("--force", action="store_true", help="overwrite an existing --out")
    s.add_argument("--ref-cn0", type=float, help="open-sky C/N0, dB-Hz (default: ADR-0031)")
    s.add_argument("--low-cn0", type=float, help="C/N0 at loss, dB-Hz (default: ADR-0031)")
    s.add_argument("--top-k", type=int, help="strongest satellites averaged (default: ADR-0031)")
    s.set_defaults(fn=cmd_frontend_gnss)

    s = sub.add_parser("record", help="capture a real session on the Pi (payload or base)")
    s.add_argument("--out", help="default: data/sessions/<date>-<platform>-<place>")
    s.add_argument("--platform", default="handheld", help="drone | handheld | vehicle | static")
    s.add_argument("--place", default="carleton", help="where, for the folder name")
    s.add_argument("--duration", type=float, help="seconds (default: until Ctrl-C)")
    s.add_argument("--receiver", choices=["payload", "reference"], default="payload")
    s.add_argument("--origin", help="session origin lat,lon,h (default: the first 3D fix)")
    s.add_argument("--reference", help="survey file for meta.yaml `reference` (pnt survey)")
    s.add_argument("--notes", default="")
    s.add_argument("--sdr", action="append", help="NAME:FREQ[:rate=..][:gain=..][:dev=..]")
    s.add_argument("--no-gnss", action="store_true")
    s.add_argument("--gpsd-port", type=int, default=2947)
    s.add_argument("--gnss-hw", default="adafruit-gps-hat", help="meta.yaml name (base: neo-6m)")
    s.add_argument("--no-imu", action="store_true")
    s.add_argument("--imu-rate", type=float, default=100.0, help="Hz")
    s.add_argument("--no-baro", action="store_true")
    s.add_argument("--baro-rate", type=float, default=10.0, help="Hz")
    s.add_argument("--baro-start-up", type=float, help="m above origin at start, if no GPS fix")
    s.add_argument("--no-camera", action="store_true")
    s.add_argument("--fc", help="flight controller: serial device or udp:host:port (default auto)")
    s.add_argument("--fc-baud", type=int, default=115200)
    s.add_argument("--no-fc", action="store_true")
    s.add_argument("--wifi", action="store_true", help="passive Wi-Fi scans (pauses the stream)")
    s.add_argument("--wifi-iface", default="wlan0")
    s.add_argument("--stream", default="tcp://*:5556", help="ZeroMQ endpoint to publish on")
    s.add_argument("--no-stream", action="store_true")
    add_link(s)
    s.set_defaults(fn=cmd_record)

    s = sub.add_parser("survey", help="survey the reference station from a session's fixes")
    s.add_argument("session")
    s.add_argument("--batch-s", type=float, default=600.0, help="batch length for sigma_m")
    s.add_argument("--out", help="default: <session>.survey.yaml beside the folder")
    s.set_defaults(fn=cmd_survey)

    s = sub.add_parser("day1", help="day-1 numbers (IMU jitter, CPU, drops, PPS) of a session")
    s.add_argument("session")
    s.add_argument("--usb-current-a", type=float, help="read off the DPS-150 by hand")
    s.add_argument("--out", help="default: <session>.day1.md beside the folder")
    s.set_defaults(fn=cmd_day1)

    s = sub.add_parser("pps-check", help="ppstest + chrony checks of the PPS time base (Pi)")
    s.add_argument("--seconds", type=float, default=30.0)
    s.add_argument("--device", default="/dev/pps0")
    s.add_argument("--out", help="JSON file for the result")
    s.set_defaults(fn=cmd_pps_check)

    s = sub.add_parser("live", help="run an estimator on the payload's live stream")
    s.add_argument("--connect", action="append", help="[payload=|reference=]endpoint, repeat "
                   "for the base; untagged: payload first, then reference "
                   "(default: tcp://pnt.local:5556)")  # fmt: skip
    s.add_argument("--origin", help="lat,lon,h (default: from the payload's stream)")
    s.add_argument("--wait", type=float, default=60.0, help="s to wait for the origin")
    s.add_argument("--reference", help="survey file of the reference station")
    s.add_argument("--reorder", type=float, default=1.0, help="s held to put records in order")
    s.add_argument("--duration", type=float, help="seconds (default: until Ctrl-C)")
    s.add_argument("--out", help="also record the stream and estimates to this session folder")
    s.add_argument(
        "--dash",
        action="store_true",
        help="show it on the operator panel (with --out only the stream is recorded)",
    )
    add_estimator(s)
    add_panel(s)
    add_link(s)
    s.set_defaults(fn=cmd_live)

    # Gamepad -> ESP32 RC bridge, tethered hover only (ADR-0029). Self-contained block.
    from pnt.flight import rc_link

    s = sub.add_parser("rc", help="fly a tethered hover from a gamepad via the ESP32 bridge")
    rc_link.add_arguments(s)
    s.set_defaults(fn=rc_link.cmd_rc)

    s = sub.add_parser("keys", help="CurveZMQ keys for the payload/base/laptop links (ADR-0026)")
    ks = s.add_subparsers(dest="keys_cmd", required=True)
    k = ks.add_parser("gen", help="make this host's key pair (secret stays here, mode 600)")
    k.add_argument("--role", required=True, choices=["payload", "reference", "laptop"])
    k.add_argument("--force", action="store_true", help="replace an existing key pair")
    add_keys_dir(k)
    k = ks.add_parser("show", help="this host's public keys and the keys it trusts")
    add_keys_dir(k)
    k = ks.add_parser("trust", help="trust a peer's public key")
    k.add_argument("name", help="payload | reference | laptop[-suffix]")
    k.add_argument("key", help="the peer's public key (z85, from its `pnt keys show`) or file")
    k.add_argument("--force", action="store_true", help="replace an existing trusted key")
    add_keys_dir(k)
    s.set_defaults(fn=cmd_keys)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
