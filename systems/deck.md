# The 5-minute deck

**The pitch in one line:** a navigation layer that knows when it is wrong, and tells the operator not to trust it.

Nine slides, 285 s, 612 words of script, 11 numbers spoken. Each slide gives the headline, what is on it, the figure, the word-for-word script and where to look if asked. Answers to questions: [`judge-questions.md`](judge-questions.md). Every number and its source: [`results.md`](results.md).

**Three rules on stage.** Say "simulated" whenever a number is simulated. Say "consistent with a registered site", never "identified". Never say "first": say "we found no published…".

| # | Slide | Seconds | Words | Numbers spoken |
| --- | --- | --- | --- | --- |
| 1 | The moment: green and 300 m wrong | 25 | 60 | 1 |
| 2 | What we built | 25 | 60 | 0 |
| 3 | Live demo | 80 | 155 | 4 |
| 4 | Real signals | 25 | 51 | 1 |
| 5 | The scoreboard | 30 | 63 | 2 |
| 6 | Why, and what the fixes buy | 30 | 65 | 3 |
| 7 | Every source can lie | 30 | 68 | 2 |
| 8 | Limits | 25 | 50 | 0 |
| 9 | Roadmap | 25 | 57 | 2 |
| | **Total** | **295** | **629** | **15** |

Numbers spoken: three hundred metres (1); five seconds, three hundred metres, half a minute, within a metre (3); six-tenths of a metre (4); fifty-metre, none of fifty (5); ninety-five percent of fifty, a hundred and thirty metres, five minutes (6); forty-five percent, one percent (7); a hundred and twenty metres, a hundred and seventy dollars (9).

---

## 1. The moment

**Headline:** The real danger is not losing GPS: it is a display that is green and confident while the aircraft is 300 m off.

**On the slide:** one screenshot, green NOMINAL with a 7 m bound and a 300 m true error (simulation). One line under it: "A navigation layer that knows when it is wrong."

**Figure:** `jump-3-followed.png` in the guard demo evidence (`analysis/pr-evidence/elshoubky-docs-28-demo-guard/`, draft PR #220); until it merges, [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/jump-3-followed.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/jump-3-followed.png) shows the same moment.

**Script (60 words, 25 s):**
> Picture a drone whose navigation display is green, with a tight error bound, while it is three hundred metres off course. That is worse than losing GPS: nobody knows to stop. A spoofer only has to wait for the filter to take the fake GPS back. We built a navigation layer that knows when it is wrong, and says so.

**If asked:** Q9 (why refuse GPS after a jump).

## 2. What we built

**Headline:** A receive-only payload on real cell towers, and a laptop that tells the operator when not to trust the position.

**On the slide:**
- Payload: Raspberry Pi 4B, low-cost software radio, GPS receiver with timing pulse, motion sensor, barometer. Never transmits.
- Laptop: tower sync signals matched to the public ISED registry, fused into a position with a bound under our model; green, amber, red.
- Every number labelled simulated or real.

**Figure:** [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-1-clean.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/outage-1-clean.png) (panel, simulation, real tower sites on the map).

**Script (60 words, 25 s):**
> A receive-only payload: a Raspberry Pi, a low-cost radio, a GPS receiver, a motion sensor and a barometer. It never transmits. It listens to real cell towers, matches each one to the public Canadian registry, and a laptop fuses everything into a position with a bound under our model. Every number we show says whether it is simulated or real.

**If asked:** Q4 (where towers are), Q10 (legal).

## 3. Live demo

**Headline:** In simulation: GPS lost, red within 5 s; a 300 m jump without the guard ends green and wrong; with the guard it stays red and recovers when the spoof ends.

**On the slide:** the live panel. Run `deploy/demo/demo.sh stage` from the guard demo runbook (`deploy/demo/RUNBOOK.md` in draft PR #220; pre-flight first). Press Enter when T+ passes 105, then 188, then 212 (stops). The stage run takes 73 to 76 s.

**Figure:** the live panel. If the laptop fails: the nine screenshots in the guard demo evidence folder, with the runbook's 60-second screenshot path.

**Script (155 words, 80 s)**, cued by the panel's T+ clock and segment, as in the runbook:
> *[Segment 1, T+0, green]* A simulated drone flying a loop over Carleton. The triangles are the real Rogers tower sites from the government registry. Green means: trust this position. *[T+62, amber]* GPS is gone. *[T+65, red]* Within five seconds the panel turns red: do not navigate on this position. *[T+65–105]* The error grows, but the bound, the blue line, stays above it on this run. *[Enter; NO DATA gap]* Now a spoofer: fake GPS that puts us three hundred metres east. *[Segment 2, T+150, amber]* Caught at the very first fake fix: GPS rejected. *[T+177, green]* But watch. Half a minute later this plain filter lets the fake GPS back in: green, a tight bound, and that far wrong. *[Enter; NO DATA gap; point at `ekf-guard` on the top bar]* Same flight, same attack, now with our jump guard. *[Segment 3, T+150]* Caught again. *[T+155–200, red]* This time the fake GPS stays out. The error grows, but the bound grows faster and the panel stays red. Nobody is told a wrong position is safe. *[T+200, green]* The spoofer stops, real GPS comes straight back, and we are green and within a metre.

If Enter comes too early in segment 2, carry on and show `jump-3-followed.png` afterwards (runbook *Fallbacks*). The guard is opt-in, not our default: say so if asked.

**If asked:** one seed is not a statistic (Q9 has the 50-run numbers); Q16 (did towers contribute).

## 4. Real signals

**Headline:** On real towers our low-cost radio is precise on strong cells, but a slower error it does not report sits on top, and we have no real position yet.

**On the slide:**
- Range noise on the strongest cells: 0.63 m (real, 10 records a second).
- A slower error the radio's own estimate leaves out.
- No GPS fix in those captures: no real position yet.

**Figure:** [`analysis/results/lte-measured-noise/white_vs_snr.png`](../analysis/results/lte-measured-noise/white_vs_snr.png) (real).

**Script (51 words, 25 s):**
> This part is real. On real towers, our low-cost radio measures range with six-tenths of a metre of noise on strong cells. But a slower error sits on top, and the radio's own estimate leaves it out. Those captures had no GPS fix, so they cannot show a real position yet.

**If asked:** Q2 (is any of it real), Q5 (8-bit radio), Q17 (multipath or oscillator), Q15 (what the sim got wrong).

## 5. The scoreboard

**Headline:** Against our own targets, in simulation: spoof and clock-drift detection work with no false alarms; accuracy without GPS and the slow drag do not.

**On the slide:** "Our targets; simulation."

| Works | Does not work yet |
| --- | --- |
| GPS jumps and a drifting GPS clock caught within seconds | Accuracy without GPS: no simulated flight meets 25 m, or the mentors' 50 m fallback |
| No false alarms on clean runs | A slow GPS drag: caught in 0 of 50 runs by the default filter |

**Figure:** none; the table is the slide.

**Script (63 words, 30 s):**
> The scoreboard, against our own targets, in simulation. What works: GPS jumps and a drifting GPS clock are caught within seconds, with no false alarms on clean runs. What does not: accuracy without GPS. No simulated flight meets our target or the mentors' fifty-metre fallback. And a slow drag of GPS, the realistic attack, our default filter catches in none of fifty runs.

Fallback: the numbers on the agreed statistic (best 10,154 m at 300 s, not met: `results.md` (b), from #170 merged via #250) do not change this slide, which quotes no accuracy value. If a judge asks for one, give the line in `results.md` (b) with its source.

**If asked:** Q1 (why we miss), Q7 (slow drag), Q8 (false alarms).

## 6. Why, and what the fixes buy

**Headline:** The radio under-reports its noise, so today the towers hurt more than they help; honest noise, more frequencies and refusing jumps are the fixes, and together they reach 132 m in simulation, short of both targets.

**On the slide:** the three fixes, and the ladder for 0–300 s (`ekf`): no towers 2,909 m; today 12,507 m; learned noise 2,474 m; more frequencies only 11,894 m; both 132 m; against the 25 m line.

**Figure:** the stacked-fixes ladder, `analysis/results/stacked-fixes/ladder.png` in draft PR #247 (sim, `challenge-drone-outage` and `challenge-drone-hop-outage`, seeds 0–49, commit 4faf994; 95th percentile across runs at each second, worst second).

**Script (65 words, 30 s):**
> Why? Our radio reports only its fast noise, so the filter over-trusts the towers; in simulation that is worse than no towers at all. The fixes: learn each tower's real noise, listen on more frequencies, and refuse a flagged jump. Together, ninety-five percent of fifty simulated flights stay within a hundred and thirty metres for five minutes, down from kilometres. Still short of our target.

Fallback: #247 is a draft on unmerged branches; if a judge asks, say so. Told the true noise the same setup reaches 111 m, so the rest of the gap is the assumed error sizes.

**If asked:** Q1, Q16.

## 7. Every source can lie

**Headline:** Every source can lie, GPS and the towers alike; towers may contradict GPS time but never confirm it, and our bound holds only under our model.

**On the slide:**
- GPS: jump, slow drag, fake time. Towers: clock jump, wrong registry entry, fake tower. Aircraft reports: someone else's GPS.
- Towers take their time from GPS: they may contradict it, never confirm it.
- The bound is under our model. Sim, `challenge-drone-outage`, 1 carrier, seeds 0–199 (draft PR #251): error above the bound in 45.3 % of epochs after GPS loss for `ekf`, 0.44 % for the opt-in `ekf-honest`; single runs still escape (worst 18.5 %); the 2 m/s ramp is undefended (99.3 %; draft PR #254: 0 of 50 detected with hopping).

**Figure:** [`analysis/results/gnss-health-20261111-fullsuite/gnss_health.png`](../analysis/results/gnss-health-20261111-fullsuite/gnss_health.png) (real GPS signal power, the baseline a jamming check uses).

**Script (68 words, 30 s):**
> Our design rule: every source can lie, GPS and towers alike. Towers take their time from GPS, so they may contradict GPS time, but never confirm it. And our bound is a bound under our model. In simulation, after GPS loss, the error escaped it forty-five percent of the time. An opt-in fix brings that under one percent, but a slow spoof still defeats every filter we have.

Fallback: the sky-map check is merged (#239 via #250, #206; ADR-0041 Accepted). Its figure, [`spoof-decision-real-sky.png`](../analysis/pr-evidence/shrikar-feat-206-spoof-decision/spoof-decision-real-sky.png), can be added here; nothing changes in the script.

**If asked:** Q6 (how the bound is computed), Q11 (what is new).

## 8. Limits

**Headline:** In the demo the towers carried almost nothing; on our one real session with GPS removed in software the towers made position worse; the noise model is measured standing still; attacks are simulated.

**On the slide:** the four limits as four lines.

**Figure:** [`analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/real-dash-today.png`](../analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/real-dash-today.png) (a real session on the panel: no data, no GPS origin).

**Script (50 words, 25 s):**
> Plainly, our limits. In the demo, the filter rejected nearly every tower reading. On our one real session with GPS removed in software, the towers made position worse, by kilometres: our front end restarts its tracking. Our noise model is measured standing still. Every attack is simulated; we never transmit.

Source: #233 (#214), merged via #250 and not re-run by us ([`real-gps-cut-20261111/summary.md`](../analysis/results/real-gps-cut-20261111/summary.md)): real static session, GPS removed in software, 6.6 to 12.4 km at 300 s with LTE against 0.6 m without; cause, the front end's arc steps. If asked for the number, give it with that caveat.

**If asked:** Q2, Q16.

## 9. Roadmap

**Headline:** A first user, a payload whose radios and antennas cost under CAD 170, and three milestones that each end in evidence.

**On the slide:**
- First user: an operator of inspection or delivery drones on an urban corridor over Ottawa, below 120 m.
- Payload: radios and antennas CAD 169.54 as bought; the rest supplied, price `TBD`; power 5 V from a supply rated ≥ 3 A, draw `TBD`.
- Milestones: flights with independent truth → fault statistics → a multi-frequency receiver with a first operator. Details: [`roadmap.md`](roadmap.md).

**Figure:** the error-against-masts-heard figure of the carrier hopping study ([`analysis/results/hopping-study/error_vs_masts.png`](../analysis/results/hopping-study/error_vs_masts.png), #179 merged via #250; simulation).

**Script (57 words, 25 s):**
> Our first user: an operator of inspection or delivery drones below a hundred and twenty metres over Ottawa. The radios and antennas we bought cost under a hundred and seventy dollars. Milestones: flights with independent truth; fault statistics from many hours of data; then a multi-frequency receiver, as the radio layer Honeywell's suite lists without a product.

**If asked:** Q13 (a month), Q14 (certification), Q18 (who buys, what altitude).

---

*Status: 2026-11-11, against `main` at `c21e047`; PR states and placeholders brought up to `8892fca`; demo cues from draft PR #220.*
