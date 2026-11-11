"""Error after GPS loss on a moving session (#214): software GPS cuts across the moving part of a
handheld walk, scored against the withheld GPS fixes, interpolated to every estimate.

    python analysis/walk_gps_cut.py <session> [--cuts 5 | --cut-at S ...] [--jobs 3]
        [--configs ...] [--lte-session DIR] [--out analysis/results/<session>]
    just walk-cut <session>

`<session>` is a session folder (or its name under `data/sessions/`). LTE records come from, in
order: the session itself (`/meas/lte`, e.g. a sim session), `--lte-session`, `<session>-lte`
beside it, or else the LTE front end (`pnt frontend lte <session>/sdr_a.cu8`) run here in a
subprocess while the no-LTE runs go ahead.

Truth (the receiver moves, so the GPS mean is no truth): the GNSS fixes the cut withholds, linear
between two good fixes at most `MAX_GAP_S` apart, at each estimate's time. A good fix is a 3D fix
whose latest gpsd SKY report has HDOP <= `HDOP_MAX` and >= `MIN_SATS` satellites used (both TBC).
gpsd's `epx`/`epy` come from DOP with an assumed range error (`payload/gpsd.py`), so they add
nothing to HDOP. A session without SKY reports (sim) is gated on the 3D fix alone, and says so.
The truth carries the fixes' own error (a few metres): an error that small is truth noise.

Cuts (seconds after the first measurement, as `pnt replay --inject` counts them): every GNSS
record from the cut on is removed with `pnt.sim.attacks`' `outage` (software fault injection,
ADR-0015). Picked from the times where the receiver has had >= `PRE_S` s of good fixes just
before, is moving (speed from the fixes >= `MOVING_MPS`, TBC) at the cut and for >= `MIN_MOVING`
of the `PRE_S` s before and the `HORIZON_S` s after it, and has truth at `HORIZON_S` s;
`--cuts N` of them spread evenly at least `MIN_SPACING_S` apart. `--cut-at` gives the times
instead (any session, static included).

Per run: horizontal error at 60, 120 and 300 s after the cut, the p95 over [cut, cut + s), the
share of scored epochs with HPL >= error, misleading epochs, the moving share of the window,
before the cut the p95 error and the share of epochs with GNSS excluded, and for `ekf-imu`
whether and when its IMU aligned (heading needs motion, `nav/imu.py`).

Privacy: no position, track, origin, or range or bearing to a tower is written. Errors, HPL,
times, counts and cell names only. The figure is error against time since the cut.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

from pnt import experiments, nav
from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_json, read_session
from pnt.nav import cells
from pnt.sim import attacks

REPO = Path(__file__).resolve().parents[1]
SESSIONS = REPO / "data" / "sessions"
HORIZON_S = 300.0  # s scored after each cut (T1's 300 s, ADR-0034)
AT_S = (60.0, 120.0, 300.0)  # s after the cut: errors reported at these instants
PRE_S = 60.0  # s of good GPS needed just before a cut
SETTLE_S = 30.0  # s of start-up left out of the before-cut statistics
HDOP_MAX = 2.0  # TBC: a good fix's HDOP
MIN_SATS = 6  # TBC: satellites used in a good fix
SKY_LAG_S = 1.0  # s: gpsd sends an epoch's SKY after its TPV
SKY_AGE_S = 5.0  # s: a SKY report older than this says nothing about a fix
MAX_GAP_S = 2.5  # s: truth only between good fixes at most this far apart (1 Hz fixes, TBC)
SPEED_BASE_S = 10.0  # s: speed from the fixes this far apart (centred)
MOVING_MPS = 0.5  # TBC: walking is 1 to 1.5 m/s; a static fix wanders far slower
MIN_MOVING = 0.8  # TBC: share of the scored window the receiver must be moving
MIN_SPACING_S = 60.0  # s between automatic cuts
N_CUTS = 5
AT_TOL_NS = 50_000_000  # an estimate within 50 ms of cut + s is the one at s

# name -> (estimator, LTE fed, extra estimator options)
CONFIGS = {
    "no LTE, ekf": ("ekf", False, {}),
    "no LTE, ekf-imu": ("ekf-imu", False, {}),
    "LTE, ekf": ("ekf", True, {}),
    "LTE, ekf-imu": ("ekf-imu", True, {}),
    "LTE, B (ekf-measured-sigma)": ("ekf-measured-sigma", True, {}),
    # opt-in: main's ekf before ADR-0050 (front end's own sigma, no bias per arc)
    "LTE, ekf before ADR-0050": ("ekf", True, {"capture_sigma_model": None, "arc_bias": False}),
}
DEFAULT_CONFIGS = [c for c in CONFIGS if "before" not in c]


# --- truth -----------------------------------------------------------------------------------
def fix_quality(fix_t: np.ndarray, sky: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """(HDOP, satellites used) for each fix, from the latest gpsd SKY report stamped at most
    `SKY_LAG_S` after it and `SKY_AGE_S` before it; satellites from a report that lists them.
    NaN where no report qualifies."""
    hdop = np.full(len(fix_t), np.nan)
    nsat = np.full(len(fix_t), np.nan)
    for out, key, rows in (
        (hdop, "hdop", [s for s in sky if s.get("hdop") is not None]),
        (nsat, "n_used", [s for s in sky if s.get("listed")]),
    ):
        if not rows:
            continue
        rows = sorted(rows, key=lambda s: s["t_ns"])
        st = np.array([s["t_ns"] for s in rows], dtype=np.int64)
        sv = np.array([float(s[key]) for s in rows])
        i = np.searchsorted(st, fix_t + round(SKY_LAG_S * 1e9), side="right") - 1
        ok = (i >= 0) & (fix_t - st[np.maximum(i, 0)] <= round(SKY_AGE_S * 1e9))
        out[ok] = sv[i[ok]]
    return hdop, nsat


def good_fixes(
    fix_t: np.ndarray,
    mode: np.ndarray,
    hdop: np.ndarray,
    nsat: np.ndarray,
    have_sky: bool,
    hdop_max: float = HDOP_MAX,
    min_sats: int = MIN_SATS,
) -> np.ndarray:
    """A 3D fix with HDOP <= `hdop_max` and >= `min_sats` used; without SKY reports, 3D only."""
    good = mode >= 3
    if have_sky:
        good &= (hdop <= hdop_max) & (nsat >= min_sats)
    return good


def interpolate(
    fix_t: np.ndarray, fix_pos: np.ndarray, t: np.ndarray, max_gap_s: float = MAX_GAP_S
) -> tuple[np.ndarray, np.ndarray]:
    """Position at each `t` (ns), linear between the two (good) fixes around it, and whether it
    has one: both fixes exist and are at most `max_gap_s` apart. A time on a fix is that fix."""
    t = np.asarray(t, dtype=np.int64)
    out = np.full((len(t), fix_pos.shape[1]), np.nan)
    if len(fix_t) == 0:
        return out, np.zeros(len(t), bool)
    j = np.searchsorted(fix_t, t, side="right")  # fix_t[j-1] <= t < fix_t[j]
    on = (j >= 1) & (fix_t[np.maximum(j - 1, 0)] == t)
    lo, hi = np.clip(j - 1, 0, len(fix_t) - 1), np.clip(j, 0, len(fix_t) - 1)
    between = (j >= 1) & (j < len(fix_t)) & (fix_t[hi] - fix_t[lo] <= round(max_gap_s * 1e9))
    ok = on | between
    span = np.maximum(fix_t[hi] - fix_t[lo], 1).astype(float)
    w = np.where(on, 0.0, (t - fix_t[lo]) / span)[:, None]
    out[ok] = ((1 - w) * fix_pos[lo] + w * fix_pos[hi])[ok]
    return out, ok


def speeds(fix_t: np.ndarray, fix_pos: np.ndarray, base_s: float = SPEED_BASE_S) -> np.ndarray:
    """Horizontal speed (m/s) at each good fix from the truth `base_s` / 2 either side; NaN where
    either side has no truth."""
    h = round(base_s / 2 * 1e9)
    a, oka = interpolate(fix_t, fix_pos[:, :2], fix_t - h)
    b, okb = interpolate(fix_t, fix_pos[:, :2], fix_t + h)
    v = np.hypot(*(b - a).T) / base_s
    v[~(oka & okb)] = np.nan
    return v


def moving_at(fix_t: np.ndarray, moving: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Whether the receiver moves at each `t`: the nearest good fix's flag, if within MAX_GAP_S."""
    t = np.asarray(t, dtype=np.int64)
    if len(fix_t) == 0:
        return np.zeros(len(t), bool)
    j = np.clip(np.searchsorted(fix_t, t), 0, len(fix_t) - 1)
    i = np.maximum(j - 1, 0)
    k = np.where(np.abs(fix_t[i] - t) < np.abs(fix_t[j] - t), i, j)
    return moving[k] & (np.abs(fix_t[k] - t) <= round(MAX_GAP_S * 1e9))


def select_cuts(
    fix_t: np.ndarray,
    fix_pos: np.ndarray,
    t0_ns: int,
    n: int = N_CUTS,
    horizon_s: float = HORIZON_S,
    pre_s: float = PRE_S,
    moving_mps: float = MOVING_MPS,
    min_moving: float = MIN_MOVING,
    min_spacing_s: float = MIN_SPACING_S,
) -> list[float]:
    """Up to `n` cut times (s after `t0_ns`) in the moving part, spread evenly; see the module
    docstring. `fix_t`, `fix_pos` are the good fixes only. Empty if no time qualifies."""
    if len(fix_t) < 2:
        return []
    v = speeds(fix_t, fix_pos)
    moving = np.nan_to_num(v, nan=0.0) >= moving_mps
    pre, hor = round(pre_s * 1e9), round(horizon_s * 1e9)
    # continuous truth: index of the first fix of the run each fix belongs to
    seg = np.cumsum(np.r_[0, np.diff(fix_t) > round(MAX_GAP_S * 1e9)])
    run_start = fix_t[np.searchsorted(seg, seg)]  # first fix of each fix's unbroken run
    grid = np.arange(0, hor + 1, 1_000_000_000)
    cand = []
    for i, T in enumerate(fix_t):
        if T - t0_ns < pre or T - run_start[i] < pre or not moving[i]:
            continue
        _, ok = interpolate(fix_t, fix_pos[:, :2], T + grid)
        if not ok[-1] or ok.mean() < 0.9:
            continue
        if moving_at(fix_t, moving, T + grid).mean() < min_moving:
            continue
        # moving before it too: the filter has a walking velocity and the IMU a chance to align
        if moving_at(fix_t, moving, T - grid[grid <= pre]).mean() < min_moving:
            continue
        cand.append(T)
    if not cand:
        return []
    cand = np.array(cand)
    chosen: list[int] = []
    for target in np.linspace(cand[0], cand[-1], n):
        far = [c for c in cand if all(abs(c - x) >= round(min_spacing_s * 1e9) for x in chosen)]
        if far:
            chosen.append(int(min(far, key=lambda c: abs(c - target))))
    return sorted(round((c - t0_ns) / 1e9, 3) for c in chosen)


# --- data ------------------------------------------------------------------------------------
def resolve(name: str) -> Path:
    p = Path(name)
    if not p.exists() and (SESSIONS / name).exists():
        p = SESSIONS / name
    if not p.exists():
        raise SystemExit(f"no session {name}")
    return p if p.is_dir() else p.parent


@functools.lru_cache(maxsize=2)
def load(path: str) -> dict:
    """A session's measurements (time order), first t_ns, origin, GPS fixes, SKY reports and
    sim truth (if any). The origin stays in memory: nothing here writes it."""
    mcap = session.mcap_path(path)
    meas, truth = [], []
    for topic, r in read_session(mcap):
        if isinstance(r, Measurement):
            meas.append(r)
        elif topic == "/truth":
            truth.append(r)
    meas.sort(key=lambda m: m.t_ns)
    sky = [d for _, d in read_json(mcap, ["/events"]) if d.get("text") == "gnss_sky"]
    fixes = sorted(
        (m for m in meas if m.source == "gnss" and m.kind == "position_enu"),
        key=lambda m: m.t_ns,
    )
    return {
        "meas": meas,
        "t0": meas[0].t_ns,
        "origin": session.read_meta(path).get("origin_llh"),
        "fix_t": np.array([m.t_ns for m in fixes], dtype=np.int64),
        "fix_pos": np.array([m.value for m in fixes], dtype=float).reshape(-1, 3),
        "fix_mode": np.array([m.meta.get("mode") or 3 for m in fixes], dtype=float),
        "sky": sky,
        "truth_t": np.array([t.t_ns for t in truth], dtype=np.int64),
        "truth_pos": np.array([t.pos_enu for t in truth], dtype=float).reshape(-1, 3),
    }


@functools.lru_cache(maxsize=2)
def truth(path: str, hdop_max: float, min_sats: int) -> dict:
    """The good fixes of a session and how they were chosen."""
    d = load(path)
    hdop, nsat = fix_quality(d["fix_t"], d["sky"])
    have_sky = bool(d["sky"])
    good = good_fixes(d["fix_t"], d["fix_mode"], hdop, nsat, have_sky, hdop_max, min_sats)
    return {
        "t": d["fix_t"][good],
        "pos": d["fix_pos"][good],
        "basis": (
            f"3D fix, HDOP <= {hdop_max:g}, >= {min_sats} satellites used (TBC)"
            if have_sky
            else "3D fix only (no gpsd SKY reports in this session)"
        ),
        "fixes": int(len(good)),
        "good": int(good.sum()),
        "hdop_p50": float(np.nanmedian(hdop)) if np.isfinite(hdop).any() else math.nan,
        "nsat_p50": float(np.nanmedian(nsat)) if np.isfinite(nsat).any() else math.nan,
    }


def cut_gnss(meas: list[Measurement], t0_ns: int, cut_s: float) -> list[Measurement]:
    """Every GNSS record from `cut_s` after `t0_ns` removed: the attack library's `outage`."""
    ctx = attacks.Context(t0_ns=t0_ns, origin_llh=None, truth_pos=None, rng=None)
    out, _ = attacks.apply(meas, [{"type": "outage", "source": "gnss", "start_s": cut_s}], ctx)
    return out


@contextlib.contextmanager
def watch_imu():
    """Every `ImuMotion` made inside, to read its alignment afterwards (no behaviour change)."""
    from pnt.nav import imu

    made: list = []
    orig = imu.ImuMotion.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        made.append(self)

    imu.ImuMotion.__init__ = init
    try:
        yield made
    finally:
        imu.ImuMotion.__init__ = orig


def estimator(name: str):
    base, _, extra = CONFIGS[name]
    if not extra:
        return base
    fn = nav.ESTIMATORS[base]
    kw = dict(getattr(fn, "keywords", {}))
    return nav.configured(getattr(fn, "func", fn), **{**kw, **extra})


# --- one run ---------------------------------------------------------------------------------
def _p95(x: np.ndarray) -> float:
    return float(np.percentile(x, 95)) if len(x) else math.nan


def score(
    est_t: np.ndarray,
    est_pos: np.ndarray,
    est_hpl: np.ndarray,
    truth_t: np.ndarray,
    truth_pos: np.ndarray,
    cut_ns: int,
    horizon_s: float = HORIZON_S,
) -> dict:
    """Horizontal error of each estimate in [cut, cut + horizon] that has truth."""
    w = (est_t >= cut_ns) & (est_t <= cut_ns + round(horizon_s * 1e9))
    t, pos, hpl = est_t[w], est_pos[w], est_hpl[w]
    ref, ok = interpolate(truth_t, truth_pos[:, :2], t)
    t, pos, hpl, ref = t[ok], pos[ok], hpl[ok], ref[ok]
    err = np.hypot(*(pos[:, :2] - ref).T)
    after = (t - cut_ns) / 1e9
    out: dict = {"n_scored": int(len(t))}
    for s in AT_S:
        k = np.argmin(np.abs(t - cut_ns - round(s * 1e9))) if len(t) else None
        hit = k is not None and abs(t[k] - cut_ns - round(s * 1e9)) <= AT_TOL_NS
        out[f"err_{s:g}s_m"] = float(err[k]) if hit else math.nan
        out[f"hpl_{s:g}s_m"] = float(hpl[k]) if hit else math.nan
        early = after < s
        full = len(after) and after.max() >= s - 1
        out[f"p95_{s:g}s_m"] = _p95(err[early]) if full else math.nan
    out["max_m"] = float(err.max()) if len(err) else math.nan
    out["hpl_bound"] = float(np.mean(hpl >= err)) if len(err) else math.nan
    out["misleading"] = int(np.sum(err > hpl))
    on_fix = np.isin(t, truth_t)
    out["hpl_bound_at_fixes"] = (
        float(np.mean(hpl[on_fix] >= err[on_fix])) if on_fix.any() else math.nan
    )
    # 1 s curve for the figure (not written to JSON): the estimate nearest each whole second
    grid = np.arange(0, int(horizon_s) + 1)
    if len(after):
        k = np.clip(np.searchsorted(after, grid), 0, len(after) - 1)
        k0 = np.maximum(k - 1, 0)
        k = np.where(np.abs(after[k0] - grid) < np.abs(after[k] - grid), k0, k)
        near = np.abs(after[k] - grid) <= 0.5
        out["_curve"] = (grid[near].tolist(), err[k][near].tolist(), hpl[k][near].tolist())
    else:
        out["_curve"] = ([], [], [])
    return out


def run_one(raw: str, lte: str | None, config: str, cut_s: float, hdop_max: float,
            min_sats: int) -> dict:  # fmt: skip
    """One replay with GNSS cut at `cut_s`, stopped `HORIZON_S` + 1 s after it, scored."""
    base, with_lte, _ = CONFIGS[config]
    d = load(lte if with_lte else raw)
    tr = truth(raw, hdop_max, min_sats)
    t0 = load(raw)["t0"]
    cut_ns = t0 + round(cut_s * 1e9)
    end = cut_ns + round((HORIZON_S + 1.0) * 1e9)
    fed = [m for m in d["meas"] if m.t_ns <= end and (with_lte or m.source != "lte")]
    fed = cut_gnss(fed, t0, cut_s)
    started = time.perf_counter()
    with watch_imu() as imus:
        est = list(nav.estimate(estimator(config), fed, origin_llh=d["origin"]))
    est_t = np.array([e.t_ns for e in est], dtype=np.int64)
    est_pos = np.array([e.pos_enu for e in est], dtype=float)
    est_hpl = np.array([np.nan if e.hpl_m is None else e.hpl_m for e in est], dtype=float)
    out = {"config": config, "estimator": base, "cut_s": cut_s}
    out.update(score(est_t, est_pos, est_hpl, tr["t"], tr["pos"], cut_ns))
    pre = (est_t >= t0 + round(SETTLE_S * 1e9)) & (est_t < cut_ns)
    ref, ok = interpolate(tr["t"], tr["pos"][:, :2], est_t[pre])
    out["pre_p95_m"] = _p95(np.hypot(*(est_pos[pre][ok, :2] - ref[ok]).T))
    out["pre_gnss_excluded"] = float(
        np.mean(["gnss_excluded" in e.flags for e, p in zip(est, pre, strict=True) if p])
    ) if pre.any() else math.nan  # fmt: skip
    v = speeds(tr["t"], tr["pos"])
    mov = np.nan_to_num(v, nan=0.0) >= MOVING_MPS
    grid = cut_ns + np.arange(0, round(HORIZON_S) + 1) * 1_000_000_000
    out["moving_share"] = float(moving_at(tr["t"], mov, grid).mean())
    out["n_lte"] = sum(m.source == "lte" for m in fed)
    if imus:
        al = imus[0].aligned_at
        out["imu_aligned"] = al is not None
        out["imu_aligned_s"] = None if al is None else round((al - t0) / 1e9, 1)
        out["imu_aligned_before_cut"] = al is not None and al < cut_ns
        out["imu_refused_windows"] = int(imus[0].refused)
    out["run_s"] = round(time.perf_counter() - started, 1)
    return out


# --- LTE records -----------------------------------------------------------------------------
def has_lte(path: Path) -> bool:
    if not (path / session.MCAP_NAME).exists():
        return False
    return any(True for _ in read_session(session.mcap_path(path), topics=["/meas/lte"]))


def lte_source(raw: Path, given: str | None) -> tuple[Path | None, subprocess.Popen | None, str]:
    """(LTE session, running front end or None, how it was found)."""
    if has_lte(raw):
        return raw, None, "the session's own /meas/lte"
    if given:
        return Path(given), None, f"--lte-session {Path(given).name}"
    beside = raw.with_name(f"{raw.name}-lte")
    if (beside / session.MCAP_NAME).exists():
        return beside, None, f"{beside.name} (front end run earlier)"
    cu8 = raw / "sdr_a.cu8"
    if not cu8.exists():
        return None, None, "none: no /meas/lte, no -lte session, no sdr_a.cu8"
    cmd = [sys.executable, "-m", "pnt.cli", "frontend", "lte", str(cu8), "--out", str(beside)]
    log = open(raw.with_name(f"{raw.name}-lte.log"), "w")  # noqa: SIM115 (lives with the process)
    print(f"front end: {' '.join(cmd)} (log {log.name})", flush=True)
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
    return beside, proc, f"{beside.name} (front end run by this script)"


def cell_report(lte: str) -> dict:
    """Per heard cell: records, how the lookup resolved it, when it was heard. No ranges."""
    d = load(lte)
    t0 = d["t0"]
    by: dict[str, list] = {}
    for m in d["meas"]:
        if m.source == "lte" and m.kind == "pseudorange":
            by.setdefault(m.emitter, []).append(m)
    table = cells.CellTable.load()
    out = {}
    for name, recs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        parsed = cells._parse(name)
        status = "sim (position given)" if "emitter_llh" in recs[0].meta or "emitter_enu" in \
            recs[0].meta else (table.associate(*parsed, d["origin"])[0] if parsed and d["origin"]
                                else cells.UNKNOWN)  # fmt: skip
        snr = [float(m.meta["snr_db"]) for m in recs if "snr_db" in m.meta]
        out[name] = {
            "records": len(recs),
            "lookup": status,
            "first_s": round((recs[0].t_ns - t0) / 1e9, 1),
            "last_s": round((recs[-1].t_ns - t0) / 1e9, 1),
            "snr_db_median": float(np.median(snr)) if snr else None,
            "arcs": len({m.meta.get("arc") for m in recs}),
        }
    return out


# --- summary ---------------------------------------------------------------------------------
def aggregate(rows: list[dict]) -> dict:
    by: dict = {}
    for r in rows:
        by.setdefault(r["config"], []).append(r)
    agg = {}
    for c, rs in by.items():
        a: dict = {"runs": len(rs)}
        for f in [f"err_{s:g}s_m" for s in AT_S] + [f"hpl_{s:g}s_m" for s in AT_S] + [
            f"p95_{s:g}s_m" for s in AT_S
        ] + ["max_m", "pre_p95_m"]:  # fmt: skip
            v = np.array([r[f] for r in rs], dtype=float)
            v = v[~np.isnan(v)]
            a[f] = {
                "median": float(np.median(v)) if v.size else math.nan,
                "worst": float(v.max()) if v.size else math.nan,
            }
        n = np.array([r["n_scored"] for r in rs])
        b = np.array([r["hpl_bound"] for r in rs], dtype=float)
        a["hpl_bound"] = float(np.nansum(b * n) / max(n.sum(), 1))
        a["misleading"] = int(sum(r["misleading"] for r in rs))
        a["scored"] = int(n.sum())
        a["pre_gnss_excluded"] = float(np.nanmean([r["pre_gnss_excluded"] for r in rs]))
        if "imu_aligned" in rs[0]:
            a["imu_aligned_runs"] = int(sum(r["imu_aligned"] for r in rs))
            a["imu_aligned_before_cut_runs"] = int(sum(r["imu_aligned_before_cut"] for r in rs))
        agg[c] = a
    return agg


def _fmt(x) -> str:
    if x is None or x != x:
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


def markdown(s: dict) -> str:
    tr = s["truth"]
    lines = [
        f"# GPS cut on a moving session: `{s['session']}` (#214)",
        "",
        f"Evidence: **{s['kind']}**, GPS cut in software (ADR-0015). Analysis at `{s['commit']}`; "
        f"LTE records: {s['lte']['source']}"
        + (
            f", front end at `{s['lte']['frontend_commit']}`"
            if s["lte"].get("frontend_commit")
            else ""
        )
        + ". "  # fmt: skip
        f"{len(s['cuts_s'])} cuts ({', '.join(f'{c:g}' for c in s['cuts_s'])} s after the first "
        f"measurement; {s['cut_mode']}), each scored for {s['horizon_s']:g} s. The cuts share one "
        "recording: they are not independent draws, and the worst cut is not a 95th percentile.",
        "",
        f"Truth: the withheld GPS fixes, linear between good fixes at most {MAX_GAP_S:g} s apart, "
        f"at every estimate. Good fix: {tr['basis']}; {tr['good']} of {tr['fixes']} fixes "
        f"(median HDOP {_fmt(tr['hdop_p50'])}, median satellites used {_fmt(tr['nsat_p50'])}). "
        "The truth carries the fixes' own error (metres), so smaller errors are truth noise. "
        f"Moving: speed from the fixes >= {MOVING_MPS:g} m/s (TBC); "
        f"{s['motion']['moving_share']:.0%} of the session with truth. "
        "No position, track, origin, range or bearing is given here, only errors.",
        "",
    ]
    if s.get("truth_check"):
        t = s["truth_check"]
        lines += [
            f"Sim check of the truth: interpolated fixes against the sim's `/truth`, horizontal, "
            f"{t['p50_m']:.2f} m median, {t['p95_m']:.2f} m p95, {t['max_m']:.2f} m max "
            f"({t['n']} epochs).",
            "",
        ]
    lines += [
        "## Horizontal error after the cut",
        "",
        "Median over the cuts, worst cut in brackets (m). HPL ≥ error: share of every scored "
        "estimate (10 Hz) in the windows.",
        "",
        "| Config | 60 s | 120 s | 300 s | p95 0–300 s (worst) | HPL at 300 s | HPL ≥ error | "
        "Error > HPL (epochs) | Before cut: p95 | Before cut: GNSS excluded |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c, a in s["aggregate"].items():
        cells_ = [
            f"{_fmt(a[f'err_{t:g}s_m']['median'])} ({_fmt(a[f'err_{t:g}s_m']['worst'])})"
            for t in AT_S
        ]
        lines.append(
            f"| {c} | {' | '.join(cells_)} | {_fmt(a['p95_300s_m']['worst'])} | "
            f"{_fmt(a['hpl_300s_m']['median'])} | {a['hpl_bound']:.0%} | "
            f"{a['misleading']} / {a['scored']} | {_fmt(a['pre_p95_m']['median'])} | "
            f"{a['pre_gnss_excluded']:.0%} |"
        )
    imu = [(c, a) for c, a in s["aggregate"].items() if "imu_aligned_runs" in a]
    if imu:
        lines += ["", "## IMU alignment (`ekf-imu`)", ""]
        for c, a in imu:
            at = [r.get("imu_aligned_s") for r in s["runs"] if r["config"] == c]
            lines.append(
                f"- {c}: aligned in {a['imu_aligned_runs']} of {a['runs']} runs, before the cut "
                f"in {a['imu_aligned_before_cut_runs']}; aligned at "
                f"{', '.join('—' if x is None else f'{x:g} s' for x in at)}."
            )
    lc = s["lte"].get("cells") or {}
    if lc:
        status = Counter(v["lookup"] for v in lc.values())
        lines += [
            "",
            "## LTE cells heard",
            "",
            f"Lookup (`pnt.nav.cells`, `MAX_RANGE_KM` {cells.MAX_RANGE_KM:g} km of the session "
            f"origin, TBC): {', '.join(f'{n} {k}' for k, n in status.items())}. Records of "
            "cells not matched are dropped before the filter. Times in s after the first "
            "measurement; no ranges.",
            "",
            "| Cell | Records | Lookup | Heard from–to (s) | Median SNR (dB) | Arcs |",
            "|---|---|---|---|---|---|",
        ]
        for name, v in lc.items():
            lines.append(
                f"| `{name}` | {v['records']} | {v['lookup']} | {v['first_s']:g}–{v['last_s']:g} "
                f"| {_fmt(v['snr_db_median'])} | {v['arcs']} |"
            )
    lines += [
        "",
        "## Runs",
        "",
        "| Config | Cut (s) | Moving share | 60 s | 120 s | 300 s | HPL ≥ error | Run time (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in s["runs"]:
        lines.append(
            f"| {r['config']} | {r['cut_s']:g} | {r['moving_share']:.0%} | "
            f"{_fmt(r['err_60s_m'])} | {_fmt(r['err_120s_m'])} | {_fmt(r['err_300s_m'])} | "
            f"{r['hpl_bound']:.0%} | {r['run_s']:g} |"
        )
    lines += ["", f"Wall time: {s['wall_s']:.0f} s.", ""]
    return "\n".join(lines)


# reference categorical palette (dataviz skill): blue, orange, aqua, yellow, violet, grey
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a5cd6", "#6b7280"]


def plot(rows: list[dict], summary: dict, path: Path) -> None:
    """Error (solid) and HPL (dashed) against time since the cut: median over the cuts, band =
    min–max, one colour per configuration. No tracks."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grid = np.arange(0, int(summary["horizon_s"]) + 1)
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    for color, c in zip(COLORS, summary["aggregate"], strict=False):
        curves_e, curves_h = [], []
        for r in rows:
            if r["config"] != c:
                continue
            x, e, h = (np.asarray(v, dtype=float) for v in r["_curve"])
            if x.size < 2:
                continue
            curves_e.append(np.interp(grid, x, e, left=np.nan, right=np.nan))
            curves_h.append(np.interp(grid, x, h, left=np.nan, right=np.nan))
        if not curves_e:
            continue
        with np.errstate(all="ignore"), contextlib.suppress(RuntimeWarning):
            e = np.array(curves_e)
            ax.fill_between(grid, np.nanmin(e, 0), np.nanmax(e, 0), color=color, alpha=0.12, lw=0)
            ax.plot(grid, np.nanmedian(e, 0), color=color, lw=2, label=f"{c}: error")
            ax.plot(grid, np.nanmedian(np.array(curves_h), 0), color=color, lw=1, ls="--",
                    label=f"{c}: HPL")  # fmt: skip
    ax.set_yscale("log")
    ax.set_ylim(0.3, 1e5)
    ax.axhline(25.0, color="0.5", lw=0.8)
    ax.text(grid[-1], 27, "T1 25 m (TBC)", ha="right", va="bottom", fontsize=7)
    ax.set_xlabel("s after the GPS cut")
    ax.set_ylabel("horizontal error / HPL (m)")
    ax.grid(True, which="major", color="0.9", lw=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(fontsize=7, frameon=False, ncol=2, loc="upper left")
    ax.set_title(
        f"{summary['session']} ({summary['kind']}), {summary['commit']}: median of "
        f"{len(summary['cuts_s'])} cuts, band = min–max",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _commit(cwd: Path = REPO) -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            cwd=cwd, capture_output=True, text=True,
        ).stdout.strip() or "unknown"  # fmt: skip
    except OSError:
        return "unknown"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session", help="session folder or name under data/sessions/")
    ap.add_argument("--cuts", type=int, default=N_CUTS, help="automatic cuts in the moving part")
    ap.add_argument("--cut-at", type=float, nargs="+", help="cut times (s) instead; no checks")
    ap.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS, choices=list(CONFIGS))
    ap.add_argument("--lte-session", help="session with the LTE records (default: see above)")
    ap.add_argument("--hdop-max", type=float, default=HDOP_MAX)
    ap.add_argument("--min-sats", type=int, default=MIN_SATS)
    ap.add_argument("--jobs", type=int, default=3, help="worker processes (<= 3 on this laptop)")
    ap.add_argument("--out", help="default analysis/results/<session>/")
    args = ap.parse_args(argv)
    started = time.perf_counter()
    raw = resolve(args.session)
    d = load(str(raw))
    tr = truth(str(raw), args.hdop_max, args.min_sats)
    if args.cut_at:
        cuts, mode = sorted(args.cut_at), "given with --cut-at"
    else:
        cuts = select_cuts(tr["t"], tr["pos"], d["t0"], args.cuts)
        mode = (
            f"picked in the moving part: >= {PRE_S:g} s of good GPS before, moving at the cut "
            f"and >= {MIN_MOVING:.0%} of the {PRE_S:g} s before and the window"
        )
    if not cuts:
        raise SystemExit(
            "no cut time qualifies (moving, >= 60 s of good GPS before, truth for 300 s after); "
            "give times with --cut-at"
        )
    print(f"cuts (s): {cuts}", flush=True)
    lte, proc, how = lte_source(raw, args.lte_session)
    configs = [c for c in args.configs if CONFIGS[c][1] is False or lte is not None]

    def task(c: str, cut: float) -> tuple:
        return (str(raw), str(lte) if lte else None, c, cut, args.hdop_max, args.min_sats)

    first = [c for c in configs if not CONFIGS[c][1]]
    later = [c for c in configs if CONFIGS[c][1]]
    jobs = max(1, args.jobs - (proc is not None))
    rows = experiments._map(run_one, [task(c, cut) for c in first for cut in cuts], jobs)
    fe_wait = 0.0
    if proc is not None:
        w = time.perf_counter()
        if proc.wait() != 0:
            raise SystemExit(f"LTE front end failed (exit {proc.returncode}); see its log")
        fe_wait = time.perf_counter() - w
    if later:
        rows += experiments._map(run_one, [task(c, cut) for c in later for cut in cuts], args.jobs)
    summary = {
        "session": raw.name,
        "kind": "sim session (replay)"
        if session.read_meta(raw).get("simulated")
        else "replay of a real session",  # fmt: skip
        "platform": session.read_meta(raw).get("platform"),
        "commit": _commit(),
        "cuts_s": cuts,
        "cut_mode": mode,
        "horizon_s": HORIZON_S,
        "truth": {k: v for k, v in tr.items() if k not in ("t", "pos")},
        "thresholds": {
            "hdop_max": args.hdop_max,
            "min_sats": args.min_sats,
            "max_gap_s": MAX_GAP_S,
            "moving_mps": MOVING_MPS,
            "min_moving": MIN_MOVING,
            "pre_s": PRE_S,
        },  # fmt: skip
        "motion": {},
        "lte": {"source": how},
        "frontend_wait_s": round(fe_wait, 1),
    }
    v = speeds(tr["t"], tr["pos"])
    summary["motion"] = {
        "moving_share": float(np.mean(np.nan_to_num(v, nan=0.0) >= MOVING_MPS)) if v.size else 0.0,
        "speed_p50_moving_mps": float(np.nanmedian(v[v >= MOVING_MPS]))
        if np.any(v >= MOVING_MPS)
        else math.nan,  # fmt: skip
    }
    if lte is not None:
        summary["lte"]["frontend_commit"] = (
            None if lte == raw else session.read_meta(lte).get("commit")
        )
        summary["lte"]["cells"] = cell_report(str(lte))
    if d["truth_t"].size:  # sim: how far the fix-based truth is from the sim's own
        ref, ok = interpolate(tr["t"], tr["pos"][:, :2], d["truth_t"])
        e = np.hypot(*(ref[ok] - d["truth_pos"][ok, :2]).T)
        summary["truth_check"] = {"n": int(ok.sum()), "p50_m": float(np.median(e)),
                                  "p95_m": _p95(e), "max_m": float(e.max())}  # fmt: skip
    summary["aggregate"] = aggregate(rows)
    summary["runs"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    summary["wall_s"] = round(time.perf_counter() - started, 1)
    out = Path(args.out) if args.out else REPO / "analysis" / "results" / raw.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    (out / "summary.md").write_text(markdown(summary))
    plot(rows, summary, out / "error_vs_time.png")
    print(markdown(summary))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
