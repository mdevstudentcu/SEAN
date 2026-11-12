# Headline numbers: spoof defence and the base station beside `ekf`

Sim only, every error model a placeholder (*Sim validity*, `systems/verification.md`). Seeds 0-49 on every scenario, every filter on the same seeds (paired). Commit `24aa5d1`; regenerate with `python analysis/headline.py --runs 50` from a clean tree (about 1.5 h with 3 workers). Every filter is registered on `main`; no default changed. Scoring is `pnt.metrics.score`, `analysis/figures.py`'s T1 statistic and `pnt.plots.stanford_counts`, as in `just results`. The presented figures in `analysis/results/final/` are plain `ekf` at `b74010e`; this run's `ekf` numbers match them (T1 677.3 m at +90 s, 17,042 hazardous epochs on `realistic-spoof-jump`) except 4 more hazardous epochs on `realistic-spoof-ramp` (92,358 against 92,354) from code changed since.

## Headline

`realistic` set: 15 scenarios × 50 runs = 2,695,450 epochs of 0.1 s per filter. Base filters: the same 15 attacks in `realistic-with-base` (identical payload records, plus the base station). Alert limit 50 m, T1 ≤ 25 m for 300 s after GPS loss: both `TBC`.

| Filter | T1: worst second of p95 after GPS loss | HPL bounds error, `long-outage`, worst run | Hazardous epochs (runs with any): spoof-ramp / spoof-jump / other | Unavailable epochs (HPL > 50 m) | Spoof detected: ramp / jump (delay) | False alarms, `nominal` |
| --- | --- | --- | --- | --- | --- | --- |
| `ekf` (presented today) | 677 m | 69.2 % | 92,358 (50) / 17,042 (20) / 0 | 402,631 (14.9 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| `ekf-guard` | 677 m | 69.2 % | 92,358 (50) / 0 / 0 | 520,145 (19.3 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| **`ekf-honest-guard`** | **449 m** | **100 %** | 92,366 (50) / **0** / 0 | 515,461 (19.1 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| `ekf-imu-guard` | 592 m | 64.5 % | 92,392 (50) / 0 / 6 (2, `jamming-zone`) | 499,568 (18.5 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| `ekf-calibrated-guard` | 749 m | 90.6 % | 92,366 (50) / 0 / 0 | 515,462 (19.1 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| `ekf-mhss` | 677 m | 100 % | 0 / 0 / 0 | 2,695,450 (**100 %**) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| `ekf-base` (sim-only base) | 500 m | 93.0 % | 92,365 (50) / 66,247 (49) / 958 (10, `gps-return`) | 348,387 (12.9 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |
| `ekf-base-imu` (sim-only base) | 332 m | 100 % | 92,401 (50) / 68,537 (49) / 1,504 (`gps-return` 1,246 in 10 runs, `meaconing` 258 in 6) | 333,723 (12.4 %) | 0/50 / 50/50 (1.1 s) | 0.0 /h |

Every filter misses T1 (25 m) by 13× or more and its fallback (50 m for 120 s) by 5× or more. `error_after_loss.png`: per-second p95 after GPS loss and after a held 300 m spoof jump, with the share of runs hazardous at each second, for `ekf`, `ekf-honest-guard`, `ekf-base` and `ekf-base-imu`.

## Recommendation (the owners decide)

**Spoofing: present `ekf-honest-guard` as "the system", or say plainly that `ekf` has no spoof defence.**

- Why `ekf-honest-guard`: of the filters on `main` it is the only one that has no hazardous epoch from a jump (0 against `ekf`'s 17,042 in 20/50 runs; ADR-0034's T4 jump target met on this scenario: detected in 1.1 s in 50/50 runs, GNSS excluded while the jump holds, no false alarm on `nominal`), whose HPL bounds the error in every run after GPS loss (100 % against 69.2 %), and whose T1 statistic is the best of the payload-only filters (449 m against 677 m). `ekf-guard` gives the same spoof result but keeps `ekf`'s 677 m and 69.2 %.
- Costs, with numbers:
  - Availability: +112,830 unavailable epochs over the set (14.9 % → 19.1 % of all epochs). Most is meaconing (+101,982): `ekf` follows the 5 s replay within 45 m p95 but misleadingly (102,032 misleading epochs, HPL under the error); the guard refuses GNSS to the end of the run and coasts, flagged: fault-window p95 45 → 239 m, worst run 245 → 803 m. On the held jump the 17,042 hazardous epochs become unavailable ones.
  - Recovery is not slower: on `gps-return` (jump undone after 50 s) unavailable epochs fall 24,210 → 22,700 and the worst run's resilience level rises 0 → 2.
  - Status: the jump guard (ADR-0038) and the slow-error state (ADR-0046) are both Proposed and opt-in. Presenting it means re-running `just results 50 ekf-honest-guard` from a clean commit, or showing it beside `ekf`; changing the default is a separate decision (ADR-0038's open follow-up).
- Do not claim:
  - **The slow ramp is not defended by any filter.** On `realistic-spoof-ramp` (2 m/s) every available filter is detected 0/50 and hazardous in 50/50 runs (about 92,400 epochs, 3.4 % of the set). It is every hazardous epoch of every guarded filter.
  - `ekf-mhss`'s zero hazardous epochs: its HPL is over the alert limit on every epoch of every run (100 % unavailable), as `verification.md` says (its subset covariances are not honest on `realistic-*`). Safe, but no service.
  - The ADR-0041 sky decision: advisory, not in any filter's output, and no `realistic` scenario has a `sky:`. Not run here.

**Base station: show it as a sim-only what-if for GPS loss, never for spoofing.**

- It is not built (ADR-0020, *Amendment 2026-11-10*); every number is sim with placeholder base values.
- What it buys on `long-outage` (`ekf` → `ekf-base` → `ekf-base-imu`): T1 statistic 677 → 500 → 332 m (still missed); p95 over the 300 s 332 → 264 → 207 m; HPL bounds error in the worst run 69.2 → 93.0 → 100 %; time error p95 0.462 → 0.314 → 0.288 µs; time PL bounds the clock error in the worst run 60.2 → 99.7 → 100 %. No hazardous epoch, as for `ekf`.
- What it costs: the base filters have no jump guard and follow the spoof more readily. `realistic-with-base-spoof-jump`: 66,247 / 68,537 hazardous epochs in 49/50 runs against `ekf`'s 17,042 in 20/50; `gps-return` gains 958 / 1,246 hazardous epochs (10 runs each) and `ekf-base-imu` 258 on `meaconing` (6 runs). There is no guarded base filter on `main`.
- Base faults while GPS is out (moved 50 m, clock step 1 µs, link lost 60 s, a tower clock step): 0 hazardous epochs; the worst run's maximum error rises 970 → 1,052 m on `base-moved` (`ekf-base`).

### What the base model assumes (`realistic-with-base.yaml`, every value `TBC`)

- **Link always up**, no latency, no loss: every base record reaches the filter at its own epoch. The one exception is `long-outage-base-lost` (60 s without the base). This is the mentor's condition ("if you can reliably communicate") assumed true, not shown.
- **Base surveyed**: the session is told the true position plus a survey error drawn at σ 1 m per axis, and the filter is told σ 1 m (ADR-0020: a GPS fix averaged over ≥ 1 h, `TBC`). The filter's survey prior matches the sim's draw: a matched, optimistic case.
- **Base clock**: PPS-disciplined to GPS, 100 ns offset, no drift, 0.5 ns wander; the filter carries it as a random walk. The base's GPS is never lost or spoofed in any scenario, including the ones where the payload's is: a jammer or spoofer that reaches the payload 250 m away is assumed not to reach the base. A real base in holdover would drift.
- **Base radio** (not measured: no base hardware): LTE σ 20 m, multipath 15 m with 300 s correlation, 95 % availability, against the payload's 50 m, 50 m (30 s) and 75 %. Same four towers, same tower clocks, same told-tower-position error.

## Tables

<!-- tables:start -->
Commit `24aa5d1`, seeds 0-49 (50 runs per scenario), sim, placeholder error models. Regenerate with `python analysis/headline.py --runs 50` from a clean tree.

### Spoofing: `realistic` set (15 scenarios)

| Estimator | T1 worst second p95 (m) | Fallback | HPL bounds error, worst run | Stanford nominal / misleading / hazardous / unavailable (epochs) | Runs with hazardous, spoof-ramp / spoof-jump | Spoof detected, ramp / jump / gps-return (% runs, mean delay s) | False alarms /h, nominal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ekf` | 677.3 at +90 s, missed | missed | 42.3 % | 2070458 / 112961 / **109400** / 402631 | 50/50 / 20/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |
| `ekf-guard` | 677.3 at +90 s, missed | missed | 42.3 % | 2072018 / 10929 / **92358** / 520145 | 50/50 / 0/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |
| `ekf-mhss` | 677.3 at +90 s, missed | missed | 100.0 % | 0 / 0 / **0** / 2695450 | 0/50 / 0/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |
| `ekf-calibrated-guard` | 748.7 at +240 s, missed | missed | 42.3 % | 2076703 / 10919 / **92366** / 515462 | 50/50 / 0/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |
| `ekf-imu-guard` | 591.7 at +299 s, missed | missed | 42.4 % | 2092300 / 11184 / **92398** / 499568 | 50/50 / 0/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |
| `ekf-honest-guard` | 448.9 at +270 s, missed | missed | 42.3 % | 2076705 / 10918 / **92366** / 515461 | 50/50 / 0/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |

Stanford counts are pooled over the 15 attacks of the `realistic` set (in either environment) and all seeds (0.1 s epochs; alert limit 50 m, TBC). T1: ≤ 25 m for 300 s after GPS loss on `realistic-long-outage`; fallback ≤ 50 m for 120 s; both TBC, scored as ADR-0034's amendment.

### Per scenario: what each defence costs

| Scenario | Estimator | Hazardous | Unavailable | Misleading | Fault-window p95 (m) | Worst run max (m) | Resilience level, worst run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `spoof-ramp` | `ekf` | 92358 | 100 | 10929 | 399.1 | 423.1 | 1 |
| `spoof-ramp` | `ekf-guard` | 92358 | 100 | 10929 | 399.1 | 423.1 | 1 |
| `spoof-ramp` | `ekf-mhss` | 0 | 179950 | 0 | 399.1 | 423.1 | 2 |
| `spoof-ramp` | `ekf-calibrated-guard` | 92366 | 100 | 10919 | 399.1 | 423.1 | 1 |
| `spoof-ramp` | `ekf-imu-guard` | 92392 | 100 | 10958 | 399.0 | 421.6 | 1 |
| `spoof-ramp` | `ekf-honest-guard` | 92366 | 100 | 10918 | 399.1 | 423.1 | 1 |
| `spoof-jump` | `ekf` | 17042 | 85608 | 0 | 235.7 | 762.2 | 1 |
| `spoof-jump` | `ekf-guard` | 0 | 102650 | 0 | 265.7 | 2232.5 | 2 |
| `spoof-jump` | `ekf-mhss` | 0 | 179950 | 0 | 235.7 | 762.2 | 2 |
| `spoof-jump` | `ekf-calibrated-guard` | 0 | 102650 | 0 | 259.9 | 1074.3 | 2 |
| `spoof-jump` | `ekf-imu-guard` | 0 | 99733 | 0 | 193.9 | 618.0 | 2 |
| `spoof-jump` | `ekf-honest-guard` | 0 | 102650 | 0 | 191.6 | 843.4 | 2 |
| `gps-return` | `ekf` | 0 | 24210 | 0 | 133.4 | 292.7 | 0 |
| `gps-return` | `ekf-guard` | 0 | 22700 | 0 | 133.4 | 292.7 | 2 |
| `gps-return` | `ekf-mhss` | 0 | 179950 | 0 | 133.4 | 292.7 | 0 |
| `gps-return` | `ekf-calibrated-guard` | 0 | 22700 | 0 | 143.8 | 262.9 | 2 |
| `gps-return` | `ekf-imu-guard` | 0 | 19783 | 2 | 109.5 | 226.8 | 2 |
| `gps-return` | `ekf-honest-guard` | 0 | 22700 | 0 | 125.0 | 261.2 | 2 |
| `meaconing` | `ekf` | 0 | 668 | 102032 | 45.4 | 244.6 | 2 |
| `meaconing` | `ekf-guard` | 0 | 102650 | 0 | 294.8 | 1345.5 | 1 |
| `meaconing` | `ekf-mhss` | 0 | 179950 | 0 | 45.4 | 244.6 | 2 |
| `meaconing` | `ekf-calibrated-guard` | 0 | 102650 | 0 | 261.0 | 1041.1 | 2 |
| `meaconing` | `ekf-imu-guard` | 0 | 99747 | 0 | 256.2 | 693.1 | 1 |
| `meaconing` | `ekf-honest-guard` | 0 | 102650 | 0 | 239.2 | 802.9 | 2 |
| `long-outage` | `ekf` | 0 | 147650 | 0 | 331.7 | 906.2 | 2 |
| `long-outage` | `ekf-guard` | 0 | 147650 | 0 | 331.7 | 906.2 | 2 |
| `long-outage` | `ekf-mhss` | 0 | 179950 | 0 | 331.7 | 906.2 | 2 |
| `long-outage` | `ekf-calibrated-guard` | 0 | 147650 | 0 | 369.5 | 1312.3 | 2 |
| `long-outage` | `ekf-imu-guard` | 0 | 144805 | 0 | 301.7 | 1078.5 | 2 |
| `long-outage` | `ekf-honest-guard` | 0 | 147650 | 0 | 296.2 | 834.6 | 2 |
| `nominal` | `ekf` | 0 | 100 | 0 | — | — | — |
| `nominal` | `ekf-guard` | 0 | 100 | 0 | — | — | — |
| `nominal` | `ekf-mhss` | 0 | 179950 | 0 | — | — | — |
| `nominal` | `ekf-calibrated-guard` | 0 | 100 | 0 | — | — | — |
| `nominal` | `ekf-imu-guard` | 0 | 100 | 0 | — | — | — |
| `nominal` | `ekf-honest-guard` | 0 | 100 | 0 | — | — | — |

### Base station: `realistic-with-base` set (19 scenarios), sim only (ADR-0020)

| Estimator | T1 worst second p95 (m) | Fallback | HPL bounds error, worst run | Stanford nominal / misleading / hazardous / unavailable (epochs) | Runs with hazardous, spoof-ramp / spoof-jump | Spoof detected, ramp / jump / gps-return (% runs, mean delay s) | False alarms /h, nominal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ekf-base` | 500.2 at +90 s, missed | missed | 42.3 % | 2074163 / 113330 / **159570** / 348387 | 50/50 / 49/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |
| `ekf-base-imu` | 331.9 at +269 s, missed | missed | 42.4 % | 2089449 / 109836 / **162442** / 333723 | 50/50 / 49/50 | 0 % (—) / 100 % (1.1) / 100 % (1.1) | 0.0 |

`ekf` on `realistic-with-base-*` is its `realistic-*` run: the payload's records are identical. Checked here on realistic-with-base-long-outage, realistic-with-base-spoof-jump: every estimate equal over all seeds.

| Scenario | Estimator | Hazardous | Unavailable | Fault-window p95 (m) | Worst run max (m) | HPL bounds error, mean / worst run | Time error p95 in fault window (µs) | Time PL bounds error, worst run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `long-outage` | `ekf` | 0 | 147650 | 331.7 | 906.2 | 93.3 % / 69.2 % | 0.462 | 60.2 % |
| `long-outage` | `ekf-base` | 0 | 147650 | 263.9 | 970.2 | 99.9 % / 93.0 % | 0.314 | 99.7 % |
| `long-outage` | `ekf-base-imu` | 0 | 144960 | 207.3 | 515.5 | 100.0 % / 100.0 % | 0.288 | 100.0 % |
| `spoof-ramp` | `ekf` | 92358 | 100 | 399.1 | 423.1 | 42.6 % / 42.3 % | 0.011 | 100.0 % |
| `spoof-ramp` | `ekf-base` | 92365 | 100 | 399.1 | 423.1 | 42.6 % / 42.3 % | 0.010 | 100.0 % |
| `spoof-ramp` | `ekf-base-imu` | 92401 | 100 | 399.0 | 421.6 | 42.6 % / 42.4 % | 0.010 | 100.0 % |
| `spoof-jump` | `ekf` | 17042 | 85608 | 235.7 | 762.2 | 87.6 % / 55.8 % | 0.010 | 100.0 % |
| `spoof-jump` | `ekf-base` | 66247 | 36403 | 298.7 | 310.2 | 63.2 % / 50.2 % | 0.010 | 100.0 % |
| `spoof-jump` | `ekf-base-imu` | 68537 | 31296 | 299.4 | 459.3 | 61.8 % / 53.3 % | 0.010 | 100.0 % |
| `nominal` | `ekf` | 0 | 100 | — | — | 100.0 % / 100.0 % | — | 100.0 % |
| `nominal` | `ekf-base` | 0 | 100 | — | — | 100.0 % / 100.0 % | — | 100.0 % |
| `nominal` | `ekf-base-imu` | 0 | 100 | — | — | 100.0 % / 100.0 % | — | 100.0 % |
| `tower-clock-step` | `ekf` | 0 | 100 | 3.0 | 5.6 | 100.0 % / 100.0 % | 0.010 | 100.0 % |
| `tower-clock-step` | `ekf-base` | 0 | 100 | 3.0 | 5.7 | 100.0 % / 100.0 % | 0.010 | 100.0 % |
| `tower-clock-step` | `ekf-base-imu` | 0 | 100 | 2.0 | 3.7 | 100.0 % / 100.0 % | 0.010 | 100.0 % |
| `long-outage-tower-clock-step` | `ekf-base` | 0 | 147650 | 264.7 | 970.2 | 99.9 % / 93.0 % | 0.317 | 99.7 % |
| `long-outage-tower-clock-step` | `ekf-base-imu` | 0 | 144960 | 208.1 | 515.5 | 100.0 % / 100.0 % | 0.294 | 100.0 % |
| `long-outage-base-moved` | `ekf-base` | 0 | 147650 | 265.6 | 1051.5 | 99.8 % / 90.0 % | 0.317 | 100.0 % |
| `long-outage-base-moved` | `ekf-base-imu` | 0 | 144960 | 209.2 | 572.9 | 100.0 % / 100.0 % | 0.285 | 100.0 % |
| `long-outage-base-clock-step` | `ekf-base` | 0 | 147650 | 297.9 | 950.4 | 99.8 % / 93.5 % | 0.348 | 98.3 % |
| `long-outage-base-clock-step` | `ekf-base-imu` | 0 | 144960 | 219.9 | 684.3 | 99.9 % / 95.0 % | 0.299 | 100.0 % |
| `long-outage-base-lost` | `ekf-base` | 0 | 147650 | 262.5 | 967.2 | 99.9 % / 93.2 % | 0.317 | 100.0 % |
| `long-outage-base-lost` | `ekf-base-imu` | 0 | 144960 | 208.4 | 554.4 | 100.0 % / 100.0 % | 0.291 | 100.0 % |
<!-- tables:end -->

## Not checked

- Any real session: everything above is sim with placeholder error models.
- Other spoof ramps (rates, directions) and jump sizes: one ramp (2 m/s) and one jump (300 m) per environment.
- `ekf-honest-guard` against `analysis/guard_manoeuvre.py` (ADR-0038's open follow-up): its availability cost after hard manoeuvres is not measured here.
- A sky-aware spoof (`fake_sky`) on the `realistic` set: no committed scenario has one.
