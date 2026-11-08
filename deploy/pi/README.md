# Raspberry Pi 4B setup

Raspberry Pi OS Bookworm (64-bit, Lite). Hostname `pnt`, user `pi`, reachable as `pi@pnt.local`.

What `setup.sh` does (idempotent; `just pi-deploy` runs it after copying the repo):
1. Installs `chrony`, `pps-tools`, `rtl-sdr`, `python3-venv`, `mavlink-router` (if packaged).
2. Enables the PPS GPIO overlay (`dtoverlay=pps-gpio,gpiopin=18`, pin TBC with the wiring) and blacklists the DVB driver so RTL-SDRs are free.
3. Installs `chrony.conf` (GPS NMEA + PPS refclocks).
4. Creates `~/pnt/.venv` with the `payload` extra.

Checks after a reboot: `sudo ppstest /dev/pps0` (one line per second), `chronyc sources -v` (PPS selected, offset in µs), `rtl_test -t` (both dongles).

Plug SDRs into the **black USB 2 ports** (USB 3 interferes with GPS and 2.4 GHz: RSK-06).
