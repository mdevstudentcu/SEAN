# ADR-0002: Record raw on board, process on the ground

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-05, REQ-10, RSK-04

## Context

Decoding LTE or Iridium in real time needs more compute than a small payload should carry, and raw recordings let us re-run any idea later.

## Decision

The payload records raw samples and sensor data and streams light measurements; decoding and fusion run on the laptop, live or from logs.

## Consequences

A Pi 4B (or smaller) is enough on board. Every session is replayable with new code. Live monitoring needs a Wi-Fi link; replay is the fallback.
