# ADR-0055: Flag a source whose innovations are correlated in time (report only)

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** the two owners
- **Traces to:** REQ-02, REQ-04, ADR-0036, ADR-0046 (Proposed), ADR-0050, #226, #251, #275
- **Owner decisions:** 2026-11-11, GNSS position analysis only and the test off on the eval path (*Decision*)

## Context

The filter takes every measurement error as white. Where it is not (LTE's told 2 m against 50 m white plus 50 m multipath correlated over 30 s on the challenge legs, #226; the `realistic` set's multipath; a real capture's arcs, ADR-0050), the covariance shrinks below the error and the bound escapes (#251's diagnosis, ADR-0046). The research report names this the first limit on accuracy (section 11.2) and lists innovation whiteness tests as the direct detector (9.4). #275 step 1 asks for that detector as a health flag, with no change to any estimate.

A Kalman filter whose model is right has white innovations. Unmodelled correlation shows as positive correlation between consecutive innovations of the same stream, whatever their size.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Windowed NIS per source (the gate's checks) | Exists for the calibration gate | Tests size, not correlation: a told σ too small fires it on white noise, and a correlated error inside a large told σ does not |
| B. Lag-1 autocorrelation of normalised innovations per source over a sliding window, self-normalised statistic | Tests correlation only; scale-free; one number per source; cheap | One lag: misses correlation that starts beyond the record spacing; a mismodelled motion also correlates the innovations |
| C. Ljung-Box over several lags | More power on slow correlation | More settings; same attribution limits |
| D. Fit a correlated-error model online (#275 step 2) | Fixes, not only detects | A change to the estimate: step 2, not this one |

## Decision

Option B, report only (`pnt.integrity.whiteness`): each innovation is normalised per component (z = y_i / √S_ii); one stream is one (source, emitter, kind, component); a record pairs with its stream's previous record if that is at most 5 s older (`TBC`). Per source over a sliding window: r = Σp / √(Σz_k² Σz_(k−1)²) and T = Σp / √Σp², p = z_k z_(k−1). `innovations_correlated:<source>` is raised while T > threshold with at least 30 pairs (`TBC`). The flag is appended after the estimator and any monitor, so status, trust and every other flag are as without it; the panel shows it as a caution and it degrades no status.

Window **60 s** and threshold **T > 3** (both `TBC`), chosen on sim seeds 0–9 by the rule in `analysis/whiteness.py` `choose`: fewest false onsets of a flagged source in honest runs, then fewest misses, then shortest delay.

**Owner decisions (2026-11-11):**

1. **GNSS position is analysis only:** its statistic is computed and reported (`analysis/whiteness.py`), never flagged (`WhitenessParams.report_only`). Receivers smooth their fixes, so consecutive fixes correlate by design and the flag would always be on. Evidence, replay of real sessions with `ekf`: the GPS HAT's fixes have lag-1 r 0.84 (`20261111-0151-static-fullsuite2`), 0.99 (`20261111-0233-static-lte-1h`) and 0.997 (`20261111-1806-walk-lte`), and are over T = 3 on 97 %, 99.7 % and 98.6 % of epochs. LTE, barometer and GNSS time keep the flag.
2. **Off on the Monte Carlo eval path:** `EKF(whiteness=False)` by default; `nav.estimate(..., whiteness=True)` switches it on for the estimators built on `ekf.run` (however wrapped). The panel's feed (`pnt sim --dash`, `pnt dash`), `pnt replay` and `pnt live` pass it; `pnt eval`, `pnt results`, `experiments` and the analysis scripts do not. Chosen over a per-estimator option because the eval paths then need no change and the registry keeps one entry per filter.

## Consequences

1. **Separates the diagnosed legs from honest noise on LTE (sim, held-out seeds 10–29, `ekf`):** LTE flagged in 80 of 80 runs of `challenge-drone-nominal`, `challenge-drone-outage`, `challenge-approach-outage` and `realistic-long-outage`; median delay from the first LTE record 29 s (drone legs, worst 32 s), 47 s (approach, worst 105 s), 61 s (`realistic-long-outage`, worst 215 s).
2. **False alarms on honest runs (8 h of `easy-nominal`, `easy-outage`, `easy-long-outage`, `nominal`):** 0.75 per hour for the flagged sources: LTE 2 onsets (`nominal`), GNSS time 4, barometer 0. The tuning seeds had none. GNSS position, not flagged, would have added 55 per hour (mostly `nominal`, whose square route the constant-velocity model does not follow).
3. **The threshold is low:** with GNSS position counted, the same rule chose T > 6, which missed 7 of 40 tuning runs (all `realistic-long-outage`). T > 3 trades 0.75 false alarms per hour for no misses. Both are `TBC`.
4. **GNSS time at GPS return:** on the approach it fires 6 s after GPS returns (8 of 20): the filter comes back overconfident, so the correlation is real, attributed to GNSS time.
5. **A filter that models the correlation is quiet:** `ekf-calibrated` (multipath state per emitter) flags LTE in 0 of 20 runs of `realistic-long-outage` and 1 of 20 of the approach (at GPS return), and 20 of 20 on the drone legs, where its multipath state is sized to the told 2 m.
6. **Real sessions (replay, whole session, `ekf`):** LTE flagged on 99.6 to 99.9 % of epochs of both static captures and the walk (r 0.96–0.99), as ADR-0036's correlated part and ADR-0050's arcs predict; barometer never; no GNSS time records.
7. **Cost:** on the panel path the hook costs about a fifth of `ekf`'s run time. The eval path is unchanged: `ekf` within ±3 % of `main`.
8. **No estimate changes:** every registered estimator's estimates hash identical to `main` without this flag, on the eval path and on the panel path (*Checks*).
9. **Not covered:** `ekf-base` and `ekf-base-imu` (own run loop: no flag); sources with no innovations (IMU); a negative correlation (one-sided).
10. **Reopen if:** step 2 of #275 (a state per flagged source) needs a different statistic; the false-alarm rate is too high in use; a moving real session with truth shows the GNSS correlation hurts the bound.

## Checks

Sim (placeholder models, ADR-0015) and replay of real sessions; numbers, commands and commits in `analysis/results/whiteness-275/NOTES.md` and `hashes.md`.

- **Window and threshold:** grid 20/30/60/120 s × T 3/4/5/6/8 on seeds 0–9 (`ekf`): 60 s / 3 had 0 false onsets, 0 misses and the shortest delay.
- **Held-out seeds 10–29:** consequences 1–5. The filter's own flags equal the offline statistic on every run.
- **Real sessions:** decision 1 and consequence 6.
- **No estimate changed:** against `main` `c62255d`, every registered estimator (21) on 10 sim scenarios × seeds 0, 1: 420 of 420 identical on the eval path (this test's flags included: there are none) and 420 of 420 on the panel path once this test's flags are left out; 6 estimators × 3 real sessions on the panel path: 18 of 18 (`hashes.md`).
- **Eval-path cost:** `ekf` on `challenge-drone-outage` and `nominal`, seeds 0–2, +0.7 % and −0.6 % against `main` `c62255d`.
- **Tests:** `tests/test_whiteness.py`; its EKF tests fail without the hook in `EKF.process`.
