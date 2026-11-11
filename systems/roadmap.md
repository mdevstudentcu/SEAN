# D3: Roadmap to a commercial alternative-navigation product

- **Status:** Draft, 2026-11-11 (#28), against `main` at `c21e047`. The humans own the final D3.
- **Honesty rule:** nothing here claims a measured accuracy, integrity level or certification status. Every number is in [`results.md`](results.md) with its kind and source. Dates after judging are `TBD`.

## Where we are on judging day

| Area | State | Source |
| --- | --- | --- |
| Payload, LTE front end, cell lookup, estimators, integrity, panel, authenticated live link | Built on `main` | [`architecture.md`](architecture.md) |
| Real signals | Static sessions: LTE at two spots (no GPS), ADS-B, a GPS HAT session with PPS, the IMU overnight. LTE precision at rest measured; no real position yet | [`results.md`](results.md) (a) |
| Targets | T1 Accepted with the mentors' fallback; T3–T5 Proposed; jump target `TBD` (ADR-0034) | [`plan.md`](plan.md) |
| Sim results on records shaped like real ones | T1 and fallback missed; T3, T5 and the position ramp missed; jumps detected, time ramp detected, false-alarm rate met | [`results.md`](results.md) (b) |
| Error models | IMU `measured`; LTE measured at rest but not yet moved (ADR-0036, Proposed); the rest `placeholder` | [`verification.md`](verification.md) *Sim validity* |
| Fault priors, integrity risk, continuity budget | `TBC` (`integrity/mhss.py`) | [`verification.md`](verification.md) |
| Reference station, LEO, hostile emitter | Sim only (ADR-0020 *Amendment 2026-11-10*, ADR-0013, ADR-0025) | — |
| Novelty | Checked against the closest full papers; IEEE Xplore and ION not searched in full text | [`research.md`](research.md) *Novelty check* |

## What the week showed, and what fixes it

In the order the evidence says they matter. A fix is a proposal until the owners decide it.

| # | Finding | Evidence | Fix | State |
| --- | --- | --- | --- | --- |
| 1 | **The front end's reported σ sees only white noise; the filter believes it**, so LTE made position worse than none | Sim: #137, #147. Real: an 8.3 m median correlated part the reported σ cannot see (ADR-0036) | Learn each cell's noise (#156); split white and correlated error, sized from captures (ADR-0036) | #156 opt-in, draft, ADR-0039 Proposed: drone leg better, timing leg still worse with LTE |
| 2 | **One carrier hears 1 to 4 cells, often sectors of one site** | Real captures (ADR-0036); synthetic near-far limit (#133) | Hop carriers with one dongle (#179, ADR-0040 Proposed); coherent integration (#171, merged); how many towers are enough with baro and IMU: `TBD (#208)` | Sim and synthetic only; real hopping untested |
| 3 | **A detected jump was followed** | Sim: #176, #180 | Refuse it until the GNSS stream steps back (#191) | Merged, opt-in (ADR-0038 Proposed). Default-on waits on latching only when an IMU or enough towers give an independent coast |
| 4 | **Deciding whether GNSS is spoofed** is what the mentors care about most | Call of 2026-11-10 | One spoofed-or-not output from signal power, the known sky and the other sensors: `TBD (#206)`; tower monitor for slow ramps (#180, ADR-0037 Proposed) | Separate cues exist (jump guard, C/N0 indicator, ADS-B warning); no sky-map check or single output yet |
| 5 | **Confidence is honest only where the model is**: MHSS safe but unavailable; `ekf-calibrated` confident on a wrong tower table | Sim: #170, #133, #132 | An honest tower model; a mapper for unregistered cells (ADR-0023); a confidence heat map for the operator `TBD (#207)` | Open |
| 6 | **The sim's values are placeholders** | *Sim validity* | Move rows to `measured`, then `validated` (ADR-0015); first real error after GPS loss `TBD (#214)` | IMU measured; LTE at rest measured, not adopted |
| 7 | **Real captures break the front end's assumptions** | Real: 200 Hz carrier aliases, weak cells breaking 19 to 105 times a minute (#183) | Flag and drop aliased Doppler; treat a re-found cell as a new arc (ADR-0036) | Open |

## Phases

Each phase ends with evidence, not a date. Durations `TBD`.

**0. Close the week's loop.** Run the fixes together on the agreed statistic (`TBD (#218)`) and one real session with GPS cut in software (`TBD (#214)`). Exit: T1's fallback met or missed on the `challenge` drone leg with the reason stated; the guard's default-on decision taken.

**1. Measure the sensor (ADR-0015).** Moving captures with independent truth (RTK, not the GPS under test); long static captures of several sites per builder; real carrier hopping; attacks injected into real recordings beside the sim results. The reference station on hardware if a second LTE receiver and a PPS GPS are bought (ADR-0020 *Reopen if*).

**2. Characterise integrity parameters.** Signals of opportunity have no integrity support message and no published fault statistics (Jia, Khalife & Kassas 2023, [`research.md`](research.md)). Fault rates per site, per builder and per association type from many hours of data; tail overbounds including correlated error; a per-builder timing-source survey; the hypotheses as a fault tree.

- Tower error model in the default filter (#77). Since ADR-0047 (our clock in the tower ranges once GNSS time is used), the default `ekf` keeps position after GPS loss but its clock is overconfident: 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets (REQ-03), accepted by the owners on 2026-11-11. `ekf-calibrated`, which models the towers' multipath and correlation, has none. Bring that model into the default, then rerun the time-integrity rows.

**3. Product hardware, still receive-only (REQ-07).** A coherent multi-channel wideband receiver (several carriers at once, SIB1 to confirm tower identity, ADR-0023); a better oscillator and IMU; 5G NR sync blocks and navaids, each with its dependency tag ([ADR-0024](adr/0024-gnss-dependency-tags.md)); the LEO layer (simulated: Iridium, ADR-0013, and Starlink, #172).

**4. Integrate as a layer.** Honeywell's alternative-navigation suite lists radios without a product ([`research.md`](research.md) §3). This is that terrestrial-communications layer: position, time, protection levels and per-source trust as an aid to the host's navigation; interface standard `TBD` with Honeywell. Option: reference stations that measure tower clocks for many users.

- **Drone as a mobile reference station (P12, #96):**
  - *On `main`, sim only (option A):* a tower-map hand-off. A drone with trusted GPS learns the tower clocks, and a GPS-less ground user starts its filter from them (`nav/tower_map.py`, `p12-drone-map-handoff`, `analysis/p12_map_handoff.py`). There is no ICD change: the map never enters a session.
  - *Sim result, realistic-set world, every value `TBC`, 20 seeds at `9a958b1`, scored as T1 (95th percentile across seeds at each second after GPS loss, worst second, ADR-0034):* over the 300 s after GPS loss the map cut the user's error from 618 m (no aid) to 416 m (map handed over at once) and 310 to 359 m (maps 5 to 30 min old). Over the first 120 s it did not help: 278 m with no aid, 291 m with the freshest map, 219 to 252 m with the older ones. A no-aid filter given the sim's own tower drift spread (0.05 m/s) as its prior did better than every map over 300 s (281 m; 241 m over 120 s), because what the drone learns in a 300 s circuit is looser (drift sigma 0.23 to 0.33 m/s in seed 0's map). Nothing meets T1 or the 50 m / 120 s fallback. Map age up to 30 min made no visible difference at these values. Whether a map beats a prior depends on the real towers' drift spread, which the radio test has to measure.
  - *Trust:* a spoofed drone hands on clocks that fit the spoofed track. The map is one more fault hypothesis, not truth, and nothing tests it yet.
  - *Roadmap (option B):* a live moving reference that streams its readings for differencing, as the ground station does (P4). It needs an ICD change for a moving reference receiver and its position.


**5. Certify.** No performance standard exists for SoOP navigation; RTCA SC-159 covers GNSS equipment ([`research.md`](research.md) §3). Route and regulator `TBD` with certification experts. UAS (UC-01, a specific-operation risk assessment) is likely shorter than crewed approach (UC-02), `TBC`. The receive-only, broadcast-only position ([`safety.md`](safety.md)) needs a legal opinion, not our reading.

## What we will not claim

- A certified, measured or validated accuracy or integrity level.
- Position from real towers, until #214 shows one.
- Real-world numbers from sim runs.
- "First": the wording is "we found no published…" ([ADR-0021](adr/0021-what-we-build-and-pitch.md)).
