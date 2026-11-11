"""Simulated GPS sky: per-PRN C/N0 on `gnss_health` records (#206, ADR-0041).

Opt-in with `sky:` on a scenario's GNSS source (which needs `health: true`). Every `period_s` the
`gnss_health` record carries `meta.snr` (PRN -> C/N0, dB-Hz), as `pnt.frontends.gnss.health` writes
it from a real session's `gnss_sky` events, so `pnt.integrity.sky` reads both the same way.

Which satellites: every GPS PRN in the committed TLE file (`pnt.integrity.sky.GPS_TLE`) whose
elevation from the receiver's true position is at least `mask_deg`. Their power:

    C/N0 = a + b sin(elevation) + bias_PRN + noise, rounded to whole dB-Hz (NMEA GSV is integer)

with `bias_PRN` drawn once per run and `noise` per report. A PRN under `min_cn0_dbhz` is not
tracked. Defaults are fitted on the one real session with skyviews (20261111-0040-static-fullsuite:
GPS HAT, external active antenna, static, open sky; 120 skyviews, 11 GPS PRNs): a least-squares
line of C/N0 on sin(elevation) (a 18.4, b 27.2), the spread of each PRN's mean residual (6.1 dB),
the report-to-report change of one PRN (1.3 dB, so 0.9 dB per report), the weakest C/N0 reported
(12 dB-Hz) and the lowest elevation tracked (8.7 deg, so a 5 deg mask). All TBC: one antenna, one
place, ten minutes; the sim's sky is `placeholder` in the Sim validity table.

The draws come from their own random stream, so a scenario's other draws do not move with it.
"""

from __future__ import annotations

import numpy as np

from pnt.core.frames import enu_to_llh

# TBC, fitted on 20261111-0040-static-fullsuite (module docstring)
CN0_A_DBHZ = 18.4
CN0_B_DBHZ = 27.2
PRN_BIAS_DB = 6.1
REPORT_NOISE_DB = 0.9
MIN_CN0_DBHZ = 12.0
MASK_DEG = 5.0
PERIOD_S = 5.0  # the GPS HAT sends a satellite list every 5 s


def snr_reports(
    ts_ns: np.ndarray,
    pos: np.ndarray,
    origin_llh,
    rng: np.random.Generator,
    period_s: float = PERIOD_S,
    mask_deg: float = MASK_DEG,
    a_dbhz: float = CN0_A_DBHZ,
    b_dbhz: float = CN0_B_DBHZ,
    prn_bias_db: float = PRN_BIAS_DB,
    noise_db: float = REPORT_NOISE_DB,
    min_cn0_dbhz: float = MIN_CN0_DBHZ,
) -> dict[int, dict[str, float]]:
    """t_ns -> {PRN: C/N0} at the GNSS sample times one `period_s` apart (the first included),
    seen from the true ENU positions `pos` about `origin_llh`."""
    from pnt.integrity.sky import GpsAlmanac

    if period_s <= 0:
        raise ValueError("sky period_s must be positive")
    t_s = (ts_ns - ts_ns[0]) / 1e9
    keep = np.flatnonzero(np.diff(np.floor(t_s / period_s + 1e-9), prepend=-1) > 0)
    t_ns, p = ts_ns[keep], pos[keep]
    # One place for the elevations: the run's median position. A route spans a few km at most,
    # which moves a GPS satellite's elevation by about 0.03 deg per km.
    where = enu_to_llh(np.median(p, axis=0), origin_llh)
    almanac = GpsAlmanac()
    look = almanac.look(t_ns, where)
    prns = sorted(look)
    bias = dict(zip(prns, rng.normal(0.0, prn_bias_db, len(prns)), strict=True))
    out: dict[int, dict[str, float]] = {int(t): {} for t in t_ns}
    for prn in prns:
        el = look[prn][0]
        cn0 = a_dbhz + b_dbhz * np.sin(np.radians(el)) + bias[prn]
        cn0 = np.round(cn0 + rng.normal(0.0, noise_db, len(el)))
        for k in np.flatnonzero((el >= mask_deg) & (cn0 >= min_cn0_dbhz)):
            out[int(t_ns[k])][str(prn)] = float(cn0[k])
    return out
