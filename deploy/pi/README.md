# Raspberry Pi 4B setup

Step-by-step with the Pi in hand (day-1 test, captures, base station): [`RUNBOOK.md`](RUNBOOK.md). The day-1 test is scripted in `day1.sh`. Which of its numbers size the sim's board capture faults: [`REHEARSAL.md`](REHEARSAL.md) (#53).

Raspberry Pi OS Lite (64-bit). The payload Pi runs Trixie (Debian 13); see the Imager notes in [`RUNBOOK.md`](RUNBOOK.md) A1. Hostname `pnt`, user `pi`, reachable as `pi@pnt.local`.
First real LTE capture, what to measure and which `TBC` it replaces: [`first-capture.md`](first-capture.md).

What `setup.sh` does (idempotent; `just pi-deploy` runs it after copying the files git tracks):
1. Installs `chrony`, `pps-tools`, `gpsd`, `rtl-sdr`, `python3-venv`, `mavlink-router` (if packaged).
2. Enables I2C for the IMU and barometer (ADR-0018). Sets up the **Adafruit Ultimate GPS HAT** (ADR-0014): UART on `/dev/serial0` without a login console, PPS overlay on GPIO4 (`dtoverlay=pps-gpio,gpiopin=4`), gpsd reading both. Blacklists the DVB driver so RTL-SDRs are free.
3. Installs `chrony.conf` (GPS NMEA + PPS refclocks).
4. Creates `~/pnt/.venv` with the `payload` extra.

`setup.sh` makes no keys. Each host makes its own CurveZMQ key pair for the stream, and the hosts exchange public keys ([`RUNBOOK.md`](RUNBOOK.md#keys-once-per-host), ADR-0026).

Checks after a reboot: `sudo ppstest /dev/pps0` (one line per second), `gpsmon` (fix + per-satellite SNR), `chronyc sources -v` (PPS selected, offset in µs), `rtl_test -t` (both dongles), `/usr/sbin/i2cdetect -y 1` (MPU6050 at 0x68, BMP180 at 0x77; a BMP280 would be 0x76 or 0x77).

The MPU6050 and BMP180 (ADR-0014) go on the Pi's I2C bus (GPIO2/GPIO3, through the HAT's prototyping area). Only if the day-1 test brings back the Pi Zero 2 W hub (ADR-0018): wire the HAT's PPS pin (GPIO4) to the Zero's PPS GPIO (`TBC`) with a common ground, and plug the Zero's data port into a Pi USB 2 port.

Plug both SDRs into the **USB 2 ports** (black). USB 3 ports radiate near GPS L1 and 2.4 GHz: leave them empty, or use one only for a shielded recording SSD kept away from the GPS antenna. Space the SDRs out with short extensions and ferrites (RSK-06). The 4B needs a 5 V 3 A supply and a heatsink or fan.

RF survey at a site (#20): `bash deploy/pi/rf_survey.sh <site>` with an antenna on the SDR: a 24–1766 MHz `rtl_power` sweep, short captures of the top LTE EARFCNs and 60 s of ADS-B, into `data/sessions/<date>-survey-<site>/`. Analyse on the laptop with `analysis/rf_survey.py`.

ADS-B and VOR are decoded from recorded IQ, not live: readsb on the Pi (installed by hand, service disabled) and Voracious on the laptop. Neither is in `setup.sh`; see [`RUNBOOK.md`](RUNBOOK.md) H.
