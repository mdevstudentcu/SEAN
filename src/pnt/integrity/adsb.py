"""ADS-B interference early warning (#91, P6, ADR-0033): aircraft around us report their own GNSS
quality, and it degrades before ours does when a jammer is ahead.

Reads `adsb_report` measurements (ICD-measurement: e, n, u, NACp, NIC) and keeps one track per
aircraft. ADS-B content is GNSS-derived (ADR-0024): it never confirms our GNSS and never enters
our position; it only says how likely a GNSS fault is around us.

Two kinds of evidence, each about one aircraft:
- **Quality drop:** an aircraft that has reported good quality (NACp >= `nacp_good` and NIC >=
  `nic_good`) reports worse for at least `hold_s`. An aircraft never heard with good quality
  (legacy avionics, or first heard inside the jamming) is not counted: its low quality is its
  normal. This is the gpsjam.org idea, per aircraft instead of per map cell.
- **Track jump with good quality:** a report away from where the aircraft's own track says it
  should be, while its NACp stays good, and the next report confirms the new place (a single bad
  decode is not a spoof). Spoofing usually keeps the quality flags high (threat-model.md: Park
  2026, Aireon), so this catches what the quality drop cannot. A slow carry-off that never
  jumps by more than the gate is not caught.

Only aircraft within `region_m` of our position count, and evidence lasts `memory_s` after the
aircraft last showed it. The warning is on while at least `min_aircraft` aircraft show a quality
drop, or any aircraft a confirmed jump. While it is on, the integrity monitor raises its GNSS
common-mode prior (`pnt.integrity.mhss`, ADR-0033).

All thresholds are TBC: none is set by a requirement, and the sim's traffic is synthetic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pnt.core.measurement import Measurement

KIND = "adsb_report"


@dataclass
class Params:
    # Good quality: NACp 9 is EPU < 30 m, NIC 7 is Rc < 0.2 NM. Most airliners report NACp >= 9
    # and NIC >= 7 in clean airspace (TBC against our own recordings, #22).
    nacp_good: int = 9
    nic_good: int = 7
    # A drop must last this long to count, so a brief dip (a turn masking the antenna) does not
    hold_s: float = 5.0
    # Aircraft with a quality drop needed for a warning. Two, so one aircraft's own avionics
    # fault does not warn alone
    min_aircraft: int = 2
    # Evidence is kept this long after the aircraft last showed it (it may land or leave range)
    memory_s: float = 300.0
    # Only aircraft this close to us count (horizontal)
    region_m: float = 50_000.0
    # Track check: a good-quality report further than this from its predicted place is a jump.
    # Above a decoded position's noise and a turn's departure from a straight line over one
    # report gap (`max_accel_mps2`, plus the gap's growth)
    jump_gate_m: float = 300.0
    max_accel_mps2: float = 5.0
    # A track older than this is restarted, not checked (the aircraft was out of range)
    track_gap_s: float = 30.0


@dataclass
class _Track:
    t_s: float
    e: float
    n: float
    ve: float = 0.0
    vn: float = 0.0
    has_vel: bool = False
    seen_good: bool = False
    bad_since: float | None = None  # quality below good since
    drop_last: float | None = None  # last time a held quality drop was seen
    jump: tuple[float, float, float] | None = None  # (t, e, n) of an unconfirmed jump
    jump_last: float | None = None  # last confirmed jump


@dataclass
class AdsbWarning:
    on: bool
    dropped: list[str] = field(default_factory=list)  # aircraft with a quality drop
    jumped: list[str] = field(default_factory=list)  # aircraft with a confirmed track jump


class AdsbMonitor:
    def __init__(self, params: Params | None = None):
        self.p = params or Params()
        self.tracks: dict[str, _Track] = {}

    def update(self, m: Measurement) -> None:
        """Fold in one `adsb_report`; other records are ignored."""
        if m.kind != KIND:
            return
        p = self.p
        t = m.t_ns / 1e9
        e, n, _, nacp, nic = m.value
        good = nacp >= p.nacp_good and nic >= p.nic_good
        tr = self.tracks.get(m.emitter)
        if tr is None or t - tr.t_s > p.track_gap_s:
            seen = tr.seen_good if tr is not None else False
            self.tracks[m.emitter] = _Track(t, e, n, seen_good=seen or good)
            return
        if good:
            tr.seen_good = True
            tr.bad_since = None
        elif tr.seen_good:
            tr.bad_since = t if tr.bad_since is None else tr.bad_since
            if t - tr.bad_since >= p.hold_s:
                tr.drop_last = t
        if good:
            self._check_track(tr, t, e, n)
        else:
            tr.jump = None  # a low-quality position says nothing about spoofing
            self._move(tr, t, e, n)

    def _check_track(self, tr: _Track, t: float, e: float, n: float) -> None:
        p = self.p
        dt = t - tr.t_s
        if tr.jump is not None:
            # The report after a jump: near the jumped place confirms it, near the old track
            # dismisses it as a bad decode
            tj, ej, nj = tr.jump
            gate = p.jump_gate_m + 0.5 * p.max_accel_mps2 * (t - tj) ** 2
            if math.hypot(e - ej - tr.ve * (t - tj), n - nj - tr.vn * (t - tj)) <= gate:
                tr.jump_last = t
                tr.t_s, tr.e, tr.n = tj, ej, nj  # the track continues from the jumped place
            tr.jump = None
        elif tr.has_vel:
            pe, pn = tr.e + tr.ve * dt, tr.n + tr.vn * dt
            gate = p.jump_gate_m + 0.5 * p.max_accel_mps2 * dt**2
            if math.hypot(e - pe, n - pn) > gate:
                tr.jump = (t, e, n)
                return  # the track stays where it was until the next report decides
        self._move(tr, t, e, n)

    def _move(self, tr: _Track, t: float, e: float, n: float) -> None:
        dt = t - tr.t_s
        if dt > 0:
            tr.ve, tr.vn, tr.has_vel = (e - tr.e) / dt, (n - tr.n) / dt, True
        tr.t_s, tr.e, tr.n = t, e, n

    def warning(self, t_ns: int, own_en: tuple[float, float] | None = None) -> AdsbWarning:
        """The warning at t_ns for a receiver at `own_en` (ENU m; None: every aircraft counts)."""
        p = self.p
        t = t_ns / 1e9
        dropped, jumped = [], []
        for icao, tr in sorted(self.tracks.items()):
            near = own_en is None or math.hypot(tr.e - own_en[0], tr.n - own_en[1]) <= p.region_m
            if not near:
                continue
            if tr.drop_last is not None and t - tr.drop_last <= p.memory_s:
                dropped.append(icao)
            if tr.jump_last is not None and t - tr.jump_last <= p.memory_s:
                jumped.append(icao)
        return AdsbWarning(len(dropped) >= p.min_aircraft or bool(jumped), dropped, jumped)
