# Results

- **Status:** Draft, 2026-11-10 (#28). Collected from PR descriptions and today's captures; nothing here was re-run for this file.
- **Rule:** every number names its kind and source. **Sim** results come from committed scenarios with every model value `TBC` or `placeholder` ([`verification.md`](verification.md) *Sim validity*), and are never real-world accuracy. **Synthetic** means generated baseband through the real front end. **Registry** means tower-table geometry with no radio. **Real** means a recorded session.
- **Most sources are open PRs.** A number from an open PR is that PR's evidence, not yet reviewed or merged into `main`. The PR names the commit and command that reproduce it (REQ-10).
- Targets T1–T5 are in [`plan.md`](plan.md); the mentors' answers of 2026-11-10 and ADR-0034 are in open PR #158.

## 1. The challenge baseline: where we stand

**Sim.** Every estimator on every entry of the three `challenge` legs ([ADR-0030](adr/0030-challenge-benchmark-set.md), Proposed): records shaped as the real front end writes them, the `realistic` set's error sizes (50 m range noise, 50 m multipath, `TBC`), 60 s of GPS, a 600 s outage. Source: open PR #170, `python analysis/challenge_baseline.py --seeds 50 --jobs 3` at `4e4c9d1`, seeds 0–49 (`ekf-mhss` 0–19 on six entries per leg).

| Target (`TBC`) | Result | Verdict |
| --- | --- | --- |
| T1, 25 m for 300 s (drone, `outage`) | Best mean 4,284 m (`ekf-calibrated`); no seed of any estimator meets it | **Not met** |
| T2, 556 m alert limit (approach, synthetic towers) | No metric scores it; 300 s error 1,313 to 2,467 m, for reference only | **Not scored** |
| T3, 1.5 µs at 10 min with an honest σ (timing, `outage`) | `ekf`, `ekf-imu`: 49 of 50 seeds (one at 1.55 µs). `ekf-calibrated`: 0.15 µs mean, but its σ bound fails on 13 seeds | **Not met** |
| T4, 2 m/s position ramp within 30 s | 0 of 50, every estimator, every leg | **Not met** |
| T4, 50 ns/s time ramp within 60 s | 50 of 50 for `ekf`, `ekf-calibrated`, `ekf-imu` (median 3 s); `baseline` 0 | **Met** by those and `ekf-mhss` |
| T4, ≤ 1 false alarm per hour (`nominal`) | 0.0 /h for the four fast estimators; `ekf-mhss` 1.3 /h on the timing leg | **Met** except `ekf-mhss` on timing |
| T5, HPL bounds the error in ≥ 99.9 % of epochs | Worst runs 0.2 % to 21 % for the fast estimators; `ekf-mhss` 0 hazardous epochs but a worst bound of 78 to 85 % | **Not met** |

Worst case worth naming: `ekf-imu` under the IMU bias entry reaches 81,955 m (`challenge-drone-outage-imu-bias`, 5 runs, #170).

**The first cause: LTE told the front end's reported sigma makes position worse than no LTE.** Sim, drone leg, 300 s p95, #137 (merged), commit `af2efce`, seeds 0–9:

| What the filter is told | `ekf` | `ekf-calibrated` |
| --- | --- | --- |
| 2 m reported sigma (what real records say) | 6,557 m | 5,260 m |
| The true 50 m | 1,002 m | 832 m |
| No LTE records | 2,513 m | 2,513 m |

Tracked as #147. A fix that learns each tower's noise from its innovations (open draft PR #156, **Not ready**) brings the drone leg's `ekf-calibrated` mean from 4,284 to 1,411 m (sim, seeds 0–49, base `7e98172` against `9c51e51`), but hazardous epochs rise (56 to 233) and on the timing leg LTE is still worse than none (229 m without LTE).

## 2. Why T1 is missed, and what it would take

### First-principles accuracy budget (UC-01)

**Sim.** Each error term after GPS loss with its source, against Monte Carlo; 120 s of GPS first. Source: open PR #178, `python analysis/accuracy_budget.py --runs 50 --jobs 5` at `cee2607`, seeds 0–49; write-up `systems/accuracy-budget.md` in that PR. `uc01` is `uc01-drone-circuit` (6 synthetic towers, 20 m noise, sim-shaped records); `uc01-realistic` is the same route with the `realistic` set's errors.

| Scenario | Estimator | T1: 25 m / 300 s (budget / Monte Carlo) | Fallback: 50 m / 120 s | Term that sets it |
| --- | --- | --- | --- | --- |
| uc01 | `ekf` | 23 / 27 m: missed | 23 / 27 m: met | Range noise after handover |
| uc01 | `ekf-imu` | 15 / 22 m: **met** | 14 / 22 m: met | Range noise after handover |
| uc01 | `ekf-calibrated` | 53 / 40 m: missed | 32 / 33 m: met | Calibration noise left in the learned drifts |
| uc01-realistic | `ekf-calibrated` | 501 / 713 m: missed | 324 / 425 m: missed | Multipath (50 m, `TBC`) and four more terms each over 25 m |
| uc01-realistic | `ekf`, `ekf-imu` | 7.2 / 4.2 to 9.4 km: missed | missed | Our clock's 20 ppb drift, not modelled in tower ranges |

- Handover (mentors' Q3): on uc01, `ekf-imu` needs 120 s of GPS before loss to meet T1; the fallback needs 30 s (`ekf`, `ekf-imu`) or 120 s (`ekf-calibrated`). With the realistic errors, no calibration time up to 300 s is enough.
- IMU alone (MPU6050 values measured in open PR #157): ≤ 25 m for 31 s, ≤ 50 m for 43 s.
- Budget and Monte Carlo disagree in places (listed in #178's write-up, some unexplained).

### Hearing more towers by hopping carriers

**Sim.** One dongle dwelling on several carriers in turn on the `challenge` drone leg. Source: open PR #179, `python analysis/accuracy_budget.py --seeds 20 --jobs 3` at `fb62912`, seeds 0–19 paired, `outage` entry; median over seeds of the p95 horizontal error, `ekf` / `ekf-calibrated`.

| What is heard | Masts per 10 s | 120 s, told 2 m | 120 s, told the true noise | 300 s, told the true noise |
| --- | --- | --- | --- | --- |
| 1 carrier (today's leg) | 2 | > 1,000 m | 374 / 413 m | 715 / 963 m |
| Hop 6 carriers | 9 | > 1,000 m | 112 / 100 m | 129 / 140 m |
| Hop 13 carriers | 27 | > 1,000 m | 68 / 69 m | 78 / 87 m |
| Every tower within 3 km, 1 carrier | 13 | > 1,000 m | 64 / 68 m | 66 / 91 m |

- **Order matters:** with the reported 2 m, no number of masts gets under 1 km. Only once the noise is honest (#147) does hopping help, by a factor of five here (374 to 68 m).
- **Neither target is met even then** (64 m against 50 m at 120 s; 66 m against 25 m at 300 s). What remains is the assumed error sizes, all `TBC`.
- Real hopping is untested: the sim keeps every arc across a retune. The hop set and dwell are open questions for the owners (#179).

PRs #178 and #179 both add `analysis/accuracy_budget.py` and `analysis/results/accuracy-budget/`, with different content. Which is the team's accuracy budget is open.

### The front end's near-far limit

**Synthetic** baseband, link budget `TBC`. Source: #133 (merged), dense case, commit `2444589`, 3 seeds; open PR #171, commit `00b1170`, seeds 0–2.

| Finding | Value | Source |
| --- | --- | --- |
| A cell is lost when it is this far below a fully loaded strong one | 13 dB | #133, #131 |
| Sectors tracked at Carleton (2 km), of 24 sent; second-strongest cell | 1.0; -18.7 dB | #133 |
| Sectors tracked far from every tower (5 km), of 57 sent | 4.7 | #133 |
| Weakest cell tracked in 3 of 3 seeds, same PSS root, default / coherent integration | -11 / -14 dB | #171 |
| Ghost PCIs, either setting | 0 | #133, #171 |
| Cells tracked at Carleton with coherent integration | 1.0 (no change) | #171 |

## 3. Spoofing and location jumps

### Location jumps (the mentors' first attack)

**Sim.** Source: open PR #176, `python analysis/jump_study.py --runs 50` at `6f03e92`, 50 seeds per size, 8 directions, jumps of 5 to 1,000 m at 150 s; `realistic-uc01` (the realistic set's errors on the UC-01 route) and `uc01` (`uc01-drone-circuit`).

| Finding | Value |
| --- | --- |
| Smallest jump detected in ≥ 95 % of runs, all four estimators, both environments | 20 m |
| Detection delay | 1.1 s (the 1 s alarm hold plus one epoch) |
| Worst error in runs that missed a jump under 20 m | ≤ 24 m |
| Runs with hazardously misleading epochs, 50 m jump, `ekf` (realistic-uc01 / uc01) | 50 of 50 / 47 of 50 |
| Same, `ekf-mhss` | 0 of 50, because its HPL exceeds 50 m in every pre-jump epoch (realistic-uc01) and 68 % of them (uc01): unavailable |
| Jump then drift (5 or 10 m, then 0.5 or 2 m/s): detected | ≤ 24 % of runs; followed to 110 to 430 m |
| False alarms, 50 clean runs (5 h) | 0 |

**The output follows a detected jump.** Sim, `challenge` legs, open PR #180 at `220a6fa`, seeds 0–49: every jump from 25 m to 300 m is detected in 1.1 s, and 30 s later the error equals the jump on 49 or 50 of 50 seeds. GNSS stays excluded for 13 % of those 30 s at a 25 m jump, 91 % at 300 m (#184). Refusing a detected jump is #184, not started.

Proposed T4 jump target, in #176 for ADR-0034 (`TBC`, not decided): a jump of 20 m or more flagged within 2 s in ≥ 95 % of runs, GNSS kept out while the jump lasts, no hazardously misleading epoch. Against it (sim): detection met; the exclusion clause failed by `ekf`, `ekf-calibrated`, `ekf-imu`.

### The slow position ramp

**Sim.** 2 m/s ramp, T4 asks for 30 s. Source: open PR #180, `python analysis/spoof_detection.py --seeds 50` at `220a6fa`, seeds 0–49; monitor settings chosen on seeds 100–109.

| Where | `ekf` | `ekf-spoof` (opt-in monitor) | Time to alert, median / worst |
| --- | --- | --- | --- |
| Drone leg as committed (1 to 3 cells) | 0 of 50 | 1 of 50 | 374 s |
| Same leg, every tower within 3 km heard (17 eNBs) | 0 of 50 | **48 of 50** | 131 s / 313 s |
| `realistic` set (4 towers) | 0 of 50 | 0 of 50 | — |

- 30 s is out of reach with these error sizes: in 30 s the ramp moves the fix 60 m, against 34 m (1σ) of the towers' own uncertainty over that lag (#180).
- No false alarms added on `nominal` or `outage`.
- Why nothing fired before: on the challenge legs the filter rejects almost every tower reading (5,374 of 5,383 before the spoof, one seed) because records report 2 m (#147). The filter is in effect GPS-only.
- ADR-0021 leads the pitch with this claim; whether to narrow its wording to what is shown is the owners' open question (#180).

### Time spoofing

**Sim**, #170: a 50 ns/s time ramp is detected on 50 of 50 seeds by `ekf`, `ekf-calibrated`, `ekf-imu`, median 3 s (§1).

## 4. A wrong tower table

**Sim over real tower positions.** Source: #133 (merged) and #132, `analysis/lte_real_geometry.py`, commit `7c1afb7`, 10 seeds (`ekf-mhss` 5). The kind case: 54 cells matched, every tower heard all the time, white noise, no multipath.

| Case | `ekf` outage p95 | `ekf-calibrated` outage p95 | `ekf-calibrated` hazardous epochs |
| --- | --- | --- | --- |
| Correct table (kind case) | 10.2 m | 10.4 m | 0 |
| One eNB filed 500 m off | 11.8 m | 77.8 m | 10 |
| Unregistered tower on one eNB's PCIs | 10.7 m | 186.5 m | 5,147 |

`ekf-mhss` stays bounded and flags the bad site, with a median HPL of 5.4 km: safe and unavailable. T1 is met only in the kind case.

## 5. Real signals

### The tower table

**Registry**, #133 (merged), commit `2444589`: of the 4,059 rows of the 2026 Ottawa table, seen from Carleton, 3,752 match their own eNB, 307 are dropped as collisions, and **0 match another eNB**.

### First captures, 2026-11-10

**Real.** Payload Pi, one NESDR SMArt v5, outside, static, no GPS fix (so no position truth and NTP-disciplined timestamps). Recorded at `4d3598b`; front end at `9fcf016` (the #181 fix). Sources: open PRs #182 and #177 record the first spot's 2460, 5145 and 5255 sessions; the rest is the team's capture summary of 2026-11-10, `TBC` until a PR records it. Tower matches checked for this file against `data/reference/lte-cells-ottawa.csv` at `8987664`.

First spot (short bundle antenna):

| EARFCN (licensee) | Cells tracked | Registered eNB | Source |
| --- | --- | --- | --- |
| 2460 (Rogers) | PCI 244, 48.9 s of 59.5 s at 14.8 dB; PCI 268 found, never tracked | 30066 | #182, #183; length 59.5 s from the summary |
| 5255 (TELUS) | PCIs 175, 188 | 219076, 219003 | #182, #177 |
| 5145 (TELUS) | PCIs 189, 175, 188 (175 and 188 break into 15 arcs each in 30 s) | 219003, 219076, 219003 | #177, #183 |
| 2535 (TELUS, Bell) | None | — | #177 |

- **Every tracked cell matched a unique registered eNB** (summary; each (EARFCN, PCI) above appears once in the table).
- **Reported against observed noise** (summary): reported σ 1.1 to 4.3 m, observed spread 4 to 13 m at 10 Hz, a ratio of 3 to 8. For PCI 244 alone (#177): epoch-to-epoch white noise 0.73 m against 1.26 m reported, and 5.95 m residual from a quadratic fit (tower clock, dongle clock and multipath wander together). The white part is small; the slow part, which the reported σ does not include, is not. This is #147 on real data.
- **Dongle frequency:** the summary gives a dongle frequency error of +0.26 to +0.29 ppm. #177 and #183 give the measured carrier offsets as -0.17 to -0.30 ppm (-120 to -260 Hz), with one outlier, PCI 175 on 5145, at +0.52 ppm (#183: a sign flip or a wrong-carrier lock, open). The sign convention between the two is `TBC`.
- **Timing chain cross-check** (#177): PCI 244's pseudorange slope, 86.8 m/s, agrees with its measured carrier offset (0.30 ppm of c is 90 m/s).

Second spot (13-carrier scan, 60 s each; summary only):

| EARFCN | Cells tracked | In the table? |
| --- | --- | --- |
| 5060 (Vidéotron) | Three cells, 54 to 58 s: two sectors of eNB 102790 and PCI 204 | PCI 204 is not |
| 2560 (TELUS) | PCI 347, 59 s | Not in the table |
| 2460 (Rogers) | Three weak cells on three eNBs | Yes |
| 2535, 5035, 5085 | None | — |

- Weaker than the first spot: most cells at the front end's floor, many broken arcs.
- Three tracked cells are not in the table. The lookup drops them (ADR-0023); a mapper for them is not built.

### Other real results

| Result | Kind | Source |
| --- | --- | --- |
| The front end crashed on 2 of the first 4 captures (negative loop variance on a re-found cell); fixed, with a test that fails without the fix | Real | #181; open PRs #182, #177 |
| Pi streamed to `pnt live` on the laptop over the authenticated CurveZMQ link, 2026-11-10, 18:00 | Real, stream only | Capture summary |
| MPU6050 noise from an overnight static session `20261110-0306-static-bench-overnight`: accel 240 µg/√Hz, gyro 0.005 °/s/√Hz | Real | Open PR #157 |

## 6. The LEO layer

**Sim, the kind case.** Doppler from real orbits added to the sim-shaped `ottawa-towers` records (not the `challenge` legs). Source: #172 (merged), `analysis/starlink_paired.py`, seeds 0–49, computed on a local merge `b498c7e` of the branch with #154, both since merged into `main`; not re-run on `main`. Fault-window p95 mean:

| Condition | `ekf` | `ekf-calibrated` |
| --- | --- | --- |
| Towers only | 19.8 m | 23.9 m |
| + Iridium | 8.0 m | 14.2 m |
| + Starlink | 4.4 m | 5.4 m |
| + both | 4.3 m | 5.0 m |

Every LEO value is `TBC`; the filter is told exact satellite positions. Starlink's downlink is Ku band, which an RTL-SDR cannot receive ([ADR-0013](adr/0013-no-iridium-hardware.md), #172).

## 7. What is not shown

- **Any position from real towers.** One to three cells per carrier, a static receiver and no GPS truth.
- **Any real-world accuracy, integrity level or detection rate.** Every number in §1 to §4 and §6 is sim or synthetic.
- **T2** (no metric scores the approach's alert limit), and the approach leg's towers are synthetic.
- **Real carrier hopping**, a moving receiver through the baseband chain, multipath on real signals.
- **Attacks injected into a real session** (ADR-0015 asks for it).
- **The reference station** on hardware, and the hostile-emitter, residual-map and drone-as-reference ideas (open PRs #167, #168, #174), all sim.
- Whether 1 to 3 cells per carrier is the near-far floor or the towers in range (#177).
