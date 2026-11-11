"""Tower map hand-off (P12, issue #96): what a drone learns about the towers while its GPS is
trusted, handed to a user on the ground who has no GPS, as the prior for that user's filter.

Option A of #96, sim only: the map is an analysis-side object (and a small JSON file), never a
session record, so ICD-measurement and ICD-session are unchanged. A live moving reference that
streams its readings (option B) needs an ICD change and stays on the roadmap.

What the map holds, from a calibrated `ekf` (ADR-0022) at one epoch `t_ns`:
- Each clock block (`site:..`, `builder:..`): offset (m) and drift (m/s). The drone's own clock
  is anchored to GPS time while GNSS time is trusted, so these are tower time against GPS time.
- Each site's told-position error states (east, north, m) with the horizontal line of sight they
  are referred to (`los0`). The drone's offset carries the part of the position error along
  `los0` (see `EKF.tower_states`), so the user takes the same `los0` with them: the pair then
  means the same tower clock and position error from wherever the user stands.
- Their joint mean and covariance. Cross terms with the drone's own states (position, velocity,
  clock) are dropped: the user's errors are independent of the drone's.
Not in it: multipath states (each receiver has its own) and the drone's own clocks.

`EKF(tower_map=...)` adds the map's states when the user's filter starts, carried from `t_ns`
to then on the coast model (`propagated`, the same one a rollback uses): the offset moves by the
learned drift and the covariance grows by the receiving filter's tower oscillator noise. From
then on the filter treats them as tower states it already knew.

Trust: the map is only as good as the drone's GPS. A spoofed drone learns, and hands on, clocks
that fit the spoofed track: in `analysis/p12_spoofed_map.py` both a 2 m/s ramp and a 300 m
jump during the build carry into the user's position. The map is one more fault hypothesis, not
truth. One guard, opt-in (`refuse_flagged`): the drone withholds its map if its own filter raised
a spoof cue while it learned (the cues ADR-0041's decision reads: the towers' spoof alarm,
`spoof_suspected`, and the jump guard's latch, `gnss_jump_latched`, the latter only when the
filter runs the guard, ADR-0038). It does nothing against a spoof the drone does not flag: the
slow ramp, on the four towers of `p12-drone-map-handoff`, raises neither.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

from pnt.core.measurement import Measurement
from pnt.nav.ekf import CALIBRATED, EKF, _two_state_q


@dataclass(frozen=True)
class TowerMap:
    t_ns: int  # epoch of the estimates (GPS ns)
    clocks: tuple[str, ...]  # clock blocks, 2 states each: offset (m), drift (m/s)
    positions: tuple[tuple[str, tuple[float, float]], ...]  # (site, los0), 2 states: east, north
    mean: np.ndarray  # clocks' states in order, then the positions'
    cov: np.ndarray
    sites: dict[str, str] = field(default_factory=dict)  # emitter -> site, as the filter had it
    builders: dict[str, str] = field(default_factory=dict)  # site -> builder

    def index(self, key: str) -> int:
        """Index in `mean` of a clock block's offset, or of a site's east position error."""
        if key in self.clocks:
            return 2 * self.clocks.index(key)
        sites = [s for s, _ in self.positions]
        return 2 * len(self.clocks) + 2 * sites.index(key)

    def propagated(self, t_ns: int, s_tower: tuple[float, float]) -> TowerMap:
        """The map carried to `t_ns` on the coast model: each clock's offset moves by its drift,
        and grows by `s_tower` (offset and drift PSDs, m^2/s and m^2/s^3, as `EKF.s_tower`).
        Told-position errors are constant. Raises for a time before the map's epoch."""
        if t_ns < self.t_ns:
            raise ValueError("a tower map can't be carried back in time")
        dt = (t_ns - self.t_ns) / 1e9
        n = len(self.mean)
        F, Q = np.eye(n), np.zeros((n, n))
        for j in range(len(self.clocks)):
            i = 2 * j
            F[i, i + 1] = dt
            Q[i : i + 2, i : i + 2] = _two_state_q(*s_tower, dt)
        cov = F @ self.cov @ F.T + Q
        return TowerMap(
            t_ns,
            self.clocks,
            self.positions,
            F @ self.mean,
            (cov + cov.T) / 2,
            dict(self.sites),
            dict(self.builders),
        )

    def apply(self, ekf: EKF) -> None:
        """Add the map's states to `ekf` (just initialised, so it has no tower states yet),
        carried to its time. The tower model must match: calibrated clocks, and told-position
        states if the map has them."""
        if not ekf.calibrated:
            raise ValueError("a tower map needs the calibrated clock model (offset and drift)")
        if self.positions and ekf.tower_position_sigma_m <= 0:
            raise ValueError("this map has told-position states: the filter needs them on")
        if ekf.clock_idx or ekf.position_idx:
            raise ValueError("a tower map goes into a filter with no tower states yet")
        m = self.propagated(ekf.t_ns, ekf.s_tower)
        n, k = len(ekf.x), len(m.mean)
        ekf.x = np.append(ekf.x, m.mean)
        P = np.zeros((n + k, n + k))
        P[:n, :n] = ekf.P
        P[n:, n:] = m.cov
        ekf.P = P
        for key in m.clocks:
            i = n + m.index(key)
            ekf.clock_idx[key] = i
            ekf._clock_prior[key] = (float(np.sqrt(P[i, i])), float(np.sqrt(P[i + 1, i + 1])))
        for site, los0 in m.positions:
            ekf.position_idx[site] = (n + m.index(site), np.array(los0, float))
        for emitter, site in m.sites.items():
            ekf.sites.setdefault(emitter, site)
        for site, builder in m.builders.items():
            ekf.builders.setdefault(site, builder)

    def to_json(self) -> str:
        return json.dumps(
            {
                "t_ns": int(self.t_ns),
                "clocks": list(self.clocks),
                "positions": [[s, list(los0)] for s, los0 in self.positions],
                "mean": self.mean.tolist(),
                "cov": self.cov.tolist(),
                "sites": self.sites,
                "builders": self.builders,
            }
        )

    @classmethod
    def from_json(cls, text: str) -> TowerMap:
        d = json.loads(text)
        return cls(
            int(d["t_ns"]),
            tuple(d["clocks"]),
            tuple((s, (float(a), float(b))) for s, (a, b) in d["positions"]),
            np.array(d["mean"], float),
            np.array(d["cov"], float),
            dict(d["sites"]),
            dict(d["builders"]),
        )


class MapWithheld(ValueError):
    """The drone flagged its own GNSS while it learned: its map is not handed on."""


def spoof_cues(ekf: EKF) -> list[str]:
    """The spoof cues the filter raised since it started, as the estimate flags ADR-0041's
    decision reads them: `spoof_suspected` (the towers refute GNSS, the filter's own detector or
    a monitor through `raise_spoof_alarm`) and `gnss_jump_latched` (the jump guard, ADR-0038).
    A gate rejection alone is not a cue: honest GNSS has them."""
    cues = ["spoof_suspected"] if ekf.spoof_alarms else []
    if ekf.jump is not None and ekf.jump.latches:
        cues.append("gnss_jump_latched")
    return cues


def export(ekf: EKF, refuse_flagged: bool = False) -> TowerMap:
    """The tower map of a calibrated filter, at its current time. With `refuse_flagged`, raises
    `MapWithheld` instead if the filter raised a spoof cue (`spoof_cues`) since it started: what
    it learned may fit a spoofed track (module docstring)."""
    if not ekf.calibrated:
        raise ValueError("a tower map needs the calibrated clock model (offset and drift)")
    if refuse_flagged and (cues := spoof_cues(ekf)):
        raise MapWithheld(f"the drone flagged its GNSS while it learned: {', '.join(cues)}")
    clocks = tuple(ekf.clock_idx)
    positions = tuple((s, (float(l0[0]), float(l0[1]))) for s, (_, l0) in ekf.position_idx.items())
    idx = [j for key in clocks for j in (ekf.clock_idx[key], ekf.clock_idx[key] + 1)]
    idx += [j for i, _ in ekf.position_idx.values() for j in (i, i + 1)]
    return TowerMap(
        int(ekf.t_ns),
        clocks,
        positions,
        ekf.x[idx].copy(),
        ekf.P[np.ix_(idx, idx)].copy(),
        dict(ekf.sites),
        dict(ekf.builders),
    )


def learn(
    measurements: Iterable[Measurement],
    until_ns: int,
    origin_llh=None,
    refuse_flagged: bool = False,
    **config,
) -> TowerMap:
    """Run the `ekf-calibrated` filter (`CALIBRATED`, `config` over it) over the time-ordered
    `measurements` before `until_ns`, and export its map at `until_ns` (`refuse_flagged` as
    `export`; `jump_guard=JumpGuard` in `config` runs the jump guard). Only `payload` records
    are used, as `pnt.nav.estimate` would pass them."""
    ekf = EKF(origin_llh=origin_llh, **{**CALIBRATED, **config})
    for m in measurements:
        if m.t_ns >= until_ns:
            break
        if m.receiver == "payload":
            ekf.process(m)
    if ekf.x is None:
        raise ValueError("no position fix before the hand-off: nothing was learned")
    ekf.predict(until_ns)
    return export(ekf, refuse_flagged)
