"""Front-ends: raw signals -> Measurements (systems/icd/measurement.md).

One subpackage per signal family. Each exposes a function or class that turns raw input (IQ
file, readsb JSON, decoder output, hub records) into Measurements with honest sigmas.

Built: lte (PSS/SSS cell search and TOA tracking on RTL-SDR captures, `pnt frontend lte`),
gnss (gpsd reports -> fixes and `gnss_health` from per-satellite SNR, `pnt frontend gnss`,
ADR-0031), adsb (readsb raw frames decoded by pyModeS), vor (Voracious radials -> bearings),
wifi (hub MAVLink records -> RSSI and range, ADR-0018), spectrum (`rtl_power` band power for
the RF survey).

Planned (see the SoOP shortlist): imu/baro (I2C on the Pi, ADR-0018).

Rule: decode only fields meant for everyone; never communication content (ADR-0011).
"""
