"""Refusing a detected GNSS position jump, before and after (#184), sim.

One command, from a clean commit:

    python analysis/jump_refusal.py --seeds 50 --jobs 2

writes `analysis/results/jump-refusal/`: `summary.md` (the tables), `runs.json` (one row per
run), `curves.json` (error after the jump, median and spread per variant) and
`error_after_jump.png`. `--redraw` rebuilds the summary and figure from the JSON files.

Legs, each from a committed scenario (no scenario file is added):
- `drone`: the `challenge-drone` leg as committed (1 to 3 cells heard).
- `many`: the same spec with `sources.lte.hearing` = {model: range, hearing_km: 3}, every sector
  within 3 km heard.
- `timing`: the `challenge-timing` leg (static receiver).

Cases per leg: the leg's `spoof-jump` entry with the jump set to 25, 50, 100 or 300 m east (from
150 s to the end of the run), the same ended at 300 s (150 s of spoof), `nominal` and `outage`.

Variants, run on the same records (same seed, paired):
- `ekf | main`, `ekf-calibrated | main`: the estimator with `jump_guard=None`, the code path
  `main` runs (byte-identical estimates, checked in the PR).
- `ekf | undo`, `ekf-calibrated | undo`: the opt-in `ekf-guard` and `ekf-calibrated-guard`,
  with the jump guard's default rule (`pnt.integrity.jump_guard`).
- `ekf | never`, `ekf | lr`: the alternative re-admission rules, for the owners' choice.

Seeds 0 to N-1 are the reported seeds; nothing was chosen on them (the thresholds are derived in
`pnt.integrity.jump_guard`; the behaviour was looked at on seeds 100-109).
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
from pnt.integrity.jump_guard import JumpGuard
from pnt.metrics import score
from pnt.nav import ESTIMATORS, configured, estimate
from pnt.nav import ekf as ekfmod
from pnt.sim.scenario import T0_NS, generate, load

OUT = Path(__file__).resolve().parent / "results" / "jump-refusal"
LEGS = {"drone": "challenge-drone", "many": "challenge-drone", "timing": "challenge-timing"}
MANY_HEARING = {"model": "range", "hearing_km": 3}
SIZES = (25.0, 50.0, 100.0, 300.0)
JUMP_START_S = 150.0  # the committed menus' start
JUMP_END_S = 300.0  # the ended variant
OUTAGE_END_S = 660.0  # the committed `outage` entry's end on both challenge legs
OFFSETS_S = (1.0, 30.0, 120.0, 300.0)  # after the jump starts
END_OFFSETS_S = (30.0, 120.0)  # after it ends
CURVE_S = (-10.0, 300.0)  # error curve window around the jump start, at 1 s
VARIANTS = (
    "ekf | main",
    "ekf | undo",
    "ekf | never",
    "ekf | lr",
    "ekf-calibrated | main",
    "ekf-calibrated | undo",
)
# Categorical slots 1 and 2 and recessive ink, as in analysis/sensitivity.py
BLUE, ORANGE, INK, GRID = "#2a78d6", "#eb6834", "#52514e", "#e4e3df"


def estimator_of(variant: str):
    name, rule = (s.strip() for s in variant.split("|"))
    if rule == "undo":
        return ESTIMATORS[f"{name}-guard"]
    fn = ekfmod.run if name == "ekf" else ekfmod.run_calibrated
    guard = None if rule == "main" else partial(JumpGuard, readmit=rule)
    return configured(fn, jump_guard=guard)


def cases() -> list[str]:
    out = []
    for leg in LEGS:
        out += [f"{leg}:jump:{s:g}" for s in SIZES]
        out += [f"{leg}:jump:{s:g}:end" for s in SIZES]
        out += [f"{leg}:nominal", f"{leg}:outage"]
    return out


def spec_of(case: str) -> dict:
    leg, entry, *mods = case.split(":")
    spec = copy.deepcopy(load(f"{LEGS[leg]}-{'spoof-jump' if entry == 'jump' else entry}"))
    if leg == "many":
        spec["sources"]["lte"]["hearing"] = dict(MANY_HEARING)
    if entry == "jump":
        (f,) = [f for f in spec["faults"] if f["type"] == "spoof_jump"]
        assert f["start_s"] == JUMP_START_S
        f["offset_enu_m"] = [float(mods[0]), 0.0, 0.0]
        if "end" in mods:
            f["end_s"] = JUMP_END_S
    spec["name"] = case
    return spec


def _at(t: np.ndarray, x: np.ndarray, s: float) -> float:
    i = int(np.searchsorted(t, s - 1e-6))
    return float(x[i]) if i < len(t) else math.nan


def _first(t: np.ndarray, mask: np.ndarray, after: float) -> float:
    i = np.flatnonzero(mask & (t >= after - 1e-6))
    return float(t[i[0]] - after) if i.size else math.nan


class _LastUsed:
    """A pass-through `monitor` for `ekf.run` that notes, at each epoch, when the filter last
    used a GNSS position fix (`EKF.last_used`). It changes no estimate."""

    def __init__(self, f, log: list):
        self.f, self.log = f, log

    def process(self, m) -> None:
        pass

    def estimate(self, est):
        self.log.append(self.f.last_used.get("gnss", -(10**18)))
        return est


def run_case(case: str, seed: int) -> tuple[list[dict], dict]:
    spec = spec_of(case)
    sim = generate(spec, seed=seed)
    truth = {g.t_ns: g for g in sim.truth}
    leg, entry, *mods = case.split(":")
    rows, curves = [], {}
    for variant in VARIANTS:
        t_start = time.time()
        log: list[int] = []
        fn = configured(estimator_of(variant), monitor=partial(_LastUsed, log=log))
        est = list(
            estimate(
                fn,
                sim.measurements,
                origin_llh=spec.get("origin_llh"),
                reference=sim.reference,
            )
        )
        runtime = time.time() - t_start
        m = score(est, sim.truth, spec, T0_NS)
        keep = [i for i, e in enumerate(est) if e.t_ns in truth]
        pairs = [(est[i], truth[est[i].t_ns]) for i in keep]
        last_used = np.array([(log[i] - T0_NS) / 1e9 for i in keep])  # s
        t = np.array([(e.t_ns - T0_NS) / 1e9 for e, _ in pairs])
        err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
        hpl = np.array([e.hpl_m for e, _ in pairs])
        used = np.array([e.trust.get("gnss", 0.0) == 1.0 for e, _ in pairs])
        excluded = np.array(["gnss_excluded" in e.flags for e, _ in pairs])
        row = {
            "case": case,
            "leg": leg,
            "entry": entry,
            "variant": variant,
            "seed": seed,
            "runtime_s": round(runtime, 2),
            "false_alarms_per_h": m.false_alarms_per_h,
            "hazardous_epochs": m.hazardous_epochs,
            "misleading_epochs": m.misleading_epochs,
            "detect_delay_s": m.detect_delay_s,
            "h_p95_m": m.h_p95_m,
        }
        if entry == "jump":
            size, s0 = float(mods[0]), JUMP_START_S
            row["size_m"] = size
            row["ended"] = "end" in mods
            # Distance from where the spoofer puts the receiver (truth plus the jump)
            spoofed = np.array(
                [math.dist(e.pos_enu[:2], (g.pos_enu[0] + size, g.pos_enu[1])) for e, g in pairs]
            )
            for o in OFFSETS_S:
                row[f"err_{o:g}s"] = _at(t, err, s0 + o)
                row[f"from_spoof_{o:g}s"] = _at(t, spoofed, s0 + o)
                row[f"hpl_{o:g}s"] = _at(t, hpl, s0 + o)
            for w in (30.0, 300.0):
                win = (t >= s0) & (t < s0 + w)
                row[f"excluded_share_{w:g}s"] = float(excluded[win].mean())
                row[f"unused_share_{w:g}s"] = float((~used[win]).mean())
            if row["ended"]:
                e0 = JUMP_END_S
                row["readmit_after_end_s"] = _first(t, last_used >= e0 - 1e-6, e0)
                for o in END_OFFSETS_S:
                    row[f"err_end_{o:g}s"] = _at(t, err, e0 + o)
            else:
                lo, hi = CURVE_S
                grid = np.arange(s0 + lo, s0 + hi + 0.5, 1.0)
                curves[variant] = [_at(t, err, g) for g in grid]
                curves[f"{variant} hpl"] = [_at(t, hpl, g) for g in grid]
        elif entry == "outage":
            row["readmit_after_outage_s"] = _first(
                t, last_used >= OUTAGE_END_S - 1e-6, OUTAGE_END_S
            )
            row["err_outage_end_30s"] = _at(t, err, OUTAGE_END_S + 30.0)
        rows.append(row)
    return rows, curves


def _job(args):
    return args, run_case(*args)


def run_all(seeds: range, jobs: int) -> tuple[list[dict], dict]:
    todo = [(c, s) for c in cases() for s in seeds]
    rows, curves = [], {}
    ctx = multiprocessing.get_context("spawn")
    t0 = time.time()
    with ProcessPoolExecutor(jobs, mp_context=ctx) as ex:
        for i, ((case, _), (r, c)) in enumerate(ex.map(_job, todo), 1):
            rows += r
            for variant, curve in c.items():
                curves.setdefault(f"{case}|{variant}", []).append(curve)
            if i % 50 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} jobs, {(time.time() - t0) / 60:.1f} min", flush=True)
    agg = {}
    for key, cs in curves.items():
        a = np.array(cs, float)
        agg[key] = {
            "median": np.nanmedian(a, axis=0).round(2).tolist(),
            "p10": np.nanpercentile(a, 10, axis=0).round(2).tolist(),
            "p90": np.nanpercentile(a, 90, axis=0).round(2).tolist(),
            "n": len(cs),
        }
    return rows, agg


# --- summary -------------------------------------------------------------------------------------
def _med(v) -> float:
    v = [x for x in v if x is not None and not math.isnan(x)]
    return float(np.median(v)) if v else math.nan


def _f(x, nd=0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x:,.{nd}f}"


def _sel(rows, **kw):
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


def summary(rows: list[dict], meta: dict) -> str:
    n, s0 = meta["seeds"], meta.get("first_seed", 0)
    out = [
        "# Refusing a detected GNSS jump, before and after (#184)",
        "",
        f"Sim, every value `TBC`. Commit {meta['commit']}, `python analysis/jump_refusal.py "
        f"--seeds {n} --jobs {meta['jobs']}`, {meta['minutes']:.1f} min. Seeds {s0}–{s0 + n - 1}, "
        "paired: every variant runs on the same records. Nothing was chosen on these seeds: the "
        "thresholds are derived in `pnt.integrity.jump_guard`, and the behaviour was looked at on "
        "seeds 100–109.",
        "",
        "`main` = the estimator with the jump guard off (the code path `main` runs); `undo` = "
        "the opt-in `-guard` estimator, which refuses a detected jump until it is undone; "
        "`never` and `lr` = the alternative re-admission rules (`ekf` only). `drone` is the "
        "`challenge-drone` leg as committed, `many` the same with every sector within 3 km "
        "heard, `timing` the `challenge-timing` leg. The jump is east, from 150 s.",
        "",
        "## Held jump: does the output follow it?",
        "",
        "Follows: horizontal error over half the jump (the issue's test; dead reckoning far from "
        "both the truth and the spoof also counts). On the spoof: within half the jump of where "
        "the spoofer puts the receiver. Medians over seeds unless stated. "
        "Excluded: share of the first 30 s / 300 s with `gnss_excluded`. Hazardous: epochs with "
        "error over the 50 m alert limit while HPL is under it (mean over seeds, and seeds with "
        "any).",
        "",
        "| Leg | Jump (m) | Variant | Detected | Follows +30 / +120 s | On the spoof +30 / +120 s "
        "| Error +1 / +30 / +120 / +300 s (m) | Error +120 s, p95 / worst (m) "
        "| HPL +30 / +120 s (m) | Excluded 30 s / 300 s | Hazardous epochs (mean, seeds) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for leg in LEGS:
        for size in SIZES:
            for v in VARIANTS:
                rs = _sel(rows, leg=leg, entry="jump", size_m=size, ended=False, variant=v)
                if not rs:
                    continue
                det = sum(1 for r in rs if not math.isnan(r["detect_delay_s"]))
                f30 = sum(r["err_30s"] > size / 2 for r in rs)
                f120 = sum(r["err_120s"] > size / 2 for r in rs)
                o30 = sum(r["from_spoof_30s"] < size / 2 for r in rs)
                o120 = sum(r["from_spoof_120s"] < size / 2 for r in rs)
                e120 = np.array([r["err_120s"] for r in rs])
                errs = " / ".join(_f(_med(r[f"err_{o:g}s"] for r in rs)) for o in OFFSETS_S)
                hp = " / ".join(_f(_med(r[f"hpl_{o:g}s"] for r in rs)) for o in (30.0, 120.0))
                ex = " / ".join(
                    _f(_med(r[f"excluded_share_{w:g}s"] for r in rs), 2) for w in (30.0, 300.0)
                )
                hz = [r["hazardous_epochs"] for r in rs]
                out.append(
                    f"| {leg} | {size:g} | `{v}` | {det}/{len(rs)} | {f30} / {f120} | "
                    f"{o30} / {o120} | {errs} | {_f(np.percentile(e120, 95))} / "
                    f"{_f(e120.max())} | {hp} | {ex} | {_f(np.mean(hz))}, "
                    f"{sum(h > 0 for h in hz)}/{len(rs)} |"
                )
    out += [
        "",
        "## Jump ended at 300 s: does honest GNSS come back?",
        "",
        "Re-admitted: seeds where the filter uses a GNSS fix taken after the spoof ended, before "
        "the run ends; delay from the end to the first epoch at which it has (median / worst over "
        "the seeds re-admitted).",
        "",
        "| Leg | Jump (m) | Variant | Re-admitted | Delay median / worst (s) | Error end +30 / "
        "+120 s (m) | Hazardous epochs (mean, seeds) |",
        "|---|---|---|---|---|---|---|",
    ]
    for leg in LEGS:
        for size in SIZES:
            for v in VARIANTS:
                rs = _sel(rows, leg=leg, entry="jump", size_m=size, ended=True, variant=v)
                if not rs:
                    continue
                d = [r["readmit_after_end_s"] for r in rs]
                d = [x for x in d if not math.isnan(x)]
                errs = " / ".join(
                    _f(_med(r[f"err_end_{o:g}s"] for r in rs)) for o in END_OFFSETS_S
                )
                hz = [r["hazardous_epochs"] for r in rs]
                out.append(
                    f"| {leg} | {size:g} | `{v}` | {len(d)}/{len(rs)} | "
                    f"{_f(_med(d), 1)} / {_f(max(d) if d else math.nan, 1)} | {errs} | "
                    f"{_f(np.mean(hz))}, {sum(h > 0 for h in hz)}/{len(rs)} |"
                )
    out += [
        "",
        "## False alarms and recovery on clean runs",
        "",
        "`pnt.metrics` false alarms (any alarm flag held 1 s outside a spoof window). Outage: GPS "
        "is lost from 60 s to 660 s; delay to the first epoch at which the filter has used a fix "
        "taken after it returns.",
        "",
        "| Leg | Entry | Variant | False alarms / h (mean) | Seeds with one | Hazardous epochs "
        "(mean) | GNSS used again after the outage, median / worst (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for leg in LEGS:
        for entry in ("nominal", "outage"):
            for v in VARIANTS:
                rs = _sel(rows, leg=leg, entry=entry, variant=v)
                if not rs:
                    continue
                fa = [r["false_alarms_per_h"] for r in rs]
                rec = "–"
                if entry == "outage":
                    d = [r["readmit_after_outage_s"] for r in rs]
                    rec = f"{_f(_med(d), 1)} / {_f(max(d), 1)}"
                out.append(
                    f"| {leg} | {entry} | `{v}` | {_f(np.mean(fa), 2)} | "
                    f"{sum(x > 0 for x in fa)}/{len(rs)} | "
                    f"{_f(np.mean([r['hazardous_epochs'] for r in rs]), 1)} | {rec} |"
                )
    out += ["", "## Runtime", "", "| Variant | Median s per run | Worst |", "|---|---|---|"]
    for v in VARIANTS:
        rt = [r["runtime_s"] for r in rows if r["variant"] == v]
        out.append(f"| `{v}` | {_f(_med(rt), 1)} | {_f(max(rt), 1)} |")
    return "\n".join(out) + "\n"


def plot(curves: dict, meta: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sizes = (25.0, 300.0)
    fig, axes = plt.subplots(
        len(sizes), len(LEGS), figsize=(11, 3.1 * len(sizes)), dpi=130, squeeze=False
    )
    lo, hi = CURVE_S
    x = np.arange(lo, hi + 0.5, 1.0)
    for i, size in enumerate(sizes):
        for j, leg in enumerate(LEGS):
            ax = axes[i, j]
            for v, colour, label in (
                ("ekf | main", BLUE, "before (`main`)"),
                ("ekf | undo", ORANGE, "after: jump refused"),
            ):
                c = curves.get(f"{leg}:jump:{size:g}|{v}")
                h = curves.get(f"{leg}:jump:{size:g}|{v} hpl")
                if c is None:
                    continue
                ax.fill_between(x, c["p10"], c["p90"], color=colour, alpha=0.15, lw=0)
                ax.plot(x, c["median"], color=colour, lw=2, label=f"{label}: error")
                if h is not None:
                    ax.plot(x, h["median"], color=colour, lw=1, ls="-.", label=f"{label}: HPL")
            ax.axhline(size, color=INK, lw=1, ls=":", label="jump size")
            ax.axhline(50.0, color=INK, lw=1, ls="--", label="alert limit 50 m (TBC)")
            ax.axvline(0.0, color=GRID, lw=1)
            ax.set_yscale("log")
            ax.set_ylim(0.5, 2e4)
            ax.set_xlim(lo, hi)
            ax.set_title(f"{leg}, {size:g} m jump", fontsize=9, loc="left")
            ax.grid(True, which="major", color=GRID, lw=0.6)
            ax.tick_params(labelsize=8)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            if i == len(sizes) - 1:
                ax.set_xlabel("time since the jump (s)", fontsize=8)
            if j == 0:
                ax.set_ylabel("horizontal error (m)", fontsize=8)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper left", bbox_to_anchor=(0.005, 0.955), ncol=6, fontsize=8,
        frameon=False,
    )  # fmt: skip
    fig.suptitle(
        f"Error after a GNSS jump, `ekf`, before and after #184: median (band 10–90 %) of "
        f"{meta['seeds']} paired seeds, {meta['commit']} (sim)",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    fig.text(
        0.01,
        0.005,
        "challenge-drone / challenge-timing spoof-jump entries with the jump size set; `many` = "
        "challenge-drone with every sector within 3 km heard. Without GNSS the filter "
        "dead-reckons (towers rejected, #147).",
        fontsize=7,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.02, 1, 0.92))
    fig.savefig(out)
    print(f"wrote {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--first-seed", type=int, default=0, help="100 for the tuning seeds")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--redraw", action="store_true", help="rebuild from runs.json, curves.json")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.redraw:
        data = json.loads((a.out / "runs.json").read_text())
        meta, rows = data["meta"], data["rows"]
        curves = json.loads((a.out / "curves.json").read_text())
    else:
        t0 = time.time()
        rows, curves = run_all(range(a.first_seed, a.first_seed + a.seeds), a.jobs)
        meta = {
            "commit": _commit(),
            "seeds": a.seeds,
            "first_seed": a.first_seed,
            "jobs": a.jobs,
            "minutes": (time.time() - t0) / 60,
        }
        (a.out / "runs.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=0))
        (a.out / "curves.json").write_text(json.dumps(curves))
    (a.out / "summary.md").write_text(summary(rows, meta))
    print(f"wrote {a.out / 'summary.md'}")
    plot(curves, meta, a.out / "error_after_jump.png")


if __name__ == "__main__":
    main()
