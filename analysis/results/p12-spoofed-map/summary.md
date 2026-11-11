# P12 with a spoofed drone (#96)

p12-drone-map-handoff and its spoofed-drone variants, ekf-calibrated user, 20 seeds (sim), seeds 0-19, commit 100b2f4. `python analysis/p12_spoofed_map.py --runs 20 --jobs 3 --out analysis/results/p12-spoofed-map`.

## Does the drone flag its own GNSS during the build?

| drone detector | ramp: seeds flagged | ramp: median s to flag | jump: seeds flagged | jump: median s to flag | honest circuit: seeds flagged |
| --- | --- | --- | --- | --- | --- |
| ekf-calibrated | 0/20 | - | 0/20 | - | 0/20 |
| ekf-calibrated-guard | 0/20 | - | 20/20 | 0.1 | 0/20 |
| ekf-calibrated-spoof | 0/20 | - | 0/20 | - | 0/20 |
| ekf-guard | 0/20 | - | 20/20 | 0.1 | 0/20 |
| ADR-0041 decision on `ekf-calibrated-guard`, no sky: seeds by highest level | unknown 20 | - | suspect 20 | - | unknown 20 |

Cues on the spoofed circuits before the spoof started: 0.

## What the map does to the ground user

| ground user's case | T1 stat 0-120 s (m) | T1 stat 0-300 s (m) | worst seed p95 0-300 s (m) | HPL >= error, 0-300 s | unsafe, 0-300 s | misleading | hazardous | map withheld |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no aid | 277.7 | 617.8 | 1003.5 (seed 3) | 0.989 | 0.984 | 0 | 0 | - |
| honest map | 290.5 | 416.0 | 415.7 (seed 14) | 1.000 | 0.984 | 0 | 0 | - |
| ramp-spoofed map | 635.2 | 751.0 | 853.9 (seed 0) | 0.873 | 0.984 | 0 | 0 | - |
| ramp-spoofed map, guarded build | 635.2 | 751.0 | 853.9 (seed 0) | 0.873 | 0.984 | 0 | 0 | - |
| ramp-spoofed map, guarded build + refusal | 635.2 | 751.0 | 853.9 (seed 0) | 0.873 | 0.984 | 0 | 0 | 0/20 |
| jump-spoofed map | 594.9 | 705.8 | 744.2 (seed 0) | 0.987 | 0.984 | 0 | 0 | - |
| jump-spoofed map, guarded build | 338.9 | 452.3 | 443.0 (seed 11) | 1.000 | 0.984 | 0 | 0 | - |
| jump-spoofed map, guarded build + refusal | 277.7 | 617.8 | 1003.5 (seed 3) | 0.989 | 0.984 | 0 | 0 | 20/20 |
