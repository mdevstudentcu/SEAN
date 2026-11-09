# ADR-0027: The dashboard streams over Server-Sent Events and draws on canvas

- **Status:** Accepted
- **Date:** 2026-11-09
- **Deciders:** Shrikar Vempati, M. Elshoubky (the two owners)
- **Traces to:** REQ-05, ADR-0010 (superseded), ADR-0004

## Context

ADR-0010 chose FastAPI with a websocket and one static page using Leaflet and uPlot. Building the panel (#25, #90, PR #112) ran into two limits:
- **No websocket server is installed.** uvicorn serves websockets only when `websockets` or `wsproto` is installed, and neither is in `uv.lock`. Adding one is a new dependency, which needs owner sign-off (AGENTS.md).
- **Leaflet and uPlot would load from a CDN at run time.** Loading code at run time also needs owner sign-off, and the indoor demo may have no network.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Server-Sent Events plus canvas drawing | No new dependency; nothing loaded at run time; works offline | The page draws its own map and charts; no map tiles |
| B. Add `websockets`, vendor Leaflet and uPlot into the repo | Two-way link; map tiles possible | A new dependency and vendored third-party code, days before judging |
| C. Keep ADR-0010 as written | Nothing to change | The websocket doesn't run with the locked dependencies; the CDN breaks offline |

## Decision

Option A. FastAPI serves one static page and streams frames over Server-Sent Events (`GET /api/stream`, the browser's built-in EventSource). Alerts are acknowledged with `POST /api/ack`, which refuses cross-site requests. The page draws the map (a local ENU plot with towers and the reference station) and its charts on canvas. Foxglove stays for internal debugging.

## Consequences

- The link is one-way, plus the acknowledgement POST, which is all the panel needs.
- There are no map tiles, so the map shows positions relative to the session origin, not streets.
- **Reopen if:**
  - the panel needs to send more than acknowledgements
  - real map tiles become worth an offline tile cache
