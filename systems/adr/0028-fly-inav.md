# ADR-0028: The drone flies INAV on the BLITZ ATF435, pilot-flown with an RC kill switch

- **Status:** Accepted; *Amendment 2026-11-11 (owners)*: the drone flies Betaflight 4.5.5, not INAV
- **Date:** 2026-11-09, amended 2026-11-11 (fly Betaflight 4.5.5, decided by the owners: see *Amendment 2026-11-11 (owners)*)
- **Deciders:** Shrikar Vempati, M. Elshoubky (the two owners)
- **Traces to:** REQ-09, RSK-01, RSK-09, ADR-0012 (superseded), `safety.md`

## Context

ADR-0012 assumed ArduPilot: scripted flights in GUIDED mode over MAVLink with pymavlink, and our navigation fed back to the flight controller only in SITL. The team's flight controller is the iFlight BLITZ ATF435 stack (`hardware/bom.md`). Its AT32F435 processor isn't supported by ArduPilot (no AT32F435 board in `libraries/AP_HAL_ChibiOS/hwdef/`, checked 2026-11-09). INAV has an `IFLIGHT_BLITZ_ATF435` target.

The demo (`plan.md`) doesn't need autonomous flight. The payload is platform-agnostic (REQ-09) and records the same data whether the drone is flown, hand-carried or driven.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. INAV on the BLITZ ATF435, pilot-flown | Hardware in hand; GPS and optical-flow position hold; failsafe on RC loss | No pymavlink GUIDED scripting; SITL behaviour won't match; MAVLink signing `TBC` |
| B. Buy an ArduPilot-supported flight controller | Keeps ADR-0012 as written | Must arrive by Tue 2026-11-10 (BOM rule 1); its harness must match the E55S ESC; re-wiring days before judging |
| C. Betaflight | Same hardware | No navigation modes |

## Decision

Option A. The drone flies INAV on the BLITZ ATF435.
- **An independent RC link with a physical kill switch is always fitted,** as in ADR-0012. Without it the drone doesn't fly.
- **Flights are pilot-flown,** using INAV position hold: GPS outdoors, MTF-01 optical flow and rangefinder indoors. INAV waypoint missions, planned in INAV Configurator, are optional.
- **The payload records INAV's MAVLink telemetry, listen-only** (`/mavlink/fc`, #114). Which messages INAV sends, and at what rate, is `TBC`.
- **Our navigation is never fed to the flight controller.** "Our nav in the loop" stays in ArduPilot SITL, which is used only to make trajectories for the sim.

## Consequences

- **Superseded:** `flight/missions/fly.py` and `flight/params/*.param` (ArduPilot) no longer apply to the real drone. They stay for SITL.
- **To fill in before the first flight:** INAV's failsafe (RC loss → land) and any geofence the installed INAV version supports, both `TBC`. `safety.md` keeps the netted area, prop guards and speed limit.
- **To buy:** the RC transmitter and receiver with a kill switch (`hardware/bom.md`).
- **Reopen if:** an ArduPilot-supported flight controller is fitted, or scripted autonomous flight becomes part of the demo.

## Amendment 2026-11-11 (owners): fly Betaflight 4.5.5, not INAV

INAV was never flashed. The owners chose to stay on Betaflight. The *Decision* and *Consequences* above are not edited; where they name INAV, read this amendment. Still in force: pilot-flown, an RC link with a physical kill switch before any flight, the payload listens to the flight controller's MAVLink, and our navigation is never fed to the flight controller.

**Why Betaflight:** it is quicker to a working link; it gives bidirectional DShot and blackbox RPM for future rotor-speed velocity work; and it sends MAVLink telemetry for the payload.

**What we lose against INAV:** GPS and optical-flow position hold, a controlled LAND failsafe (on RC loss the motors stop and the drone drops), and geofence.

**What was done on 2026-11-11** (config backups `diff all` before and after, kept off git):

- **Firmware:** Betaflight 4.5.5, a cloud build for `IFLIGHT_BLITZ_F435` (the iFlight BLITZ ATF435) with `USE_SERIALRX_IBUS` and `USE_TELEMETRY_MAVLINK` (confirmed in the build log). Flashed with `dfu-util` over USB DFU (AT32 bootloader, USB ID `2e3c:df11`).
  - The factory build, Betaflight 4.5.2, had only the CRSF receiver driver; iBUS and SBUS were compiled out. With iBUS selected the flight controller reported 0 channels, with CRSF 16.
- **Receiver:** FlySky FS-i6 transmitter and FS-iA6B receiver, iBUS into flight-controller **UART4** (R4 pad, pin A01) at 115200 baud. Measured 130 frames/s.
  - Channel order AETR is correct.
  - Every stick reaches 1000–2000 (throttle low 907), and each direction is correct.
- **Switches:**
  - **ARM = AUX1 (channel 5) = SwB**, armed at 1700–2100. SwB is the kill switch.
  - **ANGLE = AUX2 (channel 6) = SwA**, ANGLE at 900–1300 (SwA's resting position); the other position is acro.
- **Failsafe:**
  - The FS-iA6B's default on signal loss is to **hold** the last values. Seen on the bench: with the transmitter off, the flight controller kept reading channel 5 = 2000 (armed).
  - Fixed in the transmitter (*RX setup → Failsafe*): **CH3 on at −119 %** (throttle low) and **CH5 on at −100 %** (disarmed).
  - Checked live: SwB armed, transmitter off, channel 5 dropped to 1000.
  - Betaflight's own `failsafe_procedure` stays `DROP` (the default).
- **MAVLink to the Pi:** flight-controller **UART1** runs MAVLink telemetry at 115200 baud (`serial 0 512 ...`). Planned wiring: **flight-controller TX1 → Pi GPIO13 (`uart5` RX) and GND only.** The Pi's TX is not connected, so the Pi physically cannot command the flight controller. Which MAVLink messages Betaflight sends, and at what rate, is `TBC` until the payload records them (#114).
- **Accelerometer level calibration:** done on a level surface (MSP `MSP_ACC_CALIBRATION`). Attitude went from roll 0.4° / pitch 2.6° to 0.0° / 0.0°.
- **Motor check, props off,** each motor spun alone over MSP:
  - Order is correct: M1 rear-right, M2 front-right, M3 rear-left, M4 front-left (Betaflight's Quad X default, props in).
  - M1 CW and M2 CCW were correct. **M3 and M4 spun the wrong way**, fixed in the ESC with `dshotprog 2 21 12` and `dshotprog 3 21 12` (DShot: spin direction reversed, then save). Re-tested: M3 CCW, M4 CW.
  - All four directions confirmed at slow speed (M1 re-checked slowly: CW).

**Open before the first flight:**

- Props matched to each motor's direction: CCW ("R") props on M2 and M3.
- Bidirectional DShot: whether the E55S ESC firmware supports it is unknown (`TBC`).
- `failsafe_throttle` tuning, only if Betaflight's AUTO-LAND failsafe is ever used instead of `DROP`.

**Effect on other files:** `safety.md` (H4, H5, *Flight*) states the real failsafe chain and its limit; `flight/README.md` has the Betaflight pre-flight items, the FS-i6 menu reference and the before-every-arming checklist. ADR-0029's ESP32 bridge is retired by its own *Reopen if* (see its amendment); it speaks CRSF, which this build does not have.
