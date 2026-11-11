# ADR-0042: Record the radios' IQ to a USB drive, not the SD card

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners accept or change it)
- **Traces to:** REQ-01, REQ-09, REQ-10, RSK-05, RSK-06, ADR-0018, #88, #53

## Context

ADR-0018 lets the payload record to "a fast A2 microSD card or a USB SSD", with the choice open. The first two full-suite sessions on the payload Pi 4B ([`deploy/pi/DAY1-RESULTS.md`](../../deploy/pi/DAY1-RESULTS.md)) recorded both radios at 1.92 + 2.4 MS/s (8.64 MB/s), the same setup each time except where the IQ went:

| Session | IQ written to | Sample gaps (SDR A / SDR B) | IQ kept of 600 s |
| --- | --- | --- | --- |
| `20261111-0040-static-fullsuite` | SD card | 4 / 4, at the same instants on both radios, 1.2–8.4 s each | 582.3 s (97.1 %) |
| `20261111-0151-static-fullsuite2` | SanDisk USB 3.2 Gen 1 drive, ext4, on a USB 2 port | 0 / 0 | 599.4 s |

Gaps at the same instants on both radios, at low CPU and memory load, point to the card: the drive removed them. Each gap is a jump in the dongle clock that the LTE front end must size, and loses up to 8 s of every radio source.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. SD card (as recorded on 0040) | Nothing extra to mount or power | 4 gaps in 10 min, 2.9 % of the IQ lost, both radios at once |
| B. USB drive on a USB 2 port (as recorded on 0151) | No gap in 10 min; keeps both radios at full rate; the USB 3 ports stay empty (ADR-0018, RSK-06) | One more part to mount, power and secure in the payload box; one 10 min run only; it shares the USB 2 bus with both SDRs |
| C. USB SSD on a USB 3 port | Most bandwidth headroom | USB 3 noise near GPS L1 and 2.4 GHz (RSK-06); not tested |
| D. Keep the SD card, record one radio, or at a lower rate | No new part | Loses simultaneous LTE and ADS-B, or decoder margin |

## Decision

Proposed: option B, recording IQ to a USB drive on a USB 2 port. The owners accept or change this.

## Consequences

- `pnt record` and `deploy/pi/day1.sh` take the session root on the drive (the payload's mount point, `/mnt/pntdata` on 2026-11-11, is `TBC` as a permanent path). `RUNBOOK.md` says how to mount it before a capture.
- The board capture profile (`capture-pi4b`, #53) is measured on the SD card. With option B its gap rate would be the drive's: 0 in 600 s, which bounds it below about 0.3 per minute (95 %), not at zero. Until a longer run, `gaps_per_min` for the drive is `TBC`.
- Mass and power of the drive in the payload box: `TBC` (DPS-150).
- **Reopen if:** a longer capture (≥ 1 h, the LTE timing run of #21) shows gaps on the drive, or the drive's USB traffic raises the SDR or GPS noise floor.
