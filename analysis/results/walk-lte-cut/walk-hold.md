# LTE on a moving GPS cut, one change at a time: `20261111-1806-walk-lte` (#214)

LTE records: `20261111-1806-walk-lte-final`. `ekf`, options `{"lte_max_hdop": 3, "lte_gate_mode": "clock"}`. Cuts at 100, 418, 495, 818, 1049 s. Median over the cuts, worst cut in brackets (m).

| Variant | 60 s | 120 s | 300 s | HPL ≥ error | p95 before the cut | Per cut, 60 / 120 / 300 s |
|---|---|---|---|---|---|---|
| `lte` | 30 (346) | 123 (332) | 448 (1,012) | 100 % | 2.2 | 30 / 123 / 300; 21 / 35 / 1,011; 346 / 332 / 1,012; 168 / 177 / 361; 6 / 12 / 448 |
