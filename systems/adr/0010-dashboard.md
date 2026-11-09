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

## Amendment, 2026-11-09 (decided by the owner)

The page streams over Server-Sent Events (`GET /api/stream`, with `POST /api/ack` for acknowledging alerts) instead of a websocket, and draws its map and charts itself on canvas instead of loading Leaflet and uPlot.

- **Server-Sent Events:** uvicorn serves websockets only with `websockets` or `wsproto` installed, and neither is in `uv.lock`. Adding one is a new dependency. The browser's built-in EventSource carries the same frames one way, which is all the panel needs.
- **Canvas, not Leaflet and uPlot:** loading code from a CDN at run time needs owner sign-off (AGENTS.md), and the indoor demo may have no network. The map is a local ENU plot with towers and the reference station, and has no map tiles.
- **Reopen if:** the panel needs to send more than acknowledgements, or real map tiles become worth an offline tile cache.
