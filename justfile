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

# The results we present (#27), from a clean commit: every scenario's Monte Carlo into the results
# table of systems/verification.md, then the four figures (error after GPS loss scored as T1,
# Stanford, ablation, timing holdover) with their numbers into analysis/results/final/
results runs="50" estimator="ekf" jobs=num_cpus():
    {{py}} pnt results --runs {{runs}} --estimator {{estimator}} --jobs {{jobs}}
    {{py}} python analysis/figures.py --estimator {{estimator}} --runs {{runs}} --jobs {{jobs}} --out analysis/results/final

# After a rebase-merge: re-point committed results and docs at main's commits (dry run; --write applies)
recite *args="":
    {{py}} python analysis/recite.py {{args}}

# Results figures (error after GPS loss, Stanford, ablation, holdover) -> analysis/results/figures-<estimator>/
figures estimator="ekf" runs="50":
    {{py}} python analysis/figures.py --estimator {{estimator}} --runs {{runs}}

# Re-run the estimator over a recorded MCAP (sim or real session)
replay path:
    {{py}} pnt replay {{path}}

# Error, Stanford, trust and clock figures for a session -> analysis/results/<session>/
plot path *args="":
    {{py}} pnt plot {{path}} {{args}}

# Replay a session on the operator panel at http://127.0.0.1:8050 (e.g. --speed 4)
dash path *args="":
    {{py}} pnt dash {{path}} {{args}}

# The judging demo, one segment at a time: check | outage | jump | time | stage | real | live
# (deploy/demo/RUNBOOK.md). The script runs without just: deploy/demo/demo.sh <segment>
demo segment="stage" *args="":
    bash deploy/demo/demo.sh {{segment}} {{args}}

# Predict protection levels along a scenario's route; --compare 50 checks it against real runs
preflight scenario *args="":
    {{py}} pnt preflight {{scenario}} {{args}}

# Write a Foxglove companion file for a session (see analysis/README.md)
viz path:
    {{py}} pnt viz {{path}}

# Subscribe to the Pi's live stream and run nav (add --dash for the operator panel)
live *args="":
    {{py}} pnt live {{args}}

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

# Copy the repo's tracked files to the Pi and run its setup (PI_HOST=pi@pnt.local).
# Only `git ls-files`: untracked PDFs and notes in the working tree never reach the Pi.
pi-deploy host="pi@pnt.local":
    #!/usr/bin/env bash
    set -euo pipefail
    stage="$(mktemp -d)"
    trap 'rm -rf "$stage"' EXIT
    # Skip tracked files deleted in the working tree here: macOS rsync has no --ignore-missing-args
    git ls-files -z | while IFS= read -r -d '' f; do if [ -e "$f" ]; then printf '%s\0' "$f"; fi; done \
      | rsync -a --from0 --files-from=- ./ "$stage/"
    git describe --always --dirty --abbrev=7 > "$stage/.pnt-commit"  # the Pi copy has no .git (REQ-10)
    rsync -az --delete --exclude .venv --exclude data/sessions "$stage/" {{host}}:~/pnt/
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
