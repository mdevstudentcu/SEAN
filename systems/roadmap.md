# D3: Roadmap from hackathon to a certifiable product

- **Status:** Draft, 2026-11-09 (#28). The humans own the final D3 and the deck; this is the draft they build from.
- **Honesty rule:** every value we have is `TBC` or a literature placeholder ([`verification.md`](verification.md), *Sim validity*). Nothing below claims a measured accuracy, integrity level or certification status. Dates past judging are `TBD`.

## Where we are on judging day

| Area | State | What makes it a placeholder |
| --- | --- | --- |
| Estimator and integrity design | Built and tested in simulation ([`architecture.md`](architecture.md)) | Fault priors (`p_site`, `p_builder`, `p_layer`, `p_gnss_cm`), continuity budget and integrity risk are all `TBC` (`integrity/mhss.py`) |
| Error models | Literature values | Every row of *Sim validity* is `placeholder`; none measured yet |
| Targets T1–T5 | Proposed | Mentors answered Q1–Q4 on 2026-11-10; T1's threshold is theirs, the rest ours (ADR-0034, [`requirements.md`](requirements.md)) |
| Real signals | None recorded yet | LTE front end, recorder and panel not built on `main` |
| Ground reference station | Simulated | Hardware and zero-baseline test pending (#84–#86) |
| LEO, Starlink, hostile beacon, drone as reference | Simulation only | ADR-0013, ADR-0025, P12, P13 |
| Novelty | Checked against the closest full papers ([`research.md`](research.md), *Novelty check*) | Several papers still unread; IEEE Xplore and ION not searched in full text |

## Phases

Each phase ends with evidence, not a date. Durations are `TBD`.

### 1. Measure the sensor

Turn the placeholders into measurements (ADR-0015).

- Long static captures of several sites per network builder: pseudorange noise, multipath, tower clock offset, drift and jumps. Does a common term exist within a builder ([ADR-0022](adr/0022-tower-clock-model.md))?
- Walk, drive and flight sessions with independent truth (RTK, not the GPS we are testing).
- Zero-baseline and long-baseline tests of the reference station.
- Move each *Sim validity* row from `placeholder` to `measured`, then `validated` (sim and real residual distributions compared, gap recorded).
- Attacks injected into real recordings, beside the pure-sim results.

### 2. Characterise integrity parameters

Signals of opportunity have no integrity support message and no published fault statistics (Jia, Khalife & Kassas 2023). Building them is the long pole.

- Fault rates per site, per builder and per association type from many hours of data. Published starting points are single campaigns (Maaref, Khalife & Kassas 2021 derived one tower fault probability from UAV data), not fleet statistics.
- Error overbounds that hold in the tails, including time-correlated errors, for the Kalman-filter bank.
- A per-builder timing-source survey: which networks are GNSS-disciplined, with what holdover class.
- Map the fault hypotheses onto a fault tree a safety assessor recognises.

### 3. Product hardware

Still receive-only (REQ-07).

- A coherent multi-channel, wideband receiver: SIB1 decoding confirms tower identity instead of inferring it ([ADR-0023](adr/0023-tower-identity.md) roadmap), and more carriers per builder add redundancy.
- A better oscillator for longer time holdover (UC-03), and a tactical-grade IMU.
- More signal families as fault hypotheses, each with its GNSS-dependency tag ([ADR-0024](adr/0024-gnss-dependency-tags.md)): 5G NR sync blocks, VOR, ILS and DME (P9), LEO: Iridium (ADR-0013) and Starlink (P13, simulated in `starlink-outage`; a real receiver needs a Ku-band LNB and downconverter).
- Tamper-evident session logs (hash chain, [ADR-0026](adr/0026-ground-link-security.md)) and per-deployment key management.

### 4. Integrate as a layer

- **Where it fits:** Honeywell's alternative-navigation suite lists "radios" without a released module ([`research.md`](research.md) §3). This is that terrestrial-communications layer, with timing as a second output.
- **Interfaces:** position, time, protection levels and per-source trust as a navigation-aid input to the host's integrated navigation. Interface standard `TBD` with Honeywell.
- **Operator language:** protection levels against alert limits in RNP/ANP terms on crewed aircraft; the navigation-health panel (P10) on UAS.
- **Network-side option:** a ground reference station network that measures tower clocks continuously for many users, the base/rover idea at scale (P4, P12).

### 5. Certify

- **No performance standard exists for SoOP navigation.** RTCA SC-159 covers GNSS equipment (RTCA 2026, in [`research.md`](research.md)). A product needs either a new standard or an equivalent level of safety argued case by case. Which route, and with which regulator, is `TBD` with Honeywell's certification experts.
- **Development assurance** for airborne use would follow the usual system, software and hardware processes and environmental qualification; the applicable documents and design assurance level are `TBD` once the failure condition classification is known.
- **UAS first:** the UC-01 market is likely the shorter path (operational risk assessment for a specific operation), crewed approach (UC-02) the longer one. Both `TBC`.
- **Timing (UC-03):** holdover performance would be stated against telecom timing holdover masks and the CISA/DHS resilience levels we already report against. The masks to use are `TBC`.
- **Spectrum and legal:** the receive-only, broadcast-fields-only position (`safety.md`) needs a legal opinion, not our reading.

## What we will not claim on stage

- A certified, measured or validated integrity level.
- "First": the wording is "we found no published…", narrowed as the novelty check proposes.
- Real-world accuracy from simulated runs. Every result is labelled sim, replay or real.
