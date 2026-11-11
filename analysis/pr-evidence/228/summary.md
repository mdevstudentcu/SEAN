# Our clock in the tower ranges (#228)

Commit `37d66b7`, seeds 0-49 (paired), sim with placeholder models. T1: p95 horizontal error over the first 300 s after GPS loss (`outage_h_p95_300s_m`); its HPL bound is the worst run's share of those epochs with HPL >= error. Gate: share of updates accepted while GPS is lost (median NIS), all runs pooled.

| Scenario | Variant | T1 p95 mean (m) | T1 worst run (m) | T1 HPL bound, worst run | p95 mean (m) | HPL bound, worst run | Misleading / run | Hazardous / run | LTE gate (NIS) | Baro gate (NIS) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `realistic-long-outage` | `ekf` | 2350.8 | 3777.3 | 0.027 | 2331.3 | 0.189 | 0.0 | 0.0 | 0.73 (1.7) | 1.00 (0.4) |
| `realistic-long-outage` | `ekf +rx clock` | 331.7 | 787.4 | 0.631 | 317.6 | 0.692 | 0.0 | 0.0 | 0.99 (0.6) | 1.00 (0.4) |
| `realistic-long-outage` | `ekf-imu` | 2772.5 | 21410.0 | 0.044 | 2741.7 | 0.203 | 0.0 | 0.0 | 0.64 (2.7) | 1.00 (0.5) |
| `realistic-long-outage` | `ekf-imu +rx clock` | 301.6 | 1005.9 | 0.574 | 292.7 | 0.645 | 0.0 | 0.0 | 0.99 (0.6) | 1.00 (0.4) |
| `realistic-long-outage` | `ekf-calibrated` | 369.5 | 1039.8 | 0.887 | 360.5 | 0.906 | 0.0 | 0.0 | 1.00 (0.5) | 1.00 (0.4) |
| `realistic-long-outage` | `ekf-calibrated -rx clock` | 1474.2 | 2345.5 | 0.102 | 1462.7 | 0.252 | 0.0 | 0.0 | 1.00 (0.5) | 1.00 (0.4) |
| `realistic-long-outage` | `baseline` | 2350.8 | 3777.3 | 0.027 | 2331.3 | 0.189 | 0.0 | 0.0 | — | — |
| `realistic-outage` | `ekf` | — | — | — | 2668.8 | 0.481 | 0.0 | 0.0 | 0.21 (39.0) | 1.00 (0.4) |
| `realistic-outage` | `ekf +rx clock` | — | — | — | 196.4 | 0.811 | 0.0 | 0.0 | 0.99 (0.6) | 1.00 (0.4) |
| `realistic-nominal` | `ekf` | — | — | — | 3.0 | 1.000 | 0.0 | 0.0 | — | — |
| `realistic-nominal` | `ekf +rx clock` | — | — | — | 3.0 | 1.000 | 0.0 | 0.0 | — | — |
| `worst-long-outage` | `ekf` | 10404.1 | 16339.1 | 0.060 | 10267.0 | 0.217 | 0.0 | 0.0 | 0.12 (58.9) | 1.00 (0.4) |
| `worst-long-outage` | `ekf +rx clock` | 2067.9 | 5055.2 | 0.127 | 2035.0 | 0.272 | 0.0 | 0.0 | 0.45 (12.2) | 1.00 (0.4) |
| `nominal` | `ekf` | — | — | — | 5.4 | 0.960 | 48.1 | 0.0 | — | — |
| `nominal` | `ekf +rx clock` | — | — | — | 5.4 | 0.961 | 48.5 | 0.0 | — | — |
| `gps-outage` | `ekf` | — | — | — | 15.5 | 1.000 | 0.0 | 0.0 | 1.00 (0.4) | 1.00 (0.4) |
| `gps-outage` | `ekf +rx clock` | — | — | — | 17.6 | 1.000 | 0.0 | 0.0 | 1.00 (0.4) | 1.00 (0.4) |
| `spoof-ramp` | `ekf` | — | — | — | 341.0 | 0.407 | 1872.5 | 1621.3 | — | — |
| `spoof-ramp` | `ekf +rx clock` | — | — | — | 349.9 | 0.407 | 1923.5 | 1672.0 | — | — |
| `meaconing` | `ekf` | — | — | — | 41.3 | 0.429 | 1988.1 | 0.0 | — | — |
| `meaconing` | `ekf +rx clock` | — | — | — | 41.6 | 0.427 | 2048.6 | 0.0 | — | — |
| `challenge-approach-outage` | `ekf` | 2344.0 | 4984.2 | 0.085 | 4020.9 | 0.119 | 0.0 | 0.0 | 0.96 (0.9) | 1.00 (0.4) |
| `challenge-approach-outage` | `ekf +rx clock` | 1448.7 | 3398.5 | 0.540 | 3839.6 | 0.603 | 0.2 | 0.0 | 0.99 (0.8) | 1.00 (0.4) |
| `challenge-drone-outage` | `ekf` | 4944.0 | 16638.9 | 0.107 | 16025.1 | 0.128 | 7.2 | 6.4 | 0.02 (149.5) | 1.00 (0.4) |
| `challenge-drone-outage` | `ekf +rx clock` | 4944.0 | 16638.9 | 0.107 | 16025.1 | 0.128 | 7.2 | 6.4 | 0.02 (149.5) | 1.00 (0.4) |

## Mechanism: `realistic-long-outage`, `ekf`, simulated clock drift

| Drift (ppb) | Towers | T1 p95 mean (m) | T1 HPL bound, worst run | LTE gate (NIS) |
| --- | --- | --- | --- | --- |
| 0 | kept | 304.1 | 0.708 | 0.98 (0.7) |
| 0 | dropped | 2292.3 | 1.000 | — |
| 20 | kept | 2350.8 | 0.027 | 0.73 (1.7) |
| 20 | dropped | 2292.3 | 1.000 | — |
| 40 | kept | 4238.9 | 0.084 | 0.60 (2.8) |
| 40 | dropped | 2292.3 | 1.000 | — |

Figures: `error_vs_hpl.png` (seed 39), `drift.png`.
