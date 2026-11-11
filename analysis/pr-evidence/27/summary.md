# Results figures: `ekf`

Commit `c87a8e6`, seeds 0-9, sim (each model's status is in the *Sim validity* table of `systems/verification.md`). Regenerate with `just figures ekf 10` (or `just results 10 ekf` for `results/final/`).

Figures: `error_after_gps_loss.png`, `stanford.png`, `ablation.png`, `holdover.png`

## Error after GPS loss (REQ-01): `realistic-long-outage`

Scored as ADR-0034's amendment says: at each second after GPS loss, the 95th percentile of the horizontal error across the 10 runs; a target holds if that stays within it for every second of its window.

- T1 (≤ 25 m for 300 s, TBC): worst second 2638.9 m at +299 s, **missed**
- Fallback (≤ 50 m for 120 s, TBC): worst second 1369.9 m at +120 s, **missed**
- worst run's maximum error in the fault window: 2674.7 m

## Ablation (REQ-06)

| Variant | Mean p95 (m) | ± SE | Worst run (m) | Added vs all sources (paired, m) |
| --- | --- | --- | --- | --- |
| all sources | 2252.5 | 83.0 | 2560.3 | +0.0 ± 0.0 |
| no SoOP (lte) | 2255.4 | 60.1 | 2591.4 | +2.9 ± 112.6 |
| no baro | 1580.5 | 127.9 | 2472.5 | -672.0 ± 168.9 |
| no imu | 2252.5 | 83.0 | 2560.3 | +0.0 ± 0.0 |

## Stanford plot (REQ-02), per scenario

| Scenario | Epochs | Nominal | Misleading | Hazardous | Unavailable |
| --- | --- | --- | --- | --- | --- |
| `realistic-nominal` | 35990 | 35970 | 0 | 0 | 20 |
| `realistic-outage` | 35990 | 12460 | 0 | 0 | 23530 |
| `realistic-gps-no-fix` | 35990 | 12460 | 0 | 0 | 23530 |
| `realistic-gps-low-sats` | 35990 | 35970 | 0 | 0 | 20 |
| `realistic-gps-return` | 35990 | 27413 | 0 | 1856 | 6721 |
| `realistic-spoof-ramp` | 35990 | 15322 | 2180 | 18468 | 20 |
| `realistic-spoof-jump` | 35990 | 15460 | 0 | 15815 | 4715 |
| `realistic-time-spoof` | 35990 | 35970 | 0 | 0 | 20 |
| `realistic-meaconing` | 35990 | 15440 | 20496 | 0 | 54 |
| `realistic-jamming-zone` | 35230 | 26378 | 0 | 0 | 8852 |
| `realistic-baro-drift` | 35990 | 22785 | 0 | 0 | 13205 |
| `realistic-tower-loss` | 35990 | 35970 | 0 | 0 | 20 |
| `realistic-tower-clock-step` | 35990 | 35970 | 0 | 0 | 20 |
| `realistic-long-outage` | 35990 | 6460 | 0 | 0 | 29530 |
| `realistic-capture-pi4b` | 35990 | 35970 | 0 | 0 | 20 |

## Timing holdover (REQ-03)

- clock error p95 in the fault window: 0.156 µs (T3: 1.5 µs after 10 min, TBC; the default realistic-long-outage lasts only 300 s)
- 1-sigma bounds the clock error in 94.1 % of epochs (mean over runs; T3 asks for ≥ 68 %)
- time PL bounds the clock error in 100.0 % of epochs in the worst run

## Real sessions

**Placeholder: no numbers yet.** Replayed real sessions (named session plus commit, REQ-10) go here beside the sim numbers once the work below lands. Nothing in this table is a result.

| Figure | Real-session result | Waiting on |
| --- | --- | --- |
| Error after GPS loss (REQ-01) | TBD | #21 (LTE ranging go/no-go on real captures), #30 (sim-to-real validation) |
| Stanford plot (REQ-02) | TBD | #30: real sessions with faults injected (`pnt replay --inject`) |
| Ablation (REQ-06) | TBD | #21, #30 |
| Timing holdover (REQ-03) | TBD | #30: a real session with PPS logged but hidden from the filter |
