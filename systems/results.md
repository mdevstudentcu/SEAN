# Results

- **Status:** Draft, 2026-11-11 (#28), against `main` at `c21e047`. Collected from committed results and PR descriptions; nothing was re-run for this file.
- **Kinds.** **Real**: a recorded session. **Sim**: committed scenarios whose models are `placeholder` except where [`verification.md`](verification.md) *Sim validity* says `measured`; never real-world accuracy. **Synthetic**: generated baseband through the real front end. **Registry**: the ISED tower table, no radio.
- **Open PRs.** A number from an open PR is that PR's evidence, not reviewed or merged. It is marked *open*.
- **Commits** are the ones the source names. Several are pre-rebase hashes not on `main`; open PR #217 maps each to its twin on `main`, given here as "→ twin" where checked in `git log`.
- **Two T1 statistics.** **A34**: the 95th percentile of horizontal error across runs at each second after GPS loss, worst second of the window ([ADR-0034](adr/0034-targets-after-mentor-answers.md), *Amendment*). **Per-run**: each run's own 95th percentile over the window, then the median or mean over seeds. Only A34 scores T1; per-run numbers are for comparison only.
- **Placeholders** `TBD (#NNN)` are filled by that issue's work today. No value is guessed.
- **HPL** is a bound under our model (5.33 σ of the filter's covariance, or the MHSS bound), not a certified protection level. It is not honest on the worst runs: see T5 below.

## (a) What is real

### Sessions

All static, payload Pi 4B. Raw data stays out of git (`data/sessions/`).

| Session(s) | Sensors, conditions | What was measured | What it bounds, and what it cannot | Source |
| --- | --- | --- | --- | --- |
| 15 LTE captures, 2026-11-10, two spots: 60 s per carrier and one 1,800 s capture (`20261110-1759-static-out-long-e5060`) | One NESDR SMArt v5 (8-bit samples, `.cu8`), no GPS fix, NTP time | LTE range precision against SNR, the correlated part, clocks of sectors of one site | Precision at rest only. No bias (no position truth), no multipath size, no motion, one neighbourhood | [ADR-0036](adr/0036-lte-measured-error-model.md) (Proposed); [`lte-measured-noise/`](../analysis/results/lte-measured-noise/summary.md), analysis `fdb8fde` → twin `2408c19`; #190 |
| Same captures, cell lookup | (EARFCN, PCI) against the 2026 ISED table | First spot: each heard cell is used by exactly one registered eNB within the table's 10 km. Second spot (`20261110-1623-static-out-e5060-lte`): PCI 204 is not in the table | A match is a hypothesis: the lookup is made around Carleton, not the receiver | [`lte-scan-20261110/`](../analysis/results/lte-scan-20261110/summary.md); [`verification.md`](verification.md); [`deploy/demo/RUNBOOK.md`](../deploy/demo/RUNBOOK.md) §4 |
| `20261110-adsb-outside-iq`, 59.4 s | NESDR, readsb on the Pi | 198 frames, 89 with a good CRC; one aircraft, 21 position reports, NACp 10, NIC 8 | No per-frame time, so no message rate or latency; one aircraft says nothing about quality dips | [`verification.md`](verification.md) *First real-air sessions*; #192 |
| Three VOR captures, 114.6 and 115.2 MHz | Telescopic antenna | No lock in 6 runs (radials spread 87 to 111°) | VOR is sim only | Same |
| `20261110-0306-static-bench-overnight` | MPU6050 | Noise and bias instability, the only *Sim validity* row now `measured` | The real accelerometer drifts at τ > 100 s; the sim does not | [`verification.md`](verification.md); #157 |
| `20261111-0040-static-fullsuite`, 595 s | GPS HAT with PPS, NESDR, IMU, barometer | 18 satellites used (median), top-4 C/N0 median 44.2 dB-Hz, HDOP 0.59; jamming indicator 0 in every record | One session on the ground near a building; with the reference at 40 dB-Hz (`TBC`), C/N0 must fall 4.2 dB before the indicator moves | [`gnss-health-20261111-fullsuite/`](../analysis/results/gnss-health-20261111-fullsuite/summary.md), `c1a76d3` → twin `51cd950`; #211 |
| Seven antenna runs, `20261110-2307` to `-2341-static-ant-*` | NESDR, three antennas | Same spot and antenna: on the ground +14.1 dB, on a 0.5 m chair at the floor; a gap of at least 25.7 dB on PCI 204 | Placement mattered more than the antenna | [`antenna-ab-20261110/`](../analysis/results/antenna-ab-20261110/summary.md); #210 |
| `20261110-1759-live-laptop` | Pi to laptop over the authenticated link (CurveZMQ) | 28 min streamed | 0 estimates: no GPS fix and no LTE in the stream | [`deploy/demo/RUNBOOK.md`](../deploy/demo/RUNBOOK.md) *Live segment* |
| PPS on the payload Pi (2026-11-11) | GPS HAT PPS into chrony | PPS std dev 769 ns over 80 s; RMS offset 957 ns | Time-of-day discipline only, not holdover | Open PR #216 |

### What the LTE captures measured

Real. Every value and its session in [`lte-measured-noise/summary.md`](../analysis/results/lte-measured-noise/summary.md); interpretation in ADR-0036.

| Quantity (10 Hz records) | Value | Sim placeholder it is compared with |
| --- | --- | --- |
| White noise, robust σ | 0.63 m at 13 to 16 dB SNR; 2.36 m at −2 to 1 dB; 12.4 m at −11 to −8 dB; 24.7 m at −14 to −11 dB | 50 m white at 1 Hz: 3 to 10 times what was seen at rest (ADR-0036) |
| Fit at SNR ≥ −8 dB (`TBC`) | σ² = 0.64² + 2.28² / SNR_lin (m) | — |
| Front end's reported σ against the white part | 1.2 to 2.1 times larger | Sim records report 2 m |
| Correlated part inside one arc, S(1 s) | 2.4 to 15 m, median 8.3 m (9 cells above 0 dB, tracked ≥ 80 %) | Not in the reported σ at all |
| Drift between sectors of one eNB | Within 0.5 m/s (−0.18 ± 0.16 m/s, 1,800 s) | Supports one clock per site (ADR-0022, Proposed) |
| Drift between different eNBs | `TBD` (up to 6.6 m/s seen; no bound) | Sim 0.05 m/s |
| Front-end faults (#183) | 7 of 39 tracks offset by a multiple of 200 Hz; weak cells break 19 to 105 times a minute; the strongest cell starts a new arc every 8 s on the 1,800 s capture | The sim keeps every arc |

Sim against real, same tool (`pnt compare`, #199): the sim's LTE residual is 49.2 m and white (lag-1 −0.06); the real cell's is 21.3 m and smooth (lag-1 1.00), with 0.7 m record to record. Software fault injection into the real recording works (+300 m clock step applied to all 494 records from 20 s), but no position is estimated on it: the session has no origin.

## (b) The scoreboard

Targets: [`plan.md`](plan.md), [ADR-0034](adr/0034-targets-after-mentor-answers.md). **Met and Not met are against our own targets**, several of them Proposed, and most rows rest on open PRs. Sim unless marked. The `challenge` legs ([ADR-0030](adr/0030-challenge-benchmark-set.md), Proposed) use LTE records shaped as the real front end writes them, 60 s of GPS, then a 600 s outage. #170's numbers are being regenerated (#187).

| Target | Requirement / fallback | Result | Source, seeds | Verdict |
| --- | --- | --- | --- | --- |
| T1, UC-01 drone | 95 % ≤ 25 m for ≥ 300 s (A34) | `challenge` drone leg, A34: `TBD (#187)`. Per-run, for comparison: best mean 4,284 m (`ekf-calibrated`); 0 of 50 seeds of any estimator within 25 m | #170 at `ff5ee58` (open), seeds 0–49 | **Not met** on the per-run statistic; A34 value `TBD (#187)` |
| | | `uc01-drone-circuit` (6 synthetic towers, 20 m noise), A34: `ekf-imu` 22 m, `ekf` 27 m, `ekf-calibrated` 40 m. Same route, `realistic` errors: `ekf-calibrated` 713 m | #178 at `cee2607` (open), seeds 0–49 | Met only by `ekf-imu` on the easy synthetic route |
| T1 fallback | ≤ 50 m for ≥ 120 s (mentors; A34) | `challenge` drone leg, A34: `TBD (#187)`. Per-run: best mean 1,580 m (`ekf`); 0 of 50 seeds within 50 m | #170 (open) | **Not met** on the per-run statistic; A34 value `TBD (#187)` |
| | | `uc01-drone-circuit`, A34: 22 to 33 m (all three); `realistic` errors: `ekf-calibrated` 425 m | #178 (open) | Met on the easy route only |
| T2, UC-02 approach | Alert limit 556 m | No metric scores it; approach towers are synthetic | #170 | **Not scored** |
| T3, UC-03 timing | ≤ 1.5 µs after 10 min, 1-σ bounds ≥ 68 % | `ekf`: 0.44 µs mean, 1.55 µs worst, 49 of 50 seeds; σ bound mean 99.46 %. `ekf-calibrated`: 0.15 µs mean, σ bound fails on 13 seeds | #170 (open), seeds 0–49 | **Not met** (one seed at 1.55 µs) |
| T4, location jump | Target `TBD` (ADR-0034). Proposed in #176 (`TBC`): ≥ 20 m flagged within 2 s in ≥ 95 % of runs, GNSS kept out while it lasts, no hazardous epoch | Detection: ≥ 20 m in ≥ 95 % of runs, 1.1 s, all four estimators. Kept out: default estimators follow it (50 m jump: 50 of 50 runs hazardous, `ekf`, `realistic`); `ekf-guard` 0 of 20 at every size from 50 m to 1 km | #176 at `6f03e92` (open), seeds 0–49; #191 (merged), seeds 0–19 | Detection met; refusal met only by the opt-in guard; target not adopted |
| T4, position ramp | 2 m/s detected within 30 s | 0 of 50, every estimator on `main` | #170 (open) | **Not met** |
| T4, time ramp | 50 ns/s detected within 60 s | 50 of 50 for `ekf`, `ekf-calibrated`, `ekf-imu`; median 3.3, 2.9, 3.3 s | #170 (open) | **Met** |
| T4, false alarms | ≤ 1 per hour on `nominal` | 0.0 /h for `baseline`, `ekf`, `ekf-calibrated`, `ekf-imu` on all three legs | #170 (open) | **Met** |
| T5, integrity | HPL bounds the error in ≥ 99.9 % of epochs; no hazardous epoch on fault scenarios | Worst run's bound 0.22 % to 21.18 % (four fast estimators, three legs). `ekf` on drone `outage`: 320 hazardous epochs on 7 of 50 seeds. `ekf-mhss`: 0 hazardous, but unavailable (worst bound 85 % drone, 78 % timing, partial run) | #170 (open) | **Not met** |

## (c) What each fix buys

Sim. Each on its own inputs; none of these numbers is A34 except where said. Together: `TBD (#218)`.

| Fix | PR, decision, state | What it buys | What it costs or leaves | Statistic, seeds, commit |
| --- | --- | --- | --- | --- |
| **Learned LTE noise**: the filter learns each cell's range noise instead of trusting the reported σ | #156 (open, draft), ADR-0039 Proposed; opt-in `ekf-learned-noise`, `ekf-calibrated-learned-noise` | Drone leg, `ekf`: median 4,034 → 982 m, worst 16,639 → 2,828 m; hazardous epochs 320 (7 seeds) → 0; LTE at least as good as no LTE on 15 → 46 of 50 seeds | Fallback still missed on every drone seed. Timing leg: LTE still worse than none (605 against 197 m median). Opt-in run: 3 hazardous epochs on seed 8 of `tower-clock-step` where the default has none | Per-run 300 s p95; seeds 0–49; `main` `9c5cb31` against `49e09cd` |
| **Carrier hopping**: one dongle dwells on several carriers in turn | #179 (open), ADR-0040 Proposed; study leg, not benchmark | Told the true noise: 120 s error 374 / 413 m (1 carrier, 2 masts per 10 s) → 68 / 69 m (13 carriers, 27 masts) for `ekf` / `ekf-calibrated` | Told 2 m: over 1,000 m whatever is heard. Neither target met (best 64 m at 120 s). Real hopping untested; the sim keeps every arc | Per-run, median over seeds; seeds 0–19; `fb62912`, reproduced at `a0e80c0` |
| **Jump guard**: refuse a detected GNSS jump until the GNSS stream steps back | #191 (merged `83bbb97`), ADR-0038 Proposed; opt-in `ekf-guard`, `ekf-imu-guard`, `ekf-calibrated-guard` | Held 300 m jump, drone leg, `ekf`: hazardous epochs per run 5,244 (49/50 seeds) → 3 (3/50); on the spoofed position at +120 s: 44 of 47 → 0 of 50; honest GNSS back 0.1 s (median) after the jump ends, 50 of 50 | The filter then dead-reckons: median error 115 m / 1,263 m / 5,244 m at +30 / +120 / +300 s, HPL 547 m at +30 s (flagged unsafe). Keeps honest GNSS out after 5 of 46 hard manoeuvres with 1 Hz GNSS | [`jump-refusal/summary.md`](../analysis/results/jump-refusal/summary.md), seeds 0–49, `84401c5` → twin `df46bce` |
| **Tower spoof monitor**: towers tested against GNSS outside the filter, 30 s and 120 s lags, ≥ 5 sites | #180 (open), ADR-0037 Proposed; opt-in `ekf-spoof` | 2 m/s ramp with every tower within 3 km heard (17 eNBs): 0 → 48 of 50 seeds, 131 s median, 313 s worst | Drone leg as committed (1 to 3 cells): 1 of 50. `realistic` set (4 towers): 0 of 50. 30 s out of reach: the ramp moves 60 m in 30 s against the towers' 34 m (1σ). No false alarms added | Seeds 0–49, `97795d8` |
| **Coherent integration** in the LTE front end | #171 (merged `9aa896c`), opt-in settings | Synthetic: weakest cell tracked 3 of 3 seeds, same PSS root, −11 → −14 dB | At Carleton (2 km, 24 sectors): 1.0 → 1.0 cells tracked | Synthetic, seeds 0–2, `97a80bf` |
| **All of the above on the drone leg** | #218 (in progress) | `TBD (#218)` | `TBD (#218)` | A34, seeds 0–49 |

Why the noise fix comes first: told 2 m, the drone leg's `ekf` reached 6,557 m at 300 s; told the true 50 m, 1,002 m; with no LTE at all, 2,513 m (sim, per-run p95, #137 at `af2efce`, seeds 0–9; #147).

## (d) Spoofing: what is detected, how fast, what is refused

Sim unless marked. Detection means an alarm flag held 1 s (`pnt.metrics`). Read the first rows together: a sudden jump is caught in 1.1 s, while the slow 2 m/s drag, the more realistic attack, is caught by the default filter in 0 of 50 runs.

| Attack | Detected | How fast | What the output does | False alarms | Source |
| --- | --- | --- | --- | --- | --- |
| GNSS position jump, 20 m to 500 km | Every size, every variant, except one 20 m jump missed by `ekf` on `uc01-drone-circuit` (19/20) | 1.1 s (p95 1.1 s) | Default follows it: hazardous runs at 50 m, 100 m, 300 m, 1 km are 20, 19, 19, 4 of 20 (`ekf`, `realistic`). `ekf-guard`: 0 of 20 at every size | 0 of 20 runs with no jump | ADR-0038; [`pr-evidence/191`](../analysis/pr-evidence/191/guard_jump_sizes.md), seeds 0–19, `9ac2aee` → twin `5a7a1c9` |
| Jump of 15 m | 30 to 86 % of runs (by estimator and route) | 1.1 s | A missed jump under 20 m left the error ≤ 24 m | 0 in 50 clean runs (5 h) | #176 (open), seeds 0–49 |
| Small jump then drift (5 or 10 m, then 0.5 or 2 m/s) | At most 24 % of runs | — | Followed to 110 to 430 m | — | #176 (open) |
| 2 m/s position ramp | 0 of 50 on `main`; 48 of 50 with #180's monitor where 17 eNBs are heard | 131 s median | Followed until detected | None added | #170, #180 (open) |
| Meaconing (5 s late replay) | Both `ekf` and `ekf-guard` | 1.1 s | `ekf`: 1,976 misleading epochs per run; `ekf-guard`: 0 | 0 | ADR-0038, `pnt eval meaconing --runs 20` |
| 50 ns/s GNSS time ramp | 50 of 50 | 3.3 s median, 4.1 s worst (`ekf`) | GNSS time excluded | 0.0 /h on `nominal` | #170 (open); RUNBOOK |
| Interference seen by aircraft (ADS-B quality and track jumps) | Jammed and spoofed approaches: 50 of 50 warned | Lead over our own zone entry: 48.2 s (jammed), 77.9 s (spoofed), median | Raises the GNSS fault prior in `ekf-mhss`; position unchanged; no integrity gain shown (0 misleading with or without) | 1.94 per hour on the clean approach, from placeholder quality dips | #166 (merged), ADR-0033 Proposed, seeds 0–49 |
| GNSS jamming by C/N0 (ADR-0031) | Real session: indicator 0 throughout (no alarm in 595 s) | — | Not tested against a real or injected attack | 0 in one 10-min real session | #211 (real) |
| Satellite that should not be visible; one spoofed-or-not output | `TBD (#206)` | `TBD (#206)` | `TBD (#206)` | `TBD (#206)` | #206 |
| Wrong tower table: an unregistered tower on one eNB's PCIs | `ekf-mhss` flags the site | — | `ekf-calibrated`: 186.5 m outage p95 and 5,147 hazardous epochs (confidently wrong, #132). `ekf-mhss` stays bounded, median HPL 5.4 km: safe, unavailable | — | Sim over real tower positions, #133 (merged), `7c1afb7`, 10 seeds (`ekf-mhss` 5) |

## (e) What is not shown

- **Towers carrying the position on the real-shaped legs.** With records that report only the fast noise, the filter rejects nearly every tower reading (one seed: 5,374 of 5,383 before the spoof, #180), so after GPS loss the default filter flies on the barometer and dead reckoning. The guard demo's panel lists LTE as not in use (draft PR #220). No percentage of epochs is committed.
- **Any position from real towers, and any real error after GPS loss:** `TBD (#214)` (a real session with GPS cut in software, scored against the real fixes).
- **Any real-world accuracy, integrity level or detection rate.** Every number in (b), (c) and (d) is sim or synthetic, except the rows marked real.
- **T1 on the agreed statistic for the `challenge` legs:** `TBD (#187)`; with every fix together: `TBD (#218)`.
- **How many towers are enough with the barometer and IMU:** `TBD (#208)`.
- **A confidence heat map on the track:** `TBD (#207)`. Today the panel shows NOMINAL / DEGRADED / UNSAFE, the HPL against the alert limit and latched alerts.
- **T2**, scored against its alert limit; the approach leg's towers are synthetic.
- **Real carrier hopping, a moving capture, multipath size on real signals, bias against truth.**
- **The reference station on hardware** (sim only, ADR-0020 *Amendment 2026-11-10*), **LEO** (sim only, #172: towers-only 19.8 m → 4.4 m with Starlink in the kind case, every value `TBC`), the hostile beacon (#167: no accuracy gain on these models).
- **VOR's contribution:** sim, median change −0.7 m, better on 30 and worse on 20 of 50 seeds (sign test p = 0.20, [`vor-ablation/`](../analysis/results/vor-ablation/summary.md)).
