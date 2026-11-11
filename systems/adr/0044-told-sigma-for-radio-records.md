# ADR-0044: Tell radio LTE records ADR-0036's measured sigma, opt-in, beside learned noise

- **Status:** Accepted
- **Decided:** 2026-11-11 by the owners
- **Date:** 2026-11-11
- **Deciders:** team (the owners choose between the options below)
- **Traces to:** REQ-01, REQ-02, ADR-0015, ADR-0034, ADR-0036, ADR-0039, #147, #156, #183, #214

## Context

A front end's LTE pseudorange reports a σ from timing statistics, which can't see multipath. The challenge sim reports 2 m. Believing it, the filters do worse with LTE than without (#147); the tower-count study (#208) found this at every tower count. Two σ fixes exist:

- **A (ADR-0039, #156):** learn each cell's range noise from its innovations, starting from a 40 m prior. Opt-in as `ekf-learned-noise` and `ekf-calibrated-learned-noise`.
- **B (this ADR):** replace the reported σ with ADR-0036's measured model, from the record's SNR and length. ADR-0036 consequence 1 puts this in the front end, with the correlated part carried as a Gauss-Markov state; neither is built yet.

The real replays with GPS cut in software (#214) show a third problem. The front end restarts a cell's arc every few seconds, and the range steps there: 90 of 103 new arcs at SNR ≥ −8 dB start more than 100 m from the cell's last record, median 874 m. So **arc** was tried too: an opt-in `arc_bias` that gives each new arc of a cell its own range bias.

They were compared on paired sim runs and on two real static sessions (`analysis/results/told-sigma-147`). Median 300 s p95 (m) and HPL bound rate, `ekf`, LTE pseudoranges only:

| | Sim drone leg, T1 worst p95 / median NEES / HPL bound mean | Real 0040 | Real 0151 |
| --- | --- | --- | --- |
| default (reported σ) | 9,435 / 270 / 0.67 | 1,391 / 99 % | 6,299 / 33 % |
| A, learned | 2,153 / 7.4 / 0.95 | 9,554 / 94 % | 26,477 / 48 % |
| B, measured σ | 2,561 / 48 / 0.67 | 95 / 100 % | 4,026 / 96 % |
| B+A | 2,153 / 7.4 / 0.95 | 8,859 / 96 % | 22,824 / 52 % |
| arc | = default (no arc breaks in the sim) | 3,545 / 25 % | 1,873 / 23 % |
| B+arc | = B | 3,119 / 77 % | 2,267 / 69 % |
| no LTE | 2,857 / 2.0 / 1.00 | 1.4 / 100 % | 0.6 / 100 % |

The sim's error sizes are placeholders, two to three times what ADR-0036 measured at rest, so the sim favours the learner. Both real sessions are static, which favours no LTE. No moving session with GPS truth exists yet.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Defaults keep the reported σ; A and B both opt-in; `arc_bias` an option only | Nothing changes until a moving session decides; both can be shown | The defaults stay overconfident with LTE (#147 unsolved by default) |
| 2. A becomes the default | Best in the sim on error and integrity, on every leg | Worse than the default on three of four real cells (0151 HPL bound 48 %); tuned on 1 Hz sim records |
| 3. B becomes the default | Best LTE variant on both real sessions, and the only one whose HPL bounds the error on both (93 to 100 %); no tuning | Overconfident in the sim (hazardous epochs); correlated part sized at rest only |
| 4. B+A as the default | A learner above a measured floor | Behaves as A in both worlds: the 40 m prior and the learned value are above B's σ |
| 5. `arc_bias` on | Absorbs the arc steps | HPL bound falls to 23 to 25 % alone and 69 to 90 % with B, and B loses its first minute; error up on 0040 |
| 6. Leave radio LTE out of the default position solution until #183 | Best on both static real sessions and the sim timing leg | Gives up the gain every σ fix shows on the sim drone leg |

## Decision

**Option 1** (accepted by the owners, 2026-11-11).
- B is added opt-in as `ekf-measured-sigma` and `ekf-calibrated-measured-sigma` (`nav/told_sigma.py`), beside A's opt-in estimators.
- `arc_bias` is an EKF option with no registered estimator.
- No default changes.

The owners choose a default when the evidence under *Reopen* exists. They can also choose now: of the variants tried, B is the one that kept the HPL honest on real data, and on a static receiver LTE does not yet help at all.

## Consequences

1. **B lives in the filter, not the front end, for now.** Every record from a front end (`meta.rx_clock`, `meta.snr_db`, `meta.n_epochs`) is retold as it enters the EKF, so old sessions and the sim's front-end-shaped records get the model without being regenerated. ADR-0036 consequence 1 (front end and ICD) is not done; if it lands, B becomes the front end's reported σ and this remapping goes.
2. **White part:** ADR-0036's fit at SNR ≥ −8 dB and its measured bins below that, for a 10 Hz record, scaled by 20 / `n_epochs`. Below −14 dB nothing was measured: **49.4 m (`TBC`)**, one more doubling of the measured bins, chosen to be conservative. That covers 24 % of the sim drone leg's records.
3. **Correlated part without a state:** ADR-0036's 10 m and 3 s (`TBC`). It is told as white with the variance an average of correlated records really has, σ² (1 + ρ) / (1 − ρ) with ρ = exp(−T / τ): 24.6 m on a 1 Hz record and 77 m on a 10 Hz one. A single record is told more than its error. A Gauss-Markov state, as ADR-0036 asks, is `TBD`.
4. **Arc steps belong to the front end (#183).** `arc_bias` resets a cell to an unknown range on every new arc. Arcs restart every few seconds, so little range information survives a GPS cut, and steps inside an arc are not caught.
5. **No variant makes LTE help a static receiver:** the sim timing leg and both real sessions (ADR-0039 consequence 6).
6. **Dopplers are not covered.** With the front end's dopplers fed, every variant is worse, and GNSS is excluded before the cut on 19 to 20 % of epochs by default (3 to 4 % with B). #183 and ADR-0036 consequence 2 own them.
7. **Defaults unchanged:** every estimator registered on `main` hashes the same on this branch (PR evidence).

## Reopen

- A moving session with GPS truth (drone or vehicle), replayed with GPS cut. That is the case all of these are for.
- #183's front-end fix for arc steps: rerun the real replays.
- ADR-0036's sim sizes adopted (consequence 3): rerun the sim comparison.
- A Gauss-Markov state for the correlated part, or the front-end change of ADR-0036 consequence 1.
