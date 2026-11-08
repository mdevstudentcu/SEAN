# ADR-0008: Time is GPS nanoseconds; positions are ENU metres

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-01, REQ-03

## Context

Mixed time bases and coordinate frames are the most common source of fusion bugs.

## Decision

All timestamps are int64 GPS-time nanoseconds; positions are local ENU metres about a per-session origin, with WGS84 only at the edges.

## Consequences

`pnt.core.time` and `pnt.core.frames` are the only conversion points. Leap seconds handled there.
