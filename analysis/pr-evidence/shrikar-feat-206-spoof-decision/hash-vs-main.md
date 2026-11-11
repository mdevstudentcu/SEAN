# Estimator output against main (#206)

Sim, seed 0. SHA-256 (first 16 hex) of every Estimate each registered estimator gives (11), and of the sim's measurement stream. Branch at `887eab7`, `origin/main` at `0a788b2` (its base; `c21e047`, main when this was written, changes nothing under `src/`). Script: a copy of `~/.cache/pnt-work/spoof-scratch/hashcheck.py` that also hashes each estimate with `gnss_jump_latched` removed from its flags (not committed).

| Scenario | Measurements | Estimators identical | Estimators that differ |
| --- | --- | --- | --- |
| `challenge-drone-nominal` | same | 11 of 11 | none |
| `challenge-drone-outage` | same | 11 of 11 | none |
| `gps-outage` | same | 11 of 11 | none |
| `hostile-beacon` | same | 11 of 11 | none |
| `jamming-zone` | same | 11 of 11 | none |
| `meaconing` | same | 8 of 11 | `ekf-calibrated-guard`, `ekf-guard`, `ekf-imu-guard` |
| `nominal` | same | 11 of 11 | none |
| `spoof-jump` | same | 8 of 11 | `ekf-calibrated-guard`, `ekf-guard`, `ekf-imu-guard` |
| `spoof-ramp` | same | 11 of 11 | none |
| `time-spoof` | same | 11 of 11 | none |
| `uc02-yow-approach-adsb-spoofed` | same | 8 of 11 | `ekf-calibrated-guard`, `ekf-guard`, `ekf-imu-guard` |

Every difference is an opt-in `-guard` estimator on a scenario where the jump guard latches. With `gnss_jump_latched` removed from the flags, all 9 hash the same as `main`: the new flag is the only change.
