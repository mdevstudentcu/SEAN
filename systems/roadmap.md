# D3: Roadmap from hackathon to a product

- **Status:** Draft, 2026-11-10 (#28). The humans own the final D3 and the deck; this is the draft they build from.
- **Honesty rule:** nothing below claims a measured accuracy, integrity level or certification status. Every number is in [`results.md`](results.md) with its source; dates past judging are `TBD`.

## Where we are on judging day

| Area | State | Source |
| --- | --- | --- |
| Payload, LTE front end, cell lookup, estimators, integrity, operator panel, authenticated live link | Built on `main` | [`architecture.md`](architecture.md) |
| Real signals | LTE cells tracked and matched to the registry at two spots, static, one dongle, no GPS truth; IMU noise measured overnight | [`results.md`](results.md) §5 |
| Targets T1–T5 | Ours, `TBC`; T1's fallback is the mentors' figure (ADR-0034, open PR #158) | [`plan.md`](plan.md) |
| Results on records shaped like real ones (sim) | T1, T3, T5 and the position ramp missed; time-spoof detection and false-alarm rate met | [`results.md`](results.md) §1 |
| Error models | `placeholder`, except the IMU measured in open PR #157 | [`verification.md`](verification.md) *Sim validity* |
| Fault priors, continuity budget, integrity risk | `TBC` (`integrity/mhss.py`) | [`verification.md`](verification.md) |
| Ground reference station, LEO, hostile emitter, drone as reference | Simulation only | ADR-0020, ADR-0013, ADR-0025, P12 |
| Novelty | Checked against the closest full papers; several still unread | [`research.md`](research.md) *Novelty check* |

## What the week showed, and what fixes it

In the order the evidence says they matter. Each fix is a proposal until an owner decides it; a new approach gets an ADR.

| # | Finding | Evidence | Fix | State |
| --- | --- | --- | --- | --- |
| 1 | **The front end's reported sigma is optimistic, and the filter believes it.** It sees the white noise, not multipath (#147) or the slow wander (#177), so the filter rejects or overweights towers and LTE makes position worse than none | Sim: #137, #147, #170. Real: reported σ 3 to 8 times below the observed spread (2026-11-10 captures) | Size the range error apart from the reported sigma: learn it from innovations (#156), a floor, or a model sized from real captures (#118). Needs an ADR once chosen | #156 draft, *Not ready*: helps the drone leg's mean, raises hazardous epochs |
| 2 | **One carrier hears 1 to 3 towers.** The front end loses a cell 13 dB below a strong one, and near a mast every other tower is further down | Synthetic: #133, #131. Real: 1 to 3 cells per carrier at two spots | Hop carriers with one dongle (#179: in sim, a factor of five once #1 is fixed); coherent integration for a static receiver (#171, -11 to -14 dB); cancel the strong cell's sync signals; more coherent channels in a product | Sim and synthetic only. Real hopping untested; hop set open (#179) |
| 3 | **A detected location jump is followed, not refused** | Sim: #176, #180, #184 | Keep GNSS position out once flagged; let it back only when it agrees with what the filter holds without it, by a stated test (#184) | Not started |
| 4 | **A slow position ramp is caught only where at least 5 sites are heard, in minutes** | Sim: #170, #180 | Adopt #180's monitor or another, after #1 and #2 raise the sites heard. Whether to narrow ADR-0021's pitch wording to what is shown is the owners' open question | #180 opt-in, open |
| 5 | **`ekf-calibrated` stays confident on a wrong tower table; MHSS is safe but unavailable** | Sim over real positions: #133, #132; sim: #176 | An honest tower model so MHSS subsets are consistent; a mapper for cells not in the table (ADR-0023) | Open |
| 6 | **The sim's values are placeholders** | [`verification.md`](verification.md) *Sim validity* | Move each row to `measured`, then `validated` (ADR-0015): first real numbers for LTE in #177 and the capture summary; IMU in #157 | IMU measured (open PR); LTE started |
| 7 | **The front end crashed on real captures** | Real: #181 | Covariance reset on re-found cells (#182, #177); real-capture oddities in #183 | Fix in open PRs |

## Phases

Each phase ends with evidence, not a date. Durations are `TBD`.

### 0. Fix what the week found

Rows 1 to 4 above, then re-run the challenge baseline (#170) paired against it. Exit: T1's fallback (50 m for 120 s) met or missed on the `challenge` drone leg with the reason stated, and a jump refused, not followed.

### 1. Measure the sensor (ADR-0015)

- Long static captures of several sites per network builder: noise, multipath, clock offset, drift and jumps. Does a common term exist within a builder ([ADR-0022](adr/0022-tower-clock-model.md))?
- Real carrier hopping, and how many masts it hears at a known spot.
- Walk, drive and flight sessions with independent truth (RTK, not the GPS under test).
- Reference station hardware and its zero-baseline test (#84 to #86).
- Attacks injected into real recordings beside the pure-sim results.

### 2. Characterise integrity parameters

Signals of opportunity have no integrity support message and no published fault statistics (Jia, Khalife & Kassas 2023).

- Fault rates per site, per builder and per association type from many hours of data, replacing the `TBC` priors.
- Error overbounds that hold in the tails, including time-correlated errors.
- A per-builder timing-source survey: which networks are GNSS-disciplined, and their holdover class.
- The fault hypotheses as a fault tree a safety assessor recognises.
- Tower error model in the default filter (#77). Since ADR-0047 (our clock in the tower ranges once GNSS time is used), the default `ekf` keeps position after GPS loss but its clock is overconfident: 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets (REQ-03), accepted by the owners on 2026-11-11. `ekf-calibrated`, which models the towers' multipath and correlation, has none. Bring that model into the default, then rerun the time-integrity rows.

### 3. Product hardware (still receive-only, REQ-07)

- A coherent multi-channel wideband receiver: several carriers at once instead of hopping, and SIB1 decoding to confirm tower identity instead of inferring it (ADR-0023).
- A better oscillator for time holdover (UC-03) and a tactical-grade IMU.
- More signal families, each with its GNSS-dependency tag ([ADR-0024](adr/0024-gnss-dependency-tags.md)): 5G NR sync blocks; VOR, ILS and DME (P9).
- **The LEO layer.** Iridium is simulated (ADR-0013; the mentors accepted that) and Starlink too (#172). In the sim's kind case the towers-only p95 falls from 19.8 m to 8.0 m with Iridium and to 4.4 m with Starlink (`ekf`, [`results.md`](results.md) §6, every LEO value `TBC`). A real Starlink receiver needs a Ku-band LNB and downconverter; Iridium needs the Iridium PNT hardware we don't have ([`mentor-qa.md`](mentor-qa.md) Q5).
- Tamper-evident logs (hash chain, [ADR-0026](adr/0026-ground-link-security.md)) and per-deployment keys.

### 4. Integrate as a layer

- **Where it fits:** Honeywell's alternative-navigation suite lists radios without a released module ([`research.md`](research.md) §3). This is that terrestrial-communications layer, with timing as a second output.
- **Interface:** position, time, protection levels and per-source trust as an aid to the host's integrated navigation. Interface standard `TBD` with Honeywell.
- **Network option:** reference stations that measure tower clocks continuously for many users (P4, P12).
- **Drone as a mobile reference station (P12, #96):**
  - *On `main`, sim only (option A):* a tower-map hand-off. A drone with trusted GPS learns the tower clocks, and a GPS-less ground user starts its filter from them (`nav/tower_map.py`, `p12-drone-map-handoff`, `analysis/p12_map_handoff.py`). There is no ICD change: the map never enters a session.
  - *Sim result, realistic-set world, every value `TBC`, 20 seeds at `9a958b1` (unchanged at `f234749` under ADR-0048's export policy: no map withheld), scored as T1 (95th percentile across seeds at each second after GPS loss, worst second, ADR-0034):* over the 300 s after GPS loss the map cut the user's error from 618 m (no aid) to 416 m (map handed over at once) and 310 to 359 m (maps 5 to 30 min old). Over the first 120 s it did not help: 278 m with no aid, 291 m with the freshest map, 219 to 252 m with the older ones. A no-aid filter given the sim's own tower drift spread (0.05 m/s) as its prior did better than every map over 300 s (281 m; 241 m over 120 s), because what the drone learns in a 300 s circuit is looser (drift sigma 0.23 to 0.33 m/s in seed 0's map). Nothing meets T1 or the 50 m / 120 s fallback. Map age up to 30 min made no visible difference at these values. Whether a map beats a prior depends on the real towers' drift spread, which the radio test has to measure.
  - *Trust (ADR-0048):* a spoofed drone hands on clocks that fit the spoofed track, so a learned map is GNSS-derived. By default the drone builds its map with the jump guard and withholds it if the build raised a spoof cue (`analysis/p12_spoofed_map.py`, `analysis/results/p12-spoofed-map/`, 20 seeds, sim). A 300 m jump is caught and the map withheld on 20/20 seeds, and no honest build is withheld. A 2 m/s ramp on four towers is not caught, and its map costs the user 751 m against 416 m honest (T1, 0-300 s).
  - *Roadmap (option B):* a live moving reference that streams its readings for differencing, as the ground station does (P4). It needs an ICD change for a moving reference receiver and its position.

### 5. Certify

- **No performance standard exists for SoOP navigation;** RTCA SC-159 covers GNSS equipment ([`research.md`](research.md)). The route (a new standard, or an equivalent level of safety case by case) and the regulator are `TBD` with Honeywell's certification experts.
- **UAS first** (UC-01, an operational risk assessment for a specific operation) is likely the shorter path; crewed approach (UC-02) the longer. Both `TBC`.
- **Timing (UC-03):** holdover stated against telecom holdover masks and the DHS resilience levels we already report; the masks are `TBC`.
- **Spectrum and legal:** the receive-only, broadcast-fields-only position ([`safety.md`](safety.md)) needs a legal opinion, not our reading.

## What we will not claim on stage

- A certified, measured or validated accuracy or integrity level.
- Position from real towers: not shown yet.
- Real-world numbers from sim runs. Every result is labelled sim, synthetic, registry or real.
- "First": the wording is "we found no published…" ([ADR-0021](adr/0021-what-we-build-and-pitch.md)).
