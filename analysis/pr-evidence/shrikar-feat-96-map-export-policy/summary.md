# P12 map export policy (ADR-0048): before and after

Sim, `p12-drone-map-handoff`, `ekf-calibrated` user, seeds 0-19. Same command on both sides,
each in its own worktree with its own `PYTHONPATH`:
`python analysis/p12_map_handoff.py --runs 20 --jobs 3 --out <dir>/p12-map-handoff.png`.
Seed 0's age-0 map JSON is byte-identical on both sides (and to `analysis/pr-evidence/174/`).

## Before: origin/main `7c20323` (export whatever was learned)

p12-drone-map-handoff, ekf-calibrated, 20 seeds (sim), pooled over seeds
| case | T1 stat 0-120 s (m) | T1 stat 0-300 s (m) | pooled p95 0-120 s (m) | pooled p95 0-300 s (m) | worst seed p95 0-300 s (m) | HPL >= error, 0-300 s | misleading | hazardous |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no aid | 277.7 | 617.8 | 208.9 | 396.3 | 1003.5 (seed 3) | 0.989 | 0 | 0 |
| no aid, sim's drift spread as prior | 241.1 | 280.9 | 181.4 | 206.3 | 272.0 (seed 5) | 1.000 | 0 | 0 |
| map, age 0 s | 290.5 | 416.0 | 236.3 | 310.1 | 415.7 (seed 14) | 1.000 | 0 | 0 |
| map, age 300 s | 218.6 | 359.1 | 173.8 | 229.8 | 349.2 (seed 11) | 1.000 | 0 | 0 |
| map, age 600 s | 247.3 | 336.6 | 191.5 | 237.6 | 325.2 (seed 11) | 1.000 | 0 | 0 |
| map, age 1200 s | 252.0 | 357.3 | 184.3 | 232.3 | 345.4 (seed 11) | 1.000 | 0 | 0 |
| map, age 1800 s | 234.3 | 309.9 | 184.6 | 244.6 | 288.9 (seed 11) | 1.000 | 0 | 0 |

## After: `f234749` on `main` (guarded build, withheld if flagged)

p12-drone-map-handoff, ekf-calibrated, 20 seeds (sim), pooled over seeds
| case | T1 stat 0-120 s (m) | T1 stat 0-300 s (m) | pooled p95 0-120 s (m) | pooled p95 0-300 s (m) | worst seed p95 0-300 s (m) | HPL >= error, 0-300 s | misleading | hazardous | map withheld |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no aid | 277.7 | 617.8 | 208.9 | 396.3 | 1003.5 (seed 3) | 0.989 | 0 | 0 | - |
| no aid, sim's drift spread as prior | 241.1 | 280.9 | 181.4 | 206.3 | 272.0 (seed 5) | 1.000 | 0 | 0 | - |
| map, age 0 s | 290.5 | 416.0 | 236.3 | 310.1 | 415.7 (seed 14) | 1.000 | 0 | 0 | 0 |
| map, age 300 s | 218.6 | 359.1 | 173.8 | 229.8 | 349.2 (seed 11) | 1.000 | 0 | 0 | 0 |
| map, age 600 s | 247.3 | 336.6 | 191.5 | 237.6 | 325.2 (seed 11) | 1.000 | 0 | 0 | 0 |
| map, age 1200 s | 252.0 | 357.3 | 184.3 | 232.3 | 345.4 (seed 11) | 1.000 | 0 | 0 | 0 |
| map, age 1800 s | 234.3 | 309.9 | 184.6 | 244.6 | 288.9 (seed 11) | 1.000 | 0 | 0 | 0 |

Every number is the same: no honest build latched the guard or raised `spoof_suspected`, so no
map was withheld, and a guard that never latches changes nothing (ADR-0038). The spoofed-drone
cases are in `analysis/results/p12-spoofed-map/summary.md` (same 20 seeds, commit `f234749`):
every user and drone number there is unchanged against main's (commit `100b2f4`); the new
`map withheld` cell for the honest map is 0/20.
