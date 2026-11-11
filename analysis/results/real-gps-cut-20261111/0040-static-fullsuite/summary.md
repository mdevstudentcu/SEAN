# Real GPS cut: error after GPS loss on a real session (#214)

Evidence: **replay of a real session, GPS cut in software** (ADR-0015). Session `20261111-0040-static-fullsuite-lte` (front end at `f92af3a`, analysis at `f92af3a`). Static receiver, outdoors, on the ground; one site; LTE on one carrier (EARFCN 2460), few weak cells. Runs: one per cut time (99, 149, 199, 249, 299 s after the first measurement), each scored for 300 s after its cut. The runs share the same data, so they are not independent: n = 5 cut times of one session.

Truth: the GPS fixes withheld from the filter (1 Hz). Their scatter about the session's GPS mean is 0.73 m rms, 1.25 m p95, 1.46 m max (horizontal): every error below that size is truth noise. No position, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the 5 cuts, worst run in brackets (m). `hold` is the last fix before the cut, held.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–120 s (worst) | p95 0–300 s (worst) | HPL ≥ error | Error > HPL (fixes) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ekf | none | 0.2 (0.8) | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 1.7 | 3.1 | 100% | 0 / 1505 | 0.3 | 0% |
| ekf | told | 29.9 (250) | 344 (406) | 931 (1,848) | 4,015 (10,165) | 1,691 | 9,539 | 56% | 659 / 1505 | 11.9 | 0% |
| ekf | told-pr | 0.2 (0.8) | 0.2 (390) | 0.5 (851) | 1,426 (2,813) | 775 | 2,639 | 99% | 14 / 1505 | 3.9 | 0% |
| ekf | adr36 | 0.2 (0.8) | 0.2 (557) | 0.5 (1,229) | 2,041 (2,806) | 1,151 | 2,921 | 100% | 0 / 1505 | 1.4 | 0% |
| ekf | adr36-cut8 | 0.2 (0.8) | 0.2 (557) | 0.5 (1,229) | 2,041 (2,806) | 1,151 | 2,921 | 100% | 0 / 1505 | 1.4 | 0% |
| ekf-imu | none | 0.2 (0.8) | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 1.7 | 3.1 | 100% | 0 / 1505 | 0.3 | 0% |
| ekf-imu | told | 36.2 (142) | 291 (360) | 1,500 (2,306) | 8,378 (15,812) | 2,227 | 14,326 | 45% | 830 / 1505 | 18.2 | 0% |
| ekf-imu | told-pr | 8,898 (13,308) | 9,880 (14,558) | 12,682 (17,198) | 20,543 (25,169) | 16,758 | 24,725 | 0% | 1505 / 1505 | 6,427 | 93% |
| ekf-imu | adr36 | 13,153 (19,680) | 14,296 (20,839) | 19,061 (24,236) | 28,454 (34,516) | 23,581 | 33,997 | 0% | 1505 / 1505 | 10,340 | 100% |
| ekf-imu | adr36-cut8 | 13,153 (19,679) | 14,295 (20,838) | 19,061 (24,236) | 28,453 (34,515) | 23,580 | 33,996 | 0% | 1505 / 1505 | 10,340 | 100% |
| ekf-calibrated | none | 0.2 (0.8) | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 1.7 | 3.1 | 100% | 0 / 1505 | 0.3 | 0% |
| ekf-calibrated | told | 46.4 (250) | 310 (406) | 1,195 (2,282) | 6,460 (10,083) | 2,054 | 9,433 | 57% | 653 / 1505 | 7.3 | 0% |
| ekf-calibrated | told-pr | 0.2 (0.8) | 0.2 (319) | 0.5 (845) | 1,365 (2,834) | 770 | 2,622 | 100% | 0 / 1505 | 2.7 | 0% |
| ekf-calibrated | adr36 | 0.2 (0.8) | 0.2 (659) | 0.5 (1,502) | 2,146 (4,876) | 1,404 | 3,810 | 100% | 0 / 1505 | 0.7 | 0% |
| ekf-calibrated | adr36-cut8 | 0.2 (0.8) | 0.2 (659) | 0.5 (1,502) | 2,146 (4,876) | 1,404 | 3,810 | 100% | 0 / 1505 | 0.7 | 0% |
| hold | last fix | 0.2 (1.0) | 0.2 (1.2) | 1.2 (1.6) | 1.0 (1.6) | 1.6 | 1.7 | — | — | — | — |

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
| ekf | told | 575 | 1,288 | 1,092 | 1,942 |
| ekf | told-pr | 606 | 1,569 | 4,241 | 6,391 |
| ekf | adr36 | 606 | 1,569 | 4,241 | 8,962 |
| ekf | adr36-cut8 | 606 | 1,569 | 4,241 | 8,962 |
| ekf-imu | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf-imu | told | 374 | 1,255 | 672 | 4,330 |
| ekf-imu | told-pr | 3,887 | 3,485 | 4,945 | 9,927 |
| ekf-imu | adr36 | 4,238 | 4,717 | 6,362 | 11,199 |
| ekf-imu | adr36-cut8 | 4,238 | 4,717 | 6,362 | 11,199 |
| ekf-calibrated | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf-calibrated | told | 575 | 1,239 | 1,074 | 3,716 |
| ekf-calibrated | told-pr | 606 | 1,569 | 4,241 | 8,047 |
| ekf-calibrated | adr36 | 606 | 1,569 | 4,241 | 8,987 |
| ekf-calibrated | adr36-cut8 | 606 | 1,569 | 4,241 | 8,987 |

## Where a new LTE arc starts

Each pseudorange arc that starts within 1 s of its cell's last record, against that record (the cell's in-arc rate taken off, whole frames wrapped out). By the new arc's first SNR. Steps only, no range.

| New arc's SNR | Arcs | Step > 100 m | Median of those (m) | Largest (m) |
|---|---|---|---|---|
| ≥ -8 dB | 59 | 50 | 770 | 12,102 |
| < -8 dB | 300 | 295 | 792 | 1,484 |

## What this can and cannot show

- One static receiver at one site, one carrier, a few weak cells. The truth does not move, so a filter that holds still (`none`, `hold`) is right by construction: its small error says nothing about coasting on a moving drone.
- The cut times share one recording: the runs are not independent draws, and the worst run is not a 95th percentile.
- Tower positions are the committed table's matches (a hypothesis, `pnt.nav.cells`).
- The `adr36` variants apply a Proposed ADR's σ in this script only; nothing in `src/` changes, and the correlated part ADR-0036 adds (`sigma_corr_m`) is not modelled.
