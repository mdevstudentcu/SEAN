# ADR-0051: Heading at GPS loss: S-turns before the cut and a magnetometer, opt-in in the sim

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** owners (pending). The `Measurement` ICD change needs both software owners (ICD-measurement)
- **Traces to:** REQ-01, REQ-06, REQ-09, ADR-0014, ADR-0034, issue #276; owners' REQ-06 call (#279, 2026-11-11): velocity and heading aids are allowed in the sim as opt-in and labelled, radio stays primary in the defaults and claims

## Context

The research report (`reports/sources-research-20261111.md`, 7.2, 7.4, 11.2, 17.4, 18.3) ranks heading at GPS loss second among what limits accuracy: an IMU filter carries the heading it had when GPS went, and on a multirotor heading is observable only under horizontal acceleration. The accuracy budget assumes 3° there (`TBC`, `nav/imu.py`'s floor). #276 asks for heading at loss to be an output of the GPS-good phase, for manoeuvres before the cut, and for a magnetometer model with a per-flight bias.

What `analysis/heading_at_loss.py` measured on the challenge drone leg (`challenge-drone-outage`, sim, every value `TBC`; numbers in `analysis/results/heading-276/summary.md`, commit and seeds there):

- **The leg gives heading little to work with.** Its first 60 s (GPS good) has 0.29 m/s² RMS horizontal acceleration, peak 0.50 (report 7.4, check 2: not enough). `ekf-imu`'s heading at loss: median 38°, p95 145° off, against its own σ of 18°.
- **The 3° floor is not what binds** (check 1). It is applied whatever the IMU grade, but only as the floor of the heading σ given at alignment; on the S-turn path the alignment windows gave 36–102° (seed 0, payload IMU; 33–82° tactical), so the floor never acts, and a 0.3° floor gave identical runs. What binds is that the default accepts any alignment up to 180°: from the first S-turn window (σ 102°, 164° off, seed 0) the filter did not recover: it settled 162° off with a 4° σ and gated GNSS out (77 m off at the loss with GPS on).
- **S-turns** (2 m/s², 18 s over 1 m/s²) help only with an alignment limit (60°, opt-in): heading at loss 1.8° median, 5.1° p95; without the limit the median is 2.8° but the p95 134°, because some runs align on the first window.
- **Magnetometer** (`ekf-imu-mag`): 1.6° median, 6.0° p95 on the plain path, 1.3° / 3.4° with S-turns; the bias is learned to a 1.4–1.7° median error while GPS is good.
- **None of this meets T1 or the fallback on this leg.** On the payload's MPU6050 with no LTE, the best heading still leaves 250–270 m at 60 s and 0.7–0.8 km at 120 s (p95): the other inertial terms dominate. Heading at loss still orders the runs (Spearman ρ 0.44–0.79 against the 120 s error for the default filter).
- **LTE makes this leg worse, not better:** every filter is 3–20 km off at 300 s with LTE and 2.8–5.5 km without it. So in the REQ-06 ablation removing LTE *improves* the result and removing the magnetometer costs more: REQ-06 is not met on this leg (reported as it came out). The leg's LTE is already known to be the problem (challenge baseline: `ekf-imu` 24 km at 300 s; ADR-0030's open question on the front end's 2 m told σ against 50 m noise and multipath).
- **Tactical IMU** (check 4): with S-turns, the 60° limit and a tactical filter spec, 54 m at 60 s and 364 m at 300 s (p95, no LTE), not the 1–3 m and 50–110 m the report derives. With the MPU6050 spec in the filter it is 210 m at 60 s (check 3: the filter's noise and extra-noise terms must be switched with the IMU; `ImuSpec` is the filter's, never taken from the sim). Why the tactical run is still 20 times the derived figure is not established here (60 s of GPS may not calibrate the 0.5 mg accelerometer bias, which alone gives about 9 m at 60 s).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Nothing: keep the 3° assumption | No change | Heading at loss is assumed, not measured; on this leg it is far worse than 3° |
| B. S-turns before the cut, opt-in in the trajectory (`manoeuvres`) | No new sensor; measures what motion buys | Needs the vehicle to fly them; the default alignment can accept a window too poor for the filter to recover from |
| C. A magnetometer `heading` record (new `mag` source and `heading` kind), opt-in in the sim (`sources: mag`) and the filter (`ekf-imu-mag`), with a per-flight bias state | Heading in hover and on straight legs; the payload's IMU is a 6-axis part, so a 9-axis part or an autopilot's compass would supply it | Changes the `Measurement` ICD; the bias model is weak evidence (report 17.4); not on the payload |
| D. Change `ekf-imu`'s default alignment limit (180°) | Fixes the bad alignments for every run | Changes default outputs; the limit is not tuned |

## Decision

Proposed: B and C, both opt-in and labelled as sim-only, and D not taken: the 60° alignment limit stays an option the study passes (`imu: {max_yaw_sigma_deg: 60}`), not a default, until the owners decide it with a held-out tuning.

- `trajectory.py` `manoeuvres: {start_s, end_s, accel_mps2, period_s}`: a sideways weave whose side force alternates every half period, about `accel_mps2` at its peak (report 7.4: 1–3 m/s² for 5–10 s). The study uses 2 m/s², a 15 s period, 5–55 s (`TBC`). The 60° alignment limit is above the 33–47° the S-turn windows gave and below the 82–102° of the first window (seed 0, not a tuning).
- ICD-measurement: source `mag` (simulated; the payload has none, ADR-0014) and kind `heading`, (ψ,) of the body x axis, clockwise from true north, declination already applied, rad.
- `sim/sensors.py` `MAG`: a per-flight bias drawn once from a Student-t (4 degrees of freedom, scale 2.5°: heavy-ish tails, report 17.4 and 17.10) plus 1° white noise, all `TBC`; its own random stream, so no other record changes.
- `ekf-imu-mag`: `ekf-imu` with `magnetometer={}`: once the IMU is aligned, `heading` records update the attitude, with one constant bias state (prior 3°, `TBC`, Gaussian where the sim's is not). Every other filter ignores `heading` records.
- `mag` is not classified under ADR-0024 here: as an unclassified source it counts as GNSS-derived, the conservative default, until the owners classify it.

## Consequences

- Heading at loss is now an output (`analysis/heading_at_loss.py`) and the report's four checks have answers (*Context*).
- REQ-06: on this leg the ablation ranks as *Context* says; that is reported as it came out, and no default or claim changes.
- An `icd`-labelled PR: Mo's approval is needed before merge.
- Reopen if: a real magnetometer is flown (its bias replaces the placeholder); the alignment limit is tuned on held-out seeds; the challenge drone leg's LTE stops making the IMU filter worse than coasting.
