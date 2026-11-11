# ADR-0041: Decide GNSS spoofing from the known sky, the satellites' power and the other cues

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** the two owners
- **Traces to:** REQ-02, REQ-04, ADR-0021, ADR-0031, ADR-0037 (#180, Proposed), ADR-0038, #206

## Context

On the 2026-11-10 call (`transcript-speakers.srt_v1.md`, lines 265 to 305) the mentor said deciding *whether* GNSS is spoofed matters more than handling it. They asked for a function that decides from the power we can read and from the known sky: a satellite received that cannot be visible means spoofing.

We had separate cues and no decision: the jump guard (ADR-0038, opt-in) refuses a GNSS jump; the towers' check (`spoof_suspected`, #83; the tower monitor, ADR-0037, unmerged) raises the same flag; the jam indicator (ADR-0031) reads C/N0 but only for jamming. Nothing read the sky.

What we have to work with: the payload records gpsd's SKY reports as `gnss_sky` events, with each satellite's C/N0 (`ss`, dB-Hz) and `used`, but no elevation or azimuth. The GPS HAT sends a satellite list every 5 s. CelesTrak publishes GPS orbital elements, and `sgp4` is already a dependency (`pnt.sim.leo`).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Sky map only: received PRNs against predicted elevation | Hard evidence: no real signal comes from below the horizon; the mentor's example | Blind to a spoofer that simulates the right sky for our place and time |
| B. Power pattern only: C/N0 spread and its correlation with predicted elevation | Catches a single-antenna spoofer that gets the sky right | Soft: a blocked or indoor antenna also flattens the pattern; thresholds need real data |
| **C. Both, combined with the estimator's spoof cues into one advisory level per epoch** | One answer for the operator, with the cue that fired; each cue's weight follows how hard its evidence is | Weights and thresholds are new placeholders |
| D. C, and the level excludes GNSS from the filter | Acts on it | A false power alarm would cost accuracy; the jump guard already acts on jumps; the mentor asked to decide, not handle |

## Decision

Option C, **advisory**: `pnt.integrity.sky.SpoofDecision` reads each skyview and the estimate's flags, and changes no estimate. Default estimator output is unchanged (hash-checked against `main`, see the PR).

- **Almanac:** `data/reference/tle-gps-20261111.txt` (CelesTrak `gps-ops`, 2026-11-11), propagated with SGP4. Each GPS PRN (1 to 32) received with C/N0 above 0 gets a predicted elevation at the receiver's position (the latest estimate on the panel) and the skyview's time. Other constellations are not judged.
- **Sky cue** (`sky_below_horizon`): a received PRN predicted below `SKY_MASK_DEG` = −5° (`TBC`: margin for the TLE's age and the position's error).
- **Power cue** (`power_flat`): with at least 5 judged PRNs above the mask (`TBC`), the C/N0 spread (sample standard deviation) is under 3 dB, or the correlation of C/N0 with predicted elevation is under 0.2 (both `TBC`). Off while the jam indicator is 0.5 or more (`TBC`), since jamming flattens C/N0 too.
- **Held:** a sky cue counts as held once seen on 2 skyviews in a row (`TBC`; 5 to 10 s on the GPS HAT); one skyview without it clears it.
- **Combination:** noisy-OR of cue strengths, `score = 1 − ∏(1 − s)`:

| Cue | Strength | Why |
| --- | --- | --- |
| `sky_below_horizon` | 0.5 first skyview, 1.0 held | No real signal comes from below the horizon; held, that alone is spoofing |
| `power_flat` | 0.25 first, 0.5 held | Blockage or a poor antenna can flatten the pattern: alone it is only suspect |
| `jump_latched` (estimate flag `gnss_jump_latched`, new, set only by the `-guard` estimators) | 0.5 | A jump can be a receiver re-solve or multipath (ADR-0038) |
| `towers_refute` (estimate flag `spoof_suspected`) | 0.5 | The towers can be wrong too |

- **Levels:** `spoofed` at a score of 0.75 or more (a held sky cue alone, or two independent cues at 0.5), `suspect` above 0, `not_spoofed` at 0 with a skyview in the last 15 s, `unknown` otherwise: no sky data is not evidence of no spoofing.
- **Panel:** a card under the status, green, amber, red or grey, with the cue in words and the score.
- **Sim:** `sky:` on a scenario's GNSS source gives its `gnss_health` records per-PRN C/N0 every 5 s on its own random stream; `fake_sky` (software fault injection, `pnt.sim.attacks`) sets every C/N0 to one value and/or adds PRNs below the horizon. `spoof-jump-sky` is `spoof-jump` with both.

Thresholds were set from one real session, `20261111-0040-static-fullsuite` (GPS HAT, external active antenna, static, outdoors, PPS-locked; receiver position withheld for privacy): over 120 skyviews, 7 to 11 GPS PRNs judged, none predicted below −5° (lowest tracked 8.7°), C/N0 spread 7.6 to 13.3 dB and correlation 0.66 to 0.83. Each threshold sits well outside that range.

## Consequences

Evidence (`analysis/spoof_sky.py --runs 20`, numbers in `analysis/pr-evidence/shrikar-feat-206-spoof-decision/summary.md`):

- **Real sky, as recorded:** 0 false alarms in 120 skyviews (595 s). With `ekf-guard` on the session's fixes and barometer, 0 false alarms in 6,001 estimates and no false latch. Ten minutes is far too little to show REQ-04's 1 per hour.
- **Fake skies injected into the real session at 300 s:** every faked skyview is flagged. PRNs below the horizon: suspect at the first faked skyview (5.0 s), spoofed at the second (10.0 s). Equal power alone: suspect at 5.0 s and never red, by design. Equal power plus a 300 m jump through `ekf-guard`: suspect 0.1 s, spoofed 10.0 s.
- **Sim `spoof-jump-sky`, seeds 0-19:** 0 false alarms on the clean runs and before the spoof. `ekf-guard` reaches spoofed 5.0 s after the spoof on 20/20 runs; `ekf` stays at suspect on 20/20, because its towers never raised `spoof_suspected` on these runs.
- **Not caught:** a spoofer that simulates the right sky for our place and time and shapes each satellite's power with elevation; a multi-antenna spoofer. Those need the towers (ADR-0037) or the IMU.
- **Power check risk:** a skyview from a blocked, indoor or drone-mounted antenna may read flat. Untested; the first such session reopens the power thresholds.
- **Almanac age:** the TLE file must be replaced before a session weeks later (GPS satellites manoeuvre). The −5° mask leaves room for days of age.
- **Opt-in pieces:** only `-guard` estimators set `gnss_jump_latched`, and only scenarios with `sky:` carry a sky, so every other scenario and every default estimator output is unchanged.
- **Reopen if:** a real session shows a flat pattern without spoofing; REQ-04 sets a false-alarm budget; the owners want the level to act on the filter (option D); or elevation and azimuth are recorded at capture (the receiver's own sky, no almanac needed).
