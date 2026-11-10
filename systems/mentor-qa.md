# Mentor Q&A

Answers from our Honeywell mentors, kept so decisions trace back to them. Newest first.

## 2026-11-10: answers to Q1–Q4

Relayed by the team. The answers are numbered #1–#4; we read them as our Q1–Q3 (still open from 2026-11-08) and the attack-order part of Q4 (`TBC`: confirm the numbering with the mentors).

| Q | Our question | Answer | What it changes |
| --- | --- | --- | --- |
| 1 | What horizontal accuracy and outage duration would matter (REQ-01)? | "For the drone, ≤ 50 m for ~2 min should be OK-ish. You will need to explain the calculations [that] lead to this accuracy." | We keep our stricter T1 and hold the mentors' figure as the fallback (ADR-0034); an accuracy budget per error term becomes a deliverable |
| 2 | Which integrity risk or confidence level should the protection level target (REQ-02)? | "Determining this is part of the challenge. You should consider different methods for indicating a level of confidence." | T5 is ours to set; we show confidence several ways, not only the HPL (ADR-0034) |
| 3 | What timing holdover target matters (REQ-03)? | "Handover timing matters because it will affect the accuracy and duration without GPS, and it must remain within the overall timing/accuracy budget." | No number: T3 stays ours. The budget includes the handover: how long GPS must be available before loss (ADR-0034) |
| 4 | Which attacks? | "I would begin with location jumps." | Location jumps first in the attack work and `threat-model.md`; a jump target for T4, `TBD` from a jump study |

## 2026-11-08: answers to our seven questions (Teams)

From the Honeywell mentor (SATCOM). Q1–Q3 (accuracy, integrity level, timing target) were left open here; they are answered above (2026-11-10).

| Q | Our question | Answer | What it changes |
| --- | --- | --- | --- |
| 4 | Is spoofing evidence from sim + real logs with injected faults OK? Which attacks? | Transmitting interference/spoofing is OK **only in a trusted lab**. Injected or simulated spoofing/interference is acceptable, **but the architecture must be clear about how the sim aligns to reality**. Attack types: "surprise us" with the prioritized use cases we think most applicable | ADR-0015 (sim calibrated against real measurements); `verification.md` sim-validity section; threat-model work (issue); optional cabled lab spoof test (issue) |
| 5 | Can the LEO layer be simulated? | Identifying it in the roadmap is a good choice. **Simulating the Iridium network is acceptable** without the Iridium PNT ASIC dev tool | Confirms ADR-0013; LEO sim becomes Iridium-specific |
| 6 | Decode only broadcast/sync fields? | Our decision (RX only, as identified) | None; ADR-0011 stands |
| 7 | D1/D3 format and length? | D1 is written for a **technical audience experienced in navigation products**: architecture, **key requirements associated to the use cases**, proposed solution, no excess background. Length: whatever demonstrates coverage ("not one page, not a thesis"). D1 (Thursday) is separate from the Sunday-night video, which shows we understand the problem and what we propose to do | `use-cases.md`; requirements trace to use cases |
