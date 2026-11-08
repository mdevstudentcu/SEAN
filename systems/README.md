# Systems

The source of truth for what we are building and why. When code or another doc disagrees with a file here, this folder wins.

| File / folder | What lives there |
| --- | --- |
| [`use-cases.md`](use-cases.md) | Use cases (`UC-nn`) the requirements trace to |
| [`requirements.md`](requirements.md) | Mission and requirements (`REQ-nn`), each with a success measure and verification method |
| [`assumptions.md`](assumptions.md) | Assumptions (`ASM-nn`) the design rests on |
| [`adr/`](adr/README.md) | Architecture decision records (`ADR-nnnn`), one file per decision |
| [`icd/`](icd) | Interfaces: `measurement.md` (pipeline record), `pnt.xml` (ESP32↔Pi wire protocol), `session.md` (log layout) |
| [`risks.md`](risks.md) | Ranked risks (`RSK-nn`) with mitigations |
| [`safety.md`](safety.md) | RF/spectrum, legal, flight, privacy and cybersecurity considerations |
| [`verification.md`](verification.md) | Requirement → method → test → result, and how the sim aligns to reality |
| [`quality.md`](quality.md) | What every change must show before it is called ready: evidence per claim, verdicts |
| [`mentor-qa.md`](mentor-qa.md) | Answers from our Honeywell mentors, dated |
| [`sim-plan.md`](sim-plan.md) | What the simulation work will build, in what order, and what is still undecided |

## Rules

1. **IDs are never reused.** A dropped item keeps its row, marked *Deleted*.
2. **Unknown values are `TBD` (no value yet) or `TBC` (proposed, not confirmed)**, never "about".
3. **Every requirement has a verification method**: Test (T), Analysis (A), Inspection (I) or Demonstration (D).
4. **Never edit an accepted ADR's decision.** Write a new ADR that supersedes it and mark both.
5. **ICD changes are reviewed by both software owners** (they are the contract between front-ends and estimator).

## Status values

`Draft` → `Proposed` → `Baselined` → `Changed` (via PR) / `Deleted`
