# ADR-0020: A ground reference station measures tower clocks for differential LTE

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-01, REQ-02, REQ-03, REQ-04, REQ-06, ADR-0001, ADR-0002, ADR-0015, ADR-0018

## Context

LTE towers are only frequency-locked to ±50 ppb, so their clocks wander. Measured towers show sudden frequency jumps (one about every minute on one tower). A single receiver learns each tower's clock while GPS is trusted and then coasts on that model through an outage. The model decays, so position and time errors grow with outage length.

A tower with its own unknown clock also adds no fault-detection redundancy ([Jia, Khalife & Kassas, IEEE T-ITS 2023](https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Performance_analysis_of_opportunistic_ARAIM_for_navigation_with_GNSS_signals_fused_with_terrestrial_signals_of_opportunity.pdf)).

A static receiver at a known point that hears the same towers can measure their clocks continuously. Differencing the payload's measurements against it cancels the tower clocks; this is the base/rover or mapper/navigator setup of the Kassas group. Its residuals also help single out a faulty or fake tower.

Everything the base measures is processed on the ground laptop anyway (ADR-0002), so no new radio link is needed.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| No reference; learned tower clocks only | No extra hardware | Error grows with outage length; a lone tower clock is not testable |
| Reference station on hardware, mirrored in sim | Tower clocks cancel in real time; collaborative integrity; real evidence; a ground-based augmentation story like GBAS for aviation | $92.34 of parts; set-up and a zero-baseline test; a new single point of failure to monitor |
| Reference station in sim only | Free | No real evidence for the strongest part of the integrity story |

## Decision

A static ground reference station measures the same LTE towers as the payload, at a surveyed point, and the laptop differences against it. The sim gets the same second receiver.

## Consequences

- **Hardware:** NooElec NESDR SMArt v5 bundle, NEO-6M GPS with PPS, and the spare Pi 3B+ (ADR-0018), streaming to the laptop over Ethernet. Parts list, prices and delivery are in `hardware/bom.md`. It is receive-only like the payload (ADR-0001).
- **Time:** base and payload share GPS time through their own PPS-disciplined clocks. A wired link is needed because NTP gives only milliseconds, and 1 µs is 300 m.
- **Survey:** the base's position is its GPS fix averaged over at least 1 h (`TBC`).
- **Calibration:** a zero-baseline test before each session. The base and payload run side by side for 5–10 min, and the difference is their receiver bias.
- **Integrity:**
  - The base is a fault hypothesis of its own: a faulty, spoofed or compromised base would corrupt every correction.
  - Its link to the laptop is authenticated (ground-link security, `TBC` with its own decision).
  - It does **not** protect absolute time against a wide-area GNSS time spoof, which pulls the base too. That case stays with the common-mode fault hypothesis.
- **Interfaces:** measurements from two receivers need a receiver identifier. That changes `systems/icd/measurement.md` or `systems/icd/session.md`, so it is a separate PR with the `icd` label and the other owner's approval. This ADR does not change the ICD.
- **Range:** the base must hear the same towers as the payload, which holds within a few km on campus (`TBC` by the RF survey).
- **Reopen if:**
  - the parts don't arrive by Tue 2026-11-10 (rule 1 in `hardware/bom.md`), in which case it stays in sim and on the roadmap
  - the NEO-6M PPS cannot be made to work
  - the zero-baseline bias is unstable
