# ADR-0012: RC stays the safety layer; scripted flights first

- **Status:** Superseded by ADR-0028
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-09, RSK-01, RSK-09

## Context

Our code could fly the drone over MAVLink, but the only path would be Pi → Wi-Fi → laptop.

## Decision

An independent RC link with a kill switch is always fitted. Flights are scripted with pymavlink in GUIDED mode (level 1). Feeding our navigation into ArduPilot (level 2) is done in SITL only, unless proven there first.

## Consequences

If no RC receiver is available, the drone does not fly; data comes from handheld/vehicle sessions and SITL.
