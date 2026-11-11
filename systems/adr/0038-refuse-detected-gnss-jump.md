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

Every EKF estimator refuses a detected GNSS position jump, and re-admits GNSS only when the GNSS stream's own steps since the latch add up to zero (option B, `pnt.integrity.jump_guard`, on by default; `jump_guard=None` turns it off).

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
- **A genuine GNSS step:** a receiver re-solve or a multipath jump latches like a spoof, and stays out until the stream steps back. A slow return to the truth is not a step, so GNSS stays refused. This case has not been tested.
- **Unchanged:** runs in which no latch is set give the same estimates as before. On clean scenarios all 7 registered estimators are byte-identical to `main` 8987664. False alarms on `nominal` and `outage` are unchanged.
- **Tests:** the #119 alignment test injected a 30 m jump during alignment. The guard now refuses it and the IMU never aligns (a new test checks this). The alignment bound is still tested on that jump with the guard off.
- **Reopen if:**
  - real captures show GNSS steps that are not spoofs often enough to cost availability;
  - the filter gains aiding good enough that an absolute test (option D) becomes honest;
  - REQ-04's false-alarm budget sets other thresholds.
