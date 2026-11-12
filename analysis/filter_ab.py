"""Filter A/B (#286): named arms, each a dict of estimator settings on top of the control
(`ekf-honest` as registered), scored on real sessions with GPS cut in software and on the sim
drone leg, with the same functions as the studies they come from.

    python analysis/filter_ab.py real <session>-lte --cuts 99 149 199 249 299 --arms single \\
        --out analysis/results/runs/filter-ab/tune --jobs 4
    python analysis/filter_ab.py sim --legs 1c 13c --seeds 100-109 --arms single \\
        --out analysis/results/runs/filter-ab/tune --jobs 8
    python analysis/filter_ab.py table <json> ...          # markdown tables from results
    python analysis/filter_ab.py hashes --out <json>       # every registered default's estimates
    python analysis/filter_ab.py figure <real json> --rows control field no-lte ekf --out <png>

Real (`real_gps_cut.py`'s loading, cut, variants, LTE update counter, `score_cut` and
`aggregate`, so the scoring is that script's): error at 60, 120 and 300 s after each cut, median
(worst) over cuts; the p95 over 0-300 s; the share of withheld fixes with error above HPL; the
median HPL at 120 and 300 s; LTE updates after the cut accepted / unchecked / rejected; the
median horizontal speed 30-300 s after the cut (truth: 0, a static receiver). Positions are only
ever differences from a withheld fix: nothing written here holds a position or the origin.

Sim (`stacked_fixes.py`'s scenario entries, GPS-loss window, per-second curve, `p95_by_second`
and `worst_in`, so the statistic is ADR-0034's amendment): the worst second of 0-120 and 0-300 s
of the across-run 95th percentile; the share of epochs from GPS loss with error above HPL, pooled
(each run is cut 1 s after its 300 s window, as `stacked_fixes.py` cuts it); hazardous epochs
(`pnt.metrics.score`: error over 50 m while HPL is at or under it); HPL tightness as
`honest_bound.py` (#226) defines it: at each second after GPS loss, the median over runs of HPL
over the 95th percentile of error, then the median over 0-300 s.

Arms (`ARMS`): `control` is `ekf-honest`; every other arm changes one thing (`SINGLE`) or
combines arms (`COMBOS`). `REFERENCES` are always shown: no LTE, `main`'s default `ekf`,
`ekf-learned-noise`. `STATIONARY` (zero-velocity updates) is kept apart: it helps a receiver
that stops, and the sim drone never does.

Real sessions stay on this machine: pass their paths as arguments; results hold errors only.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

CONTROL = "ekf-honest"
CUTS_S = (99.0, 149.0, 199.0, 249.0, 299.0)
LEGS = {"1c": "challenge-drone-outage", "13c": "challenge-drone-hop-outage"}

# --- arms: settings on top of the control (`ekf.HONEST`) ----------------------------------------
SLOW = {"multipath_ratio": 0.0}  # the slow state sized in metres (`multipath_sigma_m`)


def slow(sigma_m: float, tau_s: float) -> dict:
    return {**SLOW, "multipath_sigma_m": sigma_m, "multipath_tau_s": tau_s}


SINGLE: dict[str, dict] = {
    "control": {},
    # 1. slow-error state from the real double differences (0040: spread 30-147 m per pair, wander
    # 171-437 m, slopes to 11 m/s): per-cell sigma and correlation time
    **{f"slow{s}-tau{t}": slow(s, t) for s in (50, 100, 150) for t in (60, 300)},
    # 2. velocity: IMU propagation; process noise sized to the platform
    "imu": {"motion": "imu"},
    "q0.3": {"q_accel": 0.3},
    "q0.1": {"q_accel": 0.1},
    # 3. geometry: LTE for position only with enough cells (or good geometry)
    "cells3": {"lte_min_cells": 3},
    "cells4": {"lte_min_cells": 4},
    "hdop3": {"lte_max_hdop": 3.0},
    "cells3-clock": {"lte_min_cells": 3, "lte_gate_mode": "clock"},
    # 4. robust weighting
    "huber1.5": {"lte_huber_k": 1.5},
    "huber2.5": {"lte_huber_k": 2.5},
    # 5. learned noise frozen while GNSS steers (its floor, the retold sigma, already holds in R)
    "freeze": {"noise_freeze_gnss": True},
    # 6. one shared bias when cells restart together (our timing step)
    "common-step": {"common_step_s": 1.5},
}
STATIONARY: dict[str, dict] = {
    "zupt": {"zupt_sigma_mps": 0.1},
    # stationary hold: arms only if GNSS showed rest over the last N s, disarms on the IMU
    **{
        f"hold{n}-v{v}-k{k}": {"hold_rest_s": float(n), "hold_speed_mps": v, "hold_k": float(k)}
        for n in (20, 30)
        for v in (0.3, 0.5)
        for k in (2, 3)
    },
}
# Round 2, after the single-arm table on tuning data (summary.md, *Combination round*)
CURV = {"curvature_inflate": True}  # a too-curved range kept with R grown by the term
COMBOS: dict[str, dict] = {
    # per-cell consistency before the loss (window s, threshold in the model's sigma, mode)
    **{
        f"consist{n}-k{k}-{mode}": {
            "lte_consistency_s": float(n),
            "lte_consistency_k": float(k),
            "lte_inconsistent_mode": mode,
        }
        for n in (30, 60, 120)
        for k in (2, 3, 4)
        for mode in ("cells3", "skip")
    },
    # the cell gate counted over a longer window
    **{
        f"cells{c}-w{w}": {"lte_min_cells": c, "lte_cells_window_s": float(w)}
        for c in (3, 4)
        for w in (3, 5)
    },
    "curv": CURV,
    "cells3+slow150-tau60": {"lte_min_cells": 3, **slow(150, 60)},
    "cells3+freeze": {"lte_min_cells": 3, "noise_freeze_gnss": True},
    "cells3+curv": {"lte_min_cells": 3, **CURV},
    "cells3-w3+curv": {"lte_min_cells": 3, "lte_cells_window_s": 3.0, **CURV},
    "cells3-w5+curv": {"lte_min_cells": 3, "lte_cells_window_s": 5.0, **CURV},
}
ARMS: dict[str, dict] = {**SINGLE, **STATIONARY, **COMBOS}
# Always shown: (registered estimator, LTE variant)
REFERENCES = {
    "no-lte": ("ekf", "none"),
    "ekf": ("ekf", "told-pr"),
    "ekf-learned-noise": ("ekf-learned-noise", "told-pr"),
}


# Stress rows: a registered estimator by name (the winner with the jump guard, ADR-0038)
STRESS_ROWS = {"control-guard": "ekf-honest-guard", "ekf-guard": "ekf-guard"}


def arm_set(spec: str) -> list[str]:
    """`--arms` value: "single", "stationary", "combos", "all" or arm names."""
    groups = {"single": SINGLE, "stationary": STATIONARY, "combos": COMBOS, "all": ARMS}
    return list(groups[spec]) if spec in groups else [spec]


def rows_for(arms: list[str], refs: bool = True) -> list[tuple[str, str, dict, str]]:
    """(label, base estimator, settings, LTE variant) for the references and the arms."""
    out = [(k, est, {}, var) for k, (est, var) in REFERENCES.items()] if refs else []
    for a in arms:
        if a in STRESS_ROWS:
            out.append((a, STRESS_ROWS[a], {}, "told-pr"))
            continue
        name, _, nolte = a.partition("@")  # "<arm>@nolte": the arm with LTE withheld
        if name not in ARMS or nolte not in ("", "nolte"):
            raise SystemExit(f"unknown arm {a!r} (known: {', '.join(ARMS)}, each @nolte)")
        out.append((a, CONTROL, ARMS[name], "none" if nolte else "told-pr"))
    return out


def build(base: str, settings: dict):
    """The registered `base` with `settings` on top of its own options."""
    from pnt import nav

    fn = nav.ESTIMATORS[base]
    if not settings:
        return fn
    keywords = dict(getattr(fn, "keywords", {}))
    return nav.configured(getattr(fn, "func", fn), **{**keywords, **settings})


@contextlib.contextmanager
def sigma_scale(scale: float):
    """ADR-0036's retold sigma (both parts) times `scale` while the block runs (stress only)."""
    from pnt.nav import told_sigma as ts

    saved = (ts.FLOOR_M, ts.SNR_TERM_M, ts.BINS, ts.SIGMA_CORR_M)
    if scale != 1.0:
        ts.FLOOR_M, ts.SNR_TERM_M = ts.FLOOR_M * scale, ts.SNR_TERM_M * scale
        ts.BINS = tuple((lo, s * scale) for lo, s in ts.BINS)
        ts.SIGMA_CORR_M *= scale
    try:
        yield
    finally:
        ts.FLOOR_M, ts.SNR_TERM_M, ts.BINS, ts.SIGMA_CORR_M = saved


@contextlib.contextmanager
def filter_counts():
    """The last EKF built while the block runs, for its counters (`holder["ekf"]`)."""
    from pnt.nav import ekf as ekf_module

    holder: dict = {}
    init = ekf_module.EKF.__init__

    def kept(self, *a, **k):
        init(self, *a, **k)
        holder["ekf"] = self

    ekf_module.EKF.__init__ = kept
    try:
        yield holder
    finally:
        ekf_module.EKF.__init__ = init


def strongest_cells(meas, n: int = 2) -> set[str]:
    """The `n` LTE cells with the highest median SNR over the session."""
    snr: dict[str, list[float]] = {}
    for m in meas:
        if m.source == "lte" and m.kind == "pseudorange" and "snr_db" in m.meta:
            snr.setdefault(m.emitter, []).append(float(m.meta["snr_db"]))
    return set(sorted(snr, key=lambda c: -np.median(snr[c]))[:n])


# --- real ---------------------------------------------------------------------------------------
def real_task(
    path: str,
    label: str,
    base: str,
    settings: dict,
    variant: str,
    cut_s: float,
    stress: dict | None = None,
) -> dict:
    """One replay with GNSS cut at `cut_s`, scored by `real_gps_cut.score_cut`."""
    import real_gps_cut as rgc

    from pnt import nav

    stress = stress or {}
    meas, t0, origin = rgc.load(path)
    fix_t, fix_pos = rgc.gps_fixes(meas)
    cut_ns = t0 + round(cut_s * 1e9)
    fed = rgc.lte_variant(rgc.cut_gnss(meas, t0, cut_s), variant)
    if stress.get("cells"):
        keep = strongest_cells(meas, stress["cells"])
        fed = [m for m in fed if m.source != "lte" or m.emitter in keep]
    with (
        sigma_scale(stress.get("sigma_scale", 1.0)),
        rgc.count_lte_updates(cut_ns) as lte,
        filter_counts() as kf,
    ):
        est = list(nav.estimate(build(base, settings), fed, origin_llh=origin))
    k = kf["ekf"]
    out_counts = {
        "hold_updates": k.hold_updates,
        "hold_armed": len(k.hold_armed_at),
        "hold_disarmed": len(k.hold_disarmed_at),
        "zupts": k.zupts,
        "geometry_held": k.geometry_held,
    }
    est_t = np.array([e.t_ns for e in est], dtype=np.int64)
    est_pos = np.array([e.pos_enu for e in est], dtype=float)
    est_hpl = np.array([e.hpl_m for e in est], dtype=float)
    out = {"estimator": label, "variant": variant, "cut_s": cut_s}
    out.update(rgc.score_cut(est_t, est_pos, est_hpl, fix_t, fix_pos, cut_ns))
    v = [math.hypot(*e.vel_enu[:2]) for e in est if cut_ns + 30e9 <= e.t_ns <= cut_ns + 300e9]
    out["speed_median_m_s"] = float(np.median(v)) if v else math.nan
    out["lte_updates"] = lte
    out["counts"] = out_counts
    out["pre_p95_m"], out["pre_gnss_excluded"] = math.nan, math.nan  # not scored here
    return out


def real_aggregate(runs: list[dict]) -> dict:
    """Per row: `real_gps_cut.aggregate`, plus the median over cuts of each cut's median speed."""
    import real_gps_cut as rgc

    agg = rgc.aggregate(runs)
    out = {}
    for key, a in agg.items():
        label = key.split("|")[0]
        mine = [r for r in runs if r["estimator"] == label]
        a["speed_median_m_s"] = float(np.median([r["speed_median_m_s"] for r in mine]))
        out[label] = a
    return out


def run_real(
    path: str, arms: list[str], cuts: list[float], jobs: int, stress: dict | None, refs: bool
) -> dict:
    import real_gps_cut as rgc

    from pnt.experiments import _map

    tasks = [
        (path, lab, base, st, var, c, stress)
        for lab, base, st, var in rows_for(arms, refs)
        for c in cuts
    ]
    t0 = time.perf_counter()
    runs = _map(real_task, tasks, jobs)
    return {
        "kind": "replay of a real session, GPS cut in software",
        "session": Path(path).name,
        "commit": rgc._commit(),
        "cuts_s": list(cuts),
        "stress": stress or {},
        "rows": {
            lab: {"base": base, "settings": st, "variant": var}
            for lab, base, st, var in rows_for(arms, refs)
        },
        "elapsed_min": (time.perf_counter() - t0) / 60,
        "aggregate": real_aggregate(runs),
        "runs": runs,
    }


# --- sim ----------------------------------------------------------------------------------------
TIGHT_WINDOW_S = 300  # honest_bound.py (#226): tightness over 0-300 s after GPS loss


def sim_spec(leg: str) -> dict:
    """A `stacked_fixes.py` entry key ("1c", "13c", "nolte", "jump-1c") or a scenario name."""
    import copy

    import stacked_fixes as sf

    from pnt.sim.scenario import load

    try:
        return sf.spec_of(leg)
    except KeyError:
        return copy.deepcopy(load(leg))


def sim_task(leg: str, seed: int, rows: list[tuple[str, str, dict]]) -> list[dict]:
    """Every row on one seed's records of `leg`, scored from GPS loss (or the jump) as
    `stacked_fixes.run_task` scores it, plus the epochs above HPL and the per-second HPL."""
    import stacked_fixes as sf

    from pnt.metrics import score
    from pnt.nav import estimate
    from pnt.sim.scenario import T0_NS, generate

    spec = sim_spec(leg)
    sim = generate(spec, seed=seed)
    try:
        start, offset = sf.window_start(spec)
    except ValueError:  # nominal: no GPS loss, no jump; score the whole run
        start, offset = None, None
    records = sim.measurements
    if start is not None:
        records = [m for m in records if m.t_ns <= start + sf.CUT_AFTER_S * 1_000_000_000]
    truth = {g.t_ns: g for g in sim.truth}
    out = []
    for label, base, settings in rows:
        t_run = time.perf_counter()
        est = list(
            estimate(
                build(base, settings),
                records,
                origin_llh=spec.get("origin_llh"),
                reference=sim.reference,
            )
        )
        m = score(est, sim.truth, spec, T0_NS)
        pairs = [(e, truth[e.t_ns]) for e in est if e.t_ns in truth]
        t = np.array([e.t_ns for e, _ in pairs])
        err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
        hpl = np.array([e.hpl_m for e, _ in pairs])
        r = {
            "leg": leg,
            "row": label,
            "seed": seed,
            "hazardous": int(m.hazardous_epochs),
            "false_alarms_per_h": float(m.false_alarms_per_h),
        }
        win = t >= start if start is not None else np.ones(len(t), bool)
        r["n_win"], r["above_win"] = int(win.sum()), int(np.sum((err > hpl) & win))
        r["hash"] = estimate_hash(est)
        if start is not None:
            at = {int(tt): i for i, tt in enumerate(t)}
            idx = [at[start + k * 1_000_000_000] for k in range(sf.HORIZON_S + 1)]
            r["curve"] = [round(float(err[i]), 2) for i in idx]
            r["hpl_curve"] = [round(float(hpl[i]), 2) for i in idx]
        if offset is not None:
            i = at[start + int(sf.SPOOF_AT_S * 1e9)]
            e, g = pairs[i]
            spoofed = (g.pos_enu[0] + offset[0], g.pos_enu[1] + offset[1])
            r["on_spoof_120s"] = bool(
                math.dist(e.pos_enu[:2], spoofed) < math.hypot(*offset[:2]) / 2
            )
        r["run_s"] = round(time.perf_counter() - t_run, 1)
        out.append(r)
    return out


def sim_aggregate(runs: list[dict]) -> dict:
    """Per (leg, row): `stacked_fixes.worst_in` of `p95_by_second`, pooled epochs above HPL from
    GPS loss, hazardous epochs, tightness (honest_bound.py's definition)."""
    import stacked_fixes as sf

    out: dict = {}
    for leg, row in dict.fromkeys((r["leg"], r["row"]) for r in runs):
        mine = sorted(
            (r for r in runs if r["leg"] == leg and r["row"] == row), key=lambda r: r["seed"]
        )
        a = {
            "runs": len(mine),
            "seeds": [r["seed"] for r in mine],
            "above_hpl": sum(r["above_win"] for r in mine) / max(sum(r["n_win"] for r in mine), 1),
            "worst_run_above_hpl": max(r["above_win"] / max(r["n_win"], 1) for r in mine),
            "hazardous": int(sum(r["hazardous"] for r in mine)),
            "hazardous_seeds": [r["seed"] for r in mine if r["hazardous"]],
            "false_alarms_per_h": float(np.nanmean([r["false_alarms_per_h"] for r in mine])),
        }
        if "curve" in mine[0]:
            p95 = sf.p95_by_second([r["curve"] for r in mine])
            a["worst_120s_m"] = sf.worst_in(p95, 120)
            a["worst_300s_m"] = sf.worst_in(p95, 300)
            hmed = np.median([r["hpl_curve"] for r in mine], axis=0)
            a["tightness"] = float(np.median((hmed / p95)[: TIGHT_WINDOW_S + 1]))
            a["p95_curve_m"] = [round(float(x), 1) for x in p95]
        if "on_spoof_120s" in mine[0]:
            a["on_spoof_120s"] = int(sum(r["on_spoof_120s"] for r in mine))
        out[f"{leg}|{row}"] = a
    return out


def sim_rows(arms: list[str], refs: bool, extra: dict | None = None) -> list[tuple]:
    """(label, base, settings) per row; no LTE runs on its own entry (`sim_task` "nolte")."""
    rows = [
        (lab, base, {**st, **(extra or {})})
        for lab, base, st, var in rows_for(arms, refs)
        if var != "none"
    ]
    return rows


def run_sim(
    legs: list[str],
    seeds: list[int],
    arms: list[str],
    jobs: int,
    refs: bool,
    extra: dict | None = None,
) -> dict:
    import real_gps_cut as rgc

    from pnt.experiments import _map

    rows = sim_rows(arms, refs, extra)
    tasks = [(leg, s, rows) for leg in legs for s in seeds]
    if refs and any(leg in LEGS for leg in legs):  # no LTE: the same entry without LTE records
        tasks += [("nolte", s, [("no-lte", "ekf", {})]) for s in seeds]
    t0 = time.perf_counter()
    runs = [r for rs in _map(sim_task, tasks, jobs) for r in rs]
    return {
        "kind": "sim, every value TBC (ADR-0015)",
        "legs": {leg: LEGS.get(leg, leg) for leg in legs},
        "seeds": seeds,
        "commit": rgc._commit(),
        "extra": extra or {},
        "rows": {lab: {"base": base, "settings": st} for lab, base, st in rows},
        "elapsed_min": (time.perf_counter() - t0) / 60,
        "aggregate": sim_aggregate(runs),
        "runs": [{k: v for k, v in r.items() if k not in ("curve", "hpl_curve")} for r in runs],
    }


# --- hashes: every default registered on main stays byte-identical ------------------------------
HASH_SCENARIOS = ("challenge-drone-outage", "challenge-drone-spoof-jump", "realistic-long-outage")
# The registry on origin/main at 6a2c0f1 (#286's base): these must not change
MAIN_ESTIMATORS = (
    "baseline",
    "ekf",
    "ekf-calibrated",
    "ekf-calibrated-measured",
    "ekf-base",
    "ekf-mhss",
    "ekf-mhss-beacon",
    "ekf-imu",
    "ekf-base-imu",
    "ekf-guard",
    "ekf-imu-guard",
    "ekf-calibrated-guard",
    "ekf-map",
    "ekf-spoof",
    "ekf-calibrated-spoof",
    "ekf-imu-spoof",
    "ekf-measured-sigma",
    "ekf-calibrated-measured-sigma",
)


def estimate_hash(estimates) -> str:
    """sha256 of every field of every estimate (msgspec JSON), first 16 hex digits."""
    import msgspec

    enc = msgspec.json.Encoder(enc_hook=lambda x: x.item() if hasattr(x, "item") else repr(x))
    h = hashlib.sha256()
    for e in estimates:
        h.update(enc.encode(e))
    return h.hexdigest()[:16]


def hash_task(scenario: str, seed: int, names: tuple[str, ...]) -> dict:
    from pnt.nav import estimate
    from pnt.sim.scenario import generate, load

    spec = load(scenario)
    run = generate(spec, seed=seed)
    return {
        f"{scenario}|{seed}|{n}": estimate_hash(
            estimate(
                n, run.measurements, origin_llh=spec.get("origin_llh"), reference=run.reference
            )
        )
        for n in names
    }


# --- tables -------------------------------------------------------------------------------------
def _m(x: float) -> str:
    if x != x:
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


def real_table(data: dict, rows: list[str] | None = None) -> list[str]:
    agg = data["aggregate"]
    lines = [
        "| Row | 60 s | 120 s | 300 s | p95 0–300 s (worst cut) | Error > HPL | HPL 120 s | "
        "HPL 300 s | LTE after cut: accepted / unchecked / rejected | Speed after cut (m/s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lab in rows or list(agg):
        if lab not in agg:
            continue
        a = agg[lab]
        at = [
            f"{_m(a[f'err_{s}s_m']['median'])} ({_m(a[f'err_{s}s_m']['worst'])})"
            for s in (60, 120, 300)
        ]
        u = a["lte_updates"]["after"]
        lte = (
            "–"
            if data["rows"][lab]["variant"] == "none"
            else (f"{u['accepted']:,} / {u['unchecked']:,} / {u['rejected']:,}")
        )
        lines.append(
            f"| {lab} | {' | '.join(at)} | {_m(a['p95_300s_m']['worst'])} | "
            f"{a['above_hpl']:.1%} ({a['misleading']:,} of {a['fixes']:,}) | "
            f"{_m(a['hpl_120s_m']['median'])} | {_m(a['hpl_300s_m']['median'])} | {lte} | "
            f"{a['speed_median_m_s']:.2f} |"
        )
    return lines


def sim_table(data: dict, rows: list[str] | None = None) -> list[str]:
    agg = data["aggregate"]
    legs = list(data["legs"])
    head = (
        "| Row | "
        + " | ".join(
            f"{leg}: worst-second p95 0–120 / 0–300 s (m) | {leg}: above HPL | {leg}: hazardous | "
            f"{leg}: tightness"
            for leg in legs
        )
        + " |"
    )
    lines = [head, "|---|" + "---|---|---|---|" * len(legs)]
    labels = rows or list(dict.fromkeys(k.split("|")[1] for k in agg))
    for lab in labels:
        cells = []
        for leg in legs:
            a = agg.get(f"{leg}|{lab}") or agg.get(f"nolte|{lab}")
            if a is None:
                cells += ["—"] * 4
                continue
            cells += [
                f"{_m(a['worst_120s_m'])} / {_m(a['worst_300s_m'])}"
                if "worst_120s_m" in a
                else "—",
                f"{a['above_hpl']:.2%}",
                f"{a['hazardous']:,}",
                f"{a['tightness']:.2f}" if "tightness" in a else "—",
            ]
        lines.append(f"| {lab} | " + " | ".join(cells) + " |")
    return lines


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def figure(data: dict, rows: list[str], out: Path) -> None:
    """Error after the cut against time, median of the cuts, one line per row, 50 m line:
    `real_gps_cut.plot_rows` on these rows (relative metres only)."""
    import real_gps_cut as rgc

    runs = [r for r in data["runs"] if r["estimator"] in rows]
    agg = {f"{lab}|{data['rows'][lab]['variant']}": {} for lab in rows}
    summary = {
        "aggregate": agg,
        "horizon_s": rgc.HORIZON_S,
        "session": data["session"],
        "cuts_s": data["cuts_s"],
        "frontend_commit": data.get("frontend_commit", "?"),
        "commit": data["commit"],
    }
    rgc.plot_rows(runs, summary, out)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("real")
    r.add_argument("session")
    r.add_argument("--cuts", type=float, nargs="+", default=list(CUTS_S))
    s = sub.add_parser("sim")
    s.add_argument("--legs", nargs="+", default=list(LEGS))
    s.add_argument("--seeds", default="100-109")
    s.add_argument("--extra", default="{}", help="JSON settings added to every LTE row (stress)")
    for p in (r, s):
        p.add_argument("--arms", nargs="+", default=["single"])
        p.add_argument("--no-refs", action="store_true", help="arms only, no reference rows")
        p.add_argument("--jobs", type=int, default=4)
        p.add_argument("--out", required=True, help="JSON file to write")
    r.add_argument("--stress", default="{}", help='JSON: {"cells": 2} or {"sigma_scale": 0.5}')
    t = sub.add_parser("table")
    t.add_argument("files", nargs="+")
    t.add_argument("--rows", nargs="+")
    h = sub.add_parser("hashes")
    h.add_argument("--seeds", default="0,1")
    h.add_argument("--names", nargs="+", default=list(MAIN_ESTIMATORS))
    h.add_argument("--jobs", type=int, default=4)
    h.add_argument("--out", required=True)
    f = sub.add_parser("figure")
    f.add_argument("file")
    f.add_argument("--rows", nargs="+", required=True)
    f.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.cmd in ("real", "sim"):
        arms = [a for spec in args.arms for a in arm_set(spec)]
        if args.cmd == "real":
            data = run_real(
                args.session, arms, args.cuts, args.jobs, json.loads(args.stress), not args.no_refs
            )
            lines = real_table(data)
        else:
            data = run_sim(
                args.legs,
                parse_seeds(args.seeds),
                arms,
                args.jobs,
                not args.no_refs,
                json.loads(args.extra),
            )
            lines = sim_table(data)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data) + "\n")
        print("\n".join(lines))
        print(f"wrote {args.out} ({data['elapsed_min']:.1f} min, {data['commit']})")
    elif args.cmd == "table":
        for name in args.files:
            data = json.loads(Path(name).read_text())
            print(f"\n{name} ({data['commit']})\n")
            table = real_table if "session" in data else sim_table
            print("\n".join(table(data, args.rows)))
    elif args.cmd == "hashes":
        from pnt.experiments import _map

        tasks = [
            (sc, sd, tuple(args.names)) for sc in HASH_SCENARIOS for sd in parse_seeds(args.seeds)
        ]
        out: dict = {}
        for part in _map(hash_task, tasks, args.jobs):
            out.update(part)
        Path(args.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(f"wrote {args.out}: {len(out)} hashes")
    else:
        figure(json.loads(Path(args.file).read_text()), args.rows, Path(args.out))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
