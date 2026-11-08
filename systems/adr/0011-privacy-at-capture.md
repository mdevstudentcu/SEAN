# ADR-0011: Privacy is enforced at capture

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-08

## Context

Wi-Fi scanning sees device identifiers; Radiocommunication Act s.9(2) limits use of intercepted communications.

## Decision

The ESP32 salts and hashes BSSIDs before sending them; only beacon/broadcast and sync fields are decoded anywhere in the pipeline.

## Consequences

Identifiers in logs cannot be reversed without the session salt. No client probe requests are captured.
