# ADR-0047: `ekf` models our receiver clock in the tower ranges by default

- **Status:** Accepted (option D, 2026-11-11, owners; time-integrity cost accepted, fix on the roadmap)
- **Date:** 2026-11-11 (proposed and accepted)
- **Deciders:** owners
- **Traces to:** REQ-01, REQ-02, REQ-04, ADR-0022 (amendment 1), ADR-0030, ADR-0034, #228

## Context

`ekf` (and `ekf-imu`, `ekf-mhss`, the `-guard` filters; `baseline` gives identical output on these runs) defaults to `pseudorange_receiver_clock=False`: a tower reading without `meta.rx_clock` carries no term for our clock. The realistic and worst sets, and `challenge-approach`, put our payload clock into every such reading (`receiver_clock: true`), as a real radio does. Their clock drifts 20 ppb (6 m/s) in the realistic set and 100 ppb (30 m/s) in the worst set.

What that does, measured in #228 (`analysis/rx_clock_in_towers.py`, commit `883bfe6`, seeds 0-49, sim, placeholder models; `analysis/pr-evidence/228/summary.md`):

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
| `gps-outage` | p95 mean (paired Δ ± SE) | 15.5 m | 17.6 m (+2.1 ± 0.8) |
| `spoof-ramp` | misleading per run (paired Δ ± SE) | 1,872.5 | 1,923.5 (+51.1 ± 60.9: not significant) |
| `meaconing` | misleading per run (paired Δ ± SE) | 1,988.1 | 2,048.6 (+60.5 ± 9.6) |
| `easy-long-outage` | T1 p95 mean (paired Δ ± SE) | 20.4 m | 4,314.2 m (+4,293.9 ± 241.8) |

The Δ rows and `easy-long-outage` are from the cost study below (`costs.md`, commit `7383c34`). The `easy-long-outage` cost was missing from this ADR's first version.

### Can the costs be avoided? (2026-11-11, owner's follow-up)

`analysis/rx_clock_in_towers.py --costs` (commit `7383c34`, seeds 0-49 paired, sim; `analysis/pr-evidence/228/costs.md`). The base scenarios that carry a cost fall into two kinds:

1. **No payload clock and no GNSS time** (`gps-outage`, `spoof-ramp`, `nominal` and most of the base set). The term adds a clock that nothing observes. The cost comes from its frequency wander (`h_2`):
   - Changing its initial offset or drift σ changed nothing (10 seeds, scratch run outside the committed script).
   - `h_2` = 2e-22 (TCXO literature: 2e-20) cuts the `gps-outage` cost to +0.4 ± 0.2 m. That is tuning to a sim that has no frequency wander; the real oscillator's `h_2` is TBC (day-1 Allan test).
2. **A payload clock and GNSS time, but towers that leave the clock out** (`meaconing`, `time-spoof` and the `easy` set). No real radio works this way: our clock reaches every tower reading. The filter then rejects the towers (`meaconing` seed 0: 47 of 900 accepted before the attack), at the same size as #228 in reverse:
   - `easy-long-outage` T1 +4,294 m.
   - `ekf-guard` with the term on `meaconing`: p95 18.1 → 5,770.8 m. The guard excludes GNSS, and the towers it has left are rejected.

What each variant gives (Δ against `ekf`):

| Variant | `realistic-long-outage` T1 (HPL bound, worst run) | `gps-outage` Δ p95 | `meaconing` Δ misleading | `easy-long-outage` Δ T1 |
| --- | --- | --- | --- | --- |
| Term always on (A) | 331.7 m (0.631) | +2.1 ± 0.8 m | +60.5 ± 9.6 | +4,293.9 m |
| `observed`: on once GNSS time has been used | 331.7 m (0.631) | +0.0 (identical) | +60.5 ± 9.6 | +4,293.9 m |
| `gnss_out`: on only while GNSS position is lost or excluded | 636.8 m (0.162) | +2.7 ± 1.2 m | −588.8, but p95 +402.2 m | +552.9 m |
| A with `h_2` = 2e-22 | 297.7 m (0.679) | +0.4 ± 0.2 m | +60.5 ± 9.6 | +6,065.6 m |
| A with the jump guard | 331.7 m (0.631) | +2.1 ± 0.8 m | p95 +5,729.5 m | +4,293.9 m |

What the variants show:

- **`gnss_out` is worse everywhere.** Tower clocks learned with the term off carry the lag of the clock ramp into the switch.
- **`observed` keeps every gain and removes the kind-1 costs exactly.** With no time source it is identical to `ekf`. A real payload always has GNSS time before an outage, so on real data `observed` equals A: it removes a sim-only cost and is not a better model.
- **No estimator-side variant removes the kind-2 costs.** Making those sims consistent (`receiver_clock: true`) reverses them; these rows pair only with each other:
  - `meaconing`: A has −53.1 ± 8.7 misleading per run against `ekf`.
  - `meaconing` with the jump guard: 20.1 m p95 with the term, against 7,002.1 m without it.
  - `easy-long-outage`: T1 22.6 m with the term, against 7,903.5 m without it.
- **`ekf-calibrated` (term on) has the same kind-1 and kind-2 costs** (ADR-0022 amendment 3: `gps-outage` +4.4 m, `meaconing` +54 misleading). It does not avoid them.

| Option | Pros | Cons |
| --- | --- | --- |
| A. `pseudorange_receiver_clock=True` by default in `ekf` | Matches every real radio and ADR-0022 amendment 1. Removes the km drift on the realistic, worst and approach sets. One line. | Changes every default output on scenarios with sim-shaped towers. The base set's towers carry no clock of ours, so the term costs one tower's worth of geometry there: `gps-outage` +2.1 m p95, `spoof-ramp` and `meaconing` +51 to +61 misleading epochs per run. |
| B. Keep the default, and show realistic-set and approach figures from `ekf-calibrated` | No change to defaults. | The default estimator stays wrong on the environment we pitch, and its HPL stays below its error. There are two estimators to explain to the judges. |
| C. A, and every scenario whose payload has a clock puts it in its towers (`receiver_clock: true`: `easy`, `meaconing`, `time-spoof`; sim change) | Kind-2 costs become gains. | Breaks pairing with earlier numbers on those scenarios. `gps-outage` +2.1 m stays. |
| D. `pseudorange_receiver_clock="observed"` by default, and C | No measured row is worse than `ekf`. The consistent-sim rows ran with A; `observed` equals A wherever GNSS time comes before the towers, as there. Equals A on real data. | Kind 1 is avoided by keying on the sim's lack of a time source, not by a better model. The sim change is as in C. |

## Decision

Accepted (2026-11-11, owners): option D. Every EKF built on `nav/ekf.py` defaults to `pseudorange_receiver_clock="observed"`, and every scenario whose payload has a clock puts it in its tower readings. Without the sim change, nothing in the estimator removes the `easy` and `meaconing` costs; A or `observed` alone still carry them.

## Consequences

- **Done (#228, PR #244):**
  - `receiver_clock: true` in the `easy` set, `meaconing` and `time-spoof`. The sim's draws are unchanged; the towers now carry the clock.
  - The `EKF` default is `"observed"`. That covers `ekf`, `ekf-imu`, `ekf-mhss`, `ekf-mhss-beacon` and the `-guard` filters. `ekf-calibrated` and `ekf-base` already had the term on, and `baseline` is a separate model.
  - Before and after against `main` (`f15ba13`), 50 seeds: `analysis/pr-evidence/228/before-after.md`.
- **The bar did not fully hold once implemented (2026-11-11, 50 seeds, sim).**
  - **Position, as expected:**
    - T1 p95 mean: `realistic-long-outage` 2,350.8 → 331.7 m (worst-run HPL bound 0.027 → 0.631); `worst-long-outage` 10,404.1 → 2,067.9 m; `challenge-approach-outage` 2,344.0 → 1,448.7 m.
    - `realistic-outage` p95 2,668.8 → 196.4 m.
    - Unchanged, as the measurement predicted: `gps-outage`, `nominal`, `spoof-ramp` and the drone and timing legs.
  - **Position costs that remain**, on the sims that now carry the clock (same draws, so these rows are paired):
    - `easy-long-outage` T1: +2.2 ± 0.7 m.
    - `meaconing` misleading epochs: +7.4 ± 3.1 per run.
    - `meaconing` with `ekf-guard`: p95 +2.0 ± 0.7 m.
    - `meaconing` with `ekf-spoof`: misleading +5.8 ± 2.6 per run, hazardous 0 → 0.3 per run.
  - **New cost to time integrity (REQ-03), not in the cost study, which scored position only.** Once GNSS time is gone, the towers steer our clock, and their white-noise model makes the clock overconfident. Time-misleading epochs per run:

    | Scenario | Before | After | Time p95 before → after |
    | --- | --- | --- | --- |
    | `realistic-long-outage` | 0 | 268 | 0.17 → 0.44 µs |
    | `worst-long-outage` | 0.02 | 316 | 0.31 → 1.65 µs |
    | `realistic-outage` | 0 | 81 | |
    | `meaconing` | 0 | 293 | |
    | `challenge-approach-outage` | 0 | 22 | 0.41 → 12.2 µs |

    `time-spoof` improves: 20.9 → 5.2 time-misleading epochs per run. `ekf-calibrated` models the towers' multipath and had 0.0 time-misleading epochs per run on `realistic-long-outage` (`analysis/results/calibrated-measured/`), so the tower model (#77) is the likely fix. It has not been tried here. Our clock's noise is not the cause: raising `h0` to the sim's 2 ns/√s (8e-18) left it at 87 time-misleading epochs per run against 93 (`realistic-long-outage`, 10 seeds, scratch run).
  - **The owners accepted this time-integrity cost (2026-11-11)**, for the position gain: the mentors (2026-11-10) put location ahead of timing. Figures made with the new default carry it, and its fix, a tower error model with the multipath and correlation `ekf-calibrated` already uses (#77), is on the roadmap (`systems/roadmap.md`, *Open work items*).
  - `tests/test_ekf_rx_clock_modes.py` fails if the default reverts.
- **The numbers above came from commits before the rebase onto `e9a9053`** (run on `c21e047`; the changes are `883bfe6` and `7383c34` on `main`). The `analysis/rx_clock_in_towers.py` variants keep the old default explicitly, so they still mean what they did.
- **A does not make the HPL honest.** With the term on, `ekf`'s T1 HPL bound on the worst `realistic-long-outage` run is 0.631. The tower model is still white noise, while the sim adds 50 m of multipath correlated over 30 s and 100 m told-position errors (#77). In the #228 bisection those two were the rest of the gap: with the sim's multipath and told-position error removed, the bound was 1.000 on 5 seeds. `ekf-calibrated` models both and still reaches only 0.887 on its worst run.
- **The UC-01 drone leg (`challenge-drone-outage`) is a separate problem.** Its front-end records already carry the dongle clock. `ekf` rejects 98 % of them (median NIS 150). Their reported σ is 2 m against the sim's 50 m white noise and 50 m multipath, which likely explains it (not bisected here). That is #147's question, not this one.
- Reopen if real captures show our clock does not reach the tower ranges (it always does with one shared oscillator), if the base-set cost grows past a stated bar, or if the measured `h_2` of our oscillator is far from 2e-20.
