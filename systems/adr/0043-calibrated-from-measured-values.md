# ADR-0043: A calibrated EKF sized from measured values, not from the sim it is scored on

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-02, REQ-10, ADR-0015, ADR-0022, ADR-0034, ADR-0036, #118

## Context

`ekf-calibrated` (`nav.ekf.CALIBRATED`) takes its multipath (50 m as the reported sigma, 30 s), told tower position (100 m), tower clock noise (0.2 m/√s) and our clock's noise (2 ns/√s) from the `realistic` set, the set it is then scored on. Its NEES there is self-consistency, not evidence that it is honest (#118). ADR-0036 (Proposed) now gives an LTE error model measured on 15 real static sessions: a white part from SNR, which ADR-0036 puts in the front end's reported sigma; a correlated part of 10 m with a 3 s correlation time (`TBC`, at rest); sectors of one eNB drifting together within 0.5 m/s; drift between eNBs `TBD`, up to 6.6 m/s seen. It measures neither the told tower position nor the clocks' noise (its Allan rows are upper bounds only).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Replace `CALIBRATED`'s values with the measured ones | One calibrated filter | Every result made with `ekf-calibrated` (spoof detection, jump refusal, timing holdover) moves at once, before the owners accept ADR-0036 |
| B. A new opt-in estimator, `ekf-calibrated-measured`, beside `ekf-calibrated` | Nothing on `main` changes; the two can be paired on the same runs | One more registry entry to keep in step |
| C. Keep only `ekf-calibrated` and state that its NEES is self-consistency | No code | Leaves #118 open: no filter sized independently of the sim |

## Decision

Option B: `ekf-calibrated-measured` (`nav.ekf.CALIBRATED_MEASURED`) is `ekf-calibrated`'s model with each value taken from a real measurement or the filter's own default, never from a sim set. Every value is `TBC`, `TBD` where noted:

| Value | `ekf-calibrated` (realistic set) | `ekf-calibrated-measured` | Source |
| --- | --- | --- | --- |
| White range noise | reported sigma | reported sigma | The record. ADR-0036 (1) puts the measured law (σ² = 0.64² + 2.28² / SNR_lin, 10 Hz) in the front end's report |
| Correlated part | Gauss-Markov, 1.0 × reported sigma, 30 s | Gauss-Markov, 10 m, 3 s (new `multipath_sigma_m`: a size in metres, not a ratio) | ADR-0036 (1), at rest, `TBC` |
| Told tower position | 100 m per axis | off | Not measurable at rest; ASM-02's bound is `TBD` |
| Tower clock offset noise `tower_h0` | 8.9e-19 s (0.2 m/√s) | `EKF` default 2.6e-22 s | Literature (Shamaei et al. 2018); ADR-0036 bounds it from above only |
| Our clock `h0`, `h_2` | 8e-18 s, 2e-23 /s | `EKF` defaults 2e-19 s, 2e-20 /s | Literature, TCXO-class |
| First-sight tower drift sigma | 1.0 m/s (default) | 6.6 m/s | ADR-0036: largest inter-eNB drift seen; `TBD`, a wide prior, not a defended value |
| New-site drift seeded from other sites | on | off | ADR-0036: eNBs differ by up to 6.6 m/s, so one eNB's drift is no prior for another's |

Default `multipath_sigma_m` is 0 (off), so every other estimator's output is unchanged (checked by hash against `main`, PR evidence).

## Consequences

- Results with `ekf-calibrated-measured` on a sim set are a filter sized from real data meeting a placeholder world, so its NEES there is a test, not self-consistency. Paired results against `ekf` and `ekf-calibrated` are in `analysis/results/calibrated-measured/`.
- First result (sim, 50 paired runs, `summary.md` there): on `ottawa-sionna` it is honest (NEES 1.6) with the lowest T1 statistic of `ekf`, `ekf-calibrated` and itself (85 m); on `realistic-long-outage` and `worst-long-outage` it is overconfident (NEES 26.5 and 85.3), because those sets' placeholder multipath is 5 to 10 times the measured at-rest part. Its time-misleading epochs come from the literature clock default for our clock, not from the LTE model. It is not proposed as the default.
- `ekf-calibrated` stays as it is; which of the two becomes the calibrated filter we pitch is for the owners once ADR-0036 is accepted and the moving capture with GPS sizes the correlated part and the told position.
- What would reopen it: the moving capture (ADR-0036 (4)); a measured told-position error (ASM-02); ADR-0036 changed by the owners; a front end that reports the correlated part in `meta` (ADR-0036 (1)), which the filter should then read in place of the fixed 10 m and 3 s.
