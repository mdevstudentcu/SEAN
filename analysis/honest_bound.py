"""Is the protection level honest after GPS loss, and still useful? (#226), sim.

Per epoch, the true horizontal error against HPL, for the default filters, their opt-in variants
and the opt-in honest-bound variants (ADR-0041 Proposed), on the challenge legs. Reuses the T5
figure's per-epoch collection (`bound_epochs` and `bound_stats` of `analysis/challenge_baseline.py`
on branch `elshoubky/feat/150-challenge-baseline`, #222): error and HPL paired with truth exactly
as `pnt.metrics.score` pairs them, so `mean(hpl >= err)` is the run's `hpl_bound_frac`.

Plans (each a list of (scenario key, seed, estimators) tasks; per-run results go to the
git-ignored `analysis/results/runs/honest-bound/<plan>.pkl`):
- `measure`: step 1 of #226, tuning seeds, the existing estimators only;
- `stress`: step 4, held-out seeds, every drone entry on 1, 6 and 13 carriers, the timing and
  approach legs, model mismatch;
- `sweep`: step 4, each honest-bound setting at 0.5x and 1.5x on drone `outage`;
- `mhss`: `ekf-mhss` as the reference that bounds but is unusable.

    python analysis/honest_bound.py --plan measure --seeds 1000-1049 --jobs 4
    python analysis/honest_bound.py --plan stress --seeds 0-199 --jobs 10 --host g14
    python analysis/honest_bound.py --report      # summary.md and the figure from the pickles

Statistics, per (scenario, estimator), pooled over runs:
- *above*: share of epochs with error > HPL, over each whole run (T5's epochs) and over the
  window from the first fault (GPS loss, jump) to the run's end (`win`), which is the stricter;
- *worst run*: the largest per-run share above, on the window;
- *hazardous*: error over the 50 m alert limit while HPL is at or under it (`pnt.metrics`);
- *tightness*: at each second after GPS loss, the median over runs of HPL divided by the 95th
  percentile over runs of the error; its median over 0-300 s (#226: <= 3 is still useful);
- *p95 curve*: the across-run 95th percentile of error at each second (ADR-0034's statistic).

Committed results need a clean tree; `--report` writes `analysis/results/honest-bound/`.
"""

from __future__ import annotations

import argparse
import copy
import functools
import gzip
import json
import math
import pickle
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hopping_study  # noqa: E402

from pnt.cli import _commit  # noqa: E402
from pnt.experiments import _map, get_param, set_param  # noqa: E402
from pnt.integrity.jump_guard import JumpGuard  # noqa: E402
from pnt.metrics import ALERT_LIMIT_M, gps_loss, score  # noqa: E402
from pnt.nav import ESTIMATORS, configured, ekf, estimate  # noqa: E402
from pnt.sim.scenario import T0_NS, generate, load  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "honest-bound"
RUNS = HERE / "results" / "runs" / "honest-bound"  # git-ignored
KIND = "sim, every value TBC (ADR-0015, ADR-0030 Proposed, ADR-0041 Proposed)"

# #226's bars (TBC: ours, set by the issue; T5 is ADR-0034's, Proposed)
ESCAPE_POOLED = 0.01  # error > HPL in at most this share of epochs, pooled, every drone entry
ESCAPE_WORST_RUN = 0.05  # ... and in the worst run
T5_BOUND = 0.999  # T5: HPL bounds the error in this share of epochs (TBC)
TIGHTNESS_MAX = 3.0  # median over 0-300 s of median(HPL) / p95(error) at each second
TIGHT_WINDOW_S = 300
P95_HARM = 1.05  # across-run p95 at its worst second, at most this times the unfixed estimator's

DRONE_ENTRIES = (
    "nominal",
    "outage",
    "outage-tower-clock-step",
    "outage-tower-holdover",
    "outage-imu-bias",
    "outage-baro-drift",
    "spoof-jump",
    "meaconing",
    "spoof-ramp",
)
CARRIERS = (1, 6, 13)
GUARDED_ENTRIES = ("spoof-jump", "meaconing", "spoof-ramp")  # GNSS attacks: the guard runs too


# --- estimators ---------------------------------------------------------------------------------
# Registered names, or combinations built from the registry's own configuration hooks (no filter
# behaviour is added here; as `analysis/stacked_fixes.py`)
COMBOS = {
    "ekf-learned-noise+guard": configured(
        ekf.run, noise_tau_s=ekf.NOISE_TAU_S, jump_guard=JumpGuard
    ),
    "ekf-calibrated-learned-noise+guard": configured(
        ekf.run_calibrated, noise_tau_s=ekf.CALIBRATED_NOISE_TAU_S, jump_guard=JumpGuard
    ),
}


def estimator(name: str, config: dict | None = None):
    """A registered estimator or a combination, with `config` passed on top (the sweep)."""
    fn = COMBOS[name] if name in COMBOS else ESTIMATORS[name]
    if not config:
        return fn
    return configured(fn.func, **{**fn.keywords, **config})


# --- scenarios ----------------------------------------------------------------------------------
def spec_of(key: str) -> dict:
    """A scenario from its key: `drone/<entry>/<n>c`, `timing/<entry>`, `approach/<entry>`, with
    an optional `/lte*<k>` (the truth's LTE noise and multipath sigma times k, what the records
    report unchanged: as `analysis/model_mismatch.py` scales a scenario)."""
    parts = key.split("/")
    scale = None
    if parts[-1].startswith("lte*"):
        scale = float(parts.pop()[4:])
    leg, entry = parts[0], parts[1]
    if leg == "drone":
        n = int(parts[2].removesuffix("c"))
        if n == 1:
            spec = copy.deepcopy(load(f"challenge-drone-{entry}"))
        else:
            spec = copy.deepcopy(load(f"challenge-drone-hop-{entry}"))
            spec["sources"]["lte"]["cells_from"]["earfcn"] = hopping_study.hop_set()[:n]
    else:
        spec = copy.deepcopy(load(f"challenge-{leg}-{entry}"))
    if scale is not None:
        for path in ("sources.lte.sigma_m", "sources.lte.multipath.sigma_m"):
            spec = set_param(spec, path, get_param(spec, path) * scale)
    return spec


def event_start_ns(spec: dict) -> int | None:
    """The first fault's start (GPS loss, a jump, a ramp), or None (nominal)."""
    starts = [f.get("start_s", 0.0) for f in spec.get("faults", [])]
    return T0_NS + int(round(min(starts) * 1e9)) if starts else None


# --- one run ------------------------------------------------------------------------------------
HIST_EDGES = np.logspace(0, 5, 61)  # 1 m to 100 km, both axes (as the T5 figure)


def bound_epochs(estimates, truth) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(t_ns, horizontal error, HPL) at every epoch, paired with truth and computed exactly as
    `pnt.metrics.score` does (T5's `bound_epochs`, #222, with the epoch times)."""
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    t = np.array([e.t_ns for e, _ in pairs])
    err_h = np.array([np.subtract(e.pos_enu, g.pos_enu)[:2] for e, g in pairs])
    return t, np.hypot(err_h[:, 0], err_h[:, 1]), np.array([e.hpl_m for e, _ in pairs])


def per_second(t: np.ndarray, x: np.ndarray, n_s: int) -> np.ndarray:
    """`x` at each whole second 0..n_s-1 from the run's start (nan where no epoch is on it)."""
    out = np.full(n_s, np.nan, np.float32)
    k = (t - T0_NS) / 1e9
    on = np.abs(k - np.round(k)) < 1e-6
    idx = np.round(k[on]).astype(int)
    ok = idx < n_s
    out[idx[ok]] = x[on][ok]
    return out


def run_task(key: str, seed: int, names: tuple[str, ...], config: dict | None = None) -> list:
    """One seed of one scenario, generated once, through each estimator."""
    spec = spec_of(key)
    sim = generate(spec, seed=seed)
    start = event_start_ns(spec)
    loss = gps_loss(spec, T0_NS)
    n_s = int(round(float(spec["duration_s"])))
    out = []
    for name in names:
        t0 = time.perf_counter()
        r = {"key": key, "seed": seed, "estimator": name, "config": config or {}}
        try:
            est = list(
                estimate(estimator(name, config), sim.measurements,
                         origin_llh=spec.get("origin_llh"), reference=sim.reference)
            )  # fmt: skip
            m = score(est, sim.truth, spec, T0_NS)
            t, err, h = bound_epochs(est, sim.truth)
        except Exception as exc:  # report the crash, don't work around it
            r["error"] = f"{type(exc).__name__}: {exc}"
            out.append(r)
            continue
        win = t >= start if start is not None else np.ones(len(t), bool)
        r.update(
            n=int(len(t)),
            n_win=int(win.sum()),
            above=int(np.sum(err > h)),
            above_win=int(np.sum((err > h) & win)),
            hazardous=int(m.hazardous_epochs),
            misleading=int(m.misleading_epochs),
            false_alarms_per_h=float(m.false_alarms_per_h),
            spoof_detected=float(m.spoof_detected),
            under_al_win=int(np.sum((h <= ALERT_LIMIT_M) & win)),
            first_unsafe_s=float("nan"),
            err_s=per_second(t, err, n_s),
            hpl_s=per_second(t, h, n_s),
            hist=np.histogram2d(np.clip(h, 1, 1e5), np.clip(err, 1, 1e5),
                                [HIST_EDGES, HIST_EDGES])[0].astype(np.int32),  # fmt: skip
            loss_s=None if loss is None else (loss[0] - T0_NS) / 1e9,
            start_s=None if start is None else (start - T0_NS) / 1e9,
        )
        if loss is not None:
            after = np.flatnonzero((t >= loss[0]) & (h > ALERT_LIMIT_M))
            if after.size:
                r["first_unsafe_s"] = float((t[after[0]] - loss[0]) / 1e9)
        r["run_s"] = round(time.perf_counter() - t0, 1)
        out.append(r)
    return out


# --- plans --------------------------------------------------------------------------------------
BASE = ("ekf", "ekf-learned-noise", "ekf-calibrated", "ekf-calibrated-learned-noise")
GUARD = ("ekf-guard", "ekf-learned-noise+guard", "ekf-calibrated-guard",
         "ekf-calibrated-learned-noise+guard")  # fmt: skip


# The calibrated filter on 6 and 13 carriers takes 2 to 8 min a run and 1.6 GB (13 carriers,
# 720 s), so on hopped entries it runs on the first CALIBRATED_HOP_SEEDS seeds only
CALIBRATED_HOP_SEEDS = 5


def split(names: tuple[str, ...], key: str, seeds: list[int]) -> list[tuple]:
    """Tasks for `names` on `key`: every seed, except the calibrated family on hopped entries."""
    plain = tuple(n for n in names if "calibrated" not in n)
    cal = tuple(n for n in names if "calibrated" in n)
    hopped = "/6c" in key or "/13c" in key
    tasks = [(key, s, plain, None) for s in seeds] if plain else []
    if cal:
        tasks += [(key, s, cal, None) for s in (seeds[:CALIBRATED_HOP_SEEDS] if hopped else seeds)]
    return tasks


def plan_measure(seeds: list[int]) -> list[tuple]:
    tasks = []
    for n in CARRIERS:
        for entry in ("nominal", "outage", "spoof-jump"):
            names = BASE + (GUARD if entry == "spoof-jump" else ())
            tasks += split(names, f"drone/{entry}/{n}c", seeds)
    return tasks


# The fix (ADR-0041) beside what it changes: the default and the same estimator without it
FIX = ("ekf", "ekf-learned-noise", "ekf-honest")
FIX_GUARD = ("ekf-guard", "ekf-learned-noise+guard", "ekf-honest-guard")
# Each new setting at 0.5x and 1.5x (#226: a +-50 % sweep); values from `ekf.HONEST`
SWEEP = {
    "multipath_ratio": ekf.HONEST["multipath_ratio"],
    "multipath_tau_s": ekf.HONEST["multipath_tau_s"],
}
SWEEP_FACTORS = (0.5, 1.5)
MHSS_SEEDS = 20


def drone_tasks(seeds: list[int], entries=DRONE_ENTRIES, carriers=CARRIERS) -> list[tuple]:
    tasks = []
    for n in carriers:
        for entry in entries:
            names = FIX + (FIX_GUARD if entry in GUARDED_ENTRIES else ())
            tasks += [(f"drone/{entry}/{n}c", s, names, None) for s in seeds]
    return tasks


def plan_tune(seeds: list[int]) -> list[tuple]:
    """The fix on every drone entry, tuning seeds (checked before the held-out run)."""
    return drone_tasks(seeds)


def plan_stress(seeds: list[int]) -> list[tuple]:
    """#226 step 4 on held-out seeds: every drone entry on 1, 6 and 13 carriers; the timing and
    approach legs' `outage` and `nominal` on the first 50 seeds; model mismatch (the truth's LTE
    noise and multipath at 0.5x and 2x, records unchanged) on drone `outage` and, once, on the
    IMU bias entry."""
    tasks = drone_tasks(seeds)
    for leg in ("timing", "approach"):
        for entry in ("outage", "nominal"):
            tasks += [(f"{leg}/{entry}", s, FIX, None) for s in seeds[:50]]
    for k in (0.5, 2.0):
        for n in CARRIERS:
            tasks += [(f"drone/outage/{n}c/lte*{k:g}", s, FIX, None) for s in seeds]
        tasks += [(f"drone/outage-imu-bias/1c/lte*{k:g}", s, FIX, None) for s in seeds[:50]]
    return tasks


def plan_sweep(seeds: list[int]) -> list[tuple]:
    """Each new setting at 0.5x and 1.5x, `ekf-honest`, drone `outage` on 1 and 13 carriers,
    the first 50 seeds; the unswept fix and its unfixed estimator ride along for pairing."""
    tasks = []
    for n in (1, 13):
        key = f"drone/outage/{n}c"
        for s in seeds[:50]:
            tasks.append((key, s, ("ekf-learned-noise", "ekf-honest"), None))
            for name, v in SWEEP.items():
                for k in SWEEP_FACTORS:
                    tasks.append((key, s, ("ekf-honest",), {name: v * k}))
    return tasks


def plan_mhss(seeds: list[int]) -> list[tuple]:
    """`ekf-mhss`, the reference that bounds but is too large to use, on 20 seeds."""
    return [(f"drone/{e}/1c", s, ("ekf-mhss",), None) for e in ("outage", "spoof-jump", "spoof-ramp")
            for s in seeds[:MHSS_SEEDS]]  # fmt: skip


PLANS = {
    "measure": plan_measure,
    "tune": plan_tune,
    "stress": plan_stress,
    "sweep": plan_sweep,
    "mhss": plan_mhss,
}


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def _clean(commit: str) -> bool:
    untracked = subprocess.run(["git", "status", "--porcelain"], cwd=HERE, capture_output=True,
                               text=True).stdout.strip()  # fmt: skip
    return len(commit) >= 7 and all(c in "0123456789abcdef" for c in commit) and not untracked


def run_plan(plan: str, seeds: list[int], jobs: int, host: str, out: Path, part: str = "") -> Path:
    """Run a plan, or the part of it named `part`: `plain` or `calibrated` (estimator family),
    optionally with `:hop` or `:1c` (scenario carriers), so one plan can be split over hosts."""
    tasks = PLANS[plan](seeds)
    if part:
        fam, _, car = part.partition(":")
        keep = []
        for key, seed, names, cfg in tasks:
            names = tuple(n for n in names if ("calibrated" in n) == (fam == "calibrated"))
            hop = "/6c" in key or "/13c" in key
            if names and (not car or (car == "hop") == hop):
                keep.append((key, seed, names, cfg))
        tasks = keep
    # Longest first: 13-carrier calibrated runs take the most time
    tasks.sort(key=lambda t: (not any("calibrated" in n for n in t[2]), "13c" not in t[0],
                              "6c" not in t[0]))
    commit = _commit()
    t0 = time.time()
    res = _map(run_task, tasks, jobs)
    runs = [r for chunk in res for r in chunk]
    doc = {
        "plan": plan,
        "seeds": seeds,
        "commit": commit,
        "clean": _clean(commit),
        "host": host,
        "python": platform.python_version(),
        "command": "python analysis/honest_bound.py " + " ".join(sys.argv[1:]),
        "elapsed_min": (time.time() - t0) / 60,
        "part": part,
        "runs": runs,
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{plan}{'-' + part.replace(':', '-') if part else ''}.pkl.gz"
    with gzip.open(path, "wb") as f:
        pickle.dump(doc, f)
    errors = [r for r in runs if "error" in r]
    print(f"{plan}: {len(runs)} runs, {len(errors)} errors, {doc['elapsed_min']:.1f} min -> {path}")
    for r in errors[:5]:
        print("  ", r["key"], r["seed"], r["estimator"], r["error"])
    return path


# --- aggregate ----------------------------------------------------------------------------------
def load_plan(path: Path) -> dict:
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def group(runs: list[dict]) -> dict:
    """{(key, estimator, config json): [runs sorted by seed]}."""
    out: dict = {}
    for r in runs:
        if "error" in r:
            continue
        k = (r["key"], r["estimator"], json.dumps(r["config"], sort_keys=True))
        out.setdefault(k, []).append(r)
    return {k: sorted(v, key=lambda r: r["seed"]) for k, v in out.items()}


def cell(runs: list[dict]) -> dict:
    """The statistics of one (scenario, estimator) over its runs (module docstring)."""
    n = sum(r["n"] for r in runs)
    nw = sum(r["n_win"] for r in runs)
    worst = max(runs, key=lambda r: r["above_win"] / max(r["n_win"], 1))
    out = {
        "runs": len(runs),
        "above": sum(r["above"] for r in runs) / n,
        "above_win": sum(r["above_win"] for r in runs) / nw,
        "worst_run": worst["above_win"] / max(worst["n_win"], 1),
        "worst_seed": worst["seed"],
        "hazardous": sum(r["hazardous"] for r in runs),
        "hazardous_runs": sum(r["hazardous"] > 0 for r in runs),
        "misleading": sum(r["misleading"] for r in runs),
        "under_al_win": sum(r["under_al_win"] for r in runs) / nw,
        "false_alarms_per_h": float(np.mean([r["false_alarms_per_h"] for r in runs])),
        "run_s": float(np.mean([r["run_s"] for r in runs])),
    }
    loss = runs[0]["loss_s"]
    if loss is not None:
        a = int(round(loss))
        e = np.array([r["err_s"][a : a + TIGHT_WINDOW_S + 1] for r in runs], float)
        h = np.array([r["hpl_s"][a : a + TIGHT_WINDOW_S + 1] for r in runs], float)
        p95 = np.nanpercentile(e, 95, axis=0)
        ratio = np.nanmedian(h, axis=0) / p95
        out.update(
            tightness=float(np.nanmedian(ratio)),
            p95_worst=float(np.nanmax(p95)),
            p95_worst_at=int(np.nanargmax(p95)),
            p95_curve=p95,
            hpl_med_curve=np.nanmedian(h, axis=0),
            unsafe_median_s=float(np.nanmedian([r["first_unsafe_s"] for r in runs])),
            unsafe_min_s=float(np.nanmin([r["first_unsafe_s"] for r in runs]))
            if not all(math.isnan(r["first_unsafe_s"]) for r in runs) else float("nan"),
        )
    start = runs[0]["start_s"]
    if start is not None and loss is None:  # a jump or ramp: p95 curve from the attack's start
        a = int(round(start))
        e = np.array([r["err_s"][a:] for r in runs], float)
        out["p95_worst"] = float(np.nanmax(np.nanpercentile(e, 95, axis=0)))
    return out


def table(path: Path) -> None:
    doc = load_plan(path)
    print(f"{doc['plan']} at {doc['commit']} on {doc['host']}, seeds {doc['seeds'][0]}-"
          f"{doc['seeds'][-1]}, {doc['elapsed_min']:.1f} min")  # fmt: skip
    print(f"{'scenario':34s} {'estimator':38s} {'runs':>4s} {'above':>7s} {'win':>7s} "
          f"{'worst':>7s} {'haz':>6s} {'tight':>6s} {'p95w':>7s} {'<AL':>6s} {'unsafe':>6s}")
    for (key, name, cfg), runs in sorted(group(doc["runs"]).items()):
        c = cell(runs)
        label = name + ("" if cfg == "{}" else " " + cfg)
        print(f"{key:34s} {label:38s} {c['runs']:4d} {100 * c['above']:6.2f}% "
              f"{100 * c['above_win']:6.2f}% {100 * c['worst_run']:6.2f}% {c['hazardous']:6d} "
              f"{c.get('tightness', float('nan')):6.2f} {c.get('p95_worst', float('nan')):7.1f} "
              f"{100 * c['under_al_win']:5.1f}% {c.get('unsafe_median_s', float('nan')):6.1f}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", choices=sorted(PLANS))
    ap.add_argument("--seeds", default="1000-1049")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--host", default=platform.node().split(".")[0])
    ap.add_argument("--out", type=Path, default=RUNS)
    ap.add_argument("--part", default="", help="plain|calibrated[:hop|:1c]: one part of the plan")
    ap.add_argument("--table", type=Path, help="print the table of one plan's pickle")
    args = ap.parse_args(argv)
    if args.table:
        table(args.table)
        return
    if args.plan:
        path = run_plan(args.plan, parse_seeds(args.seeds), args.jobs, args.host, args.out,
                        args.part)
        table(path)


if __name__ == "__main__":
    main()
