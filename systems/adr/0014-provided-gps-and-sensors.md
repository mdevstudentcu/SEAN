# ADR-0014: Use the Honeywell-provided GPS HAT, IMU and barometer

- **Status:** Accepted
- **Date:** 2026-11-08, amended 2026-11-09 (the kit's barometer is a BMP180)
- **Deciders:** team
- **Traces to:** REQ-03, REQ-09, RSK-05

## Context

Honeywell's supplies list (2026-11-08) includes an Adafruit Ultimate GPS HAT with an active antenna, and a sensor kit with an MPU6050 IMU and a BMP280 barometer. The kit that arrived on 2026-11-09 has a **BMP180** instead. We had planned to buy a NEO-6M GPS (with a soldered PPS tap), a BMI160 IMU and a BME280 barometer. The team also already owns a Pi camera.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Use the provided parts | In hand now; GPS HAT has PPS wired to GPIO4 (no soldering); saves ~CAD 50 and a Tuesday delivery | MediaTek GPS: no raw measurements, no built-in jamming indicator. MPU6050 is noisier than the BMI160 and I2C-only |
| Buy the planned parts | BMI160 lower noise, SPI | Arrives Tuesday at best; more soldering |

## Decision

Use the GPS HAT on the payload Pi (NMEA on `/dev/serial0`, PPS on GPIO4, read by gpsd and chrony), the MPU6050 and BMP280 on the ESP32 hub's I2C bus, and the Pi camera we own.

## Consequences

- GPS data now enters through the Pi, not the ESP32. The hub only timestamps the PPS edge (a wire from the HAT's PPS pin) and the Pi labels each edge with GPS time. `PNT_GNSS_RAW_NMEA` was removed from `pnt.xml` (#24).
- Interference cues come from per-satellite SNR in the NMEA GSV sentences instead of a receiver jamming flag.
- **Barometer (amended 2026-11-09):** the kit's barometer is a BMP180. It has a different register map and compensation from the BMP280 and answers chip ID `0x55`, at I2C address `0x77` only.
  - `pnt.payload.i2c` probes for either part and records which one it found (`bmp180` or `bmp280` in `meta.yaml`).
  - The sim's `BMP280` noise parameters are datasheet or literature placeholders (`TBC`) for the wrong part. A static session with the BMP180 replaces them with `measured` values (ADR-0015).
  - Using the BMP180 is not a new decision: it is the provided barometer this ADR chose. Buying a BMP280 or BME280 instead would be one.
- Reopen if the lab has a u-blox M8T or ZED-F9P (raw measurements, RTK truth), or if MPU6050 noise limits REQ-01.
- The NEO-6M is still worth buying for the ground reference station, which gets the provided spare Pi.
