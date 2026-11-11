"""Slow GNSS drag with carrier hopping (#221, #258): does hearing more masts let the tower
monitor (ADR-0037, `integrity/spoof_monitor.py`) catch the 2 m/s ramp? Sim, every value TBC.

One command, from a clean commit:

    python analysis/drag_with_hopping.py --seeds 50 --stress-seeds 10 --jobs 5

writes `summary.md` (the tables) and `detection_vs_masts.png` to
`analysis/results/drag-with-hopping/` (committed, so only from a clean tree: REQ-10), and one
row per run to `analysis/results/runs/drag-with-hopping.json` (git-ignored). `--redraw` rebuilds
the summary and figure from that file.

What the dongle hears, everything else as committed (the hop leg's ADR-0040, Proposed):
- 1 carrier: the drone leg as committed (`challenge-drone-<entry>`, EARFCN 2460);
- 6 carriers: `challenge-drone-hop-<entry>` hopping the first 6 carriers of its hop set, as
  `analysis/hopping_study.py` selects them (scan-list order, dwell as committed);
- 13 carriers: `challenge-drone-hop-<entry>` as committed.

Entries `spoof-ramp` (2 m/s from 150 s), `nominal` and `outage`, each inherited from
`challenge-drone` (no scenario file is added), paired on seeds 0 to N-1. Estimators:
- `ekf`: no monitor;
- `ekf-every-epoch-spoof` (this study only): the monitor with the site rule before #258, a site
  counting if heard on half of every epoch of a window. It is `ekf-spoof` with each reading's
  carrier dropped, which is that rule exactly (`towers_test`: rows without a carrier are one
  carrier);
- `ekf-spoof`: the monitor as committed, a site counting if heard on half of the epochs on
  which one of its own carriers was on air (ADR-0037, amendment for carrier hopping);
- with `--calibrated`, the same three on `ekf-calibrated`.

Stress cases, on `--stress-seeds` seeds (0 to M-1), 13 carriers unless named: the ramp at 1 and
0.5 m/s, dwells of 2 s (ramp and `nominal`), and the held 300 m jump (`spoof-jump`). Six
carriers and the outage entry are in the main table.

The monitor's settings are as committed (ADR-0037, chosen on seeds 100-109 of another case);
the new site rule was checked on seeds 100-109 of this leg and is not tuned on these seeds.
Runs and scoring are `spoof_detection.py`'s (`run_spec`, `detection`), so a row means the same
thing in both studies.
"""

from __future__ import annotations

import argparse
import copy
import math
import time
from functools import partial
from pathlib import Path

import hopping_study as hs
import numpy as np
import spoof_detection as sd

from pnt.cli import _commit
from pnt.experiments import _map
from pnt.integrity.spoof_monitor import Params, SpoofMonitor, f_threshold
from pnt.nav import ESTIMATORS, cells, ekf
from pnt.sim.scenario import T0_NS, generate, load

RESULTS = Path(__file__).resolve().parent / "results"
OUT = RESULTS / "drag-with-hopping"  # committed: summary.md, detection_vs_masts.png
RUNS = RESULTS / "runs" / "drag-with-hopping.json"  # git-ignored: one row per run
CARRIERS = (1, 6, 13)
ENTRIES = ("spoof-ramp", "nominal", "outage")
BEFORE = "ekf-every-epoch-spoof"  # the site rule before #258 (this study only)
PLAIN = ("ekf", BEFORE, "ekf-spoof")
CALIBRATED = ("ekf-calibrated", "ekf-calibrated-every-epoch-spoof", "ekf-calibrated-spoof")
# monitor variant -> the unchanged filter it is paired with for added false alarms
BASE = {BEFORE: "ekf", "ekf-spoof": "ekf"}
BASE.update({CALIBRATED[1]: CALIBRATED[0], CALIBRATED[2]: CALIBRATED[0]})
STRESS = (
    "13-carrier:spoof-ramp@1",
    "13-carrier:spoof-ramp@0.5",
    "13-carrier/dwell2:spoof-ramp",
    "13-carrier/dwell2:nominal",
    "13-carrier:spoof-jump",
)
WINDOW_S = 10.0
TTA_TARGET_S = 30.0  # T4's ramp time to alert (ADR-0034, TBC)
RAMP_MPS = 2.0  # the committed spoof-ramp entry
SUCCESS = 45  # #221: seeds of 50 the monitor must flag on the 13-carrier leg
# Categorical slots 1 to 3 (analysis/spoof_detection.py) for monitor off, the rule before #258
# and the rule now; on the calibrated filter the same colours with square markers
COLOURS = {"ekf": "#2a78d6", BEFORE: "#eb6834", "ekf-spoof": "#1baf7a"}
COLOURS.update(zip(CALIBRATED, list(COLOURS.values()), strict=True))
LABELS = {"ekf": "monitor off", BEFORE: "monitor, rule before #258", "ekf-spoof": "monitor now"}
INK, GRID = "#52514e", "#e4e3df"


class EveryEpochMonitor(SpoofMonitor):
    """The monitor with each reading's carrier dropped: every reading is then one carrier, and
    a site counts if heard on half of every epoch of a window (the rule before #258)."""

    def _tower_reading(self, m) -> None:
        n = len(self._rows)
        super()._tower_reading(m)
        if len(self._rows) > n:
            self._rows[-1] = self._rows[-1][:5]


# Study-only names, in this process's registry (spoof_detection's runner looks them up there)
ESTIMATORS.setdefault(BEFORE, partial(ekf.run, monitor=EveryEpochMonitor))
ESTIMATORS.setdefault(CALIBRATED[1], partial(ekf.run_calibrated, monitor=EveryEpochMonitor))


def case_id(carriers: int, entry: str) -> str:
    return f"{carriers}-carrier:{entry}"


def parse(case: str) -> tuple[int, str]:
    """(carriers, entry) of a case id `<n>-carrier[/dwell<s>]:<entry>[@<ramp m/s>]`."""
    leg, entry = case.split(":")
    return int(leg.split("-")[0]), entry


def spec_of(case: str) -> dict:
    """The spec of a case id, from the committed scenarios; only the carriers hopped, and for
    a stress case the dwell or the ramp's rate, vary."""
    n, entry = parse(case)
    leg = case.split(":")[0]
    base, _, rate = entry.partition("@")
    if n == 1:
        spec = copy.deepcopy(load(f"challenge-drone-{base}"))
    else:
        spec = copy.deepcopy(load(f"challenge-drone-hop-{base}"))
        scan = list(spec["sources"]["lte"]["cells_from"]["earfcn"])
        if not 1 < n <= len(scan):
            raise ValueError(f"{n} carriers: the hop set has {len(scan)}")
        spec["sources"]["lte"]["cells_from"]["earfcn"] = scan[:n]
        if "/dwell" in leg:
            spec["sources"]["lte"]["hop"]["dwell_s"] = float(leg.split("/dwell")[1])
    if rate:
        ramps = [f for f in spec["faults"] if f["type"] == "spoof_ramp"]
        if not ramps:
            raise ValueError(f"{case}: no ramp to set a rate on")
        for f in ramps:
            f["rate_mps"] = float(rate)
    spec["name"] = case
    return spec


def masts_per_window(run, spec: dict, mast_of: dict[str, int]) -> float:
    """Median over every `WINDOW_S` window of the run of the distinct masts heard after the cell
    lookup (registered eNBs within SAME_SITE_M are one mast, as `hopping_study.masts`)."""
    lte = [m for m in run.measurements if m.source == "lte"]
    n = int(float(spec["duration_s"]) // WINDOW_S)
    windows: list[set] = [set() for _ in range(n)]
    for m in cells.attach(lte, spec["origin_llh"]):
        k = int((m.t_ns - T0_NS) / 1e9 // WINDOW_S)
        if 0 <= k < n:
            windows[k].add(mast_of[m.meta["site"]])
    return float(np.median([len(w) for w in windows]))


TAIL_P = (0.1, 0.01, 0.001)  # tail probabilities the tests' p-values are counted below


def pooled_dof(thr: float, p: float) -> int:
    """The pooled degrees of freedom a tower test used, from its threshold (`f_threshold` is
    strictly decreasing in dof)."""
    lo, hi = 1, 10**7
    while lo < hi:
        mid = (lo + hi) // 2
        if f_threshold(p, mid) > thr * (1 + 1e-12):
            lo = mid + 1
        else:
            hi = mid
    return lo


def tails(log: list) -> dict:
    """Per tower test: how many tests had an opinion and how many of them had a p-value under
    each of `TAIL_P` against F(2, pooled dof). Under no spoof a calibrated test has a share near
    each p; the false-alarm budget rests on the far tail (`p_fa_towers`), which a run's few
    hundred correlated tests cannot reach, so this checks the shape, not the budget."""
    p_test = Params().p_fa_towers / len(Params().tower_tests)
    out: dict = {}
    for _, rep in log:
        for key, v in rep.items():
            if v is None:
                continue
            F, thr = v[0], v[1]
            dof = pooled_dof(thr, p_test)
            pv = (1.0 + 2.0 * F / dof) ** (-dof / 2.0)
            out[f"tower_test_{key}_tests"] = out.get(f"tower_test_{key}_tests", 0) + 1
            for a in TAIL_P:
                k = f"tower_test_{key}_p_lt_{a:g}"
                out[k] = out.get(k, 0) + int(pv < a)
    return out


def run_one(case: str, estimator: str, seed: int) -> dict:
    spec = spec_of(case)
    run = generate(spec, seed=seed)
    log: list = []
    row = sd.run_spec(spec, case, estimator, seed, run=run, log=log)
    if parse(case)[1] == "nominal":
        row.update(tails(log))
    for key in log[0][1] if log else ():  # each tower test's median threshold (F) when it ran
        thr = [rep[key][1] for _, rep in log if rep.get(key) is not None]
        row[f"tower_test_{key}_thr_med"] = float(np.median(thr)) if thr else math.nan
    if estimator in ("ekf", "ekf-calibrated"):  # what is heard does not depend on the estimator
        row["masts_10s"] = masts_per_window(run, spec, hs.masts())
    return row


def estimators(calibrated: bool) -> tuple[str, ...]:
    return PLAIN + CALIBRATED if calibrated else PLAIN


def plan(seeds: int, stress_seeds: int = 0, calibrated: bool = False, first: int = 0) -> list:
    """Every (case, estimator, seed); seeds from `first` (0: the reported seeds; 100: the
    tuning seeds, for development runs written elsewhere)."""
    ests = estimators(calibrated)
    tasks = [(case_id(n, e), est, s) for n in CARRIERS for e in ENTRIES for est in ests
             for s in range(first, first + seeds)]  # fmt: skip
    tasks += [(c, est, s) for c in STRESS for est in PLAIN
              for s in range(first, first + stress_seeds)]  # fmt: skip
    return tasks


# --- summary -------------------------------------------------------------------------------------
def masts(runs, n: int) -> float:
    """Median over seeds and entries of each run's median masts per 10 s (main table cases)."""
    main = {case_id(n, e) for e in ENTRIES}
    return sd._med([r.get("masts_10s", math.nan) for r in runs if r["case"] in main])


def false_alarms(runs, case: str, est: str) -> dict:
    """False alarms on one case: mean per hour, and the seeds with one."""
    rs = sd._rows(runs, case, est)
    return {
        "fa_h": sd._mean([r["false_alarms_per_h"] for r in rs]),
        "seeds": sorted(r["seed"] for r in rs if r["false_alarms_per_h"] > 0),
        "n": len(rs),
    }


def added_false_alarms(runs, cases: list[str], mon: str, base: str) -> tuple[list, int]:
    """(entry, seed) pairs where the monitor variant has more false alarms than the unchanged
    filter on the same seed, and how many pairs were compared."""
    out, pairs = [], 0
    for case in cases:
        b = {r["seed"]: r["false_alarms_per_h"] for r in sd._rows(runs, case, base)}
        for r in sd._rows(runs, case, mon):
            if r["seed"] not in b:
                continue
            pairs += 1
            if r["false_alarms_per_h"] > b[r["seed"]]:
                out.append((parse(case)[1], r["seed"]))
    return out, pairs


def cell(runs, attack: str, clean: list[str], est: str) -> dict:
    """Detection on the `attack` case and false alarms on the `clean` cases, for `est`."""
    rs = sd._rows(runs, attack, est)
    d = sd.detection(rs)
    d["hazardous_seeds"] = sum(r["hazardous_epochs"] > 0 for r in rs)
    d["fa"] = {parse(c)[1]: false_alarms(runs, c, est) for c in clean}
    base = BASE.get(est)
    d["added_fa"] = added_false_alarms(runs, clean, est, base) if base else None
    d["opinion"] = opinion(rs)
    d["sigma"] = {k: sd._med([r.get(f"tower_test_{k}_sigma_med_m", math.nan) for r in rs])
                  for k in ("30/10", "120/20")}  # fmt: skip
    d["thr"] = {k: sd._med([r.get(f"tower_test_{k}_thr_med", math.nan) for r in rs])
                for k in ("30/10", "120/20")}  # fmt: skip
    return d


def main_cell(runs, n: int, est: str) -> dict:
    return cell(runs, case_id(n, "spoof-ramp"), [case_id(n, "nominal"), case_id(n, "outage")], est)


def opinion(rs) -> str:
    """Median over runs of the share of seconds each tower test had an opinion (at least
    `min_sites` sites kept in both windows); '–' for an estimator without the monitor."""
    keys = sorted({k for r in rs for k in r if k.endswith("_opinion_share")})
    if not keys:
        return "–"
    keys.sort(key=lambda k: float(k.split("_")[2].split("/")[0]))
    return ", ".join(
        f"{k.split('_')[2]} s: {sd._f(100 * sd._med([r.get(k, math.nan) for r in rs]), 0)} %"
        for k in keys
    )


def _added(a) -> str:
    if a is None:
        return "–"
    pairs, n = a
    if not n:
        return "–"
    if not pairs:
        return f"0 of {n}"
    return f"**{len(pairs)} of {n}**: " + ", ".join(f"{e} {s}" for e, s in pairs)


def _seeds(s: list[int]) -> str:
    if not s:
        return "0"
    return f"{len(s)}: seed {', '.join(map(str, s))}" if len(s) <= 5 else str(len(s))


KEYS = ("detect_delay_s", "false_alarms_per_h", "hazardous_epochs", "misleading_epochs")


def same_as_before(runs, n: int, est: str = "ekf-spoof", before: str = BEFORE) -> tuple[int, int]:
    """(runs identical, runs compared) between `est` and `before` on the n-carrier cases: the
    scored metrics and every tower test's opinion share and sigma, seed by seed."""
    key = {(r["case"], r["estimator"], r["seed"]): r for r in runs}
    same = total = 0
    for (case, e, seed), r in key.items():
        b = key.get((case, before, seed))
        if e != est or b is None or parse(case)[0] != n or case not in _main_cases():
            continue
        total += 1
        ks = set(KEYS) | {k for k in (*r, *b) if k.startswith("tower_test_")}
        same += all(_eq(r.get(k), b.get(k)) for k in ks)
    return same, total


def _main_cases() -> set[str]:
    return {case_id(n, e) for n in CARRIERS for e in ENTRIES}


def _eq(a, b) -> bool:
    nan = lambda x: isinstance(x, float) and math.isnan(x)  # noqa: E731
    return (nan(a) and nan(b)) or a == b


def verdict(runs, seeds: int) -> list[str]:
    now = main_cell(runs, 13, "ekf-spoof")
    before = main_cell(runs, 13, BEFORE)
    added = (now["added_fa"] or ([], 0))[0]
    met = now["detected"] >= SUCCESS * seeds / 50 and not added
    lines = [
        f"- **#221's criterion (`ekf-spoof` flags the ramp on >= {SUCCESS} of 50 seeds on the "
        f"13-carrier leg, 0 added false alarms): {'met' if met else 'not met'}.** "
        f"{now['detected']} of {now['n']} seeds (rule before #258: {before['detected']} of "
        f"{before['n']}), {len(added)} added false alarms in "
        f"{(now['added_fa'] or ([], 0))[1]} paired `nominal`/`outage` runs.",
    ]
    move = RAMP_MPS * TTA_TARGET_S
    s30, thr30 = now["sigma"]["30/10"], now["thr"]["30/10"]
    met30 = not math.isnan(now["tta_max"]) and now["tta_max"] <= TTA_TARGET_S
    lines.append(
        f"- **Time to alert against T4's {TTA_TARGET_S:.0f} s (`TBC`): "
        f"{'met' if met30 else 'not met'}.** 13 carriers, `ekf-spoof`: median "
        f"{sd._f(now['tta_med'], 0)} s, worst {sd._f(now['tta_max'], 0)} s. In "
        f"{TTA_TARGET_S:.0f} s the ramp moves the fix {move:.0f} m; the 30 s-lag test's own "
        f"1-sigma on that move is {sd._f(s30, 0)} m (worst axis, median over the ramp runs' "
        f"seconds and seeds), so {move:.0f} m is {move / s30:.1f} sigma, while its threshold "
        f"(F = {sd._f(thr30, 1)}, median) needs about {math.sqrt(2 * thr30):.1f} sigma along "
        "one axis. On hopped windows the fit also sees only part of the move (the epoch term "
        f"takes the mean of the few sites on air). The 120 s-lag test has "
        f"{sd._f(now['sigma']['120/20'], 0)} m against the {RAMP_MPS * 120:.0f} m the ramp "
        "moves in 120 s."
        if s30 and not math.isnan(s30) and not math.isnan(thr30)
        else f"- Time to alert against T4's {TTA_TARGET_S:.0f} s (`TBC`): no tower sigma logged."
    )
    for n in (1, 6, 13):
        same, total = same_as_before(runs, n)
        if total:
            lines.append(
                f"- {n} carrier{'s' if n > 1 else ''}: `ekf-spoof` and the rule before #258 give "
                f"identical scored metrics and tower-test logs on {same} of {total} runs."
            )
    return lines


def _row(label: str, est: str, d: dict, clean: list[str]) -> str:
    fa = "; ".join(
        f"{e} {sd._f(d['fa'][e]['fa_h'], 2)} ({_seeds(d['fa'][e]['seeds'])})" for e in clean
    )
    return (
        f"| {label} | `{est}` | {d['detected']}/{d['n']} | {sd._f(d['tta_med'], 0)} | "
        f"{sd._f(d['tta_max'], 0)} | {sd._f(d['err_at_alert'])} | {sd._f(d['hazardous'])} "
        f"({d['hazardous_seeds']}) | {fa or '–'} | {_added(d['added_fa'])} | {d['opinion']} |"
    )


def stress_lines(runs) -> list[str]:
    present = {r["case"] for r in runs}
    cases = [c for c in STRESS if c in present]
    if not cases:
        return []
    seeds = [r["seed"] for r in runs if r["case"] in cases]
    lines = [
        "",
        f"## Stress cases, seeds {min(seeds)}–{max(seeds)}",
        "",
        "13 carriers unless named. `@1`, `@0.5`: the ramp at 1 and 0.5 m/s (from 150 s, 45°). "
        "`/dwell2`: 2 s dwells (26 s hop cycle, 2 records per dwell). `spoof-jump`: the 300 m "
        "jump at 150 s, held to the end (the filter's own gate flags it; the monitor must not "
        "lose that). Six carriers and the outage entry are in the table above, on 50 seeds.",
        "",
        "| Case | Estimator | Detected | TTA median (s) | TTA worst (s) | Error at alert (m) | "
        "Hazardous epochs, mean (seeds) | False alarms / h (seeds) | Added false alarms | "
        "Monitor has an opinion |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        entry = parse(case)[1]
        clean = entry == "nominal"
        for est in PLAIN:
            if not sd._rows(runs, case, est):
                continue
            d = cell(runs, "" if clean else case, [case] if clean else [], est)
            if clean:  # no attack: detection columns stay empty
                d["opinion"] = opinion(sd._rows(runs, case, est))
            lines.append(_row(f"`{case}`", est, d, [entry] if clean else []))
    return lines


def calibration(runs, n: int, est: str = "ekf-spoof") -> str | None:
    """Share of the tower tests on the n-carrier `nominal` runs whose p-value is under each of
    `TAIL_P` (pooled over runs and seconds), per test; None without such rows."""
    rs = sd._rows(runs, case_id(n, "nominal"), est)
    keys = sorted({k[:-6] for r in rs for k in r if k.endswith("_tests")},
                  key=lambda k: float(k.split("_")[2].split("/")[0]))  # fmt: skip
    parts = []
    for k in keys:
        tests = sum(r.get(f"{k}_tests", 0) or 0 for r in rs)
        if not tests:
            continue
        shares = [sum(r.get(f"{k}_p_lt_{a:g}", 0) or 0 for r in rs) / tests for a in TAIL_P]
        parts.append(f"{k.split('_')[2]} s ({tests:,} tests): "
                     + ", ".join(f"{100 * x:.2f} % under {a:g}" for x, a in
                                 zip(shares, TAIL_P, strict=True)))  # fmt: skip
    return "; ".join(parts) or None


def summary(data: dict) -> str:
    runs, meta = data["runs"], data["meta"]
    n_seeds, first = meta["seeds"], meta.get("first_seed", 0)
    ests = [e for e in (*PLAIN, *CALIBRATED) if any(r["estimator"] == e for r in runs)]
    lines = [
        "# Slow GNSS drag with carrier hopping: the tower monitor against masts heard "
        "(#221, #258)",
        "",
        f"Sim, study leg (ADR-0040: the payload cannot hop yet), every value `TBC`. Commit "
        f"{meta['commit']}, `{meta['command']}`, {meta['minutes']:.1f} min on {meta['host']}. "
        f"Seeds {first}–{first + n_seeds - 1}, paired. The monitor's settings are as committed "
        "(ADR-0037, chosen on seeds 100–109 of the many-tower case); the site rule for hopped "
        "carriers (ADR-0037 amendment, #258) was checked on seeds 100–109 of this leg, not on "
        "these.",
        "",
        "Entries `spoof-ramp` (2 m/s at 45°, from 150 s), `nominal` and `outage` of "
        "`challenge-drone` (1 carrier, EARFCN 2460) and `challenge-drone-hop` (the first 6 "
        "carriers of its hop set, and all 13), as committed. `ekf-spoof` is `ekf` with the "
        "opt-in tower monitor as committed; `ekf-every-epoch-spoof` is the same with the site "
        "rule before #258 (a site counts if heard on half of every epoch of a window; this "
        "study only). Detection and false alarms are `pnt.metrics` "
        "(`analysis/spoof_detection.py`'s rows). Masts: distinct masts heard per 10 s after the "
        "cell lookup, median over seeds of each run's median.",
        "",
        *verdict(runs, n_seeds),
        *[
            f"- Test calibration, {n} carriers, `nominal`, `ekf-spoof`: {c}. A calibrated "
            "F-test puts 10 %, 1 % and 0.1 % of its tests there; the seconds are correlated, so "
            "these are a shape check, not a false-alarm rate."
            for n in CARRIERS[1:]
            if (c := calibration(runs, n))
        ],
        "",
        "| Carriers (masts per 10 s) | Estimator | Ramp detected | TTA median (s) | "
        "TTA worst (s) | Error at alert (m) | Hazardous epochs on the ramp, mean (seeds) | "
        "False alarms / h (seeds) | Added false alarms (paired runs) | "
        "Monitor has an opinion (ramp, median share of s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for n in CARRIERS:
        for est in ests:
            d = main_cell(runs, n, est)
            if d["n"]:
                label = f"{n} ({sd._f(masts(runs, n), 1)})"
                lines.append(_row(label, est, d, ["nominal", "outage"]))
    lines += stress_lines(runs)
    notes = sd.during_alarm([r for r in runs if parse(r["case"])[1] == "spoof-ramp"])
    lines += [
        "",
        "TTA: time to alert from the attack's start, detected seeds only. Error at alert: "
        "horizontal error at the alert, median over detected seeds. Hazardous: epochs whose "
        "error exceeds the alert limit (`pnt.metrics`). False alarms on `nominal` and `outage`: "
        "mean per hour over seeds, and the seeds with any. Added false alarms: (entry, seed) "
        "pairs where the monitor variant has more false alarms than the same filter without it "
        "on the same seed, of the pairs compared. Opinion: share of seconds a tower test "
        "(lag/window) had at least `min_sites` sites kept (`spoof_detection.py`'s per-run "
        "share), median over the attack runs.",
        *notes,
        "",
    ]
    return "\n".join(lines)


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs, meta = data["runs"], data["meta"]
    plt.rcParams.update({"font.size": 15})
    xs = {n: masts(runs, n) for n in CARRIERS}
    x = [xs[n] for n in CARRIERS]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 7.5), dpi=100)
    ests = [e for e in (*PLAIN, *CALIBRATED) if any(r["estimator"] == e for r in runs)]
    ends = []  # (y at the last point, label, colour, bold)
    drawn = False  # any time to alert drawn
    for k, est in enumerate(ests):
        colour = COLOURS[est]
        cal = est in CALIBRATED
        now = est.endswith("-spoof") and est != BEFORE and est != CALIBRATED[1]
        d = [main_cell(runs, n, est) for n in CARRIERS]
        share = [100.0 * c["detected"] / c["n"] if c["n"] else np.nan for c in d]
        style = dict(color=colour, lw=3 if now else 2, ls="-" if now else "--",
                     ms=13 if now else 9, marker="s" if cal else "o",
                     mfc=colour if now else "white", mew=2.5, zorder=3 if now else 2)  # fmt: skip
        label = ("ekf-calibrated, " if cal else "") + LABELS[PLAIN[CALIBRATED.index(est)] if cal
                                                            else est]  # fmt: skip
        a1.plot(x, share, **style)
        ends.append((share[-1], label, colour, now))
        # time to alert: markers only (a median over few seeds is not a trend), dodged so
        # equal values stay visible, each with the seeds it is over
        dodge = (k - (len(ests) - 1) / 2) * 0.03 * max(x)
        for xi, c in zip(x, d, strict=True):
            if math.isnan(c["tta_med"]):
                continue
            xd = xi + dodge
            a2.vlines(xd, c["tta_med"], c["tta_max"], color=colour, lw=2, alpha=0.6)
            a2.plot(xd, c["tta_max"], "_", color=colour, ms=16, mew=2.5)
            a2.plot(xd, c["tta_med"], **{**style, "ls": "none"})
            a2.annotate(f"{c['detected']}/{c['n']}", (xd, c["tta_med"]),
                        xytext=(0, -24 - 16 * k), textcoords="offset points",
                        ha="center", color=colour, fontsize=12)  # fmt: skip
            drawn = True
    # direct labels right of the last point, pushed apart so equal values stay legible
    placed: list[float] = []
    for y, label, colour, now in sorted(ends, key=lambda e: e[0]):
        y = max([y] + [p + 9.0 for p in placed])
        placed.append(y)
        a1.text(x[-1] * 1.04, y, label, color=colour, fontsize=13, va="center",
                fontweight="bold" if now else "normal")  # fmt: skip
    a2.text(0.98, 0.97, "colours as left;\nn/50: seeds the median is over",
            transform=a2.transAxes, ha="right", va="top", color=INK, fontsize=12)  # fmt: skip
    if not drawn:
        a2.text(0.5, 0.55, "no seed flagged the ramp:\nno time to alert to show",
                transform=a2.transAxes, ha="center", va="center", color=INK,
                fontsize=15)  # fmt: skip
    a1.axhline(100.0 * SUCCESS / 50, color=INK, lw=1.5, ls=":")
    a1.text(0.5, 100.0 * SUCCESS / 50 + 2, f"#221 target {SUCCESS} of 50", color=INK, fontsize=13)
    a1.set_ylim(-3, 108)
    a1.set_ylabel("ramp seeds detected (%)")
    a1.set_title("Share of seeds that flag the 2 m/s ramp", loc="left", fontsize=16, pad=40)
    a2.axhline(TTA_TARGET_S, color=INK, lw=1.5, ls=":")
    a2.text(0.5, TTA_TARGET_S * 1.12, f"T4 target {TTA_TARGET_S:.0f} s (TBC)", color=INK,
            fontsize=13)  # fmt: skip
    a2.set_yscale("log")
    a2.set_ylim(10, 1000)
    a2.set_ylabel("time to alert (s): median dot, worst tick")
    a2.set_title("Time to alert, detected seeds only", loc="left", fontsize=16, pad=40)
    right = max(xs.values()) * 1.9
    for ax in (a1, a2):
        ax.set_xlim(0, right)
        ax.set_xlabel("masts heard per 10 s (median over seeds)")
        ax.grid(True, color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        top = ax.secondary_xaxis("top")  # carriers hopped, at their masts heard
        top.set_xticks(x, [str(n) for n in CARRIERS], fontsize=13, color=INK)
        top.set_xlabel("LTE carriers hopped", fontsize=13, color=INK)
        top.tick_params(length=0)
        top.spines["top"].set_visible(False)
    fig.suptitle(
        "Slow GNSS drag (2 m/s) against masts heard, 1 / 6 / 13 LTE carriers hopped, the tower "
        "monitor's site rule before and after #258:\nchallenge-drone(-hop) spoof-ramp; seeds "
        f"{meta.get('first_seed', 0)}–{meta.get('first_seed', 0) + meta['seeds'] - 1}, "
        f"{meta['commit']} (sim, study leg, every value TBC)",
        fontsize=15,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.9))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def write(data: dict, out_dir: Path) -> None:
    (out_dir / "summary.md").write_text(summary(data))
    plot(data, out_dir / "detection_vs_masts.png")
    print(f"wrote {out_dir / 'summary.md'}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--stress-seeds", type=int, default=10)
    p.add_argument("--first-seed", type=int, default=0, help="100: tuning seeds (use --out)")
    p.add_argument("--calibrated", action="store_true", help="also the ekf-calibrated trio")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--out", default=str(OUT), help="summary.md and detection_vs_masts.png")
    p.add_argument("--runs", default=str(RUNS), help="per-run rows (git-ignored by default)")
    p.add_argument("--redraw", action="store_true", help="rebuild from the runs file")
    a = p.parse_args(argv)
    out_dir, runs_path = Path(a.out), Path(a.runs)
    commit = _commit()
    # REQ-10: the committed results name a commit they can be regenerated from
    if out_dir.resolve() == OUT.resolve() and a.first_seed != 0:
        raise SystemExit("the committed results are the reported seeds 0 to N-1 (use --out)")
    if not a.redraw and out_dir.resolve() == OUT.resolve() and not sd.clean_commit(commit):
        raise SystemExit(
            f"tree is {commit}: commit first, the committed results must name a clean commit "
            "(or write elsewhere with --out)"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if not a.redraw:
        tasks = plan(a.seeds, a.stress_seeds, a.calibrated, a.first_seed)
        print(f"{len(tasks)} runs on {a.jobs} workers")
        t0 = time.time()
        runs = _map(run_one, tasks, a.jobs)
        cal = " --calibrated" if a.calibrated else ""
        cal += f" --first-seed {a.first_seed}" if a.first_seed else ""
        meta = {
            "commit": commit,
            "command": f"python analysis/drag_with_hopping.py --seeds {a.seeds} "
            f"--stress-seeds {a.stress_seeds}{cal} --jobs {a.jobs}",
            "seeds": a.seeds,
            "first_seed": a.first_seed,
            "minutes": (time.time() - t0) / 60.0,
            "host": sd.host(),
        }
        sd.save_runs({"meta": meta, "runs": runs}, runs_path)
    write(sd.load_runs(runs_path), out_dir)


if __name__ == "__main__":
    main()
