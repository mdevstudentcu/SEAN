# The 5-minute deck

**The pitch in one line:** a navigation layer that knows when it is wrong, and tells the operator not to trust it.

Seven slides, 255 s, 526 words of script, 16 numbers spoken. Seconds are the words at 2.1 a second, except the demo, which the panel's clock sets at 80 s. Each slide gives the headline, what is on it, the figure, the word-for-word script and where to look if asked. Answers to questions: [`judge-questions.md`](judge-questions.md). Every number and its source: [`results.md`](results.md) (*Numbers the deck speaks or shows*).

**Three rules on stage.** Say "simulated" whenever a number is simulated. Say "consistent with a registered site", never "identified". Never say "first": say "we found no published…".

| # | Slide | Seconds | Words | Numbers spoken |
| --- | --- | --- | --- | --- |
| 1 | The moment: green and 300 m wrong | 21 | 44 | 1 |
| 2 | What we built | 21 | 45 | 0 |
| 3 | Live demo | 80 | 157 | 3 |
| 4 | Real signals | 27 | 56 | 2 |
| 5 | Where we miss, and what closes the gap | 45 | 95 | 7 |
| 6 | Every source can lie | 35 | 74 | 2 |
| 7 | Roadmap | 26 | 55 | 1 |
| | **Total** | **255** | **526** | **16** |

Numbers spoken: three hundred metres (1); five seconds, three hundred metres, half a minute (3); seven-tenths of a metre, eight metres (4); two metres, thirteen carriers, ninety-five percent, fifty, a hundred and thirty-two metres, five minutes, twenty-five (5); fifty-nine, a third (6); a hundred and seventy dollars (7).

---

## 1. The moment

**Headline:** The real danger is not losing GPS: it is a display that is green and confident while the aircraft is 300 m off.

**On the slide:** one screenshot, green NOMINAL with a 7 m bound and a 300 m true error (simulation). One line under it: "A navigation layer that knows when it is wrong."

**Figure:** `jump-3-followed.png` in the guard demo evidence (`analysis/pr-evidence/elshoubky-docs-28-demo-guard/`, PR #220 (merged)); until it merges, [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/jump-3-followed.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/jump-3-followed.png) shows the same moment.

**Script (44 words, 21 s):**
> Picture a drone whose display is green, with a tight error bound, while it is three hundred metres off course. That is worse than losing GPS: nobody knows to stop. We built a navigation layer that knows when it is wrong, and says so.

**If asked:** Q9 (why refuse GPS after a jump).

## 2. What we built

**Headline:** A receive-only payload that records real cell towers beside GPS and motion, and a laptop that turns them into a position with a bound and tells the operator when not to trust it.

**On the slide:**
- Payload: Raspberry Pi 4B, low-cost software radio, GPS receiver with timing pulse, motion sensor, barometer. Never transmits.
- Laptop: tower sync signals matched to the public ISED registry; a position with a bound under our model; green, amber, red.
- Every number labelled simulated or real.

**Figure:** [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-1-clean.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-1-clean.png) (panel, simulation, real tower sites on the map).

**Script (45 words, 21 s):**
> A receive-only payload: a Raspberry Pi, a low-cost radio, a GPS receiver, a motion sensor and a barometer. It records real cell towers alongside GPS. A laptop turns that into a position with an error bound, and tells the operator when not to trust it.

Fallback: the script no longer says the laptop "fuses everything": today the default filter rejects nearly every tower reading (slide 5). "Error bound" means a bound under our model (slide 6).

**If asked:** Q4 (where towers are), Q10 (legal), Q21 (who else does this).

## 3. Live demo

**Headline:** In simulation: GPS lost, red within 5 s; a 300 m jump without the guard ends green and wrong; with the guard it stays red and recovers when the spoof ends.

**On the slide:** the live panel. Run `deploy/demo/demo.sh stage` from the guard demo runbook (`deploy/demo/RUNBOOK.md` in PR #220 (merged); pre-flight first). Press Enter when T+ passes 105, then 188, then 212 (stops). The stage run takes 73 to 76 s.

**Figure:** the live panel. If the laptop fails: the nine screenshots in the guard demo evidence folder, with the runbook's 60-second screenshot path.

**Script (157 words, 80 s)**, cued by the panel's T+ clock and segment, as in the runbook:
> *[Segment 1, T+0, green]* A simulated drone flying a loop over Carleton. The triangles are the real Rogers tower sites from the government registry. Green means: trust this position. *[T+62, amber]* GPS is gone. *[T+65, red]* Within five seconds the panel turns red: do not navigate on this position. *[T+65–105]* The error grows, but the bound, the blue line, stays above it on this run. *[Enter; NO DATA gap]* Now a spoofer: fake GPS that puts us three hundred metres east. *[Segment 2, T+150, amber]* Caught at the very first fake fix: GPS rejected. *[T+177, green]* But watch. Half a minute later this plain filter lets the fake GPS back in: green, a tight bound, and that far wrong. *[Enter; NO DATA gap; point at `ekf-guard` on the top bar]* Same flight, same attack, now with our jump guard. *[Segment 3, T+150]* Caught again. *[T+155–200, red]* This time the fake GPS stays out. The error grows, but the bound grows faster and the panel stays red. The panel never goes green on the fake position. *[T+200, green]* The spoofer stops, real GPS comes straight back, and we are green and within a few metres.

"Within a few metres": after GPS returns the error is 1.7 m at T+200.0, then 0.1 to 3.6 m to T+220, median 1.5 m (seed 0, `challenge-drone-gps-return`, `ekf-guard`; guard demo runbook in PR #220 at `7783e5f`, measured headlessly there, not re-run by us). If Enter comes too early in segment 2, carry on and show `jump-3-followed.png` afterwards (runbook *Fallbacks*). The guard is opt-in, not our default: say so if asked.

Optional segment 1b, the towers helping (draft #272; only if it is merged and rehearsed; adds about 23 s, 278 s in all). After the first Enter, before the spoofer:
> *[Enter; NO DATA gap; point at the banner]* Same GPS loss, now a simulation study: one radio hopping thirteen carriers, and a filter that learns each tower's noise. Our payload cannot hop yet. *[Segment 1b, T+80–105, red]* The error stays in the tens of metres, against hundreds before. Still red: the bound is above the fifty-metre limit.

45 words. On the panel at T+80 and T+100 (seed 0): error 29 and 53 m with HPL 80 and 137 m, against 106 and 321 m with HPL 311 and 829 m on today's setup. Without it, the script below runs as written.

**If asked:** one seed is not a statistic (Q9 has the 50-run numbers; the guard still has hazardous epochs on 3 of 50 seeds); Q16 (did towers contribute); Q19 (GPS returning after an outage).

## 4. Real signals

**Headline:** On real towers our low-cost radio is precise on strong cells, but a slower error it does not report sits on top; on four real static sessions with GPS removed, the towers still made position worse, by hundreds of metres to kilometres; nothing is measured on the move yet.

**On the slide:**
- Range jitter on the strongest cells: 0.73 m (real, 10 records a second). A slower error, median 8.1 m at 1 s, that the radio's own estimate leaves out.
- Four real static sessions, GPS removed in software: with towers, hundreds of metres to kilometres worse than without. Median at 300 s for the default filter: 595 m, 364 m and 4,689 m, against about 1 to 2 m; on the fourth, 255 m at 120 s against 1.6 m.
- Nothing measured on the move yet.

**Figure:** [`analysis/results/lte-measured-noise/white_vs_snr.png`](../analysis/results/lte-measured-noise/white_vs_snr.png) (real).

**Script (56 words, 27 s):**
> This part is real. On strong cells our radio's range jitter is seven-tenths of a metre, but a slower error of about eight metres sits on top, unreported. On four real sessions with GPS removed in software, standing still, towers made position hundreds of metres to kilometres worse. And nothing is measured on the move yet.

Source: ADR-0036 on `main` (numbers regenerated after #245: white σ 0.73 m at 13–16 dB; S(1 s) median 8.1 m). GPS cut: #267 (merged; ADR-0050, Accepted), the other owner's result, not re-run by us ([`real-lte-filter/NOTES.md`](../analysis/results/real-lte-filter/NOTES.md), run at `7f5e484` (the commit `summary.json` names, on #267's branch; the files are on `main` at `aac7bd4`)): the default `ekf`, which now tells a real capture's LTE records the measured σ and gives each new arc a bias, median (worst) at 300 s over five cut times 595 m (1,536 m) on `20261111-0151` and 364 m (1,582 m) on `20261111-0233` with LTE, against 0.6 m and 1.3 m without; HPL at or above the error on 76 % and 75 % of the withheld fixes. Before ADR-0050 the same sessions gave 21,553 m and 10,718 m. "No variant beats no LTE on a static receiver, and the HPL still misses a quarter of the fixes" (NOTES). The five cuts share one recording per session, and a static receiver favours no LTE by construction. If asked for the number, give it with those caveats. Third and fourth sessions: draft PR #283 (`analysis/results/real-replay-256/summary.md`): `20261111-0040-static-fullsuite`, default `ekf` 4,689 m (worst 5,193) at 300 s against 1.7 m with no LTE; `20261111-1937-static-fullsuite3` (recorded 2026-11-12 UTC, #282), 255 m (worst 1,246) at 120 s against 1.6 m; five cuts of one recording each, re-run by QA (0 of 1,479 fields differ on the first).

**If asked:** Q2 (is any of it real), Q5 (8-bit radio), Q17 (multipath or oscillator), Q15 (what the sim got wrong), Q20 (why believe 132 m).

## 5. Where we miss, and what closes the gap

**Headline:** In simulation, against our own targets: jumps and clock drift are caught with no false alarms; accuracy without GPS is not there, because the radio under-reports its noise; honest noise and more frequencies bring it to 132 m, short of both targets.

**On the slide:** "Our targets; simulation." Three cards beside the ladder.

| Works | Does not yet | What closes the gap |
| --- | --- | --- |
| GPS jumps and a drifting GPS clock caught within seconds; no false alarms on clean runs | Accuracy without GPS: no simulated flight meets 25 m or the mentors' 50 m fallback; the slow GPS drag is missed by the default filter | Learn each tower's noise (#156, opt-in); hop across 13 carriers (study leg: the payload cannot hop yet) |

Ladder, worst second of the per-second 95th percentile across 50 runs, 0–300 s after GPS loss, `ekf`: no towers 2,909 m; today 12,507 m; + learned noise 2,474 m; + more frequencies only 11,894 m; both 132 m; dashed line at 25 m.

**Figure:** the stacked-fixes ladder, `analysis/results/stacked-fixes/ladder.png` in draft PR #247 (sim, `challenge-drone-outage` and `challenge-drone-hop-outage`, seeds 0–49, commit 35d061c).

**Script (95 words, 45 s):**
> In simulation, against our own targets. Detection works: GPS jumps and a drifting GPS clock are caught within seconds, with no false alarms. Accuracy without GPS does not yet. The radio claims two metres of noise when the truth is tens, so the filter over-trusts the towers and does worse than with none. Learn each tower's real noise and hop across thirteen carriers, which our payload cannot do yet, and ninety-five percent of fifty simulated flights are within a hundred and thirty-two metres at every second of the first five minutes. Our target is twenty-five.

Fallback: #247 is a draft on unmerged branches; if a judge asks, say so. The statistic is the agreed one (ADR-0034, *Amendment*): at each second of 0–300 s after GPS loss, the 95th percentile across the 50 runs; 132 m is the worst of those seconds, at second 88. Told the true noise the same setup reaches 111 m; with LTE noise measured from our captures 105 m; with modelled arc restarts 151 m (#262, draft). The slow drag: 1 of 50 on the leg as flown, 50 of 50 with 13 carriers hopped and #263's rule, median 127 s (Q7).

**If asked:** Q1 (why we miss), Q16 (over-trust or reject), Q20 (why believe 132 m), Q7 (slow drag), Q8 (false alarms).

## 6. Every source can lie

**Headline:** Every source can lie, GPS and the towers alike; towers may contradict GPS time but never confirm it; on a real recording every faked sky was caught; and on two real sessions the default filter's bound was wrong a third of the time while our opt-in honest-bound filter's never was, though it is kilometres wide.

**On the slide:**

| Source | How it can lie |
| --- | --- |
| GPS | Jump, slow drag, fake time, fake sky |
| Cell towers | Clock jump, wrong registry entry, fake tower |
| Aircraft reports | Someone else's GPS |

- Towers take their time from GPS: they may contradict it, never confirm it.
- Real recording, GPS sky faked in software: 59 of 59 fake sky reports flagged, no false alarm on 120 real ones.
- The bound, on two real static sessions with GPS removed: the default filter's was below the error on 34 % of 3,005 withheld fixes; our opt-in honest-bound filter's on none. Its bound is kilometres wide: honest, not yet usable (draft PRs #251, #283). In simulation: 45.3 % against 0.45 %.

**Figure:** [`analysis/results/gnss-health-20261111-fullsuite/gnss_health.png`](../analysis/results/gnss-health-20261111-fullsuite/gnss_health.png) (real GPS signal power from our payload, one of the cues the sky check reads). The sky check's own figure, for questions: [`spoof-decision-real-sky.png`](../analysis/pr-evidence/shrikar-feat-206-spoof-decision/spoof-decision-real-sky.png).

**Script (74 words, 35 s):**
> Our design rule: every source can lie, GPS and towers alike. Towers take their time from GPS, so by design they may contradict GPS time, never confirm it. On a real recording we faked the GPS sky in software: all fifty-nine fakes were flagged, with no false alarm. And the bound: on two real sessions the default filter's was wrong a third of the time; our honest-bound filter's never, though it is kilometres wide.

Source: sky-map decision, #239 (merged, #250; ADR-0041 Accepted), [`summary.md`](../analysis/pr-evidence/shrikar-feat-206-spoof-decision/summary.md): real session `20261111-0040-static-fullsuite`, fake sky from 300 s, 59 of 59 faked skyviews flagged (suspect or spoofed) for each of three fake skies; 0 false alarms in 120 real skyviews. Bound on real data: draft PR #283, sessions `20261111-0040-static-fullsuite` and `20261111-1937-static-fullsuite3`, five GPS cuts each: default `ekf` above HPL on 622 of 1,505 and 403 of 1,500 withheld fixes (1,025 of 3,005, 34 %), `ekf-honest` on 0 of 3,005; its HPL is 3.2 km at 120 s and 9.4 km at 300 s on the first session; no row beats no LTE. Bound: #251 (draft, verdict Not ready), `challenge-drone-outage`, 1 carrier, seeds 0–199: 45.33 % of epochs above HPL from GPS loss for `ekf`, 0.45 % for the opt-in `ekf-honest`; single runs still escape (worst 18.5 %); the 2 m/s ramp escapes every filter (99.3 %). The tower-time rule is our design (ADR-0024); the refutation of GPS time by tower time is planned, not built (Q11).

**If asked:** Q6 (the 5.33 bound), Q11 (what is new), Q7 (slow drag), Q8 (false alarms), Q24 (detect but not mitigate).

## 7. Roadmap

**Headline:** The product is a receive-only GPS trust monitor that warns the autopilot; we found none on sale that checks GPS against cell towers, and no vendor publishing false alarms per flight hour.

**On the slide:**
- **Product:** a receive-only GPS trust monitor. It checks GPS against cell towers and warns the autopilot. Today it flags on a ground laptop; the output to the autopilot is not built.
- **Gap (our market search, 2026-11-11):** we found no spoof detector on sale that cross-checks GPS against cell towers, and no vendor publishing false alarms per flight hour.
- **First buyers (proposed; none approached):** Canadian operators flying beyond line of sight, drone-show operators, a defence test slot.
- **Proof it needs:** detection rate and delay on recorded spoofing; false alarms per hour over clean flight hours; one live-jamming event at an authorised event.
- **Cost:** radios and antennas under CAD 170; the full payload is not yet priced, weighed or power-measured.
- Milestones, each ending in evidence: [`roadmap.md`](roadmap.md).

**Figure:** the error-against-masts-heard figure of the carrier hopping study ([`analysis/results/hopping-study/error_vs_masts.png`](../analysis/results/hopping-study/error_vs_masts.png), #179 merged via #250; simulation).

**Script (55 words, 26 s):**
> The product we found nobody selling: a receive-only monitor that checks GPS against cell towers, warns the autopilot, and publishes false alarms per flight hour. First buyers: beyond-line-of-sight operators, drone shows, defence trials. Unproven: recorded spoofing, clean flight hours, authorised live jamming. Radios and antennas: under a hundred and seventy dollars; payload unpriced. Thank you.

Fallback: "beyond-line-of-sight" counts as one word here and is four when spoken: counted that way the script is 58 words, 28 s, and the talk 253 s. "Found nobody selling" is the result of a search, not proof that none exists: if pressed, say "we found none". Say nothing about Honeywell's products on stage.

Source: `reports/sources-research-20261111.md` on `main` (#271), research by another session, not a decision. Gap: section 10.1 (*checked*: no funded company found selling cellular opportunistic navigation for drones; receivers with built-in spoof flags publish no false-alarm rates), 10.2 and 17.10 (the report's summary of that search, no evidence label of their own). Product, buyers and proof: section 10.5, the report's own ranking, a proposal; product direction is an owners' decision (#279, item 4; #273). Cost: [`hardware/bom.md`](../hardware/bom.md): radios and antennas CAD 169.54 as bought; Pi, GPS HAT, IMU and barometer supplied, price `TBD`; weight and current draw `TBD`.

**If asked:** Q21 (who else does this), Q18 (who buys, what altitude), Q8 (our own false alarms), Q13 (what next, in what order), Q14 (standards), Q23 (patents), Q24 (detect but not mitigate), Q22 (why not satellites), Q3 (a regional jam).

---

*Status: 2026-11-11, seven slides (#268) against `main` at `2499f87`; numbers from `main` and the named PRs; demo cues from PR #220 (merged). Slide 7 rewritten around the trust-monitor product (#273) from the research report on `main` at `3493cfb`. Rebased onto `3493cfb`: slide 3's last line follows the runbook at `7783e5f`, and slide 4 follows ADR-0050 (#267).*
