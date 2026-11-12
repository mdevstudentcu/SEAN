"""What a ground reference station buys inside its zone (ADR-0020), on measured noise sizes.

The committed `realistic-with-base` set puts placeholder LTE errors on the drone (50 m white,
50 m / 30 s multipath, `TBC`). This study runs the same station scenarios, same seeds, three ways:

    A  as committed (reproduces analysis/results/headline)
    B  the drone's LTE white noise at ADR-0036's proposed sim value, 10 m at 1 Hz (consequence 3:
       bounded by the measured S(1 s), median 8.1 m, 15 static captures)
    C  B, plus multipath at ADR-0036's at-rest size, 10 m / 3 s (a floor for a moving drone)

and three filters: the payload alone (`ekf`), payload + station (`ekf-base-imu`), and payload +
station + the jump guard (`ekf-base-imu` with `jump_guard=JumpGuard`, the guard `ekf-guard` uses;
not a registered estimator). Every other size is the set's. Sim only.

    python analysis/station_zones.py --runs 50 --jobs 12
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from figures import FALLBACK_M, FALLBACK_WINDOW_S, T1_M, T1_WINDOW_S, t1_statistic  # noqa: E402

from pnt.integrity.jump_guard import JumpGuard  # noqa: E402
from pnt.metrics import ALERT_LIMIT_M  # noqa: E402
from pnt.nav import base_rover, configured, estimate  # noqa: E402
from pnt.sim.scenario import T0_NS, generate, load  # noqa: E402

OUT = Path(__file__).parent / "results" / "station-zones"
SET = "realistic-with-base"
VARIANTS = {
    "A": "as committed: 50 m white, 50 m / 30 s multipath (placeholders)",
    "B": "white noise 10 m at 1 Hz (ADR-0036, measured bound); multipath as committed",
    "C": "B, plus multipath 10 m / 3 s (ADR-0036 at rest)",
}
FILTERS = {
    "payload alone": "ekf",
    "+ station": "ekf-base-imu",
    "+ station + jump guard": "base-imu-guard",
}
ATTACKS = ("long-outage", "spoof-jump")
CURVE_S = 300


def spec_of(attack: str, variant: str) -> dict:
    spec = copy.deepcopy(load(f"{SET}-{attack}"))
    lte = spec["sources"]["lte"]
    if variant in ("B", "C"):
        lte["sigma_m"] = 10.0
    if variant == "C":
        lte["multipath"] = {"sigma_m": 10.0, "tau_s": 3.0}
    return spec


def filter_fn(name: str):
    if name == "base-imu-guard":
        return configured(base_rover.run, motion="imu", jump_guard=JumpGuard)
    return name


def one(args: tuple[str, str, str, int]) -> dict:
    attack, variant, filt, seed = args
    spec = spec_of(attack, variant)
    run = generate(spec, seed=seed)
    truth = {t.t_ns: np.asarray(t.pos_enu[:2]) for t in run.truth}
    rows = [
        ((e.t_ns - T0_NS) / 1e9, float(np.linalg.norm(np.asarray(e.pos_enu[:2]) - truth[e.t_ns])),
         float(e.hpl_m) if e.hpl_m is not None else np.inf)
        for e in estimate(filter_fn(FILTERS[filt]), run.measurements,
                          origin_llh=spec["origin_llh"], reference=run.reference)
        if e.t_ns in truth
    ]  # fmt: skip
    a = np.asarray(rows, float)
    t, err, hpl = a[:, 0], a[:, 1], a[:, 2]
    start = min(f.get("start_s", 0.0) for f in spec["faults"] if f["type"] in ("outage",)
                or f["type"].startswith("spoof"))  # fmt: skip
    after = t >= start
    sec = np.floor(t[after] - start).astype(int)
    per_s = np.full(CURVE_S + 1, np.nan)
    for s in range(CURVE_S + 1):
        m = sec == s
        if m.any():
            per_s[s] = err[after][m].max()
    return {
        "attack": attack, "variant": variant, "filter": filt, "seed": seed,
        "curve": per_s.tolist(),
        "covered": float(np.mean(hpl[after] >= err[after])),
        "unavailable": float(np.mean(hpl > ALERT_LIMIT_M)),
        "hazardous": int(np.sum((err > ALERT_LIMIT_M) & (hpl <= ALERT_LIMIT_M))),
        "median_after_m": float(np.median(err[after])),
    }  # fmt: skip


def summarise(rs: list[dict]) -> dict:
    curve = np.nanpercentile(np.array([r["curve"] for r in rs], float), 95, axis=0)
    return {
        "runs": len(rs),
        "t1": t1_statistic(curve, T1_M, T1_WINDOW_S),
        "fallback": t1_statistic(curve, FALLBACK_M, FALLBACK_WINDOW_S),
        "p95_curve": curve.tolist(),
        "median_after_loss_m": float(np.median([r["median_after_m"] for r in rs])),
        "covered_worst_run": min(r["covered"] for r in rs),
        "covered_pooled": float(np.mean([r["covered"] for r in rs])),
        "unavailable": float(np.mean([r["unavailable"] for r in rs])),
        "hazardous": int(sum(r["hazardous"] for r in rs)),
        "runs_with_hazardous": int(sum(r["hazardous"] > 0 for r in rs)),
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--jobs", type=int, default=8)
    a = p.parse_args(argv)
    jobs = [(atk, v, f, s) for atk in ATTACKS for v in VARIANTS for f in FILTERS
            for s in range(a.runs)]  # fmt: skip
    with ProcessPoolExecutor(a.jobs) as pool:
        out = list(pool.map(one, jobs, chunksize=4))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                            text=True).stdout.strip()  # fmt: skip
    res = {"commit": commit, "set": SET, "runs": a.runs, "variants": VARIANTS, "filters": FILTERS,
           "results": {}}  # fmt: skip
    for atk in ATTACKS:
        for v in VARIANTS:
            for f in FILTERS:
                rs = [r for r in out if (r["attack"], r["variant"], r["filter"]) == (atk, v, f)]
                res["results"][f"{atk}|{v}|{f}"] = summarise(rs)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1))
    lines = [f"# Ground-station zones on measured noise sizes\n\nSim only. `{SET}`, seeds 0–"
             f"{a.runs - 1}, commit `{commit}`. Regenerate: `python analysis/station_zones.py "
             f"--runs {a.runs}`. Statistic: worst second of the 95th percentile across runs in "
             f"0–300 s after the fault (ADR-0034).\n"]  # fmt: skip
    for v, d in VARIANTS.items():
        lines.append(f"\n## Variant {v}: {d}\n")
        lines.append(
            "| Filter | Worst second, long outage | Median after loss | Radius covers "
            "error, worst run | Unavailable | Dangerous epochs: outage / held jump |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for f in FILTERS:
            o, j = res["results"][f"long-outage|{v}|{f}"], res["results"][f"spoof-jump|{v}|{f}"]
            lines.append(
                f"| {f} | {o['t1']['worst_p95_m']:,.0f} m | {o['median_after_loss_m']:,.0f} m | "
                f"{100 * o['covered_worst_run']:.1f} % | {100 * o['unavailable']:.1f} % | "
                f"{o['hazardous']:,} / {j['hazardous']:,} ({j['runs_with_hazardous']} runs) |"
            )
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
