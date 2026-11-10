#!/usr/bin/env bash
# RF survey at one site (#20): which signals of opportunity are on air here. Receive-only.
# Run on the Pi from ~/pnt, antenna attached, the SDR not used by anything else:
#   [DEV=0] [SWEEP_S=600] [LTE_N=4] [LTE_S=10] [ADSB_S=60] [GAIN=] bash deploy/pi/rf_survey.sh <site>
# Writes data/sessions/<date>-survey-<site>/:
#   power.csv     rtl_power sweep 24-1766 MHz (power only, nothing demodulated: ADR-0011)
#   lte-<earfcn>/ short captures of the top LTE_N EARFCNs in the scan list (#87), for
#                 `pnt frontend lte` on the laptop
#   adsb/         ADS-B capture at 1090 MHz, for the ADS-B front end (#22)
# Then on the laptop: python analysis/rf_survey.py <site>=data/sessions/<...>/power.csv
set -euo pipefail
cd "$(dirname "$0")/../.."
SITE="${1:?usage: rf_survey.sh <site>}"
DEV="${DEV:-0}"
SWEEP_S="${SWEEP_S:-600}"   # TBC: long enough for several passes
LTE_N="${LTE_N:-4}"
LTE_S="${LTE_S:-10}"
ADSB_S="${ADSB_S:-60}"
PNT=.venv/bin/pnt
out="data/sessions/$(date +%Y%m%d-%H%M)-survey-$SITE"
mkdir -p "$out"
REC=(--platform static --place "$SITE" --no-imu --no-baro --no-camera --no-fc --no-stream)

echo "== Sweep 24-1766 MHz for $SWEEP_S s (100 kHz bins, 30 s per pass) =="
# -g empty: the tuner's automatic gain. The dB are relative to full scale, not dBm.
rtl_power -d "$DEV" -f 24M:1766M:100k -i 30 -e "${SWEEP_S}s" ${GAIN:+-g "$GAIN"} "$out/power.csv"

echo "== LTE: $LTE_S s on each of the top $LTE_N EARFCNs =="
tail -n +2 data/reference/lte-scan-list-ottawa.csv | head -n "$LTE_N" | while IFS=, read -r earfcn _band dl _rest; do
  $PNT record --out "$out/lte-$earfcn" --duration "$LTE_S" \
    --sdr "a:${dl}e6:rate=1.92e6:dev=$DEV:earfcn=$earfcn" "${REC[@]}" --notes "RF survey $SITE"
done

echo "== ADS-B: $ADSB_S s at 1090 MHz =="
$PNT record --out "$out/adsb" --duration "$ADSB_S" --sdr "a:1090e6:rate=2.4e6:dev=$DEV" "${REC[@]}" \
  --notes "RF survey $SITE"

echo "Done: $out. Copy data/sessions/ to the laptop (never to git), then:"
echo "  python analysis/rf_survey.py $SITE=$out/power.csv"
echo "  pnt frontend lte $out/lte-<earfcn>/sdr_a.cu8   (per EARFCN; prints the cells it found)"
