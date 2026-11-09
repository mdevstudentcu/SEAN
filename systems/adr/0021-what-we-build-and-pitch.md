# ADR-0021: We pitch integrity-first navigation that treats signals of opportunity as things that can fail

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-01–REQ-06, UC-01–UC-03, ADR-0015, ADR-0020

## Context

A multi-signal EKF with per-tower clocks is a known approach (the Kassas group has published it), so on its own it doesn't score on innovation. Our research turned up four things:

- **Every signal of opportunity can be faked, cloned or replayed,** and none is authenticated at the signal level.
- **A tower with its own unknown clock adds no fault-detection redundancy, and towers that share a clock can be grouped and calibrated into one testable constellation** ([Jia, Khalife & Kassas, IEEE T-ITS 2023](https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Performance_analysis_of_opportunistic_ARAIM_for_navigation_with_GNSS_signals_fused_with_terrestrial_signals_of_opportunity.pdf)).
- **Tower time is often GNSS-disciplined,** so it can fail together with GPS.
- **The niche is open.** Honeywell's own alternative-navigation suite covers vision, magnetic, LEO and celestial navigation, but not terrestrial communication signals.

Novelty claims rest on web and arXiv searches, re-checked against the full papers on 2026-11-09 ([`research.md`, novelty check](../research.md#novelty-check-98), #98). That check found P1 largely and P2 and P4 partly pre-empted by the Kassas group. A second reading the same day found P3 and P5 partly pre-empted too: time protection levels for GNSS timing receivers (Kirkko-Jaakkola et al. 2017; Baweja 2026), and GNSS time checked against other clocks (Zhang, Spanghero & Papadimitratos 2020). JAM-ME (Tedeschi et al. 2020, read in full) already uses a jammer as a navigation beacon, so P8 is partly pre-empted too. Nothing published was found for P8 below, or for the tower-based parts of P3 and P5, which are planned and not yet on `main`.

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
| P1 | Two-level tower clocks (site under network builder) with drift, learned under a gated calibration that is rolled back if GNSS was lying; extends Jia et al.'s SOP constellations | Core | #77 |
| P2 | Solution separation in which GNSS-timed and GNSS-derived sources fail with GPS, and each network builder's timing is its own fault | Core | #82 |
| P3 | Calibrated tower clocks as a passive detector of GNSS position spoofing, with GNSS time tested against our own clock model; towers refuting GNSS time, never confirming it, is planned | Core (lead claim) | #83 |
| P4 | Base/rover differencing in which the base is itself monitored as a fault (ground station, ADR-0020) | Core | #81 |
| P5 | A time protection level from the receiver-clock covariance (oscillator holdover in `ekf`); a term for the towers' GNSS-disciplined clocks is planned | Core (lead claim) | #78 |
| P6 | ADS-B interference early warning | Add-on | #91 |
| P7 | Pre-flight integrity prediction | Add-on | #92 |
| P8 | Hostile emitter as one low-trust source in the filter, with its own fault hypotheses (power modulation, movement) and a protection level; extends JAM-ME (sim) | Add-on | #93 |
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
- **The pitch leads with P3 and P5** (decided by the owner on 2026-11-09, after #98, and kept in their narrower wording after the second reading the same day; narrowed again to what `main` does on 2026-11-09 by AceAtDev, in the review of PR #111): calibrated towers catch a GNSS position spoof, GNSS time is checked against our own clock model, and the time we hold comes with a protection level. Pitch line: "Time integrity exists for GNSS receivers. Our time bound today covers oscillator holdover; extending it to tower-held time is planned." P1, P2 and P4 are presented as building on opportunistic ARAIM and base/rover differencing, saying what we add. This changes the story, not the work: the order below stands.
- **Claims and evidence:**
  - Every claim follows `systems/quality.md`: paired evals against `main`, Stanford plots on fault scenarios, and the sim model's validity status stated.
  - "First" is never claimed. For P3, P5 and P8 the wording is "we found no published…", with the still-unread papers in [`research.md`](../research.md#still-unread) named in the speaker notes. "Collaborative integrity" isn't used as a novelty term.
  - The Edwards AFB result is cited only as: two co-located towers of different operators kept their clock difference for over 95 minutes of intermittent, GPS-only jamming (Kassas et al. 2022).
- **Design decisions** under this scope have their own ADRs:
  - ADR-0022: tower clocks
  - ADR-0023: tower identity
  - ADR-0024: GNSS-dependency tags
  - ADR-0025: hostile beacon
  - ADR-0026: ground-link security
- **Reopen if:**
  - reading a still-unread paper shows the narrower P3 or P5 is already published
  - the mentors' targets (Q1–Q3) make the integrity focus irrelevant
