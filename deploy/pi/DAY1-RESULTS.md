# Day-1 results (#88)

What the payload Pi 4B measured with both radios recording ([`RUNBOOK.md`](RUNBOOK.md) B). Thresholds are `TBD` (ADR-0018), so these are values, not pass or fail; the hub decision stays with the owners.

## `20261111-0040-static-fullsuite` (2026-11-11)

First full-suite session. Recorded at `4d3598b` (local commit; its change is on `main` as `ee20817`, see [`verification.md`](../../systems/verification.md#first-real-air-sessions-2026-11-10)). Static, outdoors, everything on the ground and spaced apart. The receiver position is withheld for privacy.

- **Hardware:** Pi 4 Model B Rev 1.5 (4 GB), kernel `6.18.50+rpt-rpi-v8`, Python 3.13.5. Adafruit GPS HAT with an external active antenna, PPS-locked. MPU6050 and BMP180 on I2C.
- **Radios:** SDR A is a NESDR on a Bingfu antenna, LTE EARFCN 2460 (875 MHz) at 1.92 MS/s. SDR B is an AirNav FlightStick on a NooElec 1090 antenna, at 1090 MHz and 2.4 MS/s, auto gain. Together 8.64 MB/s to the SD card.
- **Source of the numbers:** `pnt day1` on the Pi, which wrote `20261111-0040-static-fullsuite.day1.md` and `.day1.json` beside the session. Both are copied to the laptop's session folder and are not in git.

| Quantity | Value |
| --- | --- |
| Duration | 599.4 s (SDR A), 599.5 s (SDR B) |
| IMU rate | 100.02 Hz, 59,803 samples |
| IMU jitter std / p99 / max | 0.743 / 1.602 / 28.429 ms |
| IMU intervals > 1.5× nominal | 222 (0.37 %); longest 38.4 ms |
| PPS edges seen (gpsd) | 600 |
| PPS offset mean / std / max | 0.304 / 14.456 / 38.186 µs |
| chrony reference; system time mean / std / max | PPS; −0.894 / 2.433 / 14.853 µs |
| chrony RMS offset mean / max | 154.7 / 260.0 µs |
| SDR A gaps; dropped samples (est.) | 4; 33,011,742 (17.19 s) |
| SDR A rate against host | −2.397 ppm |
| SDR A latency above envelope p99 / max | 312.1 / 1231.9 ms |
| SDR B gaps; dropped samples (est.) | 4; 41,116,974 (17.13 s) |
| SDR B rate against host | +19.813 ppm |
| SDR B latency above envelope p99 / max | 120.7 / 990.1 ms |
| CPU mean / max | 5.7 / 16.5 % |
| Max SoC temperature | 31.6 °C |
| Throttled flags | `0x0` |
| Min available memory | 3427 MB |
| Min free disk | 5.08 GB |
| Records dropped (queue) | 0 |
| libzmq CURVE | yes |
| USB current | `TBD`: not read off the DPS-150 |

### Both radios drop samples at the same instants

`first_gaps` in the `.day1.json`, as time from each radio's first sample (dropped samples before it added back):

| Gap | SDR A start (s) | SDR A length (s) | SDR B start (s) | SDR B length (s) |
| --- | --- | --- | --- | --- |
| 1 | 59.60 | 5.85 | 59.64 | 6.07 |
| 2 | 190.04 | 1.59 | 190.23 | 1.66 |
| 3 | 400.80 | 8.39 | 401.22 | 8.23 |
| 4 | 430.89 | 1.36 | 431.35 | 1.17 |

Each gap starts within 0.5 s on both radios and lasts about as long. Roughly 17 s of the 10 min is lost on each radio (2.9 %). A cause shared by both radios, not by one dongle, fits this: a write stall on the SD card is the likely one (`TBC`: not shown directly). CPU (5.7 % mean) and memory (3427 MB available) were far from their limits, and the record queue dropped nothing.

Options, for the owners (no decision here):

- **One radio at a time:** halves the write rate (3.84 or 4.8 MB/s). It loses the simultaneous LTE and ADS-B capture.
- **A lower sample rate:** less data per second on the card. Which rate each decoder still works at is `TBD` (readsb was run at 2.4 MS/s only).
- **Faster storage:** a USB SSD (ADR-0018 already allows one on a USB 3 port, shielded and away from the GPS antenna, RSK-06) or a faster A2 card. It needs a rerun of this test to show the gaps are gone.

For the board capture profile (`capture-pi4b`, [`REHEARSAL.md`](REHEARSAL.md), #53), from this session: 4 gap events in 10 min on both radios together (0.4 per min if a shared stall counts once, 0.8 per min if each radio's counts), mean gap 4.3 s (1.2 to 8.4 s). The committed placeholders are 0.2 per min and 0.05 s. The profile is not changed here: stream loss was not measured (no laptop recording of the stream), and the profile belongs to #53.

### ADS-B: the FlightStick overloads at auto gain

readsb decoded **0 frames** from SDR B's 9 min 42 s capture: `frames-avr.txt` is empty and `readsb.err` ends in a normal exit. On the Pi, the capture clips about 1.5 % of its samples with an RMS of 44 counts (reported from a check on the Pi; not re-checked on the laptop, which has no copy of `sdr_b.cu8`). The FlightStick has its own LNA, so auto gain overloads the front end. A fixed lower gain is needed (`:gain=<dB>` on the `--sdr` argument); its value is `TBD`, and that follow-up is owned separately.

### Not measured

- USB current (DPS-150).
- Stream loss to the laptop.
- Whether the gaps come from the SD card: a run with faster storage, or with one radio, would show it.
