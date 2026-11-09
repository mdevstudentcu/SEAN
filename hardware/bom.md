# Bill of materials

- **Status:** Draft, 2026-11-08; ground reference station adopted 2026-11-09 (ADR-0020)
- **Prices:** CAD before tax, as listed on Amazon.ca and PiShop.ca on the date in each section (2026-11-08 unless noted). Delivery dates are what Amazon showed then for Ottawa (K1V); recheck at checkout.
- Unknowns are `TBD` (no value yet) or `TBC` (proposed, not confirmed).

## Buying rules

Every item in this file meets these, and anything added later must too. An item that breaks one goes to *Not using* with the reason.

1. **In hand by Tue 2026-11-10 evening.** Real sessions are recorded Mon–Tue (ADR-0015) and the sim freezes Wednesday. An item arriving later is not worth buying unless an owner says otherwise.
2. **Price, source and delivery stated.**
   - Bought items give the price, the seller and listing ID (ASIN), and the delivery date with the date it was checked.
   - Owned or supplied items say who has them (Team, HON, Workshop).
   - "International shipping" is called out, because those dates slip.
3. **Cheapest option that does the job.** Where a cheaper or more robust option exists, the alternatives and their trade-off (price, delivery, effort such as soldering) are listed next to it.
4. **Receive-only.** Nothing on the payload or the ground station transmits on the bands we measure (ADR-0001, REQ-07). Licence-exempt control, telemetry and Wi-Fi links are the only exceptions.
5. **Traceable.** Each item says what it is for and the ADR, REQ or decision that needs it. An item no decision needs is not bought.
6. **No third-party software or data here.** Code and datasets follow the `AGENTS.md` rules, not this file.

**Source key:** **HON** = Honeywell lab supplies (`Hackathon Material Supplies From HONAero.pdf`, not committed) · **Team** = already owned · **Buy** = to order · **Workshop** = Carleton EDC mechatronics workshop consumables · **Build** = made by us

## Summary

| Tier | Items | Cost |
| --- | --- | --- |
| Must buy | SDR A, SDR B, SMA pigtails | **$133.09** |
| Buy only if day-1 tests need the hub (ADR-0018) | Pi Zero 2 W | $69.28 |
| Must buy: ground reference station (ADR-0020) | Reference SDR bundle + GPS with PPS | **$92.34** |

## 1. Payload: compute, timing and sensors

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| Raspberry Pi 4B (payload) | 1 | Records SDR IQ, GPS, sensors; streams to laptop | Team (owned) | — | ADR-0018. SDRs on the USB 2 ports (USB 3 noise, RSK-06); 5 V 3 A supply, heatsink or fan; USB current `TBC` |
| Raspberry Pi 3B+ | 1 | Not on the payload; runs the ground reference station (section 5) | Team (owned) | — | ADR-0018, ADR-0020 |
| microSD card, ≥ 64 GB, A2 (or a USB SSD) | 1 | OS + session logs. Raw IQ from one SDR at 2.4 MS/s is ~17 GB/h; both SDRs ~35 GB/h | Team `TBC` | — | Confirm size and speed |
| Raspberry Pi Zero 2 W | 0–1 | Fallback sensor hub if day-1 tests fail on the 4B: IMU, baro, PPS edge, Wi-Fi scans (ADR-0018) | Team `TBC`, else Buy: Amazon.ca | $69.28, overnight, **1 left** | PiShop.ca: out of stock (both variants). Plugs into a 4B USB 2 port (data port) |
| Adafruit Ultimate GPS HAT | 1 | GPS fix, PPS on GPIO4, truth outdoors | HON | — | ADR-0014 |
| GPS active antenna, 28 dB, 5 m, SMA | 1 | Puts the GPS antenna on a mast away from SDR/USB noise (RSK-06) | HON | — | |
| SMA to u.FL adapter cable | 1 | Antenna → HAT | HON | — | |
| CR1220 coin cell | 1 | Keeps the HAT's RTC alive (faster fix) | Buy: any pharmacy, same day | ~$5 `TBC` | Optional: only if cold starts are too slow on day 1 |
| MPU6050 IMU, BMP280 barometer, jumpers | 1 kit | IMU + baro on the Pi 4B's I2C (the Zero's, if the hub is used) | HON (Sensor Kit v4.0) | — | ADR-0014 |
| Pi camera | 1 | Optional video log | Team | — | |
| Heatsink + 5 V fan | 1 | Pi cooling under SDR load | HON | — | |

## 2. Payload: radios

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| AirNav Radar FlightStick | 1 | **SDR A:** ADS-B only (built-in 1090 MHz filter + amplifier) | Buy: Amazon.ca, ASIN B07K47P7XD | $45.15 | Tue Nov 10; ships internationally (import fees included) |
| NooElec NESDR SMArt v5 **Bundle** | 1 | **SDR B:** LTE + VOR. 0.5 ppm TCXO. Bundle adds a magnetic base with 2 m RG58 and 3 antennas | Buy: Amazon.ca, ASIN B01GDN1T4S | $77.95 | Tue Nov 10 |
| USB 2.0 extension, ~30 cm | 2 | Moves the SDRs off the Pi's ports (spacing, less RF noise) | Team / Workshop `TBC` | — | Use USB 2 ports (RSK-06) |
| Clip-on ferrites | 2–4 | On USB and power leads (RSK-06) | Workshop `TBC` | — | |

## 3. Antennas (Build)

Build steps, dimensions and tests: [`antennas.md`](antennas.md).

| Item | Qty | For | Source | Price | Notes |
| --- | --- | --- | --- | --- | --- |
| SMA male → SMA female bulkhead pigtail, RG316, 30 cm | 3 | Feed point for each DIY antenna | Workshop first; else Buy: Amazon.ca | $9.99 | Tue Nov 10. Check pack size; buy enough for 3 |
| Solid copper wire 14 AWG (or 1.5–2 mm brass rod), ~2.5 m | 1 | Radiators, radials, dipole arms | Workshop (or the bare ground wire from household NMD90 cable) | — | |
| Solid copper wire 20 AWG, a few cm | 1 | Pin stubs: 14 AWG doesn't fit the SMA centre socket | Workshop | — | |
| Single-sided copper-clad PCB, ~5 × 5 cm | 3 | Mounting/ground plate for each antenna (solderable, unlike aluminum) | Workshop | — | |
| PVC pipe or wood strip, ~1.4 m | 1 | VOR dipole boom (no metal) | Workshop | — | |
| Solder, heat-shrink, cable ties | — | | Workshop | — | |

| Antenna | Dimensions |
| --- | --- |
| ADS-B 1090 MHz ground plane | Radiator 65 mm; 4 radials × 69 mm at 45° down |
| LTE ground plane (build for the band the RF survey finds) | 850 MHz (default): radiator 81 mm, radials 85 mm · 700 MHz: 96 / 101 mm · 600 MHz: 112 / 118 mm |
| VOR 114.6 MHz horizontal dipole | 2 arms × 622 mm, ~1 cm centre gap; broadside to YOW VOR (arms 21°–201° true from Carleton) |

## 4. Power

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| USB power bank, 5 V ≥ 3 A | 1 | Handheld and vehicle sessions | Team `TBC` | — | Current draw `TBD`: measure with the DPS-150 |
| 5 V BEC ≥ 3 A | 1 | Payload power on the drone | `TBD` (drone build) | — | |
| FNIRSI DPS-150 bench supply | 1 | Bench power and current-draw measurement | HON | — | No adapter included: needs a USB-C PD charger (≤ 20 V) or DC input |

## 5. Ground

### Laptop and link

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| Laptop | 1 | Front-ends, estimator, dashboard | Team | — | |
| Wi-Fi link (phone hotspot or router) | 1 | Live stream (ADR-0009) | Team | — | Replay is the fallback (RSK-04) |

### Ground reference station (prices and delivery checked 2026-11-09)

**Adopted (ADR-0020).** A static receiver at a surveyed point that hears the same towers as the payload. It estimates their clocks for differential LTE (base/rover), and the sim gets the same second receiver.

It needs **no IMU, barometer or camera**, since it doesn't move. It does need a **GPS with PPS**: base and payload must share a time frame to well under 1 µs (1 µs ≈ 300 m), and NTP from the laptop only gives milliseconds.

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| NooElec NESDR SMArt v5 **Bundle** | 1 | Reference LTE receiver: same radio as the payload's SDR B, so the receiver biases match | Buy: Amazon.ca, ASIN B01GDN1T4S | $77.95 | **Today (Nov 9), 2–6 pm.** The bundle's magnetic base, 2 m cable and telescopic antennas (set to ~10.7 cm for 700 MHz) replace building a second LTE antenna |
| GY-NEO6MV2 NEO-6M GPS, with patch antenna | 1 | PPS timebase and surveyed position (average the fix over ≥ 1 h) | Buy: Amazon.ca, ASIN B0CTG63TYF | $14.39 | **Today (Nov 9), 2–6 pm** on orders over $25. **No PPS pin:** solder one wire from the PPS LED's pad to Pi GPIO4 (`TBC`: check the board photos) |
| Raspberry Pi 3B+ | 1 | Runs the reference SDR; PPS-disciplined timestamps (chrony + `pps-gpio`) | Team (owned, ADR-0018) | — | Or the HON lab Pi |
| microSD, 16–32 GB | 1 | Reference Pi OS. Data streams to the laptop, so nothing large is stored | Team `TBC`, else Buy | ~$12 `TBC` | The payload keeps the team's 32 GB card |
| 5 V 2.5 A micro-USB supply | 1 | Reference Pi power (wall) | Team `TBC` | — | |
| Ethernet cable | 1 | Reference → laptop, live | Team `TBC` | — | No SD storage limit, no Wi-Fi contention |
| Female–female jumper wires | 4 | GPS UART + PPS to the Pi header | HON (sensor kit) | — | |

**Total to buy: $92.34** (≈ $104 with 13% HST), arriving today.

**Before use, run a zero-baseline test:**
- Run the reference and the payload side by side for 5–10 min.
- Any difference between their measurements is receiver bias. Measure it once and subtract it.

**Alternatives:**

| Option | Price | Arrives | Trade-off |
| --- | --- | --- | --- |
| ATGM336H GPS (ASIN B0GSZY9ZYB) instead of the NEO-6M | $20.20 | Wed Nov 11, ships internationally | Real PPS pin, no soldering; arrives the day before judging, so backup only |
| NESDR SMArt v5 dongle only (Amazon.ca, seller NooElec; ASIN `TBC`) instead of the bundle | $63.95 | Tue Nov 10 | Saves $14 but needs a second hand-built LTE antenna (section 3) |
| GT-U7 GPS (has a PPS pin) | $19.99 | Nov 13–24 | Breaks rule 1: too late |

## 6. Drone

From `hardware/README.md` and `flight/`. Status and source of each are `TBD`; RSK-01 covers late parts. Without RC, the drone does not fly (ADR-0012).

| Item | Qty | Source | Status |
| --- | --- | --- | --- |
| Frame: ModuFrame-5 base (CC BY-SA), 3D printed | 1 | Build (EDC additive manufacturing lab) | `TBD` |
| Readytosky 2205 2700KV motors | 4 | `TBD` | `TBD` |
| 45 A BLHeli_S ESCs | 4 | `TBD` | `TBD` |
| ArduPilot flight controller | 1 | `TBD` | `TBD` |
| MTF-01 optical flow + rangefinder | 1 | `TBD` | `TBD` |
| RC transmitter + receiver with kill switch | 1 | `TBD` | `TBD` |
| LiPo packs, charger, LiPo bag | `TBD` | `TBD` | `TBD` |
| Props and prop guards | `TBD` | `TBD` | `TBD` |

## Not using

| Item | Why |
| --- | --- |
| ESP32-S3 | None available; sensors go on the Pi 4B, Pi Zero 2 W hub as fallback (ADR-0018). Wi-Fi FTM and FTM responders are dropped |
| Raspberry Pi Pico 2W (HON) | Considered as the hub; the Pi 4B (or the Zero fallback) runs the same Python and generated MAVLink as the recorder (ADR-0018) |
| RTL-SDR Blog V3/V4, dipole kit, FM filter | Amazon.ca delivery Dec 21–25 (rule 1) |
| GT-U7 GPS module | Amazon.ca delivery Nov 13–24 (rule 1); the ground station uses a NEO-6M instead |
| Airspy Mini | Budget |
| Flamingo FM band-stop filter ($46) | Skipped; VOR is 16.8 km away. Revisit only if the RF survey shows FM overload |
| LoRa HAT 915 MHz (HON) | A 22 dBm transmitter ~20 MHz above the 850 MHz LTE downlink would desensitize the unfiltered SDRs; Canadian certification unconfirmed |
| VL53L1X ToF (HON) | Optional indoor height truth only; drone already has the MTF-01 rangefinder |
| L-band patch antenna (Iridium) | LEO layer is simulated (ADR-0013, mentor Q5) |

## Open decisions

- Ground reference station (ADR-0020): **order today** for same-day delivery. The NEO-6M PPS solder joint needs someone with a soldering iron. If the parts miss Tue Nov 10, it stays in sim (ADR-0020, reopen).
- Base/payload receiver ID in the measurement or session ICD: a separate `icd` PR (ADR-0020).

- Hub needed at all: day-1 test of IMU jitter, CPU load, dropped samples and PPS offset on the 4B (ADR-0018, `TBD`). If yes, its USB link is serial or network gadget (`TBC`).
- USB current: two SDRs (plus the Zero, if used) against the 4B's USB budget; measure with the DPS-150 (ADR-0018, `TBC`).
- Where Wi-Fi scans run in flight without disturbing the ZeroMQ link (ADR-0018, `TBC`).
