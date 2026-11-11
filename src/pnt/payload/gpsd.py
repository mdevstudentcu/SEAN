"""GPS HAT through gpsd (ADR-0014): fixes as `gnss` Measurements, PPS edges as `/events`.

gpsd speaks JSON lines on TCP port 2947. We ask for TPV (fixes), SKY (satellites) and PPS
(edges seen on /dev/pps0, with the host clock at each edge).

- `position_enu` from each 3D fix, time-tagged with the fix's own GPS time. Its sigma is gpsd's
  95 % error estimate (`epx`, `epy`, `epv`) over 1.96. gpsd derives those from DOP and an
  assumed range error, since the MediaTek chip reports none: `TBC` against a surveyed point.
- `velocity_enu` from speed, track and climb of a 3D fix, sigma from `eps`/`epc` the same way.
- No `gnss_health` here: the chip has no jamming indicator. SKY goes to `/events` as
  `gnss_sky`, and the ground front end (`pnt frontend gnss`) makes `gnss_health` from its
  per-satellite SNR (ADR-0031).
- PPS: `/events` `pps` with `offset_ns` = host clock minus GPS at the edge (RSK-05).
"""

from __future__ import annotations

import json
import math
import socket
from datetime import datetime

from pnt.core import frames
from pnt.core.measurement import Measurement
from pnt.core.time import NS, now_gps_ns, unix_ns_to_gps_ns, utc_to_gps_ns
from pnt.payload.recorder import Fix

WATCH = b'?WATCH={"enable":true,"json":true,"pps":true};\n'
Z95 = 1.96  # 95 % two-sided, one axis


def parse_time(iso: str) -> int:
    """gpsd's ISO-8601 UTC time ("2026-11-10T14:30:00.000Z") as GPS ns."""
    return utc_to_gps_ns(datetime.fromisoformat(iso.replace("Z", "+00:00")))


def tpv_llh(tpv: dict) -> tuple[float, float, float] | None:
    """WGS84 lat, lon and ellipsoidal height of a 3D fix (None for no fix or 2D)."""
    if tpv.get("mode", 0) < 3 or "lat" not in tpv or "lon" not in tpv:
        return None
    if "altHAE" in tpv:
        h = tpv["altHAE"]
    elif "alt" in tpv and "geoidSep" in tpv:  # older gpsd: alt is MSL
        h = tpv["alt"] + tpv["geoidSep"]
    else:
        return None
    return float(tpv["lat"]), float(tpv["lon"]), float(h)


def tpv_measurements(tpv: dict, origin_llh) -> list[Measurement]:
    """`position_enu` and `velocity_enu` from one TPV report."""
    if "time" not in tpv:
        return []
    t = parse_time(tpv["time"])
    meta = {"mode": tpv.get("mode"), "device": "gpsd"}
    out = []
    llh = tpv_llh(tpv)
    if llh is not None and all(k in tpv for k in ("epx", "epy", "epv")):
        enu = frames.llh_to_enu(llh, origin_llh)
        sig = (tpv["epx"] / Z95, tpv["epy"] / Z95, tpv["epv"] / Z95)
        out.append(
            Measurement(
                t_ns=t,
                source="gnss",
                kind="position_enu",
                value=tuple(float(x) for x in enu),
                sigma=tuple(float(x) for x in sig),
                meta={**meta, "llh": list(llh)},
            )
        )
    if tpv.get("mode", 0) >= 3 and all(
        k in tpv for k in ("speed", "track", "eps", "climb", "epc")
    ):
        tr = math.radians(tpv["track"])
        ve, vn, vu = tpv["speed"] * math.sin(tr), tpv["speed"] * math.cos(tr), tpv["climb"]
        sh, sv = tpv["eps"] / Z95, tpv["epc"] / Z95
        out.append(
            Measurement(
                t_ns=t,
                source="gnss",
                kind="velocity_enu",
                value=(float(ve), float(vn), float(vu)),
                sigma=(float(sh), float(sh), float(sv)),
                meta=meta,
            )
        )
    return out


def pps_event(msg: dict) -> dict:
    """gpsd PPS report -> `/events` data. `real` is GPS time of the edge, `clock` the host's."""
    real = msg["real_sec"] * NS + msg["real_nsec"]
    clock = msg["clock_sec"] * NS + msg["clock_nsec"]
    return {
        "text": "pps",
        "edge_t_ns": unix_ns_to_gps_ns(real),
        "offset_ns": clock - real,
        "precision": msg.get("precision"),
        "device": msg.get("device"),
    }


def sky_event(msg: dict) -> dict:
    """A SKY report as the `gnss_sky` event. `listed` says whether gpsd sent a satellite list
    at all (it is optional); an empty list is a sky with nothing in it, not a missing one."""
    sats = msg.get("satellites") or []
    used = [s for s in sats if s.get("used")]
    snr = [s["ss"] for s in used if "ss" in s]
    return {
        "text": "gnss_sky",
        "listed": isinstance(msg.get("satellites"), list),
        "n_seen": len(sats),
        "n_used": len(used),
        "hdop": msg.get("hdop"),
        "snr_used_mean": sum(snr) / len(snr) if snr else None,
        "snr_used_min": min(snr) if snr else None,
        "snr": {str(s.get("PRN")): s.get("ss") for s in sats},
    }


class Gpsd:
    """The GPS HAT, through gpsd on the same host."""

    name = "gnss"

    def __init__(
        self, host: str = "127.0.0.1", port: int = 2947, hardware: str = "adafruit-gps-hat"
    ):
        self.host, self.port, self.hardware = host, port, hardware
        self.fixes = 0
        self.pps = 0
        self.reconnects = 0
        self.repeats = 0
        self._last_tpv: str | None = None

    def probe(self) -> str | None:
        try:
            socket.create_connection((self.host, self.port), timeout=2).close()
        except OSError as exc:
            return f"gpsd not reachable at {self.host}:{self.port}: {exc}"
        return None

    def status(self) -> dict:
        return {"fixes": self.fixes, "pps": self.pps, "reconnects": self.reconnects,
                "repeated_tpv": self.repeats}  # fmt: skip

    def handle(self, msg: dict, ctx) -> None:
        cls = msg.get("class")
        now = now_gps_ns()
        if cls == "TPV":
            # gpsd can report one fix several times as NMEA sentences of the same epoch arrive;
            # fusing it twice would count it twice. Keep the first report of each fix time.
            if msg.get("time") is not None and msg.get("time") == self._last_tpv:
                self.repeats += 1
                return
            self._last_tpv = msg.get("time")
            llh = tpv_llh(msg)
            if llh is not None:
                origin = ctx.set_origin_once(llh)
            else:
                origin = ctx.origin_llh
            if origin is None:
                return
            for m in tpv_measurements(msg, origin):
                ctx.emit(m)
                if m.kind == "position_enu":
                    self.fixes += 1
                    ctx.last_fix = Fix(m.t_ns, llh, m.value[2])
        elif cls == "PPS":
            self.pps += 1
            ctx.event(now, **pps_event(msg))
        elif cls == "SKY":
            ctx.event(now, **sky_event(msg))
        elif cls == "DEVICES":
            ctx.event(now, "gpsd_devices", devices=msg.get("devices", []))

    def run(self, ctx) -> None:
        while not ctx.stop.is_set():
            try:
                self._session(ctx)
            except OSError as exc:
                ctx.event(now_gps_ns(), "gpsd connection lost", error=repr(exc))
            if not ctx.stop.wait(2.0):
                self.reconnects += 1

    def _session(self, ctx) -> None:
        with socket.create_connection((self.host, self.port), timeout=5) as sock:
            sock.settimeout(1.0)
            sock.sendall(WATCH)
            buf = b""
            while not ctx.stop.is_set():
                try:
                    data = sock.recv(65536)
                except TimeoutError:
                    continue
                if not data:
                    raise ConnectionError("gpsd closed the connection")
                buf += data
                *lines, buf = buf.split(b"\n")
                for line in lines:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    self.handle(msg, ctx)
