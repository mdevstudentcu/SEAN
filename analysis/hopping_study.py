"""Carrier hopping study for UC-01 (#173): error 120 s and 300 s after GPS loss against masts
heard. A sensitivity sweep over what one dongle hears, not the per-term accuracy budget
(`analysis/accuracy_budget.py`, #178). The hop leg and its TBC values: ADR-0037 (Proposed).

The drone leg's `outage` entry, with what the dongle hears varied and everything else as
committed (sim, every value TBC):
- one carrier, today's leg (`challenge-drone-outage`), and every tower within 3 km heard on it
  (`hearing: {model: range, hearing_km: 3}`), the two reference points;
- hopping the first n carriers of `challenge-drone-hop`'s hop set (unflagged, scan-list order),
  dwell 1 s, and 0.5 s and 2 s at two of those n;
- hopping a carrier only if its registered eNBs differ from every earlier carrier's ("distinct
  eNB sets"), an alternative order taken from the registry alone.

Each runs `ekf` and `ekf-calibrated` on paired seeds, twice: with the records' reported sigma as
committed (`told_sigma_m`, 2 m), and told the true noise (white noise and multipath together),
which is what the filters would get if #147 were solved. The filters are not changed.

Heard: distinct masts (registered eNBs within SAME_SITE_M are one mast) and cells per record epoch
and per 10 s window of the outage, after the cell lookup (`pnt.nav.cells.attach`). Per run the
median, min and max over epochs; across seeds the median of medians, the min and the max.

    python analysis/hopping_study.py --seeds 20 --jobs 3
    python analysis/hopping_study.py --redraw   # summary and figure from study.json
    python analysis/hopping_study.py --seeds 1 --configs one-carrier,scan-2-1s --out <dir>
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.experiments import _map
from pnt.metrics import gps_loss, score
from pnt.nav import cells, estimate
from pnt.sim import lte_front_end
from pnt.sim.scenario import REFERENCE_DIR, SAME_SITE_M, T0_NS, generate, load

OUT = Path(__file__).parent / "results" / "hopping-study"
ONE_CARRIER = "challenge-drone-outage"
HOPPING = "challenge-drone-hop-outage"
ESTIMATORS = ("ekf", "ekf-calibrated")
VARIANTS = {
    "committed": "told sigma as committed (2 m)",
    "true-noise": "told the true noise (if #147 is solved)",
}
# TBC targets: the mentors' 50 m for about 2 minutes (#158, 2026-11-10) and our T1, 25 m for
# 300 s (systems/plan.md); both p95 horizontal error after GPS loss
MENTOR_M, MENTOR_S = 50.0, 120
T1_M, T1_S = 25.0, 300
WINDOW_S = 10.0
COUNTS = (2, 4, 6, 8, 13)  # carriers hopped at the default dwell (13: every unflagged one)
DWELLS = (0.5, 2.0)  # other dwells (s), at DWELL_AT carriers
# Only at 4: ekf-calibrated takes 20 to 70 s a run at 8 to 13 carriers (it adds a state per
# site heard), and the run is limited to 3 workers on a shared machine
DWELL_AT = (4,)
DISTINCT = (4, 6)  # carriers hopped in the distinct-eNB-set order (9 left out for the same cost)
COLOURS = {  # categorical slots in a fixed order, as analysis/challenge_baseline.py (PR #170)
    ("ekf", "committed"): "#2a78d6",
    ("ekf-calibrated", "committed"): "#eb6834",
    ("ekf", "true-noise"): "#1baf7a",
    ("ekf-calibrated", "true-noise"): "#eda100",
}
INK, GRID = "#52514e", "#e4e3df"


def hop_set() -> list[int]:
    return list(load(HOPPING)["sources"]["lte"]["cells_from"]["earfcn"])


def _table_rows() -> list[dict]:
    with open(REFERENCE_DIR / "lte-cells-ottawa.csv", newline="") as f:
        return list(csv.DictReader(f))


def distinct_enb_sets(earfcns: list[int]) -> list[int]:
    """`earfcns` without any carrier whose registered eNBs are exactly an earlier one's."""
    enbs: dict[int, set[str]] = {}
    for r in _table_rows():
        enbs.setdefault(int(r["earfcn"]), set()).add(r["enb_id"])
    out: list[int] = []
    for e in earfcns:
        if all(enbs[e] != enbs[o] for o in out):
            out.append(e)
    return out


def masts() -> dict[str, int]:
    """Site (`enb:<id>`) -> mast index: eNBs within SAME_SITE_M of each other are one mast."""
    where: dict[str, tuple[float, float]] = {}
    for r in _table_rows():
        where.setdefault(f"enb:{r['enb_id']}", (float(r["lat"]), float(r["lon"])))
    placed: list[tuple[float, float]] = []
    out = {}
    for site, (lat, lon) in sorted(where.items()):
        for i, (la, lo) in enumerate(placed):
            dn = (lat - la) * 111_132.0
            de = (lon - lo) * 111_320.0 * math.cos(math.radians(lat))
            if math.hypot(dn, de) < SAME_SITE_M:
                out[site] = i
                break
        else:
            out[site] = len(placed)
            placed.append((lat, lon))
    return out


def configs() -> list[dict]:
    """Every point of the study, in table order."""
    scan, dwell = hop_set(), load(HOPPING)["sources"]["lte"]["hop"]["dwell_s"]
    out = [
        {"key": "one-carrier", "label": "1 carrier, today's leg (2460)", "family": "reference"},
        {"key": "range-3km", "label": "every tower within 3 km (2460)", "family": "reference"},
    ]
    for n in COUNTS:
        out.append(
            {"key": f"scan-{n}-{dwell:g}s", "label": f"scan order, {n} carriers, {dwell:g} s",
             "family": "scan order", "earfcn": scan[:n], "dwell_s": dwell}
        )  # fmt: skip
    for n in DWELL_AT:
        for d in DWELLS:
            out.append(
                {"key": f"scan-{n}-{d:g}s", "label": f"scan order, {n} carriers, {d:g} s",
                 "family": "scan order", "earfcn": scan[:n], "dwell_s": d}
            )  # fmt: skip
    distinct = distinct_enb_sets(scan)
    for n in DISTINCT:
        if distinct[:n] != scan[:n]:
            out.append(
                {"key": f"distinct-{n}-{dwell:g}s",
                 "label": f"distinct eNB sets, {n} carriers, {dwell:g} s",
                 "family": "distinct eNB sets", "earfcn": distinct[:n], "dwell_s": dwell}
            )  # fmt: skip
    return out


def spec_of(cfg: dict, variant: str) -> dict:
    if cfg["key"] == "one-carrier":
        spec = copy.deepcopy(load(ONE_CARRIER))
    elif cfg["key"] == "range-3km":
        spec = copy.deepcopy(load(ONE_CARRIER))
        spec["sources"]["lte"]["hearing"] = {"model": "range", "hearing_km": 3.0}
    else:
        spec = copy.deepcopy(load(HOPPING))
        lte = spec["sources"]["lte"]
        lte["cells_from"]["earfcn"] = list(cfg["earfcn"])
        lte["hop"]["dwell_s"] = cfg["dwell_s"]
    if variant == "true-noise":
        lte = spec["sources"]["lte"]
        lte["told_sigma_m"] = math.hypot(lte["sigma_m"], lte["multipath"]["sigma_m"])
    return spec


def _epochs_ns(spec: dict) -> np.ndarray:
    """Every LTE record epoch of the run, heard or not (`dwell_schedule` or the rate grid)."""
    cfg = dict(spec["sources"]["lte"])
    rate = cfg.pop("rate_hz")
    schedule = lte_front_end.dwell_schedule(cfg, float(spec["duration_s"]), rate)
    ts = schedule.ts if schedule else np.arange(0.0, float(spec["duration_s"]), 1.0 / rate)
    return T0_NS + np.round(ts * 1e9).astype(np.int64)


def _spread(xs) -> dict:
    xs = np.asarray(xs, float)
    return {"median": float(np.median(xs)), "min": float(xs.min()), "max": float(xs.max())}


def heard(run, spec: dict, mast_of: dict[str, int]) -> dict:
    """What the filter could use during the outage, after the lookup."""
    start, end = gps_loss(spec, T0_NS)
    lte = [m for m in run.measurements if m.source == "lte" and start <= m.t_ns < end]
    counts = Counter()
    placed = list(cells.attach(lte, spec["origin_llh"], counts=counts))
    epochs = [t for t in _epochs_ns(spec) if start <= t < end]
    by_epoch = {t: (set(), set()) for t in epochs}
    windows = {k: (set(), set()) for k in range(int((end - start) / 1e9 // WINDOW_S))}
    for m in placed:
        k = int((m.t_ns - start) / 1e9 // WINDOW_S)
        for bucket in (by_epoch[m.t_ns], windows.get(k)):
            if bucket is not None:
                bucket[0].add(mast_of[m.meta["site"]])
                bucket[1].add(m.emitter)
    return {
        "masts_epoch": _spread([len(b[0]) for b in by_epoch.values()]),
        "masts_10s": _spread([len(b[0]) for b in windows.values()]),
        "cells_epoch": _spread([len(b[1]) for b in by_epoch.values()]),
        "cells_10s": _spread([len(b[1]) for b in windows.values()]),
        "masts_outage": len({mast_of[m.meta["site"]] for m in placed}),
        "epochs_per_s": len(epochs) / ((end - start) / 1e9),
        "records": len(lte),
        "dropped": sum(n for s, n in counts.items() if s != cells.MATCHED),
    }


def run_one(cfg: dict, variant: str, seed: int) -> dict:
    t0 = time.perf_counter()
    spec = spec_of(cfg, variant)
    run = generate(spec, seed=seed)
    out = {"config": cfg["key"], "variant": variant, "seed": seed}
    out["heard"] = heard(run, spec, masts())
    for name in ESTIMATORS:
        est = estimate(name, run.measurements, origin_llh=spec["origin_llh"])
        m = score(list(est), run.truth, spec, T0_NS)
        out[name] = {
            "outage_h_p95_120s_m": m.outage_h_p95_120s_m,
            "outage_h_p95_300s_m": m.outage_h_p95_300s_m,
            "outage_hpl_bound_300s": m.outage_hpl_bound_300s,
            "hazardous_epochs": m.hazardous_epochs,
        }
    out["run_s"] = time.perf_counter() - t0
    return out


def aggregate(runs: list[dict], cfgs: list[dict]) -> list[dict]:
    rows = []
    for cfg in cfgs:
        for variant in VARIANTS:
            mine = [r for r in runs if r["config"] == cfg["key"] and r["variant"] == variant]
            if not mine:
                continue
            h = [r["heard"] for r in mine]
            row = {
                "config": cfg["key"],
                "label": cfg["label"],
                "family": cfg["family"],
                "variant": variant,
                "earfcn": cfg.get("earfcn", [2460]),
                "dwell_s": cfg.get("dwell_s"),
                "seeds": len(mine),
                "epochs_per_s": float(np.median([x["epochs_per_s"] for x in h])),
                "masts_outage": _spread([x["masts_outage"] for x in h]),
            }
            for k in ("masts_epoch", "masts_10s", "cells_epoch", "cells_10s"):
                row[k] = {
                    "median": float(np.median([x[k]["median"] for x in h])),
                    "min": float(min(x[k]["min"] for x in h)),
                    "max": float(max(x[k]["max"] for x in h)),
                }
            row["dropped_share"] = sum(x["dropped"] for x in h) / max(
                1, sum(x["records"] for x in h)
            )
            for name in ESTIMATORS:
                e = [r[name] for r in mine]
                a = np.array([x["outage_h_p95_120s_m"] for x in e])
                b = np.array([x["outage_h_p95_300s_m"] for x in e])
                row[name] = {
                    "p95_120s_median": float(np.median(a)),
                    "p95_120s_worst": float(a.max()),
                    "p95_120s_meet": int((a <= MENTOR_M).sum()),
                    "p95_300s_median": float(np.median(b)),
                    "p95_300s_worst": float(b.max()),
                    "p95_300s_meet": int((b <= T1_M).sum()),
                    "hpl_bound_300s_median": float(
                        np.median([x["outage_hpl_bound_300s"] for x in e])
                    ),
                    "hpl_bound_300s_min": float(min(x["outage_hpl_bound_300s"] for x in e)),
                    "hazardous_epochs": int(sum(x["hazardous_epochs"] for x in e)),
                    "hazardous_seeds": int(sum(x["hazardous_epochs"] > 0 for x in e)),
                }
            rows.append(row)
    return rows


def _m(x: float) -> str:
    return f"{x:,.0f}"


def _reproduced(data: dict) -> str:
    """Where the numbers were checked when the commit that made them is not in the repo
    (REQ-10): a later commit and the seeds re-run at it (`reproduced` in study.json)."""
    r = data.get("reproduced")
    if not r:
        return ""
    return (
        f" {data['commit']} is not in the repo. Reproduced at {r['commit']}: `{r['command']}` "
        f"re-ran {r['what']}; {r['match']}."
    )


def summary(data: dict) -> str:
    rows, n = data["rows"], data["seeds"]
    seeds = f"seeds 0–{n - 1}"
    lines = [
        "# Carrier hopping study: error after GPS loss against masts heard (#173)",
        "",
        f"Sim, every value `TBC`. `{data['command']}` at {data['commit']}, {seeds} (paired), "
        f"{data['elapsed_min']:.1f} min. Scenarios `{ONE_CARRIER}` and `{HOPPING}`, the drone "
        "leg's 600 s outage; filters unchanged. Targets (`TBC`): the mentors' "
        f"{MENTOR_M:.0f} m at {MENTOR_S} s (#158) and our T1, {T1_M:.0f} m at {T1_S} s, both "
        "p95 horizontal error after GPS loss." + _reproduced(data),
        "",
        "## Verdict",
        "",
    ]
    for t_s, target, key, meet in (
        (MENTOR_S, MENTOR_M, "p95_120s", "p95_120s_meet"),
        (T1_S, T1_M, "p95_300s", "p95_300s_meet"),
    ):
        hits = [
            (r, name) for r in rows for name in ESTIMATORS if r[name][f"{key}_median"] <= target
        ]
        every = [(r, name) for r, name in hits if r[name][meet] == r["seeds"]]
        best = min(
            ((r, name) for r in rows for name in ESTIMATORS),
            key=lambda x: x[0][x[1]][f"{key}_median"],
        )
        b, bn = best
        lines.append(
            f"- **{target:.0f} m at {t_s} s: {'met on the median' if hits else 'not met'}.** "
            f"Best median {_m(b[bn][f'{key}_median'])} m: `{bn}`, {b['label']}, "
            f"{VARIANTS[b['variant']]}, {b['masts_10s']['median']:g} masts per 10 s "
            f"({b[bn][meet]} of {b['seeds']} seeds meet it)."
        )
        for r, name in hits:
            lines.append(
                f"  - median met: `{name}`, {r['label']}, {VARIANTS[r['variant']]}: "
                f"{_m(r[name][f'{key}_median'])} m, {r['masts_10s']['median']:g} masts per 10 s, "
                f"{r[name][meet]} of {r['seeds']} seeds"
                + (" (every seed)" if (r, name) in every else "")
            )
    lines += [
        "",
        "## What is heard during the outage",
        "",
        "After the cell lookup. Masts: registered eNBs within "
        f"{SAME_SITE_M:.0f} m are one mast. Per epoch and per {WINDOW_S:.0f} s window: median "
        "over seeds of each run's median, [min–max] over every run. Masts over the outage: "
        "median [min–max] over seeds. Told sigma does not change what is heard.",
        "",
        "| Configuration | Carriers | Record epochs /s | Masts per epoch | Masts per 10 s | "
        "Cells per 10 s | Masts over the outage | Records dropped by the lookup |",
        "|---|---|---|---|---|---|---|---|",
    ]

    def spread(s: dict) -> str:
        return f"{s['median']:g} [{s['min']:g}–{s['max']:g}]"

    for r in rows:
        if r["variant"] != "committed":
            continue
        lines.append(
            f"| {r['label']} | {', '.join(map(str, r['earfcn']))} | {r['epochs_per_s']:.2f} | "
            f"{spread(r['masts_epoch'])} | {spread(r['masts_10s'])} | {spread(r['cells_10s'])} | "
            f"{spread(r['masts_outage'])} | {100 * r['dropped_share']:.0f} % |"
        )
    for variant, text in VARIANTS.items():
        lines += [
            "",
            f"## Error, {text}",
            "",
            f"p95 horizontal error over the first {MENTOR_S} s and {T1_S} s of the outage: median "
            "over seeds (worst seed), and seeds meeting the target. HPL bound: share of the first "
            f"{T1_S} s where HPL >= error, median (min). Hazardous: epochs over the whole run "
            "(seeds with any).",
            "",
            f"| Configuration | Masts per 10 s | Estimator | p95 {MENTOR_S} s (m) | "
            f"<= {MENTOR_M:.0f} m | p95 {T1_S} s (m) | <= {T1_M:.0f} m | HPL bound {T1_S} s | "
            "Hazardous |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            if r["variant"] != variant:
                continue
            for name in ESTIMATORS:
                e = r[name]
                lines.append(
                    f"| {r['label']} | {r['masts_10s']['median']:g} | `{name}` | "
                    f"{_m(e['p95_120s_median'])} ({_m(e['p95_120s_worst'])}) | "
                    f"{e['p95_120s_meet']}/{r['seeds']} | "
                    f"{_m(e['p95_300s_median'])} ({_m(e['p95_300s_worst'])}) | "
                    f"{e['p95_300s_meet']}/{r['seeds']} | "
                    f"{e['hpl_bound_300s_median']:.2f} ({e['hpl_bound_300s_min']:.2f}) | "
                    f"{e['hazardous_epochs']} ({e['hazardous_seeds']}) |"
                )
    lines += [
        "",
        "## Not modelled",
        "",
        "- The front end's re-acquisition on air: the sim drops the first `reacquire_s` of each "
        "dwell and keeps every cell's arc; a real dongle may lose cells or start new arcs.",
        "- Record noise does not depend on how long a dwell is tracked: a 0.35 s record has the "
        "same noise as a 1 s one, and dwells under 1 s make more records per second than one "
        "carrier does (the record epochs column).",
        "- The link budget's in-band share assumes 10 MHz on every carrier; filed powers are read "
        "as given (Vidéotron rows 92 to 103 dBW, so every Vidéotron sector clears the noise "
        "floor). The near-far floor is relative within a carrier, so neither moves which "
        "sectors of a carrier are heard near its strongest.",
        "- No capture has hopped: every number here is the sim's, on registry geometry.",
        "",
    ]
    return "\n".join(lines)


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data["rows"]
    marker = {"reference": "D", "scan order": "o", "distinct eNB sets": "s"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), dpi=130, sharey=True)
    for ax, (key, t_s, target, who) in zip(
        axes,
        (("p95_120s", MENTOR_S, MENTOR_M, "mentors"), ("p95_300s", T1_S, T1_M, "T1, ours")),
        strict=True,
    ):
        for (name, variant), colour in COLOURS.items():
            for fam, mk in marker.items():
                pts = [r for r in rows if r["variant"] == variant and r["family"] == fam]
                if not pts:
                    continue
                x = [r["masts_10s"]["median"] for r in pts]
                y = [r[name][f"{key}_median"] for r in pts]
                worst = [r[name][f"{key}_worst"] for r in pts]
                ax.vlines(x, y, worst, color=colour, lw=0.8, alpha=0.6)
                ax.plot(x, y, mk, color=colour, ms=6, ls="none", alpha=0.9)
        ax.axhline(target, color=INK, lw=1.2, ls=":")
        ax.text(0.3, target * 0.78, f"{target:.0f} m at {t_s} s ({who}, TBC)", color=INK,
                fontsize=8)  # fmt: skip
        for r in rows:
            if r["family"] == "reference" and r["variant"] == "committed":
                y = max(r[n][f"{key}_median"] for n in ESTIMATORS)
                ax.annotate(
                    "1 carrier" if r["config"] == "one-carrier" else "all within 3 km",
                    (r["masts_10s"]["median"], y),
                    textcoords="offset points",
                    xytext=(4, 8),
                    fontsize=7,
                    color=INK,
                )
        ax.set_yscale("log")
        ax.set_xlim(left=0)
        ax.set_xlabel(f"masts heard per {WINDOW_S:.0f} s of the outage (median over seeds)")
        ax.set_title(f"first {t_s} s after GPS loss", fontsize=10, loc="left")
        ax.grid(True, which="major", color=GRID, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("p95 horizontal error (m): seed median, line to worst seed")
    handles = [
        plt.Line2D([], [], color=c, marker="o", ls="none", label=f"{n}, {VARIANTS[v]}")
        for (n, v), c in COLOURS.items()
    ] + [
        plt.Line2D([], [], color=INK, marker=mk, ls="none", label=fam)
        for fam, mk in marker.items()
    ]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.005, 0.93), ncol=4,
               fontsize=7.5, frameon=False)  # fmt: skip
    fig.suptitle(
        f"Carrier hopping study, drone leg outage ({ONE_CARRIER}, {HOPPING}): "
        f"seeds 0–{data['seeds'] - 1}, {data['commit']}"
        + (f", reproduced at {data['reproduced']['commit']}" if data.get("reproduced") else "")
        + " (sim, every value TBC)",
        fontsize=10,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--redraw", action="store_true", help="from study.json, without running")
    p.add_argument("--configs", help="comma-separated config keys to run (default: every one)")
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "study.json"
    if args.redraw:
        data = json.loads(path.read_text())
    else:
        cfgs = configs()
        if args.configs:
            keep = args.configs.split(",")
            unknown = set(keep) - {c["key"] for c in cfgs}
            if unknown:
                p.error(f"unknown configs: {sorted(unknown)}")
            cfgs = [c for c in cfgs if c["key"] in keep]
        tasks = [(c, v, s) for c in cfgs for v in VARIANTS for s in range(args.seeds)]
        t0 = time.perf_counter()
        runs = _map(run_one, tasks, args.jobs)
        data = {
            "command": f"python analysis/hopping_study.py --seeds {args.seeds} --jobs {args.jobs}"
            + (f" --configs {args.configs}" if args.configs else ""),
            "commit": _commit(),
            "seeds": args.seeds,
            "elapsed_min": (time.perf_counter() - t0) / 60,
            "estimators": list(ESTIMATORS),
            "variants": VARIANTS,
            "configs": cfgs,
            "rows": aggregate(runs, cfgs),
            "runs": [
                {
                    "config": r["config"],
                    "variant": r["variant"],
                    "seed": r["seed"],
                    "masts_10s": r["heard"]["masts_10s"]["median"],
                    "run_s": round(r["run_s"], 1),
                    **{
                        f"{n}_{k}": round(r[n][f"outage_h_p95_{k}_m"], 1)
                        for n in ESTIMATORS
                        for k in ("120s", "300s")
                    },
                }
                for r in runs
            ],
        }
        path.write_text(json.dumps(data, indent=1) + "\n")
    (args.out / "summary.md").write_text(summary(data))
    plot(data, args.out / "error_vs_masts.png")


if __name__ == "__main__":
    main()
