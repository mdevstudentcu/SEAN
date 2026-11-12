# ADR-0056: Horizontal protection-level factor 5.68 for a two-dimensional error

- **Status:** Accepted
- **Date:** 2026-11-12
- **Deciders:** Shrikar (owner); Mo not consulted (no contributions for a while): reopen if he disagrees. This replaces the owner call of 2026-11-11 in #279 item 8 ("after judging").
- **Traces to:** REQ-02, #265, #279, `integrity/protection.py`, `integrity/mhss.py`

## Context

HPL is `K_H` × the major-axis σ of the horizontal covariance. `K_H` was 5.33, the two-sided 1e-7 quantile of a **one-dimensional** Gaussian (the vertical factor, SBAS `K_V`). The horizontal error is two-dimensional, and the integrity risk the code names is 1e-7 per epoch (`mhss.phmi`). Bounding the ellipse by a circle of its major-axis σ, P(r > k σ) ≤ exp(−k²/2), so 5.33 gives 6.8e-7, and 1e-7 needs k = √(2 ln 10⁷) = 5.68. HPL was about 6 % smaller than the risk it claims (#265). The vertical (`K_V`) and time (`K_T`) factors bound one-dimensional errors, so 5.33 is right for them.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A: keep 5.33, state the per-axis risk | No number moves | The stated 1e-7 stays wrong for a horizontal error; a navigation-integrity reviewer finds it from the code |
| **B: `K_H` = 5.68** | Factor and stated risk agree; derived, not borrowed | Every HPL grows 6.6 %; committed results computed at 5.33 must say so |
| C: SBAS `K_H` 6.0 or 6.18 | A recognised value | Those belong to SBAS's own risk allocation and exposure, not our 1e-7 per epoch |

## Decision

`K_H` = 5.68; `K_V` and `K_T` stay 5.33.

## Consequences

- Every HPL is 6.6 % larger. Estimates, errors, flags and every source decision are unchanged (HPL feeds the panel's status and the metrics, not the filter).
- Demo, simulation, seed 0, checked segment by segment against `main` (`b2b0a5d`): the UNSAFE onsets come 0.3 s earlier (outage T+64.8 → 64.5, towers 65.0 → 64.7, jump and guard 154.8 → 154.5); no other status change or alert moves; HPL still covers the error wherever it did, and the unguarded jump still escapes it at T+176.8. `deploy/demo/RUNBOOK.md` carries the new values.
- Committed results computed at 5.33 (`analysis/results/final/`, `headline/` and the studies) keep their commits and stay reproducible there (REQ-10); `systems/results.md` says which factor they used. Regenerating them at 5.68 is follow-up work: HPL coverage can only rise, availability can only fall, and hazardous epochs can only fall.
- Still open: the exposure time behind the 1e-7 (`TBD`), and REQ-02's own risk target (`TBC`). The covariance, not the factor, causes the large escapes after GPS loss (#251, ADR-0046); this ADR does not change that.
