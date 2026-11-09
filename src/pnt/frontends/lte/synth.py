"""Synthetic LTE downlink baseband, as an RTL-SDR would record it (tests and analysis only).

Each tower sends FDD frames (normal CP, 6 resource blocks = 1.4 MHz, 72 subcarriers) with the PSS
and SSS of its PCI (TS 36.211) and random QPSK on every other resource element. The waveform is
evaluated exactly at each sample's transmit time, so delays may be fractional and time-varying
without an interpolation filter. The receiver is one dongle whose single TCXO is `clock_ppm`
fast: its local oscillator sits `clock_ppm` above the carrier, and its sample clock runs
`clock_ppm` fast (ADR-0018 hardware: tuner and ADC share the crystal).

For a sample taken at local index n (true time t = n / (fs (1 + ε))), a path of delay
τ(t) = τ0 + τ̇ t adds  a · s(t - τ(t)) · exp(-j 2π fc (τ(t) + ε t))  to the baseband.

`snr_db` is the in-band SNR of the first tower's first path: its power over the noise in the
72-subcarrier band (1.08 MHz). It equals the SNR per resource element.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pnt.frontends.lte import signals as sig

C = 299_792_458.0
N_SC = 36  # subcarriers each side of DC (6 resource blocks)
_FILLER_FRAMES = 8  # distinct QPSK frames, cycled


@dataclass(frozen=True)
class Path:
    delay_s: float = 0.0  # extra delay after the tower's first path
    power_db: float = 0.0  # relative to the first path
    phase: float = 0.0


@dataclass(frozen=True)
class Tower:
    """One cell as received: `delay_s` folds range and the tower's frame timing together."""

    pci: int
    delay_s: float
    delay_rate: float = 0.0  # dτ/dt, s/s: range rate / c
    power_db: float = 0.0  # relative to the reference level that `snr_db` is quoted at
    phase: float = 0.0
    echoes: tuple[Path, ...] = ()

    def boundary_sample(self, frame: int, fs: float, clock_ppm: float) -> float:
        """Local sample index at which the start of frame `frame` (first path) arrives."""
        t = (frame * sig.FRAME_S + self.delay_s) / (1.0 - self.delay_rate)
        return t * (1.0 + clock_ppm * 1e-6) * fs

    def range_rate_dimless(self, clock_ppm: float) -> float:
        """d(local arrival time)/d(local time) - 1: the pseudorange rate over c."""
        return (1.0 + clock_ppm * 1e-6) / (1.0 - self.delay_rate) - 1.0


def _symbol_table(pci: int, rng: np.random.Generator) -> np.ndarray:
    """(73, frames * 140) resource grid, rows k = -36..36, for `_FILLER_FRAMES` frames."""
    n_id1, n_id2 = sig.split_pci(pci)
    n_sym = _FILLER_FRAMES * sig.SYMBOLS_PER_FRAME
    qpsk = (rng.choice([-1.0, 1.0], (2, n_sym, 2 * N_SC + 1)) / math.sqrt(2)).astype(np.float64)
    grid = qpsk[0] + 1j * qpsk[1]
    grid[:, N_SC] = 0  # DC
    ks = sig.sync_subcarriers() + N_SC
    for f in range(_FILLER_FRAMES):
        for slot, sf in ((0, 0), (10, 5)):
            base = f * sig.SYMBOLS_PER_FRAME + slot * sig.SYMBOLS_PER_SLOT
            for sym, values in ((sig.SSS_SYMBOL, sig.sss(n_id1, n_id2, sf)),
                              (sig.PSS_SYMBOL, sig.pss(n_id2))):  # fmt: skip
                grid[base + sym] = 0  # reserved subcarriers stay empty
                grid[base + sym, ks] = values
    return np.ascontiguousarray(grid.T)


def _baseband(table: np.ndarray, u: np.ndarray, fs: float) -> np.ndarray:
    """The tower's transmitted baseband at transmit times `u` (s, any values).

    Each OFDM symbol is one inverse FFT of its resource elements with the symbol's fractional
    sample offset applied as a phase ramp, so delays are exact to well under 1e-3 sample. The
    ppm-level stretch of the time axis inside one 67 µs symbol is neglected."""
    n_u = sig.useful_length(fs)
    frame = np.floor(u / sig.FRAME_S)
    q = (u - frame * sig.FRAME_S) * sig.TS_HZ  # Ts into the frame
    slot = np.minimum((q // sig.SLOT_TS).astype(np.int64), sig.SLOTS_PER_FRAME - 1)
    q = q - slot * sig.SLOT_TS
    first = sig.CP0_TS + sig.N_USEFUL_TS
    sym = np.where(q < first, 0, 1 + ((q - first) // (sig.CP_TS + sig.N_USEFUL_TS)))
    sym = np.minimum(sym.astype(np.int64), sig.SYMBOLS_PER_SLOT - 1)
    useful = np.where(
        sym == 0, sig.CP0_TS, first + (sym - 1) * (sig.CP_TS + sig.N_USEFUL_TS) + sig.CP_TS
    )
    x = (q - useful) * (fs / sig.TS_HZ)  # samples after the useful start (< 0 in the CP)
    g = ((frame.astype(np.int64) % _FILLER_FRAMES) * sig.SYMBOLS_PER_FRAME
         + slot * sig.SYMBOLS_PER_SLOT + sym)  # fmt: skip
    # One fractional offset per symbol occurrence (a new occurrence starts where g changes).
    start = np.r_[0, np.nonzero(np.diff(g) != 0)[0] + 1]
    occ = np.cumsum(np.r_[0, np.diff(g) != 0])
    delta = x[start] - np.floor(x[start])
    m = np.round(x - delta[occ]).astype(np.int64)
    k = np.arange(-N_SC, N_SC + 1)
    spec = np.zeros((start.size, n_u), np.complex128)
    spec[:, k % n_u] = table[:, g[start]].T * np.exp(2j * np.pi * np.outer(delta, k) / n_u)
    wave = np.fft.ifft(spec, axis=1) * n_u
    return wave[occ, m % n_u]


def synthesize(
    towers: list[Tower],
    duration_s: float,
    *,
    fs: float = 1.92e6,
    fc: float = 875e6,
    clock_ppm: float = 0.0,
    snr_db: float | None = 10.0,
    drops: tuple[tuple[int, int], ...] = (),
    seed: int = 0,
    chunk: int = 1 << 17,
) -> np.ndarray:
    """Complex baseband samples as recorded (before 8-bit quantisation).

    `drops` are (file index, samples dropped before it), like a USB overrun: the file skips that
    many local samples there. `snr_db=None` gives no noise."""
    rng = np.random.default_rng(seed)
    eps = clock_ppm * 1e-6
    n_out = round(duration_s * fs)
    local = np.arange(n_out, dtype=np.float64)
    for at, n in sorted(drops):
        local[at:] += n
    tables = [_symbol_table(t.pci, rng) for t in towers]
    x = np.zeros(n_out, np.complex128)
    for s in range(0, n_out, chunk):
        t = local[s : s + chunk] / (fs * (1.0 + eps))  # true time of each sample
        for tower, table in zip(towers, tables, strict=True):
            paths = (Path(0.0, 0.0, 0.0), *tower.echoes)
            for p in paths:
                tau = tower.delay_s + p.delay_s + tower.delay_rate * t
                amp = 10 ** ((tower.power_db + p.power_db) / 20)
                carrier = np.exp(
                    -2j * np.pi * (fc * (tau + eps * t) % 1.0) - 1j * (tower.phase + p.phase)
                )
                x[s : s + chunk] += amp * carrier * _baseband(table, t - tau, fs)
    if snr_db is not None:
        var = fs / (sig.SUBCARRIER_HZ * 10 ** (snr_db / 10))
        x += rng.normal(0, math.sqrt(var / 2), (n_out, 2)) @ np.array([1, 1j])
    return x.astype(np.complex64)
