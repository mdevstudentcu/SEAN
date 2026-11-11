# VOR ablation, uc02-yow-approach-vor

Sim, every error value `TBC`. Commit `0906beaa400c`, `python analysis/vor_ablation.py --runs 50 --jobs 3 --out analysis/results/vor-ablation`. Seeds 0-49, paired: towers = the same run with its `vor` records dropped. The scenario has no IMU records, so `ekf-imu` predicts as `ekf` does. Every summary number equal to `ekf`'s (to 1e-9, relative): `ekf-imu`, `ekf-mhss`.

| Estimator | Condition | Outage p95, median / worst (seed) (m) | Outage max, worst (seed) (m) | HPL >= error, mean / min | Misleading epochs | NEES median | p95 change with VOR, median [min, max] (m) | Seeds better / worse (sign test p) |
|---|---|---|---|---|---|---|---|---|
| `ekf` | towers | 46.2 / 78.4 (6) | 102.9 (11) | 1.000 / 1.000 | 0 | 1.40 | - | - |
| `ekf` | +VOR | 42.9 / 74.1 (6) | 92.8 (6) | 1.000 / 1.000 | 0 | 1.38 | -0.7 [-36.0, +3.9] | 30 / 20 (0.20) |
| `ekf-imu` | towers | 46.2 / 78.4 (6) | 102.9 (11) | 1.000 / 1.000 | 0 | 1.40 | - | - |
| `ekf-imu` | +VOR | 42.9 / 74.1 (6) | 92.8 (6) | 1.000 / 1.000 | 0 | 1.38 | -0.7 [-36.0, +3.9] | 30 / 20 (0.20) |
| `ekf-mhss` | towers | 46.2 / 78.4 (6) | 102.9 (11) | 1.000 / 1.000 | 0 | 1.40 | - | - |
| `ekf-mhss` | +VOR | 42.9 / 74.1 (6) | 92.8 (6) | 1.000 / 1.000 | 0 | 1.38 | -0.7 [-36.0, +3.9] | 30 / 20 (0.20) |
