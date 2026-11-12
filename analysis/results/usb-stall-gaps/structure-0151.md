# Weak-cell wander on `20261111-0151-static-fullsuite2` (#214)

## Records and arcs

| LTE session | Records | Cells | Arcs | Arcs per minute |
|---|---|---|---|---|
| weak-cell (fcf5274) | 14792 | 4 | 59 | 5.91 |
| #306 (b339616) | 15385 | 4 | 51 | 5.11 |

## |error| by SNR (m), arc median removed: records, p50 / p95

| SNR (dB) | weak-cell (fcf5274) | #306 (b339616) |
|---|---|---|
| -99 to -10 | – | – |
| -10 to -8 | – | – |
| -8 to -6 | – | – |
| -6 to -3 | 93: 87 / 204 | 92: 106 / 182 |
| -3 to 0 | 222: 40 / 131 | 223: 45 / 139 |
| 0 to 99 | 14477: 15 / 68 | 15070: 14 / 54 |

## Structure function within one arc (m), weak-cell (fcf5274) / #306 (b339616)

| Cell | SNR p50 (dB) | 1 s | 10 s | 100 s |
|---|---|---|---|---|
| `lte:2460:92` | 7.5 | 9 / 8 | 27 / 20 | – / – |
| `lte:2460:268` | 6.5 | 13 / 13 | 45 / 50 | – / – |
| `lte:2460:244` | 6.0 | 14 / 9 | 41 / 31 | 41 / 22 |
| `lte:2460:204` | 5.1 | 9 / 9 | 21 / 21 | – / – |
| all cells |  | 11 / 10 | 37 / 35 | 69 / 90 |
