# How many towers after GPS is lost? (#208)

Sim, every value `TBC`. Commit 9f0625d, `python analysis/tower_count.py --seeds 20 --jobs 3`, 34.1 min. Seeds 0–19, paired: every variant of a seed keeps a subset of the same records. The leg, the tower rules, the aiding and the error models are in the script's docstring. The LTE model is `placeholder` (`verification.md`, *Sim validity*): these numbers compare tower counts with each other, they are not a prediction of the real drone.

Each cell: **worst-second p95 (m) / s the p95 holds ≤ 25 m / s it holds ≤ 50 m**, the T1 statistic of ADR-0034 over 20 runs, window 0–300 s after GPS loss. 300 means the whole window. T1: worst ≤ 25 m (holds 300 s); fallback: ≤ 50 m for 120 s.

## Error model `committed`

| Towers (rule) | Sites ≥ 3 on air | towers | baro | imu | baro+imu |
|---|---|---|---|---|---|
| 0 | 0% | no output / 0 / 0 | 2,871 / 6 / 11 | 23,274 / 9 / 13 | 11,979 / 9 / 14 |
| 1 (strongest) | 0% | no output / 6 / 10 | 11,851 / 6 / 10 | 65,189 / 9 / 13 | 18,544 / 8 / 14 |
| 2 (strongest) | 0% | no output / 7 / 11 | 12,541 / 7 / 11 | 63,076 / 9 / 13 | 18,870 / 9 / 14 |
| 3 (strongest) | 40% | 13,289 / 6 / 10 | 12,732 / 6 / 10 | 69,364 / 9 / 14 | 21,040 / 9 / 14 |
| 4 (strongest) | 70% | 12,669 / 6 / 10 | 10,838 / 6 / 8 | 66,884 / 8 / 12 | 24,835 / 9 / 13 |
| 6 (strongest) | 100% | 16,998 / 0 / 0 | 12,125 / 4 / 10 | 86,684 / 0 / 0 | 22,464 / 8 / 11 |
| all | 100% | 19,021 / 0 / 0 | 16,730 / 0 / 0 | 80,554 / 0 / 0 | 23,034 / 0 / 0 |
| 3 (random) | 45% | 13,686 / 6 / 9 | 15,666 / 5 / 8 | 75,780 / 9 / 12 | 16,964 / 9 / 14 |
| 4 (random) | 75% | 10,716 / 6 / 10 | 10,334 / 6 / 10 | 90,846 / 9 / 13 | 23,293 / 9 / 14 |
| 6 (random) | 100% | 13,952 / 5 / 8 | 13,780 / 5 / 8 | 75,439 / 9 / 14 | 24,149 / 8 / 13 |

## Error model `honest`

| Towers (rule) | Sites ≥ 3 on air | towers | baro | imu | baro+imu |
|---|---|---|---|---|---|
| 0 | 0% | no output / 0 / 0 | 2,871 / 6 / 11 | 23,274 / 9 / 13 | 11,979 / 9 / 14 |
| 1 (strongest) | 0% | no output / 7 / 11 | 2,780 / 7 / 11 | 3,324 / 9 / 13 | 3,097 / 9 / 13 |
| 2 (strongest) | 0% | no output / 5 / 10 | 2,272 / 5 / 10 | 2,892 / 9 / 13 | 2,957 / 9 / 14 |
| 3 (strongest) | 40% | 1,019 / 5 / 7 | 1,966 / 5 / 7 | 2,892 / 9 / 12 | 3,406 / 7 / 11 |
| 4 (strongest) | 70% | 840 / 5 / 7 | 2,259 / 5 / 7 | 1,515 / 9 / 12 | 2,168 / 7 / 12 |
| 6 (strongest) | 100% | 404 / 6 / 9 | 774 / 6 / 9 | 890 / 9 / 12 | 440 / 9 / 13 |
| all | 100% | 110 / 5 / 8 | 108 / 5 / 8 | 115 / 8 / 11 | 116 / 9 / 14 |
| 3 (random) | 45% | 1,545 / 7 / 10 | 1,720 / 7 / 10 | 3,730 / 10 / 13 | 1,894 / 11 / 17 |
| 4 (random) | 75% | 866 / 6 / 8 | 1,739 / 6 / 8 | 2,558 / 9 / 12 | 1,636 / 10 / 12 |
| 6 (random) | 100% | 850 / 5 / 6 | 556 / 5 / 6 | 670 / 8 / 10 | 539 / 8 / 11 |

## Error model `clean`

| Towers (rule) | Sites ≥ 3 on air | towers | baro | imu | baro+imu |
|---|---|---|---|---|---|
| 0 | 0% | no output / 0 / 0 | 2,871 / 6 / 11 | 23,274 / 9 / 13 | 11,979 / 9 / 14 |
| 1 (strongest) | 0% | no output / 7 / 11 | 2,968 / 7 / 11 | 2,344 / 9 / 13 | 2,285 / 9 / 13 |
| 2 (strongest) | 0% | no output / 8 / 13 | 1,450 / 8 / 13 | 3,799 / 10 / 16 | 3,148 / 9 / 16 |
| 3 (strongest) | 40% | 874 / 8 / 14 | 824 / 8 / 14 | 938 / 13 / 27 | 645 / 13 / 24 |
| 4 (strongest) | 70% | 512 / 13 / 19 | 550 / 13 / 19 | 124 / 16 / 55 | 324 / 17 / 28 |
| 6 (strongest) | 100% | 414 / 51 / 175 | 64 / 55 / 176 | 60 / 58 / 120 | 46 / 59 / 300 |
| all | 100% | 12 / 300 / 300 | 10 / 300 / 300 | 10 / 300 / 300 | 10 / 300 / 300 |
| 3 (random) | 45% | 883 / 9 / 16 | 1,056 / 9 / 16 | 2,630 / 15 / 24 | 584 / 15 / 25 |
| 4 (random) | 75% | 543 / 15 / 30 | 195 / 15 / 30 | 417 / 16 / 53 | 117 / 25 / 60 |
| 6 (random) | 100% | 129 / 51 / 58 | 123 / 56 / 58 | 113 / 45 / 55 | 79 / 45 / 58 |

## Geometry: snapshot HDOP of the N strongest sites over the route

Unit range noise, the towers' own clocks known. Median / worst over the route; `no fix` where the sites are fewer than the unknowns.

| N | x, y, clock (baro gives height) | x, y, z, clock (no baro) | x, y (baro, held clock) |
|---|---|---|---|
| 1 | no fix | no fix | no fix |
| 2 | no fix | no fix | 5.81 / 2998.3 |
| 3 | 6.34 / 5571 | no fix | 1.76 / 11.9 |
| 4 | 1.1 / 1.4 | 1.29 / 1.6 | 1.09 / 1.2 |
| 6 | 0.94 / 1 | 0.98 / 1 | 0.89 / 0.9 |
| all | 0.52 / 0.5 | 0.53 / 0.5 | 0.51 / 0.5 |

Strongest six, in order (median power over the route): eNB 30018 (0.18 km, -29.2 dBm), eNB 30276 (0.6 km, -40.5 dBm), eNB 30141 (0.94 km, -45.4 dBm), eNB 30015 (1.68 km, -47.0 dBm), eNB 30075 (1.42 km, -48.8 dBm), eNB 37257 (2.32 km, -53.3 dBm). Matched sites in the table: 86; within 3 km of the origin: 17 (`all`, and the `random` pool).

## Runtime

Median s per filter run: 2.0; worst 13.2.
