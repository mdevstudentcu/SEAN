"""Runs on the Raspberry Pi (ADR-0002): record raw data, stream light Measurements.

- recorder: `pnt record`, one session folder (systems/icd/session.md), a thread per device
- gpsd, i2c (MPU6050, BMP280 or BMP180), sdr (rtl_sdr IQ + sidecar), devices (camera, flight
  controller, health), wifi (passive scans, BSSIDs hashed at capture; off by default)
- streamer: ZeroMQ PUB of Measurements (ADR-0009), read on the laptop by `sources.live`
- survey (`pnt survey`, #85) and day1 (`pnt day1`, `pnt pps-check`, #88, #17)

Keep dependencies to the `payload` extra.
"""
