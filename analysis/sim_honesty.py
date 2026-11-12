"""Sensitivity of the challenge drone leg and `realistic-long-outage` to the sim terms of #278.

Each term (`TERMS`) is opt-in in the sim and off in every committed scenario. This study switches
them on one at a time, then together (`all`), on the same seeds as the scenario without them
(`base`). Every term draws on a random stream of its own, so a row differs from `base` only by
its term: the runs are paired.

Per row and estimator, over the T1 window (300 s from GPS loss; `calibrated_measured.per_run`):
- T1 (ADR-0034 amendment): at each second the 95th percentile of horizontal error across the
  runs; the worst second decides.
- Share of epochs above HPL: horizontal error over HPL, the mean over runs of each run's share
  in the window (1 - HPL bound rate), and the worst run's.

Estimators: `ekf`, `ekf-calibrated-measured`, and on the drone leg `ekf` with `arc_bias=True`
(`ekf-arc-bias`): on a real capture `ekf` turns the arc bias on by itself (ADR-0050), on the sim's
records it does not, so this row is what `ekf` does with arc restarts as on real data.
`ekf-honest` (#251) is not here: its branch does not merge onto `main` (conflicts in nav/ekf.py).

    python analysis/sim_honesty.py run --seeds 0-49 --jobs 3 --json rows.json
    python analysis/sim_honesty.py report --json rows.json \
        --out-dir analysis/results/sim-honesty-278

Sim only, placeholder environments (ADR-0015). Sizes and their sources: `TERMS`.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.experiments import _map
from pnt.nav import configured, estimate
from pnt.nav.ekf import run as ekf_run
from pnt.sim.scenario import generate, load

HERE = Path(__file__).parent
OUT = HERE / "results" / "sim-honesty-278"
SCENARIOS = {"drone": "challenge-drone-outage", "realistic": "realistic-long-outage"}
GPS_LOSS_S = 60.0  # both scenarios lose GPS at 60 s
ESTIMATORS = {
    "drone": ("ekf", "ekf-calibrated-measured", "ekf-arc-bias"),
    "realistic": ("ekf", "ekf-calibrated-measured"),
}

# Board temperature change (#241/#224, ADR-0045): the static receiver's BMP180 went from 6.5 to
# -1.2 C in its 10-minute session. The time constant is TBD (first-order, 300 s).
BOARD = {"change_k": -7.7, "tau_s": 300.0}
# The BMP180 read -3.4 to +77.5 m about the start over that change (ADR-0045, correlation -0.85):
# span over span, -80.9 m / 7.7 K. Not fitted: the session is not on this machine. TBC
BARO_M_PER_K = -10.5
GYRO_DPS_PER_K = 0.015  # one consumer gyro's datasheet (report 18.3). TBC for the MPU6050
SECTOR_M = (20.0, 50.0, 130.0)  # TBD: uniform +- these (sigma 12, 29, 75 m), swept
NEAR_FAR_DB = (-6.0, -20.0)  # TBD: the front end's floor, -13 dB on synthetic baseband (#133)


def _lte(spec):
    return spec["sources"]["lte"]


def _tropo(spec):
    _lte(spec)["troposphere"] = {"m_per_km": [0.3, 0.4]}


def _sector(x):
    def f(spec):
        spec["tower_clocks"]["sector"] = {"offset_m": x}

    return f


def _board(spec):
    spec["board_temperature"] = dict(BOARD)


def _gyro(spec):
    _board(spec)
    spec["sources"]["imu"]["gyro_temp_dps_per_k"] = GYRO_DPS_PER_K


def _baro(spec):
    _board(spec)
    spec["sources"]["baro"]["temp_m_per_k"] = BARO_M_PER_K


def _holdover(share):
    def f(spec):
        spec["faults"] = [
            *spec.get("faults", []),
            {"type": "tower_holdover", "source": "lte", "start_s": GPS_LOSS_S,
             "grade": "mixture", "network_share": share},
        ]  # fmt: skip

    return f


def _steering(spec):
    spec["tower_clocks"]["steering"] = {"jump_rate_hz": 1.0 / 60.0, "drift_ppb": 1.0}


def _floor(db):
    def f(spec):
        _lte(spec)["hearing"] = {**_lte(spec)["hearing"], "floor_db": db}

    return f


def _arcs(spec):
    _lte(spec)["arcs"] = {}


# (key, term, size, source, scenarios it applies to, how it changes the spec)
TERMS = (
    ("tropo", "Troposphere on near-horizontal ranges", "0.3 to 0.4 m per km of range, uniform "
     "per tower", "report 18.2 (checked for the paper; the application derived)", ("drone",
     "realistic"), _tropo),
    *((f"sector{int(x)}", "Constant bias per sector (antenna place + transmit delay)",
       f"uniform +-{x:.0f} m per sector (sigma {x / 3**0.5:.0f} m)", "TBD, swept (report 18.2: "
       "records off 30 to 50 m 'not uncommonly'; 5G cells 73 to 79 m steady bias, 17.2)",
       ("drone", "realistic"), _sector(x)) for x in SECTOR_M),
    ("gyro", "Gyro bias against temperature", f"{GYRO_DPS_PER_K} deg/s/K per axis (1 sigma), "
     f"board {BOARD['change_k']} K, tau {BOARD['tau_s']:.0f} s", "report 18.3 (datasheet "
     "snippet); temperature change: ADR-0045's session (#224); tau TBD", ("drone", "realistic"),
     _gyro),
    ("baro", "BMP180 tracking its temperature", f"{BARO_M_PER_K} m/K, board {BOARD['change_k']} K,"
     f" tau {BOARD['tau_s']:.0f} s", "our data: ADR-0045's session (#224, #241), span over span; "
     "tau TBD", ("drone", "realistic"), _baro),
    ("hold-mix", "Tower holdover, jamming reaches the towers, mixed", "half the sites "
     "network-held (30 ns in 3 h), half locally held (1 us in 3 h), from GPS loss", "report "
     "18.2 (lab tests, snippets); share TBD", ("drone", "realistic"), _holdover(0.5)),
    ("hold-local", "Tower holdover, every site locally held", "1 us in 3 h per site, from GPS "
     "loss", "report 18.2; share TBD (sweep end)", ("drone", "realistic"), _holdover(0.0)),
    ("hold-net", "Tower holdover, every site network-held", "30 ns in 3 h per builder, from GPS "
     "loss", "report 18.2; share TBD (sweep end)", ("drone", "realistic"), _holdover(1.0)),
    ("steering", "Towers steering in jumps", "drift jumps once a minute (Poisson), up to 1 ppb, "
     "per site", "Lapin et al., IEEE TVT 2024 (report 17.2, checked)", ("drone", "realistic"),
     _steering),
    *((f"floor{int(-db)}", "Cells heard: near-far floor", f"{db:.0f} dB below the strongest cell "
       "(leg: -13 dB)", "TBD, swept; -13 dB measured on synthetic baseband (#133); report 18.2",
       ("drone",), _floor(db)) for db in NEAR_FAR_DB),
    ("arcs", "Front-end arc restarts", "one per 43 s per cell; 9.4 % far (+-1.5 km), else "
     "8.0 m sigma", "our data: lte-reacq-steps (#233, #245), model of #262 (ADR-0049); far size "
     "TBC", ("drone",), _arcs),
)  # fmt: skip
ALL = ("tropo", "sector50", "gyro", "baro", "hold-mix", "steering", "arcs")


def variants(where: str) -> list[str]:
    return ["base", *(t[0] for t in TERMS if where in t[4]), "all"]


def spec_of(where: str, key: str) -> dict:
    spec = copy.deepcopy(load(SCENARIOS[where]))
    keys = [] if key == "base" else ALL if key == "all" else [key]
    by_key = {t[0]: t for t in TERMS}
    for k in keys:
        if where in by_key[k][4]:
            by_key[k][5](spec)
    return spec


def _cm():
    """`analysis/calibrated_measured.py` as a module (its per-run and across-run numbers)."""
    if "calibrated_measured" not in sys.modules:
        path = HERE / "calibrated_measured.py"
        spec = importlib.util.spec_from_file_location("calibrated_measured", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["calibrated_measured"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["calibrated_measured"]


def _estimator(name: str):
    return configured(ekf_run, arc_bias=True) if name == "ekf-arc-bias" else name


def run_task(where: str, key: str, seed: int) -> dict:
    spec = spec_of(where, key)
    run = generate(spec, seed=seed)
    out = {}
    for name in ESTIMATORS[where]:
        est = estimate(
            _estimator(name), run.measurements, origin_llh=spec.get("origin_llh"),
            reference=run.reference,
        )  # fmt: skip
        r = _cm().per_run(list(est), run.truth, spec)
        out[name] = {k: r[k] for k in ("err_per_s", "win_hpl_bound", "win_p95_m", "hazardous")}
    return out


def run(seeds: list[int], jobs: int) -> dict:
    tasks = [(w, k, s) for w in SCENARIOS for k in variants(w) for s in seeds]
    results = _map(run_task, tasks, jobs)
    rows = []
    for w in SCENARIOS:
        for k in variants(w):
            runs = [r for (tw, tk, _), r in zip(tasks, results, strict=True) if (tw, tk) == (w, k)]
            for name in ESTIMATORS[w]:
                err = np.array([r[name]["err_per_s"] for r in runs])
                curve = np.percentile(err, 95, axis=0)
                above = np.array([1.0 - r[name]["win_hpl_bound"] for r in runs])
                rows.append({
                    "scenario": w, "term": k, "estimator": name, "runs": len(runs),
                    "t1_m": float(curve.max()), "t1_second": int(curve.argmax()),
                    "t1_at_120s_m": float(curve[:120].max()),
                    "above_hpl_mean": float(above.mean()), "above_hpl_worst": float(above.max()),
                    "hazardous_total": int(sum(r[name]["hazardous"] for r in runs)),
                    "win_p95_by_seed": [round(r[name]["win_p95_m"], 2) for r in runs],
                })  # fmt: skip
    return {"commit": _commit(), "seeds": seeds, "rows": rows}


def _term(key: str):
    return next(t for t in TERMS if t[0] == key)


def _m(x: float) -> str:
    return f"{x:,.0f}" if x >= 100 else f"{x:.1f}"


def summary(data: dict) -> str:
    seeds = data["seeds"]
    rows = data["rows"]
    base = {(r["scenario"], r["estimator"]): r for r in rows if r["term"] == "base"}
    lines = [
        "# Sim honesty: sensitivity to the missing error terms (#278)",
        "",
        f"Evidence: **sim**, placeholder environments (ADR-0015). Commit `{data['commit']}`; "
        f"seeds {seeds[0]}-{seeds[-1]} ({len(seeds)} runs per row), paired: every term draws "
        "on a stream of its own. Generated by `analysis/sim_honesty.py`.",
        "",
        "T1: worst second of the per-second 95th percentile of horizontal error across runs, "
        "0-300 s after GPS loss (ADR-0034). Above HPL: share of epochs in that window with "
        "error over HPL, mean run (worst run). Δ: against `base`, same estimator and seeds. "
        "Paired: each run's own 95th percentile of error over the window, minus the same seed's "
        "in `base`; the median over seeds, and how many seeds got worse by more than 1 m.",
        "",
        "## Terms",
        "",
        "| Term | Key | Size | Source |",
        "| --- | --- | --- | --- |",
    ]
    for k, label, size, src, _w, _f in TERMS:
        lines.append(f"| {label} | `{k}` | {size} | {src} |")
    lines += ["", f"`all`: {', '.join(f'`{k}`' for k in ALL)} (drone leg; `arcs` is "
              "front-end only, so not on `realistic`). The near-far floor stays at the leg's "
              "-13 dB in `all`.", ""]  # fmt: skip
    for w, scen in SCENARIOS.items():
        names = ESTIMATORS[w]
        lines += [f"## `{scen}`", "", "| Term | " + " | ".join(
            f"`{n}` T1 m (Δ) | paired median Δ m (worse) | above HPL" for n in names) + " |",
            "| --- |" + " --- | --- | --- |" * len(names)]  # fmt: skip
        for k in variants(w):
            cells = []
            for n in names:
                r = next(
                    x for x in rows if (x["scenario"], x["term"], x["estimator"]) == (w, k, n)
                )
                b = base[(w, n)]
                d = r["t1_m"] - b["t1_m"]
                delta = "" if k == "base" else f" ({'+' if d >= 0 else '−'}{_m(abs(d))})"
                pd = np.subtract(r["win_p95_by_seed"], b["win_p95_by_seed"])
                paired = "" if k == "base" else (
                    f"{'+' if np.median(pd) >= 0 else '−'}{_m(abs(float(np.median(pd))))} "
                    f"({int(np.sum(pd > 1.0))}/{len(pd)})")  # fmt: skip
                cells += [f"{_m(r['t1_m'])}{delta}", paired,
                          f"{r['above_hpl_mean']:.3f} ({r['above_hpl_worst']:.3f})"]  # fmt: skip
            lines.append(f"| `{k}` | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def plot(data: dict, out: Path) -> None:
    """Per term and estimator: the paired change of each run's window p95 against `base` (same
    seed), as the median (bar) and the 10th to 90th percentile across seeds (whisker)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = data["rows"]
    colours = {"ekf": "#2a78d6", "ekf-calibrated-measured": "#eb6834", "ekf-arc-bias": "#1baf7a"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.5))
    for ax, (w, scen) in zip(axes, SCENARIOS.items(), strict=True):
        keys = [k for k in variants(w) if k != "base"]
        names = ESTIMATORS[w]
        width = 0.8 / len(names)
        y = np.arange(len(keys))
        for j, n in enumerate(names):
            base = next(x for x in rows if (x["scenario"], x["term"], x["estimator"])
                        == (w, "base", n))["win_p95_by_seed"]  # fmt: skip
            med, lo, hi = [], [], []
            for k in keys:
                r = next(
                    x for x in rows if (x["scenario"], x["term"], x["estimator"]) == (w, k, n)
                )
                d = np.subtract(r["win_p95_by_seed"], base)
                med.append(np.median(d))
                lo.append(np.percentile(d, 10))
                hi.append(np.percentile(d, 90))
            yy = y + (j - (len(names) - 1) / 2) * width
            med = np.array(med)
            ax.barh(yy, med, width * 0.9, color=colours[n], label=n)
            ax.errorbar(med, yy, xerr=[med - np.array(lo), np.array(hi) - med], fmt="none",
                        ecolor="#555", elinewidth=0.8, capsize=2)  # fmt: skip
        ax.set_yticks(y, keys)
        ax.invert_yaxis()
        ax.set_xscale("symlog", linthresh=10.0)
        ax.axvline(0.0, color="#888", lw=0.8)
        ax.set_xlabel("change of each run's p95 error, 0-300 s after GPS loss, vs base (m)")
        ax.set_title(scen)
        ax.grid(axis="x", alpha=0.3)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle(
        f"#278 terms one at a time, then all: paired change per seed, median (bar) and "
        f"10-90 % (whisker)\nsim, seeds {data['seeds'][0]}-{data['seeds'][-1]}, commit "
        f"{data['commit']}; symlog axis, linear within +-10 m"
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(out, dpi=110)
    plt.close(fig)


def _seeds(text: str) -> list[int]:
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--seeds", default="0-49")
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--json", type=Path, required=True)
    p = sub.add_parser("report")
    p.add_argument("--json", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        data = run(_seeds(a.seeds), a.jobs)
        a.json.write_text(json.dumps(data))
    else:
        data = json.loads(a.json.read_text())
        a.out_dir.mkdir(parents=True, exist_ok=True)
        (a.out_dir / "summary.md").write_text(summary(data) + "\n")
        plot(data, a.out_dir / "sensitivity.png")


if __name__ == "__main__":
    main()
