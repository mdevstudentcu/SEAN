"""Is GNSS spoofed? One decision from the known sky, the satellites' power and the other cues
(#206, ADR-0041, Proposed). Advisory: it never changes an estimate.

The mentors (2026-11-10 call) asked for a function that decides spoofed or not from the power we
can read and from the known sky: a satellite received that cannot be visible means spoofing.

Input is one **skyview**: a `gnss_health` record whose `meta.snr` maps PRN to C/N0 (dB-Hz), as
`pnt.frontends.gnss.health` writes it from the payload's `gnss_sky` events and the sim writes it
when its GNSS source has a `sky:` (`pnt.sim.scenario`). Only GPS PRNs (1 to 32) with C/N0 above 0
are judged: they are the ones in the almanac. The receiver's position and the time give each one's
predicted elevation from a dated CelesTrak GPS TLE file, propagated with SGP4 (`pnt.sim.leo`).

Two checks per skyview:
- **Sky map.** A judged PRN whose predicted elevation is below `SKY_MASK_DEG` cannot reach the
  antenna: a spoofer is generating it (a canned sky for another place or time).
- **Power pattern.** On a real sky C/N0 rises with elevation (antenna gain, path through the
  atmosphere) and differs from satellite to satellite. A spoofer with one antenna reaches us from
  one direction, so a simple one gives every satellite the same power, unrelated to elevation.
  With at least `POWER_MIN_SATS` judged PRNs above the mask, the pattern is **flat** when the
  C/N0 spread (sample standard deviation) is under `SPREAD_MIN_DB`, or the correlation of C/N0
  with predicted elevation is under `CORR_MIN`. Not judged while the jam indicator is at or over
  `JAM_MAX`: jamming crushes every C/N0 towards the floor, which looks flat too.

A cue is **held** once it is seen on `HOLD_REPORTS` skyviews in a row; one skyview without it
clears it. Each cue has a strength, combined as a noisy-OR, `score = 1 - prod(1 - s)`:

| Cue | Strength |
| --- | --- |
| `sky_below_horizon` (held / first skyview) | 1.0 / 0.5 |
| `power_flat` (held / first skyview) | 0.5 / 0.25 |
| `jump_latched`: the jump guard refuses GNSS (estimate flag `gnss_jump_latched`, ADR-0038) | 0.5 |
| `towers_refute`: the towers refute GNSS (estimate flag `spoof_suspected`, #83, ADR-0037) | 0.5 |

`spoofed` at a score of `SPOOFED_SCORE` or more (a held sky cue alone, or two independent cues at
0.5), `suspect` above 0, `not_spoofed` at 0 with a fresh skyview, and `unknown` at 0 with no
skyview in the last `STALE_S` (no sky data is not evidence of no spoofing). The jam indicator is
context only: it turns the power check off, and is reported.

Limits: a spoofer that simulates the right sky for our place and time, and shapes each
satellite's power with elevation, passes both sky checks; a multi-antenna spoofer can too. The
power thresholds come from one static session on the GPS HAT with its external antenna, under an
open sky: an antenna that is blocked on one side, indoors or on a moving drone may show a flatter
pattern. Every value is `TBC`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, timedelta
from pathlib import Path

import numpy as np

from pnt.core.time import gps_ns_to_utc

GPS_TLE = Path(__file__).parents[3] / "data" / "reference" / "tle-gps-20261111.txt"

# ADR-0041. All TBC.
SKY_MASK_DEG = -5.0  # TBC: a received PRN predicted below this cannot be real (TLE age margin)
POWER_MIN_SATS = 5  # TBC: judged PRNs above the mask needed to judge the power pattern
# TBC: 1/2.5 of the smallest spread (7.6 dB) on 20261111-0040-static-fullsuite (120 skyviews)
SPREAD_MIN_DB = 3.0
# TBC: well under the smallest correlation (0.66) on that session; ~0 for an equal-power spoofer
CORR_MIN = 0.2
JAM_MAX = 0.5  # TBC: power check off at or above this jam indicator (ADR-0031)
HOLD_REPORTS = 2  # TBC: skyviews in a row before a cue is held (5 s apart on the GPS HAT)
STALE_S = 15.0  # TBC: three of the GPS HAT's 5 s skyview periods
SPOOFED_SCORE = 0.75  # TBC: a held sky cue alone, or two independent cues at 0.5
STRENGTH = {
    "sky_below_horizon": (0.5, 1.0),  # (first skyview, held)
    "power_flat": (0.25, 0.5),
    "jump_latched": (0.5, 0.5),
    "towers_refute": (0.5, 0.5),
}
FLAG_CUES = {"gnss_jump_latched": "jump_latched", "spoof_suspected": "towers_refute"}
LEVELS = ("unknown", "not_spoofed", "suspect", "spoofed")
GPS_PRNS = range(1, 33)


def read_gps_tles(path: str | Path = GPS_TLE) -> dict[int, tuple[str, str]]:
    """PRN -> (line 1, line 2), from the PRN in each name, e.g. `GPS BIIR-5 (PRN 22)`."""
    from pnt.sim.leo import read_tles

    out: dict[int, tuple[str, str]] = {}
    for name, l1, l2 in read_tles(path):
        if "PRN" not in name:
            raise ValueError(f"no PRN in TLE name {name!r}")
        out[int(name.split("PRN")[1].strip(" )"))] = (l1, l2)
    return out


class GpsAlmanac:
    """Predicted elevation and azimuth of every GPS satellite in a TLE file."""

    def __init__(self, path: str | Path = GPS_TLE):
        self.path = Path(path)
        self.tles = read_gps_tles(path)

    def look(self, t_ns, receiver_llh) -> dict[int, tuple[np.ndarray, np.ndarray]]:
        """PRN -> (elevation, azimuth) in degrees at each GPS time in `t_ns` (scalar or array),
        seen from `receiver_llh` (lat, lon in degrees, height in metres)."""
        from pnt.sim.leo import satellite_enu

        t = np.atleast_1d(np.asarray(t_ns, dtype=np.int64))
        first = gps_ns_to_utc(int(t[0])).replace(tzinfo=UTC)
        utc = first.replace(microsecond=0)
        t_s = (t - t[0]) / 1e9 + (first - utc) / timedelta(seconds=1)
        out = {}
        for prn, (l1, l2) in self.tles.items():
            enu, _ = satellite_enu(l1, l2, utc, t_s, receiver_llh)
            el = np.degrees(np.arcsin(enu[:, 2] / np.linalg.norm(enu, axis=1)))
            az = np.degrees(np.arctan2(enu[:, 0], enu[:, 1])) % 360.0
            out[prn] = (el, az)
        return out

    def elevations(self, t_ns: int, receiver_llh) -> dict[int, float]:
        """PRN -> predicted elevation (degrees) at one time."""
        return {p: float(el[0]) for p, (el, _) in self.look(t_ns, receiver_llh).items()}


@dataclass
class SkyCheck:
    """Both sky checks on one skyview."""

    n_judged: int  # GPS PRNs with C/N0 > 0 in the almanac
    n_other: int  # PRNs with C/N0 > 0 not judged (other constellations, SBAS)
    below: list[int]  # judged PRNs predicted below the mask
    n_power: int  # judged PRNs above the mask, for the power pattern
    spread_db: float | None
    corr: float | None
    flat: bool | None  # None: not judged (too few satellites, or jammed)
    note: str = ""


def check(
    snr: Mapping[str, float | None],
    elevation: Mapping[int, float],
    jam: float | None = None,
    mask_deg: float = SKY_MASK_DEG,
    min_sats: int = POWER_MIN_SATS,
    spread_min_db: float = SPREAD_MIN_DB,
    corr_min: float = CORR_MIN,
    jam_max: float = JAM_MAX,
) -> SkyCheck:
    """The sky-map and power-pattern checks on one skyview (module docstring).

    `snr` is PRN (as a string, as gpsd's JSON gives it) -> C/N0 in dB-Hz, None or 0 if not
    tracked; `elevation` is PRN -> predicted elevation (degrees)."""
    got = {}
    other = 0
    for p, s in snr.items():
        if s is None or s <= 0:
            continue
        prn = int(p)
        if prn in GPS_PRNS and prn in elevation:
            got[prn] = float(s)
        else:
            other += 1
    below = sorted(p for p in got if elevation[p] < mask_deg)
    up = [p for p in got if elevation[p] >= mask_deg]
    spread = corr = flat = None
    note = ""
    if len(up) < min_sats:
        note = f"power check off: {len(up)} GPS satellites above the mask (needs {min_sats})"
    else:
        c = np.array([got[p] for p in up])
        e = np.array([elevation[p] for p in up])
        spread = float(c.std(ddof=1))
        # No C/N0 spread at all is the flattest pattern: its correlation is 0, not undefined
        corr = float(np.corrcoef(e, c)[0, 1]) if spread > 0 and e.std() > 0 else 0.0
        if jam is not None and jam >= jam_max:
            note = f"power check off: jam indicator {jam:.2f} (C/N0 low on every satellite)"
        else:
            flat = spread < spread_min_db or corr < corr_min
    return SkyCheck(len(got), other, below, len(up), spread, corr, flat, note)


@dataclass
class SpoofStatus:
    t_ns: int
    level: str  # one of LEVELS
    score: float
    cues: list[str] = field(default_factory=list)  # cues that fired, "(held)" when held
    notes: list[str] = field(default_factory=list)
    sky: SkyCheck | None = None  # the latest skyview's checks

    def to_dict(self) -> dict:
        sky = None
        if self.sky is not None:
            s = self.sky
            sky = {
                "n_judged": s.n_judged,
                "n_below": len(s.below),
                "n_power": s.n_power,
                "spread_db": None if s.spread_db is None else round(s.spread_db, 2),
                "corr": None if s.corr is None else round(s.corr, 3),
            }
        return {
            "level": self.level,
            "score": round(self.score, 3),
            "cues": list(self.cues),
            "notes": list(self.notes),
            "sky": sky,
        }


class SpoofDecision:
    """One spoofed-or-not decision per epoch (module docstring). Feed it each skyview with
    `sky(...)` (or any measurement with `measurement(...)`), then ask `decide(t_ns, flags)` with
    the estimate's flags. It changes nothing else."""

    def __init__(self, almanac: GpsAlmanac | None = None, **params):
        self.almanac = almanac if almanac is not None else GpsAlmanac()
        self.params = params  # `check`'s keyword arguments
        self.last: SkyCheck | None = None
        self.last_t: int | None = None
        self.jam: float | None = None
        self._runs = {"sky_below_horizon": 0, "power_flat": 0}

    def sky(self, t_ns: int, snr: Mapping, receiver_llh, jam: float | None = None) -> SkyCheck:
        """Judge one skyview, seen from `receiver_llh` at GPS time `t_ns`."""
        elevation = self.almanac.elevations(t_ns, receiver_llh)
        c = check(snr, elevation, jam=jam, **self.params)
        fired = {"sky_below_horizon": bool(c.below), "power_flat": bool(c.flat)}
        for cue, on in fired.items():
            self._runs[cue] = self._runs[cue] + 1 if on else 0
        self.last, self.last_t, self.jam = c, int(t_ns), jam
        return c

    def measurement(self, m, receiver_llh) -> SkyCheck | None:
        """Take a measurement: a `gnss_health` record with `meta.snr` is a skyview."""
        if m.kind != "gnss_health" or not m.meta or not m.meta.get("snr"):
            return None
        return self.sky(m.t_ns, m.meta["snr"], receiver_llh, jam=float(m.value[0]))

    def decide(self, t_ns: int, flags: Iterable[str] = ()) -> SpoofStatus:
        fresh = self.last_t is not None and t_ns - self.last_t <= STALE_S * 1e9
        strengths: dict[str, float] = {}
        notes: list[str] = []
        if fresh:
            for cue, run in self._runs.items():
                if run:
                    strengths[cue] = STRENGTH[cue][run >= HOLD_REPORTS]
            if self.last.note:
                notes.append(self.last.note)
        else:
            notes.append(f"no GPS sky data in the last {STALE_S:.0f} s")
        for flag in flags:
            if flag in FLAG_CUES:
                cue = FLAG_CUES[flag]
                strengths[cue] = STRENGTH[cue][1]
        score = 1.0 - float(np.prod([1.0 - s for s in strengths.values()]))
        if score >= SPOOFED_SCORE - 1e-9:
            level = "spoofed"
        elif score > 0:
            level = "suspect"
        else:
            level = "not_spoofed" if fresh else "unknown"
        cues = []
        for cue, s in strengths.items():
            held = cue in self._runs and s == STRENGTH[cue][1]
            cues.append(f"{cue} (held)" if held else cue)
        if self.jam is not None and fresh:
            notes.append(f"jam indicator {self.jam:.2f}")
        return SpoofStatus(int(t_ns), level, score, cues, notes, self.last if fresh else None)
