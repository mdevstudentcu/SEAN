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

# Re-run every scenario's Monte Carlo and rewrite the results table in systems/verification.md
results runs="50":
    {{py}} pnt results --runs {{runs}}

# The four results figures (error after GPS loss, Stanford, ablation, holdover) and their numbers
# -> analysis/results/figures-<estimator>/
figures estimator="ekf" runs="50":
    {{py}} python analysis/figures.py --estimator {{estimator}} --runs {{runs}}

# Re-run the estimator over a recorded MCAP (sim or real session)
replay path:
    {{py}} pnt replay {{path}}

# Error, Stanford, trust and clock figures for a session -> analysis/results/<session>/
plot path *args="":
    {{py}} pnt plot {{path}} {{args}}

# Write a Foxglove companion file for a session (see analysis/README.md)
viz path:
    {{py}} pnt viz {{path}}

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

# Everything to run before calling work ready (systems/quality.md). CI adds generated code and firmware
qa:
    #!/usr/bin/env bash
    set -euo pipefail
    commit="$(git rev-parse --short HEAD)"
    state="clean"
    if [ -n "$(git status --porcelain)" ]; then state="DIRTY, not valid for a verdict"; fi
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    {{py}} ruff check .
    {{py}} ruff format --check .
    {{py}} pytest -q
    {{py}} pnt sim gps-outage --out "$tmp/smoke"
    {{py}} pnt plot "$tmp/smoke" --out "$tmp/plots"
    echo "qa passed at $commit ($state)"
