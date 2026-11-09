# ADR-0025: In simulation, a located jammer may become a low-trust beacon behind guardrails

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-02, REQ-04, REQ-07, ASM-03, ADR-0001, ADR-0024

## Context

A GNSS jammer that has been located is a transmitter at an estimated position. Its received power, seen from a moving receiver, is a coarse range to it.

- **Prior work:** one line of work uses a jammer as a navigation beacon. JAM-ME estimates the jammer's location from the jamming signal and then homes on it "as a radio beacon". It is simulation only and has no integrity or protection levels ([Tedeschi, Oligeri & Di Pietro, IEEE Access 2020](https://pietrotedeschi.github.io/publication/tedeschi-2019-leveraging)). In our search of open literature we found no system that fuses a hostile emitter with a protection level. Military work would not show up in that search.
- **The adversary controls every assumption the beacon needs:** that it stays put, keeps steady power and keeps a stable clock.
  - Power-modulated jammers widen localisation error markedly ([Localization of a Power-Modulated Jammer](https://manara.qnl.qa/articles/journal_contribution/Localization_of_a_Power-Modulated_Jammer/25516174)).
  - In spoofer geolocation, a correct clock-correlated model gave 95.31% containment, and an uncorrelated model gave 1.38% ([Clements et al., NAVIGATION 2026](https://navi.ion.org/content/73/1/navi.750)).
- **Rogue cells** can align to a live cell's timing ([LTrack, USENIX Security 2022](https://www.usenix.org/system/files/sec22summer_kotuliak.pdf)) and are often mobile.
- **Jamming exists here only in software.** We transmit nothing (ADR-0001, ASM-03), so all of this runs on the `jamming-zone`, `spoof-ramp` and `meaconing` scenarios.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Ignore hostile emitters; navigate around them | No new trust surface | Throws away an emitter that is there anyway |
| B. Locate them for awareness only | Situational awareness on the panel; no effect on the solution | No availability gain |
| C. Low-trust beacon with guardrails, sim only | Availability in a jammed zone; a novel integrity treatment | Adversary-controlled; needs a gate, a fault hypothesis and a weight cap to stay honest |
| D. Use as an ordinary aid | Simplest | A honeypot jammer could steer the solution |

## Decision

In simulation only, a located jammer may be promoted to a low-trust coarse range beacon behind the guardrails below, and rogue cells are detected and excluded, never used as beacons.

**Guardrails:**

1. **Its own fault hypothesis.** It has a high prior P_hostile = `TBD`, far above the tower priors. Solution separation compares all-in-view against all-but-hostile.
2. **A promotion gate.** The jammer is promoted only after a stationarity test passes over a `TBD`-second window: consistent power and path-loss estimates, range rate consistent with IMU-predicted geometry, and a χ² fit. It is demoted at once on a power step or a run of large innovations.
3. **Never the only aid in any direction, and a weight cap.** If removing it leaves a horizontal direction unobservable, it adds availability but may not shrink the PL. Its weight is capped so that a deceptive move within its own σ shifts the solution by at most a `TBD` share of the alert limit.
4. **Power and clock as random walks.** Transmit power and any transmitter clock are random-walk states, never constants.
5. **Shown separately.** The panel shows it as a distinct, low-trust contributor (I17).

## Consequences

- **Rogue cells** are excluded and their estimated location is logged for awareness. They feed ADR-0023's association fault modes, not the beacon path.
- **Jammer switch-off** drops the beacon states. GNSS is re-admitted only after the REQ-04 consistency check, because jam-then-spoof is a known sequence.
- **Receive-only and defensive.** Nothing here transmits, and no code or document describes how to build or operate a jammer or spoofer. Hostile emitters exist only as software fault injection in `sim/` and `sources/`.
- **Real data:** using a real jammer's signal would need a new ADR, and there is no legal way for us to create one.
- **GNSS dependency (ADR-0024):** the beacon is independent of GNSS but adversary-controlled. Guardrail 3 keeps it from ever vouching for a solution on its own.
- **Evidence:** eval on the jamming scenarios with and without the beacon, reporting PL, misleading epochs and the worst run (I20). Accuracy is set by the power model; no accuracy figure is claimed until then.
- **Reopen if:**
  - in sim, a honeypot jammer gets through the gate and moves the solution beyond the cap
  - the guardrails cost more availability than the beacon adds
