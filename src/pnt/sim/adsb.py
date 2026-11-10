"""ADS-B traffic (#91, P6): the position reports of aircraft around us, as a receiver decodes them.

Each aircraft flies a polyline at a constant ground speed (`points_llh`, `speed_mps`) and is at
its first point at `start_s` (negative: already on its way when the session starts). It reports
only while on its track: before, it is out of range; after, it has landed or gone. A report is
ICD-measurement's `adsb_report`, (e, n, u, nacp, nic) in the session's ENU frame, from emitter
`adsb:<icao>`, at `rate_hz` per aircraft. Its `sigma` is what a decoder can know: the NACp
class's 95 % bound as a 1-sigma (`sigma_of_nacp`), not the true error.

The position is the aircraft's own GNSS fix (ADR-0024: GNSS-derived), so its error and its
quality come from one model: horizontal sigma `sigma_m`, NACp from the 95 % accuracy bound
EPU = K95 sigma, NIC from the containment radius Rc = max(rc_floor_m, K_RC sigma), on the DO-260B
tables below. The scenario's GNSS zones reach the aircraft too, through their true positions:
- `jamming_zone` (as in `pnt.sim.attacks`): between onset_m and radius_m the sigma grows to
  max_sigma_scale times, and NACp and NIC follow it; inside radius_m the aircraft has no GNSS and
  reports NACp 0 and NIC 0 (its position then comes from its own dead reckoning, modelled as the
  largest scaled error).
- `spoof_zone`: inside radius_m the position is moved by offset_enu_m and NACp and NIC stay as
  they were, as observed of real spoofing (threat-model.md: Park 2026, Aireon).
The zones are horizontal circles, as for our own receiver. A jammer reaches an aircraft at
altitude much further than a car on the ground (line of sight), so a scenario's radii for the
traffic are its own TBC choice.

Nuisance dips (TBC, no source): an aircraft briefly reports a lower NACp and NIC for reasons of
its own (antenna masking in a turn, avionics). A Poisson process per aircraft, so a warning's
false-alert rate is measured against something; the rate and length are placeholders.

`legacy: true` marks an aircraft whose avionics always report the `nacp` and `nic` given (no
SBAS, an old transponder), whatever its true accuracy.
"""

from __future__ import annotations

import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement

# DO-260B upper bounds (m) of each NACp class (EPU, 95 % horizontal accuracy) and NIC class (Rc,
# containment radius), best class first: NACp 11 is EPU < 3 m, NACp 1 is EPU < 10 NM; NIC 11 is
# Rc < 7.5 m, NIC 1 is Rc < 20 NM. Past the last bound the class is 0 (unknown).
NM = 1852.0
NACP_EPU_M = {
    11: 3.0, 10: 10.0, 9: 30.0, 8: 0.05 * NM, 7: 0.1 * NM, 6: 0.3 * NM, 5: 0.5 * NM,
    4: 1.0 * NM, 3: 2.0 * NM, 2: 4.0 * NM, 1: 10.0 * NM,
}  # fmt: skip
NIC_RC_M = {
    11: 7.5, 10: 25.0, 9: 75.0, 8: 0.1 * NM, 7: 0.2 * NM, 6: 0.6 * NM, 5: 1.0 * NM,
    4: 2.0 * NM, 3: 4.0 * NM, 2: 8.0 * NM, 1: 20.0 * NM,
}  # fmt: skip
K95 = 2.4477  # 95 % radius of a circular 2-D Gaussian, in sigmas
# Containment radius in sigmas, a protection-level-like bound (pnt.integrity.protection uses
# K_H = 5.33 for 1e-7). TBC
K_RC = 6.0
UNKNOWN_SIGMA_M = 20.0 * NM  # sigma reported for NACp 0 (unknown accuracy): a no-information value


def nacp_of(epu_m: float) -> int:
    """The NACp class of a 95 % accuracy bound (m)."""
    return next((c for c, b in NACP_EPU_M.items() if epu_m < b), 0)


def nic_of(rc_m: float) -> int:
    """The NIC class of a containment radius (m)."""
    return next((c for c, b in NIC_RC_M.items() if rc_m < b), 0)


def sigma_of_nacp(nacp: int) -> float:
    """A 1-sigma horizontal error a decoder can read off a NACp: its class bound over K95."""
    return NACP_EPU_M[nacp] / K95 if nacp in NACP_EPU_M else UNKNOWN_SIGMA_M


def track(points_enu: np.ndarray, speed_mps: float, t_s: np.ndarray):
    """Positions along a polyline at constant speed, t_s seconds after its first point.
    Returns (positions, on-track mask)."""
    seg = np.linalg.norm(np.diff(points_enu, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    s = speed_mps * t_s
    on = (s >= 0) & (s <= cum[-1])
    pos = np.column_stack([np.interp(s, cum, points_enu[:, k]) for k in range(3)])
    return pos, on


def _zone_effects(zones: list[dict], origin_llh, t_s: np.ndarray, pos: np.ndarray):
    """Per sample: (sigma scale, lost, position offset) from the GNSS zones."""
    scale = np.ones(len(t_s))
    lost = np.zeros(len(t_s), bool)
    offset = np.zeros((len(t_s), 3))
    for z in zones:
        active = (t_s >= z.get("start_s", 0.0)) & (t_s < z.get("end_s", np.inf))
        center = np.asarray(llh_to_enu(z["center_llh"], origin_llh), float)
        d = np.linalg.norm(pos[:, :2] - center[:2], axis=1)
        r_in = float(z["radius_m"])
        if z["type"] == "jamming_zone":
            r_on, k_max = float(z["onset_m"]), float(z.get("max_sigma_scale", 10.0))
            frac = np.clip((r_on - d) / (r_on - r_in), 0.0, 1.0)
            scale = np.where(active, np.maximum(scale, 1 + (k_max - 1) * frac), scale)
            lost |= active & (d < r_in)
        else:  # spoof_zone
            inside = active & (d < r_in)
            offset[inside] += np.asarray(z["offset_enu_m"], float)
    return scale, lost, offset


def reports(
    ts_s: np.ndarray,
    t0_ns: int,
    rng,
    origin_llh,
    aircraft: list[dict],
    zones: list[dict] = (),
    sigma_m: float = 3.0,
    rc_floor_m: float = 150.0,
    dip_rate_per_h: float = 0.0,
    dip_s: tuple[float, float] = (2.0, 20.0),
    dip_nacp: int = 7,
    dip_nic: int = 6,
    source: str = "adsb",
) -> list[Measurement]:
    """Every aircraft's reports at the sample times `ts_s` (s since the session start).

    sigma_m: horizontal sigma of a nominal fix (TBC: gives NACp 10, an airliner with SBAS or good
      RAIM); rc_floor_m: the containment radius of a nominal fix (TBC: gives NIC 8, as most
      airliners report). Each aircraft may override either, or give `nacp`/`nic` with `legacy`.
    zones: the scenario's `jamming_zone` and `spoof_zone` faults on GNSS.
    dip_rate_per_h, dip_s, dip_nacp, dip_nic: the nuisance dips (all TBC)."""
    out: list[Measurement] = []
    for ac in aircraft:
        icao = str(ac["icao"]).lower()
        pts = np.array([llh_to_enu(p, origin_llh) for p in ac["points_llh"]], float)
        pos, on = track(pts, float(ac["speed_mps"]), ts_s - float(ac.get("start_s", 0.0)))
        sig = float(ac.get("sigma_m", sigma_m))
        rc = float(ac.get("rc_floor_m", rc_floor_m))
        scale, lost, offset = _zone_effects(list(zones), origin_llh, ts_s, pos)
        k_lost = max([float(z.get("max_sigma_scale", 10.0)) for z in zones] + [1.0])
        dip = np.zeros(len(ts_s), bool)
        if dip_rate_per_h > 0 and on.any():
            t_on = ts_s[on]
            n = rng.poisson(dip_rate_per_h * (t_on[-1] - t_on[0]) / 3600.0)
            starts, lengths = rng.uniform(t_on[0], t_on[-1], n), rng.uniform(*dip_s, n)
            for a, d in zip(starts, lengths, strict=True):
                dip |= (ts_s >= a) & (ts_s < a + d)
        noise = rng.normal(0.0, sig, (len(ts_s), 3)) * np.array([1.0, 1.0, 1.5])
        for k in np.flatnonzero(on):
            s = sig * (k_lost if lost[k] else scale[k])
            if lost[k]:
                nacp = nic = 0
            elif ac.get("legacy"):
                nacp, nic = int(ac["nacp"]), int(ac["nic"])
            else:
                nacp, nic = nacp_of(K95 * s), nic_of(max(rc, K_RC * s))
            if dip[k]:
                nacp, nic = min(nacp, dip_nacp), min(nic, dip_nic)
            e, n_, u = pos[k] + noise[k] * (s / sig) + offset[k]
            rep = sigma_of_nacp(nacp)
            out.append(
                Measurement(
                    t_ns=t0_ns + int(round(ts_s[k] * 1e9)),
                    source=source,
                    kind="adsb_report",
                    value=(float(e), float(n_), float(u), float(nacp), float(nic)),
                    sigma=(rep, rep, 1.5 * rep, 0.0, 0.0),
                    emitter=f"adsb:{icao}",
                )
            )
    return out
