# Results

- **Status:** Draft, 2026-11-11 (#28), against `main` at `c21e047`; PR states, placeholders and the numbers that #245 and ADR-0047 moved brought up to `main` at `c97e09a`. Collected from committed results and PR descriptions; nothing was re-run for this file.
- **Kinds.** **Real**: a recorded session. **Sim**: committed scenarios whose models are `placeholder` except where [`verification.md`](verification.md) *Sim validity* says `measured`; never real-world accuracy. **Synthetic**: generated baseband through the real front end. **Registry**: the ISED tower table, no radio.
- **Open PRs.** A number from an open PR is that PR's evidence, not reviewed or merged. It is marked *open*.
- **Commits** are on `main` (or, for an open PR, on its branch). Where the source names a pre-rebase hash that is not on `origin`, its twin on `main` (same commit subject) is given instead.
- **Two T1 statistics.** **A34**: the 95th percentile of horizontal error across runs at each second after GPS loss, worst second of the window ([ADR-0034](adr/0034-targets-after-mentor-answers.md), *Amendment*). **Per-run**: each run's own 95th percentile over the window, then the median or mean over seeds. Only A34 scores T1; per-run numbers are for comparison only.
- **Placeholders** `TBD (#NNN)` are filled by that issue's work today. No value is guessed.
- **HPL** is a bound under our model (5.33 σ of the filter's covariance, or the MHSS bound), not a certified protection level. It is not honest on the worst runs: see T5 below.

## (a) What is real

### Sessions

All static, payload Pi 4B. Raw data stays out of git (`data/sessions/`).

| Session(s) | Sensors, conditions | What was measured | What it bounds, and what it cannot | Source |
| --- | --- | --- | --- | --- |
| 15 LTE captures, 2026-11-10, two spots: 60 s per carrier and one 1,800 s capture (`20261110-1759-static-out-long-e5060`) | One NESDR SMArt v5 (8-bit samples, `.cu8`), no GPS fix, NTP time | LTE range precision against SNR, the correlated part, clocks of sectors of one site | Precision at rest only. No bias (no position truth), no multipath size, no motion, one neighbourhood | [ADR-0036](adr/0036-lte-measured-error-model.md) (Proposed); [`lte-measured-noise/`](../analysis/results/lte-measured-noise/summary.md), front end and analysis at `8892fca` (after #245's fixes); #190 |
| Same captures, cell lookup | (EARFCN, PCI) against the 2026 ISED table | First spot: each heard cell is used by exactly one registered eNB within the table's 10 km. Second spot (`20261110-1623-static-out-e5060-lte`): PCI 204 is not in the table | A match is a hypothesis: the lookup is made around Carleton, not the receiver | [`lte-scan-20261110/`](../analysis/results/lte-scan-20261110/summary.md); [`verification.md`](verification.md); [`deploy/demo/RUNBOOK.md`](../deploy/demo/RUNBOOK.md) §4 |
| `20261110-adsb-outside-iq`, 59.4 s | NESDR, readsb on the Pi | 198 frames, 89 with a good CRC; one aircraft, 21 position reports, NACp 10, NIC 8 | No per-frame time, so no message rate or latency; one aircraft says nothing about quality dips | [`verification.md`](verification.md) *First real-air sessions*; #192 |
| Three VOR captures, 114.6 and 115.2 MHz | Telescopic antenna | No lock in 6 runs (radials spread 87 to 111°) | VOR is sim only | Same |
| `20261110-0306-static-bench-overnight` | MPU6050 | Noise and bias instability, the only *Sim validity* row now `measured` | The real accelerometer drifts at τ > 100 s; the sim does not | [`verification.md`](verification.md); #157 |
| `20261111-0040-static-fullsuite`, 595 s | GPS HAT with PPS, NESDR, IMU, barometer | 18 satellites used (median), top-4 C/N0 median 44.2 dB-Hz, HDOP 0.59; jamming indicator 0 in every record | One session on the ground near a building; with the reference at 40 dB-Hz (`TBC`), C/N0 must fall 4.2 dB before the indicator moves | [`gnss-health-20261111-fullsuite/`](../analysis/results/gnss-health-20261111-fullsuite/summary.md), `51cd950`; #211 |
| Seven antenna runs, `20261110-2307` to `-2341-static-ant-*` | NESDR, three antennas | Same spot and antenna: on the ground +14.1 dB, on a 0.5 m chair at the floor; a gap of at least 25.7 dB on PCI 204 | Placement mattered more than the antenna | [`antenna-ab-20261110/`](../analysis/results/antenna-ab-20261110/summary.md); #210 |
| `20261110-1759-live-laptop` | Pi to laptop over the authenticated link (CurveZMQ) | 28 min streamed | 0 estimates: no GPS fix and no LTE in the stream | [`deploy/demo/RUNBOOK.md`](../deploy/demo/RUNBOOK.md) *Live segment* |
| PPS on the payload Pi (2026-11-11) | GPS HAT PPS into chrony | PPS std dev 769 ns over 80 s; RMS offset 957 ns | Time-of-day discipline only, not holdover | #216 (merged); [`assumptions.md`](assumptions.md) ASM-04 |

### What the LTE captures measured

Real. Every value and its session in [`lte-measured-noise/summary.md`](../analysis/results/lte-measured-noise/summary.md); interpretation in ADR-0036.

| Quantity (10 Hz records) | Value | Sim placeholder it is compared with |
| --- | --- | --- |
| White noise, robust σ | 0.73 m at 13 to 16 dB SNR; 2.41 m at −2 to 1 dB; 10.9 m at −11 to −8 dB; 22.5 m at −14 to −11 dB (43 records) | 50 m white at 1 Hz: 3 to 10 times what was seen at rest (ADR-0036) |
| Fit at SNR ≥ −8 dB (`TBC`) | σ² = 0.74² + 2.32² / SNR_lin (m) | — |
| Front end's reported σ against the white part | 1.3 to 2.0 times larger | Sim records report 2 m |
| Correlated part inside one arc, S(1 s) | 2.4 to 17 m, median 8.1 m (19 cells above 0 dB, tracked ≥ 80 %) | Not in the reported σ at all |
| Drift between sectors of one eNB | Within 0.5 m/s (−0.15 ± 0.16 m/s, 1,800 s) | Supports one clock per site (ADR-0022, Proposed) |
| Drift between different eNBs | `TBD` (up to 24 m/s seen, 10.3 m/s with both cells above −8 dB; no bound) | Sim 0.05 m/s |
| Front-end faults left after #183's and #245's fixes (merged) | 4 of 40 tracks on a 200 Hz carrier alias; the 2 weak cells break 11 and 19 times a minute; the strongest cell starts a new arc every 10 s on the 1,800 s capture; doppler records are off by default | The sim keeps every arc |

Sim against real, same tool (`pnt compare`, #199): the sim's LTE residual is 49.2 m and white (lag-1 −0.06); the real cell's is 21.3 m and smooth (lag-1 1.00), with 0.7 m record to record. Software fault injection into the real recording works (+300 m clock step applied to all 494 records from 20 s), but no position is estimated on it: the session has no origin.

## (b) The scoreboard

Targets: [`plan.md`](plan.md), [ADR-0034](adr/0034-targets-after-mentor-answers.md). **Met and Not met are against our own targets**, several of them Proposed, and most rows rest on PRs merged on 2026-11-11 (#250), not re-run here. Sim unless marked. The `challenge` legs ([ADR-0030](adr/0030-challenge-benchmark-set.md), Proposed) use LTE records shaped as the real front end writes them, 60 s of GPS, then a 600 s outage. #170's numbers are on `main` in [`challenge-baseline/summary.md`](../analysis/results/challenge-baseline/summary.md) (`c847079`); its approach-leg rows of filters built on `nav/ekf.py` are stale since ADR-0047 and are not quoted here.

| Target | Requirement / fallback | Result | Source, seeds | Verdict |
| --- | --- | --- | --- | --- |
| T1, UC-01 drone | 95 % ≤ 25 m for ≥ 300 s (A34) | `challenge` drone leg, A34: best 10,154 m at 300 s (`ekf-calibrated`), `ekf` 12,507 m. Per-run, for comparison: best mean 4,284 m (`ekf-calibrated`); 0 of 50 seeds of any estimator within 25 m | #170 (merged, #250), [`challenge-baseline/summary.md`](../analysis/results/challenge-baseline/summary.md) at `c847079`, seeds 0–49 | **Not met** |
| | | `uc01-drone-circuit` (6 synthetic towers, 20 m noise), A34: `ekf-imu` 22 m, `ekf` 27 m, `ekf-calibrated` 40 m. Same route, `realistic` errors: `ekf-calibrated` 713 m | #178 at `c8eb240` (merged), seeds 0–49 | Met only by `ekf-imu` on the easy synthetic route |
| T1 fallback | ≤ 50 m for ≥ 120 s (mentors; A34) | `challenge` drone leg, A34: best 3,268 m at 120 s (`ekf`, 50 runs; `ekf-mhss` 2,901 m on 20 runs). Per-run: best mean 1,580 m (`ekf`); 0 of 50 seeds within 50 m | #170 (merged, #250), [`challenge-baseline/summary.md`](../analysis/results/challenge-baseline/summary.md) | **Not met** |
| | | `uc01-drone-circuit`, A34: 22 to 33 m (all three); `realistic` errors: `ekf-calibrated` 425 m | #178 (merged) | Met on the easy route only |
| T2, UC-02 approach | Alert limit 556 m | No metric scores it; approach towers are synthetic | #170 | **Not scored** |
| T3, UC-03 timing | ≤ 1.5 µs after 10 min, 1-σ bounds ≥ 68 % | `ekf`: 0.44 µs mean, 1.55 µs worst, 49 of 50 seeds; σ bound mean 99.46 %. `ekf-calibrated`: 0.15 µs mean, σ bound fails on 13 seeds | #170 (merged, #250), seeds 0–49 | **Not met** (one seed at 1.55 µs) |
| T4, location jump | ADR-0034 *Amendment 2026-11-11* (Accepted; 20 m `TBC`): ≥ 20 m flagged within 2 s in ≥ 95 % of runs, GNSS kept out while it lasts, no hazardous epoch | Detection: ≥ 20 m in ≥ 95 % of runs, 1.1 s, all four estimators. Kept out: default estimators follow it (50 m jump: 50 of 50 runs hazardous, `ekf`, `realistic`, before ADR-0047, not rerun); `ekf-guard` 0 of 20 at every size from 50 m to 1 km | #176 at `b00e906` (merged, #250), seeds 0–49; #191 (merged), seeds 0–19 | Detection met; refusal met only by the opt-in guard |
| T4, position ramp | 2 m/s detected within 30 s | 0 of 50, every estimator on `main` | #170 (merged, #250) | **Not met** |
| T4, time ramp | 50 ns/s detected within 60 s | 50 of 50 for `ekf`, `ekf-calibrated`, `ekf-imu`; median 3.3, 2.9, 3.3 s | #170 (merged, #250) | **Met** |
| T4, false alarms | ≤ 1 per hour on `nominal` | 0.0 /h for `baseline`, `ekf`, `ekf-calibrated`, `ekf-imu` on all three legs | #170 (merged, #250) | **Met** |
| T5, integrity | HPL bounds the error in ≥ 99.9 % of epochs; no hazardous epoch on fault scenarios | Worst run's bound 0.22 % to 21.18 % (four fast estimators, three legs). `ekf` on drone `outage`: 320 hazardous epochs on 7 of 50 seeds. `ekf-mhss`: 0 hazardous, but unavailable (worst bound 85 % drone, 78 % timing, partial run) | #170 (merged, #250) | **Not met** |

## (c) What each fix buys

Sim. Each on its own inputs; none of these numbers is A34 except where said. Together: the last row.

| Fix | PR, decision, state | What it buys | What it costs or leaves | Statistic, seeds, commit |
| --- | --- | --- | --- | --- |
| **Learned LTE noise**: the filter learns each cell's range noise instead of trusting the reported σ | #156 (open, draft), ADR-0039 proposed there (not on `main`); opt-in `ekf-learned-noise`, `ekf-calibrated-learned-noise` | Drone leg, `ekf`: median 4,034 → 982 m, worst 16,639 → 2,828 m; hazardous epochs 320 (7 seeds) → 0; LTE at least as good as no LTE on 15 → 46 of 50 seeds | Fallback still missed on every drone seed. Timing leg: LTE still worse than none (605 against 197 m median). Opt-in run: 3 hazardous epochs on seed 8 of `tower-clock-step` where the default has none | Per-run 300 s p95; seeds 0–49; `main` `9c5cb31` against #156 at `fb8a751` |
| **Carrier hopping**: one dongle dwells on several carriers in turn | #179 (merged, #250), ADR-0040 Proposed; study leg, not benchmark | Told the true noise: 120 s error 374 / 413 m (1 carrier, 2 masts per 10 s) → 68 / 69 m (13 carriers, 27 masts) for `ekf` / `ekf-calibrated` | Told 2 m: over 1,000 m whatever is heard. Neither target met (best 64 m at 120 s). Real hopping untested; the sim keeps every arc | Per-run, median over seeds; seeds 0–19; run at `fb62912` (not in the repo), seed 0 reproduced at `b61b650` |
| **Jump guard**: refuse a detected GNSS jump until the GNSS stream steps back | #191 (merged `83bbb97`), ADR-0038 Proposed; opt-in `ekf-guard`, `ekf-imu-guard`, `ekf-calibrated-guard` | Held 300 m jump, drone leg, `ekf`: hazardous epochs per run 5,244 (49/50 seeds) → 3 (3/50); on the spoofed position at +120 s: 44 of 47 → 0 of 50; honest GNSS back 0.1 s (median) after the jump ends, 50 of 50 | The filter then dead-reckons: median error 115 m / 1,263 m / 5,244 m at +30 / +120 / +300 s, HPL 547 m at +30 s (flagged unsafe). Keeps honest GNSS out after 5 of 46 hard manoeuvres with 1 Hz GNSS | [`jump-refusal/summary.md`](../analysis/results/jump-refusal/summary.md), seeds 0–49, `df46bce` |
| **Tower spoof monitor**: towers tested against GNSS outside the filter, 30 s and 120 s lags, ≥ 5 sites | #180 (merged, #250), ADR-0037 Proposed; opt-in `ekf-spoof` | 2 m/s ramp with every tower within 3 km heard (17 eNBs): 0 → 48 of 50 seeds, 131 s median, 313 s worst | Drone leg as committed (1 to 3 cells): 1 of 50. `realistic` set (4 towers): 0 of 50. 30 s out of reach: the ramp moves 60 m in 30 s against the towers' 34 m (1σ). No false alarms added | Seeds 0–49, `dd68887` |
| **Honest bound**: learned LTE noise plus the slow part of each emitter's range error as a filter state (*open*) | Draft PR #251, ADR-0046 proposed there (not on `main`); opt-in `ekf-honest`, `ekf-honest-guard` | Drone leg, 1 carrier: epochs above the HPL after GPS loss 45.33 % (`ekf`) → 0.45 % (`ekf-honest`), pooled | Single runs still escape (worst 18.5 %). 2 m/s ramp: 99.34 % of epochs above the HPL with `ekf-honest-guard` | Pooled over seeds 0–199, `analysis/results/honest-bound/summary.md` on #251 at `f9df0ea` |
| **Coherent integration** in the LTE front end | #171 (merged `9aa896c`), opt-in settings | Synthetic: weakest cell tracked 3 of 3 seeds, same PSS root, −11 → −14 dB | At Carleton (2 km, 24 sectors): 1.0 → 1.0 cells tracked | Synthetic, seeds 0–2, `9a54b73` |
| **All of the above on the drone leg** | #218, draft PR #247 at `35d061c` | today 3,268 m (120 s) / 12,507 m (300 s), `ekf` | learned noise + 13 carriers 132 m / 132 m (`ekf`), 158 m / 203 m (`ekf-calibrated`); ceiling told the true noise 111 m. **Neither target met** | A34, seeds 0–49 |

Why the noise fix comes first: told 2 m, the drone leg's `ekf` reached 6,557 m at 300 s; told the true 50 m, 1,002 m; with no LTE at all, 2,513 m (sim, per-run p95, #137 at `b6a2db2`, seeds 0–9; #147).

## (d) Spoofing: what is detected, how fast, what is refused

Sim unless marked. Detection means an alarm flag held 1 s (`pnt.metrics`). Read the first rows together: a sudden jump is caught in 1.1 s, while the slow 2 m/s drag, the more realistic attack, is caught by the default filter in 0 of 50 runs.

| Attack | Detected | How fast | What the output does | False alarms | Source |
| --- | --- | --- | --- | --- | --- |
| GNSS position jump, 20 m to 500 km | Every size, every variant, except one 20 m jump missed by `ekf` on `uc01-drone-circuit` (19/20) | 1.1 s (p95 1.1 s) | Default follows it: hazardous runs at 50 m, 100 m, 300 m, 1 km are 20, 19, 19, 4 of 20 (`ekf`, `realistic`, before ADR-0047, not rerun). `ekf-guard`: 0 of 20 at every size | 0 of 20 runs with no jump | ADR-0038; [`pr-evidence/191`](../analysis/pr-evidence/191/guard_jump_sizes.md), seeds 0–19, `5a7a1c9` |
| Jump of 15 m | 30 to 86 % of runs (by estimator and route) | 1.1 s | A missed jump under 20 m left the error ≤ 24 m | 0 in 50 clean runs (5 h) | #176 (merged, #250), seeds 0–49 |
| Small jump then drift (5 or 10 m, then 0.5 or 2 m/s) | At most 24 % of runs | — | Followed to 110 to 430 m | — | #176 (merged, #250) |
| 2 m/s position ramp | 0 of 50 on `main`; 48 of 50 with #180's monitor where 17 eNBs are heard; *open*: 0 of 50 with the monitor on 13 hopped carriers | 131 s median | Followed until detected | None added | #170, #180 (merged, #250); *open*: draft PR #254 at `3efe2bd`, `analysis/results/drag-with-hopping/summary.md` there, seeds 0–49; follow-up issue #258 |
| Meaconing (5 s late replay) | Both `ekf` and `ekf-guard` | 1.1 s | `ekf`: 1,995.5 misleading epochs per run; `ekf-guard`: 0 | 0 | ADR-0047's rerun after the scenario put our clock in its towers, seeds 0–49, [`pr-evidence/228/before-after.md`](../analysis/pr-evidence/228/before-after.md) at `73c9e9b` (1,976 on 20 runs before it, ADR-0038) |
| 50 ns/s GNSS time ramp | 50 of 50 | 3.3 s median, 4.1 s worst (`ekf`) | GNSS time excluded | 0.0 /h on `nominal` | #170 (merged, #250); RUNBOOK |
| Interference seen by aircraft (ADS-B quality and track jumps) | Jammed and spoofed approaches: 50 of 50 warned | Lead over our own zone entry: 48.2 s (jammed), 77.9 s (spoofed), median | Raises the GNSS fault prior in `ekf-mhss`; position unchanged; no integrity gain shown (0 misleading with or without) | 1.94 per hour on the clean approach, from placeholder quality dips | #166 (merged), ADR-0033 Proposed, seeds 0–49 |
| GNSS jamming by C/N0 (ADR-0031) | Real session: indicator 0 throughout (no alarm in 595 s) | — | Not tested against a real or injected attack | 0 in one 10-min real session | #211 (real) |
| Satellite that should not be visible; one spoofed-or-not output | Real session with a fake sky injected in software from 300 s: 59 of 59 faked skyviews flagged. Sim `spoof-jump-sky`: `ekf-guard` reaches spoofed in 20 of 20 runs | First suspect 5.0 s, first spoofed 10.0 s (PRNs below the horizon, real session); 5.0 s (`ekf-guard`, sim) | One spoofed-or-not level, advisory | 0 in 120 real skyviews (595 s); 0 in clean sim runs | #239 (merged, #250), ADR-0041 Accepted; [`pr-evidence/shrikar-feat-206-spoof-decision`](../analysis/pr-evidence/shrikar-feat-206-spoof-decision/summary.md), seeds 0–19 |
| Wrong tower table: an unregistered tower on one eNB's PCIs | `ekf-mhss` flags the site | — | `ekf-calibrated`: 186.5 m outage p95 and 5,147 hazardous epochs (confidently wrong, #132). `ekf-mhss` stays bounded, median HPL 5.4 km: safe, unavailable | — | Sim over real tower positions, #133 (merged), `a312c21`, 10 seeds (`ekf-mhss` 5) |

## (e) What is not shown

- **Towers carrying the position on the real-shaped legs.** With records that report only the fast noise, the filter rejects nearly every tower reading (one seed: 5,374 of 5,383 before the spoof, #180), so after GPS loss the default filter flies on the barometer and dead reckoning. The guard demo's panel lists LTE as not in use (PR #220, open). No percentage of epochs is committed.
- **A useful position from real towers.** Two real static sessions with GPS cut in software, 5 cut times each, with the front end after #245's fixes ([`lte-reacq-steps/NOTES.md`](../analysis/results/lte-reacq-steps/NOTES.md) *GPS cut*, front end `9e7728a`, cut script at `f15ba13`): with LTE, `ekf` median 21,553 m at 300 s on `20261111-0151` and 10,718 m on `20261111-0233`; without LTE 0.6 / 1.3 m, right by construction because the receiver does not move. #245 removed the front end's arc steps (re-find step median 736 → 9.4 m on `0151`), yet LTE still does not beat no LTE: the default filter trusts records told 1 to 5 m that are off by tens of metres. T1 and the fallback missed with LTE. Before #245 (#233, merged, #250; [`real-gps-cut-20261111/summary.md`](../analysis/results/real-gps-cut-20261111/summary.md), `0151` only): 4,228 m at 120 s and 12,436 m at 300 s. All of these predate ADR-0047's default, which changes `ekf` on real data (GNSS time is always used before the cut); not rerun.
- **Any real-world accuracy, integrity level or detection rate.** Every number in (b), (c) and (d) is sim or synthetic, except the rows marked real.
- **T1 on the agreed statistic for the `challenge` legs:** met by none (best 10,154 m, (b)); with every fix together: 132 m for 0–300 s (`ekf`, draft PR #247), not met.
- **How many towers are enough with the barometer and IMU:** sim, seeds 0–19 (#232, merged, #250; [`tower-count/summary.md`](../analysis/results/tower-count/summary.md)): with the committed and the honest error models no tower count meets T1 or the fallback. With clean errors, all 17 sites within 3 km meet T1 (worst second 10 to 12 m) and the 6 strongest meet the fallback.
- **A confidence heat map on the track:** built (#235, merged: the track coloured by confidence against the alert limit; [`pr-evidence/207`](../analysis/pr-evidence/207/)). Beside it the panel shows NOMINAL / DEGRADED / UNSAFE, the HPL against the alert limit and latched alerts.
- **T2**, scored against its alert limit; the approach leg's towers are synthetic.
- **Real carrier hopping, a moving capture, multipath size on real signals, bias against truth.**
- **The reference station on hardware** (sim only, ADR-0020 *Amendment 2026-11-10*), **LEO** (sim only, #172: towers-only 19.8 m → 4.4 m with Starlink in the kind case, every value `TBC`), the hostile beacon (#167: no accuracy gain on these models).
- **VOR's contribution:** sim, median change −0.7 m, better on 30 and worse on 20 of 50 seeds (sign test p = 0.20, [`vor-ablation/`](../analysis/results/vor-ablation/summary.md)).
