"""GNSS spoof detection before and after the opt-in tower monitor (#173), sim.

One command, from a clean commit:

    python analysis/spoof_detection.py --seeds 50 --mhss-seeds 5 --jobs 2

writes `summary.md` (the tables) and `detection.png` to `analysis/results/spoof-detection/`
(committed, so only from a clean tree: REQ-10), and one row per run to
`analysis/results/runs/spoof-detection.json` (git-ignored, rounded, missing values as null).
`--redraw` rebuilds the summary and figure from that file.

Legs, each from committed scenarios (no scenario file is added):
- `drone`: the `challenge-drone` leg as committed (1 to 3 cells heard per epoch).
- `drone-many`: the same spec with `sources.lte.hearing` = {model: range, hearing_km: 3}, every
  sector within 3 km heard (about 50 sectors on 17 eNBs after the cell lookup).
- `realistic`: the `realistic` set (synthetic towers).

Runs: `nominal`, `outage`, `spoof-ramp`, `spoof-jump` (300 m) and `time-spoof` on each leg, every
estimator pair being the unchanged estimator and the same one with `integrity.spoof_monitor`
(`ekf` / `ekf-spoof`, `ekf-calibrated` / `ekf-calibrated-spoof`), paired on the same seeds;
`ekf-mhss` on `--mhss-seeds`. The monitor is for the slow ramp; the jump and the time spoof are
controls (it must not lose what the filter already catches). Jumps are studied in #176, and
refusing a detected jump is #184.

Seeds 0 to N-1 are the reported seeds. The monitor's settings were chosen on seeds 100-109.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import multiprocessing
import platform
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.metrics import SPOOF_ATTACKS, score
from pnt.nav import ESTIMATORS, estimate
from pnt.sim.scenario import T0_NS, generate, load

RESULTS = Path(__file__).resolve().parent / "results"
OUT = RESULTS / "spoof-detection"  # committed: summary.md, detection.png
RUNS = RESULTS / "runs" / "spoof-detection.json"  # git-ignored: one row per run
PAIRS = (("ekf", "ekf-spoof"), ("ekf-calibrated", "ekf-calibrated-spoof"))
FAST = tuple(e for p in PAIRS for e in p)
MHSS = "ekf-mhss"
LEGS = {"drone": "challenge-drone", "drone-many": "challenge-drone", "realistic": "realistic"}
TABLE_LEGS = tuple(LEGS)
TABLE_ENTRIES = ("nominal", "outage", "spoof-ramp", "spoof-jump", "time-spoof")
MANY_HEARING = {"model": "range", "hearing_km": 3}
# Categorical slots 1-4 in a fixed order, and recessive ink (analysis/lte_table_audit.py)
COLOURS = {"ekf": "#2a78d6", "ekf-spoof": "#eb6834", "ekf-calibrated": "#1baf7a",
           "ekf-calibrated-spoof": "#eda100"}  # fmt: skip
INK, GRID = "#52514e", "#e4e3df"


def case_id(leg: str, entry: str) -> str:
    return f"{leg}:{entry}"


def spec_of(case: str) -> dict:
    """The scenario spec of a case id, built from the committed environment."""
    leg, entry = case.split(":")
    spec = copy.deepcopy(load(f"{LEGS[leg]}-{entry}"))
    if leg == "drone-many":
        spec["sources"]["lte"]["hearing"] = dict(MANY_HEARING)
    spec["name"] = case
    return spec


def _with_monitor_log(name: str, log: list):
    """The registered estimator `name`; for a `-spoof` one, its monitor's tower-test report is
    appended to `log` once a second."""
    fn = ESTIMATORS[name]
    if not name.endswith("-spoof"):
        return fn
    inner = fn.keywords["monitor"]

    def factory(f):
        mon = inner(f)
        wrapped = mon.estimate

        def est(e):
            out = wrapped(e)
            if mon.report.t_ns and (not log or log[-1][0] != mon.report.t_ns):
                log.append((mon.report.t_ns, dict(mon.report.towers)))
            return out

        mon.estimate = est
        return mon

    return partial(fn.func, *fn.args, **{**fn.keywords, "monitor": factory})


def _at(t: np.ndarray, x: np.ndarray, s: float) -> float:
    i = int(np.searchsorted(t, s))
    return float(x[i]) if i < len(t) else float("nan")


def run_one(case: str, estimator: str, seed: int) -> dict:
    spec = spec_of(case)
    run = generate(spec, seed=seed)
    log: list = []
    # CPU time of this process, not wall time: a wall clock also counts the machine sleeping
    # (#189: two runs logged 1,870 s, of which 1,859 s was the laptop asleep) and other jobs
    cpu0 = time.process_time()
    est = list(
        estimate(
            _with_monitor_log(estimator, log),
            run.measurements,
            origin_llh=spec.get("origin_llh"),
            reference=run.reference,
        )
    )
    cpu_s = time.process_time() - cpu0
    m = score(est, run.truth, spec, T0_NS)
    row = {
        "case": case,
        "estimator": estimator,
        "seed": seed,
        "cpu_s": cpu_s,
        "detect_delay_s": m.detect_delay_s,
        "false_alarms_per_h": m.false_alarms_per_h,
        "hazardous_epochs": m.hazardous_epochs,
        "misleading_epochs": m.misleading_epochs,
    }
    spoofs = [f for f in spec.get("faults", []) if f["type"] in SPOOF_ATTACKS]
    if spoofs and not math.isnan(m.detect_delay_s):
        tmap = {g.t_ns: g for g in run.truth}
        pairs = [(e, tmap[e.t_ns]) for e in est if e.t_ns in tmap]
        t = np.array([(e.t_ns - T0_NS) / 1e9 for e, _ in pairs])
        err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
        s0 = float(spoofs[0].get("start_s", 0.0))
        row["err_at_alert"] = _at(t, err, s0 + m.detect_delay_s)
    if log:
        for key in log[0][1]:
            vals = [r[key] for _, r in log if r.get(key) is not None]
            row[f"tower_test_{key}_opinion_share"] = len(vals) / len(log)
            row[f"tower_test_{key}_sigma_med_m"] = (
                float(np.median([v[4] for v in vals])) if vals else float("nan")
            )
    return row


def plan(seeds: int, mhss_seeds: int) -> list[tuple[str, str, int]]:
    cases = [case_id(leg, entry) for leg in TABLE_LEGS for entry in TABLE_ENTRIES]
    tasks = [(c, e, s) for c in cases for e in FAST for s in range(seeds)]
    tasks += [(c, MHSS, s) for c in cases for s in range(mhss_seeds)]
    return tasks


def host() -> str:
    """Where the run ran: OS, CPU model and Python version (CPU times depend on it)."""
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return f"{platform.system()}, {cpu}, Python {platform.python_version()}"


def _map(tasks, jobs: int) -> list[dict]:
    if jobs <= 1:
        return [run_one(*t) for t in tasks]
    ctx = multiprocessing.get_context("forkserver")
    with ProcessPoolExecutor(jobs, mp_context=ctx) as pool:
        return list(pool.map(run_one, *zip(*tasks, strict=True), chunksize=4))


# --- summary -------------------------------------------------------------------------------------
def _rows(runs, case, est):
    return [r for r in runs if r["case"] == case and r["estimator"] == est]


def _f(x, nd=0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:,.{nd}f}"


def _med(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return float(np.median(xs)) if xs else float("nan")


def _max(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return float(max(xs)) if xs else float("nan")


def _mean(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return float(np.mean(xs)) if xs else float("nan")


def detection(rs) -> dict:
    d = [r["detect_delay_s"] for r in rs]
    hit = [x for x in d if not math.isnan(x)]
    return {
        "n": len(rs),
        "detected": len(hit),
        "tta_med": _med(hit),
        "tta_max": _max(hit),
        "err_at_alert": _med([r.get("err_at_alert", math.nan) for r in rs]),
        "hazardous": _mean([r["hazardous_epochs"] for r in rs]),
        "fa_h": _mean([r["false_alarms_per_h"] for r in rs]),
    }


def ests_in(runs) -> list[str]:
    present = {r["estimator"] for r in runs}
    return [e for e in (*FAST, MHSS) if e in present]


def mhss_text(n: int) -> str:
    return f"`{MHSS}` 0–{n - 1}" if n > 0 else f"`{MHSS}` not run"


def summary(data: dict) -> str:
    runs, meta = data["runs"], data["meta"]
    lines = [
        "# Spoof detection, before and after the tower monitor (#173)",
        "",
        f"Sim, every value `TBC`. Commit {meta['commit']}, `{meta['command']}`, "
        f"{meta['minutes']:.1f} min on {meta.get('host', 'an unrecorded host')}. "
        f"Seeds 0–{meta['seeds'] - 1} ({mhss_text(meta['mhss_seeds'])}); the monitor's settings "
        "were chosen on seeds 100–109, never on these.",
        "",
        "`-spoof` = the same estimator with `integrity.spoof_monitor` (opt-in). `drone` is the "
        "`challenge-drone` leg as committed (1 to 3 cells heard); `drone-many` the same spec "
        "with every sector within 3 km heard; `realistic` the `realistic` set. Detection is "
        "`pnt.metrics` (any of `gnss_excluded`, `spoof_suspected`, `time_spoof_suspected` held "
        "1 s); false alarms per hour are on `nominal` and `outage` runs.",
        "",
        "The monitor is for the slow ramp. The 300 m jump and the time spoof are controls: the "
        "monitor must not lose what the filter already catches. Jumps (sizes, directions, what "
        "the output does after one) are studied in #176; refusing a detected jump is #184.",
        "",
        "## Detection per attack",
        "",
        "| Leg | Attack | Estimator | Detected | TTA median (s) | TTA worst (s) | "
        "Error at alert (m) | Hazardous epochs (mean) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for leg in TABLE_LEGS:
        for entry in ("spoof-ramp", "spoof-jump", "time-spoof"):
            for est in ests_in(runs):
                rs = _rows(runs, case_id(leg, entry), est)
                if not rs:
                    continue
                d = detection(rs)
                lines.append(
                    f"| {leg} | {entry} | `{est}` | {d['detected']}/{d['n']} | "
                    f"{_f(d['tta_med'], 1)} | {_f(d['tta_max'], 1)} | {_f(d['err_at_alert'])} | "
                    f"{_f(d['hazardous'])} |"
                )
    lines += [
        "",
        "## False alarms (an outage must not look like a spoof)",
        "",
        "| Leg | Entry | Estimator | False alarms / h (mean) | Seeds with one |",
        "|---|---|---|---|---|",
    ]
    for leg in TABLE_LEGS:
        for entry in ("nominal", "outage"):
            for est in ests_in(runs):
                rs = _rows(runs, case_id(leg, entry), est)
                if not rs:
                    continue
                fa = [r["false_alarms_per_h"] for r in rs]
                seeds = [r["seed"] for r in rs if r["false_alarms_per_h"] > 0]
                listed = ", ".join(map(str, seeds)) if 0 < len(seeds) <= 5 else ""
                lines.append(
                    f"| {leg} | {entry} | `{est}` | {_f(_mean(fa), 2)} | "
                    f"{len(seeds)}/{len(rs)}{' (' + listed + ')' if listed else ''} |"
                )
    lines += [
        "",
        "## What the towers can see: the monitor's own uncertainty",
        "",
        "Median over each run's seconds, then over seeds, of the 1-sigma (worst axis) of the "
        "displacement the tower test estimates; the share of seconds the test has an opinion "
        "(at least 5 sites heard in both windows). The ramp moves GNSS 2 m/s × lag.",
        "",
        "| Leg | Entry | Estimator | Test (lag/window s) | Opinion share | Sigma (m) | "
        "Ramp over the lag (m) |",
        "|---|---|---|---|---|---|---|",
    ]
    for leg in TABLE_LEGS:
        for entry in ("nominal",):
            for est in ("ekf-spoof",):
                rs = _rows(runs, case_id(leg, entry), est)
                keys = sorted({k for r in rs for k in r if k.startswith("tower_test_")})
                tests = sorted(
                    {k.split("_")[2] for k in keys}, key=lambda k: float(k.split("/")[0])
                )
                for key in tests:
                    share = _med([r.get(f"tower_test_{key}_opinion_share", math.nan) for r in rs])
                    sig = _med([r.get(f"tower_test_{key}_sigma_med_m", math.nan) for r in rs])
                    lag = float(key.split("/")[0])
                    lines.append(
                        f"| {leg} | {entry} | `{est}` | {key} | {_f(share, 2)} | {_f(sig, 1)} | "
                        f"{2 * lag:g} |"
                    )
    lines += [
        "",
        "## Runtime",
        "",
        "CPU seconds of the estimator per run (scenario generation and scoring not counted).",
        "",
        "| Estimator | Median CPU s per run | Worst |",
        "|---|---|---|",
    ]
    for est in ests_in(runs):
        rt = [r["cpu_s"] for r in runs if r["estimator"] == est]
        lines.append(f"| `{est}` | {_f(_med(rt), 1)} | {_f(_max(rt), 1)} |")
    return "\n".join(lines) + "\n"


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs, meta = data["runs"], data["meta"]
    groups = [(leg, entry) for leg in TABLE_LEGS for entry in ("spoof-ramp", "spoof-jump",
                                                             "time-spoof")]  # fmt: skip
    labels = {"spoof-ramp": "ramp", "spoof-jump": "jump", "time-spoof": "time"}
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 4.8), dpi=130)
    width = 0.8 / len(FAST)
    x = np.arange(len(groups))
    for k, est in enumerate(FAST):
        share, med, worst = [], [], []
        for leg, entry in groups:
            d = detection(_rows(runs, case_id(leg, entry), est))
            share.append(100.0 * d["detected"] / d["n"] if d["n"] else np.nan)
            med.append(d["tta_med"])
            worst.append(d["tta_max"])
        xs = x + (k - (len(FAST) - 1) / 2) * width
        a1.bar(xs, share, width, color=COLOURS[est], label=est)
        a2.bar(xs, med, width, color=COLOURS[est], label=est)
        a2.plot(xs, worst, "_", color=INK, ms=8, mew=1.5,
                label="worst seed" if k == 0 else None)  # fmt: skip
    for ax in (a1, a2):
        ax.set_xticks(x, [f"{labels[e]}\n{leg}" for leg, e in groups], fontsize=7)
        ax.grid(True, axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(axis="y", labelsize=8)
    a1.set_ylabel("seeds detected (%)", fontsize=8)
    a1.set_ylim(0, 105)
    a1.set_title("Detection share", fontsize=9, loc="left")
    a2.set_ylabel("time to alert (s), median bar, worst tick", fontsize=8)
    a2.set_yscale("log")
    a2.axhline(30.0, color=INK, lw=1, ls=":", label="T4 ramp target 30 s (TBC)")
    a2.set_title("Time to alert (detected seeds only)", fontsize=9, loc="left")
    handles, labels_ = a2.get_legend_handles_labels()
    fig.legend(handles, labels_, loc="upper left", bbox_to_anchor=(0.005, 0.93), ncol=6,
               fontsize=8, frameon=False)  # fmt: skip
    fig.suptitle(
        "GNSS spoof detection before and after the tower monitor (ramp 2 m/s, jump 300 m, time "
        "50 ns/s): challenge-drone (1-3 cells), drone-many (3 km), realistic; "
        f"seeds 0-{meta['seeds'] - 1}, {meta['commit']} (sim)",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def _clean(x):
    """A value as the runs file stores it: floats rounded (finer than any table prints),
    NaN as null, so the file is standard JSON (`allow_nan=False`)."""
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, 3)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def save_runs(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ",\n".join(json.dumps(_clean(r), allow_nan=False) for r in data["runs"])
    meta = json.dumps(_clean(data["meta"]), allow_nan=False)
    path.write_text(f'{{"meta": {meta},\n"runs": [\n{rows}\n]}}\n')
    print(f"wrote {path}")


def load_runs(path: Path) -> dict:
    """The runs file, with null read back as NaN for the summary."""
    data = json.loads(path.read_text())
    data["runs"] = [{k: math.nan if v is None else v for k, v in r.items()} for r in data["runs"]]
    return data


def write(data: dict, out_dir: Path) -> None:
    (out_dir / "summary.md").write_text(summary(data))
    plot(data, out_dir / "detection.png")
    print(f"wrote {out_dir / 'summary.md'}")


def clean_commit(commit: str) -> bool:
    """True for the hash of a clean tree: `_commit()` gives `<hash>-dirty` for a tree with
    uncommitted changes to tracked files, and a word when there is no git."""
    return len(commit) >= 7 and all(c in "0123456789abcdef" for c in commit)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--mhss-seeds", type=int, default=5)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--out", default=str(OUT), help="summary.md and detection.png")
    p.add_argument("--runs", default=str(RUNS), help="per-run rows (git-ignored by default)")
    p.add_argument("--redraw", action="store_true", help="rebuild from the runs file")
    a = p.parse_args(argv)
    out_dir, runs_path = Path(a.out), Path(a.runs)
    commit = _commit()
    # REQ-10: the committed results name a commit they can be regenerated from
    if not a.redraw and out_dir.resolve() == OUT.resolve() and not clean_commit(commit):
        raise SystemExit(
            f"tree is {commit}: commit first, the committed results must name a clean commit "
            "(or write elsewhere with --out)"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if not a.redraw:
        tasks = plan(a.seeds, a.mhss_seeds)
        print(f"{len(tasks)} runs on {a.jobs} workers")
        t0 = time.time()
        runs = _map(tasks, a.jobs)
        meta = {
            "commit": commit,
            "command": f"python analysis/spoof_detection.py --seeds {a.seeds} "
            f"--mhss-seeds {a.mhss_seeds} --jobs {a.jobs}",
            "seeds": a.seeds,
            "mhss_seeds": a.mhss_seeds,
            "minutes": (time.time() - t0) / 60.0,
            "host": host(),
        }
        save_runs({"meta": meta, "runs": runs}, runs_path)
    # the summary is always built from the file as written, so --redraw gives the same tables
    write(load_runs(runs_path), out_dir)


if __name__ == "__main__":
    main()
