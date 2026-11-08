"""Front-ends: raw signals -> Measurements (systems/icd/measurement.md).

One subpackage per signal family. Each exposes a function or class that turns raw input (IQ
file, readsb JSON, decoder output, ESP32 records) into Measurements with honest sigmas.

Planned (see the SoOP shortlist): adsb (readsb + pyModeS), lte (PSS/SSS timing), vor
(Voracious bearings), wifi (RSSI + FTM from the ESP32 hub), chu (time code), gnss (NMEA from
the GPS HAT via gpsd + per-satellite SNR as an interference cue), imu/baro (ESP32 hub).

Rule: decode only fields meant for everyone; never communication content (ADR-0011).
"""
