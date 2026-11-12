# Real hand-held walk `20261111-1806-walk-lte`: why the IMU and LTE make it worse (#214)

Evidence: **replay of a real session** (GPS HAT, MPU6050, BMP180, RTL-SDR on LTE EARFCN 2460), GPS cut in software (ADR-0015). Errors, innovations, times and counts only: no position, track, origin, range or bearing.

Commits (all on origin): `main` at `c526b9e` (nav code identical to #241's `289b702`), the GPS-cut tool `analysis/walk_gps_cut.py` at `fa5795c` (`shrikar/feat/214-walk-gps-cut`, not merged), this branch's fixes. Runs merge the tool onto each tree locally, so the figures and summaries name that local merge (`3fb854d`: `main` + `fa5795c` + this branch up to `ea27896`). LTE records: `20261111-1806-walk-lte-lte` (front end at `fa5795c`).

## 1. IMU: uncalibrated biases, an alignment fooled by them (fixed, ADR-0053)

Measured on the walk's still first minute (2 to 55 s): gyro −3.95, +0.15, +1.08 deg/s; specific force 8.44 m/s² along body +z (−1.37 m/s², −140 mg). The filter assumed 0.05 deg/s and 5 mg left after a start-up calibration nothing ran. Gyro x stays −3.4 to −4.0 deg/s at every stop and in every 20 s window of the walk. Gyro yaw against the GPS course over the four walking stretches: 208 to 453 deg off raw, 41 to 82 deg with the still bias removed; same sign on every turn over 45 deg. Units, axes, gravity sign, timing (97.8 Hz, monotonic, 2 gaps over 50 ms) and mounting are not at fault: the alignment fits the whole body-to-ENU rotation. Details in ADR-0053.

`after/summary.md`: this branch. Before: `main` (same table from `walk_gps_cut.py` at `fa5795c`). Median (worst) of 3 cuts, m.

| Config | | 60 s | 120 s | 300 s | Before cut p95 | GNSS excluded before | HPL ≥ error |
|---|---|---|---|---|---|---|---|
| no LTE, `ekf-imu` | main | 364,781 (438,601) | 438,601 (511,596) | 683,705 (776,150) | 270,258 | 83 % | 100 % |
| no LTE, `ekf-imu` | branch | 22.8 (89.6) | 107 (223) | 503 (557) | 1.2 | 0 % | 100 % |
| LTE, `ekf-imu` | main | 1,149,807 (1,399,498) | 1,399,498 (1,674,815) | 2,299,369 (2,647,029) | 772,387 | 84 % | 0 % |
| LTE, `ekf-imu` | branch | 103 (538) | 598 (642) | 1,629 (1,812) | 6.3 | 0 % | 70 % |
| no LTE, `ekf` (reference) | both | 22.8 (89.6) | 107 (223) | 503 (557) | 1.2 | 0 % | 100 % |

With honest bias 1-sigma (the calibration's, 0.5 to 2.9 deg/s about the vertical from the hand's sway) the alignment refuses every window of the walk, so `ekf-imu` runs the constant-velocity model: no better than `ekf`, and no longer 270 km off with GPS on.

## 2. LTE: each cell's range error wanders far beyond its model (diagnosed, not fixed)

`analysis/real_walk_lte.py` (`LTE.md`). With GPS on throughout, LTE takes `ekf` from p95 1.2 m to 5.5 m. Weak cells (−9 to −11 dB) are gated out on 66 to 92 % of their records; the accepted ones run NIS 0.2 to 2.5. The dongle clock is smooth (drift 82 to 91 m/s, changing 0.6 to 1.3 m/s between fixes, the same moving and still): not the cause.

Within one arc (so ADR-0050's per-arc bias does not apply), each cell's range error against GPS truth, structure function (m), still / moving, all cells:

| Lag | 1 s | 3 s | 10 s | 30 s | 100 s | 300 s |
|---|---|---|---|---|---|---|
| RMS | 49 / 47 | 109 / 104 | 333 / 332 | 986 / 1,054 | 2,037 / 3,653 | 4,050 / 7,639 |
| robust | 20 / 22 | 40 / 32 | 78 / 55 | 140 / 114 | 353 / 996 | 2,427 / 7,305 |
| ADR-0036 (static) | 10, levelling off by 3 s | | | | | |

The strong cells (PCI 220, 132, 268, SNR −7 to +2.5 dB) stay within 15 to 50 m out to 100 s; the weak ones walk hundreds of metres in 10 s and kilometres in 100 s, still and moving alike, without the front end declaring a new arc (PCI 204 sat 14 km off for 90 s in one arc). A per-cell table-position offset is not identifiable from this short loop and is not reported.

GPS cut at 878, 938 and 998 s, `ekf` with LTE, variants (median of 3 cuts at 60 / 120 / 300 s, m; no LTE 23 / 107 / 503):

| Variant | 60 s | 120 s | 300 s | HPL ≥ error | Before cut p95 |
|---|---|---|---|---|---|
| default (ADR-0050) | 103 | 598 | 1,629 | 57–90 % | 6.5 |
| records SNR ≥ −8 dB only | 106 | 510 | 1,555 | 32–77 % | 5.5 |
| without PCI 220 (64 arcs) | 118 | 726 | 1,971 | 19–83 % | 5.7 |
| PCI 220 only | 332 | 1,226 | 1,234 | 63–87 % | 3.9 |
| `arc_bias` off | 57 | 332 | 1,538 | 24–71 % | 6.1 |
| slow error state per cell, 100 m / 30 s | 1,119 | 1,915 | 1,735 | 14–27 % | 2.2 |
| 300 m / 60 s | 897 | 599 | 1,760 | 78–100 % | 1.6 |
| 1,000 m / 100 s | 862 | 1,271 | 1,380 | 51–82 % | 1.3 |
| 3,000 m / 300 s | 317 | 1,136 | 1,315 | 88–100 % | 1.2 |
| SNR ≥ −6 dB + 300 m / 60 s | 255 | 627 | 1,086 | 100 % | 1.3 |
| dongle clock wander 5 m/s/√s | 118 | 1,028 | 1,368 | 43–62 % | 4.2 |
| dongle clock wander 50 m/s/√s | 138 | 1,045 | 1,391 | 51–93 % | 4.0 |
| `q_accel` 0.3 | 65 | 95 | 1,610 | 60–80 % | 5.7 |

No variant beats no LTE. A slow per-cell error state of the measured size makes the filter honest before the cut (p95 1.2 to 1.6 m, as without LTE) but not after it: even one cell alone (PCI 220) pulls the coast off. Variant runs: `analysis/walk_gps_cut.py` `run_one` with the LTE records filtered or the `ekf` options given, on `3493cfb` + `289b702` + `fa5795c` (nav code identical to `main`).

## 3. Cut coverage

`select_cuts` thresholds against this walk (cuts found, at most 20, 60 s apart):

| `MIN_MOVING` | `WALK_BEFORE_S` | horizon 300 s | horizon 120 s |
|---|---|---|---|
| 0.8 (now) | 120 (now) | 3 | 7 |
| 0.8 | 60 | 3 | 8 |
| 0.7 | 60 | 5 | 11 |
| 0.6 | 60 | 9 | 12 |
| 0.6 | 30 | 11 | 13 |

Proposed (TBC): `MIN_MOVING` 0.6 and `WALK_BEFORE_S` 60, giving 9 cuts at 100, 160, 220, 418, 478, 818, 878, 938, 998 s. 120 s of walking was asked because the sim walk's IMU aligned 114 s in; with ADR-0053 the real walk's IMU does not align at all, so it buys nothing here. `relaxed/summary.md`: the 9 cuts given with `--cut-at`.

Median (worst) horizontal error, m, at both settings on this branch:

| Config | Cuts | 60 s | 120 s | 300 s | HPL ≥ error | Before cut p95 |
|---|---|---|---|---|---|---|
| no LTE, `ekf` | 3 (now) | 22.8 (89.6) | 107 (223) | 503 (557) | 100 % | 1.2 |
| no LTE, `ekf` | 9 (relaxed) | 22.8 (89.6) | 76.3 (223) | 358 (557) | 100 % | 1.5 |
| no LTE, `ekf-imu` | 3 / 9 | same as `ekf` | | | | |
| LTE, `ekf` | 3 (now) | 103 (538) | 598 (642) | 1,629 (1,812) | 70 % | 6.3 |
| LTE, `ekf` | 9 (relaxed) | 103 (538) | 642 (3,496) | 1,629 (7,409) | 49 % | 9.5 |

The relaxed cuts include the stops (minute 4 and minutes 11 to 12) inside some windows; the cuts share one recording, so they are not independent draws.
