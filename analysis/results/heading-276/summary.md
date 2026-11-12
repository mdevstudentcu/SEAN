# Heading at GPS loss (#276)

Commit `9c54a5d`, seeds 0–19 (20 runs per row), `python analysis/heading_at_loss.py --seeds 20 --jobs 3`, 320 s. Scenario: `challenge-drone-outage` cut to 360 s, built in `analysis/heading_at_loss.py` (module docstring). Every sensor value is `TBC`; sim only.

Statistic: ADR-0034's, the 95th percentile across runs at each second after GPS loss; *worst 0–300 s* is T1's (25 m), *worst 0–120 s* the fallback's (50 m). Heading error at loss: |vertical part of the rotation between the filter's attitude and the truth| at the loss; σ is the filter's own. ρ: Spearman rank correlation across runs of |heading error at loss| with the error at 120 s and 300 s.

## Horizontal acceleration while GPS is good (0–60 s)

| Path | RMS (m/s²) | Peak (m/s²) | Time over 1 m/s² (s) |
| --- | --- | --- | --- |
| plain | 0.29 | 0.50 | 0.0 |
| s-turns | 0.93 | 2.49 | 18.4 |

## Error after GPS loss against heading at loss

| Condition | Aligned at loss | Heading err. median / p95 (°) | Filter σ median (°) | p95 at 60 / 120 / 300 s (m) | Worst 0–120 s (m) | Worst 0–300 s (m) | ρ 120 s / 300 s | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| plain / LTE / ekf-imu | 20/20 | 37.8 / 144.6 | 17.8 | 995.2 / 4837.0 / 23202.8 | 4837.0 | 23202.8 (at 300 s) | 0.46 / 0.37 | T1 missed, fallback missed |
| plain / LTE / ekf-imu, align <= 60 deg | 0/20 | — / — | — | 1123.8 / 1657.0 / 8846.4 | 1657.0 | 8846.4 (at 300 s) | — / — | T1 missed, fallback missed |
| plain / LTE / ekf-imu-mag | 20/20 | 1.6 / 6.0 | 3.0 | 702.6 / 2210.4 / 8306.7 | 2210.4 | 8306.7 (at 300 s) | 0.16 / 0.41 | T1 missed, fallback missed |
| s-turns / LTE / ekf-imu | 20/20 | 2.7 / 132.6 | 2.9 | 1191.7 / 3970.1 / 14367.7 | 3970.1 | 14367.7 (at 300 s) | 0.27 / -0.09 | T1 missed, fallback missed |
| s-turns / LTE / ekf-imu, align <= 60 deg | 20/20 | 2.1 / 5.2 | 2.9 | 666.3 / 2270.6 / 20135.4 | 2270.6 | 20135.4 (at 300 s) | 0.14 / 0.18 | T1 missed, fallback missed |
| s-turns / LTE / ekf-imu-mag | 20/20 | 1.2 / 3.3 | 1.8 | 1043.8 / 2713.0 / 22831.4 | 2713.0 | 22831.4 (at 300 s) | 0.21 / 0.26 | T1 missed, fallback missed |
| plain / no LTE / ekf-imu | 20/20 | 37.8 / 153.7 | 18.1 | 661.3 / 3013.3 / 11828.8 | 3013.3 | 12009.8 (at 299 s) | 0.79 / 0.85 | T1 missed, fallback missed |
| plain / no LTE / ekf-imu, align <= 60 deg | 1/20 | 34.0 / 34.0 | 34.2 | 639.6 / 1317.9 / 2870.7 | 1317.9 | 2870.7 (at 300 s) | — / — | T1 missed, fallback missed |
| plain / no LTE / ekf-imu-mag | 20/20 | 1.6 / 6.0 | 3.0 | 244.9 / 793.4 / 2715.4 | 846.3 | 2799.6 (at 298 s) | 0.54 / 0.13 | T1 missed, fallback missed |
| s-turns / no LTE / ekf-imu | 20/20 | 2.8 / 134.0 | 2.9 | 783.6 / 1988.0 / 5290.9 | 1988.0 | 5502.1 (at 294 s) | 0.44 / 0.54 | T1 missed, fallback missed |
| s-turns / no LTE / ekf-imu, align <= 60 deg | 20/20 | 1.8 / 5.1 | 2.9 | 267.9 / 710.9 / 3260.5 | 778.3 | 3346.4 (at 297 s) | 0.29 / 0.25 | T1 missed, fallback missed |
| s-turns / no LTE / ekf-imu-mag | 20/20 | 1.3 / 3.4 | 1.8 | 257.3 / 754.6 / 3023.2 | 812.1 | 3166.9 (at 298 s) | 0.60 / 0.42 | T1 missed, fallback missed |
| tactical, plain / no LTE / filter tactical | 5/20 | 47.9 / 113.6 | 20.8 | 693.0 / 1443.7 / 3289.6 | 1443.7 | 3289.6 (at 300 s) | 0.70 / 0.70 | T1 missed, fallback missed |
| tactical, s-turns / no LTE / filter MPU6050, align <= 60 deg | 20/20 | 1.4 / 4.7 | 2.9 | 210.0 / 405.6 / 1109.8 | 454.6 | 1136.9 (at 295 s) | 0.44 / 0.02 | T1 missed, fallback missed |
| tactical, s-turns / no LTE / filter tactical | 20/20 | 1.2 / 3.7 | 1.6 | 54.2 / 91.5 / 363.7 | 98.0 | 364.2 (at 298 s) | 0.63 / 0.73 | T1 missed, fallback missed |
| tactical, s-turns / no LTE / filter tactical, floor 0.3 deg | 20/20 | 1.2 / 3.7 | 1.6 | 54.2 / 91.5 / 363.7 | 98.0 | 364.2 (at 298 s) | 0.63 / 0.73 | T1 missed, fallback missed |

## Magnetometer bias learned while GPS was good

| Condition | Largest true bias (°) | Median bias error at loss (°) |
| --- | --- | --- |
| plain / LTE / ekf-imu-mag | 7.4 | 1.70 |
| s-turns / LTE / ekf-imu-mag | 7.4 | 1.43 |
| plain / no LTE / ekf-imu-mag | 7.4 | 1.72 |
| s-turns / no LTE / ekf-imu-mag | 7.4 | 1.45 |

## Ablation: LTE against heading (REQ-06)

From `ekf-imu-mag` with LTE, one aid removed. Change in the worst p95 second (0–300 s / 0–120 s, m); negative: better without it. REQ-06 needs removing LTE to cost more than removing the magnetometer.

| Path | Both aids | Remove LTE | Remove magnetometer | Costs more to remove | REQ-06 |
| --- | --- | --- | --- | --- | --- |
| plain | 8,307 / 2,210 | 2,800 / 846 (-5,507 / -1,364) | 23,203 / 4,837 (+14,896 / +2,627) | heading (magnetometer) | not met |
| s-turns | 22,831 / 2,713 | 3,167 / 812 (-19,664 / -1,901) | 14,368 / 3,970 (-8,464 / +1,257) | heading (magnetometer) | not met |
