#!/usr/bin/env bash
# The judging demo, one command per segment (#28). Runbook: deploy/demo/RUNBOOK.md.
#
#   deploy/demo/demo.sh check      pre-flight: Python, panel imports, port, scenarios, session
#   deploy/demo/demo.sh outage     panel: GPS lost (challenge-drone-outage, seed 0)
#   deploy/demo/demo.sh jump       panel: 300 m location jump without the guard (ekf), then with
#                                  it (ekf-guard, the jump ends at T+200); Enter moves on
#   deploy/demo/demo.sh guard      panel: only the second half of jump (ekf-guard)
#   deploy/demo/demo.sh towers     panel: GPS lost on today's setup (outage), then Enter: the same
#                                  loss on 13 hopped carriers with learned LTE noise (sim study)
#   deploy/demo/demo.sh time       panel: 50 ns/s time spoof (challenge-timing-time-spoof, seed 0)
#   deploy/demo/demo.sh stage      outage -> towers study -> jump (ekf) -> jump (ekf-guard) on one
#                                  port; Enter moves on. The time spoof is left out (location first)
#   deploy/demo/demo.sh real       terminal: real LTE cells heard, and the registered sites they fit
#   deploy/demo/demo.sh realcut    panel: a real GPS session replayed with GPS cut in software at
#                                  35 s (not in stage: run it after stage ends). Location hidden
#   deploy/demo/demo.sh live [..]  panel: the Pi's live stream (bonus; extra args go to pnt live)
#
# Panel segments other than realcut are simulations of committed scenarios (nothing recorded,
# nothing on the network): the same seed gives the same screen on every run. realcut replays a
# real session (git-ignored), the same on every run. Environment:
#   PNT_PY        Python to use (default: .venv/bin/python, else `uv run python`)
#   PNT_SESSIONS  real sessions folder (default: data/sessions)
#   PNT_DEMO_CUT_SESSION  the real GPS session realcut replays (default below)
#   PNT_DEMO_PORT panel port (default 8050)
#   PNT_DEMO_OPEN 1 opens the panel in the default browser when a segment starts (default 1)
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
port="${PNT_DEMO_PORT:-8050}"
sessions="${PNT_SESSIONS:-$repo/data/sessions}"
real_session="${PNT_DEMO_REAL:-20261110-1623-static-out-e5060-lte}"
# realcut (#264): a static laptop capture with GPS, barometer and IMU (no LTE), about 600 s. GPS
# is withheld from CUT_S after its first record by `analysis/real_gps_cut.py --dash-out` (the
# `outage` fault of `pnt replay --inject`, ADR-0015) into a temporary session that holds the
# origin, so it never goes under the repo; the panel runs with --hide-origin. At x3 the cut lands
# 13 s into the replay.
cut_session="${PNT_DEMO_CUT_SESSION:-20261111-0845-live-laptop-gps}"
CUT_S=35
CUT_SPEED=3
url="http://127.0.0.1:$port"
export PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}"
# Single-threaded BLAS: the panel needs one core, and other jobs share the laptop
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1

if [ -n "${PNT_PY:-}" ]; then py=("$PNT_PY")
elif [ -x "$repo/.venv/bin/python" ]; then py=("$repo/.venv/bin/python")
else py=(uv run python)
fi
pnt() { "${py[@]}" -m pnt.cli "$@"; }

# Segment -> scenario, estimator and speed (x real time); seed 0 for all. The speeds put each
# event 12-15 s after the segment starts. `jump` holds the 300 m jump to the end of the run;
# `guard` is the same jump ended at 200 s (`gps-return`), on the opt-in jump guard (ADR-0038).
# (Plain functions: macOS ships bash 3.2, which has no `declare -A`.)
SEED=0
scen() {
  case "$1" in
    outage) echo challenge-drone-outage ;;
    jump) echo challenge-drone-spoof-jump ;;
    guard) echo challenge-drone-gps-return ;;
    towers) echo challenge-drone-hop-outage ;;
    time) echo challenge-timing-time-spoof ;;
  esac
}
estimator() { case "$1" in guard) echo ekf-guard ;; towers) echo ekf-learned-noise ;; *) echo ekf ;; esac; }
speed() { case "$1" in outage|towers) echo 5 ;; *) echo 10 ;; esac; }
# `towers` is a study, not the payload: hopping (ADR-0040) and learned LTE noise (ADR-0039, opt-in)
# are not what flies today, so the panel says so under its top bar (`--banner`) for the whole run.
# It skips the pre-flight HPL line: predicting it for 13 carriers adds about 4 s to the switch.
banner() {
  case "$1" in
    towers) echo "Simulation study: 13 LTE carriers hopped, learned tower range noise (opt-in)." \
      "Our payload cannot hop yet: it listens to one carrier." ;;
  esac
}
preflight() { case "$1" in towers) echo --no-preflight ;; esac; }

port_free() { ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; }

cut_dir=""
cut_prepare() {  # write the realcut replay session into a temporary folder; sets $cut_dir
  [ -d "$sessions/$cut_session" ] || {
    echo "realcut: session $sessions/$cut_session missing: copy it from the capture laptop or set"
    echo "PNT_SESSIONS / PNT_DEMO_CUT_SESSION. Nothing started; say the fallback sentence instead."
    exit 1
  }
  cut_dir="$(mktemp -d "${TMPDIR:-/tmp}/pnt-realcut.XXXXXX")"
  "${py[@]}" "$repo/analysis/real_gps_cut.py" "$sessions/$cut_session" \
    --dash-out "$cut_dir/$cut_session-gps-cut-${CUT_S}s" --dash-cut "$CUT_S" >/dev/null \
    || { echo "realcut: could not write the replay session"; exit 1; }
}

panel() {  # start one panel segment in the background; sets $server
  local seg="$1"
  port_free || { echo "port $port is in use: stop the other panel (lsof -iTCP:$port)"; exit 1; }
  # Started directly, not through the pnt function, so $! is the server itself and kill stops it
  if [ "$seg" = realcut ]; then
    cut_prepare
    echo "== realcut: real session $cut_session, GPS cut at ${CUT_S} s, estimator ekf," \
      "x$CUT_SPEED, origin hidden  ($url)"
    "${py[@]}" -m pnt.cli dash "$cut_dir/$cut_session-gps-cut-${CUT_S}s" --estimator ekf \
      --hide-origin --speed "$CUT_SPEED" --port "$port" &
  else
    echo "== $seg: $(scen "$seg") seed $SEED, estimator $(estimator "$seg"), x$(speed "$seg")  ($url)"
    local label pre; label="$(banner "$seg")"; pre="$(preflight "$seg")"
    "${py[@]}" -m pnt.cli sim "$(scen "$seg")" --seed "$SEED" --estimator "$(estimator "$seg")" \
      --dash --speed "$(speed "$seg")" --port "$port" ${label:+--banner "$label"} ${pre:+"$pre"} &
  fi
  server=$!
  for _ in $(seq 1 60); do  # up to 15 s for the server to listen
    port_free || break
    kill -0 "$server" 2>/dev/null || { echo "panel failed to start"; exit 1; }
    sleep 0.25
  done
  if [ "${PNT_DEMO_OPEN:-1}" = 1 ] && [ "${opened:-0}" = 0 ]; then
    open "$url" 2>/dev/null || true
    opened=1
  fi
}

stop() {  # stop the running panel and wait until its port is free again; never fails
  if [ -n "${server:-}" ]; then
    kill "$server" 2>/dev/null || true
    wait "$server" 2>/dev/null || true
    for _ in $(seq 1 20); do port_free && break; sleep 0.25; done
  fi
  server=""
  if [ -n "$cut_dir" ]; then rm -rf "$cut_dir"; cut_dir=""; fi  # it holds the session origin
}
trap stop EXIT INT TERM

sequence() {  # one panel per segment named, on one port; Enter moves on, the last Enter stops
  local segs=("$@") i
  for i in "${!segs[@]}"; do
    panel "${segs[$i]}"
    if [ "$i" -lt $((${#segs[@]} - 1)) ]; then
      read -r -p "-- Enter for the next segment (the page reconnects by itself) "
    else
      read -r -p "-- Enter to stop "
    fi
    stop
  done
}

case "${1:-}" in
  check)
    fail=0
    ok() { printf '  ok    %s\n' "$1"; }
    bad() { printf '  FAIL  %s\n' "$1"; fail=1; }
    echo "pre-flight at $(git -C "$repo" describe --always --dirty --abbrev=7)"
    "${py[@]}" -c "import fastapi, uvicorn, pnt.dashboard.server" 2>/dev/null \
      && ok "python ${py[*]}: panel imports" || bad "panel imports (${py[*]}; run just setup)"
    # Without lsof, port_free is always true: every port check here and in panel() would pass
    command -v lsof >/dev/null 2>&1 && ok "lsof found" \
      || bad "lsof missing: port checks cannot see a port in use (install lsof)"
    port_free && ok "port $port free" || bad "port $port in use (lsof -iTCP:$port)"
    for seg in outage jump guard time towers; do
      "${py[@]}" -c "from pnt.sim.scenario import load; load('$(scen "$seg")')
from pnt.nav import ESTIMATORS; assert '$(estimator "$seg")' in ESTIMATORS" 2>/dev/null \
        && ok "scenario $(scen "$seg"), estimator $(estimator "$seg")" \
        || bad "scenario $(scen "$seg") or estimator $(estimator "$seg")"
    done
    [ -d "$sessions/$real_session" ] && ok "real session $real_session" \
      || bad "real session $sessions/$real_session missing (copy it from the capture laptop)"
    [ -f "$sessions/$cut_session/session.mcap" ] && ok "realcut session $cut_session" \
      || bad "realcut session $sessions/$cut_session missing (only demo.sh realcut needs it)"
    [ "$fail" = 0 ] && echo "pre-flight passed" || { echo "pre-flight FAILED"; exit 1; }
    ;;
  outage|guard|time|realcut)
    panel "$1"
    echo "Ctrl-C to stop"
    wait "$server"
    ;;
  jump)
    sequence jump guard
    ;;
  towers)
    sequence outage towers
    ;;
  stage)
    sequence outage towers jump guard
    ;;
  real)
    "${py[@]}" "$repo/deploy/demo/cells.py" "$sessions/$real_session"
    ;;
  live)
    shift
    port_free || { echo "port $port is in use"; exit 1; }
    pnt live --dash --estimator ekf --port "$port" "$@"
    ;;
  *)
    sed -n '2,15p' "$0"
    exit 2
    ;;
esac
