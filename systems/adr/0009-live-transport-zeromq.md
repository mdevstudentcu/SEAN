# ADR-0009: Live transport is ZeroMQ PUB/SUB

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-05

## Context

The payload streams to the laptop over Wi-Fi that may drop.

## Decision

ZeroMQ PUB on the Pi, SUB on the laptop, msgpack-encoded Measurement records.

## Consequences

No broker to run. Dropped messages are acceptable live because everything is also logged on board.
