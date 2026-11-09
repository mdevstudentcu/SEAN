# ADR-0024: Every source carries a GNSS-dependency tag, and dependent evidence fails with GPS

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-02, REQ-03, REQ-04, ADR-0006, ADR-0022

## Context

`systems/safety.md` already states the rule: sources that fail together with GPS are not counted as independent evidence. Nothing in the code enforces it. Without it, a coherent spoof can be "confirmed" by its own echoes.

"Does it fail with GPS?" has three answers, not two:

- **Independent:** the signal and its timing owe nothing to GNSS.
- **GNSS-timed:** the signal is independent, but the transmitter's clock is GNSS-disciplined. Tower ranges survive jamming, but tower clocks drift in holdover or follow a time spoof (ADR-0022). Most North American public-safety radio networks reported faults during the January 2016 GPS timing error of 13.7 µs ([RNT Foundation](https://rntfnd.org/?p=8133)).
- **GNSS-derived:** the content itself is someone's GNSS fix. ADS-B position reports are the aircraft's own GNSS. During spoofing, Aireon saw aircraft integrity indicators stay high while tracks jumped ([Aireon](https://aireon.com/countering-gnss-spoofing-aireons-global-ads-b-network-delivers-trust/)).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. No tags; every source counts as independent (today) | Nothing to build | A spoof echoed by ADS-B and captured tower time looks like agreement |
| B. Two classes: independent or GNSS-dependent | Simple | Throws away tower geometry, which survives a GNSS fault even though tower time does not |
| C. Three classes: independent, GNSS-timed, GNSS-derived | Keeps tower geometry and drops only tower time; matches how each source actually fails | One more rule for integrity to apply |

## Decision

Every measurement source carries one of three GNSS-dependency tags (independent, GNSS-timed or GNSS-derived), and integrity treats GNSS-timed and GNSS-derived evidence as failing with GPS, so it is never counted twice as independent.

| Tag | Sources | What integrity does with it |
| --- | --- | --- |
| Independent | Barometer, IMU, our own oscillator in holdover, VOR, DME, ILS | Can confirm or refute GNSS |
| GNSS-timed | LTE towers, P25 | Inside the GNSS common-mode hypothesis for time and for the builder clock term. Differences between towers still count as geometry. Can never confirm GNSS time |
| GNSS-derived | ADS-B positions, Remote ID, SBAS, our own GPS | Inside the GNSS common-mode hypothesis. Never confirms GNSS |

## Consequences

- **REQ-04 verdicts** (trust or reject GPS) rest only on independent evidence and on the geometry of GNSS-timed sources. Agreement from GNSS-derived content is not evidence.
- **Learned priors inherit the dependency.** Tower clocks learned while GNSS is trusted (ADR-0022) are GNSS-timed. A prior learned under an undetected spoof is poisoned, which is why that calibration is discarded when GNSS is flagged.
- **Our own oscillator** is GNSS-disciplined while GPS is available and independent only in holdover. Its tag therefore applies from the moment GNSS is excluded.
- **Classification continues.** Sources in the ICD registry that are not listed above (`nr`, `wifi`, `ble`, `fm`, `leo`, `cam`) are `TBD`. Until a source is classified, it is treated as GNSS-dependent (the conservative default).
- **Not received:** P25 and Remote ID are listed so their class is on record. We don't receive P25: it is communication content. Remote ID is sim only, because storing an operator's location conflicts with ADR-0011. SBAS is sim only.
- **Display:** the operator panel shows each source's tag next to its trust (I17).
- **Where the tag lives: a lookup table in `integrity/`,** keyed by `source` (and `kind` where it differs). Decided 2026-11-09, over a field in `Measurement`.
  - The tag belongs to the source type, not to each record, so a per-record field would repeat the same value.
  - The one runtime change, our oscillator becoming independent in holdover, is integrity logic either way.
  - This ADR changes nothing in the ICD.
- **Reopen if:**
  - a source is shown to keep time independently of GNSS (for example, a builder with a non-GNSS timing source)
  - a new source class does not fit the three tags
