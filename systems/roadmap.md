# D3: SEAN roadmap to a commercial alternative-navigation product

**SEAN**: **S**ignals-of-opportunity, **E**rror-bounded, **A**ssured **N**avigation.

**The product (proposed, #273):** a receive-only GPS trust monitor for small drones. It checks GPS against cell towers and other signals it only listens to, and warns the autopilot when GPS should not be trusted. Underneath is the navigation layer we built: a position from cell towers after GPS is lost, with a bound, that tells the operator when not to trust it. Every number of ours here is in [`results.md`](results.md) with its kind (simulated or real) and source.

**Where the position comes from.** The research report `reports/sources-research-20261111.md` on `main` (#271), cited below as "report" with its section. It is research by another session, not a decision: it labels each claim, and this file uses only those it labels *checked* (a primary source was read), *experiment* (its scratch sim run, placeholder models) or *repo*. Product direction is an owners' decision that is still open (#279, item 4); #273 writes the roadmap around the trust monitor unless an owner says otherwise.

## The product, the gap, the buyer, the proof

| | |
| --- | --- |
| **Product** | A receive-only GPS trust monitor that warns the autopilot (report 10.5, ranked first of three product shapes; the report names MAVLink's `GNSS_INTEGRITY` message as the output). **Built today:** detection and flags on a ground laptop ([`architecture.md`](architecture.md)). **Not built:** any output to the autopilot; an ICD change, so it needs the other owner's approval |
| **Gap** | What the report's market search did not find (an absence in a search, not proof that none exists): a funded company selling cellular opportunistic navigation for drones (10.1, *checked*; the work is in university groups); a spoof detector on sale that cross-checks GPS against cell towers, since the add-ons found work inside the receiver or against Iridium (10.2); published false alarms per flight hour (10.2, 17.10; receivers with built-in spoof flags publish no false-alarm rates, 10.1, *checked*). Sections 10.2 and 17.10 are the report's summary of its search and carry no evidence label of their own |
| **Nearest competitor** | A 10 g receive-only board that takes position from Iridium's paid service (10.1, 17.3, 17.10; *checked*, vendor datasheet). The service itself, independently tested: 26.6 m horizontal at 95 % over 100 days, static (17.3, *checked*). It needs a subscription; no price is published |
| **First buyers (proposed; none approached)** | Canadian operators flying beyond line of sight, drone-show operators, a defence test slot (10.5). Demand signals, *checked* (10.3, 17.8): closed Canadian defence challenges on drone geolocation under GPS degradation and on timing, one asking for under 30 m after one hour without satellites; an NRC defence stream; NATO test centres in Ottawa. We meet none of those figures |
| **Proof it needs** | Detection rate and delay on recorded spoofing; false alarms per hour over clean flight hours (the report proposes 50 or more, `TBC`); one live-jamming event at an authorised event (10.5). Live jamming is legal only at authorised events (10.4). Where we stand on each: *Proof track* below |
| **Use case behind it** | UC-01 ([`use-cases.md`](use-cases.md)): an inspection or delivery drone on an urban corridor over Ottawa, below 120 m. Threat: in-vehicle jammers on nearby roads, carry-off spoofing aimed at drones, urban blockage. Need: an alert before the position leaves the corridor, and detection of spoofed GPS |
| **Later users** | Crewed aircraft in the terminal area (UC-02); timing users such as a satcom terminal disciplined to GPS (UC-03). Later products the report ranks second and third (10.5): a licensable fusion and integrity engine for autopilots; a sim and test tool |
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
| What does not (simulation) | Accuracy after GPS loss misses our 25 m target and the mentors' 50 m fallback; the slow GPS drag is not caught by default; the bound is not honest on the worst runs; honest GPS can stay refused after a long outage once the coast has drifted (#246) |
| Towers in practice | With the noise the radio reports, the filter rejects nearly every tower reading; after GPS loss it flies on the barometer and dead reckoning |
| Models | IMU measured; LTE measured at rest, not yet adopted (ADR-0036, Proposed); the rest placeholder |

## What the week showed, and what fixes it

| Finding | Fix | State |
| --- | --- | --- |
| The radio reports only its fast noise; the filter rejects the towers | Learn each tower's noise; split white and slow error, sized from captures (ADR-0036, Proposed; ADR-0039, Proposed, PR #156 merged); tell the filter the measured σ (ADR-0044, Accepted, opt-in `ekf-measured-sigma`) | Learned noise merged, opt-in; better on the drone leg, not yet on the timing leg. With 13 carriers hopped (study leg), 132 m on the agreed statistic in simulation, 105 m with LTE noise measured from our captures (PRs #247, #262, merged); not met, and not yet run on real data (#256) |
| One frequency hears 1 to 4 cells, often sectors of one site | Hop frequencies with one radio (ADR-0040, Proposed); coherent integration (merged) | Simulation and synthetic only |
| A detected jump was followed | Refuse it until GPS steps back (ADR-0038, Proposed) | Merged, opt-in; default-on waits on the manoeuvre follow-up |
| Deciding whether GPS is spoofed, from signal power and the known sky, is the mentors' first ask | One spoofed-or-not output from the sky and signal power (ADR-0041, Accepted); tower monitor for slow drags (ADR-0037, Proposed) | Sky decision merged (#239), advisory; on a real recording with a fake sky injected, 59 of 59 faked skyviews flagged. The tower monitor is opt-in and needs 5 or more sites heard continuously; a hop rule that lets it work on hopped carriers is merged (PR #263: 50 of 50 seeds, median 127 s, sim study leg) |
| The bound is honest only where the model is | An honest tower model; a mapper for unregistered cells; a confidence heat map on the track (built, #235) | Heat map built; an honest-bound filter merged, opt-in (PR #251: 0.45 % of epochs above HPL after GPS loss against 45.3 % for `ekf`, worst run 18.5 %, sim); tower model and mapper open |
| Real captures break front-end assumptions (aliased carriers, cells dropping often) | Doppler records off by default; first-path check and re-find fixed (#245, ADR-0036 *Amendment 2026-11-11 (owners)*) | Merged; 16 to 17 % of re-finds still step over 100 m, and 4 of 40 tracks sit on a carrier alias |

## Proof track: what the product has to show

The report's list for the trust monitor (10.5). None of the three is met.

| Proof | Where we are | Next step | Ends in |
| --- | --- | --- | --- |
| Detection rate and delay on recorded spoofing | Sim: jumps and GPS clock drift caught within seconds; a 2 m/s drag missed by default. Real: one static recording with a fake sky injected in software, 59 of 59 faked skyviews flagged ([`results.md`](results.md) (d)). No recorded over-the-air spoofing has been run | Replay a recorded-spoofing dataset through the detector (report 11.4 item 6). The dataset needs an owner's go-ahead first (#279, item 5) | Detection rate and delay on that dataset, with false alarms on its clean parts |
| False alarms per hour over clean flight hours | Sim: 0.0 per hour on `nominal`. Real: static sessions only, minutes long; our default filter refused honest GPS for 262 s of one 601 s session (#241, open). No flight hours | Log clean flights with the monitor running; hours `TBC` | False alarms per flight hour, with the hours flown and every alarm listed |
| One live-jamming event at an authorised event | None. We never jam or spoof (REQ-07, [`safety.md`](safety.md)) | Apply to an authorised event; which one and when: `TBD` | Detection and delay at that event, in its own report |

## Milestones for accuracy after GPS loss

Ordered by what limits accuracy now, as the report argues (11.2, 11.3; unchanged by its later passes, 16.9, 17.10, 18.5). **The order is a proposal:** the owners have not ruled on it (#279, item 3), and each new approach needs its ADR before any code (report 12). M1 to M4 follow 11.2, the order of what limits accuracy. For the sim, 11.3 and 15 item 3 put carrier phase ahead of a velocity source, so that radio stays primary under REQ-06; which of M3 and M4 comes first waits on that decision. Durations are `TBC`; none is committed.

| Milestone | Why here | What it does | Ends in | Duration |
| --- | --- | --- | --- | --- |
| **M1. A filter honest about correlated errors** | The filter trusts slowly varying errors as if they were white: seen with the towers' told sigma (*repo*) and again with a velocity source in the report's scratch run, where adding sources together gained nothing (5, *experiment*; 11.2 item 1) | Correlated-error states and whiteness tests (11.3 item 1; a cited method for learning correlated noise, 16.7, *checked*). Already in hand: learned tower noise (#156, merged), the honest-bound filter (PR #251, merged), the tower error model in the default filter (#77). Run them on the real sessions with GPS cut in software (#256) | HPL bound rate and misleading epochs on the fault scenarios, branch against `main`; the same filters on the real static sessions, better or worse than no towers, with the reason | `TBC` |
| **M2. Heading at GPS loss** | It sets the dead-reckoning error and decides whether a velocity source or a better IMU helps (11.2 item 2) | Heading as an output of the GPS-good phase, with manoeuvres (11.3 item 2); a moving capture with S-turns before a software GPS cut (11.4 item 1; 18.5: a compass-free start needs motion before GPS loss, not hover) and independent truth (RTK, not the GPS under test, #259). A magnetometer is the report's first heading source (17.10); a new heading kind changes the ICD | Heading error at GPS loss against truth on a moving capture; the LTE row of *Sim validity* moved to `measured` for motion; T1's fallback met or missed on real-shaped data with the reason | `TBC` |
| **M3. A velocity source** | Nothing measures velocity (11.2 item 3). In the scratch run velocity with a heading reference was the largest single lever (5, *experiment*, placeholder models) | A velocity source with heading-bias and scale states (11.3 item 7). **Blocked on two open decisions** (below): whether a velocity aid may outrank radio (REQ-06), and whether a light-emitting sensor is receive-only (REQ-07) | `just eval` on the agreed statistic with and without the source, both numbers, and REQ-06's ablation rerun | `TBC` |
| **M4. LTE carrier phase** | Towers are used at code-phase precision; the literature reports 0.37 to 0.89 m on a drone with carrier phase (6.3, *checked*; with line of sight, a GPS-disciplined receiver oscillator and the drone inside one sector). It keeps radio primary (12) | First step with a reference: discipline the dongle from LTE sync timing and measure what is left (18.5); static carrier-phase tracking of Ottawa tower clocks (11.4 item 2). Named risk: no published result without a disciplined receiver clock (16.9, 17.10) | The residual after disciplining, measured on our radio; tower clock drift per operator from a static capture | `TBC` |

Carried over from the earlier plan, after the four above:

| Milestone | What it does | Ends in | Duration (proposed) |
| --- | --- | --- | --- |
| **Earn the integrity case** | Many hours of tower data: fault rates per site, per network and per association type; tail overbounds including the slow error; a per-network timing-source survey. Also from M1's earlier scope: real frequency hopping; re-admitting honest GPS after a long outage (#246); more attacks injected into real recordings; the guard's default-on decision | Fault priors and the integrity risk derived from data instead of `TBC`; the hypotheses as a fault tree an assessor recognises | 9 months, `TBC` |
| **Product receiver with a first operator** | A coherent multi-channel receive-only receiver (several frequencies at once, tower identity from SIB1); a better oscillator and IMU; the warning output to the autopilot; size, weight, power and cost measured | A trial with a first drone operator under a specific-operation risk assessment, with the monitor feeding their autopilot | 12 months, `TBC` |

## Open decisions (#279)

The report raises conflicts with `systems/` (12, 15). They are the owners' to rule on, in #279; nothing here resolves them.

| Item | Conflict | Affects |
| --- | --- | --- |
| REQ-06 (signals of opportunity are primary, shown by ablation) | A velocity or heading aid would outrank LTE in that ablation as things stand; leading with LTE carrier phase keeps radio primary (12; 15 item 1) | M2, M3; the order of M3 and M4 |
| REQ-07 (receive-only) | Every SDR wide enough for full LTE can transmit; flow sensors and lidar emit light; ranging on the control link uses an existing emitter. Each needs a ruling (12; 15 item 2) | M3; the product receiver |
| Build order | The report proposes filter honesty and heading first, then carrier phase (15 item 3) | The milestone order above |
| Product direction | The trust monitor, the fusion engine, or neither yet (15 item 4) | This whole file |
| Third-party code and data | A recorded-spoofing dataset and outside decoders need an owner's go-ahead (12; 15 item 6; `AGENTS.md`) | The first proof |

## Open work items

- Tower error model in the default filter (#77). Since ADR-0047 (our clock in the tower ranges once GNSS time is used), the default `ekf` keeps position after GPS loss but its clock is overconfident: 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets (REQ-03), accepted by the owners on 2026-11-11. `ekf-calibrated`, which models the towers' multipath and correlation, has none. Bring that model into the default, then rerun the time-integrity rows.
- **Drone as a mobile reference station (P12, #96):**
  - *On `main`, sim only (option A):* a tower-map hand-off. A drone with trusted GPS learns the tower clocks, and a GPS-less ground user starts its filter from them (`nav/tower_map.py`, `p12-drone-map-handoff`, `analysis/p12_map_handoff.py`). There is no ICD change: the map never enters a session.
  - *Sim result, realistic-set world, every value `TBC`, 20 seeds at `9a958b1` (unchanged at `f234749` under ADR-0048's export policy: no map withheld), scored as T1 (95th percentile across seeds at each second after GPS loss, worst second, ADR-0034):* over the 300 s after GPS loss the map cut the user's error from 618 m (no aid) to 416 m (map handed over at once) and 310 to 359 m (maps 5 to 30 min old). Over the first 120 s it did not help: 278 m with no aid, 291 m with the freshest map, 219 to 252 m with the older ones. A no-aid filter given the sim's own tower drift spread (0.05 m/s) as its prior did better than every map over 300 s (281 m; 241 m over 120 s), because what the drone learns in a 300 s circuit is looser (drift sigma 0.23 to 0.33 m/s in seed 0's map). Nothing meets T1 or the 50 m / 120 s fallback. Map age up to 30 min made no visible difference at these values. Whether a map beats a prior depends on the real towers' drift spread, which the radio test has to measure.
  - *Trust (ADR-0048):* a spoofed drone hands on clocks that fit the spoofed track, so a learned map is GNSS-derived. By default the drone builds its map with the jump guard and withholds it if the build raised a spoof cue (`analysis/p12_spoofed_map.py`, `analysis/results/p12-spoofed-map/`, 20 seeds, sim). A 300 m jump is caught and the map withheld on 20/20 seeds, and no honest build is withheld. A 2 m/s ramp on four towers is not caught, and its map costs the user 751 m against 416 m honest (T1, 0-300 s).
  - *Roadmap (option B):* a live moving reference that streams its readings for differencing, as the ground station does (P4). It needs an ICD change for a moving reference receiver and its position.

**Certification.** We found no performance standard for this kind of navigation; RTCA SC-159 covers GNSS equipment ([`research.md`](research.md) §3). The report agrees: no standard for opportunistic navigation or for protection levels on non-GPS sources; the nearest framework is the DHS resilient-PNT one, four levels, whose IEEE version is still a draft (10.4, *checked*). The report maps our cross-checking onto its upper two levels; we have not assessed conformance. Route and regulator `TBD` with certification experts. Drones first (UC-01) is likely shorter than crewed approach (UC-02), `TBC`.

**Law and patents (not legal advice).** Radiocommunication Act s.9(2): the report found no case law or ISED guidance on using sync signals, and no research or navigation exception in the regulations (10.4, 17.8, *checked*). Our position is unchanged ([`safety.md`](safety.md) *Legal*, ADR-0011): we decode only signals meant for everyone, and that is our reading; a legal opinion is needed before selling. The University of California holds patents on LTE opportunistic navigation and on a LEO Doppler receiver (10.4, 17.8; three read at source, `reports/research-round2/gnss-integrity-algorithms-market.md` *Topic 12*); we have not assessed them, and a freedom-to-operate check is needed before a product. Later layers: 5G sync blocks, navaids, and the LEO layer (Iridium and Starlink, simulated).

## What we will not claim

- A certified, measured or validated accuracy or integrity level.
- A useful position from real towers: on our real static sessions LTE made position worse than none.
- Real-world numbers from simulation runs.
- "First": the wording is "we found no published…" ([ADR-0021](adr/0021-what-we-build-and-pitch.md)).

---

*Status: 2026-11-11; product, buyers, proof and milestone order rewritten from the research report on `main` at `3493cfb` (#273; decisions open in #279). Before that: against `main` at `c21e047`; brought up to `c97e09a` (#245, ADR-0047, ADR-0048), then `2499f87` (open PRs #156, #247, #251, #262, #263). Still open: combined fixes (#218, draft PR #247). Merged since: real GPS cut (#214, #233), spoof decision (#206, #239), tower count (#208, #232), heat map (#207, #235). Sources per row: [`results.md`](results.md).*
