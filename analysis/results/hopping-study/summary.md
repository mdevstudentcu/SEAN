# Carrier hopping study: error after GPS loss against masts heard (#173)

Sim, every value `TBC`. `python analysis/accuracy_budget.py --seeds 20 --jobs 3` at fb62912, seeds 0–19 (paired), 81.6 min. Scenarios `challenge-drone-outage` and `challenge-drone-hop-outage`, the drone leg's 600 s outage; filters unchanged. Targets (`TBC`): the mentors' 50 m at 120 s (#158) and our T1, 25 m at 300 s, both p95 horizontal error after GPS loss. fb62912 is not in the repo. Reproduced at 1e522d2: `python analysis/hopping_study.py --seeds 1 --jobs 3 --configs one-carrier,scan-2-1s,scan-4-0.5s,scan-4-2s,distinct-4-1s,scan-13-1s` re-ran seed 0 of 6 of the 11 configurations, both told-sigma variants (12 runs); all 12 match the recorded runs exactly (masts per 10 s, and both filters' p95 at 120 s and 300 s); the other configurations and seeds 1-19 were not re-run.

## Verdict

- **50 m at 120 s: not met.** Best median 64 m: `ekf`, every tower within 3 km (2460), told the true noise (if #147 is solved), 13 masts per 10 s (4 of 20 seeds meet it).
- **25 m at 300 s: not met.** Best median 66 m: `ekf`, every tower within 3 km (2460), told the true noise (if #147 is solved), 13 masts per 10 s (0 of 20 seeds meet it).

## What is heard during the outage

After the cell lookup. Masts: registered eNBs within 10 m are one mast. Per epoch and per 10 s window: median over seeds of each run's median, [min–max] over every run. Masts over the outage: median [min–max] over seeds. Told sigma does not change what is heard.

| Configuration | Carriers | Record epochs /s | Masts per epoch | Masts per 10 s | Cells per 10 s | Masts over the outage | Records dropped by the lookup |
|---|---|---|---|---|---|---|---|
| 1 carrier, today's leg (2460) | 2460 | 1.00 | 2 [1–18] | 2 [1–18] | 2 [1–22] | 17 [3–25] | 2 % |
| every tower within 3 km (2460) | 2460 | 1.00 | 13 [7–17] | 13 [7–17] | 39 [21–51] | 18 [17–19] | 10 % |
| scan order, 2 carriers, 1 s | 2460, 5145 | 1.00 | 2 [1–23] | 5 [2–31] | 5 [2–36] | 30 [9–47] | 1 % |
| scan order, 4 carriers, 1 s | 2460, 5145, 5255, 2535 | 1.00 | 2 [1–35] | 5 [2–38] | 11 [4–104] | 38 [21–60] | 1 % |
| scan order, 6 carriers, 1 s | 2460, 5145, 5255, 2535, 5035, 5085 | 1.00 | 2.25 [1–27] | 8.75 [4–36] | 20.25 [8–101] | 45.5 [28–60] | 2 % |
| scan order, 8 carriers, 1 s | 2460, 5145, 5255, 2535, 5035, 5085, 5205, 5060 | 1.00 | 3 [0–31] | 18 [9–61] | 29.75 [14–145] | 66.5 [42–89] | 7 % |
| scan order, 13 carriers, 1 s | 2460, 5145, 5255, 2535, 5035, 5085, 5205, 5060, 68611, 68661, 2560, 68711, 68761 | 1.00 | 3 [0–32] | 26.5 [10–75] | 46 [15–160] | 84 [67–109] | 4 % |
| scan order, 4 carriers, 0.5 s | 2460, 5145, 5255, 2535 | 2.00 | 2 [1–35] | 5 [2–38] | 11 [4–104] | 38.5 [21–60] | 1 % |
| scan order, 4 carriers, 2 s | 2460, 5145, 5255, 2535 | 1.00 | 2 [1–35] | 5 [2–38] | 11 [4–104] | 38.5 [21–60] | 1 % |
| distinct eNB sets, 4 carriers, 1 s | 2460, 5145, 2535, 5035 | 1.00 | 2 [1–27] | 8.5 [4–36] | 13 [5–71] | 45 [29–59] | 2 % |
| distinct eNB sets, 6 carriers, 1 s | 2460, 5145, 2535, 5035, 5205, 5060 | 1.00 | 3 [0–33] | 18 [9–60] | 22 [10–105] | 66 [41–90] | 8 % |

## Error, told sigma as committed (2 m)

p95 horizontal error over the first 120 s and 300 s of the outage: median over seeds (worst seed), and seeds meeting the target. HPL bound: share of the first 300 s where HPL >= error, median (min). Hazardous: epochs over the whole run (seeds with any).

| Configuration | Masts per 10 s | Estimator | p95 120 s (m) | <= 50 m | p95 300 s (m) | <= 25 m | HPL bound 300 s | Hazardous |
|---|---|---|---|---|---|---|---|---|
| 1 carrier, today's leg (2460) | 2 | `ekf` | 1,202 (3,432) | 0/20 | 4,034 (16,639) | 0/20 | 0.70 (0.11) | 180 (2) |
| 1 carrier, today's leg (2460) | 2 | `ekf-calibrated` | 1,239 (3,251) | 0/20 | 4,114 (12,059) | 0/20 | 0.74 (0.10) | 0 (0) |
| every tower within 3 km (2460) | 13 | `ekf` | 1,340 (4,222) | 0/20 | 4,815 (14,476) | 0/20 | 0.75 (0.02) | 314 (3) |
| every tower within 3 km (2460) | 13 | `ekf-calibrated` | 1,327 (4,821) | 0/20 | 4,033 (18,507) | 0/20 | 0.55 (0.05) | 284 (2) |
| scan order, 2 carriers, 1 s | 5 | `ekf` | 1,803 (3,500) | 0/20 | 4,946 (12,317) | 0/20 | 0.19 (0.02) | 387 (3) |
| scan order, 2 carriers, 1 s | 5 | `ekf-calibrated` | 1,661 (4,016) | 0/20 | 4,447 (10,344) | 0/20 | 0.18 (0.07) | 0 (0) |
| scan order, 4 carriers, 1 s | 5 | `ekf` | 1,296 (3,997) | 0/20 | 5,561 (15,987) | 0/20 | 0.50 (0.05) | 168 (4) |
| scan order, 4 carriers, 1 s | 5 | `ekf-calibrated` | 1,175 (2,701) | 0/20 | 3,225 (7,361) | 0/20 | 0.55 (0.07) | 34 (1) |
| scan order, 6 carriers, 1 s | 8.75 | `ekf` | 1,270 (4,005) | 0/20 | 4,511 (14,918) | 0/20 | 0.68 (0.04) | 89 (3) |
| scan order, 6 carriers, 1 s | 8.75 | `ekf-calibrated` | 1,276 (2,729) | 0/20 | 3,410 (9,990) | 0/20 | 0.74 (0.07) | 0 (0) |
| scan order, 8 carriers, 1 s | 18 | `ekf` | 1,269 (2,688) | 0/20 | 3,400 (8,806) | 0/20 | 0.75 (0.02) | 173 (3) |
| scan order, 8 carriers, 1 s | 18 | `ekf-calibrated` | 1,269 (3,061) | 0/20 | 3,310 (7,944) | 0/20 | 0.84 (0.04) | 36 (2) |
| scan order, 13 carriers, 1 s | 26.5 | `ekf` | 1,132 (3,291) | 0/20 | 3,866 (12,591) | 0/20 | 0.48 (0.04) | 526 (3) |
| scan order, 13 carriers, 1 s | 26.5 | `ekf-calibrated` | 1,103 (4,607) | 0/20 | 2,778 (17,395) | 0/20 | 0.63 (0.05) | 12 (1) |
| scan order, 4 carriers, 0.5 s | 5 | `ekf` | 1,175 (3,591) | 0/20 | 3,090 (16,711) | 0/20 | 0.85 (0.11) | 0 (0) |
| scan order, 4 carriers, 0.5 s | 5 | `ekf-calibrated` | 1,175 (2,714) | 0/20 | 2,752 (12,805) | 0/20 | 0.92 (0.11) | 0 (0) |
| scan order, 4 carriers, 2 s | 5 | `ekf` | 1,355 (3,778) | 0/20 | 6,532 (11,024) | 0/20 | 0.62 (0.04) | 33 (1) |
| scan order, 4 carriers, 2 s | 5 | `ekf-calibrated` | 1,309 (4,418) | 0/20 | 7,547 (16,258) | 0/20 | 0.50 (0.13) | 0 (0) |
| distinct eNB sets, 4 carriers, 1 s | 8.5 | `ekf` | 1,633 (3,949) | 0/20 | 6,125 (16,522) | 0/20 | 0.30 (0.03) | 178 (3) |
| distinct eNB sets, 4 carriers, 1 s | 8.5 | `ekf-calibrated` | 1,295 (3,326) | 0/20 | 4,649 (13,024) | 0/20 | 0.25 (0.13) | 61 (3) |
| distinct eNB sets, 6 carriers, 1 s | 18 | `ekf` | 1,206 (3,770) | 0/20 | 5,076 (16,569) | 0/20 | 0.42 (0.04) | 402 (4) |
| distinct eNB sets, 6 carriers, 1 s | 18 | `ekf-calibrated` | 1,186 (3,604) | 0/20 | 2,564 (13,281) | 0/20 | 0.21 (0.02) | 119 (5) |

## Error, told the true noise (if #147 is solved)

p95 horizontal error over the first 120 s and 300 s of the outage: median over seeds (worst seed), and seeds meeting the target. HPL bound: share of the first 300 s where HPL >= error, median (min). Hazardous: epochs over the whole run (seeds with any).

| Configuration | Masts per 10 s | Estimator | p95 120 s (m) | <= 50 m | p95 300 s (m) | <= 25 m | HPL bound 300 s | Hazardous |
|---|---|---|---|---|---|---|---|---|
| 1 carrier, today's leg (2460) | 2 | `ekf` | 374 (1,125) | 0/20 | 715 (2,305) | 0/20 | 0.94 (0.46) | 0 (0) |
| 1 carrier, today's leg (2460) | 2 | `ekf-calibrated` | 413 (701) | 0/20 | 963 (1,508) | 0/20 | 1.00 (0.82) | 71 (1) |
| every tower within 3 km (2460) | 13 | `ekf` | 64 (111) | 4/20 | 66 (102) | 0/20 | 0.94 (0.74) | 0 (0) |
| every tower within 3 km (2460) | 13 | `ekf-calibrated` | 68 (192) | 1/20 | 91 (387) | 0/20 | 1.00 (0.38) | 0 (0) |
| scan order, 2 carriers, 1 s | 5 | `ekf` | 227 (723) | 0/20 | 316 (1,080) | 0/20 | 1.00 (0.77) | 37 (3) |
| scan order, 2 carriers, 1 s | 5 | `ekf-calibrated` | 229 (571) | 0/20 | 491 (1,020) | 0/20 | 1.00 (1.00) | 0 (0) |
| scan order, 4 carriers, 1 s | 5 | `ekf` | 207 (880) | 0/20 | 278 (1,643) | 0/20 | 0.96 (0.28) | 0 (0) |
| scan order, 4 carriers, 1 s | 5 | `ekf-calibrated` | 162 (662) | 0/20 | 382 (1,142) | 0/20 | 1.00 (0.85) | 0 (0) |
| scan order, 6 carriers, 1 s | 8.75 | `ekf` | 112 (329) | 1/20 | 129 (293) | 0/20 | 1.00 (0.94) | 0 (0) |
| scan order, 6 carriers, 1 s | 8.75 | `ekf-calibrated` | 100 (363) | 1/20 | 140 (307) | 0/20 | 1.00 (1.00) | 0 (0) |
| scan order, 8 carriers, 1 s | 18 | `ekf` | 83 (122) | 1/20 | 101 (137) | 0/20 | 1.00 (1.00) | 0 (0) |
| scan order, 8 carriers, 1 s | 18 | `ekf-calibrated` | 75 (137) | 1/20 | 103 (178) | 0/20 | 1.00 (1.00) | 0 (0) |
| scan order, 13 carriers, 1 s | 26.5 | `ekf` | 68 (100) | 0/20 | 78 (102) | 0/20 | 1.00 (1.00) | 0 (0) |
| scan order, 13 carriers, 1 s | 26.5 | `ekf-calibrated` | 69 (102) | 0/20 | 87 (141) | 0/20 | 1.00 (1.00) | 0 (0) |
| scan order, 4 carriers, 0.5 s | 5 | `ekf` | 183 (650) | 0/20 | 271 (1,061) | 0/20 | 0.99 (0.79) | 0 (0) |
| scan order, 4 carriers, 0.5 s | 5 | `ekf-calibrated` | 167 (614) | 0/20 | 311 (1,142) | 0/20 | 1.00 (0.77) | 0 (0) |
| scan order, 4 carriers, 2 s | 5 | `ekf` | 212 (770) | 0/20 | 249 (1,498) | 0/20 | 0.98 (0.49) | 0 (0) |
| scan order, 4 carriers, 2 s | 5 | `ekf-calibrated` | 251 (580) | 0/20 | 468 (992) | 0/20 | 1.00 (0.92) | 0 (0) |
| distinct eNB sets, 4 carriers, 1 s | 8.5 | `ekf` | 114 (430) | 0/20 | 135 (333) | 0/20 | 1.00 (0.95) | 0 (0) |
| distinct eNB sets, 4 carriers, 1 s | 8.5 | `ekf-calibrated` | 107 (383) | 0/20 | 134 (339) | 0/20 | 1.00 (1.00) | 0 (0) |
| distinct eNB sets, 6 carriers, 1 s | 18 | `ekf` | 79 (104) | 1/20 | 88 (138) | 0/20 | 1.00 (1.00) | 0 (0) |
| distinct eNB sets, 6 carriers, 1 s | 18 | `ekf-calibrated` | 78 (129) | 0/20 | 99 (175) | 0/20 | 1.00 (1.00) | 0 (0) |

## Not modelled

- The front end's re-acquisition on air: the sim drops the first `reacquire_s` of each dwell and keeps every cell's arc; a real dongle may lose cells or start new arcs.
- Record noise does not depend on how long a dwell is tracked: a 0.35 s record has the same noise as a 1 s one, and dwells under 1 s make more records per second than one carrier does (the record epochs column).
- The link budget's in-band share assumes 10 MHz on every carrier; filed powers are read as given (Vidéotron rows 92 to 103 dBW, so every Vidéotron sector clears the noise floor). The near-far floor is relative within a carrier, so neither moves which sectors of a carrier are heard near its strongest.
- No capture has hopped: every number here is the sim's, on registry geometry.
