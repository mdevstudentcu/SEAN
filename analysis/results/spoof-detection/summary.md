# Spoof detection, before and after the tower monitor (#173)

Sim, every value `TBC`. Commit 220a6fa, `python analysis/spoof_detection.py --seeds 50 --mhss-seeds 5 --jobs 2`, 143.1 min. Seeds 0–49 (`ekf-mhss` 0–4); the monitor's settings were chosen on seeds 100–109, never on these.

`-spoof` = the same estimator with `integrity.spoof_monitor` (opt-in). `drone` is the `challenge-drone` leg as committed (1 to 3 cells heard); `drone-many` the same spec with every sector within 3 km heard; `realistic` the `realistic` set. Detection is `pnt.metrics` (any of `gnss_excluded`, `spoof_suspected`, `time_spoof_suspected` held 1 s); false alarms per hour are on `nominal` and `outage` runs.

## Detection per attack

| Leg | Attack | Estimator | Detected | TTA median (s) | TTA worst (s) | Error at alert (m) | Hazardous epochs (mean) |
|---|---|---|---|---|---|---|---|
| drone | spoof-ramp | `ekf` | 0/50 | – | – | – | 5,449 |
| drone | spoof-ramp | `ekf-spoof` | 1/50 | 374.0 | 374.0 | 750 | 5,442 |
| drone | spoof-ramp | `ekf-calibrated` | 0/50 | – | – | – | 5,449 |
| drone | spoof-ramp | `ekf-calibrated-spoof` | 1/50 | 374.0 | 374.0 | 750 | 5,442 |
| drone | spoof-ramp | `ekf-mhss` | 0/5 | – | – | – | 0 |
| drone | spoof-jump | `ekf` | 50/50 | 1.1 | 1.1 | 3 | 5,244 |
| drone | spoof-jump | `ekf-spoof` | 50/50 | 1.1 | 1.1 | 3 | 5,244 |
| drone | spoof-jump | `ekf-calibrated` | 50/50 | 1.1 | 1.1 | 3 | 4,939 |
| drone | spoof-jump | `ekf-calibrated-spoof` | 50/50 | 1.1 | 1.1 | 3 | 4,939 |
| drone | spoof-jump | `ekf-mhss` | 5/5 | 1.1 | 1.1 | 4 | 0 |
| drone | time-spoof | `ekf` | 50/50 | 3.3 | 4.1 | 1 | 0 |
| drone | time-spoof | `ekf-spoof` | 50/50 | 3.3 | 4.1 | 1 | 0 |
| drone | time-spoof | `ekf-calibrated` | 50/50 | 2.9 | 3.9 | 1 | 0 |
| drone | time-spoof | `ekf-calibrated-spoof` | 50/50 | 2.9 | 3.9 | 1 | 0 |
| drone | time-spoof | `ekf-mhss` | 5/5 | 3.3 | 3.9 | 2 | 0 |
| drone-many | spoof-ramp | `ekf` | 0/50 | – | – | – | 5,233 |
| drone-many | spoof-ramp | `ekf-spoof` | 48/50 | 131.0 | 313.0 | 261 | 3,748 |
| drone-many | spoof-ramp | `ekf-calibrated` | 0/50 | – | – | – | 5,345 |
| drone-many | spoof-ramp | `ekf-calibrated-spoof` | 49/50 | 133.0 | 313.0 | 266 | 3,776 |
| drone-many | spoof-ramp | `ekf-mhss` | 1/5 | 81.1 | 81.1 | 260 | 0 |
| drone-many | spoof-jump | `ekf` | 48/50 | 1.1 | 1.1 | 3 | 4,848 |
| drone-many | spoof-jump | `ekf-spoof` | 48/50 | 1.1 | 1.1 | 3 | 3,383 |
| drone-many | spoof-jump | `ekf-calibrated` | 50/50 | 1.1 | 533.5 | 3 | 4,547 |
| drone-many | spoof-jump | `ekf-calibrated-spoof` | 49/50 | 1.1 | 1.1 | 3 | 3,312 |
| drone-many | spoof-jump | `ekf-mhss` | 5/5 | 1.1 | 1.1 | 1 | 0 |
| drone-many | time-spoof | `ekf` | 48/50 | 3.3 | 4.1 | 1 | 2 |
| drone-many | time-spoof | `ekf-spoof` | 48/50 | 3.3 | 4.1 | 1 | 2 |
| drone-many | time-spoof | `ekf-calibrated` | 49/50 | 2.9 | 3.9 | 1 | 1 |
| drone-many | time-spoof | `ekf-calibrated-spoof` | 49/50 | 2.9 | 3.9 | 1 | 1 |
| drone-many | time-spoof | `ekf-mhss` | 5/5 | 3.3 | 3.9 | 1 | 0 |
| realistic | spoof-ramp | `ekf` | 0/50 | – | – | – | 1,847 |
| realistic | spoof-ramp | `ekf-spoof` | 0/50 | – | – | – | 1,847 |
| realistic | spoof-ramp | `ekf-calibrated` | 0/50 | – | – | – | 1,847 |
| realistic | spoof-ramp | `ekf-calibrated-spoof` | 0/50 | – | – | – | 1,847 |
| realistic | spoof-ramp | `ekf-mhss` | 0/5 | – | – | – | 0 |
| realistic | spoof-jump | `ekf` | 50/50 | 1.1 | 1.1 | 2 | 1,581 |
| realistic | spoof-jump | `ekf-spoof` | 50/50 | 1.1 | 1.1 | 2 | 1,581 |
| realistic | spoof-jump | `ekf-calibrated` | 50/50 | 1.1 | 1.1 | 2 | 1,483 |
| realistic | spoof-jump | `ekf-calibrated-spoof` | 50/50 | 1.1 | 1.1 | 2 | 1,483 |
| realistic | spoof-jump | `ekf-mhss` | 5/5 | 1.1 | 1.1 | 3 | 0 |
| realistic | time-spoof | `ekf` | 50/50 | 3.3 | 4.3 | 2 | 0 |
| realistic | time-spoof | `ekf-spoof` | 50/50 | 3.3 | 4.3 | 2 | 0 |
| realistic | time-spoof | `ekf-calibrated` | 50/50 | 3.1 | 3.7 | 2 | 0 |
| realistic | time-spoof | `ekf-calibrated-spoof` | 50/50 | 3.1 | 3.7 | 2 | 0 |
| realistic | time-spoof | `ekf-mhss` | 5/5 | 2.9 | 3.3 | 1 | 0 |

## False alarms (an outage must not look like a spoof)

| Leg | Entry | Estimator | False alarms / h (mean) | Seeds with one |
|---|---|---|---|---|
| drone | nominal | `ekf` | 0.00 | 0/50 |
| drone | nominal | `ekf-spoof` | 0.00 | 0/50 |
| drone | nominal | `ekf-calibrated` | 0.00 | 0/50 |
| drone | nominal | `ekf-calibrated-spoof` | 0.00 | 0/50 |
| drone | nominal | `ekf-mhss` | 0.00 | 0/5 |
| drone | outage | `ekf` | 4.10 | 39/50 |
| drone | outage | `ekf-spoof` | 4.10 | 39/50 |
| drone | outage | `ekf-calibrated` | 3.90 | 39/50 |
| drone | outage | `ekf-calibrated-spoof` | 3.90 | 39/50 |
| drone | outage | `ekf-mhss` | 2.00 | 2/5 (1, 2) |
| drone-many | nominal | `ekf` | 0.20 | 2/50 (36, 39) |
| drone-many | nominal | `ekf-spoof` | 0.20 | 2/50 (36, 39) |
| drone-many | nominal | `ekf-calibrated` | 0.20 | 1/50 (36) |
| drone-many | nominal | `ekf-calibrated-spoof` | 0.20 | 1/50 (36) |
| drone-many | nominal | `ekf-mhss` | 14.00 | 4/5 (0, 2, 3, 4) |
| drone-many | outage | `ekf` | 2.60 | 26/50 |
| drone-many | outage | `ekf-spoof` | 2.60 | 26/50 |
| drone-many | outage | `ekf-calibrated` | 2.70 | 26/50 |
| drone-many | outage | `ekf-calibrated-spoof` | 2.70 | 26/50 |
| drone-many | outage | `ekf-mhss` | 7.00 | 4/5 (0, 2, 3, 4) |
| realistic | nominal | `ekf` | 0.00 | 0/50 |
| realistic | nominal | `ekf-spoof` | 0.00 | 0/50 |
| realistic | nominal | `ekf-calibrated` | 0.00 | 0/50 |
| realistic | nominal | `ekf-calibrated-spoof` | 0.00 | 0/50 |
| realistic | nominal | `ekf-mhss` | 0.00 | 0/5 |
| realistic | outage | `ekf` | 10.01 | 50/50 |
| realistic | outage | `ekf-spoof` | 10.01 | 50/50 |
| realistic | outage | `ekf-calibrated` | 0.00 | 0/50 |
| realistic | outage | `ekf-calibrated-spoof` | 0.00 | 0/50 |
| realistic | outage | `ekf-mhss` | 10.01 | 5/5 (0, 1, 2, 3, 4) |

## Jumps: what happens in the first seconds, and after

Medians over seeds. Follows: error 30 s after the jump over half its size. GNSS excluded: share of the first 30 s with `gnss_excluded`.

| Leg | Jump (m) | Estimator | Detected | TTA median / worst (s) | Error, HPL at +1 s (m) | Error, HPL at +3 s (m) | GNSS excluded, first 30 s | Follows | Error at +30 s / +120 s (m) |
|---|---|---|---|---|---|---|---|---|---|
| drone | 25 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 7, 31 | 0.13 | 50/50 | 25 / 25 |
| drone | 25 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 7, 31 | 0.13 | 50/50 | 25 / 25 |
| drone | 50 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.24 | 50/50 | 50 / 50 |
| drone | 50 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.24 | 50/50 | 50 / 50 |
| drone | 100 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.41 | 50/50 | 100 / 100 |
| drone | 100 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.41 | 50/50 | 100 / 100 |
| drone | 300 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.91 | 49/50 | 302 / 300 |
| drone | 300 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.91 | 49/50 | 302 / 300 |
| drone | 300 | `ekf-calibrated` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.91 | 46/50 | 301 / 300 |
| drone | 300 | `ekf-calibrated-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.91 | 46/50 | 301 / 300 |
| drone | 300 | `ekf-mhss` | 5/5 | 1.1 / 1.1 | 3, 969 | 7, 1,046 | 0.89 | 5/5 | 301 / 300 |
| drone-many | 25 | `ekf` | 48/50 | 1.1 / 1.1 | 3, 13 | 7, 31 | 0.13 | 50/50 | 25 / 25 |
| drone-many | 25 | `ekf-spoof` | 48/50 | 1.1 / 1.1 | 3, 13 | 7, 31 | 0.13 | 50/50 | 25 / 25 |
| drone-many | 50 | `ekf` | 48/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.24 | 50/50 | 50 / 50 |
| drone-many | 50 | `ekf-spoof` | 48/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.24 | 50/50 | 50 / 50 |
| drone-many | 100 | `ekf` | 48/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.41 | 49/50 | 100 / 100 |
| drone-many | 100 | `ekf-spoof` | 48/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.41 | 49/50 | 100 / 100 |
| drone-many | 300 | `ekf` | 48/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.91 | 48/50 | 302 / 300 |
| drone-many | 300 | `ekf-spoof` | 48/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 1.00 | 9/50 | 115 / 301 |
| drone-many | 300 | `ekf-calibrated` | 50/50 | 1.1 / 533.5 | 3, 13 | 6, 31 | 0.92 | 45/50 | 302 / 300 |
| drone-many | 300 | `ekf-calibrated-spoof` | 49/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 1.00 | 7/50 | 113 / 301 |
| drone-many | 300 | `ekf-mhss` | 5/5 | 1.1 / 1.1 | 1, 1,645 | 7, 1,737 | 0.88 | 4/5 | 299 / 300 |
| timing | 25 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.11 | 50/50 | 25 / 25 |
| timing | 25 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 6, 31 | 0.11 | 50/50 | 25 / 25 |
| timing | 50 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 4, 31 | 0.22 | 50/50 | 50 / 50 |
| timing | 50 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 4, 31 | 0.22 | 50/50 | 50 / 50 |
| timing | 100 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 4, 31 | 0.37 | 50/50 | 100 / 100 |
| timing | 100 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 4, 31 | 0.37 | 50/50 | 100 / 100 |
| timing | 300 | `ekf` | 50/50 | 1.1 / 1.1 | 3, 13 | 4, 31 | 0.82 | 49/50 | 300 / 300 |
| timing | 300 | `ekf-spoof` | 50/50 | 1.1 / 1.1 | 3, 13 | 4, 31 | 0.82 | 49/50 | 300 / 300 |
| timing | 300 | `ekf-mhss` | 5/5 | 1.1 / 1.1 | 3, 491 | 5, 536 | 0.79 | 5/5 | 299 / 300 |

### Smallest jump detected on every seed

Of the sizes tried (25, 50, 100, 300 m). Detected by the filter's own GNSS gate or by the monitor; whether the output then follows the jump is in the table above. In brackets, the sizes run for that estimator. A seed whose filter raised a false alarm before the spoof starts and still holds it is scored as missed by `pnt.metrics` (an alarm already running is not a response).

| Leg | `ekf` | `ekf-spoof` | `ekf-calibrated` | `ekf-calibrated-spoof` | `ekf-mhss` |
|---|---|---|---|---|---|
| drone | 25 (25, 50, 100, 300) | 25 (25, 50, 100, 300) | 300 (300) | 300 (300) | 300 (300) |
| drone-many | none (25, 50, 100, 300) | none (25, 50, 100, 300) | 300 (300) | none (300) | 300 (300) |
| timing | 25 (25, 50, 100, 300) | 25 (25, 50, 100, 300) | not run | not run | 300 (300) |

## Recovery: the 300 m jump ended at 300 s

| Leg | Estimator | Error at end +30 s / +120 s (m, median) | Share of epochs alarmed from 120 s after the end (median) |
|---|---|---|---|
| drone | `ekf` | 167 / 2 | 0.00 |
| drone | `ekf-spoof` | 167 / 2 | 0.00 |
| drone | `ekf-calibrated` | 181 / 2 | 0.00 |
| drone | `ekf-mhss` | 3 / 1 | 0.00 |
| drone-many | `ekf` | 169 / 1 | 0.00 |
| drone-many | `ekf-spoof` | 178 / 2 | 0.00 |
| drone-many | `ekf-calibrated` | 185 / 2 | 0.00 |
| drone-many | `ekf-mhss` | 3 / 2 | 0.00 |
| timing | `ekf` | 2 / 1 | 0.00 |
| timing | `ekf-spoof` | 2 / 1 | 0.00 |
| timing | `ekf-calibrated` | 2 / 1 | 0.00 |
| timing | `ekf-mhss` | 1 / 1 | 0.00 |

## What the towers can see: the monitor's own uncertainty

Median over each run's seconds, then over seeds, of the 1-sigma (worst axis) of the displacement the tower test estimates; the share of seconds the test has an opinion (at least 5 sites heard in both windows). The ramp moves GNSS 2 m/s × lag.

| Leg | Entry | Estimator | Test (lag/window s) | Opinion share | Sigma (m) | Ramp over the lag (m) |
|---|---|---|---|---|---|---|
| drone | nominal | `ekf-spoof` | 30/10 | 0.00 | 38.3 | 60 |
| drone | nominal | `ekf-spoof` | 120/20 | 0.00 | 49.3 | 240 |
| drone-many | nominal | `ekf-spoof` | 30/10 | 0.96 | 34.3 | 60 |
| drone-many | nominal | `ekf-spoof` | 120/20 | 0.83 | 41.0 | 240 |
| realistic | nominal | `ekf-spoof` | 30/10 | 0.00 | – | 60 |
| realistic | nominal | `ekf-spoof` | 120/20 | 0.00 | – | 240 |

## Runtime

| Estimator | Median s per run | Worst |
|---|---|---|
| `ekf` | 0.7 | 3.7 |
| `ekf-spoof` | 0.9 | 6.8 |
| `ekf-calibrated` | 2.5 | 35.7 |
| `ekf-calibrated-spoof` | 3.0 | 1,876.6 |
| `ekf-mhss` | 7.9 | 17.4 |
