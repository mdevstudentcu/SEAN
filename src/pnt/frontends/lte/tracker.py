"""LTE cell search and PSS/SSS time-of-arrival tracking on RTL-SDR captures (clean-room).

Implemented from 3GPP TS 36.211 and textbook estimation theory; no third-party LTE code.
Pipeline, per carrier segment of a capture (`capture.Segment`):

1. **Search** (`search`): FFT cross-correlation with the three PSS Zadoff-Chu roots over a grid of
   carrier offsets (±`max_ppm`), folded over 5 ms half-frames and summed non-coherently (or,
   with `acq_coherent`, coherently in blocks, for cells near a strong one, #131). Peaks above a
   peak-to-mean threshold are PSS candidates.
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
   the code rate are the same clock (`rx_clock` in the measurement meta). With
   `track_coherent`, a cell found too weak for single epochs is tracked in coherent blocks of
   half-frames instead (`_Track.run_coherent`).
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
    # Smallest 1σ given to the search's carrier offset, TBC (#183). The SSS-to-PSS phase it
    # comes from assumes the PSS is the cell's own: in a frame-synchronised network every cell
    # sharing the PSS root (N_ID2) adds to it, and eNBs need not send PSS and SSS through one
    # antenna. On 20261110-lte-outside-5145 that phase was 0.2 to 0.8 rad off, so the offset
    # was up to 1,700 Hz wrong while its own 1σ said 20 to 360 Hz. With this floor the loop
    # takes its rate from the code first and carrier aiding (`carrier_lock_hz`) starts on the
    # right 200 Hz alias.
    search_cfo_sigma_hz: float = 1000.0
    # Per-epoch weight of the running PSS-to-SSS weight average (`_Track.run`), TBC: 20 epochs
    # (0.1 s), short against the beat of two cells sharing a PSS root (#183).
    pss_weight_alpha: float = 0.05
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
    # An earlier path's PSS-to-SSS power ratio must match the tracked path's within this, TBC.
    # #183, 20261110-1305-lte-outside: PCI 268's own path had PSS/SSS 0.7; the PSS of PCI 244,
    # 3 µs ahead on the same root, 3.7 (7 dB more).
    first_path_ratio_db: float = 3.0
    # And it must clear this many times the profile's interference floor, TBC: the mean power
    # of the averaged delay profile (its median over the whole cyclic grid, / ln 2). The
    # reserved-bin noise does not see the other cells' PSS and SSS, which arrive with ours in a
    # frame-synchronised network and correlate with our sequences at every delay; being static,
    # that floor does not average down, and its bins are exponential: 10x its mean is passed by
    # chance with p 4.5e-5 per bin. Without it, on the real static captures 20261111-0151 and
    # -0233, a faded cell moved 1.6 to 7.6 samples earlier every 200 ms onto that floor: 351
    # first-path moves in 600 s on 0151, each a new arc, the "re-acquisition" steps of #214.
    first_path_floor: float = 10.0
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
    # --- near-far (#131): off by default, every value below TBC ---
    # Half-frames summed coherently in the search (1: today's non-coherent fold; 15 is the
    # whole 80 ms window). The phase step between half-frames is found by an FFT across them,
    # so no carrier prior is needed, but the channel must hold still over the block: assumed
    # true for a static receiver (no capture yet says so); a receiver moving at v in multipath
    # decorrelates in about 9 / (16 π v / λ), 6 ms at 10 m/s (Clarke's model), so not there.
    # With it on, the SSS check also fits one phase reference across the whole window.
    acq_coherent: int = 1
    # PSS candidate gate when acq_coherent > 1. Below the noise: on 100 noise-only 80 ms
    # windows (acq_coherent 15) the largest coherent peak-to-mean was 5.4. The SSS gate
    # (`sss_peak_to_mean`) rejects what passes: the largest SSS score of any candidate that was
    # not a sent cell, over those windows and 100 with one strong cell, was 5.9.
    acq_coherent_peak_to_mean: float = 5.0
    # Candidates per root when acq_coherent > 1: a strong cell's PSS sidelobes reach a peak-to-
    # mean of 39 there and outrank a cell 14 dB down (4th to 14th of its root at -14 to -16 dB),
    # so a cap of 6 drops it. Each costs one SSS check.
    acq_coherent_max_cells_per_root: int = 30
    # Half-frames per coherent block when tracking a weak cell (1: off). A cell whose search
    # SNR, as a per-epoch post-correlation SNR over 124 elements, is below
    # `track_coherent_below_db` is tracked by `_Track.run_coherent`.
    track_coherent: int = 1
    track_coherent_below_db: float = 14.0
    track_coherent_snr_db: float = 13.0  # block post-correlation SNR to accept an epoch


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
    n_sync: float = 2 * sig.N_SYNC  # sync elements' worth combined: snr_post / n_sync is per RE


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
    m = min(max(cfg.acq_coherent, 1), h_count)
    threshold = cfg.acq_peak_to_mean if m == 1 else cfg.acq_coherent_peak_to_mean
    cap = cfg.max_cells_per_root if m == 1 else cfg.acq_coherent_max_cells_per_root
    for n_id2 in range(3):
        tf = _pss_spectra(fs, nfft, tuple(bins), n_id2)  # (bins, nfft), conjugated
        corr = sp_fft.ifft(xf[None, :] * tf, axis=1, workers=wk)[:, :n_valid]
        if m == 1:
            fold = (corr.real**2 + corr.imag**2).reshape(bins.size, h_count, L).sum(axis=1)
        else:
            fold = _coherent_fold(corr, bins.size, h_count, L, m, wk)
        metric[n_id2] = fold / fold.mean(axis=1, keepdims=True)
    sidelobe_mask = max(3, round(2 * fs / 1e6))  # ±~1 chip
    fetch = lambda idx: x[idx - c0]  # noqa: E731
    found: list[Found] = []
    for n_id2 in range(3):
        mt = metric[n_id2].copy()
        for _ in range(cap):
            b, j = np.unravel_index(np.argmax(mt), mt.shape)
            peak = mt[b, j]
            if peak < threshold:
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


def _coherent_fold(corr: np.ndarray, n_bins: int, h_count: int, L: int, m: int, workers: int):
    """Fold of the PSS correlation over blocks of `m` half-frames summed coherently.

    Within a block the cell's correlation turns by a fixed phase step per half-frame (its carrier
    offset left over after the bin, modulo the 200 Hz half-frame rate). An FFT across the block's
    half-frames, zero-padded 2x, sums them at every step at once; the best step is kept per delay
    and the blocks are added in power. Against noise-like interference the peak grows `m` times
    faster than the mean, which non-coherent folding does not give."""
    nb = h_count // m
    c = corr[:, : nb * m * L].reshape(n_bins, nb, m, L)
    spec = sp_fft.fft(c, n=2 * m, axis=2, workers=workers)
    pw = spec.real**2 + spec.imag**2
    return pw.max(axis=2).sum(axis=1) / m


def _coherent_reference(sub: np.ndarray, pad: int = 4):
    """A clean per-row phase reference from rows (half-frames) of a profile near its peak.

    `sub` is (rows, delays). Returns (delay index, model reference per row, phase step per row
    in cycles): the best common delay and the reference A·exp(j2π step·row) that fits the rows
    coherently, found by a zero-padded FFT across rows."""
    rows = sub.shape[0]
    spec = np.fft.fft(sub, n=pad * rows, axis=0)
    fi, gi = np.unravel_index(np.argmax(np.abs(spec)), spec.shape)
    step = fi / (pad * rows)
    w = np.exp(2j * np.pi * step * np.arange(rows))
    a = spec[fi, gi] / rows
    return int(gi), a * w, step


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
    if cfg.acq_coherent > 1:
        # Weak cells: one delay for all half-frames and a phase reference fitted across them,
        # instead of each half-frame's own noisy peak.
        gi, ref, _ = _coherent_reference(sub)
        d = np.full(sub.shape[0], gate[gi] / cfg.interp)
    else:
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
        sigma_f_hz=float(max(1.5 * sigma_f, cfg.search_cfo_sigma_hz)),
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

    def measure(
        self,
        n_id1: int,
        n_id2: int,
        bounds: np.ndarray,
        ks: np.ndarray,
        f_hz: float,
        w: np.ndarray | None = None,
    ):
        """Delay profiles (rows: epochs) of SSS + w · PSS at the given half-frame boundaries,
        the reserved-bin noise power per epoch, and the PSS and SSS products (rows: epochs, 62
        each). `w` is the PSS's complex weight per subframe (index k % 2; default 1 for both).
        Even k is subframe 0."""
        yp, rp = window_spectra(self.fetch, bounds + self.pss_off, self.fs, f_hz, self.backoff)
        ys, rs = window_spectra(self.fetch, bounds + self.sss_off, self.fs, f_hz, self.backoff)
        tbl = sig.sss_table(n_id2)[:, n_id1]
        zp = yp * np.conj(sig.pss(n_id2))[None, :]
        zs = ys * tbl[ks % 2]
        z = zs + zp if w is None else zs + w[ks % 2][:, None] * zp
        noise = 0.5 * (np.mean(np.abs(rp) ** 2, axis=1) + np.mean(np.abs(rs) ** 2, axis=1))
        return delay_profile(z, self.fs, self.cfg.interp), noise, zp, zs

    def file_index(self, c: float) -> int:
        return int(self.gaps.to_file(np.int64(math.floor(c)))[0])

    def weak(self, snr_db: float | None) -> bool:
        """Whether a cell found at `snr_db` (per resource element) goes to coherent blocks."""
        if self.cfg.track_coherent <= 1 or snr_db is None or not math.isfinite(snr_db):
            return False
        return snr_db + 10 * math.log10(2 * sig.N_SYNC) < self.cfg.track_coherent_below_db

    def run(
        self,
        cell: CellTrack,
        n_id1: int,
        n_id2: int,
        st: State,
        c_stop: float,
        snr_db: float | None = None,
    ) -> State:
        """Track `cell` from state `st` (its next epoch is st.k) to corrected index `c_stop`, or
        until it has been gone for `lost_s`. Appends epochs to `cell.epochs`. A cell the search
        found at `snr_db` below the weak-cell limit goes to `run_coherent` instead."""
        if self.weak(snr_db):
            return self.run_coherent(cell, n_id1, n_id2, st, c_stop)
        cfg, fs, L, fc = self.cfg, self.fs, self.L, cell.fc
        grid = self.n_u * cfg.interp
        gi = int(round(cfg.gate_samples * cfg.interp))
        gate = np.arange(-gi, gi + 1)
        win = np.arange(-int(round(cfg.first_path_us * 1e-6 * fs * cfg.interp)), gi + 1)
        # First-path profiles: combined, SSS alone and PSS alone (see `_earlier_path`)
        prof_acc, prof_n, interf_acc = np.zeros((3, win.size)), 0, 0.0
        e_win = np.exp((2j * np.pi / self.n_u) * np.outer(_K, win / cfg.interp))
        detect = 10 ** (cfg.detect_snr_db / 10)
        noise_ema = snr_ema = re_ema = None
        miss, settled = 0, False
        # The PSS is shared by every cell with this N_ID2, and in a frame-synchronised network
        # they all arrive together; eNBs need not send PSS and SSS through one antenna either.
        # Only the SSS is the cell's own, so the PSS is added with a weight per subframe:
        # w = E[S conj(P)] / E[|P|² - noise], S and P the SSS and PSS correlations at the
        # predicted delay.
        # A cell alone on its root gets w = 1 (both signals, as before); one whose PSS is mostly
        # another cell's gets w near 0 (its SSS alone). `pss_weight_alpha` sets the average.
        w = np.ones(2, np.complex128)
        w_num = np.zeros(2, np.complex128)
        w_den = np.zeros(2)
        w_n = np.zeros(2, np.int64)
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
            prof, noise, zp, zs = self.measure(n_id1, n_id2, bounds, ks, f_used, w)
            wk = w[ks % 2]
            n_sync = sig.N_SYNC * np.abs(1 + np.abs(wk)) ** 2 / (1 + np.abs(wk) ** 2)
            sub = np.abs(prof[:, gate % grid])
            i = np.argmax(sub, axis=1)
            rows = np.arange(sub.shape[0])
            # PSS and SSS correlations at the predicted delay (the gate's centre), every epoch: at
            # the peak would follow whichever cell's PSS is strongest.
            p_pk, s_pk = zp.sum(axis=1), zs.sum(axis=1)
            edge = (i == 0) | (i == gate.size - 1)
            a = sub[rows, np.maximum(i - 1, 0)]
            b = sub[rows, i]
            c = sub[rows, np.minimum(i + 1, gate.size - 1)]
            d = (gate[i] + _parabola(a, b, c)) / cfg.interp
            phase = np.angle(prof[rows, gate[i] % grid])
            power = np.stack(
                [
                    np.abs(prof[:, win % grid]) ** 2,
                    np.abs(zs @ e_win) ** 2,
                    np.abs(zp @ e_win) ** 2,
                ],
                axis=1,
            )
            # Interference floor per epoch: the profile's mean power from its median over the
            # whole grid, at whole samples (independent bins), see `first_path_floor`.
            interf = np.median(np.abs(prof[:, :: cfg.interp]) ** 2, axis=1) / math.log(2)
            if noise_ema is None:
                noise_ema = float(np.median(noise))
            action = None
            for r in range(ks.size):
                kk = int(ks[r])
                noise_ema = 0.95 * noise_ema + 0.05 * float(noise[r])
                n_noise = sig.N_SYNC * (1 + abs(wk[r]) ** 2)  # noise elements, weighted
                par, a_w = kk % 2, cfg.pss_weight_alpha
                w_n[par] += 1
                w_num[par] = (1 - a_w) * w_num[par] + a_w * s_pk[r] * np.conj(p_pk[r])
                w_den[par] = (1 - a_w) * w_den[par] + a_w * (
                    abs(p_pk[r]) ** 2 - sig.N_SYNC * noise_ema
                )
                snr_post = float(b[r] ** 2 / (n_noise * noise_ema)) - 1.0
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
                snr_re = snr_post / float(n_sync[r])
                re_ema = snr_re if re_ema is None else 0.9 * re_ema + 0.1 * snr_re
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
                    n_sync=float(n_sync[r]),
                )
                if settled:
                    cell.epochs.append(ep)
                last, good, last_seen = ep, st.copy(), float(bounds[r])
                prof_acc += power[r]
                interf_acc += float(interf[r])
                prof_n += 1
                if prof_n >= cfg.first_path_epochs:
                    shift = self._earlier_path(
                        prof_acc / prof_n, win, noise_ema, interf_acc / prof_n
                    )
                    prof_acc[:], prof_n, interf_acc = 0, 0, 0.0
                    if shift:
                        st.theta += shift
                        if settled:
                            cell.arc += 1
                        last = None
                        action = ("continue", kk + 1)
                        break
                    settled = True
            # New PSS weights for the next block: |w| <= 1, and 1 until both subframes have data.
            if np.all(w_n > 0):
                w = w_num / np.maximum(w_den, np.abs(w_num) + 1e-30)
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
        cell.snr_db = (10 * math.log10(max(re_ema, 1e-5))
                       if re_ema is not None else float("nan"))  # fmt: skip
        return st

    def run_coherent(
        self, cell: CellTrack, n_id1: int, n_id2: int, st: State, c_stop: float
    ) -> State:
        """Track a weak cell in blocks of `track_coherent` half-frames summed coherently.

        Each block's PSS+SSS products (124 per half-frame) are summed across its half-frames at
        the phase step an FFT across them finds (the carrier offset left after the loop's,
        modulo 200 Hz), so the block's post-correlation SNR is `track_coherent` times one
        epoch's. One Epoch per block, referred to the block's middle half-frame; its σ comes
        from the block's SNR, so blocks are independent and `emit` weights them as such. Not
        done here, unlike `run`: carrier aiding and doppler (the phase is not tracked across
        blocks), the first-path check and re-search after a loss (the next periodic search
        picks a lost cell up again)."""
        cfg, fs, L = self.cfg, self.fs, self.L
        m = cfg.track_coherent
        grid = self.n_u * cfg.interp
        gi = int(round(cfg.gate_samples * cfg.interp))
        gate = np.arange(-gi, gi + 1)
        detect = 10 ** (cfg.track_coherent_snr_db / 10)
        alpha = min(0.05 * m, 0.5)  # noise average: about as fast per second as `run`'s
        noise_ema = snr_ema = None
        last_seen = cell.n0 + st.k * L + st.theta
        k = st.k
        while True:
            n_b = int(np.clip(0.3 / (3 * math.sqrt(max(st.p11, 0.0)) * L * m + 1e-15), 1, 25))
            ks = np.arange(k, k + n_b * m)
            bounds = cell.n0 + ks * L + st.theta + st.nu * (ks - st.k) * L
            if bounds[0] > c_stop or bounds[0] - last_seen > cfg.lost_s * fs:
                break
            k = int(ks[-1]) + 1
            ok = (self.usable(bounds) & (bounds <= c_stop)).reshape(n_b, m).all(axis=1)
            if not ok.any():
                continue
            rows = np.repeat(ok, m)
            kb, bb = ks[rows].reshape(-1, m), bounds[rows].reshape(-1, m)
            f_used = -st.nu * cell.fc
            prof, noise, _, _ = self.measure(n_id1, n_id2, bounds[rows], ks[rows], f_used)
            sub = prof[:, gate % grid].reshape(-1, m, gate.size)
            amp = np.abs(np.fft.fft(sub, n=4 * m, axis=1))  # (blocks, phase steps, delays)
            noise_b = noise.reshape(-1, m).mean(axis=1)
            for r in range(amp.shape[0]):
                fi, i = np.unravel_index(np.argmax(amp[r]), amp[r].shape)
                nb_ = float(noise_b[r])
                noise_ema = nb_ if noise_ema is None else (1 - alpha) * noise_ema + alpha * nb_
                b = float(amp[r, fi, i])
                snr_post = b**2 / (2 * sig.N_SYNC * m * noise_ema) - 1.0
                if i == 0 or i == gate.size - 1 or snr_post < detect:
                    continue
                d = gate[i] + float(_parabola(amp[r, fi, i - 1], b, amp[r, fi, i + 1]))
                d /= cfg.interp
                k_ref = int(kb[r, m // 2])
                st.predict(k_ref, L, fs, self.q)
                # The block's mean offset; the predicted offsets are linear in k, so this is the
                # offset at the block's mean half-frame (k_ref, within half a half-frame).
                theta_meas = float(np.mean(bb[r] - cell.n0 - kb[r] * L)) + d
                sigma = fs / (2 * math.pi * BETA_HZ * math.sqrt(2 * snr_post))
                r_code = (cfg.sigma_scale * sigma) ** 2
                if abs(theta_meas - st.theta) > 5 * math.sqrt(st.s(0, r_code)) + 0.25:
                    continue
                snr_ema = snr_post if snr_ema is None else 0.8 * snr_ema + 0.2 * snr_post
                st.update(0, theta_meas, r_code)
                n_ref = float(np.mean(bb[r]) + 0.5 * (self.sss_off + self.pss_off) + self.n_u / 2)
                cell.epochs.append(
                    Epoch(
                        k=k_ref,
                        c_ref=cell.n0 + k_ref * L + st.theta,
                        theta_meas=theta_meas,
                        nu=st.nu,
                        sigma=sigma,
                        snr_post=snr_post / m,  # per half-frame, as `run` stores it
                        psi=0.0,
                        n_ref=n_ref,
                        locked=False,
                        arc=cell.arc,
                        n0=cell.n0,
                    )
                )
                last_seen = float(bb[r, 0])
        cell.snr_db = (10 * math.log10(max(snr_ema, 1e-3) / (2 * sig.N_SYNC * m))
                       if snr_ema is not None else float("nan"))  # fmt: skip
        return st

    def _earlier_path(
        self, profs: np.ndarray, win: np.ndarray, noise: float, interf: float = 0.0
    ) -> float:
        """Shift (samples, < 0) to an earlier path in the averaged power profiles, or 0.

        `profs` holds the tracked (combined), SSS-only and PSS-only power profiles. A local
        maximum of the combined one earlier than 1.5 samples qualifies if it is within
        `first_path_rel_db` of the tracked path, `first_path_sidelobe` times above that path's
        own sidelobe there, and clear of the noise. The earliest qualifying one wins. The first
        two conditions must also hold in the SSS alone and in the PSS alone, and the PSS-to-SSS
        power ratio there must be the tracked path's within `first_path_ratio_db`: a path of
        this cell is a copy of both, while an earlier cell sharing the PSS root is mostly PSS
        and another cell's SSS sidelobe mostly SSS (#183).

        Two more guards: the peak must clear `first_path_floor` times `interf`, the combined
        profile's interference floor (mean power per delay), and it must be the largest value
        within the code gate around it, so that the loop can track it once moved there. A peak
        on the tracked path's skirt cannot be: on 20261111-0151 PCI 92 moved -2.4 samples onto
        one, slid back, was re-found on its old path and moved again, 4 times in 7 s."""
        cfg = self.cfg
        prof = profs[0]
        zero = int(np.nonzero(win == 0)[0][0])
        near = slice(max(zero - cfg.interp, 0), zero + cfg.interp + 1)
        top = prof[near].max()
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
            & (v >= cfg.first_path_floor * interf)
        )
        gi = int(round(cfg.gate_samples * cfg.interp))
        pad = np.r_[np.zeros(gi), prof, np.zeros(gi)]  # pad[i + gi] is prof[i]
        ok &= v >= np.lib.stride_tricks.sliding_window_view(pad, 2 * gi + 1)[i].max(axis=1)
        for one in profs[1:]:  # and in the SSS and the PSS alone
            top_1 = one[near].max()
            ok &= (one[i] >= rel * top_1) & (one[i] >= cfg.first_path_sidelobe * side[i] * top_1)
        # with the PSS-to-SSS power ratio of the tracked path
        ratio = (profs[2, i] / np.maximum(profs[1, i], 1e-30)) / (
            profs[2, near].max() / max(profs[1, near].max(), 1e-30)
        )
        ok &= np.abs(10 * np.log10(np.maximum(ratio, 1e-30))) <= cfg.first_path_ratio_db
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
