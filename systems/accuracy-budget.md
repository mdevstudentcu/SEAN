# Accuracy budget: UC-01 after GPS loss

- **Status:** Draft, 2026-11-10
- **Traces to:** REQ-01, T1 in [`plan.md`](plan.md), UC-01. The mentors asked for this on 2026-11-10: "You will need to explain the calculations that lead to this accuracy", and "handover timing … must remain within the overall timing/accuracy budget".
- **Judged against:** T1 first, our goal: 95 % horizontal error ≤ 25 m for ≥ 300 s after GPS loss. Then the fallback, the mentors' figure: ≤ 50 m for ~2 min (taken as 120 s). Both `TBC` (ADR-0034, Proposed). A target holds only if the whole window is within it.
- **Script:** [`analysis/accuracy_budget.py`](../analysis/accuracy_budget.py) computes every number here. Tests: [`tests/test_accuracy_budget.py`](../tests/test_accuracy_budget.py).
- **Kind of evidence:** analysis and sim. Every tower and clock value is a `placeholder` in the *Sim validity* table of [`verification.md`](verification.md), so none of this is a real-world result. Numbers from commit `10956d6` (clean tree), seeds 0–49 (REQ-10).

## Result

Worst 95 % error over each target's window (sim, seeds 0–49, GPS good for 120 s first):

| Scenario | Estimator | T1: ≤ 25 m for 300 s | Fallback: ≤ 50 m for 120 s | Term that sets it |
| --- | --- | --- | --- | --- |
| `uc01` | `ekf` | **Missed by 2 m.** Budget 23 m, Monte Carlo 27 m | Met: 23 m, 27 m | Range noise after handover (20 m per reading): 19 m of the 21 m budget |
| `uc01` | `ekf-imu` | Borderline. Budget 15 m, Monte Carlo 25 m | Met: 14 m, 25 m | Range noise after handover: 13 m of 14 m |
| `uc01` | `ekf-calibrated` | **Missed.** Budget 53 m, Monte Carlo 40 m | Met: 32 m, 33 m | Range noise during calibration, left in the learned tower drifts and multiplied by t: 47 m alone at +300 s |
| `uc01-realistic` | `ekf-calibrated` | **Missed by 20–30×.** Budget 501 m, Monte Carlo 713 m | Missed: 324 m, 425 m | Multipath (50 m, 30 s, `TBC`): 215 m alone at +120 s, 360 m at +300 s. Four more terms are each over 25 m on their own |
| `uc01-realistic` | `ekf`, `ekf-imu` | **Missed by km.** Budget 7.2 km, Monte Carlo 4.2 / 10.5 km | Missed: 3.6 km; 2.5 / 4.1 km | Receiver clock: they do not model our clock in the tower ranges, so its 20 ppb drift (6 m/s) goes into the position: 1.1 km alone at +120 s |

- **T1 is not met anywhere in the Monte Carlo.** On the committed UC-01 scenario `ekf` and `ekf-imu` are within 0–7 m of it; the realistic set misses it by an order of magnitude or more.
- **The fallback is met on `uc01`** by all three estimators with 120 s of GPS first, and by none in the realistic set.
- **The IMU alone holds ≤ 25 m for 31 s and ≤ 50 m for 43 s** after GPS loss. It bridges tower dropouts; it cannot carry a 2 min outage.

## The two scenarios

| Name | What it is |
| --- | --- |
| `uc01` | [`uc01-drone-circuit.yaml`](../src/pnt/sim/scenarios/uc01-drone-circuit.yaml) as committed: 8 m/s circuit at 40 m, 6 synthetic towers 0.8–3 km away (new geometry each seed), 20 m range noise, tower clocks that only wander, our clock not in the ranges |
| `uc01-realistic` | The same circuit flown in the [`realistic`](../src/pnt/sim/scenarios/sets/realistic.yaml) environment: the 4 nearest real TELUS sites (0.6–1.7 km), 50 m range noise, 50 m multipath, towers heard 75 % of the time, told tower positions off by 100 m, tower clocks that drift, our own clock in every range |

Both are changed in two ways, so the budget and the Monte Carlo see the same thing:
- GPS is good for a *calibration time* (30–300 s), then lost for the rest of the run (300 s). UC-01's own outage is 120 s, too short for T1.
- The IMU is set to our measured MPU6050 (below). Main's sim still uses the datasheet values until `shrikar/feat/imu-measured` lands.

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

95 % radius of each term on its own with every tower heard (GPS good for 120 s first), then the total with dropouts. Terms are independent, so their variances add; their radii do not.

| Term | `uc01`, `ekf` | `uc01`, `ekf-calibrated` | `uc01-realistic`, `ekf-calibrated` | `uc01-realistic`, `ekf` |
| --- | --- | --- | --- | --- |
| Tower clocks | 4 / 6 m | 5 / 11 m | 8 / 17 m | 19 / 43 m |
| Multipath | — | — | **215 / 360 m** | 132 / 130 m |
| Told tower position | — | — | 43 / 58 m | 23 / 21 m |
| Receiver clock | — | — | 18 / 48 m | **1055 / 2769 m** |
| Noise during calibration | 3 / 3 m | **24 / 47 m** | 60 / 115 m | 12 / 12 m |
| Noise after handover | **19 / 19 m** | 19 / 20 m | 50 / 49 m | 50 / 49 m |
| Lag in turns | 5 / 2 m | 5 / 2 m | 19 / 10 m | 18 / 10 m |
| **Total, every tower heard** | 21 / 20 m | 31 / 51 m | 234 / 384 m | 1127 / 2853 m |
| **Total with dropouts** | 22 / 21 m | 32 / 53 m | 278 / 455 m | 3013 / 4610 m |

Why each estimator loses:
- `ekf` on `uc01`: almost all of it is the range noise itself. 20 m per reading through six towers' geometry is 7.6 m per axis after the filter averages it over 3 s. Calibration hardly matters: it learns only offsets, and the towers' clocks only wander (0.2 m/√s).
- `ekf-calibrated` on `uc01`: it also learns a drift per tower, and the synthetic towers have none. A drift fitted to 90 s of 20 m readings (the gate opens after 30 s) is off by ≈ 0.08 m/s (1 σ), 24 m per tower after 300 s. Learning a drift that is not there costs it T1.
- Realistic set: every term is larger. Multipath at 50 m with a 30 s memory is never averaged out, and goes stale within a minute of handover. With the filter unchanged, the multipath term alone would have to be ≈ 15× smaller (it scales with the multipath size) to fit 25 m at 300 s, and the range noise, told positions, receiver clock and calibration noise are each over 25 m too.

## Budget against Monte Carlo

The filters run on the same scenarios, seeds 0–49, GPS good for 120 s first. 95th percentile across seeds at each time since GPS loss (worst seed in brackets):

| Scenario | Estimator | | +30 s | +60 s | +120 s | +300 s |
| --- | --- | --- | --- | --- | --- | --- |
| `uc01` | `ekf` | budget | 23 | 21 | 22 | 21 |
| | | Monte Carlo | 18 (23) | 16 (30) | 22 (31) | 17 (20) |
| `uc01` | `ekf-calibrated` | budget | 27 | 27 | 32 | 53 |
| | | Monte Carlo | 21 (23) | 20 (35) | 28 (36) | 35 (40) |
| `uc01` | `ekf-imu` | budget | 14 | 14 | 14 | 15 |
| | | Monte Carlo | 19 (23) | 14 (28) | 18 (36) | 15 (17) |
| `uc01-realistic` | `ekf-calibrated` | budget | 199 | 246 | 278 | 455 |
| | | Monte Carlo | 190 (210) | 205 (308) | 425 (606) | 527 (962) |
| `uc01-realistic` | `ekf` | budget | 1171 | 1798 | 3013 | 4610 |
| | | Monte Carlo | 523 (582) | 1676 (1963) | 2498 (3469) | 4184 (5256) |
| `uc01-realistic` | `ekf-imu` | budget | 1147 | 1797 | 3024 | 4606 |
| | | Monte Carlo | 267 (356) | 1458 (1704) | 4115 (4846) | 10488 (19441) |

All values in metres. Figure: `analysis/results/accuracy-budget/budget_vs_monte_carlo.png`; terms: `budget_terms.png`.

Where they agree and where they do not:
- **`uc01`, `ekf`: within 30 %** at every time. The budget's worst over 300 s is 23 m against the Monte Carlo's 27 m: the Monte Carlo 95th percentile over 50 seeds moves by a few metres from second to second, and the budget is a smooth curve.
- **`uc01`, `ekf-calibrated`: the budget is high late** (53 m against 35 m at +300 s). The likely cause, not checked: the filter keeps refining its tower drifts from the redundant towers after handover, and the budget holds them (approximation 1). Its dependence on calibration time matches (below).
- **`uc01`, `ekf-imu`: the budget is low** (15 m against 25 m worst over 300 s). The budget lets the IMU filter average noise over 7 s. A likely cause, not checked: its weak heading on a multirotor (`nav/imu.py`) means it averages less.
- **`uc01-realistic`, `ekf-calibrated`: within a factor 1.6**, the budget low after +60 s (425 m against 278 m at +120 s). Not explained yet.
- **`uc01-realistic`, `ekf` and `ekf-imu`: the same size, a different shape.** The budget says the unmodelled 6 m/s clock drift drags the position by km; the Monte Carlo starts lower (the filter carries the GPS position for a while; the budget does not model its 99.9 % innovation gate) and ends as large or larger. Neither is usable.
- **Right after handover the budget is high** for every estimator: in the realistic set it starts at 90 m where the Monte Carlo starts at 3 m (figure). The filter still carries the GPS position for a few seconds; the budget's fix stands alone (approximation 2). By +30 s they agree (199 m against 190 m).

## Handover: how long GPS must be good first

What the filter learns before GPS is lost sets how fast its error grows after. GPS was lost after 30, 60, 120 or 300 s in the Monte Carlo (the budget also every 15 s in between). Worst 95 % error over each target's window, budget / Monte Carlo, in metres:

| Scenario | Estimator | Window | 30 s of GPS | 60 s | 120 s | 300 s |
| --- | --- | --- | --- | --- | --- | --- |
| `uc01` | `ekf` | T1, 300 s | 24 / 32 | 24 / 29 | 23 / 27 | 23 / 28 |
| | | fallback, 120 s | 24 / 27 | 23 / 29 | 23 / 27 | 22 / 28 |
| `uc01` | `ekf-imu` | T1, 300 s | 16 / 24 | 15 / 25 | 15 / 25 | 15 / 25 |
| | | fallback, 120 s | 15 / 23 | 14 / 24 | 14 / 25 | 14 / 21 |
| `uc01` | `ekf-calibrated` | T1, 300 s | 150 / 106 | 92 / 77 | 53 / 40 | 28 / 35 |
| | | fallback, 120 s | 67 / 72 | 46 / 72 | 32 / 33 | 25 / 35 |
| `uc01-realistic` | `ekf-calibrated` | T1, 300 s | 411 / 588 | 518 / 527 | 501 / 713 | 338 / 466 |
| | | fallback, 120 s | 297 / 406 | 308 / 286 | 324 / 425 | 269 / 421 |
| `uc01-realistic` | `ekf`, `ekf-imu` | either | km | km | km | km |

Figure: `analysis/results/accuracy-budget/handover.png`.

- **`ekf` and `ekf-imu` hardly depend on calibration time**: they learn only clock offsets, which settle within seconds of 1 Hz readings, and the synthetic towers do not drift.
- **`ekf-calibrated` depends on it strongly**: its drift error falls as T^−1.5 (step 1), so its error at +300 s falls from 150 m after 30 s of GPS to 28 m after 300 s. Budget and Monte Carlo agree on the shape; the Monte Carlo flattens out at 35 m by 120 s.
- In the realistic set calibration time does not help: multipath and range noise after handover do not depend on it.

**Minimum calibration time (`TBC`)**, the shortest time of good GPS before loss after which every longer time also meets the target:

| Scenario | Estimator | T1: ≤ 25 m for 300 s | Fallback: ≤ 50 m for 120 s |
| --- | --- | --- | --- |
| `uc01` | `ekf` | budget 30 s; Monte Carlo: not met with ≤ 300 s | 30 s (both) |
| `uc01` | `ekf-imu` | budget 30 s; Monte Carlo: not met (24–25 m, on the line) | 30 s (both) |
| `uc01` | `ekf-calibrated` | not met with ≤ 300 s (budget 28 m, Monte Carlo 35 m at 300 s) | budget 60 s, Monte Carlo 120 s |
| `uc01-realistic` | all three | not met | not met |

So on the committed UC-01 scenario, 30 s of GPS is enough for the fallback with `ekf` and `ekf-imu`, and 120 s with `ekf-calibrated`. T1 is not met by any filter with up to 300 s of GPS; `ekf-imu` is on its edge from 30 s.

## Approximations

- After handover the tower clocks are held, not re-learned. The filter does refine them a little from the one redundant tower; the budget ignores that (conservative).
- Each fix stands alone, apart from the noise averaging. Right after handover the filter still carries the GPS position for a few seconds; the budget does not (pessimistic for the first 10–30 s).
- The filter's 99.9 % innovation gate is not modelled. Where the budget predicts km of clock error (`ekf`, `ekf-imu` in the realistic set) the gate may reject towers (not checked); the budget gets the size of the failure, not its shape.
- GPS position error during calibration, altitude and the lever arm are ignored. The network builder's shared clock is counted per tower (conservative: a common part would partly go into the clock column).
- Dropouts during calibration count as lost readings on average, not block by block.
- The IMU filter's averaging uses its own assumed noise, including its `gyro_extra` attitude noise (tuning, `nav/imu.py`), not the measured sensor.

## Reproduce

```bash
uv run python analysis/accuracy_budget.py --runs 50 --jobs 6
```

Writes `analysis/results/accuracy-budget/`: `budget_terms.png`, `budget_vs_monte_carlo.png`, `handover.png` and `summary.json` (every number on this page, with the commit). Seeds 0–49 are paired across estimators and calibration times.
