# GPS cut on a moving session: `20261111-0151-static-fullsuite2` (#214)

Evidence: **replay of a real session**, GPS cut in software (ADR-0015). Analysis at `21488c2`; LTE records: 20261111-0151-static-fullsuite2-lte (front end run by this script), front end at `21488c2`. 5 cuts (100, 150, 200, 250, 300 s after the first measurement; given with --cut-at), each scored for 300 s. The cuts share one recording: they are not independent draws, and the worst cut is not a 95th percentile.

Truth: the withheld GPS fixes, linear between good fixes at most 2.5 s apart, at every estimate. Good fix: 3D fix, HDOP <= 2, >= 6 satellites used (TBC); 601 of 601 fixes (median HDOP 0.7, median satellites used 14.0). The truth carries the fixes' own error (metres), so smaller errors are truth noise. Moving: speed from the fixes >= 0.5 m/s (TBC); 0% of the session with truth. No position, track, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the cuts, worst cut in brackets (m). HPL ≥ error: share of every scored estimate (10 Hz) in the windows.

| Config | 60 s | 120 s | 300 s | p95 0–300 s (worst) | HPL at 300 s | HPL ≥ error | Error > HPL (epochs) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|
| no LTE, ekf | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 15.1 | 16,298 | 100% | 0 / 15005 | 0.0 | 0% |
| no LTE, ekf-imu | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 15.1 | 16,298 | 100% | 0 / 15005 | 0.0 | 0% |
| LTE, ekf | 137 (249) | 323 (1,175) | 595 (1,536) | 2,758 | 580 | 76% | 3626 / 15005 | 1.8 | 0% |
| LTE, ekf-imu | 137 (249) | 323 (1,175) | 595 (1,536) | 2,758 | 580 | 76% | 3626 / 15005 | 1.8 | 0% |
| LTE, B (ekf-measured-sigma) | 137 (249) | 323 (1,175) | 595 (1,536) | 2,758 | 580 | 76% | 3626 / 15005 | 1.8 | 0% |
| LTE, ekf before ADR-0050 | 9,792 (12,712) | 12,400 (15,520) | 21,553 (29,463) | 28,259 | 6,462 | 0% | 15005 / 15005 | 7,095 | 100% |

## IMU alignment (`ekf-imu`)

- no LTE, ekf-imu: aligned in 0 of 5 runs, before the cut in 0; aligned at —, —, —, —, —.
- LTE, ekf-imu: aligned in 0 of 5 runs, before the cut in 0; aligned at —, —, —, —, —.

## LTE cells heard

Lookup (`pnt.nav.cells`, `MAX_RANGE_KM` 10 km of the session origin, TBC): 4 matched. Records of cells not matched are dropped before the filter. Times in s after the first measurement; no ranges.

| Cell | Records | Lookup | Heard from–to (s) | Median SNR (dB) | Arcs |
|---|---|---|---|---|---|
| `lte:2460:268` | 5680 | matched | 1–600.2 | 6.5 | 11 |
| `lte:2460:92` | 5446 | matched | 1–600.2 | 7.5 | 30 |
| `lte:2460:204` | 2208 | matched | 21–436.8 | 5.0 | 11 |
| `lte:2460:244` | 2123 | matched | 351.1–565.1 | 6.0 | 3 |

## Runs

| Config | Cut (s) | Moving share | 60 s | 120 s | 300 s | HPL ≥ error | Run time (s) |
|---|---|---|---|---|---|---|---|
| no LTE, ekf | 100 | 0% | 0.2 | 0.4 | 0.6 | 100% | 0.6 |
| no LTE, ekf | 150 | 0% | 0.2 | 0.3 | 0.6 | 100% | 0.6 |
| no LTE, ekf | 200 | 0% | 0.2 | 0.3 | 0.6 | 100% | 0.7 |
| no LTE, ekf | 250 | 0% | 3.2 | 6.5 | 15.9 | 100% | 0.8 |
| no LTE, ekf | 300 | 0% | 0.1 | 0.2 | 1.2 | 100% | 0.9 |
| no LTE, ekf-imu | 100 | 0% | 0.2 | 0.4 | 0.6 | 100% | 1 |
| no LTE, ekf-imu | 150 | 0% | 0.2 | 0.3 | 0.6 | 100% | 1.1 |
| no LTE, ekf-imu | 200 | 0% | 0.2 | 0.3 | 0.6 | 100% | 1.4 |
| no LTE, ekf-imu | 250 | 0% | 3.2 | 6.5 | 15.9 | 100% | 1.6 |
| no LTE, ekf-imu | 300 | 0% | 0.1 | 0.2 | 1.2 | 100% | 1.8 |
| LTE, ekf | 100 | 0% | 249 | 946 | 1,123 | 47% | 2.1 |
| LTE, ekf | 150 | 0% | 203 | 1,175 | 1,536 | 39% | 2.4 |
| LTE, ekf | 200 | 0% | 137 | 323 | 595 | 93% | 2.6 |
| LTE, ekf | 250 | 0% | 101 | 61.9 | 47.7 | 100% | 2.6 |
| LTE, ekf | 300 | 0% | 97.1 | 88.4 | 216 | 100% | 3.1 |
| LTE, ekf-imu | 100 | 0% | 249 | 946 | 1,123 | 47% | 2.5 |
| LTE, ekf-imu | 150 | 0% | 203 | 1,175 | 1,536 | 39% | 3.1 |
| LTE, ekf-imu | 200 | 0% | 137 | 323 | 595 | 93% | 3.4 |
| LTE, ekf-imu | 250 | 0% | 101 | 61.9 | 47.7 | 100% | 3.9 |
| LTE, ekf-imu | 300 | 0% | 97.1 | 88.4 | 216 | 100% | 4.2 |
| LTE, B (ekf-measured-sigma) | 100 | 0% | 249 | 946 | 1,123 | 47% | 1.9 |
| LTE, B (ekf-measured-sigma) | 150 | 0% | 203 | 1,175 | 1,536 | 39% | 2.4 |
| LTE, B (ekf-measured-sigma) | 200 | 0% | 137 | 323 | 595 | 93% | 2.5 |
| LTE, B (ekf-measured-sigma) | 250 | 0% | 101 | 61.9 | 47.7 | 100% | 2.9 |
| LTE, B (ekf-measured-sigma) | 300 | 0% | 97.1 | 88.4 | 216 | 100% | 2.9 |
| LTE, ekf before ADR-0050 | 100 | 0% | 5,622 | 8,447 | 14,375 | 0% | 1.7 |
| LTE, ekf before ADR-0050 | 150 | 0% | 7,972 | 10,242 | 17,247 | 0% | 2 |
| LTE, ekf before ADR-0050 | 200 | 0% | 9,792 | 12,400 | 21,553 | 0% | 2.2 |
| LTE, ekf before ADR-0050 | 250 | 0% | 11,872 | 13,128 | 25,487 | 0% | 2.3 |
| LTE, ekf before ADR-0050 | 300 | 0% | 12,712 | 15,520 | 29,463 | 0% | 2.5 |

Wall time: 99 s.
