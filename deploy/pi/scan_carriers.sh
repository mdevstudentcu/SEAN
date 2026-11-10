#!/usr/bin/env bash
# Carrier scan (#173 part 2): one short capture per EARFCN of the scan list, on one dongle.
# Run on the Pi from ~/pnt. Receive-only: nothing here transmits (REQ-07).
#
#   bash deploy/pi/scan_carriers.sh [--seconds N] [--place NAME] [--only 2460,5145] [--dev N]
#                                   [--gain DB] [--include-flagged] [--notes TEXT] [--dry-run]
#
# Carriers: data/reference/lte-scan-list-ottawa.csv in its order (sites within 3 km first), each
# EARFCN once (a row repeated for a second licensee is skipped). Rows with `flags` (tx_rx_swapped,
# off_raster, nonstandard_bw) are left out unless --include-flagged, which adds them after all
# unflagged ones: a capture is how a flagged row gets confirmed (#173).
# Each capture is what first-capture.md step 1 records (GNSS, IMU, baro, one SDR, no stream,
# camera or FC), into data/sessions/<YYYYmmdd-HHMM>-static-<place>-e<EARFCN>/. The free space is
# checked before each one. Ctrl-C ends the capture in progress cleanly (pnt record finishes its
# files) and starts no more. --dry-run prints the commands and records nothing.
set -euo pipefail
cd "$(dirname "$0")/../.."

SECS=60 # TBC: long enough to count cells per carrier; 120 s is the checklist's short check
PLACE=carleton
ONLY=""
DEV=0
GAIN=""
RATE=1.92e6 # pnt.payload.config default; the front end needs a multiple of 15 kHz
FLAGGED=0
DRY=0
NOTES=""
LIST=data/reference/lte-scan-list-ottawa.csv
PNT=.venv/bin/pnt
MARGIN_MB=500 # TBC: kept free beyond the IQ, for the MCAP and the system

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --seconds) SECS="$2"; shift 2 ;;
    --place) PLACE="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --dev) DEV="$2"; shift 2 ;;
    --gain) GAIN="$2"; shift 2 ;;
    --include-flagged) FLAGGED=1; shift ;;
    --notes) NOTES="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$SECS" in '' | *[!0-9]*) echo "--seconds must be a whole number: $SECS" >&2; exit 2 ;; esac
case "$PLACE" in '' | *[!A-Za-z0-9_-]*) echo "--place: letters, digits, - or _: $PLACE" >&2; exit 2 ;; esac
[ -f "$LIST" ] || { echo "missing $LIST (deploy from the repo: just pi-deploy)" >&2; exit 1; }

# earfcn dl_mhz flags, unflagged rows first, each EARFCN once (the CSV has CRLF line ends)
carriers=$(
  {
    awk -F, '{ sub(/\r$/, "") } NR > 1 && $10 == "" { print $1, $3, "-" }' "$LIST"
    if [ "$FLAGGED" = 1 ]; then
      awk -F, '{ sub(/\r$/, "") } NR > 1 && $10 != "" { print $1, $3, $10 }' "$LIST"
    fi
  } | awk '!seen[$1]++'
)
if [ -n "$ONLY" ]; then
  carriers=$(echo "$carriers" | awk -v only=",$ONLY," 'index(only, "," $1 ",")')
fi
[ -n "$carriers" ] || { echo "no carriers to scan" >&2; exit 1; }

stamp=$(date +%Y%m%d-%H%M)
need_mb=$(awk -v s="$SECS" -v r="$RATE" -v m="$MARGIN_MB" 'BEGIN { printf "%d", s * r * 2 / 1e6 + m }')
n=$(echo "$carriers" | wc -l | tr -d ' ')
echo "== Carrier scan $stamp: $n carrier(s), ${SECS} s each, dongle dev=$DEV, gain ${GAIN:-auto}"
echo "   each needs ${need_mb} MB free (IQ at $RATE S/s, 2 bytes per sample, + ${MARGIN_MB} MB)"

STOP=0
trap 'STOP=1' INT TERM HUP
made=()
failed=""
while read -r earfcn mhz flags; do
  [ "$STOP" = 1 ] && break
  out="data/sessions/${stamp}-static-${PLACE}-e${earfcn}"
  if [ -e "$out" ]; then
    echo "$out exists already; not overwriting it (wait a minute or change --place)" >&2
    failed="$earfcn"; break
  fi
  free_mb=$(df -Pk "$(test -d data/sessions && echo data/sessions || echo .)" | awk 'NR == 2 { printf "%d", $4 / 1024 }')
  if [ "$free_mb" -lt "$need_mb" ]; then
    echo "only ${free_mb} MB free, ${need_mb} MB needed for EARFCN $earfcn: stopping (copy off first)" >&2
    [ "$DRY" = 1 ] || { failed="$earfcn"; break; }
  fi
  sdr="a:${mhz}e6:rate=${RATE}:dev=${DEV}${GAIN:+:gain=$GAIN}:earfcn=${earfcn}"
  note="#173 carrier scan $stamp, EARFCN $earfcn ($mhz MHz, flags $flags), ${SECS} s${NOTES:+, $NOTES}"
  cmd=("$PNT" record --out "$out" --platform static --place "${PLACE}-e${earfcn}"
    --duration "$SECS" --no-stream --no-camera --no-fc --sdr "$sdr" --notes "$note")
  echo "-- EARFCN $earfcn, $mhz MHz (flags $flags), ${free_mb} MB free"
  if [ "$DRY" = 1 ]; then
    printf '+'; printf ' %q' "${cmd[@]}"; printf '\n'
    made+=("$out")
    continue
  fi
  mkdir -p data/sessions
  rc=0
  "${cmd[@]}" </dev/null || rc=$? # stdin from /dev/null: the carrier list is on this loop's stdin
  if [ "$rc" = 0 ]; then
    made+=("$out")
  else
    echo "pnt record failed for EARFCN $earfcn (exit $rc)" >&2
    [ -d "$out" ] && made+=("$out (incomplete)")
    failed="$earfcn"; break
  fi
done <<<"$carriers"

echo
echo "== Sessions $([ "$DRY" = 1 ] && echo 'that would be made' || echo made): ${#made[@]} of $n"
for s in ${made[@]+"${made[@]}"}; do echo "   $s"; done
[ "$STOP" = 1 ] && echo "   stopped by signal; later carriers not recorded"
[ -n "$failed" ] && echo "   stopped at EARFCN $failed"
if [ ${#made[@]} -gt 0 ]; then
  echo "Laptop, after: rsync -av pi@pnt.local:~/pnt/data/sessions/ data/sessions/"
  echo "  for s in data/sessions/${stamp}-static-${PLACE}-e*/; do pnt frontend lte \"\$s/sdr_a.cu8\"; done"
  echo "  python analysis/lte_capture_report.py data/sessions/${stamp}-static-${PLACE}-e*-lte --out data/sessions/${stamp}-scan-report"
  echo "  (a carrier with no cell found writes no -lte folder: the front end says so)"
fi
[ -z "$failed" ] && [ "$STOP" = 0 ]
