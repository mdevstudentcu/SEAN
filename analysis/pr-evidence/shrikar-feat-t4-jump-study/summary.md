# Location-jump study (f17475e, sim)

Seeds 0..49 per row; seed k jumps towards 45° x (k mod 8). Jump at t = 150 s, held to the end of the 360 s run. Command: `python analysis/jump_study.py --runs 50 --jobs N --out DIR`. Environments: `realistic-uc01` is `realistic-nominal` (realistic set) flown on `uc01-drone-circuit`'s route; `uc01` is `uc01-drone-circuit` as committed. Faults removed from both first.

## Findings per estimator

| env | estimator | smallest jump detected in >= 95% of runs (m) | undetected and over 50 m (m) | sizes with hazardous epochs (m) | false alarms / h (clean) |
| --- | --- | --- | --- | --- | --- |
| realistic-uc01 | ekf | 20 | none | 50, 100, 300, 1000 | 0.00 (0/50 runs) |
| realistic-uc01 | ekf-calibrated | 20 | none | 50, 100, 300, 1000 | 0.00 (0/50 runs) |
| realistic-uc01 | ekf-imu | 20 | none | 30, 50, 100, 300, 1000 | 0.00 (0/50 runs) |
| realistic-uc01 | ekf-mhss | 20 | none | none | 0.00 (0/50 runs) |
| uc01 | ekf | 20 | none | 50 | 0.00 (0/50 runs) |
| uc01 | ekf-calibrated | 20 | none | 50, 100, 300 | 0.00 (0/50 runs) |
| uc01 | ekf-imu | 20 | none | 20, 30, 50 | 0.00 (0/50 runs) |
| uc01 | ekf-mhss | 20 | none | none | 0.00 (0/50 runs) |

## Jumps

| env | estimator | jump m | drift m/s | P detect | detect med s | detect p95 s | alert med s | P absorbed | follows after med s | worst err med m | worst err max m | worst err when missed m | runs with HMI | HMI epochs | available before jump |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| realistic-uc01 | ekf | 5 | 0 | 0.00 | nan | nan | 71.4 | 1.00 | 0.3 | 9 | 10 | 10 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 10 | 0 | 0.00 | nan | nan | 0.5 | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 15 | 0 | 0.30 | 1.1 | 1.1 | 0.1 | 1.00 | 1.1 | 19 | 21 | 21 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.2 | 25 | 26 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 30 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 3.9 | 35 | 38 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 6.3 | 56 | 59 | nan | 50 | 51595 | 1.00 |
| realistic-uc01 | ekf | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.98 | 10.9 | 106 | 3908 | nan | 49 | 97413 | 1.00 |
| realistic-uc01 | ekf | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.98 | 24.9 | 308 | 3908 | nan | 48 | 77361 | 1.00 |
| realistic-uc01 | ekf | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.38 | 51.5 | 2097 | 3908 | nan | 13 | 5241 | 1.00 |
| realistic-uc01 | ekf-calibrated | 5 | 0 | 0.00 | nan | nan | 55.1 | 1.00 | 0.4 | 9 | 10 | 10 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 10 | 0 | 0.00 | nan | nan | 0.5 | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 15 | 0 | 0.30 | 1.1 | 1.1 | 0.1 | 1.00 | 1.1 | 19 | 21 | 21 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.3 | 25 | 26 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 30 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 3.9 | 35 | 38 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 6.3 | 56 | 59 | nan | 50 | 51545 | 1.00 |
| realistic-uc01 | ekf-calibrated | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 11.8 | 106 | 132 | nan | 50 | 98722 | 1.00 |
| realistic-uc01 | ekf-calibrated | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.84 | 53.3 | 306 | 637 | nan | 46 | 59180 | 1.00 |
| realistic-uc01 | ekf-calibrated | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.06 | 142.3 | 264 | 1895 | nan | 3 | 867 | 1.00 |
| realistic-uc01 | ekf-imu | 5 | 0 | 0.00 | nan | nan | 47.7 | 1.00 | 0.9 | 8 | 9 | 9 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 10 | 0 | 0.04 | 1.1 | 1.1 | 0.3 | 1.00 | 1.1 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 15 | 0 | 0.74 | 1.1 | 1.9 | 0.1 | 1.00 | 2.7 | 20 | 178 | 24 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 5.9 | 26 | 178 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 30 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 9.2 | 36 | 179 | nan | 1 | 77 | 1.00 |
| realistic-uc01 | ekf-imu | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.98 | 13.0 | 58 | 2720 | nan | 50 | 44403 | 1.00 |
| realistic-uc01 | ekf-imu | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.96 | 19.3 | 205 | 10127 | nan | 49 | 73151 | 1.00 |
| realistic-uc01 | ekf-imu | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.94 | 34.9 | 2797 | 12352 | nan | 48 | 22002 | 1.00 |
| realistic-uc01 | ekf-imu | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.60 | 66.1 | 2665 | 12342 | nan | 25 | 2902 | 1.00 |
| realistic-uc01 | ekf-mhss | 5 | 0 | 0.00 | nan | nan | nan | 1.00 | 0.3 | 9 | 10 | 10 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 10 | 0 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 15 | 0 | 0.30 | 1.1 | 1.1 | nan | 1.00 | 1.1 | 19 | 21 | 21 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 20 | 0 | 1.00 | 1.1 | 1.1 | nan | 1.00 | 2.2 | 25 | 26 | nan | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 30 | 0 | 1.00 | 1.1 | 1.1 | nan | 1.00 | 3.9 | 35 | 38 | nan | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 50 | 0 | 1.00 | 1.1 | 1.1 | nan | 1.00 | 6.3 | 56 | 59 | nan | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 100 | 0 | 1.00 | 1.1 | 1.1 | nan | 0.98 | 10.9 | 106 | 3908 | nan | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 300 | 0 | 1.00 | 1.1 | 1.1 | nan | 0.98 | 24.9 | 308 | 3908 | nan | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 1000 | 0 | 1.00 | 1.1 | 1.1 | nan | 0.38 | 51.5 | 2097 | 3908 | nan | 0 | 0 | 0.00 |
| uc01 | ekf | 5 | 0 | 0.00 | nan | nan | 80.3 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 1.00 |
| uc01 | ekf | 10 | 0 | 0.00 | nan | nan | 0.3 | 1.00 | 0.5 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf | 15 | 0 | 0.48 | 1.1 | 1.1 | 0.1 | 1.00 | 1.3 | 19 | 21 | 21 | 0 | 0 | 1.00 |
| uc01 | ekf | 20 | 0 | 0.98 | 1.1 | 1.1 | 0.1 | 1.00 | 2.3 | 24 | 27 | 24 | 0 | 0 | 1.00 |
| uc01 | ekf | 30 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 5.1 | 34 | 38 | nan | 0 | 0 | 1.00 |
| uc01 | ekf | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.94 | 32.9 | 55 | 57 | nan | 47 | 34994 | 1.00 |
| uc01 | ekf | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 27 | 41 | nan | 0 | 0 | 1.00 |
| uc01 | ekf | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 27 | 41 | nan | 0 | 0 | 1.00 |
| uc01 | ekf | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 27 | 41 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 5 | 0 | 0.00 | nan | nan | 80.4 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 10 | 0 | 0.02 | 1.1 | 1.1 | 0.3 | 1.00 | 0.5 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 15 | 0 | 0.48 | 1.1 | 1.1 | 0.1 | 1.00 | 1.3 | 19 | 21 | 21 | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.3 | 24 | 27 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 30 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 4.1 | 35 | 38 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 8.9 | 54 | 59 | nan | 50 | 51530 | 1.00 |
| uc01 | ekf-calibrated | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 52.7 | 104 | 106 | nan | 50 | 75960 | 1.00 |
| uc01 | ekf-calibrated | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.02 | 156.7 | 36 | 305 | nan | 1 | 533 | 1.00 |
| uc01 | ekf-calibrated | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 36 | 79 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 5 | 0 | 0.00 | nan | nan | 48.3 | 1.00 | 0.9 | 8 | 10 | 10 | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 10 | 0 | 0.08 | 1.1 | 1.4 | 0.1 | 1.00 | 1.3 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 15 | 0 | 0.86 | 1.1 | 1.7 | 0.1 | 1.00 | 2.9 | 20 | 22 | 22 | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 6.3 | 25 | 52 | nan | 2 | 19 | 1.00 |
| uc01 | ekf-imu | 30 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 13.3 | 35 | 66 | nan | 1 | 87 | 1.00 |
| uc01 | ekf-imu | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.38 | 85.1 | 26 | 59 | nan | 19 | 10866 | 1.00 |
| uc01 | ekf-imu | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 23 | 33 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 23 | 33 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 23 | 33 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-mhss | 5 | 0 | 0.00 | nan | nan | 1.5 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 10 | 0 | 0.00 | nan | nan | 1.4 | 1.00 | 0.5 | 14 | 16 | 16 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 15 | 0 | 0.48 | 1.1 | 1.1 | 2.2 | 1.00 | 1.3 | 19 | 21 | 21 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 20 | 0 | 0.98 | 1.1 | 1.1 | 3.5 | 1.00 | 2.3 | 24 | 28 | 24 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 30 | 0 | 1.00 | 1.1 | 1.1 | 4.2 | 1.00 | 5.1 | 35 | 38 | nan | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 50 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.86 | 32.9 | 55 | 57 | nan | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 100 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 27 | 41 | nan | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 300 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 27 | 41 | nan | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 1000 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | nan | 27 | 41 | nan | 0 | 0 | 0.32 |

## Jump then drift

| env | estimator | jump m | drift m/s | P detect | detect med s | detect p95 s | alert med s | P absorbed | follows after med s | worst err med m | worst err max m | worst err when missed m | runs with HMI | HMI epochs | available before jump |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| realistic-uc01 | ekf | 5 | 0.5 | 0.00 | nan | nan | 59.6 | 1.00 | 0.5 | 111 | 113 | 113 | 50 | 59943 | 1.00 |
| realistic-uc01 | ekf | 5 | 2 | 0.00 | nan | nan | 59.6 | 1.00 | 0.5 | 425 | 428 | 428 | 50 | 93718 | 1.00 |
| realistic-uc01 | ekf | 10 | 0.5 | 0.00 | nan | nan | 0.3 | 1.00 | 0.5 | 116 | 118 | 118 | 50 | 64978 | 1.00 |
| realistic-uc01 | ekf | 10 | 2 | 0.00 | nan | nan | 0.3 | 1.00 | 0.6 | 430 | 433 | 433 | 50 | 95003 | 1.00 |
| realistic-uc01 | ekf-calibrated | 5 | 0.5 | 0.00 | nan | nan | 55.1 | 1.00 | 0.5 | 111 | 113 | 113 | 50 | 59931 | 1.00 |
| realistic-uc01 | ekf-calibrated | 5 | 2 | 0.00 | nan | nan | 55.1 | 1.00 | 0.5 | 425 | 428 | 428 | 50 | 93715 | 1.00 |
| realistic-uc01 | ekf-calibrated | 10 | 0.5 | 0.00 | nan | nan | 0.3 | 1.00 | 0.5 | 116 | 118 | 118 | 50 | 64963 | 1.00 |
| realistic-uc01 | ekf-calibrated | 10 | 2 | 0.00 | nan | nan | 0.3 | 1.00 | 0.6 | 430 | 433 | 433 | 50 | 95004 | 1.00 |
| realistic-uc01 | ekf-imu | 5 | 0.5 | 0.00 | nan | nan | 44.2 | 1.00 | 0.9 | 110 | 112 | 112 | 50 | 59904 | 1.00 |
| realistic-uc01 | ekf-imu | 5 | 2 | 0.00 | nan | nan | 20.7 | 1.00 | 1.2 | 425 | 427 | 427 | 50 | 93684 | 1.00 |
| realistic-uc01 | ekf-imu | 10 | 0.5 | 0.04 | 1.1 | 1.1 | 0.3 | 1.00 | 1.3 | 115 | 117 | 117 | 50 | 65015 | 1.00 |
| realistic-uc01 | ekf-imu | 10 | 2 | 0.24 | 1.1 | 2.5 | 0.3 | 1.00 | 1.5 | 430 | 432 | 432 | 50 | 94700 | 1.00 |
| realistic-uc01 | ekf-mhss | 5 | 0.5 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 111 | 113 | 113 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 5 | 2 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 425 | 428 | 428 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 10 | 0.5 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 116 | 118 | 118 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 10 | 2 | 0.00 | nan | nan | nan | 1.00 | 0.6 | 430 | 433 | 433 | 0 | 0 | 0.00 |
| uc01 | ekf | 5 | 0.5 | 0.00 | nan | nan | 80.7 | 1.00 | 0.5 | 111 | 113 | 113 | 50 | 59658 | 1.00 |
| uc01 | ekf | 5 | 2 | 0.00 | nan | nan | 77.4 | 1.00 | 0.5 | 425 | 428 | 428 | 50 | 93599 | 1.00 |
| uc01 | ekf | 10 | 0.5 | 0.02 | 1.1 | 1.1 | 1.1 | 1.00 | 0.5 | 116 | 118 | 118 | 50 | 64772 | 1.00 |
| uc01 | ekf | 10 | 2 | 0.02 | 1.1 | 1.1 | 0.3 | 1.00 | 0.5 | 430 | 433 | 433 | 50 | 94910 | 1.00 |
| uc01 | ekf-calibrated | 5 | 0.5 | 0.00 | nan | nan | 80.4 | 1.00 | 0.5 | 111 | 113 | 113 | 50 | 59928 | 1.00 |
| uc01 | ekf-calibrated | 5 | 2 | 0.04 | 88.1 | 96.2 | 80.3 | 0.98 | 0.5 | 425 | 428 | 428 | 50 | 91340 | 1.00 |
| uc01 | ekf-calibrated | 10 | 0.5 | 0.02 | 1.1 | 1.1 | 0.3 | 1.00 | 0.5 | 116 | 118 | 118 | 50 | 65037 | 1.00 |
| uc01 | ekf-calibrated | 10 | 2 | 0.06 | 79.1 | 94.4 | 0.3 | 0.98 | 0.5 | 430 | 433 | 433 | 50 | 92608 | 1.00 |
| uc01 | ekf-imu | 5 | 0.5 | 0.00 | nan | nan | 61.1 | 1.00 | 0.9 | 110 | 112 | 112 | 50 | 59593 | 1.00 |
| uc01 | ekf-imu | 5 | 2 | 0.00 | nan | nan | 36.0 | 1.00 | 1.1 | 425 | 427 | 427 | 50 | 93574 | 1.00 |
| uc01 | ekf-imu | 10 | 0.5 | 0.10 | 1.1 | 1.5 | 0.1 | 1.00 | 1.3 | 115 | 117 | 117 | 50 | 64729 | 1.00 |
| uc01 | ekf-imu | 10 | 2 | 0.18 | 1.1 | 1.4 | 0.1 | 0.92 | 1.3 | 430 | 432 | 432 | 46 | 87168 | 1.00 |
| uc01 | ekf-mhss | 5 | 0.5 | 0.08 | 137.1 | 150.4 | 1.2 | 0.76 | 0.5 | 111 | 113 | 113 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 5 | 2 | 0.12 | 47.6 | 126.1 | 0.9 | 0.76 | 0.5 | 425 | 428 | 428 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 10 | 0.5 | 0.12 | 119.1 | 149.8 | 0.8 | 0.76 | 0.5 | 116 | 118 | 118 | 0 | 0 | 0.32 |
| uc01 | ekf-mhss | 10 | 2 | 0.14 | 41.1 | 124.7 | 0.7 | 0.76 | 0.5 | 430 | 433 | 433 | 0 | 0 | 0.32 |

Definitions: detect = an alarm flag held 1 s after the jump (`pnt.metrics`); alert = any alert switching on after the jump (nan when the estimate was already `unsafe`); absorbed = over the last 30 s the along-jump error is at least half the spoofed offset; HMI = error over the 50 m alert limit (TBC) while HPL is within it; available before jump = share of pre-jump epochs not `unsafe` (HPL within the alert limit).
