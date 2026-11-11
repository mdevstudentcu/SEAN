"""The range sigma of a radio's LTE record from its SNR: ADR-0036's measured model (#147).

The front end reports a sigma from timing statistics, which can't see multipath; the challenge
sim's records report 2 m. #147: told that, the filters do worse with LTE than without it. With
`told_sigma_model="adr0036"` (estimators `ekf-measured-sigma`, `ekf-calibrated-measured-sigma`;
opt-in, ADR-0044) the EKF replaces the reported sigma of every pseudorange from a real
front end (one with `meta.rx_clock`, `meta.snr_db` and `meta.n_epochs`, as `pnt.frontends.lte`
and `sim/lte_front_end.py` write them) with the sum of two parts. Every value is TBC.

- White part, sized for a 10 Hz record of 20 epochs of 5 ms (ADR-0036 consequence 1, measured on
  static captures, `analysis/results/lte-measured-noise`): at SNR >= -8 dB the fit
  sigma^2 = 0.64^2 + 2.28^2 / SNR_lin (m); below it the measured bins, 12.4 m at -11 to -8 dB and
  24.7 m at -14 to -11 dB. Below -14 dB nothing was measured (TBD): 49.4 m, one more doubling, as
  the two measured bins double per 3 dB (TBC, chosen to be conservative). A record of n epochs
  averages n / 20 times as many, so its variance is scaled by 20 / n (white).
- Correlated part: sigma_corr 10 m with correlation time 3 s (ADR-0036 consequence 1, TBC; the
  same-eNB structure function at rest). ADR-0036 asks the filter to carry it as a Gauss-Markov
  state, never to average it down as white. Without such a state it is told as white with the
  variance that keeps an average honest: an average of N records spaced T apart, correlation
  rho = exp(-T / tau) between neighbours, has variance sigma_corr^2 (1 + rho) / (1 - rho) / N
  for large N. So each record carries sigma_corr^2 (1 + rho) / (1 - rho), T its own length:
  24.6 m for a 1 Hz record, 77 m for a 10 Hz one (the same information per second). It
  overstates the error of a single record (a filter using few records is told too little), and
  doesn't cover multipath larger than seen at rest (a moving receiver, ADR-0036 consequence 3).

A 1 Hz record is told 24.6 m for a strong cell, 25.8 m at -14 to -11 dB and 29.1 m below -14 dB:
the correlated part dominates once ten 10 Hz records are averaged.

Records from a real capture (`from_capture`: `meta.sample_index`, the record's place in its IQ
file, which `pnt.frontends.lte` writes and `sim/lte_front_end.py` leaves out) get this model by
default in the EKF (`capture_sigma_model`, ADR-0048 Proposed): the front end's own sigma (1 to 5 m
at high SNR) against double differences that wander 1 to 45 m kept GNSS out of the filter on
real sessions (#246). The sim's records keep their reported sigma unless `told_sigma_model` asks.
"""

from __future__ import annotations

import math

from msgspec.structs import replace

from pnt.core.measurement import Measurement

MODELS = ("adr0036",)

EPOCH_S = 0.005  # the front end's tracking epoch (meta.n_epochs counts these)
FIT_EPOCHS = 20  # the 10 Hz record the white model was measured on
FIT_MIN_SNR_DB = -8.0  # the fit holds from here up (TBC)
FLOOR_M, SNR_TERM_M = 0.64, 2.28  # sigma^2 = FLOOR^2 + SNR_TERM^2 / SNR_lin (TBC)
# (lowest SNR of the bin in dB, white sigma in m), highest first: measured bins, then TBC below
BINS = ((-11.0, 12.4), (-14.0, 24.7), (-math.inf, 49.4))
SIGMA_CORR_M = 10.0  # TBC: ADR-0036, the middle of the 4.9 to 18 m same-eNB S(1 s)
TAU_CORR_S = 3.0  # TBC: ADR-0036, S(tau) levels off between 1 and 10 s


def white_sigma_m(snr_db: float, n_epochs: int) -> float:
    """White range sigma (m) of a record of `n_epochs` 5 ms epochs at `snr_db`."""
    if snr_db >= FIT_MIN_SNR_DB:
        var = FLOOR_M**2 + SNR_TERM_M**2 / 10 ** (snr_db / 10)
    else:
        var = next(s for lo, s in BINS if snr_db >= lo) ** 2
    return math.sqrt(var * FIT_EPOCHS / n_epochs)


def corr_sigma_m(n_epochs: int) -> float:
    """The correlated part told as white for a record of `n_epochs` epochs (module docstring)."""
    rho = math.exp(-n_epochs * EPOCH_S / TAU_CORR_S)
    return SIGMA_CORR_M * math.sqrt((1 + rho) / (1 - rho))


def sigma_m(snr_db: float, n_epochs: int) -> float:
    """The range sigma (m) the model tells the filter: both parts together."""
    return math.hypot(white_sigma_m(snr_db, n_epochs), corr_sigma_m(n_epochs))


def from_capture(m: Measurement) -> bool:
    """Whether `m` came from a front end run on a real capture: it indexes its IQ file
    (`meta.sample_index`). The sim's front-end-shaped records have no file to index."""
    return "sample_index" in m.meta


def retold(m: Measurement, model: str) -> Measurement:
    """`m` with its sigma from `model`, if it is a pseudorange from a real front end with the SNR
    and length the model needs; otherwise `m` unchanged."""
    if model not in MODELS:
        raise ValueError(f"told_sigma_model must be one of {MODELS}, not {model!r}")
    meta = m.meta
    if m.kind != "pseudorange" or "rx_clock" not in meta:
        return m
    snr, n = meta.get("snr_db"), meta.get("n_epochs")
    if snr is None or not n:
        return m
    return replace(m, sigma=(sigma_m(float(snr), int(n)),))
