# Every command for the repo. `just --list` shows them all.
set dotenv-load := false

py := "uv run"

# Install everything for the laptop (ground + dev extras)
setup:
    uv sync --extra ground --extra dev

# Run a simulated scenario end to end -> MCAP log + metrics
sim scenario="gps-outage" *args="":
    {{py}} pnt sim {{scenario}} {{args}}

# Monte Carlo over a scenario
eval scenario="gps-outage" runs="50":
    {{py}} pnt eval {{scenario}} --runs {{runs}}

# Re-run the estimator over a recorded MCAP (sim or real session)
replay path:
    {{py}} pnt replay {{path}}

# Subscribe to the Pi's live stream, run nav + dashboard (not built yet)
live:
    {{py}} pnt live

# Regenerate MAVLink code (C for the ESP32, Python for the Pi) from systems/icd/pnt.xml
gen:
    {{py}} mavgen.py --lang=C --wire-protocol=2.0 --output=firmware/esp32-hub/lib/pnt_mavlink systems/icd/pnt.xml
    {{py}} mavgen.py --lang=Python3 --wire-protocol=2.0 --output=src/pnt/io/pnt_mavlink.py systems/icd/pnt.xml

# ESP32 hub firmware
fw:
    pio run -d firmware/esp32-hub
fw-flash:
    pio run -d firmware/esp32-hub -t upload

# ArduPilot SITL + scripted mission (see flight/sitl/README.md)
sitl:
    bash flight/sitl/run.sh
mission pattern="square":
    {{py}} python flight/missions/fly.py {{pattern}}

# Copy the repo to the Pi and restart its services (PI_HOST=pi@pnt.local)
pi-deploy host="pi@pnt.local":
    rsync -az --delete --exclude .venv --exclude data/sessions --exclude .git ./ {{host}}:~/pnt/
    ssh {{host}} 'cd ~/pnt && bash deploy/pi/setup.sh'

test:
    {{py}} pytest -q
lint:
    {{py}} ruff check .
    {{py}} ruff format --check .
fmt:
    {{py}} ruff format .
    {{py}} ruff check --fix .
