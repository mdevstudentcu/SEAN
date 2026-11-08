# Mentor Q&A

Answers from our Honeywell mentors, kept so decisions trace back to them. Newest first.

## 2026-11-08: answers to our seven questions (Teams)

From the Honeywell mentor (SATCOM). Q1–Q3 (accuracy, integrity level, timing target) are still open; they will answer later.

| Q | Our question | Answer | What it changes |
| --- | --- | --- | --- |
| 4 | Is spoofing evidence from sim + real logs with injected faults OK? Which attacks? | Transmitting interference/spoofing is OK **only in a trusted lab**. Injected or simulated spoofing/interference is acceptable, **but the architecture must be clear about how the sim aligns to reality**. Attack types: "surprise us" with the prioritized use cases we think most applicable | ADR-0015 (sim calibrated against real measurements); `verification.md` sim-validity section; threat-model work (issue); optional cabled lab spoof test (issue) |
| 5 | Can the LEO layer be simulated? | Identifying it in the roadmap is a good choice. **Simulating the Iridium network is acceptable** without the Iridium PNT ASIC dev tool | Confirms ADR-0013; LEO sim becomes Iridium-specific |
| 6 | Decode only broadcast/sync fields? | Our decision (RX only, as identified) | None; ADR-0011 stands |
| 7 | D1/D3 format and length? | D1 is written for a **technical audience experienced in navigation products**: architecture, **key requirements associated to the use cases**, proposed solution, no excess background. Length: whatever demonstrates coverage ("not one page, not a thesis"). D1 (Thursday) is separate from the Sunday-night video, which shows we understand the problem and what we propose to do | `use-cases.md`; requirements trace to use cases |
