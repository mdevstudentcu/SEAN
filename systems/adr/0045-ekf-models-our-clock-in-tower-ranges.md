# ADR-0045: `ekf` models our receiver clock in the tower ranges by default

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (owner)
- **Traces to:** REQ-01, REQ-02, REQ-04, ADR-0022 (amendment 1), ADR-0030, ADR-0034, #228

## Context

`ekf` (and `ekf-imu`, `ekf-mhss`, the `-guard` filters; `baseline` gives identical output on these runs) defaults to `pseudorange_receiver_clock=False`: a tower reading without `meta.rx_clock` carries no term for our clock. The realistic and worst sets, and `challenge-approach`, put our payload clock into every such reading (`receiver_clock: true`), as a real radio does. Their clock drifts 20 ppb (6 m/s) in the realistic set and 100 ppb (30 m/s) in the worst set.

What that does, measured in #228 (`analysis/rx_clock_in_towers.py`, commit `37d66b7`, seeds 0-49, sim, placeholder models; `analysis/pr-evidence/228/summary.md`):

- **Cause.** Each tower's own clock is a 0.2 m/√s random walk, so it cannot follow a 6 m/s ramp. Once GPS is lost the gate still accepts the towers (73 % of LTE updates on `realistic-long-outage`, median NIS 1.7), and the filter moves the position to explain the ramp while its covariance shrinks as though the towers fixed it.
- **The error follows our clock.** `ekf` on `realistic-long-outage`, T1 p95 mean: 304 m at 0 ppb, 2,351 m at 20 ppb and 4,239 m at 40 ppb. With the towers dropped it is 2,292 m at every drift (constant-velocity coasting). At 20 ppb the two are about the same by coincidence, which is why the #27 ablation found that removing LTE changed nothing (+2.9 ± 112.6 m).
- **The barometer is not at fault.** It is accepted throughout (median NIS 0.4), and the vertical error stays near the sim's 1 m baro bias. Without it, the vertical state takes up the clock ramp (2.8 km vertical error on seed 0), which takes it off the horizontal. That is the "-672 m without baro" in #27.
- **The HPL is overconfident.** On the worst run, `ekf`'s HPL bounds the error on 2.7 % of the first 300 s.
- **Turning the term on fixes the drift for every EKF.** `ekf-calibrated`, which has the term on, goes from 370 m to 1,474 m with it turned off.

ADR-0022's amendment 1 (owner, 2026-11-09) reads "Our receiver clock is modelled in the tower ranges". It was implemented only in `CALIBRATED` (`ekf-calibrated`). The default `ekf` contradicts it. `base_rover` already sets the term on.

## Options

Paired, seeds 0-49, `ekf` → `ekf` with `pseudorange_receiver_clock=True` (summary.md has every row):

| Scenario | Metric | `ekf` | With the term |
| --- | --- | --- | --- |
| `realistic-long-outage` | T1 p95 mean (worst run) | 2,350.8 (3,777.3) m | 331.7 (787.4) m |
| `realistic-long-outage` | T1 HPL bound, worst run | 0.027 | 0.631 |
| `realistic-outage` | p95 mean | 2,668.8 m | 196.4 m |
| `worst-long-outage` | T1 p95 mean | 10,404.1 m | 2,067.9 m |
| `challenge-approach-outage` | T1 p95 mean (HPL bound, worst run) | 2,344.0 m (0.085) | 1,448.7 m (0.540) |
| `challenge-drone-outage` | everything | unchanged | unchanged: its records carry their own dongle clock (`meta.rx_clock`) |
| `realistic-nominal` | p95 mean | 3.0 m | 3.0 m |
| `nominal` | p95 mean (misleading per run) | 5.4 m (48.1) | 5.4 m (48.5) |
| `gps-outage` | p95 mean | 15.5 m | 17.6 m |
| `spoof-ramp` | misleading / hazardous per run | 1,872.5 / 1,621.3 | 1,923.5 / 1,672.0 |
| `meaconing` | misleading per run | 1,988.1 | 2,048.6 |

| Option | Pros | Cons |
| --- | --- | --- |
| A. `pseudorange_receiver_clock=True` by default in `ekf` | Matches every real radio and ADR-0022 amendment 1. Removes the km drift on the realistic, worst and approach sets. One line. | Changes every default output on scenarios with sim-shaped towers. The base set's towers carry no clock of ours, so the term costs one tower's worth of geometry there: `gps-outage` +2.1 m p95, `spoof-ramp` and `meaconing` +51 to +61 misleading epochs per run. |
| B. Keep the default, and show realistic-set and approach figures from `ekf-calibrated` | No change to defaults. | The default estimator stays wrong on the environment we pitch, and its HPL stays below its error. There are two estimators to explain to the judges. |
| C. A, and the base sets put our clock in their towers too (sim change) | One model fits every scenario. | A sim change breaks pairing with every earlier number. Larger change. |

## Decision

Proposed: option A. C can follow later.

## Consequences

- If A is accepted: flip the default in `nav/ekf.py` (its comment already says "True once the sim models it (#47)"). Then rerun `just results` and the challenge legs, and report the changed default outputs against `main`.
- **A does not make the HPL honest.** With the term on, `ekf`'s T1 HPL bound on the worst `realistic-long-outage` run is 0.631. The tower model is still white noise, while the sim adds 50 m of multipath correlated over 30 s and 100 m told-position errors (#77). In the #228 bisection those two were the rest of the gap: with the sim's multipath and told-position error removed, the bound was 1.000 on 5 seeds. `ekf-calibrated` models both and still reaches only 0.887 on its worst run.
- **The UC-01 drone leg (`challenge-drone-outage`) is a separate problem.** Its front-end records already carry the dongle clock. `ekf` rejects 98 % of them (median NIS 150). Their reported σ is 2 m against the sim's 50 m white noise and 50 m multipath, which likely explains it (not bisected here). That is #147's question, not this one.
- Reopen if real captures show our clock does not reach the tower ranges (it always does with one shared oscillator), or if the base-set cost grows past a stated bar.
