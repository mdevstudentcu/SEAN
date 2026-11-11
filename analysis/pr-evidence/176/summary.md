# Location-jump study (f561d53, sim)

Seeds 0..15 per row; seed k jumps towards 45° x (k mod 8). Jump at t = 150 s, held to the end of the 360 s run. Command: `python analysis/jump_study.py --runs 16 --jobs N --out DIR`. Environments: `realistic-uc01` is `realistic-nominal` (realistic set) flown on `uc01-drone-circuit`'s route; `uc01` is `uc01-drone-circuit` as committed. Faults removed from both first. Jumps of 20 m to 500 km, with and without the jump guard: `analysis/guard_jump_sizes.py` (ADR-0038).

## Findings per estimator

| env | estimator | smallest jump detected in >= 95% of runs (m) | undetected and over 50 m (m) | sizes with hazardous epochs (m) | false alarms / h (clean) |
| --- | --- | --- | --- | --- | --- |
| realistic-uc01 | ekf | 20 | none | none | 0.00 (0/16 runs) |
| realistic-uc01 | ekf-calibrated | 20 | none | none | 0.00 (0/16 runs) |
| realistic-uc01 | ekf-imu | 20 | none | none | 0.00 (0/16 runs) |
| realistic-uc01 | ekf-mhss | 20 | none | none | 0.00 (0/16 runs) |
| realistic-uc01 | ekf-guard | 20 | none | none | 0.00 (0/16 runs) |
| uc01 | ekf | 20 | none | none | 0.00 (0/16 runs) |
| uc01 | ekf-calibrated | 20 | none | none | 0.00 (0/16 runs) |
| uc01 | ekf-imu | 15 | none | none | 0.00 (0/16 runs) |
| uc01 | ekf-mhss | 20 | none | none | 0.00 (0/16 runs) |
| uc01 | ekf-guard | 20 | none | none | 0.00 (0/16 runs) |

## Jumps

| env | estimator | jump m | drift m/s | P detect | detect med s | detect p95 s | alert med s | P absorbed | follows after med s | worst err med m | worst err max m | worst err when missed m | runs with HMI | HMI epochs | available before jump |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| realistic-uc01 | ekf | 5 | 0 | 0.00 | nan | nan | 86.9 | 1.00 | 0.3 | 9 | 10 | 10 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 10 | 0 | 0.00 | nan | nan | 28.7 | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 15 | 0 | 0.25 | 1.1 | 1.1 | 0.1 | 1.00 | 1.1 | 20 | 21 | 21 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.1 | 25 | 26 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 5 | 0 | 0.00 | nan | nan | 83.3 | 1.00 | 0.3 | 9 | 10 | 10 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 10 | 0 | 0.00 | nan | nan | 8.1 | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 15 | 0 | 0.25 | 1.1 | 1.1 | 0.1 | 1.00 | 1.1 | 20 | 21 | 21 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-calibrated | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.1 | 25 | 26 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 5 | 0 | 0.00 | nan | nan | 56.1 | 1.00 | 0.8 | 8 | 9 | 9 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 10 | 0 | 0.06 | 1.1 | 1.1 | 0.3 | 1.00 | 0.9 | 14 | 15 | 15 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 15 | 0 | 0.75 | 1.1 | 1.2 | 0.1 | 1.00 | 2.5 | 20 | 49 | 21 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-imu | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 5.1 | 26 | 83 | nan | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-mhss | 5 | 0 | 0.00 | nan | nan | nan | 1.00 | 0.3 | 9 | 10 | 10 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 10 | 0 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 15 | 0 | 0.25 | 1.1 | 1.1 | nan | 1.00 | 1.1 | 20 | 21 | 21 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 20 | 0 | 1.00 | 1.1 | 1.1 | nan | 1.00 | 2.1 | 25 | 26 | nan | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-guard | 5 | 0 | 0.00 | nan | nan | 86.9 | 1.00 | 0.3 | 9 | 10 | 10 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-guard | 10 | 0 | 0.00 | nan | nan | 28.7 | 1.00 | 0.5 | 14 | 15 | 15 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-guard | 15 | 0 | 0.31 | 1.1 | 1.1 | 0.1 | 0.94 | 1.1 | 20 | 2083 | 21 | 0 | 0 | 1.00 |
| realistic-uc01 | ekf-guard | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.56 | 5.1 | 2093 | 2709 | nan | 0 | 0 | 1.00 |
| uc01 | ekf | 5 | 0 | 0.00 | nan | nan | 52.3 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 1.00 |
| uc01 | ekf | 10 | 0 | 0.00 | nan | nan | 1.1 | 1.00 | 0.5 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf | 15 | 0 | 0.69 | 1.1 | 1.1 | 0.1 | 1.00 | 1.6 | 19 | 21 | 21 | 0 | 0 | 1.00 |
| uc01 | ekf | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.5 | 24 | 26 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 5 | 0 | 0.00 | nan | nan | 63.1 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 10 | 0 | 0.00 | nan | nan | 0.3 | 1.00 | 0.5 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 15 | 0 | 0.69 | 1.1 | 1.1 | 0.1 | 1.00 | 1.6 | 20 | 21 | 21 | 0 | 0 | 1.00 |
| uc01 | ekf-calibrated | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 2.5 | 24 | 26 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 5 | 0 | 0.00 | nan | nan | 61.1 | 1.00 | 0.8 | 8 | 10 | 10 | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 10 | 0 | 0.00 | nan | nan | 0.3 | 1.00 | 1.1 | 14 | 16 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 15 | 0 | 1.00 | 1.1 | 1.2 | 0.1 | 1.00 | 3.0 | 20 | 22 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-imu | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 1.00 | 5.3 | 25 | 29 | nan | 0 | 0 | 1.00 |
| uc01 | ekf-mhss | 5 | 0 | 0.00 | nan | nan | 3.1 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 0.29 |
| uc01 | ekf-mhss | 10 | 0 | 0.00 | nan | nan | 1.1 | 1.00 | 0.5 | 14 | 16 | 16 | 0 | 0 | 0.29 |
| uc01 | ekf-mhss | 15 | 0 | 0.69 | 1.1 | 1.1 | 4.0 | 1.00 | 1.5 | 19 | 21 | 21 | 0 | 0 | 0.29 |
| uc01 | ekf-mhss | 20 | 0 | 1.00 | 1.1 | 1.1 | 4.2 | 1.00 | 2.4 | 24 | 28 | nan | 0 | 0 | 0.29 |
| uc01 | ekf-guard | 5 | 0 | 0.00 | nan | nan | 52.3 | 1.00 | 0.5 | 9 | 11 | 11 | 0 | 0 | 1.00 |
| uc01 | ekf-guard | 10 | 0 | 0.06 | 1.1 | 1.1 | 1.1 | 0.94 | 0.5 | 14 | 26 | 16 | 0 | 0 | 1.00 |
| uc01 | ekf-guard | 15 | 0 | 0.75 | 1.1 | 1.1 | 0.1 | 0.75 | 1.7 | 20 | 31 | 21 | 0 | 0 | 1.00 |
| uc01 | ekf-guard | 20 | 0 | 1.00 | 1.1 | 1.1 | 0.1 | 0.00 | 18.2 | 28 | 35 | nan | 0 | 0 | 1.00 |

## Jump then drift

| env | estimator | jump m | drift m/s | P detect | detect med s | detect p95 s | alert med s | P absorbed | follows after med s | worst err med m | worst err max m | worst err when missed m | runs with HMI | HMI epochs | available before jump |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| realistic-uc01 | ekf | 5 | 0.5 | 0.00 | nan | nan | 79.7 | 1.00 | 0.4 | 111 | 113 | 113 | 16 | 19157 | 1.00 |
| realistic-uc01 | ekf | 5 | 2 | 0.00 | nan | nan | 79.7 | 1.00 | 0.4 | 425 | 427 | 427 | 16 | 29982 | 1.00 |
| realistic-uc01 | ekf | 10 | 0.5 | 0.00 | nan | nan | 28.7 | 1.00 | 0.5 | 116 | 118 | 118 | 16 | 20722 | 1.00 |
| realistic-uc01 | ekf | 10 | 2 | 0.00 | nan | nan | 14.9 | 1.00 | 0.5 | 430 | 432 | 432 | 16 | 30380 | 1.00 |
| realistic-uc01 | ekf-calibrated | 5 | 0.5 | 0.00 | nan | nan | 67.9 | 1.00 | 0.4 | 111 | 113 | 113 | 16 | 19157 | 1.00 |
| realistic-uc01 | ekf-calibrated | 5 | 2 | 0.00 | nan | nan | 67.9 | 1.00 | 0.4 | 425 | 427 | 427 | 16 | 29982 | 1.00 |
| realistic-uc01 | ekf-calibrated | 10 | 0.5 | 0.00 | nan | nan | 18.4 | 1.00 | 0.5 | 116 | 118 | 118 | 16 | 20715 | 1.00 |
| realistic-uc01 | ekf-calibrated | 10 | 2 | 0.00 | nan | nan | 7.7 | 1.00 | 0.5 | 430 | 432 | 432 | 16 | 30380 | 1.00 |
| realistic-uc01 | ekf-imu | 5 | 0.5 | 0.00 | nan | nan | 56.1 | 1.00 | 0.8 | 110 | 111 | 111 | 16 | 19220 | 1.00 |
| realistic-uc01 | ekf-imu | 5 | 2 | 0.00 | nan | nan | 56.1 | 1.00 | 0.9 | 424 | 426 | 426 | 16 | 29993 | 1.00 |
| realistic-uc01 | ekf-imu | 10 | 0.5 | 0.12 | 1.1 | 1.1 | 0.3 | 1.00 | 0.9 | 115 | 116 | 116 | 16 | 20688 | 1.00 |
| realistic-uc01 | ekf-imu | 10 | 2 | 0.19 | 1.1 | 1.1 | 0.3 | 1.00 | 1.3 | 429 | 431 | 431 | 16 | 30144 | 1.00 |
| realistic-uc01 | ekf-mhss | 5 | 0.5 | 0.00 | nan | nan | nan | 1.00 | 0.4 | 111 | 113 | 113 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 5 | 2 | 0.00 | nan | nan | nan | 1.00 | 0.4 | 425 | 427 | 427 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 10 | 0.5 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 116 | 118 | 118 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-mhss | 10 | 2 | 0.00 | nan | nan | nan | 1.00 | 0.5 | 430 | 432 | 432 | 0 | 0 | 0.00 |
| realistic-uc01 | ekf-guard | 5 | 0.5 | 0.00 | nan | nan | 79.7 | 1.00 | 0.4 | 111 | 113 | 113 | 16 | 19157 | 1.00 |
| realistic-uc01 | ekf-guard | 5 | 2 | 0.00 | nan | nan | 79.7 | 1.00 | 0.4 | 425 | 427 | 427 | 16 | 29982 | 1.00 |
| realistic-uc01 | ekf-guard | 10 | 0.5 | 0.00 | nan | nan | 28.7 | 1.00 | 0.5 | 116 | 118 | 118 | 16 | 20722 | 1.00 |
| realistic-uc01 | ekf-guard | 10 | 2 | 0.00 | nan | nan | 14.9 | 1.00 | 0.5 | 430 | 432 | 432 | 16 | 30380 | 1.00 |
| uc01 | ekf | 5 | 0.5 | 0.00 | nan | nan | 52.3 | 1.00 | 0.5 | 111 | 113 | 113 | 16 | 19002 | 1.00 |
| uc01 | ekf | 5 | 2 | 0.00 | nan | nan | 51.5 | 1.00 | 0.5 | 425 | 428 | 428 | 16 | 29979 | 1.00 |
| uc01 | ekf | 10 | 0.5 | 0.00 | nan | nan | 1.1 | 1.00 | 0.5 | 116 | 118 | 118 | 16 | 20719 | 1.00 |
| uc01 | ekf | 10 | 2 | 0.00 | nan | nan | 0.3 | 1.00 | 0.5 | 430 | 433 | 433 | 16 | 30358 | 1.00 |
| uc01 | ekf-calibrated | 5 | 0.5 | 0.00 | nan | nan | 63.1 | 1.00 | 0.5 | 111 | 113 | 113 | 16 | 19088 | 1.00 |
| uc01 | ekf-calibrated | 5 | 2 | 0.12 | 88.1 | 96.2 | 52.3 | 0.94 | 0.5 | 425 | 428 | 428 | 16 | 27661 | 1.00 |
| uc01 | ekf-calibrated | 10 | 0.5 | 0.00 | nan | nan | 0.3 | 1.00 | 0.5 | 116 | 118 | 118 | 16 | 20779 | 1.00 |
| uc01 | ekf-calibrated | 10 | 2 | 0.12 | 87.6 | 95.2 | 4.1 | 0.94 | 0.5 | 430 | 433 | 433 | 16 | 28012 | 1.00 |
| uc01 | ekf-imu | 5 | 0.5 | 0.00 | nan | nan | 84.5 | 1.00 | 0.8 | 110 | 111 | 111 | 16 | 19011 | 1.00 |
| uc01 | ekf-imu | 5 | 2 | 0.00 | nan | nan | 73.9 | 1.00 | 1.0 | 425 | 426 | 426 | 16 | 29950 | 1.00 |
| uc01 | ekf-imu | 10 | 0.5 | 0.00 | nan | nan | 0.3 | 1.00 | 1.1 | 115 | 116 | 116 | 16 | 20628 | 1.00 |
| uc01 | ekf-imu | 10 | 2 | 0.06 | 2.1 | 2.1 | 0.3 | 1.00 | 1.3 | 430 | 431 | 431 | 16 | 30324 | 1.00 |
| uc01 | ekf-mhss | 5 | 0.5 | 0.06 | 141.1 | 141.1 | 3.0 | 0.69 | 0.5 | 111 | 113 | 113 | 0 | 0 | 0.29 |
| uc01 | ekf-mhss | 5 | 2 | 0.12 | 47.6 | 53.5 | 1.0 | 0.69 | 0.5 | 425 | 428 | 428 | 0 | 0 | 0.29 |
| uc01 | ekf-mhss | 10 | 0.5 | 0.12 | 109.0 | 139.7 | 0.8 | 0.69 | 0.5 | 116 | 118 | 118 | 0 | 0 | 0.29 |
| uc01 | ekf-mhss | 10 | 2 | 0.12 | 47.6 | 53.5 | 0.7 | 0.69 | 0.5 | 430 | 433 | 433 | 0 | 0 | 0.29 |
| uc01 | ekf-guard | 5 | 0.5 | 0.00 | nan | nan | 52.3 | 1.00 | 0.5 | 111 | 113 | 113 | 16 | 19002 | 1.00 |
| uc01 | ekf-guard | 5 | 2 | 0.00 | nan | nan | 51.5 | 1.00 | 0.5 | 425 | 428 | 428 | 16 | 29979 | 1.00 |
| uc01 | ekf-guard | 10 | 0.5 | 0.06 | 1.1 | 1.1 | 1.1 | 0.94 | 0.5 | 116 | 118 | 118 | 15 | 19444 | 1.00 |
| uc01 | ekf-guard | 10 | 2 | 0.06 | 1.1 | 1.1 | 0.3 | 0.94 | 0.5 | 430 | 433 | 433 | 15 | 28459 | 1.00 |

Definitions: detect = an alarm flag held 1 s after the jump (`pnt.metrics`); alert = any alert switching on after the jump (nan when the estimate was already `unsafe`); absorbed = over the last 30 s the along-jump error is at least half the spoofed offset; HMI = error over the 50 m alert limit (TBC) while HPL is within it; available before jump = share of pre-jump epochs not `unsafe` (HPL within the alert limit).
