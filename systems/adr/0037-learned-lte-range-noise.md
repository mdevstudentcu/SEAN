# ADR-0037: Learn a radio's LTE range noise from its innovations, starting from a prior

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-01, REQ-02, ADR-0015, ADR-0022, ADR-0030, ADR-0034, #118, #147, #173

## Context

Real LTE records report a sigma from timing statistics. It can't see the slow error: on the
`challenge` legs (ADR-0030) the records say 2 m, and the filters believed it, rejected almost
every reading and did worse with LTE than without (#147). Real static captures agree on the
kind of error, if not its size: the reported sigma is close to the 10 Hz white noise, and 5 to
10 times below the error at 1 to 10 s (2.4 to 38 m; #173, ADR-0036 Proposed).

The first fix (PR #156's draft) learned each cell's noise from its innovations, with the
reported sigma as one sample. On single seeds it failed three ways (PR #156):

1. The first two records of a cell, counted at 2 m, fixed the dongle clock's drift so tightly
   that the gate then rejected the cell for good.
2. An innovation that state uncertainty explains (a new clock, a nonlinear geometry) is a large
   negative sample. One of them dragged the learned variance back to 2 m, and the next records
   made the stated position sigma a few metres while the error was hundreds: the hazardous
   epochs.
3. Near a tower, with a drifted position, the range is far from linear across the line of
   sight. A few records of one site then collapsed the stated sigma the same way.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Believe the reported sigma (`main`) | Nothing to choose | LTE worse than none on both legs; HPL bounds 60 % of epochs |
| B. Fixed floor on radio range sigma | One number | Needs the true size, which we don't know for real records (#118); wrong in one direction or the other |
| C. Learn per cell, reported sigma as one sample (the draft) | No size chosen | Failures 1 to 3 above: more hazardous epochs than `main` |
| D. Learn per cell from a prior, weight samples by precision, never shrink without GNSS, respect the range's curvature | Starts conservative and becomes data-driven; stated sigma grows with what it learns | One prior value (TBC); fewer ranges used near towers; a static receiver still drifts (below) |
| E. Carry the slow error as a Gauss-Markov state sized from captures (ADR-0036) | Matches the measured kind of error | Sizes come from static captures with no position truth; not applied yet |

## Decision

Option D, for records with `meta.rx_clock` only, in `ekf` and `ekf-calibrated`. It can sit
under E: the learner sizes whatever correlated term E adds.

## Consequences

1. **Prior `noise_prior_m` = 40 m (`TBC`), one sample.** Above every 1 to 10 s error measured
   on the real static captures (up to 38 m, weak cells, #173). Chosen on tuning seeds 100 to 109
   from 10, 20, 30, 40 and 60 m: 30 to 60 m behave alike, 20 m and below bring back failure 1 on
   some seeds (PR #156). Because it never decays, it keeps a share of about σ₀² / (rate × memory)
   in the learned variance: with honest 1 m records at 1 Hz, about 8 m of sigma.
2. **Weak evidence skipped or down-weighted:** an innovation whose state part exceeds the
   variance learned so far is not counted; the rest count with weight
   (noise / (noise + state part))², a variance sample's precision against a pure noise sample.
3. **No shrinking without trusted GNSS:** the learned variance may grow but not fall while GNSS
   is out, rejected or flagged.
4. **Curvature:** R of a radio range gains σ⊥⁴ / (2 r²), σ⊥² the position and told-tower variance
   across the line of sight (the standard second-order term), and a range whose term exceeds the
   learned noise is not used. No value to choose. Cost: near towers, with a drifted position,
   fewer ranges are used and the mean error rises (PR #156).
5. **Unchanged:** every record without `meta.rx_clock`, so every scenario outside the
   `challenge` drone and timing legs (hash check in PR #156).
6. **Not solved: a static receiver on one or two cells.** With the constant-velocity model the
   filter cannot tell slow range error from motion along the line of sight, so LTE moves its
   velocity by metres per second. Without LTE a static truth makes dead reckoning look good
   (velocity error frozen at its last GNSS value). The stated sigma covers the error (HPL bound
   1.0), but position with LTE stays worse than without on the timing leg. A timing receiver
   knows it is static; using that is a separate decision.
7. **Relation to #168 (residual map, ADR-0032 Proposed):** that learns a mean correction per
   place, this a variance per cell. Both enlarge R; with both on, the learned variance would
   also absorb the map's variance. Not combined or checked together.

Reopen when real sessions give radio innovations with position truth: they size the prior and
say whether learning or a captured model (E) holds.
