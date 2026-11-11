"""False alarms per hour on clean data, sim and real, with their exposure time (#274).

One stated rate per alarm, with the hours behind it and a one-sided 95 % upper bound, so "0 false
alarms" is never said without "in how many hours".

**What counts as a false alarm** is `pnt.metrics`' definition, reused, not a second one: an
alarm is an epoch carrying one of `metrics.ALARM_FLAGS` (`gnss_excluded`, `spoof_suspected`,
`time_spoof_suspected`); a run of alarmed epochs counts once, when it has lasted
`metrics.ALARM_HOLD_S` (`metrics._alarm_times`); it is false when that onset falls outside every
spoof window (`metrics.SPOOF_ATTACKS`); and the exposure is the time outside spoof windows (the
sum of epoch steps, as `metrics.score`). The script checks on every sim run that its count for
the union of those flags equals `metrics.score`'s `false_alarms_per_h` times that exposure.

Alarm types reported, each counted with that same rule (onset once held for `ALARM_HOLD_S`,
outside spoof windows):
- `any (metrics)`: the union of `ALARM_FLAGS`, the number `pnt eval` reports.
- `gnss_excluded`, `spoof_suspected`, `time_spoof_suspected`: each flag alone. `gnss_excluded` is
  the GNSS jump or exclusion alarm (the filter's gate, a latched jump guard, the spoof alarm);
  `spoof_suspected` is the tower spoof monitor (`ekf-spoof`) or the calibrated filter's own
  towers-vs-GNSS test; `time_spoof_suspected` is the time-integrity alarm. The tower monitor can
  only alarm while one of its tests holds an opinion (`min_sites` sites in both windows), so the
  report also gives those hours: zero alarms in hours it did not test say nothing about it.
- `gnss_jump_latched`: the jump guard's latch (`ekf-guard`, ADR-0038). Not in `ALARM_FLAGS`, so
  `pnt.metrics` has no false-alarm count for it; it is defined here the same way. (A latch also
  rejects GNSS, so it shows in `gnss_excluded` too.)
- `sky suspect+` and `sky spoofed`: the spoof decision (`integrity.sky.SpoofDecision`, ADR-0041)
  at each estimate, fed the run's skyviews and the estimate's flags, as the panel does; an alarm
  epoch is level `suspect` or `spoofed` (the first), or `spoofed` only (the second). Not in
  `pnt.metrics`; defined here the same way. Without a fresh skyview it judges the flags alone
  (`jump_latched`, `towers_refute`), so it is reported on every run, and the runs with a sky say
  so.
- `do not navigate (HPL > AL)`: status `unsafe`, the horizontal protection level over the alert
  limit (`metrics.ALERT_LIMIT_M`, the estimators' own default). An unavailable-but-safe warning,
  not a spoof alarm. Counted the same way, but only from the end of start-up as the panel does
  (`dashboard.health`: the first `nominal` estimate, or `STARTUP_MAX_S` after the first estimate),
  because every filter starts with the first fix's wide covariance; its exposure starts there.
- `time PL > limit`: the panel's own time alert (`dashboard.health.TIME_OVER`), the time
  protection level (`integrity.protection.tpl`) over `metrics.TIME_ALERT_LIMIT_S`, with the same
  start-up rule.

Data (`run`):
- Sim: every `nominal` entry of the `challenge` legs (`challenge-drone`, `challenge-timing`,
  `challenge-approach`, ADR-0030) and of the `realistic` set, and the standalone `nominal`
  scenario (REQ-04's false-alarm run), seeds 0 to N-1. `nominal` and `spoof-jump-sky` fly the
  `square` trajectory, whose instant 90-degree turns no vehicle can fly (`sim.trajectory`), so
  they are reported apart from the challenge and realistic legs. The clean part of
  the faulted entries is left out: before its first fault a faulted entry of a set is the same
  draws as that set's `nominal` entry at the same seed (checked: identical records), so counting
  it would count the same samples twice. `spoof-jump-sky` is the one committed scenario with a
  simulated GPS sky, so its clean part (before the spoof at 150 s, which is how `pnt.metrics`
  counts it) is reported as its own column, for the sky checks. Its GNSS, barometer and tower
  records before the spoof are the standalone `nominal`'s at the same seed (checked: identical),
  with skyviews added, so the pooled column leaves it out rather than count those samples
  twice.
- Real: every session under `--sessions` with GNSS position records, replayed through the same
  estimators. Static sessions, so no real flight hours. Only the session name and duration are
  reported: no position, no coordinate, no origin leaves this script (the decision's receiver
  position is the estimate's, in memory).

    python analysis/false_alarm_rate.py run --sessions <dir> --seeds 50 --jobs 3 \\
        --label main --out analysis/results/runs/false-alarm-rate/main.json
    python analysis/false_alarm_rate.py report <run.json> ... \\
        --out analysis/results/false-alarm-rate/summary.md

`run` records the commit of the `pnt` package it imported, so another code tree (e.g. an open
PR's commits on a throwaway branch, via `PYTHONPATH`) can be run with `--no-sim --label ...` and
reported beside main. Per-run rows go to the git-ignored `analysis/results/runs/`.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import time
from collections import Counter
from functools import partial
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from pnt.cli import _commit
from pnt.core.frames import enu_to_llh
from pnt.core.measurement import Measurement
from pnt.dashboard.health import STARTUP_MAX_S
from pnt.experiments import _map
from pnt.integrity.protection import tpl
from pnt.integrity.sky import GpsAlmanac, SpoofDecision
from pnt.integrity.spoof_monitor import SpoofMonitor
from pnt.metrics import (
    ALARM_FLAGS,
    ALARM_HOLD_S,
    SPOOF_ATTACKS,
    TIME_ALERT_LIMIT_S,
    _alarm_times,
    score,
)
from pnt.nav import ESTIMATORS as REGISTRY
from pnt.nav import ekf, estimate
from pnt.sim.scenario import T0_NS, generate, load

RESULTS = Path(__file__).resolve().parent / "results"
RUNS = RESULTS / "runs" / "false-alarm-rate"  # git-ignored
OUT = RESULTS / "false-alarm-rate" / "summary.md"

ESTIMATORS = ("ekf", "ekf-guard", "ekf-spoof")
# The clean sim entries: every `nominal` entry of the challenge legs and the realistic set
SIM_ENTRIES = (
    "challenge-drone-nominal",
    "challenge-timing-nominal",
    "challenge-approach-nominal",
    "realistic-nominal",
    "nominal",
)
SKY_ENTRY = "spoof-jump-sky"  # clean part before its spoof only (module docstring)
# Faults whose window is not clean: metrics' spoof attacks, and a faked sky (the sky checks'
# attack; in spoof-jump-sky it starts with the jump, so the clean part is metrics' own)
NOT_CLEAN = SPOOF_ATTACKS | {"fake_sky"}

FLAG_TYPES = ("gnss_excluded", "spoof_suspected", "time_spoof_suspected", "gnss_jump_latched")
SPOOF_TYPES = ("any (metrics)", *FLAG_TYPES, "sky suspect+", "sky spoofed")
SAFETY_TYPES = ("do not navigate (HPL > AL)", "time PL > limit")
TYPES = (*SPOOF_TYPES, *SAFETY_TYPES)
CONF = 0.95
TOWER_MONITOR = "ekf-spoof"


class _WatchedMonitor:
    """The `ekf-spoof` monitor, unchanged, noting at each estimate whether any tower test holds
    an opinion (fewer than `min_sites` sites in both windows gives none), so its exposure can be
    stated as the hours it actually tested."""

    def __init__(self, main, tested: list):
        self.mon = SpoofMonitor(main)
        self.tested = tested

    def process(self, m) -> None:
        self.mon.process(m)

    def estimate(self, est):
        out = self.mon.estimate(est)
        self.tested.append(any(v is not None for v in self.mon.report.towers.values()))
        return out


def _estimator(name: str):
    """(the estimator to run, list filled per epoch with "tower test has an opinion" or None).
    `ekf-spoof` is rebuilt with the watched monitor, after checking it is still exactly
    `ekf.run` with `SpoofMonitor`."""
    if name != TOWER_MONITOR:
        return name, None
    reg = REGISTRY[name]
    if getattr(reg, "func", None) is not ekf.run or reg.keywords != {"monitor": SpoofMonitor}:
        raise RuntimeError(f"{name} is no longer ekf.run with SpoofMonitor: update this script")
    tested: list = []
    return partial(ekf.run, monitor=lambda main: _WatchedMonitor(main, tested)), tested


# --- counting -----------------------------------------------------------------------------


def poisson_upper(k: int, hours: float, conf: float = CONF) -> float:
    """One-sided exact Poisson upper bound on the rate per hour, `k` events in `hours`:
    chi2.ppf(conf, 2k + 2) / 2 / hours. For k = 0 at 95 % that is -ln(0.05) / T = 2.996 / T."""
    if hours <= 0:
        return math.nan
    return float(chi2.ppf(conf, 2 * k + 2) / 2.0 / hours)


def rate_row(k: int, hours: float, conf: float = CONF) -> dict:
    """Onsets, exposure, rate per hour and the one-sided upper bound."""
    return {
        "onsets": int(k),
        "hours": float(hours),
        "rate_per_h": k / hours if hours > 0 else math.nan,
        "upper_per_h": poisson_upper(k, hours, conf),
    }


def spoof_windows(spec: dict, t0_ns: int, t_end_ns: int) -> list[tuple[int, int]]:
    """[start, end) of each fault that is not clean (NOT_CLEAN), as `metrics.score` builds its
    spoof windows (a fault with no end runs past the last epoch)."""
    out = []
    for f in spec.get("faults", []):
        if f["type"] in NOT_CLEAN:
            start = t0_ns + int(round(f.get("start_s", 0.0) * 1e9))
            end = t0_ns + int(round(f["end_s"] * 1e9)) if "end_s" in f else t_end_ns + 1
            out.append((start, end))
    return out


def count(t_ns, alarm, windows=(), valid=None, hold_s: float = ALARM_HOLD_S) -> tuple[list, float]:
    """False-alarm onsets and clean exposure (hours), by `pnt.metrics`' rule (module docstring).

    `t_ns` epoch times, `alarm` the per-epoch alarm, `windows` the [start, end) spans that are not
    clean. `valid` (optional) masks epochs that may alarm at all (the start-up rule of the
    protection-level alerts): alarms outside it are dropped before the hold, and exposure counts
    only steps into valid epochs. Returns (onset times in ns, hours)."""
    t = np.asarray(t_ns, dtype=np.int64)
    a = np.asarray(alarm, dtype=bool)
    v = np.ones(len(t), bool) if valid is None else np.asarray(valid, dtype=bool)
    onsets = _alarm_times(t, a & v, int(round(hold_s * 1e9)))
    false = [x for x in onsets if not any(s <= x < e for s, e in windows)]
    clean = v.copy()
    for s, e in windows:
        clean &= ~((t >= s) & (t < e))
    hours = float(np.sum(np.diff(t)[clean[1:]])) / 3.6e12 if len(t) > 1 else 0.0
    return false, hours


def settled(estimates) -> np.ndarray:
    """Epochs after start-up, as the panel latches alerts (`dashboard.health.NavHealth`): from
    the first `nominal` estimate, or `STARTUP_MAX_S` after the first estimate."""
    out = np.zeros(len(estimates), bool)
    if not estimates:
        return out
    t0, on = estimates[0].t_ns, False
    for i, e in enumerate(estimates):
        on = on or e.status == "nominal" or (e.t_ns - t0) / 1e9 >= STARTUP_MAX_S
        out[i] = on
    return out


def sky_levels(estimates, measurements, origin_llh, almanac) -> list[str]:
    """The spoof decision's level at each estimate: skyviews (`gnss_health` with `meta.snr`) up
    to its time, seen from the estimate's own position, and its flags (as `analysis/spoof_sky.py`
    judges the full chain). Positions stay in memory."""
    views = [m for m in measurements if m.kind == "gnss_health" and m.meta and m.meta.get("snr")]
    d = SpoofDecision(almanac=almanac)
    out, k = [], 0
    for e in estimates:
        while k < len(views) and views[k].t_ns <= e.t_ns:
            d.measurement(views[k], enu_to_llh(e.pos_enu, origin_llh))
            k += 1
        out.append(d.decide(e.t_ns, e.flags).level)
    return out


def alarms(estimates, levels) -> dict[str, np.ndarray]:
    """Per alarm type, the per-epoch alarm (module docstring)."""
    flags = [set(e.flags) for e in estimates]
    out = {"any (metrics)": np.array([bool(ALARM_FLAGS & f) for f in flags])}
    for name in FLAG_TYPES:
        out[name] = np.array([name in f for f in flags])
    out["sky suspect+"] = np.array([lv in ("suspect", "spoofed") for lv in levels])
    out["sky spoofed"] = np.array([lv == "spoofed" for lv in levels])
    out["do not navigate (HPL > AL)"] = np.array([e.status == "unsafe" for e in estimates])
    out["time PL > limit"] = np.array(
        [(tpl(e.clock_sigma_s) or 0.0) > TIME_ALERT_LIMIT_S for e in estimates]
    )
    return out


def run_row(estimates, measurements, origin_llh, windows, almanac, tested=None) -> dict:
    """Counts for one run of one estimator: onset times (s from the first estimate) per type,
    exposure hours (all epochs, and after start-up), skyviews seen, flag epochs, and (`tested`,
    the tower monitor only) the clean hours in which a tower test held an opinion."""
    t = np.array([e.t_ns for e in estimates], dtype=np.int64)
    if tested is not None:
        tested = np.asarray(tested, bool)
        if len(tested) != len(t):
            raise RuntimeError("tower monitor saw a different number of epochs")
    levels = sky_levels(estimates, measurements, origin_llh, almanac)
    ok = settled(estimates)
    row = {"onsets_s": {}, "hours": 0.0, "settled_hours": 0.0}
    for name, a in alarms(estimates, levels).items():
        valid = ok if name in SAFETY_TYPES else None
        onsets, hours = count(t, a, windows, valid)
        row["onsets_s"][name] = [round((x - t[0]) / 1e9, 1) for x in onsets]
        row["settled_hours" if name in SAFETY_TYPES else "hours"] = hours
    row["skyviews"] = sum(
        1 for m in measurements if m.kind == "gnss_health" and m.meta and m.meta.get("snr")
    )
    row["flag_epochs"] = dict(Counter(f for e in estimates for f in e.flags))
    row["epochs"] = len(estimates)
    row["tower_test_hours"] = (
        None if tested is None else count(t, np.zeros(len(t), bool), windows, tested)[1]
    )
    return row


# --- runs ---------------------------------------------------------------------------------


def sim_task(entry: str, seed: int) -> list[dict]:
    """Every estimator on one clean sim run."""
    spec = load(entry)
    run = generate(spec, seed=seed)
    almanac = GpsAlmanac()
    rows = []
    for name in ESTIMATORS:
        meas, origin = run.measurements, spec.get("origin_llh")
        fn, tested = _estimator(name)
        est = list(estimate(fn, meas, origin_llh=origin, reference=run.reference))
        windows = spoof_windows(spec, T0_NS, est[-1].t_ns)
        row = run_row(est, meas, origin, windows, almanac, tested)
        m = score(est, run.truth, spec, T0_NS)
        # metrics' own count for the union of ALARM_FLAGS (consistency check, module docstring)
        row["metrics_false"] = (
            None
            if math.isnan(m.false_alarms_per_h)
            else round(m.false_alarms_per_h * row["hours"])
        )
        rows.append({"kind": "sim", "entry": entry, "seed": seed, "estimator": name, **row})
    return rows


def real_sessions(root: Path) -> list[Path]:
    """Session folders under `root` with GNSS position records (read from each session)."""
    from pnt.io import session
    from pnt.io.mcap_log import read_session

    out = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        try:
            mcap = session.mcap_path(p)
            session.read_meta(p)
        except (FileNotFoundError, ValueError):
            continue
        if any(r.kind == "position_enu" for _, r in read_session(mcap, topics=["/meas/gnss"])):
            out.append(p)
    return out


def real_task(path: str) -> list[dict]:
    """Every estimator on one real session, replayed as recorded (`pnt replay`). Only the name
    and duration of the session are kept."""
    from pnt.io import session
    from pnt.io.mcap_log import read_session

    meta = session.read_meta(path)
    origin = meta.get("origin_llh")
    meas = [
        r
        for _, r in read_session(session.mcap_path(path), topics=["/meas/"])
        if isinstance(r, Measurement)
    ]
    almanac = GpsAlmanac()
    rows = []
    for name in ESTIMATORS:
        fn, tested = _estimator(name)
        est = list(estimate(fn, meas, origin_llh=origin, reference=meta.get("reference")))
        row = run_row(est, meas, origin, [], almanac, tested)
        rows.append(
            {
                "kind": "real",
                "entry": Path(path).name,
                "seed": None,
                "estimator": name,
                "platform": meta.get("platform"),
                "metrics_false": None,
                **row,
            }
        )
    return rows


def cmd_run(args) -> None:
    t_start = time.time()
    tasks = []
    if not args.no_sim:
        entries = [*SIM_ENTRIES, SKY_ENTRY]
        tasks = [(e, s) for e in entries for s in range(args.seeds)]
    rows = [r for part in _map(sim_task, tasks, args.jobs) for r in part]
    sessions = real_sessions(Path(args.sessions)) if args.sessions else []
    rows += [r for part in _map(real_task, [(str(p),) for p in sessions], args.jobs) for r in part]
    out = {
        "label": args.label,
        "commit": _commit(),
        "seeds": [0, args.seeds - 1] if not args.no_sim else None,
        "estimators": list(ESTIMATORS),
        "sim_entries": [] if args.no_sim else [*SIM_ENTRIES, SKY_ENTRY],
        "sessions": [p.name for p in sessions],
        "runtime_s": round(time.time() - t_start, 1),
        "jobs": args.jobs,
        "machine": platform.machine(),
        "rows": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f"{len(rows)} rows, {out['runtime_s']} s, commit {out['commit']} -> {args.out}")


# --- report -------------------------------------------------------------------------------


def kind_of(row: dict) -> str:
    """Data kind of a row: the challenge and realistic legs, the square-circuit runs (instant
    turns), the sky run before its spoof, or a real (static) session."""
    if row["kind"] == "real":
        return "real, static" if row.get("platform") == "static" else "real"
    if row["entry"] == SKY_ENTRY:
        return "sim, square, before spoof (sky)"
    return "sim, square circuit" if row["entry"] == "nominal" else "sim, challenge + realistic"


def pool(rows: list[dict], name: str) -> dict:
    """Onsets and exposure of one alarm type summed over rows."""
    k = sum(len(r["onsets_s"][name]) for r in rows)
    h = sum(r["settled_hours" if name in SAFETY_TYPES else "hours"] for r in rows)
    return rate_row(k, h)


def _num(x: float, nd: int = 3) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}g}"


def _cell(p: dict) -> str:
    return (
        f"{p['onsets']} / {p['hours']:.2f} h / {_num(p['rate_per_h'])} / {_num(p['upper_per_h'])}"
    )


def seeds_text(res: dict) -> str:
    sim = res["sim_entries"]
    if not sim:
        return "no sim; "
    return f"sim seeds {res['seeds'][0]}-{res['seeds'][1]} of {', '.join(sim)}; "


def report(results: list[dict]) -> str:
    """The summary Markdown from one or more `run` outputs."""
    lines = ["# False alarms per hour on clean data (#274)", ""]
    for res in results:
        lines.append(
            f"- `{res['label']}`: commit `{res['commit']}`; "
            + seeds_text(res)
            + f"real sessions: {', '.join(res['sessions']) or 'none'}; "
            f"{res['runtime_s']:.0f} s with {res['jobs']} workers ({res['machine']})"
        )
    lines += [
        "",
        "Each cell: false-alarm onsets / exposure hours / rate per hour / one-sided 95 % upper "
        "bound per hour (exact Poisson; zero events in T hours gives 3.0/T).",
        "",
    ]
    cols = []  # (heading, rows)
    for res in results:
        by_kind: dict[str, list] = {}
        for r in res["rows"]:
            by_kind.setdefault(kind_of(r), []).append(r)
        for kind, rs in by_kind.items():
            cols.append((f"{kind} (`{res['label']}`)", rs))
        if len(by_kind) > 1:  # spoof-jump-sky repeats nominal's draws (module docstring)
            pooled = [r for r in res["rows"] if r["entry"] != SKY_ENTRY]
            cols.append((f"**all clean data, sky run excluded** (`{res['label']}`)", pooled))
    tables = (
        ("Spoof and integrity alarms", SPOOF_TYPES),
        ("Do-not-navigate alerts (unavailable, not a spoof alarm)", SAFETY_TYPES),
    )
    for title, types in tables:
        lines += [f"## {title}", ""]
        lines.append("| Estimator | Alarm | " + " | ".join(h for h, _ in cols) + " |")
        lines.append("| --- | --- |" + " --- |" * len(cols))
        for est in ESTIMATORS:
            for name in types:
                cells = [
                    _cell(pool([r for r in rs if r["estimator"] == est], name)) for _, rs in cols
                ]
                lines.append(f"| `{est}` | {name} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += [
        "## Exposure per entry and session",
        "",
        "Hours per estimator are clean hours (the start-up rule takes a little off the "
        "do-not-navigate rows). The tower monitor's column is the part of them in which at least "
        "one of its tower tests held an opinion (it needs `min_sites` sites in both windows); "
        "outside it `ekf-spoof` cannot raise its own alarm.",
        "",
        "| Data | Entry or session | Runs | Hours per estimator | `ekf-spoof` tower tests "
        "testing (h) | Skyviews per run |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for res in results:
        seen: dict = {}
        for r in res["rows"]:
            key = (kind_of(r), r["entry"])
            n, h, tt, sky = seen.get(key, (0, 0.0, 0.0, 0))
            if r["estimator"] == ESTIMATORS[0]:
                n, h, sky = n + 1, h + r["hours"], sky + r["skyviews"]
            if r["estimator"] == TOWER_MONITOR:
                tt += r["tower_test_hours"]
            seen[key] = (n, h, tt, sky)
        for (kind, entry), (n, h, tt, sky) in seen.items():
            lines.append(
                f"| {kind} (`{res['label']}`) | `{entry}` | {n} | {h:.3f} | {tt:.3f} "
                f"| {sky / n:.0f} |"
            )
    lines += [
        "",
        "## Every false alarm and do-not-navigate onset",
        "",
        "Seconds from the run's first estimate. `any (metrics)` is left out: it is the union of "
        "the three `ALARM_FLAGS` rows.",
        "",
    ]
    any_alarm = False
    for res in results:
        for r in res["rows"]:
            for name in TYPES[1:]:
                times = r["onsets_s"][name]
                if not times:
                    continue
                any_alarm = True
                seed = "" if r["seed"] is None else f", seed {r['seed']}"
                lines.append(
                    f"- `{res['label']}`, {kind_of(r)}, `{r['entry']}`{seed}, `{r['estimator']}`: "
                    f"{name}, {len(times)} at " + ", ".join(f"{t:.1f}" for t in times) + " s"
                )
    if not any_alarm:
        lines.append("None.")
    sim_rows = [r for res in results for r in res["rows"] if r["metrics_false"] is not None]
    mism = [r for r in sim_rows if r["metrics_false"] != len(r["onsets_s"]["any (metrics)"])]
    lines += [
        "",
        f"Check against `pnt.metrics.score` (`any (metrics)` count): {len(sim_rows)} sim runs, "
        f"{len(mism)} disagree.",
        "",
    ]
    return "\n".join(lines)


def cmd_report(args) -> None:
    results = [json.loads(Path(p).read_text()) for p in args.runs]
    text = report(results)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
    print(text)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--sessions", help="folder of real sessions (git-ignored data/sessions)")
    r.add_argument("--seeds", type=int, default=50)
    r.add_argument("--jobs", type=int, default=3)
    r.add_argument("--no-sim", action="store_true", help="real sessions only")
    r.add_argument("--label", default="main")
    r.add_argument("--out", default=str(RUNS / "main.json"))
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("report")
    s.add_argument("runs", nargs="+")
    s.add_argument("--out", default=None, help=f"write the Markdown here (e.g. {OUT})")
    s.set_defaults(fn=cmd_report)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
