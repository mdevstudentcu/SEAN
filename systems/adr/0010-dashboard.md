# ADR-0010: Operator dashboard is FastAPI plus one static page

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-05

## Context

Judges need a clear live display; a React build chain is not worth it in four days.

## Decision

FastAPI serves a websocket and one static page (Leaflet map + uPlot charts). Foxglove is used for internal debugging.

## Consequences

Polish goes into what the page shows, not the framework.
