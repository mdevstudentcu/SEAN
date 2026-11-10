# ADR-0034: Targets after the mentors' answers to Q1–Q4

- **Status:** Proposed
- **Date:** 2026-11-10
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
| A. Mentors' figure as the threshold (must meet), ours as the objective (aim for) | Meets the customer's number first; keeps the stricter goal visible; the usual threshold/objective pairing in aerospace requirements | Two numbers per target to report |
| B. Keep only our stricter T1 | One number | Fails "the requirement" where the customer's figure is met; hides that we meet what they asked |
| C. Only the mentors' figure | Simplest | Drops a stricter goal our sim already reaches, and the 50 m alert limit becomes the accuracy too |

## Decision

Option A. Each target names the mentors' answer where there is one:

| Target | Threshold (must) | Objective (aim) |
| --- | --- | --- |
| T1, UC-01 drone | 95 % horizontal error ≤ 50 m for ≥ 120 s after GPS loss (mentors) | ≤ 25 m for ≥ 300 s (ours, `TBC`) |
| T2, UC-02 approach | Alert limit 556 m (RNP 0.3), unchanged (ours, `TBC`) | — |
| T3, UC-03 timing | ≤ 1.5 µs after 10 min, 1-σ bounding ≥ 68 % (ours, `TBC`); the accuracy budget states the calibration time it needs before GPS loss (handover, Q3) | — |
| T4, spoofing | Location jumps first (mentors): a jump target from the jump study, `TBD`; the ramp targets stay (ours, `TBC`) | — |
| T5, integrity | Ours, now ours to set (mentors): protection level bounds the error in ≥ 99.9 % of epochs, no hazardously misleading epochs on fault scenarios (`TBC`) | — |

## Consequences

- T1 is reported against both numbers. "Explain the calculations" becomes a deliverable: an accuracy budget per error term with its source, growing with time since GPS loss, checked against Monte Carlo.
- Q2 means we show confidence several ways, not only an HPL: the 1-σ and 95 % error ellipse, the MHSS protection level against the alert limit, consistency (NEES/NIS), per-source trust and status, and time to alert. Each needs a figure or a panel element.
- Q3 adds the handover to the budget: how long GPS must be available before loss for the tower clocks and IMU biases to be learned well enough for T1.
- Q4 orders the attack work: location jumps first (`threat-model.md`).
- Reopen if the mentors give numbers for T3 or T5, or a crewed-aircraft figure for UC-02.
