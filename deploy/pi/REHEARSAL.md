# Board rehearsal: capture faults (#53)

How to measure the Pi 4B's capture profile (ADR-0018) with both radios at their planned sample rates. The results replace the `TBC` values of `capture-pi4b` in `src/pnt/sim/scenarios/sets/_attacks.yaml` (ADR-0015).

The rehearsal is the day-1 test ([`RUNBOOK.md`](RUNBOOK.md) B, `day1.sh`): it records both SDRs (A at 1.92 MS/s, B at 2.4 MS/s) with GPS, IMU, barometer and the stream, and `pnt day1` turns the session into numbers. This file says which of those numbers go into the profile, and adds the stream-loss check.

## Before you start

- `deploy/pi/setup.sh` has run on the board and `sudo ppstest /dev/pps0` shows one line per second (#17).
- Both SDRs are on the USB 2 ports, and the board has its heat sink and its normal 5 V 3 A supply.
- The laptop can receive the stream ([`RUNBOOK.md`](RUNBOOK.md) *Keys*).

## Measure

1. On the laptop, record the stream for the whole test: `pnt live --connect <pi endpoint> --out data/sessions/<date>-rehearsal-laptop`.
2. On the Pi: `bash deploy/pi/day1.sh 10` (10 min).
3. On the laptop, with the Pi session copied over: `pnt day1 data/sessions/<date>-static-day1`.

| Profile value | From | How |
| --- | --- | --- |
| `gaps_per_min` | `pnt day1`: *sdr_a / sdr_b gaps*, and the duration in its JSON | Gaps per minute, both radios together |
| `gap_s` | `pnt day1` JSON: `dropped_samples_est` / `gaps` / `rate_hz`, per SDR | Mean gap length in seconds |
| `timestamp_jitter_ms` | `pnt day1`: *sdr latency p99 / max* | Host arrival jitter above the timing envelope. Whether this is the record-timestamp error the profile means is `TBD`: the LTE front end stamps records from sample counts |
| `stream_loss` | Record counts on `/meas/*`: the laptop's session against the Pi's | 1 - laptop / Pi, over the same span |

Also note, for the PR: *Throttled flags*, *Max SoC temperature*, *Records dropped (queue)* and the PPS rows of `pnt day1` (RSK-05, RSK-06).

## Afterwards

1. Update `capture-pi4b` with the measured values, and name the sessions and the commit in a comment.
2. Move the *Board capture* row of *Sim validity* in `systems/verification.md` to `measured`.
3. If both radios don't fit at the planned rates (gaps, or *Records dropped* above zero), record it in #53 and decide between one radio and a lower sample rate (`systems/sim-plan.md`, D6).
