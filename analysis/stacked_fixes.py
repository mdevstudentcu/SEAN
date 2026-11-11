"""Stacked fixes on the drone leg (#218), sim: what learned LTE noise (ADR-0039), carrier hopping
(ADR-0040) and the jump guard (ADR-0038) buy alone and together, against T1 (25 m for 300 s) and
the mentors' fallback (50 m for 120 s), ADR-0034.

Only committed scenario entries and existing opt-in estimators. A combination with no registered
name (learned noise + guard) is built from the registered pieces' own configuration hooks,
`configured(ekf.run, noise_tau_s=ekf.NOISE_TAU_S, jump_guard=JumpGuard)`; no filter behaviour is
added here.

Rows, paired seeds (each seed gives every row on a scenario the same records):
- outage, `challenge-drone-outage` (1 carrier, 2460) and `challenge-drone-hop-outage` cut to its
  first 6 or all 13 carriers (`hopping_study.spec_of`): no LTE (control), today (told the
  reported 2 m), + learned noise, + hopping, learned noise + hopping (the stack), the stack + the
  jump guard, and told the true noise on 13 carriers (a ceiling: no real receiver knows it);
  each for `ekf` and `ekf-calibrated`;
- held 300 m jump from 150 s, `challenge-drone-spoof-jump` and `challenge-drone-hop-spoof-jump`
  (13 carriers): default, `-guard`, and guard + learned noise.

Scored as ADR-0034's amendment: at each whole second after GPS loss (after the jump starts, on the
jump rows) the 95th percentile of horizontal error across runs; a target holds if the worst second
of its window is within it (`worst_in`). Also per row: the median over seeds of each run's own p95
(the older tables' statistic), hazardous epochs, the HPL bound share and, on jump rows, whether
the estimate sits on the spoofed position at +120 s.

    python analysis/stacked_fixes.py --seeds 0-49 --jobs 10 --host g14   # committed results
    python analysis/stacked_fixes.py --seeds 100-109 --jobs 3 --out <dir>
    python analysis/stacked_fixes.py --redraw    # summary and figure from rows.json

Committed results need a clean tree; per-run data goes to the git-ignored `results/runs/`.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import platform
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hopping_study  # noqa: E402
import lte_noise_eval  # noqa: E402

from pnt.cli import _commit  # noqa: E402
from pnt.experiments import _map  # noqa: E402
from pnt.integrity.jump_guard import JumpGuard  # noqa: E402
from pnt.metrics import ALERT_LIMIT_M, gps_loss, score  # noqa: E402
from pnt.nav import ESTIMATORS, configured, ekf, estimate  # noqa: E402
from pnt.sim.scenario import T0_NS, generate, load  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "stacked-fixes"
RUNS = HERE / "results" / "runs" / "stacked-fixes"  # git-ignored
# ADR-0034: T1 (ours, TBC) and the mentors' fallback; both 95 % horizontal error after GPS loss
FALLBACK_M, FALLBACK_S = 50.0, 120
T1_M, T1_S = 25.0, 300
HORIZON_S = T1_S
SPOOF_AT_S = 120.0  # s after the jump: is the estimate on the spoofed position?
# Each run is cut 1 s after its 300 s window: the filters are causal, so every estimate in the
# window is the full run's, and the calibrated filter on 13 carriers needs half the time and
# memory (its memory grows with run length, about 2 GB at 720 s)
CUT_AFTER_S = HORIZON_S + 1

# Scenario specs, each generated once per seed
SPECS = {
    "nolte": "no LTE records (`challenge-drone-outage` without `sources.lte`)",
    "1c": "`challenge-drone-outage` (1 carrier, 2460)",
    "6c": "`challenge-drone-hop-outage`, first 6 carriers",
    "13c": "`challenge-drone-hop-outage` (13 carriers)",
    "13c-true": "`challenge-drone-hop-outage` (13 carriers), told the true noise",
    "jump-1c": "`challenge-drone-spoof-jump` (300 m, 1 carrier)",
    "jump-13c": "`challenge-drone-hop-spoof-jump` (300 m, 13 carriers)",
}

# Estimators: registered names, or the two combinations built from the same hooks the registry uses
COMBOS = {
    "ekf-learned-noise+guard": configured(
        ekf.run, noise_tau_s=ekf.NOISE_TAU_S, jump_guard=JumpGuard
    ),
    "ekf-calibrated-learned-noise+guard": configured(
        ekf.run_calibrated, noise_tau_s=ekf.CALIBRATED_NOISE_TAU_S, jump_guard=JumpGuard
    ),
}
FAMILIES = {  # family -> (default, learned noise, guard, learned noise + guard)
    "ekf": ("ekf", "ekf-learned-noise", "ekf-guard", "ekf-learned-noise+guard"),
    "ekf-calibrated": (
        "ekf-calibrated",
        "ekf-calibrated-learned-noise",
        "ekf-calibrated-guard",
        "ekf-calibrated-learned-noise+guard",
    ),
}


def estimator(name: str):
    return COMBOS[name] if name in COMBOS else ESTIMATORS[name]


def rows() -> list[dict]:
    """Every row, in table order. `ladder`: its place in the figure (None: table only)."""
    out = []
    for fam, (dflt, learned, guard, both) in FAMILIES.items():
        outage = [
            ("no-lte", "no LTE (control)", "nolte", dflt, 0),
            ("today", "today: 1 carrier, told 2 m", "1c", dflt, 1),
            ("learned", "+ learned noise", "1c", learned, 2),
            ("hop6", "+ hopping 6 carriers", "6c", dflt, 3),
            ("hop13", "+ hopping 13 carriers", "13c", dflt, 4),
            ("learned-hop6", "learned noise + 6 carriers", "6c", learned, None),
            ("stack", "learned noise + 13 carriers", "13c", learned, 5),
            ("stack-guard", "all three: + jump guard", "13c", both, 6),
            ("ceiling", "told the true noise, 13 carriers (not available)", "13c-true", dflt, 7),
        ]
        for key, label, spec, est, ladder in outage:
            out.append({"key": f"{fam}:{key}", "family": fam, "kind": "outage", "label": label,
                        "spec": spec, "estimator": est, "ladder": ladder})  # fmt: skip
        for spec, where in (("jump-1c", "1 carrier"), ("jump-13c", "13 carriers")):
            for key, label, est in (
                ("default", "default", dflt),
                ("guard", "jump guard", guard),
                ("guard-learned", "jump guard + learned noise", both),
            ):
                out.append({"key": f"{fam}:{spec}:{key}", "family": fam, "kind": "jump",
                            "label": f"held 300 m jump, {where}: {label}", "spec": spec,
                            "estimator": est, "ladder": None})  # fmt: skip
    return out


def spec_of(key: str) -> dict:
    cfgs = {c["key"]: c for c in hopping_study.configs()}
    if key == "nolte":
        return lte_noise_eval._spec(hopping_study.ONE_CARRIER, "nolte")
    if key == "1c":
        return hopping_study.spec_of(cfgs["one-carrier"], "committed")
    if key == "6c":
        return hopping_study.spec_of(cfgs["scan-6-1s"], "committed")
    if key == "13c":
        return hopping_study.spec_of(cfgs["scan-13-1s"], "committed")
    if key == "13c-true":
        return hopping_study.spec_of(cfgs["scan-13-1s"], "true-noise")
    if key == "jump-1c":
        return copy.deepcopy(load("challenge-drone-spoof-jump"))
    if key == "jump-13c":
        return copy.deepcopy(load("challenge-drone-hop-spoof-jump"))
    raise KeyError(key)


def window_start(spec: dict) -> tuple[int, list[float] | None]:
    """(t_ns the clock of a row starts, the jump offset ENU or None): GPS loss, else the jump."""
    loss = gps_loss(spec, T0_NS)
    if loss is not None:
        return loss[0], None
    (f,) = [f for f in spec["faults"] if f["type"] == "spoof_jump"]
    return T0_NS + int(round(f["start_s"] * 1e9)), [float(v) for v in f["offset_enu_m"]]


# --- the statistic (ADR-0034 amendment) --------------------------------------------------------
def p95_by_second(curves: np.ndarray) -> np.ndarray:
    """The 95th percentile across runs (axis 0) at each second (axis 1)."""
    return np.percentile(np.asarray(curves, float), 95, axis=0)


def worst_in(curve: np.ndarray, window_s: float) -> float:
    """The largest 95 % error in the first `window_s` s after GPS loss (seconds 0 to window_s
    included): a target "<= X m for >= T s" holds only if the whole window is within X. Same
    definition as `worst_in` in PR #178's `analysis/accuracy_budget.py`, not on this base."""
    return float(np.max(curve[: int(window_s) + 1]))


def worst_second(curve: np.ndarray, window_s: float) -> int:
    return int(np.argmax(curve[: int(window_s) + 1]))


# --- one seed ----------------------------------------------------------------------------------
def run_task(spec_key: str, family: str, seed: int) -> list[dict]:
    """Every row of `family` on `spec_key`, on one seed's records."""
    spec = spec_of(spec_key)
    sim = generate(spec, seed=seed)
    start, offset = window_start(spec)
    cut = start + CUT_AFTER_S * 1_000_000_000
    records = [m for m in sim.measurements if m.t_ns <= cut]
    out = []
    for row in rows():
        if row["spec"] != spec_key or row["family"] != family:
            continue
        t0 = time.perf_counter()
        est = list(
            estimate(estimator(row["estimator"]), records,
                     origin_llh=spec.get("origin_llh"), reference=sim.reference)
        )  # fmt: skip
        m = score(est, sim.truth, spec, T0_NS)
        truth = {g.t_ns: g for g in sim.truth}
        pairs = [(e, truth[e.t_ns]) for e in est if e.t_ns in truth]
        t = np.array([e.t_ns for e, _ in pairs])
        err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
        hpl = np.array([e.hpl_m for e, _ in pairs])
        at = {int(tt): i for i, tt in enumerate(t)}
        curve = [err[at[start + k * 1_000_000_000]] for k in range(HORIZON_S + 1)]
        r = {"row": row["key"], "seed": seed, "curve": [round(float(x), 2) for x in curve]}
        for s in (FALLBACK_S, T1_S):
            w = (t >= start) & (t < start + s * 1_000_000_000)
            r[f"run_p95_{s}s"] = float(np.percentile(err[w], 95))
        w = (t >= start) & (t < start + T1_S * 1_000_000_000)
        r["hpl_bound_300s"] = float(np.mean(hpl[w] >= err[w]))
        r["hazardous_epochs"] = int(m.hazardous_epochs)
        if offset is not None:
            i = at[start + int(SPOOF_AT_S * 1e9)]
            e, g = pairs[i]
            spoofed = (g.pos_enu[0] + offset[0], g.pos_enu[1] + offset[1])
            r["from_spoof_120s"] = float(math.dist(e.pos_enu[:2], spoofed))
            r["on_spoof_120s"] = bool(r["from_spoof_120s"] < math.hypot(*offset[:2]) / 2)
        r["run_s"] = round(time.perf_counter() - t0, 1)
        out.append(r)
    return out


def tasks(seeds: list[int]) -> list[tuple]:
    pairs = sorted({(r["spec"], r["family"]) for r in rows()})
    # Longest first: the 13-carrier calibrated filters take the most time
    pairs.sort(key=lambda p: ("13c" not in p[0], p[1] != "ekf-calibrated"))
    return [(s, f, seed) for s, f in pairs for seed in seeds]


# --- aggregate ---------------------------------------------------------------------------------
def aggregate(runs: list[dict]) -> list[dict]:
    out = []
    for row in rows():
        mine = sorted((r for r in runs if r["row"] == row["key"]), key=lambda r: r["seed"])
        if not mine:
            continue
        curve = p95_by_second([r["curve"] for r in mine])
        hz = [r["hazardous_epochs"] for r in mine]
        bound = [r["hpl_bound_300s"] for r in mine]
        a = {
            **row,
            "runs": len(mine),
            "worst_120s_m": worst_in(curve, FALLBACK_S),
            "worst_120s_at_s": worst_second(curve, FALLBACK_S),
            "worst_300s_m": worst_in(curve, T1_S),
            "worst_300s_at_s": worst_second(curve, T1_S),
            "median_run_p95_120s_m": float(np.median([r["run_p95_120s"] for r in mine])),
            "median_run_p95_300s_m": float(np.median([r["run_p95_300s"] for r in mine])),
            "hazardous_epochs": int(sum(hz)),
            "hazardous_seeds": [r["seed"] for r in mine if r["hazardous_epochs"] > 0],
            "hpl_bound_300s_median": float(np.median(bound)),
            "hpl_bound_300s_min": float(min(bound)),
            "p95_curve_m": [round(float(x), 1) for x in curve],
        }
        if row["kind"] == "jump":
            a["on_spoof_120s"] = int(sum(r["on_spoof_120s"] for r in mine))
        out.append(a)
    return out


# --- outputs -----------------------------------------------------------------------------------
def _m(x: float) -> str:
    return f"{x:,.0f}" if x >= 10 else f"{x:.1f}"


def _seeds_text(seeds: list[int]) -> str:
    if seeds == list(range(seeds[0], seeds[-1] + 1)):
        return f"{seeds[0]}–{seeds[-1]}"
    return ", ".join(map(str, seeds))


def summary(data: dict) -> str:
    rs = data["rows"]
    lines = [
        "# Stacked fixes on the drone leg (#218)",
        "",
        f"**Sim, every value `TBC`** (ADR-0015; LTE noise, hop set, dwell and the learned-noise "
        f"prior are not sized from real data). `{data['command']}` at {data['commit']} on "
        f"{data['host']}, seeds {_seeds_text(data['seeds'])} (paired), "
        f"{data['elapsed_min']:.1f} min. Hopping is a study leg (ADR-0040): the payload cannot "
        "hop yet. Learned noise (ADR-0039) and the jump guard (ADR-0038) are opt-in estimators; "
        "learned noise + guard has no registered name and is "
        "`configured(ekf.run[_calibrated], noise_tau_s=..., jump_guard=JumpGuard)`.",
        "",
        "Scenario entries: " + "; ".join(f"`{k}` = {v}" for k, v in SPECS.items()) + ".",
        "",
        "**Statistic (ADR-0034 amendment):** at each whole second after GPS loss (after the jump "
        "starts, on jump rows) the 95th percentile of horizontal error across the "
        f"{rs[0]['runs']} runs; the worst second of 0–{FALLBACK_S} s is scored against the "
        f"fallback ({FALLBACK_M:.0f} m) and of 0–{T1_S} s against T1 ({T1_M:.0f} m). With "
        "this many runs the per-second 95th percentile moves by several metres from one second to "
        "the next. *Median run p95*: median over seeds of each run's own p95 over the window "
        "(older tables). *Hazardous*: epochs from the run's start to the end of the 300 s "
        "window (each run is cut there) with error over the "
        f"{ALERT_LIMIT_M:.0f} m alert limit while HPL is under it (total, seeds). *HPL bound*: "
        "share of the first 300 s with HPL >= error, median (min) over seeds.",
        "",
        f"| Row | Estimator | Scenario | Worst second 0–{FALLBACK_S} s (m) | "
        f"<= {FALLBACK_M:.0f} m | Worst second 0–{T1_S} s (m) | <= {T1_M:.0f} m | "
        f"Median run p95 {FALLBACK_S} / {T1_S} s (m) | "
        "Hazardous (seeds) | HPL bound 300 s | On spoof +120 s |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rs:
        hz = r["hazardous_seeds"]
        more = ", …" if len(hz) > 6 else ""
        seeds = f" ({', '.join(map(str, hz[:6]))}{more})" if hz else ""
        lines.append(
            f"| {r['label']} | `{r['estimator']}` | `{r['spec']}` | "
            f"{_m(r['worst_120s_m'])} (s {r['worst_120s_at_s']}) | "
            f"{'yes' if r['worst_120s_m'] <= FALLBACK_M else 'no'} | "
            f"{_m(r['worst_300s_m'])} (s {r['worst_300s_at_s']}) | "
            f"{'yes' if r['worst_300s_m'] <= T1_M else 'no'} | "
            f"{_m(r['median_run_p95_120s_m'])} / {_m(r['median_run_p95_300s_m'])} | "
            f"{r['hazardous_epochs']:,} [{len(hz)}/{r['runs']}]{seeds} | "
            f"{r['hpl_bound_300s_median']:.2f} ({r['hpl_bound_300s_min']:.2f}) | "
            + (f"{r['on_spoof_120s']}/{r['runs']}" if r["kind"] == "jump" else "–")
            + " |"
        )
    lines += [
        "",
        "Notes:",
        "",
        "- Hazardous seeds list at most the first six.",
        "- The ceiling row is told the sim's true LTE noise (white and multipath together), which "
        "no real receiver knows: an upper bound on what better noise knowledge could buy, not a "
        "result.",
        "- On the outage rows the jump guard has nothing to refuse (no GNSS fix arrives before "
        "the cut), so *all three* equals the stack.",
        "- Jump rows: the clock starts at the jump (150 s), GPS stays on (spoofed), and the error "
        "includes following the jump (about 300 m). *On spoof*: within half the jump of where the "
        "spoofer puts the receiver. A guarded estimate can land there while coasting with GNSS "
        "excluded: seen on tuning seed 105; the reported seeds' cases were not inspected.",
        "",
        "## Not checked",
        "",
        "- Any real capture: no hopped capture exists, and the learned-noise prior (40 m) and "
        "memories (60 s, 120 s) were chosen on sim tuning seeds 100–109 (ADR-0039).",
        "- `ekf-imu` and other estimators: no learned-noise variant is registered for them.",
        "- Jump guard + learned noise on clean (no jump) runs beyond the outage rows here, and "
        "false alarms.",
        "",
    ]
    return "\n".join(lines)


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {"ekf": "#2a78d6", "ekf-calibrated": "#eb6834"}  # categorical slots 1, 2
    markers = {"ekf": "o", "ekf-calibrated": "s"}
    ink, grid = "#52514e", "#e4e3df"
    lad = [r for r in data["rows"] if r["ladder"] is not None]
    labels = {r["ladder"]: r["label"] for r in lad}
    n = len(labels)
    assert n <= 8, "at most 8 rows per panel"
    fig, axes = plt.subplots(1, 2, figsize=(16, 8.2), dpi=120, sharey=True)
    for ax, (key, t_s, target, who) in zip(
        axes,
        (("worst_120s_m", FALLBACK_S, FALLBACK_M, "mentors' fallback"),
         ("worst_300s_m", T1_S, T1_M, "T1")),
        strict=True,
    ):  # fmt: skip
        vals = [r[key] for r in lad]
        lo, hi = min(vals + [target]) / 2.5, max(vals) * 4
        for fam, dy in (("ekf", -0.16), ("ekf-calibrated", 0.16)):
            pts = sorted((r for r in lad if r["family"] == fam), key=lambda r: r["ladder"])
            y = [r["ladder"] + dy for r in pts]
            x = [r[key] for r in pts]
            ax.plot(x, y, markers[fam], color=colours[fam], ms=13, mec="white", mew=1.5,
                    label=fam, zorder=3)  # fmt: skip
            for xi, yi in zip(x, y, strict=True):
                ax.text(xi * 1.13, yi, f"{xi:,.0f} m", va="center", fontsize=13, color=ink)
        ax.axvline(target, color=ink, lw=2, ls="--", zorder=1)
        ax.text(target * 1.08, -0.45, f"{target:.0f} m ({who})", ha="left", va="center",
                fontsize=14, color=ink)  # fmt: skip
        ax.set_xscale("log")
        ax.set_xlim(lo, hi)
        ax.set_title(f"worst second of 0–{t_s} s after GPS loss", fontsize=16, loc="left")
        ax.set_xlabel("95 % horizontal error across runs (m, log)", fontsize=14)
        ax.tick_params(labelsize=13)
        ax.grid(True, axis="x", which="major", color=grid, lw=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(range(n), [textwrap.fill(labels[i], 30) for i in range(n)], fontsize=14)
    axes[0].set_ylim(n - 0.4, -0.6)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="upper right", bbox_to_anchor=(0.995, 0.995), ncol=2,
               fontsize=14, frameon=False, markerscale=0.8)  # fmt: skip
    fig.suptitle(
        "Drone leg, stacked fixes: worst-second 95 % error after GPS loss\n"
        f"{data['rows'][0]['runs']} runs per row (seeds {_seeds_text(data['seeds'])}), "
        f"{data['commit']} (sim, every value TBC; hopping is a study leg)",
        fontsize=15,
        x=0.01,
        y=0.995,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def _clean(commit: str, untracked: str = "") -> bool:
    """True for the hash of a clean tree (`_commit()` gives `<hash>-dirty` otherwise), as in
    PR #170's `analysis/challenge_baseline.py`, with no untracked file outside .gitignore
    (`untracked`: `git status --porcelain` output), which `--dirty` does not see."""
    return len(commit) >= 7 and all(c in "0123456789abcdef" for c in commit) and not untracked


def _untracked() -> str:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=HERE, capture_output=True, text=True
    )
    return out.stdout.strip() if out.returncode == 0 else "no git"


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", default="0-49", help="e.g. 0-49 (reported) or 100-109 (tuning)")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--host", default=f"{platform.system()} {platform.machine()}")
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--redraw", action="store_true", help="from rows.json, without running")
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "rows.json"
    if args.redraw:
        data = json.loads(path.read_text())
    else:
        commit = _commit()
        if args.out.resolve() == OUT.resolve() and not _clean(commit, _untracked()):
            raise SystemExit(
                f"tree is {commit}: commit first, the committed results must name a clean commit "
                "(or write elsewhere with --out)"
            )
        seeds = parse_seeds(args.seeds)
        todo = tasks(seeds)
        t0 = time.perf_counter()
        runs = [r for rs in _map(run_task, todo, args.jobs) for r in rs]
        elapsed = (time.perf_counter() - t0) / 60
        data = {
            "command": f"python analysis/stacked_fixes.py --seeds {args.seeds} --jobs {args.jobs}",
            "commit": commit,
            "host": args.host,
            "seeds": seeds,
            "elapsed_min": elapsed,
            "rows": aggregate(runs),
        }
        RUNS.mkdir(parents=True, exist_ok=True)
        per_run = RUNS / f"{commit}-seeds-{args.seeds}.json"
        per_run.write_text(json.dumps({"commit": commit, "runs": runs}))
        print(f"wrote {per_run}")
        path.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    (args.out / "summary.md").write_text(summary(data))
    plot(data, args.out / "ladder.png")


if __name__ == "__main__":
    main()
