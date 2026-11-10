# Requirements

## Mission

Keep a crewed or uncrewed aircraft's **position and time** usable when GPS is degraded, jammed, spoofed or unavailable, using **communication signals of opportunity as the primary aid**, and give operators **numerical confidence** they can act on as conditions change.

Source: Honeywell kickoff deck, Challenge 2 (overview, instructions, deliverables D1–D3).

## Requirements

Targets marked `TBD` are open questions for our Honeywell mentors (see the end of this file). Values marked `TBC` are our proposals (T1–T5 in [`plan.md`](plan.md)); the mentors answered Q1–Q4 on 2026-11-10 and ADR-0034 (Proposed) folds their answers in. Use cases are defined in [`use-cases.md`](use-cases.md); mentor answers so far are in [`mentor-qa.md`](mentor-qa.md).

| ID | Requirement | Success measure | Verif. | Use cases | Status |
| --- | --- | --- | --- | --- | --- |
| REQ-01 | **Navigation continuity.** After GPS is lost, the system keeps providing horizontal position. Horizontal error (95th percentile) ≤ 50 m for ≥ 120 s after GPS loss (UC-01 threshold, mentors 2026-11-10), objective ≤ 25 m for ≥ 300 s (`TBC`, ADR-0034); within RNP 0.3 (556 m) in the terminal phase (UC-02) (`TBC`) | A, T | UC-01, UC-02 | Draft |
| REQ-02 | **Position confidence.** Every position estimate carries a horizontal protection level (HPL). | HPL bounds the true error in ≥ 99.9 % of epochs, with no hazardously misleading epochs on the fault scenarios; alert limit 50 m (UC-01), 556 m (UC-02) (`TBC`); shown as a Stanford plot | A, T | UC-01, UC-02 | Draft |
| REQ-03 | **Timing continuity and confidence.** The system keeps time after GPS loss and reports its uncertainty. | Time error ≤ 1.5 µs after 10 min without GPS; reported 1-σ bounds it in ≥ 68 % of epochs (`TBC`) | T | UC-03 | Draft |
| REQ-04 | **Spoofing and fault detection.** The system detects GPS that disagrees with independent sources and stops trusting it. | Detects a 2 m/s position spoof ramp within 30 s and a 50 ns/s time ramp within 60 s; false alarms ≤ 1 per hour on nominal runs (`TBC`) | A, T | all | Draft |
| REQ-05 | **Real-time monitoring.** An operator display shows position, HPL, timing uncertainty and per-source status live. | Update rate ≥ `TBC` 1 Hz; end-to-end latency ≤ `TBD` s | D, T | all | Draft |
| REQ-06 | **Signals of opportunity are primary.** Communication signals carry the solution; IMU and others assist. | Ablation: removing SoOP degrades REQ-01 by more than removing any single non-SoOP aid | A | all | Draft |
| REQ-07 | **Receive-only.** The payload makes no intentional emissions beyond licence-exempt control, telemetry and Wi-Fi links. | No transmit path exists in hardware or code | I | all | Draft |
| REQ-08 | **Privacy.** No communication content is decoded or stored; device identifiers are hashed at capture. | Code inspection + a session audit | I | all | Draft |
| REQ-09 | **Platform-agnostic payload.** The payload works on the drone, handheld and in a vehicle without change. | Same session format and pipeline on all three | D | all | Draft |
| REQ-10 | **Reproducibility.** Every reported result can be regenerated. | From a committed scenario, or a named session + commit hash | I | all | Draft |

## Open questions for the mentors

- ~~REQ-01: what horizontal accuracy and outage duration would matter for a Honeywell product (crewed vs UAV)?~~ Drone: ≤ 50 m for ~2 min, with the calculations explained (2026-11-10). No crewed figure yet
- ~~REQ-02: which integrity risk / confidence level should the protection level target?~~ Ours to determine; show confidence several ways (2026-11-10)
- ~~REQ-03: what timing holdover target matters (µs after how many minutes)?~~ No number; handover timing must stay within the timing and accuracy budget (2026-11-10)
- ~~Which attacks first?~~ Location jumps (2026-11-10)
- ~~REQ-04: is simulated spoofing acceptable evidence?~~ Yes, if the architecture shows how the sim aligns to reality (2026-11-08).
- ~~Is simulation acceptable for the LEO layer?~~ Yes, Iridium network simulation is acceptable (2026-11-08).
