# The 5-minute deck

**The pitch in one line:** a navigation layer that knows when it is wrong, and tells the operator not to trust it.

Seven slides, 249 s, 512 words of script, 16 numbers spoken. Seconds are the words at 2.1 a second, except the demo, which the panel's clock sets at 80 s. Each slide gives the headline, what is on it, the figure, the word-for-word script and where to look if asked. Answers to questions: [`judge-questions.md`](judge-questions.md). Every number and its source: [`results.md`](results.md) (*Numbers the deck speaks or shows*).

**Three rules on stage.** Say "simulated" whenever a number is simulated. Say "consistent with a registered site", never "identified". Never say "first": say "we found no published…".

| # | Slide | Seconds | Words | Numbers spoken |
| --- | --- | --- | --- | --- |
| 1 | The moment: green and 300 m wrong | 21 | 44 | 1 |
| 2 | What we built | 21 | 45 | 0 |
| 3 | Live demo | 80 | 156 | 4 |
| 4 | Real signals | 26 | 54 | 2 |
| 5 | Where we miss, and what closes the gap | 45 | 95 | 7 |
| 6 | Every source can lie | 32 | 67 | 1 |
| 7 | Roadmap | 24 | 51 | 1 |
| | **Total** | **249** | **512** | **16** |

Numbers spoken: three hundred metres (1); five seconds, three hundred metres, half a minute, within a metre (3); seven-tenths of a metre, eight metres (4); two metres, thirteen carriers, ninety-five percent, fifty, a hundred and thirty-two metres, five minutes, twenty-five (5); fifty-nine (6); a hundred and seventy dollars (7).

---

## 1. The moment

**Headline:** The real danger is not losing GPS: it is a display that is green and confident while the aircraft is 300 m off.

**On the slide:** one screenshot, green NOMINAL with a 7 m bound and a 300 m true error (simulation). One line under it: "A navigation layer that knows when it is wrong."

**Figure:** `jump-3-followed.png` in the guard demo evidence (`analysis/pr-evidence/elshoubky-docs-28-demo-guard/`, PR #220 (open)); until it merges, [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/jump-3-followed.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/jump-3-followed.png) shows the same moment.

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

**If asked:** Q4 (where towers are), Q10 (legal).

## 3. Live demo

**Headline:** In simulation: GPS lost, red within 5 s; a 300 m jump without the guard ends green and wrong; with the guard it stays red and recovers when the spoof ends.

**On the slide:** the live panel. Run `deploy/demo/demo.sh stage` from the guard demo runbook (`deploy/demo/RUNBOOK.md` in PR #220 (open); pre-flight first). Press Enter when T+ passes 105, then 188, then 212 (stops). The stage run takes 73 to 76 s.

**Figure:** the live panel. If the laptop fails: the nine screenshots in the guard demo evidence folder, with the runbook's 60-second screenshot path.

**Script (156 words, 80 s)**, cued by the panel's T+ clock and segment, as in the runbook:
> *[Segment 1, T+0, green]* A simulated drone flying a loop over Carleton. The triangles are the real Rogers tower sites from the government registry. Green means: trust this position. *[T+62, amber]* GPS is gone. *[T+65, red]* Within five seconds the panel turns red: do not navigate on this position. *[T+65–105]* The error grows, but the bound, the blue line, stays above it on this run. *[Enter; NO DATA gap]* Now a spoofer: fake GPS that puts us three hundred metres east. *[Segment 2, T+150, amber]* Caught at the very first fake fix: GPS rejected. *[T+177, green]* But watch. Half a minute later this plain filter lets the fake GPS back in: green, a tight bound, and that far wrong. *[Enter; NO DATA gap; point at `ekf-guard` on the top bar]* Same flight, same attack, now with our jump guard. *[Segment 3, T+150]* Caught again. *[T+155–200, red]* This time the fake GPS stays out. The error grows, but the bound grows faster and the panel stays red. The panel never goes green on the fake position. *[T+200, green]* The spoofer stops, real GPS comes straight back, and we are green and within a metre.

If Enter comes too early in segment 2, carry on and show `jump-3-followed.png` afterwards (runbook *Fallbacks*). The guard is opt-in, not our default: say so if asked.

Room for one more segment: a demo of the towers helping (learned noise and hopping, sim study) may be added (#266). No script here. It would add about 25 s: 274 s in all at this pace, inside #268's 4 min 45 s.

**If asked:** one seed is not a statistic (Q9 has the 50-run numbers; the guard still has hazardous epochs on 3 of 50 seeds); Q16 (did towers contribute); Q19 (GPS returning after an outage).

## 4. Real signals

**Headline:** On real towers our low-cost radio is precise on strong cells, but a slower error it does not report sits on top; on real static sessions with GPS removed, the towers made position worse; nothing is measured on the move yet.

**On the slide:**
- Range jitter on the strongest cells: 0.73 m (real, 10 records a second). A slower error, median 8.1 m at 1 s, that the radio's own estimate leaves out.
- Two real static sessions, GPS removed in software: with towers, kilometres worse than without (median at 300 s 21,553 m and 10,718 m, against 0.6 m and 1.3 m).
- Nothing measured on the move yet.

**Figure:** [`analysis/results/lte-measured-noise/white_vs_snr.png`](../analysis/results/lte-measured-noise/white_vs_snr.png) (real).

**Script (54 words, 26 s):**
> This part is real. On strong cells our radio's range jitter is seven-tenths of a metre, but a slower error of about eight metres sits on top, unreported. On two real sessions with GPS removed in software, standing still, the towers made position worse, by kilometres. And nothing is measured on the move yet.

Source: ADR-0036 on `main` (numbers regenerated after #245: white σ 0.73 m at 13–16 dB; S(1 s) median 8.1 m). GPS cut: #245's rerun of #233, not re-run by us ([`lte-reacq-steps/NOTES.md`](../analysis/results/lte-reacq-steps/NOTES.md) *GPS cut*): `ekf` median at 300 s 21,553 m (`20261111-0151`) and 10,718 m (`20261111-0233`) with LTE against 0.6 m and 1.3 m without. #245 fixed most of the front end's arc steps; the filter still trusts records told 1 to 5 m that are off by tens of metres. Both predate ADR-0047's default (not rerun). If asked for the number, give it with that caveat.

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

**Headline:** Every source can lie, GPS and the towers alike; towers may contradict GPS time but never confirm it; on a real recording every faked sky was caught; and our bound holds only under our model.

**On the slide:**

| Source | How it can lie |
| --- | --- |
| GPS | Jump, slow drag, fake time, fake sky |
| Cell towers | Clock jump, wrong registry entry, fake tower |
| Aircraft reports | Someone else's GPS |

- Towers take their time from GPS: they may contradict it, never confirm it.
- Real recording, GPS sky faked in software: 59 of 59 fake sky reports flagged, no false alarm on 120 real ones.
- In simulation the error still escapes the bound after GPS loss: 45.3 % of the time, 0.45 % with a proposed fix (draft PR #251).

**Figure:** [`analysis/pr-evidence/shrikar-feat-206-spoof-decision/spoof-decision-real-sky.png`](../analysis/pr-evidence/shrikar-feat-206-spoof-decision/spoof-decision-real-sky.png) (real session, fake sky injected in software).

**Script (67 words, 32 s):**
> Our design rule: every source can lie, GPS and towers alike. Towers take their time from GPS, so by design they may contradict GPS time, never confirm it. On a real recording we faked the GPS sky in software: all fifty-nine fakes were flagged, with no false alarm. And our bound holds only under our model: in simulation the error still escapes it, and we report that.

Source: sky-map decision, #239 (merged, #250; ADR-0041 Accepted), [`summary.md`](../analysis/pr-evidence/shrikar-feat-206-spoof-decision/summary.md): real session `20261111-0040-static-fullsuite`, fake sky from 300 s, 59 of 59 faked skyviews flagged (suspect or spoofed) for each of three fake skies; 0 false alarms in 120 real skyviews. Bound: #251 (draft, verdict Not ready), `challenge-drone-outage`, 1 carrier, seeds 0–199: 45.33 % of epochs above HPL from GPS loss for `ekf`, 0.45 % for the opt-in `ekf-honest`; single runs still escape (worst 18.5 %); the 2 m/s ramp escapes every filter (99.3 %). The tower-time rule is our design (ADR-0024); the refutation of GPS time by tower time is planned, not built (Q11).

**If asked:** Q6 (the 5.33 bound), Q11 (what is new), Q7 (slow drag), Q8 (false alarms).

## 7. Roadmap

**Headline:** A first user, radios and antennas under CAD 170, and three milestones that each end in evidence.

**On the slide:**
- First user: an operator of inspection or delivery drones on an urban corridor over Ottawa, below 120 m.
- Radios and antennas: under CAD 170; the full payload is not yet priced, weighed or power-measured.
- Milestones: flights with independent truth → fault statistics from many hours of data → a multi-frequency receiver with a first operator. Details: [`roadmap.md`](roadmap.md).

**Figure:** the error-against-masts-heard figure of the carrier hopping study ([`analysis/results/hopping-study/error_vs_masts.png`](../analysis/results/hopping-study/error_vs_masts.png), #179 merged via #250; simulation).

**Script (51 words, 24 s):**
> Our first user: an operator of inspection or delivery drones over a city. The radios and antennas cost under a hundred and seventy dollars; the full payload is not yet priced or weighed. Next: flights with independent truth, fault statistics from many hours of data, then a multi-frequency receiver. Thank you.

Source: [`hardware/bom.md`](../hardware/bom.md): radios and antennas CAD 169.54 as bought; Pi, GPS HAT, IMU and barometer supplied, price `TBD`; weight and current draw `TBD`.

**If asked:** Q13 (a month), Q14 (certification), Q18 (who buys, what altitude), Q3 (a regional jam).

---

*Status: 2026-11-11, seven slides (#268) against `main` at `2499f87`; numbers from `main` and the named PRs; demo cues from PR #220 (open).*
