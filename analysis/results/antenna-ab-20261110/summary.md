# LTE antenna A/B, 2026-11-10 (#200)

`python analysis/antenna_ab_table.py <runs> --out <dir>` at `e5c56a3`: the LTE front end on each run's `sdr_a.cu8`. Real sessions, statistics only. SNR is the front end's tracking estimate (dB per resource element). The detection threshold is -12.9 dB on this scale; the estimate averages only epochs above it, so `floor` (within 3 dB of it, a display mark) means the cell was marginal and its true SNR may be lower.

## Per run

| Run | Session | Cells | Above floor | Best SNR (dB) | Tracked (s, all cells) | Arcs | Capture (s) | RMS (LSB) | Clipped (%) | Gain |
|---|---|---|---|---|---|---|---|---|---|---|
| A0 | 20261110-2307-static-ant-A0-uhf-ground | 1 | 1 | 14.0 | 77.2 | 1 | 89.5 | 16.2 | 0.002 | auto |
| A0b | 20261110-2341-static-ant-A0b-uhf-ground-chairspot | 2 | 1 | 14.1 | 113.5 | 26 | 89.5 | 23.2 | 0.055 | auto |
| A1 | 20261110-2315-static-ant-A1-uhf-chair | 3 | 0 | -10.4 floor | 69.1 | 102 | 89.5 | 38.5 | 1.393 | auto |
| A2 | 20261110-2338-static-ant-A2-uhf-chair | 1 | 0 | -11.2 floor | 38.9 | 41 | 89.5 | 42.0 | 2.433 | auto |
| B | 20261110-2322-static-ant-B-bingfu-chair-HORIZONTAL | 3 | 1 | 5.1 | 46.4 | 54 | 89.5 | 47.2 | 3.392 | auto |
| B2 | 20261110-2331-static-ant-B2-bingfu-vertical | 2 | 1 | 6.1 | 54.3 | 41 | 89.5 | 48.8 | 3.818 | auto |
| C | 20261110-2334-static-ant-C-telescopic-257 | 2 | 1 | 6.1 | 97.3 | 79 | 89.5 | 55.4 | 6.767 | auto |

## Per cell: SNR (dB) / tracked (s) / arcs

| Run | PCI 204 | PCI 220 | PCI 244 |
|---|---|---|---|
| A0 | 14.0 / 77.2 / 1 | - | - |
| A0b | 14.1 / 84.4 / 2 | -11.2 floor / 29.1 / 24 | - |
| A1 | -11.6 floor / 43.5 / 27 | -10.4 floor / 12.2 / 21 | -11.0 floor / 13.4 / 54 |
| A2 | - | - | -11.2 floor / 38.9 / 41 |
| B | -10.9 floor / 16.4 / 43 | 5.1 / 27.3 / 10 | -12.4 floor / 2.7 / 1 |
| B2 | - | 6.1 / 49.6 / 26 | -12.0 floor / 4.7 / 15 |
| C | 6.1 / 75.3 / 14 | - | -12.0 floor / 22.0 / 65 |

## Pairs (second minus first, on cells both tracked)

| Pair | PCI | SNR first -> second (dB) | ΔSNR (dB) | Δtracked (s) |
|---|---|---|---|---|
| A1 -> A2 | 244 | -11.0 floor -> -11.2 floor | -0.3 | +25.5 |
| A0 -> A0b | 204 | 14.0 -> 14.1 | +0.1 | +7.2 |
| A1 -> A0b | 204 | -11.6 floor -> 14.1 | +25.7 | +40.9 |
| A1 -> A0b | 220 | -10.4 floor -> -11.2 floor | -0.8 | +16.9 |
| A2 -> A0b | no cell in common | | | |
| B -> B2 | 220 | 5.1 -> 6.1 | +1.1 | +22.3 |
| B -> B2 | 244 | -12.4 floor -> -12.0 floor | +0.4 | +2.0 |
| A1 -> B | 204 | -11.6 floor -> -10.9 floor | +0.7 | -27.1 |
| A1 -> B | 220 | -10.4 floor -> 5.1 | +15.5 | +15.0 |
| A1 -> B | 244 | -11.0 floor -> -12.4 floor | -1.4 | -10.7 |
| A2 -> B2 | 244 | -11.2 floor -> -12.0 floor | -0.7 | -34.2 |
| A2 -> C | 244 | -11.2 floor -> -12.0 floor | -0.8 | -16.9 |
| B2 -> C | 244 | -12.0 floor -> -12.0 floor | -0.0 | +17.3 |
