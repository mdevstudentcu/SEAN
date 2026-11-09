# Bill of materials

- **Status:** Draft, 2026-11-08
- **Prices:** CAD before tax, as listed on Amazon.ca and PiShop.ca on 2026-11-08. Delivery dates are what Amazon showed then for Ottawa (K1V); recheck at checkout.
- **Delivery rule:** real sessions are recorded Mon–Tue (ADR-0015) and the sim freezes Wednesday, so anything not in hand by **Tue 2026-11-10 evening** is not worth buying.
- Unknowns are `TBD` (no value yet) or `TBC` (proposed, not confirmed).

**Source key:** **HON** = Honeywell lab supplies (`Hackathon Material Supplies From HONAero.pdf`, not committed) · **Team** = already owned · **Buy** = to order · **Workshop** = Carleton EDC mechatronics workshop consumables · **Build** = made by us

## Summary

| Tier | Items | Cost |
| --- | --- | --- |
| Must buy | SDR A, SDR B, SMA pigtails | **$133.09** |
| Buy only if not owned | Pi Zero 2 W (or use the lab Pico 2W instead: $0) | $69.28 |
| Optional | Ground-reference SDR | $63.95 |

## 1. Payload: compute, timing and sensors

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| Raspberry Pi (payload) | 1 | Records SDR IQ, GPS, sensors; streams to laptop | Team | — | Model choice is open (sim plan D6) |
| microSD card, ≥ 64 GB, A2 | 1 | OS + session logs. Raw IQ from one SDR at 2.4 MS/s is ~17 GB/h | Team `TBC` | — | Confirm size and speed |
| Raspberry Pi Zero 2 W | 1 | Sensor hub (replaces the ESP32-S3) | Team `TBC`, else Buy: Amazon.ca | $69.28, overnight, **1 left** | PiShop.ca: out of stock (both variants). **Needs an ADR** (supersedes ADR-0005's ESP32 hub). Alternative: the lab Pico 2W below |
| Raspberry Pi Pico 2W | 1 | Alternative hub: I2C sensors, PIO timestamps PPS edges in hardware, Wi-Fi RSSI scans. No FTM | HON | — | Closer to ADR-0005's microcontroller hub than the Zero |
| Adafruit Ultimate GPS HAT | 1 | GPS fix, PPS on GPIO4, truth outdoors | HON | — | ADR-0014 |
| GPS active antenna, 28 dB, 5 m, SMA | 1 | Puts the GPS antenna on a mast away from SDR/USB noise (RSK-06) | HON | — | |
| SMA to u.FL adapter cable | 1 | Antenna → HAT | HON | — | |
| CR1220 coin cell | 1 | Keeps the HAT's RTC alive (faster fix) | Buy (any pharmacy) | `TBD` | Optional |
| MPU6050 IMU, BMP280 barometer, jumpers | 1 kit | IMU + baro on the hub's I2C | HON (Sensor Kit v4.0) | — | ADR-0014 |
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

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| Laptop | 1 | Front-ends, estimator, dashboard | Team | — | |
| Wi-Fi link (phone hotspot or router) | 1 | Live stream (ADR-0009) | Team | — | Replay is the fallback (RSK-04) |
| Raspberry Pi (lab) | 1 | Ground reference station | HON | — | Only useful with the SDR below |
| NooElec NESDR SMArt v5 (dongle only) | 1 | *Optional:* ground reference for differential LTE | Buy: Amazon.ca | $63.95 | Tue Nov 10 |
| GPS for the reference station (e.g. NEO-6M) | 1 | *Optional:* timebase at the reference | `TBD` | `TBD` | ADR-0014 suggests it; only with the reference SDR |

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
| ESP32-S3 | None available; hub moves to Pi Zero 2 W or Pico 2W. Wi-Fi FTM and FTM responders are dropped |
| RTL-SDR Blog V3/V4, dipole kit, FM filter | Amazon.ca delivery Dec 21–25 |
| Airspy Mini | Budget |
| Flamingo FM band-stop filter ($46) | Skipped; VOR is 16.8 km away. Revisit only if the RF survey shows FM overload |
| LoRa HAT 915 MHz (HON) | A 22 dBm transmitter ~20 MHz above the 850 MHz LTE downlink would desensitize the unfiltered SDRs; Canadian certification unconfirmed |
| VL53L1X ToF (HON) | Optional indoor height truth only; drone already has the MTF-01 rangefinder |
| L-band patch antenna (Iridium) | LEO layer is simulated (ADR-0013, mentor Q5) |

## Open decisions

- Hub: Pi Zero 2 W vs the lab Pico 2W → ADR superseding ADR-0005 (and `firmware/esp32-hub/`).
- `systems/icd/session.md`'s example `hardware:` list still names `esp32-s3` and `nesdr-smart-v5 x2`; update it in an `icd` PR once the hub is decided.
