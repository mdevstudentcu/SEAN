# Systems

The source of truth for what we are building and why. When code or another doc disagrees with a file here, this folder wins.

| File / folder | What lives there |
| --- | --- |
| [`use-cases.md`](use-cases.md) | Use cases (`UC-nn`) the requirements trace to |
| [`requirements.md`](requirements.md) | Mission and requirements (`REQ-nn`), each with a success measure and verification method |
| [`assumptions.md`](assumptions.md) | Assumptions (`ASM-nn`) the design rests on |
| [`adr/`](adr/README.md) | Architecture decision records (`ADR-nnnn`), one file per decision |
| [`icd/`](icd) | Interfaces: `measurement.md` (pipeline record), `pnt.xml` (hub↔Pi wire protocol), `session.md` (log layout) |
| [`risks.md`](risks.md) | Ranked risks (`RSK-nn`) with mitigations |
| [`safety.md`](safety.md) | RF/spectrum, legal, flight, privacy and cybersecurity considerations |
| [`verification.md`](verification.md) | Requirement → method → test → result, and how the sim aligns to reality |
| [`accuracy-budget.md`](accuracy-budget.md) | UC-01 accuracy budget: each error term after GPS loss, how it grows, and how long GPS must be good first (REQ-01, T1) |
| [`quality.md`](quality.md) | What every change must show before it is called ready: evidence per claim, verdicts |
| [`mentor-qa.md`](mentor-qa.md) | Answers from our Honeywell mentors, dated |
| [`threat-model.md`](threat-model.md) | Attacks ranked per use case, mapped to scenarios and detections, with the gaps |
| [`research.md`](research.md) | Summary of our research with cited references, and the novelty check against full papers |
| [`architecture.md`](architecture.md) | D1 draft: principal uses (navigation continuity, status and confidence monitoring) with their requirements, the architecture as built, how the confidence number is computed, how the sim aligns to reality |
| [`roadmap.md`](roadmap.md) | D3 draft: roadmap to a commercial alternative-navigation product: the product (a receive-only GPS trust monitor), its buyers and proof, what the week showed, what fixes it, milestones |
| [`results.md`](results.md) | The evidence for judges: what is real, the scoreboard on ADR-0034's statistic, what each fix buys, spoofing, what is not shown; each number with its kind and source |
| [`deck.md`](deck.md) | The 5-minute deck: per slide the headline, content, figure and a word-for-word script, with timings |
| [`judge-questions.md`](judge-questions.md) | The 24 hardest judge questions: a short answer to say, its source, and what not to claim |
| [`sim-plan.md`](sim-plan.md) | What the simulation work will build, in what order, and what is still undecided |
| [`tower-identity.md`](tower-identity.md) | Explainer: how we know which tower we hear and where it is (ISED register, EARFCN + PCI, timing not strength, clocks learned under GPS, unknown towers) |

## Rules

1. **IDs are never reused.** A dropped item keeps its row, marked *Deleted*.
2. **Unknown values are `TBD` (no value yet) or `TBC` (proposed, not confirmed)**, never "about".
3. **Every requirement has a verification method**: Test (T), Analysis (A), Inspection (I) or Demonstration (D).
4. **Never edit an accepted ADR's decision.** Write a new ADR that supersedes it and mark both.
5. **ICD changes are reviewed by both software owners** (they are the contract between front-ends and estimator).

## Status values

`Draft` → `Proposed` → `Baselined` → `Changed` (via PR) / `Deleted`
