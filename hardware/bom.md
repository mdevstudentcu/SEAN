# Bill of materials

- **Status:** Draft, 2026-11-08; ground reference station adopted 2026-11-09 (ADR-0020), then kept in sim only 2026-11-10 (ADR-0020, *Amendment 2026-11-10*); first parts received 2026-11-09 evening ([In hand](#in-hand))
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
| Must buy: payload radios | SDR A (FlightStick), SDR B (NESDR bundle) | **$123.10** |
| Must buy: antennas | LTE 2-pack (payload + spare), ADS-B | **$46.44** |
| Pi Zero 2 W hub (ADR-0018) | In hand: nothing to buy | — |
| Ground reference station (ADR-0020) | Not bought: it stays in sim (ADR-0020, *Amendment 2026-11-10*) | — |

## Size, weight and power

Not measured yet. Whoever has the assembled payload fills in both rows: the number, the date and the session name. Do not estimate.

| Quantity | Value | Measured on | How |
| --- | --- | --- | --- |
| Weight, payload as flown (Pi 4B, GPS HAT, both SDRs, the USB drive the IQ goes to (ADR-0042), sensors, heatsink and fan, USB extensions and ferrites, antennas and cables) | `TBD` g | `TBD` | Weigh the assembled payload with its antennas and cables on a kitchen scale that reads to 1 g. Write the reading here |
| Current draw at 5 V, average and peak | `TBD` A avg, `TBD` A peak | `TBD` | Put a USB power meter (or the DPS-150, section 4) in line with the Pi's supply and run a 10-minute `pnt record` of both SDRs with the session on the USB drive, as flown (ADR-0042; mount point `TBC`). `bash deploy/pi/day1.sh 10` records the same but writes under `data/sessions/` on the SD card, so it misses the drive's write load: change its `--out` to the drive first. Read average and peak current; write them here with the session name |

Size: `TBD`. These numbers feed H3 in [`safety.md`](../systems/safety.md#hazard-analysis) and the USB-current question under *Open decisions*.

## In hand

Checked 2026-11-09 evening, updated 2026-11-10. Everything else in this file is still on order or `TBD`.

| Item | Source | How it was identified | Notes |
| --- | --- | --- | --- |
| Raspberry Pi 4 Model B Rev 1.5, **4 GB** | `TBC` | `/proc/cpuinfo` and `free -m` on the Pi | **Payload recorder** from 2026-11-10 (ADR-0018 *RAM*). Raspberry Pi OS Trixie on a 32 GB SD card; it would not boot from a USB drive |
| Raspberry Pi 4B, **1 GB** | HON (kit with case, power supply and SD card; the kit contents are `TBC`) | Team read the board | **Spare** from 2026-11-10. 1 GB, not the 2 GB on Honeywell's list: see ADR-0018 *RAM* |
| NooElec NESDR SMArt v5, one | Buy (section 2) | USB descriptors on the laptop: `0bda:2838`, "Nooelec", "NESDR SMArt v5", serial `52453800` | **Payload SDR B** (LTE). Bundle or dongle-only is `TBC`: the bundle comes with three antennas and a magnetic base. No second NESDR is bought (ADR-0020, *Amendment 2026-11-10*) |
| AirNav Radar FlightStick | Buy (section 2) | Team, 2026-11-10 | **Payload SDR A** (ADS-B). Built-in 1090 MHz filter, so it cannot hear LTE |
| Bingfu 4G LTE antenna, **2-pack** | Buy (section 3) | Team, 2026-11-10 | One for the payload's SDR B; the second is a spare |
| NooElec antennas, including a 1090 MHz ADS-B antenna | Buy (section 3) | Team, 2026-11-10 | The 1090 MHz one is for the FlightStick. Which other NooElec antennas came is `TBC` |
| LoRa HAT, 915 MHz | HON | Team, 2026-11-10 | **In hand, not using** (*Not using*) |
| Adafruit Ultimate GPS HAT | HON | Team | ADR-0014 |
| GPS active antenna, Adafruit product 960 | HON | Team | The 28 dB, 5 m SMA antenna in section 1 |
| MPU6050 IMU | HON (sensor kit) | Team; on the payload Pi at `0x68` (`i2cdetect`, 2026-11-10) | ADR-0014. Records at 100 Hz: session `20261110-0301-static-bench`, at the change that is `7763667` on `main` |
| **BMP180** barometer | HON (sensor kit) | Team | **Not a BMP280**: see ADR-0014. `pnt.payload.i2c` finds either part and names it in `meta.yaml`. Check on the Pi: `i2cdetect -y 1` shows `77`, and register `0xD0` reads `0x55` |
| Raspberry Pi Zero 2 W | `TBC` (team) | Team | The ADR-0018 hub fallback; nothing to buy |
| VL53L1X ToF breakout | HON | Team | Still not used (*Not using*) |

**Not in hand yet:** the drone parts. **Not bought:** the second NESDR and the NEO-6M, since the reference station stays in sim (ADR-0020, *Amendment 2026-11-10*).

## 1. Payload: compute, timing and sensors

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| Raspberry Pi 4B, 4 GB (payload) | 1 | Records SDR IQ, GPS, sensors; streams to laptop | `TBC`, **in hand** (Honeywell's 1 GB is the spare) | — | ADR-0018. SDRs on the USB 2 ports (USB 3 noise, RSK-06); 5 V 3 A supply, heatsink or fan; USB current `TBC` |
| Raspberry Pi 3B+ | 1 | Not on the payload. It was to run the ground reference station, which stays in sim (section 5) | Team (owned) | — | ADR-0018, ADR-0020 |
| microSD card, ≥ 64 GB, A2 (or a USB SSD) | 1 | OS + session logs. Raw IQ from one SDR at 2.4 MS/s is ~17 GB/h; both SDRs ~35 GB/h | Team `TBC` | — | Confirm size and speed. The payload Pi boots from a 32 GB card today, 23 GB free (2026-11-10): about 40 min of both SDRs at 35 GB/h |
| Raspberry Pi Zero 2 W | 0–1 | Fallback sensor hub if day-1 tests fail on the 4B: IMU, baro, PPS edge, Wi-Fi scans (ADR-0018) | **In hand** (2026-11-09) | — | Plugs into a 4B USB 2 port (data port) |
| Adafruit Ultimate GPS HAT | 1 | GPS fix, PPS on GPIO4, truth outdoors | HON, **in hand** | — | ADR-0014 |
| GPS active antenna, 28 dB, 5 m, SMA | 1 | Puts the GPS antenna on a mast away from SDR/USB noise (RSK-06) | HON, **in hand** | — | Adafruit product 960 |
| SMA to u.FL adapter cable | 1 | Antenna → HAT | HON | — | |
| CR1220 coin cell | 1 | Keeps the HAT's RTC alive (faster fix) | Buy: any pharmacy, same day | ~$5 `TBC` | Optional: only if cold starts are too slow on day 1 |
| MPU6050 IMU, **BMP180** barometer, jumpers | 1 kit | IMU + baro on the Pi 4B's I2C (the Zero's, if the hub is used) | HON (Sensor Kit v4.0), **in hand** | — | ADR-0014. The kit's barometer is a BMP180, not a BMP280 |
| Pi camera | 1 | Optional video log | Team | — | |
| Heatsink + 5 V fan | 1 | Pi cooling under SDR load | HON | — | |

## 2. Payload: radios

| Item | Qty | Role | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| AirNav Radar FlightStick | 1 | **SDR A:** ADS-B only (built-in 1090 MHz filter + amplifier). No antenna included (section 3) | Buy: Amazon.ca, ASIN B07K47P7XD | $45.15 | **In hand** (2026-11-10) |
| NooElec NESDR SMArt v5 **Bundle** | 1 | **SDR B:** LTE + VOR. 0.5 ppm TCXO. Bundle adds a magnetic base with 2 m RG58 and 3 antennas; its telescopic one serves VOR, and LTE uses a Bingfu (section 3) | Buy: Amazon.ca, ASIN B01GDN1T4S | $77.95 | **In hand** (*In hand*; bundle or dongle-only `TBC`) |
| USB 2.0 extension, ~30 cm | 2 | Moves the SDRs off the Pi's ports (spacing, less RF noise) | Team / Workshop `TBC` | — | Use USB 2 ports (RSK-06) |
| Clip-on ferrites | 2–4 | On USB and power leads (RSK-06) | Workshop `TBC` | — | |

## 3. Antennas (Buy, checked 2026-11-09)

Antennas are bought, not built: nobody is free to build them this week. The DIY guide ([`antennas.md`](antennas.md)) is kept only as a fallback. All are SMA male, matching the SMA female inputs on the SDRs.

| Item | Qty | For | Source | Price | Status / notes |
| --- | --- | --- | --- | --- | --- |
| Bingfu 4G LTE antenna, 8 dBi, magnetic base, 3 m cable, **2-pack** | 1 pack | LTE on the payload's SDR B; the second is a spare (the reference station stays in sim, ADR-0020) | Buy: Amazon.ca, ASIN B08DG87HBV | $20.49 | **In hand** (2026-11-10). Rated 698–960 MHz: covers 700 and 850 MHz LTE; band 71 (600 MHz) only weakly. The RF survey picks the band |
| NooElec ADS-B Antenna Bundle (1090 MHz SMA antenna, plus a 978 MHz antenna and MCX pigtails we don't need) | 1 | ADS-B on the payload's FlightStick (SDR A has no antenna) | Buy: Amazon.ca, ASIN B01FS0GI0W | $25.95 | **In hand** (2026-11-10). Small, light and hinged: good on the drone |
| SDR B bundle's telescopic antenna | — | VOR 114.6 MHz, fully extended and laid horizontal (VOR is horizontally polarised) | Comes with SDR B (section 2) | — | VOR is an add-on; if reception is poor, VOR stays in sim |
| GPS antenna | — | Payload: HON active antenna (section 1) | — | — | |

**Total antennas: $46.44.**

**Which LTE antenna on the payload: open (#200).** A first A/B on 2026-11-10 ([`analysis/results/antenna-ab-20261110/`](../analysis/results/antenna-ab-20261110/README.md)) did not settle it. On a plastic chair 0.5 m up, the Bingfu and the bundle's telescopic (25.7 cm) each tracked one cell at about +6 dB and the bundle's UHF mast none above the detection floor; but the same UHF mast on the ground tracked a cell at +14 dB, at that spot and at another. Mounting (ground plane `TBC`), auto gain and hand-holding confound the comparison. The choice is an owner decision; a re-test of each antenna on the same ground plane (`TBD`) at fixed gain is the follow-up.

**Weight on the drone:** the Bingfu magnetic base and its 3 m cable add weight on a 5" quad. Either strip the magnet and tape the coiled cable down, or use a stub antenna with no cable. One candidate is the Superbat 5G/4G SMA stub (ASIN B0D12H2CDP, $16.37, today); its frequency range has not been checked (`TBC`), so check the listing before ordering.

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

### Ground reference station: sim only

**Not built** (ADR-0020, *Amendment 2026-11-10*). There is no second LTE-capable SDR (the FlightStick is 1090 MHz-filtered) and no GPS with PPS for it (the GPS HAT is on the payload). It stays in sim: `ekf-base` and the `*-with-base` scenarios. Issues #84–#86 are closed.

What a built station would need is in ADR-0020 *Consequences*; the two parts it would have added (a second NESDR and a NEO-6M) are under *Not using*.

## 6. Drone

From `hardware/README.md` and `flight/`. Status and source of each are `TBD`; RSK-01 covers late parts. Without RC, the drone does not fly (ADR-0028).

| Item | Qty | Source | Status |
| --- | --- | --- | --- |
| Frame: ModuFrame-5 base (CC BY-SA), 3D printed | 1 | Build (EDC additive manufacturing lab) | `TBD` |
| Readytosky 2205 2700KV motors | 4 | `TBD` | `TBD` |
| iFlight BLITZ ATF435 stack: BLITZ ATF435 flight controller + BLITZ E55S 4-in-1 ESC, wire harness, grommets | 1 | Team: Ottawa FPV Shop, $112.99 (listing checked 2026-11-09) | Arriving the evening of 2026-11-09; flies Betaflight 4.5.5 (ADR-0028, *Amendment 2026-11-11 (owners)*). See the notes below the table |
| MTF-01 optical flow + rangefinder | 1 | `TBD` | `TBD`; needs a UART on the flight controller (the ATF435 has 6) |
| RC transmitter + receiver with kill switch: FlySky FS-i6 + FS-iA6B (iBUS) | 1 | `TBD` | In hand 2026-11-11; set up and failsafe-tested on the bench (ADR-0028, *Amendment 2026-11-11 (owners)*) |
| LiPo packs, charger, LiPo bag | `TBD` | `TBD` | `TBD` |
| Props and prop guards | `TBD` | `TBD` | `TBD` |

**The BLITZ ATF435 stack** ([Ottawa FPV Shop listing](https://ottawafpvshop.ca/products/iflight-blitz-atf435-stack-with-e55s-4-in-1-esc), [iFlight](https://shop.iflight.com/electronics-cat27/BLITZ-ATF435-Stack-E55S-4-IN-1-ESC-Pro2054)):
- **Flight controller:** AT32F435 MCU, ICM42688 gyro, DPS310 barometer, AT7456E OSD, 32 MB blackbox flash, 6 UARTs, I2C pads, 30.5 × 30.5 mm mounting. BEC 5 V 2.5 A and 9 V 2 A.
- **ESC:** E55S 4-in-1, 2–6S, 55 A continuous (65 A burst), current sensor, BLHeli_S/Bluejay firmware, DShot. It replaces the four separate 45 A ESCs this list used to have.
- **Firmware: Betaflight or INAV, not ArduPilot.** Betaflight and INAV both have an `IFLIGHT_BLITZ_ATF435` target (INAV checked in `src/main/target/` on master, 2026-11-09). ArduPilot's board list (`libraries/AP_HAL_ChibiOS/hwdef/` on master, 477 boards, checked 2026-11-09) has no AT32F435 board; its iFlight Blitz boards are F745 and H743 only. iFlight also says its products don't support autonomous flight. Resolved by ADR-0028: the drone flies INAV, and `flight/params/` (ArduPilot) is for SITL only. Amended 2026-11-11: INAV was never flashed; it flies Betaflight 4.5.5 (ADR-0028, *Amendment 2026-11-11 (owners)*).
- **Power:** the flight controller's 5 V 2.5 A BEC is not enough for the Pi 4B plus two SDRs (section 4), so the payload keeps its own 5 V ≥ 3 A BEC.

## Not using

| Item | Why |
| --- | --- |
| ESP32-S3 | None available; sensors go on the Pi 4B, Pi Zero 2 W hub as fallback (ADR-0018). Wi-Fi FTM and FTM responders are dropped |
| Raspberry Pi Pico 2W (HON) | Considered as the hub; the Pi 4B (or the Zero fallback) runs the same Python and generated MAVLink as the recorder (ADR-0018) |
| RTL-SDR Blog V3/V4, dipole kit, FM filter | Amazon.ca delivery Dec 21–25 (rule 1) |
| GT-U7 GPS module | Amazon.ca delivery Nov 13–24 (rule 1); the reference station stays in sim anyway |
| NooElec NESDR SMArt v5 dongle for the reference station (ASIN B01HA642SW, $63.95, checked 2026-11-09) | The reference station stays in sim (ADR-0020, *Amendment 2026-11-10*) |
| GY-NEO6MV2 NEO-6M GPS for the reference station (ASIN B0CTG63TYF, $14.39, checked 2026-11-09); ATGM336H alternative | The reference station stays in sim (ADR-0020, *Amendment 2026-11-10*) |
| Airspy Mini | Budget |
| Flamingo FM band-stop filter ($46) | Skipped; VOR is 16.8 km away. Revisit only if the RF survey shows FM overload |
| LoRa HAT 915 MHz (HON, **in hand** 2026-11-10) | A 22 dBm transmitter ~20 MHz above the 850 MHz LTE downlink would desensitize the unfiltered SDRs; Canadian certification unconfirmed; the payload is receive-only (REQ-07); no link is needed, since the laptop does the navigation (ADR-0002) |
| VL53L1X ToF (HON, in hand) | Optional indoor height truth only; drone already has the MTF-01 rangefinder |
| L-band patch antenna (Iridium) | LEO layer is simulated (ADR-0013, mentor Q5) |
| DIY antennas (ADS-B and LTE ground planes, VOR dipole), SMA pigtails, copper wire, PCB plates | Nobody free to build them this week; antennas are bought (section 3). [`antennas.md`](antennas.md) is the fallback |

## Open decisions

- **Payload LTE antenna: open (#200).** Bingfu, telescopic or UHF mast; the 2026-11-10 A/B is confounded by mounting (section 3). Needs the ground-plane re-test, then the owner's choice.

- **LoRa HAT (915 MHz): in hand (HON, 2026-11-10), not using** (*Not using*). Using it anywhere needs a decision (an ADR) first.

- **Flight-controller firmware: decided, Betaflight 4.5.5 (ADR-0028, *Amendment 2026-11-11 (owners)*).** Which MAVLink messages Betaflight sends to the recorder is `TBC`.
- **RC transmitter and receiver with a kill switch: in hand** (FlySky FS-i6 + FS-iA6B, 2026-11-11; `flight/README.md`).

- **Ground reference station: decided, sim only** (ADR-0020, *Amendment 2026-11-10*); #84–#86 closed. The antennas are in hand (section 3).

- Hub needed at all: day-1 test of IMU jitter, CPU load, dropped samples and PPS offset on the 4B (ADR-0018, `TBD`). If yes, its USB link is serial or network gadget (`TBC`).
- USB current: two SDRs (plus the Zero, if used) against the 4B's USB budget; measure with the DPS-150 (ADR-0018, `TBC`).
- Where Wi-Fi scans run in flight without disturbing the ZeroMQ link (ADR-0018, `TBC`).
