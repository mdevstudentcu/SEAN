"""Scoring estimates against truth: the numbers that go into systems/verification.md."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from pnt.core.measurement import Estimate, Truth
from pnt.core.time import s_to_ns
from pnt.integrity.protection import tpl
from pnt.integrity.taxonomy import POSITION, TIME, classify

SPOOF_ATTACKS = {"spoof_ramp", "spoof_jump", "meaconing", "time_spoof"}
ALARM_FLAGS = {"gnss_excluded", "spoof_suspected", "time_spoof_suspected"}
# TBC: how long an alarm must persist to count, so one noisy GNSS rejection is not a detection.
# REQ-04's false-alarm target sets the real value.
ALARM_HOLD_S = 1.0
# Anything that tells the operator something is wrong, for time-to-alert: the alarms above, GNSS
# reported unavailable, or the estimator declaring itself unsafe (protection level over its AL).
ALERT_FLAGS = ALARM_FLAGS | {"gnss_unavailable"}

# TBC: REQ-01/REQ-02 targets set the real position alert limit (same placeholder as the
# estimators and the Stanford plot).
ALERT_LIMIT_M = 50.0
# TBC: REQ-03's target sets the real time alert limit. 1.5 us is the LTE-TDD base-station
# synchronisation budget (a patent-text figure, not 3GPP text), the tightest common user of GPS
# time we can serve.
TIME_ALERT_LIMIT_S = 1.5e-6

# Resilience level, our mapping onto the DHS S&T Resilient PNT Conformance Framework (Dec 2020,
# v2.0 2022). Its levels are cumulative: 1 recovers once the threat is removed, 2 keeps giving a
# solution during the threat (degradation may be unbounded), 3 keeps the degradation bounded,
# 4 operates through the threat without degradation. The framework is outcome-based and gives no
# numbers, so the thresholds below are ours (TBC). Our level 2 is stricter than DHS's: it asks for
# no hazardously misleading epoch during the threat, not only for a solution, because a confident
# wrong answer is the aviation hazard (decided 2026-11-09).
RECOVERY_SETTLE_S = 30.0  # TBC: time allowed after the fault ends before recovery is judged
NO_DEGRADATION_RATIO = 1.5  # TBC: fault-window p95 within this factor of the pre-fault p95

# Outage slices (issue #128). T1 and T3 (systems/plan.md, TBC) are stated from GPS loss, so the
# report card scores fixed lengths of time after it and outages of different lengths compare.
# GPS loss: the start of the first fault that removes GNSS position from the estimator, an
# `outage` of source gnss or a `gps_no_fix` (both drop the position readings, sim/attacks.py).
# A `jamming_zone` also does, but by place, with no start time, so it has no slices.
OUTAGE_SLICES_S = (60, 120, 300)  # s after GPS loss (TBC); 300 is T1's
T1_AFTER_S = 300.0  # s: T1's "for >= 300 s after GPS loss" (TBC), also the HPL bound slice
T3_AFTER_S = 600.0  # s: T3's "after 10 min without GPS" (TBC)
T3_WINDOW_S = 10.0  # TBC: the time error at 600 s is the p95 over the 10 s ending there


@dataclass
class RunMetrics:
    n: int
    h_rmse_m: float
    h_p95_m: float
    h_max_m: float
    fault_h_p95_m: float  # inside the fault window (nan if no fault)
    fault_h_max_m: float
    hpl_bound_frac: float  # fraction of epochs where HPL >= true horizontal error
    misleading_epochs: int  # error > HPL while status != "unsafe": the dangerous case
    detect_delay_s: float  # first sustained alarm after a spoof starts (nan if none)
    spoof_detected: float  # 1 detected, 0 missed, nan if the scenario has no spoof
    false_alarms_per_h: float  # sustained alarms outside spoof windows (nan if no such time)
    h_nees_mean: float  # horizontal NEES; about 2 if the covariance is honest, above is optimistic
    time_err_p95_us: float  # |clock error| against truth (nan if the clock is not estimated)
    fault_time_err_p95_us: float  # same, inside the fault window
    time_1sigma_bound_frac: float  # fraction of epochs where clock_sigma_s >= |clock error|
    # Report card (I5, I6). Each "misleading" count includes the hazardous ones.
    hazardous_epochs: int  # error > alert limit while HPL <= it: hazardously misleading
    time_pl_bound_frac: float  # fraction of clock epochs where the time PL >= |clock error|
    time_misleading_epochs: int  # |clock error| > time PL while time PL <= time alert limit
    time_hazardous_epochs: int  # |clock error| > time alert limit while time PL <= it
    time_to_alert_s: float  # first alert at or after a fault starts (nan if none or no fault)
    alerted: float  # 1 alert raised, 0 missed, nan if no fault that should raise one
    resilience_level: float  # 0-4, our mapping of the DHS/CISA levels: the worse of the two below
    pos_resilience_level: float  # judged if a fault corrupts position (nan if none does)
    time_resilience_level: (
        float  # judged if a fault corrupts time; 0 if the clock is not estimated
    )
    recovery_tested: float  # 1 if the run has time after the fault ends, 0 if not, nan no fault
    # Outage slices (T1, T3), from GPS loss (see OUTAGE_SLICES_S). Each is nan if the scenario
    # has no GPS loss, or if the outage or the run ends before the slice does.
    outage_h_p95_60s_m: float  # p95 horizontal error over the first 60 s after GPS loss
    outage_h_p95_120s_m: float  # same, first 120 s
    outage_h_p95_300s_m: float  # same, first 300 s (T1)
    outage_hpl_bound_300s: float  # fraction of the first 300 s where HPL >= horizontal error
    outage_time_err_600s_us: float  # |clock error| at 600 s (T3), also nan if no clock
    outage_time_sigma_bound_600s: float  # fraction of the first 600 s: clock sigma >= error

    def as_dict(self) -> dict:
        return asdict(self)


def _alarm_times(t: np.ndarray, alarm: np.ndarray, hold_ns: int) -> list[int]:
    """Time each run of consecutive alarmed epochs first reaches `hold_ns` in length."""
    out: list[int] = []
    start = None
    confirmed = False
    for ti, a in zip(t, alarm, strict=True):
        if not a:
            start, confirmed = None, False
            continue
        if start is None:
            start = ti
        if not confirmed and ti - start >= hold_ns:
            out.append(int(ti))
            confirmed = True
    return out


def _p95(x: np.ndarray) -> float:
    return float(np.percentile(x, 95)) if x.size else float("nan")


def first_alert_s(t: np.ndarray, alert: np.ndarray, start_ns: int, end_ns: int) -> float:
    """Seconds from `start_ns` to the first epoch in [start, end) where an alert starts.

    An alert already running before the fault started is not a response to it, so only epochs
    where the alert switches on count. nan if none does."""
    prev = np.r_[False, alert[:-1]]
    hit = np.flatnonzero(alert & ~prev & (t >= start_ns) & (t < end_ns))
    return (t[hit[0]] - start_ns) / 1e9 if hit.size else float("nan")


def resilience_level(recovered: bool, no_hazard: bool, bounded: bool, undegraded: bool) -> int:
    """Highest level whose criteria and every lower level's hold (the levels are cumulative).

    Our mapping (TBC), per run, for each part of the solution (position, time) a fault corrupts:
    1 recovered: after the fault ends and RECOVERY_SETTLE_S, p95 error is within the alert limit
    2 respond: during the fault, no hazardously misleading epoch (error over the alert limit
      while the protection level claims it is within)
    3 bounded: during the fault, error never exceeds the alert limit
    4 no degradation: fault-window p95 error within NO_DEGRADATION_RATIO of the pre-fault p95
    0 if not even level 1 holds."""
    level = 0
    for ok in (recovered, no_hazard, bounded, undegraded):
        if not ok:
            break
        level += 1
    return level


def _part_level(x, limit, hazardous, exists, in_fault, before, settled) -> float:
    """Resilience level of one part of the solution (position or time): `x` its error,
    `hazardous` its hazardously misleading epochs, `exists` where it is estimated at all."""
    fw = in_fault & exists
    if not fw.any():  # e.g. a time fault on an estimator with no clock: no solution to judge
        return 0.0
    pre = before & exists
    return float(
        resilience_level(
            # Not exercised when the fault never ends: then recovery is not held against it
            recovered=not settled.any() or _p95(x[settled & exists]) <= limit,
            no_hazard=not hazardous[fw].any(),
            bounded=bool(x[fw].max() <= limit),
            undegraded=bool(pre.any() and _p95(x[fw]) <= NO_DEGRADATION_RATIO * _p95(x[pre])),
        )
    )


def gps_loss(spec: dict, t0_ns: int) -> tuple[int, int | None] | None:
    """(start, end) of the first fault that removes GNSS position, end None if it never ends;
    None if the scenario has no such fault."""
    losses = [
        f
        for f in spec.get("faults", [])
        if f["type"] == "gps_no_fix"
        or (f["type"] == "outage" and f.get("source", "gnss") == "gnss")
    ]
    if not losses:
        return None
    f = min(losses, key=lambda f: f.get("start_s", 0.0))
    return (
        t0_ns + s_to_ns(f.get("start_s", 0.0)),
        t0_ns + s_to_ns(f["end_s"]) if "end_s" in f else None,
    )


def _outage_slices(t, err, hpl, clock_err, clock_sigma, has_clock, spec, t0_ns) -> dict:
    """The outage-slice fields of RunMetrics (see OUTAGE_SLICES_S)."""
    slices = {f"outage_h_p95_{s}s_m": s for s in OUTAGE_SLICES_S}
    bounds = ["outage_hpl_bound_300s", "outage_time_err_600s_us", "outage_time_sigma_bound_600s"]
    out = dict.fromkeys([*slices, *bounds], float("nan"))
    loss = gps_loss(spec, t0_ns)
    if loss is None:
        return out
    start, end = loss
    # The run lasts until one epoch after its last one: epochs every 0.1 s from 0 to 359.9 s
    # cover a 360 s run, so a 300 s outage from 60 s gets a 300 s slice.
    run_end = int(t[-1] + (np.median(np.diff(t)) if len(t) > 1 else 0))
    end = run_end if end is None else min(end, run_end)

    def window(a_s: float, b_s: float) -> np.ndarray | None:
        """Epochs in [loss + a, loss + b), or None if the outage or the run ends before b."""
        if start + s_to_ns(b_s) > end:
            return None
        return (t >= start + s_to_ns(a_s)) & (t < start + s_to_ns(b_s))

    for name, length in slices.items():
        w = window(0.0, length)
        if w is not None:
            out[name] = _p95(err[w])
    w = window(0.0, T1_AFTER_S)
    if w is not None and w.any():
        out["outage_hpl_bound_300s"] = float(np.mean(hpl[w] >= err[w]))
    w = window(T3_AFTER_S - T3_WINDOW_S, T3_AFTER_S)
    if w is not None:
        out["outage_time_err_600s_us"] = _p95(clock_err[w & has_clock]) * 1e6
    w = window(0.0, T3_AFTER_S)
    if w is not None and (w & has_clock).any():
        c = w & has_clock
        out["outage_time_sigma_bound_600s"] = float(np.mean(clock_sigma[c] >= clock_err[c]))
    return out


def score(estimates: list[Estimate], truth: list[Truth], spec: dict, t0_ns: int) -> RunMetrics:
    tmap = {t.t_ns: t for t in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    if not pairs:
        raise ValueError("no estimates line up with truth epochs")
    t = np.array([e.t_ns for e, _ in pairs])
    err_h = np.array([np.subtract(e.pos_enu, g.pos_enu)[:2] for e, g in pairs])
    err = np.hypot(err_h[:, 0], err_h[:, 1])
    hpl = np.array([e.hpl_m for e, _ in pairs])
    unsafe = np.array([e.status == "unsafe" for e, _ in pairs])
    cov_h = np.array([np.reshape(e.pos_cov, (3, 3))[:2, :2] for e, _ in pairs])
    nees = np.einsum("ij,ij->i", err_h, np.linalg.solve(cov_h, err_h[..., None])[..., 0])

    in_fault = np.zeros(len(t), bool)
    in_spoof = np.zeros(len(t), bool)
    spoof_windows: list[tuple[int, int]] = []
    for f in spec.get("faults", []):
        start = t0_ns + s_to_ns(f.get("start_s", 0.0))
        end = t0_ns + s_to_ns(f["end_s"]) if "end_s" in f else t[-1] + 1
        in_fault |= (t >= start) & (t < end)
        if f["type"] in SPOOF_ATTACKS:
            in_spoof |= (t >= start) & (t < end)
            spoof_windows.append((start, end))

    alarm = np.array([bool(ALARM_FLAGS & set(e.flags)) for e, _ in pairs])
    alarms = _alarm_times(t, alarm, s_to_ns(ALARM_HOLD_S))
    delays = [(a - s) / 1e9 for a in alarms for s, e in spoof_windows if s <= a < e]
    n_false = sum(not any(s <= a < e for s, e in spoof_windows) for a in alarms)
    clean_hours = float(np.sum(np.diff(t)[~in_spoof[1:]])) / 3.6e12

    has_clock = np.array([e.clock_sigma_s is not None for e, _ in pairs])
    clock_err = np.array([abs(e.clock_bias_s - g.clock_bias_s) for e, g in pairs])
    clock_sigma = np.array([e.clock_sigma_s or 0.0 for e, _ in pairs])

    # Report card (I5, I6)
    al, tal = ALERT_LIMIT_M, TIME_ALERT_LIMIT_S
    hazardous = (err > al) & (hpl <= al)
    time_pl = np.array([tpl(e.clock_sigma_s) or 0.0 for e, _ in pairs])
    t_avail = has_clock & (time_pl <= tal)
    t_misleading = t_avail & (clock_err > time_pl)
    t_hazardous = t_avail & (clock_err > tal)

    faults = spec.get("faults", [])
    alert = alert_epochs(e for e, _ in pairs)
    ttas, alertable = [], False
    for f in faults:
        fc = classify(f)
        if not fc.expect_alert or fc.spatial:
            continue
        alertable = True
        start = t0_ns + s_to_ns(f.get("start_s", 0.0))
        end = t0_ns + s_to_ns(f["end_s"]) if "end_s" in f else t[-1] + 1
        ttas.append(first_alert_s(t, alert, start, end))
    tta = float(np.nanmin(ttas)) if ttas and not np.all(np.isnan(ttas)) else float("nan")

    levels = {POSITION: float("nan"), TIME: float("nan")}
    recovery_tested = float("nan")
    if faults:
        affects = {a for f in faults for a in classify(f).affects}
        first = min(t0_ns + s_to_ns(f.get("start_s", 0.0)) for f in faults)
        ends = [t0_ns + s_to_ns(f["end_s"]) for f in faults if "end_s" in f]
        settled = (
            t >= max(ends) + s_to_ns(RECOVERY_SETTLE_S)
            if len(ends) == len(faults)
            else np.zeros(len(t), bool)
        )
        recovery_tested = float(settled.any())
        windows = (in_fault, t < first, settled)
        if POSITION in affects:
            levels[POSITION] = _part_level(err, al, hazardous, np.ones(len(t), bool), *windows)
        if TIME in affects:
            levels[TIME] = _part_level(clock_err, tal, t_hazardous, has_clock, *windows)
    judged = [v for v in levels.values() if not np.isnan(v)]

    fe = err[in_fault]
    return RunMetrics(
        n=len(err),
        h_rmse_m=float(np.sqrt(np.mean(err**2))),
        h_p95_m=float(np.percentile(err, 95)),
        h_max_m=float(err.max()),
        fault_h_p95_m=_p95(fe),
        fault_h_max_m=float(fe.max()) if fe.size else float("nan"),
        hpl_bound_frac=float(np.mean(hpl >= err)),
        misleading_epochs=int(np.sum((err > hpl) & ~unsafe)),
        detect_delay_s=min(delays) if delays else float("nan"),
        spoof_detected=float(bool(delays)) if spoof_windows else float("nan"),
        false_alarms_per_h=n_false / clean_hours if clean_hours > 0 else float("nan"),
        h_nees_mean=float(np.mean(nees)),
        time_err_p95_us=_p95(clock_err[has_clock]) * 1e6,
        fault_time_err_p95_us=_p95(clock_err[has_clock & in_fault]) * 1e6,
        time_1sigma_bound_frac=(
            float(np.mean(clock_sigma[has_clock] >= clock_err[has_clock]))
            if has_clock.any()
            else float("nan")
        ),
        hazardous_epochs=int(hazardous.sum()),
        time_pl_bound_frac=(
            float(np.mean(time_pl[has_clock] >= clock_err[has_clock]))
            if has_clock.any()
            else float("nan")
        ),
        time_misleading_epochs=int(t_misleading.sum()),
        time_hazardous_epochs=int(t_hazardous.sum()),
        time_to_alert_s=tta,
        alerted=float(not np.isnan(tta)) if alertable else float("nan"),
        resilience_level=min(judged) if judged else float("nan"),
        pos_resilience_level=levels[POSITION],
        time_resilience_level=levels[TIME],
        recovery_tested=recovery_tested,
        **_outage_slices(t, err, hpl, clock_err, clock_sigma, has_clock, spec, t0_ns),
    )


def alert_epochs(estimates) -> np.ndarray:
    """Per epoch: does the estimate raise any alert (an ALERT_FLAGS flag or status unsafe)?"""
    return np.array([bool(ALERT_FLAGS & set(e.flags)) or e.status == "unsafe" for e in estimates])


def summarize(runs: list[RunMetrics]) -> dict:
    """Aggregate Monte Carlo runs: mean of each metric, plus worst-case for the risky ones."""
    keys = runs[0].as_dict().keys()
    out = {}
    for k in keys:
        v = np.array([r.as_dict()[k] for r in runs], float)
        out[k] = float(np.nanmean(v)) if not np.all(np.isnan(v)) else float("nan")
    fault_max = np.array([r.fault_h_max_m for r in runs], float)
    out["worst_fault_h_max_m"] = (
        float(np.nanmax(fault_max)) if not np.all(np.isnan(fault_max)) else float("nan")
    )
    out["min_hpl_bound_frac"] = float(min(r.hpl_bound_frac for r in runs))
    # Report card: median and worst time-to-alert over the runs that alerted (`alerted` is the
    # fraction that did), worst run's time PL bound rate, and the worst run's resilience level.
    for key, src, fn in (
        ("tta_median_s", "time_to_alert_s", np.nanmedian),
        ("tta_worst_s", "time_to_alert_s", np.nanmax),
        ("min_time_pl_bound_frac", "time_pl_bound_frac", np.nanmin),
        ("resilience_level_worst", "resilience_level", np.nanmin),
        ("pos_level_worst", "pos_resilience_level", np.nanmin),
        ("time_level_worst", "time_resilience_level", np.nanmin),
    ):
        v = np.array([getattr(r, src) for r in runs], float)
        out[key] = float(fn(v)) if not np.all(np.isnan(v)) else float("nan")
    out["runs"] = len(runs)
    return out
