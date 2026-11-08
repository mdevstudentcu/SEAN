"""Runs on the Raspberry Pi (ADR-0002): record raw data, stream light Measurements.

Planned modules:
- recorder: start/stop a session folder (systems/icd/session.md), rtl_sdr captures with
  PPS-aligned start times, readsb, camera, ESP32 hub MAVLink -> /meas/* records
- streamer: ZeroMQ PUB of Measurements (ADR-0009)
- health: chrony/PPS offset, SDR overruns, disk space

Keep dependencies to the `payload` extra.
"""
