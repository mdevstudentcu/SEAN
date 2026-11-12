# ADR-0052: Flag a source whose innovations are correlated in time (report only)

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** the two owners
- **Traces to:** REQ-02, REQ-04, ADR-0036, ADR-0046 (Proposed), ADR-0050, #226, #251, #275

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

Option B, report only, on in every `ekf.run` estimator (`pnt.integrity.whiteness`): each innovation is normalised per component (z = y_i / √S_ii); one stream is one (source, emitter, kind, component); a record pairs with its stream's previous record if that is at most 5 s older (`TBC`). Per source over a sliding window: r = Σp / √(Σz_k² Σz_(k−1)²) and T = Σp / √Σp², p = z_k z_(k−1). `innovations_correlated:<source>` is raised while T > threshold with at least 30 pairs (`TBC`). The flag is appended after the estimator and any monitor, so status, trust and every other flag are as without it; the panel shows it as a caution and it degrades no status.

Window **60 s** and threshold **T > 6** (both `TBC`), chosen on sim seeds 0–9 by the rule in `analysis/whiteness.py` `choose`: fewest false onsets, then fewest misses, then shortest delay.

## Consequences

1. **Separates the diagnosed legs from honest noise on LTE (sim, held-out seeds 10–29, `ekf`):** LTE flagged in 20 of 20 runs on `challenge-drone-nominal`, `challenge-drone-outage` and `challenge-approach-outage`; no LTE flag in 8 h of honest runs (`easy-nominal`, `easy-outage`, `easy-long-outage`, `nominal`). Median delay from the first LTE record 38 s (drone legs, worst 112 s) and 159 s (approach, worst 417 s).
2. **Weak on `realistic-long-outage`:** 2 of 20 runs. Its told σ equals the white σ, so the 50 m / 30 s multipath is half the error and T peaks at 3.4–6.9. A longer window or Ljung-Box (option C) would be the next thing to try; not done.
3. **GNSS position false alarms on held-out seeds, which the tuning seeds did not show:** 35 onsets in 8 h of honest runs (4.4 per hour), 33 of them on `nominal` (8 of 20 runs, 16.5 per hour), whose square route turns sharply: the constant-velocity motion model, not the GNSS error, correlates the innovations. Tuning seeds peaked at T = 5.4 there, under the threshold. The flag names the source whose innovations are correlated, not the term that is mismodelled.
4. **GNSS after GPS returns:** on the outage legs GNSS (and on the approach GNSS time) fires within 3 to 15 s of GPS returning (17 and 13 of 20 runs): the filter comes back overconfident, so the GNSS innovations are truly correlated while it converges. A true detection of a mismodelled filter, attributed to GNSS.
5. **A filter that models the correlation is quiet:** `ekf-calibrated` (multipath state per emitter) raises no LTE flag on the approach or `realistic-long-outage` (0 of 20 each), and still fires on the drone legs, where its multipath state is sized to the told 2 m.
6. **Real sessions (replay, whole session, `ekf` as registered):** LTE flagged on 99 % of epochs of both static captures and the handheld walk (r 0.96–0.99); GNSS position on 54 %, 98 % and 88 % (r 0.84–0.997: the GPS HAT's fixes are smooth, not white); barometer never. So on real data the flag says what ADR-0036 and ADR-0050 measured for LTE, and adds that real GNSS fixes are correlated too.
7. **No estimate changes:** the flag is added after the estimator and monitors (`ekf.run`), and the panel's status ignores it (`health.panel_status`). Every registered estimator's estimates hash identical to `main` without this flag (see *Checks*).
8. **Not covered:** `ekf-base` and `ekf-base-imu` (own run loop: no flag); sources with no innovations (IMU); a negative correlation (one-sided).
9. **Reopen if:** step 2 of #275 (a state per flagged source) needs a different statistic; a source-specific threshold or window is wanted for GNSS position; a moving real session with truth shows the GNSS correlation hurts the bound.

## Checks

Sim (placeholder models, ADR-0015) and replay of real sessions; numbers, commands and commits in `analysis/results/whiteness-275/NOTES.md`.

- **Window and threshold:** grid 20/30/60/120 s × T 3/4/5/6/8 on seeds 0–9 (`ekf`): 60 s / 6 is the only point with 0 false onsets and the fewest misses (7 of 40, all `realistic-long-outage`); no point had 0 of both.
- **Held-out seeds 10–29:** the table in consequences 1–5. The filter's own flags equal the offline statistic on every run.
- **Real sessions:** consequence 6.
- **No estimate changed:** every registered estimator's estimates (time, position, velocity, covariance, clock, HPL, VPL, status, trust, every other flag) hash identical to `main` `6dc4077`: 360 of 360 sim runs (18 estimators × 10 scenarios × seeds 0, 1) and 18 of 18 real-session runs (6 estimators × 3 sessions).
- **Tests:** `tests/test_whiteness.py`; the EKF tests fail without the hook in `EKF.process`.
