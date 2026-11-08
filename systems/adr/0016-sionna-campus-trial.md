# ADR-0016: Ray-traced campus blockage is an optional, unvalidated model input

- **Status:** Proposed
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** ADR-0015, REQ-01, `sim-plan.md` (Sionna RT spike)

## Context

Buildings cause the lingering, per-tower errors that hurt a filter most. Statistical settings can represent them but cannot say where on a route they happen. Sionna RT (Apache-2.0) traces radio paths through a scene, and the plan allows a time-boxed trial with an owner's go-ahead.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Statistical model only | Simple, no extra tooling | Doesn't tie errors to places on campus |
| Ray-trace one campus route and use the table as a scenario input | Blockage happens where buildings are; a small table is all the repo needs | Most OSM heights are missing, trees are absent, materials are assumed |
| Full Ottawa digital twin | Most complete | Far beyond the time available |

## Decision

Keep the statistical model as the default. Allow one committed ray-traced table per route as an optional input, through `ray_table` in a scenario. Sionna stays in its own environment, outside the project's dependencies and CI, run through `analysis/sionna_campus.py`.

## Consequences

- Ray-traced numbers shape the model and are not reported as accuracy results unless checked against our measurements (ADR-0015).
- The table only fits the route it was traced for. A new route needs a new trace.
- Reopen if real sessions show the table predicts blockage better than the statistical model, or worse.
