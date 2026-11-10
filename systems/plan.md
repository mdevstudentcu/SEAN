# Build plan

- **Status:** Draft, 2026-11-09
- **Scope:** what we build and pitch ([ADR-0021](adr/0021-what-we-build-and-pitch.md)), step by step, mapped to issues. This doesn't override anything else in `systems/`.
- **Judging:** Thu 2026-11-12. Milestones: 1 Sim foundation (Sun–Mon) · 2 Real-data path (Mon–Tue) · 3 Show it (Tue–Wed) · 4 Deliverables (Wed–Thu).

## The story

Learn the signals of opportunity while GPS is trusted, then use them to keep position and time, catch GPS lying, and catch them lying. Towers, network builders and GNSS-dependent sources are treated as things that can fail.

## Steps

| Step | Issue | Milestone | Depends on |
| --- | --- | --- | --- |
| Build plan, pitch scope, targets (this file) | #74 | 1 | — |
| ADRs for the integrity design (0022–0026) | #75 | 1 | — |
| ICD: receiver ID (two receivers per session) | #76 | 1 | — |
| P1 calibrated tower clocks, site and builder grouping | #77 | 1 | #75 |
| P5 time protection level and timing results | #78 | 1 | — |
| P0 report card: time-to-alert, hazardous counts, resilience level | #79 | 1 | — |
| Sim: ground reference station as a second receiver | #80 | 1 | #76 |
| Order and assemble the ground reference station | #84 | 2 | — |
| Ground station setup, survey and streaming | #85 | 2 | #84, #76 |
| Zero-baseline test | #86 | 2 | #85 |
| Tower identity: scan list and cell-to-site table | #87 | 2 | #75 |
| Pi 4B day-1 test (ADR-0018) | #88 | 2 | — |
| Ground-link security | #89 | 2 | #75 |
| P4 base/rover differencing with collaborative integrity | #81 | 3 | #77, #80 |
| P2 solution-separation integrity with dependency-aware faults | #82 | 3 | #77, #75 |
| P3 calibrated clocks as a time-spoof and meaconing detector | #83 | 3 | #77 |
| P10 navigation-health panel | #90 | 3 | #25 |
| P6 ADS-B interference early warning | #91 | 3 | #22 |
| P7 pre-flight integrity prediction | #92 | 3 | — |
| P8 hostile emitter as a low-trust beacon (sim) | #93 | 3 | #75 |
| P9 GNSS-independent aviation layer | #94 | 3 | — |
| P11 residual map learned while GPS is trusted | #95 | 3 | — |
| P12 drone as a mobile reference station (sim) | #96 | 3 | #81 |
| P13 Starlink Doppler layer (sim) | #97 | 3 | — |
| Check novelty claims against the full papers | #98 | 4 | — |
| Research summary in the repo | #99 | 4 | — |
| D1 architecture, D3 roadmap, 5-min deck, rehearsal | #28 | 4 | most of the above |

Existing issues that still apply:
- **Front ends:** LTE (#21, #23), ADS-B/VOR/Wi-Fi/GNSS (#22)
- **Payload:** Pi setup (#17), recorder (#19)
- **Dashboard:** v0 (#25)
- **Analysis:** results (#27), threat model (#29), sim-to-real (#30)
- **Estimator:** stage 2, the IMU (#12)

## Demo

- **Live, indoors:**
  - real GPS loss when the payload moves indoors
  - time held through the GPS loss, with its protection level
  - a software-injected spoof setting off the alarm
  - the health panel
- **Replay of outdoor captures (real signals):**
  - tower ranges with the ground station
  - attacks injected into the recordings
  - sim-to-real calibration (ADR-0015)
- **Sim at scale:**
  - Monte Carlo statistics
  - the YOW approach
  - every attack
  - LEO layers
  - worst cases

## Proposed targets

These are in [`requirements.md`](requirements.md). The mentors answered Q1–Q4 on 2026-11-10 ([`mentor-qa.md`](mentor-qa.md)); ADR-0034 (Proposed) adds their figures as thresholds:

| Target | Use case | Value |
| --- | --- | --- |
| T1 | UC-01 drone | Threshold (mentors): 95 % horizontal error ≤ 50 m for ≥ 120 s after GPS loss, with the accuracy budget explained. Objective: ≤ 25 m for ≥ 300 s. Alert limit 50 m |
| T2 | UC-02 approach | Horizontal alert limit 556 m (RNP 0.3) in the terminal phase |
| T3 | UC-03 timing | Time error ≤ 1.5 µs after 10 min without GPS; reported 1-σ bounds it in ≥ 68 % of epochs |
| T4 | Spoofing | Location jumps first (mentors): jump target `TBD` from a jump study. 2 m/s position ramp detected within 30 s; 50 ns/s time ramp within 60 s; ≤ 1 false alarm per hour |
| T5 | Integrity | Ours to set (mentors): protection level bounds the error in ≥ 99.9 % of epochs; no hazardously misleading epochs on fault scenarios; confidence also shown as the error ellipse, consistency (NEES/NIS), per-source trust and time to alert |
