"""Scoring estimates against truth: the numbers that go into systems/verification.md."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from pnt.core.measurement import Estimate, Truth
from pnt.core.time import s_to_ns

ALARM_FLAGS = {"gnss_excluded", "spoof_suspected"}
# TBC: how long an alarm must persist to count, so one noisy GNSS rejection is not a detection.
# REQ-04's false-alarm target sets the real value.
ALARM_HOLD_S = 1.0


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
        start = t0_ns + s_to_ns(f["start_s"])
        end = t0_ns + s_to_ns(f["end_s"]) if "end_s" in f else t[-1] + 1
        in_fault |= (t >= start) & (t < end)
        if f["type"] == "spoof_ramp":
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
    )


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
    out["runs"] = len(runs)
    return out
