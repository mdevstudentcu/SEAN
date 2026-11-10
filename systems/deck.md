# Deck: 5 minutes, 10 slides

- **Status:** Draft, 2026-11-10 (#28). Content for the humans to build slides from; they own the final deck.
- **Timing:** 30 s a slide. Judges' questions follow (up to 5 min).
- **Rules:** every number on a slide is in [`results.md`](results.md) with its source. Sim numbers are said as sim. The kickoff deck is not quoted. Undecided items (ADR-0030, ADR-0034, the hop set, the spoof-pitch wording) are said as proposed or open.
- **The story:** our numbers miss T1. The story is what we found, why, and what fixes it, told with the evidence.
- **Figures:** a repo path is on `main` at `8987664`. A URL is a PR's evidence image pinned to its commit. Every caption on the slide names the scenario or session, the commit and the kind of evidence (`systems/quality.md`).

## 1. The problem and the users

**Headline:** When GPS fails, a drone, an approach and a clock each need position or time with a number they can trust.

| User ([`use-cases.md`](use-cases.md)) | GPS failure in practice | What they need |
| --- | --- | --- |
| Drone on an Ottawa corridor | Jammers in cars on nearby roads; spoofing | Stay in the corridor; alert before leaving it |
| Crewed approach into YOW | Regional jamming and spoofing | A protection level the crew can act on |
| Timing terminal | Holdover; time spoofing | Time within a bound, honest uncertainty |

**Figure:** none (the table is the slide).

**Notes:** The challenge asks for navigation and timing that keep working without GPS, using signals of opportunity, with numerical confidence. We picked three users and wrote their requirements first, with targets we set ourselves; the mentors' answers of 2026-11-10 are folded in (open PR #158). Each target traces to a use case in our systems folder.

## 2. What we built

**Headline:** A receive-only payload records cell towers, GPS, IMU and barometer; a laptop fuses them with protection levels, live or from a log.

- Pi 4B, one RTL-SDR, GPS HAT, MPU6050, BMP180; authenticated link to the laptop (CurveZMQ)
- LTE sync front end, registry lookup, EKF family with tower and dongle clocks, integrity, operator panel
- Simulation, replay and live feed the same pipeline (ADR-0004)

**Figure:** the data-flow diagram in [`architecture.md`](architecture.md) (Mermaid, rendered by GitHub; a PNG export is `TBD`). Photo of the payload: `TBD`.

**Notes:** Everything on this slide is built and on our main branch. The payload decodes only broadcast sync signals and never transmits. The same code runs on a simulated scenario, a recorded session or the live stream, so a result in simulation runs unchanged on a recording.

## 3. What makes it different

**Headline:** Integrity first: every source, GPS and the towers alike, is treated as something that can fail (ADR-0021).

- Learn the towers while GPS is trusted; then keep position and time, catch GPS lying, catch the towers lying
- Faults grouped by what fails together: one site, one network builder's timing, GPS and everything that depends on it
- Time comes with a protection level; today it covers oscillator holdover, tower-held time is planned

**Figure:** `analysis/pr-evidence/shrikar-feat-90-nav-health-panel/live-tower-step.png`. Caption: sim session `realistic-with-base-long-outage-tower-clock-step`, seed 0, through the live path on loopback with `--insecure`, commit `ce2540d`, sim (#165). It shows HPL against the alert limit, the 95 % ellipse, the time PL, latched alerts naming the tower and per-source trust.

**Notes:** Accuracy-first multi-signal filters are published work, mostly by the Kassas group, and we build on them. What we add is treating towers and their GNSS-disciplined clocks as faults with their own hypotheses. The mentors told us the integrity level is ours to choose and to show confidence several ways; the panel shows several of them. We say "we found no published…", never "first".

## 4. How we scored ourselves

**Headline:** On simulated records shaped like real ones, we miss T1, T3, T5 and the slow spoof; we meet time-spoof detection and false alarms.

| Target (ours, `TBC`) | Sim result, 50 seeds | Verdict |
| --- | --- | --- |
| T1: 25 m for 300 s (drone) | Best mean 4,284 m | Not met |
| T3: 1.5 µs at 10 min | 49 of 50 seeds (`ekf`) | Not met |
| T4: time ramp / false alarms | 50 of 50, median 3 s / 0.0 per hour | Met |

**Figure:** https://github.com/HalfPast9/genocide-hackathon/blob/0a13006040117ce0d663470361ef2ab8eb8d51a6/analysis/results/challenge-baseline/t1_drone.png?raw=true (T1, drone leg, one dot per seed, commit `4e4c9d1`, sim, #170).

**Notes:** We built a benchmark that feeds the filter records exactly as the real front end writes them, with error sizes from the literature, all unconfirmed. The benchmark set is proposed (ADR-0030), not yet adopted. On it, position after 300 s without GPS is kilometres off, not metres. The rest of the talk is why, and what fixes it.

## 5. Why: the accuracy budget

**Headline:** Two things set the error: the front end under-reports its noise, and one carrier hears only 1 to 3 towers.

| What is heard (sim, drone leg) | Masts per 10 s | 120 s, told 2 m | 120 s, told the true noise |
| --- | --- | --- | --- |
| 1 carrier | 2 | > 1,000 m | 374 m |
| Hop 13 carriers | 27 | > 1,000 m | 68 m |

**Figure:** https://github.com/HalfPast9/genocide-hackathon/blob/c0b728aa8a314ca037e2a8b4f7c1d0a0b8a0f6c8/analysis/results/accuracy-budget/error_vs_masts.png?raw=true (error at 120 s and 300 s against masts heard, commit `fb62912`, seeds 0–19, sim, #179).

**Notes:** The mentors asked us to explain the calculation behind the accuracy, so we built a budget term by term and checked it against Monte Carlo (#178, #179). Told the reported 2 m, the filter trusts towers it should not, and no number of towers helps. Told the honest noise, hopping across 13 carriers takes the error from 374 m to 68 m, still short of 50 m. Which budget the team presents, and the hop set, are open.

## 6. Spoofing: what we catch and what we don't

**Headline:** Location jumps of 20 m or more are flagged in 1.1 s, but the output then follows them; a slow ramp needs 5 or more sites.

| Attack (sim, 50 seeds) | Detected | Then |
| --- | --- | --- |
| Jump ≥ 20 m (#176) | ≥ 95 % of runs, 1.1 s | Output follows it: 49–50 of 50 seeds at +30 s (25–300 m, #180) |
| 2 m/s ramp, 1 to 3 cells | 0 of 50 | — |
| 2 m/s ramp, 17 eNBs, opt-in monitor | 48 of 50, median 131 s | T4's 30 s not reached |

**Figure:** https://github.com/HalfPast9/genocide-hackathon/blob/dcb9689bd4d9ca27c570f7564c0860e7c02bf2c5/analysis/results/spoof-detection/detection.png?raw=true (detection share and time to alert, commit `220a6fa`, seeds 0–49, sim, #180).

**Notes:** The mentors said to begin with location jumps, so we did (#176, #180). The gate catches them fast, then lets the spoofed position back in; refusing a detected jump is our next fix (#184). The slow ramp is caught only where many towers are heard, and in minutes; whether to narrow our pitch to that is an open question for the team.

## 7. Real signals

**Headline:** On real towers this week we tracked LTE cells and matched them to the registry, and saw the two problems the sim had flagged: few cells per carrier, reported noise below the observed spread.

| Real, 2026-11-10, static, no GPS truth | Value |
| --- | --- |
| Rogers 2460, PCI 244 | Tracked 48.9 s of 59.5 s at 14.8 dB; eNB 30066 |
| Cells per carrier, two spots | 1 to 3 |
| Reported σ against observed spread | 1.1–4.3 m against 4–13 m |

**Figure:** `TBD` (no capture figure is in a PR yet; a capture-report plot from #175 on session `20261110-1305-lte-outside` would fit).

**Notes:** These are the payload's own captures, one dongle, outside, with no GPS fix, so there is no position truth and no position claim. Every cell tracked at the first spot matched a unique registered tower; three cells at the second spot are not in the table. The front end crashed on two of the first four captures; we found the cause and fixed it with a test (#181). The second-spot numbers are from our capture notes and not yet recorded in a PR.

## 8. Limits and what we'd fix next

**Headline:** Three fixes, in order: honest range noise, more towers by hopping, refuse detected jumps.

| Fix | Evidence it matters | State |
| --- | --- | --- |
| Range noise sized apart from the reported σ (#147) | LTE worse than none when told 2 m (sim) | Draft #156, not ready |
| Hop carriers (#179) | 374 to 68 m once noise is honest (sim) | Sim only; real hopping untested |
| Refuse a detected jump (#184) | Output follows every jump (sim) | Not started |

**Figure:** none (the table is the slide).

**Notes:** Every result before this slide is simulation except slide 7, and every simulated error size is a placeholder until real captures replace it (ADR-0015); our overnight IMU session is the first to do so (open PR #157). Not shown: any position from real towers, any real-world integrity level, the approach target, the reference station on hardware. We'd rather show you where it breaks than a number we can't defend.

## 9. Live demo

**Headline:** We demo from replay by default (RSK-04); the live stream is a bonus.

- Replay (proposed): the panel on a committed scenario with GPS loss and an injected location jump; scenario `TBD` by the owners
- Real: the 2460 capture's tracked cell and its registry match (session `20261110-1305-lte-outside`)
- Live, if the link holds: the Pi streaming over CurveZMQ to `pnt live --dash`

**Figure:** the panel itself, live.

**Notes:** The demo runs from a recording because Wi-Fi and hardware fail on stage; it is the same pipeline as live (ADR-0004). We streamed from the Pi over the authenticated link on 2026-11-10. If the live stream fails we say so and stay on replay.

## 10. Roadmap to a product

**Headline:** Fix, measure, characterise integrity, then a better receiver and a LEO layer, then certify.

| Phase ([`roadmap.md`](roadmap.md)) | Ends with |
| --- | --- |
| Fix what the week found | Fallback target met or missed on the drone leg, with the reason; jumps refused |
| Measure the sensor; characterise integrity | Every sim model `measured`; fault rates per site and builder |
| Product receiver, LEO layer, certify | Multi-carrier receiver; Iridium/Starlink (sim today); certification route `TBD` with Honeywell |

**Figure:** https://github.com/HalfPast9/genocide-hackathon/blob/63d87676b1933fe92530f5177217e3d4ec842c98/analysis/pr-evidence/shrikar-feat-97-starlink-doppler/error_curves.png?raw=true (towers against + Iridium, + Starlink, + both, seeds 0–49, local merge `b498c7e`, sim, #172).

**Notes:** Honeywell's alternative-navigation suite lists radios among its modalities, and we found no released terrestrial-communications module: this is that layer, with timing as a second output. In simulation, adding a LEO Doppler layer cuts the towers-only error from 19.8 m to 8.0 m with Iridium and 4.4 m with Starlink, in the kind case with every value unconfirmed. No performance standard exists yet for this kind of navigation, so certification is a route to agree with Honeywell, starting with drones.

## Likely judge questions

| Question | Candid answer |
| --- | --- |
| You miss T1 by two orders of magnitude. Why trust the architecture? | We trust the diagnosis, not the number: the budget names the two causes, and fixing the noise model is the precondition for hopping to help (#179). In the kind case, every tower heard with white noise, the same filters meet T1 (10.2 m, sim over real tower positions, #133). Real error sizes decide where between the two we land |
| Is any of it real? | The payload, front end, registry lookup and live link are real and ran on real signals this week. No position from real towers yet: 1 to 3 cells per carrier and no GPS truth. Every accuracy, integrity and detection number is sim |
| Can an 8-bit RTL-SDR range on LTE? | It tracks: PCI 244 for 48.9 s at 14.8 dB, white noise 0.73 m (#177). The slow wander is 5.95 m on one cell over 49 s, and that is what the reported σ misses. Not a calibration yet |
| Why 25 m and 99.9 %? | Ours. The mentors said "≤ 50 m for ~2 min should be OK-ish" for the drone, and the integrity level is ours to choose. We keep the stricter T1 and their figure as a recorded fallback (ADR-0034, open PR #158) |
| What if a tower lies? | Each site and each network builder is its own fault hypothesis. But `ekf-calibrated` can stay confident on a wrong table (#132), and the solution-separation monitor stays safe by being unavailable. Both are open |
| Your solution-separation protection level is over the alert limit before any fault. What is it worth? | With the realistic error sizes it is over 50 m in every epoch before the jump (sim, #176). It says plainly that the position can't be used, which is the safe failure. It becomes useful once the filter's tower model is honest (#147) |
| How good is your timing? | Sim: 49 of 50 seeds within 1.5 µs after 10 min for `ekf` (#170); the time-spoof ramp is caught in a median 3 s. Our time protection level covers oscillator holdover only; tower-held time is planned |
| Is decoding cell signals legal? | Receive-only, sync and broadcast fields only, device IDs hashed at capture ([`safety.md`](safety.md)). It needs a legal opinion, not our reading |
| What is new here? | Not the multi-signal filter. The Kassas group pre-empts parts of our tower-clock and solution-separation ideas ([`research.md`](research.md)). Where we found nothing published: the tower-based parts of our time-integrity claims (P3, P5), which are planned, not built (ADR-0021) |
| What would another month buy? | Phase 0 in [`roadmap.md`](roadmap.md): honest noise, hopping on real captures, refusing jumps, then a re-run of the baseline paired against today |
