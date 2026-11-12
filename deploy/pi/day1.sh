#!/usr/bin/env bash
# Day-1 test of the Pi 4B payload (#88, ADR-0018) with the PPS check (#17, RSK-05).
# Run on the Pi from ~/pnt:  [DEV_A=0 DEV_B=1] bash deploy/pi/day1.sh [minutes] [sdr_a_hz] [sdr_b_hz]
# DEV_A/DEV_B: rtl_sdr device index or serial of each dongle (see `rtl_test -t`). Indices swap
# between boots, the serial (`SN:`) does not; a dongle that drops off USB mid-recording is
# reopened by its serial if no other dongle shares it (#288).
# The stream needs the keys from RUNBOOK "Keys"; RECORD_ARGS=--insecure only if libzmq lacks CURVE.
# Writes, under data/sessions/: the session, <session>.pps.json, <session>.day1.md and .json.
set -euo pipefail
cd "$(dirname "$0")/../.."
MIN="${1:-10}"
FA="${2:-875e6}"     # SDR A: LTE, Rogers EARFCN 2460 (top of the #87 scan list)
EARFCN_A="${EARFCN_A-2460}"  # written to the sidecar; set empty if FA is not 875 MHz
FB="${3:-1090e6}"    # SDR B: ADS-B, at 2.4 MS/s, the worst case for USB and CPU
PNT=.venv/bin/pnt
name="$(date +%Y%m%d-%H%M)-static-day1"
out="data/sessions/$name"
mkdir -p data/sessions

echo "== PPS check (30 s) =="
$PNT pps-check --seconds 30 --out "$out.pps.json"

echo "== Recording $MIN min: both SDRs, GPS, IMU, baro, camera, streaming =="
echo "   While it runs, read the USB current off the DPS-150."
$PNT record --out "$out" --platform static --duration "$((MIN * 60))" \
  --sdr "a:$FA:rate=1.92e6:dev=${DEV_A:-0}${EARFCN_A:+:earfcn=$EARFCN_A}" --sdr "b:$FB:rate=2.4e6:dev=${DEV_B:-1}" \
  ${RECORD_ARGS:-}

read -r -p "USB current from the DPS-150, amps (blank if not read): " AMPS
$PNT day1 "$out" ${AMPS:+--usb-current-a "$AMPS"}
echo "Report: $out.day1.md (session $name). Copy data/sessions/ to the laptop; never to git."
