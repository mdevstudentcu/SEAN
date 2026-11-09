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

1. **No published real-tower LTE TOA scatter from an RTL-SDR was found.** The best published results used GPSDO-locked USRPs at 10–20 MHz of bandwidth [Shamaei 2018a]. The closest hardware match, a UAV receiver sampling one channel at 3 Msps, reached 8.15 m RMSE with three eNodeBs [Shamaei 2018b]. Neither transfers to our dongles. The reports' a-priori figure for our pseudoranges is tens of metres per tower, `TBC` until the day-1 static capture (the scenarios use 20 m, also `TBC`).
2. **The dongle decodes the cell's physical ID, not its global ID.** PSS and SSS give the PCI (3·N_ID1 + N_ID2) and the PBCH gives the MIB, all in the central 1.08 MHz [3GPP TS 36.211]. SIB1, which carries the global cell ID, needs the whole carrier. Identity therefore comes from the ISED registry plus an EARFCN/PCI scan (ADR-0023).
3. **Clocks group by the network builder, not the brand.** Bell and TELUS share one RAN that TELUS builds in Ottawa [Celentano 2020]. Clock offsets were similar within one operator and differed between operators (Winter et al., reported in [Lapin 2024]).
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

ADR-0021 says "first" is never claimed and the wording stays "we found no published…" until the closest papers have been read in full. This section records that reading, done 2026-11-09. "Read in full" means the whole open PDF or HTML was read; where only an abstract or a citing paper was available, the entry says so and draws no conclusion beyond it.

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
- A tower fault is defined as a bias over 20 m, from a 5.97 m overbound fitted to UAV campaign data, which gives a fault probability of 8.08 × 10⁻⁴ per tower.
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

**Tedeschi, Oligeri & Di Pietro, IEEE Access 2020 (JAM-ME).** **Full text not retrieved**: IEEE Access is open access, but every automated fetch was blocked. From the abstract and the authors' page only: a drone estimates a jammer's position from the jamming signal and uses it as a radio beacon to reach a target, in simulation, with about 70 % mission overhead under conservative assumptions. Whether it has any uncertainty bound or deceptive-jammer model is unknown until a person reads the PDF.

### What they pre-empt in ADR-0021

| ID | Contribution | Pre-empted by | What is left that we did not find published |
| --- | --- | --- | --- |
| P0 | Attack library and report card | Not addressed by these papers | Unchanged; it was never a novelty claim |
| P1 | Calibrated tower clocks, site and builder grouping | **Largely**: Jia 2023 groups towers sharing a clock into a constellation and calibrates their offsets from GNSS | Two levels (site offset under a builder term), drift states, builder rather than brand as the key, and a calibration that is gated and rolled back when GNSS turns out to be spoofed |
| P2 | Solution separation with dependency-aware fault hypotheses | **Partly**: Jia 2023 already runs MHSS with tower faults and, formally, a constellation-wide fault per tower group | A GNSS common-mode hypothesis that also contains GNSS-timed and GNSS-derived sources (ADR-0024); the builder-wide fault tied to timing holdover or capture; adversarial towers; a Kalman-filter bank with GNSS-free re-seeding |
| P3 | Calibrated clocks as a time-spoof and meaconing detector | Not by these papers. Sharma 2026 and the Padova work are still unread (see below) | A user-side, passive detector of time-only spoofs from calibrated tower clocks |
| P4 | Base/rover with collaborative integrity | **Partly**: Maaref 2022 describes earlier work [Maaref 2020] with a base estimating tower clocks inside an integrity framework; differencing itself is published [Khalife 2023] | The base as its own fault hypothesis (moved, clock step, lost, spoofed), and an authenticated base link (ADR-0026). Confirm once Maaref 2020 is read |
| P5 | Time protection level | Not by these papers | Unchanged |
| P6, P7, P9–P13 | Add-ons | Not addressed by these papers | Not checked here |
| P8 | Hostile emitter as a low-trust beacon | JAM-ME, abstract only | A fused, gated, fault-hypothesised hostile beacon. Unchanged until JAM-ME is read in full |

Two further corrections to our earlier wording:
- **"Integrity groups assume benign towers" holds** for the three Kassas-group papers read: their faults are ranging errors, multipath and blocked line of sight. **"Security groups compute no protection levels" holds** for both KTH papers.
- **Edwards does not show "towers hold under jamming" in general.** It shows two co-located eNodeBs keeping their difference under GPS-only, intermittent jamming. Any slide citing it needs those three qualifiers.

### Still unread

Each could still pre-empt a claim; none was read for this check.
- Maaref & Kassas, IEEE T-IV 2020 (base-assisted integrity): P4. Not retrievable as open text.
- Sharma, Owens & Kiernan, arXiv 2607.11398, and Ardizzon & Laurenti (Padova, 2025): P3 (network-side and propagation-time attacks on clock estimation).
- Kassas group, *Opportunistic Autonomous Integrity Monitoring for Enhanced UAV Safety*: P2.
- An IEEE Xplore and ION full-text search for "signals of opportunity" with "spoofing", "integrity" or "holdover", 2023–2026, as the hostile-SoOP report recommended.

### Proposed wording changes (pending owner)

These are proposals for the owners. ADR-0021's decision is not edited here; a change to it goes through its owners (rule 4 in `README.md`).

1. **Context, second bullet.** Add that Jia et al. already group towers that share a clock into one constellation, calibrate them from GNSS, and allow a constellation-wide fault: "…adds no fault-detection redundancy, and towers that share a clock can be grouped and calibrated into one testable constellation (Jia, Khalife & Kassas 2023)."
2. **P1 wording.** From "Calibrated tower clocks with site and network-builder grouping" to "Two-level tower clocks (site under network builder) with drift, learned under a gated calibration that is rolled back if GNSS was lying; extends Jia et al.'s SOP constellations". Pitch line: "We build on opportunistic ARAIM's grouping; what we add is protecting the calibration from a spoofed GPS."
3. **P2 wording and role.** From "Solution-separation integrity with dependency-aware fault hypotheses, main novelty claim" to "Solution separation in which GNSS-timed and GNSS-derived sources fail with GPS, and each network builder's timing is its own fault". Pitch line: "Opportunistic ARAIM already lets a group of towers fail together. We found no published work that ties that group fault to the towers' GNSS timing, or that puts GNSS-dependent sources inside the GNSS fault." Whether P2 stays the main claim is open question 1.
4. **P4 wording.** From "Base/rover differencing with collaborative integrity" to "Base/rover differencing in which the base is itself monitored as a fault". Drop "collaborative integrity" as a novelty term until Maaref 2020 is read.
5. **Edwards on any slide.** "Two co-located towers of different operators kept their clock difference for over 95 minutes of intermittent, GPS-only jamming (Kassas et al. 2022)."
6. **P3, P5 and P8 wording stays** "we found no published…", with the unread papers above named in the speaker notes.

## References

Each entry gives authors, year, venue and a link. Organisation-authored sources name the organisation as author.

- [3GPP TS 36.104] 3GPP (ETSI TS 136 104), *E-UTRA Base Station radio transmission and reception*, §6.5.1, Release 8 onward (2008–), technical specification. https://www.etsi.org/deliver/etsi_ts/136100_136199/136104/
- [3GPP TS 36.211] 3GPP (ETSI TS 136 211), *E-UTRA Physical channels and modulation*, Release 8 onward (2008–), technical specification. https://www.etsi.org/deliver/etsi_ts/136200_136299/136211/
- [Baweja 2026] Baweja, analysis of a JammerTest 2024 time pull (topic; exact title not recorded), 2026, arXiv preprint 2606.24210. https://arxiv.org/pdf/2606.24210
- [Blanch 2012] Blanch, Walter & Enge, *Advanced RAIM User Algorithm Description*, 2012, ION GNSS. https://web.stanford.edu/group/scpnt/gpslab/pubs/papers/Blanch_et_al_IONGNSS_2012_v2.pdf
- [Celentano 2020] Celentano, *Wireless Network Sharing, Canadian Style*, 2020, Inside Towers. https://insidetowers.com/?p=41263
- [Clements 2026] Clements et al., *Single-satellite geolocation of GNSS spoofers*, 2026, NAVIGATION 73. https://navi.ion.org/content/73/1/navi.750
- [Erni 2022] Erni, Kotuliak, Leu, Roeschlin & Capkun, *AdaptOver: Adaptive Overshadowing Attacks in Cellular Networks*, 2022, ACM MobiCom. https://arxiv.org/pdf/2106.05039
- [Honeywell 2025] Honeywell Aerospace, *Honeywell launches new alternative navigation software*, 2025, press release. https://www.honeywellaerospace.com/us/en/about-us/press-release/2025/10/honeywell-launches-new-alternative-navigation-software-to-counte
- [ISPreview 2026] ISPreview, *Starlink shuts GPS location feature on satellite broadband service*, 2026, news. https://www.ispreview.co.uk/index.php/2026/04/starlink-shuts-gps-location-feature-on-satellite-broadband-service.html
- [Jia 2023] Jia, Khalife & Kassas, *Performance Analysis of Opportunistic ARAIM for Navigation With GNSS Signals Fused With Terrestrial Signals of Opportunity*, 2023, IEEE T-ITS 24(10), doi:10.1109/TITS.2023.3277393. https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Performance_analysis_of_opportunistic_ARAIM_for_navigation_with_GNSS_signals_fused_with_terrestrial_signals_of_opportunity.pdf
- [Kassas 2022] Kassas, Khalife, Abdallah & Lee, *I Am Not Afraid of the GPS Jammer: Resilient Navigation via Signals of Opportunity in GPS-Denied Environments*, 2022, IEEE Aerospace and Electronic Systems Magazine, doi:10.1109/MAES.2022.3154110. https://ece.osu.edu/sites/default/files/2022-09/I_am_not_afraid_of_the_GPS_jammer_resilient_navigation_via_signals_of_opportunity_in_GPS_denied_environments.pdf
- [Kassas 2024] Kassas et al., *I Can Hear You Loud and Clear: GNSS-Less Aircraft Navigation with Terrestrial Cellular Signals of Opportunity*, 2024, IEEE TAES. https://people.engineering.osu.edu/media/document/2025-01-02/kassas_i_can_hear_you_loud_and_clear_gnss_less_aircraft_navigation_with_terrestrial_cellular_signals_of_opportunity.pdf
- [Khalife 2023] Khalife & Kassas, *Differential Framework for Submeter-Accurate Vehicular Navigation with Cellular Signals*, 2023, IEEE T-IV. https://people.engineering.osu.edu/sites/default/files/2023-04/Kassas_Differential_Framework_for_Submeter_Accurate_Vehicular_Navigation_with_Cellular_Signals.pdf
- [Lapin 2024] Lapin et al., *Base Station Clock Offset of Cellular Measurements and Its Impact on Positioning*, 2024, IEEE TVT. https://spcomnav.uab.es/docs/journals/Base_Station_Clock_Offset_of_Cellular_Measurements_and_Its_Impact_on_Positioning.pdf
- [Liu 2024] Liu & Papadimitratos, *Extending RAIM with a Gaussian Mixture of Opportunistic Information*, 2024, arXiv preprint 2402.03449. https://arxiv.org/abs/2402.03449
- [Liu 2025] Liu & Papadimitratos, *Coordinated Position Falsification Attacks and Countermeasures for Location-Based Services*, 2025, arXiv preprint 2510.27346. https://arxiv.org/abs/2510.27346
- [Lo 2025] Lo, Liu, Ibrahim, Chen & Walter, *Observations of GNSS Spoofing in Russia in 2023–2024*, 2025, ION ITM. https://web.stanford.edu/group/scpnt/gpslab/pubs/papers/Lo_ION_ITM_2025_Russia_Spoofing.pdf
- [Ludant 2021] Ludant & Noubir, *SigUnder: a Stealthy 5G Low Power Attack and Defenses*, 2021, ACM WiSec. https://dl.acm.org/doi/pdf/10.1145/3448300.3467817
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
- [Tanil 2018] Tanil, Khanafseh, Joerger & Pervan, *An INS Monitor to Detect GNSS Spoofers Capable of Tracking Vehicle Position*, 2018, IEEE TAES. https://www.aoe.vt.edu/content/dam/aoe_vt_edu/people/faculty/joerger/publications/an_ins_monitor_to_detect_gnss_spoofers_capable_of_tracking_vehicle_position.pdf
- [Tedeschi 2020] Tedeschi, Oligeri & Di Pietro, *Leveraging Jamming to Help Drones Complete Their Mission* (JAM-ME), 2020, IEEE Access 8, doi:10.1109/ACCESS.2019.2963105. https://pietrotedeschi.github.io/publication/tedeschi-2019-leveraging
- [Tippenhauer 2009] Tippenhauer, Rasmussen, Pöpper & Čapkun, *Attacks on public WLAN-based positioning systems*, 2009, ACM MobiSys. https://dl.acm.org/doi/abs/10.1145/1555816.1555820
- [Yang 2019] Yang, Bae, Son, Kim, Kim & Kim, *Hiding in Plain Signal: Physical Signal Overshadowing Attack on LTE*, 2019, USENIX Security. https://www.usenix.org/system/files/sec19-yang-hojoon.pdf
- [Zhang 2017] Zhang, Zhou & Tokekar, *Strategies to Inject Spoofed Measurement Data to Mislead Kalman Filter*, 2017, arXiv preprint 1710.02442. https://arxiv.org/pdf/1710.02442
