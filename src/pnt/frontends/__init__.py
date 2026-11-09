"""Front-ends: raw signals -> Measurements (systems/icd/measurement.md).

One subpackage per signal family. Each exposes a function or class that turns raw input (IQ
file, readsb JSON, decoder output, hub records) into Measurements with honest sigmas.

Planned (see the SoOP shortlist): adsb (readsb + pyModeS), lte (PSS/SSS timing), vor
(Voracious bearings), wifi (RSSI from the Pi Zero 2 W hub), gnss (NMEA from
the GPS HAT via gpsd + per-satellite SNR as an interference cue), imu/baro (hub).

Rule: decode only fields meant for everyone; never communication content (ADR-0011).
"""
