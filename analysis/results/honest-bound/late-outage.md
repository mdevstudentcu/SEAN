# Late in the outage: what happens to each LTE record (#226)

**sim, every value TBC (ADR-0015, ADR-0030 Proposed, ADR-0046 Proposed).** `challenge-drone-outage`, 1 carrier, seeds 0–199. `python analysis/honest_bound_late.py --seeds 0-199 --jobs 5` at `a5a8ce4` on mac (Python 3.14.6), 8 min. Per-second samples; the counterfactual rows are experiments, not estimators (module docstring).

| Curvature skip | Estimator | s after GPS loss | LTE records | used | rejected by the gate | skipped (curvature) | first of a cell or arc | NEES mean | HPL median (m) | error median (m) | error p95 (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| as registered | `ekf-learned-noise` | 0–100 | 62,910 | 92.7% | 0.3% | 5.6% | 1.3% | 6.3 | 424 | 99 | 438 |
| as registered | `ekf-learned-noise` | 100–200 | 66,664 | 75.6% | 1.6% | 22.0% | 0.8% | 11.7 | 906 | 365 | 1,315 |
| as registered | `ekf-learned-noise` | 200–300 | 57,414 | 63.5% | 0.4% | 35.7% | 0.4% | 6.2 | 1,222 | 371 | 1,891 |
| as registered | `ekf-learned-noise` | 300–400 | 67,451 | 62.3% | 0.7% | 36.7% | 0.3% | 7.1 | 1,683 | 582 | 2,959 |
| as registered | `ekf-learned-noise` | 400–500 | 59,225 | 56.3% | 0.6% | 42.8% | 0.4% | 6.3 | 2,175 | 664 | 3,879 |
| as registered | `ekf-learned-noise` | 500–600 | 59,876 | 55.4% | 0.2% | 44.2% | 0.2% | 4.0 | 3,111 | 633 | 4,777 |
| as registered | `ekf-honest` | 0–100 | 62,910 | 91.8% | 0.6% | 6.3% | 1.3% | 3.5 | 495 | 103 | 391 |
| as registered | `ekf-honest` | 100–200 | 66,664 | 72.0% | 0.7% | 26.6% | 0.8% | 5.0 | 1,136 | 329 | 1,182 |
| as registered | `ekf-honest` | 200–300 | 57,414 | 56.2% | 0.3% | 43.1% | 0.4% | 2.8 | 1,728 | 401 | 1,734 |
| as registered | `ekf-honest` | 300–400 | 67,451 | 54.2% | 0.4% | 45.2% | 0.3% | 3.0 | 3,146 | 777 | 2,826 |
| as registered | `ekf-honest` | 400–500 | 59,225 | 41.8% | 0.2% | 57.7% | 0.4% | 2.4 | 7,107 | 885 | 3,694 |
| as registered | `ekf-honest` | 500–600 | 59,876 | 38.0% | 0.0% | 61.8% | 0.2% | 1.6 | 12,271 | 1,332 | 4,537 |
| off | `ekf-learned-noise` | 0–100 | 62,910 | 98.3% | 0.5% | 0.0% | 1.3% | 6.7 | 421 | 99 | 412 |
| off | `ekf-learned-noise` | 100–200 | 66,664 | 95.6% | 3.6% | 0.0% | 0.8% | 22.8 | 740 | 354 | 1,384 |
| off | `ekf-learned-noise` | 200–300 | 57,414 | 97.7% | 1.9% | 0.0% | 0.4% | 17.8 | 801 | 244 | 1,358 |
| off | `ekf-learned-noise` | 300–400 | 67,451 | 97.6% | 2.1% | 0.0% | 0.3% | 16.9 | 799 | 265 | 1,439 |
| off | `ekf-learned-noise` | 400–500 | 59,225 | 98.4% | 1.3% | 0.0% | 0.4% | 16.2 | 933 | 289 | 1,215 |
| off | `ekf-learned-noise` | 500–600 | 59,876 | 98.9% | 0.9% | 0.0% | 0.2% | 11.1 | 881 | 236 | 1,272 |
| off | `ekf-honest` | 0–100 | 62,910 | 98.0% | 0.8% | 0.0% | 1.3% | 3.7 | 494 | 101 | 353 |
| off | `ekf-honest` | 100–200 | 66,664 | 95.3% | 4.0% | 0.0% | 0.8% | 15.2 | 890 | 359 | 1,329 |
| off | `ekf-honest` | 200–300 | 57,414 | 97.8% | 1.8% | 0.0% | 0.4% | 9.4 | 1,015 | 259 | 1,201 |
| off | `ekf-honest` | 300–400 | 67,451 | 97.4% | 2.3% | 0.0% | 0.3% | 10.9 | 983 | 283 | 1,357 |
| off | `ekf-honest` | 400–500 | 59,225 | 98.2% | 1.5% | 0.0% | 0.4% | 9.8 | 1,130 | 290 | 1,126 |
| off | `ekf-honest` | 500–600 | 59,876 | 99.1% | 0.6% | 0.0% | 0.2% | 5.9 | 1,173 | 227 | 1,208 |
| x4 | `ekf-learned-noise` | 0–100 | 62,910 | 96.1% | 0.4% | 2.2% | 1.3% | 6.7 | 421 | 99 | 423 |
| x4 | `ekf-learned-noise` | 100–200 | 66,664 | 88.5% | 3.0% | 7.7% | 0.8% | 19.4 | 777 | 343 | 1,339 |
| x4 | `ekf-learned-noise` | 200–300 | 57,414 | 83.2% | 1.3% | 15.1% | 0.4% | 15.4 | 873 | 279 | 1,590 |
| x4 | `ekf-learned-noise` | 300–400 | 67,451 | 85.1% | 1.6% | 13.1% | 0.3% | 14.8 | 916 | 312 | 2,256 |
| x4 | `ekf-learned-noise` | 400–500 | 59,225 | 79.6% | 0.8% | 19.3% | 0.4% | 14.0 | 1,069 | 352 | 2,882 |
| x4 | `ekf-learned-noise` | 500–600 | 59,876 | 79.3% | 0.4% | 20.0% | 0.2% | 10.1 | 1,077 | 292 | 3,490 |
| x4 | `ekf-honest` | 0–100 | 62,910 | 95.4% | 0.7% | 2.6% | 1.3% | 3.7 | 494 | 101 | 363 |
| x4 | `ekf-honest` | 100–200 | 66,664 | 86.0% | 3.0% | 10.2% | 0.8% | 11.3 | 937 | 333 | 1,279 |
| x4 | `ekf-honest` | 200–300 | 57,414 | 79.7% | 0.9% | 18.9% | 0.4% | 6.3 | 1,141 | 265 | 1,431 |
| x4 | `ekf-honest` | 300–400 | 67,451 | 81.6% | 1.3% | 16.9% | 0.3% | 6.5 | 1,172 | 328 | 2,101 |
| x4 | `ekf-honest` | 400–500 | 59,225 | 75.0% | 0.9% | 23.7% | 0.4% | 5.7 | 1,429 | 356 | 2,569 |
| x4 | `ekf-honest` | 500–600 | 59,876 | 73.5% | 0.3% | 26.0% | 0.2% | 3.3 | 1,487 | 295 | 3,391 |

| Curvature skip | Estimator | above HPL, GPS loss to its end (per second) | worst run | p95 worst over the outage (m) | median at 600 s (m) |
|---|---|---|---|---|---|
| as registered | `ekf-learned-noise` | 2.30% | 26.8% | 5,180 | 642 |
| as registered | `ekf-honest` | 0.47% | 20.1% | 4,900 | 1,554 |
| off | `ekf-learned-noise` | 6.13% | 84.5% | 1,761 | 302 |
| off | `ekf-honest` | 3.27% | 84.5% | 1,606 | 286 |
| x4 | `ekf-learned-noise` | 4.83% | 84.5% | 3,740 | 351 |
| x4 | `ekf-honest` | 2.07% | 84.5% | 3,632 | 360 |
