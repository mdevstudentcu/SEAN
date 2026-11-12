# Real GPS cut: error after GPS loss on a real session (#214)

Evidence: **replay of a real session, GPS cut in software** (ADR-0015). Session `20261111-0040-static-fullsuite-lte` (front end at `28ec0a2`, analysis at `105e9a3`). Static receiver, outdoors, on the ground; one site; LTE on one carrier (EARFCN 2460), few weak cells. Runs: one per cut time (99, 149, 199, 249, 299 s after the first measurement), each scored for 300 s after its cut. The runs share the same data, so they are not independent: n = 5 cut times of one session.

Truth: the GPS fixes withheld from the filter (1 Hz). Their scatter about the session's GPS mean is 0.73 m rms, 1.25 m p95, 1.46 m max (horizontal): every error below that size is truth noise. No position, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the 5 cuts, worst run in brackets (m). `hold` is the last fix before the cut, held.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–120 s (worst) | p95 0–300 s (worst) | HPL ≥ error | Error > HPL (fixes) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ekf | none | 0.2 (0.8) | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 1.7 | 3.1 | 100% | 0 / 1505 | 0.3 | 0% |
| ekf | told-pr | 66.7 (123) | 126 (225) | 1,001 (1,616) | 4,689 (5,193) | 1,309 | 4,917 | 59% | 622 / 1505 | 6.1 | 0% |
| ekf-measured-sigma | told-pr | 66.7 (123) | 126 (225) | 1,001 (1,616) | 4,689 (5,193) | 1,309 | 4,917 | 59% | 622 / 1505 | 6.1 | 0% |
| ekf-learned-noise | told-pr | 66.7 (123) | 126 (226) | 701 (1,349) | 2,046 (3,323) | 1,023 | 2,947 | 67% | 501 / 1505 | 6.1 | 0% |
| ekf-honest | told-pr | 44.2 (88.1) | 73.0 (114) | 381 (849) | 1,229 (3,262) | 747 | 3,046 | 100% | 0 / 1505 | 0.7 | 0% |
| ekf-arc-settle | told-pr | 58.9 (127) | 113 (313) | 872 (1,467) | 2,133 (4,845) | 1,142 | 4,839 | 62% | 568 / 1505 | 5.8 | 0% |
| ekf-as-told | told-pr | 0.2 (0.8) | 0.2 (239) | 0.7 (575) | 296 (980) | 535 | 1,438 | 100% | 0 / 1505 | 223 | 30% |
| hold | last fix | 0.2 (1.0) | 0.2 (1.2) | 1.2 (1.6) | 1.0 (1.6) | 1.6 | 1.7 | — | — | — | — |

ADR-0034 on these runs (T1 `TBC`: p95 ≤ 25 m for 300 s; fallback ≤ 50 m for 120 s), taken as the worst run's p95 over the window: with this few runs the 95th percentile over runs is the worst run.

| Estimator | LTE | T1 | Fallback |
|---|---|---|---|
| ekf | none | met | met |
| ekf | told-pr | missed | missed |
| ekf-measured-sigma | told-pr | missed | missed |
| ekf-learned-noise | told-pr | missed | missed |
| ekf-honest | told-pr | missed | missed |
| ekf-arc-settle | told-pr | missed | missed |
| ekf-as-told | told-pr | missed | missed |
| hold | last fix | met | met |

## LTE updates and HPL, per row

Error at 120 and 300 s after the cut: median over the cuts (worst run). Error > HPL: share of the withheld fixes over every cut. LTE updates from the cut to the end of the session, summed over the cuts: accepted through the gate / taken unchecked (a cell's first record or a new arc) / rejected by the gate.

| Estimator | LTE | What the filter does with a real capture's LTE | 120 s | 300 s | Error > HPL | HPL held | LTE after the cut: accepted / unchecked / rejected |
|---|---|---|---|---|---|---|---|
| ekf | none | no LTE | 0.4 (2.0) | 1.7 (3.2) | 0.0% | yes | 0 / 0 / 0 |
| ekf | told-pr | ADR-0050 default: sigma retold to ADR-0036's model, a range bias per new arc | 1,001 (1,616) | 4,689 (5,193) | 41.3% | no | 43,554 / 122 / 342 |
| ekf-measured-sigma | told-pr | the same as `ekf` on a real capture (ADR-0044's retelling is what ADR-0050 made the default there) | 1,001 (1,616) | 4,689 (5,193) | 41.3% | no | 43,554 / 122 / 342 |
| ekf-learned-noise | told-pr | `ekf` + range noise learned from innovations (tau 60 s), starting from the retold sigma (ADR-0039 amendment, #156) | 701 (1,349) | 2,046 (3,323) | 33.3% | no | 36,223 / 122 / 252 |
| ekf-honest | told-pr | `ekf-learned-noise` + the slow range error as a state per cell (30 s) + our clock in the ranges (ADR-0046 Proposed, #251) | 381 (849) | 1,229 (3,262) | 0.0% | yes | 7,502 / 122 / 2 |
| ekf-arc-settle | told-pr | `ekf` + a new arc's first 5 s told 10 x sigma (ADR-0050 opt-in c2) | 872 (1,467) | 2,133 (4,845) | 37.7% | no | 43,550 / 122 / 346 |
| ekf-as-told | told-pr | `ekf` before ADR-0050: the front end's own sigma, no bias per arc | 0.7 (575) | 296 (980) | 0.0% | yes | 125 / 6 / 43,887 |

## HPL at the same instants

Median over the cuts (m).

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| ekf | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf | told-pr | 575 | 925 | 830 | 1,260 |
| ekf-measured-sigma | told-pr | 575 | 925 | 830 | 1,260 |
| ekf-learned-noise | told-pr | 575 | 927 | 831 | 1,473 |
| ekf-honest | told-pr | 575 | 1,307 | 3,177 | 9,443 |
| ekf-arc-settle | told-pr | 575 | 912 | 837 | 916 |
| ekf-as-told | told-pr | 606 | 1,569 | 4,241 | 8,920 |

## Where a new LTE arc starts

Each pseudorange arc that starts within 1 s of its cell's last record, against that record (the cell's in-arc rate taken off, whole frames wrapped out). By the new arc's first SNR. Steps only, no range.

| New arc's SNR | Arcs | Step > 100 m | Median of those (m) | Largest (m) |
|---|---|---|---|---|
| ≥ -8 dB | 19 | 5 | 664,475 | 1,192,779 |
| < -8 dB | 0 | 0 | — | — |

## What this can and cannot show

- One static receiver at one site, one carrier, a few weak cells. The truth does not move, so a filter that holds still (`none`, `hold`) is right by construction: its small error says nothing about coasting on a moving drone.
- The cut times share one recording: the runs are not independent draws, and the worst run is not a 95th percentile.
- Tower positions are the committed table's matches (a hypothesis, `pnt.nav.cells`).
- Since ADR-0050 the filter retells a real capture's pseudorange σ itself (except `ekf-calibrated-measured` and `ekf-as-told`), so the `told`, `told-pr` and `adr36` variants differ only in which records they keep, not in σ.
