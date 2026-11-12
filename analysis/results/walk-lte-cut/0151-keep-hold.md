# LTE on a moving GPS cut, one change at a time: `20261111-0151-static-fullsuite2` (#214)

LTE records: `20261111-0151-static-fullsuite2-keep15`. `ekf`, options `{"lte_max_hdop": 3, "lte_gate_mode": "clock"}`. Cuts at 100, 150, 200, 250, 300 s. Median over the cuts, worst cut in brackets (m).

| Variant | 60 s | 120 s | 300 s | HPL ≥ error | p95 before the cut | Per cut, 60 / 120 / 300 s |
|---|---|---|---|---|---|---|
| `lte` | 115 (405) | 175 (813) | 776 (883) | 47 % | 1.9 | 182 / 154 / 792; 70 / 175 / 883; 405 / 813 / 776; 90 / 235 / 270; 115 / 116 / 151 |
