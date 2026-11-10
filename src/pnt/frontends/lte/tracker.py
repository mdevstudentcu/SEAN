"""LTE cell search and PSS/SSS time-of-arrival tracking on RTL-SDR captures (clean-room).

Implemented from 3GPP TS 36.211 and textbook estimation theory; no third-party LTE code.
Pipeline, per carrier segment of a capture (`capture.Segment`):

1. **Search** (`search`): FFT cross-correlation with the three PSS Zadoff-Chu roots over a grid of
   carrier offsets (±`max_ppm`), folded over 5 ms half-frames and summed non-coherently. Peaks
   above a peak-to-mean threshold are PSS candidates.
2. **SSS and PCI**: at each candidate, the SSS of every N_ID1 (168) and subframe variant (0 or 5)
   is correlated coherently against the PSS channel phase. The best gives the PCI and which
   half-frame starts the frame. The carrier offset is refined from the SSS-to-PSS phase.
3. **Tracking** (`_Track`): every 5 ms the received SSS and PSS symbols are FFT'd and divided by
   the known sequences. The 124 products give the correlation as a function of delay,
   evaluated on a 1/8-sample grid by a zero-padded inverse FFT (the exact band-limited
   interpolation), then a parabola through the grid peak. Measured on synthetic +20 dB captures
   (analysis/lte_frontend_sigma.py), a parabola through the raw samples (`interp=1`) is as good
   (RMS 1.02 m against 1.12 m, no visible S-curve), so the grid is kept for the first-path
   search, which needs the profile between samples, not for the peak. A phase-slope fit across
   the 62 subcarriers is the same estimator in another form. A 2-state Kalman loop (boundary
   offset and its rate) predicts each epoch; its rate is aided by the carrier phase from epoch
   to epoch, because the dongle's LO and sample clock share one TCXO: the carrier offset and
   the code rate are the same clock (`rx_clock` in the measurement meta).
4. **First path**: an averaged delay profile is checked for an earlier path that is clearly not a
   sidelobe of the tracked one; if found, the loop moves to it.
5. **Gaps**: dropped USB samples step the receiver clock. A loss of lock (a step beyond the
   code gate fails the gate) triggers a re-search near the prediction; the step (modulo a
   frame, or whole with the sidecar's buffer stamps) is the number of samples dropped. Steps
   smaller than the gate at low SNR can be absorbed by the loop instead (not tested).

Every threshold below that is not from the standard is a regression guard (`TBC`), picked on
synthetic captures; the real values come from the day-1 static capture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cache

import numpy as np
from scipy import fft as sp_fft

from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.capture import Capture, Segment

C = 299_792_458.0
_K = sig.sync_subcarriers()
_RES = sig.reserved_subcarriers()
_K_ALL = np.r_[_K, _RES].astype(np.float32)
_BINS_ALL = np.r_[_K, _RES]
# RMS bandwidth of the 62 sync subcarriers: β² = Δf² · mean(k²)
BETA_HZ = sig.SUBCARRIER_HZ * math.sqrt(float(np.mean(_K.astype(float) ** 2)))


@dataclass(frozen=True)
class Config:
    """Tuning. Values marked TBC are regression guards until the day-1 capture."""

    acq_ms: float = 80.0  # search window (16 half-frames), TBC
    max_ppm: float = 5.0  # dongle offset searched (TCXO spec ±1 ppm, cold start more), TBC
    cfo_step_hz: float = 2000.0  # carrier-offset bins: ≤ 1 kHz off costs a 67 µs PSS < 0.1 dB
    # Regression guards, TBC: on 100 noise-only 80 ms windows the largest folded-PSS peak-to-
    # mean was 3.1 and the largest SSS score 6.1 (1 in 1,775 candidates above 6); a true cell's
    # SSS score is 12-15 and a strong cell's PSS ghosts score at most 4.1 on the SSS.
    acq_peak_to_mean: float = 4.0
    sss_peak_to_mean: float = 6.5
    max_cells_per_root: int = 6
    search_period_s: float = 10.0  # look for new cells this often, TBC
    settle_s: float = 0.02  # skipped after a retune (R820T settling), TBC
    interp: int = 8  # delay grid: 1/interp sample
    gate_samples: float = 1.5  # code gate around the prediction
    detect_snr_db: float = 8.0  # post-correlation SNR to accept an epoch, regression guard, TBC
    first_path_us: float = 4.0  # how far before the tracked path to look for an earlier one, TBC
    first_path_rel_db: float = -10.0  # earlier path must be within this of the tracked, TBC
    first_path_sidelobe: float = 3.0  # and this many times the tracked path's own sidelobe, TBC
    first_path_epochs: int = 40  # epochs averaged before a first-path decision (200 ms)
    # Regression guard, TBC: about one normal CP. A re-found cell this close to its prediction
    # moved to another path; beyond it, without host stamps, the jump counts as dropped samples.
    max_path_jump_us: float = 5.0
    accel_ms2: float = 2.0  # rate random walk of the loop, as an acceleration, TBC
    carrier_lock_hz: float = 20.0  # loop rate 1σ below which carrier aiding starts, TBC
    miss_limit: int = 4  # consecutive misses before re-searching near the prediction
    lost_s: float = 2.0  # give a cell up after this long without it
    output_period_s: float = 0.1  # 10 Hz
    sigma_scale: float = 1.5  # reported σ / ranging bound; 1.5 covers the synthetic tests, TBC
    # Threads for the search's FFTs (scipy `workers`; -1 = every core). Same results either way.
    fft_workers: int = 2


@dataclass(slots=True)
class Epoch:
    """One 5 ms measurement of one cell (internal; `emit` turns them into Measurements)."""

    k: int  # half-frame index from the arc's reference boundary
    c_ref: float  # corrected sample index of the half-frame boundary (posterior)
    theta_meas: float  # measured boundary offset, samples
    nu: float  # posterior rate (dimensionless)
    sigma: float  # ranging bound, samples
    snr_post: float  # post-correlation SNR (linear)
    psi: float  # carrier phase, rad (with the derotation added back)
    n_ref: float  # sample index the phase refers to
    locked: bool  # carrier aiding on
    arc: int
    n0: float  # the arc's reference boundary (`CellTrack.n0` moves when a new arc starts)


@dataclass
class CellTrack:
    """A tracked cell: identity, arc reference and its 5 ms epochs."""

    earfcn: int | None
    fc: float
    pci: int
    n0: float  # corrected sample index of the arc's reference subframe-0 boundary
    arc: int = 0
    epochs: list[Epoch] = field(default_factory=list)
    snr_db: float = float("nan")


@dataclass
class Gap:
    """Samples dropped at file index `at`; epochs touching file [at, until) are unusable."""

    at: int
    n: int
    until: int
    ambiguous: bool = False  # sized only modulo a frame (no buffer stamps)


class GapMap:
    """File index <-> corrected index (local time in samples, gaps put back)."""

    def __init__(self, gaps: list[Gap] | None = None):
        self.gaps: list[Gap] = []
        for g in gaps or []:
            self.add(g)

    def add(self, gap: Gap) -> None:
        self.gaps.append(gap)
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the lookup arrays (after `add`, or after a gap's `until` changed)."""
        self.gaps.sort(key=lambda g: g.at)
        at = np.array([g.at for g in self.gaps], np.int64)
        n = np.array([g.n for g in self.gaps], np.int64)
        self._at, self._cum = at, np.cumsum(n)
        self._cstart = at + np.concatenate([[0], self._cum[:-1]])  # corrected start of each gap
        self._cend = at + self._cum
        self._until = np.array([g.until for g in self.gaps], np.int64)

    def corrected_ends(self) -> np.ndarray:
        """Corrected index just after each gap, in the order of `gaps`."""
        return self._cend if self.gaps else np.zeros(0, np.int64)

    def to_corrected(self, f):
        if not self.gaps:
            return f
        i = np.searchsorted(self._at, f, side="right")
        return f + np.where(i > 0, self._cum[np.maximum(i - 1, 0)], 0)

    def to_file(self, c):
        """File index of corrected index `c`, and whether that sample exists and is usable."""
        c = np.asarray(c, dtype=np.int64)
        if not self.gaps:
            return c, np.ones(c.shape, bool)
        i = np.searchsorted(self._cend, c, side="right")  # gaps wholly before c
        f = c - np.where(i > 0, self._cum[np.maximum(i - 1, 0)], 0)
        j = np.searchsorted(self._cstart, c, side="right") - 1
        inside = (j >= 0) & (c < self._cend[np.maximum(j, 0)])
        jj = np.searchsorted(self._at, f, side="right") - 1  # gap at or before f
        near = (jj >= 0) & (f < self._until[np.maximum(jj, 0)])
        return f, ~(inside | near)


# --- spectra ------------------------------------------------------------------------------


def _phase(f_hz: float, n, fs: float):
    """2π · frac(f n / fs), exact enough for n up to 1e11."""
    x = np.asarray(n, dtype=np.float64) * (f_hz / fs)
    return 2 * np.pi * (x - np.floor(x))


def _phase1(f_hz: float, n: float, fs: float) -> float:
    """Scalar `_phase`."""
    x = n * (f_hz / fs)
    return 2 * math.pi * (x - math.floor(x))


def window_spectra(fetch, starts: np.ndarray, fs: float, f_hz: float, backoff: float):
    """FFT of one useful-symbol window per start (fractional corrected index of the useful
    part), after removing carrier offset `f_hz`. Returns the 62 sync bins and 10 reserved bins,
    both with the window-position phase ramp removed, so a symbol arriving `d` samples late
    gives exp(-j 2π k d / N) on subcarrier k."""
    n_u = sig.useful_length(fs)
    w = np.round(starts - backoff).astype(np.int64)
    idx = w[:, None] + np.arange(n_u)[None, :]
    x = fetch(idx) * np.exp(-1j * _phase(f_hz, idx, fs).astype(np.float32))
    y = sp_fft.fft(x, axis=1)
    e = ((w - starts) / n_u).astype(np.float32)[:, None]  # window start vs useful start
    ramp = np.exp((-2j * np.pi) * _K_ALL[None, :] * e)
    y = y[:, _BINS_ALL % n_u] * ramp
    return y[:, : _K.size], y[:, _K.size :]


def delay_profile(z: np.ndarray, fs: float, interp: int) -> np.ndarray:
    """R(d) = Σ_k z_k exp(j 2π k d / N) on d = m / interp samples (cyclic), for each row."""
    n_u = sig.useful_length(fs)
    spec = np.zeros((z.shape[0], n_u * interp), np.complex128)
    spec[:, _K % (n_u * interp)] = z
    return np.fft.ifft(spec, axis=1) * (n_u * interp)


def _single_path_sidelobe(fs: float, interp: int) -> np.ndarray:
    """|R0(d)|² / |R0(0)|² of one clean path, on the same grid as `delay_profile`."""
    r = delay_profile(np.ones((1, sig.N_SYNC)), fs, interp)[0]
    return np.abs(r) ** 2 / np.abs(r[0]) ** 2


def _parabola(a, b, c):
    den = a - 2 * b + c
    return np.where(np.abs(den) > 1e-30, 0.5 * (a - c) / np.where(den == 0, 1, den), 0.0)


def _offsets(fs: float) -> tuple[float, float, int, int, float]:
    """(SSS offset, PSS offset in samples, half-frame L, useful N, backoff)."""
    n_u = sig.useful_length(fs)
    cp = sig.samples(sig.CP_TS, fs)
    return (sig.samples(sig.SSS_OFFSET_TS, fs), sig.samples(sig.PSS_OFFSET_TS, fs),
            sig.half_frame_length(fs), n_u, cp / 2)  # fmt: skip


# --- search -------------------------------------------------------------------------------


@dataclass
class Found:
    n_id1: int
    n_id2: int
    boundary: float  # corrected sample index of a subframe-0 boundary
    f_hz: float  # carrier offset (dongle view)
    sigma_f_hz: float
    snr_db: float  # per resource element, rough
    pss_metric: float
    sss_metric: float

    @property
    def pci(self) -> int:
        return sig.pci(self.n_id1, self.n_id2)


def search(x: np.ndarray, c0: int, fs: float, fc: float, cfg: Config) -> list[Found]:
    """Find cells in `x` (contiguous samples whose first is at corrected index `c0`)."""
    sss_off, pss_off, L, n_u, backoff = _offsets(fs)
    h_count = (x.size - n_u - 1) // L
    if h_count < 2:
        return []
    n_valid = h_count * L
    nfft = sp_fft.next_fast_len(x.size + n_u)
    wk = cfg.fft_workers
    xf = sp_fft.fft(x.astype(np.complex64), nfft, workers=wk)
    f_max = cfg.max_ppm * 1e-6 * fc
    half = math.ceil(f_max / cfg.cfo_step_hz - 0.5)
    bins = np.arange(-half, half + 1) * cfg.cfo_step_hz
    metric = np.empty((3, bins.size, L), np.float32)
    for n_id2 in range(3):
        tf = _pss_spectra(fs, nfft, tuple(bins), n_id2)  # (bins, nfft), conjugated
        corr = sp_fft.ifft(xf[None, :] * tf, axis=1, workers=wk)[:, :n_valid]
        fold = (corr.real**2 + corr.imag**2).reshape(bins.size, h_count, L).sum(axis=1)
        metric[n_id2] = fold / fold.mean(axis=1, keepdims=True)
    sidelobe_mask = max(3, round(2 * fs / 1e6))  # ±~1 chip
    fetch = lambda idx: x[idx - c0]  # noqa: E731
    found: list[Found] = []
    for n_id2 in range(3):
        mt = metric[n_id2].copy()
        for _ in range(cfg.max_cells_per_root):
            b, j = np.unravel_index(np.argmax(mt), mt.shape)
            peak = mt[b, j]
            if peak < cfg.acq_peak_to_mean:
                break
            lo, hi = j - sidelobe_mask, j + sidelobe_mask + 1
            cols = np.arange(lo, hi) % L
            mt[:, cols] = 0
            a, c = metric[n_id2, b, (j - 1) % L], metric[n_id2, b, (j + 1) % L]
            jf = j + float(_parabola(a, peak, c))
            cell = _identify(fetch, c0, jf, n_id2, bins[b], h_count, fs, fc, cfg)
            if cell is not None:
                cell.pss_metric = float(peak)
                found.append(cell)
    return _dedupe(found)


@cache
def _pss_spectra(fs: float, nfft: int, bins: tuple[float, ...], n_id2: int) -> np.ndarray:
    """conj(FFT) of the PSS useful symbol shifted by each carrier-offset bin (cached)."""
    n_u = sig.useful_length(fs)
    m = np.arange(n_u)
    t = sig.sync_time_waveform(sig.pss(n_id2), fs, n_u)
    shifted = t[None, :] * np.exp(2j * np.pi * np.outer(bins, m) / fs)
    return np.conj(sp_fft.fft(shifted.astype(np.complex64), nfft, axis=1))


def _dedupe(found: list[Found]) -> list[Found]:
    """One entry per PCI: the strongest (a strong cell's ghost can decode to its own PCI)."""
    best: dict[int, Found] = {}
    for f in found:
        if f.pci not in best or f.sss_metric > best[f.pci].sss_metric:
            best[f.pci] = f
    return sorted(best.values(), key=lambda f: -f.snr_db)


def _identify(fetch, c0, jf, n_id2, f_bin, h_count, fs, fc, cfg) -> Found | None:
    """SSS detection at a PSS candidate (first useful-PSS start `jf` within the window)."""
    sss_off, pss_off, L, n_u, backoff = _offsets(fs)
    h = np.arange(h_count)
    pss_starts = c0 + jf + h * L
    keep = pss_starts - (pss_off - sss_off) - backoff >= c0 + 1
    pss_starts = pss_starts[keep]
    if pss_starts.size < 2:
        return None
    sss_starts = pss_starts - (pss_off - sss_off)
    yp, rp = window_spectra(fetch, pss_starts, fs, f_bin, backoff)
    ys, rs = window_spectra(fetch, sss_starts, fs, f_bin, backoff)
    zp = yp * np.conj(sig.pss(n_id2))[None, :]
    prof = delay_profile(zp, fs, cfg.interp)
    gate = np.r_[0 : 2 * cfg.interp + 1, -2 * cfg.interp : 0]
    sub = prof[:, gate]
    i = np.argmax(np.abs(sub), axis=1)
    d = gate[i] / cfg.interp
    ref = sub[np.arange(sub.shape[0]), i]
    ramp = np.exp(2j * np.pi * _K[None, :] * d[:, None] / n_u)
    v = ys * ramp * (np.conj(ref) / np.maximum(np.abs(ref), 1e-30))[:, None]
    table = sig.sss_table(n_id2).reshape(2 * sig.N_ID1_COUNT, sig.N_SYNC)
    score = (v @ table.T).real  # (H, 336): rows [sf0 g..., sf5 g...]
    sf0, sf5 = score[:, : sig.N_ID1_COUNT], score[:, sig.N_ID1_COUNT :]
    even = np.arange(score.shape[0]) % 2 == 0
    s = np.stack([sf0[even].sum(0) + sf5[~even].sum(0), sf5[even].sum(0) + sf0[~even].sum(0)])
    p, g = np.unravel_index(np.argmax(s), s.shape)
    metric = s[p, g] / np.mean(np.abs(s))
    if metric < cfg.sss_peak_to_mean:
        return None
    # Carrier offset from the SSS-to-PSS phase (they are pss_off - sss_off samples apart).
    parity = (np.arange(score.shape[0]) + p) % 2  # 0: subframe 0
    seqs = table[parity * sig.N_ID1_COUNT + g]
    q = np.sum(v * seqs, axis=1)  # SSS phase relative to the PSS, per half-frame
    dt = (pss_off - sss_off) / fs
    f_res = -np.angle(q.sum()) / (2 * np.pi * dt)
    spread = np.angle(q * np.conj(q.sum()))
    sigma_f = max(float(np.std(spread)) / math.sqrt(q.size) / (2 * np.pi * dt), 5.0)
    # Rough SNR per resource element from the PSS: |R|² / (124... here 62) noise.
    noise = np.mean(np.abs(rp) ** 2) + 1e-30
    snr_post = np.mean(np.abs(ref) ** 2) / (sig.N_SYNC * noise) - 1
    snr_re = max(snr_post, 1e-3) / sig.N_SYNC
    first_sf0 = pss_starts[0] + d[0] - pss_off + (L if p == 1 else 0)
    return Found(
        n_id1=int(g),
        n_id2=n_id2,
        boundary=float(first_sf0),
        f_hz=float(f_bin + f_res),
        sigma_f_hz=float(1.5 * sigma_f),
        snr_db=float(10 * math.log10(snr_re)),
        pss_metric=0.0,
        sss_metric=float(metric),
    )


# --- tracking -----------------------------------------------------------------------------


@dataclass(slots=True)
class State:
    """Loop state at half-frame `k`: boundary offset theta (samples), rate nu, covariance."""

    theta: float
    nu: float
    p00: float
    p01: float
    p11: float
    k: int

    def copy(self) -> State:
        return State(self.theta, self.nu, self.p00, self.p01, self.p11, self.k)

    def at(self, k: int, L: int) -> float:
        return self.theta + self.nu * (k - self.k) * L

    def predict(self, k: int, L: int, fs: float, q: float) -> None:
        """Propagate to half-frame k: theta += nu dn; nu is a random walk of PSD q (1/s)."""
        if k <= self.k:
            return
        dn = (k - self.k) * L
        dt = dn / fs
        self.theta += self.nu * dn
        self.p00 += 2 * dn * self.p01 + dn * dn * self.p11 + q * fs * fs * dt**3 / 3
        self.p01 += dn * self.p11 + q * fs * dt**2 / 2
        self.p11 += q * dt
        self.k = k

    def update(self, h: int, z: float, r: float) -> None:
        """Scalar update of state element h (0: theta, 1: nu) with measurement z, variance r."""
        p_h0, p_h1 = (self.p00, self.p01) if h == 0 else (self.p01, self.p11)
        s = (self.p00 if h == 0 else self.p11) + r
        g0, g1 = p_h0 / s, p_h1 / s
        innov = z - (self.theta if h == 0 else self.nu)
        self.theta += g0 * innov
        self.nu += g1 * innov
        self.p00, self.p01, self.p11 = (
            self.p00 - g0 * p_h0,
            self.p01 - g0 * p_h1,
            self.p11 - g1 * p_h1,
        )

    def reacquire(self, theta: float, var: float) -> None:
        """Replace the offset by an independent fix of variance `var` (a re-found cell).

        The new offset's error is the fix's error, which owes nothing to the rate's, so the
        cross term goes to zero and the covariance stays positive semi-definite. Setting `p00`
        alone keeps the cross term built up while coasting (about dn · p11): after a long
        coast p01² > p00 · p11, and the next update drives the variances negative (#181)."""
        self.theta, self.p00, self.p01 = theta, var, 0.0

    def s(self, h: int, r: float) -> float:
        return (self.p00 if h == 0 else self.p11) + r


class _Track:
    """Track cells of one segment (shared gap map, so a drop found by one cell helps all)."""

    def __init__(self, cap: Capture, seg: Segment, gaps: GapMap, cfg: Config):
        self.cap, self.seg, self.gaps, self.cfg = cap, seg, gaps, cfg
        self.fs = cap.fs
        self.sss_off, self.pss_off, self.L, self.n_u, self.backoff = _offsets(self.fs)
        self.sidelobe = _single_path_sidelobe(self.fs, cfg.interp)
        self.q = (cfg.accel_ms2 / C) ** 2

    def fetch(self, c):
        f, _ = self.gaps.to_file(c)
        return self.cap.gather(np.clip(f, 0, self.cap.n_samples - 1))

    def usable(self, bounds: np.ndarray) -> np.ndarray:
        """Both sync windows of each epoch lie in one gap-free stretch of this segment."""
        lo = np.floor(bounds + self.sss_off - self.backoff - 1).astype(np.int64)
        hi = np.ceil(bounds + self.pss_off - self.backoff + self.n_u + 1).astype(np.int64)
        f_lo, ok_lo = self.gaps.to_file(lo)
        f_hi, ok_hi = self.gaps.to_file(hi)
        return (ok_lo & ok_hi & (f_hi - f_lo == hi - lo) & (f_lo >= self.seg.start)
                & (f_hi < min(self.seg.stop, self.cap.n_samples)))  # fmt: skip

    def measure(self, n_id1: int, n_id2: int, bounds: np.ndarray, ks: np.ndarray, f_hz: float):
        """Delay profiles (rows: epochs) of PSS + SSS at the given half-frame boundaries, and
        the reserved-bin noise power per epoch. Even k is subframe 0."""
        yp, rp = window_spectra(self.fetch, bounds + self.pss_off, self.fs, f_hz, self.backoff)
        ys, rs = window_spectra(self.fetch, bounds + self.sss_off, self.fs, f_hz, self.backoff)
        tbl = sig.sss_table(n_id2)[:, n_id1]
        z = yp * np.conj(sig.pss(n_id2))[None, :] + ys * tbl[ks % 2]
        noise = 0.5 * (np.mean(np.abs(rp) ** 2, axis=1) + np.mean(np.abs(rs) ** 2, axis=1))
        return delay_profile(z, self.fs, self.cfg.interp), noise

    def file_index(self, c: float) -> int:
        return int(self.gaps.to_file(np.int64(math.floor(c)))[0])

    def run(self, cell: CellTrack, n_id1: int, n_id2: int, st: State, c_stop: float) -> State:
        """Track `cell` from state `st` (its next epoch is st.k) to corrected index `c_stop`, or
        until it has been gone for `lost_s`. Appends epochs to `cell.epochs`."""
        cfg, fs, L, fc = self.cfg, self.fs, self.L, cell.fc
        grid = self.n_u * cfg.interp
        gi = int(round(cfg.gate_samples * cfg.interp))
        gate = np.arange(-gi, gi + 1)
        win = np.arange(-int(round(cfg.first_path_us * 1e-6 * fs * cfg.interp)), gi + 1)
        prof_acc, prof_n = np.zeros(win.size), 0
        detect = 10 ** (cfg.detect_snr_db / 10)
        noise_ema = snr_ema = None
        miss, settled = 0, False
        last: Epoch | None = None  # previous good epoch, for the carrier step
        good: State | None = None  # loop state at the last good epoch
        last_seen = cell.n0 + st.k * L + st.theta
        next_reloc = st.k
        pending: Gap | None = None
        k = st.k
        while True:
            n_blk = int(np.clip(0.3 / (3 * math.sqrt(max(st.p11, 0.0)) * L + 1e-15), 2, 200))
            ks = np.arange(k, k + n_blk)
            bounds = cell.n0 + ks * L + st.theta + st.nu * (ks - st.k) * L
            if bounds[0] > c_stop or bounds[0] - last_seen > cfg.lost_s * fs:
                break
            ok = self.usable(bounds) & (bounds <= c_stop)
            if not ok.any():
                k += n_blk
                continue
            ks, bounds = ks[ok], bounds[ok]
            f_used = -st.nu * fc
            prof, noise = self.measure(n_id1, n_id2, bounds, ks, f_used)
            sub = np.abs(prof[:, gate % grid])
            i = np.argmax(sub, axis=1)
            rows = np.arange(sub.shape[0])
            edge = (i == 0) | (i == gate.size - 1)
            a = sub[rows, np.maximum(i - 1, 0)]
            b = sub[rows, i]
            c = sub[rows, np.minimum(i + 1, gate.size - 1)]
            d = (gate[i] + _parabola(a, b, c)) / cfg.interp
            phase = np.angle(prof[rows, gate[i] % grid])
            power = np.abs(prof[:, win % grid]) ** 2
            if noise_ema is None:
                noise_ema = float(np.median(noise))
            action = None
            for r in range(ks.size):
                kk = int(ks[r])
                noise_ema = 0.95 * noise_ema + 0.05 * float(noise[r])
                snr_post = float(b[r] ** 2 / (2 * sig.N_SYNC * noise_ema)) - 1.0
                st.predict(kk, L, fs, self.q)
                theta_meas = float(bounds[r] - cell.n0 - kk * L + d[r])
                sigma = fs / (2 * math.pi * BETA_HZ * math.sqrt(2 * max(snr_post, 1e-3)))
                r_code = (cfg.sigma_scale * sigma) ** 2
                ok_r = snr_post >= detect and not edge[r]
                if ok_r and abs(theta_meas - st.theta) > 5 * math.sqrt(st.s(0, r_code)) + 0.25:
                    ok_r = False
                if not ok_r:
                    miss += 1
                    strong = snr_ema is not None and snr_ema >= 4 * detect
                    if miss >= cfg.miss_limit and strong and kk >= next_reloc:
                        action = self._relocate(cell, st, kk, good, last)
                        next_reloc = kk + 100
                        break
                    continue
                miss = 0
                snr_ema = snr_post if snr_ema is None else 0.9 * snr_ema + 0.1 * snr_post
                st.update(0, theta_meas, r_code)
                n_ref = float(bounds[r] + 0.5 * (self.sss_off + self.pss_off) + self.n_u / 2)
                psi = float(phase[r]) + _phase1(f_used, n_ref, fs)
                locked = math.sqrt(max(st.p11, 0.0)) * fc < cfg.carrier_lock_hz
                if locked and last is not None and last.k == kk - 1:
                    dn = n_ref - last.n_ref
                    f_hat = -st.nu * fc
                    dpsi = psi - last.psi - _phase1(f_hat, dn, fs)
                    dpsi = (dpsi + math.pi) % (2 * math.pi) - math.pi
                    nu_meas = -(f_hat + dpsi * fs / (2 * math.pi * dn)) / fc
                    var_phi = 0.5 / max(snr_post, 1e-3) + 0.5 / max(last.snr_post, 1e-3)
                    r_nu = var_phi * (fs / (2 * math.pi * dn * fc)) ** 2
                    if abs(nu_meas - st.nu) < 4 * math.sqrt(st.s(1, r_nu)):
                        st.update(1, nu_meas, r_nu)
                if pending is not None:
                    pending.until = max(
                        pending.at, self.file_index(bounds[r] + self.sss_off - self.backoff)
                    )
                    self.gaps.refresh()
                    pending = None
                ep = Epoch(
                    k=kk,
                    c_ref=cell.n0 + kk * L + st.theta,
                    theta_meas=theta_meas,
                    nu=st.nu,
                    sigma=sigma,
                    snr_post=snr_post,
                    psi=psi,
                    n_ref=n_ref,
                    locked=locked,
                    arc=cell.arc,
                    n0=cell.n0,
                )
                if settled:
                    cell.epochs.append(ep)
                last, good, last_seen = ep, st.copy(), float(bounds[r])
                prof_acc += power[r]
                prof_n += 1
                if prof_n >= cfg.first_path_epochs:
                    shift = self._earlier_path(prof_acc / prof_n, win, noise_ema)
                    prof_acc[:], prof_n = 0, 0
                    if shift:
                        st.theta += shift
                        if settled:
                            cell.arc += 1
                        last = None
                        action = ("continue", kk + 1)
                        break
                    settled = True
            if action is None:
                k = int(ks[-1]) + 1
            elif action[0] == "continue":
                k = action[1]
            elif action[0] == "lost":
                k = int(ks[r]) + 1
                miss = 0
            elif action[0] == "found":
                _, k_found, theta, new_arc = action
                st.theta, st.k = theta, k_found
                st.p00 += 0.25
                if new_arc:
                    cell.arc += 1
                k, last, miss = k_found, None, 0
            else:  # ("gap", Gap)
                gap = action[1]
                self.gaps.add(gap)
                pending = gap
                st = good.copy()
                k, last, miss = good.k + 1, None, 0
        cell.snr_db = (10 * math.log10(max(snr_ema, 1e-3) / (2 * sig.N_SYNC))
                       if snr_ema is not None else float("nan"))  # fmt: skip
        return st

    def _earlier_path(self, prof: np.ndarray, win: np.ndarray, noise: float) -> float:
        """Shift (samples, < 0) to an earlier path in the averaged power profile, or 0.

        A local maximum earlier than 1.5 samples qualifies if it is within `first_path_rel_db`
        of the tracked path, `first_path_sidelobe` times above that path's own sidelobe there,
        and clear of the noise. The earliest qualifying one wins."""
        cfg = self.cfg
        zero = int(np.nonzero(win == 0)[0][0])
        top = prof[max(zero - cfg.interp, 0) : zero + cfg.interp + 1].max()
        floor = 2 * sig.N_SYNC * noise
        side = self.sidelobe[win % self.sidelobe.size]
        rel = 10 ** (cfg.first_path_rel_db / 10)
        i = np.arange(1, win.size - 1)
        v = prof[i]
        ok = (
            (win[i] < -1.5 * cfg.interp)
            & (v >= prof[i - 1])
            & (v >= prof[i + 1])
            & (v >= rel * top)
            & (v >= cfg.first_path_sidelobe * side[i] * top)
            & (v >= 4 * floor)
        )
        if ok.any():
            j = int(i[np.argmax(ok)])  # the earliest qualifying peak
            return (win[j] + float(_parabola(prof[j - 1], prof[j], prof[j + 1]))) / cfg.interp
        return 0.0

    def _relocate(self, cell: CellTrack, st: State, kk: int, good: State | None, last):
        """Search for the cell near its prediction after a loss of lock. Returns ("lost",),
        ("found", k, theta, new_arc) or ("gap", Gap)."""
        cfg, fs, L = self.cfg, self.fs, self.L
        n = int(cfg.acq_ms * 1e-3 * fs)
        f0 = max(self.file_index(cell.n0 + kk * L + st.theta - L), self.seg.start)
        if f0 + n > min(self.seg.stop, self.cap.n_samples):
            return ("lost",)
        c0 = int(self.gaps.to_corrected(np.int64(f0)))
        match = [
            f for f in search(self.cap.read(f0, n), c0, fs, cell.fc, cfg) if f.pci == cell.pci
        ]
        if not match:
            return ("lost",)
        b = match[0].boundary  # a subframe-0 boundary
        k_found = 2 * round((b - cell.n0 - st.theta) / (2 * L))
        theta_at = st.at(k_found, L)
        resid = b - cell.n0 - k_found * L - theta_at
        if abs(resid) < 0.5:
            return ("found", k_found, theta_at + resid, False)
        jump = -int(round(resid))  # > 0: arrives early, as every cell does after a drop
        at = (
            self.file_index(last.c_ref + self.pss_off - self.backoff + self.n_u) + 1
            if last is not None
            else f0
        )
        n_drop, ambiguous = jump % (2 * L), True  # the signal only sizes a drop modulo a frame
        n_host = None
        if self.cap.buffers is not None:
            n_host = _host_gap(self.cap.buffers, fs, at, f0 + n)
            if n_host is not None and n_host > 0:
                n_drop = n_host + int((jump - n_host + L) % (2 * L) - L)
                ambiguous = False
        host_stalled = n_host is not None and n_host >= L  # well beyond the stamps' jitter
        path_moved = abs(jump) <= cfg.max_path_jump_us * 1e-6 * fs and not host_stalled
        if path_moved or n_drop <= 0 or good is None:
            # Not a drop: the cell came back somewhere else (another path, or a reused PCI).
            return ("found", k_found, theta_at + resid, True)
        return ("gap", Gap(at=at, n=n_drop, until=at, ambiguous=ambiguous))


def _host_gap(buffers: np.ndarray, fs: float, f_lo: int, f_hi: int) -> int | None:
    """Samples missing between USB buffers in file range [f_lo, f_hi], from the host stamps."""
    idx, t = buffers[:, 0], buffers[:, 1]
    sel = np.nonzero((idx[1:] >= f_lo) & (idx[:-1] <= f_hi))[0]
    if sel.size == 0:
        return None
    excess = (t[sel + 1] - t[sel]) - (idx[sel + 1] - idx[sel]) * 1e9 / fs
    return int(round(float(excess.max()) * fs / 1e9))
