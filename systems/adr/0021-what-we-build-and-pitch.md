# ADR-0021: We pitch integrity-first navigation that treats signals of opportunity as things that can fail

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-01–REQ-06, UC-01–UC-03, ADR-0015, ADR-0020

## Context

A multi-signal EKF with per-tower clocks is a known approach (the Kassas group has published it), so on its own it doesn't score on innovation. Our research turned up four things:

- **Every signal of opportunity can be faked, cloned or replayed,** and none is authenticated at the signal level.
- **A tower with its own unknown clock adds no fault-detection redundancy** ([Jia, Khalife & Kassas, IEEE T-ITS 2023](https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Performance_analysis_of_opportunistic_ARAIM_for_navigation_with_GNSS_signals_fused_with_terrestrial_signals_of_opportunity.pdf)).
- **Tower time is often GNSS-disciplined,** so it can fail together with GPS.
- **The niche is open.** Honeywell's own alternative-navigation suite covers vision, magnetic, LEO and celestial navigation, but not terrestrial communication signals.

Novelty claims rest on web and arXiv searches. They are re-checked against the full papers before the pitch (#98).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Accuracy-first: more signals, better filter | Simple story | Reproduces known work; weak on innovation |
| **Integrity-first: learn the signals while GPS is trusted, then use them to keep position and time, catch GPS lying, and catch them lying** | Covers all three use cases; speaks Honeywell's integrity language; builds on what exists | More to build; fault priors are assumed, not measured |
| Hostile-emitter or space-based focus (jammer beacons, Starlink) | Eye-catching | Sim-only, weakest evidence base |

## Decision

We pitch integrity-first navigation that treats towers, network builders and GNSS-dependent sources as things that can fail. Contributions:

| ID | Contribution | Role | Issue |
| --- | --- | --- | --- |
| P0 | Attack library and report card (taxonomy, time-to-alert, resilience level) | Foundation | #79 |
| P1 | Calibrated tower clocks with site and network-builder grouping | Core | #77 |
| P2 | Solution-separation integrity with dependency-aware fault hypotheses | Core (main novelty claim) | #82 |
| P3 | Calibrated clocks as a time-spoof and meaconing detector | Core | #83 |
| P4 | Base/rover differencing with collaborative integrity (ground station, ADR-0020) | Core | #81 |
| P5 | Time protection level | Core | #78 |
| P6 | ADS-B interference early warning | Add-on | #91 |
| P7 | Pre-flight integrity prediction | Add-on | #92 |
| P8 | Hostile emitter as a low-trust beacon (sim) | Add-on | #93 |
| P9 | GNSS-independent aviation layer (VOR, ILS, DME) | Add-on | #94 |
| P10 | Navigation-health panel | Add-on (what judges see) | #90 |
| P11 | Residual map learned while GPS is trusted | Add-on | #95 |
| P12 | Drone as a mobile reference station (sim) | Roadmap / add-on | #96 |
| P13 | Starlink Doppler layer (sim) | Roadmap / add-on | #97 |

## Consequences

- **Order of work:**
  - Core work comes first, in this order: P0, P1, P5, P3, P2, P4.
  - Add-ons follow, as time allows.
  - The step order and owners are in [`../plan.md`](../plan.md).
- **Claims and evidence:**
  - Every claim follows `systems/quality.md`: paired evals against `main`, Stanford plots on fault scenarios, and the sim model's validity status stated.
  - "First" is never claimed. The wording is "we found no published…" until #98 is done.
- **Design decisions** under this scope have their own ADRs:
  - ADR-0022: tower clocks
  - ADR-0023: tower identity
  - ADR-0024: GNSS-dependency tags
  - ADR-0025: hostile beacon
  - ADR-0026: ground-link security
- **Reopen if:**
  - full-text reading (#98) shows P2 or P3 are already published
  - the mentors' targets (Q1–Q3) make the integrity focus irrelevant
