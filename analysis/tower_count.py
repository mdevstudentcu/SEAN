"""How many towers does the drone need once GPS is lost? (#208), sim.

One command, from a clean commit:

    python analysis/tower_count.py --seeds 20 --jobs 3

writes `analysis/results/tower-count/`: `summary.md` (the tables), `summary.json` (every number
in them, and the per-second 95th percentile curves at 5 s steps) and `tower_count.png`. The
per-run error curves (`runs.json`, a few MB) go to the git-ignored `analysis/results/runs/
tower-count/`; `--redraw` rebuilds the summary and figure from them.

The leg: the `challenge-drone-outage` scenario (ADR-0030, the benchmark's UC-01 leg) as
committed, with three changes, and no scenario file added:
- `duration_s` 361: 60 s of GPS, then the 300 s T1 window and one second (the committed run's
  outage lasts 600 s; the T1 slice is its first 300 s).
- `sources.lte.hearing` = {model: range, hearing_km: 10}: every sector of Rogers EARFCN 2460 in
  `lte-cells-ottawa.csv` is on air (the table's 10 km radius), so a subset can be chosen. The
  committed link-budget hearing hears 1 to 3 sectors at a time (its -13 dB near-far floor).
- The error model (`ERRORS`): `committed` as in the YAML (the records report 2 m while the true
  noise is 50 m plus 50 m multipath, ADR-0030 point 6); `honest`, the same records reporting the
  true 50 m; `clean`, 5 m white noise reported as 5 m, no multipath and no table position error,
  to show geometry alone. Tower clocks, dropouts (each eNB on air 75 % of the time, in 30 s
  blocks) and the dongle clock are as committed in all three.

Each seed's records are generated once per error model. Every variant keeps a subset of them,
so every variant of a seed sees the same draws (paired):
- Towers: N registered eNB sites (a site is a mast; its sectors share one clock, ADR-0022). Only
  sectors the lookup can match are kept (`pnt.nav.cells`: a PCI another eNB reuses is dropped).
  Two rules (`choose`): `strongest`, the N sites with the highest median link-budget power over
  the route (the committed `LinkBudget` defaults, no dropouts), the ones a receiver would hear
  first; `random`, N sites drawn per seed from the matched sites within 3 km of the origin.
  N = 0 keeps no tower (dead reckoning on what is left); `all` keeps every matched site within
  3 km of the origin (17 of the table's 86). The other 69 are 25 dB or more below the strongest
  site's median power on this route, so the front end's 13 dB near-far floor never lets them in,
  and with them a filter run takes 20 to 30 s instead of 1 to 3.
- Aiding (`AIDING`): towers only (`ekf`, constant velocity, barometer and IMU records dropped);
  + barometer (`ekf`); + IMU (`ekf-imu`, barometer dropped); + barometer + IMU (`ekf-imu`). GNSS
  is there until the loss in every variant.

Metric (ADR-0034's amendment, the owners' T1 statistic): at each second 0 to 300 s after GPS
loss, the 95th percentile across runs of the horizontal error; the worst second of the window
decides. `holds 25 m` is how long that curve stays at or under 25 m from the loss (300 means the
whole window), likewise 50 m; the fallback is <= 50 m for 120 s.

Geometry (`dops`): snapshot HDOP of the N strongest sites along the route, with unit range
noise, the towers' own clocks taken as known (learned while GPS was good), for (a) unknown
receiver clock and the barometer giving height, (b) unknown clock and height, and (c) the
barometer and a held receiver clock. Fewer sites than unknowns is no fix.

Every value is TBC (ADR-0015); this is sim, and the leg's LTE model is `placeholder` in
`verification.md`'s *Sim validity* table.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.nav import estimate
from pnt.nav.cells import MATCHED, CellTable
from pnt.sim import lte_front_end as fe
from pnt.sim import trajectory
from pnt.sim.scenario import REFERENCE_DIR, T0_NS, generate, load

OUT = Path(__file__).resolve().parent / "results" / "tower-count"
RUNS = Path(__file__).resolve().parent / "results" / "runs" / "tower-count"
LEG = "challenge-drone-outage"
LOSS_S = 60.0  # the committed outage's start
WINDOW_S = 300  # T1
DURATION_S = LOSS_S + WINDOW_S + 1.0
HEARING = {"model": "range", "hearing_km": 10.0}
COUNTS = (0, 1, 2, 3, 4, 6, "all")
RANDOM_COUNTS = (3, 4, 6)
RANDOM_POOL_KM = 3.0
ERRORS = ("committed", "honest", "clean")
# name -> (estimator, keep the barometer, keep the IMU)
AIDING = {
    "towers": ("ekf", False, False),
    "baro": ("ekf", True, False),
    "imu": ("ekf-imu", False, True),
    "baro+imu": ("ekf-imu", True, True),
}
TARGETS_M = (25.0, 50.0)
FALLBACK = (50.0, 120)  # ADR-0034: <= 50 m for >= 120 s
NO_OUTPUT_M = 1e9  # stands for a second with no estimate; reported as None
CURVE_STEP_S = 5  # summary.json keeps the p95 curves at this step
# Categorical slots 1 to 4, fixed order, recessive ink (analysis/sensitivity.py)
SLOTS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
MARKERS = ("o", "s", "^", "D")
INK, GRID = "#52514e", "#e4e3df"


def leg_spec(errors: str) -> dict:
    """The committed leg with the study's three changes (module docstring)."""
    spec = copy.deepcopy(load(LEG))
    spec["duration_s"] = DURATION_S
    lte = spec["sources"]["lte"]
    lte["hearing"] = dict(HEARING)
    if errors == "honest":
        lte.pop("told_sigma_m")  # the records report the true sigma_m
    elif errors == "clean":
        lte.pop("told_sigma_m")
        lte["sigma_m"] = 5.0
        lte.pop("multipath")
        lte["told_position_sigma_m"] = 0.0
    elif errors != "committed":
        raise ValueError(f"errors must be one of {ERRORS}, not {errors!r}")
    spec["name"] = f"{LEG}:towers:{errors}"
    return spec


def sites(spec: dict) -> dict[int, dict]:
    """Matched sites of the leg's EARFCN: eNB -> {emitters, enu (first matched sector, m),
    km (from the origin), power_dbm (median over the route of its strongest matched sector)}."""
    lte, origin = spec["sources"]["lte"], spec["origin_llh"]
    earfcn = int(lte["cells_from"]["earfcn"])
    secs = fe.sectors(REFERENCE_DIR / lte["cells_from"]["file"], earfcn)
    table = CellTable.load(REFERENCE_DIR / lte["cells_from"]["file"])
    ok = [table.associate(earfcn, s.pci, origin)[0] == MATCHED for s in secs]
    enu = fe.table_enu(secs, origin)
    pos = route(spec)
    power = fe.rx_power_dbm(secs, enu, pos, fe.LinkBudget())
    out: dict[int, dict] = {}
    for i, s in enumerate(secs):
        if not ok[i]:
            continue
        site = out.setdefault(s.enb_id, {"emitters": [], "cols": [], "enu": enu[i]})
        site["emitters"].append(s.emitter)
        site["cols"].append(i)
    for site in out.values():
        site["power_dbm"] = float(np.median(power[:, site.pop("cols")].max(axis=1)))
        site["km"] = float(np.linalg.norm(site["enu"][:2]) / 1e3)
    return out


def route(spec: dict, step_s: float = 1.0) -> np.ndarray:
    """The receiver's true ENU position (m) at `step_s` over the run."""
    traj = {**spec["trajectory"], "_origin_llh": spec["origin_llh"]}
    return trajectory.make(traj, np.arange(0.0, float(spec["duration_s"]), step_s))[0]


def choose(site_info: dict[int, dict], rule: str, n: int | str, seed: int = 0) -> list[int]:
    """The eNBs a variant keeps (module docstring). `random` draws from its own stream per
    (seed, n), so the same seed and N give the same subset whatever else is run."""
    pool = sorted(e for e in site_info if site_info[e]["km"] <= RANDOM_POOL_KM)
    if n == "all":
        return pool
    if rule == "strongest":
        ranked = sorted(site_info, key=lambda e: (-site_info[e]["power_dbm"], e))
        return ranked[:n]
    if rule == "random":
        if n > len(pool):
            raise ValueError(f"only {len(pool)} sites within {RANDOM_POOL_KM} km, not {n}")
        rng = np.random.default_rng([seed, n, 208])
        return sorted(int(e) for e in rng.choice(pool, n, replace=False))
    raise ValueError(f"rule must be strongest or random, not {rule!r}")


def keep(measurements, emitters: set[str], baro: bool, imu: bool) -> list:
    """The records a variant sees: LTE only from `emitters`, the barometer and IMU if kept."""
    out = []
    for m in measurements:
        if m.source == "lte" and m.emitter not in emitters:
            continue
        if m.source == "baro" and not baro:
            continue
        if m.source == "imu" and not imu:
            continue
        out.append(m)
    return out


def error_curve(estimates, truth) -> np.ndarray:
    """Horizontal error (m) at each second 0..WINDOW_S after the loss: the first estimate at or
    after that second, NaN past the last."""
    truth = {g.t_ns: g for g in truth}
    pairs = [(e, truth[e.t_ns]) for e in estimates if e.t_ns in truth]
    t = np.array([(e.t_ns - T0_NS) / 1e9 for e, _ in pairs])
    err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
    i = np.searchsorted(t, LOSS_S + np.arange(WINDOW_S + 1) - 1e-6)
    out = np.full(WINDOW_S + 1, np.nan)
    ok = i < len(t)
    out[ok] = err[i[ok]]
    return out


def t1(errors: np.ndarray, window_s: int = WINDOW_S) -> dict:
    """ADR-0034's statistic over runs x seconds-after-loss: the 95th percentile across runs at
    each second, its worst second over 0..`window_s`, and how long it holds each target (the
    first second over it; `window_s` if it never is). A second with no estimate (NaN: the filter
    had nothing to update on) counts as `NO_OUTPUT_M`, so it fails every target."""
    errors = np.where(np.isnan(errors), NO_OUTPUT_M, errors)
    p95 = np.percentile(errors, 95, axis=0)[: window_s + 1]
    out = {"p95": p95, "worst_m": float(np.max(p95)), "runs": int(errors.shape[0])}
    for x in TARGETS_M:
        over = np.flatnonzero(p95 > x)
        out[f"holds_{x:g}m_s"] = int(over[0]) if over.size else window_s
    lim, dur = FALLBACK
    out["fallback_met"] = bool(np.max(p95[: dur + 1]) <= lim)
    return out


def dops(site_enu: np.ndarray, rx_enu: np.ndarray) -> dict[str, np.ndarray]:
    """Snapshot HDOP per receiver position, unit range noise, tower clocks known, for the three
    cases of the module docstring. NaN where the sites are fewer than the unknowns."""
    out = {}
    los = rx_enu[:, None, :] - site_enu[None, :, :]
    u = los / np.linalg.norm(los, axis=2, keepdims=True)  # (epoch, site, 3)
    ones = np.ones(u.shape[:2] + (1,))
    cases = {
        "baro": np.concatenate([u[..., :2], ones], axis=2),
        "no_baro": np.concatenate([u, ones], axis=2),
        "baro_held_clock": u[..., :2],
    }
    for name, h in cases.items():
        hdop = np.full(len(rx_enu), np.nan)
        if h.shape[1] >= h.shape[2]:
            for k in range(len(rx_enu)):
                q = np.linalg.pinv(h[k].T @ h[k])
                hdop[k] = math.sqrt(q[0, 0] + q[1, 1])
        out[name] = hdop
    return out


def variants() -> list[tuple[str, int | str]]:
    """(rule, N) pairs run per seed; N = 0 and `all` are rule-free (named `strongest`)."""
    return [("strongest", n) for n in COUNTS] + [("random", n) for n in RANDOM_COUNTS]


def run_job(job: tuple[str, int]) -> dict:
    """One seed of one error model: every (rule, N, aiding) variant on the same records."""
    errors, seed = job
    spec = leg_spec(errors)
    info = sites(spec)
    sim = generate(spec, seed=seed)
    out = {"errors": errors, "seed": seed, "curves": {}, "on_air_3": {}, "runtime_s": {}}
    for rule, n in variants():
        enbs = choose(info, rule, n, seed)
        emitters = {e for enb in enbs for e in info[enb]["emitters"]}
        on_air = _sites_per_second(sim.measurements, emitters, info)
        out["on_air_3"][f"{rule}:{n}"] = float(np.mean(on_air >= 3))
        for aid, (name, baro, imu) in AIDING.items():
            t0 = time.time()
            meas = keep(sim.measurements, emitters, baro, imu)
            est = list(estimate(name, meas, origin_llh=spec["origin_llh"]))
            out["curves"][f"{rule}:{n}:{aid}"] = error_curve(est, sim.truth).tolist()
            out["runtime_s"][f"{rule}:{n}:{aid}"] = round(time.time() - t0, 2)
    return out


def _sites_per_second(measurements, emitters: set[str], info: dict) -> np.ndarray:
    """Distinct kept sites with a record in each second of the T1 window."""
    site_of = {e: enb for enb, s in info.items() for e in s["emitters"]}
    seen = [set() for _ in range(WINDOW_S + 1)]
    for m in measurements:
        if m.source == "lte" and m.emitter in emitters:
            k = int((m.t_ns - T0_NS) / 1e9 - LOSS_S)
            if 0 <= k <= WINDOW_S:
                seen[k].add(site_of[m.emitter])
    return np.array([len(s) for s in seen])


def run_all(seeds, jobs: int) -> list[dict]:
    work = [(e, s) for e in ERRORS for s in seeds]
    if jobs <= 1:
        return [run_job(w) for w in work]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(run_job, work))


def collect(results: list[dict]) -> dict:
    """Per (errors, rule, N, aiding): the T1 statistic over seeds; per (rule, N): the median
    share of the window with three or more sites on air."""
    rows, on_air = [], {}
    for errors in ERRORS:
        rs = sorted((r for r in results if r["errors"] == errors), key=lambda r: r["seed"])
        if not rs:
            continue
        for rule, n in variants():
            for aid in AIDING:
                key = f"{rule}:{n}:{aid}"
                stat = t1(np.array([r["curves"][key] for r in rs]))
                rows.append(
                    {
                        "errors": errors,
                        "rule": rule,
                        "n": n,
                        "aiding": aid,
                        "runs": stat["runs"],
                        "worst_p95_m": _m(stat["worst_m"]),
                        "holds_25m_s": stat["holds_25m_s"],
                        "holds_50m_s": stat["holds_50m_s"],
                        "fallback_met": stat["fallback_met"],
                        "p95_curve_m": [_m(x) for x in stat["p95"][::CURVE_STEP_S]],
                    }
                )
            if errors == ERRORS[0] or f"{rule}:{n}" not in on_air:
                shares = [r["on_air_3"][f"{rule}:{n}"] for r in rs]
                on_air[f"{rule}:{n}"] = round(float(np.median(shares)), 3)
    return {"rows": rows, "on_air_3": on_air}


def geometry(spec: dict) -> dict:
    """Median and worst snapshot HDOP over the route for the N strongest sites."""
    info = sites(spec)
    rx = route(spec)
    out = {}
    for n in COUNTS[1:]:
        enbs = choose(info, "strongest", n)
        d = dops(np.array([info[e]["enu"] for e in enbs]), rx)
        out[str(n)] = {
            case: (
                None
                if np.all(np.isnan(h))
                else {
                    "median": round(float(np.nanmedian(h)), 2),
                    "max": round(float(np.nanmax(h)), 1),
                }
            )
            for case, h in d.items()
        }
    ranked = choose(info, "strongest", 6)
    out["strongest"] = [
        {"enb": e, "km": round(info[e]["km"], 2), "power_dbm": round(info[e]["power_dbm"], 1)}
        for e in ranked
    ]
    out["sites_all"] = len(info)
    out["sites_within_pool"] = sum(s["km"] <= RANDOM_POOL_KM for s in info.values())
    return out


def _m(x: float) -> float | None:
    return None if x >= NO_OUTPUT_M / 10 else round(float(x), 1)


def _cell(r: dict) -> str:
    h25, h50 = r["holds_25m_s"], r["holds_50m_s"]
    if r["worst_p95_m"] is None:
        return f"no output / {h25} / {h50}"
    return f"{r['worst_p95_m']:,.0f} / {h25} / {h50}"


def summary(data: dict, meta: dict) -> str:
    rows, geo = data["rows"], data["geometry"]
    out = [
        "# How many towers after GPS is lost? (#208)",
        "",
        f"Sim, every value `TBC`. Commit {meta['commit']}, `python analysis/tower_count.py "
        f"--seeds {meta['seeds']} --jobs {meta['jobs']}`, {meta['minutes']:.1f} min. Seeds "
        f"0–{meta['seeds'] - 1}, paired: every variant of a seed keeps a subset of the same "
        "records. The leg, the tower rules, the aiding and the error models are in the script's "
        "docstring. The LTE model is `placeholder` (`verification.md`, *Sim validity*): these "
        "numbers compare tower counts with each other, they are not a prediction of the real "
        "drone.",
        "",
        "Each cell: **worst-second p95 (m) / s the p95 holds ≤ 25 m / s it holds ≤ 50 m**, the "
        f"T1 statistic of ADR-0034 over {meta['seeds']} runs, window 0–300 s after GPS loss. "
        "300 means the whole window. T1: worst ≤ 25 m (holds 300 s); fallback: ≤ 50 m for "
        "120 s.",
        "",
    ]
    for errors in ERRORS:
        rs = [r for r in rows if r["errors"] == errors]
        if not rs:
            continue
        out += [f"## Error model `{errors}`", ""]
        out.append("| Towers (rule) | Sites ≥ 3 on air | " + " | ".join(AIDING) + " |")
        out.append("|---|---|" + "---|" * len(AIDING))
        for rule, n in variants():
            cells = [
                _cell(
                    next(r for r in rs if r["rule"] == rule and r["n"] == n and r["aiding"] == a)
                )
                for a in AIDING
            ]
            label = f"{n} ({rule})" if n not in (0, "all") else str(n)
            share = data["on_air_3"][f"{rule}:{n}"]
            out.append(f"| {label} | {share:.0%} | " + " | ".join(cells) + " |")
        out.append("")
    out += [
        "## Geometry: snapshot HDOP of the N strongest sites over the route",
        "",
        "Unit range noise, the towers' own clocks known. Median / worst over the route; "
        "`no fix` where the sites are fewer than the unknowns.",
        "",
        "| N | x, y, clock (baro gives height) | x, y, z, clock (no baro) "
        "| x, y (baro, held clock) |",
        "|---|---|---|---|",
    ]
    for n in COUNTS[1:]:
        g = geo[str(n)]
        cells = [
            "no fix" if g[c] is None else f"{g[c]['median']:g} / {g[c]['max']:g}"
            for c in ("baro", "no_baro", "baro_held_clock")
        ]
        out.append(f"| {n} | " + " | ".join(cells) + " |")
    s = ", ".join(f"eNB {x['enb']} ({x['km']} km, {x['power_dbm']} dBm)" for x in geo["strongest"])
    out += [
        "",
        f"Strongest six, in order (median power over the route): {s}. Matched sites in the "
        f"table: {geo['sites_all']}; within {RANDOM_POOL_KM:g} km of the origin: "
        f"{geo['sites_within_pool']} (`all`, and the `random` pool).",
        "",
        "## Runtime",
        "",
        f"Median s per filter run: {meta['runtime_median_s']}; worst {meta['runtime_max_s']}.",
    ]
    return "\n".join(out) + "\n"


def plot(data: dict, meta: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data["rows"]
    errs = [e for e in ERRORS if any(r["errors"] == e for r in rows)]
    fig, axes = plt.subplots(1, len(errs), figsize=(4.1 * len(errs), 4.0), dpi=130, sharey=True)
    axes = np.atleast_1d(axes)
    x = np.arange(len(COUNTS))
    for ax, errors in zip(axes, errs, strict=True):
        for j, aid in enumerate(AIDING):
            y = [
                next(
                    r["worst_p95_m"]
                    for r in rows
                    if r["errors"] == errors
                    and r["rule"] == "strongest"
                    and r["n"] == n
                    and r["aiding"] == aid
                )
                for n in COUNTS
            ]
            y = [np.nan if v is None else v for v in y]
            ax.plot(x, y, color=SLOTS[j], lw=2, marker=MARKERS[j], ms=6, label=aid)
            yr = [
                next(
                    r["worst_p95_m"]
                    for r in rows
                    if r["errors"] == errors
                    and r["rule"] == "random"
                    and r["n"] == n
                    and r["aiding"] == aid
                )
                for n in RANDOM_COUNTS
            ]
            yr = [np.nan if v is None else v for v in yr]
            xr = [COUNTS.index(n) + 0.12 for n in RANDOM_COUNTS]
            ax.plot(xr, yr, ls="none", marker=MARKERS[j], ms=6, mfc="none", color=SLOTS[j])
        ax.axhline(25.0, color=INK, lw=1, ls="--")
        ax.axhline(50.0, color=INK, lw=1, ls=":")
        ax.text(-0.1, 25.0, "T1 25 m", fontsize=7, color=INK, ha="left", va="top")
        ax.text(-0.1, 50.0, "fallback 50 m", fontsize=7, color=INK, ha="left", va="bottom")
        ax.set_yscale("log")
        ax.set_xticks(
            x,
            [str(n) for n in COUNTS[:-1]]
            + [f"all\n({data['geometry']['sites_within_pool']}, ≤ 3 km)"],
        )
        ax.set_xlabel("towers (eNB sites) kept", fontsize=8)
        ax.set_title(f"error model `{errors}`", fontsize=9, loc="left")
        ax.grid(True, which="major", color=GRID, lw=0.6)
        ax.tick_params(labelsize=8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel(
        "worst-second p95 horizontal error,\n0–300 s after GPS loss (m)", fontsize=8
    )
    handles, labels = axes[0].get_legend_handles_labels()
    handles.append(plt.Line2D([], [], ls="none", marker="o", mfc="none", color=INK))
    labels.append("random sites within 3 km (open)")
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.005, 0.93), ncol=5,
               fontsize=8, frameon=False)  # fmt: skip
    fig.suptitle(
        "challenge-drone leg, GPS lost at 60 s: T1 statistic (ADR-0034) against tower count",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    fig.text(
        0.01,
        0.005,
        f"Sim (LTE model placeholder), commit {meta['commit']}, seeds 0-{meta['seeds'] - 1}; "
        "filled: strongest N sites; analysis/tower_count.py",
        fontsize=7,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.9))
    fig.savefig(path)
    print(f"wrote {path}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--runs", type=Path, default=RUNS, help="per-run curves (git-ignored)")
    p.add_argument("--redraw", action="store_true", help="rebuild from runs.json")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    a.runs.mkdir(parents=True, exist_ok=True)
    if a.redraw:
        results = json.loads((a.runs / "runs.json").read_text())
        meta = results.pop("meta")
        results = results["results"]
    else:
        t0 = time.time()
        results = run_all(range(a.seeds), a.jobs)
        rt = [v for r in results for v in r["runtime_s"].values()]
        meta = {
            "commit": _commit(),
            "seeds": a.seeds,
            "jobs": a.jobs,
            "minutes": round((time.time() - t0) / 60, 1),
            "runtime_median_s": round(float(np.median(rt)), 1),
            "runtime_max_s": round(float(np.max(rt)), 1),
        }
        (a.runs / "runs.json").write_text(json.dumps({"meta": meta, "results": results}))
    data = collect(results)
    data["geometry"] = geometry(leg_spec("committed"))
    (a.out / "summary.json").write_text(json.dumps({"meta": meta, **data}, indent=1))
    (a.out / "summary.md").write_text(summary(data, meta))
    print(f"wrote {a.out / 'summary.md'}")
    plot(data, meta, a.out / "tower_count.png")


if __name__ == "__main__":
    main()
