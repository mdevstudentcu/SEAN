# Slow GNSS drag with carrier hopping: the tower monitor against masts heard (#221, #258)

Sim, study leg (ADR-0040: the payload cannot hop yet), every value `TBC`. Commit 0f18c7a, `python analysis/drag_with_hopping.py --seeds 50 --stress-seeds 10 --jobs 5`, 19.9 min on Darwin, arm, Python 3.14.6. Seeds 0–49, paired. The monitor's settings are as committed (ADR-0037, chosen on seeds 100–109 of the many-tower case); the site rule for hopped carriers (ADR-0037 amendment, #258) was checked on seeds 100–109 of this leg, not on these.

Entries `spoof-ramp` (2 m/s at 45°, from 150 s), `nominal` and `outage` of `challenge-drone` (1 carrier, EARFCN 2460) and `challenge-drone-hop` (the first 6 carriers of its hop set, and all 13), as committed. `ekf-spoof` is `ekf` with the opt-in tower monitor as committed; `ekf-every-epoch-spoof` is the same with the site rule before #258 (a site counts if heard on half of every epoch of a window; this study only). Detection and false alarms are `pnt.metrics` (`analysis/spoof_detection.py`'s rows). Masts: distinct masts heard per 10 s after the cell lookup, median over seeds of each run's median.

- **#221's criterion (`ekf-spoof` flags the ramp on >= 45 of 50 seeds on the 13-carrier leg, 0 added false alarms): met.** 50 of 50 seeds (rule before #258: 0 of 50), 0 added false alarms in 100 paired `nominal`/`outage` runs.
- **Time to alert against T4's 30 s (`TBC`): not met.** 13 carriers, `ekf-spoof`: median 127 s, worst 276 s. In 30 s the ramp moves the fix 60 m; the 30 s-lag test's own 1-sigma on that move is 41 m (worst axis, median over the ramp runs' seconds and seeds), so 60 m is 1.5 sigma, while its threshold (F = 13.1, median) needs about 5.1 sigma along one axis. On hopped windows the fit also sees only part of the move (the epoch term takes the mean of the few sites on air). The 120 s-lag test has 33 m against the 240 m the ramp moves in 120 s.
- 1 carrier: `ekf-spoof` and the rule before #258 give identical scored metrics and tower-test logs on 150 of 150 runs.
- 6 carriers: `ekf-spoof` and the rule before #258 give identical scored metrics and tower-test logs on 0 of 150 runs.
- 13 carriers: `ekf-spoof` and the rule before #258 give identical scored metrics and tower-test logs on 0 of 150 runs.
- Test calibration, 6 carriers, `nominal`, `ekf-spoof`: 30/10 s (18,816 tests): 11.29 % under 0.1, 1.15 % under 0.01, 0.11 % under 0.001; 120/20 s (12,308 tests): 7.14 % under 0.1, 0.19 % under 0.01, 0.00 % under 0.001. A calibrated F-test puts 10 %, 1 % and 0.1 % of its tests there; the seconds are correlated, so these are a shape check, not a false-alarm rate.
- Test calibration, 13 carriers, `nominal`, `ekf-spoof`: 30/10 s (33,327 tests): 5.64 % under 0.1, 0.46 % under 0.01, 0.04 % under 0.001; 120/20 s (29,676 tests): 3.74 % under 0.1, 0.24 % under 0.01, 0.01 % under 0.001. A calibrated F-test puts 10 %, 1 % and 0.1 % of its tests there; the seconds are correlated, so these are a shape check, not a false-alarm rate.

| Carriers (masts per 10 s) | Estimator | Ramp detected | TTA median (s) | TTA worst (s) | Error at alert (m) | Hazardous epochs on the ramp, mean (seeds) | False alarms / h (seeds) | Added false alarms (paired runs) | Monitor has an opinion (ramp, median share of s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 (2.0) | `ekf` | 0/50 | – | – | – | 5,449 (50) | nominal 0.00 (0); outage 4.10 (39) | – | – |
| 1 (2.0) | `ekf-every-epoch-spoof` | 1/50 | 374 | 374 | 750 | 5,442 (50) | nominal 0.00 (0); outage 4.10 (39) | 0 of 100 | 30/10 s: 0 %, 120/20 s: 0 % |
| 1 (2.0) | `ekf-spoof` | 1/50 | 374 | 374 | 750 | 5,442 (50) | nominal 0.00 (0); outage 4.10 (39) | 0 of 100 | 30/10 s: 0 %, 120/20 s: 0 % |
| 6 (8.0) | `ekf` | 0/50 | – | – | – | 5,449 (50) | nominal 0.00 (0); outage 3.70 (37) | – | – |
| 6 (8.0) | `ekf-every-epoch-spoof` | 1/50 | 144 | 144 | 286 | 5,364 (50) | nominal 0.00 (0); outage 3.70 (37) | 0 of 100 | 30/10 s: 0 %, 120/20 s: 0 % |
| 6 (8.0) | `ekf-spoof` | 2/50 | 352 | 415 | 707 | 5,387 (50) | nominal 0.10 (1: seed 48); outage 3.70 (37) | **1 of 100**: nominal 48 | 30/10 s: 55 %, 120/20 s: 34 % |
| 13 (26.0) | `ekf` | 0/50 | – | – | – | 5,449 (50) | nominal 0.00 (0); outage 3.60 (36) | – | – |
| 13 (26.0) | `ekf-every-epoch-spoof` | 0/50 | – | – | – | 5,449 (50) | nominal 0.00 (0); outage 3.60 (36) | 0 of 100 | 30/10 s: 0 %, 120/20 s: 0 % |
| 13 (26.0) | `ekf-spoof` | 50/50 | 127 | 276 | 254 | 2,734 (50) | nominal 0.00 (0); outage 3.60 (36) | 0 of 100 | 30/10 s: 84 %, 120/20 s: 53 % |

## Stress cases, seeds 0–9

13 carriers unless named. `@1`, `@0.5`: the ramp at 1 and 0.5 m/s (from 150 s, 45°). `/dwell2`: 2 s dwells (26 s hop cycle, 2 records per dwell). `spoof-jump`: the 300 m jump at 150 s, held to the end (the filter's own gate flags it; the monitor must not lose that). Six carriers and the outage entry are in the table above, on 50 seeds.

| Case | Estimator | Detected | TTA median (s) | TTA worst (s) | Error at alert (m) | Hazardous epochs, mean (seeds) | False alarms / h (seeds) | Added false alarms | Monitor has an opinion |
|---|---|---|---|---|---|---|---|---|---|
| `13-carrier:spoof-ramp@1` | `ekf` | 0/10 | – | – | – | 5,199 (10) | – | – | – |
| `13-carrier:spoof-ramp@1` | `ekf-every-epoch-spoof` | 0/10 | – | – | – | 5,199 (10) | – | – | 30/10 s: 0 %, 120/20 s: 0 % |
| `13-carrier:spoof-ramp@1` | `ekf-spoof` | 4/10 | 234 | 362 | 233 | 4,254 (10) | – | – | 30/10 s: 92 %, 120/20 s: 82 % |
| `13-carrier:spoof-ramp@0.5` | `ekf` | 0/10 | – | – | – | 4,705 (10) | – | – | – |
| `13-carrier:spoof-ramp@0.5` | `ekf-every-epoch-spoof` | 0/10 | – | – | – | 4,705 (10) | – | – | 30/10 s: 0 %, 120/20 s: 0 % |
| `13-carrier:spoof-ramp@0.5` | `ekf-spoof` | 0/10 | – | – | – | 4,705 (10) | – | – | 30/10 s: 93 %, 120/20 s: 82 % |
| `13-carrier/dwell2:spoof-ramp` | `ekf` | 0/10 | – | – | – | 5,449 (10) | – | – | – |
| `13-carrier/dwell2:spoof-ramp` | `ekf-every-epoch-spoof` | 0/10 | – | – | – | 5,449 (10) | – | – | 30/10 s: 0 %, 120/20 s: 0 % |
| `13-carrier/dwell2:spoof-ramp` | `ekf-spoof` | 10/10 | 155 | 337 | 306 | 3,993 (10) | – | – | 30/10 s: 62 %, 120/20 s: 56 % |
| `13-carrier/dwell2:nominal` | `ekf` | 0/0 | – | – | – | – (0) | nominal 0.00 (0) | – | – |
| `13-carrier/dwell2:nominal` | `ekf-every-epoch-spoof` | 0/0 | – | – | – | – (0) | nominal 0.00 (0) | 0 of 10 | 30/10 s: 0 %, 120/20 s: 0 % |
| `13-carrier/dwell2:nominal` | `ekf-spoof` | 0/0 | – | – | – | – (0) | nominal 0.00 (0) | 0 of 10 | 30/10 s: 66 %, 120/20 s: 81 % |
| `13-carrier:spoof-jump` | `ekf` | 10/10 | 1 | 1 | 3 | 4,327 (9) | – | – | – |
| `13-carrier:spoof-jump` | `ekf-every-epoch-spoof` | 10/10 | 1 | 1 | 3 | 4,327 (9) | – | – | 30/10 s: 0 %, 120/20 s: 0 % |
| `13-carrier:spoof-jump` | `ekf-spoof` | 10/10 | 1 | 1 | 3 | 1,832 (6) | – | – | 30/10 s: 78 %, 120/20 s: 29 % |

TTA: time to alert from the attack's start, detected seeds only. Error at alert: horizontal error at the alert, median over detected seeds. Hazardous: epochs whose error exceeds the alert limit (`pnt.metrics`). False alarms on `nominal` and `outage`: mean per hour over seeds, and the seeds with any. Added false alarms: (entry, seed) pairs where the monitor variant has more false alarms than the same filter without it on the same seed, of the pairs compared. Opinion: share of seconds a tower test (lag/window) had at least `min_sites` sites kept (`spoof_detection.py`'s per-run share), median over the attack runs.
