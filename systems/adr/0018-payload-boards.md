# ADR-0018: The payload is a Pi 3B+ recorder with a Pi Zero 2 W sensor hub

- **Status:** Proposed
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-03, REQ-08, REQ-09, RSK-05, RSK-06; supersedes ADR-0005; settles sim plan D6

## Context

ADR-0005 assumed an ESP32-S3 sensor hub feeding a Pi 4B. We have no ESP32-S3, and the Pi that will fly is a 3B+ (sim plan D6). The hub still has a job: read the MPU6050 and BMP280 (ADR-0014), timestamp the GPS PPS edge, and scan Wi-Fi with BSSIDs hashed before they leave it (ADR-0011), without competing with the recorder for CPU.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Pi Zero 2 W hub | Same OS and Python as the recorder; the MAVLink dialect already generates Python (`src/pnt/io/pnt_mavlink.py`); powered and linked over one USB cable | Linux user-space timestamps jitter more than a microcontroller timer; no Wi-Fi FTM; 2.4 GHz scans only |
| Pico 2W hub (Honeywell supplies) | PIO timestamps PPS edges in hardware; microcontroller like the ESP32 | New firmware in C or MicroPython this week, with its own MAVLink build; no FTM |
| No hub: sensors on the Pi 3B+ | Fewest parts | IMU sampling shares four A53 cores with two SDR captures; sensors wire through the GPS HAT's prototyping area |

## Decision

The payload is a Raspberry Pi 3B+ (recorder and streamer, ADR-0002) with a Raspberry Pi Zero 2 W as the sensor hub, speaking the existing `pnt.xml` MAVLink dialect (ADR-0005's protocol, unchanged) over USB.

## Consequences

- **Link:** the Zero's data port goes to a 3B+ USB port as a USB gadget, which also powers it. Serial (CDC ACM) or network (CDC ECM, which also lets the Zero take coarse time from the 3B+ by NTP) is `TBC`.
- **Time:** the HAT's PPS line (GPIO4) is also wired to a Zero GPIO (`TBC`), read with `pps-gpio` and chrony. Hub timestamps are the Zero's PPS-disciplined clock. RSK-05 is measured on day 1 as before; a Linux hub makes it more likely, not certain.
- **Sensors:** ADR-0014's MPU6050 and BMP280 move from the ESP32's I2C bus to the Zero's. IMU rate is `TBD` from that day-1 measurement, not ADR-0005's 1 kHz.
- **Wi-Fi:** RSSI scans only, hashed on the Zero (ADR-0011). FTM is dropped: the Zero's radio has no 802.11mc initiator. `PNT_FTM_RANGE` stays in `pnt.xml` unused; `firmware/ftm-responder/` is removed.
- **Power:** two SDRs plus the Zero on the 3B+'s USB ports may exceed its 1.2 A USB budget (`TBC`, measure with the DPS-150). If it does, feed the Zero from the 5 V rail.
- **USB:** the 3B+ has only USB 2 ports, sharing one bus with its Ethernet. The phase P rehearsal (sim plan) must show both SDRs at their planned sample rate with the hub attached; otherwise decide between one radio and a lower rate.
- **Code:** `firmware/esp32-hub/` is no longer built for the payload. Removing it also changes `just gen`, the `justfile` and the CI firmware job (`.github/`), which needs owner sign-off, so it is left for a follow-up. Hub code location is `TBD`.
- Reopen if the day-1 PPS jitter on the Zero is too large for REQ-03, or if an ESP32-S3 turns up.
