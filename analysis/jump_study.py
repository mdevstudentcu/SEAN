"""Location-jump study (REQ-04, T4): which GNSS position jumps each estimator catches, and what
the ones it misses or later accepts do to the position.

Our mentors (2026-11-10): "I would begin with location jumps". T4 (systems/plan.md) states only
ramps, so this measures jumps against the same estimators to propose a jump target (TBC).

Each run: GNSS position jumps by `size` metres at t = START_S and stays there until the run ends
(`spoof_jump`, sim/attacks.py). Seed k jumps towards DIRECTIONS_DEG[k % 8] (clockwise from
north), so 50 seeds cover eight directions about six times each. The jump-then-drift variant adds
a `spoof_ramp` in the same direction from the same instant: a jump that hides in the noise, then
walks away. Both are existing fault types composed in one `faults:` list; no new fault code.

Environments (ENVIRONMENTS), each with every fault removed first:
- `realistic-uc01`: the `realistic` set's sources, receiver clock and tower clocks (as
  `realistic-nominal` loads them) flown on `uc01-drone-circuit`'s route.
- `uc01`: `uc01-drone-circuit` as committed (synthetic towers, no receiver clock in them).
Clean runs of each (no fault, same seeds) give the false-alarm rate.

Per run and estimator, from `pnt.metrics.score` and `jump_response`:
- detected: a sustained alarm (pnt.metrics: ALARM_FLAGS held ALARM_HOLD_S) after the jump; and
  its delay. time to alert: the first alert switching on after the jump (pnt.metrics).
- absorbed: over the last TAIL_S of the run, the estimate's error along the jump direction is at
  least half the spoofed offset: the filter follows the spoofer. Otherwise GNSS is held out.
  follow time: when the along-jump error first reaches half the offset.
- worst error: the largest horizontal error after the jump; hazardous epochs: error over the
  50 m alert limit while HPL is within it (pnt.metrics.ALERT_LIMIT_M, TBC).

    python analysis/jump_study.py --runs 50 --jobs 12 --out DIR     # runs and plots
    python analysis/jump_study.py --rows DIR/rows.json --out DIR    # re-plot saved rows

Writes DIR/jump_study.png, DIR/summary.md and DIR/rows.json (the per-run rows; bulky, keep it
out of git). Sim only: every model is as `verification.md`'s Sim validity table rates it.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.core.time import s_to_ns
from pnt.experiments import _map
from pnt.metrics import ALERT_LIMIT_M, score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

ESTIMATORS = ("ekf", "ekf-calibrated", "ekf-imu", "ekf-mhss")
ENVIRONMENTS = ("realistic-uc01", "uc01")
SIZES_M = (5, 10, 15, 20, 30, 50, 100, 300, 1000)
DIRECTIONS_DEG = tuple(range(0, 360, 45))
# Jump-then-drift variants: (jump m, drift m/s). The jumps are ones the gates do not see; 2 m/s
# is T4's ramp, 0.5 m/s a slower one.
DRIFTS = ((5.0, 0.5), (5.0, 2.0), (10.0, 0.5), (10.0, 2.0))
START_S = 150.0  # as spoof-jump.yaml and the attack menu's spoof-jump
TAIL_S = 30.0  # the end of the run where absorbed or held is judged
# TBC: "reliably detects" for this study; T4 states no detection probability
RELIABLE_P = 0.95

# Categorical slots 1-4 (validated: dataviz palette check, light surface) and recessive ink
COLOURS = dict(zip(ESTIMATORS, ("#2a78d6", "#eb6834", "#1baf7a", "#eda100"), strict=True))
MARKERS = dict(zip(ESTIMATORS, ("o", "s", "^", "D"), strict=True))
# Plot only: each estimator's points nudged along the log x axis so equal values stay visible
NUDGE = dict(zip(ESTIMATORS, (0.93, 0.976, 1.024, 1.07), strict=True))
INK, GRID = "#52514e", "#e4e3df"


def environment(name: str) -> dict:
    """The environment's spec with no faults."""
    if name == "realistic-uc01":
        spec = load("realistic-nominal")
        spec["trajectory"] = copy.deepcopy(load("uc01-drone-circuit")["trajectory"])
    elif name == "uc01":
        spec = load("uc01-drone-circuit")
    else:
        raise ValueError(f"unknown environment {name!r} (known: {ENVIRONMENTS})")
    spec.update(name=name, faults=[])
    return spec


def unit(direction_deg: float) -> np.ndarray:
    """Horizontal ENU unit vector, clockwise from north (as `spoof_ramp`'s direction_deg)."""
    d = math.radians(direction_deg)
    return np.array([math.sin(d), math.cos(d), 0.0])


def jump_faults(
    size_m: float, direction_deg: float, rate_mps: float = 0.0, start_s: float = START_S
) -> list[dict]:
    """A GNSS position jump of `size_m` towards `direction_deg`, then (if `rate_mps`) a drift
    the same way: a `spoof_jump`, plus a `spoof_ramp` from the same instant."""
    off = size_m * unit(direction_deg)
    faults = [
        {
            "type": "spoof_jump",
            "source": "gnss",
            "start_s": start_s,
            "offset_enu_m": [float(off[0]), float(off[1]), 0.0],
        }
    ]
    if rate_mps:
        faults.append(
            {
                "type": "spoof_ramp",
                "source": "gnss",
                "start_s": start_s,
                "rate_mps": rate_mps,
                "direction_deg": direction_deg,
            }
        )
    return faults


def jump_response(
    estimates,
    truth,
    start_ns: int,
    direction_deg: float,
    size_m: float,
    rate_mps: float = 0.0,
    tail_s: float = TAIL_S,
) -> dict:
    """How far the estimate follows the spoofed offset (`size_m` + `rate_mps` x time since
    `start_ns`, towards `direction_deg`):
    - pull: mean over the last `tail_s` of the error along the jump direction over the offset
      (1: the estimate sits on the spoofed position, 0: on the truth)
    - absorbed: pull >= 0.5
    - follow_s: seconds from the jump to the first epoch whose along-jump error reaches half the
      offset (nan if none)
    - avail_pre: fraction of epochs before the jump whose status is not `unsafe`
    """
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    t = np.array([e.t_ns for e, _ in pairs])
    err = np.array([np.subtract(e.pos_enu, g.pos_enu) for e, g in pairs])
    unsafe = np.array([e.status == "unsafe" for e, _ in pairs])
    after = t >= start_ns
    since = (t - start_ns) / 1e9
    offset = size_m + rate_mps * since
    along = err @ unit(direction_deg)
    tail = after & (t >= t[-1] - s_to_ns(tail_s))
    pull = float(np.mean(along[tail] / offset[tail])) if tail.any() else float("nan")
    follow = np.flatnonzero(after & (along >= 0.5 * offset))
    pre = ~after
    return {
        "pull": pull,
        "absorbed": float(pull >= 0.5) if not math.isnan(pull) else float("nan"),
        "follow_s": float(since[follow[0]]) if follow.size else float("nan"),
        "avail_pre": float(np.mean(~unsafe[pre])) if pre.any() else float("nan"),
    }


def run_case(env: str, size_m: float, rate_mps: float, seed: int) -> list[dict]:
    """One seed of one case, every estimator over the same simulated run. size_m None: clean."""
    spec = environment(env)
    direction = DIRECTIONS_DEG[seed % len(DIRECTIONS_DEG)]
    clean = size_m is None
    if not clean:
        spec["faults"] = jump_faults(size_m, direction, rate_mps)
    run = generate(spec, seed=seed)
    start_ns = T0_NS + s_to_ns(START_S)
    rows = []
    for est in ESTIMATORS:
        e = list(estimate(est, run.measurements, origin_llh=spec["origin_llh"]))
        m = score(e, run.truth, spec, T0_NS)
        row = {
            "env": env,
            "estimator": est,
            "kind": "clean" if clean else ("jump-drift" if rate_mps else "jump"),
            "size_m": size_m,
            "rate_mps": rate_mps,
            "direction_deg": direction,
            "seed": seed,
            "detected": m.spoof_detected,
            "detect_s": m.detect_delay_s,
            "tta_s": m.time_to_alert_s,
            "worst_m": m.fault_h_max_m,
            "hazardous": m.hazardous_epochs,
            "misleading": m.misleading_epochs,
            "false_alarms_per_h": m.false_alarms_per_h,
            "h_max_m": m.h_max_m,
        }
        if not clean:
            row.update(jump_response(e, run.truth, start_ns, direction, size_m, rate_mps))
        rows.append(row)
    return rows


def tasks(runs: int) -> list[tuple]:
    out = [(env, None, 0.0, s) for env in ENVIRONMENTS for s in range(runs)]
    out += [(env, z, 0.0, s) for env in ENVIRONMENTS for z in SIZES_M for s in range(runs)]
    out += [(env, z, r, s) for env in ENVIRONMENTS for z, r in DRIFTS for s in range(runs)]
    return out


def _nan(fn, v) -> float:
    v = np.asarray([x for x in v if x is not None], float)
    v = v[~np.isnan(v)]
    return float(fn(v)) if v.size else float("nan")


def summarize(rows: list[dict]) -> list[dict]:
    """One row per (environment, estimator, case): rates over seeds and the worst run."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["env"], r["estimator"], r["kind"], r["size_m"], r["rate_mps"])].append(r)
    out = []
    for (env, est, kind, size, rate), rs in groups.items():
        s = {
            "env": env,
            "estimator": est,
            "kind": kind,
            "size_m": size,
            "rate_mps": rate,
            "runs": len(rs),
            "max_h_err_m": max(r["h_max_m"] for r in rs),
        }
        if kind == "clean":
            s["false_alarms_per_h"] = _nan(np.mean, [r["false_alarms_per_h"] for r in rs])
            s["runs_with_false_alarm"] = sum(r["false_alarms_per_h"] > 0 for r in rs)
            s["hazardous"] = sum(r["hazardous"] for r in rs)
        else:
            s.update(
                p_detect=_nan(np.mean, [r["detected"] for r in rs]),
                detect_med_s=_nan(np.median, [r["detect_s"] for r in rs]),
                detect_p95_s=_nan(lambda v: np.percentile(v, 95), [r["detect_s"] for r in rs]),
                tta_med_s=_nan(np.median, [r["tta_s"] for r in rs]),
                p_absorbed=_nan(np.mean, [r["absorbed"] for r in rs]),
                follow_med_s=_nan(np.median, [r["follow_s"] for r in rs]),
                worst_med_m=_nan(np.median, [r["worst_m"] for r in rs]),
                worst_max_m=_nan(np.max, [r["worst_m"] for r in rs]),
                hmi_runs=sum(r["hazardous"] > 0 for r in rs),
                hazardous=sum(r["hazardous"] for r in rs),
                avail_pre=_nan(np.mean, [r["avail_pre"] for r in rs]),
            )
        out.append(s)
    order = {e: i for i, e in enumerate(ESTIMATORS)}
    kinds = {"clean": 0, "jump": 1, "jump-drift": 2}
    return sorted(
        out,
        key=lambda s: (
            s["env"],
            order[s["estimator"]],
            kinds[s["kind"]],
            s["size_m"] or 0,
            s["rate_mps"],
        ),
    )


def smallest_reliable(summary: list[dict], env: str, est: str, p: float = RELIABLE_P):
    """The smallest jump size from which every larger size in the grid is detected in at least
    a fraction `p` of runs; None if not even the largest is."""
    jumps = sorted(
        (s for s in summary if (s["env"], s["estimator"], s["kind"]) == (env, est, "jump")),
        key=lambda s: s["size_m"],
    )
    best = None
    for s in reversed(jumps):
        if s["p_detect"] < p:
            break
        best = s["size_m"]
    return best


def bands(summary: list[dict], env: str, est: str, p: float = RELIABLE_P) -> dict:
    """Jump sizes that are dangerous, two ways:
    - undetected: detected in fewer than `p` of runs, yet some run's error passes the alert limit
    - hazardous: some run has a hazardously misleading epoch (detected or not)"""
    jumps = [s for s in summary if (s["env"], s["estimator"], s["kind"]) == (env, est, "jump")]
    jumps.sort(key=lambda s: s["size_m"])
    return {
        "undetected": [
            s["size_m"] for s in jumps if s["p_detect"] < p and s["worst_max_m"] > ALERT_LIMIT_M
        ],
        "hazardous": [s["size_m"] for s in jumps if s["hmi_runs"] > 0],
    }


def _g(v, fmt="{:.2f}") -> str:
    if v is None:
        return "-"
    if isinstance(v, float) and math.isnan(v):
        return "nan"
    return fmt.format(v) if isinstance(v, float) else str(v)


def _sizes(v: list) -> str:
    return ", ".join(f"{x:g}" for x in v) if v else "none"


def markdown(summary: list[dict], meta: dict) -> str:
    lines = [
        f"# Location-jump study ({meta['commit']}, sim)",
        "",
        f"Seeds 0..{meta['runs'] - 1} per row; seed k jumps towards {DIRECTIONS_DEG[1]}° x (k mod "
        f"{len(DIRECTIONS_DEG)}). Jump at t = {START_S:g} s, held to the end of the 360 s run. "
        "Command: `python analysis/jump_study.py --runs "
        f"{meta['runs']} --jobs N --out DIR`. Environments: `realistic-uc01` is "
        "`realistic-nominal` (realistic set) flown on `uc01-drone-circuit`'s route; `uc01` is "
        "`uc01-drone-circuit` as committed. Faults removed from both first.",
        "",
        "## Findings per estimator",
        "",
        f"| env | estimator | smallest jump detected in >= {RELIABLE_P:.0%} of runs (m) | "
        "undetected and over 50 m (m) | sizes with hazardous epochs (m) | false alarms / h "
        "(clean) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for env in ENVIRONMENTS:
        for est in ESTIMATORS:
            b = bands(summary, env, est)
            clean = next(
                s for s in summary if (s["env"], s["estimator"], s["kind"]) == (env, est, "clean")
            )
            low = smallest_reliable(summary, env, est)
            lines.append(
                f"| {env} | {est} | {_g(low, '{:g}')} | {_sizes(b['undetected'])} | "
                f"{_sizes(b['hazardous'])} | {_g(clean['false_alarms_per_h'])} "
                f"({clean['runs_with_false_alarm']}/{clean['runs']} runs) |"
            )
    keys = (
        ("size_m", "jump m", "{:g}"),
        ("rate_mps", "drift m/s", "{:g}"),
        ("p_detect", "P detect", "{:.2f}"),
        ("detect_med_s", "detect med s", "{:.1f}"),
        ("detect_p95_s", "detect p95 s", "{:.1f}"),
        ("tta_med_s", "alert med s", "{:.1f}"),
        ("p_absorbed", "P absorbed", "{:.2f}"),
        ("follow_med_s", "follows after med s", "{:.1f}"),
        ("worst_med_m", "worst err med m", "{:.0f}"),
        ("worst_max_m", "worst err max m", "{:.0f}"),
        ("hmi_runs", "runs with HMI", "{}"),
        ("hazardous", "HMI epochs", "{}"),
        ("avail_pre", "available before jump", "{:.2f}"),
    )
    for kind, title in (("jump", "Jumps"), ("jump-drift", "Jump then drift")):
        lines += ["", f"## {title}", ""]
        lines.append("| env | estimator | " + " | ".join(k[1] for k in keys) + " |")
        lines.append("| --- | --- | " + " | ".join("---" for _ in keys) + " |")
        for s in summary:
            if s["kind"] != kind:
                continue
            cells = [_g(s[k], f) if not isinstance(s[k], int) else str(s[k]) for k, _, f in keys]
            lines.append(f"| {s['env']} | {s['estimator']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Definitions: detect = an alarm flag held 1 s after the jump (`pnt.metrics`); alert = any "
        "alert switching on after the jump (nan when the estimate was already `unsafe`); absorbed "
        f"= over the last {TAIL_S:g} s the along-jump error is at least half the spoofed offset; "
        "HMI = error over the 50 m alert limit (TBC) while HPL is within it; available before jump"
        " = share of pre-jump epochs not `unsafe` (HPL within the alert limit).",
    ]
    return "\n".join(lines) + "\n"


def plot(summary: list[dict], meta: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = (
        ("p_detect", "P(detected)", "linear"),
        ("detect_med_s", "detection delay, median (s)", "linear"),
        ("p_absorbed", "P(absorbed: follows the spoof)", "linear"),
        ("follow_med_s", "time until it follows, median (s)", "linear"),
        ("worst_max_m", "worst error, max of runs (m)", "log"),
        ("p_hmi", "share of runs with an HMI epoch", "linear"),
    )
    summary = [{**s, "p_hmi": s["hmi_runs"] / s["runs"]} for s in summary if s["kind"] == "jump"]
    fig, axes = plt.subplots(
        len(ENVIRONMENTS), len(panels), figsize=(21, 7.6), dpi=120, squeeze=False
    )
    for row, env in enumerate(ENVIRONMENTS):
        for col, (key, label, yscale) in enumerate(panels):
            ax = axes[row, col]
            for est in ESTIMATORS:
                pts = sorted(
                    (s["size_m"], s[key])
                    for s in summary
                    if (s["env"], s["estimator"], s["kind"]) == (env, est, "jump")
                )
                xs, ys = zip(*pts, strict=True)
                ax.plot(
                    [x * NUDGE[est] for x in xs],
                    ys,
                    marker=MARKERS[est],
                    ms=6,
                    lw=2,
                    color=COLOURS[est],
                    label=est,
                    mec="white",
                    mew=0.8,
                )
            if key == "worst_max_m":
                ax.axhline(ALERT_LIMIT_M, color=INK, lw=1, ls=":", label="50 m alert limit (TBC)")
                ax.plot(SIZES_M, SIZES_M, color=INK, lw=0.8, ls="--", label="error = jump")
            if key in ("p_detect", "p_absorbed", "p_hmi"):
                ax.set_ylim(-0.04, 1.04)
            if key == "detect_med_s":
                ax.set_ylim(0, max(2.0, ax.get_ylim()[1]))
            if key == "p_detect":
                ax.axhline(RELIABLE_P, color=INK, lw=1, ls=":", label=f"{RELIABLE_P:.0%}")
            ax.set_xscale("log")
            ax.set_yscale(yscale)
            ax.set_xticks(SIZES_M, [f"{z:g}" for z in SIZES_M], fontsize=7)
            ax.minorticks_off()
            ax.grid(True, which="major", color=GRID, lw=0.6)
            ax.tick_params(labelsize=7)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.set_title(f"{env}: {label}", fontsize=8.5, loc="left")
            if row == len(ENVIRONMENTS) - 1:
                ax.set_xlabel("jump size (m)", fontsize=8)
    worst = [k for k, _, _ in panels].index("worst_max_m")
    handles, labels = axes[0, worst].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(0.005, 0.955),
        ncol=7,
        fontsize=8,
        frameon=False,
    )
    fig.suptitle(
        f"GNSS position jump at t = {START_S:g} s, held to the end: {meta['runs']} seeds per "
        f"point, 8 directions (x nudged per estimator), {meta['commit']} (sim)",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--rows", help="re-plot from a rows.json this script wrote")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.rows:
        data = json.loads(Path(args.rows).read_text())
    else:
        rows = [r for rs in _map(run_case, tasks(args.runs), args.jobs) for r in rs]
        data = {"commit": _commit(), "runs": args.runs, "rows": rows}
        (out / "rows.json").write_text(json.dumps(data))
    summary = summarize(data["rows"])
    (out / "summary.md").write_text(markdown(summary, data))
    plot(summary, data, out / "jump_study.png")


if __name__ == "__main__":
    main()
