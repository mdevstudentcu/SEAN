"""GNSS spoof detection before and after the opt-in tower monitor (#173), sim.

One command, from a clean commit:

    python analysis/spoof_detection.py --seeds 50 --mhss-seeds 5 --jobs 2

writes `analysis/results/spoof-detection/`: `summary.md` (the tables), `runs.json` (one row per
run) and `detection.png`. `--redraw` rebuilds the summary and figure from `runs.json`.

Legs, each from committed scenarios (no scenario file is added):
- `drone`: the `challenge-drone` leg as committed (1 to 3 cells heard per epoch).
- `drone-many`: the same spec with `sources.lte.hearing` = {model: range, hearing_km: 3}, every
  sector within 3 km heard (about 50 sectors on 17 eNBs after the cell lookup).
- `timing`: the `challenge-timing` leg (static receiver), for the jump characterisation.
- `realistic`: the `realistic` set (synthetic towers).

Runs, every estimator pair being the unchanged estimator and the same one with
`integrity.spoof_monitor` (`ekf` / `ekf-spoof`, `ekf-calibrated` / `ekf-calibrated-spoof`),
paired on the same seeds; `ekf-mhss` on `--mhss-seeds` (3 to 20 s a run):
1. Table: `nominal`, `outage`, `spoof-ramp`, `spoof-jump` (300 m), `time-spoof` on drone,
   drone-many and realistic.
2. Jumps: 25, 50, 100 and 300 m east on drone, drone-many and timing (`ekf`, `ekf-spoof`; all
   four at 300 m), and the 300 m jump ended at 300 s (150 s of spoof) to see recovery (`ekf`,
   `ekf-spoof`, `ekf-calibrated`). Fewer estimators there to keep the run near 1.5 h at 2
   workers.

Seeds 0 to N-1 are the reported seeds. The monitor's settings were chosen on seeds 100-109.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.metrics import ALARM_FLAGS, SPOOF_ATTACKS, score
from pnt.nav import ESTIMATORS, estimate
from pnt.sim.scenario import T0_NS, generate, load

OUT = Path(__file__).resolve().parent / "results" / "spoof-detection"
PAIRS = (("ekf", "ekf-spoof"), ("ekf-calibrated", "ekf-calibrated-spoof"))
FAST = tuple(e for p in PAIRS for e in p)
MHSS = "ekf-mhss"
SWEEP_ESTS = ("ekf", "ekf-spoof")  # jump sizes other than the table's 300 m
END_ESTS = ("ekf", "ekf-spoof", "ekf-calibrated")  # the recovery variant
LEGS = {
    "drone": "challenge-drone",
    "drone-many": "challenge-drone",
    "timing": "challenge-timing",
    "realistic": "realistic",
}
TABLE_LEGS = ("drone", "drone-many", "realistic")
TABLE_ENTRIES = ("nominal", "outage", "spoof-ramp", "spoof-jump", "time-spoof")
JUMP_LEGS = ("drone", "drone-many", "timing")
JUMP_SIZES = (25.0, 50.0, 100.0, 300.0)
JUMP_END_S = 300.0  # the recovery variant: the 300 m jump ends here (it starts at 150 s)
OFFSETS_S = (1.0, 3.0, 5.0, 10.0, 30.0, 120.0)  # after the spoof starts
MANY_HEARING = {"model": "range", "hearing_km": 3}
# Categorical slots 1-4 in a fixed order, and recessive ink (analysis/lte_table_audit.py)
COLOURS = {"ekf": "#2a78d6", "ekf-spoof": "#eb6834", "ekf-calibrated": "#1baf7a",
           "ekf-calibrated-spoof": "#eda100"}  # fmt: skip
INK, GRID = "#52514e", "#e4e3df"


def case_id(leg: str, entry: str, size: float | None = None, end_s: float | None = None) -> str:
    out = f"{leg}:{entry}"
    if size is not None:
        out += f":{size:g}m"
    if end_s is not None:
        out += f":end{end_s:g}"
    return out


def spec_of(case: str) -> dict:
    """The scenario spec of a case id, built from the committed environment."""
    leg, entry, *mods = case.split(":")
    spec = copy.deepcopy(load(f"{LEGS[leg]}-{entry}"))
    if leg == "drone-many":
        spec["sources"]["lte"]["hearing"] = dict(MANY_HEARING)
    for mod in mods:
        for f in spec["faults"]:
            if f["type"] != "spoof_jump":
                continue
            if mod.endswith("m"):
                f["offset_enu_m"] = [float(mod[:-1]), 0.0, 0.0]
            elif mod.startswith("end"):
                f["end_s"] = float(mod[3:])
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
    t_start = time.time()
    est = list(
        estimate(
            _with_monitor_log(estimator, log),
            run.measurements,
            origin_llh=spec.get("origin_llh"),
            reference=run.reference,
        )
    )
    runtime = time.time() - t_start
    m = score(est, run.truth, spec, T0_NS)
    tmap = {g.t_ns: g for g in run.truth}
    pairs = [(e, tmap[e.t_ns]) for e in est if e.t_ns in tmap]
    t = np.array([(e.t_ns - T0_NS) / 1e9 for e, _ in pairs])
    err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
    hpl = np.array([e.hpl_m for e, _ in pairs])
    excluded = np.array(["gnss_excluded" in e.flags for e, _ in pairs])
    spoof_flag = np.array(["spoof_suspected" in e.flags for e, _ in pairs])
    alarm = np.array([bool(ALARM_FLAGS & set(e.flags)) for e, _ in pairs])
    row = {
        "case": case,
        "estimator": estimator,
        "seed": seed,
        "runtime_s": round(runtime, 2),
        "detect_delay_s": m.detect_delay_s,
        "spoof_detected": m.spoof_detected,
        "false_alarms_per_h": m.false_alarms_per_h,
        "hazardous_epochs": m.hazardous_epochs,
        "misleading_epochs": m.misleading_epochs,
        "fault_h_p95_m": m.fault_h_p95_m,
        "h_p95_m": m.h_p95_m,
    }
    spoofs = [f for f in spec.get("faults", []) if f["type"] in SPOOF_ATTACKS]
    if spoofs:
        s0 = float(spoofs[0].get("start_s", 0.0))
        for o in OFFSETS_S:
            row[f"err_{o:g}s"] = _at(t, err, s0 + o)
            row[f"hpl_{o:g}s"] = _at(t, hpl, s0 + o)
        d = m.detect_delay_s
        if not math.isnan(d):
            row["err_at_alert"] = _at(t, err, s0 + d)
            row["hpl_at_alert"] = _at(t, hpl, s0 + d)
            pre = (t >= s0) & (t < s0 + d)
            row["err_pre_alert_max"] = float(err[pre].max()) if pre.any() else float("nan")
            row["hpl_pre_alert_max"] = float(hpl[pre].max()) if pre.any() else float("nan")
        w30 = (t >= s0) & (t < s0 + 30.0)
        row["gnss_excluded_share_30s"] = float(excluded[w30].mean()) if w30.any() else math.nan
        hit = np.flatnonzero(spoof_flag & (t >= s0))
        row["spoof_flag_delay_s"] = float(t[hit[0]] - s0) if hit.size else float("nan")
        if "end_s" in spoofs[0]:
            e0 = float(spoofs[0]["end_s"])
            row["err_end_30s"] = _at(t, err, e0 + 30.0)
            row["err_end_120s"] = _at(t, err, e0 + 120.0)
            late = t >= e0 + 120.0
            row["alarm_share_after_end_120s"] = (
                float(alarm[late].mean()) if late.any() else math.nan
            )
    if log:
        for key in log[0][1]:
            vals = [r[key] for _, r in log if r.get(key) is not None]
            row[f"tower_test_{key}_opinion_share"] = len(vals) / len(log)
            row[f"tower_test_{key}_sigma_med_m"] = (
                float(np.median([v[4] for v in vals])) if vals else float("nan")
            )
    return row


def plan(seeds: int, mhss_seeds: int) -> list[tuple[str, str, int]]:
    cases_fast, cases_mhss = [], []
    for leg in TABLE_LEGS:
        for entry in TABLE_ENTRIES:
            cases_fast.append(case_id(leg, entry))
            cases_mhss.append(case_id(leg, entry))
    for leg in JUMP_LEGS:
        for size in JUMP_SIZES:
            cid = case_id(leg, "spoof-jump", None if size == 300.0 else size)
            if cid not in cases_fast:
                cases_fast.append(cid)
        cid = case_id(leg, "spoof-jump")
        if cid not in cases_mhss:
            cases_mhss.append(cid)
        cases_fast.append(case_id(leg, "spoof-jump", end_s=JUMP_END_S))
        cases_mhss.append(case_id(leg, "spoof-jump", end_s=JUMP_END_S))
    table = {case_id(leg, entry) for leg in TABLE_LEGS for entry in TABLE_ENTRIES}
    tasks = []
    for c in cases_fast:  # the jump sweep and recovery cases with fewer estimators, for time
        ests = FAST if c in table else SWEEP_ESTS if ":end" not in c else END_ESTS
        tasks += [(c, e, s) for e in ests for s in range(seeds)]
    tasks += [(c, MHSS, s) for c in cases_mhss for s in range(mhss_seeds)]
    return tasks


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


def summary(data: dict) -> str:
    runs, meta = data["runs"], data["meta"]
    lines = [
        "# Spoof detection, before and after the tower monitor (#173)",
        "",
        f"Sim, every value `TBC`. Commit {meta['commit']}, `{meta['command']}`, "
        f"{meta['minutes']:.1f} min. Seeds 0–{meta['seeds'] - 1} "
        f"(`{MHSS}` 0–{meta['mhss_seeds'] - 1}); the monitor's settings were chosen on seeds "
        "100–109, never on these.",
        "",
        "`-spoof` = the same estimator with `integrity.spoof_monitor` (opt-in). `drone` is the "
        "`challenge-drone` leg as committed (1 to 3 cells heard); `drone-many` the same spec "
        "with every sector within 3 km heard; `realistic` the `realistic` set. Detection is "
        "`pnt.metrics` (any of `gnss_excluded`, `spoof_suspected`, `time_spoof_suspected` held "
        "1 s); false alarms per hour are on `nominal` and `outage` runs.",
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
        "| Leg | Entry | Estimator | False alarms / h (mean) | Runs with one |",
        "|---|---|---|---|---|",
    ]
    for leg in TABLE_LEGS:
        for entry in ("nominal", "outage"):
            for est in ests_in(runs):
                rs = _rows(runs, case_id(leg, entry), est)
                if not rs:
                    continue
                fa = [r["false_alarms_per_h"] for r in rs]
                lines.append(
                    f"| {leg} | {entry} | `{est}` | {_f(_mean(fa), 2)} | "
                    f"{sum(x > 0 for x in fa)}/{len(rs)} |"
                )
    lines += [
        "",
        "## Jumps: what happens in the first seconds, and after",
        "",
        "Medians over seeds. Follows: error 30 s after the jump over half its size. "
        "GNSS excluded: share of the first 30 s with `gnss_excluded`.",
        "",
        "| Leg | Jump (m) | Estimator | Detected | TTA median / worst (s) | "
        "Error, HPL at +1 s (m) | Error, HPL at +3 s (m) | GNSS excluded, first 30 s | "
        "Follows | Error at +30 s / +120 s (m) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    smallest = {}
    for leg in JUMP_LEGS:
        for size in JUMP_SIZES:
            cid = case_id(leg, "spoof-jump", None if size == 300.0 else size)
            for est in ests_in(runs):
                rs = _rows(runs, cid, est)
                if not rs:
                    continue
                d = detection(rs)
                follows = sum(r["err_30s"] > size / 2 for r in rs)
                if d["detected"] == d["n"]:
                    smallest.setdefault((leg, est), size)
                    smallest[(leg, est)] = min(smallest[(leg, est)], size)
                lines.append(
                    f"| {leg} | {size:g} | `{est}` | {d['detected']}/{d['n']} | "
                    f"{_f(d['tta_med'], 1)} / {_f(d['tta_max'], 1)} | "
                    f"{_f(_med([r['err_1s'] for r in rs]))}, "
                    f"{_f(_med([r['hpl_1s'] for r in rs]))} | "
                    f"{_f(_med([r['err_3s'] for r in rs]))}, "
                    f"{_f(_med([r['hpl_3s'] for r in rs]))} | "
                    f"{_f(_med([r['gnss_excluded_share_30s'] for r in rs]), 2)} | "
                    f"{follows}/{len(rs)} | {_f(_med([r['err_30s'] for r in rs]))} / "
                    f"{_f(_med([r['err_120s'] for r in rs]))} |"
                )
    lines += [
        "",
        "### Smallest jump detected on every seed",
        "",
        "Of the sizes tried (" + ", ".join(f"{s:g}" for s in JUMP_SIZES) + " m). Detected by "
        "the filter's own GNSS gate or by the monitor; whether the output then follows the jump "
        "is in the table above.",
        "",
        "| Leg | " + " | ".join(f"`{e}`" for e in ests_in(runs)) + " |",
        "|---|" + "---|" * len(ests_in(runs)),
    ]
    for leg in JUMP_LEGS:
        cells = [_f(smallest.get((leg, e))) if (leg, e) in smallest else "none" for e in
                 ests_in(runs)]  # fmt: skip
        lines.append(f"| {leg} | " + " | ".join(cells) + " |")
    lines += [
        "",
        f"## Recovery: the 300 m jump ended at {JUMP_END_S:g} s",
        "",
        "| Leg | Estimator | Error at end +30 s / +120 s (m, median) | Share of epochs alarmed "
        "from 120 s after the end (median) |",
        "|---|---|---|---|",
    ]
    for leg in JUMP_LEGS:
        for est in ests_in(runs):
            rs = _rows(runs, case_id(leg, "spoof-jump", end_s=JUMP_END_S), est)
            if not rs:
                continue
            up = [r.get("alarm_share_after_end_120s", math.nan) for r in rs]
            lines.append(
                f"| {leg} | `{est}` | {_f(_med([r['err_end_30s'] for r in rs]))} / "
                f"{_f(_med([r['err_end_120s'] for r in rs]))} | "
                f"{_f(_med(up), 2)} |"
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
        "| Estimator | Median s per run | Worst |",
        "|---|---|---|",
    ]
    for est in ests_in(runs):
        rt = [r["runtime_s"] for r in runs if r["estimator"] == est]
        lines.append(f"| `{est}` | {_f(_med(rt), 1)} | {_f(_max(rt), 1)} |")
    return "\n".join(lines) + "\n"


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs, meta = data["runs"], data["meta"]
    groups = [(leg, entry) for leg in TABLE_LEGS for entry in ("spoof-ramp", "spoof-jump",
                                                             "time-spoof")]  # fmt: skip
    labels = {"spoof-ramp": "ramp 2 m/s", "spoof-jump": "jump 300 m", "time-spoof": "time 50 ns/s"}
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), dpi=130)
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
        ax.set_xticks(x, [f"{leg}\n{labels[e]}" for leg, e in groups], fontsize=7)
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
        "GNSS spoof detection before and after the tower monitor: challenge-drone (1-3 cells), "
        f"drone-many (3 km), realistic; seeds 0-{meta['seeds'] - 1}, {meta['commit']} (sim)",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def write(data: dict, out_dir: Path) -> None:
    (out_dir / "summary.md").write_text(summary(data))
    plot(data, out_dir / "detection.png")
    print(f"wrote {out_dir / 'summary.md'}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--mhss-seeds", type=int, default=5)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--redraw", action="store_true", help="rebuild from runs.json")
    a = p.parse_args(argv)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.redraw:
        data = json.loads((out_dir / "runs.json").read_text())
        write(data, out_dir)
        return
    tasks = plan(a.seeds, a.mhss_seeds)
    print(f"{len(tasks)} runs on {a.jobs} workers")
    t0 = time.time()
    runs = _map(tasks, a.jobs)
    data = {
        "meta": {
            "commit": _commit(),
            "command": f"python analysis/spoof_detection.py --seeds {a.seeds} "
            f"--mhss-seeds {a.mhss_seeds} --jobs {a.jobs}",
            "seeds": a.seeds,
            "mhss_seeds": a.mhss_seeds,
            "minutes": (time.time() - t0) / 60.0,
        },
        "runs": runs,
    }
    (out_dir / "runs.json").write_text(json.dumps(data, indent=0, default=float))
    write(data, out_dir)


if __name__ == "__main__":
    main()
