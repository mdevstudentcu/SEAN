"""Measured LTE pseudorange error from static real captures, beside the sim's placeholders.

    python analysis/lte_measured_noise.py <session>-lte ... [--raw-root data/sessions] [--out DIR]

Reads derived LTE sessions (`pnt frontend lte` output) recorded by a receiver that did not move,
with no position truth. What such a capture can show, and what it cannot:

- **Can:** the white noise of a 10 Hz record against its SNR; how the error grows with time
  (a structure function) for one cell (dongle clock + tower clock + changing multipath) and for
  the difference of two cells on one carrier, which cancels the dongle; the frequency offset
  between two towers' clocks, and whether sectors of one eNB share one; how a track breaks and
  where it lands when it is found again; the front end's reported σ against each of these.
- **Cannot:** any bias against truth (no position), so the size of multipath, a tower's clock
  offset and the table's tower position error; how multipath changes with motion; anything at
  another site. A static antenna's multipath is a near-constant offset that the arc constant
  absorbs: the slow component measured here bounds how much it *changes* at rest, not its size.

The structure function used throughout is the second difference

    S(τ)² = E[(x(t+τ) − 2 x(t) + x(t−τ))²] / 6

which removes an arc's constant and any constant drift (the dongle's ppm), equals σ² for white
noise of σ at every τ, grows as q τ / 3 for a random walk of q m²/s (white frequency noise), as
q τ³ / 9 for a random-walk frequency of q m²/s³, and as s² (1 − 4/3 e^(−τ/T) + 1/3 e^(−2τ/T))
for a first-order Gauss-Markov error (s, T): the sim's own error terms have closed forms, drawn
beside the measurement. Allan deviation: σ_y(τ) = √3 S(τ) / (c τ).

Only triplets inside one arc are used (an arc carries an unknown constant). Uses only what the
front end wrote from PSS and SSS (broadcast sync signals, REQ-08). Writes text and figures only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import yaml

from pnt.cli import _commit
from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.sim.lte_front_end import Dongle

C = 299_792_458.0
DT = 0.1  # the front end's output period (tracker.Config.output_period_s)
FRAME_M = C * 0.010  # pseudorange ambiguity (meta.ambiguity_m)
REPO = Path(__file__).resolve().parents[1]
SCENARIO = REPO / "src/pnt/sim/scenarios/sets/challenge-drone.yaml"
CELL_TABLE = REPO / "data/reference/lte-cells-ottawa.csv"
TAUS_SHORT = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20]
TAUS_LONG = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]
SNR_EDGES = [-14, -11, -8, -5, -2, 1, 4, 7, 10, 13, 16]
MIN_TRIPLETS = 30  # fewer second differences than this: no S(τ) value
MIN_FIT_S = 5.0  # shortest common arc for a drift fit
# TBC: a re-found track "lands on its old timing" if within this of the extrapolation. About
# three times the strongest cells' 1 s spread plus the drift error over a few-second gap.
LAND_M = 30.0
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#7b4fa0", "#1b9e9e", "#b5442e"]
INK, GRID = "#1f2328", "#d0d7de"


@dataclass
class Cell:
    session: str
    emitter: str
    earfcn: int
    pci: int
    fc: float
    k: np.ndarray  # 10 Hz grid index from the session's first record
    v: np.ndarray  # pseudorange (m)
    sig: np.ndarray  # reported σ (m)
    snr: np.ndarray  # meta.snr_db
    arc: np.ndarray
    cfo: np.ndarray  # Hz
    span_s: float

    @property
    def tracked(self) -> float:
        return self.k.size * DT / self.span_s

    def segments(self) -> np.ndarray:
        """Contiguous runs: same arc, no missing 10 Hz record."""
        brk = (np.diff(self.k) != 1) | (np.diff(self.arc) != 0)
        return np.r_[0, np.cumsum(brk)]


@dataclass
class Sess:
    name: str
    commit_fe: str
    commit_rec: str
    span_s: float
    cells: list[Cell]


def load(path: Path, raw_root: Path | None) -> Sess:
    meta = session.read_meta(path)
    series: dict[str, list[Measurement]] = defaultdict(list)
    for _topic, m in read_session(session.mcap_path(path), topics=["/meas/lte"]):
        if isinstance(m, Measurement) and m.kind == "pseudorange":
            series[m.emitter].append(m)
    if not series:
        raise SystemExit(f"{path}: no /meas/lte pseudoranges")
    t0 = min(m.t_ns for ms in series.values() for m in ms)
    t1 = max(m.t_ns for ms in series.values() for m in ms)
    span = (t1 - t0) / 1e9 + DT
    name = session.session_name(path)
    rec = "TBD"
    if raw_root is not None:
        # `<session>-partial<N>s-lte`: the front end ran on a prefix of the capture
        orig = raw_root / re.sub(r"-partial\d+s$", "", name.removesuffix("-lte"))
        if (orig / session.META_NAME).exists():
            rec = str(session.read_meta(orig).get("commit") or "TBD")
    cells = []
    for emitter, ms in series.items():
        ms.sort(key=lambda m: m.t_ns)
        md = ms[0].meta
        k = np.rint(np.array([m.t_ns - t0 for m in ms], dtype=np.float64) / 1e9 / DT)
        k = k.astype(np.int64)
        keep = np.r_[True, np.diff(k) > 0]  # one record per grid slot
        cells.append(
            Cell(
                session=name,
                emitter=emitter,
                earfcn=int(md.get("earfcn") or 0),
                pci=int(md["pci"]),
                fc=float(md["fc_hz"]),
                k=k[keep],
                v=np.array([m.value[0] for m in ms])[keep],
                sig=np.array([m.sigma[0] for m in ms])[keep],
                snr=np.array([m.meta["snr_db"] for m in ms])[keep],
                arc=np.array([m.meta.get("arc", 0) for m in ms])[keep],
                cfo=np.array([m.meta["cfo_hz"] for m in ms], dtype=float)[keep],
                span_s=span,
            )
        )
    cells.sort(key=lambda c: (c.earfcn, c.pci))
    return Sess(name, str(meta.get("commit") or "TBD"), rec, span, cells)


# --- the statistics ---------------------------------------------------------------------------


def second_diff(k: np.ndarray, v: np.ndarray, label: np.ndarray, m: int):
    """x(k+m) − 2 x(k) + x(k−m) wherever all three exist with one label; and the centre index."""
    if k.size < 3:
        return np.empty(0), np.empty(0, np.int64)
    pos = np.full(int(k.max()) + 1, -1, np.int64)
    pos[k] = np.arange(k.size)
    lo, hi = k - m, k + m
    ok = (lo >= 0) & (hi <= k.max())
    i = np.flatnonzero(ok)
    a, b = pos[lo[i]], pos[hi[i]]
    good = (a >= 0) & (b >= 0)
    i, a, b = i[good], a[good], b[good]
    same = (label[a] == label[i]) & (label[b] == label[i])
    i, a, b = i[same], a[same], b[same]
    return v[b] - 2 * v[i] + v[a], i


def structure(k, v, label, taus) -> list[dict]:
    """S(τ): RMS and robust (MAD) versions, with the triplet count."""
    out = []
    for tau in taus:
        m = max(1, round(tau / DT))
        d, _ = second_diff(k, v, label, m)
        if d.size < MIN_TRIPLETS:
            continue
        rms = math.sqrt(float(np.mean(d**2)) / 6)
        mad = 1.4826 * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(6)
        out.append({"tau_s": m * DT, "S_m": rms, "S_robust_m": mad, "n": int(d.size)})
    return out


def block_means(k, v, label, n=10):
    """1 s means of full 10 Hz blocks inside one label: (block index, mean, label)."""
    b = k // n
    key = b * 100_000 + label
    uk, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    s = np.bincount(inv, weights=v)
    full = cnt == n
    return (uk // 100_000)[full], (s / cnt)[full], (uk % 100_000)[full]


def drift_fit(k, v, label) -> dict | None:
    """Slope (m/s) per common label of ≥ MIN_FIT_S, fitted to 1 s means, combined by weight.
    The standard error comes from the 1 s residuals with an AR(1) widening; error correlated
    over longer than a piece (the dongle's wander, for one cell) is not in it."""
    bk, bv, bl = block_means(k, v, label)
    slopes, ws, spans = [], [], []
    for lab in np.unique(bl):
        sel = bl == lab
        if sel.sum() * 1.0 < MIN_FIT_S:
            continue
        t = bk[sel].astype(float)
        y = bv[sel]
        tc = t - t.mean()
        sxx = float(np.sum(tc**2))
        if sxx <= 0:
            continue
        sl = float(np.sum(tc * (y - y.mean())) / sxx)
        r = y - y.mean() - sl * tc
        # AR(1) correction: residual correlation from one 1 s mean to the next widens the SE
        rho = float(np.corrcoef(r[:-1], r[1:])[0, 1]) if len(r) > 3 else 0.0
        rho = min(max(rho if np.isfinite(rho) else 0.0, 0.0), 0.95)
        se = math.sqrt(float(np.sum(r**2)) / max(len(t) - 2, 1) / sxx * (1 + rho) / (1 - rho))
        slopes.append(sl)
        ws.append(1 / max(se, 1e-6) ** 2)
        spans.append(float(t[-1] - t[0]))
    if not slopes:
        return None
    w = np.array(ws)
    sl = float(np.sum(w * np.array(slopes)) / w.sum())
    return {
        "slope_mps": sl,
        "se_mps": float(1 / math.sqrt(w.sum())),
        "fit_s": sum(spans),
        "pieces": len(slopes),
        "piece_slopes": [round(x, 3) for x in slopes],
    }


def wrap(x: float, a: float = FRAME_M) -> float:
    return (x + a / 2) % a - a / 2


def jumps(c: Cell) -> list[dict]:
    """Where a track lands after each break, against a straight line through the last ≤ 3 s."""
    seg = c.segments()
    out = []
    for s in range(1, int(seg.max()) + 1 if seg.size else 0):
        prev = np.flatnonzero(seg == s - 1)
        nxt = np.flatnonzero(seg == s)
        if prev.size < 5 or nxt.size < 1:
            continue
        tail = prev[c.k[prev] >= c.k[prev[-1]] - 30]
        if tail.size < 5:
            continue
        tt = c.k[tail] * DT
        p = np.polyfit(tt - tt[-1], c.v[tail], 1)
        gap = (c.k[nxt[0]] - c.k[prev[-1]]) * DT
        pred = p[1] + p[0] * gap
        out.append(
            {
                "cell": c.emitter,
                "session": c.session,
                "gap_s": round(gap, 2),
                "same_arc": bool(c.arc[nxt[0]] == c.arc[prev[-1]]),
                "jump_m": wrap(float(c.v[nxt[0]] - pred)),
                "snr_before": float(np.median(c.snr[tail])),
                "snr_after": float(c.snr[nxt[0]]),
            }
        )
    return out


def gaps(c: Cell) -> dict:
    """Breaks in tracking: how long the cell is lost between contiguous runs."""
    seg = c.segments()
    starts = np.flatnonzero(np.diff(seg)) + 1
    g = (c.k[starts] - c.k[starts - 1] - 1) * DT
    g = g[g > 0]
    return {
        "breaks_per_min": round(starts.size / c.span_s * 60, 2),
        "median_gap_s": float(np.median(g)) if g.size else None,
    }


def cfo_vs_ref(c: Cell, cells: list[Cell]) -> dict:
    """This cell's CFO minus the strongest cell's on its carrier, at common epochs. One dongle,
    so the difference is the two towers' carrier offsets (±0.05 ppm allowed, 3GPP TS 36.104)
    plus estimation error; whole multiples of 200 Hz (1 / 5 ms) point to a carrier alias."""
    same = [x for x in cells if x.earfcn == c.earfcn]
    ref = max(same, key=lambda x: (np.median(x.snr), x.k.size))
    if ref is c:
        return {"cfo_ref": "self", "dcfo_hz": None, "dcfo_ppb": None, "dcfo_in_200hz": None}
    _, ia, ib = np.intersect1d(c.k, ref.k, return_indices=True)
    if ia.size < 10:
        return {"cfo_ref": ref.emitter, "dcfo_hz": None, "dcfo_ppb": None, "dcfo_in_200hz": None}
    d = float(np.nanmedian(c.cfo[ia] - ref.cfo[ib]))
    return {
        "cfo_ref": ref.emitter,
        "dcfo_hz": d,
        "dcfo_ppb": d / c.fc * 1e9,
        "dcfo_in_200hz": d / 200.0,
    }


# --- the sim's placeholders, as S(τ) ---------------------------------------------------------


def sim_values(path: Path = SCENARIO) -> dict:
    sc = yaml.safe_load(path.read_text())
    lte = sc["sources"]["lte"]
    tc = sc["tower_clocks"]
    d = Dongle()
    return {
        "scenario": str(path.relative_to(REPO)),
        "rate_hz": lte["rate_hz"],
        "sigma_m": lte["sigma_m"],
        "told_sigma_m": lte["told_sigma_m"],
        "multipath": lte["multipath"],
        "dropout": lte["dropout"],
        "told_position_sigma_m": lte["told_position_sigma_m"],
        "builder": tc["builder"],
        "site": tc["site"],
        "dongle": {
            "drift_ppm": d.drift_ppm,
            "offset_rw_m": d.offset_rw_m,
            "drift_rw_mps": d.drift_rw_mps,
        },
    }


def s_gm(tau, s, T):
    return s**2 * (1 - 4 / 3 * np.exp(-tau / T) + 1 / 3 * np.exp(-2 * tau / T))


def s_clock(tau, q1, q2):
    return q1 * tau / 3 + q2 * tau**3 / 9


def sim_curves(sv: dict, tau: np.ndarray) -> dict:
    """S(τ) of the sim's error terms, for one cell and for a pair on one carrier."""
    mp = sv["multipath"]
    st, bu, dg = sv["site"], sv["builder"], sv["dongle"]
    site = s_clock(tau, st.get("offset_rw_m", 0) ** 2, st.get("drift_rw_mps", 0) ** 2)
    builder = s_clock(tau, bu.get("offset_rw_m", 0) ** 2, bu.get("drift_rw_mps", 0) ** 2)
    dongle = s_clock(tau, dg["offset_rw_m"] ** 2, dg["drift_rw_mps"] ** 2)
    gm = s_gm(tau, mp["sigma_m"], mp["tau_s"])
    white = sv["sigma_m"] ** 2  # at the sim's 1 Hz
    return {
        "white (1 Hz)": np.full_like(tau, math.sqrt(white)),
        "multipath, one cell": np.sqrt(gm),
        "dongle clock": np.sqrt(dongle),
        "one cell, all terms": np.sqrt(white + gm + dongle + site + builder),
        "tower pair, other site, clocks": np.sqrt(2 * site),
        "tower pair, other site, all": np.sqrt(2 * (white + gm + site)),
    }


# --- analysis ---------------------------------------------------------------------------------


def table_enb(cells_csv: Path = CELL_TABLE) -> dict:
    """(EARFCN, PCI) -> eNB when the table has exactly one registered sector for it. Unverified
    against the capture's position (none): an identity by table, `TBC`."""
    import csv

    seen: dict[tuple[int, int], set] = defaultdict(set)
    with open(cells_csv) as f:
        for r in csv.DictReader(f):
            seen[(int(r["earfcn"]), int(r["pci"]))].add(r["enb_id"])
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def analyse(sessions: list[Sess]) -> dict:
    enb = table_enb()
    long_ = [s for s in sessions if s.span_s > 300]
    cells, pairs, jumps_all = [], [], []
    d2_pool = []  # (snr, d2, reported σ)
    for s in sessions:
        taus = TAUS_LONG if s in long_ else TAUS_SHORT
        for c in s.cells:
            seg = c.segments()
            d, i = second_diff(c.k, c.v, seg, 1)
            for snr, dd, sg in zip(c.snr[i], d, c.sig[i], strict=True):
                d2_pool.append((snr, dd, sg))
            row = {
                "session": s.name,
                "cell": c.emitter,
                "enb": enb.get((c.earfcn, c.pci), "TBD"),
                "n": int(c.k.size),
                "tracked": round(c.tracked, 3),
                "arcs": int(np.unique(c.arc).size),
                "segments": int(seg.max() + 1),
                "snr_db": float(np.median(c.snr)),
                "reported_m": float(np.median(c.sig)),
                "cfo_hz": float(np.nanmedian(c.cfo)),
                "white_m": (
                    math.sqrt(float(np.mean(d**2)) / 6) if d.size >= MIN_TRIPLETS else None
                ),
                "white_robust_m": (
                    1.4826 * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(6)
                    if d.size >= MIN_TRIPLETS
                    else None
                ),
                "S_contiguous": structure(c.k, c.v, seg, taus),
                "S_arc": structure(c.k, c.v, c.arc, taus),
            }
            bk, bv, bl = block_means(c.k, c.v, c.arc)
            row["S_arc_1s"] = structure(bk * 10, bv, bl, [t for t in taus if t >= 1])
            fit = drift_fit(c.k, c.v, c.arc)
            if fit:
                fit["cfo_rate_mps"] = float(-C * np.nanmedian(c.cfo) / c.fc)
                fit["code_minus_carrier_ppb"] = (fit["slope_mps"] - fit["cfo_rate_mps"]) / C * 1e9
            row["drift"] = fit
            row.update(cfo_vs_ref(c, s.cells))
            row.update(gaps(c))
            cells.append(row)
            jumps_all += jumps(c)
        for a, b in combinations(s.cells, 2):
            if a.earfcn != b.earfcn:
                continue
            common, ia, ib = np.intersect1d(a.k, b.k, return_indices=True)
            if common.size < 50:
                continue
            dv = b.v[ib] - a.v[ia]
            lab = a.arc[ia] * 1000 + b.arc[ib]
            seg_ab = a.segments()[ia] * 100_000 + b.segments()[ib]
            ea, eb = enb.get((a.earfcn, a.pci)), enb.get((b.earfcn, b.pci))
            same = "TBD" if ea is None or eb is None else ("same eNB" if ea == eb else "other eNB")
            row = {
                "session": s.name,
                "a": a.emitter,
                "b": b.emitter,
                "relation": same,
                "enb_a": ea or "TBD",
                "enb_b": eb or "TBD",
                "n": int(common.size),
                "snr_min_db": float(min(np.median(a.snr[ia]), np.median(b.snr[ib]))),
                "S_contiguous": structure(common, dv, seg_ab, taus),
                "S_arc": structure(common, dv, lab, taus),
            }
            bk, bv, bl = block_means(common, dv, lab)
            row["S_arc_1s"] = structure(bk * 10, bv, bl, [t for t in taus if t >= 1])
            fit = drift_fit(common, dv, lab)
            if fit:
                dcfo = float(np.nanmedian(b.cfo[ib] - a.cfo[ia]))
                fit["cfo_rate_mps"] = -C * dcfo / a.fc
                fit["slope_ppb"] = fit["slope_mps"] / C * 1e9
                fit["cfo_ppb"] = fit["cfo_rate_mps"] / C * 1e9
            row["drift"] = fit
            pairs.append(row)
    snr = np.array([p[0] for p in d2_pool])
    d2 = np.array([p[1] for p in d2_pool])
    rep = np.array([p[2] for p in d2_pool])
    bins = []
    for lo, hi in zip(SNR_EDGES[:-1], SNR_EDGES[1:], strict=True):
        sel = (snr >= lo) & (snr < hi)
        if sel.sum() < MIN_TRIPLETS:
            continue
        d = d2[sel]
        bins.append(
            {
                "snr_lo": lo,
                "snr_hi": hi,
                "n": int(sel.sum()),
                "white_m": math.sqrt(float(np.mean(d**2)) / 6),
                "white_robust_m": 1.4826
                * float(np.median(np.abs(d - np.median(d))))
                / math.sqrt(6),
                "reported_median_m": float(np.median(rep[sel])),
                "snr_median_db": float(np.median(snr[sel])),
            }
        )
    return {
        "cells": cells,
        "pairs": pairs,
        "jumps": jumps_all,
        "snr_bins": bins,
        "fit": fit_white(bins),
    }


def fit_white(bins: list[dict]) -> dict | None:
    """σ² = a² + b² / snr_lin (a floor plus a CRB-like term), least squares in log σ on the robust
    per-bin values, each bin weighted by √n."""
    if len(bins) < 3:
        return None
    from scipy.optimize import least_squares

    x = 10 ** (np.array([b["snr_median_db"] for b in bins]) / 10)
    y = np.array([b["white_robust_m"] for b in bins])
    w = np.sqrt([b["n"] for b in bins])

    def res(p):
        return w * (0.5 * np.log(p[0] ** 2 + p[1] ** 2 / x) - np.log(y))

    r = least_squares(res, x0=[1.0, 5.0], bounds=([0, 0], [1e3, 1e4]))
    return {
        "floor_m": float(r.x[0]),
        "snr_term_m": float(r.x[1]),
        "form": "sigma^2 = floor^2 + snr_term^2 / snr_lin, snr_lin = 10^(snr_db/10)",
    }


# --- output -----------------------------------------------------------------------------------


def _s_at(rows: list[dict], tau: float, key: str = "S_m"):
    for r in rows:
        if abs(r["tau_s"] - tau) < 1e-9:
            return r[key]
    return None


def figures(sessions, res, sv, out: Path, commit: str) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = sorted({s.name for s in sessions})
    part = [n for n in names if "-partial" in n]
    tag = f"{len(names)} real static sessions 2026-11-10 (summary.md)"
    if part:
        tag += f"; {len(part)} of them a PARTIAL capture (prefix only, {', '.join(part)})"
    tag += f"; analysed at {commit}"
    written = []

    def finish(fig, name, what):
        fig.suptitle(f"{what}\n{tag}", fontsize=8.5, x=0.01, ha="left")
        fig.tight_layout()
        p = out / name
        fig.savefig(p)
        plt.close(fig)
        written.append(p)

    # 1. White noise against SNR
    fig, ax = plt.subplots(figsize=(7, 4), dpi=130)
    b = res["snr_bins"]
    xs = [x["snr_median_db"] for x in b]
    ax.semilogy(
        xs,
        [x["white_robust_m"] for x in b],
        "o-",
        color=PALETTE[0],
        label="measured white σ, 10 Hz record (robust, 2nd difference)",
    )
    ax.semilogy(
        xs,
        [x["white_m"] for x in b],
        "o:",
        color=PALETTE[0],
        alpha=0.5,
        label="same, RMS (outliers kept)",
    )
    ax.semilogy(
        xs,
        [x["reported_median_m"] for x in b],
        "s-",
        color=PALETTE[1],
        label="front end's reported σ (median)",
    )
    f = res["fit"]
    if f:
        xx = np.linspace(min(xs), max(xs), 100)
        ax.semilogy(
            xx,
            np.sqrt(f["floor_m"] ** 2 + f["snr_term_m"] ** 2 / 10 ** (xx / 10)),
            "-",
            color=INK,
            lw=0.8,
            label=f"fit: √({f['floor_m']:.2f}² + {f['snr_term_m']:.2f}²/SNR)",
        )
    ax.axhline(
        sv["told_sigma_m"],
        color=PALETTE[4],
        ls="--",
        lw=1,
        label=f"sim told σ {sv['told_sigma_m']:g} m (TBC)",
    )
    ax.set_xlabel("SNR as the front end reports it (meta.snr_db, dB)")
    ax.set_ylabel("σ (m)")
    ax.grid(True, which="both", color=GRID, lw=0.5)
    ax.legend(fontsize=6.5)
    finish(fig, "white_vs_snr.png", "LTE pseudorange white noise against SNR, pooled over cells")

    # 2. Structure functions
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2), dpi=130, sharey=True)
    tau = np.logspace(-1, math.log10(600), 60)
    cur = sim_curves(sv, tau)
    best = [r for r in res["cells"] if r["tracked"] > 0.8 and r["S_arc"]]
    for i, r in enumerate(sorted(best, key=lambda r: -len(r["S_arc"]))[:7]):
        t = [x["tau_s"] for x in r["S_arc"]]
        axs[0].loglog(
            t,
            [x["S_robust_m"] for x in r["S_arc"]],
            "o-",
            ms=3,
            lw=1,
            color=PALETTE[i % 7],
            label=f"{r['cell']} {short(r['session'])}",
        )
    pr = [r for r in res["pairs"] if r["S_arc"] and r["snr_min_db"] > -8]
    for i, r in enumerate(sorted(pr, key=lambda r: -len(r["S_arc"]))[:7]):
        t = [x["tau_s"] for x in r["S_arc"]]
        axs[1].loglog(
            t,
            [x["S_robust_m"] for x in r["S_arc"]],
            "o-",
            ms=3,
            lw=1,
            color=PALETTE[i % 7],
            label=f"{r['b'][4:]}−{r['a'][4:]} ({r['relation']}) {short(r['session'])}",
        )
    for ax, keys in (
        (axs[0], ["one cell, all terms", "dongle clock", "multipath, one cell"]),
        (axs[1], ["tower pair, other site, all", "tower pair, other site, clocks"]),
    ):
        for j, key in enumerate(keys):
            ax.loglog(
                tau, cur[key], ls=["--", ":", "-."][j], color=INK, lw=1, label=f"sim: {key} (TBC)"
            )
        ax.set_xlabel("τ (s)")
        ax.grid(True, which="both", color=GRID, lw=0.5)
        ax.legend(fontsize=5.5, loc="lower right")
    axs[0].set_ylabel("S(τ) (m), robust")
    axs[0].set_title("one cell (dongle not removed)", fontsize=8)
    axs[1].set_title("pair on one carrier (dongle cancels), weaker cell SNR > −8 dB", fontsize=8)
    finish(
        fig,
        "structure.png",
        "LTE pseudorange structure function S(τ) inside one arc, against the sim's error terms",
    )

    # 3. Tower-pair drift
    fig, ax = plt.subplots(figsize=(7, 4), dpi=130)
    rows = [r for r in res["pairs"] if r["drift"]]
    rows.sort(key=lambda r: (r["relation"], r["session"]))
    for i, r in enumerate(rows):
        d = r["drift"]
        col = {"same eNB": PALETTE[2], "other eNB": PALETTE[0]}.get(r["relation"], PALETTE[6])
        ax.errorbar(d["slope_mps"], i, xerr=2 * d["se_mps"], fmt="o", color=col, ms=4)
        ax.plot(d["cfo_rate_mps"], i, "x", color=INK, ms=4)
    ax.set_yticks(
        range(len(rows)),
        [
            f"{r['b'][4:]}−{r['a'][4:]} {short(r['session'])} "
            f"({r['relation']}, {r['snr_min_db']:.0f} dB)"
            for r in rows
        ],
        fontsize=5.5,
    )
    sd = math.sqrt(2) * sv["site"]["drift_mps"]
    ax.axvspan(
        -2 * sd,
        2 * sd,
        color=PALETTE[3],
        alpha=0.2,
        label=f"sim ±2σ, two sites of one builder ({2 * sd:.2f} m/s, TBC)",
    )
    ax.plot([], [], "o", color=PALETTE[2], label="code drift ±2 SE, same eNB (table, TBC)")
    ax.plot([], [], "o", color=PALETTE[0], label="code drift ±2 SE, other eNB")
    ax.plot([], [], "o", color=PALETTE[6], label="code drift ±2 SE, eNB TBD")
    ax.plot([], [], "x", color=INK, label="−c·ΔCFO/fc (what the carriers say)")
    ax.set_xscale("symlog", linthresh=0.1)
    ax.set_xlabel("drift of b − a (m/s; 1 m/s = 3.34 ppb)")
    ax.grid(True, color=GRID, lw=0.5)
    ax.legend(fontsize=6)
    finish(fig, "pair_drift.png", "Tower-to-tower clock drift: pairs of cells on one carrier")

    # 4. Re-acquisition landing
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
    j = res["jumps"]
    if j:
        g = np.array([x["gap_s"] for x in j])
        y = np.abs([x["jump_m"] for x in j])
        same = np.array([x["same_arc"] for x in j])
        ax.loglog(
            g[same],
            np.maximum(y[same], 0.1),
            "o",
            ms=3,
            color=PALETTE[0],
            label="re-found on its old arc",
        )
        ax.loglog(
            g[~same], np.maximum(y[~same], 0.1), "^", ms=3, color=PALETTE[1], label="new arc"
        )
        ax.axhline(LAND_M, color=INK, ls=":", lw=1, label=f"{LAND_M:g} m (TBC)")
        ax.axhline(
            C * 0.005 / 2,
            color=PALETTE[3],
            ls="--",
            lw=1,
            label="uniform over a frame would sit near ±750 km",
        )
    ax.set_xlabel("gap (s)")
    ax.set_ylabel("|landing − extrapolation| (m), wrapped to ±1 frame")
    ax.grid(True, which="both", color=GRID, lw=0.5)
    ax.legend(fontsize=6.5)
    finish(
        fig, "reacquisition.png", "Where a broken track lands, against a line through its last 3 s"
    )
    return written


def short(name: str) -> str:
    """A session's time and spot for a legend; a partial capture says so."""
    s = name.removeprefix("20261110-").removesuffix("-lte")
    m = re.search(r"-partial(\d+)s$", s)
    s = re.sub(r"-partial\d+s$", "", s)[:13]
    return s + (f" PARTIAL {m.group(1)} s" if m else "")


def _f(x, fmt=".2f"):
    return "—" if x is None else format(x, fmt)


def report(sessions, res, sv, commit) -> str:
    L = [
        "# LTE pseudorange error measured on real static captures (#173)",
        "",
        f"`analysis/lte_measured_noise.py` at `{commit}`. Evidence: **real sessions**, static, "
        "one RTL-SDR, no GPS fix (no position truth; NTP, not PPS, time). Precision only.",
        "",
        "| Session | Recorded at | Front end at | Span (s) | Cells |",
        "|---|---|---|---|---|",
    ]
    for s in sessions:
        L.append(
            f"| {s.name} | `{s.commit_rec}` | `{s.commit_fe}` | {s.span_s:.1f} | {len(s.cells)} |"
        )
    for s in sessions:
        if "-partial" in s.name:
            L += [
                "",
                f"**{s.name} is a PARTIAL capture:** the front end ran on the prefix of "
                "the recording that was copied off the Pi, with a sidecar rebuilt from "
                "`meta.yaml` and the other sessions' sidecars (rate and centre frequency). Its "
                "absolute start time is `TBD` and it has no buffer stamps, so dropped samples "
                "were not detected (`TBD`).",
            ]
    L += ["", f"Sim placeholders from `{sv['scenario']}` and `sim/lte_front_end.py` `Dongle`.", ""]
    L += [
        "## White noise against SNR (10 Hz records, pooled)",
        "",
        "| SNR bin (dB) | n | White σ robust (m) | White σ RMS (m) | Reported σ median (m) | "
        "Robust / reported |",
        "|---|---|---|---|---|---|",
    ]
    for b in res["snr_bins"]:
        L.append(
            f"| {b['snr_lo']} to {b['snr_hi']} | {b['n']} | {b['white_robust_m']:.2f} | "
            f"{b['white_m']:.2f} | {b['reported_median_m']:.2f} | "
            f"{b['white_robust_m'] / b['reported_median_m']:.2f} |"
        )
    if res["fit"]:
        f = res["fit"]
        L += ["", f"Fit: σ² = {f['floor_m']:.2f}² + {f['snr_term_m']:.2f}² / SNR_lin (m, 10 Hz)."]
    L += [
        "",
        "## Per cell",
        "",
        "| Session | Cell | eNB (table) | Tracked | Arcs | Segments | SNR (dB) | "
        "Reported σ (m) | White σ robust (m) | S(1 s) | S(10 s) | S(100 s) | "
        "Code drift (m/s) | Code − carrier (ppb) | CFO − strongest (Hz) | in 200 Hz | "
        "Breaks/min | Median gap (s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in res["cells"]:
        d = r["drift"] or {}
        L.append(
            f"| {r['session']} | {r['cell']} | {r['enb']} | {r['tracked']:.0%} | {r['arcs']} | "
            f"{r['segments']} | {r['snr_db']:.1f} | {r['reported_m']:.2f} | "
            f"{_f(r['white_robust_m'])} | {_f(_s_at(r['S_arc'], 1, 'S_robust_m'))} | "
            f"{_f(_s_at(r['S_arc'], 10, 'S_robust_m'))} | "
            f"{_f(_s_at(r['S_arc'], 100, 'S_robust_m'))} | {_f(d.get('slope_mps'))} | "
            f"{_f(d.get('code_minus_carrier_ppb'), '.1f')} | {_f(r['dcfo_hz'], '.0f')} | "
            f"{_f(r['dcfo_in_200hz'], '.2f')} | {r['breaks_per_min']:.1f} | "
            f"{_f(r['median_gap_s'], '.1f')} |"
        )
    L += [
        "",
        "## Pairs on one carrier (dongle cancels)",
        "",
        "| Session | b − a | Relation (table) | n | Weaker SNR (dB) | S(0.1 s) | S(1 s) | "
        "S(10 s) | S(100 s) | Drift (m/s) ± SE | Drift (ppb) | Carriers say (ppb) | Pieces |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in res["pairs"]:
        d = r["drift"] or {}
        L.append(
            f"| {r['session']} | {r['b']} − {r['a']} | {r['relation']} | {r['n']} | "
            f"{r['snr_min_db']:.1f} | {_f(_s_at(r['S_arc'], 0.1, 'S_robust_m'))} | "
            f"{_f(_s_at(r['S_arc'], 1, 'S_robust_m'))} | "
            f"{_f(_s_at(r['S_arc'], 10, 'S_robust_m'))} | "
            f"{_f(_s_at(r['S_arc'], 100, 'S_robust_m'))} | "
            f"{_f(d.get('slope_mps'), '.3f')} ± {_f(d.get('se_mps'), '.3f')} | "
            f"{_f(d.get('slope_ppb'), '.2f')} | {_f(d.get('cfo_ppb'), '.1f')} | "
            f"{d.get('pieces', '—')} |"
        )
    j = res["jumps"]
    if j:
        y = np.abs([x["jump_m"] for x in j])
        same = np.array([x["same_arc"] for x in j])
        L += ["", "## Track breaks", ""]
        strong = np.array([min(x["snr_before"], x["snr_after"]) >= 0 for x in j])
        for lab, sel in (
            ("re-found on its old arc", same),
            ("new arc", ~same),
            ("re-found on its old arc, SNR ≥ 0 dB both sides", same & strong),
            ("new arc, SNR ≥ 0 dB both sides", ~same & strong),
        ):
            if sel.sum():
                L.append(
                    f"- {lab}: {int(sel.sum())} breaks, landing within {LAND_M:g} m of the "
                    f"extrapolation in {np.mean(y[sel] < LAND_M):.0%}; median "
                    f"|jump| {np.median(y[sel]):.0f} m, 90th percentile "
                    f"{np.percentile(y[sel], 90):.0f} m"
                )
    long_rows = [r for r in res["cells"] if any(x["tau_s"] >= 100 for x in r["S_arc"])]
    if long_rows:
        L += [
            "",
            "## Allan deviation of one cell's timing (dongle + tower), long sessions",
            "",
            "σ_y(τ) = √3 S(τ) / (c τ) from the robust S(τ) inside one arc; the sim's dongle "
            "(`Dongle`) beside it.",
            "",
            "| Session | Cell | " + " | ".join(f"τ {t:g} s" for t in TAUS_LONG) + " |",
            "|---|---|" + "---|" * len(TAUS_LONG),
        ]
        for r in long_rows:
            vals = []
            for t in TAUS_LONG:
                v = _s_at(r["S_arc"], t, "S_robust_m")
                vals.append("—" if v is None else f"{math.sqrt(3) * v / (C * t):.1e}")
            L.append(f"| {r['session']} | {r['cell']} | " + " | ".join(vals) + " |")
        dg = sv["dongle"]
        sim = [
            math.sqrt(3 * s_clock(t, dg["offset_rw_m"] ** 2, dg["drift_rw_mps"] ** 2)) / (C * t)
            for t in TAUS_LONG
        ]
        L.append("| sim | dongle clock (TBC) | " + " | ".join(f"{v:.1e}" for v in sim) + " |")
    L += [
        "",
        "S(τ): robust second-difference structure function inside one arc (m). "
        "Every value `TBC` until a capture with truth; see the module docstring for what a "
        "static capture cannot show.",
    ]
    return "\n".join(L) + "\n"


def _jsonable(res: dict) -> dict:
    return json.loads(json.dumps(res, default=lambda o: o.tolist() if hasattr(o, "tolist") else o))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sessions", nargs="+", type=Path, help="<session>-lte folders")
    ap.add_argument(
        "--raw-root",
        type=Path,
        default=REPO / "data/sessions",
        help="where the original sessions are, for their recording commit",
    )
    ap.add_argument("--out", type=Path, default=REPO / "analysis/results/lte-measured-noise")
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args(argv)
    sessions = [load(p, a.raw_root) for p in a.sessions]
    commit = _commit()
    sv = sim_values()
    res = analyse(sessions)
    a.out.mkdir(parents=True, exist_ok=True)
    text = report(sessions, res, sv, commit)
    (a.out / "summary.md").write_text(text)
    meta = {
        "commit": commit,
        "sim": sv,
        "sessions": [
            {
                "name": s.name,
                "recorded_at": s.commit_rec,
                "front_end_at": s.commit_fe,
                "span_s": s.span_s,
            }
            for s in sessions
        ],
    }
    (a.out / "summary.json").write_text(json.dumps({**meta, **_jsonable(res)}, indent=1))
    if not a.no_figures:
        figures(sessions, res, sv, a.out, commit)
    print(text)


if __name__ == "__main__":
    main()
