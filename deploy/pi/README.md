# Raspberry Pi 3B+ setup

Raspberry Pi OS Bookworm (64-bit, Lite). Hostname `pnt`, user `pi`, reachable as `pi@pnt.local`.

What `setup.sh` does (idempotent; `just pi-deploy` runs it after copying the repo):
1. Installs `chrony`, `pps-tools`, `gpsd`, `rtl-sdr`, `python3-venv`, `mavlink-router` (if packaged).
2. Sets up the **Adafruit Ultimate GPS HAT** (ADR-0014): UART on `/dev/serial0` without a login console, PPS overlay on GPIO4 (`dtoverlay=pps-gpio,gpiopin=4`), gpsd reading both. Blacklists the DVB driver so RTL-SDRs are free.
3. Installs `chrony.conf` (GPS NMEA + PPS refclocks).
4. Creates `~/pnt/.venv` with the `payload` extra.

Checks after a reboot: `sudo ppstest /dev/pps0` (one line per second), `gpsmon` (fix + per-satellite SNR), `chronyc sources -v` (PPS selected, offset in µs), `rtl_test -t` (both dongles).

The Pi Zero 2 W hub also needs the PPS edge: run a wire from the HAT's PPS pin (GPIO4) to the Zero's PPS GPIO (`TBC`), with a common ground. The Zero plugs into a 3B+ USB port by its data port (ADR-0018).

The 3B+ has only USB 2 ports, and they share one bus with its Ethernet: leave Ethernet unplugged while recording. Space the SDRs out with short extensions and ferrites (RSK-06).
