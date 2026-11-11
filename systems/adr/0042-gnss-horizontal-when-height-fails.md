# ADR-0042: When only its height fails the gate, a GNSS fix's horizontal part is still used

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners accept or change it)
- **Traces to:** REQ-01, REQ-02, REQ-05, #224, #227

## Context

On the real 10-minute static session `20261111-0845-live-laptop-gps` (#224, healthy 3D fix, PPS-locked), `ekf` flagged `gnss_excluded` in 261 of 601 seconds and was `unsafe` in 229, HPL up to 2,427 m. A replay on `main` reproduces the live log second for second (262 flagged lines, the same runs, 229 `unsafe`, final HPL 651.4 m).

The per-fix trace (`#227`) shows the cause is the height, never the horizontal:

- The horizontal part of every rejected fix's NIS is 0.00 to 0.01; its vertical part is 16.5 to 519 (innovation up to −81 m). The 3-D gate (`CHI2_999[3]` = 16.27) rejects the whole fix.
- The barometer (a BMP180) is told 0.3 m (`BMP280.noise_m`, the sim's white noise) at 10 Hz, so the filter's vertical sigma sits at 0.20 m. On this static receiver it read −3.4 to +77.5 m about the start, moving with the chip's own temperature (correlation −0.85, 6.5 °C to −1.2 °C). Why the chip does this is `TBD` (#227 follow-up).
- GNSS was honest: horizontal scatter 0.57 / 0.51 m (east / north standard deviation) against reported 5.4 / 2.1 m, vertical 1.71 m against 2.1 to 3.5 m.
- A rejected fix changes nothing, and the barometer keeps the vertical sigma at 0.2 m, so the gate stays shut while the barometer is off; the horizontal covariance meanwhile grows on the constant-velocity model until HPL passes the 50 m alert limit.

Ruled out by the same trace: reported GNSS sigma too small (it is 4 to 10 times too large horizontally), time-correlated GNSS error against a white gate (autocorrelation 0.86 to 0.95 at 10 s, but the horizontal NIS is near zero), HAE against MSL (the barometer is referenced to the first fix's height: −0.9 m apart at the start), the IMU (`ekf` runs constant velocity and ignores `accel_gyro`), start-up (the first 47 fixes pass with NIS ≤ 2.9), time stamps (no record out of order, fixes exactly 1 s apart).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Keep the 3-D gate | Nothing moves | Honest GNSS locked out by a barometer; the panel goes red on real data |
| B. Gate horizontal and vertical separately, always | Each axis judged on its own | Changes every fix's decision near the thresholds, in every run; two tests per fix |
| C. Gate in 3-D as now; only if that fails, gate the horizontal alone (`CHI2_999[2]`) and use it if it passes, flagging the height (`gnss_alt_excluded`) | A fix that passes the 3-D gate is handled exactly as before; a horizontal jump still fails its own gate | When the barometer and GNSS height disagree the vertical follows the barometer, told 0.3 m: the height is flagged, not fixed |
| D. Tell the filter the truth about the barometer (a larger sigma for the BMP180, or a barometer bias state) | Fixes the vertical itself | Measurement-side or model change with values `TBD`; the recorded session carries 0.3 m; not doable today |
| E. Re-admit GNSS after it has been rejected for a while | Recovers from any lock-out | What a spoofer waits for (ADR-0038): undoes jump protection |

## Decision

Option C, for every estimator built on `EKF` (it is the filter's gate, not an option).

## Consequences

- Real session (#224, replay at the branch): GNSS horizontal used in 600 of 601 seconds (the first is before the first fix), `unsafe` 1 s (start-up) instead of 229, HPL median 20.0 m and max 60.6 m (start-up) instead of 21.1 and 2,427 m; `gnss_alt_excluded` in 261 s, status `degraded` then. The same for `ekf-guard` and `ekf-calibrated`.
- A 300 m east jump injected into the session (`compare.inject`) is flagged 0.6 s after onset as on `main`; `ekf-guard` refuses it to the end; plain `ekf` follows it after 24.6 s (26.6 s on `main`), the ADR-0038 behaviour. Injected at 210 s, inside a barometer excursion, `ekf-guard` now refuses it for all 391 s; on `main` GNSS was already excluded there, the guard could not latch, and the jump was followed after 60.6 s.
- In sim the fallback fires on the few honest fixes the 3-D gate rejects for their height, so most runs change slightly. Hash check, every registered estimator on `nominal`, `spoof-jump`, `gps-outage`, `challenge-drone-nominal`, `challenge-drone-spoof-jump`, `challenge-timing-time-spoof`, seeds 0 and 1, against `main` (c21e047): 89 of 132 runs change, 43 are bit-identical. `baseline` (its own filter) never changes. A scenario-seed changes for every `EKF`-based estimator whenever one of its honest fixes failed the 3-D gate on its height (1 to 4 such fixes per run; `gnss_excluded` epochs drop by 2 to 8, the same epochs now carry `gnss_alt_excluded`). Unchanged: `spoof-jump` 0, `gps-outage` 0 and `challenge-timing-time-spoof` 0 for every estimator, and the `*-guard` estimators on `challenge-drone-spoof-jump` 0. On `spoof-jump` 0 only `ekf-mhss` and `ekf-mhss-beacon` change (their sub-filters use the same gate). Detection and false-alarm numbers on spot runs: PR evidence.
- The height: when GNSS and barometer disagree the estimate's height follows the barometer and its VPL is the barometer's. Status judges HPL only, so this is flagged (`gnss_alt_excluded`, a caution on the panel), not alarmed. Option D is the fix for the height; proposed separately, not decided here.
- Not addressed: the `drone-many` lock-out of #227 (seeds 36 and 39) is horizontal (NIS 21 to 25 at 1.4 to 2.2 s with a 1.4 m filter sigma), driven by LTE records told 2 m against 50 m white noise, 50 m multipath and 100 m table error; ADR-0036 already proposes the told sigma.
- Reopen when the barometer gets an honest sigma or a bias state (D), or a vertical requirement needs GNSS height to win over the barometer.
