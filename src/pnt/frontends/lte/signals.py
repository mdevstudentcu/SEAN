"""LTE downlink sync signals and frame timing, from 3GPP TS 36.211 (clean-room).

Only the broadcast synchronisation signals are generated here (ADR-0011): the primary (PSS,
§6.11.1) and secondary (SSS, §6.11.2) synchronisation signals of FDD frame structure type 1 with
the normal cyclic prefix (§4.1, §6.12). Nothing here touches user traffic.

Conventions:
- Subcarrier index `k` is relative to the carrier centre (DC = 0, which LTE leaves empty), so the
  62 sync subcarriers are k = -31..-1, 1..31 and the 10 reserved ones are |k| = 32..36 (§6.11.1.2).
- Times inside the frame are in basic time units Ts = 1 / 30.72 MHz (§4).
"""

from __future__ import annotations

from functools import cache

import numpy as np

TS_HZ = 30.72e6  # 1 / Ts (§4)
SUBCARRIER_HZ = 15e3  # Δf, normal CP
FRAME_S = 10e-3
HALF_FRAME_S = 5e-3
N_USEFUL_TS = 2048  # useful OFDM symbol length, Ts
CP0_TS, CP_TS = 160, 144  # normal CP: first symbol of a slot, the other six (Table 6.12-1)
SLOT_TS = 15360
SYMBOLS_PER_SLOT = 7
SLOTS_PER_FRAME = 20
SYMBOLS_PER_FRAME = SYMBOLS_PER_SLOT * SLOTS_PER_FRAME
N_SYNC = 62  # PSS/SSS length
PSS_ROOTS = (25, 29, 34)  # Zadoff-Chu root for N_ID2 = 0, 1, 2 (Table 6.11.1.1-1)
N_ID1_COUNT = 168
# The sync signals sit in the last two symbols of slots 0 and 10 (FDD, §6.11.1.2, §6.11.2.2):
SSS_SYMBOL, PSS_SYMBOL = 5, 6


def symbol_start_ts(sym: int) -> int:
    """Start (CP included) of symbol `sym` of a slot, in Ts from the slot start."""
    return 0 if sym == 0 else CP0_TS + N_USEFUL_TS + (sym - 1) * (CP_TS + N_USEFUL_TS)


def useful_start_ts(sym: int) -> int:
    """Start of the useful (post-CP) part of symbol `sym`, in Ts from the slot start."""
    return symbol_start_ts(sym) + (CP0_TS if sym == 0 else CP_TS)


# Useful-part starts of the SSS and PSS, in Ts after the half-frame boundary (slot 0 or 10).
SSS_OFFSET_TS = useful_start_ts(SSS_SYMBOL)  # 11120
PSS_OFFSET_TS = useful_start_ts(PSS_SYMBOL)  # 13312


def sync_subcarriers() -> np.ndarray:
    """Subcarrier index k of sequence element n = 0..61: k = n - 31, skipping DC (§6.11.1.2)."""
    n = np.arange(N_SYNC)
    return np.where(n < 31, n - 31, n - 30)


def reserved_subcarriers() -> np.ndarray:
    """The 10 subcarriers next to the sync signals that carry nothing in its symbols."""
    return np.array([-36, -35, -34, -33, -32, 32, 33, 34, 35, 36])


def pss(n_id2: int) -> np.ndarray:
    """Frequency-domain PSS d_u(n), n = 0..61: the length-63 Zadoff-Chu sequence with its
    middle (DC) element removed (§6.11.1.1)."""
    u = PSS_ROOTS[n_id2]
    n = np.arange(N_SYNC)
    m = np.where(n < 31, n * (n + 1), (n + 1) * (n + 2))
    return np.exp(-1j * np.pi * u * m / 63)


def _m_sequence(taps: tuple[int, ...]) -> np.ndarray:
    """±1 sequence 1 - 2x(i), x(i+5) = sum of x(i+t) for t in `taps` mod 2, x(0..4) = 0,0,0,0,1."""
    x = [0, 0, 0, 0, 1] + [0] * 26
    for i in range(26):
        x[i + 5] = sum(x[i + t] for t in taps) % 2
    return 1 - 2 * np.array(x)


_S_TILDE = _m_sequence((2, 0))  # x(i+5) = x(i+2) + x(i)
_C_TILDE = _m_sequence((3, 0))  # x(i+5) = x(i+3) + x(i)
_Z_TILDE = _m_sequence((4, 2, 1, 0))  # x(i+5) = x(i+4) + x(i+2) + x(i+1) + x(i)


def sss_indices(n_id1: int) -> tuple[int, int]:
    """(m0, m1) for group N_ID1 (§6.11.2.1, the formula behind Table 6.11.2.1-1)."""
    q_prime = n_id1 // 30
    q = (n_id1 + q_prime * (q_prime + 1) // 2) // 30
    m_prime = n_id1 + q * (q + 1) // 2
    m0 = m_prime % 31
    m1 = (m0 + m_prime // 31 + 1) % 31
    return m0, m1


def sss(n_id1: int, n_id2: int, subframe: int) -> np.ndarray:
    """SSS d(n), n = 0..61, for subframe 0 or 5 (§6.11.2.1). Real ±1."""
    if subframe not in (0, 5):
        raise ValueError("the SSS is sent in subframes 0 and 5 only")
    m0, m1 = sss_indices(n_id1)
    n = np.arange(31)
    s0 = _S_TILDE[(n + m0) % 31]
    s1 = _S_TILDE[(n + m1) % 31]
    c0 = _C_TILDE[(n + n_id2) % 31]
    c1 = _C_TILDE[(n + n_id2 + 3) % 31]
    z_m0 = _Z_TILDE[(n + m0 % 8) % 31]
    z_m1 = _Z_TILDE[(n + m1 % 8) % 31]
    d = np.empty(N_SYNC)
    if subframe == 0:
        d[0::2], d[1::2] = s0 * c0, s1 * c1 * z_m0
    else:
        d[0::2], d[1::2] = s1 * c0, s0 * c1 * z_m1
    return d


@cache
def sss_table(n_id2: int) -> np.ndarray:
    """All SSS for one N_ID2: shape (2, 168, 62), index [subframe 0 or 5 -> 0/1, N_ID1]."""
    return np.array([[sss(g, n_id2, sf) for g in range(N_ID1_COUNT)] for sf in (0, 5)])


def pci(n_id1: int, n_id2: int) -> int:
    """Physical cell identity, 0..503."""
    return 3 * n_id1 + n_id2


def split_pci(cell_id: int) -> tuple[int, int]:
    """(N_ID1, N_ID2) of a PCI."""
    if not 0 <= cell_id < 3 * N_ID1_COUNT:
        raise ValueError(f"PCI must be 0..503, not {cell_id}")
    return divmod(cell_id, 3)


def samples(ts: float, fs: float) -> float:
    """A duration in Ts, in samples at `fs` (may be fractional, e.g. at 2.4 MS/s)."""
    return ts * fs / TS_HZ


def useful_length(fs: float) -> int:
    """Samples in one useful OFDM symbol at `fs`; `fs` must be a multiple of 15 kHz."""
    n = fs / SUBCARRIER_HZ
    if abs(n - round(n)) > 1e-9:
        raise ValueError(f"sample rate {fs} Hz is not a multiple of 15 kHz")
    return round(n)


def half_frame_length(fs: float) -> int:
    """Samples in 5 ms at `fs` (must be whole)."""
    n = fs * HALF_FRAME_S
    if abs(n - round(n)) > 1e-6:
        raise ValueError(f"5 ms is not a whole number of samples at {fs} Hz")
    return round(n)


def sync_time_waveform(values: np.ndarray, fs: float, n: int | None = None) -> np.ndarray:
    """Useful part of one OFDM symbol carrying `values` on the 62 sync subcarriers, sampled at
    `fs`: sum_k X_k exp(j 2π k Δf t), t = m / fs (§6.12, without the CP)."""
    n = useful_length(fs) if n is None else n
    t = np.arange(n) / fs
    k = sync_subcarriers()
    return np.exp(2j * np.pi * SUBCARRIER_HZ * np.outer(t, k)) @ values
