# Pi runbook: day 1, captures, base station

A checklist to follow with the Pi in hand. Commands run **on the Pi in `~/pnt`** unless they say *laptop*. Results stay in `data/sessions/` (never in git); quote a number with its session name and the commit in its `meta.yaml` (REQ-10).

**The stream is authenticated.** `pnt record` streams every record on TCP port 5556 unless given `--no-stream`. It is encrypted with CurveZMQ, only laptops whose key the Pi trusts can subscribe, and the laptop accepts data only from the Pi keys it trusts (ADR-0026, #89). Both commands refuse to stream until the keys are set up ([Keys](#keys-once-per-host)). `--insecure` streams in plaintext instead: anyone who can reach the port can read the positions or inject records. Use it only on the laptop's own hotspot or Ethernet, never on campus or venue Wi-Fi.

## A. Set up (once per SD card)

1. Flash Raspberry Pi OS Bookworm Lite 64-bit: hostname `pnt`, user `pi`, Wi-Fi and SSH on.
2. Plug in: GPS HAT with its antenna at a window or outdoors; MPU6050 and BMP180 on I2C (SDA GPIO2, SCL GPIO3, 3V3, GND); both SDRs on the **black USB 2 ports** with antennas, spaced apart; Pi camera. Power from the DPS-150 at 5.1 V (current limit 3 A) so the current can be read.
3. *Laptop:* `just pi-deploy` (copies the repo and the commit stamp, runs `deploy/pi/setup.sh`). Then `ssh pi@pnt.local sudo reboot` once.
4. Check, after 10–15 min with a fix so chrony can lock:

   | Command | Good output |
   | --- | --- |
   | `sudo ppstest /dev/pps0` (Ctrl-C) | one `assert` line per second |
   | `chronyc sources -v` | `#* PPS` (selected), offset a few µs or less |
   | `gpsmon` (q) | 3D fix, satellites with SNR |
   | `rtl_test -t` | both dongles listed (`0:` and `1:`); note which index is which |
   | `i2cdetect -y 1` | `68` (MPU6050) and `77` (BMP180, ADR-0014). `pnt record` then lists `bmp180` under captured |
   | `.venv/bin/pnt record --help` | the help text (the Python install works) |
   | `.venv/bin/python -c "import zmq; print(zmq.has('curve'))"` | `True`. If `False`, this libzmq cannot authenticate the stream: record with `--no-stream`, and raise it in #89 (ADR-0026 is reopened) |

## Keys (once per host)

Before the first streamed recording.

Each host makes its own key pair. The secret key stays on that host (`~/.config/pnt/keys/<role>.key_secret`, mode 600); only public keys are copied. Keys never go in git or in a session. `pnt keys gen` never overwrites a key without `--force`.

K1. Make the keys:
   - payload Pi: `ssh pi@pnt.local '~/pnt/.venv/bin/pnt keys gen --role payload'`
   - base Pi: `ssh pi@pnt-base.local '~/pnt/.venv/bin/pnt keys gen --role reference'`
   - *laptop:* `pnt keys gen --role laptop`

K2. Copy the public keys (*laptop*). The files are public, so `scp` is enough:

   ```bash
   scp pi@pnt.local:.config/pnt/keys/payload.key /tmp/payload.key
   scp pi@pnt-base.local:.config/pnt/keys/reference.key /tmp/reference.key
   pnt keys trust payload /tmp/payload.key
   pnt keys trust reference /tmp/reference.key
   for pi in pnt pnt-base; do
     scp ~/.config/pnt/keys/laptop.key pi@$pi.local:/tmp/laptop.key
     ssh pi@$pi.local '~/pnt/.venv/bin/pnt keys trust laptop /tmp/laptop.key'
   done
   ```

   A second laptop makes its own key and is trusted under another name: `pnt keys trust laptop-mo <file>` on each Pi.

K3. Check: `pnt keys show` on each host prints its public key and an `id`. The `id` of `payload` under `trusted:` on the laptop must equal the `id` that `pnt keys show` prints on the payload Pi. Do the same for `reference` and `laptop`. Good output at stream time: `pnt record` prints `streaming on ...; stream: authenticated, CurveZMQ (#89)`, and `meta.yaml` `notes` on both sides say `stream: authenticated`.

A key is replaced with `pnt keys gen --role <role> --force`, then K2 again for that key (`trust ... --force` on the peers). Replace it if a host or its SD card may have been copied or lost.

## B. Day-1 test (#88, #17)

5. With the [keys](#keys-once-per-host) set up: `bash deploy/pi/day1.sh 10` (10 min; SDR A at 875 MHz, SDR B at 1090 MHz at 2.4 MS/s). If `rtl_test` showed the ADS-B stick as index 0: `DEV_A=1 DEV_B=0 bash deploy/pi/day1.sh 10`. If libzmq has no CURVE (A4), run it on a private link with `RECORD_ARGS=--insecure` and note that in #88: the stream cost then excludes encryption.
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

11. With the [keys](#keys-once-per-host) set up, while the Pi records: `pnt live --connect tcp://pnt.local:5556 --out data/sessions/<date>-live` prints a position line per second and records what it received. It takes the origin from the Pi's stream (the Pi's first 3D fix) unless `--origin lat,lon,h` is given.

## F. Ground reference station (Pi 3B+, #85)

12. Same set-up as A and [Keys](#keys-once-per-host) with hostname `pnt-base`, the NEO-6M on the UART (TX→GPIO15, RX→GPIO14) with PPS on GPIO4, one SDR, the LTE antenna identical to the payload's. *Laptop:* `just pi-deploy pi@pnt-base.local`.
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
    - *laptop:* `pnt live --connect payload=tcp://pnt.local:5556 --connect reference=tcp://pnt-base.local:5556 --origin $O --reference <survey.yaml> --estimator ekf-base --out data/sessions/<date>-live-base` (each endpoint is checked against its own trusted key; untagged, the first is the payload and the second the base)

## If something is wrong

- A device shows as `absent` or `failed` in the summary or in `meta.yaml` `notes`: the others kept recording. Fix it and record again.
- `rtl_sdr` busy: another program holds the dongle (`sudo pkill rtl_`), or the DVB driver is loaded (setup blacklists it; reboot).
- No PPS: check the overlay line in `/boot/firmware/config.txt` and reboot.
- `pnt record` or `pnt live` refuses to stream: the message names the missing key and the command that makes it ([Keys](#keys-once-per-host)).
- `pnt live` gets nothing while the Pi records: a key does not match, and CurveZMQ fails the handshake without telling the laptop. Compare the `id`s from `pnt keys show` (K3). The Pi's `meta.yaml` `notes` count `connections refused` (laptop key not trusted).
- `pnt live` stops receiving from one Pi mid-run: a message that fails authentication (tampered or corrupted) ends that connection, and ZeroMQ does not reopen it. Restart `pnt live`, and say so in the session notes.
