# Pi runbook: day 1, captures, base station

A checklist to follow with the Pi in hand. Commands run **on the Pi in `~/pnt`** unless they say *laptop*. Results stay in `data/sessions/` (never in git); quote a number with its session name and the commit in its `meta.yaml` (REQ-10).

## A. Set up (once per SD card)

1. Flash Raspberry Pi OS Bookworm Lite 64-bit: hostname `pnt`, user `pi`, Wi-Fi and SSH on.
2. Plug in: GPS HAT with its antenna at a window or outdoors; MPU6050 and BMP280 on I2C (SDA GPIO2, SCL GPIO3, 3V3, GND); both SDRs on the **black USB 2 ports** with antennas, spaced apart; Pi camera. Power from the DPS-150 at 5.1 V (current limit 3 A) so the current can be read.
3. *Laptop:* `just pi-deploy` (copies the repo and the commit stamp, runs `deploy/pi/setup.sh`). Then `ssh pi@pnt.local sudo reboot` once.
4. Check, after 10–15 min with a fix so chrony can lock:

   | Command | Good output |
   | --- | --- |
   | `sudo ppstest /dev/pps0` (Ctrl-C) | one `assert` line per second |
   | `chronyc sources -v` | `#* PPS` (selected), offset a few µs or less |
   | `gpsmon` (q) | 3D fix, satellites with SNR |
   | `rtl_test -t` | both dongles listed (`0:` and `1:`); note which index is which |
   | `i2cdetect -y 1` | `68` (MPU6050) and `76` or `77` (BMP280) |
   | `.venv/bin/pnt record --help` | the help text (the Python install works) |

## B. Day-1 test (#88, #17)

5. `bash deploy/pi/day1.sh 10` (10 min; SDR A at 875 MHz, SDR B at 1090 MHz at 2.4 MS/s). If `rtl_test` showed the ADS-B stick as index 0: `DEV_A=1 DEV_B=0 bash deploy/pi/day1.sh 10`.
6. While it records, read the USB current off the DPS-150 and type it in when asked.
7. Good output: `data/sessions/<date>-static-day1.day1.md` with every row filled, and `<date>-static-day1.pps.json` with `"rate_hz": 1.0` and `"pps_selected": true`. The thresholds are `TBD` (ADR-0018): post the table in #88 as it is, with the session name.

## C. Day-1 LTE capture (for the LTE front end)

8. Static, outdoors or at a window, GPS fixed, 15 min, one EARFCN: Rogers EARFCN 2460 (875 MHz, top of `data/reference/lte-scan-list-ottawa.csv` from #87):

   ```bash
   .venv/bin/pnt record --platform static --place <site> --duration 900 \
     --sdr a:875e6:rate=1.92e6:dev=0:earfcn=2460 --notes "day-1 LTE, EARFCN 2460, antenna <where>"
   ```

   Good output at the end: `captured: adafruit-gps-hat, ... rtl-sdr`, and `sdr_a.json` in the session with `"samples"` near 1.92e6 × 900 and `"gaps_suspected": []`. The GPS fixes in `/meas/gnss` are the position truth. Add `:gain=<dB>` for a fixed gain; without it the dongle uses AGC.

## D. Handheld walk and replay (#19)

9. `.venv/bin/pnt record --platform handheld --place carleton --sdr a:875e6:rate=1.92e6:earfcn=2460` and walk; Ctrl-C to stop. The summary lists what was captured, absent or failed.
10. *Laptop:* `rsync -av pi@pnt.local:~/pnt/data/sessions/ data/sessions/` then `pnt replay data/sessions/<session>` (prints the number of estimates) and `pnt viz data/sessions/<session>` for Foxglove.

## E. Live (laptop)

11. While the Pi records: `pnt live --connect tcp://pnt.local:5556 --out data/sessions/<date>-live` prints a position line per second and records what it received. It takes the origin from the Pi's stream (the Pi's first 3D fix) unless `--origin lat,lon,h` is given.

## F. Ground reference station (Pi 3B+, #85)

12. Same set-up as A with hostname `pnt-base`, the NEO-6M on the UART (TX→GPIO15, RX→GPIO14) with PPS on GPIO4, one SDR, the LTE antenna identical to the payload's. *Laptop:* `just pi-deploy pi@pnt-base.local`.
13. Survey, at least 1 h (`TBC`, ADR-0020), antenna fixed and not touched:

    ```bash
    .venv/bin/pnt record --receiver reference --platform static --place <site> --gnss-hw neo-6m \
      --no-imu --no-baro --no-camera --no-fc --duration 4000 --sdr a:875e6:rate=1.92e6:earfcn=2460
    .venv/bin/pnt survey data/sessions/<session>
    ```

    Good output: `data/sessions/<session>.survey.yaml` with `reference.position_llh` and a numeric `sigma_m` from the averaging (it is `TBD` if fewer than four 10-min batches). Do not edit `sigma_m` by hand.
14. Base-and-payload sessions: give both Pis the **same origin**, the surveyed point (`O=<lat>,<lon>,<h>` from the survey file):
    - base: `pnt record --receiver reference --origin $O --reference data/sessions/<survey>.survey.yaml --gnss-hw neo-6m --no-imu --no-baro --no-camera --no-fc --sdr a:875e6:earfcn=2460`
    - payload: `pnt record --origin $O ...` as in D
    - *laptop:* `pnt live --connect tcp://pnt.local:5556 --connect tcp://pnt-base.local:5556 --origin $O --reference <survey.yaml> --estimator ekf-base --out data/sessions/<date>-live-base`

## If something is wrong

- A device shows as `absent` or `failed` in the summary or in `meta.yaml` `notes`: the others kept recording. Fix it and record again.
- `rtl_sdr` busy: another program holds the dongle (`sudo pkill rtl_`), or the DVB driver is loaded (setup blacklists it; reboot).
- No PPS: check the overlay line in `/boot/firmware/config.txt` and reboot.
