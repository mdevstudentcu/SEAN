# ADR-0049: Sizes of the measured-noise ladder study, and the arc model it uses for one row

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-01, REQ-02, REQ-10, ADR-0015, ADR-0034, ADR-0036, ADR-0039, ADR-0040, ADR-0044, #214, #218, #257

## Context

#247's ladder (`analysis/stacked_fixes.py`) runs the drone leg with its assumed LTE sizes: 50 m white noise at 1 Hz, 50 m / 30 s multipath, 100 m tower table error, all `TBC`. ADR-0036 measured the white part on 15 real static sessions, much smaller. #257 re-runs the ladder with the measured white part beside the assumed one, as a study variant (no committed scenario entry or default changes). Several sizes have no measurement, and the sim cannot express two of them (arc restarts, hop re-acquisition loss). This ADR records what the study chose, so that no value is chosen in passing.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Measured rows lower every size a capture touched, including multipath to ADR-0036's at-rest 10 m / 3 s | Biggest effect | Lowers multipath on a moving drone, which no capture measures |
| B. Measured rows replace only the white part; every unmeasured size stays at the leg's value and moves alone in a sensitivity row | Each number says which sizes it rests on; nothing unmeasured is lowered silently | The measured stack still carries the leg's assumed multipath |
| C. Change the committed `challenge-drone` entry | One leg | Breaks pairing with every result on `main`, before the owners adopt ADR-0036 consequence 3 |

## Decision

Option B, with these study values (every one `TBC`, none a default):

1. **White noise (measured rows):** each LTE record gets white noise of `pnt.nav.told_sigma.white_sigma_m(snr_db, n_epochs)`: ADR-0036's law and bins, × √(20 / n_epochs); below −14 dB, ADR-0044's 49.4 m (not measured). The generated spec has `sigma_m: 0` and the noise is added in the study, on a random stream of its own per cell, so assumed and measured rows share every other draw.
2. **Multipath:** 50 m / 30 s in the measured rows. Sensitivity: ADR-0036's at-rest 10 m / 3 s, a floor for a moving drone.
3. **Tower table error:** 100 m. Sensitivity: 50 m and 20 m (sweep points from #257).
4. **Arc restarts and steps (sensitivity only).** The sim writes `arc: 0` always. The study adds, per cell, restarts as a Poisson process at the pooled measured rate (250 new arcs in 10,780 tracked cell-seconds, one per 43 s; `analysis/results/lte-reacq-steps/summary.json`, "after", front end `ea72f6a` on real static sessions `20261111-0151-static-fullsuite2` and `20261111-0233-static-lte-1h`). Each arc carries one range offset, independent between arcs: with probability q uniform within ±1,500 m, otherwise normal with σ s. q (0.094) is set so that the share of steps over 100 m is the measured 16.8 %, and s (8.0 m) so that the median step is the measured 9.8 m. **Chosen here:** the ±1,500 m far size, which puts the model's step p90 (about 670 m) between the two sessions' 462 and 1,033 m; the iid offsets (no memory between arcs), which fits the 80 to 88 % of epochs whose double difference is within 100 m of truth; and restarts in wall time at the static rate. `tests/test_stacked_fixes.py` checks that the model reproduces the measured rate, median, share over 100 m and p90 range.
5. **Hop re-acquisition loss (sensitivity only):** each cell loses its record in half of its dwells (a sweep point, not a value; no hopped capture exists, ADR-0040).
6. **Rows and statistic as #247** (ADR-0034's amendment), seeds 0–49 paired; nothing tuned for the measured sizes (learned noise keeps ADR-0039's prior and memories).

## Consequences

- The measured rows answer "what if the white noise is as measured at rest and everything else is as assumed", not "what does the drone do".
- The arc model is a study model, in `analysis/` only. If the sim should carry arc restarts, that is a change to `sim/lte_front_end.py` with its own review.
- The pre-fix front end (#214's median 874 m steps, ADR-0044) is not modelled; the post-fix rate and steps are static sessions only.
- What would reopen it: a moving capture with GPS truth (multipath, arcs in motion); #245's re-generated white-noise bins (ADR-0036 amendment); a hopped capture; a measured tower table error (ASM-02).
