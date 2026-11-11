Session `20261111-0040-static-fullsuite-lte`, analysed at `b437a3b`. Receiver truth: mean of 600 GNSS fixes (position withheld for privacy). Capture on disk 582.3 s. SNR cut -8 dB (`TBC`, ADR-0036). eNB by the committed table only: a hypothesis.

| Cell | eNB (table) | Lookup | Tracked | Tracked ≥ -8 dB | Arcs | SNR median (dB) | Told σ median (m) | Told σ < -8 dB (m) | White σ ≥ -8 dB (m) | ADR-0036 white (m) | S(1 s) ≥ -8 dB (m) | S(1 s) < -8 dB (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lte:2460:106 | 36118 | matched | 0.2% | 0.2% | 1 | 3.1 | 2.68 | — | — | 1.72 | — | — |
| lte:2460:220 | 36122 | matched | 33.9% | 18.9% | 101 | 5.6 | 9.61 | 31.19 | 1.49 | 1.20 | 8.23 | 16 |
| lte:2460:244 | 30066 | matched | 36.6% | 1.2% | 230 | -11.5 | 29.65 | 30.29 | — | 5.03 | — | 27 |
| lte:2460:90 | 36118 | matched | 5.6% | 2.0% | 28 | -8.9 | 14.20 | 23.14 | 2.95 | 1.34 | 8.61 | — |
| lte:2460:92 | 30015 | matched | 10.9% | 1.0% | 44 | -11.3 | 20.59 | 21.08 | 2.08 | 2.43 | — | 12 |

| Pair (cell − ref) | Same eNB | Common epochs, all | All: robust σ (m) | All: told σ (m) | Both ≥ -8 dB | Span (s) | Frame offset after truth (µs) | Arcs (jumped) | Resid σ (m) | Robust σ (m) | White σ (m) | Told σ (m) | ADR-0036 white (m) | S(0.5 s) (m) | S(1 s) (m) | S(2 s) (m) | S(5 s) (m) | S(10 s) (m) | Drift (m/s) | GM fit: white, s (m), T (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lte:2460:106 − lte:2460:220 | no | 11 | 34 | 20.30 | 0 (0.0%) | too few | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| lte:2460:244 − lte:2460:220 | no | 750 | 8134 | 35.81 | 26 (0.4%) | 337.9 | -1.183 | 8 (8) | — | — | — | 9.85 | 1.70 | — | — | — | — | — | — | — |
| lte:2460:90 − lte:2460:220 | no | 214 | 1530 | 26.18 | 88 (1.5%) | 14.9 | -0.038 | 8 (4) | 24.80 | 19.43 | 3.43 | 6.48 | 1.75 | 12.44 | — | — | — | — | — | — |
| lte:2460:92 − lte:2460:220 | no | 417 | 8867 | 30.38 | 34 (0.6%) | 6.5 | -0.387 | 4 (3) | 10.02 | 8.72 | — | 6.77 | 1.69 | — | — | — | — | — | — | — |
