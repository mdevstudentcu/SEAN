"""VOR front end (#22): Voracious radials -> `vor` `bearing` records.

**Input.** Voracious (MIT, https://docs.rs/crate/voracious/0.4.1, source in
https://github.com/xoolive/desperado) decodes a VOR from RTL-SDR IQ and prints JSON Lines, one
object per radial window (3 s by default, `--window`). The fields this reads, as its README
documents them for 0.4.1:

    {"timestamp": 1762539961.05835, "radial_deg": 115.31, "frequency_mhz": 116.0,
     "signal_quality": {"clipping_ratio": "<1.82e-7", "snr_30hz_db": 36.89,
                        "snr_9960hz_db": 15.7, "lock_quality": "9.72e-2",
                        "radial_variance": "1.00e0"},
     "ident": "ARL"}

- `timestamp`: Unix seconds, UTC. Live, the wall-clock time when the window is printed. From a
  file, Voracious's start time for the file (from a gqrx file name, or the file's creation or
  modification time) plus elapsed time: pass `file_t0` to put those on the capture's own clock
  (its sidecar `t_ns`) instead. Where in the window the radial is valid is `TBD`.
- `radial_deg`: the VOR radial, i.e. the magnetic bearing from the station to the receiver.
- `ident`: the Morse identifier, when Voracious decoded one.
- `signal_quality`: kept in `meta` as given. Voracious says these are relative within one run,
  so nothing here thresholds them.

**Stations.** A radial is only a bearing with the station's position and magnetic variation,
which the caller passes (`Station`; `data/reference/navaids.csv` is `TBD`). A record is matched
by its ident; with no ident, by its frequency if one station has it. A record whose ident and
frequency name different stations, or no known station, is dropped and counted.

**Output.** `bearing` (ICD-measurement): from the station to us, clockwise from true north, rad
in [0, 2π): radial + the station's magnetic variation (east positive). Emitter `vor:<ident>`,
`meta.emitter_llh` the station. Sigma is `BEARING_SIGMA_DEG`, a placeholder: the radial's
white noise only. The station's alignment error is constant, so the estimator holds it as a
bias state per station (`pnt.nav.ekf`), not the record.

The receiver only listens to the VOR broadcast (ADR-0001); Voracious runs outside this repo.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass

from pnt.core.measurement import Measurement
from pnt.core.time import unix_ns_to_gps_ns

# 1-sigma of one radial's white noise, degrees. Placeholder (TBC) until a static session at a
# surveyed point measures the radials' scatter about their mean. It leaves out the station's own
# alignment error (the mean's offset from the true bearing): the EKF's per-station bias state
# holds that (`BEARING_BIAS_SIGMA_RAD`, #155).
BEARING_SIGMA_DEG = 2.0
# VOR channels are 50 kHz apart: a frequency within half of that names the channel.
FREQ_TOL_MHZ = 0.025


@dataclass(frozen=True)
class Station:
    ident: str
    freq_mhz: float
    lat: float
    lon: float
    h: float  # m, WGS84 ellipsoid
    magvar_deg: float  # the station's magnetic variation, east positive


@dataclass
class Result:
    measurements: list[Measurement]
    unmatched: int  # no known station, or ident and frequency disagree
    unreadable: int  # not JSON, or no timestamp, radial or frequency


def _match(rec: dict, stations: dict[str, Station]) -> Station | None:
    freq = float(rec["frequency_mhz"])
    on_freq = [s for s in stations.values() if abs(s.freq_mhz - freq) <= FREQ_TOL_MHZ]
    ident = (rec.get("ident") or "").strip().upper()
    if ident:
        st = stations.get(ident)
        return st if st is not None and st in on_freq else None
    return on_freq[0] if len(on_freq) == 1 else None


def process(
    lines: Iterable[str],
    stations: Iterable[Station],
    receiver: str = "payload",
    file_t0: tuple[float, int] | None = None,
) -> Result:
    """Voracious JSON Lines -> `bearing` records, for the stations given.

    `file_t0` = (the Unix seconds Voracious took as the file's start, GPS ns of its sample 0)
    re-times records from a file; without it, `timestamp` is taken as UTC as it stands."""
    table = {s.ident.upper(): s for s in stations}
    out: list[Measurement] = []
    unmatched = unreadable = 0
    sigma = math.radians(BEARING_SIGMA_DEG)
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            t_unix_ns = round(float(rec["timestamp"]) * 1e9)
            radial = float(rec["radial_deg"])
            float(rec["frequency_mhz"])
        except (ValueError, KeyError, TypeError):
            unreadable += 1
            continue
        st = _match(rec, table)
        if st is None:
            unmatched += 1
            continue
        if file_t0 is None:
            t_ns = unix_ns_to_gps_ns(t_unix_ns)
        else:
            t_ns = file_t0[1] + t_unix_ns - round(file_t0[0] * 1e9)
        out.append(
            Measurement(
                t_ns=t_ns,
                source="vor",
                kind="bearing",
                emitter=f"vor:{st.ident}",
                receiver=receiver,
                value=(math.radians((radial + st.magvar_deg) % 360.0),),
                sigma=(sigma,),
                meta={
                    "emitter_llh": [st.lat, st.lon, st.h],
                    "radial_deg": radial,
                    "magvar_deg": st.magvar_deg,
                    "freq_mhz": float(rec["frequency_mhz"]),
                    "ident_decoded": bool((rec.get("ident") or "").strip()),
                    "signal_quality": rec.get("signal_quality") or {},
                },
            )
        )
    return Result(out, unmatched, unreadable)
