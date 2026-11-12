"""Protection levels from the estimator covariance.

Baseline only: assumes the covariance is honest and errors are Gaussian. The integrity work
(fault detection, correlated-failure awareness) replaces or extends this.
"""

from __future__ import annotations

import math

import numpy as np

# Multiplier on the horizontal error ellipse's major-axis sigma (ADR-0056): the horizontal error
# is two-dimensional, so the 1e-7 per-epoch integrity risk (mhss.phmi) needs
# P(r > k sigma_major) <= exp(-k^2 / 2) = 1e-7, k = sqrt(2 ln 1e7) = 5.68 (bounding the ellipse
# by a circle of its major-axis sigma). The risk is TBC by REQ-02; the exposure time is TBD.
K_H = math.sqrt(2 * math.log(1e7))  # 5.6777, the same tail mhss uses at phmi = 1e-7
# Vertical and time are one-dimensional: the two-sided 1e-7 Gaussian factor, 5.33.
K_V = 5.33


def hpl(pos_cov: np.ndarray, k: float = K_H) -> float:
    """Horizontal protection level from a 3x3 (or 2x2) ENU position covariance."""
    ch = np.asarray(pos_cov)[:2, :2]
    return float(k * np.sqrt(max(np.linalg.eigvalsh(ch).max(), 0.0)))


def vpl(pos_cov: np.ndarray, k: float = K_V) -> float:
    return float(k * np.sqrt(max(float(np.asarray(pos_cov)[2, 2]), 0.0)))


# Multiplier on the clock 1-sigma for the time protection level: the clock is one-dimensional, so
# the same 1e-7 risk as K_H takes the 1-D factor, 5.33 (ADR-0056). TBC: REQ-03's target sets the
# real value.
K_T = 5.33


def tpl(clock_sigma_s: float | None, k: float = K_T) -> float | None:
    """Time protection level (s): a bound on |receiver clock error| from the clock 1-sigma.

    There is no standard definition of a time protection level (CISA, DHS and IEEE P1952 publish
    none that we found). Research definitions exist for GNSS timing receivers (Kirkko-Jaakkola et
    al., ION GNSS 2017; Baweja, arXiv 2606.24210, 2026; see systems/research.md); ours is the
    receiver-clock 1-sigma, in `ekf` oscillator holdover: TPL = K_T * clock_sigma_s, the HPL
    recipe applied to the one-dimensional clock state, with the same Gaussian,
    honest-covariance assumption. Computed
    outside the estimator from `Estimate.clock_sigma_s`; None when the clock is not estimated.
    """
    if clock_sigma_s is None:
        return None
    return float(k * max(clock_sigma_s, 0.0))
