# Real GPS cut: error after GPS loss on a real session (#214)

Evidence: **replay of a real session, GPS cut in software** (ADR-0015). Session `20261111-1937-static-fullsuite3-lte` (front end at `fcafe6b`, analysis at `fcafe6b`). Static receiver, outdoors, on the ground; one site; LTE on one carrier (EARFCN 2460), few weak cells. Runs: one per cut time (99, 149, 199, 249, 299 s after the first measurement), each scored for 300 s after its cut. The runs share the same data, so they are not independent: n = 5 cut times of one session.

Truth: the GPS fixes withheld from the filter (1 Hz). Their scatter about the session's GPS mean is 1.86 m rms, 3.45 m p95, 3.52 m max (horizontal): every error below that size is truth noise. No position, origin, range or bearing is given here, only errors.

## Horizontal error after the cut

Median over the 5 cuts, worst run in brackets (m). `hold` is the last fix before the cut, held.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–120 s (worst) | p95 0–300 s (worst) | HPL ≥ error | Error > HPL (fixes) | Before cut: p95 | Before cut: GNSS excluded |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ekf | none | 0.9 (3.6) | 0.8 (5.7) | 1.6 (9.6) | — (—) | 9.1 | 19.3 | 100% | 0 / 1500 | 0.2 | 0% |
| ekf | told-pr | 107 (171) | 145 (344) | 255 (1,246) | — (—) | 1,014 | 2,586 | 73% | 403 / 1500 | 10.1 | 0% |
| ekf-measured-sigma | told-pr | 107 (171) | 145 (344) | 255 (1,246) | — (—) | 1,014 | 2,586 | 73% | 403 / 1500 | 10.1 | 0% |
| ekf-learned-noise | told-pr | 107 (171) | 145 (344) | 255 (1,247) | — (—) | 1,013 | 2,589 | 73% | 401 / 1500 | 10.1 | 0% |
| ekf-honest | told-pr | 71.5 (95.5) | 128 (227) | 150 (326) | — (—) | 372 | 696 | 100% | 0 / 1500 | 2.4 | 0% |
| ekf-arc-settle | told-pr | 96.1 (150) | 207 (354) | 217 (433) | — (—) | 591 | 728 | 96% | 55 / 1500 | 10.4 | 0% |
| ekf-as-told | told-pr | 1.0 (3.6) | 2.1 (5.7) | 4.5 (9.6) | — (—) | 9.1 | 19.3 | 100% | 0 / 1500 | 48.9 | 4% |
| hold | last fix | 1.0 (1.6) | 1.9 (2.3) | 2.0 (3.9) | — (—) | 3.8 | 4.2 | — | — | — | — |

ADR-0034 on these runs (T1 `TBC`: p95 ≤ 25 m for 300 s; fallback ≤ 50 m for 120 s), taken as the worst run's p95 over the window: with this few runs the 95th percentile over runs is the worst run.

| Estimator | LTE | T1 | Fallback |
|---|---|---|---|
| ekf | none | met | met |
| ekf | told-pr | missed | missed |
| ekf-measured-sigma | told-pr | missed | missed |
| ekf-learned-noise | told-pr | missed | missed |
| ekf-honest | told-pr | missed | missed |
| ekf-arc-settle | told-pr | missed | missed |
| ekf-as-told | told-pr | met | met |
| hold | last fix | met | met |

## LTE updates and HPL, per row

Error at 120 and 300 s after the cut: median over the cuts (worst run). Error > HPL: share of the withheld fixes over every cut. LTE updates from the cut to the end of the session, summed over the cuts: accepted through the gate / taken unchecked (a cell's first record or a new arc) / rejected by the gate.

| Estimator | LTE | What the filter does with a real capture's LTE | 120 s | 300 s | Error > HPL | HPL held | LTE after the cut: accepted / unchecked / rejected |
|---|---|---|---|---|---|---|---|
| ekf | none | no LTE | 1.6 (9.6) | — (—) | 0.0% | yes | 0 / 0 / 0 |
| ekf | told-pr | ADR-0050 default: sigma retold to ADR-0036's model, a range bias per new arc | 255 (1,246) | — (—) | 26.9% | no | 69,193 / 95 / 50 |
| ekf-measured-sigma | told-pr | the same as `ekf` on a real capture (ADR-0044's retelling is what ADR-0050 made the default there) | 255 (1,246) | — (—) | 26.9% | no | 69,193 / 95 / 50 |
| ekf-learned-noise | told-pr | `ekf` + range noise learned from innovations (tau 60 s), starting from the retold sigma (ADR-0039 amendment, #156) | 255 (1,247) | — (—) | 26.7% | no | 69,193 / 95 / 50 |
| ekf-honest | told-pr | `ekf-learned-noise` + the slow range error as a state per cell (30 s) + our clock in the ranges (ADR-0046 Proposed, #251) | 150 (326) | — (—) | 0.0% | yes | 68,905 / 95 / 0 |
| ekf-arc-settle | told-pr | `ekf` + a new arc's first 5 s told 10 x sigma (ADR-0050 opt-in c2) | 217 (433) | — (—) | 3.7% | no | 69,243 / 95 / 0 |
| ekf-as-told | told-pr | `ekf` before ADR-0050: the front end's own sigma, no bias per arc | 4.5 (9.6) | — (—) | 0.0% | yes | 0 / 0 / 69,338 |

## HPL at the same instants

Median over the cuts (m).

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| ekf | none | 695 | 1,689 | 4,406 | — |
| ekf | told-pr | 254 | 341 | 395 | — |
| ekf-measured-sigma | told-pr | 254 | 341 | 395 | — |
| ekf-learned-noise | told-pr | 254 | 341 | 396 | — |
| ekf-honest | told-pr | 536 | 1,076 | 1,705 | — |
| ekf-arc-settle | told-pr | 297 | 412 | 433 | — |
| ekf-as-told | told-pr | 695 | 1,689 | 4,406 | — |

## Where a new LTE arc starts

Each pseudorange arc that starts within 1 s of its cell's last record, against that record (the cell's in-arc rate taken off, whole frames wrapped out). By the new arc's first SNR. Steps only, no range.

| New arc's SNR | Arcs | Step > 100 m | Median of those (m) | Largest (m) |
|---|---|---|---|---|
| ≥ -8 dB | 20 | 3 | 260,646 | 1,062,993 |
| < -8 dB | 0 | 0 | — | — |

## What this can and cannot show

- One static receiver at one site, one carrier, a few weak cells. The truth does not move, so a filter that holds still (`none`, `hold`) is right by construction: its small error says nothing about coasting on a moving drone.
- The cut times share one recording: the runs are not independent draws, and the worst run is not a 95th percentile.
- Tower positions are the committed table's matches (a hypothesis, `pnt.nav.cells`).
- Since ADR-0050 the filter retells a real capture's pseudorange σ itself (except `ekf-calibrated-measured` and `ekf-as-told`), so the `told`, `told-pr` and `adr36` variants differ only in which records they keep, not in σ.
