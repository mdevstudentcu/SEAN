# Real GPS cut with the three fixes combined (#214)

Evidence: **replay of real static sessions, GPS cut in software** (ADR-0015). Code: `origin/main` c21e047, `shrikar/feat/214-real-gps-cut` 8e7a216, `shrikar/fix/183-lte-real-capture-bugs` 0ebe18a, `shrikar/fix/147-measured-told-sigma` e39742f, `shrikar/fix/228-long-outage-drift` 85d1324, merged in that order in the local branch `tmp/e2e-combined` (never pushed); driver `run_combined.py` here, run at `de888ca` of that branch. `#183`'s front end re-run on each capture. Every error is horizontal, against the GPS fix the filter no longer sees; no position, origin, range or bearing is given. Median over the cuts, worst cut in brackets (m).

## 20261111-0151-static-fullsuite2-lte

600 s; front end at `7001dab`; 5 cuts at 100, 150, 200, 250, 300 s, each scored for 300 s. LTE: 4 cells, 376 arcs, 13,380 pseudoranges, 12,376 dopplers. GPS fix scatter (truth noise) 0.38 m rms, 1.15 m max. The cuts share one recording: not independent draws.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–300 s, worst cut | Worst second | HPL ≥ error | Error > HPL | Before cut: GNSS excluded | Before cut: p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no LTE | none | 0.1 (1.6) | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 15.1 | 15.9 | 100% | 0 / 1505 | 0% | 0.1 |
| hold | last fix | 0.0 (0.2) | 0.1 (0.2) | 0.3 (0.4) | 0.5 (1.2) | 1.1 | 1.2 | — | — | — | — |
| ekf | PR | 5,428 (8,960) | 4,722 (8,254) | 5,232 (8,607) | 7,857 (9,277) | 9,527 | 9,978 | 24% | 1143 / 1505 | 100% | 5,800 |
| ekf | PR+doppler | 64.1 (340) | 378 (472) | 816 (1,457) | 2,281 (5,525) | 5,416 | 5,758 | 50% | 746 / 1505 | 43% | 367 |
| B | PR | 0.1 (1.6) | 0.2 (355) | 0.4 (1,155) | 3,658 (10,034) | 9,007 | 10,034 | 90% | 155 / 1505 | 0% | 3.4 |
| B | PR+doppler | 59.4 (156) | 171 (472) | 556 (1,457) | 2,876 (7,092) | 6,801 | 7,092 | 56% | 661 / 1505 | 0% | 7.4 |
| B+arc | PR | 121 (312) | 474 (534) | 1,215 (1,838) | 1,947 (2,209) | 3,880 | 3,977 | 41% | 889 / 1505 | 0% | 1.8 |
| ekf+rx | PR | 5,428 (8,960) | 4,722 (8,254) | 5,232 (8,607) | 7,857 (9,277) | 9,527 | 9,978 | 24% | 1143 / 1505 | 100% | 5,800 |
| ekf+rx | PR+doppler | 64.1 (340) | 378 (472) | 816 (1,457) | 2,281 (5,525) | 5,416 | 5,758 | 50% | 746 / 1505 | 43% | 367 |
| B+rx | PR | 0.1 (1.6) | 0.2 (355) | 0.4 (1,155) | 3,658 (10,034) | 9,007 | 10,034 | 90% | 155 / 1505 | 0% | 3.4 |
| B+rx | PR+doppler | 59.4 (156) | 171 (472) | 556 (1,457) | 2,876 (7,092) | 6,801 | 7,092 | 56% | 661 / 1505 | 0% | 7.4 |

Receiver-clock term (`+rx`): bit-identical to the run without it on every cut.

HPL after the cut (median over the cuts, m): the coasting covariance.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| no LTE | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf | PR | 4,998 | 3,953 | 1,207 | 4,042 |
| ekf | PR+doppler | 260 | 362 | 329 | 870 |
| B | PR | 606 | 1,569 | 4,241 | 5,936 |
| B | PR+doppler | 181 | 277 | 329 | 614 |
| B+arc | PR | 533 | 714 | 892 | 1,978 |

Stress: GNSS pulled 1 m/s for the 60 s before each cut (`spoof_ramp`), so each run enters the coast 60 m off and drifting; truth stays the real fixes. A coast with nothing else keeps drifting; LTE with information pulls it back.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–300 s, worst cut | Worst second | HPL ≥ error | Error > HPL | Before cut: GNSS excluded | Before cut: p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no LTE | none, drift | 90.0 (91.1) | 120 (122) | 180 (185) | 359 (371) | 355 | 371 | 99% | 20 / 1505 | — | — |
| ekf | PR, drift | 5,428 (8,960) | 4,722 (8,254) | 5,232 (8,607) | 7,857 (9,277) | 9,527 | 9,978 | 24% | 1143 / 1505 | — | — |
| ekf | PR+doppler, drift | 158 (339) | 281 (443) | 814 (1,435) | 2,629 (5,513) | 5,404 | 5,746 | 41% | 894 / 1505 | — | — |
| B | PR, drift | 90.0 (91.1) | 120 (327) | 180 (1,174) | 3,778 (11,323) | 10,411 | 11,323 | 81% | 284 / 1505 | — | — |
| B | PR+doppler, drift | 118 (195) | 207 (443) | 521 (1,435) | 2,036 (7,030) | 6,767 | 7,030 | 50% | 759 / 1505 | — | — |
| B+arc | PR, drift | 101 (374) | 467 (540) | 1,211 (1,893) | 1,939 (3,029) | 3,934 | 4,042 | 36% | 958 / 1505 | — | — |

## 20261111-0233-static-lte-1h-lte

3,599 s; front end at `a37e534`; 10 cuts at 300, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700, 3000 s, each scored for 300 s. LTE: 5 cells, 1915 arcs, 74,820 pseudoranges, 70,013 dopplers. GPS fix scatter (truth noise) 0.55 m rms, 1.24 m max. The cuts share one recording: not independent draws.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–300 s, worst cut | Worst second | HPL ≥ error | Error > HPL | Before cut: GNSS excluded | Before cut: p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no LTE | none | 0.2 (0.4) | 0.2 (0.7) | 0.4 (1.3) | 1.0 (3.2) | 3.1 | 3.2 | 100% | 0 / 3010 | 0% | 0.1 |
| hold | last fix | 0.1 (0.3) | 0.2 (0.3) | 0.2 (0.5) | 0.4 (1.4) | 1.4 | 1.6 | — | — | — | — |
| ekf | PR | 2.4 (184) | 173 (728) | 1,108 (3,153) | 3,645 (5,682) | 5,195 | 5,682 | 48% | 1559 / 3010 | 0% | 6.0 |
| ekf | PR+doppler | 5,077 (14,095) | 5,205 (14,835) | 5,179 (15,666) | 5,631 (13,521) | 15,860 | 16,030 | 5% | 2872 / 3010 | 66% | 5,098 |
| B | PR | 3.2 (149) | 53.9 (1,006) | 537 (1,908) | 1,958 (12,145) | 10,568 | 12,217 | 78% | 672 / 3010 | 0% | 1.2 |
| B | PR+doppler | 4,310 (13,476) | 4,184 (13,826) | 4,025 (13,321) | 4,701 (16,292) | 16,077 | 16,292 | 5% | 2867 / 3010 | 66% | 10,860 |
| B+arc | PR | 164 (880) | 649 (2,380) | 1,381 (3,679) | 3,023 (5,525) | 5,359 | 5,625 | 25% | 2270 / 3010 | 0% | 2.7 |
| ekf+rx | PR | 2.4 (184) | 173 (728) | 1,108 (3,153) | 3,645 (5,682) | 5,195 | 5,682 | 48% | 1559 / 3010 | 0% | 6.0 |
| ekf+rx | PR+doppler | 5,077 (14,095) | 5,205 (14,835) | 5,179 (15,666) | 5,631 (13,521) | 15,860 | 16,030 | 5% | 2872 / 3010 | 66% | 5,098 |
| B+rx | PR | 3.2 (149) | 53.9 (1,006) | 537 (1,908) | 1,958 (12,145) | 10,568 | 12,217 | 78% | 672 / 3010 | 0% | 1.2 |
| B+rx | PR+doppler | 4,310 (13,476) | 4,184 (13,826) | 4,025 (13,321) | 4,701 (16,292) | 16,077 | 16,292 | 5% | 2867 / 3010 | 66% | 10,860 |

Receiver-clock term (`+rx`): bit-identical to the run without it on every cut.

HPL after the cut (median over the cuts, m): the coasting covariance.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s |
|---|---|---|---|---|---|
| no LTE | none | 606 | 1,569 | 4,241 | 16,298 |
| ekf | PR | 606 | 955 | 1,212 | 2,155 |
| ekf | PR+doppler | 1,661 | 1,664 | 1,729 | 2,282 |
| B | PR | 606 | 1,569 | 2,567 | 1,880 |
| B | PR+doppler | 1,359 | 1,342 | 1,566 | 1,902 |
| B+arc | PR | 426 | 669 | 1,026 | 1,736 |

Stress: GNSS pulled 1 m/s for the 60 s before each cut (`spoof_ramp`), so each run enters the coast 60 m off and drifting; truth stays the real fixes. A coast with nothing else keeps drifting; LTE with information pulls it back.

| Estimator | LTE | 30 s | 60 s | 120 s | 300 s | p95 0–300 s, worst cut | Worst second | HPL ≥ error | Error > HPL | Before cut: GNSS excluded | Before cut: p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| no LTE | none, drift | 90.0 (90.3) | 120 (121) | 180 (181) | 360 (362) | 346 | 362 | 99% | 40 / 3010 | — | — |
| ekf | PR, drift | 90.0 (273) | 214 (825) | 1,184 (3,097) | 4,062 (8,911) | 8,791 | 9,485 | 41% | 1768 / 3010 | — | — |
| ekf | PR+doppler, drift | 5,077 (14,095) | 5,205 (14,835) | 5,179 (15,666) | 5,631 (13,521) | 15,860 | 16,030 | 4% | 2892 / 3010 | — | — |
| B | PR, drift | 90.2 (214) | 123 (1,005) | 653 (3,007) | 2,032 (4,927) | 5,724 | 7,718 | 75% | 764 / 3010 | — | — |
| B | PR+doppler, drift | 4,310 (13,476) | 4,184 (13,826) | 4,025 (13,321) | 4,701 (16,292) | 16,077 | 16,292 | 4% | 2887 / 3010 | — | — |
| B+arc | PR, drift | 205 (821) | 678 (2,321) | 1,374 (3,614) | 3,056 (5,222) | 5,390 | 5,573 | 23% | 2326 / 3010 | — | — |

## Result

- **LTE does not help on these real sessions, with all three fixes in.** By 300 s after the cut every LTE variant is 1.9 to 7.9 km off (median over the cuts); `no LTE` stays within 1 m (16 m worst cut) because the receiver does not move.
- **Under the drift stress LTE still loses.** `no LTE` drifts as injected (360 m at 300 s, HPL bounds it on 99 % of fixes). Every LTE variant is 1.9 km or more off at 300 s (median): LTE does not pull a drifting coast back, it pulls it further away.
- **`B` (measured σ) is the least bad.** With pseudoranges only it never excludes GNSS before the cut, tracks `no LTE` at first (median: to 120 s on the 600 s session, to 30 s on the 1 h one; it barely weights LTE then), and its HPL bounds 78 to 90 % of fixes; it still ends km off, with 155 and 672 fixes above HPL.
- **The receiver-clock term (ADR-0045) changes nothing on real records** (bit-identical, see above).
- **Dopplers hurt.** On the 1 h session they make `ekf` and `B` exclude GNSS on 66 % of the epochs before the cut, and both start the coast 4 to 5 km off. On the 600 s session the default `ekf` with #183's pseudoranges alone excludes GNSS on 100 %; `B` on 0 %. Where GNSS was already excluded before the cut, the stress rows equal the unstressed ones (the pulled GNSS never reached the filter).
- **`B+arc` does not fix it.** A new bias per arc lowers the 600 s session's worst 300 s error (2.2 km against 10 km) but is worse early on both sessions and bounds only 25 to 41 % of fixes.

## What this can and cannot show

- Both sessions are **static**, outdoors, on the ground, at one site: LTE on one carrier (EARFCN 2460), four cells (600 s session) and five (1 h), the front end's mean SNR per cell -12 to -11 dB on the 600 s session and -12 to +8 dB on the 1 h one. The truth does not move, so `no LTE` and `hold` are right by construction: the constant-velocity coast holds the last position, and its small error says nothing about coasting on a moving drone. Its HPL (16 km at 300 s) is the coast's own honest uncertainty.
- The stress (GNSS pulled before the cut) is the cleanest drift injection the code allows. An IMU bias does not work here: `ekf-imu` needs motion to align its heading (the MPU6050 has no magnetometer), so on a static receiver it never leaves the constant-velocity model (`ekf-imu` with no LTE is bit-identical to `ekf` on 0151, cut 300 s).
- `+rx` (`pseudorange_receiver_clock=True`, ADR-0045) cannot change these runs: real front-end records carry `meta.rx_clock`, and the EKF already puts that dongle's clock in every such range (`use_rx = name is not None or pr_rx_clock`). The tables show the runs bit-identical; ADR-0045 is about sim towers without `rx_clock`.
- The cuts in one session share one recording: they are not independent draws, and the worst cut is not a 95th percentile.
- New arcs still step with #183's front end: of the arcs that start within 1 s of their cell's last record, 309 of 322 (600 s) and 1,575 of 1,689 (1 h) step by more than 100 m, median 650 to 790 m (`arc_steps` in summary.json; steps only, no range). `B+arc` (#147's opt-in arc bias) is run to test whether that is what pulls the position.
- Tower positions are the committed table's matches (a hypothesis, `pnt.nav.cells`). A wrong tower position is one candidate for the km errors; it was not checked here.
- Default `ekf` is unchanged by the merge: on 0151 (cut 300 s) its error and HPL curves hash the same on origin/main c21e047 and on the merged code, for `told-pr`, `told` and `none`. The change in its pre-cut GNSS exclusion against #214's table comes from the #183 front end's records: on the same session and cut, origin/main's `ekf` with pseudoranges excludes GNSS on 0 % of pre-cut epochs with the c21e047 front end's records and on 100 % with #183's.
