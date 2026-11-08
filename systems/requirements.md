# Requirements

## Mission

Keep a crewed or uncrewed aircraft's **position and time** usable when GPS is degraded, jammed, spoofed or unavailable, using **communication signals of opportunity as the primary aid**, and give operators **numerical confidence** they can act on as conditions change.

Source: Honeywell kickoff deck, Challenge 2 (overview, instructions, deliverables D1–D3).

## Requirements

Targets marked `TBD` are open questions for our Honeywell mentors (see the end of this file).

| ID | Requirement | Success measure | Verif. | Status |
| --- | --- | --- | --- | --- |
| REQ-01 | **Navigation continuity.** After GPS is lost, the system keeps providing horizontal position. | Horizontal error ≤ `TBD` m (95th percentile) for ≥ `TBD` s after GPS loss | A, T | Draft |
| REQ-02 | **Position confidence.** Every position estimate carries a horizontal protection level (HPL). | HPL bounds the true error in ≥ `TBD` % of epochs; shown as a Stanford plot | A, T | Draft |
| REQ-03 | **Timing continuity and confidence.** The system keeps time after GPS loss and reports its uncertainty. | Time error ≤ `TBD` µs after `TBD` min without GPS; reported 1-σ bounds it in ≥ `TBD` % of epochs | T | Draft |
| REQ-04 | **Spoofing and fault detection.** The system detects GPS that disagrees with independent sources and stops trusting it. | Detects a spoof drift of `TBD` m/s within `TBD` s; false alarms ≤ `TBD` per hour | A, T | Draft |
| REQ-05 | **Real-time monitoring.** An operator display shows position, HPL, timing uncertainty and per-source status live. | Update rate ≥ `TBC` 1 Hz; end-to-end latency ≤ `TBD` s | D, T | Draft |
| REQ-06 | **Signals of opportunity are primary.** Communication signals carry the solution; IMU and others assist. | Ablation: removing SoOP degrades REQ-01 by more than removing any single non-SoOP aid | A | Draft |
| REQ-07 | **Receive-only.** The payload makes no intentional emissions beyond licence-exempt control, telemetry and Wi-Fi links. | No transmit path exists in hardware or code | I | Draft |
| REQ-08 | **Privacy.** No communication content is decoded or stored; device identifiers are hashed at capture. | Code inspection + a session audit | I | Draft |
| REQ-09 | **Platform-agnostic payload.** The payload works on the drone, handheld and in a vehicle without change. | Same session format and pipeline on all three | D | Draft |
| REQ-10 | **Reproducibility.** Every reported result can be regenerated. | From a committed scenario, or a named session + commit hash | I | Draft |

## Open questions for the mentors

- REQ-01: what horizontal accuracy and outage duration would matter for a Honeywell product (crewed vs UAV)?
- REQ-02: which integrity risk / confidence level should the protection level target?
- REQ-03: what timing holdover target matters (µs after how many minutes)?
- REQ-04: is a simulated spoofing scenario acceptable as evidence, or do they want recorded data (e.g. public datasets)?
- Is simulation acceptable for the LEO (Iridium/Starlink) layer?
