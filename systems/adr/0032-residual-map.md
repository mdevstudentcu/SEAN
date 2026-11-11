# ADR-0032: Learn a per-place residual map of each tower while GPS is trusted

- **Status:** Accepted (2026-11-11, owners) as opt-in only: never a default estimator until real data shows a repeatable per-place error above the noise (see *Guardrail*)
- **Date:** 2026-11-10
- **Deciders:** team
- **Traces to:** REQ-01, REQ-02, ADR-0015, ADR-0016, ADR-0021 (P11), ADR-0022, ADR-0024

## Context

A tower's reading carries an error that depends on where the receiver is: a reflection off a building, or a blocked direct path, repeats every time the drone passes the same place. The campus ray trace shows it: one TELUS site reads 40–45 m long over the same 400 m arc on every lap (`data/reference/sionna-campus-route.csv`, ADR-0016). The EKF models tower error as white noise, a clock per site and, in `CALIBRATED`, a Gauss-Markov process in time. None of these remembers a place, so after GPS loss the same reflection pulls the solution again.

While GPS is trusted our position is known to a few metres, so a pseudorange innovation is mostly that place's error. ADR-0021 lists this as P11 (#95). A drone on a repeated route (inspection, delivery, UC-01) passes the same places again.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Nothing: inflate the noise | No state | The error stays; NEES stays high |
| B. Per emitter, mean innovation per horizontal grid cell, learned only while GPS is trusted, applied with its own variance | Simple, causal, no new filter states; frozen when GPS is not trusted | Only where we have been; cell size is a guess; learns a slow spoof GNSS checks accept |
| C. Gaussian-process map per emitter | Interpolates between places | Cost grows with samples; hyper-parameters to tune; no gain shown over B yet |
| D. Map states in the filter | Joint estimation with clocks | Thousands of states; learns from the solution it makes when GPS is gone |

## Decision

Option B, opt-in as `ekf-map` (`residual_map=` on the EKF): per emitter and 25 m cell, the running mean of accepted innovations while `gnss_trusted()`, used once the cell has 2 of them. Each cell's mean is shrunk towards zero by the emitter's own spread of place errors (empirical Bayes: τ² = variance of its cell means less their noise variance v, needing 5 cells; estimate k·mean with variance k·v, k = τ²/(τ² + v)), so an emitter with no place error gets no correction and no added noise. Cell size, counts and the shrinkage form are `TBC`.

The map stays opt-in. Issue #95's guardrail says ray tracing or ML may only lower a tower's weight and never enter the protection-level maths; subtracting a learned per-cell mean goes beyond lowering a weight. The owners accept that only for `ekf-map`, never for a default estimator, until real data shows a repeatable per-place error above the noise (*Guardrail* below).

Shrinkage is part of the decision because without it the map made `gps-outage` (no place error) worse: fault-window p95 19.9 m → 22.2 m over 50 paired runs (`pnt eval gps-outage --runs 50`, sim, seeds 0-49; `ekf` at 6b4a23e, `ekf-map` at 5f59e37, the map before shrinkage). With shrinkage (6b4a23e) it is 19.9 m, and `residual-map` goes from 38.7 m (`ekf`) to 36.7 m, against 34.7 m without shrinkage.

## Guardrail

- **Opt-in only.** The mean correction runs only when `ekf-map` or `residual_map=` is chosen. Default estimators never use it.
- **Before any default use**, both must hold, and changing the default needs a new ADR:
  1. A real repeated-route session shows a repeatable per-place error above the noise (the *Sim validity* row for `place_error` stops being a placeholder).
  2. The protection level accounts for the correction's common-mode error.
- **Open issue, not fixed: common-mode error of a cell's correction.** The added variance (k·v) is applied to each reading as if independent, but a cell's estimation error is shared by every reading that uses that cell. Many readings in one cell, over epochs or repeat passes, therefore over-trust that cell's correction, and the protection level can come out too small by an amount not yet measured. Found in review of PR #168.

## Consequences

- **Learned only while GPS is trusted (ADR-0024).** The map never learns from a solution it is helping to make. A slow spoof that the GNSS checks accept writes into it, as into the tower clocks (ADR-0022); the map has no rollback (not built).
- **Only where we have been, at our estimated position.** After a long outage the lookup cell may be wrong; the added variance and the 25 m cell bound the harm, not a test.
- **Tested against a new sim error:** `place_error` on a pseudorange source (`sim/models.py`), a Gaussian random field per tower over horizontal position, form from ray tracing, sizes `TBC`. It is a placeholder in the *Sim validity* table.
- **Not built:** keeping the map between sessions (survey once, fly later), sharing it between payloads, and a map for the reference station.
- **Reopen if:** a real repeated-route session shows no repeatable per-place error above the noise, or the map makes results worse on a scenario without one (`gps-outage`, `ottawa-sionna`).
