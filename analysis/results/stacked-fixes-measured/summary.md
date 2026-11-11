# Stacked fixes with LTE error sizes from our captures (#257)

**Sim, a study variant of the drone leg** (ADR-0015; no committed scenario entry or default changed). At ebf7802: `python analysis/stacked_fixes.py --study measured --families ekf --seeds 0-49 --jobs 4` on g14 (Ryzen 7 8845HS, Linux), 11.2 min; `python analysis/stacked_fixes.py --study measured --families ekf-calibrated --seeds 0-49 --jobs 4` on g14 (Ryzen 7 8845HS, Linux), 222.8 min. Seeds 0–49, paired: on a seed every row sees the same trajectory, GNSS, IMU, baro, dongle, tower clocks, multipath, dropout and table error draws, so *assumed* and *measured* differ only in the LTE white noise (and a sensitivity row in its one moved size). Only the white noise is measured, and at rest (ADR-0036): the measured rows keep every other size at the leg's assumed value. Hopping is a study leg (ADR-0040): the payload cannot hop yet. Choices of this study: ADR-0049 (Proposed).

## Sizes

| Term | Assumed rows (the leg) | Measured rows | Source |
|---|---|---|---|
| White range noise per record | 50 m at 1 Hz, every record | ADR-0036 law from the record's SNR: σ² = 0.64² + 2.28² / SNR_lin (10 Hz, SNR ≥ −8 dB), 12.4 m (−11 to −8 dB), 24.7 m (−14 to −11 dB), × √(20 / n_epochs); 1 Hz record: 0.2 to 7.8 m; below −14 dB 49.4 m (× 0.32 at 1 Hz = 15.6 m) | measured at −14 dB and up: `analysis/results/lte-measured-noise/summary.json`, 15 real static sessions `20261110-*`, front end and analysis at `e9a9053`; ADR-0036 consequence 1; `pnt.nav.told_sigma.white_sigma_m`. Below −14 dB not measured: ADR-0044's 49.4 m (`TBC`) |
| Correlated range error (multipath) | 50 m, 30 s Gauss-Markov per eNB | 50 m, 30 s (unchanged: no capture measures it on the move) | assumed (`challenge-drone.yaml`, `TBC`). Sensitivity: ADR-0036's at-rest 10 m, 3 s (same-eNB S(1 s) 4.9 to 18 m, `20261110-*`), a floor for a moving drone, not a value |
| Tower table position error | 100 m per axis per eNB | 100 m (unchanged) | assumed (`TBC`, ASM-02 `TBD`; not measurable at rest). Sensitivity: 50 m, 20 m |
| Arc restarts and steps | none (`arc` always 0) | none (unchanged) | Sensitivity: restarts at the measured rate with steps sized from `analysis/results/lte-reacq-steps/summary.json` (after, front end `ea72f6a`; real static sessions `20261111-0151-static-fullsuite2`, `20261111-0233-static-lte-1h`, GPS truth); far-offset size `TBC` (ADR-0049) |
| Hop re-acquisition loss | none (0.15 s dead time per dwell) | none (unchanged) | not modelled, no hopped capture (ADR-0040). Sensitivity: half of the dwells lose the cell |
| Told sigma (today, + 13 carriers) | 2 m | 2 m (unchanged) | `challenge-drone.yaml` |
| Dropout, tower clocks, dongle, GNSS, IMU, baro, trajectory | as the leg | as the leg | assumed (`TBC`). Tower clocks: the leg's 0.035 m/s per site is inside ADR-0036's same-eNB bound (0.5 m/s); between eNBs `TBD` |

Arc model of the sensitivity row (ADR-0049): restarts every 43 s per cell on average (Poisson; 250 new arcs over 10,780 tracked cell-seconds); each arc's offset is far with probability 0.094 (uniform within ±1,500 m, `TBC`), else normal with σ 8.0 m. This gives 16.8% of steps over 100 m and a median step of about 10 m, as measured (`tests/test_stacked_fixes.py` checks the model against `REACQ_AFTER`). The default filters ignore `meta.arc` (`arc_bias` is off).

Specs: `nolte` = no LTE records (`challenge-drone-outage` without `sources.lte`); `1c` = `challenge-drone-outage` (1 carrier, 2460); `13c` = `challenge-drone-hop-outage` (13 carriers); `13c-true` = `challenge-drone-hop-outage` (13 carriers), told the true noise; `m-1c` = `1c` with the measured white noise; `m-13c` = `13c` with the measured white noise; `m-13c-true` = `m-13c`, told the true noise (each record's white σ and the multipath); `m-13c-tp50` = `m-13c`, tower position error 50 m; `m-13c-tp20` = `m-13c`, tower position error 20 m; `m-13c-mprest` = `m-13c`, multipath at the at-rest 10 m, 3 s; `m-13c-arcs` = `m-13c` with arc restarts and steps; `m-13c-hoploss` = `m-13c` with half of the hop dwells lost.

**Statistic (ADR-0034 amendment):** at each whole second after GPS loss the 95th percentile of horizontal error across the 50 runs; the worst second of 0–120 s is scored against the fallback (50 m) and of 0–300 s against T1 (25 m). *Median run p95*: median over seeds of each run's own p95 over the window. *Hazardous*: epochs to the end of the 300 s window with error over the 50 m alert limit while HPL is under it (total [seeds]). *HPL bound*: share of the first 300 s with HPL >= error, median (min) over seeds.

## Ladder: assumed against measured

| Row | `ekf` assumed 120 / 300 s (m) | `ekf` measured 120 / 300 s (m) | `ekf-calibrated` assumed 120 / 300 s (m) | `ekf-calibrated` measured 120 / 300 s (m) |
|---|---|---|---|---|
| no LTE (control) | 1,329 / 2,909 | 1,329 / 2,909 | 1,329 / 2,909 | 1,329 / 2,909 |
| today: 1 carrier, told 2 m | 3,268 / 12,507 | 2,309 / 6,604 | 3,418 / 10,154 | 2,577 / 5,673 |
| + learned noise | 813 / 2,474 | 1,058 / 4,024 | 848 / 2,268 | 1,124 / 3,352 |
| + 13 carriers | 3,628 / 11,894 | 3,073 / 11,098 | 4,065 / 15,256 | 2,177 / 4,791 |
| learned noise + 13 carriers | 132 / 132 | 105 / 105 | 158 / 203 | 154 / 183 |
| ceiling: told the true noise, 13 carriers | 111 / 111 | 101 / 101 | 122 / 144 | 106 / 146 |

## Every row

| Row | Sizes | Estimator | Spec | Worst second 0–120 s (m) | <= 50 m | Worst second 0–300 s (m) | <= 25 m | Median run p95 120 / 300 s (m) | Hazardous [seeds] | HPL bound 300 s |
|---|---|---|---|---|---|---|---|---|---|---|
| no LTE (control) | both | `ekf` | `nolte` | 1,329 (s 120) | no | 2,909 (s 300) | no | 1,140 / 2,468 | 0 [0/50] | 1.00 (1.00) |
| today: 1 carrier, told 2 m | assumed | `ekf` | `1c` | 3,268 (s 120) | no | 12,507 (s 300) | no | 1,185 / 4,034 | 285 [5/50] (14, 15, 24, 28, 35) | 0.73 (0.11) |
| today: 1 carrier, told 2 m | measured | `ekf` | `m-1c` | 2,309 (s 120) | no | 6,604 (s 300) | no | 1,082 / 3,009 | 1,345 [19/50] (3, 5, 8, 10, 11, 14, …) | 0.31 (0.09) |
| + learned noise | assumed | `ekf-learned-noise` | `1c` | 813 (s 120) | no | 2,474 (s 300) | no | 413 / 982 | 0 [0/50] | 1.00 (0.53) |
| + learned noise | measured | `ekf-learned-noise` | `m-1c` | 1,058 (s 120) | no | 4,024 (s 300) | no | 433 / 1,140 | 0 [0/50] | 0.99 (0.29) |
| + 13 carriers | assumed | `ekf` | `13c` | 3,628 (s 120) | no | 11,894 (s 300) | no | 1,103 / 3,611 | 1,072 [7/50] (0, 5, 15, 31, 35, 41, …) | 0.40 (0.04) |
| + 13 carriers | measured | `ekf` | `m-13c` | 3,073 (s 116) | no | 11,098 (s 300) | no | 998 / 3,349 | 2,866 [31/50] (0, 1, 2, 4, 6, 7, …) | 0.08 (0.02) |
| learned noise + 13 carriers | assumed | `ekf-learned-noise` | `13c` | 132 (s 88) | no | 132 (s 88) | no | 81 / 87 | 0 [0/50] | 1.00 (0.98) |
| learned noise + 13 carriers | measured | `ekf-learned-noise` | `m-13c` | 105 (s 88) | no | 105 (s 88) | no | 67 / 75 | 0 [0/50] | 1.00 (0.98) |
| ceiling: told the true noise, 13 carriers | assumed | `ekf` | `13c-true` | 111 (s 90) | no | 111 (s 90) | no | 73 / 77 | 0 [0/50] | 1.00 (1.00) |
| ceiling: told the true noise, 13 carriers | measured | `ekf` | `m-13c-true` | 101 (s 89) | no | 101 (s 89) | no | 62 / 67 | 0 [0/50] | 1.00 (1.00) |
| stack, tower position 50 m | sensitivity | `ekf-learned-noise` | `m-13c-tp50` | 101 (s 89) | no | 104 (s 233) | no | 65 / 73 | 0 [0/50] | 1.00 (0.98) |
| stack, tower position 20 m | sensitivity | `ekf-learned-noise` | `m-13c-tp20` | 107 (s 89) | no | 107 (s 89) | no | 64 / 73 | 0 [0/50] | 1.00 (0.98) |
| stack, multipath at rest (10 m, 3 s) | sensitivity | `ekf-learned-noise` | `m-13c-mprest` | 51 (s 87) | no | 51 (s 87) | no | 29 / 29 | 0 [0/50] | 1.00 (1.00) |
| stack, arc restarts and steps | sensitivity | `ekf-learned-noise` | `m-13c-arcs` | 143 (s 89) | no | 151 (s 177) | no | 71 / 85 | 0 [0/50] | 1.00 (0.98) |
| stack, half of hop dwells lost | sensitivity | `ekf-learned-noise` | `m-13c-hoploss` | 117 (s 89) | no | 118 (s 171) | no | 85 / 84 | 0 [0/50] | 1.00 (0.99) |
| no LTE (control) | both | `ekf-calibrated` | `nolte` | 1,329 (s 120) | no | 2,909 (s 300) | no | 1,140 / 2,468 | 0 [0/50] | 1.00 (1.00) |
| today: 1 carrier, told 2 m | assumed | `ekf-calibrated` | `1c` | 3,418 (s 117) | no | 10,154 (s 300) | no | 1,239 / 3,180 | 56 [1/50] (35) | 0.70 (0.04) |
| today: 1 carrier, told 2 m | measured | `ekf-calibrated` | `m-1c` | 2,577 (s 116) | no | 5,673 (s 297) | no | 1,088 / 2,417 | 374 [8/50] (5, 6, 7, 9, 14, 16, …) | 0.28 (0.03) |
| + learned noise | assumed | `ekf-calibrated-learned-noise` | `1c` | 848 (s 120) | no | 2,268 (s 300) | no | 450 / 1,163 | 0 [0/50] | 1.00 (0.57) |
| + learned noise | measured | `ekf-calibrated-learned-noise` | `m-1c` | 1,124 (s 120) | no | 3,352 (s 300) | no | 631 / 1,713 | 0 [0/50] | 1.00 (0.46) |
| + 13 carriers | assumed | `ekf-calibrated` | `13c` | 4,065 (s 120) | no | 15,256 (s 300) | no | 1,085 / 2,580 | 187 [6/50] (0, 30, 31, 35, 44, 48) | 0.44 (0.05) |
| + 13 carriers | measured | `ekf-calibrated` | `m-13c` | 2,177 (s 115) | no | 4,791 (s 300) | no | 562 / 1,851 | 1,050 [26/50] (0, 2, 5, 6, 8, 15, …) | 0.10 (0.03) |
| learned noise + 13 carriers | assumed | `ekf-calibrated-learned-noise` | `13c` | 158 (s 89) | no | 203 (s 173) | no | 98 / 126 | 0 [0/50] | 1.00 (0.95) |
| learned noise + 13 carriers | measured | `ekf-calibrated-learned-noise` | `m-13c` | 154 (s 115) | no | 183 (s 185) | no | 75 / 112 | 0 [0/50] | 1.00 (0.79) |
| ceiling: told the true noise, 13 carriers | assumed | `ekf-calibrated` | `13c-true` | 122 (s 90) | no | 144 (s 171) | no | 71 / 84 | 0 [0/50] | 1.00 (1.00) |
| ceiling: told the true noise, 13 carriers | measured | `ekf-calibrated` | `m-13c-true` | 106 (s 87) | no | 146 (s 181) | no | 61 / 78 | 0 [0/50] | 1.00 (1.00) |
| stack, tower position 50 m | sensitivity | `ekf-calibrated-learned-noise` | `m-13c-tp50` | 146 (s 115) | no | 177 (s 171) | no | 82 / 114 | 0 [0/50] | 1.00 (0.83) |
| stack, tower position 20 m | sensitivity | `ekf-calibrated-learned-noise` | `m-13c-tp20` | 144 (s 114) | no | 171 (s 300) | no | 81 / 110 | 0 [0/50] | 1.00 (0.79) |
| stack, multipath at rest (10 m, 3 s) | sensitivity | `ekf-calibrated-learned-noise` | `m-13c-mprest` | 50 (s 87) | yes | 54 (s 178) | no | 30 / 35 | 0 [0/50] | 1.00 (1.00) |
| stack, arc restarts and steps | sensitivity | `ekf-calibrated-learned-noise` | `m-13c-arcs` | 459 (s 106) | no | 608 (s 158) | no | 87 / 124 | 0 [0/50] | 1.00 (0.94) |
| stack, half of hop dwells lost | sensitivity | `ekf-calibrated-learned-noise` | `m-13c-hoploss` | 136 (s 107) | no | 189 (s 172) | no | 87 / 117 | 0 [0/50] | 1.00 (0.99) |

## Read with

- The measured white noise is at rest, on one RTL-SDR, at two spots in one neighbourhood, before #245 (ADR-0036's amendment says its bins will move). Below −14 dB nothing was measured; ADR-0044's 49.4 m (`TBC`) stands there.
- A static capture cannot size multipath on a moving drone, tower table error, bias, or arc restarts in motion; those stay at the leg's values in the measured rows and are moved one at a time in the sensitivity rows. The multipath-at-rest row is a floor for a moving drone, not a value.
- The arc row uses the front end on `main` after its re-acquisition fix. Before it, the real GPS-cut replays (#214, ADR-0044) saw 90 of 103 new arcs at SNR ≥ −8 dB step more than 100 m (median 874 m); that front end is not modelled here.
- The ceiling is told each record's true white σ and the multipath σ, which no real receiver knows: a bound on what noise knowledge could buy, not a result.
- The learned-noise prior and memories were chosen on the assumed leg (ADR-0039, seeds 100–109); nothing was retuned for the measured sizes.
