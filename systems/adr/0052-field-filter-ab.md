# ADR-0052: Keep `ekf-honest` as the opt-in LTE filter after the field A/B; the field settings stay unregistered

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** the two owners (each point below is theirs to accept or change)
- **Traces to:** REQ-01, REQ-02, REQ-10, ADR-0034, ADR-0036, ADR-0039, ADR-0046 (Proposed, #251), ADR-0050, #256, #283, #286

## Context

#283 replayed two real static sessions with GPS cut in software. Every LTE-aided filter was hundreds of metres to kilometres worse than no LTE (about 2 m at 300 s). `ekf-honest` (ADR-0046) was the only one whose HPL covered every withheld fix, with a bound kilometres wide. Its diagnosis named causes that looked like configuration:
- range errors larger and slower than modelled;
- a free velocity;
- LTE used with fewer than 3 cells;
- the learner shrinking;
- a timing step shared by cells.

#286 tested each as an opt-in arm against `ekf-honest`, then combinations. The selection rule and the held-out protocol were fixed in advance. Every number, command and commit is in [`analysis/results/filter-ab/summary.md`](../../analysis/results/filter-ab/summary.md).

## Options (each an opt-in setting in `nav/ekf.py`, off by default)

| Option (setting) | Value tried, and where it came from | Tuning result (real `0040`; sim seeds 100–109) |
|---|---|---|
| Slow-error state sized in metres (`multipath_sigma_m`, `multipath_tau_s`, ratio 0) | 50, 100, 150 m × 60, 300 s, from `0040`'s double differences (spread 30–147 m per pair, wander 171–437 m) | No real gain (1,019–1,698 m at 300 s against 1,229 m). Error above HPL rose to 10–27 % on real, except 150 m / 60 s. Sim 1-carrier +30–62 % |
| IMU propagation (`motion="imu"`) | `ekf-imu`'s model | Never aligns on a static receiver: identical to the control on real data. Sim 1-carrier 1.37 % above HPL |
| Process noise sized to the platform (`q_accel`) | 0.3, 0.1 (a still receiver) | Real 155–583 m. Sim 25–88 % above HPL and 33–1,669 hazardous epochs: the sim drone's accelerations match 1 (ADR-0046) |
| Cell gate (`lte_min_cells`, `lte_cells_window_s`, `lte_max_hdop`, `lte_gate_mode`) | 3, 4 cells (a 2-D fix with our clock unknown needs 3); 1, 3, 5 s; HDOP 3; skip or clock states only | `cells3`: real 4.0 m, HPL holds; sim 1-carrier 5,765 m (+359 %). `cells4`: real 1.7 m (no LTE update after any cut); sim +89 % |
| Per-cell consistency gate (`lte_consistency_s`, `_k`, `lte_inconsistent_mode`) | 30, 60, 120 s; 2, 3, 4 model sigmas; then 3 cells or skip | Every real cell passes: normalised innovation RMS 0.09–0.29 against the sim's 0.96–2.33, because tower clock and slow-error states absorb the real error while GNSS steers. Real 971 m; sim 1-carrier +39 % |
| Huber weighting (`lte_huber_k`) | 1.5, 2.5 | No real effect (the control rejects 2 updates); sim 2.4–5.0 % above HPL |
| Learning frozen while GNSS steers (`noise_freeze_gnss`) | on | Real 5.2 % above HPL, no gain. The learned noise already cannot pull R below the retold sigma (`range_variance`) |
| Shared bias on a common timing step (`common_step_s`) | 1.5 s (#283's diagnosis window) | Real 1,244 m (control 1,229). Sim identical (no arcs in sim records) |
| Curvature inflation (`curvature_inflate`) | on | Lets held-back LTE back in; real 18.4 % above HPL |
| Zero-velocity update on IMU stillness (`zupt_sigma_mps`) | 0.1 m/s; thresholds from `0040` | Real 1.1 m. Fires in flight in the sim (74 % above HPL, 1,245 hazardous): a 2 s IMU variance cannot tell this drone from a still receiver |
| Stationary hold armed by rest at GNSS loss (`hold_rest_s`, `hold_speed_mps`, `hold_k`, `hold_sigma_mps`) | 20, 30 s; 0.3, 0.5 m/s; k 2, 3; 0.1 m/s | Never arms in flight (sim estimates hash identical to the control, 20 of 20 runs per arm). On `0040` it arms, then disarms on a still receiver after 3–200 s: one gyro axis's 1 s spread reaches 3.9–4.6 × its rest value. With LTE: 12.6–16.3 % above HPL |

## Decision

**Under the fixed rule no arm or combination beats the control.** The rule asks for:
- (a) error above HPL at most 1 % on real and sim tuning data;
- then (b) the lowest real error at 300 s;
- subject to (c) sim worst-second p95 at most 5 % worse than the control on both legs, with 0 hazardous epochs.

So `ekf-honest` stays the opt-in LTE filter, with its ADR-0046 settings. No new estimator is registered.

The field settings above stay in `nav/ekf.py` as opt-in keywords, unregistered, so the study can be repeated (`analysis/filter_ab.py`). Each value in the table is `TBC`.

## Consequences

1. **Defaults unchanged.** All 18 estimators registered on `main`, plus the four learned-noise and honest ones, hash the same on this branch as on its base. The checks are below; ADR-0045 is not on this branch.
2. **What the held-out data says** (real session `20261111-1937-static-fullsuite3`, sim seeds 0–49):
   - `ekf-honest`'s HPL covered every withheld fix (0 of 1,500 above).
   - Its 300 s median HPL was 970 m against no LTE's 16,556 m.
   - Its error at 300 s was 492 m against no LTE's 6.9 m. The "does no harm" bar is missed by 485 m.
   - On sim it is the control, so its sim bars hold by definition: 0 hazardous epochs; 1.39 % (1 carrier) and 0.38 % (13 carriers) of epochs above HPL.
3. **The labelled near-miss `cells4` (not passing the rule).**
   - Held-out real: 422 m at 300 s (worst cut 4,416 m), 1.0 % above HPL.
   - Held-out sim: 1-carrier 1,330 / 3,149 m (+89 % / +40 %); 13 carriers +5.4 % / +14.7 %, with 1.91 % above HPL.
4. **`ekf-honest` + stationary hold on held-out real** (with LTE):
   - 101 m at 300 s, 0 % above HPL, HPL 838 m at 300 s.
   - With LTE withheld: 1.2 m, HPL 3,220 m.
   - It is a stationary-only aid. It never acts in flight (sim identical to the control, 100 of 100 held-out runs).
5. **Not covered:**
   - any moving real session;
   - sessions `0151` and `0233`;
   - a real disarm, from rest then motion after the loss. No session or committed scenario has one; the disarm is covered only by `tests/test_ekf_field_options.py` with a synthetic IMU;
   - the MPU-6050 gyro glitch that disarms the hold on a still receiver (not investigated);
   - more than one front end;
   - an error model whose slow part is visible while GNSS steers (#283: tower clocks absorb it).
6. **Reopen when:**
   - a moving real session with GPS truth exists;
   - the front end flags common timing steps;
   - a slow-error test that clock states cannot absorb exists, for example double differences against the GNSS position, formed before the filter.

## Checks

- **Hashes.** Every field of every estimate, on `challenge-drone-outage`, `challenge-drone-spoof-jump` and `realistic-long-outage`, seeds 0 and 1; `analysis/filter_ab.py hashes`:
  - Branch head against its base `2fbb84f`: 132 of 132 identical.
  - Against today's `origin/main` `8f992ed`: 59 of 108 identical.
  - The 49 that differ also differ between `main`'s merge-base with this branch (`3493cfb`) and `8f992ed`. The merge-base matches this branch on all 108. So every difference comes from `main`'s 21 later commits, whose only change under `src/pnt/nav` is ADR-0045's GNSS-height fallback.
- **The branch could not be rebased onto `8f992ed`.** The first #156 commit conflicts with ADR-0045 in `nav/ekf.py`.
