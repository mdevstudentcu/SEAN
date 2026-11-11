# The 5-minute deck

- **Status:** Draft, 2026-11-11 (#28), against `main` at `c21e047`. Written for a presenter who did not build the system.
- **Format:** 10 slides, 300 s, 643 words of script. Each slide: the headline (the point, as a sentence), what is on it, the figure, the word-for-word script, and where to look if asked. Question answers: [`judge-questions.md`](judge-questions.md). Every number: [`results.md`](results.md).
- **Three rules on stage.** Say "simulation" whenever a number is simulated. Say "consistent with a registered site", never "identified". Never say "first": say "we found no published…".
- **Placeholders.** `TBD (#NNN)` lines are filled from that issue before judging. If one is not filled, use the script as written: it does not depend on it.

| # | Slide | Seconds | Words |
| --- | --- | --- | --- |
| 1 | The problem and who needs it | 25 | 54 |
| 2 | What we built | 30 | 63 |
| 3 | Integrity first: every source can lie | 30 | 67 |
| 4 | Live demo | 55 | 98 |
| 5 | What we measured on real signals | 30 | 69 |
| 6 | The calculation behind the accuracy | 30 | 66 |
| 7 | The honest scoreboard | 30 | 65 |
| 8 | What each fix buys | 30 | 67 |
| 9 | Limits | 20 | 42 |
| 10 | Roadmap | 20 | 52 |
| | **Total** | **300** | **643** |

---

## 1. The problem and who needs it

**Headline:** When GPS is jammed or faked, a drone needs a position and an honest answer to whether it can trust it.

**On the slide:**
- Users: an inspection drone over Ottawa (first), an aircraft approaching Ottawa airport, a timing receiver.
- Our mentors' order: location first; tell when GPS is lying; timing second.
- Our answer: keep position from cell towers already on the air, with a confidence number.

**Figure:** [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-1-clean.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-1-clean.png) (operator panel, simulation, real tower sites on the map).

**Script (54 words, 25 s):**
> GPS is easy to jam and easy to fake. When that happens, a drone over Ottawa needs a position, and an honest answer to "can I trust it?" Our Honeywell mentors were clear: location first, and above all, tell when GPS is lying. That is what we built, for drones first, with timing second.

**If asked:** use cases, [`use-cases.md`](use-cases.md); mentors' priorities, call of 2026-11-10 and [`mentor-qa.md`](mentor-qa.md).

## 2. What we built

**Headline:** A receive-only payload records real cell towers, GPS, motion and pressure; a laptop turns them into a position with a confidence number.

**On the slide:**
- Payload: Raspberry Pi 4B, low-cost software radio (NESDR SMArt v5), GPS receiver with timing pulse, motion sensor, barometer. It never transmits.
- Laptop: tower sync signals, matched to the public ISED registry, fused by a Kalman filter, shown on an operator panel.
- One code path for simulation, recordings and live.

**Figure:** [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-3-time-pl-alert.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-3-time-pl-alert.png) (panel, simulation, the real Rogers sites on the map).

**Script (63 words, 30 s):**
> A Raspberry Pi payload with a low-cost software radio, a GPS receiver, a motion sensor and a barometer. It only listens; it never transmits. A laptop picks out the sync signals of real cell towers, looks each tower up in the public Canadian registry, and fuses everything into a position with a confidence number. The same code runs on simulation, recordings and live.

**If asked:** Q4 (where towers are), Q10 (legal); [`architecture.md`](architecture.md).

## 3. Integrity first: every source can lie

**Headline:** Every source can lie, GPS and the towers alike, so only independent evidence may vouch for GPS.

**On the slide:**

| Source | How it can lie | What catches it today |
| --- | --- | --- |
| GPS | Jump, slow drag, fake time | Jump flagged in 1.1 s; time drag in 3.3 s median (simulation) |
| Cell towers | Clock jump, wrong registry entry, fake tower | One fault test per site and per network (simulation) |
| Aircraft reports (ADS-B) | Carry someone else's GPS | An early warning only (simulation) |

Sky-map check (a satellite that should not be visible): `TBD (#206)`.

**Figure:** [`analysis/results/gnss-health-20261111-fullsuite/gnss_health.png`](../analysis/results/gnss-health-20261111-fullsuite/gnss_health.png) (real GPS signal power, 595 s, no jamming flag).

**Script (67 words, 30 s):**
> Design rule: every source can lie. GPS can jump, or be dragged slowly. A tower's clock can jump, or the registry can be wrong. Towers take their time from GPS, so they may contradict GPS time but never confirm it. On the right is real GPS signal power from our payload, the baseline our jamming check uses. The sky-map check our mentor suggested is in progress today.

If #206 lands, replace the last sentence with one line from its result (same length), and put its figure here.

**If asked:** Q7 (slow ramp), Q8 (false alarms), Q9 (why refuse GPS); [ADR-0024](adr/0024-gnss-dependency-tags.md).

## 4. Live demo

**Headline:** In simulation, the panel says "do not trust this" seconds after GPS is lost, and catches a 300 m GPS jump at once.

**On the slide:** the live panel. Run `deploy/demo/demo.sh stage` ([`deploy/demo/RUNBOOK.md`](../deploy/demo/RUNBOOK.md), pre-flight first). Press Enter when T+ passes 142 (outage → jump). Press Ctrl-C when T+ passes 190: the time-spoof segment is left out (timing is second priority, and the 55 s does not hold it).

**Figure:** the live panel. Fallback if the laptop fails: the screenshots in [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/), `outage-1` to `jump-3`, with the same script.

**Script (98 words, 55 s)**, cued by the panel's T+ clock as in the runbook:
> *[T+0, NOMINAL]* This is simulated, over the real tower sites around Carleton. The circle is our bound on the error. *[T+62]* Now GPS is gone. *[T+65, UNSAFE]* Five seconds later the panel says: do not navigate on this position. *[T+100]* Forty seconds in, we are 321 metres off, and the bound is still larger than the error. *[Enter; T+150]* Now a spoofer moves GPS 300 metres east. Caught at once: GPS rejected. *[T+177, NOMINAL]* But watch: after 27 seconds this default filter lets the fake GPS back in. That was our open bug. The fix is merged as an option; the next slide shows it over fifty runs.

The demo runs plain `ekf`, as rehearsed. Showing `ekf-guard` refusing the jump live is the owners' call and is **not rehearsed** (RUNBOOK, *`ekf-guard`*). Only if it is chosen and rehearsed, replace the last three sentences with "This time the jump is refused: GPS stays out, and the panel says unsafe rather than following it."

**If asked:** one seed is not a statistic: over 50 seeds, `ekf` has hazardous epochs on 7 (#170); Q6 (how the bound is computed).

## 5. What we measured on real signals

**Headline:** On real towers our low-cost radio is precise to under a metre on strong cells, but a slower error of several metres sits on top that it does not report.

**On the slide:**
- 15 static captures, 2026-11-10: 1 to 4 cells per frequency; most consistent with a registered site, at least one not in the registry.
- Range noise: 0.63 m on the strongest cells, 24.7 m on the weakest (10 records a second); a slow error of 8.3 m median the radio's own estimate leaves out.
- No GPS fix in those captures: no real position yet. Real GPS session with timing pulse, 2026-11-11: 18 satellites, no jamming flag.

**Figure:** [`analysis/results/lte-measured-noise/white_vs_snr.png`](../analysis/results/lte-measured-noise/white_vs_snr.png) (real).

**Script (69 words, 30 s):**
> Real signals. On November tenth we recorded fifteen static captures of real towers. We hear one to four cells per frequency, most matching a registered site. Range noise falls from 25 metres on weak cells to 0.6 metres on strong ones. But a slower error, typically 8 metres, sits on top, and the radio's own estimate misses it. Those captures had no GPS fix, so no real position yet.

**If asked:** Q2 (is any of it real), Q5 (8-bit radio), Q15 (what the sim got wrong); [ADR-0036](adr/0036-lte-measured-error-model.md) (Proposed).

## 6. The calculation behind the accuracy

**Headline:** We add up every error term after GPS loss and check the sum against simulated flights: easy assumptions meet 25 m, realistic ones do not.

**On the slide:**
- Terms: range noise, multipath, tower and receiver clock drift, geometry; each with its source.
- Six synthetic towers, easy errors: 95 % of 50 flights within 22 m for 300 s with the motion sensor (budget 15 m). Realistic errors: 713 m.
- Handover: GPS must be good for 120 s before loss to stay within 25 m.

**Figure:** [budget against Monte Carlo, open PR #178 at `1bd1791`](https://github.com/HalfPast9/genocide-hackathon/blob/1bd1791ac137de2fc92703b92eaae9c2d1f7f687/analysis/results/accuracy-budget/budget_vs_monte_carlo.png?raw=true) (simulation).

**Script (66 words, 30 s):**
> The mentors asked us to explain the calculation. So we list every error source after GPS loss: range noise, multipath, clock drift, geometry. We add them up and check the total against fifty simulated flights. With six towers and easy error sizes, the motion-sensor version keeps 95 percent of flights within 22 metres for five minutes. With realistic sizes, multipath alone pushes it past 360 metres.

**If asked:** Q1 (why we miss our target), Q3 (three towers); #178 write-up `systems/accuracy-budget.md` (open PR).

## 7. The honest scoreboard

**Headline:** In simulation we detect spoofing on time, but miss the accuracy targets on records shaped like real ones.

**On the slide:**

| Target | Result (simulation) | Verdict |
| --- | --- | --- |
| Position: 25 m for 5 min; fallback 50 m for 2 min | No simulated flight meets either; agreed statistic `TBD (#187)` | Missed |
| GPS jump ≥ 20 m flagged within 2 s | 1.1 s, ≥ 95 % of runs | Met |
| Time drag flagged within 60 s; ≤ 1 false alarm/h | 50 of 50, 3.3 s median; 0.0 /h | Met |
| Bound holds in 99.9 % of epochs | Worst run 0.22 % to 21 % | Missed |

**Figure:** [T1 per seed, drone leg, open PR #170 at `9b2ed25`](https://github.com/mdevstudentcu/genocide-hackathon/blob/9b2ed253da1c34aee82ffd665a509a37da62d642/analysis/results/challenge-baseline/t1_drone.png?raw=true) (simulation; being regenerated, #187). Replace with #187's figure when it lands.

**Script (65 words, 30 s):**
> Here is the honest scoreboard, all simulation, on records shaped like our real ones. A GPS jump of 20 metres or more is flagged in 1.1 seconds, a time drag in a median of 3.3 seconds, with no false alarms on clean runs. But no simulated flight meets our 25-metre target or the mentors' 50-metre fallback. Numbers on the agreed statistic are being regenerated today.

**If asked:** Q1, Q6, Q8; the statistic is ADR-0034's *Amendment* (95th percentile across runs at every second, worst second).

## 8. What each fix buys

**Headline:** Each fix helps on its own in simulation; the line that counts, all of them together, is `TBD (#218)`.

**On the slide:**

| Fix | What it buys (simulation) | Status |
| --- | --- | --- |
| Learn each tower's noise | Median of each run's 5-min p95 error 4,034 → 982 m; dangerous epochs 320 → 0 | Open PR #156, opt-in |
| Listen on 13 frequencies (noise known) | 2-min error 374 → 68 m | Open PR #179 |
| Refuse a flagged jump | Dangerous epochs on a held 300 m jump: 5,244 → 3 per run | Merged #191, opt-in |
| All together, drone leg | `TBD (#218)` | In progress |

**Figure:** [`analysis/results/jump-refusal/error_after_jump.png`](../analysis/results/jump-refusal/error_after_jump.png) (simulation, 50 seeds); the #218 ladder `TBD (#218)`.

**Script (67 words, 30 s):**
> What does each fix buy, in simulation? Learning each tower's real noise cut the median five-minute error from 4,034 to 982 metres, with no dangerous epochs left. Once the noise is right, listening on thirteen frequencies instead of one cuts the two-minute error from 374 to 68 metres. Refusing a flagged jump cut dangerous epochs from 5,244 per run to 3. All three together is running today.

If #218 lands, replace the last sentence with "All three together: `TBD (#218)` metres at two minutes, against 50." Read the number from #218's summary, not from memory.

**If asked:** Q9 (why refuse); the guard's cost: after a refused jump the filter dead-reckons (median 1,263 m at +120 s, flagged unsafe).

## 9. Limits

**Headline:** We have not shown a position from real towers, real frequency hopping, or an error model measured on the move.

**On the slide:**
- No real position yet; first real error after GPS loss `TBD (#214)`.
- Noise measured at rest only; nothing moving; hopping untested on hardware.
- Reference station, satellites and attacks: simulation only. We never transmit.

**Figure:** [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/real-dash-today.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/real-dash-today.png) (a real session on the panel: NO DATA, no GPS origin). Replace with #214's figure if it lands.

**Script (42 words, 20 s):**
> Our limits. No position from real towers yet: those captures had no GPS fix. A replay with GPS cut in software is in progress today. Our noise model is measured at rest, never moving. And every attack is simulated: we never transmit.

If #214 lands, replace the second and third sentences with its one-line result, labelled "real session, GPS removed in software".

**If asked:** Q2, Q13; [`results.md`](results.md) (e).

## 10. Roadmap

**Headline:** Next: measure on the move, earn integrity from real fault statistics, then offer the radio layer Honeywell's suite lists without a product.

**On the slide:**
- Moving captures with independent truth; one spoofed-or-not decision from signal power and the sky.
- Fault statistics from many hours of data; a receiver that hears many frequencies at once.
- Certification: no standard exists yet for this kind of navigation; drones first.

**Figure:** [error against masts heard, open PR #179 at `ff45493`](https://github.com/mdevstudentcu/genocide-hackathon/blob/ff45493df7962050b700aa535e7093283ed76bf7/analysis/results/hopping-study/error_vs_masts.png?raw=true) (simulation).

**Script (52 words, 20 s):**
> Next: moving captures with an independent truth, and one clear spoofed-or-not decision from signal power and the sky. Then fault statistics from many hours of data, which certification needs, and a receiver that hears many frequencies at once. Honeywell's suite lists radios without a product. This could be that layer. Thank you.

**If asked:** Q13 (a month), Q14 (certification); [`roadmap.md`](roadmap.md).
