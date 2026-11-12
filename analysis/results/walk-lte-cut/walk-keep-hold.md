# LTE on a moving GPS cut, one change at a time: `20261111-1806-walk-lte` (#214)

LTE records: `20261111-1806-walk-lte-keep15`. `ekf`, options `{"lte_max_hdop": 3, "lte_gate_mode": "clock"}`. Cuts at 100, 418, 495, 818, 1049 s. Median over the cuts, worst cut in brackets (m).

| Variant | 60 s | 120 s | 300 s | HPL ≥ error | p95 before the cut | Per cut, 60 / 120 / 300 s |
|---|---|---|---|---|---|---|
| `lte` | 21 (205) | 53 (784) | 696 (3,100) | 100 % | 3.0 | 5 / 53 / 696; 21 / 53 / 686; 60 / 156 / 984; 205 / 784 / 3,100; 8 / 17 / 358 |
