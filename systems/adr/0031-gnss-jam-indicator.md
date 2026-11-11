# ADR-0031: The GNSS jam indicator is the C/N0 drop of the strongest satellites

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** team
- **Traces to:** REQ-04, ADR-0014, ICD-measurement (`gnss_health`), sim plan D3

## Context

`gnss_health` carries `(jam_indicator, n_sats, hdop)`. The sim emits a jam indicator in [0, 1] (`pnt.sim.attacks`), but the GPS HAT's MediaTek receiver has no jamming flag (ADR-0014). What it does report, through gpsd, is each satellite's C/N0 (NMEA GSV, gpsd `ss`, dB-Hz). Sim plan D3 asked what the indicator means on real hardware.

Jamming raises the noise floor, so every satellite's C/N0 falls together. Blockage lowers some satellites and removes others. Spoofing often raises C/N0.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. No real `gnss_health` (today) | Nothing to tune | Real sessions have no jamming cue; the sim's is untested against anything |
| B. C/N0 drop of the `k` strongest satellites against a fixed open-sky level | One number per SKY report, causal, cheap; the strongest satellites are the ones the fix rests on | Needs an open-sky level per antenna; can't tell jamming from blockage |
| C. Drop against a level learned at the start of each session | No per-antenna constant | Wrong for the whole session if it starts indoors or jammed |
| D. Spread of C/N0 across satellites, or C/N0 against elevation | Separates blockage (uneven) from jamming (even) better | Needs elevation-dependent models we have not measured; more to tune |

## Decision

Option B: `S` is the mean C/N0 of the 4 strongest satellites, a missing one counting as the loss level, and the indicator is `(ref - S) / (ref - low)` clipped to [0, 1], with `ref` = 40 dB-Hz and `low` = 25 dB-Hz (all three `TBC`).

## Consequences

- `pnt.frontends.gnss` computes it from the `gnss_sky` events the payload already records, and `pnt frontend gnss <session>` writes `gnss_health` into a derived session. The payload only adds `listed` to each `gnss_sky` event: whether gpsd sent a satellite list, so an empty sky can be told from a report without one.
- `ref`, `low` and `k` are `TBC` until a static open-sky session with the GPS HAT sets `ref` (the median of `S`) and shows where satellites drop out (`low`). They are command-line options until then.
- The indicator says "GNSS signal degraded", not "jammed": indoors or under trees it rises too. Integrity must treat it as a cue, not as proof of an attack.
- It does not see spoofing. A spoof cue from C/N0 (too high, too uniform) would be a separate decision.
- Each SKY report is stamped on arrival, not at its measurement epoch; the latency is `TBD` (gpsd sends SKY about once a second).
- **Reopen if** a real session shows blockage and jamming need telling apart (option D), or a receiver with a jamming flag replaces the HAT.
