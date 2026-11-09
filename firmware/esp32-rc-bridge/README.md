# ESP32 RC bridge (tethered hover only)

> **[ADR-0029](../../systems/adr/0029-tethered-hover-wifi-control.md): tethered, low, indoor hover only.** Free flight needs a real RC link with a physical kill switch ([`safety.md`](../../systems/safety.md), ADR-0028).

```
gamepad ─USB─ laptop (`pnt rc`) ─UDP over the ESP32's own 2.4 GHz WPA2 AP─ ESP32 ─CRSF on UART2─ ATF435 (INAV)
```

- **The laptop** reads the gamepad and sends a control packet 50 times a second (`TBC`). Each packet carries a truncated HMAC-SHA256 tag, a strictly increasing sequence number and the bridge's boot nonce.
- **The bridge** drops anything that fails those checks and counts it. Valid packets become CRSF `RC_CHANNELS_PACKED` frames at 50 Hz (`TBC`), 420000 baud (`TBC`).
- **Silence means failsafe.** With no valid packet for 200 ms (`kHbTimeoutMs`, `TBC`), the bridge sends nothing. INAV sees RX loss and runs its failsafe (LAND). The bridge never sends substitute values.
- **KILL** forces the arm channel and the throttle low, so INAV disarms and the motors stop at once.
- **Boot is disarmed.** After the bridge boots, and after any link loss, it holds ARM low until it has seen a disarmed packet.

| Path | What |
| --- | --- |
| `lib/rc_bridge/rc_bridge.h` | All protocol logic, with no Arduino calls: packet check, CRSF packing, CRC8, HMAC-SHA256, watchdog. The wire format is documented at the top |
| `src/main.cpp` | Wi-Fi AP, UDP, UART2 and timing. Constants marked `TBC` are at the top |
| `include/secrets.h.example` | Template for the git-ignored `include/secrets.h` |
| `host_test/` | C++ tests and a driver, built with g++ by `tests/test_rc_bridge_cpp.py` |
| `src/pnt/flight/rc_link.py` | The laptop side (`pnt rc`) |

## Build and flash

1. Make the secrets file. It holds the AP password and the pre-shared key; it is git-ignored and **never committed**.

   ```bash
   cp firmware/esp32-rc-bridge/include/secrets.h.example firmware/esp32-rc-bridge/include/secrets.h
   python -c "import secrets; print(secrets.token_hex(32))"      # -> RCB_PSK_HEX
   python -c "import secrets; print(secrets.token_urlsafe(18))"  # -> RCB_AP_PASSWORD
   ```

   The laptop reads `RCB_PSK_HEX` from the same file (`pnt rc --key-file`, which defaults to it). If the laptop is a different machine from the one that builds, copy the file over a trusted channel.

2. Build and flash with [PlatformIO](https://platformio.org) (`espressif32 @ 8.0.0`, Arduino core 3.3.12):

   ```bash
   pio run -d firmware/esp32-rc-bridge              # build
   pio run -d firmware/esp32-rc-bridge -t upload    # flash over USB
   pio device monitor -b 115200                     # console: link state and counters, once a second
   ```

CI doesn't build this folder yet (it needs a `.github/` change with owner sign-off). The protocol logic is tested on the host: `pytest tests/test_rc_bridge_cpp.py tests/test_rc_link.py`.

## Wiring (ESP32 devkit ↔ ATF435)

| ESP32 | ATF435 | Note |
| --- | --- | --- |
| GPIO17 (UART2 TX) | RX pad of a free UART (`UARTn`, `TBC`) | CRSF frames to INAV |
| GPIO16 (UART2 RX) | TX pad of the same UART | INAV's CRSF telemetry; read and discarded. Optional |
| GND | GND | Common ground is required |
| 5V / VIN | 5V pad (BEC 5 V 2.5 A) | Don't feed USB and the 5V pad at the same time unless the devkit has a diode on VIN (`TBC` for our board) |

- Both sides use 3.3 V logic, so no level shifter is needed.
- Which UART is free is `TBC`: the MTF-01 and the payload's MAVLink telemetry also need UARTs (the ATF435 has 6).
- Keep the ESP32's antenna away from the payload's SDR antennas and the GPS antenna.

## INAV setup (`TBC` against the installed INAV version)

Check each setting name with `get <name>` in the INAV CLI before relying on it, and record the INAV version here once it is known (`TBC`). UART numbers in the CLI start at 0, so `UARTn` is `serial n-1`.

```text
# Receiver: CRSF on UARTn (function mask 64 = RX_SERIAL)
serial <n-1> 64 115200 115200 0 115200
set receiver_type = SERIAL
set serialrx_provider = CRSF            # CRSF runs at 420000 baud; INAV sets that itself
set serialrx_inverted = OFF
set serialrx_halfduplex = OFF           # TBC: some versions use AUTO
map AETR                                # channel order the bridge sends

# Failsafe: RX loss -> LAND after a short delay (ADR-0029)
set failsafe_procedure = LAND
set failsafe_delay = 5                  # TBC: tenths of a second, so 0.5 s
set failsafe_throttle = TBC             # throttle for a landing without altitude hold; from the hover test
set failsafe_off_delay = TBC            # how long the landing may take before INAV disarms
set failsafe_throttle_low_delay = TBC
save
```

**Check `rxfail` too:** it decides what INAV sends while it waits out `failsafe_delay`. Throttle must not drop to idle in that window. `TBC` for the installed version.

**Modes:** set these in INAV Configurator's *Modes* tab, then check them with `aux` in the CLI.

| Mode | Channel | Range (µs) | Gamepad |
| --- | --- | --- | --- |
| ARM | AUX1 (ch 5) | 1700–2100 | LB + RB held 1 s (`TBC`), throttle at the bottom |
| ANGLE | AUX2 (ch 6) | 900–2100 (always on, never acro) | — |
| NAV ALTHOLD | AUX2 | 1300–1700 | A |
| NAV POSHOLD | AUX2 | 1700–2100 | Y |
| (ANGLE only) | AUX2 | 900–1300 | X |

- **KILL is the B button.** It drops AUX1, so INAV disarms. Confirm on the bench that INAV disarms at any throttle (step 6 below).
- Arm in ANGLE (X): INAV may refuse to arm while a navigation mode is selected.
- **Position hold indoors uses the MTF-01** (optical flow and rangefinder) on its own UART: MSP function on that UART, `opflow_hardware = MSP`, `rangefinder_hardware = MSP`, and the MTF-01 set to MSP output. All of these are `TBC`, and so is whether this INAV version holds position on optical flow alone. Until a tethered hover shows it working, fly ANGLE or ALTHOLD only.
- With a self-centring gamepad stick, releasing the throttle gives mid-stick (1500 µs). In ALTHOLD/POSHOLD that means "hold height"; in ANGLE it can mean "climb", up to the tether.

**Gamepad mapping** (`PadMap` in `rc_link.py`, Linux xpad layout, `TBC` on the team's gamepad):

| Input | Default |
| --- | --- |
| Throttle / yaw | left stick Y / X (axes 1 / 0) |
| Pitch / roll | right stick Y / X (axes 4 / 3) |
| Arm / kill | buttons 4 + 5 (LB + RB) / button 1 (B) |
| Mode | button 2 (X) ANGLE, 0 (A) ALTHOLD, 3 (Y) POSHOLD |

## Bench test (props OFF, every session before the tethered hover)

**Props off for the whole test.** Loop plug in, battery on, ESP32 wired to the ATF435. Open INAV Configurator over USB to watch the *Receiver* tab and the arming state.

1. **Bridge up.** In the ESP32 console you see `rc-bridge: AP pnt-rc ...`, then `link none gate closed` once a second. INAV shows RX loss: the bridge sends nothing yet.
2. **Laptop joins the AP** (SSID and password from `secrets.h`). Check that it shows as WPA2: `nmcli -f SSID,SECURITY dev wifi list`.
3. **Mapping:** `pnt rc --dry-run` prints one line per packet. Move each stick and press each button, and check the printed values against the table above.
4. **Link:** `pnt rc`. The laptop shows `LINK LIVE gate open`, the console shows `link LIVE`, and INAV's *Receiver* tab follows the sticks: right stick right means roll high, stick up means pitch and throttle high. AUX2 changes with X, A and Y.
5. **Arm:** throttle at the bottom, X (ANGLE), hold LB + RB for 1 s. INAV arms and the motors idle.
6. **Kill:** raise the throttle a little, press B. The motors stop at once and INAV shows disarmed. Keep LB + RB held and release B: it must **not** re-arm.
7. **Link loss → failsafe:** re-arm and raise the throttle a little. Turn off the laptop's Wi-Fi (`nmcli radio wifi off`).
   - Within 200 ms the console shows `link LOST`.
   - INAV shows RX loss, then FAILSAFE (LAND) after `failsafe_delay`.
   - Time it from Wi-Fi off to failsafe and write it here (`TBD`).
   - Turn Wi-Fi back on. INAV must not re-arm by itself: the laptop drops to disarmed ("bridge lost the link") and arming needs a fresh LB + RB hold.
8. **Program stops → failsafe:** repeat step 7, but stop `pnt rc` with Ctrl-C, then repeat it by unplugging the gamepad. Both times the laptop stops sending and INAV fails safe.
9. **Replay, forgery and old-boot packets are rejected:** with `pnt rc` stopped, run `pnt rc --link-test`. It sends one replayed packet, one with a changed byte and one signed for another boot of the bridge, and prints `PASS` if the bridge's counters show each one rejected (`replay`, `bad_tag`, `bad_nonce`). Every test packet is disarmed with the throttle low.
10. **Reboot:** arm, then power-cycle the ESP32 while `pnt rc` runs. The laptop must drop to disarmed ("bridge rebooted"), and arming must need a fresh LB + RB hold.

If any step fails, don't fly. Record the result, the INAV version and the commit in the session notes.

## Pre-flight checklist (tethered hover)

- [ ] Bench test above passed today, props off
- [ ] Tether anchored to the floor, about 0.5 m long, attached to the frame (not the payload); hover at 0.3–0.5 m
- [ ] Prop guards fitted; padding under the drone
- [ ] XT60 loop plug in the battery lead, someone standing by to pull it
- [ ] Everyone clear of the tether radius; netted area
- [ ] Laptop Wi-Fi on the bridge's AP (2.4 GHz); payload stream on 5 GHz
- [ ] `pnt rc` shows `LINK LIVE gate open`; INAV mode ANGLE before arming
- [ ] LiPo checked (no puffing or damage); LiPo bag ready; after any hard landing, check the pack again before reuse
