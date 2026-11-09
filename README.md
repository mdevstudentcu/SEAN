# PNT from Signals of Opportunity

**Hack the Horizons 2026 (Honeywell Aerospace × Carleton FED), Challenge 2: Resilient Navigation in GPS-Denied Environments.**

A removable, receive-only payload listens to the signals already around us (cell towers, aircraft ADS-B, VOR navaids, Wi-Fi), together with an IMU, barometer and GPS. A ground laptop fuses them into position **and time**, and reports **how far to trust each estimate**: protection levels, timing uncertainty, per-source health. When GPS is jammed, spoofed or gone, navigation continues and the operator can see how reliable it is.

> Status: scaffold (2026-11-08). The idea layer on top of the foundation is still being chosen; see `systems/adr/`.

## How it fits together

```
 payload (Pi 4B)                                    ground laptop
 ┌───────────────────────────┐   Wi-Fi (ZeroMQ)   ┌──────────────────────────────────────────┐
 │ GPS+PPS  IMU  baro  Wi-Fi │ ─────────────────► │ front-ends → estimator → integrity → UI  │
 │ SDR A (ADS-B)  SDR B (LTE,│     or MCAP log    │                ▲                         │
 │ VOR, FM)       camera     │ ─────────────────► │ sim (scenarios, fault injection)         │
 └───────────────────────────┘                    └──────────────────────────────────────────┘
```

The estimator cannot tell whether its measurements come from the simulator, a recorded session or the live payload (ADR-0004). That is how GPS outages and spoofing are tested safely: in software, never on the air.

## Quickstart

```bash
# with uv + just (recommended)
just setup
just sim gps-outage        # writes data/sessions/sim-gps-outage-*.mcap, prints metrics
just eval gps-outage 50    # Monte Carlo
just test

# without them
python -m venv .venv && .venv/bin/pip install -e '.[ground,dev]'
.venv/bin/pnt sim gps-outage
```

Open any `.mcap` in [Foxglove](https://foxglove.dev) to inspect truth, measurements and estimates.

## Where things are

| Folder | |
| --- | --- |
| [`systems/`](systems/README.md) | Requirements, assumptions, decisions, interfaces, risks, safety, verification: the engineering record |
| [`src/pnt/`](src/pnt) | The Python package: core types, sources, sim, front-ends, nav, integrity, payload, dashboard |
| [`firmware/`](firmware) | Superseded ESP32-S3 hub firmware (ADR-0018) |
| [`flight/`](flight) | INAV pre-flight notes (ADR-0028); ArduPilot parameters, scripted missions and SITL for the sim only |
| [`deploy/pi/`](deploy/pi) | Raspberry Pi setup |
| [`analysis/`](analysis) | Monte Carlo and figures |
| [`hardware/`](hardware) | CAD, wiring, link to the payload spec |

Contributors and coding agents: start with [`AGENTS.md`](AGENTS.md).
