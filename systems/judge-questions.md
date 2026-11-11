# Judge questions

- **Use:** for the presenter of [`deck.md`](deck.md): the 24 hardest questions a navigation engineer is likely to ask. Each answer is at most 45 words and can be said as written. Numbers are simulation unless the answer says real; each source line names its PR or file, and [`results.md`](results.md) collects them.
- **If you don't know:** say "I don't have that number; it is in our results file" and move on. Never estimate a number on stage.
- **The research report** cited in Q10, Q13, Q14, Q18 and Q21 to Q23 is `reports/sources-research-20261111.md` on `main` (#271): research by another session, not decisions. Only claims it labels *checked*, *experiment* or *repo* are spoken; a vendor's own number is called a vendor figure.
- **Agreed statistic** (ADR-0034, *Amendment*): at each second after GPS loss, the 95th percentile of error across runs; the worst second of the window counts. "Worst second" below means this.

## 1. Your own target is 25 m for five minutes. Why do you miss it?

> Mostly the noise our radio reports: only the fast part, so the filter over-trusts towers, worse than none in simulation. Learning each tower's noise, on a study leg hopping thirteen frequencies, brings the worst second to a hundred and thirty-two metres. Still far from 25.

- **Source:** agreed statistic, sim, `challenge` drone leg, seeds 0–49, `ekf`, 0–300 s: #247 (open, draft; results re-cited at `31aaca1`): no LTE 2,909 m; today (1 carrier, told 2 m) 12,507 m; learned noise 2,474 m; learned noise + 13 carriers 132 m; ceiling told the true noise 111 m. #262 (open, draft, `7e80092`): LTE white noise measured from our static captures 105 m; multipath as small as measured at rest 51 m; front-end arc restarts added 151 m. Learned noise: #156 (open, opt-in), ADR-0039 (proposed in #156, not on `main`). Thirteen carriers is a study leg: the payload cannot hop (#179, merged, #250; ADR-0040 Proposed). Backup, what limits it now: multipath, measured only at rest (#262).
- **Do not claim:** that any row meets T1 or the 50 m fallback (closest 51 m against 50 m, only if a moving drone's multipath is as small as at rest and there are no arc restarts); that #156, #247 or #262 is merged or on by default; that the payload hops. Do not quote #156's per-run 4,034 → 982 m: per-run numbers do not score T1 ([`results.md`](results.md), *Two T1 statistics*).

## 2. Is any of it real?

> The payload, the radio captures and the tower matches are real. We measured range noise on fifteen real captures and recorded a GPS session with a timing pulse. Every accuracy and detection number is simulation. With GPS removed in two real sessions, towers worsened position.

- **Source:** [`results.md`](results.md) (a); ADR-0036; #211. Real error after GPS loss: #233 (merged, #250) rerun after #245's front-end fixes, [`lte-reacq-steps/NOTES.md`](../analysis/results/lte-reacq-steps/NOTES.md) *GPS cut*: `ekf` with LTE, median 21,553 m (`20261111-0151`) and 10,718 m (`20261111-0233`) at 300 s over 5 cut times each, against 0.6 and 1.3 m without LTE; before ADR-0047's default, not rerun. The other owner's result, not re-run by us. Same runs, opt-in `ekf-measured-sigma` (#240, merged, #250): 205 / 1,513 m, still worse than no LTE. Our learned-noise and honest-bound filters have not run on real data (#256, blocked on the sessions).
- **Do not claim:** a position from real towers, or any real accuracy, integrity or detection rate; that any LTE filter beats no LTE on real data. Quote #214's line labelled "real session, GPS removed in software".

## 3. In a regional jam your towers lose GPS timing too, and at altitude you are above their downtilted beams. What is left?

> Tower geometry survives; their clocks drift. We simulated every tower going into holdover mid-outage: our opt-in honest filter behaved as without it. A spoofer who also captures tower timing is outside our design. Altitude reception is unmeasured; then barometer and dead reckoning remain.

- **Source:** [`architecture.md`](architecture.md) *Where it stops* (a wide-area time spoof that also captures tower timing is not covered by design); ADR-0024 (towers are GNSS-timed). Sim, `challenge-drone-outage-tower-holdover` (every tower in OCXO holdover from 180 s, `TBC`), 1 carrier, seeds 0–199, #251 (open, draft, verdict Not ready): `ekf-honest` 0.45 % of epochs above HPL from the fault, worst run 18.0 %, 0 hazardous, against 0.45 % / 18.5 % on the plain outage; `ekf` 45.6 %. Altitude: [`roadmap.md`](roadmap.md) *Operating envelope* (downtilt not measured, not studied); real captures on the ground or 0.5 m up (#210).
- **Do not claim:** any real-tower result in a jam; that reception at altitude is fine; that tower-timing capture is detected; that `ekf-honest` is merged or the default.

## 4. How do you know where a tower is, and what if the table is wrong?

> From the ISED registry: the frequency and cell ID we decode map to one registered site, or we drop the cell. Locally, no row matched another site; ambiguous rows are dropped. In simulation, a fake tower on a real ID fooled one filter.

- **Source:** ADR-0023 (Proposed); registry audit of 4,059 rows, #133 (the count of dropped ambiguous rows is in no committed file: `TBD`); wrong-table simulation, #133 and #132 (`ekf-calibrated` 186.5 m, 5,147 hazardous epochs; `ekf-mhss` flags the site, HPL 5.4 km). Backup, table position error (sim, #262, open, draft): with 13 carriers and learned noise, 100 → 20 m of tower position error gives 107 m against 105 m: it barely matters.
- **Do not claim:** that a tower is "identified": say "consistent with a registered site". The dongle cannot decode the global cell ID (SIB1).

## 5. Can an 8-bit RTL-SDR range on LTE at all?

> For precision at rest, yes: 0.7 metres of noise on strong cells, 23 on weak ones, at ten records a second. But a slow error, typically 8 metres, sits on top, weak cells drop often, and without truth we measured no bias.

- **Source:** real, ADR-0036 and [`lte-measured-noise/`](../analysis/results/lte-measured-noise/summary.md) (at `8892fca`, after #245: white σ 0.73 m at 13–16 dB, 22.5 m at −14 to −11 dB on 43 records; correlated S(1 s) median 8.1 m). [`research.md`](research.md) §2: no published real-tower LTE TOA scatter from an RTL-SDR was found.
- **Do not claim:** an accuracy (no truth), or that it works while moving.

## 6. Your 5.33-sigma bound: 5.33 is a one-dimensional factor, and with what exposure time? How does 1e-7 square with 45 % escapes?

> 5.33 is the one-dimensional factor, applied to our largest horizontal deviation; a round error needs nearer 5.7. No exposure time is set. But the factor is not what failed: in simulation the filter's own uncertainty was wrong, so the error escaped 45 percent of epochs.

- **Source:** `integrity/protection.py` (`K_H` 5.33, "a common choice for a ~1e-7 integrity risk under Gaussian errors", `TBC`); `integrity/mhss.py` (`phmi` 1e-7, priors 1e-3 / 1e-4 / 1e-4 / 1e-3, all `TBC`); [`architecture.md`](architecture.md) *How the confidence number is computed*. Arithmetic, not a committed result: the two-sided Gaussian tail beyond 5.33 σ is 9.8e-8; for a circular horizontal error P(r > 5.33 σ) = exp(−5.33²/2) = 6.8e-7, and 1e-7 needs 5.68 σ. No exposure time is defined in REQ-02, ADR-0034 or [`verification.md`](verification.md) (`TBD`). The factor itself: issue #265 (open; options for the owners, no code change before a decision). Why the covariance, not K: #251 (open, draft) *Cause* (d): with the slow error as a state, mean NEES is near 2. The two numbers: 45.3 % = epochs after GPS loss with error above HPL, `ekf`, `challenge-drone-outage`, 1 carrier, seeds 0–199 (#251; #170's T5 figure gives 43.7 % over whole runs, #222); 7 of 50 = seeds with a hazardous epoch (error over the 50 m alert limit while HPL is under it), #170 (merged, #250), seeds 0–49; on #251's 200 seeds, 33 runs. Opt-in `ekf-honest`: 0.45 %, worst run 18.5 %, 0 hazardous; its settings are the sim's own truth; HPL is under the 50 m alert limit on only 9.8 % of epochs.
- **Do not claim:** that the bound always holds, a certified integrity risk, that 5.33 is the right horizontal factor, or an exposure time. Call it "a bound under our model". Where it held: through the demo's outage and guarded jump (seed 0); where it failed: the unguarded jump, and 7 of 50 seeds of the drone outage.

## 7. What happens when the spoofer is subtle, a slow ramp?

> Our default filter misses a 2 metre-per-second drag in simulation. An opt-in tower monitor catches 1 of 50 on our leg as flown, 48 if every nearby tower is heard, 50 on a study leg hopping thirteen frequencies: two minutes median, not 30 seconds.

- **Source:** #170 (merged, #250; 0 of 50). #180 (merged, #250; ADR-0037 Proposed): drone leg as committed (1 to 3 cells) 1 of 50; every tower within 3 km heard continuously (17 eNBs) 48 of 50, 131 s median, 313 s worst. #263 (open, ready for review; study leg, the payload cannot hop): 13 carriers 50 of 50, 127 s median, 276 s worst, 0 added false alarms in 100 runs; 6 carriers 2 of 50 and 1 added false alarm; 1 m/s 4 of 10; 0.5 m/s 0 of 10. The bound does not help either: 99.3 % of epochs above HPL on the ramp (#251, draft). Small jump then drift: at most 24 % (#176, merged, #250).
- **Do not claim:** that we catch slow spoofing within 30 s, on the leg as flown, or below 2 m/s; that the payload hops; that #263 is merged.

## 8. What about false alarms?

> In simulation, zero per hour on clean runs; the aircraft-based warning, 1.94 per hour. Real data showed another cost: our default filter refused honest GPS for over four of ten minutes, because the barometer drifted with temperature. A fix is in review.

- **Source:** #170 (0.0 /h on `nominal`, four estimators); #166 (ADR-0033 Proposed). Real, #241 (open, ready for review; ADR-0045 Proposed): one static 601 s session, honest GPS refused in 262 s (the PR's per-second log; 273 in the reviewer's per-epoch replay); the BMP180, told 0.3 m, read −3.4 to +77.5 m, correlation with its temperature −0.85; with the fix the GPS horizontal is used 600 of 601 s. Backup: the jump guard kept honest GPS out after 5 of 46 hard manoeuvres (ADR-0038 *Consequences*); #263's hop rule adds 0 false alarms in 100 runs at 13 carriers, 1 at 6. Real: the C/N0 jamming indicator stayed 0 over one 595 s session (#211); the sky-map check flagged 0 of 120 real skyviews (#239, merged, #250).
- **Do not claim:** a real-world false-alarm rate; that #241 is merged.

## 9. Why refuse GPS after a jump, rather than trust it again?

> Because a spoofer only has to wait. Once GPS is rejected, the filter's uncertainty grows until the same fake fix passes. The guard keeps GPS out until its own stream steps back. Honest GPS returns 0.1 seconds after the jump ends; meanwhile we dead-reckon.

- **Source:** ADR-0038 (Proposed), #191 (merged, opt-in); [`jump-refusal/summary.md`](../analysis/results/jump-refusal/summary.md). Cost: median error 1,263 m at +120 s after a refused jump on the drone leg, flagged unsafe; hazardous epochs on 3 of 50 seeds. Backup (#247, open, draft; study leg): held 300 m jump, 13 carriers, worst second over 0–300 s: guard alone 11,103 m; guard with learned noise 120 m, 0 hazardous, 0 of 50 on the spoofed position. After a long outage the guard does not judge returning GPS (Q19).
- **Do not claim:** that the guard is on by default, that it is free, or that it has no hazardous epochs.

## 10. Is this legal? You record cell signals.

> The payload never transmits. We decode only signals meant for everyone, sync signals and broadcast fields, never content. Whether taking timing from them counts as use under section 9(2) of the Radiocommunication Act has no ruling we found. We need a legal opinion before selling.

- **Source:** REQ-07, REQ-08, ADR-0001, ADR-0011, [`safety.md`](safety.md) *Legal* (our reading, not legal advice; mentor confirmation `TBD`); `tests/test_hard_rules.py`. Report (`reports/sources-research-20261111.md` on `main`) 10.4 and 17.8, *checked*: s.9(2) forbids intercepting and making use of a radiocommunication; s.9(3) exempts broadcasting; the regulations have no research or navigation exception; no case law or ISED guidance on using sync signals exists. Backup: Wi-Fi identifiers are hashed at capture (ADR-0011); attacks are software only.
- **Do not claim:** that a lawyer or regulator has approved it; that cell sync signals are "broadcasting" under s.9(3) (not decided anywhere we found); any legal conclusion.

## 11. What is new compared with Kassas and colleagues?

> Two things we found no published work doing: tagging every source by its GPS dependence, so towers may contradict GPS time but never confirm it; and a GPS fault hypothesis that includes the towers' borrowed time. And we measured the slow error our radio hides.

- **Source:** [ADR-0024](adr/0024-gnss-dependency-tags.md) (dependency tags); [`research.md`](research.md) *Novelty check* (P2, P5; Jia, Khalife & Kassas 2023 already group tower clocks and run solution separation); slow error, ADR-0036. IEEE Xplore and ION were not searched in full text.
- **Do not claim:** "first". Do not claim the tower-time refutation of GPS time is built: it is planned. Do not claim measuring the slow error is new: say we measured it.

## 12. What about timing?

> Second priority, as the mentors asked. In simulation the timing receiver stays within 1.5 microseconds after ten minutes on 49 of 50 runs, and a 50 nanosecond-per-second time drag is caught in a median of 3.3 seconds. Elsewhere our time bound is overconfident.

- **Source:** #170 (merged, #250; T3 missed on one seed at 1.55 µs; `ekf-calibrated`'s σ bound fails on 13 seeds); RUNBOOK (time PL calls time unsafe early). Elsewhere: since ADR-0047 (Accepted, cost accepted by the owners) the default `ekf` has 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets ([`pr-evidence/228/before-after.md`](../analysis/pr-evidence/228/before-after.md), `73c9e9b`). Real: PPS discipline on the Pi, 769 ns standard deviation (#216, merged; ASM-04).
- **Do not claim:** that T3 is met, that the time bound is honest on every set, or a real holdover number.

## 13. What would you build next, and why in that order? What would another month buy?

> In the order our research says limits us. First a filter honest about slowly varying errors, then heading at GPS loss, then a velocity source, then LTE carrier phase. Each ends in a measurement on real data. No durations, and no promise of 25 metres.

- **Source:** [`roadmap.md`](roadmap.md) *Milestones for accuracy after GPS loss*, M1 to M4; report 11.2 and 11.3 (order; item 1 seen in the *repo* and in its scratch *experiment*, section 5, placeholder models), 16.9, 17.10, 18.5 (order unchanged by later passes). The order is a proposal: the owners have not ruled (#279, item 3), and M3 waits on REQ-06 and REQ-07 (#279, items 1 and 2). If REQ-06 keeps radio primary, carrier phase moves ahead of the velocity source (report 11.3, 15 item 3). A month buys the start of M1 and M2: our noise-learning and honest-bound filters on real sessions (#256), a moving capture with independent truth (#259), honest GPS taken back after long outages (#246). Backup, carrier phase: 0.37 to 0.89 m on a drone in the literature (report 6.3, *checked*; line of sight, a GPS-disciplined receiver oscillator, the drone inside one sector); no published result without a disciplined receiver clock (16.9). Multipath limits the simulated stack (#262, draft: 51 m with at-rest multipath, 105 m without). Already done, not future: the fixes run together on the agreed statistic (#247, draft, #218) and the sky-map spoof decision (#239, merged, #250).
- **Do not claim:** a date or a target we expect to meet; that the order is decided; that carrier phase would give us sub-metre accuracy (that result had a disciplined clock we do not have); any number from the report's scratch experiment as ours.

## 14. What standard would this be certified against? What is the certification path?

> We found no standard for opportunistic navigation, or for protection levels on sources other than GPS; RTCA SC-159 covers GNSS equipment. The nearest framework is the US resilient-navigation one from DHS: four levels, and cross-checking sources belongs to its upper two. Route and regulator: undecided.

- **Source:** [`research.md`](research.md) §3 item 6; [`roadmap.md`](roadmap.md) *Certification*. Report 10.4, *checked*: the DHS resilient-PNT framework has four levels and its IEEE version is still a draft; no standard exists for opportunistic navigation or for protection levels on non-GPS sources. The mapping of our cross-checking onto the upper two levels is the report's reading; we have not assessed conformance. Backup: drones under a specific-operation risk assessment look shorter than crewed aircraft (`TBC`); first we need fault statistics from many hours of data.
- **Do not claim:** a certification plan agreed with anyone, a design assurance level, or conformance to any level of the DHS framework. Say "we found no standard", never "none exists": the report's supporting notes list a 2025 ASTM specification for drone navigation that nobody on the team has read.

## 15. What did the simulation get wrong, compared with the captures?

> The sim assumed 50 metres of white noise per second; at rest, real white noise is 0.7 to 23 metres, plus a slow 8-metre error. Records told the filter 2 metres. Real cells drop and reacquire often; the sim kept every track.

- **Source:** ADR-0036 (Proposed; the *Sim validity* row is not yet moved); `pnt compare` sim against real (#199: 49.2 m white against 21.3 m smooth); #183 (closed) and #245 (merged): front-end faults. Backup (#262, open, draft): putting the measured white noise into the sim moves the stacked result from 132 to 105 m; adding modelled arc restarts, 151 m.
- **Do not claim:** that the simulator is validated, or that the measured model is adopted.

## 16. Your panel says LTE is not in use, yet you say towers make position worse. Which is it?

> Both. Records claim 2 metres where the truth is tens, so almost every reading fails the filter's check. The few that pass are believed to 2 metres: each shrinks the filter's uncertainty while pulling position away. In simulation that is worse than no towers.

- **Source:** #251 (open, draft) *Cause* 1: "its gate rejects most LTE records and each one it accepts at 2 m collapses the covariance"; #241 *Not fixed* (sim: a few towers pull the state, the covariance stays tight, the gate never reopens); #147 (told 2 m 6,557 m, told the true 50 m 1,002 m, no LTE 2,513 m; per-run, seeds 0–9). Agreed statistic (#247, draft): no LTE 2,909 m, today 12,507 m. Count: #180 description (one seed, spoof leg: 5,374 of 5,383 tower readings rejected before the spoof). Panel: guard demo runbook (open PR #220: Sources lists `lte` under *Not in use*). Fixes: #156 (open, opt-in), ADR-0039 (proposed in #156, not on `main`); `ekf-measured-sigma` (#240, merged, #250, opt-in).
- **Do not claim:** that the demo's position after GPS loss came from towers; a percentage of epochs (none is committed); that the 9 of 5,383 is from the outage leg.

## 17. Is the 8 m slow error multipath, or your dongle's oscillator?

> Not the dongle, nor the tower clock. The slow error remains in differences between two sectors of one site on one frequency, where dongle and shared site clock cancel. That leaves multipath at a static antenna or our tracking loop; which, we have not determined.

- **Source:** real, ADR-0036 *Context* (same-eNB sector pairs, which share a clock, still show S(1 s) of 5.5 to 36 m, 5.5 to 18 m without the one pair whose cell sits on a carrier alias; "so it is not a clock"); [`lte-measured-noise/summary.md`](../analysis/results/lte-measured-noise/summary.md), *Pairs on one carrier (dongle cancels)*. In the sim, multipath is the size that matters (#262, draft).
- **Do not claim:** that it is multipath: the tracker's loop is not ruled out. A static capture cannot size multipath in motion.

## 18. Who buys this, and at what altitude does it work, given tower antenna downtilt?

> First buyers we would approach: Canadian operators flying beyond line of sight, drone-show operators, and a defence test slot. None has been approached. Altitude is an assumption: we recorded on the ground only, and how downtilted tower antennas affect reception at altitude is not measured.

- **Source:** report 10.5 (the report's own ranking of product shapes and first buyers: a proposal, no evidence label); demand, 10.3, *checked*: closed Canadian defence challenges on drone geolocation under GPS degradation and on timing; calls elsewhere on GPS-independent navigation for small drones. Use case: UC-01, [`use-cases.md`](use-cases.md) (inspection or delivery drone on an urban corridor below 120 m); [`roadmap.md`](roadmap.md) *Operating envelope*; real captures on the ground or 0.5 m up (#210). Simulated flights at 40 to 45 m.
- **Do not claim:** a buyer who has expressed interest, a price for the product, or a working altitude. Do not quote the report's "17 cells heard at 120 m": it is what a modem with interference cancellation reports, and the report's third pass says a single dongle hears fewer (18.4).

## 19. GPS comes back after a long outage, hundreds of metres from your estimate. Does the guard refuse it, and what stops a spoofer stepping back in?

> The guard never judges a fix returning after an outage; only the normal check does. If we have drifted far, that check can reject honest GPS for good: one simulated run reached 54 kilometres. A spoofer who jams first meets that check. Both are open.

- **Source:** `integrity/jump_guard.py` (latches only if GNSS was used within `gnss_timeout_s`, 2 s: "A fix returning after an outage never latches"; "A spoofer that first jams GNSS for longer than `gnss_timeout_s` is judged by the ordinary gate"); ADR-0038 (Proposed; a covariance-based re-admission was rejected because the covariance is not honest after a long coast). Issue #246 (open): `challenge-drone-outage` seed 2, `ekf`, `main` `c21e047`: GNSS refused for all 60 s after it returned, maximum error 54 km; how many seeds: `TBD`. While latched, GPS is re-admitted only when its own stream steps back by the jump; one that ramps while latched and then steps back gets in with the ramp's offset (stated limit).
- **Do not claim:** that honest GPS is always taken back; that the guard covers jam-then-spoof; a seed count for #246.

## 20. Why believe 132 m? Your real front end restarts cells, real data is kilometres worse, and the figure is the same at 120 s and 300 s.

> Not as a real number. It is simulation, on a study leg the payload cannot fly, and adding modelled track restarts makes it 150. It is flat because the worst second comes early, at 88 seconds. On real data, no tower filter beats none yet.

- **Source:** #247 (open, draft): learned noise + 13 carriers, worst second 132 m at s 88 in both windows, so no later second is worse. #262 (open, draft): arc restarts and steps added, 143 m (0–120 s) and 151 m (0–300 s, at s 177). Real: #240 and #245 (merged; nothing beats no LTE on two static sessions; #245 fixed most arc steps; the filter still trusts records told 1 to 5 m that are off by tens of metres); not reproduced on real data (#256). Backup (sim, #232, merged, #250, [`tower-count/summary.md`](../analysis/results/tower-count/summary.md)): with the committed and honest error models no tower count meets T1 or the fallback; with clean errors all 17 sites within 3 km meet T1.
- **Do not claim:** that 132 m is a real-world or flight number, that it meets any target, or that the payload hops.

## 21. Who else does this? Who is your nearest competitor?

> We found no company selling cell-tower navigation for drones; the work is in universities. The nearest product is a ten-gram receive-only board, a vendor figure, that takes position from Iridium satellites. Receivers with built-in spoof flags exist; we found no false-alarm rates published for them.

- **Source:** report 10.1, *checked* (vendor claims marked): no funded company found selling cellular or LEO opportunistic navigation for drones; a 10 g receive-only board on Iridium's positioning chip; receivers with built-in spoof flags publish no false-alarm rates. 17.3, *checked*: Iridium's paid service independently tested at 26.6 m horizontal, 95 %, over 100 days, static; the 10 g, 1.2 W board is from the vendor's datasheet; it needs a subscription and no price is published. 10.2 and 17.10 (the report's summary): no spoof detector on sale cross-checks against cell towers; that board is the nearest competitor. Research, not products: Kassas and colleagues (Q11). Backup, only if a judge raises it, worded as here: Honeywell's alternative-navigation framework has vision shipping, with magnetic and LEO modules slated for 2026, and the report found no published figure for it (report 10.1, *checked*; [`research.md`](research.md) §3).
- **Do not claim:** "nobody does this" or "first": say "we found none". Do not compare ourselves with any Honeywell product. Do not say the Iridium board is worse than ours: it is a product with an independently tested service, and ours has no real accuracy. Left out for weak evidence: that board "flagged spoofing within 1 s at a 2026 jamming test" (a vendor statement the supporting notes mark as a snippet).

## 22. Why cell towers and not satellites in low orbit?

> Iridium is a low-orbit signal our radio can hear. Published fixes from its open bursts are 100 to 200 metres, standing still, over minutes, and those bursts are unauthenticated. Its paid service already sells on a chip. Towers are where we found no product.

- **Source:** report 6.1, *checked*: Iridium only, published orbits, height aiding, minutes of observation, static: 198 m and 163 m (Tan et al.), about 132 m, and 130 to 140 m from a cold start; no Iridium-only drone result was found; the open bursts have no source authentication; a chip for the paid service has been on sale since 2026-07-14. Report 11.1 and 17.10 (its analysis: Doppler should not lead; on a free-running dongle crystal Doppler is kilometre-class). The report calls Iridium the only LEO signal our dongles reach (1, 11.1), but its own 6.1 lists Orbcomm at 137 MHz, so do not say "only". Ours: LEO is simulation only ([`results.md`](results.md) (e), #172, every value `TBC`), and the report says that layer has no orbit error, so its numbers are not credible (report 5, *experiment*).
- **Do not claim:** that satellites cannot work: with a disciplined clock and corrected orbits the literature reaches tens of metres on vehicles (report 17.10), and the paid Iridium service tested at 26.6 m (17.3, *checked*). Do not quote our simulated LEO numbers. Do not say towers are more accurate than satellites on real data: ours are not.

## 23. Are there patents in your way?

> Possibly. The University of California holds patents on navigating with LTE signals, running to about 2038, and on a low-orbit Doppler receiver. We have not assessed them and draw no legal conclusion. A freedom-to-operate check is needed before any product. Nothing here is for sale.

- **Source:** report 10.4 and 17.8: University of California patent families to about 2038 (LTE) and 2040 (LEO); "not legal advice; a freedom-to-operate check is needed before a product"; not a full landscape. Those two sections carry no evidence label; the supporting notes (`reports/research-round2/gnss-integrity-algorithms-market.md` on `main`, *Topic 12*) mark three of the patents, with their dates, as read at source, and say the expiry dates are the patent database's estimates and that Canadian counterparts were not checked.
- **Do not claim:** that we infringe or do not infringe; that the patents do or do not cover our filter; an expiry date as exact. Do not mention any other company's patents.

## 24. You detect and flag. You do not mitigate. Is that right?

> By default, yes: we flag, reject the bad GPS and coast. Our opt-in jump guard keeps a detected fake out until GPS steps back. In simulation, on a study leg, towers with learned noise held a refused jump to 120 metres. Not flown.

- **Source:** rejecting and coasting: slide 3 (the default filter rejects the first fake fix, then lets it back in half a minute later, seed 0), Q9. Jump guard: ADR-0038 (Proposed), #191 (merged, opt-in); [`jump-refusal/summary.md`](../analysis/results/jump-refusal/summary.md); cost: median error 1,263 m at +120 s after a refused jump on the drone leg, flagged unsafe; hazardous epochs on 3 of 50 seeds. Towers during a refused jump (#247, open, draft; study leg, 13 carriers, which the payload cannot hop): held 300 m jump, worst second over 0–300 s: guard alone 11,103 m; guard with learned noise 120 m, 0 hazardous, 0 of 50 on the spoofed position. On real static sessions towers made position worse than none (Q2). The product on slide 7 is a monitor that warns; mitigation stays with the autopilot.
- **Do not claim:** that we mitigate by default; that the guard is on by default or free; that towers hold position during a spoof on real data or on the leg as flown; that 120 m is a flight number.

---

*Status: 2026-11-11, against `main` at `c21e047`; brought up to `c97e09a` (#245, ADR-0041, ADR-0047); today's results (#241, #244, #247, #251, #262, #263) and the five questions of #268 added against `2499f87`. Q10, Q13, Q14 and Q18 rewritten and Q21 to Q24 added from the research report on `main` at `3493cfb` (#273).*
