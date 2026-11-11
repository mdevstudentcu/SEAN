"""#214 with the day's three fixes combined: the real GPS cut on two real static sessions.

    python analysis/results/real-gps-cut-combined-20261111/run_combined.py \
        <0151>-lte <0233>-lte --out analysis/results/real-gps-cut-combined-20261111 [--jobs 3]

Each `<session>-lte` is a real session after `pnt frontend lte` run with #183's front end. Runs
`analysis/real_gps_cut.py`'s method unchanged (`run_one`, `hold_last_fix`, `aggregate`: GNSS cut
in software with the attack library's `outage` fault at each cut time, scored against the
withheld GPS fixes) for these estimators, all opt-in here, nothing under `src/` changed:

- `ekf`: the default.
- `ekf+rx`: `ekf` with `pseudorange_receiver_clock=True` (ADR-0045 Proposed, #228).
- `B`: `ekf-measured-sigma` (#147, ADR-0044 Proposed: LTE records told ADR-0036's measured σ).
- `B+rx`: `B` with `pseudorange_receiver_clock=True`.
- `B+arc`: `B` with `arc_bias=True` (#147's opt-in: a cell's new arc gets its own range bias),
  pseudoranges only. Not one of the three fixes asked for; run because most new arcs step.
- `no LTE`: `ekf` with every LTE record dropped; and `hold`, the last fix before the cut held.

LTE records as the front end wrote them: pseudoranges only (`told-pr`) and pseudoranges with
dopplers (`told`). Cuts every 300 s from 300 s on the 1 h session; 100 to 300 s by 50 s on the
600 s one (#214's), each scored for 300 s.

Writes summary.json, summary.md and error_after_cut.png into `--out`: errors and HPL only, never
a position, origin, range or bearing (the sessions are at a private site).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from pnt import experiments, nav
from pnt.nav import ESTIMATORS, configured, ekf
from pnt.sim import attacks

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CUT_SCRIPT = REPO / "analysis" / "real_gps_cut.py"

# Inputs merged, in this order, onto origin/main c21e047 in the local branch tmp/e2e-combined
INPUTS = (
    ("origin/main", "c21e047"),
    ("shrikar/feat/214-real-gps-cut", "8e7a216"),
    ("shrikar/fix/183-lte-real-capture-bugs", "0ebe18a"),
    ("shrikar/fix/147-measured-told-sigma", "e39742f"),
    ("shrikar/fix/228-long-outage-drift", "85d1324"),
)

# name -> (registry name, LTE variants run)
ESTS = {
    "ekf": "ekf",
    "ekf+rx": "e2e:ekf+rx",
    "B": "ekf-measured-sigma",
    "B+rx": "e2e:B+rx",
    "B+arc": "e2e:B+arc",
}
ESTIMATORS["e2e:ekf+rx"] = configured(ekf.run, pseudorange_receiver_clock=True)
ESTIMATORS["e2e:B+rx"] = configured(
    ekf.run, told_sigma_model="adr0036", pseudorange_receiver_clock=True
)
ESTIMATORS["e2e:B+arc"] = configured(ekf.run, told_sigma_model="adr0036", arc_bias=True)
LTE = {"told-pr": "PR", "told": "PR+doppler"}
ONLY_PR = ("B+arc",)  # run with pseudoranges only
HORIZON_S = 300.0
AT_S = (30.0, 60.0, 120.0, 300.0)


def _cut():
    spec = importlib.util.spec_from_file_location("real_gps_cut", CUT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CUT = _cut()


def run_one(path: str, name: str, lte: str, cut_s: float) -> dict:
    reg = ESTS.get(name, "ekf")
    out = CUT.run_one(path, reg, lte, cut_s)
    out["estimator"], out["variant"] = name, LTE.get(lte, "none")
    curve = np.array([out["after_s"], out["err_m"], out["hpl_m"]], float)
    out["hash"] = hashlib.sha1(curve.tobytes()).hexdigest()[:12]
    return out


# Stress (the receiver is static, so a coast that holds still is right by construction): GNSS
# is pulled at DRIFT_MPS for the DRIFT_S before the cut (the attack library's `spoof_ramp`,
# software fault injection), so the filter enters the coast DRIFT_S * DRIFT_MPS off and moving
# at DRIFT_MPS, as a coast that has drifted would. Scored against the real, unpulled fixes. A
# coast with no other source keeps drifting; LTE that carries information pulls it back. TBC:
# an illustration, not a model of any drone.
DRIFT_MPS, DRIFT_S, DRIFT_DEG = 1.0, 60.0, 45.0
STRESS = (
    ("no LTE", "none"),
    ("ekf", "told-pr"),
    ("ekf", "told"),
    ("B", "told-pr"),
    ("B", "told"),
    ("B+arc", "told-pr"),
)


def run_stress(path: str, name: str, lte: str, cut_s: float) -> dict:
    meas, t0, origin = CUT.load(path)
    fix_t, fix_pos = CUT.gps_fixes(meas)  # truth: the real fixes, not the pulled ones
    ramp = {"type": "spoof_ramp", "source": "gnss", "rate_mps": DRIFT_MPS,
            "direction_deg": DRIFT_DEG, "start_s": cut_s - DRIFT_S, "end_s": cut_s}  # fmt: skip
    cut = {"type": "outage", "source": "gnss", "start_s": cut_s}
    ctx = attacks.Context(t0_ns=t0, origin_llh=None, truth_pos=None, rng=None)
    fed, _ = attacks.apply(meas, [ramp, cut], ctx)
    est = list(nav.estimate(ESTS.get(name, "ekf"), CUT.lte_variant(fed, lte), origin_llh=origin))
    est_t = np.array([e.t_ns for e in est], dtype=np.int64)
    est_pos = np.array([e.pos_enu for e in est], dtype=float)
    est_hpl = np.array([e.hpl_m for e in est], dtype=float)
    out = {"estimator": name, "variant": LTE.get(lte, "none") + ", drift", "cut_s": cut_s}
    out.update(CUT.score_cut(est_t, est_pos, est_hpl, fix_t, fix_pos, t0 + round(cut_s * 1e9)))
    out["pre_p95_m"], out["pre_gnss_excluded"] = math.nan, math.nan
    return out


def cuts_for(duration_s: float) -> list[float]:
    if duration_s < 1000:
        return [100.0, 150.0, 200.0, 250.0, 300.0]
    return [float(c) for c in range(300, int(duration_s - HORIZON_S) + 1, 300)]


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return r.stdout.strip()


def session_summary(path: str, jobs: int) -> tuple[dict, list[dict]]:
    meas, t0, _ = CUT.load(path)
    fix_t, fix_pos = CUT.gps_fixes(meas)
    dur = (fix_t[-1] - t0) / 1e9
    cuts = cuts_for(dur)
    tasks = [
        (path, n, lte, c)
        for n in ESTS
        for lte in LTE
        for c in cuts
        if n not in ONLY_PR or lte == "told-pr"
    ]
    tasks += [(path, "no LTE", "none", c) for c in cuts]
    rows = experiments._map(run_one, tasks, jobs)
    stress = [(path, n, lte, c) for n, lte in STRESS for c in cuts]
    rows += experiments._map(run_stress, stress, jobs)
    for c in cuts:
        h = CUT.hold_last_fix(fix_t, fix_pos, t0 + round(c * 1e9))
        rows.append({"estimator": "hold", "variant": "last fix", "cut_s": c, **h})
        rows[-1]["pre_p95_m"] = math.nan
    agg = CUT.aggregate(rows)
    for key, a in agg.items():  # the worst second: largest error at any withheld fix
        rs = [r for r in rows if f"{r['estimator']}|{r['variant']}" == key]
        a["worst_second_m"] = float(max(max(r["err_m"]) for r in rs if r["err_m"]))
        if key.endswith(", drift"):
            a.pop("pre_gnss_excluded", None)
    same = {
        f"{rx} vs {base}, {LTE[lte]}": all(
            next(
                r["hash"]
                for r in rows
                if (r["estimator"], r["variant"], r["cut_s"]) == (rx, LTE[lte], c)
            )
            == next(
                r["hash"]
                for r in rows
                if (r["estimator"], r["variant"], r["cut_s"]) == (base, LTE[lte], c)
            )
            for c in cuts
        )
        for rx, base in (("ekf+rx", "ekf"), ("B+rx", "B"))
        for lte in LTE
    }
    lte = [m for m in meas if m.source == "lte"]
    s = {
        "session": Path(path).name,
        "frontend_commit": CUT.session.read_meta(path).get("commit"),
        "duration_s": float(dur),
        "cuts_s": cuts,
        "gps_scatter": CUT.gps_scatter(fix_pos),
        "lte_records": {
            "pseudorange": sum(m.kind == "pseudorange" for m in lte),
            "doppler": sum(m.kind == "doppler" for m in lte),
            "cells": len({m.emitter for m in lte}),
            "arcs": len({(m.emitter, m.meta.get("arc")) for m in lte}),
        },
        "arc_steps": CUT.arc_steps(meas),
        "rx_term_identical": same,
        "aggregate": agg,
    }
    return s, rows


def _fmt(x: float) -> str:
    if x != x:
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


STRESS_ORDER = [
    ("no LTE", "none, drift"),
    ("ekf", "PR, drift"),
    ("ekf", "PR+doppler, drift"),
    ("B", "PR, drift"),
    ("B", "PR+doppler, drift"),
    ("B+arc", "PR, drift"),
]
ORDER = [
    ("no LTE", "none"),
    ("hold", "last fix"),
    ("ekf", "PR"),
    ("ekf", "PR+doppler"),
    ("B", "PR"),
    ("B", "PR+doppler"),
    ("B+arc", "PR"),
    ("ekf+rx", "PR"),
    ("ekf+rx", "PR+doppler"),
    ("B+rx", "PR"),
    ("B+rx", "PR+doppler"),
]


def table(s: dict, order=None) -> list[str]:
    lines = [
        "| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–300 s, worst cut | "
        "Worst second | HPL ≥ error | Error > HPL | Before cut: GNSS excluded | "
        "Before cut: p95 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for est, var in order or ORDER:
        a = s["aggregate"].get(f"{est}|{var}")
        if a is None:
            continue
        cells = [
            f"{_fmt(a[f'err_{t:g}s_m']['median'])} ({_fmt(a[f'err_{t:g}s_m']['worst'])})"
            for t in AT_S
        ]
        bound = f"{a['hpl_bound']:.0%}" if "hpl_bound" in a else "—"
        mis = f"{a['misleading']} / {a['fixes']}" if "misleading" in a else "—"
        excl = f"{a['pre_gnss_excluded']:.0%}" if "pre_gnss_excluded" in a else "—"
        lines.append(
            f"| {est} | {var} | {' | '.join(cells)} | {_fmt(a['p95_300s_m']['worst'])} | "
            f"{_fmt(a['worst_second_m'])} | {bound} | {mis} | {excl} | "
            f"{_fmt(a['pre_p95_m']['median'])} |"
        )
    return lines


def hpl_table(s: dict) -> list[str]:
    lines = ["| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |", "|---|---|---|---|---|---|"]
    for est, var in ORDER:
        a = s["aggregate"].get(f"{est}|{var}")
        if a is None or "hpl_bound" not in a or "+rx" in est:
            continue
        cells = [_fmt(a[f"hpl_{t:g}s_m"]["median"]) for t in AT_S]
        lines.append(f"| {est} | {var} | {' | '.join(cells)} |")
    return lines


def markdown(summary: dict) -> str:
    inputs = ", ".join(f"`{b}` {c}" for b, c in summary["inputs"])
    lines = [
        "# Real GPS cut with the three fixes combined (#214)",
        "",
        "Evidence: **replay of real static sessions, GPS cut in software** (ADR-0015). "
        f"Code: {inputs}, merged in that order in the local branch `tmp/e2e-combined` "
        f"(never pushed); driver `run_combined.py` here, run at `{summary['commit']}` of that "
        "branch. `#183`'s front end re-run on each capture. Every error is horizontal, against "
        "the GPS fix the filter no longer sees; no position, origin, range or bearing is "
        "given. Median over the cuts, worst cut in brackets (m).",
        "",
    ]
    for s in summary["sessions"]:
        g, n = s["gps_scatter"], s["lte_records"]
        same = all(s["rx_term_identical"].values())
        lines += [
            f"## {s['session']}",
            "",
            f"{s['duration_s']:,.0f} s; front end at `{s['frontend_commit']}`; "
            f"{len(s['cuts_s'])} cuts at {', '.join(f'{c:g}' for c in s['cuts_s'])} s, each "
            f"scored for {HORIZON_S:g} s. LTE: {n['cells']} cells, {n['arcs']} arcs, "
            f"{n['pseudorange']:,} pseudoranges, {n['doppler']:,} dopplers. GPS fix scatter "
            f"(truth noise) {g['rms_m']:.2f} m rms, {g['max_m']:.2f} m max. The cuts share one "
            "recording: not independent draws.",
            "",
            *table(s),
            "",
            "Receiver-clock term (`+rx`): "
            + (
                "bit-identical to the run without it on every cut."
                if same
                else f"differs: {s['rx_term_identical']}"
            ),
            "",
            "HPL after the cut (median over the cuts, m): the coasting covariance.",
            "",
            *hpl_table(s),
            "",
            f"Stress: GNSS pulled {DRIFT_MPS:g} m/s for the {DRIFT_S:g} s before each cut "
            f"(`spoof_ramp`), so each run enters the coast {DRIFT_MPS * DRIFT_S:g} m off and "
            "drifting; truth stays the real fixes. A coast with nothing else keeps drifting; "
            "LTE with information pulls it back.",
            "",
            *table(s, STRESS_ORDER),
            "",
        ]
    lines += summary.get("notes", [])
    return "\n".join(lines) + "\n"


SERIES = [  # (estimator, LTE, colour, label): reference categorical palette, fixed order
    ("no LTE", "none", "#2a78d6", "no LTE"),
    ("ekf", "PR", "#eb6834", "ekf, PR"),
    ("ekf", "PR+doppler", "#1baf7a", "ekf, PR+doppler"),
    ("B", "PR", "#eda100", "B, PR"),
    ("B", "PR+doppler", "#e87ba4", "B, PR+doppler"),
    ("B+arc", "PR", "#6250d6", "B+arc, PR"),
]


def plot(all_rows: dict, summary: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sess = summary["sessions"]
    fig, axes = plt.subplots(1, len(sess), figsize=(6.2 * len(sess), 4.8), sharey=True)
    axes = np.atleast_1d(axes)
    grid = np.arange(0.0, HORIZON_S + 1.0, 1.0)

    def curve(rs, field):
        ys = [
            np.interp(grid, r["after_s"], np.asarray(r[field], float), left=np.nan, right=np.nan)
            for r in rs
        ]
        return np.nanmedian(ys, axis=0)

    for ax, s in zip(axes, sess, strict=True):
        rows = all_rows[s["session"]]
        for est, var, c, label in SERIES:
            rs = [r for r in rows if r["estimator"] == est and r["variant"] == var]
            ax.plot(grid, curve(rs, "err_m"), color=c, lw=2, label=f"{label}: error")
            ax.plot(grid, curve(rs, "hpl_m"), color=c, lw=1.2, ls="--", label=f"{label}: HPL")
        hold = [r for r in rows if r["estimator"] == "hold"]
        ax.plot(grid, curve(hold, "err_m"), color="0.35", lw=1, ls=":", label="hold last fix")
        drift = [r for r in rows if r["estimator"] == "no LTE" and r["variant"] == "none, drift"]
        ax.plot(grid, curve(drift, "err_m"), color="0.15", lw=1.2, ls="-.",
                label=f"no LTE, stress {DRIFT_MPS:g} m/s drift: error")  # fmt: skip
        ax.axhspan(0.01, s["gps_scatter"]["max_m"], color="0.93", lw=0)
        ax.text(grid[-1], 0.012, "GPS fix scatter (truth noise)", ha="right", fontsize=7)
        ax.axhline(25.0, color="0.5", lw=0.8)
        ax.text(grid[-1], 28.0, "T1 25 m (TBC)", ha="right", va="bottom", fontsize=7)
        ax.set_yscale("log")
        ax.set_ylim(0.01, 1e5)
        ax.set_title(
            f"{s['session']}: median of {len(s['cuts_s'])} cuts (static receiver)", fontsize=9
        )
        ax.set_xlabel("s after GPS cut")
        ax.grid(True, which="major", color="0.9", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("horizontal error (solid) / HPL (dashed), m")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=7, frameon=False)
    fig.suptitle(
        "Error after a software GPS cut, real static sessions (replay), #183 + #147 (B) + "
        f"#228 merged, {summary['commit']}. +rx runs are identical to their base and not drawn.",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--notes", type=Path, help="markdown appended to summary.md")
    a = ap.parse_args(argv)
    sessions, all_rows = [], {}
    for p in a.sessions:
        s, rows = session_summary(str(p), a.jobs)
        sessions.append(s)
        all_rows[s["session"]] = rows
    summary = {
        "kind": "replay of real static sessions, GPS cut in software",
        "inputs": [list(x) for x in INPUTS],
        "integration_branch": "tmp/e2e-combined (local only, never pushed)",
        "commit": _git("describe", "--always", "--dirty", "--abbrev=7"),
        "horizon_s": HORIZON_S,
        "estimators": {k: v for k, v in ESTS.items()} | {"no LTE": "ekf, LTE dropped"},
        "sessions": sessions,
        "notes": a.notes.read_text().splitlines() if a.notes else [],
        "runs": [
            {k: v for k, v in r.items() if k not in ("after_s", "err_m", "hpl_m")}
            for rows in all_rows.values()
            for r in rows
        ],
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    (a.out / "summary.md").write_text(markdown(summary))
    plot(all_rows, summary, a.out / "error_after_cut.png")
    print(markdown(summary))


if __name__ == "__main__":
    main()
