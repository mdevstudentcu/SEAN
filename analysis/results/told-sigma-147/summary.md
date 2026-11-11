# What should the filter believe about a radio's LTE records? (#147)

Two fixes for an optimistic reported σ, compared on the same records: **A**, learn each cell's range noise from its innovations (ADR-0039, #156); **B**, tell the filter ADR-0036's measured σ from each record's SNR (`nav/told_sigma.py`, ADR-0043); **B+A**, both; the **default** (the reported σ, 2 m in the sim); and **no LTE** as a reference. Each for `ekf` and `ekf-calibrated`. Every value is `TBC`.

**Where the numbers come from.** Sim and replay both ran on `src/` at `01154f5` (the replay wrapper at `20bd344`, the same file as on this branch): local branch `cmp147` = #156 rebased onto `main` `c21e047` (branch `fix156`) plus this branch's B commits and the comparison script. `src/` there is the union of the two branches, and on it every default estimator hashes the same as on `main` (PR text). The defaults, B and no LTE reproduce from this branch alone; A and B+A need #156's code as well. The figure and tables are drawn by `analysis/told_sigma_147_report.py` from the JSON beside them.

```bash
# sim (wall 20 min and 15 min, 3 workers)
python analysis/told_sigma_147.py --legs challenge-drone-outage challenge-timing-outage \
    --seeds 200-249 --jobs 3 --out <dir> --tag=-t1
python analysis/told_sigma_147.py --legs challenge-drone-outage-tower-clock-step \
    challenge-drone-spoof-jump --seeds 200-219 --jobs 3 --out <dir> --tag=-other
# real replay through #214's script (analysis/real_gps_cut.py at 8e7a216, not yet on main)
python analysis/told_sigma_147_real.py <dir>/20261111-0151-static-fullsuite2-lte \
    --cut-script <#214>/analysis/real_gps_cut.py --with-doppler --jobs 3 --out <dir>
python analysis/told_sigma_147_report.py <dir> --out analysis/results/told-sigma-147
```

**Seeds.** Sim seeds 200–249 for the two T1 legs and 200–219 for the other two (reduced seed count): none of them was used to tune A (100–149) or B (none). The sim's LTE model is `placeholder` (`verification.md`, *Sim validity*): 50 m white and 50 m / 30 s multipath per eNB, records told 2 m. These numbers compare the variants with each other and do not predict a flight.

**Real session.** `20261111-0151-static-fullsuite2-lte`: a static receiver on the ground at one site, EARFCN 2460, 10 Hz records. GPS is cut in software at 100, 150, 200, 250 and 300 s and the filter is scored against the fixes it no longer sees. The five cuts share one recording, so they are not independent runs. A static receiver favours `no LTE` (dead reckoning from a stopped vehicle stays put) and the held last fix. Only errors are given here: no position, origin, range or bearing.

![p95 across runs of the horizontal error after GPS loss, each variant](t1_curves.png)

*Sim (`placeholder` LTE model), `01154f5`. The drone and timing legs use seeds 200–249; the tower-clock-step leg uses seeds 200–219. Each line is ADR-0034's T1 statistic: the 95th percentile across runs at each second. B+A (dotted) lies on A for `ekf`.*

### Sim: drone, timing — seeds 200-249, commit `01154f5`

| Leg | Filter | Variant | T1 worst-second p95 (m) | median run 300 s p95 (m) | NEES median / p95 | HPL bound mean / worst run | misleading (runs) | hazardous (runs) | false alarms /h | T3 600 s time p95 median (µs) |
|---|---|---|---|---|---|---|---|---|---|---|
| drone | ekf | default | **9,435** | 3,738 | 270 / 2,022 | 0.67 / 0.09 | 799 (7) | 720 (7) | 3.3 | 0.3 |
| drone | ekf | A | **2,153** | 656 | 7.4 / 29.0 | 0.95 / 0.63 | 0 (0) | 0 (0) | 0.6 | 0.3 |
| drone | ekf | B | **2,561** | 677 | 48.5 / 194 | 0.67 / 0.29 | 73 (3) | 43 (3) | 4.2 | 0.3 |
| drone | ekf | B+A | **2,153** | 656 | 7.4 / 29.0 | 0.95 / 0.63 | 0 (0) | 0 (0) | 0.6 | 0.3 |
| drone | ekf | no LTE | **2,857** | 2,503 | 2.0 / 2.4 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.3 |
| drone | ekf-calibrated | default | **10,808** | 3,653 | 75.4 / 579 | 0.65 / 0.02 | 109 (2) | 69 (2) | 3.2 | 0.1 |
| drone | ekf-calibrated | A | **2,166** | 731 | 2.0 / 6.4 | 1.00 / 0.86 | 0 (0) | 0 (0) | 0.1 | 0.1 |
| drone | ekf-calibrated | B | **2,872** | 792 | 14.8 / 59.4 | 0.82 / 0.44 | 31 (1) | 31 (1) | 3.7 | 0.1 |
| drone | ekf-calibrated | B+A | **2,218** | 701 | 2.0 / 7.2 | 1.00 / 0.93 | 0 (0) | 0 (0) | 0.1 | 0.1 |
| drone | ekf-calibrated | no LTE | **2,857** | 2,503 | 2.0 / 2.4 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.1 |
| timing | ekf | default | **10,289** | 2,743 | 104 / 2,227 | 0.76 / 0.05 | 93 (9) | 85 (9) | 3.1 | 0.3 |
| timing | ekf | A | **1,761** | 552 | 0.7 / 6.9 | 0.99 / 0.74 | 0 (0) | 0 (0) | 0.0 | 0.3 |
| timing | ekf | B | **3,067** | 980 | 25.9 / 225 | 0.84 / 0.47 | 178 (5) | 158 (4) | 3.1 | 0.3 |
| timing | ekf | B+A | **1,761** | 552 | 0.7 / 6.9 | 0.99 / 0.74 | 0 (0) | 0 (0) | 0.0 | 0.3 |
| timing | ekf | no LTE | **421** | 212 | 0.0 / 0.1 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.3 |
| timing | ekf-calibrated | default | **8,407** | 2,632 | 16.5 / 215 | 0.78 / 0.17 | 0 (0) | 0 (0) | 2.9 | 0.1 |
| timing | ekf-calibrated | A | **842** | 239 | 0.1 / 0.9 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.1 |
| timing | ekf-calibrated | B | **3,017** | 1,022 | 12.7 / 89.1 | 0.91 / 0.51 | 0 (0) | 0 (0) | 2.9 | 0.1 |
| timing | ekf-calibrated | B+A | **841** | 242 | 0.1 / 0.8 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.1 |
| timing | ekf-calibrated | no LTE | **421** | 212 | 0.0 / 0.1 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.1 |

### Sim: drone, tower clock step, drone, spoof jump — seeds 200-219, commit `01154f5`

| Leg | Filter | Variant | T1 worst-second p95 (m) | median run 300 s p95 (m) | NEES median / p95 | HPL bound mean / worst run | misleading (runs) | hazardous (runs) | false alarms /h | T3 600 s time p95 median (µs) |
|---|---|---|---|---|---|---|---|---|---|---|
| drone, tower clock step | ekf | default | **8,587** | 3,640 | 187 / 1,521 | 0.67 / 0.09 | 503 (3) | 450 (3) | 3.0 | 0.2 |
| drone, tower clock step | ekf | A | **1,893** | 1,049 | 11.0 / 39.7 | 0.91 / 0.64 | 58 (2) | 24 (2) | 1.5 | 0.2 |
| drone, tower clock step | ekf | B | **3,704** | 1,421 | 76.2 / 264 | 0.63 / 0.30 | 60 (3) | 28 (3) | 5.0 | 0.2 |
| drone, tower clock step | ekf | B+A | **1,892** | 1,049 | 11.0 / 39.7 | 0.91 / 0.64 | 57 (2) | 23 (2) | 1.5 | 0.2 |
| drone, tower clock step | ekf | no LTE | **2,809** | 2,490 | 2.0 / 2.5 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.2 |
| drone, tower clock step | ekf-calibrated | default | **10,614** | 3,234 | 59.7 / 505 | 0.66 / 0.07 | 0 (0) | 0 (0) | 3.5 | 0.1 |
| drone, tower clock step | ekf-calibrated | A | **2,233** | 933 | 2.6 / 10.0 | 0.99 / 0.85 | 0 (0) | 0 (0) | 0.3 | 0.1 |
| drone, tower clock step | ekf-calibrated | B | **2,681** | 891 | 21.3 / 107 | 0.76 / 0.37 | 0 (0) | 0 (0) | 4.0 | 0.1 |
| drone, tower clock step | ekf-calibrated | B+A | **2,241** | 886 | 2.5 / 9.7 | 0.99 / 0.87 | 0 (0) | 0 (0) | 0.3 | 0.1 |
| drone, tower clock step | ekf-calibrated | no LTE | **2,809** | 2,490 | 2.0 / 2.5 | 1.00 / 1.00 | 0 (0) | 0 (0) | 0.0 | 0.1 |

| Leg | Filter | Variant | misleading (runs) | hazardous (runs) | false alarms /h |
|---|---|---|---|---|---|
| drone, spoof jump | ekf | default | 97,251 (19) | 97,251 (19) | 0.0 |
| drone, spoof jump | ekf | A | 98,676 (20) | 98,676 (20) | 0.0 |
| drone, spoof jump | ekf | B | 94,730 (20) | 94,730 (20) | 0.0 |
| drone, spoof jump | ekf | B+A | 98,676 (20) | 98,676 (20) | 0.0 |
| drone, spoof jump | ekf | no LTE | 108,596 (20) | 108,596 (20) | 0.0 |
| drone, spoof jump | ekf-calibrated | default | 98,608 (19) | 98,608 (19) | 0.0 |
| drone, spoof jump | ekf-calibrated | A | 104,554 (20) | 104,554 (20) | 0.0 |
| drone, spoof jump | ekf-calibrated | B | 104,226 (20) | 104,226 (20) | 0.0 |
| drone, spoof jump | ekf-calibrated | B+A | 104,480 (20) | 104,480 (20) | 0.0 |
| drone, spoof jump | ekf-calibrated | no LTE | 108,596 (20) | 108,596 (20) | 0.0 |

### Real replay: `20261111-0151-static-fullsuite2-lte`, GPS cut in software at 100, 150, 200, 250, 300 s (#214's script at `8e7a216`)

Errors against the withheld GPS fixes; median over the cuts, worst cut in brackets (m). HPL bound pooled over every withheld fix.

| Filter | Variant | LTE records | p95 0–120 s | p95 0–300 s | error at 60 s | error at 300 s | HPL ≥ error | error > HPL (fixes) |
|---|---|---|---|---|---|---|---|---|
| ekf | default | told-pr | 1,463 (2,069) | 6,299 (11,047) | 449 (595) | 7,886 (11,919) | 33% | 1009 / 1505 |
| ekf | default | told | 3,965 (8,009) | 11,507 (15,759) | 1,703 (5,521) | 12,436 (16,531) | 6% | 1422 / 1505 |
| ekf | B | told-pr | 0.4 (2,543) | 4,026 (8,521) | 0.2 (7.6) | 4,277 (9,083) | 96% | 66 / 1505 |
| ekf | B | told | 2,094 (3,104) | 7,418 (9,316) | 945 (1,297) | 7,615 (10,282) | 8% | 1381 / 1505 |
| ekf | A | told-pr | 3,557 (5,347) | 26,477 (51,535) | 160 (238) | 28,453 (53,295) | 48% | 786 / 1505 |
| ekf | A | told | 1,872 (3,957) | 6,553 (12,306) | 569 (1,258) | 6,859 (13,032) | 25% | 1131 / 1505 |
| ekf | B+A | told-pr | 3,824 (6,408) | 22,824 (33,892) | 306 (658) | 21,137 (37,342) | 52% | 726 / 1505 |
| ekf | B+A | told | 1,871 (3,941) | 6,587 (9,132) | 568 (1,258) | 6,910 (9,401) | 25% | 1131 / 1505 |
| ekf-calibrated | default | told-pr | 781 (1,568) | 7,731 (8,513) | 205 (447) | 8,526 (9,246) | 50% | 754 / 1505 |
| ekf-calibrated | default | told | 1,624 (3,797) | 7,624 (9,419) | 717 (1,248) | 8,333 (10,176) | 20% | 1209 / 1505 |
| ekf-calibrated | B | told-pr | 0.4 (973) | 3,280 (4,686) | 0.2 (6.8) | 3,553 (4,969) | 93% | 108 / 1505 |
| ekf-calibrated | B | told | 575 (3,186) | 7,635 (9,933) | 364 (1,258) | 8,304 (10,633) | 33% | 1008 / 1505 |
| ekf-calibrated | A | told-pr | 726 (1,621) | 12,859 (15,518) | 39.3 (174) | 15,876 (17,068) | 86% | 205 / 1505 |
| ekf-calibrated | A | told | 1,719 (3,018) | 7,388 (9,518) | 695 (1,193) | 7,574 (10,154) | 20% | 1208 / 1505 |
| ekf-calibrated | B+A | told-pr | 1,771 (1,866) | 16,170 (18,510) | 186 (328) | 17,581 (20,461) | 77% | 349 / 1505 |
| ekf-calibrated | B+A | told | 511 (3,147) | 6,943 (7,723) | 362 (1,263) | 7,325 (7,972) | 37% | 945 / 1505 |
| ekf | no LTE | none | 0.3 (6.1) | 0.6 (15.1) | 0.2 (3.2) | 0.6 (15.9) | 100% | 0 / 1505 |
| ekf-calibrated | no LTE | none | 0.3 (6.1) | 0.6 (15.1) | 0.2 (3.2) | 0.6 (15.9) | 100% | 0 / 1505 |
| hold | last fix | - | 0.3 (0.3) | 0.4 (1.1) | 0.1 (0.2) | 0.5 (1.2) | — | — |
## What it shows

- **Sim, drone leg:** every fix beats the default (T1 9,435 → 2,153 to 2,872 m). A and B+A also beat no LTE (2,857 m) and keep the covariance honest: median NEES 7.4 (`ekf`) and 2.0 (`ekf-calibrated`), HPL bound 0.95 to 1.00, no misleading epoch. B alone beats no LTE on error (2,561 m) but stays overconfident. Its median NEES is 48 (`ekf`) and 15 (`ekf-calibrated`), its HPL bound mean is 0.67 and 0.82, and 3 and 1 runs have hazardous epochs. The sim's true error (50 m white, 50 m / 30 s multipath) is two to three times what B tells (about 25 to 29 m at 1 Hz), and B never learns that.
- **Sim, timing leg (static):** no variant beats no LTE (T1 421 m). A and B+A come closest (1,761 and 842 m) with honest NEES. B gets 3,067 and 3,017 m, with hazardous epochs in 4 `ekf` runs. ADR-0039's consequence 6 holds for every variant: a static receiver on few cells mistakes slow range error for motion.
- **B+A ≈ A in the sim.** A's 40 m prior and the variance it learns are above B's told σ, so B's value is a floor that never binds.
- **Tower clock step (20 seeds):** same ranking. A and B+A have misleading epochs in 2 `ekf` runs (58 and 57), B in 3 (60); `ekf-calibrated` has none in any variant. False alarms per hour: A and B+A 1.5 and 0.3, B 5.0 and 4.0, default 3.0 and 3.5.
- **Spoof jump (20 seeds):** every variant follows the held jump, with or without LTE (thousands of hazardous epochs per run). Refusing it is ADR-0038's job.
- **Real replay, pseudoranges only (`told-pr`):** the ranking reverses. B is the only LTE variant whose HPL bounds the error at 93 to 96 % of withheld fixes; it has the lowest median 300 s p95 (4,026 and 3,280 m against the default's 6,299 and 7,731 m) and the error at 60 s stays under 8 m in every cut. A is worse than the default here: median 300 s p95 26,477 m (`ekf`) and 12,859 m (`ekf-calibrated`), HPL bound 48 % and 86 %. B+A follows A. On this static session `no LTE` (0.6 m) beats every LTE variant, as on the sim timing leg.
- **Real replay with dopplers (`told`):** every LTE variant is worse, and no fix makes the dopplers usable. Their σ is not covered by either fix, and #183 flags their carrier aliases.

## What it cannot show

- Only one real session, and it is static. Neither fix has been checked on a moving receiver with GPS truth, which is the drone's case.
- The sim's LTE error sizes are placeholders, larger than ADR-0036 measured at rest. B is sized from those static measurements and A learns whatever the sim draws, so the sim favours A by construction and a world with the measured sizes would favour B. Neither world is validated.
- B's correlated part (10 m, 3 s) comes from static captures. Multipath on a moving drone is `TBD` (ADR-0036 consequence 3).
- The real records are 10 Hz and the sim's are 1 Hz. A's memories and prior were tuned on 1 Hz sim records only.
