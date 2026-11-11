# LTE pseudoranges against GPS truth: how these results were made (#21)

Evidence: **real session**, static, outdoors, payload Pi 4B. One NESDR on a Bingfu antenna at EARFCN 2460 (875 MHz), 1.92 MS/s, auto gain. GPS HAT with an external antenna, PPS-locked. Recorded at `4d3598b`; its change is on `main` as `ee20817`. The raw IQ is not in git. **The receiver position is withheld for privacy**: no file here gives it, a range, or a distance or bearing to a tower.

## Commands

```bash
s=data/sessions/20261111-0040-static-fullsuite
pnt frontend lte $s/sdr_a.cu8 --out <out>/20261111-0040-static-fullsuite-lte
python analysis/lte_gps_truth.py <out>/20261111-0040-static-fullsuite-lte --raw $s \
    --out analysis/results/lte-gps-truth-20261111 --plot analysis/results/lte-gps-truth-20261111/pairs.png
```

Front end and analysis at `b437a3b`. No file under `src/` differs from `origin/main` `83bbb97`. Truth is the mean of the session's 600 GNSS fixes. Tower positions come from `data/reference/lte-cells-ottawa.csv` through `pnt.nav.cells`. Tower height is the receiver's height plus the antenna's height above ground (`TBC`, flat ground).

## Caveat: the antenna may have fallen

At about 01:40 the owner found the LTE antenna lying on its side on the ground, about 50 min after the recording (00:40 to 00:50). When it fell is unknown.

The strongest cell (PCI 220, eNB 36122 by the table) is at or above −8 dB in four runs: 0–34 s, 130–166 s, 332–359 s and 413–428 s after the first LTE record. Between them it drops below −8 dB or is not tracked at all, twice for long stretches (65–130 s and 184–332 s), and each time it comes back at 6 to 8 dB. After 428 s it never comes back above −8 dB (150 s, to the end).

- That last step is the only one that fits a fall during the recording.
- The two earlier dropouts came back at full SNR, so they are not a fall. Whether they are fading or the front end not re-finding the cell is `TBD`.
- So the record does not show whether, or when, the antenna fell. Every number below may come from a tilted antenna.

## What the data show

- **Usable records are rare.** At SNR ≥ −8 dB (ADR-0036's cut, `TBC`), the best cell gives 18.9 % of the 582 s capture and the others 0.2 to 2.0 %. Both cells of a pair are above the cut at the same time for 0 to 1.5 % (88 epochs at most, over 14.9 s).
- **Below the cut the records lose lock but still report.** On the three pairs with more than 11 common epochs, the error over every common epoch, after truth, spreads by 1.5 to 8.9 km (robust σ). The told σ of those records is 21 to 31 m, so the told σ understates the error 50 to 300 times. A record below −8 dB is not a noisy pseudorange: it drifts by hundreds of m/s (left panel of `pairs.png`). One cell's own S(1 s) below the cut is 12 to 27 m (dongle clock included).
- **Above the cut:**
  - White σ of one cell at 10 Hz is 1.49 m (PCI 220, median 5.6 dB) against ADR-0036's 1.20 m. It is 2.95 m (PCI 90) against 1.34 m, and 2.08 m (PCI 92) against 2.43 m.
  - One cell's S(1 s), dongle clock included, is 8.2 to 8.6 m. #190 measured a median of 8.3 m.
  - The one pair with enough epochs (90 − 220, 88 epochs over 14.9 s) has white σ 3.43 m, S(0.5 s) 12.4 m and robust σ 19.4 m about one constant. In 4 of its 8 arc pairs the arc lands more than 30 m (`TBC`) from that constant.
  - Too short for S(τ) beyond 0.5 s, for a drift or for a Gauss-Markov fit.
- **Tower frame timing, after truth:** differenced, with the true range difference removed and wrapped to one 10 ms frame, the offset is:
  - −0.038 µs (−11 m) for 90 − 220
  - −0.387 µs (−116 m) for 92 − 220
  - −1.18 µs for 244 − 220, from 26 epochs that all sit in arcs more than 30 m from their median, so not reliable
  - An unsynchronised pair would land anywhere in ±5 ms (±1,500 km). Three pairs within 1.2 µs of zero mean two things: the table's eNB matches for PCI 90, 92, 220 and probably 244 are right, and these Rogers eNBs transmit frame-aligned to within about 0.4 µs.
  - This is one session, with 34 and 88 epochs behind the two good pairs: a sign, not a value.
- **Not measured:** wander and drift over 10 to 100 s. No pair stays above the cut long enough. The hour from a fixed spot that #21 asks for is also not met (582 s).

## Against the sim and ADR-0036

- `challenge-drone` (TBC): white `sigma_m` 50 m plus a per-eNB Gauss-Markov multipath of 50 m over 30 s, and a told σ of 2 m. Above the cut the real records are well inside 50 m. Below it they are far outside: the sim never drifts kilometres while reporting 20 to 30 m.
- ADR-0036 (Proposed, #190): the white σ against SNR is 0.86 to 2.2 times its value on three cells. Its −8 dB cut is supported: below it these records are not ranging at all. Its correlated part (10 m, 3 s) cannot be checked beyond 0.5 s here.

## Front end and recorder disagree on sample gaps

The recorder's sidecar lists 4 `gaps_suspected`, at recorded samples 114,425,856 (5.85 s), 353,632,256 (1.59 s), 755,236,864 (8.39 s) and 796,917,760 (1.36 s), and no `gaps`. The front end opened the capture as one segment and sized its own gaps:

- at 353,632,256 (2.37 s) and 697,434,112 (0.75 s)
- three of 4 to 6 ms near 800 M samples, one of them "ambiguous (no buffer stamps)"

It does not list the 5.85 s and 8.39 s gaps. Pair differences cancel the dongle clock, so they are not affected. One cell's timing across those gaps is, and so is any filter that holds the dongle clock across them. For #183.

## Not checked

- Whether the antenna fell during the recording.
- Tower identity by any means other than the table and the frame-timing check above.
- The wander, the drift and the correlated part beyond 0.5 s.
