"""Allan deviation of a sensor sitting still, to calibrate the sim's IMU model (ADR-0015).

`overlapping_adev` is the standard overlapping estimator for rate data (gyro rad/s, accel
m/s^2) sampled evenly at fs. `fit` reads the usual figures off the curve:

- white noise: the slope -1/2 line, read at tau = 1 s, from the segment closest to that slope
  among taus with at least 100 clusters. In the convention of `pnt.sim.sensors`
  (sigma = N * sqrt(fs / 2)) the density is N = sqrt(2) * adev(1 s): `density_from_white`.
  A vibration bends the curve, so `psd_density` reads the same density off the flat part of
  the spectrum instead, away from the vibration's peak.
- bias instability: the curve's minimum and where it is. `bias_floor_reached` is False when the
  curve is still falling at the longest tau, so the minimum is only an upper bound. The sim
  models wander as Gauss-Markov, not flicker, so the floor is compared by overlaying the sim's
  own curve (`analysis/imu_allan.py`), not mapped to `ImuParams` here.
- rate random walk: the slope +1/2 line, read at tau = 3 s, when the curve rises.

A figure is None when no part of the curve has the slope it needs (within `SLOPE_TOL`).
"""

from __future__ import annotations

import numpy as np

SLOPE_TOL = 0.2  # how far a segment's log-log slope may be from -1/2 or +1/2
PER_DECADE = 10  # tau points per decade
MIN_CLUSTERS = 10  # longest tau is the record length / MIN_CLUSTERS


def cluster_sizes(n: int) -> np.ndarray:
    """Cluster sizes (samples), log-spaced from 1 to n / MIN_CLUSTERS."""
    top = n // MIN_CLUSTERS
    if top < 1:
        raise ValueError(f"{n} samples is too short for an Allan deviation")
    m = np.logspace(0, np.log10(top), max(2, int(np.log10(top) * PER_DECADE) + 1))
    return np.unique(np.round(m).astype(int))


def overlapping_adev(x, fs: float, m=None) -> tuple[np.ndarray, np.ndarray]:
    """(tau s, Allan deviation) of evenly sampled rate data x at fs Hz."""
    x = np.asarray(x, float)
    x = x - x.mean()  # the mean cancels; removing it keeps the cumulative sum precise
    m = cluster_sizes(len(x)) if m is None else np.asarray(m, int)
    c = np.concatenate([[0.0], np.cumsum(x)])
    adev = np.empty(len(m))
    for i, k in enumerate(m):
        avg = (c[k:] - c[:-k]) / k  # mean of every window of k samples
        d = avg[k:] - avg[:-k]  # adjacent windows
        adev[i] = np.sqrt(0.5 * np.mean(d**2))
    return m / fs, adev


def _slopes(tau, adev) -> np.ndarray:
    return np.diff(np.log(adev)) / np.diff(np.log(tau))


def fit(tau, adev) -> dict:
    """White noise, bias instability and rate random walk read off one Allan curve."""
    tau, adev = np.asarray(tau, float), np.asarray(adev, float)
    s = _slopes(tau, adev)
    i_min = int(np.argmin(adev))
    out = {
        "white_adev_1s": None,
        "white_slope": None,
        "floor": float(adev[i_min]),
        "floor_tau_s": float(tau[i_min]),
        "bias_floor_reached": bool(i_min < len(adev) - 1),
        "rrw_adev_3s": None,
        "rrw_slope": None,
    }
    before = np.arange(min(i_min, len(s)))
    if len(before):
        # The last decade of tau rests on fewer than 100 clusters (`cluster_sizes`): too noisy.
        steady = before[tau[before + 1] <= tau[-1] / 10]
        pool = steady if len(steady) else before
        j = pool[np.argmin(np.abs(s[pool] + 0.5))]
        if abs(s[j] + 0.5) <= SLOPE_TOL:
            # line of slope -1/2 through point j, read at tau = 1 s
            out["white_adev_1s"] = float(adev[j] * np.sqrt(tau[j]))
            out["white_slope"] = float(s[j])
    after = np.arange(i_min, len(s))
    if len(after):
        j = after[np.argmin(np.abs(s[after] - 0.5))]
        if abs(s[j] - 0.5) <= SLOPE_TOL:
            out["rrw_adev_3s"] = float(adev[j] * np.sqrt(3.0 / tau[j]))
            out["rrw_slope"] = float(s[j])
    return out


PSD_BAND_HZ = (10.0, 30.0)  # TBC: flat part of the MPU6050 spectrum at 100 Hz, DLPF 42 Hz


def psd_density(x, fs: float, band=PSD_BAND_HZ) -> float:
    """White noise density (unit/sqrt(Hz), the sim's convention) from the median one-sided
    Welch spectrum in `band`: for white noise, sigma^2 = N^2 * fs / 2 is the spectrum's area."""
    from scipy.signal import welch  # ground extra; the Pi never imports this module

    x = np.asarray(x, float)
    f, p = welch(x - x.mean(), fs=fs, nperseg=min(len(x), 1024))
    sel = (f >= band[0]) & (f <= band[1])
    if not sel.any():
        raise ValueError(f"no spectrum bins in {band} Hz at fs = {fs} Hz")
    return float(np.sqrt(np.median(p[sel])))


def density_from_white(adev_1s: float) -> float:
    """White noise density (unit/sqrt(Hz)) as `pnt.sim.sensors` uses it, from adev at 1 s.

    The sim draws white samples with sigma = N * sqrt(fs / 2); averaging tau * fs of them gives
    an Allan deviation of N / sqrt(2 * tau)."""
    return float(adev_1s * np.sqrt(2.0))
