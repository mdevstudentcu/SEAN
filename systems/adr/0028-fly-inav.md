# ADR-0028: The drone flies INAV on the BLITZ ATF435, pilot-flown with an RC kill switch

- **Status:** Accepted
- **Date:** 2026-11-09
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
