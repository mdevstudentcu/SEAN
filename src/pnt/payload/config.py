"""Devices for `pnt record` from its command-line options."""

from __future__ import annotations

from pnt.payload.devices import Camera, FlightController, Health
from pnt.payload.gpsd import Gpsd
from pnt.payload.i2c import Bmp280, Mpu6050
from pnt.payload.sdr import RtlSdr
from pnt.payload.wifi import WifiScan

SDR_KEYS = {"rate": float, "gain": float, "dev": str, "ppm": int}


def parse_sdr(spec: str, index: int) -> RtlSdr:
    """`NAME:FREQ_HZ[:key=value...]`, keys rate (S/s), gain (dB; omit for auto), dev (index or
    serial; default: the order given), ppm. E.g. `a:875e6:rate=1.92e6:gain=40`."""
    name, freq, *rest = spec.split(":")
    if not name or not name.isalnum():
        raise ValueError(f"SDR name must be letters/digits, e.g. 'a': {spec!r}")
    opts: dict = {"dev": str(index)}
    for kv in rest:
        k, _, v = kv.partition("=")
        if k not in SDR_KEYS:
            raise ValueError(f"unknown SDR option {k!r} in {spec!r} (known: {sorted(SDR_KEYS)})")
        opts[k] = SDR_KEYS[k](v)
    return RtlSdr(
        name,
        float(freq),
        rate_hz=opts.get("rate", 1.92e6),
        gain_db=opts.get("gain"),
        device=opts["dev"],
        ppm=opts.get("ppm", 0),
    )


def parse_llh(text: str | None) -> tuple[float, float, float] | None:
    if text is None:
        return None
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 3:
        raise ValueError(f"expected lat,lon,h: {text!r}")
    return parts[0], parts[1], parts[2]


def build(args) -> list:
    """The device list for `pnt record` (absent hardware is found by each device's probe)."""
    devices: list = [Health()]
    if not args.no_gnss:
        devices.append(Gpsd(port=args.gpsd_port, hardware=args.gnss_hw))
    if not args.no_imu:
        devices.append(Mpu6050(rate_hz=args.imu_rate))
    if not args.no_baro:
        devices.append(Bmp280(rate_hz=args.baro_rate, start_up_m=args.baro_start_up))
    devices += [parse_sdr(s, i) for i, s in enumerate(args.sdr or [])]
    if not args.no_camera:
        devices.append(Camera())
    if not args.no_fc:
        devices.append(FlightController(args.fc, baud=args.fc_baud))
    if args.wifi:
        devices.append(WifiScan(args.wifi_iface))
    return devices
