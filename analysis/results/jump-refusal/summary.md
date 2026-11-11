# Refusing a detected GNSS jump, before and after (#184)

Sim, every value `TBC`. Commit 84401c5, `python analysis/jump_refusal.py --seeds 50 --jobs 2`, 125.0 min. Seeds 0–49, paired: every variant runs on the same records. Nothing was chosen on these seeds: the thresholds are derived in `pnt.integrity.jump_guard`, and the behaviour was looked at on seeds 100–109.

Per-run data (`runs.json`, 7 MB, and `curves.json`, 1 MB) is not committed: the script writes it beside this file, and for this run it was moved to the git-ignored `analysis/results/runs/jump-refusal/`. Re-run the command above at 84401c5 to get it back; `--redraw --out` that folder rebuilds this summary and the figure from it.

`main` = the estimator with the jump guard off (the code path `main` runs); `undo` = the registered estimator, which now refuses a detected jump until it is undone; `never` and `lr` = the alternative re-admission rules (`ekf` only). `drone` is the `challenge-drone` leg as committed, `many` the same with every sector within 3 km heard, `timing` the `challenge-timing` leg. The jump is east, from 150 s.

## Held jump: does the output follow it?

Follows: horizontal error over half the jump (the issue's test; dead reckoning far from both the truth and the spoof also counts). On the spoof: within half the jump of where the spoofer puts the receiver. Medians over seeds unless stated. Excluded: share of the first 30 s / 300 s with `gnss_excluded`. Hazardous: epochs with error over the 50 m alert limit while HPL is under it (mean over seeds, and seeds with any).

| Leg | Jump (m) | Variant | Detected | Follows +30 / +120 s | On the spoof +30 / +120 s | Error +1 / +30 / +120 / +300 s (m) | Error +120 s, p95 / worst (m) | HPL +30 / +120 s (m) | Excluded 30 s / 300 s | Hazardous epochs (mean, seeds) |
|---|---|---|---|---|---|---|---|---|---|---|
| drone | 25 | `ekf | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 25 / 25 / 25 | 26 / 27 | 7 / 7 | 0.13 / 0.01 | 0, 0/50 |
| drone | 25 | `ekf | undo` | 50/50 | 50 / 50 | 1 / 1 | 3 / 115 / 1,225 / 4,870 | 3,605 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 25 | `ekf | never` | 50/50 | 50 / 50 | 1 / 1 | 3 / 115 / 1,225 / 4,870 | 3,605 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 25 | `ekf | lr` | 50/50 | 50 / 50 | 15 / 30 | 3 / 106 / 26 / 25 | 1,746 / 3,217 | 547 / 7 | 1.00 / 0.30 | 6, 15/50 |
| drone | 25 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 25 / 25 / 25 | 26 / 27 | 7 / 7 | 0.13 / 0.01 | 0, 0/50 |
| drone | 25 | `ekf-calibrated | undo` | 50/50 | 50 / 50 | 1 / 1 | 3 / 117 / 1,154 / 3,986 | 2,678 / 3,354 | 547 / 3,542 | 1.00 / 1.00 | 1, 2/50 |
| drone | 50 | `ekf | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 50 / 50 / 50 | 51 / 52 | 7 / 7 | 0.24 / 0.02 | 2,915, 50/50 |
| drone | 50 | `ekf | undo` | 50/50 | 50 / 50 | 0 / 0 | 3 / 115 / 1,263 / 5,244 | 3,790 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 50 | `ekf | never` | 50/50 | 50 / 50 | 0 / 0 | 3 / 115 / 1,263 / 5,244 | 3,790 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 50 | `ekf | lr` | 50/50 | 50 / 50 | 11 / 30 | 3 / 108 / 51 / 50 | 1,746 / 3,217 | 547 / 7 | 1.00 / 0.31 | 2,043, 45/50 |
| drone | 50 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 50 / 50 / 50 | 51 / 52 | 7 / 7 | 0.24 / 0.02 | 2,914, 50/50 |
| drone | 50 | `ekf-calibrated | undo` | 50/50 | 50 / 50 | 0 / 0 | 3 / 117 / 1,172 / 4,110 | 2,678 / 3,354 | 547 / 4,014 | 1.00 / 1.00 | 1, 2/50 |
| drone | 100 | `ekf | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 100 / 100 / 100 | 101 / 102 | 7 / 7 | 0.41 / 0.04 | 5,576, 50/50 |
| drone | 100 | `ekf | undo` | 50/50 | 50 / 50 | 0 / 0 | 3 / 115 / 1,263 / 5,244 | 3,790 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 100 | `ekf | never` | 50/50 | 50 / 50 | 0 / 0 | 3 / 115 / 1,263 / 5,244 | 3,790 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 100 | `ekf | lr` | 50/50 | 50 / 50 | 6 / 31 | 3 / 112 / 101 / 100 | 1,357 / 3,217 | 547 / 7 | 1.00 / 0.31 | 4,080, 46/50 |
| drone | 100 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 100 / 100 / 100 | 101 / 102 | 7 / 7 | 0.41 / 0.04 | 5,574, 50/50 |
| drone | 100 | `ekf-calibrated | undo` | 50/50 | 50 / 50 | 0 / 0 | 3 / 117 / 1,172 / 4,110 | 2,678 / 3,354 | 547 / 4,014 | 1.00 / 1.00 | 1, 2/50 |
| drone | 300 | `ekf | main` | 50/50 | 49 / 50 | 44 / 47 | 3 / 302 / 300 / 300 | 381 / 2,200 | 8 / 7 | 0.91 / 0.09 | 5,244, 49/50 |
| drone | 300 | `ekf | undo` | 50/50 | 6 / 50 | 0 / 0 | 3 / 115 / 1,263 / 5,244 | 3,790 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 300 | `ekf | never` | 50/50 | 6 / 50 | 0 / 0 | 3 / 115 / 1,263 / 5,244 | 3,790 / 4,373 | 547 / 2,659 | 1.00 / 1.00 | 3, 3/50 |
| drone | 300 | `ekf | lr` | 50/50 | 6 / 50 | 0 / 32 | 3 / 115 / 301 / 300 | 1,296 / 2,058 | 547 / 7 | 1.00 / 0.31 | 4,034, 46/50 |
| drone | 300 | `ekf-calibrated | main` | 50/50 | 46 / 49 | 42 / 45 | 3 / 301 / 300 / 300 | 629 / 2,308 | 8 / 7 | 0.91 / 0.09 | 4,939, 47/50 |
| drone | 300 | `ekf-calibrated | undo` | 50/50 | 6 / 49 | 0 / 1 | 3 / 117 / 1,172 / 4,110 | 2,678 / 3,354 | 547 / 4,014 | 1.00 / 1.00 | 1, 2/50 |
| many | 25 | `ekf | main` | 48/50 | 50 / 50 | 47 / 47 | 3 / 25 / 25 / 25 | 1,326 / 16,619 | 7 / 7 | 0.13 / 0.01 | 4, 3/50 |
| many | 25 | `ekf | undo` | 48/50 | 50 / 50 | 1 / 1 | 3 / 113 / 1,093 / 2,770 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 25 | `ekf | never` | 48/50 | 50 / 50 | 1 / 1 | 3 / 113 / 1,093 / 2,770 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 25 | `ekf | lr` | 48/50 | 50 / 50 | 16 / 25 | 3 / 103 / 446 / 26 | 3,006 / 16,619 | 547 / 270 | 1.00 / 0.38 | 4, 7/50 |
| many | 25 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 45 / 45 | 3 / 25 / 25 / 25 | 1,618 / 8,924 | 7 / 7 | 0.13 / 0.01 | 23, 4/50 |
| many | 25 | `ekf-calibrated | undo` | 50/50 | 50 / 50 | 1 / 1 | 3 / 110 / 1,093 / 2,908 | 4,026 / 8,924 | 547 / 4,126 | 1.00 / 1.00 | 32, 7/50 |
| many | 50 | `ekf | main` | 48/50 | 50 / 50 | 46 / 46 | 3 / 50 / 50 / 50 | 2,121 / 16,619 | 7 / 7 | 0.24 / 0.02 | 2,690, 50/50 |
| many | 50 | `ekf | undo` | 48/50 | 49 / 50 | 0 / 0 | 3 / 113 / 1,102 / 2,871 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 50 | `ekf | never` | 48/50 | 49 / 50 | 0 / 0 | 3 / 113 / 1,102 / 2,871 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 50 | `ekf | lr` | 48/50 | 50 / 50 | 13 / 25 | 3 / 107 / 459 / 51 | 2,912 / 16,619 | 547 / 270 | 1.00 / 0.41 | 1,707, 37/50 |
| many | 50 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 44 / 44 | 3 / 50 / 50 / 50 | 2,037 / 8,924 | 7 / 7 | 0.24 / 0.02 | 2,598, 49/50 |
| many | 50 | `ekf-calibrated | undo` | 50/50 | 50 / 50 | 0 / 0 | 3 / 110 / 1,102 / 2,910 | 4,026 / 8,924 | 547 / 4,126 | 1.00 / 1.00 | 32, 7/50 |
| many | 100 | `ekf | main` | 48/50 | 49 / 50 | 45 / 46 | 3 / 100 / 100 / 100 | 2,121 / 16,619 | 7 / 7 | 0.41 / 0.04 | 5,133, 50/50 |
| many | 100 | `ekf | undo` | 48/50 | 49 / 50 | 0 / 0 | 3 / 113 / 1,102 / 2,871 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 100 | `ekf | never` | 48/50 | 49 / 50 | 0 / 0 | 3 / 113 / 1,102 / 2,871 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 100 | `ekf | lr` | 48/50 | 49 / 50 | 9 / 25 | 3 / 107 / 484 / 101 | 2,912 / 16,619 | 547 / 270 | 1.00 / 0.38 | 3,267, 37/50 |
| many | 100 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 43 / 44 | 3 / 100 / 100 / 100 | 2,037 / 8,924 | 7 / 7 | 0.41 / 0.04 | 4,948, 49/50 |
| many | 100 | `ekf-calibrated | undo` | 50/50 | 50 / 50 | 0 / 0 | 3 / 110 / 1,102 / 2,910 | 4,026 / 8,924 | 547 / 4,126 | 1.00 / 1.00 | 32, 7/50 |
| many | 300 | `ekf | main` | 48/50 | 48 / 50 | 42 / 44 | 3 / 302 / 300 / 300 | 2,569 / 16,619 | 8 / 7 | 0.91 / 0.09 | 4,848, 49/50 |
| many | 300 | `ekf | undo` | 48/50 | 7 / 50 | 0 / 0 | 3 / 113 / 1,102 / 2,871 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 300 | `ekf | never` | 48/50 | 7 / 50 | 0 / 0 | 3 / 113 / 1,102 / 2,871 | 3,212 / 16,619 | 547 / 4,126 | 1.00 / 1.00 | 10, 6/50 |
| many | 300 | `ekf | lr` | 48/50 | 7 / 50 | 0 / 25 | 3 / 113 / 584 / 301 | 2,301 / 16,619 | 547 / 270 | 1.00 / 0.40 | 3,189, 38/50 |
| many | 300 | `ekf-calibrated | main` | 50/50 | 45 / 50 | 40 / 41 | 3 / 302 / 300 / 300 | 2,964 / 8,924 | 8 / 7 | 0.92 / 0.09 | 4,547, 48/50 |
| many | 300 | `ekf-calibrated | undo` | 50/50 | 5 / 50 | 0 / 0 | 3 / 110 / 1,102 / 2,910 | 4,026 / 8,924 | 547 / 4,126 | 1.00 / 1.00 | 32, 7/50 |
| timing | 25 | `ekf | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 25 / 25 / 25 | 27 / 28 | 7 / 7 | 0.11 / 0.01 | 0, 0/50 |
| timing | 25 | `ekf | undo` | 50/50 | 45 / 50 | 4 / 1 | 3 / 31 / 155 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 25 | `ekf | never` | 50/50 | 45 / 50 | 4 / 1 | 3 / 31 / 155 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 25 | `ekf | lr` | 50/50 | 47 / 50 | 21 / 24 | 3 / 25 / 38 / 26 | 985 / 2,333 | 547 / 367 | 1.00 / 0.45 | 3, 8/50 |
| timing | 25 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 25 / 25 / 25 | 27 / 28 | 7 / 7 | 0.11 / 0.01 | 0, 0/50 |
| timing | 25 | `ekf-calibrated | undo` | 50/50 | 46 / 50 | 4 / 1 | 3 / 34 / 158 / 2,314 | 1,626 / 1,981 | 547 / 4,126 | 1.00 / 1.00 | 2, 5/50 |
| timing | 50 | `ekf | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 50 / 50 / 50 | 52 / 53 | 7 / 7 | 0.22 / 0.02 | 2,852, 50/50 |
| timing | 50 | `ekf | undo` | 50/50 | 32 / 50 | 2 / 0 | 3 / 31 / 157 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 50 | `ekf | never` | 50/50 | 32 / 50 | 2 / 0 | 3 / 31 / 157 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 50 | `ekf | lr` | 50/50 | 37 / 50 | 15 / 23 | 3 / 41 / 53 / 51 | 985 / 2,333 | 547 / 739 | 1.00 / 0.51 | 1,810, 42/50 |
| timing | 50 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 50 / 50 / 50 | 52 / 53 | 7 / 7 | 0.21 / 0.02 | 2,854, 50/50 |
| timing | 50 | `ekf-calibrated | undo` | 50/50 | 35 / 50 | 2 / 0 | 3 / 35 / 163 / 2,314 | 1,626 / 1,981 | 547 / 4,126 | 1.00 / 1.00 | 2, 5/50 |
| timing | 100 | `ekf | main` | 50/50 | 50 / 50 | 50 / 50 | 3 / 100 / 100 / 100 | 102 / 103 | 7 / 7 | 0.37 / 0.04 | 5,586, 50/50 |
| timing | 100 | `ekf | undo` | 50/50 | 12 / 47 | 0 / 2 | 3 / 31 / 157 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 100 | `ekf | never` | 50/50 | 12 / 47 | 0 / 2 | 3 / 31 / 157 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 100 | `ekf | lr` | 50/50 | 19 / 48 | 9 / 22 | 3 / 38 / 101 / 101 | 1,276 / 2,333 | 547 / 864 | 1.00 / 0.53 | 3,511, 42/50 |
| timing | 100 | `ekf-calibrated | main` | 50/50 | 50 / 50 | 49 / 50 | 3 / 100 / 100 / 100 | 102 / 103 | 7 / 7 | 0.37 / 0.04 | 5,568, 50/50 |
| timing | 100 | `ekf-calibrated | undo` | 50/50 | 14 / 46 | 0 / 2 | 3 / 35 / 163 / 2,314 | 1,626 / 1,981 | 547 / 4,126 | 1.00 / 1.00 | 2, 5/50 |
| timing | 300 | `ekf | main` | 50/50 | 49 / 50 | 45 / 47 | 3 / 300 / 300 / 300 | 400 / 2,333 | 7 / 7 | 0.82 / 0.08 | 5,317, 50/50 |
| timing | 300 | `ekf | undo` | 50/50 | 6 / 27 | 0 / 2 | 3 / 31 / 157 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 300 | `ekf | never` | 50/50 | 6 / 27 | 0 / 2 | 3 / 31 / 157 / 1,837 | 1,597 / 2,333 | 547 / 4,126 | 1.00 / 1.00 | 4, 6/50 |
| timing | 300 | `ekf | lr` | 50/50 | 8 / 37 | 3 / 23 | 3 / 33 / 299 / 300 | 1,402 / 2,333 | 547 / 847 | 1.00 / 0.65 | 3,362, 42/50 |
| timing | 300 | `ekf-calibrated | main` | 50/50 | 47 / 50 | 44 / 47 | 3 / 300 / 300 / 300 | 638 / 1,981 | 7 / 7 | 0.83 / 0.08 | 5,233, 49/50 |
| timing | 300 | `ekf-calibrated | undo` | 50/50 | 5 / 29 | 1 / 1 | 3 / 35 / 163 / 2,314 | 1,626 / 1,981 | 547 / 4,126 | 1.00 / 1.00 | 2, 5/50 |

## Jump ended at 300 s: does honest GNSS come back?

Re-admitted: seeds where the filter uses a GNSS fix taken after the spoof ended, before the run ends; delay from the end to the first epoch at which it has (median / worst over the seeds re-admitted).

| Leg | Jump (m) | Variant | Re-admitted | Delay median / worst (s) | Error end +30 / +120 s (m) | Hazardous epochs (mean, seeds) |
|---|---|---|---|---|---|---|
| drone | 25 | `ekf | main` | 50/50 | 2.3 / 3.5 | 1 / 1 | 0, 0/50 |
| drone | 25 | `ekf | undo` | 49/50 | 0.1 / 0.3 | 1 / 1 | 2, 2/50 |
| drone | 25 | `ekf | never` | 0/50 | – / – | 1,754 / 3,807 | 3, 3/50 |
| drone | 25 | `ekf | lr` | 37/50 | 56.3 / 406.3 | 205 / 423 | 8, 16/50 |
| drone | 25 | `ekf-calibrated | main` | 50/50 | 2.3 / 3.5 | 1 / 1 | 0, 0/50 |
| drone | 25 | `ekf-calibrated | undo` | 49/50 | 0.1 / 0.3 | 1 / 1 | 0, 1/50 |
| drone | 50 | `ekf | main` | 50/50 | 4.9 / 395.1 | 1 / 1 | 765, 50/50 |
| drone | 50 | `ekf | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 2, 2/50 |
| drone | 50 | `ekf | never` | 0/50 | – / – | 1,780 / 4,164 | 3, 3/50 |
| drone | 50 | `ekf | lr` | 36/50 | 74.3 / 406.3 | 190 / 967 | 294, 37/50 |
| drone | 50 | `ekf-calibrated | main` | 49/50 | 4.9 / 8.7 | 1 / 1 | 763, 50/50 |
| drone | 50 | `ekf-calibrated | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 0, 1/50 |
| drone | 100 | `ekf | main` | 50/50 | 8.5 / 217.3 | 2 / 1 | 1,428, 50/50 |
| drone | 100 | `ekf | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 2, 2/50 |
| drone | 100 | `ekf | never` | 0/50 | – / – | 1,780 / 4,164 | 3, 3/50 |
| drone | 100 | `ekf | lr` | 39/50 | 61.3 / 363.3 | 146 / 443 | 600, 38/50 |
| drone | 100 | `ekf-calibrated | main` | 49/50 | 8.5 / 370.3 | 2 / 1 | 1,426, 50/50 |
| drone | 100 | `ekf-calibrated | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 0, 1/50 |
| drone | 300 | `ekf | main` | 48/50 | 18.8 / 53.1 | 167 / 2 | 1,193, 48/50 |
| drone | 300 | `ekf | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 2, 2/50 |
| drone | 300 | `ekf | never` | 0/50 | – / – | 1,780 / 4,164 | 3, 3/50 |
| drone | 300 | `ekf | lr` | 38/50 | 83.3 / 391.3 | 162 / 1,051 | 531, 39/50 |
| drone | 300 | `ekf-calibrated | main` | 45/50 | 18.9 / 223.3 | 181 / 2 | 1,139, 47/50 |
| drone | 300 | `ekf-calibrated | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 0, 1/50 |
| many | 25 | `ekf | main` | 47/50 | 2.3 / 3.5 | 1 / 1 | 4, 3/50 |
| many | 25 | `ekf | undo` | 47/50 | 0.1 / 0.3 | 1 / 1 | 9, 6/50 |
| many | 25 | `ekf | never` | 0/50 | – / – | 1,318 / 2,440 | 10, 6/50 |
| many | 25 | `ekf | lr` | 26/50 | 25.6 / 337.3 | 206 / 1,143 | 6, 10/50 |
| many | 25 | `ekf-calibrated | main` | 47/50 | 2.5 / 383.5 | 1 / 1 | 23, 4/50 |
| many | 25 | `ekf-calibrated | undo` | 49/50 | 0.1 / 383.5 | 1 / 1 | 32, 7/50 |
| many | 50 | `ekf | main` | 45/50 | 4.9 / 5.5 | 1 / 1 | 724, 50/50 |
| many | 50 | `ekf | undo` | 48/50 | 0.1 / 0.1 | 1 / 1 | 9, 6/50 |
| many | 50 | `ekf | never` | 0/50 | – / – | 1,322 / 2,507 | 10, 6/50 |
| many | 50 | `ekf | lr` | 25/50 | 37.3 / 212.3 | 193 / 1,166 | 288, 32/50 |
| many | 50 | `ekf-calibrated | main` | 46/50 | 5.1 / 383.5 | 2 / 1 | 692, 49/50 |
| many | 50 | `ekf-calibrated | undo` | 50/50 | 0.1 / 383.5 | 1 / 1 | 32, 7/50 |
| many | 100 | `ekf | main` | 45/50 | 8.5 / 9.3 | 2 / 1 | 1,325, 50/50 |
| many | 100 | `ekf | undo` | 48/50 | 0.1 / 0.1 | 1 / 1 | 9, 6/50 |
| many | 100 | `ekf | never` | 0/50 | – / – | 1,322 / 2,507 | 10, 6/50 |
| many | 100 | `ekf | lr` | 26/50 | 39.8 / 261.3 | 150 / 1,147 | 546, 32/50 |
| many | 100 | `ekf-calibrated | main` | 46/50 | 8.5 / 383.5 | 2 / 1 | 1,276, 49/50 |
| many | 100 | `ekf-calibrated | undo` | 50/50 | 0.1 / 383.5 | 1 / 1 | 32, 7/50 |
| many | 300 | `ekf | main` | 45/50 | 18.9 / 26.5 | 169 / 1 | 1,126, 49/50 |
| many | 300 | `ekf | undo` | 48/50 | 0.1 / 0.1 | 1 / 1 | 9, 6/50 |
| many | 300 | `ekf | never` | 0/50 | – / – | 1,322 / 2,507 | 10, 6/50 |
| many | 300 | `ekf | lr` | 26/50 | 39.8 / 300.3 | 171 / 1,151 | 446, 34/50 |
| many | 300 | `ekf-calibrated | main` | 45/50 | 18.9 / 383.5 | 185 / 2 | 1,069, 47/50 |
| many | 300 | `ekf-calibrated | undo` | 50/50 | 0.1 / 383.5 | 1 / 1 | 32, 7/50 |
| timing | 25 | `ekf | main` | 50/50 | 3.1 / 4.3 | 1 / 1 | 0, 0/50 |
| timing | 25 | `ekf | undo` | 49/50 | 0.1 / 0.3 | 1 / 1 | 2, 3/50 |
| timing | 25 | `ekf | never` | 0/50 | – / – | 500 / 1,374 | 4, 6/50 |
| timing | 25 | `ekf | lr` | 34/50 | 91.3 / 384.3 | 43 / 28 | 4, 9/50 |
| timing | 25 | `ekf-calibrated | main` | 50/50 | 3.1 / 4.5 | 1 / 1 | 0, 0/50 |
| timing | 25 | `ekf-calibrated | undo` | 49/50 | 0.1 / 0.3 | 1 / 1 | 0, 1/50 |
| timing | 50 | `ekf | main` | 50/50 | 6.3 / 53.1 | 1 / 1 | 754, 50/50 |
| timing | 50 | `ekf | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 2, 3/50 |
| timing | 50 | `ekf | never` | 0/50 | – / – | 500 / 1,374 | 4, 6/50 |
| timing | 50 | `ekf | lr` | 34/50 | 88.8 / 374.3 | 66 / 8 | 268, 28/50 |
| timing | 50 | `ekf-calibrated | main` | 50/50 | 6.3 / 12.9 | 1 / 1 | 752, 50/50 |
| timing | 50 | `ekf-calibrated | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 0, 1/50 |
| timing | 100 | `ekf | main` | 50/50 | 10.9 / 52.7 | 1 / 1 | 1,435, 50/50 |
| timing | 100 | `ekf | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 2, 3/50 |
| timing | 100 | `ekf | never` | 0/50 | – / – | 500 / 1,374 | 4, 6/50 |
| timing | 100 | `ekf | lr` | 33/50 | 91.3 / 332.3 | 114 / 60 | 467, 26/50 |
| timing | 100 | `ekf-calibrated | main` | 50/50 | 11.1 / 82.3 | 1 / 1 | 1,417, 50/50 |
| timing | 100 | `ekf-calibrated | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 0, 1/50 |
| timing | 300 | `ekf | main` | 48/50 | 24.4 / 128.3 | 2 / 1 | 1,211, 48/50 |
| timing | 300 | `ekf | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 2, 3/50 |
| timing | 300 | `ekf | never` | 0/50 | – / – | 500 / 1,374 | 4, 6/50 |
| timing | 300 | `ekf | lr` | 35/50 | 91.3 / 336.3 | 291 / 97 | 404, 26/50 |
| timing | 300 | `ekf-calibrated | main` | 47/50 | 24.5 / 106.1 | 2 / 1 | 1,208, 48/50 |
| timing | 300 | `ekf-calibrated | undo` | 50/50 | 0.1 / 0.1 | 1 / 1 | 0, 1/50 |

## False alarms and recovery on clean runs

`pnt.metrics` false alarms (any alarm flag held 1 s outside a spoof window). Outage: GPS is lost from 60 s to 660 s; delay to the first epoch at which the filter has used a fix taken after it returns.

| Leg | Entry | Variant | False alarms / h (mean) | Seeds with one | Hazardous epochs (mean) | GNSS used again after the outage, median / worst (s) |
|---|---|---|---|---|---|---|
| drone | nominal | `ekf | main` | 0.00 | 0/50 | 0.0 | – |
| drone | nominal | `ekf | undo` | 0.00 | 0/50 | 0.0 | – |
| drone | nominal | `ekf | never` | 0.00 | 0/50 | 0.0 | – |
| drone | nominal | `ekf | lr` | 0.00 | 0/50 | 0.0 | – |
| drone | nominal | `ekf-calibrated | main` | 0.00 | 0/50 | 0.0 | – |
| drone | nominal | `ekf-calibrated | undo` | 0.00 | 0/50 | 0.0 | – |
| drone | outage | `ekf | main` | 4.10 | 39/50 | 6.4 | 0.1 / 32.1 |
| drone | outage | `ekf | undo` | 4.10 | 39/50 | 6.4 | 0.1 / 32.1 |
| drone | outage | `ekf | never` | 4.10 | 39/50 | 6.4 | 0.1 / 32.1 |
| drone | outage | `ekf | lr` | 4.10 | 39/50 | 6.4 | 0.1 / 32.1 |
| drone | outage | `ekf-calibrated | main` | 3.90 | 39/50 | 1.1 | 0.1 / 13.5 |
| drone | outage | `ekf-calibrated | undo` | 3.90 | 39/50 | 1.1 | 0.1 / 13.5 |
| many | nominal | `ekf | main` | 0.20 | 2/50 | 1.9 | – |
| many | nominal | `ekf | undo` | 0.20 | 2/50 | 1.9 | – |
| many | nominal | `ekf | never` | 0.20 | 2/50 | 1.9 | – |
| many | nominal | `ekf | lr` | 0.20 | 2/50 | 1.9 | – |
| many | nominal | `ekf-calibrated | main` | 0.20 | 1/50 | 1.0 | – |
| many | nominal | `ekf-calibrated | undo` | 0.20 | 1/50 | 1.0 | – |
| many | outage | `ekf | main` | 2.60 | 26/50 | 9.8 | 0.1 / – |
| many | outage | `ekf | undo` | 2.60 | 26/50 | 9.8 | 0.1 / – |
| many | outage | `ekf | never` | 2.60 | 26/50 | 9.8 | 0.1 / – |
| many | outage | `ekf | lr` | 2.60 | 26/50 | 9.8 | 0.1 / – |
| many | outage | `ekf-calibrated | main` | 2.70 | 26/50 | 17.3 | 0.1 / – |
| many | outage | `ekf-calibrated | undo` | 2.70 | 26/50 | 17.3 | 0.1 / – |
| timing | nominal | `ekf | main` | 0.00 | 0/50 | 0.0 | – |
| timing | nominal | `ekf | undo` | 0.00 | 0/50 | 0.0 | – |
| timing | nominal | `ekf | never` | 0.00 | 0/50 | 0.0 | – |
| timing | nominal | `ekf | lr` | 0.00 | 0/50 | 0.0 | – |
| timing | nominal | `ekf-calibrated | main` | 0.00 | 0/50 | 0.0 | – |
| timing | nominal | `ekf-calibrated | undo` | 0.00 | 0/50 | 0.0 | – |
| timing | outage | `ekf | main` | 3.20 | 32/50 | 0.4 | 0.1 / 20.5 |
| timing | outage | `ekf | undo` | 3.20 | 32/50 | 0.4 | 0.1 / 20.5 |
| timing | outage | `ekf | never` | 3.20 | 32/50 | 0.4 | 0.1 / 20.5 |
| timing | outage | `ekf | lr` | 3.20 | 32/50 | 0.4 | 0.1 / 20.5 |
| timing | outage | `ekf-calibrated | main` | 3.40 | 33/50 | 1.7 | 0.1 / 8.3 |
| timing | outage | `ekf-calibrated | undo` | 3.40 | 33/50 | 1.7 | 0.1 / 8.3 |

## Runtime

| Variant | Median s per run | Worst |
|---|---|---|
| `ekf | main` | 0.6 | 2.1 |
| `ekf | undo` | 1.1 | 2.7 |
| `ekf | never` | 1.1 | 2.5 |
| `ekf | lr` | 1.1 | 2.5 |
| `ekf-calibrated | main` | 1.4 | 10.5 |
| `ekf-calibrated | undo` | 1.9 | 11.6 |
