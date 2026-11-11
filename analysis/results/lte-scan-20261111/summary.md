# LTE scan, laptop captures of 2026-11-10 and 2026-11-11 (#87)

`python analysis/lte_scan_table.py <captures> --out <dir>` at `bd54b01`, LTE front end on each `sdr_a.cu8`, cells looked up in `data/reference/lte-cells-ottawa.csv`. Real sessions; the receiver position is not given (`--receiver-llh`), so no distance from it is listed. A `unique` match is a hypothesis: eNBs beyond the table's 10 km can reuse a PCI.

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
| 20261110-2307-static-ant-A0-uhf-ground | 2460 | 204 | 77.2 | 14.0 | -0.303 | 1 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2315-static-ant-A1-uhf-chair | 2460 | 244 | 13.4 | -11.0 | -0.378 | 54 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261110-2315-static-ant-A1-uhf-chair | 2460 | 204 | 43.5 | -11.6 | -0.253 | 27 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2315-static-ant-A1-uhf-chair | 2460 | 220 | 12.2 | -10.4 | -0.237 | 21 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2322-static-ant-B-bingfu-chair-HORIZONTAL | 2460 | 204 | 16.4 | -10.9 | -1.137 | 43 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2322-static-ant-B-bingfu-chair-HORIZONTAL | 2460 | 244 | 2.7 | -12.4 | -0.317 | 1 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261110-2322-static-ant-B-bingfu-chair-HORIZONTAL | 2460 | 220 | 27.3 | 5.1 | -0.331 | 10 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2331-static-ant-B2-bingfu-vertical | 2460 | 220 | 49.6 | 6.1 | -0.274 | 26 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2331-static-ant-B2-bingfu-vertical | 2460 | 244 | 4.7 | -12.0 | -0.195 | 15 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261110-2334-static-ant-C-telescopic-257 | 2460 | 204 | 75.3 | 6.1 | -0.295 | 14 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2334-static-ant-C-telescopic-257 | 2460 | 244 | 22.0 | -12.0 | -0.325 | 65 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261110-2338-static-ant-A2-uhf-chair | 2460 | 244 | 38.9 | -11.2 | -0.294 | 41 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261110-2341-static-ant-A0b-uhf-ground-chairspot | 2460 | 204 | 84.4 | 14.1 | -0.325 | 2 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261110-2341-static-ant-A0b-uhf-ground-chairspot | 2460 | 220 | 29.1 | -11.2 | -0.285 | 24 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261111-0040-static-fullsuite | 2460 | 220 | 128.2 | -11.8 | -0.295 | 107 | unique | 36122 (1) | Rogers Communications Canada Inc. | MOONEY'S BAY | 2.38 | position unknown |
| 20261111-0040-static-fullsuite | 2460 | 244 | 74.0 | -11.8 | -0.776 | 247 | unique | 30066 (1) | Rogers Communications Canada Inc. | ALBION & HEATHRINGTON | 3.82 | position unknown |
| 20261111-0040-static-fullsuite | 2460 | 92 | 28.9 | -10.3 | -0.337 | 45 | unique | 30015 (1) | Rogers Communications Canada Inc. | BILLINGS BRIDGE | 1.68 | position unknown |
| 20261111-0040-static-fullsuite | 2460 | 106 | 0.9 | -8.0 | +0.164 | 5 | unique | 36118 (1) | Rogers Communications Canada Inc. | PRINCE OF WALES & DYNES | 2.07 | position unknown |
| 20261111-0040-static-fullsuite | 2460 | 90 | 18.3 | -11.6 | -0.345 | 27 | unique | 36118 (1) | Rogers Communications Canada Inc. | PRINCE OF WALES & DYNES | 2.07 | position unknown |

Tracked = number of 5 ms epochs × 5 ms; a cell found by the search but never tracked shows 0.0 s and no CFO. SNR is the front end's acquisition estimate.
