# Accuracy budget: UC-01 after GPS loss

- **Status:** Draft, 2026-11-10
- **Traces to:** REQ-01, T1 in [`plan.md`](plan.md), UC-01. The mentors asked for this on 2026-11-10: "You will need to explain the calculations that lead to this accuracy", and "handover timing … must remain within the overall timing/accuracy budget".
- **Judged against:** T1 first, our goal: 95 % horizontal error ≤ 25 m for ≥ 300 s after GPS loss. Then the fallback, the mentors' figure: ≤ 50 m for about 2 min. Both `TBC` (ADR-0034, Proposed). A target holds only if the whole window is within it.
- **Script:** [`analysis/accuracy_budget.py`](../analysis/accuracy_budget.py) computes every number here. Tests: [`tests/test_accuracy_budget.py`](../tests/test_accuracy_budget.py).
- **Kind of evidence:** analysis and sim. Every tower and clock value is a `placeholder` in the *Sim validity* table of [`verification.md`](verification.md), so none of this is a real-world result.

<!-- budget:headline -->

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
| Tower clock offset and drift | offset error + drift error × t + wander × √t | The filter fits each clock as offset + drift. From N readings of noise σ over T seconds, the drift is known to σ √(12 / (N (N² − 1))), about σ √12 / T^1.5 at 1 Hz. A short calibration leaves a large drift error, and it is multiplied by t |
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

<!-- budget:imu -->

## The values and where they come from

<!-- budget:terms -->

## Budget against Monte Carlo

<!-- budget:compare -->

## Handover: how long GPS must be good first

<!-- budget:handover -->

## Approximations

- After handover the tower clocks are held, not re-learned. The filter does refine them a little from the one redundant tower; the budget ignores that (conservative).
- Each fix stands alone, apart from the noise averaging. Right after handover the filter still carries the GPS position for a few seconds; the budget does not (pessimistic for the first 10–30 s).
- The filter's 99.9 % innovation gate is not modelled. Where the budget predicts km of clock error (`ekf`, `ekf-imu` in the realistic set) the gate will reject towers; the budget gets the size of the failure, not its shape.
- GPS position error during calibration, altitude and the lever arm are ignored. The network builder's shared clock is counted per tower (conservative: a common part would partly go into the clock column).
- Dropouts during calibration count as lost readings on average, not block by block.
- The IMU filter's averaging uses its own assumed noise, including its `gyro_extra` attitude noise (tuning, `nav/imu.py`), not the measured sensor.

## Reproduce

```bash
uv run python analysis/accuracy_budget.py --runs 50 --jobs 6
```

Writes `analysis/results/accuracy-budget/`: `budget_terms.png`, `budget_vs_monte_carlo.png`, `handover.png` and `summary.json` (every number on this page, with the commit). Seeds 0–49 are paired across estimators and calibration times.
