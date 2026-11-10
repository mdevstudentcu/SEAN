"""ADS-B front end (#22): readsb raw frames, decoded by pyModeS -> `adsb` `adsb_report` records.

**Input.** Mode S frames as readsb's raw output port prints them (`--net-ro-port`, conventionally
30002; https://github.com/wiedehopf/readsb), one frame per line in the AVR text form that
dump1090 established: `*<hex>;`, or `@<12 hex digits of readsb's 12 MHz clock><hex>;` with
`--net-ro-mlat`-style timestamps. Each line comes paired with the host GPS-ns time it arrived
(`process`). Which recorder logs those lines on the payload, and in what file, is `TBD`: none
does yet.

**Decoding.** Only DF17/DF18 extended squitters are decoded: ADS-B broadcasts meant for
everyone (ADR-0011). Replies to ground interrogations (DF4/5/20/21) are dropped unread. A
`pyModeS.PipeDecoder` resolves airborne positions from even/odd CPR pairs (no reference
position needed) and later frames locally from the last one. It holds a new aircraft's
positions back until three of them agree, so the first reports of each track are not emitted.

**Output.** One `adsb_report` per resolved airborne position (TC 9-18, 20-22), emitter
`adsb:<icao>`:

- `value` = (e, n, u, nacp, nic): the aircraft about the session origin, its latest NACp, and
  the NIC of this position message.
- NACp comes from the aircraft's latest operational status (TC 31) or target state (TC 29)
  message; until one arrives it is 0, which DO-260B defines as "unknown accuracy".
- NIC comes from the type code with the NIC supplements (`nic`), as DO-260B tables it.
- `u`: TC 20-22 carry GNSS height above the ellipsoid. TC 9-18 carry pressure altitude, which
  is not a height: it is used as one, with `BARO_ALT_SIGMA_M`, and `meta.alt_type` says so.
- `sigma` (1-sigma): horizontally the NACp's 95 % bound (EPU) over 2.45, the 95 % radius of a
  circular Gaussian; vertically its VEPU over 1.96 where NACp defines one and the height is
  GNSS, else `BARO_ALT_SIGMA_M`. NACp and NIC are categories: their sigma is 0.

ADS-B positions are the aircraft's own GNSS fix (GNSS-derived, ADR-0024): a jammed or spoofed
aircraft reports a jammed or spoofed position, and NIC/NACp may not show it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from pnt.core import frames
from pnt.core.measurement import Measurement

FT = 0.3048
# DO-260B NACp -> (EPU, VEPU), metres, 95 %. NACp 0 is "unknown or >= 10 NM": its EPU here is
# 10 NM, so the sigma it gives is a floor, not a bound.
NACP_EPU_M: dict[int, tuple[float, float | None]] = {
    11: (3.0, 4.0), 10: (10.0, 15.0), 9: (30.0, 45.0), 8: (92.6, None), 7: (185.2, None),
    6: (555.6, None), 5: (926.0, None), 4: (1852.0, None), 3: (3704.0, None),
    2: (7408.0, None), 1: (18520.0, None), 0: (18520.0, None),
}  # fmt: skip
R95_2D = 2.4477  # 95 % radius of a circular 2D Gaussian, in sigmas
Z95 = 1.96
# Pressure altitude used as height: 1-sigma, m. TBC. It differs from ellipsoidal height by the
# day's departure from the standard atmosphere (about 8 m per hPa) and the geoid (-34 m near
# Ottawa); both are left in this sigma until a QNH and geoid correction exist.
BARO_ALT_SIGMA_M = 100.0
EXTENDED_SQUITTER = (17, 18)


def nic(tc: int, version: int, nic_a: int, nic_b: int) -> int:
    """NIC of an airborne position message (DO-260B, ADS-B version 1 and 2).

    `nic_b` is the position message's own supplement bit; `nic_a` comes from the aircraft's
    operational status (TC 31). Version 0 and unknown versions defined no supplements: they get
    the lower of the two values a type code allows."""
    base = {9: 11, 10: 10, 12: 7, 13: 6, 14: 5, 15: 4, 17: 1, 18: 0, 20: 11, 21: 10, 22: 0}
    if tc in base:
        return base[tc]
    if tc not in (11, 16):
        raise ValueError(f"type code {tc} is not an airborne position")
    hi, lo = (9, 8) if tc == 11 else (3, 2)
    if version == 1:
        return hi if nic_b else lo
    if version >= 2:
        return hi if (nic_a and nic_b) else lo
    return lo


def parse_avr(line: str) -> str | None:
    """`*8D...;` or `@<12 hex>8D...;` -> the frame's hex, upper case. None if it is not one."""
    s = line.strip()
    if s.startswith("*"):
        body = s[1:]
    elif s.startswith("@"):
        body = s[13:]
    else:
        return None
    body = body.rstrip(";")
    if len(body) not in (14, 28):
        return None
    try:
        int(body, 16)
    except ValueError:
        return None
    return body.upper()


@dataclass
class _Aircraft:
    nac_p: int = 0
    version: int | None = None
    nic_a: int = 0


@dataclass
class Decoder:
    """Stateful: feed frames in arrival order with `add`, or all at once with `process`."""

    origin_llh: tuple[float, float, float]
    receiver: str = "payload"
    _pipe: object = None
    _aircraft: dict[str, _Aircraft] = field(default_factory=dict)
    decoded: int = 0  # DF17/18 frames with a good CRC
    skipped: int = 0  # not DF17/18, or bad CRC

    def __post_init__(self):
        import pyModeS

        self._pipe = pyModeS.PipeDecoder()

    def add(self, t_ns: int, line: str) -> Measurement | None:
        msg = parse_avr(line)
        if msg is None or (int(msg[:2], 16) >> 3) not in EXTENDED_SQUITTER:
            self.skipped += 1
            return None
        d = self._pipe.decode(msg, timestamp=t_ns / 1e9)
        if not d.get("crc_valid", False):
            self.skipped += 1
            return None
        self.decoded += 1
        icao = str(d["icao"]).lower()
        ac = self._aircraft.setdefault(icao, _Aircraft())
        tc = d.get("typecode")
        if tc in (29, 31) and d.get("nac_p") is not None:
            ac.nac_p = int(d["nac_p"]) if d["nac_p"] in NACP_EPU_M else 0  # 12-15: reserved
        if tc == 31:
            if d.get("subtype") == 0:  # airborne status: its supplement A applies to positions
                ac.nic_a = int(d.get("nic_supplement_a") or 0)
            ac.version = d.get("version")
        if tc is None or not (9 <= tc <= 18 or 20 <= tc <= 22):
            return None
        if d.get("latitude") is None or d.get("altitude") is None:
            return None
        return self._report(t_ns, icao, tc, d, ac)

    def _report(self, t_ns, icao, tc, d, ac) -> Measurement:
        gnss_height = tc >= 20
        h = d["altitude"] * FT
        e, n, u = frames.llh_to_enu((d["latitude"], d["longitude"], h), self.origin_llh)
        epu, vepu = NACP_EPU_M[ac.nac_p]
        s_h = epu / R95_2D
        s_v = vepu / Z95 if (gnss_height and vepu is not None) else BARO_ALT_SIGMA_M
        version = ac.version if ac.version is not None else -1
        return Measurement(
            t_ns=int(t_ns),
            source="adsb",
            kind="adsb_report",
            emitter=f"adsb:{icao}",
            receiver=self.receiver,
            value=(
                float(e),
                float(n),
                float(u),
                float(ac.nac_p),
                float(nic(tc, version, ac.nic_a, d.get("nic_b") or 0)),
            ),
            sigma=(s_h, s_h, s_v, 0.0, 0.0),
            meta={
                "typecode": tc,
                "alt_type": "gnss_hae" if gnss_height else "baro_pressure",
                "llh": [d["latitude"], d["longitude"], h],
                "version": ac.version,
            },
        )


def process(
    frames_: Iterable[tuple[int, str]], origin_llh, receiver: str = "payload"
) -> list[Measurement]:
    """(host GPS ns, raw AVR line) pairs, in arrival order -> `adsb_report` records."""
    dec = Decoder(tuple(origin_llh), receiver)
    out = []
    for t_ns, line in frames_:
        m = dec.add(t_ns, line)
        if m is not None:
            out.append(m)
    return out
