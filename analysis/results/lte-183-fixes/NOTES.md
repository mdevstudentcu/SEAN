# #183 front-end fixes on real captures

Evidence: **real sessions**, static, payload Pi, one NESDR (`sdr_a`), 14 captures from 2026-11-10/11 (EARFCN 2460, 2535, 5145, 5255). Before: front end at `c21e047` (`main`). After: the #183 branch (commit named in the PR). Raw IQ stays in `data/sessions/` (not in git); `20261111-0233-static-lte-1h` was read in place from the USB drive. No receiver position, distance or bearing is computed or written here.

Files: `table.md` (per session and per cell, before → after), `cells.json` (the same, per cell), `before_after.png`.

## Commands

```bash
caps="20261110-1305-lte-outside 20261110-lte-outside-5145 20261110-lte-outside-5255
      20261110-lte-outside-2535 20261110-23{07,15,22,31,34,38,41}-static-ant-*
      20261111-0040-static-fullsuite 20261111-0151-static-fullsuite2 20261111-0233-static-lte-1h"
# <main>: a worktree at c21e047; every command single-threaded BLAS
PYTHONPATH=<main>/src python analysis/lte_183_fixes.py run <each data/sessions/$c/sdr_a.cu8> --out <before>
PYTHONPATH=src        python analysis/lte_183_fixes.py run <each data/sessions/$c/sdr_a.cu8> --out <after>
python analysis/lte_183_fixes.py compare <before> <after> --out analysis/results/lte-183-fixes
```

The per-capture JSONs were made by the same per-cell code as `cell_stats` in a scratch copy of it; `compare` read them as they are.

## Read with

- **Code rate** is the slope of the measured frame boundary against the sample index inside arcs of ≥ 1 s: the dongle's sample clock (+0.23 to +0.37 ppm on these captures with the fixed front end), which the tuner shares. A right carrier offset has −CFO/fc equal to it within the towers' ±0.05 ppm. The recorder's `rate_ppm_vs_host` cannot serve: on the NTP-timed 2026-11-10 sessions it reads −15 to +20 ppm; on the PPS-timed `0151` and `0233` sessions +0.77 and +0.43 ppm.
- **SNR ≥ −8 dB** time counts 5 ms epochs at that per-resource-element SNR, the white-σ fit's lower edge in ADR-0036. Before #183 an epoch's SNR assumed 124 combined elements, after it the ones actually combined.
- **Jumps** are arc-to-arc timing steps (the new arc's first boundary against the old arc's last, extrapolated at its rate), wrapped to ±5 ms.
- `20261110-lte-outside-2535`: no cell found by either.

## Known limits

- `20261111-0151-static-fullsuite2`, PCI 92: time at SNR ≥ −8 dB falls from 238.5 to 156.7 s while the other three cells there gain 36→54, 3→55 and 9→147 s. A trace shows a first-path move of −2.4 samples at about 18 s that left the peak at the gate edge; the loop then coasts on weak correlations until a later re-find. Not fixed here.
- Both front ends hang on to a cell near the detection threshold (about −12 dB) for long stretches: epochs pass the 8 dB post-correlation gate, so the loop never re-searches and the periodic search skips a cell still tracked. Pre-existing.
- Dropped-sample gaps the front end infers: `0233` 65 (23 ambiguous) before, 11 (none ambiguous) after; `0151` 4 → 3 (2 ambiguous after); `0040` 5 → 6. The recorder reports none. Whether any is real is `TBD` (as in `lte-measured-noise/NOTES.md`).

## ADR-0036's noise numbers: would they move?

ADR-0036 was measured on 15 sessions; 3 are on the laptop (`20261110-1305-lte-outside`, `-5145`, `-5255`). They and `0151` were re-run through `pnt frontend lte --no-copy` at `c21e047` and at the branch (its `src/` then differed from the final commit only by one `ruff format` line wrap), then through `analysis/lte_measured_noise.py` and `analysis/lte_capture_report.py` (both unchanged, at `c21e047`). Yes, several move:

| Quantity (`lte_measured_noise.py`) | Before | After |
|---|---|---|
| White σ robust, 10 to 13 dB (3 sessions) | 1.16 m (n 417) | 1.17 m (n 445) |
| White σ robust, 13 to 16 dB (3 sessions) | 0.63 m (n 929) | 0.72 m (n 1,111) |
| Bins −2 to 10 dB (3 sessions) | none | 1.25 to 2.33 m (PCI 268, newly tracked) |
| Fit, SNR ≥ −8 dB (3 sessions) | not fittable (2 bins) | 0.59² + 2.73² / SNR_lin |
| Fit, SNR ≥ −8 dB (`0151`, not in the ADR) | 0.26² + 1.83² / SNR_lin | 0.18² + 1.92² / SNR_lin |
| Same-eNB drift 189 − 188, `5145` | −16.29 ± 3.24 m/s | −2.61 ± 1.22 m/s |
| Other-eNB drift 188 − 175, `5145` | not measurable (13 arcs) | +9.81 ± 0.69 m/s |
| Other-eNB drift 188 − 175, `5255` | −1.88 ± 0.52 m/s | −1.71 ± 0.76 m/s |
| New-arc breaks, 3 sessions | 11, median \|jump\| 24 m | 6, median \|jump\| 153 m (90th pct 605 m) |
| `lte_capture_report.py` dongle ε, `5145` | +0.137 ppm | +0.264 ppm |

The ADR's "−16.3 m/s" same-eNB pair, which it called a front-end artefact, becomes −2.6 ± 1.2 m/s; the ADR's "7 of 39 cell tracks have a carrier offset a whole multiple of 200 Hz" has no case left on the 14 laptop captures (CFO within 0.1 ppm of the code rate for every cell). Regenerating the ADR's tables needs the 12 sessions on the Pi: not done.
