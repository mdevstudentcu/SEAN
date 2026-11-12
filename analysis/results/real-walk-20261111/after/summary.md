# GPS cut on a moving session: `20261111-1806-walk-lte` (#214)

Evidence: **replay of a real session**, GPS cut in software (ADR-0015). Analysis at `3fb854d`; LTE records: --lte-session 20261111-1806-walk-lte-lte, front end at `fa5795c`. 3 cuts (878, 938, 998 s after the first measurement; picked in the moving part: >= 60 s of good GPS before, moving at the cut and >= 80% of the 120 s before and the window), each scored for 300 s. The cuts share one recording: they are not independent draws, and the worst cut is not a 95th percentile.

Truth: the withheld GPS fixes, linear between good fixes at most 2.5 s apart, at every estimate. Good fix: 3D fix, HDOP <= 2, >= 6 satellites used (TBC); 1346 of 1358 fixes (median HDOP 0.8, median satellites used 14.0). The truth carries the fixes' own error (metres), so smaller errors are truth noise. Moving: speed from the fixes >= 0.5 m/s (TBC); 73% of the session with truth. No position, track, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the cuts, worst cut in brackets (m). HPL ≥ error: share of every scored estimate (10 Hz) in the windows.

| Config | 60 s | 120 s | 300 s | p95 0–300 s (worst) | HPL at 300 s | HPL ≥ error | Error > HPL (epochs) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|
| no LTE, ekf | 22.8 (89.6) | 107 (223) | 503 (557) | 538 | 16,304 | 100% | 0 / 9003 | 1.2 | 0% |
| no LTE, ekf-imu | 22.8 (89.6) | 107 (223) | 503 (557) | 538 | 16,304 | 100% | 0 / 9003 | 1.2 | 0% |
| LTE, ekf | 103 (538) | 598 (642) | 1,629 (1,812) | 1,798 | 584 | 70% | 2657 / 9003 | 6.3 | 0% |
| LTE, ekf-imu | 103 (538) | 598 (642) | 1,629 (1,812) | 1,798 | 584 | 70% | 2657 / 9003 | 6.3 | 0% |
| LTE, B (ekf-measured-sigma) | 103 (538) | 598 (642) | 1,629 (1,812) | 1,798 | 584 | 70% | 2657 / 9003 | 6.3 | 0% |

## IMU alignment (`ekf-imu`)

- no LTE, ekf-imu: aligned in 0 of 3 runs, before the cut in 0; aligned at —, —, —.
- LTE, ekf-imu: aligned in 0 of 3 runs, before the cut in 0; aligned at —, —, —.

## LTE cells heard

Lookup (`pnt.nav.cells`, `MAX_RANGE_KM` 10 km of the session origin, TBC): 10 matched. Records of cells not matched are dropped before the filter. Times in s after the first measurement; no ranges.

| Cell | Records | Lookup | Heard from–to (s) | Median SNR (dB) | Arcs |
|---|---|---|---|---|---|
| `lte:2460:220` | 13780 | matched | 1.1–1380 | 2.5 | 64 |
| `lte:2460:204` | 12690 | matched | 11.1–1369.2 | -2.9 | 30 |
| `lte:2460:90` | 9926 | matched | 131.1–1357 | -7.1 | 5 |
| `lte:2460:98` | 9286 | matched | 201.1–1363.6 | -9.7 | 3 |
| `lte:2460:92` | 7025 | matched | 91.1–1359.2 | -10.7 | 5 |
| `lte:2460:106` | 5907 | matched | 131.1–740.8 | -2.9 | 4 |
| `lte:2460:132` | 5144 | matched | 831.1–1360 | -5.6 | 6 |
| `lte:2460:244` | 4754 | matched | 181.1–1358.9 | -9.0 | 2 |
| `lte:2460:212` | 1669 | matched | 461.1–672.1 | -10.0 | 1 |
| `lte:2460:268` | 1537 | matched | 1191.1–1379.4 | -7.3 | 1 |

## Runs

| Config | Cut (s) | Moving share | 60 s | 120 s | 300 s | HPL ≥ error | Run time (s) |
|---|---|---|---|---|---|---|---|
| no LTE, ekf | 878 | 100% | 22.8 | 43.9 | 223 | 100% | 3.4 |
| no LTE, ekf | 938 | 100% | 17.4 | 107 | 503 | 100% | 2.3 |
| no LTE, ekf | 998 | 86% | 89.6 | 223 | 557 | 100% | 2.2 |
| no LTE, ekf-imu | 878 | 100% | 22.8 | 43.9 | 223 | 100% | 5.6 |
| no LTE, ekf-imu | 938 | 100% | 17.4 | 107 | 503 | 100% | 6.6 |
| no LTE, ekf-imu | 998 | 86% | 89.6 | 223 | 557 | 100% | 6.5 |
| LTE, ekf | 878 | 100% | 538 | 598 | 1,070 | 90% | 13.3 |
| LTE, ekf | 938 | 100% | 103 | 642 | 1,629 | 64% | 14.4 |
| LTE, ekf | 998 | 86% | 86.5 | 412 | 1,812 | 57% | 12 |
| LTE, ekf-imu | 878 | 100% | 538 | 598 | 1,070 | 90% | 31 |
| LTE, ekf-imu | 938 | 100% | 103 | 642 | 1,629 | 64% | 31.6 |
| LTE, ekf-imu | 998 | 86% | 86.5 | 412 | 1,812 | 57% | 28.3 |
| LTE, B (ekf-measured-sigma) | 878 | 100% | 538 | 598 | 1,070 | 90% | 16.9 |
| LTE, B (ekf-measured-sigma) | 938 | 100% | 103 | 642 | 1,629 | 64% | 17.8 |
| LTE, B (ekf-measured-sigma) | 998 | 86% | 86.5 | 412 | 1,812 | 57% | 11.6 |

Wall time: 156 s.
