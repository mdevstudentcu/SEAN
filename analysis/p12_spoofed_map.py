"""P12 with a spoofed drone (issue #96): the tower map built while the drone's GNSS is spoofed.

The map (`pnt.nav.tower_map`) is learned against the drone's GNSS, so a spoof during the build
is in it. For each seed, three runs of the same world: `p12-drone-map-handoff` (honest drone)
and its two variants with the drone spoofed from 100 s into its 300 s circuit to the hand-off,
`-spoof-ramp` (2 m/s to the north-east) and `-spoof-jump` (300 m east). The ground user's
records are the same in all three (checked per seed), so every case below is paired.

The drone (circuit only, the records `tower_map.learn` sees): does it flag its own GNSS? Per
detector, the seeds with a spoof cue (`spoof_suspected`, `gnss_jump_latched`) after the spoof
starts, the median time to the first, and the seeds with one on the honest circuit:
- `ekf-calibrated`, the map's learner: the towers' spoof detector inside the filter (#83)
- `ekf-calibrated-guard`: the same with the jump guard (ADR-0038)
- `ekf-calibrated-spoof`: the same with the tower displacement monitor (ADR-0037)
- `ekf-guard`: `ekf` with the jump guard
- ADR-0041's decision (`SpoofDecision`) on `ekf-calibrated-guard`'s flags, its highest level.
  The scenario has no GPS sky (`sky:`): the spoofer is taken to fake the right sky, so only the
  flag cues can fire.

The ground user (`ekf-calibrated`, GPS lost 10 s after switch-on, map age 0): no aid, the honest
drone's map, the spoofed drone's map built without the guard and handed on whatever the drone saw
(`tower_map.learn(..., jump_guard=None, refuse_flagged=False)`, the behaviour before ADR-0048),
and the spoofed drone's map learned with the jump guard on, handed on (`guarded`,
`refuse_flagged=False`) or withheld when the drone raised a cue (`guarded + refusal`, the default
export policy of ADR-0048: the user then has no aid). The honest map is built with the default
policy too. Per case, as
`p12_map_handoff.py`: ADR-0034's T1 statistic (95th percentile across seeds at each second
after GPS loss, worst second) over 0-120 s and 0-300 s, the share of 0-300 s epochs where HPL
bounds the error, the share it flags itself `unsafe` (HPL over the alert limit), and
misleading and hazardous epochs over the user's whole run (misleading: error over HPL while not
`unsafe`).

    python analysis/p12_spoofed_map.py --runs 20 --jobs 3 --out analysis/results/p12-spoofed-map
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np

from pnt.core.time import s_to_ns
from pnt.experiments import _map
from pnt.integrity.jump_guard import JumpGuard
from pnt.integrity.sky import LEVELS, SpoofDecision
from pnt.metrics import gps_loss, score
from pnt.nav import configured, ekf, estimate, tower_map
from pnt.sim.scenario import T0_NS, generate, load

_spec = importlib.util.spec_from_file_location(
    "p12_map_handoff", Path(__file__).with_name("p12_map_handoff.py")
)
handoff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(handoff)

BASE = "p12-drone-map-handoff"
SPOOFS = {"ramp": f"{BASE}-spoof-ramp", "jump": f"{BASE}-spoof-jump"}
DETECTORS = ("ekf-calibrated", "ekf-calibrated-guard", "ekf-calibrated-spoof", "ekf-guard")
DECISION_ON = "ekf-calibrated-guard"
CUES = ("spoof_suspected", "gnss_jump_latched")
NO_AID, HONEST = "no aid", "honest map"


def spoofed(kind: str) -> str:
    return f"{kind}-spoofed map"


def guarded(kind: str) -> str:
    return f"{kind}-spoofed map, guarded build"


def refused(kind: str) -> str:
    return f"{kind}-spoofed map, guarded build + refusal"


def case_names() -> list[str]:
    return [NO_AID, HONEST] + [f(k) for k in SPOOFS for f in (spoofed, guarded, refused)]


def drone_cues(name: str, records, spoof_ns: int, origin_llh) -> dict:
    """First spoof cue at or after `spoof_ns` (s after it, None: none) and whether any came
    before it; the ADR-0041 level reached after it (no sky data: flag cues only)."""
    decision = SpoofDecision()
    first, before, level = None, False, "unknown"
    for e in estimate(name, records, origin_llh=origin_llh):
        cue = any(c in e.flags for c in CUES)
        if e.t_ns < spoof_ns:
            before |= cue
            continue
        if cue and first is None:
            first = (e.t_ns - spoof_ns) / 1e9
        lv = decision.decide(e.t_ns, e.flags).level
        level = max(level, lv, key=LEVELS.index)
    return {"first_s": first, "before": before, "level": level}


def user_rows(est, user, loss) -> np.ndarray:
    truth = {t.t_ns: np.asarray(t.pos_enu[:2]) for t in user.truth}
    return np.array(
        [
            [
                (e.t_ns - loss) / 1e9,
                np.linalg.norm(np.asarray(e.pos_enu[:2]) - truth[e.t_ns]),
                e.hpl_m,
                e.status == "unsafe",
            ]
            for e in est
            if e.t_ns in truth and loss <= e.t_ns < loss + s_to_ns(handoff.T1_S)
        ]
    )


def seed_result(seed: int) -> dict:
    base = load(BASE)
    origin = base["origin_llh"]
    start = T0_NS + s_to_ns(base["ground_user"]["start_s"])  # map age 0: hand-off at switch-on
    first = start - s_to_ns(base["handoff"]["circuit_s"])
    runs = {"honest": generate(base, seed=seed)}
    runs |= {k: generate(load(n), seed=seed) for k, n in SPOOFS.items()}
    user = runs["honest"].ground_user
    for k in SPOOFS:
        if runs[k].ground_user.measurements != user.measurements:
            raise RuntimeError(f"seed {seed}: the {k} variant changed the user's records")
    circuit = {k: [m for m in r.measurements if first <= m.t_ns < start] for k, r in runs.items()}

    out: dict = {"drone": {}, "withheld": {}}
    for name in DETECTORS:
        # the honest circuit, judged over the whole of it
        out["drone"][("honest", name)] = drone_cues(name, circuit["honest"], first, origin)
        for k in SPOOFS:
            spoof_ns = T0_NS + s_to_ns(load(SPOOFS[k])["faults"][0]["start_s"])
            out["drone"][(k, name)] = drone_cues(name, circuit[k], spoof_ns, origin)

    def learn(k: str, **kw):
        return tower_map.learn(circuit[k], start, origin_llh=origin, **kw)

    def default(k: str) -> dict:
        """The map under the default export policy (ADR-0048), or none if it is withheld."""
        try:
            config = {"tower_map": learn(k)}
            out["withheld"][k] = False
        except tower_map.MapWithheld:
            config = {}  # no map: the user has no aid
            out["withheld"][k] = True
        return config

    configs = {NO_AID: {}, HONEST: default("honest")}
    for k in SPOOFS:
        configs[spoofed(k)] = {"tower_map": learn(k, jump_guard=None, refuse_flagged=False)}
        configs[guarded(k)] = {"tower_map": learn(k, jump_guard=JumpGuard, refuse_flagged=False)}
        configs[refused(k)] = default(k)

    loss = gps_loss(user.spec, T0_NS)[0]
    for name, config in configs.items():
        if "tower_map" in config:  # through its JSON form, as a hand-off would
            config = {"tower_map": tower_map.TowerMap.from_json(config["tower_map"].to_json())}
        est = list(estimate(configured(ekf.run_calibrated, **config), user.measurements, origin))
        out[name] = (score(est, user.truth, user.spec, T0_NS), user_rows(est, user, loss))
    return out


def drone_table(runs: list[dict]) -> list[str]:
    n = len(runs)
    lines = [
        "| drone detector | ramp: seeds flagged | ramp: median s to flag | jump: seeds flagged "
        "| jump: median s to flag | honest circuit: seeds flagged |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in DETECTORS:
        row = [name]
        for k in SPOOFS:
            t = [r["drone"][(k, name)]["first_s"] for r in runs]
            hit = [x for x in t if x is not None]
            row += [f"{len(hit)}/{n}", f"{np.median(hit):.1f}" if hit else "-"]
        honest = sum(r["drone"][("honest", name)]["first_s"] is not None for r in runs)
        lines.append("| " + " | ".join([*row, f"{honest}/{n}"]) + " |")
    row = [f"ADR-0041 decision on `{DECISION_ON}`, no sky: seeds by highest level"]
    for k in SPOOFS:
        levels = [r["drone"][(k, DECISION_ON)]["level"] for r in runs]
        row += [", ".join(f"{lv} {levels.count(lv)}" for lv in LEVELS if lv in levels), "-"]
    levels = [r["drone"][("honest", DECISION_ON)]["level"] for r in runs]
    row.append(", ".join(f"{lv} {levels.count(lv)}" for lv in LEVELS if lv in levels))
    lines.append("| " + " | ".join(row) + " |")
    before = sum(r["drone"][(k, n_)]["before"] for r in runs for k in SPOOFS for n_ in DETECTORS)
    lines.append("")
    lines.append(f"Cues on the spoofed circuits before the spoof started: {before}.")
    return lines


def user_table(runs: list[dict], stats: dict) -> list[str]:
    n = len(runs)
    lines = [
        f"| ground user's case | T1 stat 0-{handoff.FALLBACK_S} s (m) "
        f"| T1 stat 0-{handoff.T1_S} s (m) | worst seed p95 0-{handoff.T1_S} s (m) "
        f"| HPL >= error, 0-{handoff.T1_S} s | unsafe, 0-{handoff.T1_S} s | misleading "
        "| hazardous | map withheld |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in case_names():
        s = stats[name]
        held = "-"
        for k in ("honest", *SPOOFS):
            if name == (HONEST if k == "honest" else refused(k)):
                held = f"{sum(r['withheld'][k] for r in runs)}/{n}"
        lines.append(
            f"| {name} | {s['t1_120']:.1f} | {s['t1_300']:.1f} | {s['worst_300']:.1f} "
            f"(seed {s['worst_seed']}) | {s['bound_300']:.3f} | {s['unsafe_300']:.3f} "
            f"| {s['misleading']} "
            f"| {s['hazardous']} | {held} |"
        )
    return lines


def figure(runs: list[dict], stats: dict, path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.6), dpi=150, sharey=True)
    for ax, k in zip(axes, SPOOFS, strict=True):
        # categorical slots 1-4, each with its own line style (identity not by colour alone)
        series = (
            (HONEST, "#2a78d6", "-"),
            (NO_AID, "#eb6834", "--"),
            (spoofed(k), "#1baf7a", "-."),
            (guarded(k), "#e87ba4", (0, (6, 2, 1, 2))),
            (refused(k), "#eda100", ":"),
        )
        for name, color, ls in series:
            err = np.stack([r[name][1][:, 1] for r in runs])
            t = runs[0][name][1][:, 0]
            p95 = np.percentile(err, 95, axis=0)
            label = f"{name}: T1 stat {stats[name]['t1_300']:.0f} m"
            ax.plot(t, p95, color=color, lw=2, ls=ls, label=label)
        ax.axhline(handoff.T1_M, color="#52514e", lw=1, ls=":")
        ax.text(handoff.T1_S, handoff.T1_M * 1.08, f"T1 {handoff.T1_M:.0f} m (TBC)",
                color="#52514e", fontsize=8, ha="right")  # fmt: skip
        ax.set_yscale("log")
        ax.set_xlabel("time since the ground user lost GPS (s)")
        ax.set_title(f"drone's GNSS spoofed by a {k} while it built the map", fontsize=10)
        ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13))
        ax.grid(True, which="major", color="#e4e3df", lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("p95 across seeds of the user's horizontal error (m)")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--out", required=True, help="folder for summary.md, summary.json, figure")
    args = p.parse_args(argv)

    runs = _map(seed_result, [(s,) for s in range(args.runs)], args.jobs)
    stats = {
        name: handoff.summary(runs, name)
        | {"unsafe_300": float(np.mean(np.concatenate([r[name][1][:, 3] for r in runs])))}
        for name in case_names()
    }
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    title = f"{BASE} and its spoofed-drone variants, ekf-calibrated user, {args.runs} seeds (sim)"
    lines = [
        "# P12 with a spoofed drone (#96)",
        "",
        f"{title}, seeds 0-{args.runs - 1}, commit {commit}. "
        f"`python analysis/p12_spoofed_map.py --runs {args.runs} --jobs {args.jobs} "
        f"--out {args.out}`.",
        "",
        "## Does the drone flag its own GNSS during the build?",
        "",
        *drone_table(runs),
        "",
        "## What the map does to the ground user",
        "",
        "The default export (ADR-0048) is the honest map and the `guarded build + refusal` rows: "
        "built with the jump guard, withheld if the drone raised a cue.",
        "",
        *user_table(runs, stats),
        "",
    ]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text("\n".join(lines))
    drone = {
        f"{k} {name}": [r["drone"][(k, name)] for r in runs]
        for k in ("honest", *SPOOFS)
        for name in DETECTORS
    }
    withheld = {k: [r["withheld"][k] for r in runs] for k in ("honest", *SPOOFS)}
    (out / "summary.json").write_text(
        json.dumps(
            {
                "commit": commit,
                "runs": args.runs,
                "user": stats,
                "drone": drone,
                "withheld": withheld,
            },
            indent=1,
        )
        + "\n"  # fmt: skip
    )
    figure(runs, stats, out / "spoofed_map.png", title)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
