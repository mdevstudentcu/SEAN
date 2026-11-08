# ADR-0017: Work is ready when evidence matches the claim

- **Status:** Proposed
- **Date:** 2026-11-08
- **Deciders:** team (pending review by both owners)
- **Traces to:** REQ-02, REQ-04, REQ-07, REQ-08, REQ-10, ADR-0004, ADR-0015

## Context

Two owners and several coding agents are landing work quickly before judging on 2026-11-12. The PR template has a checklist, but nothing says what evidence a given claim needs, so "tests pass" can stand in for "the estimator got better" or "this works on the Pi". The kickoff deck asks for quantitative results and says the judges will decide whether we chose our data and monitoring well, so our worst failure is a wrong or overconfident number. The REQ-01 to REQ-04 targets are still `TBD`, so changes cannot be gated on them yet.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Keep only the PR checklist | No work | A tick does not say what evidence a claim needs or what was left unchecked |
| Adopt a full product-release standard (live trials, release promotion, restore drills) | Thorough | Built for a long-lived product. Most of it does not apply here and it costs days we do not have |
| One short standard: evidence matched to each claim, a verdict on every PR, one pre-PR command | Aims at our biggest risk and fits inside normal review | Most of it is checked by people, not CI |

## Decision

`systems/quality.md` defines the evidence each kind of claim needs and every PR ends with one scoped verdict, with `just qa` as the single pre-PR command.

## Consequences

- While a REQ target is `TBD`, changes are compared against `main` and both numbers are reported. No target is invented to make a gate possible.
- A PR stays in draft until it has a verdict, and a check that did not run is reported as unverified.
- PR descriptions are short and use images as the default evidence. Images that cannot be dragged in (`gh` cannot upload them) are committed under `analysis/pr-evidence/<n>/`, apart from the presented figures in `analysis/results/`.
- No new dependencies or CI jobs come with this decision. `just qa` runs what CI already runs, minus generated code and firmware.
- Automating the hard rules in `AGENTS.md` (REQ-07, REQ-08) and adding a `Source` contract test are follow-up work. Until then those rules depend on review.
- Reopen when the REQ targets are set: the numeric gate should then move from "no worse than `main`" to the target itself.
