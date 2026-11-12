"""Innovation whiteness test per source (#275 step 1, ADR-0052 Proposed): a health flag that a
source's errors are correlated in time while the filter takes them as white.

A Kalman filter whose model is right has white innovations: any two of them, at different
times, are uncorrelated. A source whose error is correlated in time (multipath, a bias, a told
sigma far below a slow error) and is modelled as white gives innovations that are positively
correlated from one record to the next of the same stream. This test measures that directly.

- Each innovation the EKF computes (`EKF._update`, kept in `_last_innov`) is normalised per
  component, z = y_i / sqrt(S_ii). One stream is one (source, emitter, kind, component).
- Each record forms a lag-1 pair with the previous record of its stream, if that is at most
  `max_gap_s` older. Its product p = z_k z_(k-1) is added to its source's window.
- Over the last `window_s`, per source: the pooled lag-1 autocorrelation
  r = sum(p) / sqrt(sum(z_k^2) sum(z_(k-1)^2)), and the test statistic
  T = sum(p) / sqrt(sum(p^2)). With white innovations the products are uncorrelated with mean
  zero, so T is about standard normal whatever the innovations' scale: a told sigma that is
  wrong in size alone does not raise it, only correlation does.
- The flag `innovations_correlated:<source>` is raised while T > `threshold` with at least
  `min_pairs` pairs in the window. One-sided: unmodelled slow errors correlate positively.
  GNSS position is analysis only (`report_only`): its statistic is computed, never flagged.

Report only. It never changes an estimate: the flag is added to each Estimate after the
estimator and any integrity monitor have made it (`ekf.run`), so status, trust and every other
flag are as without it. Off by default (`EKF(whiteness=False)`): the panel's paths switch it on
through `nav.estimate(..., whiteness=True)`; Monte Carlo evals, results and sweeps leave it off,
as it costs about a fifth of `ekf`'s run time. Every value here is TBC (ADR-0052), chosen on
sim seeds 0-9 (`analysis/whiteness.py`).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import msgspec
import numpy as np

from pnt.core.measurement import Estimate

FLAG = "innovations_correlated"  # the flag is f"{FLAG}:{source}"


@dataclass(frozen=True)
class WhitenessParams:
    window_s: float = 60.0  # s: sliding window of lag-1 pairs per source (TBC, ADR-0052)
    threshold: float = 3.0  # T above this raises the flag (TBC, ADR-0052)
    min_pairs: int = 30  # fewer pairs in the window: no opinion (TBC)
    max_gap_s: float = 5.0  # s: a record pairs with its stream's previous one this close (TBC)
    # Sources whose statistic is computed but never flagged (owners, 2026-11-11, ADR-0052): GNSS
    # position, as receivers smooth their fixes, so consecutive fixes correlate by design
    report_only: tuple[str, ...] = ("gnss",)


class Whiteness:
    """Lag-1 innovation whiteness per source over a sliding window (module docstring)."""

    def __init__(self, params: WhitenessParams | None = None):
        self.p = params or WhitenessParams()
        self.window_ns = int(self.p.window_s * 1e9)
        self.max_gap_ns = int(self.p.max_gap_s * 1e9)
        self._last: dict[tuple, tuple[int, float]] = {}  # stream -> (t_ns, z) of its last record
        # source -> deque of (t_ns, p, z_k^2, z_(k-1)^2), and running sums of the last three
        # and of p^2
        self._pairs: dict[str, deque[tuple[int, float, float, float]]] = {}
        self._sums: dict[str, list[float]] = {}
        self._dropped: dict[str, int] = {}  # pairs evicted since the sums were last re-summed

    def add(self, t_ns: int, source: str, emitter: str | None, kind: str, y, S) -> None:
        """One innovation y with covariance S (the EKF's `_last_innov`)."""
        # plain floats from here: this runs on every record (ndarray methods, not np.* wrappers)
        ys = y.ravel().tolist() if isinstance(y, np.ndarray) else np.ravel(y).tolist()
        vs = S.diagonal().tolist() if np.ndim(S) == 2 else np.ravel(S).tolist()
        for i, (yi, vi) in enumerate(zip(ys, vs, strict=True)):
            if not vi > 0.0 or not math.isfinite(yi):
                continue
            z = yi / math.sqrt(vi)
            stream = (source, emitter, kind, i)
            prev = self._last.get(stream)
            self._last[stream] = (t_ns, z)
            if prev is not None and t_ns - prev[0] <= self.max_gap_ns:
                self._pair(t_ns, source, z * prev[1], z * z, prev[1] * prev[1])

    def _pair(self, t_ns: int, source: str, p: float, a2: float, b2: float) -> None:
        w = self._pairs.get(source)
        if w is None:
            w = self._pairs[source] = deque()
            self._sums[source] = [0.0, 0.0, 0.0, 0.0]
        w.append((t_ns, p, a2, b2))
        s = self._sums[source]
        s[0] += p
        s[1] += p * p
        s[2] += a2
        s[3] += b2
        self._evict(source, t_ns)

    def _evict(self, source: str, t_ns: int) -> None:
        w, s = self._pairs[source], self._sums[source]
        old = t_ns - self.window_ns
        if not w or w[0][0] > old:
            return
        dropped = self._dropped.get(source, 0)
        while w and w[0][0] <= old:
            _, p, a2, b2 = w.popleft()
            s[0] -= p
            s[1] -= p * p
            s[2] -= a2
            s[3] -= b2
            dropped += 1
        self._dropped[source] = dropped
        # Re-sum exactly once as many pairs have left as the window holds (amortised O(1)), so
        # the running sums never drift; at once when it empties
        if dropped and (not w or dropped >= max(len(w), 256)):
            self._dropped[source] = 0
            ps = [r[1] for r in w]
            s[0] = math.fsum(ps)
            s[1] = math.fsum(p * p for p in ps)
            s[2] = math.fsum(r[2] for r in w)
            s[3] = math.fsum(r[3] for r in w)

    def stats(self, t_ns: int) -> dict[str, tuple[float, float, int]]:
        """Per source with pairs in the window ending at t_ns: (r, T, pairs)."""
        out = {}
        for source in self._pairs:
            self._evict(source, t_ns)
            n = len(self._pairs[source])
            if n == 0:
                continue
            sp, sp2, sa2, sb2 = self._sums[source]
            den = math.sqrt(sa2 * sb2)
            r = sp / den if den > 0 else 0.0
            T = sp / math.sqrt(sp2) if sp2 > 0 else 0.0
            out[source] = (r, T, n)
        return out

    def flags(self, t_ns: int) -> list[str]:
        """`innovations_correlated:<source>` for each source over the threshold, sorted;
        never for a `report_only` source."""
        out = []
        for source, w in self._pairs.items():
            if source in self.p.report_only:
                continue
            self._evict(source, t_ns)
            if len(w) < self.p.min_pairs:
                continue
            sp, sp2 = self._sums[source][:2]
            if sp2 > 0 and sp / math.sqrt(sp2) > self.p.threshold:  # T, as in `stats`
                out.append(f"{FLAG}:{source}")
        return sorted(out)

    def flag(self, est: Estimate) -> Estimate:
        """`est` with this test's flags appended; nothing else changes (not even status)."""
        extra = self.flags(est.t_ns)
        return msgspec.structs.replace(est, flags=[*est.flags, *extra]) if extra else est


def advisory(flag: str) -> bool:
    """True for this test's flags: they report, they never degrade a status."""
    return flag.startswith(FLAG + ":")
