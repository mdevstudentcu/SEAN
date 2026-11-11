# ADR-0037: A tower displacement monitor checks the GNSS position against the towers, opt-in

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-02, REQ-04, ADR-0021, ADR-0022, ADR-0024, ADR-0030, ADR-0034, #147, #170, #173, #189

## Context

ADR-0021 pitches towers catching a GPS position spoof. In the challenge baseline (#170) the 2 m/s ramp of the T4 target is detected on no seed by any estimator. On the challenge legs the filter rejects almost every tower reading, because the records report 2 m while the error is far larger (#147), so the filter is in effect GPS-only, and a slow ramp is followed rather than flagged.

`src/pnt/integrity/spoof_monitor.py` (#173) tests the towers against the GNSS fix outside the filter. Once a second, per (lag, window) pair, it removes every clock and each site's constant bias by a two-way fit, fits how far the GNSS position moved against the towers over the lag, and tests that displacement with an F-test. Nothing the filter learned while GNSS steered it can hide a spoof from it. It is wired as new estimator names (`ekf-spoof`, `ekf-calibrated-spoof`, `ekf-imu-spoof`); existing estimators are byte-identical.

Its settings are values we chose, not requirements, so adopting it is a decision. Results: `analysis/results/spoof-detection/summary.md` (sim, seeds 0–49, `python analysis/spoof_detection.py --seeds 50 --mhss-seeds 5 --jobs 2`).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. No monitor: the filter's own GNSS gate | Nothing to add | Catches jumps, not the ramp: 0 of 50 seeds on every leg |
| B. `ekf-mhss` solution separation | Exists; also gives an HPL | 1 of 5 ramp seeds on the many-tower case; 14 false alarms per hour on its `nominal` (5 seeds) |
| C. Tower displacement monitor, sliding lags (this ADR) | Clock-free, outside the filter, no calibration before the spoof needed; a ramp cannot be learned as normal | Needs at least 5 sites; minutes, not 30 s, for 2 m/s; assumes independent per-site errors |
| D. The same test anchored to a pre-spoof reference | More displacement to test as the ramp grows | Needs a clean calibration period, and the towers' own errors drift away from the anchor |
| E. GNSS-free IMU copy against the filter (`imu=True`) | Sees a change of GNSS velocity the IMU did not feel | Sees acceleration only; a ramp already running is inherited. No detection added on 5 tuning seeds |
| F. Fix the told sigma (#147) so the filter uses the towers | Fixes the cause for every estimator | Not done; owned by #147; the filter would still adapt to a slow ramp |

## Decision

Option C as an opt-in integrity monitor (`ekf-spoof`, `ekf-calibrated-spoof`), with the settings below, all `TBC`. The IMU test (E) stays in the code, off by default.

## Consequences

Each point is proposed; the owners accept or change it.

1. **Settings, all `TBC`, chosen on tuning seeds 100–109 of the many-tower drone case, never on the reported seeds 0–49:**
   - Tower tests `(lag, window)` = `(30 s, 10 s)` and `(120 s, 20 s)`. Lags of 30, 60, 120 and 240 s with windows of 10 and 20 s were tried alone; `(120, 20)` had the shortest median time to alert on the ramp with no false alarm, and `(30, 10)` is the shortest lag tried, for steps.
   - `p_fa_towers` = 1e-4 per second for all tower tests, split evenly (Bonferroni): by the union bound at most 0.36 false alarms per hour, inside T4's 1 per hour.
   - F(2, dof) threshold in closed form; residual variance pooled over `pool_s` = 300 s, dof counted over non-overlapping windows only.
   - `min_sites` = 5 sites heard in both windows: 2 displacement unknowns and 1 common term leave n − 3 ≥ 2 for a variance.
   - `hold_s` = 3 s before an exceedance raises the alarm.
2. **What it detects (sim):** the 2 m/s ramp where at least 5 sites are heard, in 2 to 5 minutes: on the drone leg with every tower within 3 km heard (17 eNBs) on 48 of 50 seeds, median 131 s, worst 313 s. It adds no false alarm on `nominal` or `outage`, on any leg or seed.
3. **What it does not detect:**
   - **The ramp within T4's 30 s** (kept by ADR-0034, `TBC`). It is not reachable with these error sizes: in 30 s the ramp moves the fix 60 m, against about 34 m (1σ) of the towers' own uncertainty over that lag.
   - **Anything with 1 to 3 cells,** which is the drone leg as committed (1 of 50 seeds) and the `realistic` set (4 towers, 0 of 50): with fewer than 5 sites it has no opinion.
   - Spoofers slower than 2 m/s were not run (threat model, *Slower or filter-aware position drift*).
4. **Response:** an alarm calls `EKF.raise_spoof_alarm`, the filter's own response (GNSS position excluded until it agrees again, a calibrated filter's tower clocks roll back). Jumps are the filter's own gate's job; refusing a detected jump is #184, the jump study #176.
5. **Assumption to check on real captures:** each site's error is independent of the others' with one shared variance. Correlated multipath across sites would make the F-test overconfident (more false alarms than the bound).
6. **Pitch:** what is shown is "towers catch a slow position spoof where at least 5 sites are heard, in minutes for 2 m/s". ADR-0021's wording would need an amendment for the narrower claim; that is an open question for the owners, not part of this ADR.
7. **Reopen** if real captures show correlated per-site errors, if #147 makes the filter use the towers, or if the hearing on the real drone leg is below 5 sites.

**Open questions:**

- Default the monitor on, or keep it opt-in until a real session shows its false-alarm rate?
- Re-tune on more than 10 seeds, or on the challenge leg as heard, once real captures size the per-site error?
