Session `20261111-0151-static-fullsuite2-lte`, analysed at `f2804b0`. Receiver truth: mean of 601 GNSS fixes (position withheld for privacy). Capture on disk 599.4 s. SNR cut -8 dB (`TBC`, ADR-0036). eNB by the committed table only: a hypothesis.

| Cell | eNB (table) | Lookup | Tracked | Tracked ≥ -8 dB | Arcs | SNR median (dB) | Told σ median (m) | Told σ < -8 dB (m) | White σ ≥ -8 dB (m) | ADR-0036 white (m) | S(1 s) ≥ -8 dB (m) | S(1 s) < -8 dB (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lte:2460:204 | 36122 | matched | 32.1% | 6.6% | 94 | -11.4 | 20.61 | 22.49 | 0.95 | 1.25 | 9.00 | 18 |
| lte:2460:244 | 30066 | matched | 7.3% | 0.6% | 55 | -11.7 | 22.88 | 23.66 | — | 1.07 | — | 9 |
| lte:2460:268 | 30111 | matched | 20.1% | 2.0% | 135 | -11.3 | 22.37 | 23.90 | 3.11 | 5.33 | — | 27 |
| lte:2460:92 | 30015 | matched | 61.2% | 43.1% | 250 | 6.7 | 4.35 | 24.01 | 0.86 | 1.16 | 4.80 | 22 |

| Pair (cell − ref) | Same eNB | Common epochs, all | All: robust σ (m) | All: told σ (m) | Both ≥ -8 dB | Span (s) | Frame offset after truth (µs) | Same, longest arc pair (µs, epochs) | Arcs (jumped) | Resid σ (m) | Robust σ (m) | White σ (m) | Told σ (m) | ADR-0036 white (m) | S(0.5 s) (m) | S(1 s) (m) | S(2 s) (m) | S(5 s) (m) | S(10 s) (m) | Drift (m/s) | GM fit: white, s (m), T (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lte:2460:204 − lte:2460:92 | no | 1272 | 12858 | 25.53 | 46 (0.8%) | 203.7 | +0.029 | +0.080 (37) | 6 (4) | 20.85 | 29.20 | 1.97 | 11.45 | 1.80 | — | — | — | — | — | — | — |
| lte:2460:244 − lte:2460:92 | no | 203 | 12088 | 30.62 | 0 (0.0%) | too few | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| lte:2460:268 − lte:2460:92 | no | 863 | 7279 | 25.86 | 81 (1.4%) | 384.1 | -17.453 | -43.254 (25) | 16 (15) | 11.08 | 31.01 | — | 12.17 | 4.88 | — | — | — | — | — | — | — |
