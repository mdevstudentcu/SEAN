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
from pnt.integrity.mhss import MHSS  # noqa: E402
from pnt.integrity.protection import K_H  # noqa: E402
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
@functools.cache
def combos() -> dict:
    """Built on first use, so `--hashes` also imports against a tree without these settings."""
    return {
        "ekf-learned-noise+guard": configured(
            ekf.run, noise_tau_s=ekf.NOISE_TAU_S, jump_guard=JumpGuard
        ),
        "ekf-calibrated-learned-noise+guard": configured(
            ekf.run_calibrated, noise_tau_s=ekf.CALIBRATED_NOISE_TAU_S, jump_guard=JumpGuard
        ),
        # The fix under solution separation (`ekf-mhss`'s monitor): a reference for the GNSS
        # attacks the fault-free bound cannot cover, not a proposed estimator
        "ekf-honest-mhss": configured(ekf.run, monitor=MHSS, **ekf.HONEST),
    }


def estimator(name: str, config: dict | None = None):
    """A registered estimator or a combination, with `config` passed on top (the sweep)."""
    fn = combos()[name] if name in combos() else ESTIMATORS[name]
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


def horizontal_nees(estimates, truth) -> np.ndarray:
    """Horizontal NEES at every epoch, as `pnt.metrics.score` computes it (2 on average for an
    honest covariance; over K_H^2 the error is outside the HPL's ellipse)."""
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    d = np.array([np.subtract(e.pos_enu, g.pos_enu)[:2] for e, g in pairs])
    c = np.array([np.reshape(e.pos_cov, (3, 3))[:2, :2] for e, _ in pairs])
    return np.einsum("ij,ij->i", d, np.linalg.solve(c, d[..., None])[..., 0])


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
            nees = horizontal_nees(est, sim.truth)
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
            nees_sum_win=float(np.sum(nees[win])),
            nees_over_k2_win=int(np.sum(nees[win] > K_H**2)),
            first_unsafe_s=float("nan"),
            err_s=per_second(t, err, n_s),
            hpl_s=per_second(t, h, n_s),
            hist=np.histogram2d(
                np.clip(h, 1, 1e5), np.clip(err, 1, 1e5), [HIST_EDGES, HIST_EDGES]
            )[0].astype(np.int32),  # fmt: skip
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
_HONEST = getattr(ekf, "HONEST", {})  # absent on a tree without ADR-0041 (`--hashes` there)
SWEEP = {name: _HONEST[name] for name in ("multipath_ratio", "multipath_tau_s") if _HONEST}
SWEEP_FACTORS = (0.5, 1.5)
TAU_AT_REST_S = 3.0  # s: ADR-0036's at-rest correlated-error time (TBC)
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
    # On 1 carrier only: `ekf-honest` takes 10 to 40 s a run on 6 and 13 carriers (one multipath
    # state per heard cell), so the hopped entries run on fewer seeds (`--part plain:6c` etc.)
    for k in (0.5, 2.0):
        tasks += [(f"drone/outage/1c/lte*{k:g}", s, FIX, None) for s in seeds]
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
            # Outside the sweep: ADR-0036's at-rest correlation time (3 s, TBC), far below the
            # sets' 30 s, to show what a much shorter one does
            tasks.append((key, s, ("ekf-honest",), {"multipath_tau_s": TAU_AT_REST_S}))
    return tasks


def plan_mhss(seeds: list[int]) -> list[tuple]:
    """`ekf-mhss`, the reference that bounds but is too large to use, and the fix under the same
    monitor, on 20 seeds: GPS loss, nominal and the GNSS attacks."""
    entries = ("nominal", "outage", "spoof-jump", "meaconing", "spoof-ramp")
    return [(f"drone/{e}/1c", s, ("ekf-mhss", "ekf-honest-mhss"), None) for e in entries
            for s in seeds[:MHSS_SEEDS]]  # fmt: skip


# Step 2 (#226), tuning seeds: which term is wrong. Each candidate changes one term of the
# learned-noise filter: the coasting process noise (q_accel 1 -> 1.5 m/s^2/sqrt(Hz)), the tower
# clock random walk (q_emitter 0.2 -> 1 m/sqrt(s)), the slow range error as a state (the fix)
DIAGNOSE = (
    ("ekf-learned-noise", None),
    ("ekf-learned-noise", {"q_accel": 1.5}),
    ("ekf-learned-noise", {"q_emitter": 1.0}),
    ("ekf-honest", None),
    ("ekf-honest", {"q_accel": 1.5}),
)


DIAGNOSE_13C_SEEDS = 10  # ekf-honest takes 40-70 s a run on 13 carriers


def plan_diagnose(seeds: list[int]) -> list[tuple]:
    one = [("drone/outage/1c", s, (n,), c) for n, c in DIAGNOSE for s in seeds]
    hop = [("drone/outage/13c", s, (n,), c) for n, c in DIAGNOSE
           for s in seeds[:DIAGNOSE_13C_SEEDS]]  # fmt: skip
    return one + hop


def truth_dynamics(scenario: str = "challenge-drone-outage", seed: int = 1000) -> dict:
    """The truth trajectory's horizontal acceleration, against the CV model's white
    acceleration: per axis, var(velocity change over T) / T, which is q_accel^2 for the model."""
    sim = generate(load(scenario), seed=seed)
    v = np.array([g.vel_enu[:2] for g in sim.truth])
    dt = np.median(np.diff([g.t_ns for g in sim.truth])) / 1e9
    a = np.hypot(*(np.diff(v, axis=0) / dt).T)
    out = {"accel_rms": float(np.sqrt(np.mean(a**2))), "accel_max": float(a.max()), "psd": {}}
    for T in (1, 5, 10, 20, 60, 120):
        k = int(round(T / dt))
        dv = v[k:] - v[:-k]
        out["psd"][T] = [float(x) for x in np.mean(dv**2, axis=0) / T]
    return out


PLANS = {
    "diagnose": plan_diagnose,
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
    optionally with `:hop`, `:1c`, `:6c` or `:13c` (scenario carriers; `1c` includes the other
    legs), so one plan can be split over hosts and seed counts."""
    tasks = PLANS[plan](seeds)
    if part:
        fam, _, car = part.partition(":")
        keep = []
        for key, seed, names, cfg in tasks:
            names = tuple(n for n in names if ("calibrated" in n) == (fam == "calibrated"))
            hop = "/6c" in key or "/13c" in key
            match = {"hop": hop, "1c": not hop, "6c": "/6c" in key, "13c": "/13c" in key}
            if names and (not car or match[car]):
                keep.append((key, seed, names, cfg))
        tasks = keep
    # Longest first: 13-carrier calibrated runs take the most time
    tasks.sort(
        key=lambda t: (
            not any("calibrated" in n for n in t[2]),
            "13c" not in t[0],
            "6c" not in t[0],
        )
    )
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
    print(
        f"{plan}: {len(runs)} runs, {len(errors)} errors, {doc['elapsed_min']:.1f} min -> {path}"
    )
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
        "nees_mean_win": sum(r.get("nees_sum_win", np.nan) for r in runs) / nw,
        "nees_over_k2_win": sum(r.get("nees_over_k2_win", np.nan) for r in runs) / nw,
        "false_alarms_per_h": float(np.mean([r["false_alarms_per_h"] for r in runs])),
        "run_s": float(np.mean([r["run_s"] for r in runs])),
    }
    # From GPS loss, else from the attack's start (a held jump refused by the guard is a GPS loss
    # in all but name; a ramp or meaconing keeps GNSS)
    loss = runs[0]["loss_s"] if runs[0]["loss_s"] is not None else runs[0]["start_s"]
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
            # never unsafe counts as the run's end: the median then says so
            unsafe_median_s=float(
                np.median(
                    [
                        math.inf if math.isnan(r["first_unsafe_s"]) else r["first_unsafe_s"]
                        for r in runs
                    ]
                )
            )
            if runs[0]["loss_s"] is not None
            else math.nan,  # no GPS loss: time to unsafe is not defined
        )
    return out


def table(path: Path) -> None:
    doc = load_plan(path)
    print(f"{doc['plan']} at {doc['commit']} on {doc['host']}, seeds {doc['seeds'][0]}-"
          f"{doc['seeds'][-1]}, {doc['elapsed_min']:.1f} min")  # fmt: skip
    print(
        f"{'scenario':34s} {'estimator':38s} {'runs':>4s} {'above':>7s} {'win':>7s} "
        f"{'worst':>7s} {'haz':>6s} {'tight':>6s} {'p95w':>7s} {'<AL':>6s} {'unsafe':>6s}"
    )
    for (key, name, cfg), runs in sorted(group(doc["runs"]).items()):
        c = cell(runs)
        label = name + ("" if cfg == "{}" else " " + cfg)
        print(
            f"{key:34s} {label:38s} {c['runs']:4d} {100 * c['above']:6.2f}% "
            f"{100 * c['above_win']:6.2f}% {100 * c['worst_run']:6.2f}% {c['hazardous']:6d} "
            f"{c.get('tightness', float('nan')):6.2f} {c.get('p95_worst', float('nan')):7.1f} "
            f"{100 * c['under_al_win']:5.1f}% {c.get('unsafe_median_s', float('nan')):6.1f}"
        )


# --- report -------------------------------------------------------------------------------------
def load_plans(runs_dir: Path) -> dict:
    """{plan: {"docs": [plan docs], "cells": {(key, estimator, config): cell}}}, every pickle of a
    plan (its parts) merged."""
    out: dict = {}
    for path in sorted(runs_dir.glob("*.pkl.gz")):
        doc = load_plan(path)
        p = out.setdefault(doc["plan"], {"docs": [], "runs": []})
        p["docs"].append({k: v for k, v in doc.items() if k != "runs"})
        p["runs"] += doc["runs"]
    for p in out.values():
        p["groups"] = group(p["runs"])
        p["cells"] = {k: cell(v) for k, v in p["groups"].items()}
        p["errors"] = [r for r in p["runs"] if "error" in r]
    return out


def _pct(x: float, nd: int = 2) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{nd}f} %"


def _num(x: float, fmt: str = ".2f") -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, fmt)


def _provenance(p: dict) -> str:
    parts = []
    for d in p["docs"]:
        s = d["seeds"]
        parts.append(f"`{d['command']}` at `{d['commit']}`{'' if d['clean'] else ' (DIRTY TREE)'} "
                     f"on {d['host']} (Python {d['python']}), seeds {s[0]}–{s[-1]}, "
                     f"{d['elapsed_min']:.0f} min")  # fmt: skip
    return "; ".join(parts)


ROW_HEAD = (
    "| Scenario | Estimator | runs | above HPL, whole run | above HPL, from fault | worst run "
    "| hazardous (runs) | NEES mean | tightness | HPL ≤ 50 m | p95 worst (m, s) | "
    "unsafe after loss (median s) |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
)


def row(key: str, label: str, c: dict) -> str:
    at = f" (s {c['p95_worst_at']})" if "p95_worst_at" in c else ""
    return (f"| `{key}` | `{label}` | {c['runs']} | {_pct(c['above'])} | {_pct(c['above_win'])} | "
            f"{_pct(c['worst_run'], 1)} (seed {c['worst_seed']}) | {c['hazardous']:,} "
            f"({c['hazardous_runs']}) | {_num(c['nees_mean_win'], '.1f')} | "
            f"{_num(c.get('tightness', math.nan))} | {_pct(c['under_al_win'], 1)} | "
            f"{_num(c.get('p95_worst', math.nan), ',.0f')}{at} | "
            f"{_unsafe(c.get('unsafe_median_s', math.nan))} |")  # fmt: skip


def _unsafe(x: float) -> str:
    return "never" if x == math.inf else _num(x, ".1f")


def label_of(name: str, cfg: str) -> str:
    return name if cfg == "{}" else f"{name} {cfg}"


def rows_of(p: dict, keys=None, names=None) -> list[str]:
    out = []
    for (key, name, cfg), c in sorted(p["cells"].items(), key=lambda kv: _order(kv[0])):
        if (keys is None or key in keys) and (names is None or name in names):
            out.append(row(key, label_of(name, cfg), c))
    return out


def _order(k: tuple) -> tuple:
    key, name, cfg = k
    parts = key.split("/")
    leg = {"drone": 0, "timing": 1, "approach": 2}[parts[0]]
    entry = DRONE_ENTRIES.index(parts[1]) if parts[1] in DRONE_ENTRIES else 99
    n = int(parts[2].removesuffix("c")) if leg == 0 else 0
    names = list(FIX + FIX_GUARD + BASE + GUARD) + ["ekf-mhss", "ekf-honest-mhss"]
    return (leg, len(parts), n, entry, names.index(name) if name in names else 99, cfg)


def fix_pair(name: str) -> tuple[str, str]:
    """(the same estimator without the fix, the default) for a fix estimator."""
    return {"ekf-honest": ("ekf-learned-noise", "ekf"),
            "ekf-honest-guard": ("ekf-learned-noise+guard", "ekf-guard")}[name]  # fmt: skip


def bars(p: dict, keys: list[str]) -> list[dict]:
    """#226's bars for the fix on each scenario key (guarded entries: `ekf-honest-guard`)."""
    out = []
    for key in keys:
        entry = key.split("/")[1]
        name = "ekf-honest-guard" if entry in GUARDED_ENTRIES else "ekf-honest"
        c = p["cells"].get((key, name, "{}"))
        if c is None:
            continue
        unfixed, default = fix_pair(name)
        u = p["cells"].get((key, unfixed, "{}"), {})
        d = p["cells"].get((key, default, "{}"), {})
        honest = (c["above_win"] <= ESCAPE_POOLED and c["worst_run"] <= ESCAPE_WORST_RUN
                  and c["hazardous"] == 0)  # fmt: skip
        tight = c.get("tightness", math.nan)
        harm_ratio = c.get("p95_worst", math.nan) / u.get("p95_worst", math.nan)
        fa = c["false_alarms_per_h"] - u.get("false_alarms_per_h", math.nan)
        out.append({
            "key": key, "name": name, "c": c, "u": u, "d": d, "honest": honest,
            "t5": c["above_win"] <= 1 - T5_BOUND,
            "useful": None if math.isnan(tight) else tight <= TIGHTNESS_MAX,
            "harm_ratio": harm_ratio,
            "no_harm": bool(harm_ratio <= P95_HARM) if not math.isnan(harm_ratio) else None,
            "fa_added": fa,
        })  # fmt: skip
    return out


def _yn(v) -> str:
    return "–" if v is None else ("met" if v else "**not met**")


def bars_table(bs: list[dict]) -> list[str]:
    lines = [
        "| Scenario | Fix | above HPL from fault (pooled) | worst run | hazardous | Honest "
        "(≤ 1 %, ≤ 5 %, 0) | T5 99.9 % | tightness | Useful (≤ 3) | HPL ≤ 50 m | p95 worst: fix / "
        "unfixed / default (m) | No harm (≤ 1.05×) | false alarms /h added |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for b in bs:
        c, u, d = b["c"], b["u"], b["d"]
        lines.append(
            f"| `{b['key']}` | `{b['name']}` | {_pct(c['above_win'])} | "
            f"{_pct(c['worst_run'], 1)} | "
            f"{c['hazardous']:,} | {_yn(b['honest'])} | {_yn(b['t5'])} | "
            f"{_num(c.get('tightness', math.nan))} | {_yn(b['useful'])} | "
            f"{_pct(c['under_al_win'], 1)} | {_num(c.get('p95_worst', math.nan), ',.0f')} / "
            f"{_num(u.get('p95_worst', math.nan), ',.0f')} / "
            f"{_num(d.get('p95_worst', math.nan), ',.0f')} | "
            f"{_num(b['harm_ratio'], '.3f')} {_yn(b['no_harm'])} | {_num(b['fa_added'], '+.2f')} |"
        )  # fmt: skip
    return lines


FIG_CELLS = (  # (scenario key, panel row label, default, fix)
    ("drone/outage/1c", "GPS lost 600 s\n(outage, 1 carrier)", "ekf", "ekf-honest"),
    (
        "drone/spoof-jump/1c",
        "GNSS held 300 m off\n(spoof-jump, 1 carrier)",
        "ekf-guard",
        "ekf-honest-guard",
    ),
)


def figure(p: dict, out: Path, tail: str) -> str | None:
    """Q: does the HPL bound the true error, default against the fix? Error against HPL at every
    epoch of every run (the T5 figure's density); above the diagonal the error escaped."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    g = p["groups"]
    if not all((k, d, "{}") in g and (k, f, "{}") in g for k, _, d, f in FIG_CELLS):
        return None
    lo, hi, al = 1.0, 1e5, ALERT_LIMIT_M
    edges = HIST_EDGES
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, axes = plt.subplots(2, 2, figsize=(13, 12.5), dpi=110, sharex=True, sharey=True)
    for r, (key, rlabel, dflt, fix) in enumerate(FIG_CELLS):
        for c, name in enumerate((dflt, fix)):
            ax = axes[r, c]
            runs = g[(key, name, "{}")]
            st = cell(runs)
            count = sum(x["hist"] for x in runs)
            ax.fill_between([lo, hi], [lo, hi], hi, color="#fbe3d6", lw=0, zorder=0)
            ax.fill_between([lo, al], [al, al], hi, color="#f2b694", lw=0, zorder=0)
            ax.pcolormesh(edges, edges, np.ma.masked_equal(count.T, 0), cmap="Blues",
                          norm=LogNorm(1, 2e5), zorder=1, rasterized=True)  # fmt: skip
            ax.plot([lo, hi], [lo, hi], color="black", lw=2, zorder=2)
            color = "#b2182b" if st["above"] > ESCAPE_POOLED else "#1a1a1a"
            ax.text(0.04, 0.96, f"{100 * st['above']:.1f} %", transform=ax.transAxes, va="top",
                    fontsize=40, weight="bold", color=color, zorder=3)  # fmt: skip
            ax.text(0.04, 0.80, f"of all epochs: error above HPL\n({name}; from the fault: "
                    f"{100 * st['above_win']:.1f} %)", transform=ax.transAxes, va="top",
                    fontsize=13, zorder=3)  # fmt: skip
            ax.text(0.97, 0.03, f"worst run {100 * st['worst_run']:.1f} % above\n"
                    f"hazardous epochs {st['hazardous']:,}", transform=ax.transAxes, ha="right",
                    va="bottom", fontsize=14, color="#333333", zorder=3)  # fmt: skip
            if r == 0:
                ax.set_title(("before: default" if c == 0 else "after: the fix"), fontsize=20,
                             weight="bold", color="#2a78d6" if c == 0 else "#1b7837")  # fmt: skip
            if c == 0:
                ax.set_ylabel("true horizontal error (m)", fontsize=16)
                ax.annotate(rlabel, (0, 0.5), xycoords="axes fraction", xytext=(-95, 0),
                            textcoords="offset points", rotation=90, ha="right", va="center",
                            fontsize=17, weight="bold")  # fmt: skip
            if r == 1:
                ax.set_xlabel("protection level HPL (m)", fontsize=16)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlim(lo, hi)
            ax.set_ylim(lo, hi)
            ax.set_aspect("equal")
            ticks = [1, 10, 100, 1e3, 1e4, 1e5]
            labels = ["≤1", "10", "100", "1k", "10k", "100k"]
            ax.set_xticks(ticks, labels)
            ax.set_yticks(ticks, labels)
            ax.minorticks_off()
            ax.tick_params(labelsize=14)
    axes[0, 1].text(2e3, 1.5e4, "error > HPL:\nbound escaped", fontsize=13, ha="center",
                    color="#8c4a2f", zorder=3)  # fmt: skip
    axes[0, 1].text(3, 2e2, "hazardous:\nerror > 50 m,\nHPL ≤ 50 m", fontsize=12,
                    color="#8c4a2f", zorder=3)  # fmt: skip
    n = cell(g[(FIG_CELLS[0][0], FIG_CELLS[0][3], "{}")])["runs"]
    fig.suptitle(f"Does the protection level bound the true error? Drone leg, {n} runs each,\n"
                 f"every 0.1 s epoch of each 720 s run · {tail}",
                 fontsize=18, y=0.985)  # fmt: skip
    fig.text(0.01, 0.005, f"{KIND} · analysis/honest_bound.py; numbers in summary.md\n"
             "darker blue: more epochs · ekf-honest: learned LTE noise with its slow part as a "
             "state (ADR-0041); -guard: with the jump guard (ADR-0038)", fontsize=11,
             color="#555555")  # fmt: skip
    fig.subplots_adjust(left=0.15, right=0.98, top=0.88, bottom=0.07, wspace=0.06, hspace=0.12)
    name = "bound_before_after.png"
    _save_png(fig, out / name)
    plt.close(fig)
    return name


def _save_png(fig, path: Path) -> None:
    """A 256-colour PNG (as the challenge baseline's figures): keeps the committed folder small."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)


def sweep_table(p: dict) -> list[str]:
    lines = [
        "| Scenario | Setting | above HPL from fault | worst run | hazardous | tightness | "
        "p95 worst (m) | p95 worst / unfixed | Honest | Useful | No harm |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (key, name, cfg), c in sorted(p["cells"].items(), key=lambda kv: _order(kv[0])):
        if name != "ekf-honest":
            continue
        u = p["cells"].get((key, "ekf-learned-noise", "{}"), {})
        ratio = c.get("p95_worst", math.nan) / u.get("p95_worst", math.nan)
        honest = (c["above_win"] <= ESCAPE_POOLED and c["worst_run"] <= ESCAPE_WORST_RUN
                  and c["hazardous"] == 0)  # fmt: skip
        setting = "as proposed" if cfg == "{}" else cfg.strip("{}").replace('"', "")
        lines.append(
            f"| `{key}` | {setting} | {_pct(c['above_win'])} | {_pct(c['worst_run'], 1)} | "
            f"{c['hazardous']:,} | {_num(c.get('tightness', math.nan))} | "
            f"{_num(c.get('p95_worst', math.nan), ',.0f')} | {_num(ratio, '.3f')} | "
            f"{_yn(honest)} | "
            f"{_yn(c.get('tightness', math.inf) <= TIGHTNESS_MAX)} | {_yn(ratio <= P95_HARM)} |"
        )  # fmt: skip
    return lines


def write_summary(plans: dict, out: Path, figures: list[str], diagnosis: str) -> None:
    L: list[str] = ["# Honest bound after GPS loss (#226)", ""]
    L += [
        f"**{KIND}.** Every number is a simulation of the committed `challenge-*` scenario "
        "entries; no real flight. The fix is the opt-in `ekf-honest` (`ekf-honest-guard` with the "
        "jump guard), ADR-0041 Proposed: `ekf-learned-noise` (ADR-0039) with the slow part of a "
        "radio's LTE range error carried as a Gauss-Markov state per emitter "
        "(`multipath_ratio` 1.0, `multipath_tau_s` 30 s, both `TBC`). No default changes.",
        "",
        "**Scenario keys:** `drone/<entry>/<n>c` is `challenge-drone-<entry>` (1 carrier, EARFCN "
        "2460) or `challenge-drone-hop-<entry>` cut to its first n of 13 carriers (as "
        "`analysis/stacked_fixes.py`); `timing/<entry>`, `approach/<entry>` the other legs; "
        "`/lte*k` the truth's LTE white noise and multipath sigma times k, the records still "
        "reporting 2 m (model mismatch). Guarded entries (`spoof-jump`, `meaconing`, "
        "`spoof-ramp`) "
        "score the `-guard` estimators.",
        "",
        "**Statistics.** *Above HPL*: share of 0.1 s epochs with true horizontal error > HPL, "
        "pooled over runs, over each whole 720 s run (T5's epochs, as the T5 figure, #222) and "
        "from the first fault to the run's end (the stricter; the bars use it). *Worst run*: the "
        "largest per-run share from the fault. *Hazardous*: error > 50 m alert limit with HPL "
        "≤ 50 m (`pnt.metrics`). *NEES mean*: horizontal NEES from the fault (2 if the "
        "covariance is honest). *Tightness*: at each second 0–300 s after GPS loss, median over "
        "runs of HPL / 95th percentile over runs of error; the median of that over the 300 s. "
        "*HPL ≤ 50 m*: share of epochs from the fault with HPL under the alert limit (the bound "
        "usable for the 50 m alert limit, `TBC`). *Unsafe*: median seconds from GPS loss to HPL "
        "over 50 m. *p95 worst*: ADR-0034's statistic, the worst second of the across-run 95th "
        "percentile of error over 0–300 s. *Tightness* and *p95 worst* count from GPS loss, "
        "or on the GNSS attack entries (jump, meaconing, ramp) from the attack's start.",
        "",
    ]
    if figures:
        L += [f"![{f}]({f})" for f in figures] + [""]
    st = plans.get("stress")
    if st:
        L += ["## Bars on held-out seeds (`stress`)", "", _provenance(st), ""]
        drone = {k for (k, _, _) in st["cells"] if k.startswith("drone/") and "lte*" not in k}
        keys = sorted(drone,
                      key=lambda k: _order((k, "", "")))  # fmt: skip
        bs = bars(st, keys)
        L += bars_table(bs) + [""]
        miss = [b for b in bs if not b["honest"]]
        L += [
            f"Honest on {len(bs) - len(miss)} of {len(bs)} drone scenario keys; T5's 99.9 % on "
            f"{sum(b['t5'] for b in bs)} of {len(bs)}; useful (where there is a GPS loss) on "
            f"{sum(bool(b['useful']) for b in bs)} of {sum(b['useful'] is not None for b in bs)}; "
            f"no harm on {sum(bool(b['no_harm']) for b in bs)} of "
            f"{sum(b['no_harm'] is not None for b in bs)}.",
            "",
            "## Before and after, every drone scenario key (`stress`)",
            "",
            ROW_HEAD,
            *rows_of(st, keys=set(keys)),
            "",
            "## Other legs and model mismatch (`stress`)",
            "",
            ROW_HEAD,
            *rows_of(
                st,
                keys={k for (k, _, _) in st["cells"] if not k.startswith("drone/") or "lte*" in k},
            ),  # fmt: skip
            "",
        ]
    sw = plans.get("sweep")
    if sw:
        L += ["## Sweep of the new settings (`sweep`)", "", _provenance(sw), "",
              *sweep_table(sw), ""]  # fmt: skip
    mh = plans.get("mhss")
    if mh:
        L += ["## Solution separation as the reference (`mhss`)", "", _provenance(mh), "",
              ROW_HEAD, *rows_of(mh), ""]  # fmt: skip
    if diagnosis:
        L += [diagnosis, ""]
    for plan, title in (
        ("measure", "Step 1: the existing estimators on tuning seeds (`measure`)"),
        ("diagnose", "Step 2: one term changed at a time, tuning seeds (`diagnose`)"),
        ("tune", "The fix on tuning seeds before the held-out run (`tune`)"),
    ):
        p = plans.get(plan)
        if p:
            L += [f"## {title}", "", _provenance(p), "", ROW_HEAD, *rows_of(p), ""]
    errs = sum(len(p["errors"]) for p in plans.values())
    L += [f"Runs that raised: {errs}.", ""]
    (out / "summary.md").write_text("\n".join(L))


def report(runs_dir: Path, out: Path) -> None:
    plans = load_plans(runs_dir)
    out.mkdir(parents=True, exist_ok=True)
    figures = []
    st = plans.get("stress")
    if st:
        d = st["docs"][0]
        tail = f"sim · seeds {d['seeds'][0]}–{d['seeds'][-1]} · commit {d['commit']}"
        f = figure(st, out, tail)
        if f:
            figures.append(f)
    write_summary(plans, out, figures, diagnosis(plans))
    print(f"wrote {out / 'summary.md'}", *figures)


def _c(p: dict | None, key: str, name: str, cfg: dict | None = None) -> dict:
    if not p:
        return {}
    return p["cells"].get((key, name, json.dumps(cfg or {}, sort_keys=True)), {})


def diagnosis(plans: dict) -> str:
    """#226 step 2, written from the `measure` and `diagnose` plans (tuning seeds only)."""
    me, dg = plans.get("measure"), plans.get("diagnose")
    if not (me and dg):
        return ""
    k1, k13 = "drone/outage/1c", "drone/outage/13c"
    e, ln, cl = (
        _c(me, k1, "ekf"),
        _c(me, k1, "ekf-learned-noise"),
        _c(me, k1, "ekf-calibrated-learned-noise"),
    )
    d = {(name, json.dumps(cfg or {}, sort_keys=True)): _c(dg, k1, name, cfg)
         for name, cfg in DIAGNOSE}  # fmt: skip
    d13 = {(name, json.dumps(cfg or {}, sort_keys=True)): _c(dg, k13, name, cfg)
           for name, cfg in DIAGNOSE}  # fmt: skip

    def line(dd, name, cfg, what):
        c = dd[(name, json.dumps(cfg or {}, sort_keys=True))]
        if not c:
            return f"| {what} | – | – | – | – | – |"
        return (f"| {what} | {_pct(c['above_win'])} | {_pct(c['worst_run'], 1)} | "
                f"{_num(c['nees_mean_win'], '.1f')} | {_pct(c['nees_over_k2_win'])} | "
                f"{_num(c.get('tightness', math.nan))} |")  # fmt: skip

    what = (  # in DIAGNOSE's order
        "`ekf-learned-noise` as it is",
        "(a) coasting process noise q_accel 1 → 1.5",
        "(c) tower clock random walk 0.2 → 1 m/√s",
        "slow range error as a state (`ekf-honest`, the fix)",
        "the fix + (a)",
    )
    td = truth_dynamics()
    psd = td["psd"]
    out = [
        "## Diagnosis (#226 step 2, tuning seeds 1000–1049 only)",
        "",
        f"1. **`ekf` believes the 2 m the records report** (true error 50 m white + 50 m "
        f"Gauss-Markov, 30 s; `challenge-drone`, `TBC`). After GPS loss its gate rejects most "
        f"LTE records and each one it accepts at 2 m collapses the covariance: on `{k1}` "
        f"error above HPL in {_pct(e.get('above_win'))} of epochs from GPS loss, worst run "
        f"{_pct(e.get('worst_run'), 1)} (`measure`). That is the T5 figure's 43.7 %. Learned "
        "noise (ADR-0039) removes most of it.",
        f"2. **`ekf-learned-noise` takes the whole error as white.** The size it learns is right, "
        "but an error correlated over 30 s is averaged down as if each 1 Hz record were "
        f"independent: on `{k1}` {_pct(ln.get('above_win'))} above HPL from loss, worst run "
        f"{_pct(ln.get('worst_run'), 1)}, mean horizontal NEES "
        f"{_num(d[('ekf-learned-noise', '{}')].get('nees_mean_win', math.nan), '.1f')} against "
        "2 for an honest covariance (`diagnose`): a model error, not a K error. "
        f"`ekf-calibrated-learned-noise`, which already has a multipath state per emitter, is at "
        f"{_pct(cl.get('above_win'))} on the same entry and seeds. With 13 carriers more cells "
        "average the slow errors of different towers and the escape is small already.",
        "3. **One term changed at a time** (`diagnose`, 50 seeds each):",
        "",
        "| Change to `ekf-learned-noise` | above HPL from loss, 1 carrier | worst run | NEES mean "
        "| NEES > K² | tightness |",
        "|---|---|---|---|---|---|",
        *[line(d, n, c, w) for (n, c), w in zip(DIAGNOSE, what, strict=True)],
        "",
        "| Same, 13 carriers | above HPL from loss | worst run | NEES mean | NEES > K² | "
        "tightness |",
        "|---|---|---|---|---|---|",
        *[line(d13, n, c, w) for (n, c), w in zip(DIAGNOSE, what, strict=True)],
        "",
        "   - (a) **Process noise is not the wrong term.** The circuit (8 m/s, 40 m corners) "
        f"has |a| rms {td['accel_rms']:.2f} m/s², max {td['accel_max']:.2f}. Per axis, "
        "var(velocity change over T) / T, which is q_accel² = 1 m²/s³ for the model: "
        + ", ".join(f"{T} s: {max(v):.2f}" for T, v in psd.items())
        + " (the larger axis; `challenge-drone-outage` seed 1000). Under 1 up to 10 s, up to "
        "2.2 at 60 s and above: the turns are correlated, not white. A larger q_accel helps "
        "the stretches just after loss but makes HPL larger everywhere.",
        "   - (b) **Covariance collapse on a few accepted ranges** is case 1 (2 m believed); "
        "with learned noise and its curvature term (ADR-0039) it is the averaging of a "
        "correlated error, row 1.",
        "   - (c) **Clock states:** a tower clock random walk 5 × larger changes the escape "
        "share little (row 3).",
        "   - (d) **K:** K_H = 5.33 on the largest horizontal sigma. With the slow error as a "
        "state the NEES mean is near 2 and NEES > K² rare, so the covariance, not K, was wrong; "
        "no empirical inflation is used.",
    ]
    return "\n".join(out)


# "No harm": the defaults' every estimate hashes the same on this branch as on `main`
HASH_SCENARIOS = (
    "challenge-drone-outage",
    "challenge-drone-spoof-jump",
    "challenge-timing-outage",
)
HASH_ESTIMATORS = ("baseline", "ekf", "ekf-calibrated", "ekf-imu", "ekf-mhss")


def default_hashes() -> list[str]:
    """`scenario seed estimator sha256[:16]` of every Estimate (msgpack) of each default
    estimator, seeds 0 and 1. Run on two trees and compare; this file need not exist on both:
    `python -c 'import sys; sys.path.insert(0, "<this tree>/analysis"); ...'`."""
    import hashlib

    import msgspec

    enc = msgspec.msgpack.Encoder(enc_hook=lambda o: o.item())
    out = []
    for scn in HASH_SCENARIOS:
        spec = load(scn)
        for seed in (0, 1):
            sim = generate(spec, seed=seed)
            for name in HASH_ESTIMATORS:
                h = hashlib.sha256()
                for e in estimate(name, sim.measurements, origin_llh=spec.get("origin_llh"),
                                  reference=sim.reference):  # fmt: skip
                    h.update(enc.encode(e))
                out.append(f"{scn} {seed} {name} {h.hexdigest()[:16]}")
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", choices=sorted(PLANS))
    ap.add_argument("--seeds", default="1000-1049")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--host", default=platform.node().split(".")[0])
    ap.add_argument("--out", type=Path, default=RUNS)
    ap.add_argument("--part", default="", help="plain|calibrated[:hop|:1c]: one part of the plan")
    ap.add_argument("--table", type=Path, help="print the table of one plan's pickle")
    ap.add_argument("--report", action="store_true", help="summary.md and the figure")
    ap.add_argument("--hashes", action="store_true", help="hash the defaults' estimates")
    args = ap.parse_args(argv)
    if args.table:
        table(args.table)
        return
    if args.hashes:
        print("\n".join(default_hashes()))
        return
    if args.report:
        report(args.out, OUT)
        return
    if args.plan:
        path = run_plan(
            args.plan, parse_seeds(args.seeds), args.jobs, args.host, args.out, args.part
        )
        table(path)


if __name__ == "__main__":
    main()
