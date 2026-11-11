# Slow GNSS drag with carrier hopping: the tower monitor against masts heard (#221)

Sim, study leg (ADR-0040: the payload cannot hop yet), every value `TBC`. Commit 9e784ed, `python analysis/drag_with_hopping.py --seeds 50 --jobs 6`, 296.5 min on Darwin, arm, Python 3.14.6. Seeds 0–49, paired; the monitor's settings are as committed (ADR-0037, chosen on seeds 100–109), not re-tuned.

Entries `spoof-ramp` (2 m/s at 45°, from 150 s), `nominal` and `outage` of `challenge-drone` (1 carrier, EARFCN 2460) and `challenge-drone-hop` (the first 6 carriers of its hop set, and all 13), as committed; `-spoof` is the same filter with the opt-in tower monitor. Detection and false alarms are `pnt.metrics` (`analysis/spoof_detection.py`'s rows). Masts: distinct masts heard per 10 s after the cell lookup, median over seeds of each run's median.

- **#221's criterion (`ekf-spoof` flags the ramp on >= 45 of 50 seeds on the 13-carrier leg, 0 added false alarms): not met.** 0 of 50 seeds, 0 added false alarms on `nominal`/`outage`.
- Time to alert against T4's 30 s (`TBC`), 13 carriers, `ekf-spoof`: median – s, worst – s.
- **Under 25 of 50: hopping does not rescue the monitor as committed.** Its tower tests had an opinion on 30/10 s: 0 %, 120/20 s: 0 % of the seconds (median over ramp runs). `spoof_monitor.towers_test` keeps a site only if it is heard on at least half of each window's record epochs. Hopping puts one carrier on air per epoch, so a site is heard on the epochs its own carriers are dwelled on, which is under half of a window when it is on few of the carriers hopped; with fewer than `min_sites` (5) sites kept the monitor has no opinion. More masts are heard, fewer are kept (seen on tuning seed 100, not a reporting seed).

| Carriers | Masts per 10 s | Estimator | Ramp detected | TTA median (s) | TTA worst (s) | Error at alert (m) | Hazardous epochs on the ramp, mean (seeds) | False alarms / h, nominal (seeds) | False alarms / h, outage (seeds) | Added false alarms vs. unchanged | Monitor has an opinion (ramp, median share of s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2.0 | `ekf` | 0/50 | – | – | – | 5,449 (50) | 0.00 (0) | 4.10 (39) | – | – |
| 1 | 2.0 | `ekf-spoof` | 1/50 | 374 | 374 | 750 | 5,442 (50) | 0.00 (0) | 4.10 (39) | 0 | 30/10 s: 0 %, 120/20 s: 0 % |
| 1 | 2.0 | `ekf-calibrated` | 0/50 | – | – | – | 5,449 (50) | 0.00 (0) | 3.90 (39) | – | – |
| 1 | 2.0 | `ekf-calibrated-spoof` | 1/50 | 374 | 374 | 750 | 5,442 (50) | 0.00 (0) | 3.90 (39) | 0 | 30/10 s: 0 %, 120/20 s: 0 % |
| 6 | 8.0 | `ekf` | 0/50 | – | – | – | 5,449 (50) | 0.00 (0) | 3.70 (37) | – | – |
| 6 | 8.0 | `ekf-spoof` | 1/50 | 144 | 144 | 286 | 5,364 (50) | 0.00 (0) | 3.70 (37) | 0 | 30/10 s: 0 %, 120/20 s: 0 % |
| 6 | 8.0 | `ekf-calibrated` | 0/50 | – | – | – | 5,449 (50) | 0.00 (0) | 3.80 (37) | – | – |
| 6 | 8.0 | `ekf-calibrated-spoof` | 1/50 | 144 | 144 | 286 | 5,365 (50) | 0.00 (0) | 3.80 (37) | 0 | 30/10 s: 0 %, 120/20 s: 0 % |
| 13 | 26.0 | `ekf` | 0/50 | – | – | – | 5,449 (50) | 0.00 (0) | 3.60 (36) | – | – |
| 13 | 26.0 | `ekf-spoof` | 0/50 | – | – | – | 5,449 (50) | 0.00 (0) | 3.60 (36) | 0 | 30/10 s: 0 %, 120/20 s: 0 % |
| 13 | 26.0 | `ekf-calibrated` | 1/50 | 148 | 148 | 294 | 5,365 (50) | 0.00 (0) | 3.90 (38) | – | – |
| 13 | 26.0 | `ekf-calibrated-spoof` | 1/50 | 148 | 148 | 294 | 5,365 (50) | 0.00 (0) | 3.90 (38) | 0 | 30/10 s: 0 %, 120/20 s: 0 % |

TTA: time to alert from the ramp's start, detected seeds only. Error at alert: horizontal error at the alert, median over detected seeds. Hazardous: epochs whose error exceeds the alert limit (`pnt.metrics`). Added false alarms: (entry, seed) pairs where `-spoof` has more false alarms than the unchanged filter on the same seed. Opinion: share of seconds a tower test (lag/window) had at least `min_sites` sites kept (`spoof_detection.py`'s per-run share), median over the ramp runs.
