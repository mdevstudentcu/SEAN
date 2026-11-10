"""Residual map learned while GPS is trusted (P11, ADR-0032 Proposed, #95).

A tower's reading carries an error that depends on where we are: a reflection or a blocked
direct path seen from a street repeats every time we pass that street. The filter's white noise
and per-tower clock don't model it, so after GPS loss it pulls the solution. While GNSS is
trusted our position is known to a few metres, so each pseudorange innovation is mostly that
place's error. The map keeps, per emitter and per horizontal grid cell of `cell_m`, the mean of
those innovations, and from then on subtracts an estimate of that place's error from the
emitter's readings in that cell, with the estimate's variance added to the noise.

- **Learned only while GNSS is trusted** (`EKF.gnss_trusted`: GNSS position used recently and
  neither position nor time rejected since). Out of GNSS, or with GNSS flagged, the map is
  frozen: it never learns from a solution it is helping to make, and a spoof that was rejected
  writes nothing into it. A slow spoof that GNSS checks accept does write into it, as it does
  into the tower clocks (ADR-0022), and the map has no rollback (not built).
- **Only accepted innovations** are learned (`EKF._update` passed its 99.9 % gate), so an outlier
  the filter refused does not land in the map. What is learned is the innovation before the
  map's own correction, so a cell's mean stays the mean error at that place.
- **Shrunk towards no error** (empirical Bayes, as in James-Stein): a cell's mean of a few noisy
  readings is mostly noise when the emitter has no place error. Per emitter, the spread of place
  errors tau^2 is the variance of its cell means less their mean noise variance v (at least 0).
  A cell's estimate is k * mean with variance k * v, k = tau^2 / (tau^2 + v): with no place
  error the map corrects nothing and adds no noise; with a large one it trusts the cell.
- **Used once a cell has `min_samples`**, looked up at the filter's own position. A cell's noise
  variance v is the larger of its sample variance and the reported noise, over its count.
  tau^2 needs `min_cells` usable cells of that emitter.
- **Clock split:** the per-emitter clock states absorb any part of the error that is the same
  everywhere; the map learns what changes with place. Both are learned while GNSS is trusted.

Every value is TBC (ADR-0015, ADR-0032). The map is in memory for one run: carrying it between
sessions (a survey flight that maps, a later flight that uses it) is not built.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MapParams:
    cell_m: float = 25.0  # TBC: grid cell edge, horizontal
    min_samples: int = 2  # TBC: readings in a cell before it is used
    min_cells: int = 5  # TBC: usable cells of an emitter before its spread is estimated


class ResidualMap:
    """Per (emitter, cell): count, mean and sum of squared deviations of the innovations."""

    def __init__(self, params: MapParams):
        self.p = params
        self.cells: dict[tuple[str, int, int], list[float]] = {}  # [n, mean, m2]
        self._by_emitter: dict[str, list[list[float]]] = {}
        self._learned: dict[str, int] = {}  # readings learned per emitter
        self._spread: dict[str, tuple[int, float, float]] = {}  # (learned, sigma, tau^2) cache

    def _key(self, emitter: str, pos) -> tuple[str, int, int]:
        c = self.p.cell_m
        return emitter, int(np.floor(pos[0] / c)), int(np.floor(pos[1] / c))

    def _noise(self, cell: list[float], sigma: float) -> float:
        """Variance of a cell's mean as an estimate of its place error."""
        n, _, m2 = cell
        return (max(m2 / (n - 1), sigma * sigma) if n > 1 else sigma * sigma) / n

    def spread(self, emitter: str, sigma: float) -> float | None:
        """tau^2: the variance of this emitter's place errors (m^2), None until `min_cells`."""
        learned = self._learned.get(emitter, 0)
        cached = self._spread.get(emitter)
        if cached is not None and cached[:2] == (learned, sigma):
            return cached[2]
        usable = [c for c in self._by_emitter.get(emitter, []) if c[0] >= self.p.min_samples]
        tau2 = None
        if len(usable) >= self.p.min_cells:
            means = np.array([c[1] for c in usable])
            noise = np.mean([self._noise(c, sigma) for c in usable])
            tau2 = max(float(np.var(means, ddof=1)) - float(noise), 0.0)
        self._spread[emitter] = (learned, sigma, tau2)
        return tau2

    def correction(self, emitter: str, pos, sigma: float) -> tuple[float, float]:
        """(error to subtract, its variance) for a reading at `pos`; (0, 0) if unknown."""
        cell = self.cells.get(self._key(emitter, pos))
        if cell is None or cell[0] < self.p.min_samples:
            return 0.0, 0.0
        tau2 = self.spread(emitter, sigma)
        if not tau2:
            return 0.0, 0.0
        v = self._noise(cell, sigma)
        k = tau2 / (tau2 + v)
        return k * cell[1], k * v

    def learn(self, emitter: str, pos, residual: float) -> None:
        """Add the error a trusted-GNSS reading showed at `pos` (Welford's running mean)."""
        key = self._key(emitter, pos)
        cell = self.cells.get(key)
        if cell is None:
            cell = self.cells[key] = [0, 0.0, 0.0]
            self._by_emitter.setdefault(emitter, []).append(cell)
        cell[0] += 1
        d = residual - cell[1]
        cell[1] += d / cell[0]
        cell[2] += d * (residual - cell[1])
        self._learned[emitter] = self._learned.get(emitter, 0) + 1
