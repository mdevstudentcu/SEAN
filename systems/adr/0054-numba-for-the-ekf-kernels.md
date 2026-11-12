# ADR-0054: numba compiles the EKF's covariance kernels

- **Status:** Proposed (numba as a dependency signed off by the owner, 2026-11-09; the kernels approved 2026-11-11)
- **Date:** 2026-11-11
- **Deciders:** owners
- **Traces to:** REQ-10, ADR-0003, #255

## Context

A full `pnt results` pass is slow enough to limit how often we rerun it. `ekf` on main `c62255d`, seed 0, one BLAS thread, over the 138 scenarios: 104 CPU-s generating, 187 estimating and 6 scoring. The 12 `challenge-drone-hop-*` scenarios take 78 CPU-s of the estimate: their state has up to 145 entries (one bias per hopped cell), against 14–30 elsewhere.

Two dense products in `pnt.nav.ekf` cost most of the estimate on those:

- `_update`: the Joseph form `(I - KH) P (I - KH)' + K R K'`, O(n³).
- `predict`: `F P F' + Q`, O(n³), although F differs from the identity in 5–11 rows (position, the clocks, the multipath states).

And `pnt eval` / `pnt results` start one worker per core (`--jobs` defaults to the core count), each with OpenBLAS's default of a thread per core.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Keep the dense numpy products | No change | The cost above |
| B. The same algebra in numpy, without forming I - KH, and the sparse predict in numpy above a size threshold | No dependency | numpy's per-call overhead dominates at n ≤ 30, where most scenarios are; the numpy sparse predict is slower than dense up to 53 states (table below) |
| C. B's algebra compiled with numba (`cache=True`) | Faster at every size we run (table below); no threshold to tune | A dependency (ground extra: numba and llvmlite, 196 MB installed); a compile on first use per checkout, then about 1 s per process to load it |

Each kernel, one core, on the filter's own matrices captured from `challenge-drone-hop-nominal` and `challenge-drone-nominal` (seed 0, `ekf` and `ekf-imu`; µs per call; `analysis/ekf_kernel_bench.py` on this change over main `c62255d`, sim):

| States n | Joseph dense | Joseph numba | Predict dense | Predict sparse numpy | Predict numba |
| --- | --- | --- | --- | --- | --- |
| 14 | 11.6 | 2.9 | 4.5 | 19.9 | 2.3 |
| 30 | 18.7 | 4.7 | 8.9 | 23.9 | 3.3 |
| 53 | 41.7 | 9.6 | 24.3 | 30.9 | 6.9 |
| 134 | 342.3 | 44.5 | 272.7 | 81.0 | 31.9 |

(Joseph for one measurement; three at n = 134: 304.6 → 83.9. The numpy sparse predict overtakes the dense one between 53 and 67 states; the numba one is faster at every size, so there is no threshold.)

## Decision

Option C: `pnt.nav._kernels` holds the Joseph update in O(n²m) form and the predict over F's non-identity rows and columns, compiled with numba, and `pnt eval` / `pnt results` workers start with one BLAS thread unless the environment sets otherwise.

## Consequences

- **Results change only at rounding; no decision changes.** The kernels sum in a different order from the BLAS product, so they are not bit-identical (neither is the numpy sparse predict: it differed from the dense product in 39 of 55 sizes tried). Every registered estimator, run on main and on this change with the same measurements, compared epoch by epoch (sim; #255 has the table):
  - main `c62255d`, seed 0: the 33 `challenge-*` legs without hopping, `gps-outage`, `realistic-long-outage`, `meaconing`, `spoof-jump`, `spoof-ramp`, and the `challenge-drone-hop-` `nominal`, `outage`, `spoof-ramp` and `meaconing` legs (the MHSS filters on `hop-outage` only, the calibrated ones on no hop leg): 852 runs.
  - main `8892fca`, seeds 0-1, with all 16 hop legs (the MHSS filters on `hop-nominal` and `hop-outage`, the calibrated ones on `hop-outage`, seed 0): 1,583 runs.
  - Both: no gate verdict (every `_update` accept or reject), status, flag or trust key changed. `baseline`, which does not use the kernels, is bit-identical. The largest differences: 5.1 cm in position and 4.6 cm in HPL for `ekf-measured-sigma` on `challenge-timing-outage-baro-drift`, where the HPL is 7.7 km (a relative 6e-6, on a position the filter cannot see in that outage); below 0.12 mm everywhere else; clock below 1e-17 s.
- `pnt eval` summaries at printed precision (3 runs): identical for `gps-outage` (`ekf`), `spoof-ramp` (`ekf-mhss`), `realistic-long-outage` (`ekf-calibrated`) and `challenge-drone-outage` (`ekf-imu`). `challenge-timing-outage-baro-drift` with `ekf-measured-sigma` moves its errors by up to 4.8 cm on 1.8–6.5 km; every count (misleading, hazardous, alarms) is unchanged.
- **Speed** (`ekf`, seed 0, the 138 scenarios, one BLAS thread, CPU-s): estimate 187 → 129; the 12 hop scenarios 78 → 28; the other 126 108 → 100. Generating (104) is unchanged and is now the larger part. The test suite: 172 → 158 s wall.
- **One BLAS thread per worker** takes effect (`tests/test_eval_parallel.py` counts the worker's threads: 1 with it, 16 without), but gave no measured speed-up at 3 workers: `pnt eval challenge-drone-hop-nominal --runs 6 --jobs 3 --estimator ekf` on main took 15.7 s with 16 BLAS threads and 18.3 s with one. Not measured at the default `--jobs` (one worker per core), where 16 workers each starting 16 threads is the case it guards against.
- numba joins the ground extra. The Pi imports `pnt.nav` through `pnt.cli` with the payload extra only, so `pnt.nav._kernels` imports numba when a filter first runs, not at import (`tests/test_payload.py` blocks numba on the Pi's imports).
- The first filter run in a checkout compiles both kernels (1.4–2.9 s measured, depending on load); later processes load them from `src/pnt/nav/__pycache__` (0.4–1 s, with the numba import).
- The workers come from a forkserver, as `experiments._map`'s already do, so that the BLAS setting is in place before numpy loads.
- Reopen if a numba release stops supporting our numpy or Python, or a decision changes because of rounding.
