"""Residual map learned while GPS is trusted (P11, ADR-0032 Proposed, #95).

A tower's reading carries an error that depends on where we are: a reflection or a blocked
direct path seen from a street repeats every time we pass that street. The filter's white noise
and per-tower clock don't model it, so after GPS loss it pulls the solution. While GNSS is
trusted our position is known to a few metres, so each pseudorange innovation is mostly that
place's error. The map keeps, per emitter and per horizontal grid cell of `cell_m`, the mean of
those innovations, and from then on subtracts it from the emitter's readings in that cell, with
the mean's own variance added to the noise.

- **Learned only while GNSS is trusted** (`EKF.gnss_trusted`: GNSS position used recently and
  neither position nor time rejected since). Out of GNSS, or with GNSS flagged, the map is
  frozen: it never learns from a solution it is helping to make, and a spoof that was rejected
  writes nothing into it. A slow spoof that GNSS checks accept does write into it, as it does
  into the tower clocks (ADR-0022), and the map has no rollback (not built).
- **Only accepted innovations** are learned (`EKF._update` passed its 99.9 % gate), so an outlier
  the filter refused does not land in the map. What is learned is the innovation before the
  map's own correction, so a cell's mean stays the mean error at that place.
- **Used once a cell has `min_samples`**, looked up at the filter's own position. Its variance is
  the larger of the sample variance and the reported noise, over the count, and is added to the
  reading's noise: a cell learned from three readings of 20 m noise corrects to about 12 m.
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


class ResidualMap:
    """Per (emitter, cell): count, mean and sum of squared deviations of the innovations."""

    def __init__(self, params: MapParams):
        self.p = params
        self.cells: dict[tuple[str, int, int], list[float]] = {}  # [n, mean, m2]

    def _key(self, emitter: str, pos) -> tuple[str, int, int]:
        c = self.p.cell_m
        return emitter, int(np.floor(pos[0] / c)), int(np.floor(pos[1] / c))

    def correction(self, emitter: str, pos, sigma: float) -> tuple[float, float]:
        """(mean error to subtract, its variance) for a reading at `pos`; (0, 0) if unknown."""
        cell = self.cells.get(self._key(emitter, pos))
        if cell is None or cell[0] < self.p.min_samples:
            return 0.0, 0.0
        n, mean, m2 = cell
        var = max(m2 / (n - 1), sigma * sigma) if n > 1 else sigma * sigma
        return mean, var / n

    def learn(self, emitter: str, pos, residual: float) -> None:
        """Add the error a trusted-GNSS reading showed at `pos` (Welford's running mean)."""
        cell = self.cells.setdefault(self._key(emitter, pos), [0, 0.0, 0.0])
        cell[0] += 1
        d = residual - cell[1]
        cell[1] += d / cell[0]
        cell[2] += d * (residual - cell[1])
