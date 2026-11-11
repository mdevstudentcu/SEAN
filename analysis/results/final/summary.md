# Results figures: `ekf`

Commit `cb386ca`, seeds 0-49, sim (each model's status is in the *Sim validity* table of `systems/verification.md`). Regenerate with `just figures ekf 50` (or `just results 50 ekf` for `results/final/`).

Figures: `error_after_gps_loss.png`, `stanford.png`, `ablation.png`, `holdover.png`

## Error after GPS loss (REQ-01): `realistic-long-outage`

Scored as ADR-0034's amendment says: at each second after GPS loss, the 95th percentile of the horizontal error across the 50 runs; a target holds if that stays within it for every second of its window.

- T1 (≤ 25 m for 300 s, TBC): worst second 677.3 m at +90 s, **missed**
- Fallback (≤ 50 m for 120 s, TBC): worst second 677.3 m at +90 s, **missed**
- worst run's maximum error in the fault window: 906.2 m

## Ablation (REQ-06)

| Variant | Mean p95 (m) | ± SE | Worst run (m) | Added vs all sources (paired, m) |
| --- | --- | --- | --- | --- |
| all sources | 331.7 | 20.5 | 787.4 | +0.0 ± 0.0 |
| no SoOP (lte) | 2292.3 | 26.5 | 2757.5 | +1960.7 ± 33.3 |
| no baro | 409.4 | 33.9 | 1407.9 | +77.7 ± 27.8 |
| no imu | 331.7 | 20.5 | 787.4 | +0.0 ± 0.0 |

## Stanford plot (REQ-02), per scenario

| Scenario | Epochs | Nominal | Misleading | Hazardous | Unavailable |
| --- | --- | --- | --- | --- | --- |
| `realistic-nominal` | 179950 | 179850 | 0 | 0 | 100 |
| `realistic-outage` | 179950 | 120086 | 0 | 0 | 59864 |
| `realistic-gps-no-fix` | 179950 | 120086 | 0 | 0 | 59864 |
| `realistic-gps-low-sats` | 179950 | 179850 | 0 | 0 | 100 |
| `realistic-gps-return` | 179950 | 155740 | 0 | 0 | 24210 |
| `realistic-spoof-ramp` | 179950 | 76563 | 10933 | 92354 | 100 |
| `realistic-spoof-jump` | 179950 | 77300 | 0 | 17042 | 85608 |
| `realistic-time-spoof` | 179950 | 179850 | 0 | 0 | 100 |
| `realistic-meaconing` | 179950 | 77250 | 102032 | 0 | 668 |
| `realistic-jamming-zone` | 176150 | 152181 | 0 | 0 | 23969 |
| `realistic-baro-drift` | 179950 | 113227 | 0 | 0 | 66723 |
| `realistic-tower-loss` | 179950 | 179850 | 0 | 0 | 100 |
| `realistic-tower-clock-step` | 179950 | 179850 | 0 | 0 | 100 |
| `realistic-long-outage` | 179950 | 32300 | 0 | 0 | 147650 |
| `realistic-capture-pi4b` | 179950 | 179850 | 0 | 0 | 100 |

## Timing holdover (REQ-03)

- clock error p95 in the fault window: 0.462 µs (T3: 1.5 µs after 10 min, TBC; the default realistic-long-outage lasts only 300 s)
- 1-sigma bounds the clock error in 37.2 % of epochs (mean over runs; T3 asks for ≥ 68 %)
- time PL bounds the clock error in 60.2 % of epochs in the worst run

## Real sessions

**Placeholder: no numbers yet.** Replayed real sessions (named session plus commit, REQ-10) go here beside the sim numbers once the work below lands. Nothing in this table is a result.

| Figure | Real-session result | Waiting on |
| --- | --- | --- |
| Error after GPS loss (REQ-01) | TBD | #21 (LTE ranging go/no-go on real captures), #30 (sim-to-real validation) |
| Stanford plot (REQ-02) | TBD | #30: real sessions with faults injected (`pnt replay --inject`) |
| Ablation (REQ-06) | TBD | #21, #30 |
| Timing holdover (REQ-03) | TBD | #30: a real session with PPS logged but hidden from the filter |
