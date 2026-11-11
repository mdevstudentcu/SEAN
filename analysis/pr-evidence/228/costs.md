# Keeping our clock in the tower ranges without its costs (#228, ADR-0045)

Commit `8b7cbda`, seeds 0-49 (paired), sim with placeholder models. Δ: mean paired difference from `ekf` in the same rows ± its standard error. Rows marked *sim: towers carry our clock* rerun that scenario with `receiver_clock: true` (a sim change: they pair only with each other).

| Scenario | Variant | p95 mean (m) | Δ p95 (m) | T1 p95 mean (m) | Δ T1 (m) | T1 HPL bound, worst run | Misleading / run | Δ misleading | Hazardous / run | Δ hazardous |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gps-outage` | `ekf` | 15.5 | +0.0 ± 0.0 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `gps-outage` | `ekf +rx clock` | 17.6 | +2.1 ± 0.8 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `gps-outage` | `ekf rx clock observed` | 15.5 | +0.0 ± 0.0 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `gps-outage` | `ekf rx clock gnss_out` | 18.1 | +2.7 ± 1.2 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `gps-outage` | `ekf +rx clock, h_2 2e-22` | 15.9 | +0.4 ± 0.2 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `gps-outage` | `ekf-guard` | 15.5 | +0.0 ± 0.0 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `gps-outage` | `ekf-guard +rx clock` | 17.6 | +2.1 ± 0.8 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `spoof-ramp` | `ekf` | 341.0 | +0.0 ± 0.0 | — | — | — | 1872.5 | +0.0 ± 0.0 | 1621.3 | +0.0 ± 0.0 |
| `spoof-ramp` | `ekf +rx clock` | 349.9 | +8.9 ± 12.2 | — | — | — | 1923.5 | +51.1 ± 60.9 | 1672.0 | +50.7 ± 61.3 |
| `spoof-ramp` | `ekf rx clock observed` | 341.0 | +0.0 ± 0.0 | — | — | — | 1872.5 | +0.0 ± 0.0 | 1621.3 | +0.0 ± 0.0 |
| `spoof-ramp` | `ekf rx clock gnss_out` | 345.7 | +4.7 ± 5.1 | — | — | — | 1895.1 | +22.7 ± 26.1 | 1643.9 | +22.6 ± 26.1 |
| `spoof-ramp` | `ekf +rx clock, h_2 2e-22` | 351.8 | +10.8 ± 12.0 | — | — | — | 1933.5 | +61.1 ± 59.6 | 1682.6 | +61.3 ± 59.8 |
| `spoof-ramp` | `ekf-guard` | 333.7 | -7.2 ± 7.2 | — | — | — | 1830.6 | -41.8 ± 41.8 | 1584.3 | -37.0 ± 37.0 |
| `spoof-ramp` | `ekf-guard +rx clock` | 342.7 | +1.7 ± 14.2 | — | — | — | 1881.7 | +9.3 ± 74.4 | 1635.0 | +13.7 ± 72.1 |
| `meaconing` | `ekf` | 41.3 | +0.0 ± 0.0 | — | — | — | 1988.1 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `meaconing` | `ekf +rx clock` | 41.6 | +0.3 ± 0.0 | — | — | — | 2048.6 | +60.5 ± 9.6 | 0.0 | +0.0 ± 0.0 |
| `meaconing` | `ekf rx clock observed` | 41.6 | +0.3 ± 0.0 | — | — | — | 2048.6 | +60.5 ± 9.6 | 0.0 | +0.0 ± 0.0 |
| `meaconing` | `ekf rx clock gnss_out` | 443.5 | +402.2 ± 85.5 | — | — | — | 1399.3 | -588.8 ± 94.4 | 2.1 | +2.1 ± 0.7 |
| `meaconing` | `ekf +rx clock, h_2 2e-22` | 41.6 | +0.3 ± 0.0 | — | — | — | 2048.6 | +60.5 ± 9.6 | 0.0 | +0.0 ± 0.0 |
| `meaconing` | `ekf-guard` | 18.1 | -23.2 ± 0.3 | — | — | — | 0.0 | -1988.1 ± 9.7 | 0.0 | +0.0 ± 0.0 |
| `meaconing` | `ekf-guard +rx clock` | 5770.8 | +5729.5 ± 131.3 | — | — | — | 0.0 | -1988.1 ± 9.7 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` | `ekf` | 19.7 | +0.0 ± 0.0 | 20.4 | +0.0 ± 0.0 | 1.000 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` | `ekf +rx clock` | 4261.2 | +4241.5 ± 237.4 | 4314.2 | +4293.9 ± 241.8 | 0.227 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` | `ekf rx clock observed` | 4261.2 | +4241.5 ± 237.4 | 4314.2 | +4293.9 ± 241.8 | 0.227 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` | `ekf rx clock gnss_out` | 561.3 | +541.6 ± 103.8 | 573.2 | +552.9 ± 104.8 | 0.027 | 4.4 | +4.4 ± 1.1 | 4.0 | +4.0 ± 1.0 |
| `easy-long-outage` | `ekf +rx clock, h_2 2e-22` | 5978.4 | +5958.7 ± 218.0 | 6086.0 | +6065.6 ± 214.8 | 0.333 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` | `ekf-guard` | 19.7 | +0.0 ± 0.0 | 20.4 | +0.0 ± 0.0 | 1.000 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` | `ekf-guard +rx clock` | 4261.2 | +4241.5 ± 237.4 | 4314.2 | +4293.9 ± 241.8 | 0.227 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf` | 2331.3 | +0.0 ± 0.0 | 2350.8 | +0.0 ± 0.0 | 0.027 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf +rx clock` | 317.6 | -2013.6 ± 67.5 | 331.7 | -2019.1 ± 67.8 | 0.631 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf rx clock observed` | 317.6 | -2013.6 ± 67.5 | 331.7 | -2019.1 ± 67.8 | 0.631 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf rx clock gnss_out` | 621.7 | -1709.5 ± 84.5 | 636.8 | -1714.0 ± 84.6 | 0.162 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf +rx clock, h_2 2e-22` | 285.9 | -2045.3 ± 69.5 | 297.7 | -2053.1 ± 69.4 | 0.679 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf-guard` | 2331.3 | +0.0 ± 0.0 | 2350.8 | +0.0 ± 0.0 | 0.027 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-long-outage` | `ekf-guard +rx clock` | 317.6 | -2013.6 ± 67.5 | 331.7 | -2019.1 ± 67.8 | 0.631 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-outage` | `ekf` | 2668.8 | +0.0 ± 0.0 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-outage` | `ekf +rx clock` | 196.4 | -2472.4 ± 70.5 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-outage` | `ekf rx clock observed` | 196.4 | -2472.4 ± 70.5 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-outage` | `ekf rx clock gnss_out` | 990.4 | -1678.4 ± 91.5 | — | — | — | 3.6 | +3.6 ± 1.4 | 0.9 | +0.9 ± 0.4 |
| `realistic-outage` | `ekf +rx clock, h_2 2e-22` | 163.5 | -2505.3 ± 70.3 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-outage` | `ekf-guard` | 2668.8 | +0.0 ± 0.0 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `realistic-outage` | `ekf-guard +rx clock` | 196.4 | -2472.4 ± 70.5 | — | — | — | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `meaconing` (sim: towers carry our clock) | `ekf` | 41.6 | +0.0 ± 0.0 | — | — | — | 2048.6 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `meaconing` (sim: towers carry our clock) | `ekf +rx clock` | 41.4 | -0.3 ± 0.0 | — | — | — | 1995.5 | -53.1 ± 8.7 | 0.0 | +0.0 ± 0.0 |
| `meaconing` (sim: towers carry our clock) | `ekf-guard` | 7002.1 | +6960.4 ± 233.6 | — | — | — | 0.0 | -2048.6 ± 0.7 | 0.0 | +0.0 ± 0.0 |
| `meaconing` (sim: towers carry our clock) | `ekf-guard +rx clock` | 20.1 | -21.5 ± 0.8 | — | — | — | 0.0 | -2048.6 ± 0.7 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` (sim: towers carry our clock) | `ekf` | 7813.9 | +0.0 ± 0.0 | 7903.5 | +0.0 ± 0.0 | 0.224 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` (sim: towers carry our clock) | `ekf +rx clock` | 21.8 | -7792.0 ± 693.0 | 22.6 | -7881.0 ± 704.8 | 1.000 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` (sim: towers carry our clock) | `ekf-guard` | 7813.9 | +0.0 ± 0.0 | 7903.5 | +0.0 ± 0.0 | 0.224 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
| `easy-long-outage` (sim: towers carry our clock) | `ekf-guard +rx clock` | 21.8 | -7792.0 ± 693.0 | 22.6 | -7881.0 ± 704.8 | 1.000 | 0.0 | +0.0 ± 0.0 | 0.0 | +0.0 ± 0.0 |
