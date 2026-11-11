"""LTE pseudorange error of a static capture against GPS truth (#21).

    python analysis/lte_gps_truth.py <session>-lte [--out DIR] [--plot PNG]

Reads a session that `pnt frontend lte` wrote from a static capture with a GPS fix (the front end
copies the capture's `/meas/gnss` records into it). The receiver's true position is the mean of
its 3D fixes. Each heard cell is looked up in the committed cell table (`pnt.nav.cells`): a match
is a hypothesis (the (EARFCN, PCI) is used by one registered eNB only), never a confirmed
identity, and the table has no ground height (tower height = receiver height + antenna height
above ground, `TBC`, as `cells.attach` does).

For each matched cell the error is `e(t) = pseudorange(t) − true range`. One cell's error still
holds the dongle clock, which jumps at every sample gap, so each cell is differenced against the
strongest cell on the same `rx_clock` (as `analysis/lte_static_capture.py` does):

    D(t) = e_cell(t) − e_ref(t) = c·(tower clock difference) + noise + multipath change

D is known only modulo one 10 ms frame. Wrapped to ±half a frame, its median is the two towers'
**frame-timing offset** after the true range difference is removed: near zero when the two
towers transmit in step. Removing that one constant per pair (not one per arc) is what the GPS
truth adds: every arc is placed on the same constant, so reacquisitions that land elsewhere show
up as jumps and the drift and wander are measured across the whole capture.

Per pair: residual σ, white σ, the structure function S(τ) for 0.1 to 100 s, a linear drift
(tower clock frequency difference) and a Gauss-Markov fit to S(τ), beside the sim's challenge
values and ADR-0036's proposed model. The structure function is the second difference used by
ADR-0036 (`analysis/lte_measured_noise.py`, #190):

    S(τ)² = E[(x(t+τ) − 2 x(t) + x(t−τ))²] / 6

which removes a constant and a constant drift, equals σ for white noise at every τ, and for a
first-order Gauss-Markov error (s, T) is s² (1 − 4/3 e^(−τ/T) + 1/3 e^(−2τ/T)).

**Privacy:** the receiver position, the true ranges and their differences are used in memory
only. Nothing that pins the receiver down is printed or written: only residual statistics,
cell and eNB identifiers and timing offsets after truth is removed.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pnt.core.frames import enu_to_llh, llh_to_enu
from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.nav.cells import MATCHED, CellTable

C = 299_792_458.0
DT = 0.1  # the front end's output period (tracker.Config.output_period_s)
FRAME_M = C * 0.010  # pseudorange ambiguity (meta.ambiguity_m)
TAUS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]
MIN_TRIPLETS = 30  # fewer second differences than this: no S(τ) value (as in #190)
MIN_EPOCHS = 20  # fewer common epochs above the SNR cut than this: no pair statistics
# TBC: ADR-0036's cut (#190). Below it a cell's records are not used for the statistics: on
# 2026-11-10 the white-σ law stopped holding there, and on 20261111-0040-static-fullsuite the
# records below it drift by kilometres (loss of lock the front end still reports).
SNR_MIN_DB = -8.0
# TBC: an arc of a pair whose median sits further than this from the pair's constant has landed
# on another timing after reacquisition (a jump). #190 uses 30 m for "lands on its old timing".
JUMP_M = 30.0
# Sim values the comparison is drawn against (src/pnt/sim/scenarios/sets/challenge-drone.yaml):
# white range noise and a per-eNB Gauss-Markov multipath, both TBC there.
SIM_CHALLENGE = {"sigma_m": 50.0, "multipath_m": 50.0, "multipath_tau_s": 30.0, "told_m": 2.0}
# ADR-0036 (Proposed, #190): white σ² = A² + B² / SNR_lin at 10 Hz for SNR ≥ −8 dB, and a
# per-cell correlated part (sigma_corr_m, tau_corr_s). All TBC there.
ADR36 = {"a_m": 0.64, "b_m": 2.28, "fit_min_snr_db": -8.0, "corr_m": 10.0, "corr_tau_s": 3.0}
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#7b4fa0", "#1b9e9e"]
INK, GRID, MUTED = "#1f2328", "#d0d7de", "#8c959f"


@dataclass
class Series:
    """One cell's 10 Hz pseudoranges on one dongle."""

    emitter: str
    rx_clock: str
    earfcn: int
    pci: int
    k: np.ndarray  # 10 Hz grid index from the session's first LTE record
    v: np.ndarray  # pseudorange (m)
    sig: np.ndarray  # reported σ (m)
    snr: np.ndarray  # meta.snr_db
    arc: np.ndarray


# --- loading ----------------------------------------------------------------------------------


def load_lte(path) -> list[Series]:
    by: dict[tuple[str, str], list[Measurement]] = defaultdict(list)
    for _, m in read_session(session.mcap_path(path), topics=["/meas/lte"]):
        if isinstance(m, Measurement) and m.kind == "pseudorange":
            by[(m.meta.get("rx_clock", ""), m.emitter)].append(m)
    if not by:
        raise SystemExit(f"{path}: no /meas/lte pseudoranges")
    t0 = min(m.t_ns for ms in by.values() for m in ms)
    out = []
    for (clock, emitter), ms in sorted(by.items()):
        ms.sort(key=lambda m: m.t_ns)
        k = np.rint((np.array([m.t_ns for m in ms], dtype=np.int64) - t0) / 1e9 / DT)
        keep = np.r_[True, np.diff(k) > 0]  # one record per grid slot
        out.append(
            Series(
                emitter=emitter,
                rx_clock=clock,
                earfcn=int(ms[0].meta.get("earfcn") or 0),
                pci=int(ms[0].meta["pci"]),
                k=k[keep].astype(np.int64),
                v=np.array([m.value[0] for m in ms])[keep],
                sig=np.array([m.sigma[0] for m in ms])[keep],
                snr=np.array([m.meta["snr_db"] for m in ms], dtype=float)[keep],
                arc=np.array([m.meta.get("arc", 0) for m in ms], dtype=np.int64)[keep],
            )
        )
    return out


def receiver_llh(path) -> tuple[np.ndarray, int]:
    """Mean of the session's 3D GNSS fixes, as WGS84 lat, lon, height; and the fix count."""
    origin = session.read_meta(path).get("origin_llh")
    if origin is None:
        raise SystemExit(f"{path}: no origin_llh, so no GNSS truth")
    enu = [
        m.value
        for _, m in read_session(session.mcap_path(path), topics=["/meas/gnss"])
        if isinstance(m, Measurement) and m.kind == "position_enu"
    ]
    if not enu:
        raise SystemExit(f"{path}: no /meas/gnss position_enu fixes, so no GNSS truth")
    return enu_to_llh(np.mean(np.array(enu, dtype=float), axis=0), origin), len(enu)


def true_ranges(series: list[Series], rx_llh, table: CellTable) -> dict[str, dict]:
    """Per emitter: lookup status, eNB and the true range (m), which stays in memory only."""
    out = {}
    for s in series:
        status, cell = table.associate(s.earfcn, s.pci, rx_llh)
        info = {"status": status, "enb": None, "range_m": None}
        if status == MATCHED and cell is not None:
            tower = [cell.lat, cell.lon, float(rx_llh[2]) + cell.height_agl_m]
            info["enb"] = cell.enb_id
            info["range_m"] = float(np.linalg.norm(llh_to_enu(tower, rx_llh)))
        out[s.emitter] = info
    return out


# --- statistics -------------------------------------------------------------------------------


def wrap(x, period: float = FRAME_M):
    """x into [−period/2, period/2)."""
    return (np.asarray(x, dtype=float) + period / 2) % period - period / 2


def second_diff(k: np.ndarray, v: np.ndarray, label: np.ndarray, m: int) -> np.ndarray:
    """x(k+m) − 2 x(k) + x(k−m) wherever all three exist with one label."""
    if k.size < 3:
        return np.empty(0)
    pos = np.full(int(k.max()) + 1, -1, np.int64)
    pos[k] = np.arange(k.size)
    lo, hi = k - m, k + m
    i = np.flatnonzero((lo >= 0) & (hi <= k.max()))
    a, b = pos[lo[i]], pos[hi[i]]
    ok = (a >= 0) & (b >= 0)
    i, a, b = i[ok], a[ok], b[ok]
    same = (label[a] == label[i]) & (label[b] == label[i])
    i, a, b = i[same], a[same], b[same]
    return v[b] - 2 * v[i] + v[a]


def structure(k, v, label, taus=TAUS) -> dict[float, float]:
    """S(τ) (m), robust (MAD) form, for each τ with enough triplets."""
    out = {}
    for tau in taus:
        d = second_diff(k, v, label, max(1, round(tau / DT)))
        if d.size >= MIN_TRIPLETS:
            out[float(tau)] = 1.4826 * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(6)
    return out


def gm_structure(tau, white_m: float, s_m: float, t_s: float):
    """S(τ) of white noise plus a first-order Gauss-Markov error (s, T)."""
    tau = np.asarray(tau, dtype=float)
    gm = s_m**2 * (1 - 4 / 3 * np.exp(-tau / t_s) + 1 / 3 * np.exp(-2 * tau / t_s))
    return np.sqrt(white_m**2 + gm)


def fit_gm(s_tau: dict[float, float]) -> dict | None:
    """Least squares in log S over a grid of correlation times: (white, s, T)."""
    if len(s_tau) < 4:
        return None
    tau = np.array(list(s_tau))
    y = np.array(list(s_tau.values())) ** 2
    best = None
    for t_s in np.geomspace(0.1, 1000, 121):
        g = 1 - 4 / 3 * np.exp(-tau / t_s) + 1 / 3 * np.exp(-2 * tau / t_s)
        a = np.c_[np.ones_like(tau), g] / y[:, None]  # relative error: each τ counts alike
        coef, *_ = np.linalg.lstsq(a, np.ones_like(tau), rcond=None)
        coef = np.maximum(coef, 0.0)
        cost = float(np.sum(np.log(gm_structure(tau, *np.sqrt(coef), t_s) ** 2 / y) ** 2))
        if best is None or cost < best[0]:
            best = (cost, math.sqrt(coef[0]), math.sqrt(coef[1]), float(t_s))
    _, w, s, t = best
    return {
        "white_m": w,
        "corr_m": s,
        "corr_tau_s": t,
        "rms_log_misfit": math.sqrt(best[0] / tau.size),
    }


def drift(k: np.ndarray, v: np.ndarray, pieces: int = 4) -> dict | None:
    """Slope (m/s) of 1 s means, with its standard error widened to the spread of the slopes of
    `pieces` equal parts (correlated noise makes the least-squares error too small)."""
    sec = k // 10
    u, inv = np.unique(sec, return_inverse=True)
    if u.size < 4 * pieces:
        return None
    t = u.astype(float)
    y = np.bincount(inv, weights=v) / np.bincount(inv)
    p, cov = np.polyfit(t, y, 1, cov=True)
    se = math.sqrt(cov[0, 0])
    parts = [np.polyfit(t[c], y[c], 1)[0] for c in np.array_split(np.arange(t.size), pieces)]
    se_parts = float(np.std(parts, ddof=1) / math.sqrt(pieces))
    return {"slope_mps": float(p[0]), "se_mps": max(se, se_parts), "span_s": float(t[-1] - t[0])}


def adr36_white(snr_db: float) -> float:
    """ADR-0036's proposed white σ (m, 10 Hz) at this SNR; NaN below its fit's range."""
    if snr_db < ADR36["fit_min_snr_db"]:
        return float("nan")
    return math.sqrt(ADR36["a_m"] ** 2 + ADR36["b_m"] ** 2 / 10 ** (snr_db / 10))


def pair(
    ref: Series, cell: Series, rho_ref: float, rho_cell: float, snr_min_db: float = None
) -> dict | None:
    """Error of `cell` minus error of `ref` on their common 10 Hz epochs (see module docstring).

    Statistics are on the epochs where both cells are at or above `snr_min_db` (default
    SNR_MIN_DB); `all_*` values use every common epoch, to show what the records below it do.
    The returned arrays are residuals only: the true ranges never leave this function."""
    snr_min_db = SNR_MIN_DB if snr_min_db is None else snr_min_db
    common, i, j = np.intersect1d(cell.k, ref.k, return_indices=True)
    if common.size == 0:
        return None
    d_all = wrap((cell.v[i] - rho_cell) - (ref.v[j] - rho_ref))
    told = np.hypot(cell.sig[i], ref.sig[j])
    out = {
        "n_all": int(common.size),
        "all_robust_m": _circ_spread(d_all),
        "all_told_sigma_m": float(np.median(told)),
    }
    gate = (cell.snr[i] >= snr_min_db) & (ref.snr[j] >= snr_min_db)
    out["n"] = int(gate.sum())
    if gate.sum() < MIN_EPOCHS:
        return out
    k, d = common[gate], d_all[gate]
    # One constant for the pair: the circular median keeps a frame wrap from splitting it.
    c0 = float(np.median(d))
    c1 = float(np.median(wrap(d - c0)))
    offset = float(wrap(c0 + c1))
    resid = wrap(d - c0) - c1
    arc_pair = cell.arc[i][gate] * 100_000 + ref.arc[j][gate]
    arc_meds = {int(a): float(np.median(resid[arc_pair == a])) for a in np.unique(arc_pair)}
    # The longest arc pair: its cells have been tracked longest without a break, so it is the
    # least likely to hold a track that has not settled or is running off.
    labels, counts = np.unique(arc_pair, return_counts=True)
    longest = labels[np.argmax(counts)]
    off_long = float(wrap(offset + arc_meds[int(longest)]))
    jumped = {a for a, med in arc_meds.items() if abs(med) > JUMP_M}
    keep = ~np.isin(arc_pair, list(jumped))
    one = np.zeros(k.size, np.int64)  # one label: S(τ) spans arcs (they share a constant)
    s_tau = structure(k[keep], resid[keep], one[keep])
    snr_c = float(np.median(cell.snr[i][gate]))
    snr_r = float(np.median(ref.snr[j][gate]))
    out.update(
        span_s=float((k[-1] - k[0]) * DT),
        snr_db=snr_c,
        ref_snr_db=snr_r,
        offset_m=offset,
        offset_us=offset / C * 1e6,
        offset_longest_arc_us=off_long / C * 1e6,
        longest_arc_n=int(counts.max()),
        arcs=len(arc_meds),
        arcs_jumped=len(jumped),
        epochs_in_jumped_arcs=int((~keep).sum()),
        resid_sigma_m=float(np.std(resid[keep])) if keep.any() else float("nan"),
        resid_robust_m=1.4826 * float(np.median(np.abs(resid[keep])))
        if keep.any()
        else float("nan"),
        white_m=s_tau.get(0.1, float("nan")),
        S_m=s_tau,
        drift=drift(k[keep], resid[keep]),
        gm_fit=fit_gm(s_tau),
        told_sigma_m=float(np.median(told[gate])),
        adr36_white_m=math.hypot(adr36_white(snr_c), adr36_white(snr_r)),
        _k=k[keep],
        _resid=resid[keep],
    )
    return out


def _circ_spread(d: np.ndarray) -> float:
    """Robust σ (MAD) of values known modulo one frame, about their circular median."""
    c0 = float(np.median(d))
    x = wrap(d - c0)
    return 1.4826 * float(np.median(np.abs(x - np.median(x))))


def analyse(
    series: list[Series], info: dict[str, dict], capture_s: float, snr_min_db: float = None
) -> dict:
    """Per-cell availability and SNR; per-pair residuals against the cell on each dongle with the
    most epochs at or above the SNR cut."""
    snr_min_db = SNR_MIN_DB if snr_min_db is None else snr_min_db
    cells, pairs = [], []
    for s in series:
        hi = s.snr >= snr_min_db
        cells.append(
            {
                "emitter": s.emitter,
                "rx_clock": s.rx_clock,
                "status": info[s.emitter]["status"],
                "enb": info[s.emitter]["enb"],
                "n": int(s.k.size),
                "tracked": float(s.k.size * DT / capture_s),
                "tracked_above_cut": float(hi.sum() * DT / capture_s),
                "arcs": int(np.unique(s.arc).size),
                "snr_db": float(np.median(s.snr)),
                "told_sigma_m": float(np.median(s.sig)),
                "told_sigma_below_cut_m": float(np.median(s.sig[~hi])) if (~hi).any() else None,
                # one cell (dongle clock in it): S(τ) inside each arc, above and below the cut
                "S1_above_cut_m": structure(s.k[hi], s.v[hi], s.arc[hi], [1]).get(1.0),
                "S1_below_cut_m": structure(s.k[~hi], s.v[~hi], s.arc[~hi], [1]).get(1.0),
                "white_above_cut_m": structure(s.k[hi], s.v[hi], s.arc[hi], [0.1]).get(0.1),
                "adr36_white_m": adr36_white(float(np.median(s.snr[hi])))
                if hi.any()
                else float("nan"),
            }
        )
    for clock in sorted({s.rx_clock for s in series}):
        matched = [s for s in series if s.rx_clock == clock and info[s.emitter]["range_m"]]
        if len(matched) < 2:
            continue
        ref = max(matched, key=lambda s: (int((s.snr >= snr_min_db).sum()), s.k.size))
        for s in matched:
            if s is ref:
                continue
            r = pair(ref, s, info[ref.emitter]["range_m"], info[s.emitter]["range_m"], snr_min_db)
            if r is None:
                continue
            r.update(
                emitter=s.emitter,
                ref=ref.emitter,
                rx_clock=clock,
                same_enb=info[s.emitter]["enb"] == info[ref.emitter]["enb"],
                tracked=float(r["n"] * DT / capture_s),
            )
            pairs.append(r)
    return {"capture_s": capture_s, "snr_min_db": snr_min_db, "cells": cells, "pairs": pairs}


# --- output -----------------------------------------------------------------------------------


def _f(x, nd=2) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def markdown(res: dict, name: str, commit: str, n_fix: int) -> str:
    taus = [0.5, 1.0, 2.0, 5.0, 10.0]
    cut = res["snr_min_db"]
    lines = [
        f"Session `{name}`, analysed at `{commit}`. Receiver truth: mean of {n_fix} GNSS fixes "
        f"(position withheld for privacy). Capture on disk {res['capture_s']:.1f} s. SNR cut "
        f"{cut:g} dB (`TBC`, ADR-0036). eNB by the committed table only: a hypothesis.",
        "",
    ]
    head = [
        "Cell", "eNB (table)", "Lookup", "Tracked", f"Tracked ≥ {cut:g} dB", "Arcs",
        "SNR median (dB)", "Told σ median (m)", f"Told σ < {cut:g} dB (m)",
        f"White σ ≥ {cut:g} dB (m)", "ADR-0036 white (m)", f"S(1 s) ≥ {cut:g} dB (m)",
        f"S(1 s) < {cut:g} dB (m)",
    ]  # fmt: skip
    lines += ["| " + " | ".join(head) + " |", "|---" * len(head) + "|"]
    for c in res["cells"]:
        lines.append(
            f"| {c['emitter']} | {c['enb'] or '—'} | {c['status']} | {c['tracked']:.1%} | "
            f"{c['tracked_above_cut']:.1%} | {c['arcs']} | {c['snr_db']:.1f} | "
            f"{_f(c['told_sigma_m'])} | {_f(c['told_sigma_below_cut_m'])} | "
            f"{_f(c['white_above_cut_m'])} | {_f(c['adr36_white_m'])} | "
            f"{_f(c['S1_above_cut_m'])} | {_f(c['S1_below_cut_m'], 0)} |"
        )
    head = [
        "Pair (cell − ref)", "Same eNB", "Common epochs, all", "All: robust σ (m)",
        "All: told σ (m)", f"Both ≥ {cut:g} dB", "Span (s)", "Frame offset after truth (µs)",
        "Same, longest arc pair (µs, epochs)",
        "Arcs (jumped)", "Resid σ (m)", "Robust σ (m)", "White σ (m)", "Told σ (m)",
        "ADR-0036 white (m)", *(f"S({t:g} s) (m)" for t in taus), "Drift (m/s)",
        "GM fit: white, s (m), T (s)",
    ]  # fmt: skip
    lines += ["", "| " + " | ".join(head) + " |", "|---" * len(head) + "|"]
    for p in res["pairs"]:
        row = [
            f"{p['emitter']} − {p['ref']}", "yes" if p["same_enb"] else "no", str(p["n_all"]),
            _f(p["all_robust_m"], 0), _f(p["all_told_sigma_m"]), f"{p['n']} ({p['tracked']:.1%})",
        ]  # fmt: skip
        if "offset_m" not in p:
            row += ["too few"] + ["—"] * (len(head) - len(row) - 1)
        else:
            dr, gm = p["drift"], p["gm_fit"]
            row += [
                _f(p["span_s"], 1), f"{p['offset_us']:+.3f}",
                f"{p['offset_longest_arc_us']:+.3f} ({p['longest_arc_n']})",
                f"{p['arcs']} ({p['arcs_jumped']})", _f(p["resid_sigma_m"]),
                _f(p["resid_robust_m"]), _f(p["white_m"]), _f(p["told_sigma_m"]),
                _f(p["adr36_white_m"]), *(_f(p["S_m"].get(t)) for t in taus),
                f"{dr['slope_mps']:+.2f} ± {dr['se_mps']:.2f}" if dr else "—",
                f"{gm['white_m']:.2f}, {gm['corr_m']:.2f}, {gm['corr_tau_s']:.1f}" if gm else "—",
            ]  # fmt: skip
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def plot(res: dict, path: Path, caption: str, all_pairs: list[dict]) -> None:
    """Left: every common epoch of each pair after truth (km). Middle: the epochs above the SNR
    cut after one constant (m). Right: their S(τ) beside the sim and ADR-0036."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pairs = [p for p in res["pairs"] if "offset_m" in p]
    fig, (a0, a1, a2) = plt.subplots(
        1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1.2, 1.2, 1]}
    )
    for ax in (a0, a1, a2):
        ax.grid(True, color=GRID, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for n, p in enumerate(all_pairs):
        a0.plot(p["t"], p["d_km"], ".", ms=2, color=PALETTE[n % len(PALETTE)], label=p["label"])
    vals = np.concatenate([p["d_km"] for p in all_pairs]) if all_pairs else np.zeros(1)
    lim = 1.2 * float(np.percentile(np.abs(vals), 99)) + 0.1
    off = int(np.sum(np.abs(vals) > lim))
    a0.set_ylim(-lim, lim)
    a0.set_xlabel("time since first LTE record (s)")
    a0.set_ylabel("pair error after truth, every epoch (km)")
    if off:
        a0.text(0.01, 0.01, f"{off} epoch(s) off scale", transform=a0.transAxes, fontsize=8)
    a0.set_title("all records", loc="left", fontsize=10)
    a0.legend(fontsize=8, markerscale=5, frameon=False)
    for n, p in enumerate(res["pairs"]):
        if "offset_m" not in p:
            continue
        col = PALETTE[n % len(PALETTE)]
        lab = f"{p['emitter']} − {p['ref']}"
        if p["_k"].size == 0:
            continue
        a1.plot(p["_k"] * DT, p["_resid"], ".", ms=3, color=col, label=lab)
        t = sorted(p["S_m"])
        a2.plot(t, [p["S_m"][x] for x in t], "o-", ms=4, lw=2, color=col, label=lab)
    a1.set_xlabel("time since first LTE record (s)")
    a1.set_ylabel("pair error after truth and one constant (m)")
    a1.set_title(f"both cells ≥ {res['snr_min_db']:g} dB", loc="left", fontsize=10)
    a1.legend(fontsize=8, markerscale=3, frameon=False)
    tau = np.geomspace(0.1, 100, 60)
    sim = SIM_CHALLENGE
    a2.plot(
        tau,
        math.sqrt(2)
        * gm_structure(tau, sim["sigma_m"], sim["multipath_m"], sim["multipath_tau_s"]),
        "--",
        color=MUTED,
        lw=1.5,
        label="sim challenge-drone, pair (TBC)",
    )
    if pairs:
        w36 = float(np.nanmedian([p["adr36_white_m"] for p in pairs]))
        a2.plot(
            tau,
            math.sqrt(2)
            * gm_structure(tau, w36 / math.sqrt(2), ADR36["corr_m"], ADR36["corr_tau_s"]),
            ":",
            color=INK,
            lw=1.5,
            label="ADR-0036 proposed, pair",
        )
    a2.set_xscale("log")
    a2.set_yscale("log")
    a2.set_xlabel("τ (s)")
    a2.set_ylabel("S(τ) (m)")
    a2.set_title(f"structure function, both ≥ {res['snr_min_db']:g} dB", loc="left", fontsize=10)
    a2.legend(fontsize=8, frameon=False)
    fig.suptitle(caption, fontsize=9, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def all_epochs(series: list[Series], info: dict[str, dict], res: dict) -> list[dict]:
    """For the left panel: each pair's error after truth on every common epoch, about its
    circular median (km). Residuals only."""
    by = {s.emitter: s for s in series}
    out = []
    for p in res["pairs"]:
        a, b = by[p["emitter"]], by[p["ref"]]
        common, i, j = np.intersect1d(a.k, b.k, return_indices=True)
        d = wrap((a.v[i] - info[a.emitter]["range_m"]) - (b.v[j] - info[b.emitter]["range_m"]))
        out.append(
            {
                "t": common * DT,
                "d_km": wrap(d - np.median(d)) / 1e3,
                "label": f"{p['emitter']} − {p['ref']}",
            }
        )
    return out


def _capture_s(lte_session: Path, raw: Path | None, series: list[Series]) -> float:
    """Recorded IQ length (s) from the capture's sidecar; the LTE record span without one."""
    for folder in [raw, lte_session]:
        side = folder / "sdr_a.json" if folder else None
        if side and side.exists():
            j = json.loads(side.read_text())
            return float(j["samples"]) / float(j["sample_rate_hz"])
    span = max(int(s.k.max()) for s in series) + 1
    return span * DT


def main() -> None:
    import subprocess

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", help="`pnt frontend lte` output of a static capture with GNSS")
    p.add_argument("--raw", help="the capture's own session folder (for sdr_a.json)")
    p.add_argument("--out", help="folder for summary.md and summary.json")
    p.add_argument("--plot", help="PNG of the pair residuals and S(τ)")
    p.add_argument("--snr-min-db", type=float, default=SNR_MIN_DB, help="SNR cut (dB)")
    a = p.parse_args()
    path = Path(a.session)
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    series = load_lte(path)
    rx, n_fix = receiver_llh(path)
    info = true_ranges(series, rx, CellTable.load())
    del rx  # nothing below needs the position
    capture = _capture_s(path, Path(a.raw) if a.raw else None, series)
    res = analyse(series, info, capture, a.snr_min_db)
    name = session.session_name(path)
    md = markdown(res, name, commit, n_fix)
    print(md)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.md").write_text(md)
        clean = {
            **res,
            "pairs": [{k: v for k, v in q.items() if not k.startswith("_")} for q in res["pairs"]],
            "session": name,
            "commit": commit,
            "gnss_fixes": n_fix,
        }
        (out / "summary.json").write_text(json.dumps(clean, indent=1, default=float) + "\n")
    if a.plot:
        cap = f"{name}, real session, static, GPS truth, analysis at {commit}"
        plot(res, Path(a.plot), cap, all_epochs(series, info, res))


if __name__ == "__main__":
    main()
