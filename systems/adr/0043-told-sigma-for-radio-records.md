# ADR-0043: Tell radio LTE records ADR-0036's measured sigma, opt-in, beside learned noise

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners choose between the options below)
- **Traces to:** REQ-01, REQ-02, ADR-0015, ADR-0034, ADR-0036, ADR-0039, #147, #156, #214

## Context

A front end's LTE pseudorange reports a σ from timing statistics, which can't see multipath. The challenge sim reports 2 m. Believing it, the filters do worse with LTE than without (#147). The tower-count study (#208) found the same at every tower count.

Two fixes exist:

- **A (ADR-0039, #156):** learn each cell's range noise from its innovations, starting from a 40 m prior. Opt-in as `ekf-learned-noise` and `ekf-calibrated-learned-noise`.
- **B (this ADR):** replace the reported σ with ADR-0036's measured model, from the record's SNR and length. ADR-0036 consequence 1 puts that in the front end, with the correlated part carried as a Gauss-Markov state. Neither is built yet.

They were compared on paired sim runs and on one real replay with GPS cut in software (`analysis/results/told-sigma-147`, at `01154f5`). The two kinds of evidence disagree:

| | Sim drone leg, T1 worst p95 (m) / median NEES / HPL bound mean (`ekf`) | Real static replay, median 300 s p95 (m) / HPL bound (`ekf`) |
| --- | --- | --- |
| default (reported σ) | 9,435 / 270 / 0.67 | 6,299 / 33 % |
| A, learned | 2,153 / 7.4 / 0.95 | 26,477 / 48 % |
| B, measured σ | 2,561 / 48 / 0.67 | 4,026 / 96 % |
| B+A | 2,153 / 7.4 / 0.95 | 22,824 / 52 % |
| no LTE | 2,857 / 2.0 / 1.00 | 0.6 / 100 % |

The sim's error sizes are placeholders, two to three times what ADR-0036 measured at rest, so the sim favours the learner. The real session is static, which favours no LTE, and it is only one session. No moving session with GPS truth exists yet.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Default stays the reported σ; A and B both opt-in | Nothing changes until evidence decides; both can be shown | The defaults stay overconfident with LTE (#147 unsolved by default) |
| 2. A becomes the default | Best in the sim on error and integrity, every leg | Worst on the real replay (HPL bounds 48 %); tuned on 1 Hz sim records only |
| 3. B becomes the default | Honest HPL on the real replay (93 to 96 %); no tuning, sized from measurements | Overconfident in the sim (hazardous epochs); its correlated part is sized at rest only |
| 4. B+A as the default | Learner on top of a measured floor | Behaves as A in both worlds: the 40 m prior and the learned value are above B's σ |
| 5. Drop radio LTE from the default position solution | Best of all on the static cases | Gives up the drone leg's gain, which every fix shows in the sim |

## Decision

Proposed: **option 1**. B is added opt-in as `ekf-measured-sigma` and `ekf-calibrated-measured-sigma` (`nav/told_sigma.py`), beside A's opt-in estimators. No default changes. The owners choose a default when the evidence under *Reopen* exists, or earlier with what is here.

## Consequences

1. **B is in the filter, not the front end, for now.** Every record from a front end (`meta.rx_clock`, `meta.snr_db`, `meta.n_epochs`) is retold as it enters the EKF. Old sessions and the sim's front-end-shaped records then get the same model without regenerating anything. ADR-0036 consequence 1 (front end and ICD) is not done. If it lands, B becomes the front end's reported σ and this remapping goes.
2. **White part:** ADR-0036's fit at SNR ≥ −8 dB and its measured bins below that, for a 10 Hz record. It is scaled by 20 / `n_epochs` for other record lengths. Below −14 dB nothing was measured: **49.4 m (`TBC`)**, one more doubling of the measured bins, chosen to be conservative. 24 % of the sim drone leg's records are below −14 dB.
3. **Correlated part without a state:** ADR-0036's 10 m, 3 s (`TBC`). It is told as white with the variance an average of correlated records really has, σ² (1 + ρ) / (1 − ρ) with ρ = exp(−T / τ): 24.6 m on a 1 Hz record and 77 m on a 10 Hz one. A record alone is told more than its error. ADR-0036 asks for a Gauss-Markov state; that is `TBD`.
4. **Neither fix makes LTE help a static receiver** (sim timing leg, real replay): ADR-0039 consequence 6, now seen on real data too.
5. **Dopplers are not covered.** With the front end's dopplers fed (`told`), every variant is worse on the real replay. #183 and ADR-0036 consequence 2 own them.
6. **Defaults unchanged:** every estimator registered on `main` hashes the same on this branch (PR evidence).

## Reopen

- A moving session with GPS truth (drone or vehicle), replayed with GPS cut. That is the case both fixes are for, and neither has been checked on it.
- ADR-0036's sim sizes adopted (consequence 3): rerun the sim comparison.
- A Gauss-Markov state for the correlated part, or the front-end change of ADR-0036 consequence 1.
