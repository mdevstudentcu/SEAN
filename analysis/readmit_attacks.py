"""Does GNSS re-admission (#246, ADR-0048, `gnss_readmit`) let a spoof back in? Paired sim runs.

    python analysis/readmit_attacks.py --seeds 0-2 --jobs 3 --out <file>.json

For each attack scenario and seed, each family is run as registered (`off`) and with
`gnss_readmit=GnssReadmit` (`readmit`), on the same records. Per run: re-admissions (with a reset)
at or after the first fault starts, misleading and hazardous epochs, the worst horizontal error
in the fault window, and whether the spoof was detected (`pnt.metrics.score`). Sim evidence; the
LTE models are `placeholder` (verification.md, *Sim validity*).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from pnt.experiments import _map
from pnt.integrity.gnss_readmit import GnssReadmit
from pnt.metrics import score
from pnt.nav import ESTIMATORS, configured, estimate
from pnt.sim.scenario import T0_NS, generate, load

SCENARIOS = (
    "spoof-jump",
    "spoof-ramp",
    "meaconing",
    "gps-outage",  # honest GNSS returning after a gap
    "challenge-drone-spoof-jump",
    "challenge-drone-spoof-ramp",
    "challenge-drone-meaconing",
)
FAMILIES = ("ekf", "ekf-imu", "ekf-guard", "ekf-imu-guard", "ekf-calibrated-guard")
FIELDS = ("misleading_epochs", "hazardous_epochs", "fault_h_max_m", "spoof_detected")


def with_readmit(name: str, holder: list):
    fn = ESTIMATORS[name]
    base = getattr(fn, "func", fn)
    keywords = dict(getattr(fn, "keywords", {}))

    def factory():
        holder.append(GnssReadmit())
        return holder[-1]

    return configured(base, **keywords, gnss_readmit=factory)


def job(scenario: str, seed: int) -> list[dict]:
    spec = load(scenario)
    run = generate(spec, seed=seed)
    start_ns = T0_NS + round(min(f["start_s"] for f in spec.get("faults", [])) * 1e9)
    rows = []
    for name in FAMILIES:
        for variant in ("off", "readmit"):
            holder: list[GnssReadmit] = []
            fn = ESTIMATORS[name] if variant == "off" else with_readmit(name, holder)
            t = time.time()
            out = list(estimate(fn, run.measurements, origin_llh=spec.get("origin_llh")))
            m = score(out, run.truth, spec, T0_NS).as_dict()
            late = [x for r in holder for x in r.readmits if x >= start_ns]
            rows.append({"scenario": scenario, "seed": seed, "family": name, "variant": variant,
                         "readmits_after_fault": len(late), "run_s": round(time.time() - t, 1)}
                        | {f: m[f] for f in FIELDS})  # fmt: skip
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    ap.add_argument("--seeds", default="0-2")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    lo, hi = (int(x) for x in a.seeds.split("-"))
    tasks = [(s, k) for s in a.scenarios for k in range(lo, hi + 1)]
    rows = [r for rs in _map(job, tasks, a.jobs) for r in rs]
    summary: dict = {}
    for r in rows:
        key = f"{r['scenario']}|{r['family']}|{r['variant']}"
        summary.setdefault(key, []).append(r)
    table = {}
    for key, rs in summary.items():
        table[key] = {
            "runs": len(rs),
            "readmits_after_fault": int(sum(r["readmits_after_fault"] for r in rs)),
            "misleading_epochs": float(np.mean([r["misleading_epochs"] for r in rs])),
            "hazardous_epochs": float(np.mean([r["hazardous_epochs"] for r in rs])),
            "fault_h_max_m": float(np.max([r["fault_h_max_m"] for r in rs])),
        }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"summary": table, "rows": rows}, indent=1) + "\n")
    for key, v in table.items():
        print(key, v)


if __name__ == "__main__":
    main()
