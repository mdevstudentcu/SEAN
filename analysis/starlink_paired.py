"""Paired Monte Carlo of the simulated LEO Doppler layers through a GPS outage (P13, #97).

    python analysis/starlink_paired.py --runs 50 --jobs 6 --out <folder>

Each seed generates `starlink-outage`, `iridium-outage` and `iridium-starlink-outage`. Their
GNSS, barometer and tower records are identical (the LEO blocks come last; tests/test_starlink.py
checks it), so four conditions share every non-LEO draw:
- towers: `starlink-outage` with its Doppler records dropped (the same records as ottawa-towers)
- +Iridium, +Starlink, +both: each scenario with all its records

An estimator that ignores `doppler` scores the four alike; the numbers only differ with one
that uses it (the EKF's `doppler` model, #13).

Writes summary.json (per condition: fault-window p95 and max, RMSE, HPL bound, misleading
epochs, NEES; paired p95 ratios against towers), error_curves.png (horizontal error across seeds
against time) and visibility.png (Starlink satellites above the mask and heard, Iridium above
its mask, and a sky plot of the heard Starlink passes for seed 0).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pnt import metrics, nav
from pnt.sim import trajectory
from pnt.sim.scenario import T0_NS, generate, load

CONDITIONS = ("towers", "+Iridium", "+Starlink", "+both")
SOURCES = {
    "towers": "starlink-outage",
    "+Iridium": "iridium-outage",
    "+Starlink": "starlink-outage",
    "+both": "iridium-starlink-outage",
}
KEYS = (
    "fault_h_p95_m",
    "fault_h_max_m",
    "h_rmse_m",
    "hpl_bound_frac",
    "misleading_epochs",
    "h_nees_mean",
)
STEP_S = 1.0  # error curves: the worst error in each second


def _curve(estimates, truth) -> np.ndarray:
    tmap = {t.t_ns: t.pos_enu for t in truth}
    t = np.array([(e.t_ns - T0_NS) / 1e9 for e in estimates if e.t_ns in tmap])
    err = np.array(
        [np.hypot(*np.subtract(e.pos_enu, tmap[e.t_ns])[:2]) for e in estimates if e.t_ns in tmap]
    )
    bins = np.floor(t / STEP_S).astype(int)
    out = np.full(bins.max() + 1, np.nan)
    np.fmax.at(out, bins, err)
    return out


def one_seed(seed: int, estimators: tuple[str, ...]) -> dict:
    runs = {name: generate(load(name), seed=seed) for name in set(SOURCES.values())}
    out: dict = {}
    for cond in CONDITIONS:
        run = runs[SOURCES[cond]]
        meas = run.measurements
        if cond == "towers":
            meas = [m for m in meas if m.kind != "doppler"]
        for est_name in estimators:
            est = list(nav.estimate(est_name, meas, origin_llh=run.spec["origin_llh"]))
            score = metrics.score(est, run.truth, run.spec, T0_NS)
            out[(est_name, cond)] = {
                "metrics": {k: float(getattr(score, k)) for k in KEYS},
                "curve": _curve(est, run.truth),
            }
    return out


def visibility(seed: int = 0) -> dict:
    """Per second: Starlink satellites above the mask (every pass) and heard (this seed), and
    Iridium above its mask; plus the heard Starlink tracks' azimuth and elevation."""
    import copy

    def counts(spec):
        run = generate(spec, seed=seed)
        recs = [m for m in run.measurements if m.kind == "doppler"]
        t = (np.array([m.t_ns for m in recs]) - T0_NS) / 1e9
        n = np.bincount(np.round(t).astype(int), minlength=int(spec["duration_s"]))
        return n, recs, t

    spec = load("starlink-outage")
    every = copy.deepcopy(spec)
    every["sources"]["leo"]["pass_availability"] = 1.0
    n_heard, recs, t = counts(spec)
    n_above, _, _ = counts(every)
    n_iridium, _, _ = counts(load("iridium-outage"))
    traj = {**spec["trajectory"], "_origin_llh": spec["origin_llh"]}
    pos, _ = trajectory.make(traj, t)
    tracks: dict[str, list] = {}
    for m, p in zip(recs, pos, strict=True):
        los = np.array(m.meta["emitter_enu"]) - p
        az = np.arctan2(los[0], los[1])
        el = np.degrees(np.arcsin(los[2] / np.linalg.norm(los)))
        tracks.setdefault(m.emitter, []).append((az, el))
    return {
        "above": n_above,
        "heard": n_heard,
        "iridium": n_iridium,
        "tracks": tracks,
        "mask_deg": spec["sources"]["leo"]["elevation_mask_deg"],
    }


def summarize(results: list[dict], estimators) -> dict:
    out: dict = {}
    for est in estimators:
        towers = np.array([r[(est, "towers")]["metrics"]["fault_h_p95_m"] for r in results])
        for cond in CONDITIONS:
            ms = [r[(est, cond)]["metrics"] for r in results]
            p95 = np.array([m["fault_h_p95_m"] for m in ms])
            ratio = p95 / towers
            out[f"{est} {cond}"] = {
                "runs": len(ms),
                "fault_h_p95_m_median": float(np.median(p95)),
                "fault_h_p95_m_mean": float(np.mean(p95)),
                "fault_h_p95_m_worst": float(np.max(p95)),
                "fault_h_max_m_worst": float(np.max([m["fault_h_max_m"] for m in ms])),
                "h_rmse_m_median": float(np.median([m["h_rmse_m"] for m in ms])),
                "hpl_bound_frac_min": float(np.min([m["hpl_bound_frac"] for m in ms])),
                "misleading_epochs_total": int(np.sum([m["misleading_epochs"] for m in ms])),
                "h_nees_mean_median": float(np.median([m["h_nees_mean"] for m in ms])),
                "p95_ratio_to_towers_median": float(np.median(ratio)),
                "seeds_better_than_towers": int(np.sum(p95 < towers)),
            }
    return out


def plot_curves(results, estimators, spec, path: Path) -> None:
    import matplotlib.pyplot as plt

    colors = {
        "towers": "#7a7974",
        "+Iridium": "#eb6834",
        "+Starlink": "#2a78d6",
        "+both": "#1baf7a",
    }
    fig, axes = plt.subplots(
        1, len(estimators), figsize=(5.2 * len(estimators), 3.6), sharey=True, squeeze=False
    )
    outage = next(f for f in spec["faults"] if f["type"] == "outage")
    for ax, est in zip(axes[0], estimators, strict=True):
        ax.axvspan(outage["start_s"], outage["end_s"], color="#e34948", alpha=0.08, lw=0)
        for cond in CONDITIONS:
            curves = [r[(est, cond)]["curve"] for r in results]
            n = min(len(c) for c in curves)
            c = np.array([x[:n] for x in curves])
            t = np.arange(n) * STEP_S
            ax.fill_between(
                t,
                np.nanpercentile(c, 50, 0),
                np.nanpercentile(c, 95, 0),
                color=colors[cond],
                alpha=0.12,
                lw=0,
            )
            ax.plot(t, np.nanmedian(c, 0), color=colors[cond], lw=1.6, label=cond)
        ax.set_title(f"{est}: median (line) to p95 (band), {len(results)} seeds", fontsize=9)
        ax.set_xlabel("time (s); GPS outage shaded")
        ax.set_yscale("log")
        ax.grid(True, which="major", color="0.9", lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0][0].set_ylabel("horizontal error (m), worst per second")
    axes[0][-1].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_visibility(vis: dict, path: Path) -> None:
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(10.4, 3.8))
    ax = fig.add_subplot(1, 2, 1)
    t = np.arange(len(vis["above"]))
    ax.plot(
        t,
        vis["above"],
        color="#2a78d6",
        lw=1.0,
        ls="--",
        label=f"Starlink above {vis['mask_deg']:g}°",
    )
    ax.plot(t, vis["heard"], color="#2a78d6", lw=1.8, label="Starlink heard (seed 0)")
    ax.plot(t, vis["iridium"][: len(t)], color="#eb6834", lw=1.8, label="Iridium above 8.2°")
    ax.set_xlabel("time (s) from 2026-11-12 18:00 UTC, Carleton")
    ax.set_ylabel("satellites with a Doppler record")
    ax.set_ylim(0, 1.35 * max(vis["above"]))
    ax.grid(True, color="0.9", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper center", ncol=3)
    sky = fig.add_subplot(1, 2, 2, projection="polar")
    sky.set_theta_zero_location("N")
    sky.set_theta_direction(-1)
    for track in vis["tracks"].values():
        az, el = np.array(track).T
        sky.plot(az, 90 - el, color="#2a78d6", lw=1.0)
        sky.plot(az[-1], 90 - el[-1], "o", color="#2a78d6", ms=2.5)
    ring = np.linspace(0, 2 * np.pi, 200)
    sky.plot(ring, np.full_like(ring, 90 - vis["mask_deg"]), color="0.5", lw=0.8, ls="--")
    sky.set_rmax(90)
    sky.set_yticks([30, 60], labels=["60°", "30°"], fontsize=7)
    sky.set_title(
        f"{len(vis['tracks'])} heard Starlink passes, seed 0 (dot: end; dashed: mask)", fontsize=9
    )
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--estimators", default="ekf,ekf-calibrated")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    estimators = tuple(args.estimators.split(","))
    args.out.mkdir(parents=True, exist_ok=True)
    seeds = list(range(args.runs))
    with ProcessPoolExecutor(max(1, args.jobs)) as pool:
        results = list(pool.map(one_seed, seeds, [estimators] * len(seeds)))
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=12"], capture_output=True, text=True
    ).stdout.strip()
    summary = {
        "commit": commit,
        "seeds": f"0..{args.runs - 1}",
        "conditions": summarize(results, estimators),
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    plot_curves(results, estimators, load("starlink-outage"), args.out / "error_curves.png")
    plot_visibility(visibility(0), args.out / "visibility.png")
    for name, s in summary["conditions"].items():
        print(
            f"{name:28s} p95 median {s['fault_h_p95_m_median']:7.1f} m  worst "
            f"{s['fault_h_p95_m_worst']:7.1f}  ratio {s['p95_ratio_to_towers_median']:.2f}  "
            f"better {s['seeds_better_than_towers']}/{s['runs']}  HPL>=err min "
            f"{100 * s['hpl_bound_frac_min']:.1f} %  misleading {s['misleading_epochs_total']}"
            f"  NEES {s['h_nees_mean_median']:.1f}"
        )
    print(f"commit {commit} -> {args.out}")


if __name__ == "__main__":
    main()
