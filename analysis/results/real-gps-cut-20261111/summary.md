# Real GPS cut: error after GPS loss on a real session (#214)

Evidence: **replay of a real session, GPS cut in software** (ADR-0015). Session `20261111-0151-static-fullsuite2-lte` (front end at `c21e047`, analysis at `0e4147f`). Static receiver, outdoors, on the ground; one site; LTE on one carrier (EARFCN 2460), few weak cells. Runs: one per cut time (100, 150, 200, 250, 300 s after the first measurement), each scored for 300 s after its cut. The runs share the same data, so they are not independent: n = 5 cut times of one session.

Truth: the GPS fixes withheld from the filter (1 Hz). Their scatter about the session's GPS mean is 0.38 m rms, 1.03 m p95, 1.15 m max (horizontal): every error below that size is truth noise. No position, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the 5 cuts, worst run in brackets (m). `hold` is the last fix before the cut, held.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–120 s (worst) | p95 0–300 s (worst) | HPL ≥ error | Error > HPL (fixes) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ekf | none | 0.1 (1.6) | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 6.1 | 15.1 | 100% | 0 / 1505 | 0.1 | 0% |
| ekf | told | 768 (4,585) | 1,703 (5,521) | 4,228 (8,284) | 12,436 (16,531) | 8,009 | 15,759 | 6% | 1422 / 1505 | 202 | 20% |
| ekf | told-pr | 110 (274) | 449 (595) | 1,520 (2,278) | 7,886 (11,919) | 2,069 | 11,047 | 33% | 1009 / 1505 | 6.2 | 0% |
| ekf | adr36 | 0.1 (59.1) | 351 (509) | 1,522 (1,916) | 7,743 (10,799) | 1,725 | 9,783 | 41% | 895 / 1505 | 3.7 | 0% |
| ekf | adr36-cut8 | 0.1 (81.3) | 183 (495) | 1,654 (2,184) | 6,552 (10,248) | 2,037 | 9,318 | 50% | 759 / 1505 | 3.7 | 0% |
| ekf-imu | none | 0.1 (1.6) | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 6.1 | 15.1 | 100% | 0 / 1505 | 0.1 | 0% |
| ekf-imu | told | 787 (3,060) | 1,476 (3,729) | 2,845 (5,135) | 7,883 (10,095) | 4,979 | 9,588 | 0% | 1505 / 1505 | 462 | 47% |
| ekf-imu | told-pr | 78.8 (112) | 472 (743) | 2,302 (3,322) | 7,282 (15,772) | 3,322 | 14,142 | 38% | 935 / 1505 | 15.9 | 0% |
| ekf-imu | adr36 | 54.5 (92.0) | 282 (770) | 3,700 (5,280) | 11,988 (21,967) | 5,005 | 19,958 | 36% | 964 / 1505 | 10.3 | 0% |
| ekf-imu | adr36-cut8 | 38.3 (92.5) | 317 (770) | 3,740 (5,323) | 12,336 (18,413) | 5,040 | 16,921 | 37% | 952 / 1505 | 10.5 | 0% |
| ekf-calibrated | none | 0.1 (1.6) | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 6.1 | 15.1 | 100% | 0 / 1505 | 0.1 | 0% |
| ekf-calibrated | told | 318 (386) | 717 (1,248) | 1,785 (4,080) | 8,333 (10,176) | 3,797 | 9,419 | 20% | 1209 / 1505 | 117 | 19% |
| ekf-calibrated | told-pr | 0.1 (90.3) | 205 (447) | 1,083 (2,344) | 8,526 (9,246) | 1,568 | 8,513 | 50% | 754 / 1505 | 4.8 | 0% |
| ekf-calibrated | adr36 | 0.2 (389) | 298 (977) | 1,409 (3,381) | 11,055 (14,949) | 3,066 | 13,832 | 38% | 926 / 1505 | 3.9 | 0% |
| ekf-calibrated | adr36-cut8 | 0.1 (35.8) | 262 (488) | 1,983 (2,487) | 8,055 (9,522) | 1,959 | 8,811 | 50% | 748 / 1505 | 3.9 | 0% |
| hold | last fix | 0.0 (0.2) | 0.1 (0.2) | 0.3 (0.4) | 0.5 (1.2) | 0.3 | 1.1 | — | — | — | — |

ADR-0034 on these runs (T1 `TBC`: p95 ≤ 25 m for 300 s; fallback ≤ 50 m for 120 s), taken as the worst run's p95 over the window: with this few runs the 95th percentile over runs is the worst run.

| Estimator | LTE | T1 | Fallback |
|---|---|---|---|
| ekf | none | met | met |
| ekf | told | missed | missed |
| ekf | told-pr | missed | missed |
| ekf | adr36 | missed | missed |
| ekf | adr36-cut8 | missed | missed |
| ekf-imu | none | met | met |
| ekf-imu | told | missed | missed |
| ekf-imu | told-pr | missed | missed |
| ekf-imu | adr36 | missed | missed |
| ekf-imu | adr36-cut8 | missed | missed |
| ekf-calibrated | none | met | met |
| ekf-calibrated | told | missed | missed |
| ekf-calibrated | told-pr | missed | missed |
| ekf-calibrated | adr36 | missed | missed |
| ekf-calibrated | adr36-cut8 | missed | missed |
| hold | last fix | met | met |

## HPL at the same instants

Median over the cuts (m).

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| ekf | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf | told | 193 | 625 | 1,446 | 3,630 |
| ekf | told-pr | 590 | 951 | 670 | 3,575 |
| ekf | adr36 | 606 | 1,569 | 1,930 | 3,643 |
| ekf | adr36-cut8 | 606 | 1,569 | 3,977 | 3,464 |
| ekf-imu | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf-imu | told | 223 | 459 | 703 | 3,085 |
| ekf-imu | told-pr | 471 | 1,735 | 1,689 | 4,743 |
| ekf-imu | adr36 | 441 | 1,665 | 1,984 | 5,164 |
| ekf-imu | adr36-cut8 | 442 | 1,683 | 1,980 | 5,404 |
| ekf-calibrated | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf-calibrated | told | 306 | 467 | 603 | 3,598 |
| ekf-calibrated | told-pr | 606 | 1,569 | 2,726 | 3,578 |
| ekf-calibrated | adr36 | 606 | 1,568 | 1,738 | 3,800 |
| ekf-calibrated | adr36-cut8 | 606 | 1,568 | 2,218 | 3,694 |

## Where a new LTE arc starts

Each pseudorange arc that starts within 1 s of its cell's last record, against that record (the cell's in-arc rate taken off, whole frames wrapped out). By the new arc's first SNR. Steps only, no range.

| New arc's SNR | Arcs | Step > 100 m | Median of those (m) | Largest (m) |
|---|---|---|---|---|
| ≥ -8 dB | 103 | 90 | 874 | 5,983 |
| < -8 dB | 351 | 346 | 899 | 1,427 |

## What this can and cannot show

- One static receiver at one site, one carrier, a few weak cells. The truth does not move, so a filter that holds still (`none`, `hold`) is right by construction: its small error says nothing about coasting on a moving drone.
- The cut times share one recording: the runs are not independent draws, and the worst run is not a 95th percentile.
- Tower positions are the committed table's matches (a hypothesis, `pnt.nav.cells`).
- The `adr36` variants apply a Proposed ADR's σ in this script only; nothing in `src/` changes, and the correlated part ADR-0036 adds (`sigma_corr_m`) is not modelled.
