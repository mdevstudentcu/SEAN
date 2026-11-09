# ADR-0018: The payload is a Pi 4B recorder; a Pi Zero 2 W hub only if day-1 tests need it

- **Status:** Proposed
- **Date:** 2026-11-08, amended 2026-11-09 (the recorder changed from a Pi 3B+ to a Pi 4B: we have both)
- **Deciders:** team
- **Traces to:** REQ-03, REQ-08, REQ-09, RSK-05, RSK-06; supersedes ADR-0005; settles sim plan D6

## Context

ADR-0005 assumed an ESP32-S3 sensor hub feeding a Pi 4B. We have no ESP32-S3. The first version of this ADR flew a Pi 3B+ because it was thought to be the only board available. We have both a Pi 4B and a Pi 3B+.

The payload records two RTL-SDRs at up to 2.4 MS/s each: 4.8 MB/s each, 9.6 MB/s together, about 35 GB/h. It also reads the MPU6050 and BMP280 (ADR-0014), timestamps the GPS PPS edge, scans Wi-Fi with BSSIDs hashed at capture (ADR-0011), and streams to the laptop over Wi-Fi (ADR-0009).

| | Pi 3B+ | Pi 4B |
| --- | --- | --- |
| USB | All four ports and Ethernet share one USB 2.0 link (480 Mb/s) | USB controller on its own PCIe lane; Ethernet separate |
| CPU | 4× Cortex-A53, 1.4 GHz | 4× Cortex-A72, 1.5–1.8 GHz |
| RAM | 1 GB | 2–8 GB |
| Recording | SD card, or a USB SSD on the shared bus | Faster SD, or a USB 3 SSD with its own bandwidth |
| Power | Lower | Higher; needs a 5 V 3 A supply and cooling |
| Noise | — | USB 3 ports radiate near GPS L1 and 2.4 GHz (RSK-06) |

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Pi 4B, sensors on its own I2C (no hub) | One board and one clock: PPS, IMU and SDR timestamps share the recorder's PPS-disciplined clock; fewest parts | IMU sampled from Linux user space, so jitter is higher than a microcontroller's (`TBD` on day 1); Wi-Fi scans compete with the streaming link on the onboard radio |
| Pi 4B with a Pi Zero 2 W hub | Keeps sensor timing off the recorder; the Zero's radio can scan Wi-Fi while the 4B's radio streams | Two clocks to align (PPS wired to both); extra part, cable and power |
| Pi 3B+ with a Pi Zero 2 W hub (first version of this ADR) | Lower power | Shared USB 2 bus with Ethernet for two SDRs plus the hub; slower cores and 1 GB of RAM for buffering IQ |
| Pico 2W hub (Honeywell supplies) | PIO timestamps PPS edges in hardware | New firmware in C or MicroPython this week, with its own MAVLink build |

## Decision

The payload recorder is the **Raspberry Pi 4B** (recorder and streamer, ADR-0002).

- **SDRs:** both go on the 4B's **USB 2 ports** (the black ones). The USB 3 ports stay empty unless a recording SSD needs one. That SSD is shielded and kept away from the GPS antenna (RSK-06).
- **Sensors:** by default the MPU6050 and BMP280 are on the 4B's I2C bus and the PPS is on its GPIO4, with **no hub**.
- **Hub fallback:** a day-1 test with both SDRs recording measures IMU sample jitter, CPU load, dropped SDR samples and PPS offset (RSK-05). If any fails its threshold (`TBD`), the Pi Zero 2 W hub from the first version of this ADR comes back. It speaks the existing `pnt.xml` MAVLink dialect over USB (ADR-0005's protocol, unchanged).
- **The Pi 3B+** is not on the payload. It runs the ground reference station (ADR-0020).

## Consequences

- **Recording:** a fast A2 microSD card or a USB SSD. The 2 h static capture with both SDRs is about 70 GB, so capacity is planned per session (`TBC`). At 1.92 MS/s it is 3.84 MB/s per SDR.
- **Power and heat:**
  - The 4B draws more and throttles when hot, so it needs a heatsink or fan in the payload box and a 5 V 3 A supply.
  - The USB current for two SDRs (plus the Zero, if used) is measured with the DPS-150 (`TBC`).
- **Time:** without a hub, every timestamp comes from one PPS-disciplined clock on the 4B (chrony + `pps-gpio`), which removes the hub-to-recorder alignment step. RSK-05 is still measured on day 1.
- **Wi-Fi:**
  - RSSI scans only, with BSSIDs hashed on the board that scans (ADR-0011).
  - Without a hub, scanning on the onboard radio interrupts the ZeroMQ link (ADR-0009). Where scans run in flight (the Zero, a second USB Wi-Fi radio, or between streaming windows) is `TBC`.
  - FTM stays dropped: neither Pi's radio is an 802.11mc initiator, and FTM would transmit to third-party access points. `PNT_FTM_RANGE` stays in `pnt.xml` unused; `firmware/ftm-responder/` is removed.
- **Hardware unchanged:** the GPS HAT fits both Pis (same 40-pin header, PPS on GPIO4).
- **Code:** `firmware/esp32-hub/` is no longer built for the payload. Removing it also changes `just gen`, the `justfile` and the CI firmware job (`.github/`), which needs owner sign-off, so it is left for a follow-up. If the hub returns, its code location is `TBD`.
- **Reopen if:**
  - the day-1 test fails on the 4B and the Zero cannot fix it
  - the 4B's USB 3 noise can't be kept off the GPS and SDRs
  - an ESP32-S3 turns up
