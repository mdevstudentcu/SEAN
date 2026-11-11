# False alarms per hour on clean data (#274)

Sim, and replay of one real static session. **No real flight hours.** Generated tables below the line come from:

```bash
OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONPATH=src \
  python analysis/false_alarm_rate.py run --sessions <data/sessions> --seeds 50 --jobs 3 \
  --label main --out analysis/results/runs/false-alarm-rate/main.json          # at 47a91e0
PYTHONPATH=<main 3493cfb + PR #241's eb1f4a9, 611fa7b, 2510902 cherry-picked>/src \
  python analysis/false_alarm_rate.py run --no-sim --jobs 1 --sessions <data/sessions> \
  --label "main 3493cfb + PR #241 cherry-picked (throwaway)" --out .../pr241.json
python analysis/false_alarm_rate.py report .../main.json .../pr241.json
```

Seeds 0-49 on every entry (no seed cut: 235 s with 3 workers on this Mac). The `7a841db` commit of the second run is a local throwaway branch, not on GitHub: it is `origin/main` `3493cfb` with the three commits of open PR #241 cherry-picked, run to show the real session with that fix.

## What it says

| Data | Hours (per estimator) | Spoof alarms (`spoof_suspected`, `time_spoof_suspected`, sky `spoofed`) | GNSS exclusion (`gnss_excluded`) | Jump guard latch / sky `suspect` (`ekf-guard`) | Do not navigate (HPL > AL) |
| --- | --- | --- | --- | --- | --- |
| Sim, challenge legs + realistic (`nominal` entries) | 35.0 | 0 (95 % bound 0.086/h) | 0 (0.086/h) | 0 (0.086/h) | 0 (0.086/h) |
| Sim, square circuit (`nominal` scenario) | 5.0 | 0 (0.60/h) | **21** (4.2/h, bound 6.1/h) | **1** (0.2/h, bound 0.95/h) | 0 (0.60/h) |
| Real, static, `main` (`20261111-0845-live-laptop-gps`, 601 s) | 0.17 | 0 (18/h) | **10** (60/h, bound 102/h) | 0 (18/h) | **10** (60/h) |
| Real, static, `main` + PR #241 (same session) | 0.17 | 0 (18/h) | 0 (18/h) | 0 (18/h) | 0 (18/h) |
| **All clean data on `main`** (sky run excluded, see below) | **40.2** | **0 (0.075/h)** | **31** (0.77/h, bound 1.04/h) | **1** (0.025/h, bound 0.12/h) | **10** (0.25/h, bound 0.42/h) |

Counts are the same for `ekf`, `ekf-guard` and `ekf-spoof` except the latch, which only `ekf-guard` has. `time PL > limit` fired nowhere.

**Sentence a presenter can say (only this, as it stands on `main`):** "In 40 hours of clean data, 35 of them simulated flight on the challenge and realistic legs and 10 minutes real and static, no spoofing alarm fired, which bounds that rate at 0.075 per hour at 95 %. Our GPS-rejection alarm did fire: on a simulated circuit with instant right-angle turns, and on our one real session from a barometer fault whose fix is in review." Do not say "no false alarms" without the second sentence, and do not say "real flight".

## Every false alarm, and its cause

- **Square circuit, 21 `gnss_excluded` (15 of 50 seeds), all three estimators alike.** Every onset is 1.4 to 3.0 s after a corner of the `square` trajectory (corners every 25 s: side 200 m at 8 m/s), so the rejection starts 0.4 to 2.0 s after the corner. `square` turns 90 degrees instantly, which `sim/trajectory.py` says no vehicle can fly; the constant-velocity filter's GNSS gate rejects about a second of fixes through the turn. A real hard manoeuvre would do the same (`guard_manoeuvre.py`), so this is a property of the gate, not only of the sim. One of them (seed 38, 77.2 s) also latched the jump guard, which makes the sky decision `suspect` (not `spoofed`).
- **Real session on `main`, 10 `gnss_excluded` and 10 do-not-navigate onsets, from 204 s to the end.** Issue #227: the barometer wanders, the 3-D GNSS gate fails on height, honest GPS is refused, HPL grows past 50 m. Shown, not guessed: with PR #241 the same 2602 epochs flagged `gnss_excluded` on `main` are flagged `gnss_alt_excluded` instead (identical epoch list), i.e. each refused fix passes the horizontal gate and only its height fails; then 0 alarms and 0 do-not-navigate onsets. (`gnss_alt_excluded` is a caution, not an alarm, and is not counted.) By `pnt.metrics`' rule the one lock-out counts as 10 onsets, because single accepted fixes break it up.

## Definitions

- **False alarm** (`pnt.metrics`, reused): an epoch carrying any of `ALARM_FLAGS` (`gnss_excluded`, `spoof_suspected`, `time_spoof_suspected`), counted once when the run of alarmed epochs has lasted `ALARM_HOLD_S` = 1 s, outside every spoof window. Exposure: the time outside spoof windows. The script's count equals `metrics.score`'s on all 900 sim runs.
- The jump guard latch (`gnss_jump_latched`), the sky decision (ADR-0041, `suspect` or worse, and `spoofed`), HPL over the 50 m alert limit and the time PL over 1.5 us have no false-alarm count in `pnt.metrics`; the script counts them by the same rule. The two protection-level alerts start after the panel's start-up rule (first `nominal` estimate, or 30 s).
- **Bound:** one-sided 95 % exact Poisson upper bound, chi2(0.95, 2k+2)/2/T; 2.996/T for zero events.

## What it is not

- **No real flight hours.** The only real session with GNSS in the sessions folder is static and 10 minutes long; its bound (18/h) is weak. The session with 120 real skyviews (`20261111-0040-static-fullsuite`, PR #239: 0 false alarms) is not in the folder, so it is not recomputed or counted here.
- **Sim flight**, placeholder error models (`systems/verification.md` *Sim validity*), 50 seeds each.
- **The tower monitor barely tested.** `ekf-spoof`'s tower tests held an opinion for 7.4 of the 40.2 h (0 on `realistic`, 0.2 h on the drone leg, 0 on the real session): zero `spoof_suspected` elsewhere says nothing about it.
- **The sky checks ran only on simulated skies** (`spoof-jump-sky` before its spoof, 2.1 h, 72 skyviews a run). Its records before the spoof are the `nominal` scenario's at the same seed (checked identical), so it is kept out of the pooled column; it shows the same corner alarms. Everywhere else the decision judged the flags only.
- Faulted entries' clean time before their fault is left out: it is the same draws as the set's `nominal` entry at the same seed (checked identical), so it would count the same samples twice.
- Not covered: `ekf-calibrated`, `ekf-imu`, `ekf-mhss` and the other opt-in estimators; the `challenge-drone-hop`, `easy`, `worst` and `realistic-with-base` `nominal` entries; the dashboard's own latching (it merges a condition that clears for under 2 s).

---


- `main`: commit `47a91e0`; sim seeds 0-49 of challenge-drone-nominal, challenge-timing-nominal, challenge-approach-nominal, realistic-nominal, nominal, spoof-jump-sky; real sessions: 20261111-0845-live-laptop-gps; 235 s with 3 workers (arm64)
- `main 3493cfb + PR #241 cherry-picked (throwaway)`: commit `7a841db`; no sim; real sessions: 20261111-0845-live-laptop-gps; 4 s with 1 workers (arm64)

Each cell: false-alarm onsets / exposure hours / rate per hour / one-sided 95 % upper bound per hour (exact Poisson; zero events in T hours gives 3.0/T).

## Spoof and integrity alarms

| Estimator | Alarm | sim, challenge + realistic (`main`) | sim, square circuit (`main`) | sim, square, before spoof (sky) (`main`) | real, static (`main`) | **all clean data, sky run excluded** (`main`) | real, static (`main 3493cfb + PR #241 cherry-picked (throwaway)`) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ekf` | any (metrics) | 0 / 34.99 h / 0 / 0.0856 | 21 / 5.00 h / 4.2 / 6.05 | 8 / 2.08 h / 3.85 / 6.94 | 10 / 0.17 h / 60 / 102 | 31 / 40.15 h / 0.772 / 1.04 | 0 / 0.17 h / 0 / 18 |
| `ekf` | gnss_excluded | 0 / 34.99 h / 0 / 0.0856 | 21 / 5.00 h / 4.2 / 6.05 | 8 / 2.08 h / 3.85 / 6.94 | 10 / 0.17 h / 60 / 102 | 31 / 40.15 h / 0.772 / 1.04 | 0 / 0.17 h / 0 / 18 |
| `ekf` | spoof_suspected | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf` | time_spoof_suspected | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf` | gnss_jump_latched | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf` | sky suspect+ | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf` | sky spoofed | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | any (metrics) | 0 / 34.99 h / 0 / 0.0856 | 21 / 5.00 h / 4.2 / 6.05 | 8 / 2.08 h / 3.85 / 6.94 | 10 / 0.17 h / 60 / 102 | 31 / 40.15 h / 0.772 / 1.04 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | gnss_excluded | 0 / 34.99 h / 0 / 0.0856 | 21 / 5.00 h / 4.2 / 6.05 | 8 / 2.08 h / 3.85 / 6.94 | 10 / 0.17 h / 60 / 102 | 31 / 40.15 h / 0.772 / 1.04 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | spoof_suspected | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | time_spoof_suspected | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | gnss_jump_latched | 0 / 34.99 h / 0 / 0.0856 | 1 / 5.00 h / 0.2 / 0.949 | 1 / 2.08 h / 0.481 / 2.28 | 0 / 0.17 h / 0 / 18 | 1 / 40.15 h / 0.0249 / 0.118 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | sky suspect+ | 0 / 34.99 h / 0 / 0.0856 | 1 / 5.00 h / 0.2 / 0.949 | 1 / 2.08 h / 0.481 / 2.28 | 0 / 0.17 h / 0 / 18 | 1 / 40.15 h / 0.0249 / 0.118 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | sky spoofed | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | any (metrics) | 0 / 34.99 h / 0 / 0.0856 | 21 / 5.00 h / 4.2 / 6.05 | 8 / 2.08 h / 3.85 / 6.94 | 10 / 0.17 h / 60 / 102 | 31 / 40.15 h / 0.772 / 1.04 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | gnss_excluded | 0 / 34.99 h / 0 / 0.0856 | 21 / 5.00 h / 4.2 / 6.05 | 8 / 2.08 h / 3.85 / 6.94 | 10 / 0.17 h / 60 / 102 | 31 / 40.15 h / 0.772 / 1.04 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | spoof_suspected | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | time_spoof_suspected | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | gnss_jump_latched | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | sky suspect+ | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | sky spoofed | 0 / 34.99 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.599 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |

## Do-not-navigate alerts (unavailable, not a spoof alarm)

| Estimator | Alarm | sim, challenge + realistic (`main`) | sim, square circuit (`main`) | sim, square, before spoof (sky) (`main`) | real, static (`main`) | **all clean data, sky run excluded** (`main`) | real, static (`main 3493cfb + PR #241 cherry-picked (throwaway)`) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ekf` | do not navigate (HPL > AL) | 0 / 34.98 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.6 | 0 / 2.08 h / 0 / 1.44 | 10 / 0.17 h / 60.1 / 102 | 10 / 40.15 h / 0.249 / 0.423 | 0 / 0.17 h / 0 / 18 |
| `ekf` | time PL > limit | 0 / 34.98 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.6 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | do not navigate (HPL > AL) | 0 / 34.98 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.6 | 0 / 2.08 h / 0 / 1.44 | 10 / 0.17 h / 60.1 / 102 | 10 / 40.15 h / 0.249 / 0.423 | 0 / 0.17 h / 0 / 18 |
| `ekf-guard` | time PL > limit | 0 / 34.98 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.6 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | do not navigate (HPL > AL) | 0 / 34.98 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.6 | 0 / 2.08 h / 0 / 1.44 | 10 / 0.17 h / 60.1 / 102 | 10 / 40.15 h / 0.249 / 0.423 | 0 / 0.17 h / 0 / 18 |
| `ekf-spoof` | time PL > limit | 0 / 34.98 h / 0 / 0.0856 | 0 / 5.00 h / 0 / 0.6 | 0 / 2.08 h / 0 / 1.44 | 0 / 0.17 h / 0 / 18 | 0 / 40.15 h / 0 / 0.0746 | 0 / 0.17 h / 0 / 18 |

## Exposure per entry and session

Hours per estimator are clean hours (the start-up rule takes a little off the do-not-navigate rows). The tower monitor's column is the part of them in which at least one of its tower tests held an opinion (it needs `min_sites` sites in both windows); outside it `ekf-spoof` cannot raise its own alarm.

| Data | Entry or session | Runs | Hours per estimator | `ekf-spoof` tower tests testing (h) | Skyviews per run |
| --- | --- | --- | --- | --- | --- |
| sim, challenge + realistic (`main`) | `challenge-drone-nominal` | 50 | 9.997 | 0.226 | 0 |
| sim, challenge + realistic (`main`) | `challenge-timing-nominal` | 50 | 9.997 | 0.091 | 0 |
| sim, challenge + realistic (`main`) | `challenge-approach-nominal` | 50 | 9.997 | 2.491 | 0 |
| sim, challenge + realistic (`main`) | `realistic-nominal` | 50 | 4.997 | 0.000 | 0 |
| sim, square circuit (`main`) | `nominal` | 50 | 4.997 | 4.569 | 0 |
| sim, square, before spoof (sky) (`main`) | `spoof-jump-sky` | 50 | 2.081 | 1.653 | 72 |
| real, static (`main`) | `20261111-0845-live-laptop-gps` | 1 | 0.167 | 0.000 | 0 |
| real, static (`main 3493cfb + PR #241 cherry-picked (throwaway)`) | `20261111-0845-live-laptop-gps` | 1 | 0.167 | 0.000 | 0 |

## Every false alarm and do-not-navigate onset

Seconds from the run's first estimate. `any (metrics)` is left out: it is the union of the three `ALARM_FLAGS` rows.

- `main`, sim, square circuit, `nominal`, seed 16, `ekf`: gnss_excluded, 1 at 351.8 s
- `main`, sim, square circuit, `nominal`, seed 16, `ekf-guard`: gnss_excluded, 1 at 351.8 s
- `main`, sim, square circuit, `nominal`, seed 16, `ekf-spoof`: gnss_excluded, 1 at 351.8 s
- `main`, sim, square circuit, `nominal`, seed 17, `ekf`: gnss_excluded, 1 at 78.0 s
- `main`, sim, square circuit, `nominal`, seed 17, `ekf-guard`: gnss_excluded, 1 at 78.0 s
- `main`, sim, square circuit, `nominal`, seed 17, `ekf-spoof`: gnss_excluded, 1 at 78.0 s
- `main`, sim, square circuit, `nominal`, seed 19, `ekf`: gnss_excluded, 1 at 177.0 s
- `main`, sim, square circuit, `nominal`, seed 19, `ekf-guard`: gnss_excluded, 1 at 177.0 s
- `main`, sim, square circuit, `nominal`, seed 19, `ekf-spoof`: gnss_excluded, 1 at 177.0 s
- `main`, sim, square circuit, `nominal`, seed 26, `ekf`: gnss_excluded, 3 at 277.6, 327.0, 351.8 s
- `main`, sim, square circuit, `nominal`, seed 26, `ekf-guard`: gnss_excluded, 3 at 277.6, 327.0, 351.8 s
- `main`, sim, square circuit, `nominal`, seed 26, `ekf-spoof`: gnss_excluded, 3 at 277.6, 327.0, 351.8 s
- `main`, sim, square circuit, `nominal`, seed 28, `ekf`: gnss_excluded, 1 at 227.6 s
- `main`, sim, square circuit, `nominal`, seed 28, `ekf-guard`: gnss_excluded, 1 at 227.6 s
- `main`, sim, square circuit, `nominal`, seed 28, `ekf-spoof`: gnss_excluded, 1 at 227.6 s
- `main`, sim, square circuit, `nominal`, seed 30, `ekf`: gnss_excluded, 2 at 101.6, 202.8 s
- `main`, sim, square circuit, `nominal`, seed 30, `ekf-guard`: gnss_excluded, 2 at 101.6, 202.8 s
- `main`, sim, square circuit, `nominal`, seed 30, `ekf-spoof`: gnss_excluded, 2 at 101.6, 202.8 s
- `main`, sim, square circuit, `nominal`, seed 33, `ekf`: gnss_excluded, 1 at 101.8 s
- `main`, sim, square circuit, `nominal`, seed 33, `ekf-guard`: gnss_excluded, 1 at 101.8 s
- `main`, sim, square circuit, `nominal`, seed 33, `ekf-spoof`: gnss_excluded, 1 at 101.8 s
- `main`, sim, square circuit, `nominal`, seed 38, `ekf`: gnss_excluded, 1 at 77.0 s
- `main`, sim, square circuit, `nominal`, seed 38, `ekf-guard`: gnss_excluded, 1 at 77.0 s
- `main`, sim, square circuit, `nominal`, seed 38, `ekf-guard`: gnss_jump_latched, 1 at 77.2 s
- `main`, sim, square circuit, `nominal`, seed 38, `ekf-guard`: sky suspect+, 1 at 77.2 s
- `main`, sim, square circuit, `nominal`, seed 38, `ekf-spoof`: gnss_excluded, 1 at 77.0 s
- `main`, sim, square circuit, `nominal`, seed 39, `ekf`: gnss_excluded, 2 at 52.2, 327.2 s
- `main`, sim, square circuit, `nominal`, seed 39, `ekf-guard`: gnss_excluded, 2 at 52.2, 327.2 s
- `main`, sim, square circuit, `nominal`, seed 39, `ekf-spoof`: gnss_excluded, 2 at 52.2, 327.2 s
- `main`, sim, square circuit, `nominal`, seed 41, `ekf`: gnss_excluded, 1 at 77.4 s
- `main`, sim, square circuit, `nominal`, seed 41, `ekf-guard`: gnss_excluded, 1 at 77.4 s
- `main`, sim, square circuit, `nominal`, seed 41, `ekf-spoof`: gnss_excluded, 1 at 77.4 s
- `main`, sim, square circuit, `nominal`, seed 43, `ekf`: gnss_excluded, 1 at 352.2 s
- `main`, sim, square circuit, `nominal`, seed 43, `ekf-guard`: gnss_excluded, 1 at 352.2 s
- `main`, sim, square circuit, `nominal`, seed 43, `ekf-spoof`: gnss_excluded, 1 at 352.2 s
- `main`, sim, square circuit, `nominal`, seed 44, `ekf`: gnss_excluded, 1 at 327.4 s
- `main`, sim, square circuit, `nominal`, seed 44, `ekf-guard`: gnss_excluded, 1 at 327.4 s
- `main`, sim, square circuit, `nominal`, seed 44, `ekf-spoof`: gnss_excluded, 1 at 327.4 s
- `main`, sim, square circuit, `nominal`, seed 45, `ekf`: gnss_excluded, 1 at 27.0 s
- `main`, sim, square circuit, `nominal`, seed 45, `ekf-guard`: gnss_excluded, 1 at 27.0 s
- `main`, sim, square circuit, `nominal`, seed 45, `ekf-spoof`: gnss_excluded, 1 at 27.0 s
- `main`, sim, square circuit, `nominal`, seed 47, `ekf`: gnss_excluded, 1 at 201.8 s
- `main`, sim, square circuit, `nominal`, seed 47, `ekf-guard`: gnss_excluded, 1 at 201.8 s
- `main`, sim, square circuit, `nominal`, seed 47, `ekf-spoof`: gnss_excluded, 1 at 201.8 s
- `main`, sim, square circuit, `nominal`, seed 48, `ekf`: gnss_excluded, 3 at 127.0, 351.4, 353.0 s
- `main`, sim, square circuit, `nominal`, seed 48, `ekf-guard`: gnss_excluded, 3 at 127.0, 351.4, 353.0 s
- `main`, sim, square circuit, `nominal`, seed 48, `ekf-spoof`: gnss_excluded, 3 at 127.0, 351.4, 353.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 17, `ekf`: gnss_excluded, 1 at 78.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 17, `ekf-guard`: gnss_excluded, 1 at 78.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 17, `ekf-spoof`: gnss_excluded, 1 at 78.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 30, `ekf`: gnss_excluded, 1 at 101.6 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 30, `ekf-guard`: gnss_excluded, 1 at 101.6 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 30, `ekf-spoof`: gnss_excluded, 1 at 101.6 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 33, `ekf`: gnss_excluded, 1 at 101.8 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 33, `ekf-guard`: gnss_excluded, 1 at 101.8 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 33, `ekf-spoof`: gnss_excluded, 1 at 101.8 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 38, `ekf`: gnss_excluded, 1 at 77.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 38, `ekf-guard`: gnss_excluded, 1 at 77.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 38, `ekf-guard`: gnss_jump_latched, 1 at 77.2 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 38, `ekf-guard`: sky suspect+, 1 at 77.2 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 38, `ekf-spoof`: gnss_excluded, 1 at 77.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 39, `ekf`: gnss_excluded, 1 at 52.2 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 39, `ekf-guard`: gnss_excluded, 1 at 52.2 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 39, `ekf-spoof`: gnss_excluded, 1 at 52.2 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 41, `ekf`: gnss_excluded, 1 at 77.4 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 41, `ekf-guard`: gnss_excluded, 1 at 77.4 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 41, `ekf-spoof`: gnss_excluded, 1 at 77.4 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 45, `ekf`: gnss_excluded, 1 at 27.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 45, `ekf-guard`: gnss_excluded, 1 at 27.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 45, `ekf-spoof`: gnss_excluded, 1 at 27.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 48, `ekf`: gnss_excluded, 1 at 127.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 48, `ekf-guard`: gnss_excluded, 1 at 127.0 s
- `main`, sim, square, before spoof (sky), `spoof-jump-sky`, seed 48, `ekf-spoof`: gnss_excluded, 1 at 127.0 s
- `main`, real, static, `20261111-0845-live-laptop-gps`, `ekf`: gnss_excluded, 10 at 204.0, 276.0, 371.0, 399.0, 422.0, 449.0, 484.0, 527.0, 551.0, 570.0 s
- `main`, real, static, `20261111-0845-live-laptop-gps`, `ekf`: do not navigate (HPL > AL), 10 at 206.1, 278.1, 373.4, 401.4, 424.4, 451.4, 486.4, 529.4, 553.4, 572.1 s
- `main`, real, static, `20261111-0845-live-laptop-gps`, `ekf-guard`: gnss_excluded, 10 at 204.0, 276.0, 371.0, 399.0, 422.0, 449.0, 484.0, 527.0, 551.0, 570.0 s
- `main`, real, static, `20261111-0845-live-laptop-gps`, `ekf-guard`: do not navigate (HPL > AL), 10 at 206.1, 278.1, 373.4, 401.4, 424.4, 451.4, 486.4, 529.4, 553.4, 572.1 s
- `main`, real, static, `20261111-0845-live-laptop-gps`, `ekf-spoof`: gnss_excluded, 10 at 204.0, 276.0, 371.0, 399.0, 422.0, 449.0, 484.0, 527.0, 551.0, 570.0 s
- `main`, real, static, `20261111-0845-live-laptop-gps`, `ekf-spoof`: do not navigate (HPL > AL), 10 at 206.1, 278.1, 373.4, 401.4, 424.4, 451.4, 486.4, 529.4, 553.4, 572.1 s

Check against `pnt.metrics.score` (`any (metrics)` count): 900 sim runs, 0 disagree.
