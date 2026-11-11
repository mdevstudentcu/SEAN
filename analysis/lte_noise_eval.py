"""Paired evaluation for #147: the challenge legs with LTE records as written (told 2 m), and with
no LTE records at all, per seed, for each estimator. Writes one JSON row per run.

    python analysis/lte_noise_eval.py --scenarios challenge-drone-outage challenge-timing-outage \
        --seeds 0-49 --variants lte nolte --estimators ekf ekf-calibrated --jobs 6 --out rows.json

Run it with PYTHONPATH pointing at the `src/` under test (a branch, or `main` for the base), so
both sides share this script. Seeds pair: the same seed gives both sides the same records.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import time
from pathlib import Path

from pnt.experiments import _map
from pnt.metrics import score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

FIELDS = (
    "outage_h_p95_120s_m",  # ADR-0034 fallback: <= 50 m for 120 s
    "outage_h_p95_300s_m",  # T1
    "outage_hpl_bound_300s",
    "outage_time_err_600s_us",  # T3
    "hazardous_epochs",
    "misleading_epochs",
    "hpl_bound_frac",
    "h_nees_mean",
    "false_alarms_per_h",
    "time_hazardous_epochs",
)


def _spec(scenario: str, variant: str) -> dict:
    spec = load(scenario)
    if variant == "nolte":
        spec = copy.deepcopy(spec)
        del spec["sources"]["lte"]
    elif variant != "lte":
        raise ValueError(f"variant must be lte or nolte, not {variant!r}")
    return spec


def _job(scenario: str, variant: str, seed: int, estimators: tuple[str, ...]) -> list[dict]:
    spec = _spec(scenario, variant)
    run = generate(spec, seed=seed)
    rows = []
    for est in estimators:
        out = estimate(est, run.measurements, origin_llh=spec.get("origin_llh"))
        m = score(list(out), run.truth, spec, T0_NS).as_dict()
        rows.append({"scenario": scenario, "variant": variant, "estimator": est, "seed": seed}
                    | {f: m[f] for f in FIELDS})  # fmt: skip
    return rows


def _seeds(text: str) -> list[int]:
    a, b = text.split("-")
    return list(range(int(a), int(b) + 1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenarios", nargs="+", required=True)
    ap.add_argument("--seeds", default="0-49")
    ap.add_argument("--variants", nargs="+", default=["lte", "nolte"])
    ap.add_argument("--estimators", nargs="+", default=["ekf", "ekf-calibrated"])
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import pnt

    src = Path(pnt.__file__).resolve().parents[1]
    commit = subprocess.run(["git", "-C", str(src), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()  # fmt: skip
    dirty = subprocess.run(["git", "-C", str(src), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip() != ""  # fmt: skip
    tasks = [(s, v, seed, tuple(a.estimators))
             for s in a.scenarios for v in a.variants for seed in _seeds(a.seeds)]  # fmt: skip
    t0 = time.time()
    rows = [r for rs in _map(_job, tasks, a.jobs) for r in rs]
    meta = {"src": str(src), "commit": commit, "dirty": dirty, "seeds": a.seeds,
            "wall_s": round(time.time() - t0)}  # fmt: skip
    Path(a.out).write_text(json.dumps({"meta": meta, "rows": rows}, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
