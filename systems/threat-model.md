# Threat model

- **Status:** Draft, 2026-11-09 (#29)
- **Scope:** which attacks and failures matter most for each use case ([`use-cases.md`](use-cases.md)), why, and what we show against each. It answers mentor Q4 ("surprise us" with prioritised attacks per use case, [`mentor-qa.md`](mentor-qa.md)).
- **Evidence:** incidents and papers are cited; the full research behind them is in [`research.md`](research.md). Likelihood and impact ratings are the team's judgement (`TBC`), not measurements.

Everything here is defensive. Attacks exist only as software fault injection in `sim/` and `sources/` (ADR-0001, ASM-03); nothing in this file describes how to build or operate a jammer or spoofer.

## How the ranking works

- **Likelihood (L):** how likely the attack or failure is for that use case around Ottawa, from incidents and published demonstrations. H, M or L.
- **Impact (I):** what it does to that user if nothing catches it. H: silent, hazardously misleading position or time. M: loss of service that the user notices. L: degraded accuracy, still bounded.
- **Rank** orders by L × I (H = 3, M = 2, L = 1), with ties broken by impact: on equal L × I, silent failures rank above loud ones, because a confident wrong answer is the aviation hazard (the same reasoning as our level 2 in `pnt.metrics.resilience_level`). Rows equal on both keep their listed order.

## What the evidence says about Ottawa

- **Local, low-power jamming near roads is the most common GNSS interference in civil airspace outside conflict zones.** At Newark, personal privacy jammers in vehicles on the New Jersey Turnpike repeatedly disrupted the airport's GBAS: about two events a day of at least 10 dB receiver degradation, mostly 30–60 s long, effective over hundreds of metres [Grabowski 2012]. The FCC fined one driver who used a jammer to defeat his employer's vehicle tracker [Inside GNSS 2013].
- **Jamming has brought down drones.** During a 2018 light show in Hong Kong, 46 of 100 drones fell into the harbour; jamming was the suspected cause [SCMP 2018].
- **Regional interference and spoofing cluster in conflict-adjacent airspace,** not over Canada. gpsjam.org's daily ADS-B accuracy maps show it around the Baltic, the Black Sea, the Eastern Mediterranean and Middle East, and the Persian Gulf; its only North American note is the southwestern US, attributed to military training aircraft and jamming tests [Wiseman, gpsjam.org]. Aircraft over Russia were seen spoofed onto circles and airport positions [Lo 2025], and EASA keeps a bulletin on GNSS interference [EASA 2022].
- **Spoofing usually leaves the integrity flags high.** In a large ADS-B dataset, almost all confirmed position anomalies kept high quality indicators [Park 2026]; Aireon saw the same [Aireon]. A recorded time spoof at an authorised test pulled a receiver's time by about a millisecond while it reported nanosecond accuracy [Baweja 2026, not peer reviewed].
- **Timing users fail with GNSS.** The January 2016 GPS UTC error pushed telecom timing into holdover at many sites [RNT 2016]. Tower time is GNSS-disciplined, so towers can follow a time spoof (ADR-0024).
- **No published attack targets a SoOP navigation receiver.** Rogue and overshadowed cells are demonstrated only against phones [research.md §1]. Tower attacks are therefore rated L in likelihood here, and kept because they are cheap to simulate and judges will ask.

## Location jumps first (studies, 2026-11-10)

Our Honeywell mentors' answer on which attacks to start with (2026-11-10): "I would begin with location jumps". Asked how big real jumps are, they said most are in the range of hundreds (of kilometres, not metres). Two sim studies cover the sizes, both on the `uc01-drone-circuit` route with the `realistic` set's error model (`realistic-uc01`) and as committed (`uc01`, synthetic towers), a jump at 150 s held to the end of the 360 s run, eight directions. Every model is `placeholder` in `verification.md`.

- Jumps of 20 m to 500 km, `ekf` and `ekf-imu` with and without the opt-in jump guard: `analysis/guard_jump_sizes.py`, 20 seeds, numbers in ADR-0038 (*Jump size*).
- Jumps of 5 to 20 m, and a small jump that then drifts, for `ekf`, `ekf-calibrated`, `ekf-imu`, `ekf-mhss` and `ekf-guard`: `analysis/jump_study.py`, 16 seeds at `54dd146` ([`summary.md`](../analysis/pr-evidence/176/summary.md)).

What they show:

- **A jump of 20 m or more is flagged 1.1 s after it** (the 1 s alarm hold), by every estimator in both environments, up to 500 km, in every run but one (a 20 m jump `ekf` missed on `uc01`, 19 of 20). A 15 m jump is flagged in 25 to 100 % of runs, a 5 or 10 m jump in at most 6 %. No estimator raised a false alarm on clean runs.
- **A jump the gate misses is absorbed, and stays small.** In every run that missed one, the worst error was at most 21 m, with no hazardous epoch.
- **Flagging is not refusing.** Without the guard, the filter coasts after the rejection, its covariance grows, and the same jumped fix is accepted again: held jumps leave hazardously misleading epochs (realistic set: 50 to 300 m in 19 or 20 of 20 runs, 1 km in 4 to 9 of 20). Jumps of 100 km and more are never taken back within the run. The opt-in guard (`*-guard`, ADR-0038, Proposed) refuses held jumps of 50 m and more with no hazardous epoch; its cost is the coast, flagged `unsafe` (on the realistic set it already latches on some 15 to 20 m jumps, and the error then grows to as much as 2.7 km).
- **`ekf-imu` can diverge after a small detected jump.** With the realistic set, two seeds (6 and 14) detected a 15 or 20 m jump and then drifted to 41 to 83 m, with an alert raised and no hazardous epoch.
- **`ekf-mhss` has no hazardous epoch only because it is not available.** Its HPL is over the 50 m alert limit in every pre-jump epoch with the realistic set, and in 71 % of them on `uc01`.
- **A small jump that then drifts is followed like a ramp.** A 5 or 10 m jump, then 0.5 or 2 m/s the same way (2 m/s is T4's ramp), is flagged in at most 19 % of runs by any estimator, the guard included. The output follows the spoofed track to 113 to 433 m, with hazardous epochs in 15 or 16 of 16 runs for every estimator except `ekf-mhss` (unavailable). No estimator in the study runs the spoof detector (#102), which is opt-in.
- **T4's jump target is set** (ADR-0034, *Amendment 2026-11-11*, from the jump study #176): a jump of 20 m (`TBC`) or more flagged within 2 s in ≥ 95 % of runs, GNSS excluded while it lasts, no hazardously misleading epoch. The default estimators meet the detection part; the opt-in `-guard` estimators meet all of it (ADR-0038).

## Ranked attacks per use case

### UC-01: drone on an urban corridor (Ottawa, below 120 m)

| Rank | Attack or failure | L | I | Why |
| --- | --- | --- | --- | --- |
| 1 | Local GNSS jamming from a vehicle on a nearby road (personal privacy device) | H | M | The Newark pattern: frequent, short, near roads [Grabowski 2012]. Loud (GNSS drops out), so the risk is losing the corridor, not being misled |
| 2 | Tower clock jump or a stale or wrong tower record | M | M | LTE clocks jump [Lapin 2024]. The 2024 ISED file behind the sim's `cells-ottawa.csv` is two years old; the 2026 extract (#110) is current, but registry staleness and PCI collisions (152 of 3,904 (EARFCN, PCI) pairs near Carleton are shared by more than one eNB, #110) remain association fault modes (ADR-0023). Biases position during an outage |
| 3 | Ground reference station fault (moved, clock step, link lost) | M | M | A new single point of failure that every differenced reading inherits (ADR-0020). Likelihood M while it is a hobby-grade box on a mast |
| 4 | Slow position spoof that drags the drone off course (carry-off) | L | H | Silent; aimed at drones in UC-01's own threat list. Needs a deliberate, illegal transmitter. A filter-aware drift beats per-epoch gates [Shen 2020] |
| 5 | Forged records on a ground link | L | H | Skips every radio check (ADR-0026). Needs access to the local network |
| 6 | Crude position takeover (jump) | L | H | Same transmitter as the slow position spoof. The GNSS gate flags a jump of 20 m or more within 1.1 s, then, without the opt-in guard, accepts a held jump of 50 m to 1 km again once the coast has grown past it: hazardously misleading (location jumps above). Impact was M before the studies; H confirmed by the owners (2026-11-11) |
| 7 | Rogue or overshadowed cell posing as a tower | L | M | Demonstrated on phones only; registry and clock checks should catch most (ADR-0023) |

### UC-02: crewed approach into YOW

| Rank | Attack or failure | L | I | Why |
| --- | --- | --- | --- | --- |
| 1 | Jamming on final from a vehicle near the airport | M | H | The Newark case is an airport next to a highway [Grabowski 2012]. On an approach, losing GNSS needs a protection level the crew can act on (UC-02) |
| 2 | ADS-B content that is wrong because the reporting aircraft's GNSS is wrong | M | M | ADS-B is GNSS-derived and keeps high quality flags under spoofing [Park 2026]. Matters for the ADS-B warning (P6), not for our position today |
| 3 | Position spoof (ramp or jump), including an aircraft spoofed elsewhere and still wrong on arrival | L | H | Common in conflict-adjacent airspace [Lo 2025; EASA 2022], not reported near Ottawa. Silent and hazardous |
| 4 | Jam then spoof (GNSS lost, then a false signal offered on reacquisition) | L | H | The known sequence ADR-0025 names. Catching the return of GNSS matters as much as its loss |
| 5 | Wide-area jamming with towers drifting in holdover | L | M | Edwards showed two co-located towers holding under GPS-only, intermittent jamming [Kassas 2022], which says little about long or multi-constellation jamming |

### UC-03: timing user (GNSS-disciplined terminal)

| Rank | Attack or failure | L | I | Why |
| --- | --- | --- | --- | --- |
| 1 | Time spoof that pushes time without moving position | M | H | Shown over the air at an authorised test, silently [Baweja 2026]. UC-03's named threat |
| 2 | Meaconing (record and rebroadcast with a delay) | M | H | Shown over cables against telecom timing receivers [Blum 2019]. Positions look plausible |
| 3 | Jamming, forcing holdover | H | M | The common case; loud. The question is how long the time bound holds (REQ-03) |
| 4 | Wide-area time spoof or GNSS anomaly that also moves the towers' time | L | H | The 2016 UTC error is the benign version [RNT 2016]. Tower time follows GNSS, so the towers cannot vouch for it (ADR-0024) |

## What we show against each top attack

Detections are flags on the `Estimate`; responses are what the estimator does. "On main" means in `origin/main` at the commit this file was written on. Every scenario named is in the attack library (`src/pnt/sim/scenarios/`; the `realistic-*` and `easy-*` variants come from `sets/_attacks.yaml`).

| Attack | Scenarios | Detection and response | Status |
| --- | --- | --- | --- |
| Local jamming | `jamming-zone`, `gps-outage`, `uc01-drone-circuit`, `uc02-yow-approach`, `*-outage`, `*-long-outage`, `*-gps-no-fix` | GNSS loss is self-evident (`gnss_unavailable`). The filter coasts on towers, barometer and clocks; the HPL grows, and MHSS (#82, #108) bounds it with tower-site and builder hypotheses. Time keeps its own protection level (P5) | On main |
| Slow position spoof | `spoof-ramp`, `*-spoof-ramp` | Spoof detector (#102): calibrated towers refute the GNSS-steered position, raising `spoof_suspected` and `gnss_excluded`, and the tower clocks roll back. MHSS GNSS common-mode hypothesis (#82, #108) excludes GNSS on a failed separation test or a held GNSS alarm | Detector on main, opt-in (`clock_model="calibrated"`); MHSS on main as `ekf-mhss` |
| Position jump, GNSS returning | `spoof-jump`, `*-spoof-jump`, `*-gps-return` | GNSS innovation gate (`gnss_excluded`); jump guard (`*-guard`, ADR-0038); spoof detector; MHSS exclusion | Detection on main: 20 m or more within 1.1 s. Refusal on main, opt-in (`*-guard`); without it a held jump is accepted again (Gaps) |
| Time spoof | `time-spoof`, `*-time-spoof` | Time gate: GNSS time tested against our clock model (`time_spoof_suspected`); GNSS time is then not used. Since ADR-0047, `ekf` and `ekf-mhss` put our clock in the tower ranges once GNSS time is used, so the towers steer our clock after GNSS time is rejected. On `time-spoof` that cut time-misleading epochs from 20.9 to 5.2 per run (PR #244). Refuting GNSS time from the towers is still planned (ADR-0024). Time protection level for what is left | On main |
| Meaconing | `meaconing`, `*-meaconing` | Time gate (the delay appears as a clock step); spoof detector when the delay moves position against the towers | On main |
| Tower clock jump | `*-tower-clock-step`, `realistic-with-base-long-outage-tower-clock-step` | MHSS site hypothesis (#82, #108); with the base, it cancels in the difference and the base flags `tower_fault` | On main |
| Jamming or spoofing that reaches the traffic around us first | `uc02-yow-approach-adsb-jammed`, `-spoofed` (clean: `uc02-yow-approach-adsb`) | ADS-B early warning (#91, ADR-0033): aircraft that reported good quality report a held NACp/NIC drop, or a track jump with good quality; `ekf-mhss` raises its GNSS common-mode prior and flags `adsb_interference` / `adsb_spoofed_aircraft`. Lead time and false alerts: `analysis/adsb_warning.py` | Proposed (#91) |
| Forged ground-link records | No sim scenario: it is a network attack. Loopback tests in `tests/test_link_security.py` | Prevention, not detection: CurveZMQ (ADR-0026). The laptop pins each Pi's key, so an impostor never completes the handshake. Each Pi admits only trusted laptop keys (ZAP). A record changed in flight fails authentication and ends the connection. `pnt record` and `pnt live` refuse plaintext unless `--insecure` | Authenticated (#89) |
| Base station fault | `realistic-with-base-long-outage-base-moved`, `-base-clock-step`, `-base-lost` | Base fault hypothesis inside `ekf-base` (#107): the base disagrees with its survey across towers, `base_excluded`, and the filter falls back to the tower clocks the base measured before | On main (`ekf-base`); not an MHSS hypothesis (`ekf-mhss` does not use the base) |
| Sensor degradation, nuisance | `*-baro-drift`, `*-gps-low-sats`, `*-tower-loss`, `nominal` | False-alarm checks: no alarm is expected on `gps-low-sats` and `nominal` (taxonomy `expect_alert`) | On main |

The numbers for these rows (time-to-alert, detection rate, false alarms, hazardous epochs, resilience level) come from `just results` on the final commit, into the results block of [`verification.md`](verification.md). They are not quoted here because the estimators are still changing.

## Gaps

Top attacks with no scenario, or no detection we can show. These are open work, not fixed here.

| Attack | Use case (rank) | Gap |
| --- | --- | --- |
| Position jump accepted again after exclusion | UC-01 (6), UC-02 (3) | **Fix is opt-in.** Without the jump guard the gate excludes a jump at once, then accepts it once the coasting covariance has grown past it: held jumps of 50 m to 1 km leave hazardous epochs (location jumps above). The guard (ADR-0038, Proposed) is not the default: it can keep honest GNSS out after a hard manoeuvre, and its coast is long |
| Jump then drift (a jump inside the noise, then a ramp) | UC-01 (4, 6) | **No detection in the estimators studied.** A 5 to 10 m jump followed by a 0.5 or 2 m/s drift is flagged in at most 19 % of runs, the guard included, and followed to 113 to 433 m (jump study). The spoof detector (#102) is opt-in and was not in the study. Not in `_attacks.yaml`: the study composes `spoof_jump` and `spoof_ramp` |
| Jam then spoof | UC-02 (4) | **No scenario.** Every scenario has one fault type for GNSS; an outage followed by a spoof on return is not in `_attacks.yaml` |
| Wide-area time spoof that also moves the towers | UC-03 (4) | **No scenario.** `time-spoof` moves only our GNSS time; the sim's tower clocks never follow GNSS. **No detection** from towers by design (ADR-0024); only our own oscillator in holdover can refute it, and only briefly |
| Network builder's timing fault (holdover, captured grandmaster) | UC-01 (2), UC-03 (4) | **No fault type.** The realistic sets model a shared builder clock, but no attack steps or ramps it. MHSS has the builder hypothesis; nothing exercises it |
| Towers drifting in holdover during wide-area jamming | UC-02 (5) | **No scenario.** Tower clocks behave the same with GNSS on or off |
| Slower or filter-aware position drift | UC-01 (4) | Only one ramp rate (2 m/s, T4). No sweep of slower ramps, where the spoof detector and MHSS are weakest |
| Reference station fault inside MHSS | UC-01 (3) | **No base hypothesis in MHSS.** `ekf-mhss` (#108) does not take the base, so a base fault is caught only by `ekf-base`'s own check (#107), with no protection level that accounts for it |
| Forged ground-link records | UC-01 (5) | Authenticated (#89). Still open: **a stolen key** (a copied Pi secret key or SD card impersonates that Pi, and nothing detects it); **no hash chain**, so an edited session log on the Pi is not detected (after judging, ADR-0026); **MAVLink not signed** (`TBC`, INAV, ADR-0028); a tampered connection is dropped and not reopened, so it fails closed until `pnt live` is restarted |
| Rogue or overshadowed cell, cellular meaconing | UC-01 (7) | **No scenario.** `tower_clock_step` is the nearest (a step on one tower); there is no phantom cell, ramp on one tower, or relay of several towers |
| ADS-B content wrong under spoofing | UC-02 (2) | Synthetic traffic only (#91): placeholder tracks, avionics quality and nuisance dips, no recorded traffic yet (#22). A slow carry-off of the traffic, under the 300 m jump gate, is not caught. ADS-B stays GNSS-derived (ADR-0024): it widens our protection level, never confirms GNSS |
| Real-data evidence for any attack | all | Attacks have been injected only into simulated runs. Injecting them into real sessions (ADR-0015) waits on the first captures |

## References

- [Aireon] Aireon, *Countering GNSS spoofing: Aireon's global ADS-B network delivers trust*, n.d., company article. https://aireon.com/countering-gnss-spoofing-aireons-global-ads-b-network-delivers-trust/
- [Baweja 2026] Baweja, *A Conditional Timing Protection Level: Holdover-Limited Undetected Time Error Under GNSS Spoofing*, 2026, arXiv preprint 2606.24210. https://arxiv.org/abs/2606.24210
- [Blum 2019] Blum, Dötterböck & Pany, *Investigation of the Vulnerability of Mobile Networks Against Spoofing Attacks on their GNSS Timing-receiver and Developing a Meaconing Protection*, 2019, ION ITM. https://www.ion.org/publications/abstract.cfm?articleID=16697
- [EASA 2022] EASA, *Safety Information Bulletin 2022-02: Global Navigation Satellite System outage and alterations leading to communication / navigation / surveillance degradation*, 2022 and updates, safety bulletin. https://www.easa.europa.eu/en/newsroom-and-events/news/easa-updates-safety-information-bulletin-gnss-interference
- [Grabowski 2012] Grabowski, *Personal Privacy Jammers: Locating Jersey PPDs Jamming GBAS Safety-of-Life Signals*, 2012, GPS World. https://www.gpsworld.com/?p=12837
- [Inside GNSS 2013] Inside GNSS staff, *FCC Fines Operator of GPS Jammer That Affected Newark Airport GBAS*, 2013, Inside GNSS. https://insidegnss.com/fcc-fines-operator-of-gps-jammer-that-affected-newark-airport-gbas/
- [Kassas 2022] Kassas, Khalife, Abdallah & Lee, *I Am Not Afraid of the GPS Jammer*, 2022, IEEE AES Magazine, doi:10.1109/MAES.2022.3154110. https://ece.osu.edu/sites/default/files/2022-09/I_am_not_afraid_of_the_GPS_jammer_resilient_navigation_via_signals_of_opportunity_in_GPS_denied_environments.pdf
- [Lapin 2024] Lapin et al., *Base Station Clock Offset of Cellular Measurements and Its Impact on Positioning*, 2024, IEEE TVT. https://spcomnav.uab.es/docs/journals/Base_Station_Clock_Offset_of_Cellular_Measurements_and_Its_Impact_on_Positioning.pdf
- [Lo 2025] Lo, Liu, Ibrahim, Chen & Walter, *Observations of GNSS Spoofing in Russia in 2023–2024*, 2025, ION ITM. https://web.stanford.edu/group/scpnt/gpslab/pubs/papers/Lo_ION_ITM_2025_Russia_Spoofing.pdf
- [Park 2026] Park, Lee & Son, *Track-Consistency-Based GNSS RFI Monitoring Using Crowdsourced ADS-B Sensor Networks*, 2026, arXiv preprint 2607.09700. https://arxiv.org/abs/2607.09700
- [RNT 2016] RNT Foundation (Chronos case study), *26 January 2016 GPS event*, 2016, report. https://rntfnd.org/wp-content/uploads/26-January-2016-GPS-Event.pdf
- [SCMP 2018] South China Morning Post, *HK$1 million in damage caused by GPS jamming that caused 46 drones to plummet during Hong Kong show*, 2018, news. https://www.scmp.com/news/hong-kong/law-and-crime/article/2170669/hk13-million-damage-caused-gps-jamming-caused-46-drones
- [Shen 2020] Shen, Won, Chen & Chen, *Drift with Devil*, 2020, USENIX Security. https://arxiv.org/abs/2006.10318
- [Wiseman, gpsjam.org] Wiseman, *GPSJam FAQ*, checked 2026-11-09, website. https://gpsjam.org/faq
