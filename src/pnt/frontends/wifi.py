"""Wi-Fi front end (#22): hub MAVLink records -> `wifi` `rssi` and `range` records.

Two ways Wi-Fi reaches a session (ADR-0018):

- **Scans on the Pi 4B** (`pnt.payload.wifi`): the recorder already writes `rssi` records. No
  front end is needed.
- **Scans on a Pi Zero 2 W hub** (the ADR-0018 fallback): the hub sends `pnt.xml` messages
  (ICD, `systems/icd/pnt.xml`), stamped with its own monotonic clock `time_us`. This module turns
  them into records:
  - `PNT_PPS` (`time_us`, `gps_week`, `gps_tow_ms`) pairs the hub clock with GPS time at each
    PPS edge. A record's GPS time is interpolated between the edges either side of it, so the
    hub crystal's drift between edges is taken out. Records outside the edges by more than
    `MAX_EXTRAP_S`, or before two edges exist, have no time and are dropped (counted).
  - `PNT_WIFI_AP` -> `rssi` (dBm), emitter `wifi:<bssid_hash>` in the same 16-hex form as the
    Pi's scans (`pnt.payload.wifi.hash_bssid`), sigma `RSSI_SIGMA_DB` from there too.
  - `PNT_FTM_RANGE` -> `range` (m), sigma c · `rtt_sigma_ns` / 2 (range is half the round
    trip). Nothing sends it today: FTM is dropped because it transmits (ADR-0018). It is
    decoded because the ICD still defines it.

BSSIDs arrive hashed (ADR-0011); nothing here can see a raw BSSID or an SSID. The hub has no
field for its salt's `salt_id`, so a hub session's `wifi salt` event is `TBD`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np

from pnt.core.measurement import Measurement
from pnt.core.time import NS, WEEK_NS
from pnt.payload.wifi import RSSI_SIGMA_DB

C_MPS = 299_792_458.0
# How far past the first or last PPS edge a record may lie and still be timed: TBC. The hub's
# crystal drifts tens of ppm at most, so 2 s of extrapolation costs well under 1 ms.
MAX_EXTRAP_S = 2.0


def channel_mhz(channel: int) -> float | None:
    """Centre frequency of a 2.4 or 5 GHz Wi-Fi channel (IEEE 802.11), None if unknown."""
    if channel == 14:
        return 2484.0
    if 1 <= channel <= 13:
        return 2407.0 + 5 * channel
    if 32 <= channel <= 177:
        return 5000.0 + 5 * channel
    return None


@dataclass
class HubClock:
    """Hub `time_us` -> GPS ns, from its `PNT_PPS` messages.

    Assumes one hub boot (its `time_us` never restarts) and correctly labelled edges."""

    edges_us: list[int] = field(default_factory=list)
    edges_gps_ns: list[int] = field(default_factory=list)
    _table: tuple[np.ndarray, np.ndarray] | None = None

    def add_pps(self, time_us: int, gps_week: int, gps_tow_ms: int) -> None:
        self.edges_us.append(int(time_us))
        self.edges_gps_ns.append(int(gps_week) * WEEK_NS + int(gps_tow_ms) * 1_000_000)
        self._table = None

    def to_gps_ns(self, time_us: int) -> int | None:
        if self._table is None:  # sorted, one entry per edge time
            us, idx = np.unique(np.asarray(self.edges_us, dtype=np.int64), return_index=True)
            self._table = us, np.asarray(self.edges_gps_ns, dtype=np.int64)[idx]
        us, gps = self._table
        if len(us) < 2:
            return None
        if not us[0] - MAX_EXTRAP_S * 1e6 <= time_us <= us[-1] + MAX_EXTRAP_S * 1e6:
            return None
        i = int(np.clip(np.searchsorted(us, time_us) - 1, 0, len(us) - 2))
        rate = (gps[i + 1] - gps[i]) / ((us[i + 1] - us[i]) * 1e3)  # GPS ns per hub ns
        return int(gps[i] + round((time_us - us[i]) * 1e3 * rate))


def _name(msg) -> str:
    if isinstance(msg, dict):
        return msg.get("mavpackettype", "")
    return msg.get_type()


def _field(msg, key):
    return msg[key] if isinstance(msg, dict) else getattr(msg, key)


@dataclass
class Result:
    measurements: list[Measurement]
    untimed: int  # Wi-Fi messages dropped for want of PPS edges around them


def process(messages: Iterable, receiver: str = "payload") -> Result:
    """Hub messages (generated `pnt_mavlink` objects, or their `to_dict()`) -> records.

    The whole list is read first, so a record is timed by the PPS edges either side of it,
    including those that arrive after it."""
    msgs = list(messages)
    clock = HubClock()
    for m in msgs:
        if _name(m) == "PNT_PPS":
            clock.add_pps(_field(m, "time_us"), _field(m, "gps_week"), _field(m, "gps_tow_ms"))
    out: list[Measurement] = []
    untimed = 0
    for m in msgs:
        name = _name(m)
        if name not in ("PNT_WIFI_AP", "PNT_FTM_RANGE"):
            continue
        t = clock.to_gps_ns(_field(m, "time_us"))
        if t is None:
            untimed += 1
            continue
        emitter = "wifi:" + bytes(_field(m, "bssid_hash")).hex()
        if name == "PNT_WIFI_AP":
            ch = int(_field(m, "channel"))
            out.append(
                Measurement(
                    t_ns=t,
                    source="wifi",
                    kind="rssi",
                    emitter=emitter,
                    receiver=receiver,
                    value=(float(_field(m, "rssi")),),
                    sigma=(RSSI_SIGMA_DB,),
                    meta={
                        "freq_mhz": channel_mhz(ch),
                        "channel": ch,
                        "device": "hub",
                        "ftm_responder": bool(_field(m, "ftm_responder")),
                    },
                )
            )
        else:
            out.append(
                Measurement(
                    t_ns=t,
                    source="wifi",
                    kind="range",
                    emitter=emitter,
                    receiver=receiver,
                    value=(float(_field(m, "range_m")),),
                    sigma=(C_MPS * float(_field(m, "rtt_sigma_ns")) / 2 / NS,),
                    meta={"n_frames": int(_field(m, "n_frames")), "device": "hub"},
                )
            )
    return Result(out, untimed)


def parse_bytes(data: bytes) -> list:
    """Raw hub serial bytes -> `pnt_mavlink` messages (bad CRCs and other dialects dropped)."""
    from pnt.io import pnt_mavlink

    mav = pnt_mavlink.MAVLink(None)
    mav.robust_parsing = True  # skip bad frames instead of raising
    return [m for m in mav.parse_buffer(data) or [] if m.get_type() != "BAD_DATA"]
