# LTE on a moving GPS cut, one change at a time: `20261111-1806-walk-lte` (#214)

LTE records: `20261111-1806-walk-lte-keep15`. `ekf`. Cuts at 100, 418, 495, 818, 1049 s. Median over the cuts, worst cut in brackets (m).

| Variant | 60 s | 120 s | 300 s | HPL ≥ error | p95 before the cut | Per cut, 60 / 120 / 300 s |
|---|---|---|---|---|---|---|
| `no-lte` | 21 (51) | 44 (161) | 168 (484) | 100 % | 1.4 | 51 / 156 / 359; 21 / 44 / 118; 8 / 18 / 168; 44 / 161 / 484; 6 / 12 / 155 |
| `lte` | 113 (448) | 206 (709) | 1,609 (2,299) | 81 % | 6.3 | 26 / 71 / 158; 448 / 709 / 1,609; 274 / 161 / 2,299; 113 / 590 / 493; 34 / 206 / 2,095 |
