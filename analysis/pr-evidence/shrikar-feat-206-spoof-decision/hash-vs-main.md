# Estimator output against main (#206)

Sim, seed 0. SHA-256 (first 16 hex) of every Estimate each registered estimator gives, and of the sim's measurement stream. Branch at `8420ce7` (code as the final commit), `origin/main` at `e66ccf7`. Script: `~/.cache/pnt-work/spoof-scratch/hashcheck.py` (not committed).

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

Every difference is an opt-in `-guard` estimator on a scenario where the jump guard latches. With `gnss_jump_latched` removed from the flags, all 9 hash the same as `main` (spoof-jump, meaconing, uc02-yow-approach-adsb-spoofed x ekf-guard, ekf-imu-guard, ekf-calibrated-guard): the new flag is the only change. Estimates flagged per run: 2,099 (spoof-jump), 2,099 (meaconing), 828 (uc02), the same for each of the three estimators.
