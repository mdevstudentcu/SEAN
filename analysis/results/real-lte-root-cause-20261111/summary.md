# Why LTE pulls the real static sessions kilometres away after a GPS cut (#214)

Evidence: **replay of real static sessions** (ADR-0015), GPS cut in software. Code: the local integration branch `tmp/e2e-combined` at `583e425` (origin/main c21e047 + #214 8e7a216 + #183 0ebe18a + #147 e39742f + #228 85d1324, never pushed); driver `root_cause.py` here. #183's front end on each capture. Truth: the mean of the session's GPS fixes. Errors and residuals only; tower IDs are the table's eNBs.

## 20261111-0151-static-fullsuite2-lte

### 1. Pseudoranges against truth: double differences (our clock cancelled)

Epochs with a pseudorange: 5,894. Two cells ≥ −8 dB at once: 25%; and agreeing with truth within 100 m: 11%.

| Pair (PCI) | eNBs | Common epochs | DD median, all (m) | All within 100 m | Both ≥ −8 dB | DD median ≥ −8 (m) | Robust σ ≥ −8 (m) | Within 100 m ≥ −8 | Told σ of the DD ≥ −8 (m) | First arcs: epochs | First arcs: median (m) | First arcs: span (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 92 − 204 | 30015 − 36122 | 1,922 | 9,792 | 1% | 144 | -429 | 7,056 | 11% | 12.2 | 0 | — | — |
| 92 − 244 | 30015 − 30066 | 1,270 | -4,848 | 0% | 58 | -8,404 | 1,875 | 0% | 20.4 | 0 | — | — |
| 92 − 268 | 30015 − 30111 | 3,404 | 1,018 | 18% | 1,227 | 3.2 | 152 | 50% | 6.7 | 104 | -7.6 | 82.4 |
| 204 − 244 | 36122 − 30066 | 592 | 2,190 | 0% | 2 | 6,569 | 36.7 | 0% | 13.8 | 0 | — | — |
| 204 − 268 | 36122 − 30111 | 1,715 | -4,675 | 0% | 179 | 2,507 | 31.5 | 0% | 12.8 | 0 | — | — |
| 244 − 268 | 30066 − 30111 | 1,171 | 6,322 | 0% | 25 | 11,893 | 1,034 | 0% | 13.9 | 0 | — | — |

Truth-good cells (a partner's DD median ≥ −8 dB within 100 m over ≥ 20 epochs): PCI 92, 268.

Steps at a new arc, one cell of a pair re-acquired, our clock cancelled: 414 steps, median 708 m, 99% over 100 m; 64 with both ≥ −8 dB, median 606 m.

Dopplers: of 8,676 two-cell differences at one epoch (zero at rest), 68% fall within 3 % of a whole 100 Hz alias (34.26 m/s; 6 % if uniform); 49% on a non-zero one; 19% within 1 m/s of zero. Told σ median 0.10 m/s; the differences' robust σ 51 m/s.

### 2. Default `ekf`, pseudoranges only: GNSS exclusion before the cut

GNSS excluded on 100% of the settled epochs. First GNSS fix rejected at 10.0 s (NIS 42.6 against 16.3, the 99.9 % gate for 3 dof; told σ 5.4 m, filter σ 4.2 m), after 9 fixes were used. Until the cut: 0 fixes used, 290 rejected. Position moved by LTE before the first rejection: lte:2460:92 1.8 m (told σ 2.6 m, SNR 6.1 dB), lte:2460:268 14.3 m (told σ 4.3 m, SNR 6.5 dB).

### 3. `B`, pseudoranges only, cut at 200 s: per cell

| Cell | Used before the cut | Last used before the cut (s) | Used in the 300 s after | Net position change after (m) | Summed |change| after (m) |
|---|---|---|---|---|---|
| lte:2460:204 | 375 / 1108 | 59.4 | 0 / 1399 | 0.0 | 0.0 |
| lte:2460:244 | 0 / 0 | — | 529 / 1145 | 1,243 | 4,011 |
| lte:2460:268 | 115 / 1659 | 12.3 | 0 / 1870 | 0.0 | 0.0 |
| lte:2460:92 | 211 / 1733 | 27.6 | 0 / 1906 | 0.0 | 0.0 |

### 4. Opt-in fixes: error after the cut, 5 cuts at 100, 150, 200, 250, 300 s, median (worst) in m

| Variant | 60 s | 120 s | 300 s | ≤ 50 m at 300 s | HPL ≥ error | GNSS excluded before the cut | Note |
|---|---|---|---|---|---|---|---|
| no LTE | 0.2 (3.2) | 0.3 (6.5) | 0.6 (15.9) | 5 / 5 | 100% | 0% |  |
| B | 0.2 (355) | 0.4 (1,155) | 3,658 (10,034) | 0 / 5 | 90% | 0% |  |
| B, ≥ −8 dB only | 0.2 (356) | 0.4 (1,158) | 3,667 (9,917) | 0 / 5 | 90% | 0% |  |
| B, 1 Hz | 0.2 (176) | 0.4 (1,124) | 4,352 (6,969) | 0 / 5 | 71% | 0% |  |
| B, truth-good cells | 0.2 (1,131) | 1,148 (3,251) | 5,521 (11,218) | 0 / 5 | 56% | 0% | uses truth: only cells whose DD agrees with truth (diagnostic) |
| B, arc bias | 474 (534) | 1,215 (1,838) | 1,947 (2,209) | 0 / 5 | 41% | 0% |  |
| B, tower clock q 0.02 | 0.2 (355) | 0.4 (1,155) | 3,657 (10,034) | 0 / 5 | 90% | 0% |  |
| B, tower clock q 2 | 0.2 (363) | 0.4 (1,194) | 3,800 (10,326) | 0 / 5 | 88% | 0% |  |
| B, tower clock q 20 | 0.2 (1,046) | 2,474 (3,947) | 8,588 (12,279) | 0 / 5 | 50% | 0% |  |
| B, dongle wander 5 | 212 (969) | 1,446 (2,337) | 5,464 (7,638) | 0 / 5 | 62% | 0% |  |
| B, pairs ≥ −8 dB only | 0.2 (118) | 0.4 (998) | 6,191 (6,963) | 0 / 5 | 76% | 0% | a record kept only if another cell is ≥ −8 dB at that epoch |
| B, told σ × 10 | 2,260 (4,071) | 3,335 (8,704) | 6,910 (14,054) | 0 / 5 | 27% | 0% | ADR-0036's σ times 10, told to the default EKF |
| B, all four | 74.3 (730) | 185 (1,968) | 1,105 (4,170) | 0 / 5 | 100% | 0% | ≥ −8 dB, 1 Hz, truth-good cells and arc bias together |
| B, q_accel 0.1 (static prior) | 0.4 (7.5) | 1.2 (35.0) | 147 (869) | 0 / 5 | 100% | 0% | a near-static motion prior: not a fix for a drone |

## 20261111-0233-static-lte-1h-lte

### 1. Pseudoranges against truth: double differences (our clock cancelled)

Epochs with a pseudorange: 35,005. Two cells ≥ −8 dB at once: 21%; and agreeing with truth within 100 m: 9%.

| Pair (PCI) | eNBs | Common epochs | DD median, all (m) | All within 100 m | Both ≥ −8 dB | DD median ≥ −8 (m) | Robust σ ≥ −8 (m) | Within 100 m ≥ −8 | Told σ of the DD ≥ −8 (m) | First arcs: epochs | First arcs: median (m) | First arcs: span (m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 92 − 204 | 30015 − 36122 | 14,534 | 2,206 | 7% | 2,926 | -11.5 | 1,647 | 34% | 8.9 | 0 | — | — |
| 92 − 220 | 30015 − 36122 | 488 | 16,267 | 0% | 1 | -9,876 | 0.0 | 0% | 24.7 | 0 | — | — |
| 92 − 244 | 30015 − 30066 | 1,229 | 10,573 | 0% | 102 | 6,278 | 7,922 | 0% | 11.0 | 0 | — | — |
| 92 − 268 | 30015 − 30111 | 19,339 | 1,047 | 10% | 4,388 | 4.8 | 1,192 | 41% | 8.2 | 58 | -0.9 | 53.3 |
| 204 − 220 | 36122 − 36122 | 222 | 17,509 | 0% | 0 | — | — | — | — | 0 | — | — |
| 204 − 244 | 36122 − 30066 | 54 | -14,861 | 0% | 0 | — | — | — | — | 0 | — | — |
| 204 − 268 | 36122 − 30111 | 13,213 | -311 | 6% | 2,185 | 13.9 | 1,254 | 33% | 12.2 | 0 | — | — |
| 220 − 268 | 36122 − 30111 | 425 | -15,883 | 0% | 58 | -5,790 | 1,216 | 0% | 12.4 | 0 | — | — |
| 244 − 268 | 30066 − 30111 | 658 | -8,463 | 0% | 0 | — | — | — | — | 0 | — | — |

Truth-good cells (a partner's DD median ≥ −8 dB within 100 m over ≥ 20 epochs): PCI 92, 204, 268.

Steps at a new arc, one cell of a pair re-acquired, our clock cancelled: 1934 steps, median 733 m, 95% over 100 m; 367 with both ≥ −8 dB, median 644 m.

Dopplers: of 44,231 two-cell differences at one epoch (zero at rest), 71% fall within 3 % of a whole 100 Hz alias (34.26 m/s; 6 % if uniform); 51% on a non-zero one; 20% within 1 m/s of zero. Told σ median 0.09 m/s; the differences' robust σ 51 m/s.

### 2. Default `ekf`, pseudoranges only: GNSS exclusion before the cut

GNSS excluded on 0%; never rejected.

### 3. `B`, pseudoranges only, cut at 1800 s: per cell

| Cell | Used before the cut | Last used before the cut (s) | Used in the 300 s after | Net position change after (m) | Summed |change| after (m) |
|---|---|---|---|---|---|
| lte:2460:204 | 1177 / 8298 | 1,776 | 70 / 1744 | 107 | 138 |
| lte:2460:220 | 0 / 714 | — | 0 / 0 | 0.0 | 0.0 |
| lte:2460:244 | 5 / 1287 | 371 | 0 / 0 | 0.0 | 0.0 |
| lte:2460:268 | 3053 / 12468 | 1,790 | 1218 / 2379 | 366 | 2,081 |
| lte:2460:92 | 5313 / 15966 | 1,727 | 645 / 1926 | 525 | 2,100 |

### 4. Opt-in fixes: error after the cut, 5 cuts at 600, 1200, 1800, 2400, 3000 s, median (worst) in m

| Variant | 60 s | 120 s | 300 s | ≤ 50 m at 300 s | HPL ≥ error | GNSS excluded before the cut | Note |
|---|---|---|---|---|---|---|---|
| no LTE | 0.5 (0.7) | 0.8 (1.3) | 1.3 (3.2) | 5 / 5 | 100% | 0% |  |
| B | 48.0 (332) | 584 (1,908) | 1,638 (12,145) | 0 / 5 | 74% | 0% |  |
| B, ≥ −8 dB only | 311 (537) | 597 (1,354) | 979 (4,420) | 0 / 5 | 86% | 0% |  |
| B, 1 Hz | 61.3 (132) | 264 (1,226) | 518 (1,906) | 1 / 5 | 95% | 0% |  |
| B, truth-good cells | 48.0 (332) | 429 (1,808) | 1,307 (12,144) | 0 / 5 | 89% | 0% | uses truth: only cells whose DD agrees with truth (diagnostic) |
| B, arc bias | 1,121 (2,380) | 1,478 (3,679) | 5,074 (5,525) | 0 / 5 | 23% | 0% |  |
| B, tower clock q 0.02 | 65.1 (428) | 499 (1,925) | 1,469 (12,134) | 0 / 5 | 75% | 0% |  |
| B, tower clock q 2 | 197 (301) | 672 (1,496) | 1,645 (7,493) | 0 / 5 | 79% | 0% |  |
| B, tower clock q 20 | 29.4 (167) | 300 (1,274) | 1,609 (3,906) | 0 / 5 | 94% | 0% |  |
| B, dongle wander 5 | 2.8 (415) | 1,219 (2,677) | 1,464 (6,725) | 0 / 5 | 75% | 0% |  |
| B, pairs ≥ −8 dB only | 20.4 (199) | 446 (2,082) | 246 (5,283) | 0 / 5 | 83% | 0% | a record kept only if another cell is ≥ −8 dB at that epoch |
| B, told σ × 10 | 986 (1,568) | 1,433 (4,223) | 5,850 (8,501) | 1 / 5 | 63% | 0% | ADR-0036's σ times 10, told to the default EKF |
| B, all four | 100 (268) | 223 (312) | 1,026 (1,723) | 0 / 5 | 98% | 0% | ≥ −8 dB, 1 Hz, truth-good cells and arc bias together |
| B, q_accel 0.1 (static prior) | 1.9 (18.3) | 17.7 (268) | 198 (861) | 1 / 5 | 95% | 0% | a near-static motion prior: not a fix for a drone |

