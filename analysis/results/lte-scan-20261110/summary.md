# LTE scan, 2026-11-10 captures (#87)

`python analysis/lte_scan_table.py <captures> --out <dir>` at `136d6cc`, LTE front end on each `sdr_a.cu8`, cells looked up in `data/reference/lte-cells-ottawa.csv`. Real sessions; no GNSS fix in them, so the receiver position is unknown and no distance from it is given. A `unique` match is a hypothesis: eNBs beyond the table's 10 km can reuse a PCI.

| Session | EARFCN | PCI | Tracked (s) | SNR (dB) | CFO (ppm) | Arcs | Table | eNB (sectors on this PCI) | Licensee | Location | km from Carleton | km from receiver |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261110-1305-lte-outside | 2460 | 244 | 48.9 | 14.8 | -0.300 | 1 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261110-1305-lte-outside | 2460 | 268 | 0.0 | -12.0 |  | 2 | unique | 30111 (1) | Rogers Communications Canada Inc. | OTTAWA AIRPORT PKWY | 4.95 | position unknown |
| 20261110-lte-outside-2535 | 2535 | none found in 29.5 s | | | | | | | | | | |
| 20261110-lte-outside-5145 | 5145 | 188 | 9.0 | -11.2 | -0.165 | 15 | unique | 219003 (1) | TELUS Communications Inc. | 1245 WALKLEY RD | 3.22 | position unknown |
| 20261110-lte-outside-5145 | 5145 | 189 | 27.8 | 12.5 | -0.191 | 3 | unique | 219003 (1) | TELUS Communications Inc. | 1245 WALKLEY RD | 3.22 | position unknown |
| 20261110-lte-outside-5145 | 5145 | 175 | 12.0 | 12.8 | +0.523 | 15 | unique | 219076 (1) | TELUS Communications Inc. | 1501 BANK ST | 2.20 | position unknown |
| 20261110-lte-outside-5255 | 5255 | 175 | 29.0 | 12.9 | -0.258 | 1 | unique | 219076 (1) | TELUS Communications Inc. | 1501 BANK ST | 2.20 | position unknown |
| 20261110-lte-outside-5255 | 5255 | 188 | 19.3 | 14.0 | -0.269 | 3 | unique | 219003 (1) | TELUS Communications Inc. | 1245 WALKLEY RD | 3.22 | position unknown |

Tracked = number of 5 ms epochs × 5 ms; a cell found by the search but never tracked shows 0.0 s and no CFO. SNR is the front end's acquisition estimate.
