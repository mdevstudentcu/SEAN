# LTE pseudoranges against GPS truth: how these results were made (#21)

Evidence: **real sessions**, static, outdoors, payload Pi 4B, two 10 min captures on 2026-11-11. One NESDR on a Bingfu antenna at EARFCN 2460 (875 MHz), 1.92 MS/s, auto gain. GPS HAT with an external antenna, PPS-locked. The raw IQ is not in git. **The receiver position is withheld for privacy**: no file here gives it, a range, or a distance or bearing to a tower.

| Folder | Session | Recorded at | IQ | Antenna | Use |
| --- | --- | --- | --- | --- | --- |
| [`0151-static-fullsuite2/`](0151-static-fullsuite2/summary.md) | `20261111-0151-static-fullsuite2` | the change that is `8c4e856` on `main` | 599.4 s, no recorder gap (USB drive) | taped upright | **main numbers** |
| [`0040-static-fullsuite/`](0040-static-fullsuite/summary.md) | `20261111-0040-static-fullsuite` | the change that is `ee20817` on `main` | 582.3 s, 4 recorder gaps (SD card) | found on its side about 50 min after the recording; when it fell is unknown | second session |

## Commands

```bash
s=data/sessions/20261111-0151-static-fullsuite2    # and 20261111-0040-static-fullsuite
pnt frontend lte $s/sdr_a.cu8 --out <out>/<session>-lte
python analysis/lte_gps_truth.py <out>/<session>-lte --raw $s \
    --out analysis/results/lte-gps-truth-20261111/<folder> --plot .../<folder>/pairs.png
```

Each session's `meta.yaml` names the branch commit it had then. The front end ran at the changes that are `c4cc026` (0040) and `5af8d5a` (0151) on `main`, and the analysis at the one that is `f2804b0`, for both. At each run `src/` was identical to `main` `83bbb97`. On `main` they sit above `3d82fa0`, which adds coherent LTE options to the front end, off by default.

- Truth is the mean of the session's GNSS fixes (600 and 601).
- Tower positions come from `data/reference/lte-cells-ottawa.csv` through `pnt.nav.cells`. Every heard cell matched one registered eNB: a table hypothesis, not a confirmed identity.
- Tower height is the receiver's height plus the antenna's height above ground (`TBC`, flat ground).

## What the data show

**One cell ranges; pairs rarely do.**

- On 0151, PCI 92 (eNB 30015) is at SNR ≥ −8 dB (ADR-0036's cut, `TBC`) for 43.1 % of the capture, in runs of up to 71 s. Every other cell is above the cut for 0.6 to 6.6 %.
- Both cells of a pair are above the cut together for 0 to 1.4 % (81 epochs at most).
- On 0040 the best cell (PCI 220) gives 18.9 %, and pairs 0 to 1.5 %.
- Upright and gap-free, 0151 is better for one cell but not for pairs. The second cell is the limit.

**Below −8 dB the records lose lock but still report.**

- On every pair with more than 11 common epochs, the error over all common epochs, after truth, spreads by 7.3 to 12.9 km (0151) and 1.5 to 8.9 km (0040), robust σ.
- The records are told 21 to 31 m, so the told σ understates the error about 60 to 500 times.
- These records drift by hundreds of m/s (left panel of each `pairs.png`).
- An SNR at or above the cut is not enough on its own: arcs of a few epochs right after a cell is (re)found also sit kilometres off (below).

**Above −8 dB, one cell** (dongle clock included in S(τ)):

| Cell (session) | White σ at 10 Hz (m) | ADR-0036's (m) | S(1 s) (m) | S(10 s) (m) |
| --- | --- | --- | --- | --- |
| PCI 92 (0151), the best cell | 0.86 | 1.16 | 4.80 | 14.6 |
| PCI 204 (0151) | 0.95 | 1.25 | 9.00 | — |
| PCI 268 (0151) | 3.11 | 5.33 | — | — |
| PCI 220 (0040) | 1.49 | 1.20 | 8.23 | — |
| PCI 90 (0040) | 2.95 | 1.34 | 8.61 | — |
| PCI 92 (0040) | 2.08 | 2.43 | — | — |

The measured white σ is 0.58 to 2.2 times ADR-0036's: at or below it at 0151, above it for two cells of 0040. #190 measured a median S(1 s) of 8.3 m.

**Above −8 dB, pairs.** The residual after one constant has a robust σ of 8.7 to 31 m, from 34 to 88 epochs, with many arcs more than 30 m (`TBC`) from the pair's constant. No pair has more than 8.8 s of epochs above the cut. So there is no S(τ) beyond 0.5 s, no drift and no Gauss-Markov fit.

**Tower frame timing, after truth.** The true range difference is removed and the result is wrapped to one 10 ms frame. An unsynchronised pair would land anywhere in ±5 ms (±1,500 km).

| Pair (session) | eNBs (table) | Offset, longest arc pair (µs) | Epochs in it | Offset, median of all above the cut (µs) |
| --- | --- | --- | --- | --- |
| 204 − 92 (0151) | 36122 − 30015 | +0.080 | 37 | +0.029 |
| 268 − 92 (0151) | 30111 − 30015 | −43.25 | 25 | −17.45 |
| 90 − 220 (0040) | 36118 − 36122 | −0.070 | 22 | −0.038 |
| 92 − 220 (0040) | 30015 − 36122 | −0.384 | 27 | −0.387 |
| 244 − 220 (0040) | 30066 − 36122 | −0.261 | 11 | −1.183 |

- Four pairs land within 0.4 µs of zero. That means the table matches for PCI 90, 92, 204, 220 and 244 are very likely right, and these Rogers eNBs transmit frame-aligned to within about 0.4 µs.
- The same eNB pair 30015 / 36122 reads −0.38 µs on 0040 (through PCI 220) and −0.08 µs on 0151 (through PCI 204, sign flipped). The 0.3 µs (90 m) between them is the scale of this check.
- **268 − 92 does not fit.** Its two longest arcs sit at −43.3 µs (t 99–104 s) and −5.3 µs (t 381–383 s). A tower clock moving that much in 280 s would be about 40 m/s (136 ppb), so more likely PCI 268's track is not locked, or PCI 268 is another eNB than the table's 30111. `TBD`.
- These are a few seconds of data in two sessions: a sign, not a value.

**Not measured:** wander and drift over 10 to 100 s between towers. The hour from a fixed spot that #21 asks for is also not met (600 s each).

## Against the sim and ADR-0036

- **`challenge-drone`** (TBC: white `sigma_m` 50 m plus a per-eNB Gauss-Markov multipath of 50 m over 30 s, and a told σ of 2 m):
  - Above the cut, the real records are well inside 50 m.
  - Below it they are far outside, and the sim never drifts kilometres while reporting 20 to 30 m.
  - The sim's towers have independent clock offsets (`site.offset_m` 1000 m, TBC). The frame-timing check suggests these Rogers towers are aligned within about 0.4 µs (about 120 m).
- **ADR-0036** (Proposed, #190):
  - The white σ is near its law above the cut.
  - Its −8 dB cut is needed: below it these records are not ranging.
  - Its correlated part (10 m, 3 s) cannot be checked beyond 0.5 s for a pair. One cell's S(1 s) of 4.8 to 9.0 m, dongle clock included, is in its range.

## Antenna caveat (0040)

At about 01:40 the LTE antenna of 0040 was found lying on its side, about 50 min after that recording. On 0040, PCI 220 is at or above −8 dB in four runs: 0–34 s, 130–166 s, 332–359 s and 413–428 s after the first LTE record. Twice it was gone for long stretches (65–130 s and 184–332 s) and came back at 6 to 8 dB. After 428 s it never returns above −8 dB. That last step is the only one that fits a fall during the recording, so the record does not show whether, or when, the antenna fell. 0151, with the antenna taped upright, still hears only one strong cell.

## Front end against recorder on sample gaps

- **0040:** the recorder lists 4 `gaps_suspected`, at recorded samples 114,425,856 (5.85 s), 353,632,256 (1.59 s), 755,236,864 (8.39 s) and 796,917,760 (1.36 s). The front end sized its own gaps:
  - at 353,632,256 (2.37 s) and 697,434,112 (0.75 s)
  - three of 4 to 6 ms near 800 M samples, one of them "ambiguous (no buffer stamps)"

  It does not list the 5.85 s and 8.39 s gaps.
- **0151:** the recorder lists no gap. The front end sizes four: 60, 10, 180 and 10 ms.
- Pair differences cancel the dongle clock, so they are not affected. One cell's timing is, and so is any filter that holds the dongle clock across those points. For #183.

## Not checked

- Whether the 0040 antenna fell during its recording.
- Tower identity by anything other than the table and the frame-timing check.
- Wander, drift and the correlated part between towers beyond 0.5 s.
- An hour-long capture.
