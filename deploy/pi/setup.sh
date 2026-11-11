#!/usr/bin/env bash
# Idempotent Pi setup for the payload. Run on the Pi from ~/pnt: `bash deploy/pi/setup.sh`.
set -euo pipefail
cd "$(dirname "$0")/../.."

sudo apt-get update -qq
sudo apt-get install -y -qq chrony pps-tools gpsd gpsd-clients rtl-sdr python3-venv i2c-tools
sudo apt-get install -y -qq mavlink-router 2>/dev/null || echo "mavlink-router not packaged: build from source (TODO)"
# readsb (Debian package) decodes recorded ADS-B IQ offline only: `--device-type ifile` (RUNBOOK).
# Debian's build has no RTL-SDR support, and its service stays disabled so nothing touches the radios at boot.
sudo apt-get install -y -qq readsb
if systemctl cat readsb.service >/dev/null 2>&1; then
  sudo systemctl disable --now readsb.service
fi

CFG=/boot/firmware/config.txt
# Adafruit Ultimate GPS HAT: NMEA on /dev/serial0, PPS on GPIO4 (ADR-0014)
grep -q '^dtoverlay=pps-gpio' "$CFG" || echo 'dtoverlay=pps-gpio,gpiopin=4' | sudo tee -a "$CFG"
sudo raspi-config nonint do_serial_cons 1   # no login console on the UART
sudo raspi-config nonint do_serial_hw 0     # UART hardware on
sudo raspi-config nonint do_i2c 0           # I2C on: MPU6050 + BMP180 on the Pi (ADR-0018)
printf 'DEVICES="/dev/serial0 /dev/pps0"\nGPSD_OPTIONS="-n"\nUSBAUTO="false"\n' | sudo tee /etc/default/gpsd >/dev/null
sudo systemctl enable --now gpsd
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/rtlsdr.conf >/dev/null

sudo install -m 644 deploy/pi/chrony.conf /etc/chrony/conf.d/pnt.conf
# chrony 4.6 (Trixie) exits if /dev/pps0 is missing, as it is before the first reboot
if ! sudo systemctl restart chrony; then
  [ -e /dev/pps0 ] && exit 1
  echo "chrony did not start: /dev/pps0 appears after the reboot below"
fi

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -e '.[payload]'
echo "setup done; reboot once after the first run for the PPS overlay"
