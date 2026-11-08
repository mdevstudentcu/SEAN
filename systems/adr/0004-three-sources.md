# ADR-0004: Sim, replay and live are interchangeable sources

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-01..REQ-05, REQ-10, RSK-04

## Context

We need results before hardware exists, safe GPS-denial tests, and a demo that survives hardware failure.

## Decision

`pnt.sources` provides `sim`, `replay` and `live`, each yielding the same time-ordered stream of `Measurement` records; the estimator never knows which it is fed.

## Consequences

Fault injection (GPS outage, spoofing) lives in sources, not in the estimator. Demo defaults to replay; live is a bonus.
