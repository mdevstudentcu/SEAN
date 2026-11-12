# ADR-0053: Calibrate the IMU biases from a still stretch before alignment

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners)
- **Traces to:** REQ-01, REQ-02, ADR-0014, ADR-0015, #12, #119, #214

## Context

`ImuSpec` (`nav/imu.py`) and the sim's `sensors.MPU6050` both assume the biases left *after a start-up calibration*: 0.05 deg/s gyro and 5 mg accelerometer, 1-sigma. Nothing in the pipeline runs that calibration. The sim's own notes give the raw part as ±20 deg/s zero-rate offset and ±50 to 80 mg zero-g offset.

The real hand-held walk `20261111-1806-walk-lte` (#214) shows what that costs. Its first minute is still (the filter's speed 0.01 to 0.08 m/s):

| | Measured while still (2 to 55 s) | Filter assumed (1-sigma) |
|---|---|---|
| Gyro x | −3.95 deg/s | 0.05 deg/s |
| Gyro y, z | +0.15, +1.08 deg/s | 0.05 deg/s |
| Specific force magnitude | 8.44 m/s² (−1.37 m/s², −140 mg, along the vertical) | 5 mg |
| Specific force direction | body +z up within 3 deg | (alignment finds it) |

- The gyro x mean stays at −3.4 to −4.0 deg/s in every still stop (minutes 4, 6 and 11 to 12) and in every 20 s window of the walk, so it is a bias, not motion. The vertical accelerometer offset drifts from −1.37 to −1.0 m/s² over 12 minutes (the board warming).
- Against the GPS course: the gyro's yaw (rate about the measured vertical, integrated) over the four walking stretches of 130 to 250 s is off by 208 to 453 deg raw, and by 41 to 82 deg with the still-period bias removed. Its sign agrees with the course on every turn over 45 deg (slope 0.83).
- Units, scale and axes are as the ICD says (m/s², rad/s, sensor axes; ±8 g at 4096 LSB/g, ±500 deg/s at 65.5 LSB/(deg/s)). Samples are monotonic at 97.8 Hz, 1 % of steps 20 ms (a missed read), two gaps over 50 ms, all inside `max_hold_s`. Gravity's sign in the mechanisation is right: a still sample gives zero acceleration. "Antennas facing down" does not matter: the alignment fits the whole body-to-ENU rotation (Wahba), so no mounting rotation needs configuring.

With the bias uncalibrated, the bias turns the integrated specific force by 4 deg/s, the alignment takes that turning for heading and aligns at 175 s, and the IMU then drags the filter off while GPS is still on: its gate shuts GNSS out on 83 % of epochs and the error before any cut reaches p95 270 km (`ekf-imu`, main with #241).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A: calibrate in the filter from a still stretch the filter itself sees (GNSS steering, position within a radius) | needs no new procedure or file; runs on replay and live alike; recalibrates at every later stop | needs a still stretch before alignment; a receiver turning in place while "still" biases the gyro estimate |
| B: a calibration step on the payload at start-up, written to the session's meta | the biases travel with the recording | a new procedure and ICD field (`icd` label); an old session has none |
| C: widen the bias priors to the raw part's | honest with no procedure | the alignment then never accepts heading (its gyro-drift allowance swamps any spread), so `ekf-imu` is `ekf` everywhere, sim included |

## Decision (Proposed)

**A.** While GNSS steers and the filter's horizontal position stays within `still_radius_m` (3 m, TBC) of where the stretch began, the receiver counts as still once that has lasted `still_guard_s` (5 s, TBC: anything faster than 0.6 m/s never counts). The stretch's samples are summed in 1 s blocks, less the last `still_guard_s` (a receiver about to move may already be turning). Once the rest lasts `still_min_s` (20 s, TBC), it is the calibration, updated as the stretch goes on, and a later stretch replaces it:

- gyro bias: the mean rate;
- accelerometer bias: the mean specific force's excess over gravity, along it (the other two axes look like tilt when still and are left to the alignment);
- each 1-sigma: the standard error of the 1 s means, at least `ImuSpec`'s. A hand-held receiver sways, and sway does not average down as white noise.

At alignment the bias states start from the calibration with those 1-sigma, the alignment window integrates bias-corrected samples, and its gyro-drift allowance uses the calibration's largest gyro 1-sigma. No alignment window runs while the receiver is still: heading cannot show without motion, and an uncalibrated bias would pass for it.

On (`still_calibration=True`) by default: it acts only on a stretch the filter sees as still before alignment, so a moving sim run never meets it.

## What it bought on the walk

`20261111-1806-walk-lte`, no LTE, `ekf-imu`, three GPS cuts while walking, median (worst) horizontal error after the cut; replay at this ADR's commit on main with #241. Script `analysis/walk_gps_cut.py` (#214).

| | 60 s | 120 s | 300 s | Before the cut: p95 | GNSS excluded before | HPL ≥ error |
|---|---|---|---|---|---|---|
| main | 364,781 (438,601) | 438,601 (511,596) | 683,705 (776,150) | 270,258 m | 83 % | 100 % |
| this ADR | 22.8 (89.6) | 107 (223) | 503 (557) | 1.2 m | 0 % | 100 % |
| no LTE, `ekf` (constant velocity) | 22.8 (89.6) | 107 (223) | 503 (557) | 1.2 m | 0 % | 100 % |

The calibration fires at 38 s and again at each stop. Its gyro z 1-sigma (0.5 to 2.9 deg/s, the hand turning a little while standing) keeps the alignment refusing every window of the walk, so `ekf-imu` holds the constant-velocity model and equals `ekf`: an honest result. With the old 0.05 deg/s prior and the biases removed by hand, it aligned at 699 s and reached 150 to 212 km at 300 s, with HPL ≥ error on 20 to 70 % of epochs: the residual bias (about 0.3 deg/s about the vertical, from the course check) is far above what the prior allows.

## Consequences

- A session that starts moving gets no calibration and keeps today's assumption that one was done elsewhere. Before a real flight or walk the payload must sit still for at least 25 s with GPS (procedure, TBC). Whether `ekf-imu` should refuse to align on a real IMU without a calibration is open for the owners.
- The bias random walks in `ImuSpec` (100 µg and 20 deg/h over 100 s) are far below this board's warm-up drift (0.37 m/s² vertical over 12 minutes). They stay TBC until an Allan variance over a warm-up (`analysis/imu_allan.py`).
- A hand-held MPU6050 cannot give heading from motion here; pedestrian dead reckoning (steps and heading) would be a new approach and a new ADR.
- Reopen if a still stretch with a slow turn (a drone yawing in hover) is common: the gyro mean then carries the turn rate.
- The sim is unchanged: every registered estimator hashes the same as on main on the challenge legs, `gps-outage`, `realistic-long-outage`, `meaconing`, `spoof-jump` and `spoof-ramp`, seeds 0 and 1 (PR evidence).
