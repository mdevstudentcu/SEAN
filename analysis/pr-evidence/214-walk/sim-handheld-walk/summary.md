# GPS cut on a moving session: `sim-handheld-walk` (#214)

Evidence: **sim session (replay)**, GPS cut in software (ADR-0015). Analysis at `e38ca45`; LTE records: the session's own /meas/lte. 5 cuts (60, 330, 599, 869, 1139 s after the first measurement; picked in the moving part: >= 60 s of good GPS before, moving at the cut and >= 60% of the 60 s before and the window), each scored for 300 s. The cuts share one recording: they are not independent draws, and the worst cut is not a 95th percentile.

Truth: the withheld GPS fixes, linear between good fixes at most 2.5 s apart, at every estimate. Good fix: 3D fix only (no gpsd SKY reports in this session); 1440 of 1440 fixes (median HDOP —, median satellites used —). The truth carries the fixes' own error (metres), so smaller errors are truth noise. Moving: speed from the fixes >= 0.5 m/s (TBC); 99% of the session with truth. No position, track, origin, range or bearing is given here, only errors.

Sim check of the truth: interpolated fixes against the sim's `/truth`, horizontal, 2.35 m median, 4.89 m p95, 10.35 m max (14391 epochs).

## Horizontal error after the cut

Median over the cuts, worst cut in brackets (m). HPL ≥ error: share of every scored estimate (10 Hz) in the windows.

| Config | 60 s | 120 s | 300 s | p95 0–300 s (worst) | HPL at 300 s | HPL ≥ error | Error > HPL (epochs) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|
| no LTE, ekf | 46.6 (100) | 116 (181) | 404 (438) | 409 | 16,215 | 100% | 0 / 15005 | 5.8 | 0% |
| no LTE, ekf-imu | 66.7 (100) | 156 (228) | 2,928 (5,476) | 4,954 | 47,190 | 100% | 0 / 15005 | 5.4 | 0% |
| LTE, ekf | 46.6 (100) | 116 (630) | 3,709 (6,657) | 6,517 | 4,260 | 81% | 2797 / 15005 | 5.8 | 0% |
| LTE, ekf-imu | 66.4 (100) | 155 (6,448) | 17,448 (41,241) | 37,754 | 11,413 | 72% | 4273 / 15005 | 5.4 | 0% |
| LTE, B (ekf-measured-sigma) | 87.3 (328) | 100 (332) | 68.3 (585) | 961 | 68.7 | 58% | 6239 / 15005 | 5.9 | 0% |

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
| no LTE, ekf | 60 | 100% | 100 | 181 | 404 | 100% | 0.4 |
| no LTE, ekf | 330 | 100% | 46.6 | 116 | 438 | 100% | 0.7 |
| no LTE, ekf | 599 | 100% | 28.4 | 43.5 | 138 | 100% | 1 |
| no LTE, ekf | 869 | 100% | 20.1 | 36.7 | 159 | 100% | 1.5 |
| no LTE, ekf | 1139 | 98% | 79.5 | 158 | 408 | 100% | 1.7 |
| no LTE, ekf-imu | 60 | 100% | 100 | 181 | 404 | 100% | 0.6 |
| no LTE, ekf-imu | 330 | 100% | 42.0 | 228 | 3,506 | 100% | 2.7 |
| no LTE, ekf-imu | 599 | 100% | 48.1 | 130 | 2,928 | 100% | 4.1 |
| no LTE, ekf-imu | 869 | 100% | 73.8 | 120 | 2,129 | 100% | 5.1 |
| no LTE, ekf-imu | 1139 | 98% | 66.7 | 156 | 5,476 | 100% | 6.4 |
| LTE, ekf | 60 | 100% | 100 | 630 | 6,657 | 80% | 0.7 |
| LTE, ekf | 330 | 100% | 46.6 | 116 | 5,929 | 60% | 1.2 |
| LTE, ekf | 599 | 100% | 28.4 | 43.5 | 3,709 | 67% | 1.7 |
| LTE, ekf | 869 | 100% | 20.1 | 36.7 | 159 | 100% | 2.3 |
| LTE, ekf | 1139 | 98% | 79.5 | 158 | 408 | 100% | 2.8 |
| LTE, ekf-imu | 60 | 100% | 100 | 630 | 6,657 | 80% | 0.9 |
| LTE, ekf-imu | 330 | 100% | 42.1 | 6,448 | 32,008 | 34% | 3.3 |
| LTE, ekf-imu | 599 | 100% | 48.1 | 132 | 41,241 | 53% | 4.8 |
| LTE, ekf-imu | 869 | 100% | 73.6 | 124 | 17,448 | 91% | 6.7 |
| LTE, ekf-imu | 1139 | 98% | 66.4 | 155 | 5,508 | 100% | 7.8 |
| LTE, B (ekf-measured-sigma) | 60 | 100% | 36.9 | 100 | 121 | 70% | 0.7 |
| LTE, B (ekf-measured-sigma) | 330 | 100% | 31.0 | 10.9 | 66.2 | 41% | 1.3 |
| LTE, B (ekf-measured-sigma) | 599 | 100% | 87.3 | 34.6 | 68.3 | 48% | 2.1 |
| LTE, B (ekf-measured-sigma) | 869 | 100% | 91.8 | 332 | 17.6 | 49% | 2.6 |
| LTE, B (ekf-measured-sigma) | 1139 | 98% | 328 | 202 | 585 | 84% | 2.8 |

Wall time: 48 s.
