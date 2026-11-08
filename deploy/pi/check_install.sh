#!/usr/bin/env bash
# Install the payload software in a 64-bit ARM container, the architecture of both the Pi 4B and
# the Pi 3B+. Catches missing packages and install problems, not hardware problems: use
# REHEARSAL.md for those. Needs Docker. Run from anywhere in the repo.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

git archive HEAD | docker run --rm -i --platform linux/arm64 python:3.11-bookworm bash -c '
  set -euo pipefail
  mkdir /pnt && tar -x -C /pnt && cd /pnt
  python -m venv .venv
  .venv/bin/pip install -q -e ".[payload]"
  .venv/bin/python -c "import pnt.core.measurement, pnt.io.mcap_log, pnt.payload, zmq, serial"
  echo "payload install OK on $(uname -m), $(.venv/bin/python --version)"
'
