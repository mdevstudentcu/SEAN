# ADR-0005: ESP32↔Pi wire protocol is a custom MAVLink dialect

- **Status:** Superseded by ADR-0018
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-05, REQ-09

## Context

The ESP32 sends IMU data at up to 1 kHz plus barometer, PPS and Wi-Fi records; JSON over serial would saturate the link. MAVLink is already in the stack (ArduPilot) and familiar from arc-monorepo's sync link.

## Decision

Messages are defined in `systems/icd/pnt.xml`; `just gen` produces C for the ESP32 and Python for the Pi with mavgen.

## Consequences

Generated code is never edited by hand. Message IDs 61000–61099 are ours.
