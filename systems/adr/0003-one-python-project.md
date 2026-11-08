# ADR-0003: One Python project managed with uv

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-10

## Context

Two software people, four days. Nx/multi-package setups (as in arc-monorepo) pay off over years, not days.

## Decision

One package `pnt` with subpackages and optional extras (`ground`, `payload`, `dev`), managed by uv, commands in a justfile.

## Consequences

Simple installs on laptop and Pi. If firmware or web grow into their own toolchains they stay in their folders (PlatformIO, static web) without a workspace tool.
