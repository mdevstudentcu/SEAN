# No estimate changed: hashes against main

Each run's estimates are hashed by `analysis/whiteness.py hash`: time, position, velocity, covariance, clock, HPL, VPL, status, trust, and every flag except `innovations_correlated:*`. A second hash covers this test's flags alone. Runs: once with `main` `c62255d` on `PYTHONPATH`, and twice with this branch at `8218318`: on the eval path (`nav.estimate` as `pnt eval` calls it, the test off) and on the panel path (`--whiteness`, the test on). `compare` diffs the runs.

| Kind | Estimators | Inputs | Eval path vs `main` | Panel path vs `main` (without this flag) | Runs where the panel path adds the flag |
|---|---|---|---|---|---|
| Sim | all 21 registered | `challenge-approach-outage`, `challenge-drone-outage`, `challenge-timing-outage`, `easy-nominal`, `gps-outage`, `meaconing`, `nominal`, `realistic-long-outage`, `spoof-jump`, `spoof-ramp`; seeds 0, 1 | **420 of 420**, this flag's hash too | **420 of 420** | 194 |
| Real replay | `baseline`, `ekf`, `ekf-calibrated-measured`, `ekf-guard`, `ekf-measured-sigma`, `ekf-spoof` | `20261111-0151-static-fullsuite2`, `20261111-0233-static-lte-1h` (#245 records), `20261111-1806-walk-lte` (`-lte` records), whole sessions | not run | **18 of 18** | 15 |

Not hashed on real sessions: the other 15 estimators. A run of all of them on the three sessions had not finished in 30 min per side; all 21 are in the sim rows. `challenge-drone-hop-*`: not run.

Files: `hash-sim-main.json`, `hash-sim-eval-path.json`, `hash-sim-panel-path.json`, `hash-real-main.json`, `hash-real-panel-path.json`. Eval-path timing against `main`: `timing-main-{1,2}.json`, `timing-branch-{1,2}.json`.
