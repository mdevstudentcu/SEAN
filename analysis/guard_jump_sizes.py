"""GNSS position jumps of 20 m to 500 km, with and without the opt-in jump guard (ADR-0038), sim.

Each run: GNSS position jumps by `size` metres at t = START_S and stays there to the end of the
360 s run (`spoof_jump`). Seed k jumps towards DIRECTIONS_DEG[k % 8], clockwise from north.
Clean runs (no fault, same seeds) give false alarms and show whether the guard ever latches
without a jump. The jump is added to the ENU position records, so a jump of hundreds of
kilometres is a flat ENU offset (it leaves out the Earth's curvature, about 20 km at 500 km).

Environments, each with its faults removed first:
- `realistic-uc01`: `realistic-nominal` (the realistic set) flown on `uc01-drone-circuit`'s route
- `uc01`: `uc01-drone-circuit` as committed

Variants, on the same records: `ekf`, `ekf-guard`, `ekf-imu`, `ekf-imu-guard`.

    PYTHONPATH=src python analysis/guard_jump_sizes.py --seeds 20 --jobs 3 --out DIR

Writes DIR/summary.md (the table) and DIR/rows.json (per run; keep it out of git).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.core.time import s_to_ns
from pnt.metrics import score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

VARIANTS = ("ekf", "ekf-guard", "ekf-imu", "ekf-imu-guard")
ENVIRONMENTS = ("realistic-uc01", "uc01")
SIZES_M = (20.0, 50.0, 100.0, 300.0, 1000.0, 100_000.0, 500_000.0)
DIRECTIONS_DEG = tuple(range(0, 360, 45))
START_S = 150.0
AFTER_S = (30.0, 120.0)  # error reported this long after the jump


def environment(name: str) -> dict:
    """The environment's spec with no faults."""
    if name == "realistic-uc01":
        spec = load("realistic-nominal")
        spec["trajectory"] = copy.deepcopy(load("uc01-drone-circuit")["trajectory"])
    elif name == "uc01":
        spec = load("uc01-drone-circuit")
    else:
        raise ValueError(f"unknown environment {name!r}")
    spec.update(name=name, faults=[])
    return spec


def run_case(env: str, size_m: float | None, seed: int) -> list[dict]:
    """Every variant over one simulated run. `size_m` None: no jump."""
    spec = environment(env)
    if size_m is not None:
        d = math.radians(DIRECTIONS_DEG[seed % len(DIRECTIONS_DEG)])
        off = [size_m * math.sin(d), size_m * math.cos(d), 0.0]
        spec["faults"] = [
            {"type": "spoof_jump", "source": "gnss", "start_s": START_S, "offset_enu_m": off}
        ]
    run = generate(spec, seed=seed)
    truth = {g.t_ns: g for g in run.truth}
    start = T0_NS + s_to_ns(START_S)
    rows, plain = [], {}
    for v in VARIANTS:
        est = list(estimate(v, run.measurements, origin_llh=spec["origin_llh"]))
        m = score(est, run.truth, spec, T0_NS)
        on = [e for e in est if e.t_ns in truth]
        t = np.array([e.t_ns for e in on])
        err = np.array([np.hypot(*np.subtract(e.pos_enu, truth[e.t_ns].pos_enu)[:2]) for e in on])
        at = {
            s: float(err[min(np.searchsorted(t, start + s_to_ns(s)), len(t) - 1)]) for s in AFTER_S
        }
        if not v.endswith("-guard"):
            plain[v] = repr(est)
        rows.append(
            {
                "env": env,
                "variant": v,
                "size_m": size_m,
                "seed": seed,
                "detected": m.spoof_detected,
                "detect_s": m.detect_delay_s,
                "tta_s": m.time_to_alert_s,
                "hazardous": m.hazardous_epochs,
                "misleading": m.misleading_epochs,
                "false_alarms_per_h": m.false_alarms_per_h,
                "err_at": at,
                "same_as_plain": (
                    repr(est) == plain[v.removesuffix("-guard")] if v.endswith("-guard") else None
                ),
            }
        )
    return rows


def _nan(fn, v) -> float:
    v = np.array([x for x in v if x is not None], float)
    v = v[~np.isnan(v)]
    return float(fn(v)) if v.size else math.nan


def summary(rows: list[dict], meta: dict) -> str:
    out = [
        f"# GNSS jumps of 20 m to 500 km, with and without the jump guard ({meta['commit']}, sim)",
        "",
        f"Seeds 0..{meta['seeds'] - 1} per row. Command: `python analysis/guard_jump_sizes.py "
        f"--seeds {meta['seeds']} --jobs N --out DIR`. Jump at {START_S:g} s, held to the end. "
        "Detect: an alarm flag held 1 s (`pnt.metrics`); alert: any alert after the jump; "
        "HMI: error over the 50 m alert limit (TBC) while HPL is within it.",
        "",
        "| env | jump | variant | P(detect) | detect med / p95 (s) | alert med (s) | runs with "
        "HMI | HMI epochs | runs misleading | error +30 s med / max (m) | error +120 s med / max "
        "(m) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for env in ENVIRONMENTS:
        for size in SIZES_M:
            for v in VARIANTS:
                rs = [r for r in rows if (r["env"], r["size_m"], r["variant"]) == (env, size, v)]
                if not rs:
                    continue
                d = [r["detect_s"] for r in rs]
                e30 = [r["err_at"][30.0] for r in rs]
                e120 = [r["err_at"][120.0] for r in rs]
                p_det = _nan(np.mean, [r["detected"] for r in rs])
                hmi = sum(r["hazardous"] for r in rs)
                out.append(
                    f"| {env} | {size:g} m | `{v}` | {p_det:.2f}"
                    f" | {_nan(np.median, d):.1f} / {_nan(lambda x: np.percentile(x, 95), d):.1f}"
                    f" | {_nan(np.median, [r['tta_s'] for r in rs]):.1f}"
                    f" | {sum(r['hazardous'] > 0 for r in rs)}/{len(rs)}"
                    f" | {hmi} | {sum(r['misleading'] > 0 for r in rs)}"
                    f" | {np.median(e30):.0f} / {np.max(e30):.0f}"
                    f" | {np.median(e120):.0f} / {np.max(e120):.0f} |"
                )
    out += [
        "",
        "## No jump",
        "",
        "| env | variant | runs with a false alarm | runs with HMI | guarded output identical "
        "to the unguarded |",
        "| --- | --- | --- | --- | --- |",
    ]
    for env in ENVIRONMENTS:
        for v in VARIANTS:
            rs = [r for r in rows if (r["env"], r["size_m"], r["variant"]) == (env, None, v)]
            if not rs:
                continue
            same = (
                f"{sum(bool(r['same_as_plain']) for r in rs)}/{len(rs)}"
                if v.endswith("-guard")
                else "-"
            )
            out.append(
                f"| {env} | `{v}` | {sum(r['false_alarms_per_h'] > 0 for r in rs)}/{len(rs)}"
                f" | {sum(r['hazardous'] > 0 for r in rs)}/{len(rs)} | {same} |"
            )
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"commit": _commit(), "seeds": a.seeds}
    tasks = [(e, z, s) for e in ENVIRONMENTS for z in (None, *SIZES_M) for s in range(a.seeds)]
    if a.jobs > 1:
        ctx = multiprocessing.get_context("forkserver")
        with ProcessPoolExecutor(a.jobs, mp_context=ctx) as pool:
            parts = list(pool.map(run_case, *zip(*tasks, strict=True)))
    else:
        parts = [run_case(*t) for t in tasks]
    rows = [r for rs in parts for r in rs]
    (out / "rows.json").write_text(json.dumps({"meta": meta, "rows": rows}))
    (out / "summary.md").write_text(summary(rows, meta))
    print(f"wrote {out / 'summary.md'}")


if __name__ == "__main__":
    main()
