# GPS cut on a moving session: `20261111-1806-walk-lte` (#214)

Evidence: **replay of a real session**, GPS cut in software (ADR-0015). Analysis at `unknown`; LTE records: --lte-session 20261111-1806-walk-lte-main, front end at `28c313ad`. 5 cuts (100, 418, 495, 818, 1049 s after the first measurement; given with --cut-at), each scored for 300 s. The cuts share one recording: they are not independent draws, and the worst cut is not a 95th percentile.

Truth: the withheld GPS fixes, linear between good fixes at most 2.5 s apart, at every estimate. Good fix: 3D fix, HDOP <= 2, >= 6 satellites used (TBC); 1346 of 1358 fixes (median HDOP 0.8, median satellites used 14.0). The truth carries the fixes' own error (metres), so smaller errors are truth noise. Moving: speed from the fixes >= 0.5 m/s (TBC); 73% of the session with truth. No position, track, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the cuts, worst cut in brackets (m). HPL ≥ error: share of every scored estimate (10 Hz) in the windows.

| Config | 60 s | 120 s | 300 s | p95 0–300 s (worst) | HPL at 300 s | HPL ≥ error | Error > HPL (epochs) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|
| no LTE, ekf | 21.0 (51.2) | 43.6 (161) | 168 (484) | 457 | 16,304 | 100% | 0 / 14976 | 1.4 | 0% |
| LTE, ekf | 150 (378) | 458 (3,496) | 1,941 (8,749) | 8,342 | 1,077 | 42% | 8642 / 14976 | 9.4 | 0% |

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
| no LTE, ekf | 100 | 69% | 51.2 | 156 | 359 | 100% | 0.5 |
| no LTE, ekf | 418 | 76% | 21.0 | 43.6 | 118 | 100% | 1 |
| no LTE, ekf | 495 | 60% | 8.4 | 18.1 | 168 | 100% | 1.1 |
| no LTE, ekf | 818 | 100% | 44.5 | 161 | 484 | 100% | 1.7 |
| no LTE, ekf | 1049 | 77% | 6.1 | 12.3 | 155 | 100% | 1.9 |
| LTE, ekf | 100 | 69% | 59.1 | 91.4 | 578 | 64% | 3.2 |
| LTE, ekf | 418 | 76% | 342 | 3,496 | 3,827 | 12% | 5.8 |
| LTE, ekf | 495 | 60% | 84.5 | 445 | 8,749 | 42% | 6.4 |
| LTE, ekf | 818 | 100% | 378 | 1,102 | 1,015 | 51% | 8.7 |
| LTE, ekf | 1049 | 77% | 150 | 458 | 1,941 | 41% | 10.4 |

Wall time: 47 s.
