# Use cases

Requirements trace to these (mentor guidance, `mentor-qa.md` Q7). Each names who relies on PNT, what GPS failure looks like for them, and what they need from us.

| ID | Use case | GPS threat in practice | What they need from us | Requirements |
| --- | --- | --- | --- | --- |
| UC-01 | **Uncrewed aircraft on an urban corridor** (inspection or delivery drone over Ottawa, below 120 m) | Local jamming from in-vehicle jammers on nearby roads; carry-off spoofing aimed at drones; urban signal blockage | Position that stays within the corridor through a GPS outage, an alert *before* it leaves, and detection of spoofed GPS | REQ-01, REQ-02, REQ-04, REQ-05 |
| UC-02 | **Crewed aircraft in the terminal area** (approach into YOW) | Regional jamming that also degrades other aircraft's ADS-B position reports; spoofing reported in conflict-adjacent airspace | Continuity of position with a protection level the crew can act on until a non-GNSS approach or landing; clear integrity status | REQ-01, REQ-02, REQ-04, REQ-05 |
| UC-03 | **Timing user** (e.g. a satcom or comms terminal disciplined to GPS time) | Jamming causes holdover; time spoofing shifts the clock without moving the position | Time that stays within a bound after GPS loss, an honest uncertainty, and detection of time spoofing | REQ-03, REQ-04, REQ-05 |

All three share REQ-06 to REQ-10 (SoOP primary, receive-only, privacy, platform-agnostic payload, reproducibility).

Targets for each (accuracy, integrity level, timing bound) are in `requirements.md`; the mentors answered Q1–Q4 on 2026-11-10 (`mentor-qa.md`, ADR-0034): the drone keeps our stricter T1 (95 % horizontal error ≤ 25 m for ≥ 300 s, `TBC`; Accepted in ADR-0034), with the mentors' ≤ 50 m for ≥ 120 s as the declared fallback; the integrity level is ours to set, and location jumps come first. The prioritized attack list per use case is in [`threat-model.md`](threat-model.md).
