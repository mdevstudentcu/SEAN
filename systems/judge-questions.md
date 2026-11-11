# Judge questions

- **Use:** for the presenter of [`deck.md`](deck.md): the 18 hardest questions a navigation engineer is likely to ask. Each answer is at most 45 words and can be said as written. Numbers are simulation unless the answer says real; sources are in [`results.md`](results.md).
- **If you don't know:** say "I don't have that number; it is in our results file" and move on. Never estimate a number on stage.

## 1. Your own target is 25 m for five minutes. Why do you miss it?

> Mostly the radio's noise. Our front end reports only fast noise, so the filter rejects nearly every tower reading; LTE made position worse than none. In simulation, learning each tower's noise cut the median five-minute error from 4,034 to 982 metres. Still far from 25.

- **Source:** #137, #147 (LTE worse than none); #156 (open, draft, opt-in; per-run p95, seeds 0–49); ADR-0039 (proposed in #156, not on `main`). On the easy synthetic route the budget meets 25 m (#178).
- **Do not claim:** that any fix meets T1 or the 50 m fallback; that #156 is merged or on by default.

## 2. Is any of it real?

> The payload, the radio captures and the tower matches are real. We measured range noise on fifteen real captures and recorded a GPS session with a timing pulse. Every accuracy and detection number is simulation. With GPS removed in two real sessions, towers worsened position.

- **Source:** [`results.md`](results.md) (a); ADR-0036; #211. Real error after GPS loss: #233 (merged, #250) rerun after #245's front-end fixes, [`lte-reacq-steps/NOTES.md`](../analysis/results/lte-reacq-steps/NOTES.md) *GPS cut*: `ekf` with LTE, median 21,553 m (`20261111-0151`) and 10,718 m (`20261111-0233`) at 300 s over 5 cut times each, against 0.6 and 1.3 m without LTE; before ADR-0047's default, not rerun.
- **Do not claim:** a position from real towers, or any real accuracy, integrity or detection rate. Quote #214's line labelled "real session, GPS removed in software".

## 3. Why are three towers not enough?

> Each range carries the receiver's clock error. With barometer height, three ranges solve position and clock with nothing left to check them, and a tower with its own unknown clock adds no check. In simulation, with our error model, no tower count met the target.

- **Source:** [`research.md`](research.md) §1 item 9 (Jia, Khalife & Kassas 2023); this is why tower clocks are learned while GPS is trusted (ADR-0022, Proposed). Study: #232 (merged, #250), [`tower-count/summary.md`](../analysis/results/tower-count/summary.md): with the committed and honest error models no tower count meets T1 or the fallback; with clean errors all 17 sites within 3 km meet T1. Backup (simulation, #179): 2 masts heard per 10 s gives 374 m at 2 min; 27 masts, 68 m, once the noise is right.
- **Do not claim:** a minimum tower count; that the motion sensor makes three towers enough.

## 4. How do you know where a tower is, and what if the table is wrong?

> From the ISED registry: the frequency and cell ID we decode map to one registered site, or we drop the cell. From Carleton, no row matched another site; ambiguous rows are dropped. In simulation, a fake tower on a real ID fooled one filter.

- **Source:** ADR-0023 (Proposed); registry audit of 4,059 rows, #133 (the count of dropped ambiguous rows is in no committed file: `TBD`); wrong-table simulation, #133 and #132 (`ekf-calibrated` 186.5 m, 5,147 hazardous epochs; `ekf-mhss` flags the site, HPL 5.4 km).
- **Do not claim:** that a tower is "identified": say "consistent with a registered site". The dongle cannot decode the global cell ID (SIB1).

## 5. Can an 8-bit RTL-SDR range on LTE at all?

> For precision at rest, yes: 0.7 metres of noise on strong cells, 23 on weak ones, at ten records a second. But a slow error, typically 8 metres, sits on top, weak cells drop often, and without truth we measured no bias.

- **Source:** real, ADR-0036 and [`lte-measured-noise/`](../analysis/results/lte-measured-noise/summary.md) (at `8892fca`, after #245: white σ 0.73 m at 13–16 dB, 22.5 m at −14 to −11 dB on 43 records; correlated S(1 s) median 8.1 m). [`research.md`](research.md) §2: no published real-tower LTE TOA scatter from an RTL-SDR was found.
- **Do not claim:** an accuracy (no truth), or that it works while moving.

## 6. Your 5.33-sigma bound: how is it computed, and at what integrity risk?

> It is 5.33 times our filter's largest horizontal standard deviation: a bound under our model, one in ten million per epoch only if errors are Gaussian and the covariance honest. On some simulated flights it is not honest, and the error escapes the bound.

- **Source:** `integrity/protection.py` (`K_H` 5.33); `integrity/mhss.py` (`phmi` 1e-7, priors 1e-3 / 1e-4 / 1e-4 / 1e-3, all `TBC`); [`verification.md`](verification.md) *Integrity monitor*. T5 is missed: `ekf` has hazardous epochs on 7 of 50 seeds of the drone outage (#170).
- **Do not claim:** that the bound always holds, or a certified integrity risk. Call it "a bound under our model", not a protection level in the certified sense. Where it held: through the demo's outage and guarded jump (seed 0); where it failed: the unguarded jump, and 7 of 50 seeds of the drone outage.

## 7. What happens when the spoofer is subtle, a slow ramp?

> Our default filter misses a 2 metre-per-second drag entirely in simulation. An opt-in tower monitor catches it in 48 of 50 runs where 17 sites are heard, after 131 seconds median, not 30. A small jump then drift is caught in at most 24 percent.

- **Source:** #170 (0 of 50); #180 (merged, #250; ADR-0037 Proposed; 1 of 50 on the drone leg as committed); #176 (merged, #250; jump then drift followed to 110–430 m).
- **Do not claim:** that we catch slow spoofing within 30 s, or with 1 to 3 cells.

## 8. What about false alarms?

> In simulation, zero per hour on clean runs. The aircraft-based warning gives 1.94 per hour from modelled quality dips. The jump guard has a different cost: after 5 of 46 hard manoeuvres it kept honest GPS out. Real-world false-alarm rates are not measured.

- **Source:** #170 (0.0 /h on `nominal`, four estimators); #166 (ADR-0033 Proposed); ADR-0038 *Consequences* (manoeuvre cases, GNSS at 1 Hz). Real: the C/N0 jamming indicator stayed 0 over one 595 s session (#211).
- **Do not claim:** a real-world false-alarm rate.

## 9. Why refuse GPS after a jump, rather than trust it again?

> Because a spoofer only has to wait. Once GPS is rejected, the filter's uncertainty grows until the same fake fix passes. The guard keeps GPS out until its own stream steps back. Honest GPS returns 0.1 seconds after the jump ends; meanwhile we dead-reckon.

- **Source:** ADR-0038 (Proposed), #191 (merged, opt-in); [`jump-refusal/summary.md`](../analysis/results/jump-refusal/summary.md). Cost: median error 1,263 m at +120 s after a refused jump on the drone leg, flagged unsafe.
- **Do not claim:** that the guard is on by default, or that it is free.

## 10. Is this legal? You record cell signals.

> The payload never transmits: no transmit path in code or hardware. We decode only signals meant for everyone, sync and broadcasts, our reading of section 9(2) of the Radiocommunication Act. Wi-Fi identifiers are hashed at capture. Attacks are software only. No legal opinion yet.

- **Source:** REQ-07, REQ-08, ADR-0001, ADR-0011, [`safety.md`](safety.md); `tests/test_hard_rules.py`.
- **Do not claim:** that a lawyer or regulator has approved it.

## 11. What is new compared with Kassas and colleagues?

> Two things we found no published work doing: tagging every source by its GPS dependence, so towers may contradict GPS time but never confirm it; and a GPS fault hypothesis that includes the towers' borrowed time. And we measured the slow error our radio hides.

- **Source:** [ADR-0024](adr/0024-gnss-dependency-tags.md) (dependency tags); [`research.md`](research.md) *Novelty check* (P2, P5; Jia, Khalife & Kassas 2023 already group tower clocks and run solution separation); slow error, ADR-0036. IEEE Xplore and ION were not searched in full text.
- **Do not claim:** "first". Do not claim the tower-time refutation of GPS time is built: it is planned. Do not claim measuring the slow error is new: say we measured it.

## 12. What about timing?

> Second priority, as the mentors asked. In simulation the timing receiver stays within 1.5 microseconds after ten minutes on 49 of 50 runs, and a 50 nanosecond-per-second time drag is caught in a median of 3.3 seconds. Elsewhere our time bound is overconfident.

- **Source:** #170 (merged, #250; T3 missed on one seed at 1.55 µs; `ekf-calibrated`'s σ bound fails on 13 seeds); RUNBOOK (time PL calls time unsafe early). Elsewhere: since ADR-0047 (Accepted, cost accepted by the owners) the default `ekf` has 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets ([`pr-evidence/228/before-after.md`](../analysis/pr-evidence/228/before-after.md), `73c9e9b`). Real: PPS discipline on the Pi, 769 ns standard deviation (#216, merged; ASM-04).
- **Do not claim:** that T3 is met, that the time bound is honest on every set, or a real holdover number.

## 13. What would another month buy?

> Moving captures with independent truth, so the error model covers motion; the fixes run together on the agreed statistic; and real frequency hopping. We have not estimated durations, and we will not promise 25 metres.

- **Source:** [`roadmap.md`](roadmap.md) *Three milestones*, M1; #218. Realistic multipath alone exceeds 25 m in the budget (#178).
- **Do not claim:** a date or a target we expect to meet.

## 14. What is the certification path?

> No performance standard exists for this kind of navigation; RTCA SC-159 covers GNSS equipment. Drones under a specific-operation risk assessment look shorter than crewed aircraft. First we need fault statistics from many hours of data. Route and regulator are to be decided with experts.

- **Source:** [`research.md`](research.md) §3 item 6; [`roadmap.md`](roadmap.md) *Certification*.
- **Do not claim:** a certification plan agreed with anyone, or a design assurance level.

## 15. What did the simulation get wrong, compared with the captures?

> The sim assumed 50 metres of white noise per second; at rest, real white noise is 0.7 to 23 metres, plus a slow 8-metre error. Records told the filter 2 metres. Real cells drop and reacquire often; the sim kept every track.

- **Source:** ADR-0036 (Proposed; the *Sim validity* row is not yet moved); `pnt compare` sim against real (#199: 49.2 m white against 21.3 m smooth); #183 (front-end faults).
- **Do not claim:** that the simulator is validated, or that the measured model is adopted.

## 16. Your panel says LTE is not in use. Did the towers contribute anything to the position I just watched?

> Very little: records report only fast noise, so the filter rejects nearly every tower reading; on one simulated run, all but 9 of 5,383 before the spoof. After GPS loss it flies on barometer and dead reckoning. Learning tower noise is the fix in review.

- **Source:** #180 description (one seed, `challenge` drone leg: 5,374 of 5,383 tower readings rejected before the spoof); #147; guard demo runbook (PR #220, open: Sources lists `lte` under *Not in use*). Fix: #156, ADR-0039 (proposed in #156, not on `main`; opt-in).
- **Do not claim:** that the demo's position after GPS loss came from towers; a percentage of epochs (no committed count).

## 17. Is the 8 m slow error multipath, or your dongle's oscillator?

> Not the dongle, nor the tower clock. The slow error remains in differences between two sectors of one site on one frequency, where dongle and shared site clock cancel. That leaves multipath at a static antenna or our tracking loop; which, we have not determined.

- **Source:** real, ADR-0036 *Context* (same-eNB sector pairs, which share a clock, still show S(1 s) of 5.5 to 36 m, 5.5 to 18 m without the one pair whose cell sits on a carrier alias; "so it is not a clock"); [`lte-measured-noise/summary.md`](../analysis/results/lte-measured-noise/summary.md), *Pairs on one carrier (dongle cancels)*.
- **Do not claim:** that it is multipath: the tracker's loop is not ruled out. A static capture cannot size multipath in motion.

## 18. Who buys this, and at what altitude does it work, given tower antenna downtilt?

> First user: an operator of inspection or delivery drones on an urban corridor below 120 metres. Altitude is an assumption: we recorded on the ground only, and how tower antennas tilted toward the street affect reception at altitude is not measured.

- **Source:** UC-01, [`use-cases.md`](use-cases.md); [`roadmap.md`](roadmap.md) *Operating envelope*; real captures on the ground or 0.5 m up (#210). Simulated flights at 40 to 45 m.
- **Do not claim:** a buyer who has expressed interest, a price for the product, or a working altitude.

---

*Status: 2026-11-11, against `main` at `c21e047`; brought up to `c97e09a` (#245, ADR-0041, ADR-0047).*
