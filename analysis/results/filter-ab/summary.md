# Filter A/B on real cuts and the sim drone leg (#286)

Draft written **before the held-out data was opened**: the protocol, the selection rule and the tuning tables. Held-out results, stress rows and the bars are added below once run.

## Protocol (fixed in advance)

- **Tuning data:** real session `20261111-0040-static-fullsuite` (GPS cut in software at 99, 149, 199, 249, 299 s; scored 300 s against the withheld 1 Hz fixes) and sim seeds 100–109 on `challenge-drone-outage` (1 carrier, `1c`) and `challenge-drone-hop-outage` (13 carriers, `13c`).
- **Held out, not run while choosing:** real session `20261111-1937-static-fullsuite3` and sim seeds 0–49 on both legs. Read before choosing: #283's committed summary and `diagnosis.json` of `1937` (cells heard, double-difference spreads, the existing filters' numbers), which the issue already quoted. No arm of this study was run on `1937` or on seeds 0–49 before the selection below was committed.
- **Control:** `ekf-honest` as registered on this branch. Always shown: no LTE, `main`'s default `ekf`, `ekf-learned-noise`.
- **Harness:** `analysis/filter_ab.py` (scoring from `real_gps_cut.py` and `stacked_fixes.py`; tightness as `honest_bound.py`, #226). Real error at an instant: the withheld fix on it, else the nearest within 0.5 s (`15baf6d`); on `0040` every row of #283's table reproduces exactly.

## Selection rule (fixed before held-out data)

Among arms and combinations, prefer the one that on tuning data
(a) keeps error above HPL at 1 % or less of withheld fixes (real) and of epochs from GPS loss (sim, both legs), then
(b) minimises real error at 300 s (median over cuts), subject to
(c) sim worst-second p95 on seeds 100–109 no more than 5 % worse than the control on both legs (both windows, 0–120 and 0–300 s) and 0 hazardous epochs.
Ties: fewer new settings. If no arm passes, the control stays the winner.

## Tuning: single arms (commit `9c33c57`)

Real `0040`: error median (worst) over the five cuts, m; HPL median, m.

| Row | 60 s | 120 s | 300 s | p95 0–300 s (worst cut) | Error > HPL | HPL 120 s | HPL 300 s | LTE after cut: accepted / unchecked / rejected | Speed after cut (m/s) |
|---|---|---|---|---|---|---|---|---|---|
| no-lte | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 3.1 | 0.0% (0 of 1,505) | 4,241 | 16,298 | – | 0.01 |
| ekf | 126 (225) | 1,001 (1,616) | 4,689 (5,193) | 4,917 | 41.3% (622 of 1,505) | 830 | 1,260 | 43,554 / 122 / 342 | 10.54 |
| ekf-learned-noise | 126 (226) | 701 (1,349) | 2,046 (3,323) | 2,947 | 33.3% (501 of 1,505) | 831 | 1,473 | 36,223 / 122 / 252 | 10.20 |
| control | 73.0 (114) | 381 (849) | 1,229 (3,262) | 3,046 | 0.0% (0 of 1,505) | 3,177 | 9,443 | 7,502 / 122 / 2 | 4.61 |
| slow50-tau60 | 81.6 (163) | 484 (1,349) | 1,266 (2,096) | 2,806 | 13.5% (203 of 1,505) | 1,374 | 7,656 | 14,693 / 122 / 63 | 4.83 |
| slow50-tau300 | 96.3 (206) | 510 (1,364) | 1,698 (3,132) | 2,711 | 26.5% (399 of 1,505) | 873 | 1,453 | 35,630 / 122 / 252 | 7.47 |
| slow100-tau60 | 82.7 (128) | 400 (1,380) | 1,249 (2,470) | 2,596 | 10.4% (156 of 1,505) | 2,876 | 8,465 | 13,622 / 122 / 63 | 5.19 |
| slow100-tau300 | 86.0 (168) | 503 (1,378) | 1,324 (2,047) | 2,838 | 13.5% (203 of 1,505) | 1,387 | 7,507 | 14,835 / 122 / 63 | 5.88 |
| slow150-tau60 | 71.1 (130) | 397 (931) | 1,248 (4,040) | 3,764 | 0.0% (0 of 1,505) | 3,309 | 9,542 | 7,335 / 122 / 2 | 5.24 |
| slow150-tau300 | 88.0 (142) | 480 (1,396) | 1,019 (2,308) | 2,738 | 12.4% (187 of 1,505) | 1,539 | 8,129 | 14,487 / 122 / 63 | 3.45 |
| imu | 73.0 (114) | 381 (849) | 1,229 (3,262) | 3,046 | 0.0% (0 of 1,505) | 3,177 | 9,443 | 7,502 / 122 / 2 | 4.61 |
| q0.3 | 26.0 (32.6) | 144 (426) | 583 (2,498) | 2,348 | 6.2% (94 of 1,505) | 1,196 | 1,562 | 38,133 / 122 / 254 | 1.63 |
| q0.1 | 5.1 (6.9) | 23.9 (50.9) | 155 (383) | 338 | 0.0% (0 of 1,505) | 442 | 1,226 | 43,581 / 122 / 315 | 0.33 |
| cells3 | 0.6 (74.4) | 1.3 (153) | 4.0 (440) | 414 | 0.0% (0 of 1,505) | 4,184 | 11,153 | 2,673 / 52 / 0 | 0.02 |
| cells4 | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 3.1 | 0.0% (0 of 1,505) | 4,241 | 14,162 | 0 / 35 / 0 | 0.01 |
| hdop3 | 0.6 (74.4) | 1.3 (153) | 4.0 (440) | 414 | 0.0% (0 of 1,505) | 4,184 | 11,153 | 2,673 / 52 / 0 | 0.02 |
| cells3-clock | 0.6 (74.8) | 42.1 (220) | 682 (917) | 860 | 0.0% (0 of 1,505) | 4,182 | 10,937 | 23,650 / 122 / 315 | 1.87 |
| huber1.5 | 73.0 (114) | 381 (847) | 1,229 (3,253) | 3,037 | 0.0% (0 of 1,505) | 3,179 | 9,443 | 7,502 / 122 / 2 | 4.61 |
| huber2.5 | 73.0 (114) | 381 (849) | 1,229 (3,262) | 3,046 | 0.0% (0 of 1,505) | 3,177 | 9,443 | 7,502 / 122 / 2 | 4.61 |
| freeze | 63.9 (113) | 381 (1,218) | 1,200 (2,998) | 2,889 | 5.2% (78 of 1,505) | 2,985 | 8,599 | 13,584 / 122 / 63 | 4.56 |
| common-step | 70.4 (119) | 378 (851) | 1,244 (3,262) | 3,046 | 0.0% (0 of 1,505) | 3,170 | 9,440 | 7,498 / 120 / 2 | 4.54 |

Sim seeds 100–109 (sim, every value `TBC`): worst-second p95 of the across-run 95th percentile, m; share of epochs above HPL from GPS loss; hazardous epochs; tightness (median HPL / p95 error, median over 0–300 s).

| Row | 1c: worst-second p95 0–120 / 0–300 s (m) | 1c: above HPL | 1c: hazardous | 1c: tightness | 13c: worst-second p95 0–120 / 0–300 s (m) | 13c: above HPL | 13c: hazardous | 13c: tightness |
|---|---|---|---|---|---|---|---|---|
| ekf | 3,137 / 8,189 | 39.03% | 59 | 0.69 | 3,359 / 9,911 | 57.70% | 168 | 0.30 |
| ekf-learned-noise | 648 / 1,780 | 2.69% | 0 | 0.92 | 145 / 145 | 0.00% | 0 | 2.04 |
| control | 505 / 1,256 | 0.00% | 0 | 1.25 | 141 / 141 | 0.02% | 0 | 1.95 |
| slow50-tau60 | 665 / 1,668 | 1.64% | 0 | 1.21 | 129 / 149 | 0.00% | 0 | 2.25 |
| slow50-tau300 | 736 / 1,865 | 2.84% | 0 | 1.02 | 128 / 132 | 0.00% | 0 | 2.35 |
| slow100-tau60 | 704 / 2,036 | 0.00% | 0 | 2.81 | 103 / 132 | 0.00% | 0 | 3.09 |
| slow100-tau300 | 704 / 1,445 | 1.56% | 0 | 1.64 | 116 / 155 | 0.00% | 0 | 2.67 |
| slow150-tau60 | 715 / 1,638 | 0.00% | 0 | 4.23 | 91.3 / 141 | 0.00% | 0 | 3.98 |
| slow150-tau300 | 613 / 1,729 | 0.00% | 0 | 2.23 | 116 / 151 | 0.00% | 0 | 2.94 |
| imu | 625 / 1,307 | 1.37% | 0 | 1.40 | 120 / 120 | 0.13% | 0 | 1.84 |
| q0.3 | 811 / 2,140 | 25.50% | 33 | 0.63 | 182 / 249 | 10.84% | 54 | 1.02 |
| q0.1 | 1,203 / 2,450 | 87.59% | 1,519 | 0.28 | 350 / 350 | 80.48% | 1,669 | 0.51 |
| cells3 | 1,681 / 5,765 | 0.00% | 0 | 0.89 | 142 / 149 | 0.01% | 0 | 1.89 |
| cells4 | 1,103 / 2,378 | 0.00% | 0 | 3.76 | 140 / 145 | 0.01% | 0 | 1.91 |
| hdop3 | 1,176 / 2,566 | 0.00% | 0 | 3.39 | 785 / 1,911 | 0.00% | 0 | 0.20 |
| cells3-clock | 1,411 / 2,564 | 14.98% | 0 | 0.73 | 145 / 145 | 0.02% | 0 | 1.95 |
| huber1.5 | 582 / 3,298 | 5.03% | 0 | 0.63 | 126 / 127 | 0.00% | 0 | 2.11 |
| huber2.5 | 563 / 1,656 | 2.43% | 0 | 0.95 | 136 / 136 | 0.00% | 0 | 2.04 |
| freeze | 439 / 1,336 | 0.18% | 0 | 1.17 | 127 / 142 | 0.03% | 0 | 1.92 |
| common-step | 505 / 1,256 | 0.00% | 0 | 1.25 | 141 / 141 | 0.02% | 0 | 1.95 |
| no-lte | 1,258 / 2,729 | 0.00% | 0 | 4.18 | 1,258 / 2,729 | 0.00% | 0 | 4.18 |

## Tuning: combination round (commit `33e66b0`)

Arms dropped from combinations after the single-arm table: IMU propagation (never aligns on a static receiver: identical to the control on real data), Huber (no effect: the control rejects 2 updates), the shared reset (no effect), lower `q_accel` (error above HPL 25–88 % on sim). Added: a per-cell consistency gate (a cell whose normalised innovations over the last 30/60/120 s of trusted GNSS have an RMS above 2/3/4 model sigmas may update position only with 3 cells heard, `cells3`, or not at all, `skip`); the cell gate counted over 3 and 5 s; curvature inflation (a range too curved for the linear update is kept with R grown by the term instead of dropped).

| Row | 60 s | 120 s | 300 s | p95 0–300 s (worst cut) | Error > HPL | HPL 120 s | HPL 300 s | LTE after cut: accepted / unchecked / rejected | Speed after cut (m/s) |
|---|---|---|---|---|---|---|---|---|---|
| control | 73.0 (114) | 381 (849) | 1,229 (3,262) | 3,046 | 0.0% (0 of 1,505) | 3,177 | 9,443 | 7,502 / 122 / 2 | 4.61 |
| cells3 | 0.6 (74.4) | 1.3 (153) | 4.0 (440) | 414 | 0.0% (0 of 1,505) | 4,184 | 11,153 | 2,673 / 52 / 0 | 0.02 |
| consist30-k2-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist30-k2-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist30-k3-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist30-k3-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist30-k4-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist30-k4-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist60-k2-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist60-k2-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist60-k3-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist60-k3-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist60-k4-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist60-k4-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist120-k2-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist120-k2-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist120-k3-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist120-k3-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| consist120-k4-cells3 | 81.7 (114) | 385 (534) | 971 (1,283) | 1,205 | 0.0% (0 of 1,505) | 3,311 | 8,740 | 7,469 / 112 / 0 | 4.43 |
| consist120-k4-skip | 81.7 (350) | 422 (708) | 1,219 (3,114) | 2,914 | 0.0% (0 of 1,505) | 3,319 | 10,095 | 7,082 / 100 / 0 | 4.43 |
| cells3-w3 | 0.6 (74.4) | 36.4 (153) | 122 (440) | 414 | 0.0% (0 of 1,505) | 4,173 | 11,153 | 2,689 / 52 / 0 | 0.48 |
| cells3-w5 | 0.6 (74.4) | 115 (638) | 137 (2,166) | 2,030 | 0.0% (0 of 1,505) | 4,166 | 11,153 | 2,696 / 52 / 0 | 1.01 |
| cells4-w3 | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 3.1 | 0.0% (0 of 1,505) | 4,241 | 14,162 | 0 / 35 / 0 | 0.01 |
| cells4-w5 | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 3.1 | 0.0% (0 of 1,505) | 4,241 | 14,162 | 0 / 35 / 0 | 0.01 |
| curv | 73.0 (114) | 489 (1,228) | 2,349 (2,998) | 2,903 | 18.4% (277 of 1,505) | 1,360 | 2,623 | 43,581 / 122 / 315 | 5.50 |
| cells3+slow150-tau60 | 0.6 (64.7) | 1.3 (116) | 3.9 (317) | 299 | 0.0% (0 of 1,505) | 4,184 | 11,168 | 2,673 / 52 / 0 | 0.02 |
| cells3+freeze | 0.6 (74.4) | 1.3 (162) | 4.0 (467) | 440 | 0.0% (0 of 1,505) | 4,184 | 11,153 | 2,673 / 52 / 0 | 0.02 |
| cells3+curv | 0.6 (74.4) | 1.1 (153) | 950 (1,882) | 1,830 | 2.7% (40 of 1,505) | 4,184 | 3,168 | 22,594 / 52 / 7,545 | 1.01 |
| cells3-w3+curv | 0.6 (74.4) | 38.2 (153) | 1,003 (1,812) | 1,773 | 3.6% (54 of 1,505) | 4,164 | 3,146 | 22,774 / 52 / 7,545 | 1.01 |
| cells3-w5+curv | 0.6 (74.4) | 115 (604) | 1,677 (2,371) | 2,217 | 8.2% (123 of 1,505) | 3,846 | 3,831 | 22,909 / 52 / 7,545 | 1.60 |

| Row | 1c: worst-second p95 0–120 / 0–300 s (m) | 1c: above HPL | 1c: hazardous | 1c: tightness | 13c: worst-second p95 0–120 / 0–300 s (m) | 13c: above HPL | 13c: hazardous | 13c: tightness |
|---|---|---|---|---|---|---|---|---|
| control | 505 / 1,256 | 0.00% | 0 | 1.25 | 141 / 141 | 0.02% | 0 | 1.95 |
| cells3 | 1,681 / 5,765 | 0.00% | 0 | 0.89 | 142 / 149 | 0.01% | 0 | 1.89 |
| consist30-k2-cells3 | 695 / 1,751 | 0.00% | 0 | 1.37 | 143 / 150 | 0.00% | 0 | 1.93 |
| consist30-k2-skip | 782 / 2,109 | 0.00% | 0 | 4.02 | 1,261 / 2,736 | 0.00% | 0 | 4.17 |
| consist30-k3-cells3 | 695 / 1,751 | 0.00% | 0 | 1.37 | 143 / 150 | 0.00% | 0 | 1.93 |
| consist30-k3-skip | 782 / 2,109 | 0.00% | 0 | 4.02 | 1,261 / 2,736 | 0.00% | 0 | 4.17 |
| consist30-k4-cells3 | 695 / 1,751 | 0.00% | 0 | 1.37 | 143 / 150 | 0.00% | 0 | 1.93 |
| consist30-k4-skip | 782 / 2,109 | 0.00% | 0 | 4.02 | 1,261 / 2,736 | 0.00% | 0 | 4.17 |
| consist60-k2-cells3 | 695 / 1,751 | 0.00% | 0 | 1.32 | 143 / 151 | 0.00% | 0 | 1.93 |
| consist60-k2-skip | 781 / 2,109 | 0.00% | 0 | 4.02 | 787 / 2,136 | 0.09% | 0 | 2.27 |
| consist60-k3-cells3 | 695 / 1,751 | 0.00% | 0 | 1.32 | 143 / 151 | 0.00% | 0 | 1.93 |
| consist60-k3-skip | 781 / 2,109 | 0.00% | 0 | 4.02 | 787 / 2,136 | 0.09% | 0 | 2.27 |
| consist60-k4-cells3 | 695 / 1,751 | 0.00% | 0 | 1.32 | 143 / 151 | 0.00% | 0 | 1.93 |
| consist60-k4-skip | 781 / 2,109 | 0.00% | 0 | 4.02 | 787 / 2,136 | 0.09% | 0 | 2.27 |
| consist120-k2-cells3 | 695 / 1,751 | 0.00% | 0 | 1.32 | 143 / 151 | 0.00% | 0 | 1.93 |
| consist120-k2-skip | 781 / 2,109 | 0.00% | 0 | 4.02 | 787 / 2,136 | 0.09% | 0 | 2.27 |
| consist120-k3-cells3 | 695 / 1,751 | 0.00% | 0 | 1.32 | 143 / 151 | 0.00% | 0 | 1.93 |
| consist120-k3-skip | 781 / 2,109 | 0.00% | 0 | 4.02 | 787 / 2,136 | 0.09% | 0 | 2.27 |
| consist120-k4-cells3 | 695 / 1,751 | 0.00% | 0 | 1.32 | 143 / 151 | 0.00% | 0 | 1.93 |
| consist120-k4-skip | 781 / 2,109 | 0.00% | 0 | 4.02 | 787 / 2,136 | 0.09% | 0 | 2.27 |
| cells3-w3 | 1,617 / 4,052 | 0.00% | 0 | 1.18 | 137 / 137 | 0.00% | 0 | 1.96 |
| cells3-w5 | 1,876 / 5,519 | 0.00% | 0 | 0.61 | 137 / 137 | 0.00% | 0 | 1.96 |
| cells4-w3 | 1,155 / 3,036 | 0.00% | 0 | 2.82 | 134 / 134 | 0.00% | 0 | 1.97 |
| cells4-w5 | 1,103 / 2,695 | 0.00% | 0 | 2.26 | 134 / 134 | 0.00% | 0 | 1.97 |
| curv | 547 / 1,382 | 2.40% | 0 | 1.15 | 141 / 141 | 0.02% | 0 | 1.95 |
| cells3+slow150-tau60 | 1,572 / 6,297 | 0.00% | 0 | 1.63 | 109 / 140 | 0.00% | 0 | 3.89 |
| cells3+freeze | 1,681 / 5,765 | 0.00% | 0 | 0.90 | 147 / 155 | 0.19% | 0 | 1.86 |
| cells3+curv | 1,610 / 4,119 | 6.76% | 0 | 0.42 | 142 / 149 | 0.01% | 0 | 1.89 |
| cells3-w3+curv | 1,004 / 1,471 | 0.00% | 0 | 0.96 | 137 / 137 | 0.00% | 0 | 1.96 |
| cells3-w5+curv | 1,637 / 3,927 | 7.24% | 0 | 0.44 | 137 / 137 | 0.00% | 0 | 1.96 |


### Applying the rule

- (a) passed by: control; every `cells*` arm without curvature inflation; every `consist*` arm; `cells3+slow150-tau60`; `cells3+freeze`. Failed by: `curv` (real 18.4 %), `cells3+curv` (real 2.7 %, sim 6.8 %), `cells3-w3+curv` (real 3.6 %), `cells3-w5+curv`, the slow-error arms other than `slow150-tau60`, `freeze` (real 5.2 %), `huber1.5` (sim 5.0 %), `huber2.5`, `ekf-learned-noise`, `imu` (sim 1.37 %), `q0.3`, `q0.1`.
- (c) on the 1-carrier leg (control 505 / 1,256 m, 5 % = 530 / 1,319 m): no arm that passes (a) other than the control and `common-step` stays within it. Closest: `consist*-cells3` 695 / 1,751 m (+38 % / +39 %; 13 carriers 143–150 m, +7 %); `cells4` 1,103 / 2,378 m (+118 % / +89 %); `cells3` 1,681 / 5,765 m.
- `common-step` passes (a) and (c) but its real 300 s error is 1,244 m against the control's 1,229 m.
- **Winner under the rule: the control (`ekf-honest`).**
- **Best near-miss, chosen by a rule fixed here before held-out data:** among arms passing (a) with 0 hazardous epochs, the lowest real 300 s error; ties broken by the smaller miss of (c), then fewer settings. `cells4`, `cells4-w3` and `cells4-w5` tie at 1.7 m (no LTE's value: with 4 cells needed, `0040` makes no LTE update after any cut); `cells4` has the smallest miss of (c) (1-carrier +118 % / +89 %; 13 carriers within 5 %) and one setting. **Near-miss for the held-out run: `cells4` (`lte_min_cells=4`), labelled as not passing the rule.**

## Stationary aiding (kept apart; not a candidate)

Zero-velocity update when the IMU's 2 s variance is at its noise level (thresholds from `0040`). The test cannot tell the sim drone in flight from a still receiver (2 s IMU standard deviations overlap: `0040` 0.018–0.022 m/s² and 0.0006–0.0009 rad/s, sim drone 0.016–0.019 m/s² and 0.0006–0.0026 rad/s), so it fires in flight: not usable as is.

| Row | 60 s | 120 s | 300 s | p95 0–300 s (worst cut) | Error > HPL | HPL 120 s | HPL 300 s | LTE after cut: accepted / unchecked / rejected | Speed after cut (m/s) |
|---|---|---|---|---|---|---|---|---|---|
| no-lte | 0.2 (0.6) | 0.4 (2.0) | 1.7 (3.2) | 3.1 | 0.0% (0 of 1,505) | 4,241 | 16,298 | – | 0.01 |
| control | 73.0 (114) | 381 (849) | 1,229 (3,262) | 3,046 | 0.0% (0 of 1,505) | 3,177 | 9,443 | 7,502 / 122 / 2 | 4.61 |
| zupt | 0.5 (1.3) | 1.4 (1.8) | 1.1 (1.8) | 1.9 | 0.0% (0 of 1,505) | 42.3 | 48.2 | 43,581 / 122 / 315 | 0.00 |

| Row | 1c: worst-second p95 0–120 / 0–300 s (m) | 1c: above HPL | 1c: hazardous | 1c: tightness | 13c: worst-second p95 0–120 / 0–300 s (m) | 13c: above HPL | 13c: hazardous | 13c: tightness |
|---|---|---|---|---|---|---|---|---|
| control | 505 / 1,256 | 0.00% | 0 | 1.25 | 141 / 141 | 0.02% | 0 | 1.95 |
| zupt | 478 / 478 | 74.18% | 1,245 | 0.47 | 364 / 364 | 72.18% | 2,403 | 0.38 |
| no-lte | 1,258 / 2,729 | 0.00% | 0 | 4.18 | 1,258 / 2,729 | 0.00% | 0 | 4.18 |

## Findings from the tuning data

- **The consistency test passes every real cell.** Before each cut the real cells' normalised innovation RMS (1 Hz) is 0.09–0.29 over 30–120 s, the sim cells' 0.96–2.33: while GNSS steers, the tower clock and slow-error states absorb the real slow error, so the innovations look better than the model, not worse. Every threshold (2, 3, 4) and window gives the same result on `0040`; what the arm holds back is only cells first heard after the loss (no evidence). With threshold 2 some sim cells fail, none real. A test on innovations cannot see this error; it is not a finding about the sim's realism.
- **LTE held back cannot come back** without curvature inflation: once the position sigma has grown, the curvature check drops nearly every record (`cells4`: 0 LTE updates after any cut). Inflating instead lets it back in, and then the HPL stops holding on real data (18.4 % above HPL alone, 2.7 % with `cells3`).
