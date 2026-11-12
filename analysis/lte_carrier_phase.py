"""LTE carrier phase on static captures: discipline the dongle from the cells' common drift and
measure what is left (#277). Analysis only; the front end and the estimators are unchanged.

    # 1. front end on a capture in chunks, with each epoch's SSS carrier phase kept (local npz)
    python analysis/lte_carrier_phase.py run <session>/sdr_a.cu8 <out>.npz [--chunk-s 600]
    # 2. the numbers, the figure and summary.json from one or more npz files
    python analysis/lte_carrier_phase.py report <out>.npz ... [--out DIR]

Idea (implemented from the description of Calvo-Palomino et al., "LTESS-track", ACM WiNTECH
2017, DOI 10.1145/3131473.3131481; none of its code is used): the dongle's tuner LO and ADC run
from one crystal, and every tower's carrier is within tens of ppb of nominal, so the carrier
offset that all cells on one carrier share is the dongle's frequency error. Here it is taken
from the carrier phase, not only the sync timing:

1. **Phase per epoch.** At each 5 ms epoch the tracker accepted, the SSS correlation (the
   cell's own sequence; the PSS is shared by every cell on its root) is summed over its 62
   subcarriers. Its angle plus the derotation the tracker applied is the carrier phase at the
   SSS window's centre, in the dongle's (gap-corrected) sample time. Symmetric subcarriers make
   it insensitive to a small timing error.
2. **Two streams, no alias.** Epochs are 5 ms apart, so the phase fixes the frequency only
   modulo 200 Hz, and modulo 100 Hz when subframes 0 and 5 reach us with different phases
   (ADR-0036 amendment, 5). They do: another cell's SSS leaks into ours through a cross-
   correlation that differs between the two subframes (synthetic IQ: one tower gives the
   phase bound, a second one 3 dB down triples the joined series' 5 ms noise and leaves each
   subframe at the bound). So each subframe is its own 10 ms stream, unambiguous to ±50 Hz,
   unwrapped by an α-β loop seeded from the code rate over the run's first `INIT_S` (the
   boundary drift: the same crystal, good to a few Hz). The subframe-5 minus subframe-0 offset
   δ is kept as a diagnostic only.
3. **Continuity.** A run of phase ends at a new code arc, a dropped-sample gap, more than
   `MAX_MISS` missing epochs, or a cycle slip (a step of more than π, after a local slope,
   between `SLIP_W` samples either side).
4. **Common mode.** Per 1 s window each cell's carrier frequency is fitted; the weighted mean
   over cells is the dongle (plus the towers' mean offset, which no static capture can split
   off); a cell minus the mean of the others is its tower's frequency against the rest. Phase
   noise beyond one sample is measured on the single difference with the chunk's reference
   cell (most epochs × SNR), which cancels the dongle exactly.

Statistics: S(τ) is the second-difference structure function of `lte_measured_noise.py`
(S² = E[(x(t+τ) − 2x(t) + x(t−τ))²] / 6: σ for white noise, linear drift removed), robust (MAD)
version. Code phase is measured the same way on the same epochs, so the two compare directly.

Privacy: the sessions are static captures at a private address. Only noise, frequencies, slips,
SNR and operator names leave this script: no position, range, timing offset or bearing.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

C = 299_792_458.0
REPO = Path(__file__).resolve().parents[1]
CELL_TABLE = REPO / "data/reference/lte-cells-ottawa.csv"
EPOCH_S = 5e-3  # half-frame
REC = 20  # epochs per 10 Hz record (each stream has 10 of them)
N_SSS = 62
# TBC (regression guards picked on synthetic captures and these, not requirements):
MAX_MISS = 10  # missing epochs (50 ms) a run may bridge
SLIP_W = 10  # stream samples (0.1 s) in each of the four windows of the slip test
SLIP_RAD = math.pi  # a step larger than this is a cycle slip
FREQ_SLIP_HZ = 30.0  # a jump in the 0.1 s frequency larger than this is a frequency slip
ALPHA, BETA = 0.5, 0.1  # the unwrap loop's phase and frequency gains per 10 ms sample
INIT_S = 2.0  # the code rate over a run's first INIT_S seeds the unwrap loop
MIN_REC = 5  # stream samples (of 10) a 10 Hz carrier record needs
# Epochs (of 20) a 10 Hz code record needs: the code is detrended by the chunk's mean rate only,
# and the dongle drifts up to tens of m/s from it, so a record missing epochs is off-centre.
MIN_CODE_REC = 18
MIN_TRIPLETS = 30
FREQ_WIN_S = 1.0  # carrier frequency windows (dongle, towers)
CMP_WIN_S = 10.0  # windows for carrier against code frequency
MIN_WIN = 25  # stream samples a frequency window needs
TAUS = [0.1, 1.0, 10.0, 100.0]
SNR_EDGES = [-14, -11, -8, -5, -2, 1, 4, 7, 10, 13, 16]
# ADR-0036's code white σ at 10 Hz, SNR >= -8 dB (TBC there): σ² = A² + B² / SNR_lin
ADR36_A, ADR36_B = 0.74, 2.32


# --- maths (tested on synthetic IQ and series: tests/test_lte_carrier_phase.py) ---------------


def wrap(x):
    """Angle(s) to [-π, π)."""
    return (np.asarray(x) + np.pi) % (2 * np.pi) - np.pi


def cycles(f_hz: float, n, fs: float) -> np.ndarray:
    """2π · frac(f n / fs): the phase of frequency f at sample n, exact for large n."""
    x = np.asarray(n, np.float64) * (f_hz / fs)
    return 2 * np.pi * (x - np.floor(x))


def code_rate(k: np.ndarray, theta: np.ndarray, arc: np.ndarray, L: int) -> float | None:
    """Dimensionless clock rate ν from the boundary offset `theta` (samples) against k·L inside
    each arc (one intercept per arc), with one 5-MAD clip. The carrier offset is −ν fc."""
    x = k.astype(np.float64) * L
    keep = np.ones(k.size, bool)
    nu = None
    for _ in range(2):
        r = np.full(k.size, np.nan)
        xs, ys, idx = [], [], []
        for a in np.unique(arc[keep]):
            m = np.flatnonzero(keep & (arc == a))
            if m.size < 20:
                continue
            xs.append(x[m] - x[m].mean())
            ys.append(theta[m] - theta[m].mean())
            idx.append(m)
        if not xs:
            return nu
        xc, yc = np.concatenate(xs), np.concatenate(ys)
        sxx = float(np.sum(xc**2))
        if sxx <= 0:
            return nu
        nu = float(np.sum(xc * yc) / sxx)
        r[np.concatenate(idx)] = yc - nu * xc
        mad = 1.4826 * np.nanmedian(np.abs(r - np.nanmedian(r)))
        keep = keep & np.isfinite(r) & (np.abs(r) <= 5 * max(mad, 1e-6))
    return nu


def runs(e: np.ndarray, arc: np.ndarray, breaks: np.ndarray, max_miss: int = MAX_MISS):
    """Run label per epoch (sorted by e): a new run at a new arc, more than `max_miss` missing
    epochs, or where `breaks` is set (the first epoch after a dropped-sample gap)."""
    new = np.r_[True, (np.diff(arc) != 0) | (np.diff(e) > max_miss + 1)] | breaks
    return np.cumsum(new) - 1


def track_unwrap(
    t: np.ndarray, phi: np.ndarray, f_init: float, alpha: float = ALPHA, beta: float = BETA
) -> tuple[np.ndarray, np.ndarray]:
    """Unwrap one phase series (rad, wrapped) at times `t` (s) with an α-β (second-order) loop:
    each sample goes on the cycle nearest the loop's prediction. The loop starts at `f_init`
    (Hz), which must be within half the sample rate of the truth (±50 Hz at 10 ms); after that
    it follows the dongle's drift. Returns the unwrapped phase and the loop's frequency (Hz)."""
    n = t.size
    u, fr = np.empty(n), np.empty(n)
    if n == 0:
        return u, fr
    tl, pl = t.tolist(), phi.tolist()
    ph, f = pl[0], float(f_init)
    u[0], fr[0] = ph, f
    two_pi = 2 * math.pi
    for i in range(1, n):
        dt = tl[i] - tl[i - 1]
        pred = ph + two_pi * f * dt
        r = (pl[i] - pred + math.pi) % two_pi - math.pi
        u[i] = pred + r
        ph = pred + alpha * r
        f += beta * r / (two_pi * dt)
        fr[i] = f
    return u, fr


def slips(u: np.ndarray, label: np.ndarray, w: int = SLIP_W, thr: float = SLIP_RAD):
    """Cycle slips: positions i (a new run starts at i) where the phase steps by more than
    `thr`. Step at i = (after − before) − ½((before − before₂) + (after₂ − after)), the four
    windows of `w` samples each (a local slope removed). Returns (positions, steps in cycles)."""
    pos, size = [], []
    for lab in np.unique(label):
        m = np.flatnonzero(label == lab)
        if m.size < 4 * w:
            continue
        cs = np.r_[0.0, np.cumsum(u[m])]
        i = np.arange(2 * w, m.size - 2 * w + 1)
        # means of the run's samples j .. j + w - 1, for j = i - 2w, i - w, i, i + w
        bb, b, a, aa = ((cs[j + w] - cs[j]) / w for j in (i - 2 * w, i - w, i, i + w))
        step = (a - b) - 0.5 * ((b - bb) + (aa - a))
        hit = np.abs(step) > thr
        if not hit.any():
            continue
        edges = np.flatnonzero(np.diff(np.r_[0, hit.astype(np.int8), 0]))
        peaks = [s0 + int(np.argmax(np.abs(step[s0:s1])))
                 for s0, s1 in zip(edges[::2], edges[1::2], strict=True)]  # fmt: skip
        # a step of S also reads S/2 at ±w: keep only the largest within 2w
        kept: list[int] = []
        for j in sorted(peaks, key=lambda j: -abs(step[j])):
            if all(abs(j - q) > 2 * w for q in kept):
                kept.append(j)
        for j in kept:
            pos.append(int(m[i[j]]))
            size.append(float(step[j] / (2 * np.pi)))
    order = np.argsort(pos)
    return np.array(pos, np.int64)[order], np.array(size)[order]


def freq_slips(t: np.ndarray, u: np.ndarray, w: int = SLIP_W, thr: float = FREQ_SLIP_HZ):
    """Frequency slips: the loop moved onto another alias (100 Hz on a 10 ms stream) and kept
    tracking there, so the phase has no step, only a kink. Positions i where the frequency over
    the `w` samples after i differs from that over the `w` before by more than `thr` Hz; the
    largest within 2w of each other only."""
    n = u.size
    if n < 2 * w + 1:
        return np.empty(0, np.int64)
    i = np.arange(w, n - w)
    after = (u[i + w] - u[i]) / (2 * np.pi * (t[i + w] - t[i]))
    before = (u[i] - u[i - w]) / (2 * np.pi * (t[i] - t[i - w]))
    jump = np.abs(after - before)
    kept: list[int] = []
    for j in np.argsort(-jump):
        if jump[j] <= thr:
            break
        if all(abs(int(i[j]) - q) > 2 * w for q in kept):
            kept.append(int(i[j]))
    return np.array(sorted(kept), np.int64)


def detrend(t: np.ndarray, u: np.ndarray, fr: np.ndarray, n: int = 101) -> np.ndarray:
    """u minus the phase of the loop's frequency smoothed by a running median of `n` samples
    (1 s): what is left is smooth, so a slip shows as a step whatever the sample spacing."""
    from scipy.ndimage import median_filter

    f_s = median_filter(fr, size=min(n, fr.size), mode="nearest")
    model = np.r_[0.0, np.cumsum(2 * np.pi * f_s[:-1] * np.diff(t))]
    return u - model


def stream(e, t, phi, lab0, f_init: np.ndarray) -> dict:
    """One subframe's 10 ms stream of a cell: split the cell's runs (`lab0`) where this stream
    alone misses more than MAX_MISS epochs, unwrap each (seeded by `f_init` at its first
    sample, Hz), split again at slips. Returns u (rad), lab (sub-run per sample), slips."""
    lab0 = np.cumsum(np.r_[True, (np.diff(lab0) != 0) | (np.diff(e) > MAX_MISS + 2)]) - 1
    u = np.empty(e.size)
    lab = np.zeros(e.size, np.int64)
    n_lab = n_slip = 0
    cuts = np.r_[0, np.flatnonzero(np.diff(lab0)) + 1, e.size]
    for s0, s1 in zip(cuts[:-1], cuts[1:], strict=True):
        if s1 <= s0:
            continue
        tt = t[s0:s1]
        uu, fr = track_unwrap(tt, phi[s0:s1], float(f_init[s0]))
        pos, _ = slips(detrend(tt, uu, fr), np.zeros(uu.size, np.int64))
        both = np.union1d(pos, freq_slips(tt, uu))
        pos = [int(x) for x in both[np.r_[True, np.diff(both) > 2 * SLIP_W]]] if both.size else []
        sub = np.zeros(uu.size, np.int64)
        for p in pos:
            sub[p:] += 1
        u[s0:s1] = uu
        lab[s0:s1] = n_lab + sub
        n_lab += int(sub.max()) + 1
        n_slip += len(pos)
    return {"u": u, "lab": lab, "slips": n_slip}


def subframe_offset(s0: dict, s1: dict) -> np.ndarray:
    """δ samples: each subframe-5 phase minus the mean of its two subframe-0 neighbours, where
    both neighbours exist in one sub-run. Returns (e of the subframe-5 sample, δ unwrapped)."""
    pos = {int(x): i for i, x in enumerate(s0["e"])}
    out_e, out_d = [], []
    for j, ej in enumerate(s1["e"].tolist()):
        a, b = pos.get(ej - 1), pos.get(ej + 1)
        if a is None or b is None or s0["lab"][a] != s0["lab"][b]:
            continue
        out_e.append(ej)
        out_d.append(s1["u"][j] - 0.5 * (s0["u"][a] + s0["u"][b]))
    return np.array(out_e, np.int64), np.array(out_d)


def second_diff(q: np.ndarray, v: np.ndarray, label: np.ndarray, lag: int):
    """v(q+lag) − 2v(q) + v(q−lag) wherever all three exist in one label; and centre positions."""
    if q.size < 3:
        return np.empty(0), np.empty(0, np.int64)
    q0 = int(q.min())
    pos = np.full(int(q.max()) - q0 + 1, -1, np.int64)
    pos[q - q0] = np.arange(q.size)
    lo, hi = q - lag - q0, q + lag - q0
    i = np.flatnonzero((lo >= 0) & (hi < pos.size))
    a, b = pos[lo[i]], pos[hi[i]]
    ok = (a >= 0) & (b >= 0)
    i, a, b = i[ok], a[ok], b[ok]
    ok = (label[a] == label[i]) & (label[b] == label[i])
    i, a, b = i[ok], a[ok], b[ok]
    return v[b] - 2 * v[i] + v[a], i


def robust_s(d: np.ndarray) -> float:
    """S from second differences: 1.4826 MAD / √6 (σ for white noise)."""
    if d.size < MIN_TRIPLETS:
        return float("nan")
    return 1.4826 * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(6)


def records(e: np.ndarray, v: np.ndarray, label: np.ndarray, snr: np.ndarray, min_n: int):
    """10 Hz records: means of v over e // REC inside one label, ≥ `min_n` samples each.
    Returns (record index, mean v, label, mean SNR linear)."""
    q = e // REC
    big = int(label.max()) + 1 if label.size else 1
    key = q.astype(np.int64) * big + label
    uk, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    mv = np.bincount(inv, weights=v) / cnt
    ms = np.bincount(inv, weights=snr) / cnt
    ok = cnt >= min_n
    return (uk // big)[ok], mv[ok], (uk % big)[ok], ms[ok]


def window_freq(t, u, label, win_s=FREQ_WIN_S, min_n=MIN_WIN):
    """Frequency (Hz) of phase u (rad) in windows of `win_s`: one slope, one intercept per
    label inside the window. Returns (window index, Hz, samples used)."""
    w = np.floor(t / win_s).astype(np.int64)
    out_w, out_f, out_n = [], [], []
    for wi in np.unique(w):
        m = w == wi
        if m.sum() < min_n:
            continue
        tm, um, lm = t[m], u[m], label[m]
        xs, ys = [], []
        for lab in np.unique(lm):
            s = lm == lab
            if s.sum() < 5:
                continue
            xs.append(tm[s] - tm[s].mean())
            ys.append(um[s] - um[s].mean())
        if not xs:
            continue
        xc, yc = np.concatenate(xs), np.concatenate(ys)
        sxx = float(np.sum(xc**2))
        if xc.size < min_n or sxx < (0.25 * win_s) ** 2 / 12 * xc.size:
            continue
        out_w.append(int(wi))
        out_f.append(float(np.sum(xc * yc) / sxx / (2 * np.pi)))
        out_n.append(int(xc.size))
    return np.array(out_w, np.int64), np.array(out_f), np.array(out_n)


def allan(y: np.ndarray, ms=(1, 10, 100, 1000)) -> dict:
    """Non-overlapping Allan deviation of a 1 s fractional-frequency series with NaN holes:
    σ_y(m s) from consecutive m-averages that are both complete."""
    out = {}
    for m in ms:
        n = y.size // m
        if n < 3:
            continue
        a = y[: n * m].reshape(n, m)
        full = np.isfinite(a).all(axis=1)
        av = np.full(n, np.nan)
        av[full] = a[full].mean(axis=1)
        d = np.diff(av)
        d = d[np.isfinite(d)]
        if d.size >= 2:
            out[str(m)] = {"adev": float(math.sqrt(0.5 * np.mean(d**2))), "n": int(d.size)}
    return out


# --- collection: the front end with each epoch's phase kept ----------------------------------


def _sub_capture(cap, a: int, b: int):
    """Samples [a, b) of a one-segment capture as a capture of their own."""
    from pnt.frontends.lte.capture import Capture, Segment

    seg = cap.segments[0]
    buf = None
    if cap.buffers is not None:
        sel = (cap.buffers[:, 0] >= a) & (cap.buffers[:, 0] < b)
        buf = cap.buffers[sel].copy()
        buf[:, 0] -= a
    return Capture(
        path=cap.path,
        raw=cap.raw[2 * a : 2 * b],
        fs=cap.fs,
        t0_ns=cap.t0_ns + round(a * 1e9 / cap.fs),
        dongle=cap.dongle,
        segments=[Segment(0, b - a, seg.center_freq_hz, seg.earfcn)],
        gaps=[(g - a, n) for g, n in cap.gaps if a <= g < b],
        buffers=buf,
        gain_db=cap.gain_db,
    )


def collect(path: Path, chunk_s: float = 600.0, cfg=None, limit_s: float | None = None) -> dict:
    """Run the front end over a capture in chunks and keep, per accepted epoch of every cell,
    what this analysis needs. Returns column arrays (one row per epoch) and per-chunk meta."""
    from pnt.frontends.lte import frontend, tracker
    from pnt.frontends.lte import signals as sig
    from pnt.frontends.lte.capture import open_capture

    cap = open_capture(path)
    if len(cap.segments) != 1:
        raise SystemExit(f"{path}: {len(cap.segments)} segments; one carrier per capture only")
    log: list = []

    class PhaseTrack(tracker._Track):
        def measure(self, n_id1, n_id2, bounds, ks, f_hz, w=None):
            out = super().measure(n_id1, n_id2, bounds, ks, f_hz, w)
            _, noise, zp, zs = out
            s, p = zs.sum(axis=1), zp.sum(axis=1)
            mid = -self.backoff + self.n_u / 2
            ph_s = np.angle(s) + cycles(f_hz, bounds + self.sss_off + mid, self.fs)
            ph_p = np.angle(p) + cycles(f_hz, bounds + self.pss_off + mid, self.fs)
            log.append((sig.pci(n_id1, n_id2), np.rint(bounds).astype(np.int64),
                        wrap(ph_s), wrap(ph_p), np.abs(s), np.abs(p), noise))  # fmt: skip
            return out

    fs = cap.fs
    L = sig.half_frame_length(fs)
    _, _, _, n_u, backoff = tracker._offsets(fs)
    sss_off, pss_off = tracker._offsets(fs)[:2]
    ref_off = 0.5 * (sss_off + pss_off) + n_u / 2
    sss_mid = sss_off - backoff + n_u / 2
    n_tot = cap.n_samples if limit_s is None else min(cap.n_samples, round(limit_s * fs))
    step = round(chunk_s * fs)
    cols = defaultdict(list)
    chunks = []
    orig = frontend._Track
    frontend._Track = PhaseTrack
    try:
        for ci, a in enumerate(range(0, n_tot, step)):
            b = min(n_tot, a + step)
            if (b - a) / fs < 2.0:
                break
            sub = _sub_capture(cap, a, b)
            log.clear()
            r = frontend.process_capture(sub, cfg)
            gap_ends = sorted(float(x) for x in r_gap_ends(r))
            chunks.append({"chunk": ci, "start_s": a / fs, "dur_s": (b - a) / fs,
                           "gaps": len(r.gaps), "elapsed_s": r.elapsed_s})  # fmt: skip
            by_pci: dict[int, list] = defaultdict(list)
            for row in log:
                by_pci[row[0]].append(row)
            for cell in r.cells:
                if len(cell.epochs) < 200 or cell.pci not in by_pci:
                    continue
                rows = by_pci[cell.pci]
                kb = np.concatenate([x[1] for x in rows])
                # the last measurement of a boundary wins (a re-measured block)
                order = np.argsort(kb, kind="stable")
                kb_s = kb[order]
                last = np.r_[kb_s[1:] != kb_s[:-1], True]
                kb_u, src = kb_s[last], order[last]
                vals = [np.concatenate([x[j] for x in rows])[src] for j in range(2, 7)]
                ep = cell.epochs
                bound = np.array([x.n_ref for x in ep]) - ref_off
                kb_e = np.rint(bound).astype(np.int64)
                pos = np.searchsorted(kb_u, kb_e)
                pos = np.minimum(pos, kb_u.size - 1)
                hit = kb_u[pos] == kb_e
                if hit.sum() < 200:
                    continue
                n0 = np.array([x.n0 for x in ep])
                kk = np.array([x.k for x in ep], np.int64)
                after_gap = np.zeros(len(ep), bool)
                if gap_ends:
                    # the first epoch after each gap's end starts a new run
                    ob = np.argsort(bound)
                    gi = np.searchsorted(bound[ob], np.array(gap_ends))
                    after_gap[ob[gi[gi < len(ep)]]] = True
                sel = np.flatnonzero(hit)
                c = cols
                c["chunk"].append(np.full(sel.size, ci, np.int32))
                c["pci"].append(np.full(sel.size, cell.pci, np.int32))
                c["bound"].append(bound[sel])
                c["n_sss"].append(bound[sel] + sss_mid)
                c["k"].append(kk[sel])
                c["parity"].append((kk[sel] % 2).astype(np.int8))
                c["arc"].append(np.array([x.arc for x in ep], np.int32)[sel])
                c["theta"].append(np.array([x.theta_meas for x in ep])[sel])
                c["nu"].append(np.array([x.nu for x in ep])[sel])
                c["snr"].append(np.array([x.snr_post / x.n_sync for x in ep], np.float32)[sel])
                c["after_gap"].append(after_gap[sel])
                c["n0"].append(n0[sel])
                for name, v in zip(("phi_s", "phi_p", "amp_s", "amp_p", "noise"), vals,
                                   strict=True):  # fmt: skip
                    c[name].append(v[pos[sel]])
            print(f"chunk {ci}: {(b - a) / fs:.0f} s, {len(r.cells)} cells, "
                  f"{len(r.gaps)} gaps, {r.elapsed_s:.0f} s", flush=True)  # fmt: skip
    finally:
        frontend._Track = orig
    seg = cap.segments[0]
    out = {k: np.concatenate(v) for k, v in cols.items()}
    meta = {"capture": path.parent.name, "fs": fs, "L": L, "fc": seg.center_freq_hz,
            "earfcn": seg.earfcn, "dongle": cap.dongle, "chunk_s": chunk_s,
            "capture_s": cap.n_samples / fs, "chunks": chunks}  # fmt: skip
    return {"meta": meta, **out}


def r_gap_ends(r) -> list[float]:
    """Corrected index just after each gap the front end used (sized or not)."""
    from pnt.frontends.lte.tracker import GapMap

    return list(GapMap(list(r.gaps)).corrected_ends())


def save(data: dict, out: Path) -> None:
    arrays = {k: v for k, v in data.items() if k != "meta"}
    np.savez_compressed(out, meta=json.dumps(data["meta"]), **arrays)


def load(path: Path) -> dict:
    z = np.load(path, allow_pickle=False)
    d = {k: z[k] for k in z.files if k != "meta"}
    d["meta"] = json.loads(str(z["meta"]))
    return d


# --- analysis -------------------------------------------------------------------------------


def analyse_cell(d: dict, sel: np.ndarray, fs: float, L: int, fc: float, seed=None):
    """One cell in one chunk: code rate and the two subframe streams, unwrapped and split at
    slips. Each run's loop is seeded by `seed(t)` (Hz, NaN where unknown: the cells' common
    frequency on the second pass) or else by the code rate. The 100 Hz alias is chosen
    later, across cells (`align_aliases`). None if the cell has too little."""
    order = sel[np.argsort(d["bound"][sel])]
    k, arc, theta = d["k"][order], d["arc"][order], d["theta"][order]
    nu = code_rate(k, theta, arc, L)
    if nu is None:
        return None
    e = np.rint(d["bound"][order] / L).astype(np.int64)
    t = d["n_sss"][order] / fs
    after_gap = d["after_gap"][order]
    lab0 = runs(e, arc, after_gap)
    phi = d["phi_s"][order].astype(np.float64)
    par = d["parity"][order].astype(np.int64)
    snr = d["snr"][order].astype(np.float64)
    lam = C / fc
    # seed per run: the code rate over the run's first INIT_S, else the chunk's
    f_init = np.empty(e.size)
    cuts = np.r_[0, np.flatnonzero(np.diff(lab0)) + 1, e.size]
    for s0, s1 in zip(cuts[:-1], cuts[1:], strict=True):
        first = np.arange(s0, s1)[(t[s0:s1] - t[s0]) <= INIT_S]
        nu_loc = code_rate(k[first], theta[first], arc[first], L) if first.size >= 100 else None
        f_init[s0:s1] = -(nu_loc if nu_loc is not None else nu) * fc
        if seed is not None and math.isfinite(f := seed(float(t[s0]))):
            f_init[s0:s1] = f
    streams = []
    for p in (0, 1):
        m = par == p
        if m.sum() < 4 * SLIP_W:
            continue
        st = stream(e[m], t[m], phi[m], lab0[m], f_init[m])
        st.update(p=p, e=e[m], t=t[m], snr=snr[m], code_raw_m=theta[m] * C / fs)
        streams.append(st)
    if not streams:
        return None
    a0 = float(np.median(d["amp_s"][order][par == 0])) if (par == 0).any() else float("nan")
    a1 = float(np.median(d["amp_s"][order][par == 1])) if (par == 1).any() else float("nan")
    new_arc = np.r_[False, np.diff(arc) != 0]
    new_miss = np.r_[False, np.diff(e) > MAX_MISS + 1] & ~new_arc
    new_gap = after_gap & ~new_arc & ~new_miss
    return {
        "e": e, "t": t, "arc": arc, "snr": snr, "theta": theta, "nu_trk": d["nu"][order],
        "code_m": (theta - nu * k * L) * C / fs, "streams": streams, "lam": lam, "fc": fc,
        "fs": fs, "f_code": -nu * fc,
        "breaks": {"arc": int(new_arc.sum()), "miss": int(new_miss.sum()),
                   "gap": int(new_gap.sum()),
                   "slip": int(sum(st["slips"] for st in streams))},
        "amp_ratio_db": 20 * math.log10(a1 / a0) if a0 > 0 and a1 > 0 else float("nan"),
        "tracked_s": e.size * EPOCH_S,
    }  # fmt: skip


ALIAS_HZ = 100.0  # a 10 ms stream cannot tell frequencies this far apart
MIN_UNIT = 40  # stream samples (0.4 s) a sub-run needs to be kept, TBC
SEED_CLUSTER_HZ = 10.0  # cells this close in one 1 s window vote together, TBC
# A sub-run whose own 10 ms white phase noise exceeds both of these is incoherent, TBC: real
# sub-runs read 1 to 1.3 times the SSS bound (at most 0.45 rad, at -14 dB); a mis-tracked
# one 3 to 7 rad.
INCOHERENT_RAD, INCOHERENT_X = 0.6, 3.0


def _slope(t: np.ndarray, y: np.ndarray) -> float:
    tc = t - t.mean()
    return float(np.sum(tc * (y - y.mean())) / max(float(np.sum(tc**2)), 1e-12))


def align_aliases(cells: dict, seed=None) -> dict:
    """Put every sub-run of every stream on the right 100 Hz alias, greedily by confidence
    (duration × SNR): a sub-run that overlaps sub-runs already placed takes their frequency's
    alias (the towers differ by far less than 50 Hz, so the dongle sets them all); one that
    overlaps none takes the alias its own code says (the slope of code + carrier, in m, which
    is the alias error times 100 λ). With `seed` (the cells' common frequency from a first
    pass), a sub-run takes the alias of the seed over its span instead. Sub-runs shorter than
    MIN_UNIT samples, and incoherent ones (`INCOHERENT_*`), are dropped. Returns counts:
    sub-runs placed by the seed, by others, by code, where the code's alias disagreed with the
    one taken, and the stream seconds dropped as incoherent."""
    units = []
    counts = {"by_seed": 0, "by_others": 0, "by_code": 0, "code_disagrees": 0,
              "incoherent_s": 0.0}  # fmt: skip
    for pci, c in cells.items():
        lam = c["lam"]
        for st in c["streams"]:
            keep = np.zeros(st["e"].size, bool)
            for lab in np.unique(st["lab"]):
                m = np.flatnonzero(st["lab"] == lab)
                if m.size < MIN_UNIT:
                    continue
                t, u = st["t"][m], st["u"][m]
                # the SSS phase must be coherent: a sub-run far above its bound is the tracker
                # on another signal (its PSS can still be clean, being shared by a root)
                dd, _ = second_diff(st["e"][m] // 2, u, np.zeros(m.size, np.int64), 1)
                bound = 1 / math.sqrt(2 * N_SSS * max(float(np.median(st["snr"][m])), 1e-3))
                # zero-centred: a loop at the half alias gives second differences of ±2π,
                # whose median-centred MAD can be small
                s_w = (1.4826 * float(np.median(np.abs(dd))) / math.sqrt(6)
                       if dd.size >= MIN_TRIPLETS else float("nan"))  # fmt: skip
                if not s_w <= max(INCOHERENT_RAD, INCOHERENT_X * bound):
                    counts["incoherent_s"] += m.size * 2 * EPOCH_S
                    continue
                keep[m] = True
                s_code = _slope(t, st["code_raw_m"][m] + u * lam / (2 * np.pi))
                conf = (t[-1] - t[0]) * min(float(np.median(st["snr"][m])), 100.0)
                units.append({"pci": pci, "st": st, "m": m, "conf": conf,
                              "n_code": int(round(s_code / (ALIAS_HZ * lam)))})  # fmt: skip
            st["keep"] = keep
    units.sort(key=lambda x: -x["conf"])
    placed: list[tuple[float, float, float]] = []  # (t0, t1, Hz) of placed sub-runs
    for un in units:
        st, m = un["st"], un["m"]
        t, u = st["t"][m], st["u"][m]
        f_u = _slope(t, u) / (2 * np.pi)
        t0, t1 = float(t[0]), float(t[-1])
        near = [f for a, b, f in placed if a <= t1 + 1.0 and b >= t0 - 1.0]
        ref = np.nan
        if seed is not None:
            ref = float(np.nanmedian([seed(x) for x in np.linspace(t0, t1, 5)] + [np.nan]))
        if math.isfinite(ref):
            n = int(round((f_u - ref) / ALIAS_HZ))
            counts["by_seed"] += 1
            counts["code_disagrees"] += int(n != un["n_code"])
        elif near:
            n = int(round((f_u - float(np.median(near))) / ALIAS_HZ))
            counts["by_others"] += 1
            counts["code_disagrees"] += int(n != un["n_code"])
        else:
            n = un["n_code"]
            counts["by_code"] += 1
        if n:
            st["u"][m] = u - 2 * np.pi * ALIAS_HZ * n * (t - t0)
            f_u -= ALIAS_HZ * n
        placed.append((t0, t1, f_u))
    for c in cells.values():
        for st in c["streams"]:
            k = st.pop("keep")
            for key in ("e", "t", "snr", "u", "lab", "code_raw_m"):
                st[key] = st[key][k]
    return counts


def common_seed(cells: dict, reach_s: float = 2.0):
    """The cells' common carrier frequency as a function of time. Per 1 s window each cell's
    frequency (mean over its streams) votes with weight samples × SNR; cells within
    `SEED_CLUSTER_HZ` of each other form a cluster, and the heaviest cluster's weighted mean
    is the value (a median of two cells 100 Hz apart would sit on the half alias). The
    nearest window within `reach_s`, else NaN."""
    per_w: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for pci, c in cells.items():
        snr = min(float(np.median(c["snr"])), 100.0)
        for st in c["streams"]:
            for w, hz, n in zip(*window_freq(st["t"], st["u"], st["lab"]), strict=True):
                per_w[int(w)][pci].append((hz, n * snr))
    if not per_w:
        return lambda t: float("nan")
    ws = np.array(sorted(per_w))
    hz = np.empty(ws.size)
    for i, w in enumerate(ws):
        votes = [(float(np.mean([r[0] for r in v])), sum(r[1] for r in v))
                 for v in per_w[w].values()]  # fmt: skip
        best = max(
            votes, key=lambda x: sum(b for a, b in votes if abs(a - x[0]) < SEED_CLUSTER_HZ)
        )
        mem = [(a, b) for a, b in votes if abs(a - best[0]) < SEED_CLUSTER_HZ]
        hz[i] = sum(a * b for a, b in mem) / max(sum(b for _, b in mem), 1e-12)
    centres = (ws + 0.5) * FREQ_WIN_S

    def seed(t: float) -> float:
        i = int(np.argmin(np.abs(centres - t)))
        return float(hz[i]) if abs(centres[i] - t) <= reach_s else float("nan")

    return seed


def finish_cell(c: dict) -> None:
    """After `align_aliases`: per stream metres, run lengths; δ; carrier against code and the
    tracker's loop."""
    lam, fc, fs = c["lam"], c["fc"], c["fs"]
    c["streams"] = [st for st in c["streams"] if st["e"].size >= 4 * SLIP_W]
    for st in c["streams"]:
        st["u_m"] = st["u"] * lam / (2 * np.pi)
        cs = np.r_[0, np.flatnonzero(np.diff(st["lab"])) + 1]
        ce = np.r_[cs[1:], st["e"].size] - 1
        st["dur"] = (st["e"][ce] - st["e"][cs] + 2) * EPOCH_S
        st["censored"] = int(np.sum((cs == 0) | (ce == st["e"].size - 1)))
    c["delta"] = {}
    if len(c["streams"]) == 2:
        de, dd = subframe_offset(c["streams"][0], c["streams"][1])
        if dd.size >= MIN_TRIPLETS:
            s1 = c["streams"][1]
            lab = s1["lab"][np.searchsorted(s1["e"], de)]
            d1, _ = second_diff(de // 2, dd, lab, 50)  # δ's wander at 1 s inside one sub-run
            z = np.exp(1j * dd)
            c["delta"] = {"mean_rad": float(np.angle(z.mean())), "R": float(abs(z.mean())),
                          "near_pi_share": float(np.mean(np.abs(wrap(dd - np.pi)) < 0.5)),
                          "near_0_share": float(np.mean(np.abs(wrap(dd)) < 0.5)),
                          "S_1s_rad": robust_s(d1), "n": int(dd.size)}  # fmt: skip
    c["car_minus_code_hz"] = np.empty(0)
    c["trk_minus_car_hz"] = np.empty(0)
    if c["streams"]:
        s = c["streams"][0]
        wc, fcar, _ = window_freq(s["t"], s["u"], s["lab"], CMP_WIN_S)
        v = -2 * np.pi * fc * c["theta"] / fs
        wk, fcode, _ = window_freq(c["t"], v, c["arc"].astype(np.int64), CMP_WIN_S)
        _, ia, ib = np.intersect1d(wc, wk, return_indices=True)
        wt = np.floor(c["t"] / CMP_WIN_S).astype(np.int64)
        trk = np.array([-float(np.mean(c["nu_trk"][wt == w])) * fc for w in wc])
        c["car_minus_code_hz"] = fcar[ia] - fcode[ib]
        c["trk_minus_car_hz"] = trk - fcar


def _ref_lookup(c: dict):
    """A reference cell's carrier, both streams, by half-frame index: (e, u_m, label)."""
    e = np.concatenate([s["e"] for s in c["streams"]])
    u = np.concatenate([s["u_m"] for s in c["streams"]])
    lab = np.concatenate([s["lab"] * 2 + s["p"] for s in c["streams"]])
    o = np.argsort(e)
    return e[o], u[o], lab[o]


def operators(path: Path = CELL_TABLE) -> dict:
    """(EARFCN, PCI) -> (operator, eNB) where the table registers it once. Identity by table
    only (TBC); no position is read."""
    seen: dict = defaultdict(set)
    with open(path) as f:
        for r in csv.DictReader(f):
            seen[(int(r["earfcn"]), int(r["pci"]))].add((r["licensee"].split()[0], r["enb_id"]))
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def analyse(data: dict) -> dict:
    """Every cell of every chunk of one capture -> per-cell and dongle results."""
    m = data["meta"]
    fs, L, fc = m["fs"], m["L"], m["fc"]
    pcs: dict[int, dict] = defaultdict(lambda: defaultdict(list))
    win_rows: dict[int, list] = defaultdict(list)  # 1 s window -> [(pci, Hz, weight)]
    alias_counts: dict[str, float] = defaultdict(float)
    for ch in m["chunks"]:
        in_ch = data["chunk"] == ch["chunk"]
        sels = {int(p): np.flatnonzero(in_ch & (data["pci"] == p))
                for p in np.unique(data["pci"][in_ch])}  # fmt: skip
        # pass 1: seeded by the code rate; pass 2: by the cells' common carrier frequency
        cells = {p: c for p, sel in sels.items()
                 if (c := analyse_cell(data, sel, fs, L, fc)) is not None}  # fmt: skip
        if not cells:
            continue
        align_aliases(cells)
        seed = common_seed(cells)
        cells = {p: c for p, sel in sels.items()
                 if (c := analyse_cell(data, sel, fs, L, fc, seed)) is not None}  # fmt: skip
        cnt = align_aliases(cells, seed)
        for key, v in cnt.items():
            alias_counts[key] += v
        for c in cells.values():
            finish_cell(c)
        cells = {p: c for p, c in cells.items() if c["streams"]}
        if not cells:
            continue
        rank = sorted(cells, key=lambda p: -cells[p]["e"].size * np.median(cells[p]["snr"]))
        w0 = int(round(ch["start_s"] / FREQ_WIN_S))
        for pci, c in cells.items():
            pc = pcs[pci]
            for st in c["streams"]:  # own carrier, 10 ms
                dd, i = second_diff(st["e"] // 2, st["u_m"], st["lab"], 1)
                pc["d_car10ms"].append(dd)
                pc["s_car10ms"].append(st["snr"][i])
                pc["dur"].append(st["dur"])
                pc["censored"].append(st["censored"])
                pc["stream_s"].append(st["e"].size * 2 * EPOCH_S)
            q, v, lab, s = records(c["e"], c["code_m"], c["arc"].astype(np.int64), c["snr"],
                                   MIN_CODE_REC)  # fmt: skip
            dd, i = second_diff(q, v, lab, 1)
            pc["d_code10hz"].append(dd)
            pc["s_code10hz"].append(s[i])
            other = rank[0] if pci != rank[0] else (rank[1] if len(rank) > 1 else None)
            if other is not None:
                pc["ref"].append(other)
                re_, ru, rl = _ref_lookup(cells[other])
                for st in c["streams"]:
                    pos = np.searchsorted(re_, st["e"])
                    pos = np.minimum(pos, re_.size - 1)
                    hit = re_[pos] == st["e"]
                    ee = st["e"][hit]
                    sd = st["u_m"][hit] - ru[pos[hit]]
                    sl = st["lab"][hit] * 1_000_000 + rl[pos[hit]]
                    dd, _ = second_diff(ee // 2, sd, sl, 1)
                    pc["d_sd10ms"].append(dd)
                    q, v, lab, s = records(ee, sd, sl, st["snr"][hit], MIN_REC)
                    for tau in TAUS:
                        dd, i = second_diff(q, v, lab, max(1, round(tau / 0.1)))
                        pc[f"sd_car_{tau}"].append(dd)
                        if tau == TAUS[0]:
                            pc["s_sd10hz"].append(s[i])
                oc = cells[other]
                qa, va, la, _ = records(c["e"], c["code_m"], c["arc"].astype(np.int64), c["snr"],
                                        MIN_CODE_REC)  # fmt: skip
                qb, vb, lb, _ = records(oc["e"], oc["code_m"], oc["arc"].astype(np.int64),
                                        oc["snr"], MIN_CODE_REC)  # fmt: skip
                _, ia, ib = np.intersect1d(qa, qb, return_indices=True)
                for tau in TAUS:
                    dd, _ = second_diff(qa[ia], va[ia] - vb[ib], la[ia] * 100_000 + lb[ib],
                                        max(1, round(tau / 0.1)))  # fmt: skip
                    pc[f"sd_code_{tau}"].append(dd)
            for key in ("car_minus_code_hz", "trk_minus_car_hz", "snr"):
                pc[key].append(c[key])
            for key in ("amp_ratio_db", "tracked_s"):
                pc[key].append(c[key])
            if c["delta"]:
                pc["delta"].append(c["delta"])
            for kb, nb in c["breaks"].items():
                pc[f"brk_{kb}"].append(nb)
            # 1 s carrier frequency: mean of the two streams' slopes
            per_w: dict[int, list] = defaultdict(list)
            for st in c["streams"]:
                for a, hz, n in zip(*window_freq(st["t"], st["u"], st["lab"]), strict=True):
                    per_w[int(a)].append((hz, n))
            for a, rows in per_w.items():
                hz = float(np.mean([r[0] for r in rows]))
                n = sum(r[1] for r in rows)
                win_rows[w0 + a].append((pci, hz, n * float(np.median(c["snr"]))))
    out = summarise(pcs, win_rows, m)
    out["alias"] = dict(alias_counts)
    kept = float(sum(np.sum(p["stream_s"]) for p in pcs.values()))
    out["stream_s_kept"] = kept
    out["incoherent_share"] = alias_counts["incoherent_s"] / max(
        kept + alias_counts["incoherent_s"], 1e-9
    )
    return out


def _pct(x, q):
    return float(np.percentile(x, q)) if len(x) else float("nan")


def _spread(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0}
    return {"median": float(np.median(x)), "p5": _pct(x, 5), "p95": _pct(x, 95),
            "n": int(x.size)}  # fmt: skip


def _alias_share(x: np.ndarray) -> float | None:
    """Share of windows where the tracker's loop sits on a non-zero multiple of 100 Hz from the
    carrier (within 10 Hz)."""
    x = x[np.isfinite(x)]
    if not x.size:
        return None
    k = np.rint(x / 100.0)
    return float(np.mean((k != 0) & (np.abs(x - 100.0 * k) < 10.0)))


def _cat(v):
    return np.concatenate(v) if v else np.empty(0)


def summarise(pcs, win_rows, m) -> dict:
    fc, earfcn = m["fc"], m["earfcn"]
    lam = C / fc
    ops = operators()
    wins = sorted(win_rows)
    n_w = (max(wins) + 1) if wins else 0
    y_dongle = np.full(n_w, np.nan)
    resid: dict[int, np.ndarray] = defaultdict(lambda: np.full(n_w, np.nan))
    for w in wins:
        rows = win_rows[w]
        hz = np.array([r[1] for r in rows])
        wt = np.array([max(r[2], 1e-3) for r in rows])
        y_dongle[w] = -float(np.sum(wt * hz) / wt.sum()) / fc  # a fast dongle: negative CFO
        for j, r in enumerate(rows):
            o = np.arange(len(rows)) != j
            if o.any():
                resid[r[0]][w] = r[1] - float(np.sum(wt[o] * hz[o]) / wt[o].sum())
    cells = []
    # sites as letters per capture (A, B, ...): which cells share an eNB, without its identity
    sites: dict[str, str] = {}
    for pci in sorted(pcs, key=lambda p: -float(np.sum(pcs[p]["tracked_s"]))):
        pc = pcs[pci]
        snr_lin = _cat(pc["snr"])
        snr_db = 10 * np.log10(np.maximum(snr_lin, 1e-6))
        tracked = float(np.sum(pc["tracked_s"]))
        stream_s = float(np.sum(pc["stream_s"]))
        dur = _cat(pc["dur"])
        r_hz = resid[pci] if pci in resid else np.full(n_w, np.nan)
        r_ok = r_hz[np.isfinite(r_hz)]
        s10 = robust_s(_cat(pc["d_car10ms"]))
        bound = 1 / math.sqrt(2 * N_SSS * float(np.median(snr_lin)))
        deltas = pc["delta"]
        nd = np.array([x["n"] for x in deltas], float)
        op = ops.get((earfcn, pci), ("TBD", "TBD"))
        cells.append({
            "pci": pci, "operator": op[0],
            "site": "TBD" if op[1] == "TBD" else sites.setdefault(op[1], chr(65 + len(sites))),
            "tracked_s": round(tracked, 1),
            "snr_db_median": float(np.median(snr_db)),
            "carrier_white_10ms_mm": 1e3 * s10,
            "carrier_white_10ms_rad": s10 * 2 * np.pi / lam,
            "carrier_white_over_bound": s10 * 2 * np.pi / lam / bound,
            "carrier_sd_white_10ms_mm": 1e3 * robust_s(_cat(pc["d_sd10ms"])),
            "code_white_10hz_m": robust_s(_cat(pc["d_code10hz"])),
            "sd_ref": sorted({int(x) for x in pc["ref"]}),
            "carrier_sd_S_mm": {str(t): 1e3 * robust_s(_cat(pc[f"sd_car_{t}"])) for t in TAUS},
            "code_sd_S_m": {str(t): robust_s(_cat(pc[f"sd_code_{t}"])) for t in TAUS},
            "slips": int(np.sum(pc["brk_slip"])),
            "slips_per_stream_min": float(np.sum(pc["brk_slip"]) / (stream_s / 60))
            if stream_s else 0.0,
            "breaks": {b: int(np.sum(pc[f"brk_{b}"])) for b in ("arc", "miss", "gap", "slip")},
            "runs": int(dur.size),
            "run_s_median": _pct(dur, 50), "run_s_p90": _pct(dur, 90),
            "run_s_max": float(dur.max()) if dur.size else float("nan"),
            "share_in_runs_ge_10s": float(dur[dur >= 10].sum() / dur.sum()) if dur.size else 0.0,
            "share_in_runs_ge_60s": float(dur[dur >= 60].sum() / dur.sum()) if dur.size else 0.0,
            "runs_cut_by_chunk_edge": int(np.sum(pc["censored"])),
            "carrier_minus_code_hz": _spread(_cat(pc["car_minus_code_hz"])),
            "tracker_minus_carrier_hz": _spread(_cat(pc["trk_minus_car_hz"])),
            "tracker_on_100hz_alias_share": _alias_share(_cat(pc["trk_minus_car_hz"])),
            "subframe5": {
                "mean_rad": float(np.angle(np.sum([x["n"] * x["R"] * np.exp(1j * x["mean_rad"])
                                                   for x in deltas]))) if deltas else None,
                "near_pi_share": float(np.sum([x["n"] * x["near_pi_share"] for x in deltas])
                                       / nd.sum()) if deltas else None,
                "near_0_share": float(np.sum([x["n"] * x["near_0_share"] for x in deltas])
                                      / nd.sum()) if deltas else None,
                "S_1s_rad_median": float(np.nanmedian([x["S_1s_rad"] for x in deltas]))
                if deltas else None,
                "amp_db": float(np.nanmedian(pc["amp_ratio_db"])),
            },
            "freq_vs_others_ppb_mean": float(np.mean(r_ok) / fc * 1e9) if r_ok.size else None,
            "freq_vs_others_ppb_std": float(np.std(r_ok) / fc * 1e9) if r_ok.size > 1 else None,
            "freq_vs_others_windows": int(r_ok.size),
            "freq_vs_others_adev": allan(r_hz / fc) if r_ok.size > 3 else {},
        })  # fmt: skip
    yd = y_dongle[np.isfinite(y_dongle)]
    # 10 s means of the dongle, for the figure (frequency only)
    n10 = n_w // 10
    y10 = [
        float(np.nanmean(y_dongle[i * 10 : i * 10 + 10]) * 1e6)
        if np.isfinite(y_dongle[i * 10 : i * 10 + 10]).any()
        else None
        for i in range(n10)
    ]
    dongle = {
        "ppm_mean": float(np.mean(yd) * 1e6) if yd.size else None,
        "ppm_min": float(np.min(yd) * 1e6) if yd.size else None,
        "ppm_max": float(np.max(yd) * 1e6) if yd.size else None,
        "windows_1s": int(yd.size),
        "adev": allan(y_dongle),
        "ppm_10s": y10,
    }
    bins = {
        "carrier_sd_10hz": binned(_cat([x for p in pcs.values() for x in p["sd_car_0.1"]]),
                                  _cat([x for p in pcs.values() for x in p["s_sd10hz"]])),
        "code_10hz": binned(_cat([x for p in pcs.values() for x in p["d_code10hz"]]),
                            _cat([x for p in pcs.values() for x in p["s_code10hz"]])),
        "carrier_10ms": binned(_cat([x for p in pcs.values() for x in p["d_car10ms"]]),
                               _cat([x for p in pcs.values() for x in p["s_car10ms"]])),
    }  # fmt: skip
    return {"capture": m["capture"], "earfcn": earfcn, "fc_hz": fc, "lambda_m": lam,
            "capture_s": m["capture_s"], "chunk_s": m["chunk_s"], "chunks": len(m["chunks"]),
            "gaps": int(sum(c["gaps"] for c in m["chunks"])),
            "dongle": dongle, "cells": cells, "bins": bins}  # fmt: skip


def binned(d: np.ndarray, snr_lin: np.ndarray) -> list[dict]:
    """Robust S per 3 dB SNR bin (the centre sample's SNR)."""
    snr_db = 10 * np.log10(np.maximum(snr_lin, 1e-6))
    out = []
    for lo, hi in zip(SNR_EDGES[:-1], SNR_EDGES[1:], strict=True):
        m = (snr_db >= lo) & (snr_db < hi)
        s = robust_s(d[m])
        if math.isfinite(s):
            out.append({"lo": lo, "hi": hi, "snr_median_db": float(np.median(snr_db[m])),
                        "S_m": s, "n": int(m.sum())})  # fmt: skip
    return out


# --- report ---------------------------------------------------------------------------------


def _round(o, sig: int = 4):
    if isinstance(o, bool) or o is None or isinstance(o, str | int):
        return o
    if isinstance(o, float | np.floating):
        o = float(o)
        return float(f"{o:.{sig}g}") if math.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, dict):
        return {k: _round(v, sig) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_round(v, sig) for v in o]
    return o


def figure(results: list[dict], out: Path, commit: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, grid, muted = "#1f2328", "#d0d7de", "#59636e"
    blue, orange = "#2a78d6", "#eb6834"
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.0), constrained_layout=True)
    ax = axes[0]
    for key, col, mk in (("carrier_sd_10hz", blue, "o"), ("code_10hz", orange, "s")):
        for res in results:
            b = [x for x in res["bins"][key] if x["n"] >= 100]
            ax.plot([x["snr_median_db"] for x in b], [x["S_m"] for x in b], mk, ms=4.5,
                    color=col, alpha=0.6, mec="none")  # fmt: skip
    snr = np.linspace(-14, 16, 200)
    lin = 10 ** (snr / 10)
    ax.plot(snr, np.sqrt(ADR36_A**2 + ADR36_B**2 / lin), color=orange, lw=1.4,
            label="code, ADR-0036 fit (10 Hz, SNR ≥ −8 dB)")  # fmt: skip
    lam = float(np.median([r["lambda_m"] for r in results]))
    ax.plot(
        snr,
        lam / (2 * np.pi) / np.sqrt(2 * N_SSS * lin * REC / 2) * math.sqrt(2),
        color=blue,
        lw=1.4,
        ls="--",
        label="carrier, SSS bound × √2 (single difference)",
    )
    ax.plot([], [], "s", color=orange, ms=4.5, label="code, one cell, these captures")
    ax.plot([], [], "o", color=blue, ms=4.5, label="carrier, single difference, these captures")
    ax.set_yscale("log")
    ax.set_xlabel("SNR per resource element (dB)")
    ax.set_ylabel("white noise of a 10 Hz record, S(0.1 s) (m)")
    ax.set_title("Noise against SNR: carrier ~1,000× below code", loc="left", color=ink,
                 fontsize=10.5)  # fmt: skip
    ax.legend(frameon=False, fontsize=7.5, loc="center left", bbox_to_anchor=(0.0, 0.47))
    ax = axes[1]
    for key, col, mk, lab, scale in (("carrier_sd_S_mm", blue, "o", "carrier", 1e-3),
                                     ("code_sd_S_m", orange, "s", "code", 1.0)):  # fmt: skip
        first = True
        for res in results:
            for c in res["cells"]:
                if c["snr_db_median"] < -8:
                    continue
                v = [c[key].get(str(t)) for t in TAUS]
                v = [x * scale if x is not None else np.nan for x in v]
                ax.plot(
                    TAUS,
                    v,
                    "-" + mk,
                    color=col,
                    alpha=0.35,
                    ms=3,
                    lw=0.8,
                    label=f"{lab}, single difference, one cell" if first else None,
                )
                first = False
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("τ (s)")
    ax.set_ylabel("S(τ) inside one run (m)")
    ax.set_title("Growth with time, cells ≥ −8 dB", loc="left", color=ink, fontsize=10.5)
    ax.legend(frameon=False, fontsize=7.5)
    ax = axes[2]
    styles = iter([("#1baf7a", "-"), ("#7b4fa0", "--"), ("#eda100", ":")])
    for res in sorted(results, key=lambda r: -r["capture_s"]):
        y = res["dongle"]["ppm_10s"]
        if len(y) < 30:
            continue
        green, ls = next(styles, ("#59636e", "-."))
        tt = np.arange(len(y)) * 10 / 60
        yy = np.array([np.nan if v is None else v for v in y])
        ax.plot(tt, (yy - np.nanmean(yy)) * 1e3, color=green, ls=ls, lw=1.2,
                label=res["capture"])  # fmt: skip
    ax.set_xlabel("time (min)")
    ax.set_ylabel("dongle frequency − its mean (ppb), 10 s means")
    ax.set_title("The dongle, from the cells' common carrier", loc="left", color=ink,
                 fontsize=10.5)  # fmt: skip
    ax.legend(frameon=False, fontsize=7.5)
    for a in axes:
        a.grid(True, which="major", color=grid, lw=0.6)
        a.tick_params(colors=muted)
        for s in a.spines.values():
            s.set_color(grid)
    fig.suptitle(f"Real static captures, one NESDR, LTE SSS carrier phase; analysis at {commit}",
                 x=0.995, ha="right", fontsize=8, color=muted)  # fmt: skip
    path = out / "carrier_vs_code.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="front end + phase per epoch -> npz")
    r.add_argument("capture", type=Path)
    r.add_argument("out", type=Path)
    r.add_argument("--chunk-s", type=float, default=600.0)
    r.add_argument("--limit-s", type=float, default=None)
    p = sub.add_parser("report", help="npz files -> summary.json and the figure")
    p.add_argument("npz", nargs="+", type=Path)
    p.add_argument("--out", type=Path, default=REPO / "analysis/results/carrier-phase-277")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        save(collect(a.capture, a.chunk_s, limit_s=a.limit_s), a.out)
        return
    from pnt.cli import _commit

    commit = _commit()
    results = [analyse(load(f)) for f in a.npz]
    a.out.mkdir(parents=True, exist_ok=True)
    figure(results, a.out, commit)
    (a.out / "summary.json").write_text(
        json.dumps(_round({"commit": commit, "captures": results}), separators=(",", ":")) + "\n"
    )
    for res in results:
        dg = res["dongle"]
        print(f"{res['capture']}: dongle {dg['ppm_mean']} ppm, adev {dg['adev']}")
        for c in res["cells"]:
            print(f"  {c['pci']:3d} {c['operator']:6s} snr {c['snr_db_median']:5.1f} "
                  f"tracked {c['tracked_s']:6.0f} s  car10ms {c['carrier_white_10ms_mm']:.2f} mm "
                  f"(x{c['carrier_white_over_bound']:.2f} bound) code10Hz "
                  f"{c['code_white_10hz_m']:.2f} m  slips/min {c['slips_per_stream_min']:.2f} "
                  f"runs med {c['run_s_median']:.1f} p90 {c['run_s_p90']:.1f} "
                  f"max {c['run_s_max']:.0f} s  vs-others {c['freq_vs_others_ppb_mean']} "
                  f"± {c['freq_vs_others_ppb_std']} ppb")  # fmt: skip


if __name__ == "__main__":
    main()
