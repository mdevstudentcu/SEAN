# ADR-0048: What the EKF does with a real capture's LTE records

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners)
- **Traces to:** REQ-01, REQ-02, REQ-04, ADR-0015, ADR-0036, ADR-0038, ADR-0044, #147, #191, #214, #246

## Context

#245's front end fixed the ~700 m re-acquisition walks (median re-find step now about 10 m), but replaying the two real static sessions with GPS cut in software (#214's `analysis/real_gps_cut.py`) still gives LTE-aided errors of kilometres, where no LTE gives about 1 m:

- The default `ekf` believes the front end's σ (1 to 5 m at high SNR) while two cells' double difference wanders 1 to 45 m. It pulls the position off, keeps its covariance tight, and its χ² gate then rejects every GNSS fix: GNSS is excluded on 100 % (0151) and 28 % (0233) of the epochs before the cut (#246). LTE alone keeps consistent GNSS out.
- 16 to 17 % of re-finds still step more than 100 m, and a cell first heard after the cut has nothing to check it against.

ADR-0044 kept every default on the reported σ until a moving session decides. This ADR asks the owners to change that for real captures only, and proposes three opt-in guards. Results: [`analysis/results/real-lte-filter`](../../analysis/results/real-lte-filter/NOTES.md).

## Options and what each bought

RESULTS_TABLE

## Decision (Proposed)

DECISION

## Consequences

CONSEQUENCES
