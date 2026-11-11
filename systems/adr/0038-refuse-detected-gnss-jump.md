# ADR-0038: Refuse a detected GNSS position jump until the jump is undone

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** the two owners
- **Traces to:** REQ-02, REQ-04, ADR-0021, ADR-0024, #158, #180, #184

## Context

The mentors asked us to begin with location jumps (#158). In #180's evidence every jump from 25 m to 300 m on the `challenge` legs is detected in 1.1 s, and the output then follows it.

Why (sim, `ekf`, `challenge-drone`, tuning seeds 100-102):

- The GNSS gate (`CHI2_999`, 3 dof) rejects the first jumped fix: NIS 71 to 108 for 25 m, about 11,000 for 300 m.
- Each rejection leaves the filter coasting. On these legs it rejects almost every tower reading (#147), so it dead-reckons, and the position sigma grows from 1.2 m to 5.4 m in 2.8 s.
- Once the covariance has grown enough, the same jumped fix passes the same gate (at +3 to +4 s for 25 m, at +28 s for 300 m). One fix pulls the estimate across, and from then on GNSS is followed with an HPL of 7 m.

So a spoofer only has to wait. Any re-admission test whose covariance grows with time has the same flaw.

## Options

Numbers: sim, `ekf`, seeds 0-49, commit 84401c5 (`analysis/results/jump-refusal/summary.md`). Each cell gives the drone leg, the many-tower drone case and the timing leg.

| Option | Held 300 m jump: hazardous epochs per run (seeds with any) | Held jump: output on the spoofed position at +120 s | Jump ended at 300 s: seeds re-admitted, median delay |
| --- | --- | --- | --- |
| A. Gate only (before) | 5,244 (49/50); 4,848 (49/50); 5,317 (50/50) | Yes, on 44/47, 42/44, 45/47 seeds | 48/50, 18.8 s; 45/50, 18.9 s; 48/50, 24.4 s |
| **B. Refuse; re-admit when the stream's steps since the latch add up to zero (`undo`)** | **3 (3/50); 10 (6/50); 4 (6/50)** | **No (0/50)** | **50/50, 0.1 s; 48/50, 0.1 s; 50/50, 0.1 s** |
| C. Refuse for the rest of the run (`never`) | 3; 10; 4 | No | 0/50 on every leg |
| D. Refuse; re-admit on a likelihood-ratio test against the filter's covariance (`lr`) | 4,034 (46/50); 3,189 (38/50); 3,362 (42/50) | Yes: error 301 m at +120 s on the drone | 38/50, 83 s; 26/50, 40 s; 35/50, 91 s |

D's false re-admission bound holds only if the filter's covariance is honest, which it is not after a long coast. C never lets honest GNSS back in.

## Decision

Option B, **opt-in for now**: the estimators `ekf-guard`, `ekf-imu-guard` and `ekf-calibrated-guard` refuse a detected GNSS position jump, and re-admit GNSS only when the GNSS stream's own steps since the latch add up to zero (`pnt.integrity.jump_guard`). The default is off (`jump_guard=None`), so every other registered estimator's output is as on `main`. Making it the default waits on the follow-up under Consequences: it can keep honest GNSS out after a hard manoeuvre when GNSS is the only position source.

- **Latch:** the mean of the newest 1 to 3 fixes steps away from a straight line fitted to the stream's last 2 s (NIS over `STEP_NIS`). At the same fix, the innovation against the filter is over `JUMP_NIS`, and GNSS was used within `gnss_timeout_s`. The step is the offset GNSS is taken to hold.
- **While latched:** GNSS position is not used (`gnss_excluded`). Each further step of the stream is added to the offset and its covariance.
- **Re-admit:** when the offset is consistent with zero (NIS within `ADMIT_NIS`). Fixes then skip the gate until the filter has agreed with GNSS for `TRACK_S`.
- **Values (3 dof, GNSS position):**

| Value | Setting | Status |
| --- | --- | --- |
| `JUMP_NIS` | 30.66 | Derived: chi-square quantile, false latch 1e-6 per honest fix if the covariance is honest; `TBC` until REQ-04's false-alarm budget |
| `STEP_NIS` | 30.66 | Derived: same quantile, false step at most 3e-6 per fix over the 3 tests; `TBC` |
| `ADMIT_NIS` | 16.27 | Derived: the gate's 99.9 % bound, so an honest return is refused 1e-3; must stay under `STEP_NIS`; `TBC` |
| `TRACK_S`, `TRACK_MIN`, `STEP_K` | 2 s, 5 fixes, 3 | Not derived, `TBC`; chosen on tuning seeds 100-109 |

## Consequences

- **Accuracy:** a refused jump leaves the filter dead-reckoning on the challenge legs. Median error at +30 / +120 / +300 s on the drone is 115 m / 1.2 km / 5 km (seeds 0-49), against the jump size when following it. The HPL grows with it (about 550 m at +30 s), so the output is flagged unsafe rather than confidently wrong. Better aiding without GNSS (#147, IMU) is what reduces this cost.
- **Integrity:** hazardous epochs on held jumps of 50 m and more drop from thousands per run to single digits. On the many-tower case, refusing exposes the towers-only solution, whose HPL shrinks while its error grows (32 hazardous epochs per run on 7/50 seeds for `ekf-calibrated`, #147).
- **Small jumps:** a jump too small to latch is followed as before. On seed 17 the 25 m jump was missed on every leg (1/50).
- **A genuine GNSS step:** a receiver re-solve or a multipath jump latches like a spoof, and stays out until the stream steps back. A slow return to the truth is not a step, so GNSS stays refused. Receiver re-solves and multipath steps have not been tested.
- **A hard manoeuvre on a GNSS-only coast** can latch the same way and is never undone. `analysis/guard_manoeuvre.py` (sim, seed 0, GNSS sigma 2.5 m, manoeuvre at 20 s, run to 80 s; "recovered": GNSS used within 2 s of the last fix) runs 46 cases; `tests/test_jump_guard.py` pins every one. Both the gate alone and the guard recover GNSS in 22, both lose it in 19 (the coast flies the old velocity and drifts away faster than its covariance grows, so the gate never takes GNSS back either), and the guard alone keeps it out in these 5, all with GNSS at 1 Hz, where the stream's own 2 s track holds too few fixes for a line:

| Case (GNSS 1 Hz) | Gate only: recovered | Guard: recovered |
| --- | --- | --- |
| Accelerate 5.0 m/s² for 4 s | yes | no |
| Accelerate 5.5 m/s² for 4 s | yes | no |
| Accelerate 6.0 m/s² for 4 s | yes | no |
| Turn 90° at 10 m/s | yes | no |
| Turn 45° at 20 m/s | yes | no |

  The estimate is then the coast's own and flagged `unsafe`, not misleading: the cost is availability. At 5 Hz the guard locked nothing out in these cases.
- **Meaconing:** with the guard, the `meaconing` scenarios latch at the replay's start (150 s, seed 0) and GNSS stays excluded to the end of the run. That is correct: the replay lasts to the end, 5 s late, about 40 m behind the receiver on the 8 m/s loop, so GNSS is faulted for the rest of the run. The gate alone takes the lagging GNSS back once the coast has grown.
  `pnt eval meaconing --runs 20` (sim, seeds 0-19, at 9ac2aee): `ekf` has a worst-run HPL bound rate of 0.429, 1,976 misleading epochs per run and a fault-window p95 of 41.6 m; `ekf-guard` 1.000, 0 and 19.5 m. Both detect at 1.1 s; neither has a hazardous epoch or a false alarm.
- **Jump size, 20 m to 500 km** (sim, seeds 0-19, `analysis/guard_jump_sizes.py --seeds 20` at 9ac2aee; table in `analysis/pr-evidence/191/guard_jump_sizes.md`). A jump held from 150 s on the UC-01 route, realistic set (`realistic-nominal` on `uc01-drone-circuit`'s route) and `uc01-drone-circuit` as committed. Every jump is detected 1.1 s after it (p95 1.1 s), with an alert 0.1 s after it, by every variant at every size, except one 20 m jump on `uc01-drone-circuit` that `ekf` missed (19/20; `ekf-guard` 20/20). The guard changes what follows detection, not detection. Runs with hazardously misleading epochs, realistic set:

| Jump | `ekf` | `ekf-guard` | `ekf-imu` | `ekf-imu-guard` |
| --- | --- | --- | --- | --- |
| 20 m | 0/20 | 0/20 | 0/20 | 0/20 |
| 50 m | 20/20 | 0/20 | 20/20 | 0/20 |
| 100 m | 19/20 | 0/20 | 20/20 | 0/20 |
| 300 m | 19/20 | 0/20 | 19/20 | 0/20 |
| 1 km | 4/20 | 0/20 | 9/20 | 0/20 |
| 100 km, 500 km | 0/20 | 0/20 | 0/20 | 0/20 |

  On `uc01-drone-circuit` (synthetic towers) only 50 m has any (19/20 runs for `ekf`, 6/20 for `ekf-imu`, 0 with the guard). The cost on the realistic set is the coast: a median error of about 1.6 km at +120 s, flagged `unsafe`, against the jump when following it. Jumps of 100 km and more are never taken back by the gate alone within the run, so the guard changes nothing there; the jump is a flat ENU offset (no Earth curvature, about 20 km at 500 km). At 20 m the guard has misleading (not hazardous) epochs in 2/20 runs (`ekf-imu-guard` 3/20), where `ekf` follows the 20 m jump in all 20. With no jump, 0/20 runs have a false alarm and every guarded run is byte-identical to the unguarded one.
- **Unchanged:** the guard is opt-in, so every default estimator's output is as on `main`, including on meaconing and jump scenarios. Runs of a `-guard` estimator in which no latch is set give the same estimates as without the guard.
  Checked by hashing every estimate (sim, seeds 0-1, `meaconing`, `spoof-jump`, `easy-gps-return`, `gps-outage`, `nominal`, `uc01-drone-circuit`): all 7 estimators registered on `main` 8987664 are byte-identical to it, and, merged onto `main` d9d51ad, all 8 registered there are byte-identical to it.
- **Tests:** the #119 alignment test injects a 30 m jump during alignment. With the guard on, it refuses the jump and the IMU never aligns (a new test checks this). The alignment bound is still tested on that jump without the guard, the default.
- **Follow-up (open):** latch only when an independent coast exists: an IMU (`motion="imu"`), or at least N (`TBD`) towers in use. Without one, a rejection after a manoeuvre is as likely to be the coast's error as a jump, and the latch only removes availability. Re-run `analysis/guard_manoeuvre.py` on the IMU filter before deciding, and then decide whether the guard becomes the default.
- **Reopen if:**
  - real captures show GNSS steps that are not spoofs often enough to cost availability;
  - the filter gains aiding good enough that an absolute test (option D) becomes honest;
  - REQ-04's false-alarm budget sets other thresholds.
