# Day-1 results (#88)

What the payload Pi 4B measured with both radios recording ([`RUNBOOK.md`](RUNBOOK.md) B). Thresholds are `TBD` (ADR-0018), so these are values, not pass or fail; the hub decision stays with the owners.

## `20261111-0040-static-fullsuite` (2026-11-11)

First full-suite session. Recorded at the change that is `ee20817` on `main` (the session's `meta.yaml` names the commit it had then, from #141's branch; see [`verification.md`](../../systems/verification.md#first-real-air-sessions-2026-11-10)). Static, outdoors, everything on the ground and spaced apart. The receiver position is withheld for privacy.

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

Each gap starts within 0.5 s on both radios and lasts about as long. Roughly 17 s of the 10 min is lost on each radio (2.9 %). The cause is shared by both radios, not one dongle. CPU (5.7 % mean) and memory (3427 MB available) were far from their limits, and the record queue dropped nothing. The re-record below, with the IQ on a USB drive, had no gap, which points to SD-card write stalls.

The board capture profile (`capture-pi4b`, [`REHEARSAL.md`](REHEARSAL.md), #53) takes its gap rate and length from this session.

### ADS-B: the FlightStick overloads at auto gain

readsb decoded **0 frames** from SDR B's 9 min 42 s capture: `frames-avr.txt` is empty and `readsb.err` ends in a normal exit. On the Pi, the capture clips about 1.5 % of its samples with an RMS of 44 counts (reported from a check on the Pi; not re-checked on the laptop, which has no copy of `sdr_b.cu8`). The FlightStick has its own LNA, so auto gain overloads the front end. A fixed lower gain is needed (`:gain=<dB>` on the `--sdr` argument); its value is `TBD`, and that follow-up is owned separately.

### Not measured

- USB current (DPS-150).
- Stream loss to the laptop.

## `20261111-0151-static-fullsuite2` (2026-11-11)

Re-record, 01:51–02:01, recorded at the change that is `8c4e856` on `main` (the session's `meta.yaml` names the commit it had then, from #209's branch). Laptop `pnt day1` at `463982c` on the copied session; the copy's SHA-256 matched the drive (coordinator's check). Same setup as 0040 except:

- IQ to a SanDisk USB 3.2 Gen 1 drive (ext4) on the USB 2 bus, mounted at `/mnt/pntdata`
- the LTE antenna taped upright
- the FlightStick at a fixed 38.6 dB

| Quantity | 0040 (SD card) | 0151 (USB drive) |
| --- | --- | --- |
| SDR A gaps; IQ kept | 4; 582.3 s of 599.4 s | 0 (`gaps` and `gaps_suspected` empty); 599.4 s |
| SDR B gaps; IQ kept | 4; 582.4 s of 599.5 s | 0; 599.4 s |
| SDR A / B latency above envelope p99 (ms) | 312.1 / 120.7 | 4.0 / 14.2 |
| SDR A / B latency above envelope max (ms) | 1231.9 / 990.1 | 524.0 / 558.8 |
| SDR A / B rate against host (ppm) | −2.397 / +19.813 | +0.772 / +23.116 |
| IMU samples; jitter std / p99 / max (ms) | 59,803; 0.743 / 1.602 / 28.429 | 59,863; 0.675 / 1.369 / 27.712 |
| IMU intervals > 1.5× nominal | 222 | 186 |
| GNSS fixes; barometer samples | 600; 5,998 | 601; 5,999 |
| PPS offset mean / std / max (µs) | 0.304 / 14.456 / 38.186 | −5.184 / 4.411 / 19.513 |
| chrony RMS offset mean / max (µs) | 154.7 / 260.0 | 11.1 / 20.6 |
| CPU mean / max | 5.7 / 16.5 % | 6.0 / 14.7 % |
| Max SoC temperature; throttled | 31.6 °C; `0x0` | 30.2 °C; `0x0` |
| Min available memory | 3427 MB | 3476 MB |
| Records dropped (queue) | 0 | 0 |
| Camera | not in the session | failed: `rpicam-vid exited with 255` (no camera fitted, `TBC`) |

**Storage:** the gaps went away with the USB drive. One 10 min run with no gap bounds the drive's gap rate below about 0.3 per minute (95 %); it does not show zero. Which storage the payload records to is an owner decision: [ADR-0042](../../systems/adr/0042-record-iq-to-usb-drive.md) (Proposed) lays out the options with this evidence.

**ADS-B:** at a fixed 38.6 dB the FlightStick capture still holds impulsive interference that comes in through the antenna (#211). With the antenna unscrewed, the share of samples above 30× the median fell from 5.0 % to 0.02 %. That was measured on the Pi by the coordinator and is not re-checked here. Whether readsb decodes frames from this capture is not checked here.
