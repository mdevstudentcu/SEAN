# ADR-0037: A tower displacement monitor checks the GNSS position against the towers, opt-in

- **Status:** Proposed
- **Date:** 2026-11-10, amendment proposed 2026-11-11 (the site rule on hopped carriers: see *Amendment 2026-11-11 (Proposed)*)
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-02, REQ-04, ADR-0021, ADR-0022, ADR-0024, ADR-0030, ADR-0034, ADR-0038, ADR-0040, #147, #170, #173, #189, #221, #258

## Context

ADR-0021 pitches towers catching a GPS position spoof. In the challenge baseline (#170) the 2 m/s ramp of the T4 target is detected on no seed by any estimator. On the challenge legs the filter rejects almost every tower reading, because the records report 2 m while the error is far larger (#147), so the filter is in effect GPS-only, and a slow ramp is followed rather than flagged.

`src/pnt/integrity/spoof_monitor.py` (#173) tests the towers against the GNSS fix outside the filter. Once a second, per (lag, window) pair, it removes every clock and each site's constant bias by a two-way fit, fits how far the GNSS position moved against the towers over the lag, and tests that displacement with an F-test. Nothing the filter learned while GNSS steered it can hide a spoof from it. It is wired as new estimator names (`ekf-spoof`, `ekf-calibrated-spoof`, `ekf-imu-spoof`); existing estimators are byte-identical.

Its settings are values we chose, not requirements, so adopting it is a decision. Results: `analysis/results/spoof-detection/summary.md` (sim, seeds 0–49, `python analysis/spoof_detection.py --seeds 50 --mhss-seeds 5 --jobs 5`; the summary names the commit and host).

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
4. **Response:** an alarm calls `EKF.raise_spoof_alarm`, the filter's own response (GNSS position excluded until it agrees again, a calibrated filter's tower clocks roll back). Jumps are the filter's own gate's job; refusing a detected jump is the opt-in jump guard ([ADR-0038](0038-refuse-detected-gnss-jump.md), `ekf-guard`, #191), the jump study #176. The monitor is not combined with the guard here.
5. **Assumption to check on real captures:** each site's error is independent of the others' with one shared variance. Correlated multipath across sites would make the F-test overconfident (more false alarms than the bound).
6. **Pitch:** what is shown is "towers catch a slow position spoof where at least 5 sites are heard, in minutes for 2 m/s". ADR-0021's wording would need an amendment for the narrower claim; that is an open question for the owners, not part of this ADR.
7. **Reopen** if real captures show correlated per-site errors, if #147 makes the filter use the towers, or if the hearing on the real drone leg is below 5 sites.

**Open questions:**

- Default the monitor on, or keep it opt-in until a real session shows its false-alarm rate?
- Re-tune on more than 10 seeds, or on the challenge leg as heard, once real captures size the per-site error?

## Amendment 2026-11-11 (Proposed): the site rule on hopped carriers (#258)

Proposed; the owners accept or change it. Nothing here re-tunes a setting of consequence 1.

**Context.** With one dongle hopping carriers (ADR-0040, Proposed, a study leg: the payload cannot hop yet), the monitor had no opinion on any second of the 2 m/s ramp and flagged it on 0 of 50 seeds at 13 carriers (#221, PR #254). A site counted only if heard on half of every epoch of a window. Hopping puts one carrier on air per epoch, so a site is heard only on its own carriers' dwells: at 13 carriers and 1 s dwells, about 1 epoch in 13. On tuning seed 100, 51 sites were heard in a 10 s window and the best on 3 of 10 epochs. The rule was there to drop sites that fade in and out; on hopped data it dropped every site for a reason that has nothing to do with fading.

**Rule.** A site counts if heard on at least half of each window's epochs on which one of its own carriers was on air. A carrier is on air at an epoch if any reading on it (`meta.earfcn`) falls there; a site's carriers are those it was heard on in the test's span (`spoof_monitor.towers_test`). With one carrier, or records that name none, every epoch with a reading has that carrier on air, so the keep mask, and everything after it, is the rule before: a special case, not a switch.

**What changes in the test's statistics on hopped windows**, and what was checked:

- **Noise model:** a site's delta is a mean over 1 or 2 readings per window instead of about 10, so white noise is not averaged down, and sites on 1 and on 3 carriers have different variances. The test keeps one pooled variance per test (300 s), which absorbs the level but not the spread.
- **Degrees of freedom:** the epoch term of the two-way fit is estimated from the few sites heard at that epoch, all on one carrier, so it takes their mean displacement. The displacement fit is biased low (0.68 of the true move in the synthetic test `test_tower_test_has_an_opinion_on_hopped_carriers`), and the deltas of one dwell are correlated, so F(2, (n − 3) × windows) is an approximation, not exact.
- **Threshold:** unchanged. On `nominal`, seeds 100–109 (`python analysis/drag_with_hopping.py --seeds 10 --stress-seeds 10 --first-seed 100 --jobs 5 --out DIR`, at b9564ef), the share of tests under p = 0.1 / 0.01 / 0.001 against that F distribution: 6.7 / 0.76 / 0.07 % (30/10 s) and 5.4 / 0.52 / 0.00 % (120/20 s) at 13 carriers, 11.4 / 0.96 / 0.00 % and 8.8 / 0.40 / 0.00 % at 6. A calibrated test puts 10 %, 1 % and 0.1 % there, so the test is at or below its nominal rate in the body of the distribution. These are correlated seconds, a few thousand per test: they check the shape, not the 1e-4 tail the false-alarm budget rests on. No false alarm on those seeds (20 paired `nominal`/`outage` runs at 6 and at 13 carriers, and 10 `nominal` runs with 2 s dwells), so nothing was re-tuned.

**Options considered:**

| Option | For | Against |
| --- | --- | --- |
| A. Keep the rule | Nothing changes | No opinion on hopped data: 0 of 50 at 13 carriers |
| B. Count against the epochs a site's own carriers were on air (this amendment) | One rule for every data; the old rule is its single-carrier case, byte-identical; needs no hop schedule as configuration | The test's distribution is an approximation on hopped windows (above) |
| C. Windows of whole hop cycles (13 s, 26 s) | Every carrier in every window | Does not help alone: a site on one carrier is still heard on 1 of 13 epochs. Changes the tuned lags and windows |
| D. A minimum count of readings, scaled by the hop duty | Same as B on a regular schedule | Needs the hop set and dwell as monitor configuration; B reads them from the data |
| E. B, plus one joint least squares of site constant, epoch clock and site step, regressing the steps with an intercept per direction the clocks leave unidentified | Recovers the whole displacement in a synthetic hopped case where B recovers about two thirds (prototype); degrees of freedom counted exactly | More code. Tried as a prototype outside the repo (not committed) on seeds 100–109: no earlier alarm worth it (median 120 s against 124 s, 10 of 10 both), and its tail shares at p = 0.01 were 1.3 to 2 times nominal at 13 carriers. Not taken |

**Result (sim, study leg, every value `TBC`):** `analysis/results/drag-with-hopping/summary.md`, seeds 0–49 paired, at f931bb0 (`--seeds 50 --stress-seeds 10 --jobs 5`, results commit b9564ef). At 13 carriers (26 masts per 10 s) `ekf-spoof` flags the 2 m/s ramp on 50 of 50 seeds (0 of 50 with the rule before), median 127 s, worst 276 s, error at alert 254 m (median); hazardous epochs on the ramp 2,734 against 5,449 without the monitor (mean); no added false alarm in 100 paired `nominal`/`outage` runs. #221's bar (>= 45 of 50, 0 added false alarms) is met at 13 carriers. With one carrier every scored metric and tower-test log is identical to the rule before on 150 of 150 runs, and every registered estimator hashes identical to `main` 8892fca on `challenge-drone-outage`, `-spoof-ramp` and `-spoof-jump`, seeds 0 and 1 (108 of 108), as do the three `-spoof` estimators on the many-tower case and `realistic` (36 of 36). The held 300 m jump is flagged on 10 of 10 seeds at 1 s, as without the monitor. 2 s dwells: 10 of 10 ramps (median 155 s, worst 337 s), no false alarm on 10 `nominal` runs. `outage` (GNSS lost 120–240 s): no alarm added on any of 50 seeds at 1, 6 or 13 carriers; the alarms counted there are the filter's own, the same with and without the monitor.

**What it does not cover:**

- **T4's 30 s.** Median 127 s, worst 276 s. In 30 s the ramp moves the fix 60 m; the 30 s-lag test's own 1σ on that move is 41 m (median), and its threshold needs about 5 σ along one axis, so 30 s is out of reach at these error sizes, hopped or not (consequence 3).
- **Six carriers** (about 8 masts per 10 s): 2 of 50 ramps (352 and 415 s), against 1 of 50 with the rule before; the rule before's one detection (seed 24, 144 s) is lost, and **one false alarm is added**: `nominal` seed 48, 0.10 per hour over the 50 runs. Rerun by hand at b9564ef with the per-second log: on seed 24 the new rule's 120/20 s test exceeded for 2 s, short of `hold_s`; on seed 48 the 30/10 s test exceeded at 432–435 s with 5 sites kept (`min_sites`, 2 degrees of freedom per test). It is on a reported seed, so no setting was changed for it; tuning seeds 100–109 showed none. At this hearing the rule gives the monitor an opinion (55 % of seconds on the 30/10 s test) but not the power to catch the ramp.
- **Ramps slower than 2 m/s:** 1 m/s, 4 of 10 seeds (median 234 s, worst 362 s); 0.5 m/s, 0 of 10 (seeds 0–9, 13 carriers). The test sees a ramp only once it has moved the fix several σ over 120 s.
- **Real data.** The payload cannot hop (ADR-0040 point 5), so this is sim only, and ADR-0040's one clock per eNB across carriers is `TBC`. Several dongles hopping at once would put several receiver clocks in one epoch; the two-way fit assumes one common term per epoch.
- **Correlated per-site errors** (consequence 5) matter more here: with few sites per epoch, one shared error moves the epoch term.
