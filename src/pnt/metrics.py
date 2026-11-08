"""Scoring estimates against truth: the numbers that go into systems/verification.md."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from pnt.core.measurement import Estimate, Truth
from pnt.core.time import s_to_ns


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
    detect_delay_s: float  # first gnss_excluded/spoof flag after a spoof starts (nan if none)

    def as_dict(self) -> dict:
        return asdict(self)


def score(estimates: list[Estimate], truth: list[Truth], spec: dict, t0_ns: int) -> RunMetrics:
    tmap = {t.t_ns: t for t in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    if not pairs:
        raise ValueError("no estimates line up with truth epochs")
    t = np.array([e.t_ns for e, _ in pairs])
    err = np.array([np.hypot(*(np.subtract(e.pos_enu, g.pos_enu)[:2])) for e, g in pairs])
    hpl = np.array([e.hpl_m for e, _ in pairs])
    unsafe = np.array([e.status == "unsafe" for e, _ in pairs])

    in_fault = np.zeros(len(t), bool)
    detect = float("nan")
    for f in spec.get("faults", []):
        start = t0_ns + s_to_ns(f["start_s"])
        end = t0_ns + s_to_ns(f["end_s"]) if "end_s" in f else t[-1] + 1
        in_fault |= (t >= start) & (t < end)
        if f["type"] == "spoof_ramp":
            for e, _ in pairs:
                if e.t_ns >= start and {"gnss_excluded", "spoof_suspected"} & set(e.flags):
                    detect = (e.t_ns - start) / 1e9
                    break

    fe = err[in_fault]
    return RunMetrics(
        n=len(err),
        h_rmse_m=float(np.sqrt(np.mean(err**2))),
        h_p95_m=float(np.percentile(err, 95)),
        h_max_m=float(err.max()),
        fault_h_p95_m=float(np.percentile(fe, 95)) if fe.size else float("nan"),
        fault_h_max_m=float(fe.max()) if fe.size else float("nan"),
        hpl_bound_frac=float(np.mean(hpl >= err)),
        misleading_epochs=int(np.sum((err > hpl) & ~unsafe)),
        detect_delay_s=detect,
    )


def summarize(runs: list[RunMetrics]) -> dict:
    """Aggregate Monte Carlo runs: mean of each metric, plus worst-case for the risky ones."""
    keys = runs[0].as_dict().keys()
    out = {}
    for k in keys:
        v = np.array([r.as_dict()[k] for r in runs], float)
        out[k] = float(np.nanmean(v)) if not np.all(np.isnan(v)) else float("nan")
    out["worst_fault_h_max_m"] = float(np.nanmax([r.fault_h_max_m for r in runs]))
    out["min_hpl_bound_frac"] = float(min(r.hpl_bound_frac for r in runs))
    out["runs"] = len(runs)
    return out
