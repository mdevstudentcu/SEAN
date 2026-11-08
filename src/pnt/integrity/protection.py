"""Protection levels from the estimator covariance.

Baseline only: assumes the covariance is honest and errors are Gaussian. The integrity work
(fault detection, correlated-failure awareness) replaces or extends this.
"""

from __future__ import annotations

import numpy as np

# Multiplier on the horizontal error ellipse's major-axis sigma. 5.33 is a common choice for a
# ~1e-7 integrity risk under Gaussian errors. TBC: REQ-02's target sets the real value.
K_H = 5.33
K_V = 5.33


def hpl(pos_cov: np.ndarray, k: float = K_H) -> float:
    """Horizontal protection level from a 3x3 (or 2x2) ENU position covariance."""
    ch = np.asarray(pos_cov)[:2, :2]
    return float(k * np.sqrt(max(np.linalg.eigvalsh(ch).max(), 0.0)))


def vpl(pos_cov: np.ndarray, k: float = K_V) -> float:
    return float(k * np.sqrt(max(float(np.asarray(pos_cov)[2, 2]), 0.0)))
