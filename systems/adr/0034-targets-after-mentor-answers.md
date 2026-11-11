# ADR-0034: Targets after the mentors' answers to Q1–Q4

- **Status:** T1 Accepted (team, 2026-11-10); T4's jump target Accepted (owners, 2026-11-11); T3, T5 and T4's ramp targets Proposed
- **Date:** 2026-11-10, amended 2026-11-11 (the T4 jump target, decided by the owners: see *Amendment 2026-11-11*)
- **Deciders:** team
- **Traces to:** REQ-01, REQ-02, REQ-03, REQ-04, T1–T5 (`plan.md`), mentor answers of 2026-11-10 (`mentor-qa.md`)

## Context

T1–T5 were our proposals, `TBC` until the mentors answered Q1–Q3. On 2026-11-10 they answered (`mentor-qa.md`):

- Q1 (accuracy, drone): "≤ 50 m for ~2 min should be OK-ish". We must explain the calculations that lead to the accuracy.
- Q2 (integrity level): choosing it is part of the challenge; we should consider several ways of showing confidence.
- Q3 (timing): no number. Handover timing matters because it sets the accuracy and duration without GPS, and it must stay within the overall timing and accuracy budget.
- Q4 (attacks): begin with location jumps.

Our T1 (95 % ≤ 25 m for ≥ 300 s) is stricter than the mentors' figure on both accuracy and duration.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Mentors' figure as the requirement, ours as a stretch objective | Meets the customer's number first | Aims low: our sim already reaches the stricter goal on the base scenarios, and the 50 m figure equals the alert limit |
| B. Our stricter T1 as the requirement, the mentors' figure as the declared fallback | Aims for the better result; the fallback is the customer's own number, so dropping to it is defensible; the switch is recorded, not silent | If the realistic sets miss 25 m, results must say so and invoke the fallback |
| C. Only the mentors' figure | Simplest | Drops a stricter goal, and the 50 m alert limit becomes the accuracy too |

## Decision

Option B (team, 2026-11-10). We aim for our stricter goal; the mentors' figure is the fallback if the evidence shows we cannot meet it:

| Target | Requirement | Fallback |
| --- | --- | --- |
| T1, UC-01 drone | 95 % horizontal error ≤ 25 m for ≥ 300 s after GPS loss (ours, `TBC`) | ≤ 50 m for ≥ 120 s (mentors' "OK-ish" figure) |
| T2, UC-02 approach | Alert limit 556 m (RNP 0.3), unchanged (ours, `TBC`) | — |
| T3, UC-03 timing | ≤ 1.5 µs after 10 min, 1-σ bounding ≥ 68 % (ours, `TBC`); the accuracy budget states the calibration time it needs before GPS loss (handover, Q3) | — |
| T4, spoofing | Location jumps first (mentors): the jump target of *Amendment 2026-11-11*, from the jump study (#176); the ramp targets stay (ours, `TBC`) | — |
| T5, integrity | Ours, now ours to set (mentors): protection level bounds the error in ≥ 99.9 % of epochs, no hazardously misleading epochs on fault scenarios (`TBC`) | — |

### Amendment 2026-11-10: how the 95 % is taken (T1 and its fallback)

"95 % horizontal error ≤ X m for ≥ T s" is scored across Monte Carlo runs, per epoch:

1. Paired runs of one scenario, seeds declared, each losing GPS at the same point.
2. At each second t after GPS loss, take the 95th percentile of the horizontal error across the runs.
3. The target holds if that curve stays ≤ X for every second of 0 to T s: the worst second of the window decides.

So T1 reads "at any moment of the first 300 s, 95 % of flights are within 25 m" (likewise the fallback: 50 m, 120 s). This is the usual reading of a navigation accuracy figure (95 % probability at each epoch, held over the interval), and it is what the accuracy budget predicts, so the budget and the Monte Carlo compare like for like.

Not used: each run's own 95th percentile over time with every seed required to pass. It drops the worst 5 % of each run's coast, which is its end, where the error is largest, and requiring every seed makes the verdict depend on how many seeds are run.

Report the number of runs with every result: with 50 runs the per-second 95th percentile moves by a few metres from one second to the next.

### Amendment 2026-11-11: the T4 jump target (decided by the owners)

The jump study (#176, `analysis/jump_study.py`) proposed the jump target this ADR left `TBD`. The owners accepted it on 2026-11-11:

> A GNSS position jump of 20 m or more is flagged within 2 s in at least 95 % of runs, GNSS stays excluded for as long as the jump lasts, and no epoch is hazardously misleading (error over the 50 m alert limit while HPL is within it). False alarms: at most 1 per hour, shared with the ramp targets.

- **20 m** is `TBC`: it follows from the GNSS sigma (2.5 m, a placeholder). In the sim every jump of 20 m or more was flagged in 16 of 16 runs by the five estimators of #176, and in 20 of 20 in #191 except one `ekf` miss at 20 m on `uc01` (19 of 20).
- **2 s:** observed 1.1 s (the 1 s alarm hold plus one epoch).
- **Status (sim):** detection is met by all estimators. Exclusion and no hazardously misleading epoch are met by the opt-in `-guard` estimators (#191: 0 such epochs from 20 m to 500 km), not by the default ones. The jump guard stays opt-in (ADR-0038).

## Consequences

- T1 is reported against both numbers. Falling back to the mentors' figure is a recorded decision (an amendment here naming the evidence), never a silent change. "Explain the calculations" becomes a deliverable: an accuracy budget per error term with its source, growing with time since GPS loss, checked against Monte Carlo.
- Q2 means we show confidence several ways, not only an HPL: the 1-σ and 95 % error ellipse, the MHSS protection level against the alert limit, consistency (NEES/NIS), per-source trust and status, and time to alert. Each needs a figure or a panel element.
- Q3 adds the handover to the budget: how long GPS must be available before loss for the tower clocks and IMU biases to be learned well enough for T1.
- Q4 orders the attack work: location jumps first (`threat-model.md`).
- Reopen if the mentors give numbers for T3 or T5, or a crewed-aircraft figure for UC-02.
