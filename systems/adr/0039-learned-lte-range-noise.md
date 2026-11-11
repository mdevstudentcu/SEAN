# ADR-0039: Learn a radio's LTE range noise from its innovations, starting from a prior

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

Option D, for records with `meta.rx_clock` only, **opt-in for now** (owner decision,
2026-11-10): the estimators `ekf-learned-noise` (`ekf`, memory 60 s) and
`ekf-calibrated-learned-noise` (`ekf-calibrated`, memory 120 s), both memories `TBC`. `ekf`,
`ekf-calibrated` and every other default keep the reported sigma until the bar in *Default-on*
below is met. It can sit under E: the learner sizes whatever correlated term E adds.

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
5. **Unchanged:** every default estimator, on every record (learning is opt-in; hash check
   under *Checks*). The opt-in estimators also leave every record without `meta.rx_clock` alone, so they
   differ from the defaults only on the `challenge` drone and timing legs.
6. **Not solved: a static receiver on one or two cells.** With the constant-velocity model the
   filter cannot tell slow range error from motion along the line of sight, so LTE moves its
   velocity by metres per second. Without LTE a static truth makes dead reckoning look good
   (velocity error frozen at its last GNSS value). The stated sigma covers the error (HPL bound
   1.0), but position with LTE stays worse than without on the timing leg. A timing receiver
   knows it is static; using that is a separate decision.
7. **Relation to #168 (residual map, ADR-0032 Proposed):** that learns a mean correction per
   place, this a variance per cell. Both enlarge R; with both on, the learned variance would
   also absorb the map's variance. Not combined or checked together.

## Checks (sim, seeds 0-9, at a3dcf28)

- **Defaults unchanged:** every estimate (`pos_enu`, `pos_cov`, `hpl_m`) of the 8 estimators
  registered on `main` 9c5cb31 hashes the same as on 9c5cb31, on `challenge-drone-outage`,
  `challenge-drone-spoof-jump`, `challenge-timing-outage`,
  `challenge-drone-outage-tower-clock-step`, `uc01-drone-circuit`, `gps-outage` and
  `realistic-spoof-ramp`, seeds 0-1 (112 runs). The opt-in estimators differ from their defaults
  on the four `challenge` scenarios only.
- **Outage, `analysis/lte_noise_eval.py --seeds 0-9`** (`main` 9c5cb31 for the defaults and no
  LTE): horizontal p95 over the first 300 s of the outage, median / worst (m), and mean NEES.
  No run has a hazardous epoch.

| Leg | Default, LTE | Opt-in, LTE | No LTE |
| --- | --- | --- | --- |
| drone, `ekf` | 4,337 / 16,639; 239 | 552 / 2,640; 8.1 | 2,480 / 2,806; 1.3 |
| drone, `ekf-calibrated` | 3,307 / 12,059; 118 | 746 / 1,557; 2.4 | 2,480 / 2,806; 1.3 |
| timing, `ekf` | 1,809 / 10,685; 204 | 534 / 1,049; 1.1 | 207 / 509; 0.3 |
| timing, `ekf-calibrated` | 1,925 / 14,250; 85 | 392 / 1,222; 0.5 | 207 / 509; 0.3 |

- **`challenge-drone-outage-tower-clock-step`, `pnt eval ... --runs 10`:** 300 s HPL bound
  rate 0.751 → 0.888 for `ekf` (worst run 0.107 → 0.501) and 0.732 → 0.939 for `ekf-calibrated`.
  `ekf-learned-noise` has 3 hazardous epochs on seed 8 (the default has none) and 2.0 false
  alarms per hour (default 2.5); `ekf-calibrated-learned-noise` has none of either.
- **`challenge-drone-spoof-jump`, `pnt eval ... --runs 10`:** every run of every variant follows
  the held jump, so hazardous epochs stay in the thousands per run: 5,341 → 4,952 (`ekf`) and
  5,341 → 5,216 (`ekf-calibrated`). Refusing the jump is ADR-0038's job, not this one's. `ekf-imu`
  has no opt-in variant; with `noise_tau_s=60` passed by hand it went 3,789 → 4,956 (seeds 1 and
  6 had 0 and 55 without learning).

## Default-on

Learning stays opt-in until all of these hold, then the owners decide:

1. Paired 50-run evals (seeds 0-49) of each opt-in estimator against its default on the
   `challenge` legs, judged as in ADR-0022's *Amendment*: spoof scenarios on integrity (no more
   misleading or hazardous epochs, no slower detection, at most 1 false alarm per hour), the rest
   on p95. The tower-clock-step hazardous epochs above are explained or gone.
2. An IMU variant (`ekf-imu` with learning) is checked the same way, or left out of the default.
3. Consequence 6 (a static receiver) is either solved or accepted by the owners in writing.
4. The prior (`noise_prior_m`) and memories (`noise_tau_s`) are confirmed or sized from real
   sessions (*Reopen* below), or the owners accept them as `TBC` defaults.

Reopen when real sessions give radio innovations with position truth: they size the prior and
say whether learning or a captured model (E) holds.

## Amendment: real-capture records after ADR-0050 (Proposed, 2026-11-11)

ADR-0050 (Accepted) makes the default EKF retell a real capture's LTE records (`meta.sample_index`)
to ADR-0036's σ and give each new arc its own range bias. Both act where this learner lives
(`EKF._pseudorange`), so the owners choose how the two combine. Proposed (owner decision, to be
confirmed by the other owner in PR #156): **keep both.**

1. **Sim records** (no `sample_index`): the opt-in estimators behave exactly as before
   ADR-0050 (40 m prior, reported σ, no arc bias). Hashes identical before and after the rebase
   (PR #156).
2. **A real capture's records that ADR-0050 retells:** the learner starts from the record's
   retold σ in place of the 40 m prior (still one sample, `EKF.noise_prior_variance`), and the
   record keeps ADR-0050's bias per new arc. The learner stays one per cell across its arcs; a
   fresh learner per arc is not done. A record ADR-0050 cannot retell (no SNR or length) keeps
   the 40 m prior.
3. **Defaults:** every default estimator behaves exactly as on `main` (ADR-0050).

Because the record's σ is already the learner's lower bound (*Decision*), the retold σ is also
its floor. A 10 Hz record of 20 epochs (the size ADR-0036 fits) is retold 77 to 92 m, above
the 40 m prior, so on such records the learner can only raise the σ above ADR-0050's. The
alternative, the retold σ as a floor only with the 40 m prior kept, gives the same σ until a
cell's learned variance exceeds the retold one, and a slightly lower one after (the prior is one
sample of 40 m instead of 77 m or more). It is not implemented. Neither is checked on real
sessions with this learner: reopen with ADR-0050's real-session runs
(`analysis/real_lte_filter.py`).
