#!/usr/bin/env bash
# Start ArduPilot Copter SITL, forwarding MAVLink to udp:127.0.0.1:14550 for fly.py / QGC.
# Needs ArduPilot's sim_vehicle.py on PATH (see README.md).
set -euo pipefail
if ! command -v sim_vehicle.py >/dev/null; then
  echo "sim_vehicle.py not found. See flight/sitl/README.md to install ArduPilot SITL." >&2
  exit 1
fi
# Carleton campus as home: lat,lon,alt,heading
exec sim_vehicle.py -v ArduCopter --frame quad --custom-location=45.3876,-75.6960,70,0 \
  --out=udp:127.0.0.1:14550 --no-rebuild "$@"
