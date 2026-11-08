#!/usr/bin/env bash
# Idempotent Pi setup for the payload. Run on the Pi from ~/pnt: `bash deploy/pi/setup.sh`.
set -euo pipefail
cd "$(dirname "$0")/../.."

sudo apt-get update -qq
sudo apt-get install -y -qq chrony pps-tools rtl-sdr python3-venv
sudo apt-get install -y -qq mavlink-router 2>/dev/null || echo "mavlink-router not packaged: build from source (TODO)"

CFG=/boot/firmware/config.txt
grep -q '^dtoverlay=pps-gpio' "$CFG" || echo 'dtoverlay=pps-gpio,gpiopin=18' | sudo tee -a "$CFG"
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/rtlsdr.conf >/dev/null

sudo install -m 644 deploy/pi/chrony.conf /etc/chrony/conf.d/pnt.conf
sudo systemctl restart chrony

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -e '.[payload]'
echo "setup done; reboot once after the first run for the PPS overlay"
