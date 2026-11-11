"""Slow GNSS drag with carrier hopping (#221): does hearing more masts let the tower monitor
(ADR-0037, `integrity/spoof_monitor.py`) catch the 2 m/s ramp? Sim, every value TBC.

One command, from a clean commit:

    python analysis/drag_with_hopping.py --seeds 50 --jobs 6

writes `summary.md` (one table) and `detection_vs_masts.png` to
`analysis/results/drag-with-hopping/` (committed, so only from a clean tree: REQ-10), and one
row per run to `analysis/results/runs/drag-with-hopping.json` (git-ignored). `--redraw` rebuilds
the summary and figure from that file.

What the dongle hears, everything else as committed (the hop leg's ADR-0040, Proposed):
- 1 carrier: the drone leg as committed (`challenge-drone-<entry>`, EARFCN 2460);
- 6 carriers: `challenge-drone-hop-<entry>` hopping the first 6 carriers of its hop set, as
  `analysis/hopping_study.py` selects them (scan-list order, dwell as committed);
- 13 carriers: `challenge-drone-hop-<entry>` as committed.

Entries `spoof-ramp` (2 m/s from 150 s), `nominal` and `outage`, each inherited from
`challenge-drone` (no scenario file is added). Estimators `ekf`, `ekf-spoof`, `ekf-calibrated`,
`ekf-calibrated-spoof`, paired on seeds 0 to N-1. The monitor's settings are as committed; they
were chosen on seeds 100-109 of another case (ADR-0037) and are not re-tuned here. Runs and
scoring are `spoof_detection.py`'s (`run_spec`, `detection`), so a row means the same thing in
both studies.
"""

from __future__ import annotations

import argparse
import copy
import math
import time
from pathlib import Path

import hopping_study as hs
import numpy as np
import spoof_detection as sd

from pnt.cli import _commit
from pnt.experiments import _map
from pnt.nav import cells
from pnt.sim.scenario import T0_NS, generate, load

RESULTS = Path(__file__).resolve().parent / "results"
OUT = RESULTS / "drag-with-hopping"  # committed: summary.md, detection_vs_masts.png
RUNS = RESULTS / "runs" / "drag-with-hopping.json"  # git-ignored: one row per run
CARRIERS = (1, 6, 13)
ENTRIES = ("spoof-ramp", "nominal", "outage")
ESTIMATORS = ("ekf", "ekf-spoof", "ekf-calibrated", "ekf-calibrated-spoof")
PAIRS = sd.PAIRS  # (unchanged, with the monitor)
WINDOW_S = 10.0
TTA_TARGET_S = 30.0  # T4's ramp time to alert (ADR-0034, TBC)
SUCCESS = 45  # #221: seeds of 50 the monitor must flag on the 13-carrier leg
# Colour-blind-safe pair (categorical slots 1 and 2, analysis/spoof_detection.py) for the two
# filters; monitor on is solid and filled, off dashed and hollow
COLOURS = {"ekf": "#2a78d6", "ekf-calibrated": "#eb6834"}
MARKERS = {"ekf": "o", "ekf-calibrated": "s"}
INK, GRID = "#52514e", "#e4e3df"


def case_id(carriers: int, entry: str) -> str:
    return f"{carriers}-carrier:{entry}"


def parse(case: str) -> tuple[int, str]:
    leg, entry = case.split(":")
    return int(leg.split("-")[0]), entry


def spec_of(case: str) -> dict:
    """The spec of a case id, from the committed scenarios; only the carriers hopped vary."""
    n, entry = parse(case)
    if n == 1:
        spec = copy.deepcopy(load(f"challenge-drone-{entry}"))
    else:
        spec = copy.deepcopy(load(f"challenge-drone-hop-{entry}"))
        scan = list(spec["sources"]["lte"]["cells_from"]["earfcn"])
        if not 1 < n <= len(scan):
            raise ValueError(f"{n} carriers: the hop set has {len(scan)}")
        spec["sources"]["lte"]["cells_from"]["earfcn"] = scan[:n]
    spec["name"] = case
    return spec


def masts_per_window(run, spec: dict, mast_of: dict[str, int]) -> float:
    """Median over every `WINDOW_S` window of the run of the distinct masts heard after the cell
    lookup (registered eNBs within SAME_SITE_M are one mast, as `hopping_study.masts`)."""
    lte = [m for m in run.measurements if m.source == "lte"]
    n = int(float(spec["duration_s"]) // WINDOW_S)
    windows: list[set] = [set() for _ in range(n)]
    for m in cells.attach(lte, spec["origin_llh"]):
        k = int((m.t_ns - T0_NS) / 1e9 // WINDOW_S)
        if 0 <= k < n:
            windows[k].add(mast_of[m.meta["site"]])
    return float(np.median([len(w) for w in windows]))


def run_one(case: str, estimator: str, seed: int) -> dict:
    spec = spec_of(case)
    run = generate(spec, seed=seed)
    row = sd.run_spec(spec, case, estimator, seed, run=run)
    if estimator == ESTIMATORS[0]:  # what is heard does not depend on the estimator
        row["masts_10s"] = masts_per_window(run, spec, hs.masts())
    return row


def plan(seeds: int) -> list[tuple[str, str, int]]:
    return [
        (case_id(n, e), est, s)
        for n in CARRIERS
        for e in ENTRIES
        for est in ESTIMATORS
        for s in range(seeds)
    ]


# --- summary -------------------------------------------------------------------------------------
def masts(runs, n: int) -> float:
    """Median over seeds and entries of each run's median masts per 10 s."""
    return sd._med([r.get("masts_10s", math.nan) for r in runs if parse(r["case"])[0] == n])


def false_alarms(runs, n: int, est: str) -> dict:
    """False alarms on `nominal` and `outage`: mean per hour, and the seeds with one."""
    out = {}
    for entry in ("nominal", "outage"):
        rs = sd._rows(runs, case_id(n, entry), est)
        out[entry] = {
            "fa_h": sd._mean([r["false_alarms_per_h"] for r in rs]),
            "seeds": sorted(r["seed"] for r in rs if r["false_alarms_per_h"] > 0),
            "n": len(rs),
        }
    return out


def added_false_alarms(runs, n: int, mon: str, base: str) -> list[tuple[str, int]]:
    """(entry, seed) where the monitor variant has more false alarms than the unchanged
    estimator on the same seed (paired)."""
    out = []
    for entry in ("nominal", "outage"):
        b = {r["seed"]: r["false_alarms_per_h"] for r in sd._rows(runs, case_id(n, entry), base)}
        for r in sd._rows(runs, case_id(n, entry), mon):
            if r["false_alarms_per_h"] > b.get(r["seed"], math.inf):
                out.append((entry, r["seed"]))
    return out


def cell(runs, n: int, est: str) -> dict:
    ramp = sd._rows(runs, case_id(n, "spoof-ramp"), est)
    d = sd.detection(ramp)
    d["hazardous_seeds"] = sum(r["hazardous_epochs"] > 0 for r in ramp)
    d["fa"] = false_alarms(runs, n, est)
    base = dict((m, b) for b, m in PAIRS).get(est)
    d["added_fa"] = added_false_alarms(runs, n, est, base) if base else None
    d["opinion"] = opinion(ramp)
    return d


def opinion(rs) -> str:
    """Median over runs of the share of seconds each tower test had an opinion (at least
    `min_sites` sites kept in both windows); '–' for an estimator without the monitor."""
    keys = sorted({k for r in rs for k in r if k.endswith("_opinion_share")})
    if not keys:
        return "–"
    keys.sort(key=lambda k: float(k.split("_")[2].split("/")[0]))
    return ", ".join(
        f"{k.split('_')[2]} s: {sd._f(100 * sd._med([r.get(k, math.nan) for r in rs]), 0)} %"
        for k in keys
    )


def _seeds(s: list[int]) -> str:
    if not s:
        return "0"
    return f"{len(s)}: seed {', '.join(map(str, s))}" if len(s) <= 5 else str(len(s))


def verdict(runs, seeds: int) -> list[str]:
    best = cell(runs, 13, "ekf-spoof")
    added = best["added_fa"] or []
    met = best["detected"] >= SUCCESS * seeds / 50 and not added
    lines = [
        f"- **#221's criterion (`ekf-spoof` flags the ramp on >= {SUCCESS} of 50 seeds on the "
        f"13-carrier leg, 0 added false alarms): {'met' if met else 'not met'}.** "
        f"{best['detected']} of {best['n']} seeds, {len(added)} added false alarms on "
        "`nominal`/`outage`.",
        f"- Time to alert against T4's {TTA_TARGET_S:.0f} s (`TBC`), 13 carriers, `ekf-spoof`: "
        f"median {sd._f(best['tta_med'], 0)} s, worst {sd._f(best['tta_max'], 0)} s.",
    ]
    if best["detected"] < 25 * seeds / 50:
        lines.append(
            "- **Under 25 of 50: hopping does not rescue the monitor as committed.** Its tower "
            f"tests had an opinion on {best['opinion']} of the seconds (median over ramp runs). "
            "`spoof_monitor.towers_test` keeps a site only if it is heard on at least half of "
            "each window's record epochs. Hopping puts one carrier on air per epoch, so a site "
            "is heard on the epochs its own carriers are dwelled on, which is under half of a "
            "window when it is on few of the carriers hopped; with fewer than `min_sites` (5) "
            "sites kept the monitor has no opinion. More masts are heard, fewer are kept (seen on "
            "tuning seed 100, not a reporting seed)."
        )
    return lines


def summary(data: dict) -> str:
    runs, meta = data["runs"], data["meta"]
    n_seeds = meta["seeds"]
    lines = [
        "# Slow GNSS drag with carrier hopping: the tower monitor against masts heard (#221)",
        "",
        f"Sim, study leg (ADR-0040: the payload cannot hop yet), every value `TBC`. Commit "
        f"{meta['commit']}, `{meta['command']}`, {meta['minutes']:.1f} min on {meta['host']}. "
        f"Seeds 0–{n_seeds - 1}, paired; the monitor's settings are as committed (ADR-0037, "
        "chosen on seeds 100–109), not re-tuned.",
        "",
        "Entries `spoof-ramp` (2 m/s at 45°, from 150 s), `nominal` and `outage` of "
        "`challenge-drone` (1 carrier, EARFCN 2460) and `challenge-drone-hop` (the first 6 "
        "carriers of its hop set, and all 13), as committed; `-spoof` is the same filter with "
        "the opt-in tower monitor. Detection and false alarms are `pnt.metrics` "
        "(`analysis/spoof_detection.py`'s rows). Masts: distinct masts heard per 10 s after the "
        "cell lookup, median over seeds of each run's median.",
        "",
        *verdict(runs, n_seeds),
        "",
        "| Carriers | Masts per 10 s | Estimator | Ramp detected | TTA median (s) | "
        "TTA worst (s) | Error at alert (m) | Hazardous epochs on the ramp, mean (seeds) | "
        "False alarms / h, nominal (seeds) | False alarms / h, outage (seeds) | "
        "Added false alarms vs. unchanged | Monitor has an opinion (ramp, median share of s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for n in CARRIERS:
        for est in ESTIMATORS:
            d = cell(runs, n, est)
            if not d["n"]:
                continue
            fa = d["fa"]
            added = "–" if d["added_fa"] is None else str(len(d["added_fa"]))
            lines.append(
                f"| {n} | {sd._f(masts(runs, n), 1)} | `{est}` | {d['detected']}/{d['n']} | "
                f"{sd._f(d['tta_med'], 0)} | {sd._f(d['tta_max'], 0)} | "
                f"{sd._f(d['err_at_alert'])} | {sd._f(d['hazardous'])} "
                f"({d['hazardous_seeds']}) | "
                f"{sd._f(fa['nominal']['fa_h'], 2)} ({_seeds(fa['nominal']['seeds'])}) | "
                f"{sd._f(fa['outage']['fa_h'], 2)} ({_seeds(fa['outage']['seeds'])}) | {added} | "
                f"{d['opinion']} |"
            )
    notes = sd.during_alarm([r for r in runs if parse(r["case"])[1] == "spoof-ramp"])
    lines += [
        "",
        "TTA: time to alert from the ramp's start, detected seeds only. Error at alert: "
        "horizontal error at the alert, median over detected seeds. Hazardous: epochs whose "
        "error exceeds the alert limit (`pnt.metrics`). Added false alarms: (entry, seed) pairs "
        "where `-spoof` has more false alarms than the unchanged filter on the same seed. "
        "Opinion: "
        "share of seconds a tower test (lag/window) had at least `min_sites` sites kept "
        "(`spoof_detection.py`'s per-run share), median over the ramp runs.",
        *notes,
        "",
    ]
    return "\n".join(lines)


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs, meta = data["runs"], data["meta"]
    plt.rcParams.update({"font.size": 15})
    xs = {n: masts(runs, n) for n in CARRIERS}
    x = [xs[n] for n in CARRIERS]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 7.5), dpi=100)
    ends: dict = {a1: [], a2: []}  # (y at the last point, label, colour, bold) per axis
    for base, mon in PAIRS:
        colour, marker = COLOURS[base], MARKERS[base]
        for est, on in ((base, False), (mon, True)):
            d = [cell(runs, n, est) for n in CARRIERS]
            share = [100.0 * c["detected"] / c["n"] if c["n"] else np.nan for c in d]
            style = dict(color=colour, lw=3 if on else 2, ls="-" if on else "--",
                         ms=13 if on else 9, marker=marker, mfc=colour if on else "white",
                         mew=2.5, zorder=3 if on else 2)  # fmt: skip
            label = f"{base}, monitor {'on' if on else 'off'}"
            a1.plot(x, share, **style)
            ends[a1].append((share[-1], label, colour, on))
            med = [c["tta_med"] for c in d]
            worst = [c["tta_max"] for c in d]
            if all(math.isnan(m) for m in med):
                continue
            a2.plot(x, med, **style)
            for xi, m, w in zip(x, med, worst, strict=True):
                if not math.isnan(m):
                    a2.vlines(xi, m, w, color=colour, lw=2, alpha=0.6)
                    a2.plot(xi, w, "_", color=colour, ms=16, mew=2.5)
            last = max(i for i, m in enumerate(med) if not math.isnan(m))
            ends[a2].append((math.log10(med[last]), label, colour, on))
    # direct labels right of the last point, pushed apart so equal values stay legible
    for ax, gap, to_y in ((a1, 9.0, lambda v: v), (a2, 0.12, lambda v: 10**v)):
        placed: list[float] = []
        for y, label, colour, on in sorted(ends[ax], key=lambda e: e[0]):
            y = max([y] + [p + gap for p in placed])
            placed.append(y)
            ax.text(x[-1] * 1.04, to_y(y), label, color=colour, fontsize=13, va="center",
                    fontweight="bold" if on else "normal")  # fmt: skip
    if not ends[a2]:
        a2.text(0.5, 0.55, "no seed flagged the ramp:\nno time to alert to show",
                transform=a2.transAxes, ha="center", va="center", color=INK,
                fontsize=15)  # fmt: skip
    a1.axhline(100.0 * SUCCESS / 50, color=INK, lw=1.5, ls=":")
    a1.text(0.5, 100.0 * SUCCESS / 50 + 2, f"#221 target {SUCCESS} of 50", color=INK, fontsize=13)
    a1.set_ylim(-3, 108)
    a1.set_ylabel("ramp seeds detected (%)")
    a1.set_title("Share of seeds that flag the 2 m/s ramp", loc="left", fontsize=16, pad=40)
    a2.axhline(TTA_TARGET_S, color=INK, lw=1.5, ls=":")
    a2.text(0.5, TTA_TARGET_S * 1.12, f"T4 target {TTA_TARGET_S:.0f} s (TBC)", color=INK,
            fontsize=13)  # fmt: skip
    a2.set_yscale("log")
    a2.set_ylim(10, 1000)
    a2.set_ylabel("time to alert (s): median dot, worst tick")
    a2.set_title("Time to alert, detected seeds only", loc="left", fontsize=16, pad=40)
    right = max(xs.values()) * 1.75
    for ax in (a1, a2):
        ax.set_xlim(0, right)
        ax.set_xlabel("masts heard per 10 s (median over seeds)")
        ax.grid(True, color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        top = ax.secondary_xaxis("top")  # carriers hopped, at their masts heard
        top.set_xticks(x, [str(n) for n in CARRIERS], fontsize=13, color=INK)
        top.set_xlabel("LTE carriers hopped", fontsize=13, color=INK)
        top.tick_params(length=0)
        top.spines["top"].set_visible(False)
    fig.suptitle(
        "Slow GNSS drag (2 m/s) against masts heard, 1 / 6 / 13 LTE carriers hopped: "
        f"challenge-drone(-hop) spoof-ramp, nominal, outage;\nseeds 0–{meta['seeds'] - 1}, "
        f"{meta['commit']} (sim, study leg, every value TBC)",
        fontsize=15,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.9))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def write(data: dict, out_dir: Path) -> None:
    (out_dir / "summary.md").write_text(summary(data))
    plot(data, out_dir / "detection_vs_masts.png")
    print(f"wrote {out_dir / 'summary.md'}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--out", default=str(OUT), help="summary.md and detection_vs_masts.png")
    p.add_argument("--runs", default=str(RUNS), help="per-run rows (git-ignored by default)")
    p.add_argument("--redraw", action="store_true", help="rebuild from the runs file")
    a = p.parse_args(argv)
    out_dir, runs_path = Path(a.out), Path(a.runs)
    commit = _commit()
    # REQ-10: the committed results name a commit they can be regenerated from
    if not a.redraw and out_dir.resolve() == OUT.resolve() and not sd.clean_commit(commit):
        raise SystemExit(
            f"tree is {commit}: commit first, the committed results must name a clean commit "
            "(or write elsewhere with --out)"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if not a.redraw:
        tasks = plan(a.seeds)
        print(f"{len(tasks)} runs on {a.jobs} workers")
        t0 = time.time()
        runs = _map(run_one, tasks, a.jobs)
        meta = {
            "commit": commit,
            "command": f"python analysis/drag_with_hopping.py --seeds {a.seeds} --jobs {a.jobs}",
            "seeds": a.seeds,
            "minutes": (time.time() - t0) / 60.0,
            "host": sd.host(),
        }
        sd.save_runs({"meta": meta, "runs": runs}, runs_path)
    write(sd.load_runs(runs_path), out_dir)


if __name__ == "__main__":
    main()
