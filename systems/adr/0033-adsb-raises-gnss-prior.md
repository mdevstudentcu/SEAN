# ADR-0033: ADS-B interference evidence raises the GNSS fault prior

- **Status:** Proposed
- **Date:** 2026-11-10, amended 2026-11-10 (the warning is not a REQ-04 alarm, decided by the owner: see *Amendment*)
- **Deciders:** Shrikar Vempati, M. Elshoubky (the two owners)
- **Traces to:** REQ-04, REQ-02, UC-02, ADR-0024, ADR-0022, threat-model.md (UC-02 row 2)

## Context

#91 (P6): aircraft around us broadcast their own GNSS quality (NACp, NIC) in ADS-B. A jammer
ahead degrades theirs before ours, so their reports can warn us early. Spoofing usually leaves
the quality fields high, so a spoofed aircraft shows instead as a jump in its track (Park 2026,
Aireon, in threat-model.md). ADS-B content is GNSS-derived (ADR-0024): it must never confirm our
GNSS, and it says nothing about our position.

The issue asks that this raise our fault priors. Which prior, by how much, and on what evidence
are new engineering choices. The integrity monitor (`pnt.integrity.mhss`, #82) already carries a
GNSS common-mode prior, `p_gnss_cm` = 1e-3 (TBC).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. While the warning is on, set `p_gnss_cm` to a fixed higher value (`p_gnss_cm_warned`) | One number; uses the MHSS hypothesis that already covers GNSS faults; the HPL widens before our own GNSS shows anything; no position changes | A step, not a graded prior; the value is a placeholder |
| B. Scale `p_gnss_cm` with the number or share of degraded aircraft | Graded | More placeholders (a curve) with no data to fit it |
| C. Deweight or exclude our GNSS while warned | Acts on position, not only the bound | ADS-B would steer our position; a false warning costs accuracy; GNSS-derived evidence deciding about GNSS |
| D. Show the warning on the panel only | Nothing to tune | The issue asks for the prior to move; the HPL stays blind to it |

## Decision

Option A. The evidence is per aircraft (`pnt.integrity.adsb`): a quality drop below NACp 9 or NIC 7 held for 5 s by an aircraft that earlier reported good quality, or a track jump over 300 m with good quality that the next report confirms. The warning is on while at least 2 aircraft within 50 km show a drop, or any shows a confirmed jump, and for 300 s after. While it is on, `p_gnss_cm` is 1e-1 instead of 1e-3, and the estimate is flagged `adsb_interference` or `adsb_spoofed_aircraft`. Every threshold and both priors are TBC.

## Consequences

- Only `ekf-mhss` reads ADS-B. Position, velocity and every filter are unchanged by it (tested);
  only the protection level and the flags move.
- A false warning costs continuity, not accuracy: a wider HPL for up to `memory_s`.
- Aircraft first heard with poor quality (legacy avionics, or already inside the jamming) are
  never counted, so a jammer that already covers every aircraft in range gives no warning.
- A slow carry-off spoof of the traffic that never jumps more than the gate is not caught.
- Sim evidence (`analysis/adsb_warning.py`) uses synthetic traffic and placeholder nuisance dips;
  no number from it is a real-world lead time or false-alert rate.
- **Reopen if:** recorded traffic (#22 front end) shows nuisance quality drops often enough to
  matter at 2 aircraft and 5 s; REQ-04 sets a false-alert target; or option C is wanted because
  the wider HPL alone does not change any decision.

## Amendment (2026-11-10, decided by the owner)

The ADS-B interference warning is not an alarm under REQ-04 ("false alarms ≤ 1 per hour on
nominal runs"), so that target does not apply to it. It only raises the GNSS fault prior and sets
the status to `degraded` (`unsafe` only if the wider HPL passes the alert limit); it never
excludes GNSS and never raises an alarm (`adsb_interference` and `adsb_spoofed_aircraft` are not
in `pnt.metrics.ALARM_FLAGS`). Its measured nuisance rate, 1.94 per hour (`analysis/adsb_warning.py`,
seeds 0–49, `uc02-yow-approach-adsb`, sim), comes from the sim's placeholder quality-dip rate
(TBC) and is to be re-measured on real FlightStick ADS-B traffic.
