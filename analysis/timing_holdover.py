"""T3 (systems/plan.md, TBC): time error after 10 min without GPS, and whether the reported 1-sigma
bounds it in >= 68 % of epochs. Sim evidence on the realistic set (every model there `TBC`).

The realistic set runs 360 s, too short for T3, so this builds the case from it: the realistic
`long-outage` scenario run for 900 s with GPS lost from 300 s, giving 5 min of calibration and
10 min of holdover. Seeds 0..N-1 as `pnt eval` uses.

    python analysis/timing_holdover.py [runs] [estimator ...]
"""

from __future__ import annotations

import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from pnt.nav import estimate
from pnt.sim.scenario import generate, load

SCENARIO = "realistic-long-outage"
GPS_LOST_S, DURATION_S = 300.0, 900.0  # 10 min without GPS
T3_LIMIT_S = 1.5e-6  # TBC: REQ-03


def spec() -> dict:
    s = load(SCENARIO)
    s["duration_s"] = DURATION_S
    s["faults"] = [{"type": "outage", "source": "gnss", "start_s": GPS_LOST_S}]
    return s


def one(estimator: str, seed: int) -> tuple[float, float, float]:
    """(|time error| at the end, its reported 1-sigma, fraction of holdover epochs bounded)."""
    s = spec()
    run = generate(s, seed=seed)
    truth = {t.t_ns: t.clock_bias_s for t in run.truth}
    t0 = run.truth[0].t_ns
    err, sig = [], []
    for e in estimate(estimator, run.measurements, origin_llh=s["origin_llh"]):
        if e.t_ns in truth and e.clock_sigma_s is not None and e.t_ns - t0 >= GPS_LOST_S * 1e9:
            err.append(abs(e.clock_bias_s - truth[e.t_ns]))
            sig.append(e.clock_sigma_s)
    err, sig = np.array(err), np.array(sig)
    return float(err[-1]), float(sig[-1]), float(np.mean(sig >= err))


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    estimators = sys.argv[2:] or ["ekf", "ekf-calibrated"]
    ctx = multiprocessing.get_context("forkserver")
    print(f"{SCENARIO}, {DURATION_S:.0f} s, GPS lost from {GPS_LOST_S:.0f} s, seeds 0-{runs - 1}")
    print(
        "| estimator | end error median / p95 (us) | runs <= 1.5 us | end 1-sigma median (us) "
        "| holdover epochs bounded by 1-sigma (mean) |"
    )
    print("| --- | --- | --- | --- | --- |")
    with ProcessPoolExecutor(mp_context=ctx) as pool:
        for name in estimators:
            res = np.array(list(pool.map(one, [name] * runs, range(runs))))
            end, sig, frac = res[:, 0] * 1e6, res[:, 1] * 1e6, res[:, 2]
            print(
                f"| {name} | {np.median(end):.2f} / {np.percentile(end, 95):.2f} | "
                f"{np.mean(end <= T3_LIMIT_S * 1e6):.0%} | {np.median(sig):.2f} | "
                f"{frac.mean():.0%} |"
            )


if __name__ == "__main__":
    main()
