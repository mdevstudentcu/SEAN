"""P12 tower-map hand-off (issue #96): a GPS-less ground user, with and without the drone's map.

For each seed of the scenario (default `p12-drone-map-handoff`):
- The drone flies a circuit of `handoff.circuit_s` with GPS, ending at the map's epoch, and its
  `ekf-calibrated` filter learns the tower clocks; the map is exported there
  (`pnt.nav.tower_map`), and goes through its JSON form as a hand-off would.
- The ground user (`ground_user:`, the same world: towers, told positions and tower clocks) runs
  `ekf-calibrated` over the same records: with no aid (tower clocks unknown, the filter's wide
  priors), with no aid but a tower drift prior equal to the sim's own spread (a prior nobody has
  until towers are measured: it shows how much of the map's gain a good prior alone would give),
  and starting from the map. Paired: same seeds, same user records.
- Map age: time from the map's epoch to the user's switch-on (`ground_user.start_s`); the user
  loses GPS 10 s later. Each age has its own circuit of the same length.

Prints, per case, the p95 horizontal error pooled over seeds over the first 120 s and 300 s
after GPS loss (T1 in systems/plan.md, TBC; the 50 m / 120 s fallback is ADR-0034, proposed on
PR #158), the worst seed, the share of those 300 s where HPL bounds the error, and misleading
(error > HPL, not flagged unsafe) and hazardous (error > alert limit, HPL within it) epochs over
the user's whole run. Writes a figure and seed 0's freshest map as JSON.

    python analysis/p12_map_handoff.py --runs 50 --out fig.png
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np

from pnt.core.time import s_to_ns
from pnt.experiments import _map
from pnt.metrics import ALERT_LIMIT_M, gps_loss, score
from pnt.nav import configured, ekf, estimate, tower_map
from pnt.sim.scenario import T0_NS, generate, load

T1_M, T1_S = 25.0, 300  # TBC: T1 in systems/plan.md, p95 horizontal error for 300 s after loss
FALLBACK_M, FALLBACK_S = 50.0, 120  # TBC: ADR-0034's fallback (proposed, PR #158)
NO_AID = "no aid"
SIM_PRIOR = "no aid, sim's drift spread as prior"


def age_case(age_s: float) -> str:
    return f"map, age {age_s:g} s"


def sim_drift_spread(spec: dict) -> float:
    """Each tower's true drift sigma in the sim (m/s): its builder's and its site's, combined."""
    levels = spec["tower_clocks"].values()
    return float(np.sqrt(sum((lv or {}).get("drift_mps", 0.0) ** 2 for lv in levels)))


def cases(spec: dict, run) -> dict[str, dict]:
    """The user filter's settings per case: no aid, no aid with the sim's drift spread as its
    prior, then the drone's map at each age, each through its JSON form."""
    ho = spec["handoff"]
    start_ns = T0_NS + s_to_ns(spec["ground_user"]["start_s"])
    out = {NO_AID: {}, SIM_PRIOR: {"init_tower_drift_sigma": sim_drift_spread(spec)}}
    for age in ho["map_ages_s"]:
        epoch = start_ns - s_to_ns(age)
        first = epoch - s_to_ns(ho["circuit_s"])
        if first < T0_NS:
            raise ValueError(f"map age {age} s: the circuit would start before the run")
        drone = [m for m in run.measurements if m.t_ns >= first]
        learned = tower_map.learn(drone, epoch, origin_llh=spec["origin_llh"])
        out[age_case(age)] = {"tower_map": tower_map.TowerMap.from_json(learned.to_json())}
    return out


def seed_result(scenario: str, seed: int) -> dict:
    """Per case: the run's metrics, and (time since GPS loss, error, HPL) over T1_S."""
    spec = load(scenario)
    run = generate(spec, seed=seed)
    user = run.ground_user
    loss = gps_loss(user.spec, T0_NS)[0]
    truth = {t.t_ns: np.asarray(t.pos_enu[:2]) for t in user.truth}
    out = {}
    for name, config in cases(spec, run).items():
        fn = configured(ekf.run_calibrated, **config)
        est = list(estimate(fn, user.measurements, origin_llh=spec["origin_llh"]))
        rows = np.array(
            [
                [
                    (e.t_ns - loss) / 1e9,
                    np.linalg.norm(np.asarray(e.pos_enu[:2]) - truth[e.t_ns]),
                    e.hpl_m,
                ]
                for e in est
                if e.t_ns in truth and loss <= e.t_ns < loss + s_to_ns(T1_S)
            ]
        )
        out[name] = (score(est, user.truth, user.spec, T0_NS), rows)
        if seed == 0 and name == age_case(spec["handoff"]["map_ages_s"][0]):
            out["_map_json"] = config["tower_map"].to_json()
    return out


def summary(runs: list[dict], name: str) -> dict:
    err = np.stack([r[name][1][:, 1] for r in runs])
    hpl = np.stack([r[name][1][:, 2] for r in runs])
    t = runs[0][name][1][:, 0]
    first = t < FALLBACK_S
    per_seed = [r[name][0].outage_h_p95_300s_m for r in runs]
    return {
        "p95_120": float(np.percentile(err[:, first], 95)),
        "p95_300": float(np.percentile(err, 95)),
        "worst_300": float(np.max(per_seed)),
        "worst_seed": int(np.argmax(per_seed)),
        "bound_300": float(np.mean(hpl >= err)),
        "misleading": int(sum(r[name][0].misleading_epochs for r in runs)),
        "hazardous": int(sum(r[name][0].hazardous_epochs for r in runs)),
    }


def free_cores() -> int:
    """Cores not already busy (other jobs share the machine), at least 1."""
    return max(1, (os.cpu_count() or 1) - round(os.getloadavg()[0]))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scenario", default="p12-drone-map-handoff")
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--jobs", type=int, default=None, help="default: the free cores")
    p.add_argument("--out", required=True, help="figure path; the map JSON goes beside it")
    p.add_argument("--caption", default="")
    args = p.parse_args(argv)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    jobs = args.jobs or free_cores()
    runs = _map(seed_result, [(args.scenario, s) for s in range(args.runs)], jobs)
    spec = load(args.scenario)
    ages = spec["handoff"]["map_ages_s"]
    names = [NO_AID, SIM_PRIOR, *map(age_case, ages)]
    stats = {n: summary(runs, n) for n in names}

    print(f"{args.scenario}, ekf-calibrated, {args.runs} seeds (sim), pooled over seeds")
    print(
        f"| case | p95 0-{FALLBACK_S} s (m) | p95 0-{T1_S} s (m) | worst seed p95 0-{T1_S} s (m) "
        f"| HPL >= error, 0-{T1_S} s | misleading | hazardous |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for n in names:
        s = stats[n]
        print(
            f"| {n} | {s['p95_120']:.1f} | {s['p95_300']:.1f} | {s['worst_300']:.1f} "
            f"(seed {s['worst_seed']}) | {s['bound_300']:.3f} | {s['misleading']} "
            f"| {s['hazardous']} |"
        )

    out = Path(args.out)
    (out.parent / f"{out.stem}-map-seed0.json").write_text(runs[0]["_map_json"] + "\n")

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 6.0), dpi=150, width_ratios=(3, 2))
    # categorical slots 1-3
    colors = {NO_AID: "#eb6834", SIM_PRIOR: "#1baf7a", age_case(ages[0]): "#2a78d6"}
    short = {NO_AID: "no aid", SIM_PRIOR: "no aid, sim prior", age_case(ages[0]): "map, age 0"}
    for name, color in colors.items():
        err = np.stack([r[name][1][:, 1] for r in runs])
        t = runs[0][name][1][:, 0]
        ax.plot(t, np.median(err, axis=0), color=color, lw=2, label=f"{short[name]}: median")
        ax.plot(t, np.percentile(err, 95, axis=0), color=color, lw=1.2, ls="--",
                label=f"{short[name]}: p95")  # fmt: skip
    for y, label in ((T1_M, f"T1 {T1_M:.0f} m (TBC)"), (ALERT_LIMIT_M, "alert limit 50 m (TBC)")):
        ax.axhline(y, color="#52514e", lw=1, ls=":")
        ax.text(T1_S, y * 1.08, label, color="#52514e", fontsize=8, ha="right")
    ax.axvline(FALLBACK_S, color="#52514e", lw=0.8, ls="-.")
    ax.set_yscale("log")
    ax.set_xlabel("time since the user lost GPS (s)")
    ax.set_ylabel("ground user's horizontal error (m)")
    ax.set_title("error after GPS loss (map handed off 10 s before)", fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)

    for key, ls, label in (
        ("p95_120", "-", f"0-{FALLBACK_S} s"),
        ("p95_300", "--", f"0-{T1_S} s"),
    ):
        bx.plot(ages, [stats[age_case(a)][key] for a in ages], color="#2a78d6", lw=2, ls=ls,
                marker="o", label=f"map, {label}")  # fmt: skip
        for name in (NO_AID, SIM_PRIOR):
            bx.axhline(stats[name][key], color=colors[name], lw=1.5, ls=ls,
                       label=f"{short[name]}, {label}")  # fmt: skip
    bx.axhline(T1_M, color="#52514e", lw=1, ls=":")
    bx.set_xlabel("map age at hand-off (s)")
    bx.set_ylabel("p95 horizontal error, pooled over seeds (m)")
    bx.set_title("how long the map stays useful", fontsize=10)
    bx.set_ylim(bottom=0)
    bx.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
    for a in (ax, bx):
        a.grid(True, which="major", color="#e4e3df", lw=0.6)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
    fig.suptitle(f"{args.scenario}, ekf-calibrated, {args.runs} seeds (sim)", fontsize=10)
    if args.caption:
        fig.text(0.01, 0.01, args.caption, fontsize=7, color="#52514e")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
