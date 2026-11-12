# Flight

The real drone flies Betaflight 4.5.5 on the iFlight BLITZ ATF435, pilot-flown with a FlySky FS-i6 and its kill switch (ADR-0028, *Amendment 2026-11-11 (owners)*). The ArduPilot files below are for SITL only: they make trajectories for the sim and try "our nav in the loop" with no crash risk.

| Folder | |
| --- | --- |
| `params/` | Versioned ArduPilot parameter files: `base.param` (frame, motors, failsafes, geofence), `indoor-flow.param` (MTF-01 optical flow + rangefinder, no GPS), `sitl.param`. Export from Mission Planner/QGC after each tuning session and commit |
| `missions/fly.py` | Scripted patterns over MAVLink. The pilot arms, takes off and selects GUIDED; the script stops the moment the mode changes. Only `--sitl` arms by itself |
| `sitl/` | ArduPilot software-in-the-loop: test scripts, generate realistic trajectories, and try "our nav in the loop" (level 2) with no crash risk |

## The real drone: Betaflight and the FS-i6

Set up on 2026-11-11 (ADR-0028, *Amendment 2026-11-11 (owners)*):

| What | Setting |
| --- | --- |
| Firmware | Betaflight 4.5.5, cloud build for `IFLIGHT_BLITZ_F435` with `USE_SERIALRX_IBUS` and `USE_TELEMETRY_MAVLINK`, flashed with `dfu-util` over USB DFU (AT32 bootloader `2e3c:df11`). The factory 4.5.2 build reads CRSF only |
| Receiver | FS-iA6B, iBUS on flight-controller UART4 (R4 pad), 115200 baud. Channel order AETR |
| ARM | AUX1 (channel 5) = **SwB**, armed at 1700–2100. **SwB is the kill switch** |
| ANGLE | AUX2 (channel 6) = **SwA**, ANGLE at 900–1300 (SwA's resting position); the other position is acro |
| Failsafe | In the transmitter: CH3 on at −119 % (throttle low), CH5 on at −100 % (disarmed). Betaflight `failsafe_procedure` `DROP`. On RC loss the drone disarms and falls; there is no controlled landing |
| MAVLink to the Pi | UART1, MAVLink telemetry, 115200 baud. Wire flight-controller TX1 → Pi GPIO13 (`uart5` RX) and GND only; the Pi's TX stays unconnected (`deploy/pi/RUNBOOK.md`) |

The same in the Betaflight CLI (`diff all`, 2026-11-11). UART numbers in the CLI start at 0:

```
serial 0 512 115200 57600 115200 115200   # UART1: MAVLink telemetry
serial 3 64 115200 57600 0 115200         # UART4: serial receiver (iBUS)
aux 0 0 0 1700 2100 0 0                   # ARM on AUX1
aux 1 1 1 900 1300 0 0                    # ANGLE on AUX2
```

**Done 2026-11-11:** accelerometer level calibration (roll 0.4° / pitch 2.6° → 0.0° / 0.0°); motor order and direction, props off. Order is Betaflight's Quad X default, props in: M1 rear-right CW, M2 front-right CCW, M3 rear-left CCW, M4 front-left CW. M3 and M4 were reversed and fixed in the ESC (`dshotprog 2 21 12`, `dshotprog 3 21 12`), then re-tested; all four directions confirmed at slow speed.

**Open before the first flight:** bidirectional DShot (whether the ESC supports it is `TBC`); `failsafe_throttle`, only if AUTO-LAND is ever used instead of `DROP`.

### Pre-flight (indoor)

Netted area · prop guards · speed limit · props matched to motor direction (CCW/"R" props on M2 and M3) · payload secured · the receiver failsafe tested (below) · SwB disarms at any throttle · MAVLink telemetry reaching the recorder (`/mavlink/fc`). No position hold or geofence on this setup.

### Before every arming

1. Receiver LED solid.
2. SwB disarmed.
3. Throttle down.
4. SwA at rest (ANGLE).
5. Props each matched to its motor's direction (CCW/"R" on M2 and M3).
6. SwB is the kill: flip it to stop the motors.

### FS-i6 menu reference

- **Hold OK** opens the menu. **UP/DOWN** move, **OK** selects, **CANCEL** goes back.
- **Hold CANCEL until it beeps** to save.

| Path | What |
| --- | --- |
| *Functions setup → Aux. channels* | CH5 = SwB, CH6 = SwA |
| *System setup → RX setup → Failsafe* | Per channel: set the stick or switch to its safe position first, then **On**, then save (hold CANCEL). Keep the receiver powered and connected for a few seconds so it takes the values. Then test: SwB armed → transmitter off → arm must drop (channel 5 to 1000 in Betaflight's *Receiver* tab) |
| *Functions setup → Reverse* | Channel direction |
| *Functions setup → End points* | Channel travel |

The receiver's default on signal loss is to **hold the last values**, which keeps the drone armed. Re-test the failsafe after any rebind or receiver change.
