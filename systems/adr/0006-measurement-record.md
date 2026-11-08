# ADR-0006: One pipeline record: Measurement

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-06, REQ-10

## Context

Front-ends and estimator are built by different people in parallel; the idea layer is still undecided.

## Decision

Every observable is a `Measurement` (msgspec struct, `systems/icd/measurement.md`) with an open registry of `source` and `kind` values.

## Consequences

Adding a signal source adds a front-end and a measurement model, never a change to the record. Changing the record needs both owners (ICD rule).
