# D3: Roadmap to a commercial alternative-navigation product

**The product:** a receive-only navigation layer that keeps a position from cell towers after GPS is lost, and tells the operator when not to trust it. Every number here is in [`results.md`](results.md) with its kind (simulated or real) and source.

## Who it is for

| | |
| --- | --- |
| **First user** | An operator of inspection or delivery drones on an urban corridor over Ottawa, below 120 m (UC-01, [`use-cases.md`](use-cases.md)). Their threat: in-vehicle jammers on nearby roads, carry-off spoofing aimed at drones, urban blockage. What they need: a position that stays in the corridor through a GPS outage, an alert before it leaves, and detection of spoofed GPS |
| **Later users** | Crewed aircraft in the terminal area (UC-02); timing users such as a satcom terminal disciplined to GPS (UC-03) |
| **Where it fits** | Honeywell's alternative-navigation suite lists radios without a product ([`research.md`](research.md) §3). This is that terrestrial-radio layer: position, time, a bound and per-source trust, as an aid to the host's navigation |

## The payload today: cost, size, weight, power

From [`hardware/bom.md`](../hardware/bom.md) (CAD before tax, Amazon.ca, 2026-11-08 and 2026-11-09).

| Item | Cost | Source |
| --- | --- | --- |
| NooElec NESDR SMArt v5 bundle (LTE radio) | 77.95 | Bought |
| Bingfu LTE antenna, 2-pack | 20.49 | Bought |
| AirNav FlightStick (ADS-B radio) | 45.15 | Bought |
| NooElec ADS-B antenna bundle | 25.95 | Bought |
| **Radios and antennas** | **169.54** | Sum of the four |
| Raspberry Pi 4B 4 GB, GPS HAT and active antenna, MPU6050, BMP180 | `TBD` | Supplied (team or Honeywell); no price in the BOM |
| Payload power: 5 V BEC | `TBD` | Not yet chosen |

- **Size and weight:** `TBD`, not measured. The BOM flags the LTE antenna's magnetic base and 3 m cable as too heavy for a 5" quad.
- **Power:** 5 V from a supply rated ≥ 3 A; the draw is `TBD` (to be measured on the bench supply).

## Operating envelope (assumptions, `TBC`)

| Assumption | Basis | Status |
| --- | --- | --- |
| Below 120 m above ground, urban corridor | UC-01 | `TBC` |
| Simulated flights at 40 to 45 m above the origin, 8 m/s | `uc01-drone-circuit` and the `challenge` drone leg (waypoints) | Simulation only |
| Real captures on the ground or 0.5 m up, static | 2026-11-10 sessions | Real; nothing recorded in flight |
| Tower antennas are tilted down toward the street, so reception at altitude may differ from the ground | Not measured; not studied | `TBD` |
| GPS available at mission start, then lost or degraded in an area | Mentors, call of 2026-11-10 | Matches the scenarios |
| Height from the barometer; navigation mainly horizontal | ASM-05 | `TBC` |

## Where we are

| Area | State |
| --- | --- |
| Built | Payload, LTE front end, tower lookup, estimators, integrity monitor, operator panel, authenticated live link ([`architecture.md`](architecture.md)) |
| Real signals | LTE range precision measured at rest; GPS sessions with timing pulse; on real static sessions with GPS removed in software, the towers made position worse than none |
| What works (simulation) | Jumps and GPS clock drift detected within seconds; no false alarms on clean runs; a refused jump stays red and recovers when the spoof ends (opt-in guard) |
| What does not (simulation) | Accuracy after GPS loss misses our 25 m target and the mentors' 50 m fallback; the slow GPS drag is not caught by default; the bound is not honest on the worst runs |
| Towers in practice | With the noise the radio reports, the filter rejects nearly every tower reading; after GPS loss it flies on the barometer and dead reckoning |
| Models | IMU measured; LTE measured at rest, not yet adopted (ADR-0036, Proposed); the rest placeholder |

## What the week showed, and what fixes it

| Finding | Fix | State |
| --- | --- | --- |
| The radio reports only its fast noise; the filter rejects the towers | Learn each tower's noise; split white and slow error, sized from captures (ADR-0036, ADR-0039, both Proposed) | In review, opt-in; better on the drone leg, not yet on the timing leg |
| One frequency hears 1 to 4 cells, often sectors of one site | Hop frequencies with one radio (ADR-0040, Proposed); coherent integration (merged) | Simulation and synthetic only |
| A detected jump was followed | Refuse it until GPS steps back (ADR-0038, Proposed) | Merged, opt-in; default-on waits on the manoeuvre follow-up |
| Deciding whether GPS is spoofed, from signal power and the known sky, is the mentors' first ask | One spoofed-or-not output from the sky and signal power (ADR-0041, Accepted); tower monitor for slow drags (ADR-0037, Proposed) | Sky decision merged (#239), advisory; the tower monitor is opt-in and needs 5 or more sites heard continuously |
| The bound is honest only where the model is | An honest tower model; a mapper for unregistered cells; a confidence heat map on the track (built, #235) | Heat map built; tower model and mapper open |
| Real captures break front-end assumptions (aliased carriers, cells dropping often) | Doppler records off by default; first-path check and re-find fixed (#245, ADR-0036 *Amendment 2026-11-11 (owners)*) | Merged; 16 to 17 % of re-finds still step over 100 m, and 4 of 40 tracks sit on a carrier alias |

## Three milestones

Durations are proposals, `TBC`; none is committed.

| Milestone | What it does | Ends in | Duration (proposed) |
| --- | --- | --- | --- |
| **M1. Measure on the move** | Run the fixes together on the agreed statistic; a real session with GPS cut in software; moving captures with independent truth (RTK, not the GPS under test); real frequency hopping; attacks injected into real recordings | The LTE row of *Sim validity* moved to `measured` for motion; T1's fallback met or missed on real-shaped data with the reason; the guard's default-on decision | 3 months, `TBC` |
| **M2. Earn the integrity case** | Many hours of tower data: fault rates per site, per network and per association type; tail overbounds including the slow error; a per-network timing-source survey | Fault priors and the integrity risk derived from data instead of `TBC`; the hypotheses as a fault tree an assessor recognises | 9 months, `TBC` |
| **M3. Product receiver with a first operator** | A coherent multi-channel receive-only receiver (several frequencies at once, tower identity from SIB1); a better oscillator and IMU; size, weight, power and cost measured | A trial with a first drone operator under a specific-operation risk assessment, with the layer feeding their navigation | 12 months, `TBC` |

## Open work items

- Tower error model in the default filter (#77). Since ADR-0047 (our clock in the tower ranges once GNSS time is used), the default `ekf` keeps position after GPS loss but its clock is overconfident: 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets (REQ-03), accepted by the owners on 2026-11-11. `ekf-calibrated`, which models the towers' multipath and correlation, has none. Bring that model into the default, then rerun the time-integrity rows.
- **Drone as a mobile reference station (P12, #96):**
  - *On `main`, sim only (option A):* a tower-map hand-off. A drone with trusted GPS learns the tower clocks, and a GPS-less ground user starts its filter from them (`nav/tower_map.py`, `p12-drone-map-handoff`, `analysis/p12_map_handoff.py`). There is no ICD change: the map never enters a session.
  - *Sim result, realistic-set world, every value `TBC`, 20 seeds at `9a958b1`, scored as T1 (95th percentile across seeds at each second after GPS loss, worst second, ADR-0034):* over the 300 s after GPS loss the map cut the user's error from 618 m (no aid) to 416 m (map handed over at once) and 310 to 359 m (maps 5 to 30 min old). Over the first 120 s it did not help: 278 m with no aid, 291 m with the freshest map, 219 to 252 m with the older ones. A no-aid filter given the sim's own tower drift spread (0.05 m/s) as its prior did better than every map over 300 s (281 m; 241 m over 120 s), because what the drone learns in a 300 s circuit is looser (drift sigma 0.23 to 0.33 m/s in seed 0's map). Nothing meets T1 or the 50 m / 120 s fallback. Map age up to 30 min made no visible difference at these values. Whether a map beats a prior depends on the real towers' drift spread, which the radio test has to measure.
  - *Trust:* a spoofed drone hands on clocks that fit the spoofed track. The map is one more fault hypothesis, not truth, and nothing tests it yet.
  - *Roadmap (option B):* a live moving reference that streams its readings for differencing, as the ground station does (P4). It needs an ICD change for a moving reference receiver and its position.

**Certification.** No performance standard exists for this kind of navigation; RTCA SC-159 covers GNSS equipment ([`research.md`](research.md) §3). Route and regulator `TBD` with certification experts. Drones first (UC-01) is likely shorter than crewed approach (UC-02), `TBC`. The receive-only, broadcast-only position ([`safety.md`](safety.md)) needs a legal opinion, not our reading. Later layers: 5G sync blocks, navaids, and the LEO layer (Iridium and Starlink, simulated).

## What we will not claim

- A certified, measured or validated accuracy or integrity level.
- A useful position from real towers: on our real static sessions LTE made position worse than none.
- Real-world numbers from simulation runs.
- "First": the wording is "we found no published…" ([ADR-0021](adr/0021-what-we-build-and-pitch.md)).

---

*Status: 2026-11-11, against `main` at `c21e047`; brought up to `c97e09a` (#245, ADR-0047, ADR-0048). Still open: combined fixes (#218, draft PR #247). Merged since: real GPS cut (#214, #233), spoof decision (#206, #239), tower count (#208, #232), heat map (#207, #235). Sources per row: [`results.md`](results.md).*
