# Accuracy budget: UC-01 after GPS loss

- **Status:** Draft, 2026-11-10
- **Traces to:** REQ-01, T1 in [`plan.md`](plan.md), UC-01. The mentors asked for this on 2026-11-10: "You will need to explain the calculations that lead to this accuracy", and "handover timing … must remain within the overall timing/accuracy budget".
- **Judged against:** T1 first, our goal: 95 % horizontal error ≤ 25 m for ≥ 300 s after GPS loss. Then the fallback, the mentors' figure: ≤ 50 m for ~2 min (taken as 120 s). Both values `TBC`; T1 and its fallback were accepted by the team on 2026-11-10 (ADR-0034), and its amendment sets the statistic: the 95th percentile across runs at each second after GPS loss. A target holds only if the whole window is within it.
- **Script:** [`analysis/accuracy_budget.py`](../analysis/accuracy_budget.py) computes every number here. Tests: [`tests/test_accuracy_budget.py`](../tests/test_accuracy_budget.py).
- **Kind of evidence:** analysis and sim. Every tower and clock value is a `placeholder` in the *Sim validity* table of [`verification.md`](verification.md), so none of this is a real-world result. Numbers from commit `f736bda` (clean tree), seeds 0–19 (REQ-10). 20 seeds, not 50: the rerun after rebasing on main had to fit the time left. With 20 runs the per-second 95th percentile lies between the two worst runs, so the Monte Carlo reads higher than a 50-run figure would; a 50-seed run before the rebase gave `ekf-imu` 22 m where this gives 26 m, and that difference mixes the seed count with main's changes since. Rerun at 50 seeds before quoting a Monte Carlo number to the judges (about 70 min on 3 workers).

## Result

Worst 95 % error over each target's window (sim, seeds 0–19, GPS good for 120 s first):

| Scenario | Estimator | T1: ≤ 25 m for 300 s | Fallback: ≤ 50 m for 120 s | Term that sets it |
| --- | --- | --- | --- | --- |
| `uc01` | `ekf` | **Missed** in the Monte Carlo (36 m). Budget 24.6 m, just within | Met: 24 m, 36 m | Range noise after handover (20 m per reading): 21 m of the 22 m budget |
| `uc01` | `ekf-imu` | **Missed by 0.5 m** in the Monte Carlo (25.5 m; 26.0 m with 300 s of GPS). Budget 16 m | Met: 15 m, 26 m | Range noise after handover: 14 m of 14 m |
| `uc01` | `ekf-calibrated` | **Missed.** Budget 58 m, Monte Carlo 41 m | Met: 36 m, 41 m | Range noise during calibration, left in the learned tower drifts and multiplied by t: 51 m alone at +300 s |
| `uc01-realistic` | `ekf-calibrated` | **Missed by 20×.** Budget 501 m, Monte Carlo 488 m | Missed: 324 m, 425 m | Multipath (50 m, 30 s, `TBC`): 215 m alone at +120 s, 360 m at +300 s. Four more terms are each over 25 m on their own |
| `uc01-realistic` | `ekf`, `ekf-imu` | **Missed by km.** Budget 7.2 km, Monte Carlo 3.9 / 3.3 km | Missed: 3.6 km; 1.9 / 1.9 km | Receiver clock: they do not model our clock in the tower ranges, so its 20 ppb drift (6 m/s) goes into the position: 1.1 km alone at +120 s |

- **No estimator meets T1 in this 20-seed Monte Carlo.** The closest is `ekf-imu` on the committed UC-01 scenario, 25.5 m with 120 s of GPS first; the budget puts it at 16 m. `ekf` misses by 6–16 m; the realistic set misses by an order of magnitude or more with every estimator.
- **The fallback is met on `uc01`** by all three estimators with 120 s of GPS first, and by none in the realistic set.
- **The IMU alone holds ≤ 25 m for 31 s and ≤ 50 m for 43 s** after GPS loss. It bridges tower dropouts; it cannot carry a 2 min outage.

## The two scenarios

| Name | What it is |
| --- | --- |
| `uc01` | [`uc01-drone-circuit.yaml`](../src/pnt/sim/scenarios/uc01-drone-circuit.yaml) as committed: 8 m/s circuit at 40 m, 6 synthetic towers 0.8–3 km away (new geometry each seed), 20 m range noise, tower clocks that only wander, our clock not in the ranges |
| `uc01-realistic` | The same circuit flown in the [`realistic`](../src/pnt/sim/scenarios/sets/realistic.yaml) environment: the 4 nearest real TELUS sites (0.6–1.7 km), 50 m range noise, 50 m multipath, towers heard 75 % of the time, told tower positions off by 100 m, tower clocks that drift, our own clock in every range |

Both are changed in two ways, so the budget and the Monte Carlo see the same thing:
- GPS is good for a *calibration time* (30–300 s), then lost for the rest of the run (300 s). UC-01's own outage is 120 s, too short for T1.
- The IMU is set to our measured MPU6050 (below), the same values as main's sim model now (`pnt.sim.sensors.MPU6050`).

## How the error is built, in four steps

GPS is lost at the *handover*. Up to then the position is known, so every tower range is a reading of that tower's clock. The filter learns each clock while GPS is good. After the handover it holds what it learned and uses the towers to find the position. Every error after the handover is either something it learned wrong, something that changed since, or noise.

**Step 1: what each tower's range is wrong by, t seconds after handover.** One term per cause:

| Term | How it grows after handover | Why |
| --- | --- | --- |
| Tower clock offset and drift | offset error + drift error × t + wander × √t | The filter fits each clock as offset + drift. From N readings of noise σ over T seconds, the drift is known to σ √(12 / (N (N² − 1))), ≈ σ √12 / T^1.5 at 1 Hz. A short calibration leaves a large drift error, and it is multiplied by t |
| Noise during calibration | the same growth | Range noise during calibration is what makes that drift error. Kept as its own term so that the handover's cost is visible |
| Multipath | σ_mp √(1 − e^(−2t/τ)) | A reflection the filter had learned at handover goes stale with its correlation time τ |
| Told tower position | σ_p × \|u(t) − u(0)\| | The published position is off by a fixed amount. At handover its part along the line of sight is inside the clock offset; the rest appears as the line of sight u turns along the circuit |
| Receiver clock | c × (white frequency noise) × √t | Our clock is in every range. It is common to all towers, so the filter estimates it as one extra unknown, which costs geometry (as a fourth satellite costs a GNSS receiver) |
| Noise after handover | σ per reading | Each new reading's own noise |

The script computes this with a linear covariance analysis of the filter's own clock model (offset and drift, or offset only; multipath and told-position states if it has them) run against the scenario's true error model, one second at a time. The filter's gains come from what it assumes, the errors from what is true, so a filter that leaves something out (no drift state, no receiver clock) is scored as it is. The least-squares drift formula above is checked against it in the tests.

**Step 2: from range errors to position.** Each epoch the filter makes a weighted least-squares fix from the towers it hears, weighted by what it believes their errors are. Position error = L × range errors, with L the gain of that fix: the geometry (HDOP) with the receiver-clock column. Noise after handover is averaged over the filter's memory: the constant-velocity filter (q = 1 m/s²/√Hz) averages over 3–5 s, the IMU filter over 7–11 s. A constant-velocity filter also lags in the turns; the IMU filter does not.

**Step 3: dropouts.** In the realistic set each tower is heard in 75 % of 30 s blocks, independently. Every pattern of towers heard is weighted by its probability. With fewer than two towers, or a fix too weak to steer the filter (believed σ over 500 m, `TBC`), the filter coasts from the start of that block: on constant velocity it misses the turns; on the IMU it drifts as below.

**Step 4: the 95 % radius.** For one circular 2-D Gaussian with σ per axis it is 2.45 σ. Across dropout patterns, tower geometries and mean offsets (lag in turns, a drift every run shares) the script takes the 95 % radius of the mixture.

### The IMU alone

If every tower were lost at handover, our MPU6050 would carry the position alone. Classical growth formulas (Groves 2013 ch. 14), per axis:

| Error | Growth |
| --- | --- |
| Velocity at handover | v₀ t |
| Accelerometer bias wander | b t² / 2 (the tilt left at handover is part of this bias, so not counted twice) |
| Accelerometer white noise | N t^1.5 / √3 |
| Gyro bias wander (tilts the platform) | g b t³ / 6 |
| Gyro white noise | g N t^2.5 / √20 |
| Heading error × turn acceleration | a ψ t² / 2 |

With our measured values, v₀ = 0.15 m/s per axis (the GPS-steered filter's steady state) and the circuit's rms turn acceleration 0.34 m/s², the 95 % radius (2.45 σ) of each term:

| Term | +30 s | +60 s | +120 s |
| --- | --- | --- | --- |
| Velocity at handover | 11 m | 23 m | 45 m |
| Accelerometer bias wander | 3 m | 12 m | 48 m |
| Accelerometer white noise | 0.5 m | 1.5 m | 4 m |
| Gyro bias wander | 8 m | 67 m | 536 m |
| Gyro white noise | 2 m | 13 m | 74 m |
| Heading (3°, `TBC`) × turn acceleration | 20 m | 78 m | 312 m |
| **All together** | **24 m** | **107 m** | **628 m** |

The gyro bias (t³) and the heading in the turns (t²) end the IMU's usefulness after 43 s (50 m).

## The values and where they come from

Labels as in ADR-0015. *Scenario, TBC* means the value is a placeholder in the scenario YAML.

| Term | `uc01` | `uc01-realistic` | Source |
| --- | --- | --- | --- |
| Tower range noise | 20 m per reading, 1 Hz | 50 m per reading, 1 Hz | scenario, TBC (RSK-02) |
| Tower geometry | 6 towers in a 0.8–3 km ring, new each seed | 4 TELUS sites, 0.6–1.7 km | synthetic / literature (ISED registry) |
| Multipath | none | 50 m, 30 s correlation | scenario, TBC |
| Tower heard | always | 75 % of 30 s blocks | scenario, TBC |
| Told tower position | exact | 100 m per axis | scenario, TBC |
| Tower clock offset | ±1000 m (577 m σ), wander 0.2 m/√s | the same | scenario, TBC |
| Tower clock drift | none | 0.05 m/s (site and builder), wander 3.8e-4 m/s/√s | form: literature (Shamaei et al. 2018); size TBC |
| Our clock in the ranges | no | yes: 20 ppb drift (6.0 m/s), 0.6 m/√s | scenario, TBC |
| GNSS time while GPS is good | none | 6 m (20 ns) at 5 Hz | scenario, TBC |
| GNSS position while GPS is good | 2.5 m at 5 Hz | the same | scenario, TBC |
| Accelerometer white noise | 240 µg/√Hz | the same | measured (20261110-0306-static-bench-overnight, 1800–18000 s); datasheet 400 |
| Accelerometer bias wander | 280 µg | the same | measured (same session) |
| Gyro white noise | 0.005 °/s/√Hz | the same | measured (same session, 0.0049–0.0053 per axis); datasheet 0.005 |
| Gyro bias wander | 16 °/h | the same | measured (same session) |
| Heading at handover | 3° | the same | TBC: the IMU filter's floor (`nav/imu.py`) |
| Filter motion noise (constant velocity) | 1 m/s²/√Hz | the same | filter tuning (`nav/ekf.py`) |
| Filter clock model | `ekf`, `ekf-imu`: offset per tower, 0.2 m/√s, no receiver clock in the ranges. `ekf-calibrated`: offset and drift per tower, multipath and told-position states, our clock in the ranges (`CALIBRATED`) | the same | filter tuning (`nav/ekf.py`) |

### Each term at +120 s and +300 s

95 % radius of each term on its own with every tower heard (GPS good for 120 s first), then the total with dropouts. Terms are independent, so their variances add; their radii do not. Synthetic towers differ per seed, so the `uc01` columns are pooled over seeds 0–19.

| Term | `uc01`, `ekf` | `uc01`, `ekf-calibrated` | `uc01-realistic`, `ekf-calibrated` | `uc01-realistic`, `ekf` |
| --- | --- | --- | --- | --- |
| Tower clocks | 5 / 7 m | 6 / 12 m | 8 / 17 m | 19 / 43 m |
| Multipath | — | — | **215 / 360 m** | 132 / 130 m |
| Told tower position | — | — | 43 / 58 m | 23 / 21 m |
| Receiver clock | — | — | 18 / 48 m | **1055 / 2769 m** |
| Noise during calibration | 3 / 3 m | **26 / 51 m** | 60 / 115 m | 12 / 12 m |
| Noise after handover | **21 / 20 m** | 21 / 21 m | 50 / 49 m | 50 / 49 m |
| Lag in turns | 5 / 2 m | 5 / 2 m | 18 / 10 m | 18 / 10 m |
| **Total, every tower heard** | 22 / 21 m | 33 / 54 m | 234 / 384 m | 1127 / 2853 m |
| **Total with dropouts** | 24 / 23 m | 36 / 58 m | 278 / 455 m | 3013 / 4610 m |

Why each estimator loses:
- `ekf` on `uc01`: almost all of it is the range noise itself. 20 m per reading through six towers' geometry is 8.0 m per axis after the filter averages it over 3 s. Calibration hardly matters: it learns only offsets, and the towers' clocks only wander (0.2 m/√s).
- `ekf-calibrated` on `uc01`: it also learns a drift per tower, and the synthetic towers have none. A drift fitted to 90 s of 20 m readings (the gate opens after 30 s) is off by ≈ 0.08 m/s (1 σ), 24 m per tower after 300 s. Learning a drift that is not there costs it T1.
- Realistic set: every term is larger. Multipath at 50 m with a 30 s memory is never averaged out, and goes stale within a minute of handover. With the filter unchanged, the multipath term alone would have to be ≈ 15× smaller (it scales with the multipath size) to fit 25 m at 300 s, and the range noise, told positions, receiver clock and calibration noise are each over 25 m too.

### Each term: how it grows, what compensates it, how long it takes

The mentors (2026-11-10) asked for each drift: how it grows, how we compensate for it, and how long it takes to reach a given error. Time is the first second after GPS loss at which that term **on its own** is over 25 m / 50 m (95 % radius, every tower heard, GPS good for 120 s first; `summary.json`, `time_to`). "From loss": over the limit from the first second after GPS loss. "—": within the limit for all 300 s.

| Term | Grows as | Compensation today | `uc01`, `ekf` | `uc01`, `ekf-calibrated` | `uc01-realistic`, `ekf-calibrated` | `uc01-realistic`, `ekf` |
| --- | --- | --- | --- | --- | --- | --- |
| Tower clocks | offset + drift × t + wander × √t | Learned while GPS is good: offset per tower (`ekf`, `ekf-imu`), offset and drift (`ekf-calibrated`); held after loss | — / — | — / — | — / — | 143 s / — |
| Noise during calibration | the same as the clock it corrupts (× t for a drift) | Longer calibration: drift error falls as T^−1.5 (handover below) | — / — | 114 s / 290 s ¹ | from loss / 61 s | — / — |
| Multipath | σ √(1 − e^(−2t/τ)), stale within ~τ | `ekf-calibrated` models it per tower (Gauss-Markov); nothing once stale | not in scenario | not in scenario | from loss / 2 s | from loss / from loss |
| Told tower position | σ_p × \|u(t) − u(0)\| as the line of sight turns | `ekf-calibrated` carries told-position states; a better survey of the towers | not in scenario | not in scenario | 43 s / 67 s | from loss / — |
| Receiver clock | c × frequency noise × √t, plus 6 m/s drift if unmodelled | `ekf-calibrated` estimates our clock as one unknown (costs geometry); `ekf`, `ekf-imu` do not | not in scenario | not in scenario | 136 s / — | from loss / from loss |
| Noise after handover | constant per reading | Averaged by the filter's motion model (3–5 s; the IMU filter 7–11 s); more towers | — / — | — / — | from loss / 31 s | from loss / 31 s |
| Lag in turns | the circuit's turns | The IMU filter removes it | — / — | — / — | — / — | — / — |
| **Total with dropouts** | | | — / — | 7 s ² / 231 s | from loss / from loss | from loss / from loss |
| IMU alone (no towers) | t to t³ (table above) | Bridges tower dropouts only | 31 s / 43 s | 31 s / 43 s | 31 s / 43 s | 31 s / 43 s |

¹ With 120 s of GPS first; longer calibration delays it (handover below). ² The total is already 24.9 m at loss (the range noise after handover alone is 20 m) and passes 25 m at +7 s as the drift error grows.

The IMU's own terms reach 25 m / 50 m at: heading × turn acceleration 34 s / 49 s, gyro bias wander 44 s / 55 s, velocity at handover 67 s / 133 s, gyro noise 78 s / 103 s, accelerometer bias wander 87 s / 122 s; accelerometer noise never within 300 s.

## Budget against Monte Carlo

The filters run on the same scenarios, seeds 0–19, GPS good for 120 s first. 95th percentile across seeds at each time since GPS loss (worst seed in brackets):

| Scenario | Estimator | | +30 s | +60 s | +120 s | +300 s |
| --- | --- | --- | --- | --- | --- | --- |
| `uc01` | `ekf` | budget | 24 | 21 | 24 | 23 |
| | | Monte Carlo | 18 (18) | 18 (30) | 20 (22) | 17 (17) |
| `uc01` | `ekf-calibrated` | budget | 28 | 29 | 36 | 58 |
| | | Monte Carlo | 20 (23) | 22 (35) | 23 (23) | 32 (40) |
| `uc01` | `ekf-imu` | budget | 14 | 14 | 15 | 16 |
| | | Monte Carlo | 18 (18) | 15 (28) | 15 (19) | 14 (16) |
| `uc01-realistic` | `ekf-calibrated` | budget | 199 | 246 | 278 | 455 |
| | | Monte Carlo | 179 (194) | 172 (176) | 425 (426) | 392 (492) |
| `uc01-realistic` | `ekf` | budget | 1171 | 1798 | 3013 | 4610 |
| | | Monte Carlo | 562 (582) | 1530 (1611) | 1805 (1895) | 3553 (3962) |
| `uc01-realistic` | `ekf-imu` | budget | 1147 | 1797 | 3024 | 4606 |
| | | Monte Carlo | 243 (309) | 1260 (1280) | 1736 (2190) | 3217 (3516) |

All values in metres. Figure: `analysis/results/accuracy-budget/budget_vs_monte_carlo.png`; terms: `budget_terms.png`.

Where they agree and where they do not:
- **`uc01`, `ekf`: within 6 m** at the times in the table, the budget high. The worst over 300 s is the other way round, 25 m against 36 m: with 20 runs the Monte Carlo's per-second 95th percentile follows the worst runs from second to second, and the budget is a smooth curve.
- **`uc01`, `ekf-calibrated`: the budget is high late** (58 m against 32 m at +300 s). The likely cause, not checked: the filter keeps refining its tower drifts from the redundant towers after handover, and the budget holds them (approximation 1). Its dependence on calibration time matches (below).
- **`uc01`, `ekf-imu`: the budget is low over the window** (16 m against 26 m worst over 300 s), though close at the times in the table. A likely cause, not checked: its weak heading on a multirotor (`nav/imu.py`) means it averages less than the budget's 7 s.
- **`uc01-realistic`, `ekf-calibrated`: within a factor 1.6**, the budget low at +120 s (278 m against 425 m) and high at +300 s (455 m against 392 m). Not explained yet.
- **`uc01-realistic`, `ekf` and `ekf-imu`: the same size, a different shape.** The budget says the unmodelled 6 m/s clock drift drags the position by km; the Monte Carlo starts lower (the filter carries the GPS position for a while; the budget does not model its 99.9 % innovation gate) and ends at 3.2–3.6 km against the budget's 4.6 km. Neither is usable.
- **Right after handover the budget is high** for every estimator: in the realistic set it starts at 90 m where the Monte Carlo starts at 3 m (figure). The filter still carries the GPS position for a few seconds; the budget's fix stands alone (approximation 2). By +30 s they agree (199 m against 179 m).

## Handover: how long GPS must be good first

What the filter learns before GPS is lost sets how fast its error grows after. GPS was lost after 30, 60, 120 or 300 s in the Monte Carlo (the budget also every 15 s in between). Worst 95 % error over each target's window, budget / Monte Carlo, in metres:

| Scenario | Estimator | Window | 30 s of GPS | 60 s | 120 s | 300 s |
| --- | --- | --- | --- | --- | --- | --- |
| `uc01` | `ekf` | T1, 300 s | 25 / 33 | 25 / 41 | 25 / 36 | 24 / 31 |
| | | fallback, 120 s | 25 / 27 | 24 / 32 | 24 / 36 | 24 / 28 |
| `uc01` | `ekf-imu` | T1, 300 s | 17 / 31 | 16 / 33 | 16 / 25.5 | 16 / 26.0 |
| | | fallback, 120 s | 16 / 30 | 15 / 33 | 15 / 25.5 | 15 / 26 |
| `uc01` | `ekf-calibrated` | T1, 300 s | 154 / 117 | 97 / 86 | 58 / 41 | 31 / 44 |
| | | fallback, 120 s | 69 / 67 | 48 / 82 | 36 / 41 | 26 / 35 |
| `uc01-realistic` | `ekf-calibrated` | T1, 300 s | 411 / 730 | 518 / 740 | 501 / 488 | 338 / 1554 |
| | | fallback, 120 s | 297 / 430 | 308 / 316 | 324 / 425 | 269 / 914 |
| `uc01-realistic` | `ekf`, `ekf-imu` | either | km | km | km | km |

Figure: `analysis/results/accuracy-budget/handover.png`.

- **`ekf` and `ekf-imu` hardly depend on calibration time** in the budget: they learn only clock offsets, which settle within seconds of 1 Hz readings, and the synthetic towers do not drift. The 20-seed Monte Carlo moves by up to 10 m between calibration times with no trend (not checked whether that is the seed count).
- **`ekf-calibrated` depends on it strongly**: its drift error falls as T^−1.5 (step 1), so its worst error over 300 s falls from 154 m after 30 s of GPS to 31 m after 300 s. Budget and Monte Carlo agree on the shape; the Monte Carlo flattens out at 41–44 m from 120 s.
- In the realistic set calibration time does not help: multipath and range noise after handover do not depend on it. The Monte Carlo's 1.55 km for `ekf-calibrated` after 300 s of GPS comes from its worst runs: with 20 runs the per-second 95th percentile lies between the two worst (not checked which seeds).

**Minimum calibration time (`TBC`)**, the shortest time of good GPS before loss after which every longer time also meets the target:

| Scenario | Estimator | T1: ≤ 25 m for 300 s | Fallback: ≤ 50 m for 120 s |
| --- | --- | --- | --- |
| `uc01` | `ekf` | budget 45 s; Monte Carlo: not met with ≤ 300 s | 30 s (both) |
| `uc01` | `ekf-imu` | budget 30 s; **Monte Carlo: not met** (25.5–26.0 m with 120–300 s) | 30 s (both) |
| `uc01` | `ekf-calibrated` | not met with ≤ 300 s (budget 31 m, Monte Carlo 44 m at 300 s) | budget 60 s, Monte Carlo 120 s |
| `uc01-realistic` | all three | not met | not met |

So on the committed UC-01 scenario, 30 s of GPS is enough for the fallback with `ekf` and `ekf-imu`, and 120 s with `ekf-calibrated`. T1 is within reach only of `ekf-imu`: the budget says it meets T1 with 30 s of GPS; the 20-seed Monte Carlo misses by 0.5–1 m with 120–300 s and by 6–8 m with 30–60 s. Per the budget, the IMU removes the constant-velocity filter's lag in the turns and lets it average the range noise for longer. In the realistic set no filter meets either target with up to 300 s of GPS.

## Approximations

- After handover the tower clocks are held, not re-learned. The filter does refine them a little from the one redundant tower; the budget ignores that (conservative).
- Each fix stands alone, apart from the noise averaging. Right after handover the filter still carries the GPS position for a few seconds; the budget does not (pessimistic for the first 10–30 s).
- The filter's 99.9 % innovation gate is not modelled. Where the budget predicts km of clock error (`ekf`, `ekf-imu` in the realistic set) the gate may reject towers (not checked); the budget gets the size of the failure, not its shape.
- GPS position error during calibration, altitude and the lever arm are ignored. The network builder's shared clock is counted per tower (conservative: a common part would partly go into the clock column).
- Dropouts during calibration count as lost readings on average, not block by block.
- The IMU filter's averaging uses its own assumed noise, including its `gyro_extra` attitude noise (tuning, `nav/imu.py`), not the measured sensor.

## Reproduce

```bash
uv run python analysis/accuracy_budget.py --runs 20 --jobs 3   # the run on this page; --runs 50 for the full one
```

Writes `analysis/results/accuracy-budget/`: `budget_terms.png`, `budget_vs_monte_carlo.png`, `handover.png` and `summary.json` (every number on this page, with the commit). Seeds 0–19 here, paired across estimators and calibration times.
