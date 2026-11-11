"""The first real error after GPS loss (#214): a real session replayed with GPS cut in software,
scored against the real GPS fixes the filter no longer sees.

    python analysis/real_gps_cut.py <session>-lte [--cuts 100 150 200 250 300] [--jobs 3]
        [--out analysis/results/real-gps-cut-20261111] [--dash-out DIR --dash-cut 300]

`<session>-lte` is a real session after `pnt frontend lte` (its GNSS, IMU and barometer records
copied beside `/meas/lte`). For each cut time T (seconds from the first measurement, as
`pnt replay --inject` counts them), every GNSS record from T on is removed with the `outage`
fault of `pnt.sim.attacks` (software fault injection, ADR-0015: the same code as
`pnt replay <session> --inject analysis/inject/gnss-cut-300s.yaml`). The estimator runs over the
rest; its estimate at each withheld fix's time is compared with that fix.

Truth is the withheld GPS fix, so the error includes the fix's own scatter: `gps_scatter` in the
summary gives its size about the session's GPS mean. Positions are only ever differences from a
fix: no file this writes gives a position, the origin, or a range or bearing to a tower.

LTE variants (all opt-in here; nothing under `src/` changes):
- `none`: LTE records dropped. IMU, barometer only.
- `told`: the front end's records as written: pseudorange and doppler, each with its told σ.
- `told-pr`: pseudoranges only, told σ (like-for-like with the two below, which drop doppler).
- `adr36`: pseudoranges only, σ replaced by ADR-0036's measured white σ for the record's SNR
  (`adr36_sigma`); below -14 dB ADR-0036 has no value (`TBD`), so those records are dropped.
  Doppler records are dropped: ADR-0036 gives them no σ and flags carrier aliases (#183).
- `adr36-cut8`: `adr36`, keeping only records at SNR >= -8 dB (ADR-0036's fit range).

Per run (estimator, variant, cut): horizontal error at 30, 60, 120 and 300 s after the cut; the
p95 over [cut, cut + s) for s in 60, 120 and 300 (as `pnt.metrics` scores outage slices for T1);
the share of withheld fixes with HPL >= error, and how many have error > HPL; and, before the cut
while GNSS is fed, the p95 error and the share of epochs flagged `gnss_excluded`. `hold` is the
last fix before the cut held: the error a receiver that never moves gets for free.

Writes summary.json, summary.md and error_after_cut.png into `--out`. With `--dash-out`, also
writes a session for `pnt dash` (outside git: it holds the session's origin): the records with
GNSS cut at `--dash-cut`, and every GPS fix as `/truth`, so the panel can draw error against HPL.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import subprocess
from pathlib import Path

import msgspec
import numpy as np

from pnt import experiments, nav
from pnt.core.measurement import Measurement, Truth
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_session
from pnt.sim import attacks

CUTS_S = (100.0, 150.0, 200.0, 250.0, 300.0)
HORIZON_S = 300.0  # s of coast scored after each cut (T1's 300 s, ADR-0034)
AT_S = (30.0, 60.0, 120.0, 300.0)  # s after the cut: errors reported at these instants
SLICES_S = (60.0, 120.0, 300.0)  # p95 over [cut, cut + s), as metrics.OUTAGE_SLICES_S
ESTIMATORS = ("ekf", "ekf-imu", "ekf-calibrated")
VARIANTS = ("none", "told", "told-pr", "adr36", "adr36-cut8")
SETTLE_S = 30.0  # s of start-up left out of the before-cut statistics
T1_M, T1_S = 25.0, 300.0  # ADR-0034 T1 (TBC): 95 % <= 25 m for >= 300 s
FALLBACK_M, FALLBACK_S = 50.0, 120.0  # ADR-0034's fallback (mentors): <= 50 m for >= 120 s

# ADR-0036 (Proposed) white σ of a 10 Hz LTE pseudorange: the fit at SNR >= -8 dB, the measured
# bins below it, nothing below -14 dB (TBD)
ADR36_FLOOR_M, ADR36_SNR_M = 0.64, 2.28
ADR36_BINS = ((-11.0, 12.4), (-14.0, 24.7))  # (lower edge dB, σ m) below -8 dB
ADR36_CUT_DB = -8.0


def adr36_sigma(snr_db: float) -> float | None:
    """ADR-0036's white σ (m) for a 10 Hz pseudorange at `snr_db`; None where it has no value."""
    if snr_db >= ADR36_CUT_DB:
        return math.sqrt(ADR36_FLOOR_M**2 + ADR36_SNR_M**2 / 10 ** (snr_db / 10))
    for lower, sigma in ADR36_BINS:
        if snr_db >= lower:
            return sigma
    return None


def lte_variant(meas: list[Measurement], variant: str) -> list[Measurement]:
    """`meas` with its LTE records as `variant` says (module docstring); others untouched."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r} (known: {VARIANTS})")
    out = []
    for m in meas:
        if m.source != "lte":
            out.append(m)
        elif variant == "told":
            out.append(m)
        elif m.kind != "pseudorange" or variant == "none":
            continue
        elif variant == "told-pr":
            out.append(m)
        else:
            snr = float(m.meta.get("snr_db", float("-inf")))
            sigma = adr36_sigma(snr)
            if sigma is None or (variant == "adr36-cut8" and snr < ADR36_CUT_DB):
                continue
            out.append(msgspec.structs.replace(m, sigma=(sigma,)))
    return out


def cut_gnss(meas: list[Measurement], t0_ns: int, cut_s: float) -> list[Measurement]:
    """Every GNSS record from `cut_s` after `t0_ns` removed: the attack library's `outage`."""
    ctx = attacks.Context(t0_ns=t0_ns, origin_llh=None, truth_pos=None, rng=None)
    fault = {"type": "outage", "source": "gnss", "start_s": cut_s}
    out, _ = attacks.apply(meas, [fault], ctx)
    return out


def gps_fixes(meas: list[Measurement]) -> tuple[np.ndarray, np.ndarray]:
    """(t_ns, ENU position) of every payload GNSS position fix, in time order."""
    fixes = sorted(
        (m for m in meas if m.source == "gnss" and m.kind == "position_enu"),
        key=lambda m: m.t_ns,
    )
    t = np.array([m.t_ns for m in fixes], dtype=np.int64)
    return t, np.array([m.value for m in fixes], dtype=float).reshape(-1, 3)


def _p95(x: np.ndarray) -> float:
    return float(np.percentile(x, 95)) if len(x) else float("nan")


def score_cut(
    est_t: np.ndarray,
    est_pos: np.ndarray,
    est_hpl: np.ndarray,
    fix_t: np.ndarray,
    fix_pos: np.ndarray,
    cut_ns: int,
    horizon_s: float = HORIZON_S,
) -> dict:
    """Score one run against the fixes withheld from it: those in [cut, cut + horizon] that
    fall on an estimate epoch. Errors are horizontal, in metres."""
    keep = (fix_t >= cut_ns) & (fix_t <= cut_ns + round(horizon_s * 1e9))
    t, pos = fix_t[keep], fix_pos[keep]
    i = np.searchsorted(est_t, t)
    on = (i < len(est_t)) & (est_t[np.minimum(i, len(est_t) - 1)] == t)
    t, pos, i = t[on], pos[on], i[on]
    err = np.hypot(*(est_pos[i, :2] - pos[:, :2]).T)
    hpl = est_hpl[i]
    after = (t - cut_ns) / 1e9
    out = {"n_fixes": int(len(t)), "after_s": after.tolist(), "err_m": err.tolist()}
    out["hpl_m"] = hpl.tolist()
    for s in AT_S:
        k = np.flatnonzero(np.isclose(after, s, atol=0.05))
        out[f"err_{s:g}s_m"] = float(err[k[0]]) if len(k) else float("nan")
        out[f"hpl_{s:g}s_m"] = float(hpl[k[0]]) if len(k) else float("nan")
    for s in SLICES_S:
        w = after < s
        out[f"p95_{s:g}s_m"] = _p95(err[w]) if after.size and after.max() >= s - 1 else math.nan
    out["max_m"] = float(err.max()) if err.size else float("nan")
    out["hpl_bound"] = float(np.mean(hpl >= err)) if err.size else float("nan")
    out["misleading"] = int(np.sum(err > hpl))
    return out


def hold_last_fix(fix_t: np.ndarray, fix_pos: np.ndarray, cut_ns: int) -> dict:
    """The last fix before the cut, held: scored like a run, with no HPL."""
    last = int(np.flatnonzero(fix_t < cut_ns)[-1])
    est_t = fix_t[fix_t >= cut_ns]
    est_pos = np.repeat(fix_pos[last : last + 1], len(est_t), axis=0)
    out = score_cut(est_t, est_pos, np.full(len(est_t), np.nan), fix_t, fix_pos, cut_ns)
    out["hpl_bound"], out["misleading"] = float("nan"), None
    return out


@functools.lru_cache(maxsize=1)
def load(path: str) -> tuple[list[Measurement], int, list | None]:
    """(measurements in time order, first measurement's t_ns, origin_llh) of a session."""
    meas = [r for _, r in read_session(session.mcap_path(path), topics=["/meas/"])]
    meas = sorted((m for m in meas if isinstance(m, Measurement)), key=lambda m: m.t_ns)
    return meas, meas[0].t_ns, session.read_meta(path).get("origin_llh")


def run_one(path: str, estimator: str, variant: str, cut_s: float) -> dict:
    """One replay with GNSS cut at `cut_s`, scored after the cut and before it."""
    meas, t0, origin = load(path)
    fix_t, fix_pos = gps_fixes(meas)
    cut_ns = t0 + round(cut_s * 1e9)
    fed = lte_variant(cut_gnss(meas, t0, cut_s), variant)
    est = list(nav.estimate(estimator, fed, origin_llh=origin))
    est_t = np.array([e.t_ns for e in est], dtype=np.int64)
    est_pos = np.array([e.pos_enu for e in est], dtype=float)
    est_hpl = np.array([e.hpl_m for e in est], dtype=float)
    out = {"estimator": estimator, "variant": variant, "cut_s": cut_s}
    out.update(score_cut(est_t, est_pos, est_hpl, fix_t, fix_pos, cut_ns))
    # before the cut, GNSS fed: how far the filter is from the fixes it is given
    pre = (fix_t >= t0 + round(SETTLE_S * 1e9)) & (fix_t < cut_ns)
    i = np.searchsorted(est_t, fix_t[pre])
    on = (i < len(est_t)) & (est_t[np.minimum(i, len(est_t) - 1)] == fix_t[pre])
    pre_err = np.hypot(*(est_pos[i[on], :2] - fix_pos[pre][on, :2]).T)
    out["pre_p95_m"] = _p95(pre_err)
    settled = [e for e in est if t0 + SETTLE_S * 1e9 <= e.t_ns < cut_ns]
    out["pre_gnss_excluded"] = float(np.mean(["gnss_excluded" in e.flags for e in settled]))
    out["n_lte"] = sum(m.source == "lte" for m in fed)
    return out


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError:
        return "unknown"


def gps_scatter(fix_pos: np.ndarray) -> dict:
    """Size of the fixes' scatter about their own mean (horizontal, m): the truth's own error."""
    d = np.hypot(*(fix_pos[:, :2] - fix_pos[:, :2].mean(axis=0)).T)
    return {"rms_m": float(np.sqrt(np.mean(d**2))), "p95_m": _p95(d), "max_m": float(d.max())}


ARC_STEP_M = 100.0  # m: a new arc's step from its cell's last record counted as a jump
ARC_GAP_S = 1.0  # s: only arcs that start within this of the last record are judged


def arc_steps(meas: list[Measurement]) -> dict:
    """How far each LTE pseudorange arc starts from where its cell's last arc ended, for arcs
    that start within ARC_GAP_S of it. The cell's median in-arc rate (our dongle's clock drift
    against the tower's) times the gap is taken off; whole 10 ms frames are wrapped out. Steps
    only: no range. Split at ADR-0036's -8 dB by the new arc's first SNR."""
    by_cell: dict[str, list[Measurement]] = {}
    for m in meas:
        if m.source == "lte" and m.kind == "pseudorange":
            by_cell.setdefault(m.emitter, []).append(m)
    steps: dict[str, list[float]] = {"above": [], "below": []}
    for recs in by_cell.values():
        recs.sort(key=lambda m: m.t_ns)
        pairs = list(zip(recs, recs[1:], strict=False))
        rates = [
            (b.value[0] - a.value[0]) / ((b.t_ns - a.t_ns) / 1e9)
            for a, b in pairs
            if a.meta.get("arc") == b.meta.get("arc") and b.t_ns > a.t_ns
        ]
        rate = float(np.median(rates)) if rates else 0.0
        for a, b in pairs:
            dt = (b.t_ns - a.t_ns) / 1e9
            if a.meta.get("arc") == b.meta.get("arc") or dt > ARC_GAP_S:
                continue
            step = b.value[0] - a.value[0] - rate * dt
            amb = b.meta.get("ambiguity_m")
            if amb:
                step = (step + amb / 2) % amb - amb / 2
            snr = float(b.meta.get("snr_db", float("-inf")))
            steps["above" if snr >= ADR36_CUT_DB else "below"].append(abs(step))
    out = {}
    for side, v in steps.items():
        v = np.asarray(v)
        big = v[v > ARC_STEP_M]
        out[side] = {
            "arcs": int(v.size),
            f"over_{ARC_STEP_M:g}m": int(big.size),
            "median_jump_m": float(np.median(big)) if big.size else math.nan,
            "max_jump_m": float(big.max()) if big.size else math.nan,
        }
    return out


def aggregate(rows: list[dict]) -> dict:
    """Per (estimator, variant): each figure over the cuts (median and worst run), the HPL bound
    rate pooled over every withheld fix, and the ADR-0034 checks on these runs."""
    out: dict = {}
    for r in rows:
        out.setdefault(f"{r['estimator']}|{r['variant']}", []).append(r)
    agg = {}
    for key, rs in out.items():
        a: dict = {"runs": len(rs), "cuts_s": [r["cut_s"] for r in rs]}
        for f in (
            [f"err_{s:g}s_m" for s in AT_S]
            + [f"p95_{s:g}s_m" for s in SLICES_S]
            + [
                "max_m",
                "pre_p95_m",
            ]
        ):
            v = np.array([r[f] for r in rs], dtype=float)
            ok = v[~np.isnan(v)]
            a[f] = {
                "median": float(np.median(ok)) if ok.size else math.nan,
                "worst": float(ok.max()) if ok.size else math.nan,
                "n": int(ok.size),
            }
        if rs[0]["hpl_bound"] == rs[0]["hpl_bound"]:  # not the held fix
            err = np.concatenate([r["err_m"] for r in rs])
            hpl = np.concatenate([r["hpl_m"] for r in rs])
            a["hpl_bound"] = float(np.mean(hpl >= err))
            a["misleading"] = int(sum(r["misleading"] for r in rs))
            a["fixes"] = int(err.size)
            a["pre_gnss_excluded"] = float(np.mean([r["pre_gnss_excluded"] for r in rs]))
        # ADR-0034 over the runs; with a handful of runs the 95th percentile is the worst
        a["t1_met"] = bool(a[f"p95_{T1_S:g}s_m"]["worst"] <= T1_M)
        a["fallback_met"] = bool(a[f"p95_{FALLBACK_S:g}s_m"]["worst"] <= FALLBACK_M)
        agg[key] = a
    return agg


def _fmt(x: float) -> str:
    if x != x:
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


def markdown(summary: dict) -> str:
    s = summary
    g = s["gps_scatter"]
    lines = [
        "# Real GPS cut: error after GPS loss on a real session (#214)",
        "",
        f"Evidence: **replay of a real session, GPS cut in software** (ADR-0015). Session "
        f"`{s['session']}` (front end at `{s['frontend_commit']}`, analysis at `{s['commit']}`). "
        "Static receiver, "
        "outdoors, on the ground; one site; LTE on one carrier (EARFCN 2460), few weak cells. "
        f"Runs: one per cut time ({', '.join(f'{c:g}' for c in s['cuts_s'])} s after the first "
        f"measurement), each scored for {s['horizon_s']:g} s after its cut. The runs share the "
        f"same data, so they are not independent: n = {len(s['cuts_s'])} cut times of one "
        "session.",
        "",
        f"Truth: the GPS fixes withheld from the filter (1 Hz). Their scatter about the session's "
        f"GPS mean is {g['rms_m']:.2f} m rms, {g['p95_m']:.2f} m p95, {g['max_m']:.2f} m max "
        "(horizontal): every error below that size is truth noise. No position, origin, range "
        "or bearing is given here, only errors.",
        "",
        "## Horizontal error after the cut",
        "",
        f"Median over the {len(s['cuts_s'])} cuts, worst run in brackets (m). `hold` is the last "
        "fix before the cut, held.",
        "",
        "| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–120 s (worst) | "
        "p95 0–300 s (worst) | HPL ≥ error | Error > HPL (fixes) | Before cut: p95 | "
        "Before cut: GNSS excluded |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key, a in s["aggregate"].items():
        est, var = key.split("|")
        cells = [
            f"{_fmt(a[f'err_{t:g}s_m']['median'])} ({_fmt(a[f'err_{t:g}s_m']['worst'])})"
            for t in AT_S
        ]
        bound = f"{a['hpl_bound']:.0%}" if "hpl_bound" in a else "—"
        mis = f"{a['misleading']} / {a['fixes']}" if "misleading" in a else "—"
        excl = f"{a['pre_gnss_excluded']:.0%}" if "pre_gnss_excluded" in a else "—"
        lines.append(
            f"| {est} | {var} | {' | '.join(cells)} | {_fmt(a['p95_120s_m']['worst'])} | "
            f"{_fmt(a['p95_300s_m']['worst'])} | {bound} | {mis} | "
            f"{_fmt(a['pre_p95_m']['median'])} | {excl} |"
        )
    lines += [
        "",
        f"ADR-0034 on these runs (T1 `TBC`: p95 ≤ {T1_M:g} m for {T1_S:g} s; fallback "
        f"≤ {FALLBACK_M:g} m for {FALLBACK_S:g} s), taken as the worst run's p95 over the window: "
        "with this few runs the 95th percentile over runs is the worst run.",
        "",
        "| Estimator | LTE | T1 | Fallback |",
        "|---|---|---|---|",
    ]
    for key, a in s["aggregate"].items():
        est, var = key.split("|")
        yes = {True: "met", False: "missed"}
        lines.append(f"| {est} | {var} | {yes[a['t1_met']]} | {yes[a['fallback_met']]} |")
    lines += [
        "",
        "## HPL at the same instants",
        "",
        "Median over the cuts (m).",
        "",
        "| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |",
        "|---|---|---|---|---|---|",
    ]
    for key, a in s["aggregate"].items():
        if "hpl_bound" not in a:
            continue
        est, var = key.split("|")
        cells = [_fmt(a[f"hpl_{t:g}s_m"]["median"]) for t in AT_S]
        lines.append(f"| {est} | {var} | {' | '.join(cells)} |")
    st = s["arc_steps"]
    big = f"over_{ARC_STEP_M:g}m"
    lines += [
        "",
        "## Where a new LTE arc starts",
        "",
        f"Each pseudorange arc that starts within {ARC_GAP_S:g} s of its cell's last record, "
        "against that record (the cell's in-arc rate taken off, whole frames wrapped out). By the "
        "new arc's first SNR. Steps only, no range.",
        "",
        f"| New arc's SNR | Arcs | Step > {ARC_STEP_M:g} m | Median of those (m) | Largest (m) |",
        "|---|---|---|---|---|",
    ]
    for side, label in (("above", "≥ -8 dB"), ("below", "< -8 dB")):
        r = st[side]
        lines.append(
            f"| {label} | {r['arcs']} | {r[big]} | {_fmt(r['median_jump_m'])} | "
            f"{_fmt(r['max_jump_m'])} |"
        )
    lines += [
        "",
        "## What this can and cannot show",
        "",
        "- One static receiver at one site, one carrier, a few weak cells. The truth does not "
        "move, so a filter that holds still (`none`, `hold`) is right by construction: its small "
        "error says nothing about coasting on a moving drone.",
        "- The cut times share one recording: the runs are not independent draws, and the "
        "worst run is not a 95th percentile.",
        "- Tower positions are the committed table's matches (a hypothesis, `pnt.nav.cells`).",
        "- The `adr36` variants apply a Proposed ADR's σ in this script only; nothing in `src/` "
        "changes, and the correlated part ADR-0036 adds (`sigma_corr_m`) is not modelled.",
        "",
    ]
    return "\n".join(lines)


PLOT_VARIANTS = ("none", "told", "adr36", "adr36-cut8")
# reference categorical palette (dataviz skill), fixed order: blue, orange, aqua, yellow
COLORS = {"none": "#2a78d6", "told": "#eb6834", "adr36": "#1baf7a", "adr36-cut8": "#eda100"}


def plot(rows: list[dict], summary: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ests = [e for e in summary["estimators"] if any(r["estimator"] == e for r in rows)]
    fig, axes = plt.subplots(1, len(ests), figsize=(4.2 * len(ests), 4.2), sharey=True)
    axes = np.atleast_1d(axes)
    grid = np.arange(0.0, summary["horizon_s"] + 1.0, 1.0)

    def curve(rs, field):
        ys = []
        for r in rs:
            x, y = np.asarray(r["after_s"]), np.asarray(r[field], dtype=float)
            ys.append(np.interp(grid, x, y, left=np.nan, right=np.nan))
        return np.nanmedian(ys, axis=0), np.nanmin(ys, axis=0), np.nanmax(ys, axis=0)

    for ax, est in zip(axes, ests, strict=True):
        for var in PLOT_VARIANTS:
            rs = [r for r in rows if r["estimator"] == est and r["variant"] == var]
            if not rs:
                continue
            med, lo, hi = curve(rs, "err_m")
            c = COLORS[var]
            ax.fill_between(grid, lo, hi, color=c, alpha=0.12, lw=0)
            ax.plot(grid, med, color=c, lw=2, label=f"{var}: error")
            ax.plot(grid, curve(rs, "hpl_m")[0], color=c, lw=1.2, ls="--", label=f"{var}: HPL")
        hold = [r for r in rows if r["estimator"] == "hold"]
        if hold:
            ax.plot(grid, curve(hold, "err_m")[0], color="0.35", lw=1, ls=":", label="hold: error")
        ax.axhline(T1_M, color="0.5", lw=0.8)
        ax.text(grid[-1], T1_M * 1.1, "T1 25 m (TBC)", ha="right", va="bottom", fontsize=7)
        ax.text(grid[-1], 0.12, "GPS fix scatter (truth noise)", ha="right", fontsize=7)
        ax.axhspan(0.1, summary["gps_scatter"]["max_m"], color="0.94", lw=0)
        ax.set_yscale("log")
        ax.set_ylim(0.1, 1e5)
        ax.set_title(est, fontsize=10)
        ax.set_xlabel("s after GPS cut")
        ax.grid(True, which="major", color="0.9", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("horizontal error / HPL (m)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, fontsize=7, frameon=False)
    fig.suptitle(
        f"Error after a software GPS cut, real session {summary['session']} (replay), "
        f"{summary['commit']}: median of {len(summary['cuts_s'])} cut times, band = min–max",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def write_dash_session(path: str, out: Path, cut_s: float) -> None:
    """A session for `pnt dash`: GNSS cut at `cut_s`, every GPS fix as `/truth`. Outside git."""
    meas, t0, _ = load(path)
    fix_t, fix_pos = gps_fixes(meas)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} already holds data")
    out.mkdir(parents=True, exist_ok=True)
    meta = session.read_meta(path)
    note = (
        f"GNSS cut at {cut_s:g} s by analysis/real_gps_cut.py at {_commit()}; /truth = GPS fixes"
    )
    session.write_meta(
        out, {**meta, "name": out.name, "notes": f"{meta.get('notes') or ''}\n{note}"}
    )
    with SessionWriter(out / session.MCAP_NAME, metadata={"injected": note}) as w:
        for t, p in zip(fix_t, fix_pos, strict=True):
            w.write("/truth", Truth(t_ns=int(t), pos_enu=tuple(p), vel_enu=(0.0, 0.0, 0.0)))
        for m in cut_gnss(meas, t0, cut_s):
            w.write(f"/meas/{m.source}", m)
    print(f"wrote {out}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session", help="real session after `pnt frontend lte` (<session>-lte)")
    ap.add_argument("--cuts", type=float, nargs="+", default=list(CUTS_S), help="s")
    ap.add_argument("--estimators", nargs="+", default=list(ESTIMATORS))
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--jobs", type=int, default=1, help="worker processes (<= 3 on this laptop)")
    ap.add_argument("--out", help="folder for summary.json, summary.md, error_after_cut.png")
    ap.add_argument("--dash-out", help="also write a session for `pnt dash` here (not in git)")
    ap.add_argument("--dash-cut", type=float, default=300.0, help="s, for --dash-out")
    args = ap.parse_args(argv)
    path = str(args.session)
    if args.dash_out:
        write_dash_session(path, Path(args.dash_out), args.dash_cut)
    if not args.out:
        return
    meas, t0, _ = load(path)
    fix_t, fix_pos = gps_fixes(meas)
    if args.cuts and max(args.cuts) + HORIZON_S > (fix_t[-1] - t0) / 1e9 + 0.5:
        raise SystemExit(f"a cut leaves less than {HORIZON_S:g} s of withheld fixes")
    tasks = [(path, e, v, c) for e in args.estimators for v in args.variants for c in args.cuts]
    rows = experiments._map(run_one, tasks, args.jobs)
    for c in args.cuts:
        h = hold_last_fix(fix_t, fix_pos, t0 + round(c * 1e9))
        rows.append({"estimator": "hold", "variant": "last fix", "cut_s": c, **h})
        rows[-1]["pre_p95_m"] = math.nan
    summary = {
        "session": session.session_name(path),
        "commit": _commit(),
        "frontend_commit": session.read_meta(path).get("commit"),
        "kind": "replay of a real session, GPS cut in software",
        "cuts_s": list(args.cuts),
        "horizon_s": HORIZON_S,
        "estimators": list(args.estimators),
        "variants": list(args.variants),
        "gps_scatter": gps_scatter(fix_pos),
        "arc_steps": arc_steps(meas),
        "lte_records_fed": {
            f"{r['estimator']}|{r['variant']}": r["n_lte"] for r in rows if "n_lte" in r
        },
        "aggregate": aggregate(rows),
        "runs": [
            {k: v for k, v in r.items() if k not in ("after_s", "err_m", "hpl_m")} for r in rows
        ],
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "summary.md").write_text(markdown(summary))
    plot(rows, summary, out / "error_after_cut.png")
    print(markdown(summary))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
