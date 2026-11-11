"""The challenge baseline (#150, package 5 of #126): every registered estimator on every entry
of the three `challenge` legs (ADR-0030, Proposed), as the "before" table that fixes pair with.

    python analysis/challenge_baseline.py --seeds 50 --jobs 3

Writes to `--out` (default `analysis/results/challenge-baseline/`):
- summary.md: the verdict per target (T1 to T5, systems/plan.md; T1 also against ADR-0034's
  fallback), the jump guard against the default filters, then the full table of leg x entry x
  estimator, with the commit, seeds, command and runtime. The committed results are written
  only from a clean tree.
- t1_drone.png, t3_timing.png, t4_detection.png: one question each (see the fig_* functions)
- t1_curves.json: the across-run p95 curve per second of the drone `outage` entry, per estimator
  (small, so the T1 figure can be redrawn for a slide)

Per-run data goes to the git-ignored `analysis/results/runs/challenge-baseline/runs.json` (or
into `--out` when it is not the committed folder): a subset of `pnt.metrics.RunMetrics` per run
(6 significant digits) and, on every entry with a GPS loss, the run's horizontal error at each
second 0..300 s after the loss. From it the summary and figures can be redrawn without
re-running (`--redraw`), and an interrupted run can carry on (`--resume`, same commit only).

T1 and its fallback are scored as ADR-0034's amendment (2026-11-10, adf24d7) says: at each
second after GPS loss, the 95th percentile of the horizontal error across the runs; the target
holds only if that curve stays within the limit for every second of the window (T1: 25 m over
0-300 s; fallback: 50 m over 0-120 s). The worst second and the number of runs are reported.
Each run's own 300 s p95 is kept as an extra column; it is not ADR-0034's statistic.

Each (scenario, seed) is generated once and every estimator runs on the same measurements, so
estimators are paired, and seeds 0..N-1 are those of `pnt eval` (systems/quality.md). Scoring is
`pnt.metrics.score`, as in `pnt eval`. Nothing here changes an estimator, scenario or metric:
a target that fails is reported as failing.

Estimators: `ekf-base` and `ekf-base-imu` need a reference station (ADR-0020). The challenge
legs have none (the script checks), and without one `nav/base_rover.py` is `ekf` with the
payload's clock, so they are not run. `ekf-mhss` takes several seconds a run, so by default it
runs fewer seeds on only the entries where its monitor matters (`--mhss-seeds`,
`--mhss-entries`). The opt-in jump-guard estimators (ADR-0038, Proposed) run only on the
held-jump and meaconing entries and on `nominal` and `outage` (`--guard-entries`), to show what
they change and that they change nothing without a jump. The summary says what was cut.

The approach leg is synthetic geometry (ADR-0030 point 3): its towers are a synthetic ring and
its T1 slice does not measure LTE. It is labelled so wherever its numbers appear.
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
import sys
import time
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.core.time import s_to_ns
from pnt.experiments import _map
from pnt.metrics import ALERT_LIMIT_M, gps_loss, score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, expand, generate, load

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "results" / "challenge-baseline"
RUNS = REPO / "analysis" / "results" / "runs" / "challenge-baseline"  # git-ignored

LEGS = ("drone", "timing", "approach")
LEG_LABEL = {
    "drone": "drone (UC-01)",
    "timing": "timing (UC-03)",
    "approach": "approach (UC-02, synthetic geometry)",
}
# The default filters first, then the opt-in jump-guard ones (ADR-0038, Proposed)
ESTIMATOR_ORDER = (
    "baseline",
    "ekf",
    "ekf-calibrated",
    "ekf-imu",
    "ekf-mhss",
    "ekf-guard",
    "ekf-calibrated-guard",
    "ekf-imu-guard",
)
# Each jump-guard estimator and the default filter it guards
GUARDED = {
    "ekf-guard": "ekf",
    "ekf-calibrated-guard": "ekf-calibrated",
    "ekf-imu-guard": "ekf-imu",
}
# Where the guard matters: the held GNSS jump and meaconing entries, and `nominal` and `outage` to
# show it changes nothing without a jump
GUARD_ENTRIES = ("nominal", "outage", "spoof-jump", "meaconing")
JUMP_ENTRIES = ("spoof-jump", "meaconing")
# Need a reference station (ADR-0020); not run when the legs have none (checked in main)
NEEDS_REFERENCE = ("ekf-base", "ekf-base-imu")
SLOW = "ekf-mhss"
# Where ekf-mhss's monitor matters (#150): the outage, the T4 attacks, the tower faults, and the
# fault-free entry for its false alarms
MHSS_ENTRIES = (
    "nominal",
    "outage",
    "spoof-ramp",
    "time-spoof",
    "outage-tower-clock-step",
    "outage-tower-holdover",
)
MHSS_SEEDS = 20
# The T5 bound figure (#222): every epoch's horizontal error and HPL is kept for these runs only
# (the drone leg's GPS loss and held jump, the default filters and their guard), in BOUND_FILE
# beside runs.json. They are the runs T5 scores, so the figure's shares come from the same epochs.
BOUND_LEG = "drone"
BOUND_ENTRIES = ("outage", "spoof-jump")
BOUND_ESTIMATORS = ("ekf", "ekf-guard", "ekf-calibrated", "ekf-calibrated-guard", "ekf-mhss")
BOUND_FILE = "bound.npz"

# Targets, systems/plan.md and ADR-0034 (T1 Accepted with its value TBC; T3 to T5 Proposed)
# T1 and its fallback, scored as ADR-0034's amendment (adf24d7) says: the 95th percentile across
# runs at each second after GPS loss, held for every second of the window
T1_M, T1_WINDOW_S = 25.0, 300
T1_FALLBACK_M, T1_FALLBACK_WINDOW_S = 50.0, 120  # the mentors' figure, T1's declared fallback
CURVE_S = 300  # each run's horizontal error is kept at every second 0..CURVE_S after GPS loss
T2_AL_M = 556.0  # RNP 0.3 alert limit, terminal phase: no RunMetrics field scores it
T3_US = 1.5  # time error after 10 min without GPS
T3_SIGMA = 0.68  # reported 1-sigma bounds the time error in this share of epochs
T4_RAMP_S = 30.0  # 2 m/s position ramp detected within
T4_TIME_S = 60.0  # 50 ns/s time ramp detected within
T4_FA_PER_H = 1.0  # false alarms per hour
T5_HPL = 0.999  # protection level bounds the error in this share of epochs

# The RunMetrics fields kept per run (the JSON stays small)
FIELDS = (
    "outage_h_p95_60s_m",
    "outage_h_p95_120s_m",
    "outage_h_p95_300s_m",
    "outage_hpl_bound_300s",
    "outage_time_err_600s_us",
    "outage_time_sigma_bound_600s",
    "fault_h_p95_m",
    "hpl_bound_frac",
    "hazardous_epochs",
    "misleading_epochs",
    "spoof_detected",
    "detect_delay_s",
    "false_alarms_per_h",
    "time_err_p95_us",
    "time_hazardous_epochs",
)

# Fixed categorical colours in a fixed order: slots 1 to 4 as in analysis/lte_table_audit.py,
# and the deliberately simple reference filter in recessive ink
COLORS = {
    "baseline": "#52514e",
    "ekf": "#2a78d6",
    "ekf-calibrated": "#eb6834",
    "ekf-imu": "#1baf7a",
    "ekf-mhss": "#eda100",
}
# A guard estimator takes its default filter's colour and is drawn hatched
for _g, _d in GUARDED.items():
    COLORS[_g] = COLORS[_d]
INK, GRID = "#52514e", "#e4e3df"
KIND = "sim, every value TBC (ADR-0015, ADR-0030 Proposed)"


def _round(v) -> float | int | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return int(v)
    return float(f"{float(v):.6g}")


def error_curve(estimates, truth, spec: dict) -> list | None:
    """The run's horizontal error (m) at each second 0..CURVE_S after GPS loss: the estimate at
    the first epoch at or after loss + k s, paired with truth as `pnt.metrics.score` pairs them.
    None if the scenario has no GPS loss; nan for a second past the run or the outage."""
    loss = gps_loss(spec, T0_NS)
    if loss is None:
        return None
    start, end = loss
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    t = np.array([e.t_ns for e, _ in pairs])
    err = np.array([math.hypot(*np.subtract(e.pos_enu, g.pos_enu)[:2]) for e, g in pairs])
    out = []
    for k in range(CURVE_S + 1):
        at = start + s_to_ns(k)
        i = int(np.searchsorted(t, at))
        ok = i < len(t) and (end is None or t[i] < end) and t[i] - at < s_to_ns(1)
        out.append(_round(err[i]) if ok else None)
    return out


def bound_epochs(estimates, truth) -> tuple[np.ndarray, np.ndarray]:
    """(horizontal error, HPL) in metres at every epoch, paired with truth and computed exactly
    as `pnt.metrics.score` does, so `mean(hpl >= err)` is the run's `hpl_bound_frac`."""
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    err_h = np.array([np.subtract(e.pos_enu, g.pos_enu)[:2] for e, g in pairs])
    return np.hypot(err_h[:, 0], err_h[:, 1]), np.array([e.hpl_m for e, _ in pairs])


def is_bound_case(scenario: str, estimator: str) -> bool:
    """Is this one of the runs whose every epoch the T5 bound figure keeps?"""
    entry = scenario.removeprefix(f"challenge-{BOUND_LEG}-")
    return entry != scenario and entry in BOUND_ENTRIES and estimator in BOUND_ESTIMATORS


def run_one(scenario: str, seed: int, estimators: tuple[str, ...]) -> tuple[dict, dict, dict]:
    """One seed of one scenario, generated once, through each estimator. Returns
    ({estimator: [FIELDS values] or "Error: message" if it raised},
     {estimator: error_curve} for the estimators that ran, on an entry with a GPS loss,
     {estimator: (error, HPL) at every epoch} for the T5 bound figure's runs)."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    out: dict = {}
    curves: dict = {}
    epochs: dict = {}
    for name in estimators:
        try:
            est = list(
                estimate(
                    name,
                    run.measurements,
                    origin_llh=spec.get("origin_llh"),
                    reference=run.reference,
                )
            )
            m = score(est, run.truth, spec, T0_NS).as_dict()
            out[name] = [_round(m[k]) for k in FIELDS]
            curve = error_curve(est, run.truth, spec)
            if curve is not None:
                curves[name] = curve
            if is_bound_case(scenario, name):
                epochs[name] = bound_epochs(est, run.truth)
        except Exception as exc:  # report the crash, don't work around it
            out[name] = f"{type(exc).__name__}: {exc}"
    return out, curves, epochs


def across_run_p95(curves: list) -> np.ndarray:
    """ADR-0034's amendment, step 2: at each second after GPS loss, the 95th percentile of the
    horizontal error across the runs (rows: runs, columns: seconds). nan where no run has one."""
    a = np.array([[np.nan if v is None else v for v in c] for c in curves], float)
    out = np.full(a.shape[1] if a.ndim == 2 else 0, np.nan)
    have = ~np.all(np.isnan(a), axis=0) if a.size else np.zeros(0, bool)
    if have.any():
        out[have] = np.nanpercentile(a[:, have], 95, axis=0)
    return out


def worst_in(curve: np.ndarray, window_s: int) -> tuple[float, int]:
    """ADR-0034's amendment, step 3: (largest value, its second) of the curve over every second
    0..window_s; the target holds only if that value is within the limit. nan if any second of
    the window has no value, since the window is then not covered."""
    w = np.asarray(curve, float)[: window_s + 1]
    if w.size < window_s + 1 or np.any(np.isnan(w)):
        return math.nan, -1
    i = int(np.argmax(w))
    return float(w[i]), i


def entries(leg: str) -> list[str]:
    """The entry names (attack menu) of one leg, in menu order."""
    env = f"challenge-{leg}"
    return [n[len(env) + 1 :] for n in expand(env)]


def plan_tasks(data: dict) -> list[tuple[str, int, tuple[str, ...]]]:
    """Every (scenario, seed, estimators still to run) the options ask for."""
    tasks = []
    for leg in data["legs"]:
        for entry in data["entries"][leg]:
            scn = f"challenge-{leg}-{entry}"
            for seed in range(max(data["seeds"], data["mhss_seeds"])):
                todo = tuple(
                    e
                    for e in data["estimators"]
                    if seed < seeds_for(data, e, entry)
                    and str(seed) not in data["runs"].get(scn, {}).get(e, {})
                )
                if todo:
                    tasks.append((scn, seed, todo))
    return tasks


def subset(data: dict, estimator: str) -> tuple[int, list[str] | None]:
    """(seeds, entries or None for every entry) that one estimator runs."""
    if estimator == SLOW:
        return data["mhss_seeds"], data["mhss_entries"]
    if estimator in GUARDED:
        return data["seeds"], data["guard_entries"]
    return data["seeds"], None


def seeds_for(data: dict, estimator: str, entry: str) -> int:
    n, ents = subset(data, estimator)
    return n if ents is None or entry in ents else 0


# ---------------------------------------------------------------- reading the runs


def values(data: dict, scn: str, est: str, field: str) -> np.ndarray:
    """Per-seed values of one field, in seed order (nan for none); empty if not run."""
    runs = data["runs"].get(scn, {}).get(est, {})
    i = FIELDS.index(field)
    seeds = sorted((int(s) for s, r in runs.items() if isinstance(r, list)))
    return np.array([np.nan if runs[str(s)][i] is None else runs[str(s)][i] for s in seeds], float)


def curve_p95(data: dict, scn: str, est: str) -> tuple[np.ndarray, int]:
    """(across-run p95 per second after GPS loss, number of runs) for one entry and estimator;
    an empty curve and 0 if it has no curves."""
    runs = data.get("curves", {}).get(scn, {}).get(est, {})
    if not runs:
        return np.zeros(0), 0
    return across_run_p95([runs[s] for s in sorted(runs, key=int)]), len(runs)


def t1_cell(data: dict, scn: str, est: str, window_s: int) -> tuple[float, int, int]:
    """(worst second's across-run p95, that second, runs) over 0..window_s."""
    curve, n = curve_p95(data, scn, est)
    if not n:
        return math.nan, -1, 0
    v, s = worst_in(curve, window_s)
    return v, s, n


def _nanmean(v):
    return float(np.nanmean(v)) if v.size and not np.all(np.isnan(v)) else math.nan


def _nanmax(v):
    return float(np.nanmax(v)) if v.size and not np.all(np.isnan(v)) else math.nan


def _nanmin(v):
    return float(np.nanmin(v)) if v.size and not np.all(np.isnan(v)) else math.nan


def fmt_m(v: float) -> str:
    if math.isnan(v):
        return "—"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.1f}"


def fmt_us(v: float) -> str:
    return "—" if math.isnan(v) else f"{v:.2f}"


def fmt_pct(v: float) -> str:
    return "—" if math.isnan(v) else f"{100 * v:.2f} %"


def detected_within(data, scn, est, window_s) -> tuple[int, int]:
    """(seeds with a sustained alarm within window_s of the spoof start, seeds run)."""
    det = values(data, scn, est, "spoof_detected")
    delay = values(data, scn, est, "detect_delay_s")
    ok = (det == 1) & (delay <= window_s)
    return int(ok.sum()), int(det.size)


# ---------------------------------------------------------------- summary


def _est_cols(data) -> list[str]:
    return [e for e in ESTIMATOR_ORDER if e in data["estimators"]]


def jump_cell(data: dict, scn: str, est: str) -> str | None:
    """Detection, hazardous epochs and fault-window error on one jump or meaconing entry."""
    det = values(data, scn, est, "spoof_detected")
    if not det.size:
        return None
    delay = values(data, scn, est, "detect_delay_s")
    haz = values(data, scn, est, "hazardous_epochs")
    med = float(np.nanmedian(delay)) if not np.all(np.isnan(delay)) else math.nan
    return (
        f"{int(np.nansum(det == 1))} of {det.size}, "
        f"{'—' if math.isnan(med) else f'{med:.1f} s'}; "
        f"{_nanmean(haz):,.0f} /run, {int(np.sum(haz > 0))} of {haz.size}; "
        f"{fmt_m(_nanmean(values(data, scn, est, 'fault_h_p95_m')))} m"
    )


def identical(data: dict, scn: str, a: str, b: str) -> tuple[int, int]:
    """(seeds where b's metrics and error curve equal a's exactly, seeds both ran)."""
    ra = data["runs"].get(scn, {}).get(a, {})
    rb = data["runs"].get(scn, {}).get(b, {})
    ca = data.get("curves", {}).get(scn, {}).get(a, {})
    cb = data.get("curves", {}).get(scn, {}).get(b, {})
    both = [s for s in ra if s in rb]
    same = [s for s in both if ra[s] == rb[s] and ca.get(s) == cb.get(s)]
    return len(same), len(both)


def guard_rows(data: dict) -> list[list[str]]:
    """Default against guard, per leg x guard entry x guarded filter."""
    rows = []
    for leg in data["legs"]:
        for entry in data["guard_entries"]:
            if entry not in data["entries"][leg]:
                continue
            scn = f"challenge-{leg}-{entry}"
            for g, d in GUARDED.items():
                if g not in data["estimators"] or d not in data["estimators"]:
                    continue
                same, n = identical(data, scn, d, g)
                if not n:
                    continue
                cells = []
                for e in (d, g):
                    haz = values(data, scn, e, "hazardous_epochs")
                    mis = values(data, scn, e, "misleading_epochs")
                    hpl = values(data, scn, e, "hpl_bound_frac")
                    cells.append(
                        f"{int(np.sum(haz > 0))} of {haz.size}; {_nanmean(haz):,.0f}; "
                        f"{_nanmean(mis):,.0f}; "
                        f"{fmt_m(_nanmean(values(data, scn, e, 'fault_h_p95_m')))}; "
                        f"{fmt_pct(_nanmin(hpl))}"
                    )
                rows.append(
                    [f"{LEG_LABEL[leg]}", f"`{entry}`", f"`{d}` → `{g}`", *cells, f"{same} of {n}"]
                )
    return rows


def verdict_rows(data: dict) -> list[tuple[str, str, str, dict, str]]:
    """(target, where, measure, {estimator: cell}, verdict) per target row."""
    rows = []
    ests = _est_cols(data)

    def has(leg, entry):
        return leg in data["legs"] and entry in data["entries"][leg]

    def cut(leg, row_entries) -> dict:
        """{estimator: why} for each estimator that ran fewer seeds or entries than the row
        (`ekf-mhss`, the guard estimators)."""
        out = {}
        for e in ests:
            n, sub = subset(data, e)
            ran = [x for x in row_entries if sub is None or x in sub]
            why = []
            if len(ran) < len(row_entries):
                why.append(f"{len(ran)} of {len(row_entries)} entries")
            if ran and n < data["seeds"]:
                why.append(f"{seeds_text(n)}, not {data['seeds']}")
            if why:
                out[e] = ", ".join(why)
        return out

    def verdict(oks: list[bool | None], partial: dict | None = None) -> str:
        """`partial`: {estimator: why} for estimators that ran only some of the entries or seeds
        the row covers. Meeting the target there does not score it: such a row reads
        *partial / not scored* for them."""
        partial = partial or {}
        run = [o for o in oks if o is not None]
        if not run:
            return "not run"
        met = [e for e, o in zip(ests, oks, strict=True) if o and e not in partial]
        part = [e for e, o in zip(ests, oks, strict=True) if o and e in partial]
        tail = "; ".join(f"`{e}` meets it on a partial run ({partial[e]})" for e in part)
        if met:
            return "**met** by " + ", ".join(f"`{e}`" for e in met) + (f"; {tail}" if tail else "")
        if part:
            return f"**partial / not scored**: {tail}"
        return "**not met**"

    # T1 (ours) and ADR-0034's fallback (the mentors' figure): drone leg, outage entry, scored
    # as ADR-0034's amendment says (the 95th percentile across runs at each second after GPS
    # loss; the worst second of the window decides). Each run's own p95 over the slice is shown
    # after it, labelled: the amendment names it as not used.
    if has("drone", "outage"):
        scn = "challenge-drone-outage"
        for target, field, limit_m, window_s in (
            ("T1", "outage_h_p95_300s_m", T1_M, T1_WINDOW_S),
            ("T1 fallback (ADR-0034)", "outage_h_p95_120s_m", T1_FALLBACK_M, T1_FALLBACK_WINDOW_S),
        ):
            cells, oks = {}, []
            for e in ests:
                worst, at, n = t1_cell(data, scn, e, window_s)
                if not n:
                    cells[e], oks = "not run", [*oks, None]
                    continue
                per_run = values(data, scn, e, field)
                cells[e] = (
                    f"**{fmt_m(worst)} m** at {at} s; {n} runs (per-run {window_s} s p95, not "
                    f"the ADR's statistic: mean {fmt_m(_nanmean(per_run))} m)"
                )
                oks.append(bool(worst <= limit_m))
            rows.append(
                (
                    target,
                    "drone, `outage`",
                    f"95th percentile across runs at each second after GPS loss: worst second of "
                    f"0–{window_s} s (≤ {limit_m:g} m to meet), its second, runs",
                    cells,
                    verdict(oks, cut("drone", ["outage"])),
                )
            )
    # T2: approach leg, not scored
    if has("approach", "outage"):
        scn = "challenge-approach-outage"
        cells = {}
        for e in ests:
            v = values(data, scn, e, "outage_h_p95_300s_m")
            cells[e] = f"{fmt_m(_nanmean(v))} / {fmt_m(_nanmax(v))} m" if v.size else "not run"
        rows.append(
            (
                "T2",
                "approach, `outage` (**synthetic geometry**)",
                "300 s p95 mean / worst (not the T2 measure)",
                cells,
                f"**not scored**: no field tests the {T2_AL_M:g} m alert limit",
            )
        )
    # T3: timing leg, outage entry
    if has("timing", "outage"):
        scn = "challenge-timing-outage"
        cells, oks = {}, []
        for e in ests:
            v = values(data, scn, e, "outage_time_err_600s_us")
            s = values(data, scn, e, "outage_time_sigma_bound_600s")
            if not v.size:
                cells[e], oks = "not run", [*oks, None]
                continue
            if np.all(np.isnan(v)):
                cells[e], oks = "no clock state", [*oks, False]
                continue
            n = int(np.sum((v <= T3_US) & (s >= T3_SIGMA)))
            cells[e] = (
                f"{fmt_us(_nanmean(v))} / {fmt_us(_nanmax(v))} µs; "
                f"σ bound {fmt_pct(_nanmean(s))} / {fmt_pct(_nanmin(s))}; {n} of {v.size}"
            )
            oks.append(n == v.size)
        rows.append(
            (
                "T3",
                "timing, `outage`",
                f"600 s error mean / worst; σ bound mean / worst; seeds with ≤ {T3_US:g} µs "
                f"and ≥ {100 * T3_SIGMA:g} %",
                cells,
                verdict(oks, cut("timing", ["outage"])),
            )
        )
    # T4: spoof ramp (drone), time spoof (timing), false alarms on nominal (each leg)
    for leg, entry, window, what in (
        ("drone", "spoof-ramp", T4_RAMP_S, "2 m/s ramp"),
        ("timing", "time-spoof", T4_TIME_S, "50 ns/s time ramp"),
    ):
        if not has(leg, entry):
            continue
        scn = f"challenge-{leg}-{entry}"
        cells, oks = {}, []
        for e in ests:
            n, total = detected_within(data, scn, e, window)
            if not total:
                cells[e], oks = "not run", [*oks, None]
                continue
            delay = values(data, scn, e, "detect_delay_s")
            med = float(np.nanmedian(delay)) if not np.all(np.isnan(delay)) else math.nan
            cells[e] = f"{n} of {total}; median {'—' if math.isnan(med) else f'{med:.1f} s'}"
            oks.append(n == total)
        rows.append(
            (
                "T4",
                f"{leg}, `{entry}`",
                f"{what}: seeds detected ≤ {window:g} s; median delay of those detected",
                cells,
                verdict(oks, cut(leg, [entry])),
            )
        )
    # T4, location jumps (the mentors' first attack): the held 300 m jump and meaconing on each
    # leg. This table does not score T4's jump target (ADR-0034, amendment 2026-11-11) yet; the
    # cells show detection and whether the output then misleads (hazardous epochs), default
    # filters beside the guard.
    for leg in data["legs"]:
        for entry in JUMP_ENTRIES:
            if not has(leg, entry):
                continue
            scn = f"challenge-{leg}-{entry}"
            cells = {}
            for e in ests:
                c = jump_cell(data, scn, e)
                cells[e] = c if c else "not run"
            rows.append(
                (
                    "T4 (jump)",
                    f"{LEG_LABEL[leg]}, `{entry}`",
                    "seeds detected, median delay; hazardous epochs per run, runs with any; "
                    "fault-window p95 mean",
                    cells,
                    "**not scored** here: jump target in ADR-0034's amendment of 2026-11-11"
                    if entry == "spoof-jump"
                    else "**not scored**: no T4 target for meaconing",
                )
            )
    for leg in data["legs"]:
        if not has(leg, "nominal"):
            continue
        scn = f"challenge-{leg}-nominal"
        cells, oks = {}, []
        for e in ests:
            v = values(data, scn, e, "false_alarms_per_h")
            if not v.size:
                cells[e], oks = "not run", [*oks, None]
                continue
            # equal run lengths, so the mean of per-run rates is the pooled rate
            pooled = _nanmean(v)
            cells[e] = f"{pooled:.1f} /h; worst run {_nanmax(v):.0f} /h"
            oks.append(pooled <= T4_FA_PER_H)
        rows.append(
            (
                "T4",
                f"{LEG_LABEL[leg]}, `nominal`",
                f"false alarms per hour, pooled; worst run (target ≤ {T4_FA_PER_H:g} /h)",
                cells,
                verdict(oks, cut(leg, ["nominal"])),
            )
        )
    # T5: every entry of each leg
    for leg in data["legs"]:
        cells, oks = {}, []
        partial = cut(leg, data["entries"][leg])
        for e in ests:
            fracs, haz, nrun = [], 0, 0
            for entry in data["entries"][leg]:
                scn = f"challenge-{leg}-{entry}"
                f = values(data, scn, e, "hpl_bound_frac")
                fracs += list(f)
                nrun += f.size
                if entry != "nominal":
                    haz += int(np.nansum(values(data, scn, e, "hazardous_epochs")))
            if not nrun:
                cells[e], oks = "not run", [*oks, None]
                continue
            f = np.array(fracs)
            n = int(np.sum(f >= T5_HPL))
            cells[e] = f"worst {fmt_pct(_nanmin(f))}; {n} of {nrun} runs; {haz:,} hazardous" + (
                f" ({partial[e]})" if e in partial else ""
            )
            oks.append(n == nrun and haz == 0)
        rows.append(
            (
                "T5",
                f"{LEG_LABEL[leg]}, every entry",
                f"HPL bound, worst run; runs ≥ {100 * T5_HPL:g} %; hazardous epochs on fault "
                "entries (sum)",
                cells,
                verdict(oks, partial),
            )
        )
    return rows


FULL_COLS = (
    ("seeds", None),
    ("60 s p95 (m)", "outage_h_p95_60s_m"),
    ("120 s p95 (m)", "outage_h_p95_120s_m"),
    ("300 s p95 mean / worst (m; per run, not ADR-0034's statistic)", "outage_h_p95_300s_m"),
    ("across-run p95, worst second of 0–300 s (m, at s)", None),
    ("fault p95 (m)", "fault_h_p95_m"),
    ("HPL bound worst", "hpl_bound_frac"),
    ("hazardous", "hazardous_epochs"),
    ("misleading", "misleading_epochs"),
    ("detected / median delay", "spoof_detected"),
    ("false alarms /h", "false_alarms_per_h"),
    ("600 s time err mean / worst (µs)", "outage_time_err_600s_us"),
    ("600 s σ bound mean", "outage_time_sigma_bound_600s"),
)


def full_row(data, scn, est) -> list[str] | None:
    v = {f: values(data, scn, est, f) for f in FIELDS}
    n = v["hpl_bound_frac"].size
    if not n:
        return None
    det = v["spoof_detected"]
    if np.all(np.isnan(det)):
        det_txt = "—"
    else:
        d = v["detect_delay_s"]
        med = float(np.nanmedian(d)) if not np.all(np.isnan(d)) else math.nan
        det_txt = f"{int(np.nansum(det))} of {n}" + ("" if math.isnan(med) else f" / {med:.1f} s")
    p300 = v["outage_h_p95_300s_m"]
    t600 = v["outage_time_err_600s_us"]
    worst, at, nc = t1_cell(data, scn, est, T1_WINDOW_S)
    return [
        str(n),
        fmt_m(_nanmean(v["outage_h_p95_60s_m"])),
        fmt_m(_nanmean(v["outage_h_p95_120s_m"])),
        "—" if np.all(np.isnan(p300)) else f"{fmt_m(_nanmean(p300))} / {fmt_m(_nanmax(p300))}",
        "—" if not nc or math.isnan(worst) else f"{fmt_m(worst)} at {at} s",
        fmt_m(_nanmean(v["fault_h_p95_m"])),
        fmt_pct(_nanmin(v["hpl_bound_frac"])),
        f"{int(np.nansum(v['hazardous_epochs'])):,}",
        f"{int(np.nansum(v['misleading_epochs'])):,}",
        det_txt,
        "—"
        if np.all(np.isnan(v["false_alarms_per_h"]))
        else f"{_nanmean(v['false_alarms_per_h']):.1f}",
        "—" if np.all(np.isnan(t600)) else f"{fmt_us(_nanmean(t600))} / {fmt_us(_nanmax(t600))}",
        fmt_pct(_nanmean(v["outage_time_sigma_bound_600s"])),
    ]


def seeds_text(n: int) -> str:
    return f"seeds 0–{n - 1}" if n > 1 else "seeds 0"


def cut_lines(data: dict) -> list[str]:
    lines = []
    if SLOW in data["estimators"]:
        ran = [e for e in data["mhss_entries"]]
        lines.append(
            f"- `{SLOW}`: {seeds_text(data['mhss_seeds'])} (not {data['seeds']}), and only "
            f"the entries {', '.join(f'`{e}`' for e in ran)} of each leg. It takes 3 to 10 s a "
            f"run against about 1 s for the others; its cells elsewhere read *not run*."
        )
    guards = [e for e in GUARDED if e in data["estimators"]]
    if guards:
        lines.append(
            f"- {', '.join(f'`{e}`' for e in guards)} (opt-in jump guard, ADR-0038 Proposed): "
            f"{seeds_text(data['seeds'])}, only the entries "
            f"{', '.join(f'`{e}`' for e in data['guard_entries'])} of each leg (the held 300 m "
            "GNSS jump from 150 s and meaconing, and two entries without a jump); their cells "
            "elsewhere read *not run*."
        )
    for e in NEEDS_REFERENCE:
        lines.append(
            f"- `{e}`: not run. It needs a reference station (ADR-0020) and these legs have "
            "none (no entry run has a `reference:` block, checked before running); without one "
            "`nav/base_rover.py` is `ekf` with the payload's clock in its tower readings."
        )
    skipped = [e for e in ESTIMATOR_ORDER if e not in data["estimators"]]
    if skipped:
        lines.append(f"- Not asked for in this run: {', '.join(f'`{e}`' for e in skipped)}.")
    for leg in LEGS:
        if leg not in data["legs"]:
            lines.append(f"- Leg not run: {LEG_LABEL[leg]}.")
        elif data["entries"][leg] != entries(leg):
            lines.append(
                f"- {LEG_LABEL[leg]}: only {', '.join(f'`{e}`' for e in data['entries'][leg])}."
            )
    return lines


def write_summary(
    data: dict, out: Path, figures: list[str], bound: tuple[dict, dict] | None = None
) -> Path:
    ests = _est_cols(data)
    lines = [
        "# Challenge baseline: every estimator on every `challenge` entry",
        "",
        f'The "before" table (#150, package 5 of #126). **{KIND}.** It becomes the presented '
        "result only once ADR-0030 is accepted.",
        "",
        f"- **Commit:** `{data['commit']}`"
        + (
            ""
            if _clean(data["commit"])
            else " (**not a clean commit**: these numbers are not reproducible, REQ-10)"
        ),
        f"- **Seeds:** {seeds_text(data['seeds'])[6:]} (`ekf-mhss`: "
        f"{seeds_text(data['mhss_seeds'])[6:]})"
        if SLOW in data["estimators"]
        else f"- **Seeds:** {seeds_text(data['seeds'])[6:]}",
        f"- **Command:** `{data['command']}`",
        f"- **Runtime:** {data['runtime_s'] / 60:.1f} min wall, {data['jobs']} worker(s)",
        "- **Approach leg: synthetic geometry** (ADR-0030 point 3). Its towers are a synthetic "
        "ring, all ahead of the aircraft; its T1 slice does not measure LTE (in effect IMU and "
        "barometer dead reckoning).",
        "",
        "**What was cut:**",
        "",
        *cut_lines(data),
    ]
    if data["errors"]:
        lines += ["", "**Crashes** (reported, not worked around):", ""]
        for key, msg in sorted(data["errors"].items()):
            lines.append(f"- {key}: `{msg}`")
    lines += [
        "",
        "## Verdict per target",
        "",
        "Targets from `systems/plan.md` and ADR-0034 (T1 Accepted, its value `TBC`; T4's jump "
        "target Accepted; T3, T5 and T4's ramp targets Proposed). T3 is **met** by an estimator "
        "only if every seed meets it, T4 detection likewise, false alarms on the pooled rate. "
        "Cells read *mean / worst* over seeds; *of* counts seeds (or runs) meeting the target. "
        "An estimator that ran fewer seeds or entries than the row covers (`ekf-mhss`, the guard "
        "estimators) does not score it: where only such an estimator meets the target the row "
        "reads *partial / not scored*.",
        "",
        "**T1 statistic** (ADR-0034's amendment of 2026-11-10, adf24d7 on `main`): at each "
        "second after GPS loss, the 95th percentile of the horizontal error across the runs; "
        f"T1 holds only if that curve stays ≤ {T1_M:g} m for every second of 0–{T1_WINDOW_S} s. "
        "The cell gives the worst second's value, that second, and the number of runs. The "
        f"*T1 fallback* row is ADR-0034's declared fallback, the mentors' figure (≤ "
        f"{T1_FALLBACK_M:g} m over 0–{T1_FALLBACK_WINDOW_S} s), scored the same way. Each run's "
        "own p95 over the slice is shown after it in brackets: the amendment names it as not "
        "used, and no verdict rests on it.",
        "",
        "| Target | Leg, entry | Measure | " + " | ".join(f"`{e}`" for e in ests) + " | Verdict |",
        "|---" * (4 + len(ests)) + "|",
    ]
    for target, where, measure, cells, verdict in verdict_rows(data):
        lines.append(
            f"| {target} | {where} | {measure} | "
            + " | ".join(cells.get(e, "not run") for e in ests)
            + f" | {verdict} |"
        )
    lines += [
        "",
        "T2 asks for a 556 m horizontal alert limit (RNP 0.3) in the terminal phase. No field "
        "of `pnt.metrics.RunMetrics` scores it (the alert limit used is "
        "`ALERT_LIMIT_M` = 50 m), so its 300 s error is given only for reference, and it is "
        "synthetic geometry.",
        "",
    ]
    grows = guard_rows(data)
    if grows:
        lines += [
            "## Jump guard: default against guard",
            "",
            "The opt-in guard estimators (ADR-0038, Proposed) beside the default filter they "
            "guard, paired on the same runs. `spoof-jump` holds a 300 m GNSS jump east from "
            "150 s to the end; `meaconing` replays GNSS 5 s late from 150 s to the end. "
            "Each cell: runs with a hazardously misleading epoch (error over the 50 m alert "
            "limit with HPL under it); hazardous epochs per run (mean); misleading epochs per "
            "run (mean); fault-window p95 (m, mean); HPL bound, worst run. *Identical*: runs "
            "whose metrics and error curve equal the default's exactly.",
            "",
            "| Leg | Entry | Default → guard | Default | Guard | Identical |",
            "|---|---|---|---|---|---|",
            *[f"| {' | '.join(r)} |" for r in grows],
            "",
        ]
    lines += [
        "## Full table",
        "",
        "Means over seeds unless marked; *worst* is the worst seed. Slices count from GPS loss "
        "(60 s); a slice is — when the entry has no GPS loss. The 60, 120 and 300 s p95 are "
        "each run's own; *across-run p95* is ADR-0034's statistic (the worst second of the "
        "per-second 95th percentile across runs). HPL bound worst: the worst run's "
        "share of epochs with HPL ≥ error. Hazardous and misleading: epochs summed over seeds. "
        "Detected: seeds with a sustained alarm after a spoof starts, and the median delay. "
        "False alarms: alarms outside spoof windows per hour.",
        "",
    ]
    for leg in data["legs"]:
        lines += [f"### {LEG_LABEL[leg]}", ""]
        lines.append("| Entry | Estimator | " + " | ".join(c for c, _ in FULL_COLS) + " |")
        lines.append("|---" * (2 + len(FULL_COLS)) + "|")
        for entry in data["entries"][leg]:
            scn = f"challenge-{leg}-{entry}"
            for e in ests:
                row = full_row(data, scn, e)
                if row is None:
                    continue
                lines.append(f"| `{entry}` | `{e}` | " + " | ".join(row) + " |")
        lines.append("")
    if figures:
        lines += ["## Figures", ""]
        lines += [f"![{f}]({f})" for f in figures]
        if bound is not None and "t5_bound.png" in figures:
            lines += bound_caption(data, bound)
        lines.append("")
    lines += [
        "## Reproduce",
        "",
        f"From commit `{data['commit']}`, a clean tree: `{data['command']}`. The per-run data "
        "(`runs.json`: metrics, and each run's error at every second after GPS loss) goes to "
        "the git-ignored `analysis/results/runs/challenge-baseline/`; it is not committed. "
        "`--redraw` rewrites this file and the figures from it without running.",
        "",
    ]
    path = out / "summary.md"
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------- figures

# Slide-sized (16:9) and legible from the back of a room
FIG_SIZE, FIG_DPI = (13.33, 7.5), 110
FS_TITLE, FS_LABEL, FS_TICK, FS_NOTE = 19, 15, 13, 11


def _style(ax) -> None:
    ax.grid(True, which="major", color=GRID, lw=0.8)
    ax.tick_params(labelsize=FS_TICK)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _defaults(data) -> list[str]:
    """The estimator columns without the guard estimators (drawn only where they differ)."""
    return [e for e in _est_cols(data) if e not in GUARDED]


def _guard_note(data, scn: str) -> str:
    """'guard estimators identical on N of N runs' for one entry, or '' if none ran there."""
    pairs = [identical(data, scn, d, g) for g, d in GUARDED.items() if g in data["estimators"]]
    pairs = [p for p in pairs if p[1]]
    if not pairs:
        return ""
    same, n = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
    head = "jump-guard estimators (ADR-0038): identical to their default on"
    return (
        f"{head} all {n} runs, not drawn" if same == n else f"{head} {same} of {n} runs, not drawn"
    )


def _strip(ax, data, scn, field, ests, scale=1.0) -> list:
    """Each estimator's seeds as dots, with a bar at the median. Returns the plotted values."""
    allv = []
    rng = np.random.default_rng(0)  # jitter only, fixed so the figure is reproducible
    for i, e in enumerate(ests):
        v = values(data, scn, e, field) * scale
        v = v[~np.isnan(v)]
        if not v.size:
            ax.text(i, 0.02, "not run", ha="center", va="bottom", fontsize=FS_NOTE, color=INK,
                    transform=ax.get_xaxis_transform(), rotation=90)  # fmt: skip
            continue
        x = i + rng.uniform(-0.2, 0.2, v.size)
        ax.plot(x, v, "o", ms=5, color=COLORS[e], alpha=0.55, mew=0)
        ax.plot([i - 0.32, i + 0.32], [np.median(v)] * 2, color=COLORS[e], lw=3.5)
        allv += list(v)
    ax.set_xticks(range(len(ests)), [""] * len(ests))
    ax.set_xlim(-0.6, len(ests) - 0.4)
    return allv


def _legend(fig, ests, extra=(), marker="o") -> None:
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], marker=marker, ls="", ms=10, color=COLORS[e], label=e) for e in ests]
    handles += list(extra)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=FS_LABEL,
               frameon=False, bbox_to_anchor=(0.5, 0.03))  # fmt: skip


def _caption(fig, text: str) -> None:
    fig.text(0.01, 0.008, text, fontsize=FS_NOTE, color=INK)


def _title(fig, title: str, sub: str) -> None:
    fig.text(0.01, 0.975, title, fontsize=FS_TITLE, weight="bold", va="top")
    fig.text(0.01, 0.915, sub, fontsize=FS_NOTE + 1, color=INK, va="top")


def _spread(y: list[float], gap: float) -> list[float]:
    """Label positions (axes fraction) near `y`, at least `gap` apart, order kept."""
    order = sorted(range(len(y)), key=lambda i: y[i])
    out = list(y)
    for k in range(1, len(order)):
        a, b = order[k - 1], order[k]
        out[b] = max(out[b], out[a] + gap)
    top = max(out) if out else 0
    if top > 0.98:  # shift the stack down if it runs off the top
        for i in range(len(out)):
            out[i] -= top - 0.98
    return out


def fig_t1(data: dict, title_tail: str, caption: str):
    """Q: at each second after GPS loss, is the 95 % error across runs within T1 (and the
    fallback), on the drone leg's `outage` entry? (ADR-0034's statistic)"""
    if "drone" not in data["legs"] or "outage" not in data["entries"]["drone"]:
        return None
    import matplotlib.pyplot as plt

    scn = "challenge-drone-outage"
    ests = [e for e in _defaults(data) if curve_p95(data, scn, e)[1]]
    if not ests:
        return None
    fig, ax = plt.subplots(figsize=FIG_SIZE, dpi=FIG_DPI)
    t = np.arange(CURVE_S + 1)
    ends, labels, ymax, ymin = [], [], T1_FALLBACK_M, T1_M
    for e in ests:
        curve, n = curve_p95(data, scn, e)
        ax.plot(t[: curve.size], curve, color=COLORS[e], lw=3.2, solid_capstyle="round")
        worst, at = worst_in(curve, T1_WINDOW_S)
        ax.plot(at, worst, "o", ms=9, color=COLORS[e], mec="white", mew=1.5, zorder=5)
        ymax, ymin = max(ymax, np.nanmax(curve)), min(ymin, np.nanmin(curve[curve > 0]))
        ends.append(curve[min(T1_WINDOW_S, curve.size - 1)])
        runs = f", {n} runs" if n != data["seeds"] else ""
        labels.append((e, f"{e}: worst {fmt_m(worst)} m{runs}"))
    ax.set_yscale("log")
    ax.set_ylim(max(ymin / 2, 0.5), ymax * 2.5)
    ax.set_xlim(0, CURVE_S)
    # The targets, each drawn over its own window
    ax.hlines(T1_M, 0, T1_WINDOW_S, color=INK, lw=2, ls=(0, (2, 2)))
    ax.hlines(T1_FALLBACK_M, 0, T1_FALLBACK_WINDOW_S, color=INK, lw=2, ls=(0, (6, 3)))
    # Labelled where the curves are far above the lines, so no curve crosses the text
    ax.text(T1_WINDOW_S - 3, T1_M / 1.12, f"T1: {T1_M:g} m, every second 0–{T1_WINDOW_S} s",
            fontsize=FS_LABEL, color=INK, va="top", ha="right")  # fmt: skip
    ax.text(T1_FALLBACK_WINDOW_S - 2, T1_FALLBACK_M * 1.1,
            f"fallback: {T1_FALLBACK_M:g} m, 0–{T1_FALLBACK_WINDOW_S} s",
            fontsize=FS_LABEL, color=INK, va="bottom", ha="right")  # fmt: skip
    # Direct labels at the right end of each curve, spread so they do not overlap
    lo, hi = (math.log10(v) for v in ax.get_ylim())
    frac = [(math.log10(max(v, 1e-9)) - lo) / (hi - lo) for v in ends]
    for (e, text), y in zip(labels, _spread(frac, 0.055), strict=True):
        ax.text(1.01, y, text, transform=ax.transAxes, fontsize=FS_LABEL, color=COLORS[e],
                va="center", weight="bold")  # fmt: skip
    ax.set_xlabel("time since GPS loss (s)", fontsize=FS_LABEL)
    ax.set_ylabel("95th percentile across runs of\nhorizontal error at that second (m)",
                  fontsize=FS_LABEL)  # fmt: skip
    _style(ax)
    note = _guard_note(data, scn)
    _title(
        fig,
        "T1: 95 % of runs' horizontal error at each second after GPS loss (drone, outage)",
        f"ADR-0034 statistic; a dot marks each curve's worst second · {title_tail}"
        + (f"\n{note}" if note else ""),
    )
    _caption(fig, caption)
    fig.subplots_adjust(left=0.09, right=0.67, top=0.82, bottom=0.12)
    return fig


def fig_t3(data: dict, title_tail: str, caption: str):
    """Q: is the timing receiver within T3 at 10 min without GPS, on each outage entry?"""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    if "timing" not in data["legs"]:
        return None
    ents = [e for e in data["entries"]["timing"] if e.startswith("outage")]
    # `baseline` has no clock state, so no time error
    ests = [e for e in _defaults(data) if e != "baseline"]
    if not ents or not ests:
        return None
    ncol = 3
    nrow = math.ceil(len(ents) / ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=FIG_SIZE, dpi=FIG_DPI, sharey=True,
                             squeeze=False)  # fmt: skip
    for ax in list(axes.flat)[len(ents) :]:
        ax.set_visible(False)
    allv = []
    for ax, entry in zip(axes.flat, ents, strict=False):
        allv += _strip(ax, data, f"challenge-timing-{entry}", "outage_time_err_600s_us", ests)
        ax.axhline(T3_US, color=INK, lw=2, ls=(0, (2, 2)))
        ax.set_yscale("log")
        ax.set_title(entry, fontsize=FS_LABEL, loc="left")
        _style(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel("|time error| 600 s after\nGPS loss (µs)", fontsize=FS_LABEL)
    if allv:
        axes[0, 0].set_ylim(min([*allv, T3_US]) / 2, max([*allv, T3_US]) * 2)
    t3 = Line2D([], [], color=INK, lw=2, ls=(0, (2, 2)), label=f"T3 {T3_US:g} µs")
    _legend(fig, ests, [t3])
    note = _guard_note(data, "challenge-timing-outage")
    _title(
        fig,
        "T3: time error 10 min after GPS loss — timing leg, one dot per seed, bar at median",
        f"p95 of the last 10 s; baseline has no clock · {title_tail}"
        + (f"\n{note} (outage entry)" if note else ""),
    )
    _caption(fig, caption)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.8, bottom=0.17, hspace=0.35, wspace=0.08)
    return fig


SPOOF_ENTRIES = (
    ("spoof-ramp", T4_RAMP_S, f"ramp\n≤ {T4_RAMP_S:g} s"),
    ("time-spoof", T4_TIME_S, f"time ramp\n≤ {T4_TIME_S:g} s"),
    ("spoof-jump", math.inf, "300 m jump\nany delay"),
    ("meaconing", math.inf, "meaconing\nany delay"),
)


def fig_t4(data: dict, title_tail: str, caption: str):
    """Q: which GNSS spoofs does each estimator detect, and after a held jump or meaconing,
    does the output mislead, with and without the jump guard?"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    legs = data["legs"]
    ests = _defaults(data)
    if not legs:
        return None
    guards = [g for g in GUARDED if g in data["estimators"]]
    nrow = 2 if guards else 1
    fig, axes = plt.subplots(nrow, len(legs), figsize=FIG_SIZE, dpi=FIG_DPI, sharey="row",
                             squeeze=False)  # fmt: skip
    width = 0.8 / len(ests)
    for ax, leg in zip(axes[0], legs, strict=True):
        spoofs = [s for s in SPOOF_ENTRIES if s[0] in data["entries"][leg]]
        for j, e in enumerate(ests):
            for i, (entry, window, _) in enumerate(spoofs):
                n, total = detected_within(data, f"challenge-{leg}-{entry}", e, window)
                x = i - 0.4 + width * (j + 0.5)
                if total:
                    ax.bar(x, n / total, width, color=COLORS[e])
                    # a dot on top, so a share of 0 still shows that the estimator ran
                    ax.plot(x, n / total, "o", ms=5, color=COLORS[e], clip_on=False)
                else:
                    ax.text(x, 0.03, "not run", rotation=90, ha="center", va="bottom",
                            fontsize=FS_NOTE - 2, color=INK)  # fmt: skip
        ax.set_xticks(range(len(spoofs)), [s[2] for s in spoofs], fontsize=FS_NOTE)
        ax.set_ylim(0, 1.05)
        ax.set_title(LEG_LABEL[leg].replace(" geometry", ""), fontsize=FS_LABEL, loc="left")
        _style(ax)
        ax.tick_params(axis="x", labelsize=FS_NOTE)
    axes[0, 0].set_ylabel("share of seeds\ndetected", fontsize=FS_LABEL)
    if guards:
        pairs = [(GUARDED[g], g) for g in guards]
        jumps = [e for e in JUMP_ENTRIES]
        w = 0.8 / (2 * len(pairs))
        for ax, leg in zip(axes[1], legs, strict=True):
            for i, entry in enumerate(jumps):
                scn = f"challenge-{leg}-{entry}"
                for j, (d, g) in enumerate(pairs):
                    for k, e in enumerate((d, g)):
                        haz = values(data, scn, e, "hazardous_epochs")
                        x = i - 0.4 + w * (2 * j + k + 0.5)
                        if not haz.size:
                            continue
                        share = float(np.mean(haz > 0))
                        ax.bar(x, share, w, color=COLORS[e] if k == 0 else "white",
                               edgecolor=COLORS[e], hatch="//" if k else None, lw=1.5)  # fmt: skip
                        ax.plot(x, share, "o", ms=5, color=COLORS[e], clip_on=False)
            ax.set_xticks(range(len(jumps)), ["300 m jump", "meaconing"], fontsize=FS_NOTE)
            ax.set_ylim(0, 1.05)
            _style(ax)
            ax.tick_params(axis="x", labelsize=FS_NOTE)
        axes[1, 0].set_ylabel("share of runs with a\nhazardous epoch", fontsize=FS_LABEL)
    handles = [Patch(color=COLORS[e], label=e) for e in ests]
    if guards:
        handles.append(
            Patch(facecolor="white", edgecolor=INK, hatch="//", label="with jump guard")
        )
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=FS_LABEL - 1,
               frameon=False, bbox_to_anchor=(0.5, 0.03))  # fmt: skip
    _title(
        fig,
        "T4: GNSS spoofs detected; after a held jump, does the output mislead?",
        "top: sustained alarm within the T4 window (jump, meaconing: any delay) · bottom: "
        "error over 50 m with HPL under it, default solid, guard hatched\n"
        f"approach leg: synthetic geometry · {title_tail}",
    )
    _caption(fig, caption)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.82, bottom=0.17, hspace=0.45, wspace=0.08)
    return fig


BOUND_LABEL = {
    "outage": "outage: GPS lost\n60–660 s",
    "spoof-jump": "spoof-jump: GNSS\n300 m east, 150 s on",
}
BOUND_RANGE_M = (1.0, 1e5)  # both axes; values outside are drawn on the edge, counted as they are
ESCAPED, HAZARD = "#fbe3d6", "#f2b694"  # pale tints of ekf-calibrated's orange


def bound_stats(runs: dict) -> dict:
    """One estimator on one entry, from every epoch of every run: the share of epochs where the
    error exceeds HPL (pooled), the worst run's share with HPL >= error (T5's 'HPL bound, worst
    run'), the hazardous epochs (error over the alert limit with HPL at or under it, as
    `pnt.metrics.score` counts them) and the runs and epochs."""
    err = [r[0] for r in runs.values()]
    hpl = [r[1] for r in runs.values()]
    e, h = np.concatenate(err), np.concatenate(hpl)
    return {
        "above": float(np.mean(e > h)),
        "worst_bound": min(float(np.mean(b >= a)) for a, b in zip(err, hpl, strict=True)),
        "hazardous": int(np.sum((e > ALERT_LIMIT_M) & (h <= ALERT_LIMIT_M))),
        "runs": len(err),
        "epochs": int(e.size),
    }


def _bound_cells(data: dict, bound: dict) -> list[tuple[str, str, dict | None]]:
    """(entry, estimator, its runs or None) for every panel of the T5 bound figure, in order."""
    ests = [e for e in BOUND_ESTIMATORS if e in data["estimators"]]
    ents = [e for e in BOUND_ENTRIES if e in data["entries"].get(BOUND_LEG, [])]
    return [
        (entry, e, bound.get(f"challenge-{BOUND_LEG}-{entry}", {}).get(e) or None)
        for entry in ents
        for e in ests
    ]


def fig_t5(data: dict, bound: dict, title_tail: str, caption: str):
    """Q: at every epoch of every run, does the HPL bound the true horizontal error, on the drone
    leg's GPS loss and held jump? Error against HPL: above the diagonal the error escaped."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    cells = _bound_cells(data, bound)
    if not any(r for _, _, r in cells):
        return None
    ents = list(dict.fromkeys(c[0] for c in cells))
    ests = list(dict.fromkeys(c[1] for c in cells))
    lo, hi, al = *BOUND_RANGE_M, ALERT_LIMIT_M
    edges = np.logspace(math.log10(lo), math.log10(hi), 61)
    fig, axes = plt.subplots(len(ents), len(ests), figsize=FIG_SIZE, dpi=FIG_DPI, sharex=True,
                             sharey=True, squeeze=False)  # fmt: skip
    empty = []
    for (entry, e, runs), ax in zip(cells, axes.flat, strict=True):
        r, c = ents.index(entry), ests.index(e)
        if r == 0:
            ax.set_title(e, fontsize=FS_LABEL, color=COLORS[e], weight="bold")
        if c == 0:
            ax.set_ylabel("true error (m)", fontsize=FS_NOTE + 1)
            ax.annotate(BOUND_LABEL.get(entry, entry), (0, 0.5), xycoords="axes fraction",
                        xytext=(-62, 0), textcoords="offset points", rotation=90, ha="right",
                        va="center", fontsize=FS_LABEL, weight="bold")  # fmt: skip
        if not runs:
            empty.append((ax, f"{e} not run on {entry}"))
            continue
        # Escaped region (error > HPL), and inside it the hazardous box (HPL <= AL < error)
        ax.fill_between([lo, hi], [lo, hi], hi, color=ESCAPED, lw=0, zorder=0)
        ax.fill_between([lo, al], [al, al], hi, color=HAZARD, lw=0, zorder=0)
        err = np.clip(np.concatenate([v[0] for v in runs.values()]), lo, hi)
        hpl = np.clip(np.concatenate([v[1] for v in runs.values()]), lo, hi)
        count, _, _ = np.histogram2d(hpl, err, [edges, edges])
        ax.pcolormesh(edges, edges, np.ma.masked_equal(count.T, 0), cmap="Blues",
                      norm=LogNorm(1, 5e4), zorder=1, rasterized=True)  # fmt: skip
        ax.plot([lo, hi], [lo, hi], color="black", lw=1.6, zorder=2)
        st = bound_stats(runs)
        sub = "of epochs above"
        if e in GUARDED:
            same, n = identical(data, f"challenge-{BOUND_LEG}-{entry}", GUARDED[e], e)
            if same == n:
                sub += f"\nidentical: {same} of {n} runs"
        ax.text(0.04, 0.97, f"{100 * st['above']:.1f} %", transform=ax.transAxes, va="top",
                fontsize=FS_TITLE + 1, weight="bold", zorder=3)  # fmt: skip
        ax.text(0.04, 0.80, sub, transform=ax.transAxes, va="top", fontsize=FS_NOTE, zorder=3)
        low = f"worst run\nbounded {fmt_pct(st['worst_bound'])}\nhazardous {st['hazardous']:,}"
        ax.text(0.97, 0.03, low, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=FS_NOTE, color=INK, zorder=3)  # fmt: skip
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal")
        ticks = [1, 100, 1e4]
        ax.set_xticks(ticks, ["≤1", "100", "10k"])
        ax.set_yticks(ticks, ["≤1", "100", "10k"])
        ax.minorticks_off()
        ax.tick_params(labelsize=FS_TICK)
    # The key goes in an empty panel if there is one, else below the panels
    handles = [
        Patch(color=ESCAPED, label="error > HPL:\nbound escaped"),
        Patch(color=HAZARD, label=f"hazardous: error\n> {al:g} m, HPL ≤ {al:g} m"),
        Line2D([], [], color="black", lw=1.6, label="error = HPL"),
        Patch(color="#4a90c8", label="epochs (darker:\nmore of them)"),
    ]
    if empty:
        ax, why = empty[0]
        ax.set_axis_off()
        ax.legend(handles=handles, loc="upper left", fontsize=FS_NOTE + 1, frameon=False,
                  bbox_to_anchor=(-0.05, 1.02), handlelength=1.6)  # fmt: skip
        ax.text(0.0, 0.08, "\n".join(w for _, w in empty).replace(" on ", "\non "),
                transform=ax.transAxes, fontsize=FS_NOTE + 1, color=INK)  # fmt: skip
    else:
        fig.legend(handles=handles, loc="lower right", ncol=3, fontsize=FS_NOTE, frameon=False)
    for ax in axes[-1]:
        if ax.axison:
            ax.set_xlabel("HPL (m)", fontsize=FS_NOTE + 1)
    _title(
        fig,
        "T5: does the protection level bound the true error? Every epoch of every run",
        "big number: share of all epochs above the diagonal · bottom right: T5's worst run "
        "(share of its epochs bounded) and hazardous epochs, as in summary.md\n"
        f"drone (UC-01), each whole 720 s run at 10 Hz · {title_tail}",
    )
    _caption(fig, caption)
    fig.subplots_adjust(left=0.11, right=0.99, top=0.82, bottom=0.11, wspace=0.10, hspace=0.18)
    return fig


def _save_png(fig, path: Path) -> None:
    """A 256-colour PNG: the figures are flat colour, and this keeps the committed folder small."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)


def write_t1_curves(data: dict, out: Path) -> str | None:
    """The across-run p95 per second on the drone `outage` entry, small enough to commit."""
    scn = "challenge-drone-outage"
    curves = {}
    for e in _est_cols(data):
        c, n = curve_p95(data, scn, e)
        if n:
            curves[e] = {"runs": n, "p95_m": [None if math.isnan(v) else _round(v) for v in c]}
    if not curves:
        return None
    doc = {
        "what": "95th percentile across runs of the horizontal error at each second 0..300 s "
        "after GPS loss, challenge-drone-outage (ADR-0034 amendment); sim",
        "commit": data["commit"],
        "command": data["command"],
        "curves": curves,
    }
    (out / "t1_curves.json").write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False))
    return "t1_curves.json"


def write_figures(data: dict, out: Path, bound: tuple[dict, dict] | None = None) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    seeds = seeds_text(data["seeds"])
    if SLOW in data["estimators"]:
        seeds += f" (ekf-mhss {seeds_text(data['mhss_seeds'])[6:]})"
    tail = f"sim · {seeds} · commit {data['commit']}"
    caption = f"{KIND} · analysis/challenge_baseline.py; numbers in summary.md"
    written = []
    for name, fn in (
        ("t1_drone.png", fig_t1),
        ("t3_timing.png", fig_t3),
        ("t4_detection.png", fig_t4),
    ):
        fig = fn(data, tail, caption)
        if fig is None:
            continue
        _save_png(fig, out / name)
        plt.close(fig)
        written.append(name)
    if bound is not None:
        epochs, meta = bound
        ents = [e for e in BOUND_ENTRIES if e in data["entries"].get(BOUND_LEG, [])]
        runs = "; ".join(f"{e} {bound_seeds(data, epochs, e)}" for e in ents)
        fig = fig_t5(data, epochs, f"sim · {runs} · computed at commit {meta['commit']}", caption)
        if fig is not None:
            _save_png(fig, out / "t5_bound.png")
            plt.close(fig)
            written.append("t5_bound.png")
    return written


def bound_seeds(data: dict, epochs: dict, entry: str) -> str:
    """'seeds 0–49 (ekf-mhss 0–19)' for the runs the T5 bound figure has on one entry."""
    by_est = epochs.get(f"challenge-{BOUND_LEG}-{entry}", {})
    n = {e: len(r) for e, r in by_est.items()}
    if not n:
        return "not run"
    most = max(n.values())
    fewer = [f"{e} {seeds_text(k)[6:]}" for e, k in n.items() if k != most]
    return seeds_text(most) + (f" ({', '.join(fewer)})" if fewer else "")


def bound_caption(data: dict, bound: tuple[dict, dict]) -> list[str]:
    """The T5 bound figure's caption in summary.md: where it comes from and its numbers."""
    epochs, meta = bound
    lines = [
        "",
        "*t5_bound.png*: the drone leg's true horizontal error against HPL at every 0.1 s epoch "
        "of each whole run (the epochs T5 scores). Above the diagonal the error escaped the "
        "bound. Per panel: the share of all epochs above it (pooled over runs); the worst "
        "run's share with HPL ≥ error (the *HPL bound worst* column above); hazardous epochs "
        "(summed, the *hazardous* column).",
    ]
    if meta["commit"] != data["commit"]:
        lines[-1] += (
            f" Computed at `{meta['commit']}` (`{meta['command']}`, the runs' metrics checked "
            f"equal to `runs.json`); every table and the other figures are from "
            f"`{data['commit']}`."
        )
    lines += [
        "",
        "| Entry | Estimator | runs | epochs above HPL | worst run bounded | hazardous |",
    ]
    lines.append("|---|---|---|---|---|---|")
    for entry, e, runs in _bound_cells(data, epochs):
        if not runs:
            continue
        st = bound_stats(runs)
        lines.append(
            f"| `{entry}` | `{e}` | {st['runs']} | {fmt_pct(st['above'])} | "
            f"{fmt_pct(st['worst_bound'])} | {st['hazardous']:,} |"
        )
    return lines


# ---------------------------------------------------------------- main


def _clean(commit: str) -> bool:
    """True for the hash of a clean tree: `_commit()` gives `<hash>-dirty` for a tree with
    uncommitted changes to tracked files, and a word when there is no git."""
    return len(commit) >= 7 and all(c in "0123456789abcdef" for c in commit)


def _save(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))


def save_bound(bound: dict, meta: dict, path: Path) -> None:
    """The T5 bound figure's epochs ({scenario: {estimator: {seed: (err, hpl)}}}) as float64
    arrays, exact so the figure's shares equal T5's, with `meta` (commit, command) as JSON."""
    arrays = {"meta": np.array(json.dumps(meta))}
    for scn, by_est in bound.items():
        for est, by_seed in by_est.items():
            for seed, (err, hpl) in by_seed.items():
                arrays[f"{scn}/{est}/{seed}/err"] = np.asarray(err, float)
                arrays[f"{scn}/{est}/{seed}/hpl"] = np.asarray(hpl, float)
    with path.open("wb") as f:
        np.savez_compressed(f, **arrays)


def load_bound(path: Path) -> tuple[dict, dict] | None:
    """(epochs, meta) as `save_bound` wrote them, or None if there is no file."""
    if not path.exists():
        return None
    bound: dict = {}
    with np.load(path, allow_pickle=False) as z:
        meta = json.loads(str(z["meta"]))
        for key in z.files:
            if key == "meta" or not key.endswith("/err"):
                continue
            scn, est, seed, _ = key.split("/")
            hpl = z[f"{scn}/{est}/{seed}/hpl"]
            bound.setdefault(scn, {}).setdefault(est, {})[seed] = (z[key], hpl)
    return bound, meta


def bound_tasks(data: dict) -> list[tuple[str, int, tuple[str, ...]]]:
    """The T5 bound figure's runs, with the seeds the baseline in `data` ran per estimator."""
    tasks = []
    if BOUND_LEG not in data["legs"]:
        return tasks
    for entry in BOUND_ENTRIES:
        if entry not in data["entries"][BOUND_LEG]:
            continue
        scn = f"challenge-{BOUND_LEG}-{entry}"
        for seed in range(max(data["seeds"], data["mhss_seeds"])):
            todo = tuple(
                e
                for e in data["estimators"]
                if is_bound_case(scn, e) and seed < seeds_for(data, e, entry)
            )
            if todo:
                tasks.append((scn, seed, todo))
    return tasks


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=50, help="seeds 0..N-1 (default 50)")
    p.add_argument("--jobs", type=int, default=3, help="worker processes (default 3)")
    p.add_argument(
        "--estimators",
        nargs="+",
        default=list(ESTIMATOR_ORDER),
        choices=list(ESTIMATOR_ORDER),
        help="default: every registered estimator these legs can run",
    )
    p.add_argument("--legs", nargs="+", default=list(LEGS), choices=list(LEGS))
    p.add_argument("--entries", nargs="+", help="only these entries of each leg (default: all)")
    p.add_argument("--mhss-seeds", type=int, default=MHSS_SEEDS, help="ekf-mhss seeds 0..M-1")
    p.add_argument("--mhss-entries", nargs="+", default=list(MHSS_ENTRIES))
    p.add_argument(
        "--guard-entries",
        nargs="+",
        default=list(GUARD_ENTRIES),
        help="entries the jump-guard estimators run on",
    )
    p.add_argument("--out", default=str(OUT))
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--resume", action="store_true", help="keep the runs already in runs.json (same commit)"
    )
    g.add_argument(
        "--redraw", action="store_true", help="only rewrite summary and figures from runs.json"
    )
    g.add_argument(
        "--bound",
        action="store_true",
        help=f"re-run only the T5 bound figure's runs into {BOUND_FILE}, check them against "
        "runs.json, then redraw",
    )
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    committed = out.resolve() == OUT.resolve()
    # Per-run data is not committed: beside the committed results it goes to the ignored folder
    runs_dir = RUNS if committed else out
    runs_dir.mkdir(parents=True, exist_ok=True)
    json_path = runs_dir / "runs.json"
    bound_path = runs_dir / BOUND_FILE
    commit = _commit()
    # REQ-10: the committed results name a commit they can be regenerated from
    if not args.redraw and committed and not _clean(commit):
        raise SystemExit(
            f"tree is {commit}: commit first, the committed results must name a clean commit "
            "(or write elsewhere with --out)"
        )

    argv_list = sys.argv[1:] if argv is None else list(argv)
    if args.redraw:
        data = json.loads(json_path.read_text())
    elif args.bound:
        data = json.loads(json_path.read_text())
        tasks = bound_tasks(data)
        print(f"bound: {len(tasks)} (scenario, seed) tasks", flush=True)
        t_start = time.time()
        results = _map(run_one, tasks, args.jobs)
        bound: dict = {}
        differ = []
        for (scn, seed, _), (res, _curves, epochs) in zip(tasks, results, strict=True):
            for est, r in res.items():
                # The same runs at another commit: their metrics must equal the table's
                if r != data["runs"].get(scn, {}).get(est, {}).get(str(seed)):
                    differ.append(f"{scn} {est} seed {seed}")
            for est, ep in epochs.items():
                bound.setdefault(scn, {}).setdefault(est, {})[str(seed)] = ep
        if differ:
            raise SystemExit(
                f"{len(differ)} run(s) differ from runs.json ({data['commit']}), nothing written: "
                + "; ".join(differ[:10])
            )
        meta = {
            "commit": commit,
            "command": "python analysis/challenge_baseline.py " + shlex.join(argv_list),
            "runtime_s": time.time() - t_start,
        }
        save_bound(bound, meta, bound_path)
        print(f"bound: {len(tasks)} tasks in {meta['runtime_s']:.0f} s, equal to runs.json")
    else:
        command = "python analysis/challenge_baseline.py " + shlex.join(
            [a for a in argv_list if a != "--resume"]
        )
        ests = [e for e in ESTIMATOR_ORDER if e in args.estimators]
        legs = [leg for leg in LEGS if leg in args.legs]
        ents = {
            leg: [e for e in entries(leg) if args.entries is None or e in args.entries]
            for leg in legs
        }
        data = {
            "commit": commit,
            "command": command.strip(),
            "seeds": args.seeds,
            "mhss_seeds": args.mhss_seeds if SLOW in ests else 0,
            "mhss_entries": list(args.mhss_entries) if SLOW in ests else [],
            "guard_entries": list(args.guard_entries) if set(GUARDED) & set(ests) else [],
            "estimators": ests,
            "legs": legs,
            "entries": ents,
            "jobs": args.jobs,
            "fields": list(FIELDS),
            "runtime_s": 0.0,
            "curve_s": CURVE_S,
            "runs": {},
            "curves": {},
            "errors": {},
        }
        if args.resume and json_path.exists():
            old = json.loads(json_path.read_text())
            if old["commit"] != commit:
                raise SystemExit(
                    f"runs.json is from {old['commit']}, this is {commit}: one commit per table"
                )
            data["runs"], data["errors"] = old["runs"], old["errors"]
            data["curves"] = old.get("curves", {})
            data["runtime_s"] = old["runtime_s"]
        # The base/rover filters need a reference station; `generate` makes one only from a
        # `reference:` block, so check every entry has none before leaving them out
        for leg in legs:
            for entry in ents[leg]:
                if load(f"challenge-{leg}-{entry}").get("reference"):
                    raise SystemExit(f"challenge-{leg}-{entry} has a reference station")
        t_start = time.time()
        bound: dict = {}
        for leg in legs:  # one leg at a time, saved after each, so --resume loses little
            tasks = [t for t in plan_tasks(data) if t[0].startswith(f"challenge-{leg}-")]
            print(f"{leg}: {len(tasks)} (scenario, seed) tasks", flush=True)
            t_leg = time.time()
            results = _map(run_one, tasks, args.jobs)
            for (scn, seed, _), (res, curves, epochs) in zip(tasks, results, strict=True):
                for est, r in res.items():
                    data["runs"].setdefault(scn, {}).setdefault(est, {})[str(seed)] = r
                    if isinstance(r, str):
                        data["errors"][f"{scn} {est} seed {seed}"] = r
                for est, c in curves.items():
                    data["curves"].setdefault(scn, {}).setdefault(est, {})[str(seed)] = c
                for est, ep in epochs.items():
                    bound.setdefault(scn, {}).setdefault(est, {})[str(seed)] = ep
            data["runtime_s"] += time.time() - t_leg
            _save(data, json_path)
            print(f"{leg}: done in {time.time() - t_leg:.0f} s", flush=True)
        print(f"ran in {time.time() - t_start:.0f} s", flush=True)
        # A --resume keeps no epochs from before it, so it writes the file only if it has them all
        if bound and not args.resume:
            save_bound(bound, {"commit": commit, "command": data["command"]}, bound_path)

    bound = load_bound(bound_path)
    figures = write_figures(data, out, bound)
    path = write_summary(data, out, figures, bound)
    curves = write_t1_curves(data, out)
    print(f"wrote {path}, {json_path}, {curves} and {len(figures)} figure(s)")


if __name__ == "__main__":
    main()
