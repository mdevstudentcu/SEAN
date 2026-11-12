# LTE on a moving GPS cut, one change at a time: `20261111-0233-static-lte-1h` (#214)

LTE records: `20261111-0233-static-lte-1h-keep15`. `ekf`, options `{"lte_max_hdop": 3, "lte_gate_mode": "clock"}`. Cuts at 600, 1200, 1800, 2400, 3000 s. Median over the cuts, worst cut in brackets (m).

| Variant | 60 s | 120 s | 300 s | HPL ≥ error | p95 before the cut | Per cut, 60 / 120 / 300 s |
|---|---|---|---|---|---|---|
| `lte` | 56 (128) | 107 (549) | 274 (1,830) | 93 % | 2.5 | 38 / 21 / 66; 128 / 107 / 1,830; 1 / 2 / 274; 56 / 549 / 740; 120 / 139 / 37 |
