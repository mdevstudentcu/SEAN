# Board rehearsal

Run this on each board we might fly (Pi 4B, Pi 3B+), with both radios at full rate. The results replace the `TBC` capture profiles in `src/pnt/sim/scenarios/sets/_attacks.yaml` (ADR-0015).

Both radios at full rate means 2 × 2.4 MS/s × 2 bytes = 9.6 MB/s to the SD card. Whether a board keeps up is what this measures. On the Pi 3B+, the USB ports and Ethernet share one USB 2 connection.

## Before you start

- `deploy/pi/check_install.sh` passes on a laptop with Docker.
- `deploy/pi/setup.sh` has run on the board and `ppstest /dev/pps0` shows 1 Hz (#17).
- Both radios are plugged in, and the board has a heat sink and its normal power supply.

## Measure

| What | How | Record in the capture profile |
| --- | --- | --- |
| Dropped samples, each radio alone | `rtl_test -s 2400000 -d 0`, 10 minutes, then `-d 1`. Count "lost at least" lines | Baseline for `gaps_per_min` |
| Dropped samples, both radios | Both `rtl_test` commands at once, 10 minutes | `gaps_per_min`, `gap_s` |
| SD card keeps up | Both radios to disk with `rtl_sdr` for 10 minutes while watching `iostat 5` | Whether full rate is sustainable |
| Timing pulse | `sudo ppstest /dev/pps0`, and `chronyc sources -v` offset over 10 minutes | Note in ASM-04 (RSK-05) |
| Radio timestamp jitter | Repeat the recorder start 20 times against PPS once #19 exists | `timestamp_jitter_ms` |
| Stream loss | Stream over Wi-Fi for 10 minutes and compare counts with the on-board log, once #19 exists | `stream_loss` |
| Temperature and throttling | `vcgencmd measure_temp` and `vcgencmd get_throttled` during all of the above | Note in the PR |

## Afterwards

1. Update that board's profile, and name the session and date in a comment.
2. Change the matching row of *Sim validity* in `systems/verification.md`.
3. If both radios don't fit at full rate, record it and decide between one radio and a lower sample rate.
