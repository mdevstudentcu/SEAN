# ADR-0013: LEO (Iridium) is simulated, not received

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-06, RSK-07

## Context

Iridium needs its own antenna (GPS patches filter 1616–1626 MHz) and is risky to get working in four days.

## Decision

The LEO layer is simulated with real orbits (TLE snapshot); real hardware covers terrestrial signals of opportunity.

## Consequences

The commercial roadmap (D3) shows LEO as the next layer. Reopen if time allows after the core works.
