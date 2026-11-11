# GPS cut on a moving session: `sim-handheld-walk` (#214)

Evidence: **sim session (replay)**, GPS cut in software (ADR-0015). Analysis at `0d52214`; LTE records: the session's own /meas/lte. 5 cuts (101, 360, 620, 879, 1139 s after the first measurement; picked in the moving part: >= 60 s of good GPS before, moving at the cut and >= 80% of the 120 s before and the window), each scored for 300 s. The cuts share one recording: they are not independent draws, and the worst cut is not a 95th percentile.

Truth: the withheld GPS fixes, linear between good fixes at most 2.5 s apart, at every estimate. Good fix: 3D fix only (no gpsd SKY reports in this session); 1440 of 1440 fixes (median HDOP —, median satellites used —). The truth carries the fixes' own error (metres), so smaller errors are truth noise. Moving: speed from the fixes >= 0.5 m/s (TBC); 99% of the session with truth. No position, track, origin, range or bearing is given here, only errors.

Sim check of the truth: interpolated fixes against the sim's `/truth`, horizontal, 2.35 m median, 4.89 m p95, 10.35 m max (14391 epochs).

## Horizontal error after the cut

Median over the cuts, worst cut in brackets (m). HPL ≥ error: share of every scored estimate (10 Hz) in the windows.

| Config | 60 s | 120 s | 300 s | p95 0–300 s (worst) | HPL at 300 s | HPL ≥ error | Error > HPL (epochs) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|
| no LTE, ekf | 93.0 (99.9) | 161 (184) | 341 (419) | 390 | 16,215 | 100% | 0 / 15005 | 5.9 | 0% |
| no LTE, ekf-imu | 93.9 (154) | 156 (499) | 3,534 (5,476) | 4,954 | 46,856 | 100% | 0 / 15005 | 5.4 | 0% |
| LTE, ekf | 93.0 (280) | 161 (2,337) | 2,784 (11,470) | 10,593 | 5,279 | 80% | 3034 / 15005 | 5.9 | 0% |
| LTE, ekf-imu | 94.1 (280) | 499 (2,921) | 7,286 (23,432) | 21,266 | 6,752 | 70% | 4545 / 15005 | 5.4 | 0% |
| LTE, B (ekf-measured-sigma) | 88.0 (328) | 66.4 (326) | 83.1 (585) | 960 | 80.8 | 60% | 5951 / 15005 | 5.9 | 0% |

## IMU alignment (`ekf-imu`)

- no LTE, ekf-imu: aligned in 4 of 5 runs, before the cut in 4; aligned at —, 114.1 s, 114.1 s, 114.1 s, 114.1 s.
- LTE, ekf-imu: aligned in 4 of 5 runs, before the cut in 4; aligned at —, 114.1 s, 114.1 s, 114.1 s, 114.1 s.

## LTE cells heard

Lookup (`pnt.nav.cells`, `MAX_RANGE_KM` 10 km of the session origin, TBC): 23 matched, 2 collision. Records of cells not matched are dropped before the filter. Times in s after the first measurement; no ranges.

| Cell | Records | Lookup | Heard from–to (s) | Median SNR (dB) | Arcs |
|---|---|---|---|---|---|
| `lte:2460:300` | 1140 | matched | 0–1439 | -1.1 | 1 |
| `lte:2460:148` | 1110 | matched | 0–1439 | -10.1 | 1 |
| `lte:2460:100` | 762 | matched | 48–1259 | -6.5 | 1 |
| `lte:2460:172` | 638 | matched | 55–1439 | -10.5 | 1 |
| `lte:2460:273` | 631 | matched | 208–1169 | -8.5 | 1 |
| `lte:2460:305` | 537 | matched | 189–860 | -10.7 | 1 |
| `lte:2460:413` | 525 | matched | 180–1169 | -13.8 | 1 |
| `lte:2460:317` | 525 | collision | 190–1169 | -15.2 | 1 |
| `lte:2460:220` | 467 | matched | 126–1169 | -14.8 | 1 |
| `lte:2460:33` | 426 | matched | 130–1169 | -15.9 | 1 |
| `lte:2460:308` | 394 | matched | 19–1439 | -11.7 | 1 |
| `lte:2460:132` | 300 | matched | 150–479 | -13.4 | 1 |
| `lte:2460:9` | 300 | matched | 510–1169 | -16.4 | 1 |
| `lte:2460:313` | 207 | matched | 717–1169 | -14.6 | 1 |
| `lte:2460:106` | 186 | matched | 197–1169 | -17.8 | 1 |
| `lte:2460:281` | 180 | matched | 990–1259 | -12.2 | 1 |
| `lte:2460:201` | 82 | matched | 780–1169 | -15.7 | 1 |
| `lte:2460:159` | 66 | matched | 630–929 | -14.9 | 1 |
| `lte:2460:144` | 60 | matched | 780–929 | -15.8 | 1 |
| `lte:2460:105` | 48 | matched | 780–917 | -17.9 | 1 |
| `lte:2460:192` | 30 | collision | 780–809 | -17.9 | 1 |
| `lte:2460:293` | 30 | matched | 780–809 | -16.8 | 1 |
| `lte:2460:257` | 30 | matched | 1140–1169 | -15.3 | 1 |
| `lte:2460:249` | 15 | matched | 795–809 | -18.8 | 1 |
| `lte:2460:365` | 4 | matched | 900–903 | -16.6 | 1 |

## Runs

| Config | Cut (s) | Moving share | 60 s | 120 s | 300 s | HPL ≥ error | Run time (s) |
|---|---|---|---|---|---|---|---|
| no LTE, ekf | 101 | 100% | 99.9 | 184 | 341 | 100% | 0.7 |
| no LTE, ekf | 360 | 100% | 93.0 | 161 | 216 | 100% | 1.2 |
| no LTE, ekf | 620 | 100% | 49.4 | 124 | 419 | 100% | 1.1 |
| no LTE, ekf | 879 | 100% | 94.9 | 175 | 259 | 100% | 2.1 |
| no LTE, ekf | 1139 | 98% | 79.5 | 158 | 408 | 100% | 1.8 |
| no LTE, ekf-imu | 101 | 100% | 99.9 | 184 | 341 | 100% | 1.3 |
| no LTE, ekf-imu | 360 | 100% | 88.3 | 138 | 3,589 | 100% | 4.6 |
| no LTE, ekf-imu | 620 | 100% | 93.9 | 122 | 2,727 | 100% | 4.2 |
| no LTE, ekf-imu | 879 | 100% | 154 | 499 | 3,534 | 100% | 6.7 |
| no LTE, ekf-imu | 1139 | 98% | 66.7 | 156 | 5,476 | 100% | 6.5 |
| LTE, ekf | 101 | 100% | 280 | 2,337 | 7,286 | 58% | 0.8 |
| LTE, ekf | 360 | 100% | 93.0 | 161 | 11,470 | 68% | 2.3 |
| LTE, ekf | 620 | 100% | 49.4 | 124 | 2,784 | 74% | 3.1 |
| LTE, ekf | 879 | 100% | 94.9 | 175 | 259 | 100% | 2.1 |
| LTE, ekf | 1139 | 98% | 79.5 | 158 | 408 | 100% | 4.9 |
| LTE, ekf-imu | 101 | 100% | 280 | 2,337 | 7,286 | 58% | 1 |
| LTE, ekf-imu | 360 | 100% | 88.2 | 2,921 | 23,432 | 35% | 6.1 |
| LTE, ekf-imu | 620 | 100% | 94.1 | 124 | 1,656 | 69% | 5 |
| LTE, ekf-imu | 879 | 100% | 154 | 499 | 21,825 | 87% | 11.1 |
| LTE, ekf-imu | 1139 | 98% | 66.4 | 155 | 5,508 | 100% | 7.4 |
| LTE, B (ekf-measured-sigma) | 101 | 100% | 24.2 | 66.4 | 61.4 | 67% | 1.5 |
| LTE, B (ekf-measured-sigma) | 360 | 100% | 44.2 | 57.3 | 103 | 53% | 2.6 |
| LTE, B (ekf-measured-sigma) | 620 | 100% | 146 | 46.8 | 64.0 | 48% | 2.2 |
| LTE, B (ekf-measured-sigma) | 879 | 100% | 88.0 | 326 | 83.1 | 49% | 2.4 |
| LTE, B (ekf-measured-sigma) | 1139 | 98% | 328 | 202 | 585 | 84% | 2.8 |

Wall time: 60 s.
