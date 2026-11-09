# Research summary

- **Status:** Draft, 2026-11-09
- **Scope:** what our research found, and the published work it rests on, so D1 and the pitch can cite it (#99). It summarises three internal research reports written 2026-11-08/09: *Hostile signals of opportunity*, *LTE tower ranging on RTL-SDR*, and *Unconventional PNT sources and angles*. The reports themselves are not in the repo.
- **Decisions** that came out of this research are in the ADRs (0019–0026); this file records the evidence, not the choices.

**How far to trust it.** The reports rest on web and arXiv searches. IEEE Xplore and ION proceedings were not searched in full text, and many papers were read only as abstracts. "We found no published…" means not found with that effort, not proven absent. The novelty checks against full papers are in [Novelty check (#98)](#novelty-check-98). Evidence is tagged as the reports tag it: demonstrated over the air, demonstrated over cables or in the lab, simulated, theoretical, or our own inference.

## 1. Hostile signals of opportunity

What can go wrong with every signal we fuse, and what a passive receiver can do about it.

1. **No signal of opportunity we use is authenticated at the signal level.** The cryptographic fixes (encrypted 5G PRS, 802.11az secure ranging, Iridium STL) all need a cooperating or licensed receiver, so none reaches us. Defence has to come from physical consistency, registries and clocks.
2. **Cellular downlink attacks are proven against phones, not against navigation receivers.** Fake base stations work on commercial devices [Shaik 2016]. Overshadowing replaces broadcast subframes at little more than the legitimate power [Yang 2019; Erni 2022], and has been done on the 5G sync block below the legitimate power [Ludant 2021]. Because the sync sequences are fully known, a delayed, stronger copy can enlarge a measured distance without a protocol-level bound [Singh 2022]. **No paper was found that attacks a SoOP pseudorange receiver**; the effect on our ranges is inference.
3. **Jamming the sync signals is harder than jamming the reference signals.** In a cabled LTE testbed, denial needed about 30 dB more jamming power against PSS/SSS than against CRS [Rao 2017]. That favours our PSS/SSS ranging.
4. **Tower time inherits GNSS failures.** TDD cells hold a tight time budget, normally from GNSS-disciplined grandmasters [Ruffini 2021]. In holdover an OCXO-class reference drifts by microseconds per hour, which is hundreds of metres of range [Sharma 2026]. The January 2016 GPS UTC error pushed telecom timing into holdover at many sites [RNT 2016]. A recorded time spoof at an authorised test pulled a receiver's time by about a millisecond while it reported nanosecond accuracy [Baweja 2026, single author, not peer reviewed]. So **tower time can "confirm" a spoofed GNSS time**, which is why ADR-0024 lets tower time refute GNSS but never confirm it.
5. **Under GPS-only, intermittent jamming, two co-located tower clocks held.** At Edwards AFB the clock difference between two eNodeBs of different operators, on the same site, stayed stable for over 95 minutes [Kassas 2022]. Only GPS was jammed (Galileo and GLONASS were available), and the jammers ran 10 min on, 2 min off. The authors give three possible reasons: other constellations disciplining the towers, stable free-running oscillators, or the towers relocking to GPS in the gaps. So this says little about long or multi-constellation jamming, and nothing about sites far apart.
6. **ADS-B content is someone else's GNSS fix.** ADS-B is unauthenticated [Strohmeier 2015]. Aircraft spoofed over Russia were seen in published tracks [Lo 2025], and in a large regional dataset almost all confirmed position anomalies kept high integrity indicators [Park 2026]. So ADS-B fails with GNSS (ADR-0024), and NIC/NACp detect jamming far better than spoofing.
7. **Wi-Fi beacons can be cloned, and hashing doesn't help.** Location spoofing and database poisoning of Wi-Fi positioning date from 2009 [Tippenhauer 2009]. A cloned BSSID hashes to the same value, so ADR-0011's hashing protects privacy only. FTM ranging can be manipulated [Schepers 2021], but it needs a transmitter, so it is out of scope (ADR-0001).
8. **Coordinated and filter-aware attacks target the fusion.** Detecting coordinated attacks on opportunistic sources needs enough benign subsets [Liu 2024]. A filter-aware slow drift beat a production multi-sensor fusion in most attempts on real traces [Shen 2020], and a per-epoch χ² gate can be evaded [Zhang 2017]. Solution separation and cumulative monitors see slow ramps better [Blanch 2012; Tanil 2018].
9. **A tower with its own unknown clock adds no fault-detection redundancy.** In opportunistic ARAIM, towers sharing a clock term form one "SOP constellation" with one clock state; a constellation needs at least two measurements for its faults to be detectable, and a single pseudorange from a new constellation leaves the test statistic unchanged and raises the protection level [Jia 2023]. Calibrating and grouping tower clocks therefore buys redundancy, and creates a common-mode fault per group that must be named (ADR-0022).
10. **The research communities split along our seam.** Integrity groups model SoOP faults as multipath and assume benign transmitters [Jia 2023; Maaref 2022]; security groups model realistic SoOP attacks but compute no protection levels [Liu 2024; Liu 2025]. ADR-0021's pitch sits between them.

## 2. LTE tower ranging on an RTL-SDR

What our front end can realistically measure and identify (RSK-02, ADR-0022, ADR-0023).

1. **No published real-tower LTE TOA scatter from an RTL-SDR was found.** The best published results used GPSDO-locked USRPs at 10–20 MHz of bandwidth [Shamaei 2018a]. The closest hardware match, a UAV receiver sampling one channel at 3 Msps, reached 8.15 m RMSE with three eNodeBs [Shamaei 2018b]. Neither transfers to our dongles. The reports' a-priori figure for our pseudoranges is tens of metres per tower, `TBC` until the day-1 static capture (the standalone scenarios and the `easy` set use 20 m, `realistic` 50 m and `worst` 100 m, with multipath of the same size added in the last two; all `TBC`).
2. **The dongle decodes the cell's physical ID, not its global ID.** PSS and SSS give the PCI (3·N_ID1 + N_ID2) and the PBCH gives the MIB, all in the central 1.08 MHz [3GPP TS 36.211]. SIB1, which carries the global cell ID, needs the whole carrier. Identity therefore comes from the ISED registry plus an EARFCN/PCI scan (ADR-0023).
3. **Clocks group by the network builder, not the brand.** Bell and TELUS share one RAN that TELUS builds in Ottawa [Celentano 2020]. Clock offsets were similar within one operator and differed between operators (Winter et al., reported in [Lapin 2024]). [Winter 2024] itself compares only a few cell pairs and does not establish this: it says it can't yet tell whether what it saw holds generally for an operator.
4. **LTE clocks jump.** One of two tracked towers showed a frequency jump about every minute, and a linear clock fitted under GNSS held only for short coasts [Lapin 2024]. A learned clock prior has a shelf life (ADR-0022).
5. **Neighbouring FDD sites are only frequency-locked**, to ±50 ppb [3GPP TS 36.104], so each site keeps its own offset.
6. **Base/rover differencing cancels tower clocks** whatever their holdover class [Khalife 2023], but it does not protect absolute time against a wide-area spoof that pulls the base too (ADR-0020).
7. **Altitude adds towers and costs SINR.** Crewed-aircraft flights tracked over 100 eNodeBs, some beyond 100 km [Kassas 2024]. Our captures are ground-level, so the altitude part of the sim stays `literature`.
8. **No public dataset has commercial LTE pseudoranges with truth.** Sim validation rests on our own captures (ADR-0015).
9. **Legal basis.** We decode only broadcast synchronisation and system information, never user content (Radiocommunication Act s.9(2), ADR-0011). That is an engineering position, not legal advice (`safety.md`).

## 3. Unconventional PNT sources and angles

Which other sources are worth adding, and where Honeywell already is.

1. **Sort sources by how they fail with GPS:** independent, GNSS-timed, or GNSS-derived. Sources that fail for different reasons than GPS are worth more than more signals of the same kind (ADR-0024).
2. **Honeywell's alternative-navigation suite (HANA, October 2025)** covers vision, magnetic anomaly, LEO and celestial navigation, and lists "radios" without a product [Honeywell 2025]. Terrestrial communication signals with an integrity case, and timing, are the open niche (inference from the public list).
3. **Hostile emitters as beacons have one precedent.** JAM-ME homes on a jammer as a radio beacon, in simulation, with no integrity treatment [Tedeschi 2020]. The adversary controls the beacon's position, power and clock: in spoofer geolocation, a clock-correlated model gave far better containment than an uncorrelated one [Clements 2026]. Hence ADR-0025's guardrails.
4. **Starlink means listening, not subscribing.** A dish transmits (ADR-0001), and its local location API was withdrawn for most plans in May 2026 [ISPreview 2026]. Only the opportunistic downlink is open to us, so P13 is simulation.
5. **CHU shortwave time ended on 22 June 2026** [SWLing 2026], which led to ADR-0019.
6. **No MOPS exists for SoOP navigation.** RTCA SC-159's terms of reference cover GNSS equipment [RTCA 2026]. This frames the certification roadmap (`roadmap.md`).
7. **The base/rover differential method is published** [Khalife 2023]; a collaborative protection level built on it looked under-studied in a 2025 review of cooperative-positioning integrity [Nayak 2025].
8. **Ranking.** The report ranked twelve additions; ADR-0021 adopted them as P4–P13.

## Novelty check (#98)

ADR-0021 says "first" is never claimed and the wording stays "we found no published…" until the closest papers have been read in full. This section records that reading, done 2026-11-09, and a second reading the same day for the lead claims P3 and P5. "Read in full" means the whole open PDF or HTML was read; where only an abstract or a citing paper was available, the entry says so and draws no conclusion beyond it.

### What each paper does

**Jia, Khalife & Kassas, IEEE T-ITS 2023 (opportunistic ARAIM).** Read in full.
- Snapshot weighted least squares with baseline-ARAIM solution separation, giving HPL and VPL. Not a Kalman filter.
- Towers whose clocks share a common term, for example the same protocol and network provider, form one "SOP constellation" with one clock state. Each tower's initial offset is calibrated from GNSS before GNSS is lost. No drift states.
- Fault model: inherited from multi-constellation ARAIM. A single-source fault prior per tower and a constellation-wide fault prior per constellation, SOP constellations included (Appendix B). The theorems' proofs set the wide-fault prior to zero, and the experiment states only the single-source value (10⁻⁴) and σ_URA (3 m); the SOP wide-fault value in Table I did not survive text extraction.
- Faults are generic ranging faults. Towers are never adversarial, and no fault couples GNSS with the towers' GNSS-disciplined time.
- No time output, time protection level or time-spoof detection.
- Evidence: Monte Carlo (5,000 runs) and one UAV flight, 815 m in 220 s with 11 mapped LTE towers, recorded with a GPSDO-driven USRP at 10 MS/s.

**Maaref & Kassas, IEEE T-ITS 2022 (cellular RAIM with an IMU).** Read in full.
- EKF with an IMU, and per-tower clock bias and drift relative to the receiver. GNSS is unavailable throughout; tower positions are known.
- Faults are multipath and unmodelled biases from blocked line of sight. One fault at a time is detected with a windowed NIS chi-square test and excluded. HPL is computed.
- Ground vehicle, 825 m in a deep urban area; exclusion cut position RMSE by 66 %.
- No tower grouping, common-mode fault, adversarial tower, or GNSS cross-check.
- It cites the group's earlier work [Maaref 2020], in which a static **base with a known position estimated the tower clocks and shared them with the vehicle inside an integrity framework**. That paper was not retrievable; what it does is known only from this description.

**Maaref, Khalife & Kassas, IEEE T-ITS 2021 (aerial PL reduction).** Read in full.
- Snapshot WNLS fusing GNSS with cellular towers, treated as an extra "constellation". Each tower clock is a constant offset plus drift relative to the receiver. Solution-separation and least-squares RAIM, single faults.
- A tower fault is defined as a bias over 20 m, from a 5.97 m overbound fitted to UAV campaign data, which gives a fault probability of 8.08 × 10⁻⁴ per tower. This is a Gaussian tail value, not a count of observed faults; the authors call their SOP integrity parameters preliminary, a proof of concept, and say the value could be conservative or optimistic.
- UAV flight of 823 m: HPL fell by 82.4 % (GPS-based) and 74.6 % (GNSS-based) with towers added.
- No grouping, common-mode or adversarial faults, no timing.

**Kassas, Khalife, Abdallah & Lee, IEEE AES Magazine 2022 (Edwards AFB jamming).** Read in full.
- Experiment 1: a static receiver heard two eNodeBs (Verizon and T-Mobile) **on the same site** at about 60 dB J/S. Jammers cycled 10 min on, 2 min off; only GPS was jammed. The clock-bias difference stayed stable for over 95 min.
- The authors attribute this to other constellations disciplining the towers, to stable free-running oscillators, or to the towers relocking to GPS in the gaps, and call for tests with more than 8 h of jamming.
- Experiment 2: radio SLAM with one tower whose position was uncertain by kilometres gave 32 m RMSE where GPS-IMU gave 238 m.
- No integrity, protection level or spoofing.

**Liu & Papadimitratos, arXiv 2402.03449 (2024).** Read in full (HTML).
- Extends RAIM with a Gaussian mixture over position fixes from subsets: GNSS, Wi-Fi, cellular, onboard sensors. Opportunistic sources are untrusted; coordinated and uncoordinated attacks are analysed, and detection needs benign subsets to outnumber adversarial ones by a combinatorial condition.
- Opportunistic ranges are RSSI, SNR or TOA position fixes; base-station and access-point clocks are not modelled. No protection level or integrity risk. No timing attacks.
- Real walking trace from one phone, with GNSS attacks synthesised and rogue Wi-Fi access points simulated.

**Liu & Papadimitratos, arXiv 2510.27346 (2025).** Read in full (HTML, first 100,000 of 127,360 characters; the rest is references and appendix).
- Real, low-cost coordinated attacks: multi-band GNSS spoofing, Wi-Fi beacon replay with GNSS jamming (under $50), and network-traffic relay. Evaluated on Jammertest 2024 data and an isolated over-the-air testbed.
- Countermeasure: a RAIM-style consistency score over subset positions, thresholded on an ROC curve. No protection level.
- Rogue cellular base stations are in the adversary model but not implemented or evaluated. No tower clocks, timing attacks or cost-of-attack metric.

**Tedeschi, Oligeri & Di Pietro, IEEE Access 2020 (JAM-ME).** Read in full (open access, CC BY), 2026-11-09, by the owner's browser session.
- A drone with no other sensors (no IMU, explicitly) navigates on the received signal strength (RSS) of one jammer, using a free-space path-loss model with no multipath.
- **It calibrates the jammer while GPS still works:** a PID controller flies the drone along the jamming boundary at constant RSS, and a circle fit of its GPS positions locates the jammer (25 m error after about 190 m of boundary flight). Inside the jammed area it flies on RSS alone and stops when RSS reaches the value expected at the target.
- It assumes a constant-power, isotropic, stationary jammer. It names power-modulated and distance-adaptive jamming as the countermeasures that would defeat it, and doesn't defend against them.
- There is no filter, no uncertainty bound or protection level, no fault detection, and no fusion with other sources. Evidence is MATLAB simulation only; a real-drone testbed is mentioned as future work.

### Second reading (P3, P5 lead claims), 2026-11-09

Read after the owner moved the pitch to P3 and P5. **It changes both verdicts: P3 and P5 are each partly published** (see the table below). Neither paper found does what we do with towers, but the general ideas behind both claims are in print.

**Time protection levels for GNSS timing receivers (P5).**
- **Kirkko-Jaakkola et al., ION GNSS 2017.** Abstract only. Derives time protection level equations for a GNSS time solution from false-alarm and missed-detection probabilities and the number of simultaneous faults, and falls back to oscillator holdover when a fault cannot be excluded.
- **Lin, Su & Schön, ION GNSS+ 2024.** Abstract only (full text behind a sign-in). An integrity framework for GNSS time synchronisation with timing errors, sector-specific timing alert limits (finance, telecom) and timing protection levels; better clocks (CSAC) help.
- **Baweja, arXiv 2606.24210 (2026).** Read in full (HTML). Single-author preprint, not peer reviewed. We cited it before only for its JammerTest time pull; it is in fact **a conditional timing protection level under spoofing**: a detectability floor from a cross-satellite consistency monitor plus the oscillator's holdover uncertainty over the detection latency. It argues that no finite bound exists without an independent detector. Its only aiding during holdover is the local oscillator; no terrestrial or opportunistic source is used. It states that it carries no integrity-risk budget and is calibrated on one campaign, not validated.
- **Winter, Morrison & Sokolova, Sensors 2024.** Read (open full text). The "Winter et al." that Lapin 2024 cites for clocks clustering by operator is this group's work. Measures LTE and 5G sync-signal timing from a static receiver against a GNSS-disciplined rubidium clock, motivated by time holdover. No holdover through an outage is demonstrated, and no bound or protection level is computed. It compares only a few cell pairs and does not establish that clocks cluster by operator.

**GNSS time-spoof detection from other time sources (P3).**
- **Zhang, Spanghero & Papadimitratos, IEEE/ION PLANS 2020 (arXiv 2202.10891).** Read in part: abstract, related-technology survey and system model. Validates GNSS time against other time sources on a commodity platform: Wi-Fi beacon timestamps and NTP, after a survey that includes cellular network time. Shifts above about 24 µs (Wi-Fi) and 2 ms (NTP) are detected. The external sources are trusted as independent of GNSS; tower clocks are not calibrated, and no time bound is given.
- **Sharma, Owens & Kiernan, arXiv 2607.11398 (2026).** Read in full (HTML). Network-side: the operator correlates timing drift across base stations that share a grandmaster to detect a GNSS spoof of the grandmaster, in simulation (detection above 95 % for drifts over 0.5 ns/s). Nothing a passive user can measure, and no user-facing time bound.
- **Crosara, Tuninato, Ardizzon, Caparra, Lapin & Laurenti, IEEE SPAWC 2025.** Abstract only: no open copy found (Padova repository lists no file, no arXiv version). Attacks on 5G PRS positioning that alter propagation times and corrupt the estimated clock offset. An attack paper on network positioning, not a detector.
- **Bai, Sun, Dempster, Zhao & Feng, IEEE TAES 2024.** Abstract only. Detects and mitigates GNSS **position** spoofing with one 5G base station in a hybrid EKF, treating 5G as spoof-free. Not time-only, and the base station's GNSS-disciplined time is not considered.

**The rest of the list.**
- **Khalife, Maaref & Kassas, IEEE AES Magazine 2023** [Khalife 2023b] (*Opportunistic Autonomous Integrity Monitoring for Enhanced UAV Safety*). Read in full. Snapshot opportunistic ARAIM with a fault tree of up to three simultaneous faults; P_SOP 10⁻⁴ per tower and **P_const,SOP set to 0**, because no tower-group fault had been seen in their tests (they note this may be optimistic). Its experiment uses a base receiver for differential corrections and **assumes the base has a known position and clock and adds no common error**.
- **Maaref, Khalife & Kassas, ACM/IEEE ICCPS 2019** (work-in-progress abstract, the conference precursor of Maaref 2020). Read in full (2 pages). A base with a known state estimates tower clocks and shares them; EKF with NIS outlier detection. The base is not a fault.
- **Maaref & Kassas, IEEE T-IV 2020.** **Not retrievable**: no open copy found (author pages, NSF PAR, eScholarship hold only the 2019 precursor).
- **JAM-ME (Tedeschi, Oligeri & Di Pietro 2020).** Read in full on 2026-11-09 (see above).

### What they pre-empt in ADR-0021

| ID | Contribution | Pre-empted by | What is left that we did not find published |
| --- | --- | --- | --- |
| P0 | Attack library and report card | Not addressed by these papers | Unchanged; it was never a novelty claim |
| P1 | Calibrated tower clocks, site and builder grouping | **Largely**: Jia 2023 groups towers sharing a clock into a constellation and calibrates their offsets from GNSS | Two levels (site offset under a builder term), drift states, builder rather than brand as the key, and a calibration that is gated and rolled back when GNSS turns out to be spoofed |
| P2 | Solution separation with dependency-aware fault hypotheses | **Partly**: Jia 2023 already runs MHSS with tower faults and, formally, a constellation-wide fault per tower group; Khalife 2023b sets that group fault's prior to zero | A GNSS common-mode hypothesis that also contains GNSS-timed and GNSS-derived sources (ADR-0024); a non-zero builder-wide fault tied to timing holdover or capture; adversarial towers; a Kalman-filter bank with GNSS-free re-seeding |
| P3 | Calibrated clocks as a time-spoof and meaconing detector | **Partly**: checking GNSS time against other time sources is published (Zhang 2020: Wi-Fi and NTP, tens of µs to ms); operators detect grandmaster spoofing network-side (Sharma 2026); 5G aiding detects position spoofs (Bai 2024) | A passive user's detector built on **calibrated tower clocks**, sensitive well below Zhang's thresholds (sizes `TBC` until measured), that treats tower time as GNSS-timed so it can refute GNSS time but never confirm it, and catches a meacon's delay as a clock step. On `main` today the tower detector covers GNSS position, and GNSS time is tested against our own clock model; towers refuting GNSS time is planned. |
| P4 | Base/rover with collaborative integrity | **Partly**: a base estimating tower clocks inside an integrity framework is published (Maaref 2019, and Maaref 2020 as described by Maaref 2022); differencing itself is published [Khalife 2023] | The base as its own fault hypothesis (moved, clock step, lost, spoofed): both papers read assume the base is known and fault-free. An authenticated base link (ADR-0026). Maaref 2020 itself is still unread |
| P5 | Time protection level | **Partly**: time protection levels for GNSS timing receivers are published (Kirkko-Jaakkola 2017; Lin 2024), including one bounded by oscillator holdover under spoofing (Baweja 2026) | A time protection level for time **held by signals of opportunity** through a GNSS outage, whose bound accounts for the towers being GNSS-timed; and the timing Stanford plot and report card against it. No paper found does this. On `main` today the bound is the receiver-clock covariance, oscillator holdover in `ekf`; accounting for GNSS-timed towers is planned. |
| P6, P7, P9–P13 | Add-ons | Not addressed by these papers | Not checked here |
| P8 | Hostile emitter as a low-trust beacon | **Partly**: JAM-ME already uses a jammer as a navigation beacon and calibrates its position from GPS before entering the jammed area | A hostile emitter fused as one low-trust source among others in a filter, with gating, its own fault hypotheses (power modulation, moving, adaptive power: the very countermeasures JAM-ME names but doesn't handle) and a protection level. Nothing found does this |

Two further corrections to our earlier wording:
- **"Integrity groups assume benign towers" holds** for the three Kassas-group papers read: their faults are ranging errors, multipath and blocked line of sight. **"Security groups compute no protection levels" holds** for both KTH papers.
- **Edwards does not show "towers hold under jamming" in general.** It shows two co-located eNodeBs keeping their difference under GPS-only, intermittent jamming. Any slide citing it needs those three qualifiers.

### Still unread

Each could still change a verdict.
- Maaref & Kassas, IEEE T-IV 2020 (P4): not retrievable as open text.
- Full texts of Kirkko-Jaakkola 2017, Lin 2024 (P5), Crosara 2025 and Bai 2024 (P3): abstracts only.
- An IEEE Xplore and ION full-text search for "signals of opportunity" with timing integrity or time spoofing. The web and arXiv searches done (2026-11-09) found the papers above and nothing that computes a time protection level for SoOP-held time or detects time-only spoofs from calibrated tower clocks.

### Wording changes after the second reading (adopted 2026-11-09)

These change wording adopted earlier the same day. The owner adopted 1–3 on 2026-11-09 and ADR-0021 carries them; 4 is done in `protection.py`.

1. **P5.** From "Time protection level" to "A time protection level for time held by signals of opportunity, which accounts for the towers' GNSS-disciplined clocks". Pitch line: "Time protection levels exist for GNSS timing receivers (Kirkko-Jaakkola et al. 2017). We found no published one for time held by cell towers through a GNSS outage." On `main` today the bound is the receiver-clock covariance, oscillator holdover in `ekf`; accounting for GNSS-timed towers is planned. ADR-0021 carries that narrower wording.
2. **P3.** From "Calibrated clocks as a time-spoof and meaconing detector" to "Calibrated tower clocks as a passive time-spoof and meaconing detector that can refute GNSS time but never confirm it". Pitch line: "Checking GNSS time against other clocks is known (Zhang, Spanghero & Papadimitratos 2020, with Wi-Fi and NTP). We found no published detector that uses calibrated cell-tower clocks, or that treats tower time as failing with GPS." On `main` today the tower detector covers GNSS position, and GNSS time is tested against our own clock model; towers refuting GNSS time is planned. ADR-0021 carries that narrower wording.
3. **ADR-0021 Context** said the check found "nothing published for P3, P5 or P8". It now records P3, P5 and P8 as partly pre-empted, P8 after JAM-ME was read in full, with nothing found for their narrower wording.
4. **`src/pnt/integrity/protection.py`** said no standard defines a time protection level. That stays true of standards, but research definitions exist (above), so the docstring now cites Kirkko-Jaakkola 2017 and Baweja 2026.

### Wording changes (adopted 2026-11-09)

The owner adopted these on 2026-11-09, together with leading the pitch on P3 and P5; ADR-0021 now carries them.

1. **Context, second bullet.** Add that Jia et al. already group towers that share a clock into one constellation, calibrate them from GNSS, and allow a constellation-wide fault: "…adds no fault-detection redundancy, and towers that share a clock can be grouped and calibrated into one testable constellation (Jia, Khalife & Kassas 2023)."
2. **P1 wording.** From "Calibrated tower clocks with site and network-builder grouping" to "Two-level tower clocks (site under network builder) with drift, learned under a gated calibration that is rolled back if GNSS was lying; extends Jia et al.'s SOP constellations". Pitch line: "We build on opportunistic ARAIM's grouping; what we add is protecting the calibration from a spoofed GPS."
3. **P2 wording and role.** From "Solution-separation integrity with dependency-aware fault hypotheses, main novelty claim" to "Solution separation in which GNSS-timed and GNSS-derived sources fail with GPS, and each network builder's timing is its own fault". Pitch line: "Opportunistic ARAIM already lets a group of towers fail together. We found no published work that ties that group fault to the towers' GNSS timing, or that puts GNSS-dependent sources inside the GNSS fault." P2 is no longer the main claim: the pitch leads with P3 and P5.
4. **P4 wording.** From "Base/rover differencing with collaborative integrity" to "Base/rover differencing in which the base is itself monitored as a fault". Drop "collaborative integrity" as a novelty term until Maaref 2020 is read.
5. **Edwards on any slide.** "Two co-located towers of different operators kept their clock difference for over 95 minutes of intermittent, GPS-only jamming (Kassas et al. 2022)."
6. **P3, P5 and P8 claims keep the form** "we found no published…", now on the narrower wording in ADR-0021, with the unread papers above named in the speaker notes.

## References

Each entry gives authors, year, venue and a link. Organisation-authored sources name the organisation as author.

- [3GPP TS 36.104] 3GPP (ETSI TS 136 104), *E-UTRA Base Station radio transmission and reception*, §6.5.1, Release 8 onward (2008–), technical specification. https://www.etsi.org/deliver/etsi_ts/136100_136199/136104/
- [3GPP TS 36.211] 3GPP (ETSI TS 136 211), *E-UTRA Physical channels and modulation*, Release 8 onward (2008–), technical specification. https://www.etsi.org/deliver/etsi_ts/136200_136299/136211/
- [Bai 2024] Bai, Sun, Dempster, Zhao & Feng, *GNSS Spoofing Detection and Mitigation With a Single 5G Base Station Aiding*, 2024, IEEE TAES, doi:10.1109/TAES.2024.3382074. https://doi.org/10.1109/TAES.2024.3382074
- [Baweja 2026] Baweja, *A Conditional Timing Protection Level: Holdover-Limited Undetected Time Error Under GNSS Spoofing*, 2026, arXiv preprint 2606.24210. https://arxiv.org/abs/2606.24210
- [Blanch 2012] Blanch, Walter & Enge, *Advanced RAIM User Algorithm Description*, 2012, ION GNSS. https://web.stanford.edu/group/scpnt/gpslab/pubs/papers/Blanch_et_al_IONGNSS_2012_v2.pdf
- [Celentano 2020] Celentano, *Wireless Network Sharing, Canadian Style*, 2020, Inside Towers. https://insidetowers.com/?p=41263
- [Clements 2026] Clements et al., *Single-Satellite-Based Geolocation of Broadcast GNSS Spoofers from a Low Earth Orbit*, 2026, NAVIGATION 73. https://navi.ion.org/content/73/1/navi.750
- [Crosara 2025] Crosara, Tuninato, Ardizzon, Caparra, Lapin & Laurenti, *Spoofing Attacks on 5G PRS-Based Positioning*, 2025, IEEE SPAWC, doi:10.1109/SPAWC66079.2025.11143312. https://hdl.handle.net/11577/3565973
- [Erni 2022] Erni, Kotuliak, Leu, Roeschlin & Capkun, *AdaptOver: Adaptive Overshadowing Attacks in Cellular Networks*, 2022, ACM MobiCom. https://arxiv.org/pdf/2106.05039
- [Honeywell 2025] Honeywell Aerospace, *Honeywell launches new alternative navigation software*, 2025, press release. https://www.honeywellaerospace.com/us/en/about-us/press-release/2025/10/honeywell-launches-new-alternative-navigation-software-to-counte
- [ISPreview 2026] ISPreview, *Starlink shuts GPS location feature on satellite broadband service*, 2026, news. https://www.ispreview.co.uk/index.php/2026/04/starlink-shuts-gps-location-feature-on-satellite-broadband-service.html
- [Jia 2023] Jia, Khalife & Kassas, *Performance Analysis of Opportunistic ARAIM for Navigation With GNSS Signals Fused With Terrestrial Signals of Opportunity*, 2023, IEEE T-ITS 24(10), doi:10.1109/TITS.2023.3277393. https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Performance_analysis_of_opportunistic_ARAIM_for_navigation_with_GNSS_signals_fused_with_terrestrial_signals_of_opportunity.pdf
- [Kassas 2022] Kassas, Khalife, Abdallah & Lee, *I Am Not Afraid of the GPS Jammer: Resilient Navigation via Signals of Opportunity in GPS-Denied Environments*, 2022, IEEE Aerospace and Electronic Systems Magazine, doi:10.1109/MAES.2022.3154110. https://ece.osu.edu/sites/default/files/2022-09/I_am_not_afraid_of_the_GPS_jammer_resilient_navigation_via_signals_of_opportunity_in_GPS_denied_environments.pdf
- [Kassas 2024] Kassas et al., *I Can Hear You Loud and Clear: GNSS-Less Aircraft Navigation with Terrestrial Cellular Signals of Opportunity*, 2024, IEEE TAES. https://people.engineering.osu.edu/media/document/2025-01-02/kassas_i_can_hear_you_loud_and_clear_gnss_less_aircraft_navigation_with_terrestrial_cellular_signals_of_opportunity.pdf
- [Khalife 2023] Khalife & Kassas, *Differential Framework for Submeter-Accurate Vehicular Navigation with Cellular Signals*, 2023, IEEE T-IV. https://people.engineering.osu.edu/sites/default/files/2023-04/Kassas_Differential_Framework_for_Submeter_Accurate_Vehicular_Navigation_with_Cellular_Signals.pdf
- [Khalife 2023b] Khalife, Maaref & Kassas, *Opportunistic Autonomous Integrity Monitoring for Enhanced UAV Safety*, 2023, IEEE Aerospace and Electronic Systems Magazine, doi:10.1109/MAES.2022.3178664. https://people.engineering.osu.edu/sites/default/files/2023-05/Kassas_Opportunistic_Autonomous_Integrity_Monitoring_for_Enhanced_UAV_Safety.pdf
- [Kirkko-Jaakkola 2017] Kirkko-Jaakkola, Thombre, Honkala, Söderholm, Kaasalainen, Kuusniemi, Zelle, Veerman, Wallin, Aarmo & Boyero, *Receiver-level robustness concepts for EGNSS timing services*, 2017, ION GNSS, doi:10.33012/2017.15137. https://cris.vtt.fi/en/publications/receiver-level-robustness-concepts-for-egnss-timing-services/
- [Lapin 2024] Lapin et al., *Base Station Clock Offset of Cellular Measurements and Its Impact on Positioning*, 2024, IEEE TVT. https://spcomnav.uab.es/docs/journals/Base_Station_Clock_Offset_of_Cellular_Measurements_and_Its_Impact_on_Positioning.pdf
- [Lin 2024] Lin, Su & Schön, *Towards Integrity Monitoring for GNSS-Based Time Synchronization in Technical Applications*, 2024, ION GNSS+. https://www.ion.org/publications/abstract.cfm?articleID=19740
- [Liu 2024] Liu & Papadimitratos, *Extending RAIM with a Gaussian Mixture of Opportunistic Information*, 2024, arXiv preprint 2402.03449. https://arxiv.org/abs/2402.03449
- [Liu 2025] Liu & Papadimitratos, *Coordinated Position Falsification Attacks and Countermeasures for Location-Based Services*, 2025, arXiv preprint 2510.27346. https://arxiv.org/abs/2510.27346
- [Lo 2025] Lo, Liu, Ibrahim, Chen & Walter, *Observations of GNSS Spoofing in Russia in 2023–2024*, 2025, ION ITM. https://web.stanford.edu/group/scpnt/gpslab/pubs/papers/Lo_ION_ITM_2025_Russia_Spoofing.pdf
- [Ludant 2021] Ludant & Noubir, *SigUnder: a Stealthy 5G Low Power Attack and Defenses*, 2021, ACM WiSec. https://dl.acm.org/doi/pdf/10.1145/3448300.3467817
- [Maaref 2019] Maaref, Khalife & Kassas, *Pseudorange measurement outlier detection for navigation with cellular signals* (work-in-progress abstract), 2019, ACM/IEEE ICCPS, doi:10.1145/3302509.3313334. https://escholarship.org/uc/item/269713kp
- [Maaref 2020] Maaref & Kassas, *Measurement Characterization and Autonomous Outlier Detection and Exclusion for Ground Vehicle Navigation With Cellular Signals*, 2020, IEEE Transactions on Intelligent Vehicles 5(4). https://doi.org/10.1109/TIV.2020.2991947 (not read: see the novelty check)
- [Maaref 2021] Maaref, Khalife & Kassas, *Aerial Vehicle Protection Level Reduction by Fusing GNSS and Terrestrial Signals of Opportunity*, 2021, IEEE T-ITS 22(9). https://doi.org/10.1109/TITS.2021.3095184 ; open copy https://par.nsf.gov/servlets/purl/10321488
- [Maaref 2022] Maaref & Kassas, *Autonomous Integrity Monitoring for Vehicular Navigation With Cellular Signals of Opportunity and an IMU*, 2022, IEEE T-ITS. https://people.engineering.osu.edu/sites/default/files/2022-10/Kassas_Autonomous_integrity_monitoring_for_vehicular_navigation_with_cellular_signals_of_opportunity_and_an_IMU.pdf
- [Nayak 2025] Nayak & Barth, *The Role of Integrity Monitoring in Connected and Automated Vehicles: Current State-of-Practice and Future Directions*, 2025, arXiv preprint 2502.04874 (DOI 10.1109/MITS.2025.3589632). https://arxiv.org/abs/2502.04874
- [Park 2026] Park, Lee & Son, *Track-Consistency-Based GNSS RFI Monitoring Using Crowdsourced ADS-B Sensor Networks*, 2026, arXiv preprint 2607.09700. https://arxiv.org/abs/2607.09700
- [Rao 2017] Rao, Ha, Marojevic & Reed, *LTE PHY Layer Vulnerability Analysis and Testing Using Open-Source SDR Tools*, 2017, IEEE MILCOM. https://ar5iv.labs.arxiv.org/html/1708.05887
- [RNT 2016] RNT Foundation (Chronos case study), *26 January 2016 GPS event*, 2016, report. https://rntfnd.org/wp-content/uploads/26-January-2016-GPS-Event.pdf
- [RTCA 2026] RTCA, *SC-159 Terms of Reference, Rev 26*, 2026, terms of reference. https://www.rtca.org/wp-content/uploads/2026/06/SC-159-TOR-Rev-26-Approved-2026-06-23.pdf
- [Ruffini 2021] Ruffini, Johansson, Pohlman & Sandgren, *5G synchronization requirements and solutions*, 2021, Ericsson Technology Review. https://www.ericsson.com/en/reports-and-papers/ericsson-technology-review/articles/5g-synchronization-requirements-and-solutions
- [Schepers 2021] Schepers, Singh & Ranganathan, *Here, There, and Everywhere: Security Analysis of Wi-Fi Fine Timing Measurement*, 2021, ACM WiSec. https://aanjhan.com/assets/schepers_ftm_wisec21.pdf
- [Shaik 2016] Shaik, Borgaonkar, Asokan, Niemi & Seifert, *Practical attacks against privacy and availability in 4G/LTE mobile communication systems*, 2016, NDSS. https://www.arxiv.org/pdf/1510.07563
- [Shamaei 2018a] Shamaei & Kassas, *LTE receiver design and multipath analysis for navigation in urban environments*, 2018, NAVIGATION 65(4). https://people.engineering.osu.edu/sites/default/files/2022-10/Kassas_LTE_Receiver_Design_and_Multipath_Analysis_for_Navigation_in_Urban_Environments.pdf
- [Shamaei 2018b] Shamaei, Khalife & Kassas, *Exploiting LTE Signals for Navigation: Theory to Implementation*, 2018, IEEE TWC 17(4). https://escholarship.org/uc/item/5rw6t83d
- [Sharma 2026] Sharma, Owens & Kiernan, *GNSS Spoofing Detection in TDD Networks: A 3GPP Standards-Based Security Framework*, 2026, arXiv preprint 2607.11398. https://arxiv.org/pdf/2607.11398
- [Shen 2020] Shen, Won, Chen & Chen, *Drift with Devil: Security of Multi-Sensor Fusion based Localization in High-Level Autonomous Driving under GPS Spoofing*, 2020, USENIX Security. https://arxiv.org/abs/2006.10318
- [Singh 2022] Singh, Roeschlin, Ranganathan, Capkun et al., *V-Range: Enabling Secure Ranging in 5G Wireless Networks*, 2022, NDSS. https://www.ndss-symposium.org/wp-content/uploads/2022-151-paper.pdf
- [Strohmeier 2015] Strohmeier, Lenders & Martinovic, *On the Security of the Automatic Dependent Surveillance-Broadcast Protocol*, 2015, IEEE Communications Surveys & Tutorials. https://arxiv.org/pdf/1307.3664
- [SWLing 2026] SWLing Post, *CHU closure on June 22, 2026*, 2026, blog. https://swling.com/blog/2026/06/chu-closure-on-june-22-2026/
- [Tanil 2018] Tanil, Khanafseh, Joerger & Pervan, *An INS Monitor to Detect GNSS Spoofers Capable of Tracking Vehicle Position*, 2018, IEEE TAES 54(1), doi:10.1109/TAES.2017.2739924. https://doi.org/10.1109/TAES.2017.2739924
- [Tedeschi 2020] Tedeschi, Oligeri & Di Pietro, *Leveraging Jamming to Help Drones Complete Their Mission* (JAM-ME), 2020, IEEE Access 8, doi:10.1109/ACCESS.2019.2963105. https://pietrotedeschi.github.io/publication/tedeschi-2019-leveraging
- [Tippenhauer 2009] Tippenhauer, Rasmussen, Pöpper & Čapkun, *Attacks on public WLAN-based positioning systems*, 2009, ACM MobiSys. https://dl.acm.org/doi/abs/10.1145/1555816.1555820
- [Winter 2024] Winter, Morrison & Sokolova, *Analysis of 5G and LTE Signals for Opportunistic Navigation and Time Holdover*, 2024, Sensors 24(1):213, doi:10.3390/s24010213. https://pmc.ncbi.nlm.nih.gov/articles/PMC10781334/
- [Yang 2019] Yang, Bae, Son, Kim, Kim & Kim, *Hiding in Plain Signal: Physical Signal Overshadowing Attack on LTE*, 2019, USENIX Security. https://www.usenix.org/system/files/sec19-yang-hojoon.pdf
- [Zhang 2017] Zhang, Zhou & Tokekar, *Strategies to Inject Spoofed Measurement Data to Mislead Kalman Filter*, 2017, arXiv preprint 1710.02442. https://arxiv.org/pdf/1710.02442
- [Zhang 2020] Zhang, Spanghero & Papadimitratos, *Protecting GNSS-based Services using Time Offset Validation*, 2020, IEEE/ION PLANS, doi:10.1109/PLANS46316.2020.9110224. https://arxiv.org/abs/2202.10891
