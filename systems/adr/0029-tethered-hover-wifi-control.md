# ADR-0029: Tethered indoor hover may be flown from a gamepad through an ESP32 Wi-Fi bridge

- **Status:** Accepted
- **Date:** 2026-11-09
- **Deciders:** Shrikar Vempati, M. Elshoubky (the two owners)
- **Traces to:** REQ-07, REQ-09, RSK-01, ADR-0026, ADR-0028, `safety.md`

## Context

ADR-0028 flies INAV on the BLITZ ATF435 and needs an RC link with a physical kill switch before any flight. The team can't afford an RC transmitter. Without a control link the drone doesn't fly, and RSK-01 (no flying drone) becomes real.

A low, tethered hover still gives the payload real vibration, motor noise and rotor-wash data. INAV reads any receiver that speaks CRSF on a serial port.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Real RC link (ELRS transmitter + receiver) | Proper physical kill switch; range; the standard way | Not affordable |
| B. DIY ELRS transmitter from an ESP32 + radio module | Real RC protocol | Too slow to build and test this week |
| C. Laptop gamepad → Wi-Fi → ESP32 that speaks CRSF to INAV, **tethered** | Parts in hand; INAV treats it as a receiver, so its RX-loss failsafe works unchanged; the tether caps the height whatever the software does | Wi-Fi is not an RC link: higher latency, the laptop's OS in the loop, no physical kill switch on the controller |
| D. Option C with no tether | Free flight | Rejected: a software-only kill path is not enough for free flight |

## Decision

Option C, for **tethered, low indoor hover only**:

- **Bridge:** a classic ESP32 runs its own 2.4 GHz WPA2 access point, sits on a spare UART of the ATF435 and emulates an RC receiver over CRSF (`serialrx_provider = CRSF`). Firmware: `firmware/esp32-rc-bridge/`.
- **Controller:** the laptop reads a USB gamepad and sends stick, arm, kill and mode values over UDP (`pnt rc`, `src/pnt/flight/rc_link.py`).
- **Authentication:** every packet carries a truncated HMAC-SHA256 tag under a pre-shared key, a strictly increasing sequence number, and a nonce the bridge picks at each boot. Anything that fails is dropped and counted. The key and the AP password live in a git-ignored file that people create; they are never committed (ADR-0026).
- **Silence means failsafe.** If no valid packet arrives for the heartbeat timeout (`TBC`, 200 ms; `kHbTimeoutMs` in `main.cpp`), the bridge stops sending CRSF frames entirely. INAV then sees RX loss and runs its own failsafe. The bridge never sends substitute "failsafe" channel values and never re-sends stale ones.
- **INAV failsafe procedure: LAND** after a short delay (`failsafe_delay`, `TBC`, 0.5 s).
- **Kill = DISARM** through the arm switch: the motors stop at once. An emergency drop from the hover height is deliberate. KILL wins over every other input, on both the laptop and the bridge.
- **Boot is disarmed.** Arming needs a deliberate gamepad action (both shoulder buttons held, `TBC`, 1 s, with the throttle at the bottom) and goes out only while packets are fresh. The bridge also holds ARM low after its boot and after any link loss until it has seen a disarmed packet.
- **Hardware limits:**
  - The tether is anchored to the floor and about 0.5 m long, so it sets the ceiling. Hover at 0.3–0.5 m.
  - Prop guards and padding under the drone.
  - An XT60 loop plug in the battery lead is the physical kill on the ground.
  - Check the LiPo after any hard landing.
- **Bands:** the payload streams on 5 GHz and the control AP is on 2.4 GHz, so they don't compete.
- **Radio:** the ESP32's 2.4 GHz Wi-Fi is a licence-exempt control link, like the RC link `safety.md` already lists. It is not a payload transmit path; REQ-07 covers the payload, which stays receive-only.

**Free flight is unchanged:** it still needs a real RC link with a physical kill switch, and ADR-0028 stays in force for it.

## Consequences

- `safety.md` lists this link and its limits. The bench test (props off) and the pre-flight checklist are in `firmware/esp32-rc-bridge/README.md`; both are done before every tethered session.
- The INAV settings (UART, CRSF, failsafe procedure, delays, switch mapping, position hold on the MTF-01) are `TBC` against the installed INAV version.
- The laptop needs a Wi-Fi interface on the bridge's AP. If its only adapter is also on the payload's 5 GHz network, a second adapter is needed (`TBC`).
- CI does not build `firmware/esp32-rc-bridge/` yet: that needs a `.github/` change with owner sign-off. Its protocol logic is tested on the host with g++ (`tests/test_rc_bridge_cpp.py`).
- **Limits:** the latency of the Wi-Fi path is `TBD` (measure on the bench). A laptop or OS stall shows up as silence, which INAV handles as RX loss. The kill button is software on the laptop; the loop plug is the hardware kill.
- **Reopen if:** an RC transmitter becomes available (then use it, and this link is retired), the tether can't be used, or the bench test fails.
