# ADR-0007: Logs are MCAP, raw IQ sits beside them

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-10

## Context

We need a log format that tools can open (Foxglove) and that holds measurements, estimates and MAVLink; raw SDR samples are GBs.

## Decision

Each session is a folder with `session.mcap` (JSON-encoded topics) plus raw `.cu8` sidecar files indexed by PPS-aligned time (`systems/icd/session.md`).

## Consequences

Sessions never go in git. Foxglove works out of the box for debugging.
