"""Our receiver clock in the tower ranges, which `ekf` leaves out by default (#228).

    python analysis/rx_clock_in_towers.py --runs 50 --jobs 3 --out analysis/results/rx-clock

The realistic and worst sets put our payload clock (20 ppb drift, 2 ns/sqrt(s) walk) into every
tower reading (`receiver_clock: true`), as a real radio would. `ekf` defaults to
`pseudorange_receiver_clock=False`, so each tower's own clock (a random walk of 0.2 m/sqrt(s))
has to absorb a common 6 m/s ramp. With GNSS lost, the filter accepts those readings and moves
the position instead, at about the clock's drift rate, while the covariance shrinks as if the
towers fixed it. This script measures that, paired by seed (seeds 0..runs-1):

1. Variants: `ekf`, `ekf-imu` and `ekf-calibrated`, each with our clock in the tower model on and
   off (`ekf-calibrated` has it on; the others off), and `baseline`, over `--scenarios`.
   Per variant: the T1 slice (p95 horizontal error over the first 300 s after GPS loss) and its
   HPL bound rate, the run's p95, HPL bound rate, misleading and hazardous epochs, and per
   source the share of updates the gate accepts while GPS is lost, with their median NIS.
2. Mechanism, on `--mechanism` (default realistic-long-outage), `ekf`: the simulated clock drift
   at 0, 20 (the set's) and 40 ppb, with the LTE records kept or dropped. The clock's draws do
   not depend on its drift, so the rows share every draw.
3. Figure: horizontal error and HPL after GPS loss on `--mechanism`'s worst `ekf` run, for `ekf`
   and for `ekf` with our clock in the tower model.

Writes summary.md, summary.json, error_vs_hpl.png and drift.png into `--out`.

With `--costs` it runs only the cost study instead (ADR-0045's follow-up): can the term be kept
without its costs on the base sets? `COST_VARIANTS` over `COST_SCENARIOS`, paired with `ekf`
(mean difference and its standard error over the seeds): the term always on, on only once GNSS
time has been used (`observed`) or only while GNSS position is lost (`gnss_out`), with a smaller
clock frequency wander (`h_2`), and with the jump guard. Then the scenarios whose payload has a
clock but whose towers leave it out (`COST_SIM_RX`) are rerun with it in the towers
(`receiver_clock: true`, a sim change, so those rows pair only with each other). Writes
costs.md and costs.json.

Sim only; every model in these sets is a placeholder (systems/verification.md, *Sim validity*).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from pnt import metrics, nav
from pnt.integrity.jump_guard import JumpGuard
from pnt.nav import cells, ekf
from pnt.sim.scenario import T0_NS, generate, load

SCENARIOS = (
    "realistic-long-outage",
    "realistic-outage",
    "realistic-nominal",
    "worst-long-outage",
    "nominal",
    "gps-outage",
    "spoof-ramp",
    "meaconing",
    "challenge-approach-outage",
    "challenge-drone-outage",
)
RX = {"pseudorange_receiver_clock": True}
# name -> (EKF config, or None for the `baseline` registry entry). The three registry EKFs, then
# each with our clock in the tower model switched the other way.
VARIANTS = {
    "ekf": {},
    "ekf +rx clock": RX,
    "ekf-imu": {"motion": "imu"},
    "ekf-imu +rx clock": {"motion": "imu", **RX},
    "ekf-calibrated": ekf.CALIBRATED,
    "ekf-calibrated -rx clock": {**ekf.CALIBRATED, "pseudorange_receiver_clock": False},
    "baseline": None,
}
COST_VARIANTS = {
    "ekf": {},
    "ekf +rx clock": RX,
    "ekf rx clock observed": {"pseudorange_receiver_clock": "observed"},
    "ekf rx clock gnss_out": {"pseudorange_receiver_clock": "gnss_out"},
    "ekf +rx clock, h_2 2e-22": {**RX, "h_2": 2e-22},
    "ekf-guard": {"jump_guard": JumpGuard},
    "ekf-guard +rx clock": {"jump_guard": JumpGuard, **RX},
}
CONFIGS = {**VARIANTS, **COST_VARIANTS}  # every variant name -> its config
COST_SCENARIOS = (
    "gps-outage",
    "spoof-ramp",
    "meaconing",
    "easy-long-outage",
    "realistic-long-outage",
    "realistic-outage",
)
# Scenarios whose payload clock (`clock:`, with GNSS time) is left out of their tower readings
COST_SIM_RX = ("meaconing", "easy-long-outage")
COST_SIM_VARIANTS = ("ekf", "ekf +rx clock", "ekf-guard", "ekf-guard +rx clock")
SHORT = ("ekf", "ekf +rx clock")  # the variants run on every scenario; the rest on --mechanism
DRIFTS_PPB = (0.0, 20.0, 40.0)
KEYS = (
    "outage_h_p95_300s_m",
    "outage_hpl_bound_300s",
    "h_p95_m",
    "hpl_bound_frac",
    "misleading_epochs",
    "hazardous_epochs",
)
COLORS = {"error": "#2a78d6", "hpl": "#eb6834"}  # categorical slots 1 and 2


class _Logged(ekf.EKF):
    """`ekf.EKF` that logs every gated update: (t_ns, source key, accepted, NIS)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.updates: list[tuple[int, str, bool, float]] = []

    def _update(self, key, t_ns, y, H, R, gate=True):
        ok = super()._update(key, t_ns, y, H, R, gate)
        if gate:
            self.updates.append((t_ns, key, ok, self._last_nis[0]))
        return ok


def _run_ekf(meas, origin_llh, config, epoch_ns=100_000_000):
    """`ekf.run`'s loop with the logged filter: (estimates, logged updates)."""
    f = _Logged(origin_llh=origin_llh, **config)
    out, next_epoch = [], None
    for m in meas:
        if f.x is not None:
            if next_epoch is None:
                next_epoch = (f.t_ns // epoch_ns + 1) * epoch_ns
            while next_epoch <= m.t_ns:
                f.predict(next_epoch)
                out.append(f.estimate())
                next_epoch += epoch_ns
        f.process(m)
    return out, f.updates


def one(
    scenario: str, variant: str, seed: int, drift_ppb=None, drop_lte=False, curve=False, rx=False
):
    spec = load(scenario)
    if rx:
        spec["sources"]["lte"]["receiver_clock"] = True
    if drift_ppb is not None:
        spec["clock"] = {**spec["clock"], "drift_ppb": drift_ppb}
    run = generate(spec, seed=seed)
    meas = [m for m in run.measurements if not (drop_lte and m.source == "lte")]
    origin = spec.get("origin_llh")
    config = CONFIGS[variant]
    if config is None:
        est, updates = list(nav.estimate(variant, meas, origin_llh=origin)), []
    else:
        payload = [m for m in meas if m.receiver in nav.DEFAULT_RECEIVERS]
        est, updates = _run_ekf(cells.attach(payload, origin), origin, config)
    m = metrics.score(est, run.truth, spec, T0_NS)
    row = {k: getattr(m, k) for k in KEYS}
    loss = metrics.gps_loss(spec, T0_NS)
    gate = defaultdict(lambda: [0, 0, []])  # source -> [accepted, gated, NIS] while GPS is lost
    if loss is not None:
        end = loss[1] if loss[1] is not None else np.iinfo(np.int64).max
        for t, key, ok, nis in updates:
            if loss[0] <= t < end:
                g = gate[key]
                g[0] += ok
                g[1] += 1
                g[2].append(nis)
    row["gate"] = {k: (a, n, float(np.median(x))) for k, (a, n, x) in gate.items()}
    if curve and loss is not None:
        tmap = {t.t_ns: t.pos_enu for t in run.truth}
        e = [x for x in est if x.t_ns in tmap and x.t_ns >= loss[0]]
        row["curve"] = {
            "t_s": [(x.t_ns - loss[0]) / 1e9 for x in e],
            "err": [float(np.hypot(*np.subtract(x.pos_enu, tmap[x.t_ns])[:2])) for x in e],
            "hpl": [x.hpl_m for x in e],
        }
    return row


def _star(args):
    return one(*args)


def _summary(rows: list[dict]) -> dict:
    a = {k: np.array([r[k] for r in rows], float) for k in KEYS}

    def nanmean(x):
        return float(np.nanmean(x)) if np.isfinite(x).any() else float("nan")

    def nanworst(x, fn):
        return float(fn(x)) if np.isfinite(x).any() else float("nan")

    gate = {}
    for src in sorted({s for r in rows for s in r["gate"]}):
        acc = sum(r["gate"].get(src, (0, 0, 0))[0] for r in rows)
        n = sum(r["gate"].get(src, (0, 0, 0))[1] for r in rows)
        med = [r["gate"][src][2] for r in rows if src in r["gate"]]
        gate[src] = {"accept": acc / n if n else float("nan"), "nis_median": float(np.median(med))}
    return {
        "runs": len(rows),
        "t1_p95_mean_m": nanmean(a["outage_h_p95_300s_m"]),
        "t1_p95_worst_m": nanworst(a["outage_h_p95_300s_m"], np.nanmax),
        "t1_hpl_bound_worst": nanworst(a["outage_hpl_bound_300s"], np.nanmin),
        "p95_mean_m": nanmean(a["h_p95_m"]),
        "hpl_bound_worst": float(a["hpl_bound_frac"].min()),
        "misleading_per_run": float(a["misleading_epochs"].mean()),
        "hazardous_per_run": float(a["hazardous_epochs"].mean()),
        "gate_while_gps_lost": gate,
        "t1_per_seed_m": [float(x) for x in a["outage_h_p95_300s_m"]],
    }


def _commit() -> str:
    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()

    dirty = " (dirty)" if git("status", "--porcelain") else ""
    return git("rev-parse", "--short", "HEAD") + dirty


def _fmt(x, f="{:.1f}"):
    return "—" if x != x else f.format(x)


def _figures(out: Path, curves: dict, seed: int, drift: list[dict], scenario: str, commit: str):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, (name, c) in zip(axes, curves.items(), strict=True):
        ax.plot(c["t_s"], c["err"], color=COLORS["error"], lw=2, label="horizontal error")
        ax.plot(c["t_s"], c["hpl"], color=COLORS["hpl"], lw=2, ls="--", label="HPL")
        ax.set_yscale("log")
        ax.set_title(name, fontsize=10)
        ax.set_xlabel("time after GPS loss (s)")
        ax.grid(True, which="major", color="0.9", lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("metres (log)")
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle(f"{scenario}, seed {seed} (worst ekf run by T1): error and HPL", fontsize=11)
    fig.text(0.01, 0.01, f"sim, placeholder models; commit {commit}", fontsize=7, color="0.4")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "error_vs_hpl.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    for drop, ls, label, color in (
        (False, "-", "towers kept", COLORS["error"]),
        (True, "--", "towers dropped", "#7a7974"),  # gray: the reference
    ):
        pts = sorted((r["drift_ppb"], r["t1_p95_mean_m"]) for r in drift if r["drop_lte"] == drop)
        ax.plot(*zip(*pts, strict=True), ls=ls, marker="o", ms=8, lw=2, color=color,
                label=label)  # fmt: skip
        ax.annotate(label, pts[-1], textcoords="offset points", xytext=(6, 0), fontsize=8,
                    va="center", color="0.25")  # fmt: skip
    ax.set_xlabel("simulated payload clock drift (ppb)")
    ax.set_ylabel("T1 p95, mean over runs (m)")
    ax.set_xticks(DRIFTS_PPB)
    ax.set_xlim(-4, 52)
    ax.set_ylim(bottom=0)
    ax.grid(True, color="0.9", lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title(f"{scenario}, ekf: error follows our clock's drift", fontsize=10)
    fig.text(0.01, 0.01, f"sim, placeholder models; commit {commit}", fontsize=7, color="0.4")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "drift.png", dpi=130)
    plt.close(fig)


def _paired(rows: list[dict], base: list[dict], key: str) -> tuple[float, float]:
    d = np.array([r[key] - b[key] for r, b in zip(rows, base, strict=True)], float)
    d = d[np.isfinite(d)]
    if not d.size:
        return float("nan"), float("nan")
    return float(d.mean()), float(d.std(ddof=1) / np.sqrt(d.size)) if d.size > 1 else 0.0


def costs(args, commit: str) -> None:
    seeds = range(args.runs)
    tasks = {}
    for scn in COST_SCENARIOS:
        for v in COST_VARIANTS:
            for s in seeds:
                tasks[(scn, v, s, False)] = (scn, v, s, None, False, False, False)
    for scn in COST_SIM_RX:
        for v in COST_SIM_VARIANTS:
            for s in seeds:
                tasks[(scn, v, s, True)] = (scn, v, s, None, False, False, True)
    with ProcessPoolExecutor(args.jobs) as pool:
        results = dict(zip(tasks, pool.map(_star, tasks.values()), strict=True))
    groups = [(scn, False, list(COST_VARIANTS)) for scn in COST_SCENARIOS]
    groups += [(scn, True, list(COST_SIM_VARIANTS)) for scn in COST_SIM_RX]
    table = []
    for scn, rx, variants in groups:
        base = [results[(scn, "ekf", s, rx)] for s in seeds]
        for v in variants:
            rows = [results[(scn, v, s, rx)] for s in seeds]
            row = {"scenario": scn, "towers_carry_our_clock": rx, "variant": v, **_summary(rows)}
            for k in ("h_p95_m", "outage_h_p95_300s_m", "misleading_epochs", "hazardous_epochs"):
                row[f"d_{k}"] = _paired(rows, base, k)
            table.append(row)
    (args.out / "costs.json").write_text(
        json.dumps({"commit": commit, "runs": args.runs, "table": table}, indent=1)
    )

    def pm(x):
        return "—" if x[0] != x[0] else f"{x[0]:+.1f} ± {x[1]:.1f}"

    lines = [
        "# Keeping our clock in the tower ranges without its costs (#228, ADR-0045)",
        "",
        f"Commit `{commit}`, seeds 0-{args.runs - 1} (paired), sim with placeholder models. "
        "Δ: mean paired difference from `ekf` in the same rows ± its standard error. "
        "Rows marked *sim: towers carry our clock* rerun that scenario with "
        "`receiver_clock: true` (a sim change: they pair only with each other).",
        "",
        "| Scenario | Variant | p95 mean (m) | Δ p95 (m) | T1 p95 mean (m) | Δ T1 (m) "
        "| T1 HPL bound, worst run | Misleading / run | Δ misleading | Hazardous / run "
        "| Δ hazardous |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in table:
        scn = f"`{r['scenario']}`" + (
            " (sim: towers carry our clock)" if r["towers_carry_our_clock"] else ""
        )
        lines.append(
            f"| {scn} | `{r['variant']}` | {_fmt(r['p95_mean_m'])} | {pm(r['d_h_p95_m'])} "
            f"| {_fmt(r['t1_p95_mean_m'])} | {pm(r['d_outage_h_p95_300s_m'])} "
            f"| {_fmt(r['t1_hpl_bound_worst'], '{:.3f}')} | {r['misleading_per_run']:.1f} "
            f"| {pm(r['d_misleading_epochs'])} | {r['hazardous_per_run']:.1f} "
            f"| {pm(r['d_hazardous_epochs'])} |"
        )
    lines.append("")
    (args.out / "costs.md").write_text("\n".join(lines))
    print("\n".join(lines))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    p.add_argument("--mechanism", default="realistic-long-outage")
    p.add_argument("--out", type=Path, default=Path("analysis/results/rx-clock"))
    p.add_argument("--costs", action="store_true", help="run only the cost study (costs.md)")
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    seeds = range(args.runs)
    commit = _commit()
    if args.costs:
        costs(args, commit)
        return

    tasks = {}
    for scn in args.scenarios:
        for v in VARIANTS if scn == args.mechanism else SHORT:
            for s in seeds:
                tasks[(scn, v, s, None, False)] = (scn, v, s, None, False, False)
    for d in DRIFTS_PPB:
        for drop in (False, True):
            for s in seeds:
                tasks[(args.mechanism, "ekf", s, d, drop)] = (args.mechanism, "ekf", s, d, drop)
    with ProcessPoolExecutor(args.jobs) as pool:
        results = dict(zip(tasks, pool.map(_star, tasks.values()), strict=True))

    table = []
    for scn in args.scenarios:
        for v in VARIANTS if scn == args.mechanism else SHORT:
            rows = [results[(scn, v, s, None, False)] for s in seeds]
            table.append({"scenario": scn, "variant": v, **_summary(rows)})
    drift = []
    for d in DRIFTS_PPB:
        for drop in (False, True):
            rows = [results[(args.mechanism, "ekf", s, d, drop)] for s in seeds]
            drift.append({"drift_ppb": d, "drop_lte": drop, **_summary(rows)})

    ekf_t1 = next(r for r in table if (r["scenario"], r["variant"]) == (args.mechanism, "ekf"))
    worst = int(np.nanargmax(ekf_t1["t1_per_seed_m"]))
    with ProcessPoolExecutor(2) as pool:
        named = ("ekf", "ekf +rx clock")
        got = pool.map(_star, [(args.mechanism, v, worst, None, False, True) for v in named])
        curves = {
            f"{v} (T1 HPL bound {r['outage_hpl_bound_300s']:.2f})": r["curve"]
            for v, r in zip(named, got, strict=True)
        }
    _figures(args.out, curves, worst, drift, args.mechanism, commit)

    (args.out / "summary.json").write_text(
        json.dumps(
            {"commit": commit, "runs": args.runs, "table": table, "drift": drift, "worst": worst},
            indent=1,
        )
    )
    lines = [
        "# Our clock in the tower ranges (#228)",
        "",
        f"Commit `{commit}`, seeds 0-{args.runs - 1} (paired), sim with placeholder models. "
        "T1: p95 horizontal error over the first 300 s after GPS loss (`outage_h_p95_300s_m`); "
        "its HPL bound is the worst run's share of those epochs with HPL >= error. "
        "Gate: share of updates accepted while GPS is lost (median NIS), all runs pooled.",
        "",
        "| Scenario | Variant | T1 p95 mean (m) | T1 worst run (m) | T1 HPL bound, worst run "
        "| p95 mean (m) | HPL bound, worst run | Misleading / run | Hazardous / run "
        "| LTE gate (NIS) | Baro gate (NIS) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    def gate(r, src):
        g = r["gate_while_gps_lost"].get(src)
        return "—" if g is None else f"{g['accept']:.2f} ({g['nis_median']:.1f})"

    for r in table:
        lines.append(
            f"| `{r['scenario']}` | `{r['variant']}` | {_fmt(r['t1_p95_mean_m'])} "
            f"| {_fmt(r['t1_p95_worst_m'])} | {_fmt(r['t1_hpl_bound_worst'], '{:.3f}')} "
            f"| {_fmt(r['p95_mean_m'])} | {r['hpl_bound_worst']:.3f} "
            f"| {r['misleading_per_run']:.1f} | {r['hazardous_per_run']:.1f} "
            f"| {gate(r, 'lte')} | {gate(r, 'baro')} |"
        )
    lines += [
        "",
        f"## Mechanism: `{args.mechanism}`, `ekf`, simulated clock drift",
        "",
        "| Drift (ppb) | Towers | T1 p95 mean (m) | T1 HPL bound, worst run | LTE gate (NIS) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in drift:
        lines.append(
            f"| {r['drift_ppb']:.0f} | {'dropped' if r['drop_lte'] else 'kept'} "
            f"| {_fmt(r['t1_p95_mean_m'])} | {_fmt(r['t1_hpl_bound_worst'], '{:.3f}')} "
            f"| {gate(r, 'lte')} |"
        )
    lines += ["", f"Figures: `error_vs_hpl.png` (seed {worst}), `drift.png`.", ""]
    (args.out / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
