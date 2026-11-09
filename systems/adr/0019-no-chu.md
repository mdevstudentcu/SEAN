# ADR-0019: Drop CHU broadcast time

- **Status:** Proposed
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-03, RSK-07; ICD-measurement

## Context

The scaffold listed the NRC's CHU shortwave time station (3.33, 7.85 and 14.67 MHz) as a quick-win time source (RSK-07). Two things rule it out:

- **It is off the air.** NRC ended CHU's shortwave broadcasts on 2026-06-22 ([Wikipedia](https://en.wikipedia.org/wiki/CHU_(radio_station)), [SWLing Post](https://swling.com/blog/2026/06/chu-closure-on-june-22-2026/)). NRC's own CHU page returned 404 on 2026-11-08, so the date rests on secondary sources plus recordings of the final transmissions.
- **Our radios can't tune it.** The NESDR SMArt v5 and FlightStick use the R820T2 tuner, whose range starts at 24 MHz, and neither supports direct sampling; HF needs an upconverter or a different SDR, and none arrives before Tuesday (`hardware/bom.md`).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Drop CHU; no broadcast time source this week | Nothing to build; matches what we can receive | No absolute time once GPS is lost: timing rests on the clock states in `nav/ekf.py` |
| WWVB (60 kHz, Colorado) | Still on air | Needs an LF receiver and antenna we don't have; weak in Ottawa by day |
| FM RDS clock time (group 4A) | Our SDR tunes FM | Minute resolution, stations' clocks unverified; a new ADR if wanted |

## Decision

Drop CHU: remove `chu` from the `source` registry and every reference, and add no broadcast time source in this decision.

## Consequences

- REQ-03 timing during GPS loss relies on the receiver clock model and oscillator holdover. Using an LTE carrier as a frequency reference is a separate, open idea.
- `chu` leaves `systems/icd/measurement.md` and `SOURCES` in `src/pnt/core/measurement.py` (ICD change: `icd` label, other owner's approval). No sim scenario or session uses it.
- The "CHU time" Sim validity row and the `chu.csv` TODO are removed.
- Reopen if an HF-capable SDR or LF receiver is in hand and another broadcast time station is worth the work.
