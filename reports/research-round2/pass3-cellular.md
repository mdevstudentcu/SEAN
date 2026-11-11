# Cellular signals: saturation pass 3 (strict 8-dry rule)

Date 2026-11-11. Reports only what is new or corrected relative to `reports/sources-research-20261111.md`,
`research-round2/radio.md` and `research-round2/radio-pass2-cellular.md` (cited below as R1, P1 and P2). Labels: [V]
read today in the primary source, [S] search snippet or secondary page, [M] memory, [C] own arithmetic. Flags: TX,
NET, OPTICAL; no flag = passive, stand-alone.

Work in progress. Topics are written as they finish.

## A. Radio SLAM, mapper/navigator, tower maps

Stopped at 90 searches without 8 dry in a row (longest dry run 7, searches 43-49 then broken by a CellMapper
comparison; later runs of 5 and 5). Search log (n = new in-scope item, d = dry; items outside the topic's scope,
e.g. robotics range-only SLAM, mmWave ISAC, integrity, were logged but counted dry):
1-10 n n d n n d n n d d; 11-20 d n n d n d d n n d; 21-30 d d d n n n n n d d; 31-40 n d d n n d d d d d;
41-50 n d d d d d d d n d (CPS poster numbers); 51-60 d n d d n n d d d d; 61-70 d d d d n d d d d n;
71-80 n d d d d d n d d d; 81-90 n n d d d d d n d n.
Items from search 60 onward were patents, vendor claims, trade-press anecdotes or adjacent fields; no new
peer-reviewed cellular radio SLAM result with numbers appeared after search 77 (A22).
- A26 Late items [S]: GPS-aided INS on the NAVFEST ground vehicle grew to about 238 m RMSE over 5 km in 180 s
  (baseline for P2 E1's 29.4 / 32.2 m radio SLAM). Ghasemi & Parekh, "Deep Learning based Localization of LTE
  eNodeBs from Large Crowdsourced Smartphone Datasets", IEEE VTC2021-Spring, DOI
  10.1109/VTC2021-Spring51267.2021.9448857: restricted Boltzmann machine features, no number found. Patents US
  9900749 / US 10257650 "Detection of infrastructure changes in opportunity signal data": classify each source as
  new / compatible / indifferent / incompatible against stored statistics and replace incompatible entries, i.e.
  automated detection of moved or retired transmitters. ISED has required 54 site-data fields since 31 Oct 2024; a
  commercial Canadian service (Loxcel) indexes sites by operator-prefixed PCI.
- Judgement A: see section 5.
- Not found in A: any peer-reviewed metre-level comparison of OpenCelliD, CellMapper, MLS or ISED coordinates
  against surveyed masts; any non-Kassas airborne radio SLAM with real cellular towers; any 2025-2026 UAV radio
  SLAM flight; the full text of the Arizabaleta-Diez, Morales collaborative, Yang waypoint and Driusso papers (all
  PDFs came back as compressed binary or refused connection).

## B. Air-to-ground cellular ranging vs altitude

Stopped at 58 searches without 8 dry in a row (longest dry run 7, searches 43-49, broken by the AAU WCNC 2018
neighbour-cell statistic; the final run reached 5 dry before the Ericsson RSRP-gap numbers). Log: 1-10 d n d n d
n n n n n; 11-20 n n d n d n d n d n; 21-30 n d d d n d d d n d; 31-40 n n d n d d d n n d; 41-50 d d n d d d d d
d n; 51-58 d d d d d d (5 dry) n. Late "new" items were channel-statistic numbers, not new methods. Still no
altitude-binned TOA/pseudorange error distribution from a real cellular downlink exists in the open literature.

- B1 Air-ground channel from dedicated ground stations (not down-tilted cell towers): Matolak & Sun, "Air-Ground
  Channel Characterization for Unmanned Aircraft Systems, Part III: The Suburban and Near-Urban Environments", IEEE
  TVT 2017, DOI 10.1109/TVT.2017.2659651 [V abstract]: Rician K 12 dB (near-urban) / 14 dB (suburban) at L-band
  (968 MHz), 27.4 / 28.5 dB at C-band (5060 MHz); C-band RMS delay spread typically 10-60 ns, maximum about 4 µs.
  Part II hilly/mountainous [S]: K about 12.8 dB L-band, 29.4 dB C-band; delay spread mostly about 10 ns, peaks
  1 µs (hilly) and 180 ns (mountainous). NASA S-3B flights, seven ground environments [S]. Sim use [C]: an upper
  bound on channel quality for a drone seen from an up-looking antenna; real cell towers (down-tilted, P2 B1) are
  worse (K 7.6 dB, 80-110 ns above 15 m). Long-delay (µs) echoes from terrain exist and a ranging receiver must
  not lock to them.
- B2 LOS probability models beyond TR 36.777 [S]: the Al-Hourani sigmoid P_LOS = 1/(1 + a·exp(-b(θ - a))) with θ
  the elevation angle in degrees; commonly quoted (a, b): suburban 4.88, 0.43; urban 9.61, 0.16; dense urban 11.95,
  0.136; derived from ITU-R P.1410 built-up parameters (α, β, γ): suburban 0.1, 750, 8; urban 0.3, 500, 15; dense
  urban 0.5, 300, 20 (high-rise γ given as 20 or 50 in different sources). A 2025 ray-traced refit (arXiv 2501.14389)
  gives suburban 3.44, 0.108; urban 6.55, 0.069; dense urban 9.67, 0.064, so the classic values are optimistic for
  Manhattan-like layouts. Sim use [C]: for a drone at 30-120 m and towers 1-10 km away, elevation angles are only
  0.2-5°, where every sigmoid gives low LOS probability; TR 36.777's "100 % LOS above 100 m" applies only to UMa
  geometry and should not be used for a distant tower at low elevation.
- B3 AERPAW curated dataset catalogue: Fahim Raouf et al. (21 authors, NC State), "Curated Wireless Datasets for
  Aerial Network Research", arXiv 2510.08752 (Oct 2025, v2 Mar 2026) [V abstract]: signal-, power- and KPI-level
  aerial datasets with harmonised metadata and post-processing scripts; altitudes, licences and links not on the
  abstract page. One-stop source for the altitude model calibration P2 B14 suggested. Owner go-ahead needed.
- B4 Ericsson field trials: "Mobile-Network Connected Drones: Field Trials, Simulations, and Design Insights",
  arXiv 1801.10508 [S]: commercial LTE, field trials to 150 m, simulations to 300 m; SINR and RSRQ fall with
  height across the range. Median RSRP gap between the serving cell and the strongest neighbour: 6.5 dB on the
  ground, 2.8 dB at 50 m, 1.6 dB at 150 m [S]. Uplink side (AAU, rural Denmark, 800 MHz, 50 live cells): an
  aerial transmitter raised interference over thermal by up to 7.7 dB in surrounding cells [S] (TX case, for
  context only). Sim use [C]: at 50-150 m the strongest and second-strongest co-channel cells are typically within
  2-3 dB, so a PSS/SSS correlator sees two comparable peaks most of the time; the receiver must separate cells by
  PCI code (and cancel), not by "strongest wins".
- B5 Sandia / Ohio State weather-balloon payload (ION GNSS+ 2024, Baltimore) [V news release, Oct 2024]: LTE
  "signal beacons" detected at the 82,000 ft (25 km) peak; data still being processed; no C/N0 or count published.
  Shows cellular sync signals reach far above the 15-300 m band; the limit at altitude is interference and
  geometry, not reach.
- B6 Directional vs omni base antenna, by height. Rodríguez-Piñeiro, Domínguez-Bolaño, Cai, Huang, Yin,
  "Air-to-Ground Channel Characterization for Low-Height UAVs in Realistic Network Deployments", arXiv 2007.11502
  (IEEE Trans. Antennas Propag.) [V, full HTML tables]. Dedicated LTE-like sounder, 2.5 GHz, 9 MHz occupied, BS
  at 15 m, directional 12 dBi sector at 0° downtilt vs 0 dBi omni; UAV at 15/25/35/45/60/75/90/105 m, 100-500 m
  horizontal range, two suburban routes.
  - K-factor (dB, mean): omni 11-16 at every height; directional 5.5 (15 m, LOS road) and 8-13 above, lower and
    more variable than omni at most heights; obstructed-LOS at 15 m: 4.6 (omni) / 1.8 (directional).
  - RMS delay spread: log10 means -6.4 to -6.9, i.e. about 120 to 380 ns [C]; no clear height trend.
  - Path loss: with the directional antenna the log-distance fit breaks above 45 m (fitted exponent 0.3-1.9,
    because the drone moves between main lobe and side lobes); shadow σ stays 1.6-3.1 dB at every height
    (omni falls 1.6 -> 0.8 dB).
  - Authors' conclusion: with a sector antenna the channel depends more on the antenna pattern than on height;
    the UAV mostly receives side-lobe energy.
  - Sim implication [C]: confirms P2 B1/B7 with a controlled comparison: model per-tower received power from a
    vertical pattern with side lobes, K about 8-13 dB with σ about 2 dB above 25 m, and delay spread about 100-400 ns
    (30-120 m of unresolved multipath for a 1-2 MHz PSS/SSS ranging bandwidth, so a positive range bias of metres
    to tens of metres per tower), not falling with height in the 15-105 m band.
- B7 TR 36.777 fast-fading alternatives [S, arXiv 1809.01752 survey]: three alternatives agreed in Rel-15: a CDL
  model with UAV-specific features (e.g. a specular reflection off the building roof in UMa), adjusted means and
  spreads of the large-scale parameters, or the simplest, the ground model with K fixed at 15 dB. A separate
  measurement summary reports K rising from about 5 dB at low altitude to over 15 dB at higher elevation [S]. TR
  36.777 Annex B equations still not read (ETSI PDF 404 in P2).
- B8 Seeing many cells at altitude needs successive cancellation [S, patents US 9014154, US 9544083, US 9924408, US
  10243683]: detect the strongest PSS/SSS, estimate its channel, subtract it, search again (successive or parallel
  interference cancellation); cancelling a strong cell can also erase a weaker cell that shares an identifier
  component. The near-far problem in an LTE navigation receiver ("only the strongest up to three PSSs") is already
  in the Kassas literature. No test of cancellation-based cell search from an airborne receiver was found. Sim
  implication [C]: "cells heard" in P2 B4/B6 (17 at 120 m) is what a commercial modem with cancellation reports; a
  plain correlator on one RTL-SDR channel will lock fewer, so the sim should model detectable cells as those within
  X dB (TBD, about 10-15 dB for SIC, 3-6 dB without) of the strongest co-channel cell.
- B9 AERIQ (Maeng, Ozdemir, Güvenç, Sichitiu, Dutta, Mushi), arXiv 2210.07433 [V abstract]: SDR I/Q capture
  framework flown on AERPAW UAVs, one testbed eNB at 3.51 GHz; RSRP vs altitude, coherence bandwidth and time vs
  altitude and distance, kriging 3-D RSRP maps; raw I/Q and software released. Single private eNB, so no
  inter-cell timing.
- B10 Angular spread at the drone. Izydorczyk, Tavares, Berardinelli, Bucur, Mogensen, "Angular Distribution of
  Cellular Signals for UAVs in Urban and Rural Scenarios", EuCAP 2019 (AAU) [S]: live LTE, ground to 40 m, SAGE;
  angular spread falls below 30° with height as LOS dominates; mean AoA deviates from the tower direction by up to
  55° (urban) and up to 20° (rural); urban multipath persists about 20 m above rooftops. Relevance [C]: sets the
  bearing-bias tail for any on-drone AoA (P1 topic 6) and supports a non-negligible urban NLOS term up to roof+20 m.
  Minor [S]: a GSM-era survey found RSSI rises with height in cities (less blockage) but falls in rural areas
  (longer links); an open-source UAV platform paper (arXiv 2509.03818, rural) again finds RSRQ/SINR falling with
  height from neighbour-cell interference.
- B11 Cranfield PhD thesis, "Unmanned aerial vehicle positioning using 5G new radio technology in urban
  environment" (dspace.lib.cranfield.ac.uk 1826/20596) [S]: real-world 5G performance evaluated for UAVs at 50-110
  m; a neural-network TOA correction trained on simulated (ray-traced) data gives 1.3 m (LOS) and 1.7 m (NLOS)
  ranging error. Not a measured bias-vs-altitude curve.
- B12 UAV cellular error overbounds and fault rate: Maaref & Kassas, IEEE T-ITS 2021 (NSF PAR 10321488), the
  journal follow-up of the ION GNSS+ 2019 paper in P1 topic 7 [S; PDF unreadable]: pdf- and cdf-based Gaussian
  overbounds and an SOP fault rate computed from hours of UAV flights across environments, providers and
  frequencies; errors attributed to multipath, residual clock bias and geometry. Related numbers [S]: adding SOPs to
  a UAV cut HPL by 82.4 % (GPS) and 74.6 % (GNSS); opportunistic ARAIM with a fault tree for GNSS+SOP (Khalife,
  Maaref, Kassas, IEEE AES Magazine 2023). The overbound σ and fault probability values were not obtained; they are
  the numbers the integrity model needs, so this paper is worth a library copy.
- B13 Sector-antenna nulls and side lobes [S]: patents US 9831547 and US 11355864 describe the null above a base
  station array as a dead zone for aircraft (a 20° null becomes miles wide at aircraft altitude), with upper-null
  fill targets of about 15 dB (one example still 22 dB); stochastic-geometry and practical-pattern studies (arXiv
  2002.00294; 2503.20296, 2025) find coverage worse than with idealised patterns and "altitude handovers" as a drone
  crosses side-lobe peaks and nulls while climbing. Sim implication [C]: individual towers should fade in and out
  with elevation angle (10-20 dB swings), which matters for which towers are trackable on a climb or descent.
- B14 Minor measurement studies, communications focus [S]: "5G Wings" (Clemson, arXiv 2307.00959, IEEE 2023):
  DJI M30T with three phones on T-Mobile low-band and mid-band 5G and LTE, elevations and speeds varied, downtilt
  coverage gaps and interference from many visible towers. "5G in the Sky" (Liu, Huang, Li, Peng, IEEE/ACM ToN
  2025): AT&T and T-Mobile, good 5G cells often not selected for drones. Neither reports ranging.
- B15 Interference ceiling at aircraft altitude [S]: CEPT SINR analysis (docdb.cept.org document 109/110; ECC
  Report 093 lineage, CEPT Report 81): a UE on board an aircraft could not register on any GSM or LTE frequency
  considered because of the many co-channel base stations in view; a companion minimum-coupling-loss study found
  registration infeasible for some LTE bands at 3,000-4,000 m. US DOT/Appareo final report (Nov 2024, contract
  697DCK-21-C-00233) tested airborne LTE up to 7,000 ft for UAS use. Relevance [C]: registration needs SINR around
  -6 dB; a navigation receiver integrating PSS/SSS/CRS over many frames tolerates far lower SINR (A14 in P2: > 100
  eNodeBs trackable at 11,000 ft with URS), so these results bound modems, not ranging receivers.
- B16 Tropospheric delay on terrestrial ranging paths (a term none of R1/P1/P2 carries). Narayanan, McGraw,
  Osechas, Uijt de Haag, "Residual Error Model to Bound Unmodeled Tropospheric Delays for Terrestrial Navigation
  Systems at Very Low Elevation Angles", NAVIGATION 73(1), Jan 2026, navi.732 [V abstract and summary page]:
  elevations 0.2° to zenith, ranges to 250 km; unmodelled delay near the horizon reaches about 30-50 m at long
  range; delay varies by about 10 cm per km of range; after a polynomial mapping function with Saastamoinen (dry)
  and GPT2w (wet) zenith delays, the residual is bounded by about 0.75 mm/km (range-normalised Gaussian); ducting
  adds up to about 20 cm zenith, several metres at low elevation.
  - Sim implication [C]: for a drone at 30-120 m and towers 1-20 km away (elevation under about 5°), the radio path
    is almost horizontal through surface air with refractivity N about 300-380 (seasonal in Ottawa, TBC), so the
    excess delay is about N·1e-6·d = 0.3-0.4 m per km: 3-4 m at 10 km, different for every tower. A tower-clock
    state absorbs the constant part, but the part that changes with range as the drone moves (0.3 m per km of range
    change) does not; that is a few metres over a multi-km flight. Model it as a deterministic range-proportional
    delay with N from a standard atmosphere (correctable) and a residual of about 1 mm/km (or 10 % of the delay,
    TBC) plus seasonal and weather variation. Same for every terrestrial ranging source (LTE, ATSC, DME).
  - Surface refractivity for Ottawa: ITU-R P.453 gives monthly sea-level N0 maps, wet-term maps (0.75° grid) and
    ΔN in the lowest 65 m [S]; Canadian values not extracted (TBD; owner go-ahead needed for the data files).
  - Companion NAVIGATION 72(4) navi.725 (Sonth, Morton, Scott 2025) is LEO-only: up to 37 m at 3° elevation in
    Indonesia [V abstract]; not terrestrial.
- B17 Aircraft 3G (CDMA) pseudorange noise [S, Kassas-group high-altitude campaign, par.nsf.gov 10180904 family]:
  tower ranges about 5-23 km; per-tower measurement noise variance 0.003 to 0.87 m² on one run (σ about 0.05 to
  0.93 m [C]). Noise only (clock and bias states absorb the rest), consistent with P1's 0.75-1.23 m UAV values.
- B18 Terrain [S]: a UC Irvine drone-to-ground propagation study reports about +10 dB received power per 100 ft of
  altitude gain up to 400 ft over flat terrain, more complex over hills (escholarship qt1ps0342b); a mountain-rescue
  relay-drone study (Future Internet 16(3):89, 2024) combines tower sites with a DEM and runs viewshed analysis per
  altitude, reporting over 40 % coverage gain at 100 m. Ottawa is flat, but the method (DEM viewshed per tower per
  altitude) is the right way to set each tower's LOS flag in the sim instead of a statistical LOS curve.
- B19 Minor [S]: Gharib, Nandadapu, Afghah, arXiv 2105.03778 (Verizon 1700 MHz, rural forest near Flagstaff,
  phone on a drone): the arXiv abstract and the full text disagree on whether low or high altitude was worse;
  Tampere/Ericsson Finland flights at 50/100/150 m; 3GPP TS 38.300 §16.18.5 lets aerial UEs report when N cells
  meet an event, with altitude-dependent events (Rel-18/19). AAU field data restated: 5 cells at 1.5 m, > 16 at
  120 m.
- B20 Tower geometry defaults for the sim when the registry lacks them [S]: NTIA LTE technical characteristics:
  base-station antenna height 30 m urban/suburban, 15-60 m rural, 3° downtilt, three 120° sectors; a Telenor 2.6
  GHz city network used 0-10° electrical downtilt with 5° elevation beamwidth and 60° azimuth beamwidth (AAU
  paper); a Rohde & Schwarz example shows 1° of tilt error roughly doubling the outer cell radius. With a 5°
  beamwidth and 0-10° tilt, a drone at 100 m and 1 km range (elevation +4° above a 30 m mast, [C]) sits above the
  main lobe of most sectors, which is why side lobes dominate (B6, B13).
- B21 Co-channel crowding, urban [S, AAU WCNC 2018 "LTE measurements above urban rooftops", 800/1800/2600 MHz,
  northern Denmark]: at 100 m, four or more neighbour cells within 3 dB of the serving cell in 2.6 %, 4.2 % and
  7.4 % of samples (by band), against under 1 % at 1.5 m. Sim use [C]: probability that the strongest cell's PSS
  does not dominate (several co-channel cells within 3 dB, where a single-correlator receiver mis-acquires or
  tracks a mixture) is a few % at 100 m, rising with frequency.
- B22 Side notes outside cellular [S]: Honda & Otsuyama (ENRI), "Feasibility Study on Aircraft Positioning by
  Using ISDB-T Signal Delay" (IEICE letter, 2016): digital-TV delay ranging for aircraft, ground-site field test;
  FAA 1979 RAPPS DME evaluation: about 285 ft residual ranging error from multipath and terrain masking. The AERPAW
  dataset survey notes the Keysight sensor software behind P2 B13 is proprietary and natively 2-D only.

## C. 5G NR as a signal of opportunity

SATURATED: 21 searches, the last 9 dry (searches 13-21). Log: 1 d, 2 n, 3 n, 4 d, 5 d, 6 d, 7 d, 8 n, 9 n, 10 d,
11 n, 12 n, 13-21 d. Dry searches covered SSB beam-dependent timing, 5G from aircraft, SSB carrier-phase gaps,
gNB holdover, static SSB pseudorange noise, co-sited LTE/NR clocks (SFTD), PSS/SSS-only CRB, RTL-SDR NR cell
search, commercial OTA sync surveys. Items surfaced in C that belong to E are reported under E.

- C1 Low-band NR uses one SSB beam [S]: Rochman, Ye, Zhang, Ghosh, "A Comprehensive Real-World Evaluation of 5G
  Improvements over 4G in Low- and Mid-Bands", arXiv 2312.00957 (Chicago and Minneapolis): all low-band NR
  channels measured (n5, n71) used a single SSB index. Relevance [C]: on n71 (600 MHz, the only Canadian NR band an
  R820T dongle can tune, P2 A9) there is one wide beam per cell, so no beam-dependent timing or SSB-index angle
  effects; mid-band n78 sweeps up to 8 beams, so SSB timing and power depend on which beam the drone sits in.
- C2 Beyond the SSB on a commercial gNB [S]: the tracking reference signal (TRS) is a wideband CSI-RS sent in
  periodic bursts every 10, 20, 40 or 80 ms (RRC-configured) for the UE's fine time and frequency sync. BUAA,
  "Enhanced wireless sensing by exploiting opportunistic 5G NR signals" (IEEE VTC2024-Spring): channel-feature
  blind detection that recovers complete CSI-RS parameters from the physical layer alone on commercial NR, for
  passive sensing; a 2024 preprint uses commercial CSI-RS for passive radar. Relevance [C]: a passive receiver can
  in principle find the TRS without decoding RRC, giving full-bandwidth (20-100 MHz) ranging a few times per 100 ms,
  but only with a wideband SDR; no navigation use on a commercial network found (P2's "not found" stands for
  ranging).
- C3 Dynamic spectrum sharing (DSS) [S, 3GPP rate-matching IEs via Devopedia, MediaTek white papers, patents]: on
  a DSS carrier LTE CRS stays on air and NR PDSCH is rate-matched around it (RateMatchPatternLTE-CRS, Rel-16
  allows several CRS patterns); NR SSB is commonly placed in LTE MBSFN subframes, where CRS is present only in the
  first one or two OFDM symbols; LTE PDCCH symbols are reserved. Implication [C]: an LTE PSS/SSS/CRS ranging
  receiver keeps working on a DSS carrier, but CRS-based tracking must expect CRS-light (MBSFN) subframes, and the
  same carrier may also carry an NR SSB from the same site and clock. A positioning patent for LTE-NR DSS exists
  (US 11888610). Whether Canadian operators run DSS on bands in RTL-SDR range is TBD.
- C6 Canadian band facts [S, trade press 2020-2026]: Rogers deployed DSS on its 600 MHz and AWS spectrum in 2020
  (so 600 MHz carriers can carry LTE and NR on one channel), launched 5G SA (core from Dec 2020), and lists n71,
  n41 and n78 as 5G bands; Bell bought no 600 MHz; Telus SA since 2023; Canada's SA share 8.8 % in Q4 2025 (Ookla
  via press); Bell-Telus network sharing extended (ISED approvals published 9 Oct 2025). Corrects P2 A9's "n71,
  n66, n78 for all three national operators" [S, aggregator]: Bell has no n71 [S]. Ottawa-specific band use is TBC
  (would need the ISED extract or a capture).
- C7 More commercial-network 5G ranging numbers [S]: UC Irvine patent US 12,401,558 (Aug 2025, "opportunistic
  TOA estimation ... with 5G signals"): SS/PBCH pseudorange σ 1.19 m (conditions not given). Chinese work: Wuhan
  University (ISPRS Archives XLVIII-4-2024, p. 619): only one China Mobile gNB audible indoors, n41 SSB Case C at 30
  kHz SCS, SDR receiver; "A Range Measurement Approach based on 5G Opportunity Signal in Urban Environment" (2023):
  outdoor macro gNBs in a real city, pedestrian, average range RMSE 5.37 m over two paths; BUAA "Radio SLAM based 5G
  RSS ranging in GNSS-constrained environments" (RSS, not timing). None airborne. The same patent reports a
  conventional ESPRIT estimate on the same data at about 34 m σ.
- C8 Co-sited LTE and NR [S, patents]: UEs in EN-DC measure SFTD (SFN and frame timing difference between the LTE
  PCell and NR PSCell); LTE and NR reference signals at one site can be quasi-co-located; an older patent notes
  synchronised eNodeBs can carry a known non-zero offset, e.g. one subframe. No measured LTE-to-NR offset at a
  shared site found. Sim implication [C]: treat an LTE cell and an NR cell at the same site as sharing one clock
  state plus a constant offset (TBD), which a receiver can learn while GNSS is good.
- C9 Late item, found during D [S, title only]: Li, Kou, Guo, Xiu (Beihang), "Joint Spoofing and Multipath
  Suppression Using MEDLL and GNSS/5G/INS Consistency Check", WIPHAL 2026 (CEUR Vol-4298, paper 3, pp. 25-33; PDF
  unreadable through the fetch tool). A GNSS/5G/INS consistency check for spoofing is the same role the payload's
  spoof detector plays with LTE; worth reading.
- Not found in C: any commercial-network 5G SSB pseudorange flight on a drone or aircraft (P2's gap stands); a
  measured SSB-beam-dependent timing offset; a measured LTE-NR co-site offset; an RTL-SDR 5G NR ranging receiver;
  multi-site OTA time-error surveys of commercial gNBs (only vendor examples).

## D. Low-cost LTE navigation, differential LTE, carrier phase

SATURATED: 39 searches, the last 8 dry (32-39). Log: 1-10 d d n d d n n n n d; 11-20 d d n n n n d d d n; 21-31
n d n n d d d d n n n; 32-39 d. The BYU thesis (8.03 m) and its PLANS 2025 version are still unread: the thesis is
403 on every route, dblp's PLANS 2025 page sits behind an anti-bot wall, and no other copy or author slide deck
was found. Its hardware, reference-station setup and clock handling remain unknown.

- D1 Integer ambiguity fixing for LTE carrier phase with a base receiver. Khodabandeh & Teunissen, "Ambiguity-Fixing
  in Frequency-Varying Carrier Phase Measurements: Global Navigation Satellite System and Terrestrial Examples",
  NAVIGATION 70(2), 2023, navi.580, DOI 10.33012/navi.580 [V abstract and summary]: plain double differences of LTE
  carrier phase are NOT integer (each tower has its own carrier frequency); the paper builds full-rank models and
  admissible integer transformations that are integer-estimable. Simulation: two receivers, eight transmitters,
  carrier frequency ratios 739-2415 on a 1 MHz base, height aid σ 1 m. Code σ 0.3 m / phase 0.01 cycle: about 10
  epochs to exceed 99.5 % ambiguity success; code 1.0 m / phase 0.03 cycle: about 50 epochs static, about 30 at
  10 m/s; horizontal precision improves about 100-fold after fixing. No real LTE data. Relevance [C]: it is the
  method a differential LTE (base laptop + drone) carrier-phase design would need; NET (base-to-rover link).
- D2 UniBw LTE CRS tracking-noise paper (athene-forschung 147963) [S]: code and carrier tracking noise of the LTE
  CRS with a time-domain replica, analysed in theory and experiment; research Amarisoft eNB sending two PCIs from
  separate antennas allows LTE-only double differences between a static base and a moving rover; four
  configurations (three KF, one LS) on three trajectories; relative precision below 10 cm east/north and 25 cm up
  (search summary, not confirmed in the abstract); the receiver carries an on-board atomic clock. This reconciles
  P2 C10's note: the UAV did carry an atomic clock, and GNSS SPP gave the receiver clock offset. Not low-cost.
- D3 Oscillator grade on a cheap SDR, cellular signals [S]: in the TU Ilmenau SoO synchronisation work (arXiv
  2306.04586, P1 topic 8), an SDRplay Duo with a 0.5 ppm TCXO worked, while a free-running 50 ppm oscillator failed
  and was more than ten times worse than the better references. Implication [C]: an RTL-SDR v3/v4 (TCXO, about 1
  ppm) is in the "works" class for code tracking; uncompensated 50 ppm crystals (some clones) are not. Also new and
  peripheral: arXiv 2511.05204 (Nov 2025), a low-cost modular FR3 front end for carrier-phase wireless
  localisation (not opportunistic).
- D4 Disciplining an RTL-SDR's frequency from LTE. Calvo-Palomino, Ricciato et al., "LTESS-track: A Precise and
  Fast Frequency Offset Estimation for low-cost SDR Platforms", ACM WiNTECH 2017, DOI 10.1145/3131473.3131481
  (IMDEA / Electrosense) [S; PDF unreadable]: uses LTE PSS arrival times and instantaneous frequency deviation to
  estimate the dongle's LO offset, targeting sub-ppm resolution within one second; benchmarks rtl_test,
  Kalibrate-RTL and LTE-Cell-Scanner (which "occasionally" gives large errors; Kalibrate fails with large offsets)
  on two RTL-SDR models with and without TCXO; short- and long-term variation evaluated. Open Python implementation
  "pyltess-track" for Raspberry Pi (licence not checked). Related: Calvo-Palomino PhD thesis, UC3M 2019 (Electrosense
  low-cost spectrum sensing); CalibrateSDR does the same with DAB+ (not used in Canada). Relevance [C]: this is the
  published, Pi-class way to make the payload's dongles frequency-coherent with the tower network (tower
  frequency within ±50 ppb), which also feeds the Iridium Doppler problem in P1 topic 1 (a dongle known to about
  0.05 ppm gives about 80 Hz at 1.6 GHz). Owner go-ahead needed before using the code.
- D5 How precise can an RTL-SDR time a signal [S]: Calvo-Palomino et al., arXiv 1802.07016 (Electrosense): Mode S
  (1090 MHz) time-of-arrival on low-cost RTL-SDR sensors with 1.5 ns standard deviation for the best method; the
  same group's INFOCOM 2017 paper used GPS time sync on every RTL-SDR node. Relevance [C]: the dongle's sampling
  is not what limits LTE ranging precision; bandwidth, multipath and the dongle-to-dongle clock (if several are
  used) are. A sub-ns ToA on pulses at high SNR is consistent with metre-level PSS/SSS ranging noise.
- D6 RTL-SDR on a quadcopter, LTE [S]: UC Santa Barbara / Northern Arizona, "Evaluating LTE Coverage and Quality
  from an Unmanned Aircraft System" (IEEE MASS, about 2019; ebelding.cs.ucsb.edu): a small RTL-SDR on an
  off-the-shelf quadcopter measured eNodeB RSRP over a wide area; its accuracy was comparable to expensive
  hardware and within one quality gradation of phones on the ground. Not navigation, but the only published
  flight of an RTL-SDR processing LTE found; shows PSS/SSS/CRS capture from a small drone with this class of
  dongle works (vibration, EMI from motors not reported in the snippet).
- D7 STARE, a publicly available real-time cellular PNT software receiver [V ESA ESSR project page,
  essr.esa.int/project/stare, updated 15 Jan 2026]: ESA-owned, C++, real-time from an arbitrary SDR or
  post-processing of recorded baseband; 5G NR, LTE, NB-IoT, NR-NTN/IoT-NTN, custom OFDM and non-OFDM signals;
  tracking-loop and snapshot modes; outputs code phase, carrier phase, Doppler, SNR and C/N0. Licence: ESA Community
  License v2.4 Permissive (Type 3). NAVITEC 2026 (ESTEC, 20-22 May 2026) talk "All You Can STARE: Real-Time Software
  Receiver for Estimating PNT Measurements from NR-NTN, IoT-NTN, Starlink, and Arbitrary Satcom Signals" [S,
  programme title only]. A 2026 ESA-hosted paper calls it "publicly available" and notes other cellular receivers
  never released source [S]. No accuracy figures, no ARM/Raspberry Pi statement. Relevance [C]: the only
  published, licensed, real-time LTE/NR ranging receiver found; a candidate reference implementation for the
  ground laptop (third-party code: owner go-ahead and licence review needed before download).
- D9 A second low-cost LTE thesis. Ikhtiari, "Navigation in GNSS denied environments using software defined radios
  and LTE signals of opportunities", ME thesis, University of Canterbury (NZ), 2019 (ir.canterbury.ac.nz
  10092/16939, 403 to the fetch tool) [S]: USRP B200mini + srsUE-based LTE receiver tracking pilot (reference)
  sequences; the B200mini's TCXO drift was "non-linear and volatile; changing from trial to trial". Navigation
  results not obtained. Relevance [C]: direct evidence that a TCXO-class SDR clock cannot be modelled as a fixed
  linear drift between flights; the receiver clock must be a filter state per session (random walk on frequency),
  consistent with the TCXO process noise already in P1 topic 7.
- D10 Timing advance needs a transmitting UE [S]: TA steps are about 0.52 µs (about 78 m [C]), only the serving
  cell, phone-side access device-dependent; TA + signal level gave 70-191 m in a 2023 drive-test study. TX and NET:
  not usable on a receive-only payload.
- D11 An RTL-SDR has been used for LTE positioning before (lab signals). del Peral-Rosado, Parro-Jiménez,
  López-Salcedo, Seco-Granados (UAB), "Comparative Results Analysis on Positioning with Real LTE Signals and
  Low-Cost Hardware Platforms" (ESA NAVITEC, about 2014-2016) [S abstract via SciSpace; PDF not readable]: an OTDoA
  SDR receiver run on either a USRP or a DVB-T dongle with the RTL2832U chip, on real LTE signals generated in a
  laboratory and post-processed; authors conclude the results support low-cost hardware on commercial networks.
  Numbers not obtained. Related: Soderini et al. (ENAC), ION ITM 2020: pseudoranges from LTE physical channels such
  as PDCCH, "almost not considered in the literature" [S]. Ground-vehicle LTE baselines (Kassas group, not
  low-cost): 5.80 m with six eNodeBs in severe multipath; 3.17 m over 1.44 km urban; 2.6 m with eight pre-mapped
  towers (NDSS AutoSec 2022) [S].
- D12 Receiver oscillators get worse in flight [S]: "Performance of miniaturized atomic clocks in static
  laboratory and dynamic flight environments", GPS Solutions 2020, DOI 10.1007/s10291-020-01036-4 (geo-leo
  e-docs 11858/10687; Springer behind a login redirect): each oscillator fed a geodetic GNSS receiver in an
  aircraft; frequency stability degraded by at least an order of magnitude against the lab; the two quartz
  oscillators showed g-sensitivity frequency shifts of -1.2e-9 and +1.5e-9 (units per g as reported in the
  snippet; check), rubidium much less. arXiv 2406.16037 (2024): airborne testing of UAV GNSS-disciplined
  oscillators, lab tests overlook flight behaviour; 15-30 min warm-up settling. Sim implication [C]: on a
  quadcopter, the dongle's TCXO frequency will jump with vibration and manoeuvre load at the 1e-9 level (about 0.3
  m/s of pseudorange-rate error, 1.6 Hz at 1.6 GHz); add a vibration-driven white-frequency term about 10 times
  the bench Allan deviation, plus a warm-up drift for the first 15-30 min after power-on.
- D13 Dongle oscillator numbers [S, vendor and hobby measurements, no Allan deviation found]: RTL-SDR Blog V4
  (R828D tuner): TCXO "1 ppm", per the maker's shop text under 1 ppm typical, 2 ppm maximum initial offset, 0.5-1
  ppm temperature drift; a non-TCXO dongle drifted about 6-7 ppm in its first 30 min against under 1 ppm for a
  TCXO unit; an AirSpy (1.5 ppm TCXO) shifted 0.685 ppm over a temperature run against 4.78 ppm for a plain
  RTL2832 quartz. Sim values [C]: initial offset uniform ±2 ppm (3.2 kHz at 1.6 GHz, 1.4 kHz at 700 MHz), slow
  thermal drift up to 1 ppm over a flight, plus the vibration term of D12; P1's "about 1e-9 at 1 s" ADEV remains
  [M]. All of it is removable by locking to LTE (D4).
- D8 Open LTE PHY code [S]: libLTE (LGPLv3) does PSS detection and SSS cell-ID; pyltess-track (D4) is GPL. Both are
  third-party code under copyleft licences (owner decision).
- D14 Minor [S]: Kassas-group magazine piece (Inside Unmanned Systems, 2020): a drone flew more than 2 km on
  non-differential real LTE with 14.8 m error after 2 min without GPS; indoor LTE carrier phase with a synthetic
  aperture array, 8 m RMSE with 4 eNodeBs (OSU PDF). No search found a free-running-oscillator cellular carrier-phase
  demonstration (P1 topic 3 negative result still stands after this pass), an RTL-SDR/Pluto/Lime/bladeRF LTE
  navigation flight, a 2026 low-cost LTE flight paper, or a Pi-class real-time LTE ranging receiver with CPU
  figures.

## E. Cell tower clocks

NOT SATURATED: 11 searches in E (plus 3 E-relevant searches made under C: holdover, timing-source outage, SFTD),
stopped by the weekly search limit. Log: 1 d, 2 n, 3 n, 4 n, 5 n, 6 n, 7 d, 8 d, 9 n, 10 d, 11 d (last two dry).

- E1 Jamming geometry matters for towers [S, Nkom via Barents Observer, High North News, Arctic Today, 2024-2026]:
  Finnmark jamming days rose from 6 (2019) to 294 (2023); a 2026 Nkom analysis found disturbances down to about
  600 m over the Varanger peninsula, while earlier Nkom measurements had found no GNSS disruption on the ground;
  Nkom added two ground monitoring stations in eastern Finnmark (May 2026). Traficom (Apr 2026): no effect on
  Finnish mobile networks (service statement, not timing data). Implication [C]: cross-border or airborne-target
  jamming is strongest at altitude; ground-mounted tower GNSS timing receivers (often with antennas near the
  ground or on the mast) can stay locked while a drone at 100 m is jammed. The sim should offer both cases: a
  local jammer that hits towers and drone alike, and a regional/high jammer that hits the drone only.
- E2 The only incident reports found of ground timing users losing GNSS in a real (unintended) jamming event, both
  US 2022 [V GPS World "DHS report on Denver jamming: more questions than answers"; S InsideGNSS, CISA]:
  - Denver area, December 2022: interference for 33 hours (FCC found and stopped it; "presumably accidental").
    A public-safety operator's trouble report: local P25 simulcast systems "lost GPS lock", two of its base
    transceiver systems began losing sync, "no other BTS affected other than three sites in Aurora"; replacing GPS
    receivers, cabling and surge protectors did not help. These are land-mobile-radio base stations, not LTE
    eNodeBs; no commercial carrier reported. A separate GPS World item [S] describes a simulcast system whose
    rubidium backup clocks drifted apart during an outage until towers isolated (incident not named).
  - Dallas-Fort Worth, 17-18 Oct 2022: about 44 hours of intermittent jamming, source never found; analysis
    suggests an upward-pointing directional antenna; 162 Texas CORS ground receivers showed no widespread impact
    [S]. Supports E1: aviation-band jamming events often spare ground timing receivers.
  - CISA "GPS Interference" insight (Feb 2023) [S]: a site with built-in alternate timing saw minor or no service
    degradation. NSTAC GPS report [S]: CDMA handoff degrades only after extended GPS loss.
  - Sim implication [C]: tower-timing faults at jamming onset are plausible only for jammers in the towers' own
    reception footprint; when they occur, expect loss of sync after minutes to hours (holdover), not an instant
    step. Commercial LTE eNodeBs were not reported affected in either event.
- E3 Operators are adding non-GNSS timing at cell sites [S, Iridium press release 21 Oct 2025, GPS World, Inside
  GNSS, Via Satellite]: US DOT Complementary PNT Rapid Phase Award II (five awards: Iridium, NAB, UrsaNav, Viavi,
  MerlinTPS); under Iridium's (about US$1.5 M) T-Mobile will add Iridium PNT timing receivers at 90 more live 5G
  sites ("more" implies an earlier set exists), claimed sub-100 ns, authenticated. NextNav and Oscilloquartz
  announced 5G-based timing for critical infrastructure (Oct 2025, vendor); NextNav claims 30-day holdover with
  atomic clocks at its leader sites (vendor); Oscilloquartz ePRTC claims ±100 ns to UTC for up to two weeks
  (vendor); a "5G-based backup to GPS" policy report (2025) argues the US has no terrestrial GPS backup. Nokia
  blog [S]: without a backup source gNBs need costly oscillators for holdover. Implication [C]: a growing (still
  small, US-first) share of towers will keep GNSS-independent time through a GNSS outage, which would make their
  clocks behave better than free holdover; no Canadian operator announcement found (TBD).
- E4 3GPP's own timing-error vocabulary [S, TR 38.857 drafts, RAN1/RAN2 drafts, CEUR Vol-3097 paper 35]: Rel-17
  defines the Tx timing error as the delay left after a TRP's internal calibration (antenna/RF chain), grouped into
  "TRP Tx Timing Error Groups" (TEGs) of PRS resources whose errors lie within a margin; TR 38.857 Annex B.1
  evaluates horizontal accuracy with gNB/UE Tx/Rx timing errors; one Rel-17 analysis modelled them as Gaussian with
  σ = 5 ns truncated at ±2σ and got 3.41 m DL-TDOA error at 90 %. Some RAN1 evaluations ran without sync or
  timing errors at all. Relevance [C]: 3GPP itself treats per-antenna transmit delay as a separate,
  calibration-limited term of a few ns (about 1-2 m), distinct from the site clock; it supports the per-sector
  constant bias already in P1 4.4 and A11 of this pass. The 50 ns sync and 2/10 ns TEG values remain unconfirmed
  (TR text not reached).
- E5 Measured holdover in telecom sync chains (lab interop, not live towers) [S, EANTC public interop reports
  2025-2026; SEL at NASPI 2023; WSTS 2025]:
  - A telecom grandmaster that lost GNSS kept PTP/SyncE within masks for a full hour, still advertising clockClass 6
    (EANTC 2025, "Simulated Grandmaster GNSS disruption, bridging mode").
  - With enhanced SyncE assisting holdover, a chain of eight boundary clocks kept average time error between about
    -4 and -31 ns through GNSS and PTP loss, against the ITU-T G.8271 accuracy-level 6A limit of 130 ns; failover
    tests stayed within level 6C (±65 ns).
  - SEL utility PRTC: about 200 ns after one day on internal rubidium; 180 ns after 14 days with cesium assist.
  - Vendor targets: 100 ns over 100 days with a high-performance cesium ePRTC (claim).
  - Context: P2 E4's Cisco slide (1.1 µs kept only for "several hours" on a local oscillator); a Rohde & Schwarz
    blog says some countries require a cell's deviation from the GNSS UTC second to stay within 130 ns, which
    matches G.8271 class 6A; R&S's field example showed a 17.5 ns reference time error [S].
  - Sim implication [C]: a tower fed by a network grandmaster with SyncE (common in modern backhaul) can drift only
    tens of ns (about 10 m) over hours after GNSS loss, whereas a tower with its own GNSS receiver and plain OCXO
    drifts about 1 µs in a few hours (300 m). Model tower holdover as a mixture: "network-held" towers (σ tens of
    ns per hour) and "local-OCXO" towers (hundreds of ns per hour), share TBD. TimeBeat announced 5G fronthaul
    field holdover measurements from Q3 2026 (no results yet).
- E6 Standards-track handling of a tower losing its timing source [S, patents US 11754665, US 12092752, US
  11909582, US 12407437; RAN2 drafts]: a gNB that detects a timing-source outage (e.g. failed GNSS decoding)
  notifies the location server over NRPPa, optionally with an expected drift; the server can exclude the TRP or mute
  its PRS and fall back to timing-robust methods; UEs can be told via RRC/MAC-CE/DCI and relay via LPP or
  sidelink; a 5GS-side "GNSS health" report from NG-RAN nodes and a 5G-system holdover timer exist in patent
  form. Not confirmed as adopted spec text. Relevance [C]: a passive receiver cannot see these messages (NET), but
  they show the industry expects per-TRP timing faults during GNSS outages and handles them by exclusion, which is
  what the payload's integrity layer must do on its own (innovation gating per tower).
- E7 Antenna-port and sector offsets: one search for measured CRS port-0/port-1 timing offsets on a commercial
  eNodeB found only background (ports are logical; a TDD CoMP calibration paper reports about π/8 residual phase
  between eNBs in simulation, arXiv 1905.01046) [S]. A UniBw preprint titled "LTE-AntennaPort" appeared in one
  result list but its URL returned 404. Nothing new on sector offsets beyond P1 4.4.
- E8 GPSDO steering background [S]: a NIST GPS-disciplined clock description gives frequency-control loop time
  constants of several hours; a GPSDO tutorial notes frequency steps appear when the oscillator's control
  resolution is coarse; temperature shocks perturb a disciplined oscillator's frequency. Consistent with the
  minute-scale jumps in P1 4.1 being the eNodeB's own steering design, not the GNSS loop as such.
- Search budget ended here. The next WebSearch call returned exactly: "You've hit your weekly limit · resets 11am
  (America/Toronto)". Per the brief, no other search route was used after this.
- C4 Vendor OTA timing notes [S, Rohde & Schwarz blog 2022-23]: SSB ToA from a drive-test scanner is precise to
  only about 400 ns; the stationary TAE method reaches below 30 ns with good GNSS; reliable measurement needs SINR
  above 15 dB and delay spread below 17 ns (a LOS indicator); compare SSBs with the same index. The blog quotes 260
  ns for intra-band contiguous CA, which conflicts with P2 E3's 130 ns (spec copy); P2's value is the better
  source.
- C5 Peripheral [S]: arXiv 2410.18323 (3GPP-compliant 5G positioning testbed, ±50 ns hardware sync, NET);
  TiamiTwin, arXiv 2609.22709 (2026), bistatic sensing of a drone with an opportunistic receiver synchronised only
  from the SSB (the drone is the target, not the receiver); arXiv 2507.16600 (dedicated 5G positioning
  infrastructure, carrier-phase trilateration, < 5 m in a KITTI-based simulation, NET).

- A1 Observability conditions (foundation, not in R1/P1/P2). Kassas & Humphreys, "Observability Analysis of
  Collaborative Opportunistic Navigation With Pseudorange Measurements", IEEE T-ITS 15(1):260-273, 2014, DOI
  10.1109/TITS.2013.2278293; open copy core.ac.uk/download/10647482.pdf [S]. Single-receiver precursor: a planar
  environment of one receiver and n SOPs is observable if EITHER the receiver's initial state (position, velocity,
  clock) is known, OR its initial position is known together with the full initial state (position and clock) of one
  SOP [S]. Receiver-controlled manoeuvres reduce the prior knowledge needed (receding-horizon vs greedy planning) [S].
  Sim implication [C]: radio SLAM starting at GNSS loss (receiver state known) is observable; a cold start with all
  towers unknown is not, so the sim must start radio SLAM only from a GNSS-initialised state or with at least one
  tower fully known.
- A2 Collaborative inertial radio SLAM. Morales, Khalife, Kassas, "Information Fusion Strategies for Collaborative
  Inertial Radio SLAM", IEEE T-ITS 23(8):12935-12952, 2022, DOI 10.1109/TITS.2021.3118678 [S; OSU PDF fetched but
  unreadable binary]. Several UAVs share tower state estimates; UAV experiment: final error after 30 s without GPS
  about 55 m with INS alone vs about 6 m collaborative [S]. Companion: "Event-Based Communication Strategies for
  Collaborative Inertial Radio SLAM" (OSU PDF) [S, not read]. NET (vehicle-to-vehicle link).
- A3 UniBw transmitter-mapping chain, earlier paper. Arizabaleta-Diez, Hameed, Pany, "LTE Transmitter Location and
  Clock State Estimation: Simulated and Real Measurements Using the SSS and CRS Signals", UniBw ATHENE 143101 [S;
  PDF exceeds the 10 MB fetch limit, repository host refused connection]. SSS and CRS as 10 ms GNSS-like replicas in
  MuSNAT; Kalman filter on base-station position and clock; applied to two commercial eNBs and one Amarisoft eNB.
  Preceded by Hameed et al. 2022 (2-D, SSS only). No numbers obtained; the PLANS 2023 follow-up (P2 C10) gives
  0.3 m H / 1 m V with carrier phase.
- A4 Crowd-sourced RSS tower localisation is km-class. Li, Nika, Zhang, Zhu, Yao, Zhao, Zheng, "Identifying Value
  in Crowdsourced Wireless Signal Measurements", WWW 2017 [V abstract: 419 M measurements, about 1 M cells, ground
  truth base-station locations; raw RSS gives poor, high-variance results]; numbers [S]: median error weighted
  centroid 2.83 km downtown, 7 km rural; strongest-RSS 2.75 km downtown, 0.7 km rural. Rahman, Hossain, Yuksel,
  "Multi-Operator Cell Tower Locations Prediction from Crowdsourced Data", ICCCN 2021 [V abstract]: weighted k-means
  on OpenCelliD, compared with FCC site data, "significant accuracy", no number in abstract. A patent gives 32 m and
  171 m for two drive-sampled examples [S].
  - Correction-relevant [C]: OpenCelliD/crowd "cell positions" are coverage centroids, not masts; RSS-only
    estimates are 0.7 to 7 km off. Only timing-advance or pseudorange methods reach the 40 to 100 m class (P1). A
    sim that uses a crowd map as the tower prior must use σ of km unless the map was built from timing.
- A5 Rail radio SLAM (non-cellular, simulation). Siebler, Sand, Hanebeck (DLR/KIT), "Simultaneous Train
  Localization and Radio Transmitter Mapping with TDoA and Magnetic Field Measurements", FUSION 2026 [S; KIT PDF
  unreadable]: pose-graph SLAM, two synchronised train antennas (TDoA cancels transmitter clocks), magnetic loop
  closures, FRMCS-parameter simulation; transmitters "localised with metre-level accuracy" [S]. Shows the TDoA
  trick (two receive antennas on one vehicle) that removes transmitter clocks from the SLAM state.
- A6 Channel-SLAM, LTE. Ulmschneider & Gentner (DLR), multipath-assisted positioning with 3GPP LTE signals and only
  two base stations, IEEE/ION PLANS 2016 [S, no numbers]; Channel-SLAM treats each multipath component as a virtual
  transmitter, no prior map needed; single physical transmitter works indoors with UWB (Karasek & Gentner, IEEE
  Access 2020) [S]. Ground/indoor only.
- A7 Correction to A4 attribution: the 2.75 km / 2.83 km downtown medians belong to Yang, Varshavsky, Liu, Chen,
  Gruteser, "Accuracy Characterization of Cell Tower Localization", UbiComp 2010 (Los Angeles, wardriving trace
  against actual tower locations) [S]; two secondary summaries disagree on which method gave 0.7 km and which 7 km
  rural. The paper adds a bounding step (keep only cells inside the trace's area) and a cell-combining step that
  halves the error [S]. Conclusion unchanged: RSS-only crowd/wardriving tower positions are km-class.
- A8 CellMapper vs independent estimates. arXiv 1804.05186 ("Cellular Network Traces Towards 5G", 2018), Table 2
  [S]: 100 cells compared by hand; mean distance between the authors' estimated base-station positions and
  CellMapper's: operator 1 about 32 m (macro) / 5 m (micro), operator 2 about 21 m / 12 m; cell-ID match 63 % and
  72 %. Neither side is surveyed truth. CellMapper's FAQ [S]: towers with one or two cells (e.g. omni) are always
  "low accuracy" and placed at the strongest-signal point, which is much worse.
- A9 SOP-aided INS with unknown towers, numbers [S, patent US 11366236 and Morales/Kassas papers]: ground vehicle,
  tactical IMU, one unknown cellular tower, 30 s GNSS cut: final error 57.30 m (GNSS-INS coasting) vs 9.59 m
  (SOP-aided INS). Collaborative SOP-aided INS, two unknown towers: north-east RMSE 9.42 m, final tower
  localisation error 15.5 m, vs 23.5 m for GPS-INS after GPS loss; the patent claims consumer-grade IMUs reach
  performance "comparable to when GNSS is available" in this framework (claim, not measured here). UAV, consumer
  IMU, radio SLAM bounded in simulation (par.nsf.gov 10413010) [S]. CONFLICT between snippets: a later search
  summary of the same paper (Morales & Kassas, "Tightly Coupled Inertial Navigation System With Signals of
  Opportunity Aiding", IEEE TAES 2021) attributes the 57.30 m vs 9.59 m to a UAV aiding a consumer-grade IMU, not a
  ground vehicle with a tactical IMU. Treat platform and IMU grade for this number as unresolved until the paper
  is read.
- A10 5G factor-graph SLAM with unknown base stations: Kabiri et al. (Univ. Luxembourg), arXiv 2412.12406 [S]:
  ToA from 5G with a bias node per base station (absorbs clock offset), unknown BS positions, ToA used instead of
  loop closure to bound drift; mostly indoor. NR5G-SAM (Karfakis et al., 2023) [S]: 5G NR radio SLAM for a field
  robot, simulation, five gNBs. Both show the factor-graph alternative to the EKF; neither is airborne.
- A11 Base-station almanac (network side) error mechanisms [S, Qualcomm-era patents US 7800540 family, US
  8437772]: the listed position is sometimes the equipment shelter, not the antenna; almanac entries are verified by
  inverting handset fixes; a per-direction "forward link calibration" value absorbs antenna-position and
  cable/transmit-delay errors together. Sim implication [C]: a tower's registered position error and its fixed
  transmit-delay bias are not separable from one range, and a per-sector constant range bias (tens to hundreds of
  ns, TBD) belongs in the model alongside the position prior.
- A12 PCI aliasing [S, patents only]: operators only avoid PCI reuse between neighbours; a receiver far from the
  planned neighbourhood (which a drone at 60-120 m is, P2 B4: serving cells > 5 km away) can hear two cells with the
  same PCI. Association should key on PCI + EARFCN + coarse position gate, not PCI alone. No measured aliasing rate
  at altitude found.
- A13 Minor [S]: TU Wien crowdsourced timing advance reaches about 50 m mean on a low-multipath subset (100 m
  overall) with > 97.5 % cell identification. Canadian context: an audit found ISED and CRTC never verified
  operator-submitted coverage data (2018-2023); a Bell witness called ISED site data "pretty reliable" with "some
  examples of inaccuracy". 2026 TU Delft BSc thesis (Kuipers) compares TDoA/RSSI EKFs for UAV SoOP in ray-traced
  cities (simulation, results not read).
- A14 Sel & Kassas, "Demonstration of Radio SLAM with Terrestrial Signals of Opportunity in a GPS-Denied
  Environment", IEEE VTC2025-Spring, Oslo, pp. 1-5 [S, listing only, no numbers]. Probably the NAVFEST jammed-area
  data (P2 E1: 29.4 m / 32.2 m) re-analysed [C, inference]. NSF CPS 2024 poster [S]: aircraft 57 km in 11 min,
  4.96 m RMSE with radio SLAM; altimeter-aided INS alone 27,226 m on the all-unknown-towers run (43.27 m with radio
  SLAM). Adds the dead-reckoning baseline to P1 topic 10.
- A15 Multipath SLAM with unsynchronised base stations: Venus, Leitinger, Witrisal, "Simultaneous Source
  Separation, Synchronization, Localization and Mapping for 6G Systems", arXiv 2512.22393, Dec 2025 [V abstract]:
  factor-graph sum-product MP-SLAM that estimates a per-BS synchronisation bias jointly with positions and
  data association; "no significant performance degradation" vs perfectly synchronised BSs; no numbers; looks
  simulation-only.
- A16 Aviation obstacle files as a tower map (US) [S, FAA DOF/OE-AAA pages, Florida GDL metadata]: every verified
  obstacle carries a horizontal accuracy code: 1 = ±20 ft (6 m), 2 = ±50 ft (15 m), 3 = ±100 ft (30 m) ... 8 =
  ±1 NM, 9 = unknown; unverified entries are flagged unreliable; DOF reissued every 56 days. FAA certified surveys
  are 1A (±20 ft H, ±3 ft V) or 2C (±50 ft H, ±20 ft V). Canada: NAV CANADA compiles obstacle data from owners'
  reports; no free public download or accuracy statement found (Garmin sells a Canadian set, towers > 200 ft AGL)
  [S]. Sim implication [C]: for tall towers a per-entry σ from the accuracy code (6-30 m) is a defensible prior where
  such a file exists; most urban rooftop cell sites are too short to appear.
- A17 Imagery-based manual mapping: Goudarzi & Landry, "Assessing horizontal positional accuracy of Google Earth
  imagery in the city of Montreal, Canada", Geodesy and Cartography 2017 [S]: 0.1 to 2.7 m against 10 GPS points;
  Potere (Sensors 2008) [S]: 24.1 m RMSE in developed countries, 39.7 m global mean. So imagery is not the limit in
  a Canadian city; the 30 m H / 34 m V offset in P2 C10 must come from picking the wrong point or a map pin, and
  vertical position (antenna height) is not available from imagery at all [C].
- A18 Other [S]: patent US 8463292 "TDOA-based reconstruction of base station location data" (network-side
  almanac repair from handset TDOA); a GSA/OTDOA note that target error is about twice the tower-antenna position
  error and that rooftop sector antennas can sit metres apart from the site coordinate (ArcGIS planning tools carry
  a per-antenna roof offset). FCC registry includes dismantled towers. OpenCelliD licence CC BY-SA 4.0 per
  Wikipedia (3.0 in an older table), free API key needed for download; primary licence page not read. RSS-only
  "SLUS" (simultaneous localisation of UAV and RF sources, ICUAS 2014; Trans. Inst. Meas. Control) is the
  search-and-rescue analogue, RSS-based, low value for towers.
- A19 Trajectory matters for observability. Yang, Khalife, Morales, Kassas, "UAV Waypoint Opportunistic
  Navigation in GNSS-Denied Environments", IEEE TAES, DOI 10.1109/TAES.2021.3103140 [S; NSF PAR PDF unreadable]:
  UAV with unknown initial state, several unknown SOPs plus one anchor SOP of known state; greedy one-step
  look-ahead multi-objective motion planning reaches the waypoint with a user-set confidence, while flying straight
  at the waypoint fails (environment poorly estimable) and earlier random/open-loop motion made the filter diverge
  [S]. Sim implication [C]: test radio SLAM on straight legs as well as circuits; a straight leg toward or away
  from towers gives little bearing change and the tower states may not converge.
- A20 Unknown tower clock process noise: Kassas, Ghadiok, Humphreys, "Adaptive Estimation of Signals of
  Opportunity", ION GNSS+ 2014 (core.ac.uk/download/211388834.pdf) [S]: compares an innovation-based
  maximum-likelihood adaptive KF with an interacting multiple model filter for identifying a cellular source's clock
  process noise online; simulation and experiment; outcome not read. Follow-up: "A Static Reduced-Order Multiple
  Model Adaptive Estimator for Noise Identification" (Kassas group, 2022) [S]. Sim/filter implication [C]: the
  per-tower jump-and-drift behaviour in P1 4.1 (Lapin) is a mode switch; an IMM with a "quiet" and a "steering
  jump" clock mode per tower is the published way to handle it, instead of one inflated random walk.
- A21 Range-only SLAM initialisation (robotics, out of the cellular scope but directly usable) [S]: a new tower with
  no prior can enter the filter from its first range as a weighted Gaussian mixture on a ring (Caballero, Merino,
  Ollero, ICRA 2010; composite beacon initialisation, HAL 01219746); Channel-SLAM initialises virtual transmitters
  from the first ToA with a deliberately wide prior because of the unknown clock offset (DLR) [S].
- A22 Collaborative mapping (stationary or slow receivers, GNSS available). Morales & Kassas, "Optimal Receiver
  Placement for Collaborative Mapping of Signals of Opportunity", ION GNSS+ 2015, and journal version "Optimal
  Collaborative Mapping of Terrestrial Transmitters" (IEEE TAES 2018) [S]: GDOP minimisation vs determinant/area
  maximisation for where to place the next receiver; cellular-tower experiment with several receiver trajectories;
  a demonstration reports 3.44 m emitter localisation error (escholarship qt9nt0p7cp) [S]. This is the "self-survey
  while GNSS works" number for a well-placed set of receivers; P2 C1 (42 -> 7 m from one 175 s UAV flight) is the
  single-UAV equivalent.
- A23 Lead not read: Qualcomm white papers "Introduction to OTDOA on LTE Networks" (Fischer, Aug 2014) §2.2.4
  eNodeB synchronisation and §2.2.5 cell database accuracy with a figure on antenna-coordinate error vs location
  accuracy, and "OTDOA Positioning in 3GPP LTE" (Jun 2014) §8.3 [S, headings only; both PDFs came back as
  compressed binary through WebFetch, no HTML version found].
- A24 Operator-side antenna records [S, vendor and trade press, interested party]: Sunsight (antenna-alignment
  tool vendor) says recorded tower-antenna location errors of 30-50 m are "not uncommon" and that network-based
  caller location error is about twice the antenna location error; a 2013 audit of over 6,000 antennas found more
  than a third installed out of tolerance (azimuth/tilt/alignment). RCR Wireless 1998: positional audits for two
  carriers' clients found half the tower sites outside the 1-A tolerance (±20 ft, 6 m). IQGeo 2026 survey of 500
  telecom decision-makers (US, Canada, UK): only 13 % say more than three-quarters of their network records are
  accurate. Sim implication [C]: even operator records carry 30-50 m antenna-position errors at a meaningful rate,
  and sector azimuth/tilt fields (which the altitude model in topic B would use from ISED, P2 C2) are wrong for
  something like a third of antennas.
- A25 Ground-vehicle LTE tracking on a commercial network with tower positions from a public database and clock
  properties estimated in a preliminary phase: Driusso, Marshall, Sabathy, Knutti, Mathis, Babich, "Vehicular
  Position Tracking Using LTE Signals", IEEE TVT 2017 (Trieste/ETH, post-print on arts.units.it) [S; PDF
  unreadable]. Numbers not obtained.
