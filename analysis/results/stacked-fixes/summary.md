# Stacked fixes on the drone leg (#218)

**Sim, every value `TBC`** (ADR-0015; LTE noise, hop set, dwell and the learned-noise prior are not sized from real data). `python analysis/stacked_fixes.py --seeds 0-49 --jobs 4` at 52a7dfe on g14 (Ryzen 7 8845HS, Linux), seeds 0–49 (paired), 218.6 min. Hopping is a study leg (ADR-0040): the payload cannot hop yet. Learned noise (ADR-0039) and the jump guard (ADR-0038) are opt-in estimators; learned noise + guard has no registered name and is `configured(ekf.run[_calibrated], noise_tau_s=..., jump_guard=JumpGuard)`.

Scenario entries: `nolte` = no LTE records (`challenge-drone-outage` without `sources.lte`); `1c` = `challenge-drone-outage` (1 carrier, 2460); `6c` = `challenge-drone-hop-outage`, first 6 carriers; `13c` = `challenge-drone-hop-outage` (13 carriers); `13c-true` = `challenge-drone-hop-outage` (13 carriers), told the true noise; `jump-1c` = `challenge-drone-spoof-jump` (300 m, 1 carrier); `jump-13c` = `challenge-drone-hop-spoof-jump` (300 m, 13 carriers).

**Statistic (ADR-0034 amendment):** at each whole second after GPS loss (after the jump starts, on jump rows) the 95th percentile of horizontal error across the 50 runs; the worst second of 0–120 s is scored against the fallback (50 m) and of 0–300 s against T1 (25 m). With this many runs the per-second 95th percentile moves by several metres from one second to the next. *Median run p95*: median over seeds of each run's own p95 over the window (older tables). *Hazardous*: epochs from the run's start to the end of the 300 s window (each run is cut there) with error over the 50 m alert limit while HPL is under it (total, seeds). *HPL bound*: share of the first 300 s with HPL >= error, median (min) over seeds.

| Row | Estimator | Scenario | Worst second 0–120 s (m) | <= 50 m | Worst second 0–300 s (m) | <= 25 m | Median run p95 120 / 300 s (m) | Hazardous (seeds) | HPL bound 300 s | On spoof +120 s |
|---|---|---|---|---|---|---|---|---|---|---|
| no LTE (control) | `ekf` | `nolte` | 1,329 (s 120) | no | 2,909 (s 300) | no | 1,140 / 2,468 | 0 [0/50] | 1.00 (1.00) | – |
| today: 1 carrier, told 2 m | `ekf` | `1c` | 3,268 (s 120) | no | 12,507 (s 300) | no | 1,185 / 4,034 | 285 [5/50] (14, 15, 24, 28, 35) | 0.73 (0.11) | – |
| + learned noise | `ekf-learned-noise` | `1c` | 813 (s 120) | no | 2,474 (s 300) | no | 413 / 982 | 0 [0/50] | 1.00 (0.53) | – |
| + hopping 6 carriers | `ekf` | `6c` | 3,901 (s 120) | no | 15,222 (s 300) | no | 1,346 / 4,947 | 296 [5/50] (1, 16, 28, 35, 37) | 0.57 (0.02) | – |
| + hopping 13 carriers | `ekf` | `13c` | 3,628 (s 120) | no | 11,894 (s 300) | no | 1,103 / 3,611 | 1,072 [7/50] (0, 5, 15, 31, 35, 41, …) | 0.40 (0.04) | – |
| learned noise + 6 carriers | `ekf-learned-noise` | `6c` | 199 (s 82) | no | 245 (s 268) | no | 132 / 139 | 0 [0/50] | 1.00 (0.81) | – |
| learned noise + 13 carriers | `ekf-learned-noise` | `13c` | 132 (s 88) | no | 132 (s 88) | no | 81 / 87 | 0 [0/50] | 1.00 (0.98) | – |
| all three: + jump guard | `ekf-learned-noise+guard` | `13c` | 132 (s 88) | no | 132 (s 88) | no | 81 / 87 | 0 [0/50] | 1.00 (0.98) | – |
| told the true noise, 13 carriers (not available) | `ekf` | `13c-true` | 111 (s 90) | no | 111 (s 90) | no | 73 / 77 | 0 [0/50] | 1.00 (1.00) | – |
| held 300 m jump, 1 carrier: default | `ekf` | `jump-1c` | 832 (s 112) | no | 832 (s 112) | no | 302 / 302 | 130,417 [49/50] (0, 1, 2, 3, 4, 5, …) | 0.09 (0.08) | 47/50 |
| held 300 m jump, 1 carrier: jump guard | `ekf-guard` | `jump-1c` | 3,790 (s 120) | no | 11,310 (s 300) | no | 1,147 / 5,161 | 131 [3/50] (14, 36, 48) | 0.65 (0.15) | 0/50 |
| held 300 m jump, 1 carrier: jump guard + learned noise | `ekf-learned-noise+guard` | `jump-1c` | 1,183 (s 120) | no | 3,135 (s 300) | no | 405 / 562 | 0 [0/50] | 1.00 (0.83) | 1/50 |
| held 300 m jump, 13 carriers: default | `ekf` | `jump-13c` | 1,571 (s 120) | no | 3,218 (s 300) | no | 302 / 302 | 115,394 [49/50] (0, 1, 2, 3, 4, 5, …) | 0.09 (0.02) | 42/50 |
| held 300 m jump, 13 carriers: jump guard | `ekf-guard` | `jump-13c` | 2,810 (s 120) | no | 11,103 (s 300) | no | 1,119 / 2,949 | 589 [8/50] (0, 15, 30, 31, 35, 41, …) | 0.64 (0.02) | 0/50 |
| held 300 m jump, 13 carriers: jump guard + learned noise | `ekf-learned-noise+guard` | `jump-13c` | 114 (s 104) | no | 120 (s 250) | no | 83 / 88 | 0 [0/50] | 1.00 (0.98) | 0/50 |
| no LTE (control) | `ekf-calibrated` | `nolte` | 1,329 (s 120) | no | 2,909 (s 300) | no | 1,140 / 2,468 | 0 [0/50] | 1.00 (1.00) | – |
| today: 1 carrier, told 2 m | `ekf-calibrated` | `1c` | 3,418 (s 117) | no | 10,154 (s 300) | no | 1,239 / 3,180 | 56 [1/50] (35) | 0.70 (0.04) | – |
| + learned noise | `ekf-calibrated-learned-noise` | `1c` | 848 (s 120) | no | 2,268 (s 300) | no | 450 / 1,163 | 0 [0/50] | 1.00 (0.57) | – |
| + hopping 6 carriers | `ekf-calibrated` | `6c` | 3,205 (s 120) | no | 10,251 (s 279) | no | 1,297 / 4,102 | 0 [0/50] | 0.60 (0.05) | – |
| + hopping 13 carriers | `ekf-calibrated` | `13c` | 4,065 (s 120) | no | 15,256 (s 300) | no | 1,085 / 2,580 | 187 [6/50] (0, 30, 31, 35, 44, 48) | 0.44 (0.05) | – |
| learned noise + 6 carriers | `ekf-calibrated-learned-noise` | `6c` | 575 (s 120) | no | 935 (s 300) | no | 156 / 209 | 0 [0/50] | 1.00 (0.31) | – |
| learned noise + 13 carriers | `ekf-calibrated-learned-noise` | `13c` | 158 (s 89) | no | 203 (s 173) | no | 98 / 126 | 0 [0/50] | 1.00 (0.95) | – |
| all three: + jump guard | `ekf-calibrated-learned-noise+guard` | `13c` | 158 (s 89) | no | 203 (s 173) | no | 98 / 126 | 0 [0/50] | 1.00 (0.95) | – |
| told the true noise, 13 carriers (not available) | `ekf-calibrated` | `13c-true` | 122 (s 90) | no | 144 (s 171) | no | 71 / 84 | 0 [0/50] | 1.00 (1.00) | – |
| held 300 m jump, 1 carrier: default | `ekf-calibrated` | `jump-1c` | 1,006 (s 102) | no | 1,736 (s 300) | no | 302 / 302 | 123,263 [47/50] (0, 1, 2, 3, 4, 5, …) | 0.09 (0.08) | 45/50 |
| held 300 m jump, 1 carrier: jump guard | `ekf-calibrated-guard` | `jump-1c` | 2,678 (s 120) | no | 11,241 (s 300) | no | 1,104 / 3,989 | 40 [2/50] (36, 45) | 0.72 (0.10) | 1/50 |
| held 300 m jump, 1 carrier: jump guard + learned noise | `ekf-calibrated-learned-noise+guard` | `jump-1c` | 1,126 (s 120) | no | 2,717 (s 300) | no | 402 / 1,039 | 0 [0/50] | 1.00 (0.74) | 4/50 |
| held 300 m jump, 13 carriers: default | `ekf-calibrated` | `jump-13c` | 1,995 (s 112) | no | 5,894 (s 300) | no | 302 / 302 | 103,160 [46/50] (0, 1, 2, 3, 4, 5, …) | 0.09 (0.03) | 38/50 |
| held 300 m jump, 13 carriers: jump guard | `ekf-calibrated-guard` | `jump-13c` | 3,092 (s 120) | no | 10,314 (s 300) | no | 1,089 / 2,937 | 161 [8/50] (0, 8, 15, 30, 31, 38, …) | 0.59 (0.03) | 1/50 |
| held 300 m jump, 13 carriers: jump guard + learned noise | `ekf-calibrated-learned-noise+guard` | `jump-13c` | 155 (s 75) | no | 176 (s 270) | no | 95 / 105 | 0 [0/50] | 1.00 (0.93) | 0/50 |

Notes:

- Hazardous seeds list at most the first six.
- The ceiling row is told the sim's true LTE noise (white and multipath together), which no real receiver knows: an upper bound on what better noise knowledge could buy, not a result.
- On the outage rows the jump guard has nothing to refuse (no GNSS fix arrives before the cut), so *all three* equals the stack.
- Jump rows: the clock starts at the jump (150 s), GPS stays on (spoofed), and the error includes following the jump (about 300 m). *On spoof*: within half the jump of where the spoofer puts the receiver. A guarded estimate can land there while coasting with GNSS excluded: seen on tuning seed 105; the reported seeds' cases were not inspected.

## Not checked

- Any real capture: no hopped capture exists, and the learned-noise prior (40 m) and memories (60 s, 120 s) were chosen on sim tuning seeds 100–109 (ADR-0039).
- `ekf-imu` and other estimators: no learned-noise variant is registered for them.
- Jump guard + learned noise on clean (no jump) runs beyond the outage rows here, and false alarms.
