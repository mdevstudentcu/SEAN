"""Simulated Iridium Doppler from real orbits (issue #15, ADR-0013, mentor Q5).

Satellite motion comes from a dated TLE snapshot in data/reference/, propagated with SGP4. The
receiver is not simulating Iridium's waveform: it produces the range-rate observable a real
receiver would report, with a stated error. The sigma and elevation mask are `TBC`, because
this layer cannot be measured this week (see verification.md, Sim validity).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from pnt.core.frames import _rot_ecef_to_enu, llh_to_ecef
from pnt.core.measurement import Measurement
from pnt.core.time import gps_ns_to_utc
from pnt.sim.models import C_MPS

EARTH_RATE_RAD_S = 7.292115e-5


def read_tles(path: str | Path) -> list[tuple[str, str, str]]:
    """(name, line 1, line 2) for each satellite in a three-line TLE file."""
    lines = [ln.rstrip() for ln in Path(path).read_text().splitlines() if ln.strip()]
    return [(lines[i].strip(), lines[i + 1], lines[i + 2]) for i in range(0, len(lines) - 2, 3)]


def satellite_enu(line1: str, line2: str, utc: datetime, t_s: np.ndarray, origin_llh):
    """Position (m) and velocity (m/s) in session ENU at t_s seconds after `utc`."""
    from sgp4.api import Satrec, jday
    from sgp4.propagation import gstime

    sat = Satrec.twoline2rv(line1, line2)
    jd0, fr0 = jday(utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second)
    fr = fr0 + t_s / 86400.0
    errors, r_km, v_kms = sat.sgp4_array(np.full_like(fr, jd0), fr)
    if np.any(errors):
        raise ValueError(f"SGP4 failed for satellite {sat.satnum}")
    theta = np.array([gstime(jd0 + f) for f in fr])
    c, s = np.cos(theta), np.sin(theta)
    # TEME to Earth-fixed: rotate by Greenwich sidereal time, and remove Earth's rotation
    r = (
        np.column_stack(
            [c * r_km[:, 0] + s * r_km[:, 1], -s * r_km[:, 0] + c * r_km[:, 1], r_km[:, 2]]
        )
        * 1000.0
    )
    v = (
        np.column_stack(
            [c * v_kms[:, 0] + s * v_kms[:, 1], -s * v_kms[:, 0] + c * v_kms[:, 1], v_kms[:, 2]]
        )
        * 1000.0
    )
    v[:, 0] += EARTH_RATE_RAD_S * r[:, 1]
    v[:, 1] -= EARTH_RATE_RAD_S * r[:, 0]
    rot = _rot_ecef_to_enu(origin_llh)
    return (rot @ (r - llh_to_ecef(origin_llh)).T).T, (rot @ v.T).T


def doppler(
    ts_ns,
    pos,
    vel,
    rng,
    origin_llh,
    tle_path: str | Path,
    sigma_mps: float,
    elevation_mask_deg: float,
    source: str = "leo",
    clock_s: np.ndarray | None = None,
) -> list[Measurement]:
    """Range rate to every satellite above the mask. `clock_s` adds the receiver's clock drift."""
    t_s = (ts_ns - ts_ns[0]) / 1e9
    first = gps_ns_to_utc(int(ts_ns[0]))
    utc = first.replace(microsecond=0, tzinfo=UTC)
    t_s = t_s + (first.replace(tzinfo=UTC) - utc) / timedelta(seconds=1)
    drift = C_MPS * np.gradient(clock_s, (ts_ns - ts_ns[0]) / 1e9) if clock_s is not None else 0.0
    out: list[Measurement] = []
    for name, line1, line2 in read_tles(tle_path):
        sat_pos, sat_vel = satellite_enu(line1, line2, utc, t_s, origin_llh)
        los = sat_pos - pos
        ranges = np.linalg.norm(los, axis=1)
        visible = np.degrees(np.arcsin(los[:, 2] / ranges)) >= elevation_mask_deg
        rate = np.sum((sat_vel - vel) * los, axis=1) / ranges + drift
        rate = rate + rng.normal(0.0, sigma_mps, len(rate)) if sigma_mps else rate
        emitter = f"{source}:{name.replace(' ', '')}"
        out += [
            Measurement(
                t_ns=int(ts_ns[k]),
                source=source,
                kind="doppler",
                emitter=emitter,
                value=(float(rate[k]),),
                sigma=(sigma_mps,),
                meta={
                    "emitter_enu": [float(x) for x in sat_pos[k]],
                    "emitter_vel_enu": [float(x) for x in sat_vel[k]],
                },
            )
            for k in np.flatnonzero(visible)
        ]
    return out
