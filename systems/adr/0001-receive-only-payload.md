# ADR-0001: The payload is receive-only

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-07, RSK-08

## Context

The organizers warned that interfering with the radio spectrum outside a controlled lab nearly rules a team out. Jamming and spoofing are the threats we must demonstrate against.

## Decision

The payload contains only receivers. Jamming and spoofing are injected in software (sim and replay), never transmitted.

## Consequences

No transmit-capable SDR (HackRF excluded). Results on spoofing come from simulation and public datasets (e.g. TEXBAT), which we state openly. Reopen only for a shielded, licensed lab setup.
