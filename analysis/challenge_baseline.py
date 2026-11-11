"""The challenge baseline (#150, package 5 of #126): every registered estimator on every entry
of the three `challenge` legs (ADR-0030, Proposed), as the "before" table that fixes pair with.

    python analysis/challenge_baseline.py --seeds 50 --jobs 3

Writes to `--out` (default `analysis/results/challenge-baseline/`):
- summary.md: the verdict per target (T1 to T5, systems/plan.md, all TBC; T1 also against
  ADR-0034's fallback), then the full table of leg x entry x estimator, with the commit,
  seeds, command and runtime. The committed results are written only from a clean tree.
- runs.json: the per-run metrics behind it (a subset of `pnt.metrics.RunMetrics`, 6 significant
  digits), so the summary and figures can be redrawn without re-running (`--redraw`) and an
  interrupted run can carry on (`--resume`, same commit only)
- t1_drone.png, t3_timing.png, t4_detection.png: one question each (see the fig_* functions)

Each (scenario, seed) is generated once and every estimator runs on the same measurements, so
estimators are paired, and seeds 0..N-1 are those of `pnt eval` (systems/quality.md). Scoring is
`pnt.metrics.score`, as in `pnt eval`. Nothing here changes an estimator, scenario or metric:
a target that fails is reported as failing.

Estimators: `ekf-base` and `ekf-base-imu` need a reference station (ADR-0020). The challenge
legs have none (the script checks), and without one `nav/base_rover.py` is `ekf` with the
payload's clock, so they are not run. `ekf-mhss` takes several seconds a run, so by default it
runs fewer seeds on only the entries where its monitor matters (`--mhss-seeds`,
`--mhss-entries`); the summary says what was cut.

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
from pnt.experiments import _map
from pnt.metrics import score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, expand, generate, load

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "results" / "challenge-baseline"

LEGS = ("drone", "timing", "approach")
LEG_LABEL = {
    "drone": "drone (UC-01)",
    "timing": "timing (UC-03)",
    "approach": "approach (UC-02, synthetic geometry)",
}
ESTIMATOR_ORDER = ("baseline", "ekf", "ekf-calibrated", "ekf-imu", "ekf-mhss")
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

# Targets, systems/plan.md (all TBC until the mentors answer Q1 to Q3)
T1_M = 25.0  # 95 % horizontal error over the first 300 s after GPS loss
# ADR-0034 (open PR #158): the mentors' figure, T1's declared fallback
T1_FALLBACK_M = 50.0  # horizontal error over the first 120 s after GPS loss
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
INK, GRID = "#52514e", "#e4e3df"
KIND = "sim, every value TBC (ADR-0015, ADR-0030 Proposed)"


def _round(v) -> float | int | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return int(v)
    return float(f"{float(v):.6g}")


def run_one(scenario: str, seed: int, estimators: tuple[str, ...]) -> dict:
    """One seed of one scenario, generated once, through each estimator. Returns
    {estimator: [FIELDS values]} or {estimator: "Error: message"} if it raised."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    out: dict = {}
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
        except Exception as exc:  # report the crash, don't work around it
            out[name] = f"{type(exc).__name__}: {exc}"
    return out


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


def seeds_for(data: dict, estimator: str, entry: str) -> int:
    if estimator != SLOW:
        return data["seeds"]
    return data["mhss_seeds"] if entry in data["mhss_entries"] else 0


# ---------------------------------------------------------------- reading the runs


def values(data: dict, scn: str, est: str, field: str) -> np.ndarray:
    """Per-seed values of one field, in seed order (nan for none); empty if not run."""
    runs = data["runs"].get(scn, {}).get(est, {})
    i = FIELDS.index(field)
    seeds = sorted((int(s) for s, r in runs.items() if isinstance(r, list)))
    return np.array([np.nan if runs[str(s)][i] is None else runs[str(s)][i] for s in seeds], float)


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


def verdict_rows(data: dict) -> list[tuple[str, str, str, dict, str]]:
    """(target, where, measure, {estimator: cell}, verdict) per target row."""
    rows = []
    ests = _est_cols(data)

    def has(leg, entry):
        return leg in data["legs"] and entry in data["entries"][leg]

    def cut(leg, row_entries) -> dict:
        """{estimator: why} for `ekf-mhss` when it ran fewer seeds or entries than the row."""
        if SLOW not in ests:
            return {}
        ran = [e for e in row_entries if e in data["mhss_entries"]]
        why = []
        if len(ran) < len(row_entries):
            why.append(f"{len(ran)} of {len(row_entries)} entries")
        if data["mhss_seeds"] < data["seeds"]:
            why.append(f"{seeds_text(data['mhss_seeds'])}, not {data['seeds']}")
        return {SLOW: ", ".join(why)} if why else {}

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

    # T1 (ours) and ADR-0034's fallback (the mentors' figure): drone leg, outage entry. The
    # statistic is each run's own p95 over the slice, and every seed must pass. The p95 across
    # seeds of those per-run values is shown too: ADR-0034 is to settle which one T1 means.
    if has("drone", "outage"):
        scn = "challenge-drone-outage"
        for target, field, limit_m, slice_s in (
            ("T1", "outage_h_p95_300s_m", T1_M, 300),
            ("T1 fallback (ADR-0034, #158)", "outage_h_p95_120s_m", T1_FALLBACK_M, 120),
        ):
            cells, oks = {}, []
            for e in ests:
                v = values(data, scn, e, field)
                if not v.size:
                    cells[e], oks = "not run", [*oks, None]
                    continue
                n = int(np.sum(v <= limit_m))
                across = float(np.nanpercentile(v, 95)) if not np.all(np.isnan(v)) else math.nan
                cells[e] = (
                    f"{fmt_m(_nanmean(v))} / {fmt_m(_nanmax(v))} m; {n} of {v.size}; "
                    f"across seeds {fmt_m(across)} m"
                )
                oks.append(n == v.size)
            rows.append(
                (
                    target,
                    "drone, `outage`",
                    f"{slice_s} s p95 mean / worst; seeds ≤ {limit_m:g} m; p95 across seeds",
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
    ("300 s p95 mean / worst (m)", "outage_h_p95_300s_m"),
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
    return [
        str(n),
        fmt_m(_nanmean(v["outage_h_p95_60s_m"])),
        fmt_m(_nanmean(v["outage_h_p95_120s_m"])),
        "—" if np.all(np.isnan(p300)) else f"{fmt_m(_nanmean(p300))} / {fmt_m(_nanmax(p300))}",
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


def write_summary(data: dict, out: Path, figures: list[str]) -> Path:
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
        "Targets from `systems/plan.md`, all `TBC`. A target is **met** by an estimator only if "
        "every seed meets it (false alarms: the pooled rate). Cells read *mean / worst* over "
        "seeds; *of* counts seeds (or runs) meeting the target. An estimator that ran fewer "
        "seeds or entries than the row covers (`ekf-mhss`) does not score it: where it alone "
        "meets the target the row reads *partial / not scored*.",
        "",
        "**T1 statistic:** each run's own 95th percentile of horizontal error over the slice "
        "after GPS loss, and every seed must pass. *Across seeds* gives the 95th percentile of "
        "those per-run values over the seeds, for comparison. ADR-0034 (open PR #158) is to "
        "settle which of the two T1 means; until then the verdict uses the first. The "
        "*T1 fallback* row is ADR-0034's declared fallback, the mentors' figure (≤ "
        f"{T1_FALLBACK_M:g} m for 120 s), scored the same way.",
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
        "## Full table",
        "",
        "Means over seeds unless marked; *worst* is the worst seed. Slices count from GPS loss "
        "(60 s); a slice is — when the entry has no GPS loss. HPL bound worst: the worst run's "
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
        lines.append("")
    lines += [
        "## Reproduce",
        "",
        f"From commit `{data['commit']}`, a clean tree: `{data['command']}`. "
        "`--redraw` rewrites this file and the figures from `runs.json` without running.",
        "",
    ]
    path = out / "summary.md"
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------- figures


def _style(ax) -> None:
    ax.grid(True, which="major", color=GRID, lw=0.6)
    ax.tick_params(labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _strip(ax, data, scn, field, ests, scale=1.0) -> list:
    """Each estimator's seeds as dots, with a bar at the median. Returns the plotted values."""
    allv = []
    rng = np.random.default_rng(0)  # jitter only, fixed so the figure is reproducible
    for i, e in enumerate(ests):
        v = values(data, scn, e, field) * scale
        v = v[~np.isnan(v)]
        if not v.size:
            ax.text(i, 0.02, "not run", ha="center", va="bottom", fontsize=7, color=INK,
                    transform=ax.get_xaxis_transform(), rotation=90)  # fmt: skip
            continue
        x = i + rng.uniform(-0.18, 0.18, v.size)
        ax.plot(x, v, "o", ms=3, color=COLORS[e], alpha=0.6, label=e)
        ax.plot([i - 0.3, i + 0.3], [np.median(v)] * 2, color=COLORS[e], lw=2.5)
        allv += list(v)
    ax.set_xticks(range(len(ests)), [""] * len(ests))
    ax.set_xlim(-0.6, len(ests) - 0.4)
    return allv


def _legend(fig, ests, extra=()) -> None:
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], marker="o", ls="", color=COLORS[e], label=e) for e in ests]
    handles += list(extra)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, 0.035))  # fmt: skip


def _panels(n: int, ncol: int = 3):
    import matplotlib.pyplot as plt

    nrow = math.ceil(n / ncol)
    fig, axes = plt.subplots(
        nrow, ncol, figsize=(11, 0.8 + 3.0 * nrow), dpi=130, sharey=True, squeeze=False
    )
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    return fig, axes


def _caption(fig, text: str) -> None:
    fig.text(0.01, 0.005, text, fontsize=7, color=INK)


def fig_t1(data: dict, title_tail: str, caption: str):
    """Q: does any estimator keep the drone leg's 300 s error within T1, on each outage entry?"""
    from matplotlib.lines import Line2D

    if "drone" not in data["legs"]:
        return None
    ents = [e for e in data["entries"]["drone"] if e.startswith("outage")]
    ests = _est_cols(data)
    if not ents:
        return None
    fig, axes = _panels(len(ents))
    allv = []
    for ax, entry in zip(axes.flat, ents, strict=False):
        allv += _strip(ax, data, f"challenge-drone-{entry}", "outage_h_p95_300s_m", ests)
        ax.axhline(T1_M, color=INK, lw=1, ls=":")
        ax.set_yscale("log")
        ax.set_title(entry, fontsize=9, loc="left")
        _style(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel("p95 horizontal error over the\nfirst 300 s after GPS loss (m)", fontsize=8)
    if allv:
        axes[0, 0].set_ylim(min([*allv, T1_M]) / 2, max(allv) * 2)
    t1 = Line2D([], [], color=INK, lw=1, ls=":", label=f"T1 {T1_M:g} m (TBC)")
    _legend(fig, ests, [t1])
    fig.suptitle(
        f"T1: 300 s error after GPS loss, challenge-drone (UC-01), one dot per seed, bar at "
        f"median\n{title_tail}",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    _caption(fig, caption)
    fig.tight_layout(rect=(0, 0.08, 1, 0.93))
    return fig


def fig_t3(data: dict, title_tail: str, caption: str):
    """Q: is the timing receiver within T3 at 10 min without GPS, on each outage entry?"""
    from matplotlib.lines import Line2D

    if "timing" not in data["legs"]:
        return None
    ents = [e for e in data["entries"]["timing"] if e.startswith("outage")]
    # `baseline` has no clock state, so no time error
    ests = [e for e in _est_cols(data) if e != "baseline"]
    if not ents or not ests:
        return None
    fig, axes = _panels(len(ents))
    allv = []
    for ax, entry in zip(axes.flat, ents, strict=False):
        allv += _strip(ax, data, f"challenge-timing-{entry}", "outage_time_err_600s_us", ests)
        ax.axhline(T3_US, color=INK, lw=1, ls=":")
        ax.set_yscale("log")
        ax.set_title(entry, fontsize=9, loc="left")
        _style(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel("|time error| at 600 s after\nGPS loss, p95 of last 10 s (µs)", fontsize=8)
    if allv:
        axes[0, 0].set_ylim(min([*allv, T3_US]) / 2, max([*allv, T3_US]) * 2)
    t3 = Line2D([], [], color=INK, lw=1, ls=":", label=f"T3 {T3_US:g} µs (TBC)")
    _legend(fig, ests, [t3])
    fig.suptitle(
        "T3: time error 10 min after GPS loss, challenge-timing (UC-03), one dot per seed, bar "
        f"at median (baseline: no clock)\n{title_tail}",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    _caption(fig, caption)
    fig.tight_layout(rect=(0, 0.08, 1, 0.93))
    return fig


SPOOF_ENTRIES = (
    ("spoof-ramp", T4_RAMP_S, f"spoof-ramp\n≤ {T4_RAMP_S:g} s (T4)"),
    ("time-spoof", T4_TIME_S, f"time-spoof\n≤ {T4_TIME_S:g} s (T4)"),
    ("spoof-jump", math.inf, "spoof-jump\nany delay"),
    ("meaconing", math.inf, "meaconing\nany delay"),
)


def fig_t4(data: dict, title_tail: str, caption: str):
    """Q: which GNSS spoofs does each estimator detect, on each leg?"""
    legs = data["legs"]
    ests = _est_cols(data)
    if not legs:
        return None
    fig, axes = _panels(len(legs))
    width = 0.8 / len(ests)
    for ax, leg in zip(axes.flat, legs, strict=False):
        spoofs = [s for s in SPOOF_ENTRIES if s[0] in data["entries"][leg]]
        for j, e in enumerate(ests):
            for i, (entry, window, _) in enumerate(spoofs):
                n, total = detected_within(data, f"challenge-{leg}-{entry}", e, window)
                x = i - 0.4 + width * (j + 0.5)
                if total:
                    ax.bar(x, n / total, width, color=COLORS[e])
                    # a dot on top, so a share of 0 still shows that the estimator ran
                    ax.plot(x, n / total, "o", ms=4, color=COLORS[e], clip_on=False)
                else:
                    ax.text(x, 0.02, "not run", rotation=90, ha="center", va="bottom",
                            fontsize=6, color=INK)  # fmt: skip
        ax.set_xticks(range(len(spoofs)), [s[2] for s in spoofs], fontsize=7)
        ax.set_ylim(0, 1.05)
        ax.set_title(LEG_LABEL[leg], fontsize=9, loc="left")
        _style(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel("share of seeds detected\n(sustained alarm)", fontsize=8)
    from matplotlib.patches import Patch

    handles = [Patch(color=COLORS[e], label=e) for e in ests]
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, 0.035))  # fmt: skip
    fig.suptitle(
        f"T4: GNSS spoofs detected, every challenge leg (approach: synthetic geometry)\n"
        f"{title_tail}",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    _caption(fig, caption)
    fig.tight_layout(rect=(0, 0.08, 1, 0.92))
    return fig


def write_figures(data: dict, out: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    seeds = seeds_text(data["seeds"])
    if SLOW in data["estimators"]:
        seeds += f" (ekf-mhss {seeds_text(data['mhss_seeds'])}, some entries)"
    tail = f"{seeds} · commit {data['commit']}"
    caption = f"{KIND} · analysis/challenge_baseline.py, numbers in summary.md and runs.json"
    written = []
    for name, fn in (
        ("t1_drone.png", fig_t1),
        ("t3_timing.png", fig_t3),
        ("t4_detection.png", fig_t4),
    ):
        fig = fn(data, tail, caption)
        if fig is None:
            continue
        fig.savefig(out / name)
        plt.close(fig)
        written.append(name)
    return written


# ---------------------------------------------------------------- main


def _clean(commit: str) -> bool:
    """True for the hash of a clean tree: `_commit()` gives `<hash>-dirty` for a tree with
    uncommitted changes to tracked files, and a word when there is no git."""
    return len(commit) >= 7 and all(c in "0123456789abcdef" for c in commit)


def _save(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))


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
    p.add_argument("--out", default=str(OUT))
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--resume", action="store_true", help="keep the runs already in runs.json (same commit)"
    )
    g.add_argument(
        "--redraw", action="store_true", help="only rewrite summary and figures from runs.json"
    )
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "runs.json"
    commit = _commit()
    # REQ-10: the committed results name a commit they can be regenerated from
    if not args.redraw and out.resolve() == OUT.resolve() and not _clean(commit):
        raise SystemExit(
            f"tree is {commit}: commit first, the committed results must name a clean commit "
            "(or write elsewhere with --out)"
        )

    if args.redraw:
        data = json.loads(json_path.read_text())
    else:
        argv_list = sys.argv[1:] if argv is None else list(argv)
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
            "estimators": ests,
            "legs": legs,
            "entries": ents,
            "jobs": args.jobs,
            "fields": list(FIELDS),
            "runtime_s": 0.0,
            "runs": {},
            "errors": {},
        }
        if args.resume and json_path.exists():
            old = json.loads(json_path.read_text())
            if old["commit"] != commit:
                raise SystemExit(
                    f"runs.json is from {old['commit']}, this is {commit}: one commit per table"
                )
            data["runs"], data["errors"] = old["runs"], old["errors"]
            data["runtime_s"] = old["runtime_s"]
        # The base/rover filters need a reference station; `generate` makes one only from a
        # `reference:` block, so check every entry has none before leaving them out
        for leg in legs:
            for entry in ents[leg]:
                if load(f"challenge-{leg}-{entry}").get("reference"):
                    raise SystemExit(f"challenge-{leg}-{entry} has a reference station")
        t_start = time.time()
        for leg in legs:  # one leg at a time, saved after each, so --resume loses little
            tasks = [t for t in plan_tasks(data) if t[0].startswith(f"challenge-{leg}-")]
            print(f"{leg}: {len(tasks)} (scenario, seed) tasks", flush=True)
            t_leg = time.time()
            results = _map(run_one, tasks, args.jobs)
            for (scn, seed, _), res in zip(tasks, results, strict=True):
                for est, r in res.items():
                    data["runs"].setdefault(scn, {}).setdefault(est, {})[str(seed)] = r
                    if isinstance(r, str):
                        data["errors"][f"{scn} {est} seed {seed}"] = r
            data["runtime_s"] += time.time() - t_leg
            _save(data, json_path)
            print(f"{leg}: done in {time.time() - t_leg:.0f} s", flush=True)
        print(f"ran in {time.time() - t_start:.0f} s", flush=True)

    figures = write_figures(data, out)
    path = write_summary(data, out, figures)
    print(f"wrote {path}, {json_path} and {len(figures)} figure(s)")


if __name__ == "__main__":
    main()
