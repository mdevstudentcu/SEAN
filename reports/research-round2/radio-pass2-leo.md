# Radio pass 2: LEO Doppler and Iridium, finished to saturation

Date 2026-11-11. Builds on `reports/sources-research-20261111.md` and `research2/radio.md`; reports only what is new
or corrected relative to both. Labels [V] [S] [M] [C]; flags TX / NET / OPTICAL.

(in progress; coverage table at the end of the run)

## Topic A. LEO Doppler and orbit-error handling

### A.1 Orbit error as an along-track time offset: the numbers behind it
- Hayek, Saroufim, Kassas, "Ephemeris Error Modeling in Opportunistic LEO Satellite Tracking with Pseudorange and
  Doppler Measurements", ION GNSS+ 2023 (OSU PDF,
  https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Ephemeris_error_modeling_in_opportunistic_LEO_satellite_tracking_with_pseudorange_and_Doppler_measurements.pdf)
  [V full text via text extraction].
- Idea: a known receiver estimates the satellite's argument of latitude in an EKF and converts it to an SGP4 epoch
  time adjustment; this removes most of the along-track and radial-velocity error but not the radial position error.
- Numbers [V]: optimal epoch shift -257 ms (Starlink, simulation) and -950 ms (Orbcomm, real); SGP4 error about
  1 to 10 km 24 h after a TLE (cited); Starlink sim initial error 1,880 m to 356 m (pseudorange) / 367 m (Doppler);
  Orbcomm real 7.1 km to 242 m RMSE; ground receiver 2.67 km to 211 m, while using raw SGP4 made it worse (5.8 km,
  with an inconsistent covariance). Radial position error about 200 m is left after the time shift. Cross-track is
  least observable.
- Sim needs [C]: per satellite, along-track error = v_sat x dt with dt drawn per pass (|dt| 0.1 to 1 s TBC, i.e.
  0.75 to 7.5 km), plus an independent radial error of about 200 m and a cross-track error about 100 x smaller than
  along-track (first report). The filter's "one time-offset state per satellite" removes the first term only, so a
  residual of about 200 m radial should remain in the honest sim.
- Khairallah & Kassas, "Ephemeris Tracking and Error Propagation Analysis of LEO Satellites With Application to
  Opportunistic Navigation", IEEE TAES 2024 (OSU PDF
  https://people.engineering.osu.edu/media/document/2024-04-15/kassas_ephemeris_tracking_and_error_propagation_analysis_of_leo_satellites_with_application_to_opportunistic_navigation.pdf)
  [S]: Orbcomm, carrier phase, about 6 min of tracking from a known receiver: satellite error 7.1 km / 7.3 m/s to
  698.7 m / 1.8 m/s; a stationary receiver then went from 13,476 m initial error to 343 m. Error bounds from
  satellite state to receiver state are derived. Related PhD thesis: Khairallah, "Towards Opportunistic Navigation
  with LEO Satellites: Adaptive Clock Estimation and Closed-Loop Ephemeris Tracking", UC Irvine
  (https://escholarship.org/uc/item/5q98d5vr) [S].

### A.2 Full orbit-error sensitivity table (upgrades the single 300 m row in the first report)
From the Frontiers survey (A.3), citing Shi et al., simulation, 3D RMS position error [S, survey table]:

| Injected orbit error | 3D RMS (m) |
| --- | --- |
| position 3 m / velocity 3 cm/s | 5.83 / 6.68 |
| position 30 m / velocity 30 cm/s | 27.44 / 40.36 |
| position 300 m / velocity 3 m/s | 268.28 / 399.29 |
| position 3 km / velocity 30 m/s | 2,692 / 3,977 |

Roughly linear: about 0.9 m of fix error per metre of orbit position error and about 133 m per m/s of velocity error
[C]. Least-squares epoch solutions fail when the initial guess is more than about 200 km off [S].

### A.3 Survey with a results table
- "Survey on positioning technology based on signal of opportunity from low earth orbit", Frontiers in Physics 2025,
  DOI 10.3389/fphy.2025.1592447 (https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2025.1592447/full)
  [V first 100k characters]. New static results in its tables, not in either earlier report:
  - Starlink differential Doppler, two receivers 1 km apart: 5.6 m horizontal (Shadram et al.) [S via survey]. NET.
  - Starlink Doppler with OFDM reference signals: 10 m to 6.5 m horizontal (Neinavaie et al.) [S via survey].
  - Starlink carrier phase with adaptive Kalman: 25.9 m horizontal / 33.5 m 3D (Khalife et al.) [S via survey].
  - OneWeb carrier phase, nine satellites, static: 30.4 m 2D (Kozhaya et al.) [S via survey].
  - Iridium Doppler with ephemerides tracked from Doppler/carrier phase: 22 m 2D (Khairallah & Kassas) [S via survey].
  - Multi-constellation (2 OneWeb + 4 Starlink + 1 Iridium + 1 Orbcomm), stationary: 5.1 m 2D (Kassas group 2023,
    https://people.engineering.osu.edu/sites/default/files/2023-05/Kassas_Navigation_with_multi_constellation_LEO_satellite_signals_of_opportunity_Starlink_OneWeb_Orbcomm_and_Iridium.pdf)
    [S].
  - Ionosphere effect on Doppler positioning: VHF up to several km, L-band tens of m, Ku under 1 m [S via survey].
    Supports a frequency-dependent iono term in the sim (Orbcomm and NOAA much worse than Iridium, Starlink nearly
    free of it).

### A.4 More static results and methods (new to both reports)
- Starlink, pseudorange "fused LEO GNSS" by mock implementation: Morgan et al. (UT Austin), "A Mock Implementation of
  Fused LEO GNSS", IEEE/ION PLANS 2025, best student paper
  (https://radionavlab.ae.utexas.edu/wp-content/uploads/morgan_MockStarlink_plans.pdf) [S]: live-signal Starlink
  solutions at about 10 m with minutes of processing delay. Key argument for any differential design [S]: Starlink
  timing errors are beam-specific in the worst case, so a network-aided (base-station) scheme would need reference
  stations closer than one beam, about 20 km. Sim implication [C]: a base-rover Starlink model should decorrelate
  corrections beyond about 20 km or across beams. NET.
- Starlink carrier phase, six satellites, real: 7.7 m horizontal (Khalife, Neinavaie, Kassas 2022 letter,
  https://ece.osu.edu/sites/default/files/2022-09/The_first_carrier_phase_tracking_and_positioning_results_with_Starlink_LEO_satellite_Signals.pdf)
  [S]. Non-differential, static.
- Starlink beacon receiver (Wuhan University), six satellites, field test: 28.9 m 3D, 11.8 m horizontal,
  Systems Engineering and Electronics 46(8), 2024, DOI 10.12305/j.issn.1001-506X.2024.08.01 [S]. Beacon near 11.95 /
  12.45 GHz [S].
- Orbcomm Doppler, BUAA: better than 140 m [S]; Iridium single-tone Doppler, BUAA: better than 200 m [S].
- Ambiguity-resolved LEO carrier phase over short baselines: Yang, Khodabandeh, Zaminpardaz, Teunissen, Journal of
  Geodesy 2025 [S]: frequency-varying (satellite-specific) carrier phase handled with GLONASS-style FDMA integer theory;
  cm-level relative positioning possible on short baselines even at a 50° mask (feasibility, simulated). NET (base).
  Dureppagari et al., arXiv 2603.18360, 2026 [S]: simulated 6G NR-NTN delay + carrier phase, all ambiguities fixed in
  0.5 to 1 s. Neither is relevant to a passive single receiver.
- Chalmers/UAB, Bader, Saleh, Seco-Granados, Noureldin, "Theoretical Limits of Differential Doppler Positioning Using
  LEO Satellite Signals", IEEE GLOBECOM 2025, DOI 10.1109/GLOBECOM59602.2025.11431750
  (https://spcomnav.uab.es/docs/conferences/Theoretical_Limits_of_Differential_Doppler_Positioning_Using_LEO_Satellite_Signals_1779798066.pdf)
  [S]: CRB for position, velocity and frequency bias from Doppler only, with an atmospheric correlation model against
  baseline; differential beats non-differential most at low SNR. Same group as the 2026 asynchronous-clock
  differential preprint in radio.md.
- Geometry-only papers, no numbers: Liu et al. (UAB) arXiv 2603.19499 (single-satellite Doppler DOP: cross-track
  error severe, along-track small) [V abstract]; Thornton arXiv 2606.09496 (orbital-plane dihedral angle governs
  two-satellite conditioning) [V abstract]. Both support a sim rule [C]: a fix from satellites in one orbital plane
  is weak cross-track; require two planes crossing at a useful angle (radio.md already has about 20° for Iridium).

### A.5 Kuiper (Amazon Leo) and direct-to-cell
- Kuiper downlink is Ka band, 17.7 to 19.7 GHz [S]; published Kuiper positioning frameworks (Doppler, and a
  reference-signal design for delay) are simulation only; a Politecnico di Torino paper studies DLL tracking of
  Kuiper "meta-signals" [S]. No real Kuiper signal capture or waveform description found. Ka band is outside any
  RTL-SDR-class front end without a Ka LNB [C].
- D2C: still nothing on positioning from direct-to-cell LTE downlinks. The network pre-compensates Doppler per beam
  (up to 24 ppm), so the user sees only the residual within the beam [S]; this confirms radio.md's point.

### A.6 Clock grade and impairments
- Bezerra de Freitas Diniz, Eriksson, Gustavsson, Saleh, Wymeersch, Euler, "Doppler-Based Localization Under Hardware,
  Atmospheric and Orbital Impairments for Single LEO Satellite Systems", IEEE TAES 62, 2026, DOI
  10.1109/TAES.2026.3717291 (https://research.chalmers.se/publication/553355) [V abstract]: simulation, one satellite,
  one pass, EKF on pilot phase then WLS, with carrier frequency offset, phase noise, atmosphere and orbit errors.
  The 90th-percentile error only falls below 10 km in narrowband line of sight, and under strong phase noise reaching
  10 km takes much of the pass. Independent support for radio.md 2.8: a single satellite with a cheap oscillator
  is a km-to-10-km source, not a navigation aid.
- Jardak, Adam, Jault, "Leveraging Multi-LEO Satellite Signals for Opportunistic Positioning", IEEE Access 2024,
  DOI 10.1109/ACCESS.2024.3456382 [S]: Doppler accuracy measured on real Iridium NEXT, Orbcomm and NOAA captures;
  uses Orbcomm's two frequencies to cut Doppler noise and gives a method to get unambiguous Doppler from NOAA's
  FM-AM (APT) signal; three constellations beat one or two, but mixing them is limited by unequal measurement
  quality. The per-constellation Hz figures are in the paper body, not read (DOAJ 403).

### A.7 Direction of arrival to LEO satellites with three antennas
- StarLoc, "Pinpointing Transmitting LEO Satellites from a Single Passive Array", MobiSys 2026, arXiv 2604.21147
  (https://arxiv.org/abs/2604.21147) [S, abstract-level summary]: three antennas in an L, widely spaced; the
  grating-lobe ambiguity is resolved with the Doppler rate (which is unaffected by the receiver's frequency offset);
  range is inferred from orbital dynamics. Median 0.73° 3D angle error and 5 km range, against 5° for a half-wavelength
  planar array. X/Ku/Ka downlinks. Dataset and code stated public (not downloaded).
- Relevance [C]: the inverse use (known satellite, unknown attitude) would give heading/attitude at under 1° from a
  three-element Ku array, and the Doppler-rate trick removes the cheap-oscillator problem for disambiguation. No paper
  doing that from a moving vehicle was found. Hardware: three coherent Ku channels, i.e. three LNBs on one reference.
- OSU technology listing: passive joint DOA/FOA from received signal strength on commercial phased-array SATCOM
  terminals, combined with Doppler [S]; no new numbers beyond the first report's 21 to 29 m.

### A.8 The closest LEO result to our hardware: RTL-SDR + Pi 4 + consumer IMU on Starlink Doppler rate
- Camuzcu, Hoang, Vahid, "Starlink Beacons for Passive LEO-Aided 9D Navigation", arXiv 2605.20394, May 2026
  (https://arxiv.org/html/2605.20394) [V full text, via summary].
- Idea: measure the Doppler rate (second derivative of range) of Starlink beacon tones, which a constant receiver
  frequency offset does not affect, and fuse it with an IMU for position, velocity and attitude.
- Hardware [V]: Ku LNB on a 12 V battery via bias-tee, RTL-SDR V3, Raspberry Pi 4B, u-blox NEO-M10 GNSS, WitMotion
  WT901C consumer IMU; reference clock not stated.
- Results [V]: hardware capture of about 20 s with five Starlink Doppler-rate updates; post-fit Doppler-rate residual
  median 0.8 Hz/s, mean 1.46 Hz/s, max 3.4 Hz/s across five matched beacons. Simulation (tactical IMU, 5 to 45
  satellites): LEO + IMU 6 to 9 m position RMSE; with GPS 1 to 2 m. Hardware LEO + IMU described only as "several
  metres", "sub-10 m", no number.
- Caveats [C]: TLEs propagated with SGP4 with no orbit-error correction, a 20 s window, and no stated ground truth
  for the LEO-only segment; the "sub-10 m" hardware claim cannot be from absolute positioning with km-level TLE error
  and is best read as bounded drift over 20 s from a GNSS-initialised state. Still, it proves an RTL-SDR on a Ku LNB
  can detect and track Starlink beacon tones post-2023 on a Pi 4, which the first report's "about 20 dB-Hz,
  practically unusable with a small feed" casts doubt on. C/N0 not reported.
- Sim needs [C]: Doppler-rate measurement, σ about 1 to 1.5 Hz/s at 11.7 GHz (about 0.03 m/s² [C]), a few updates per
  20 s, immune to receiver frequency offset but not to frequency drift rate. A drift of 0.1 ppm/min is about 2.5 Hz/s
  on the dongle at a 1.5 GHz IF but about 17 Hz/s on a free-running LNB LO at 10 GHz [C], i.e. ten times the reported
  residual, so the LNB LO's thermal drift is the error term that matters. Model LNB LO drift rate as a random walk
  state, value TBC; a PLL LNB on an external reference removes it.

### A.9 Base-rover residual against baseline geometry (upgrades radio.md 1.4's 7.13 m row from [S] to [V])
- Saroufim, Hayek, Kassas, "Evaluation of Orbit Errors and Measurement Corrections in Differential Navigation With
  LEO Satellites", ION GNSS+ 2023 (OSU PDF,
  https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Evaluation_of_orbit_errors_and_measurement_corrections_in_differential_navigation_with_LEO_satellites.pdf)
  [V full text via extraction].
- Residual geometry [V]: with a 4 km in-track orbit error and a 5 km baseline (Starlink), the differential range
  residual is at most 23 m when the baseline is normal to the estimated range vector projected on the orbital plane,
  and near zero when they are collinear. Sim rule [C]: residual ≈ (orbit error) x (baseline / range) x |sin ψ|,
  about 23 m per 5 km of baseline per 4 km of along-track error, i.e. about 1.2e-3 x baseline x (along-track error
  in km); consistent with the first report's "about 80 m at 14 km".
- Ground vehicle, real [V]: 2 Orbcomm + 1 Iridium NEXT, TLE+SGP4 orbits, base on a roof at a mean 1.1 km baseline,
  540 m in 60 s with the last 40 s (492 m) without GNSS: 7.13 m 3D RMSE differential vs 41.29 m non-differential vs
  87.74 m GNSS-aided INS coasting. NET (base link).
- Simulation [V]: 28 km in 300 s, GNSS for the first 60 s, tactical IMU + altimeter: 52 cm 3D RMSE differential vs
  12.5 m non-differential.
- Kassas group, "Assessment of differential Doppler navigation with Starlink LEO satellite signals of opportunity"
  (2023, OSU PDF) [S]: stationary base and rover 1 km apart, three Starlink satellites: 33.4 m 3D, 5.6 m 2D. The 2D
  number is the survey's "Shadram et al." row in A.3; the 3D number shows how weak the vertical is with three LEO
  satellites, so the sim must keep the barometer in the loop.

### A.10 How much better is "supplemental" orbit data for Starlink? Only about 2x (corrects an implication in radio.md 2.1)
- Constant, Bhattarai, Ziebart (UCL Space Geodesy and Navigation Lab), "Limitations of Current Practices in
  Uncooperative Space Surveillance: Analysis of Mega-Constellation Data Time-Series", AMOS 2023 poster
  (https://cconstant.cc/Figures/AMOS-Poster.pdf) [V full poster text].
- 165,327 TLEs (NORAD and supplemental) for OneWeb and Starlink, 2021-07 to 2023-01, SGP4-propagated and benchmarked
  against Starlink operator ephemerides over 72 h. Supplemental TLEs were 52 % more accurate on average than NORAD
  TLEs, i.e. about half the error, not an order of magnitude. Errors have a once-per-revolution periodicity that
  persists against the operator ephemeris, pointing at the SGP4 force model itself; TLE updates cause position
  discontinuities. Starlink supplemental TLEs are generated about every 8 h; OneWeb does not publish operator
  ephemerides (only Starlink could be benchmarked).
- Correction [C]: radio.md 2.1 inferred an "operator ephemeris tier" from CelesTrak's 10x figure for GPS/GLONASS.
  For Starlink, anything that passes through the TLE/SGP4 format keeps the SGP4 model error, so SupGP is roughly a 2x
  improvement. Only the operator's own ephemeris files (Space-Track, Modified ITC, with covariance) are a separate,
  much better tier. Sim tiers [C, TBC]: NORAD GP (first report's 0.94 km median at 6 h), SupGP about half of that,
  operator ephemeris file metres to tens of metres (value TBD, not found).
- Orbit prediction error for Globalstar and others: Esmaeilkhah & Landry, Eng. Proc. 88:29, 2025 [S]: about 400 m of
  navigation error attributed to predicted-versus-actual trajectory mismatch, nominal drift about 250 m. Globalstar
  Doppler, two real satellites: better than 100 m horizontal (BUAA, year not shown) [S].

### A.11 Doppler-only geometry, satellite count and orbit-age details
- Jankovic, "How long can you trust a Starlink TLE?", arXiv 2605.19850, 2026 [S, secondary summary]: adds to the
  first report's 0.94 km at 6 h: median 3D error about 38.5 km at 7 days; along-track about 100x radial and
  cross-track at every age; a high-fidelity propagator fed from public TLEs does not beat SGP4 (SGP4 wins 65 to 75 %
  of pairs). So better propagation cannot fix TLE error; only fresher or better orbit data can [C].
- Moore, Psiaki, Buehrer (Virginia Tech), "Time-Diverse Doppler-Only LEO PNT: Initial Solution", 2024
  (https://rosap.ntl.bts.gov/view/dot/80647) [S]: snapshot Doppler-only positioning (position, velocity, clock bias,
  drift) needs at least 8 satellites in view; with 6 or 7 it fails, so they use time-diverse measurements assuming
  constant velocity and clock drift, plus a Kalman variant. They state their own 2023 D-GDOP analysis (and the
  "TRANSIT on steroids" model, Psiaki, NAVIGATION 68(3), 2021) made inconsistent assumptions. Related dissertation:
  McLemore, Virginia Tech 2023, LEO RF observables with INS aiding, simulation [S]; its group notes accuracy
  "deteriorates" with motion even with an INS [S].
- Caravaca Gallego, Gurfil, Rotstein, arXiv 2609.11296, Sep 2026 [V abstract]: closed-form Doppler Jacobian; clock
  bias is observable only through a coupling that also inflates covariance; the clock bias-drift correlation cannot
  be removed by any geometry; altitude diversity (two shells) helps. No numbers.
- Ma, Zheng, Liu, Zhang, Nasir, Al-Naffouri, "Orbital Errors in LEO Satellite Positioning: Modeling, Analysis, and
  Bayesian Calibration", arXiv 2511.06060 [V abstract]: TLE error statistics learned from real history used as a
  Bayesian prior; misspecified CRB; simulation; no numbers in abstract.
- Sim implication [C]: with Iridium + Orbcomm + a few Starlink, a snapshot (single-epoch) Doppler fix is usually not
  available (fewer than 8); the EKF must carry clock bias/drift and accumulate over time, and its covariance should
  show the bias-drift coupling. A snapshot-based protection level for LEO is not meaningful.

### A.12 Track on one pass, predict to the next: the closest moving result with a MEMS IMU
- Kassas, Hayek, Ahmad, "LEO Satellite Orbit Prediction via Closed-Loop Machine Learning With Application to
  Opportunistic Navigation", IEEE AES Magazine 2024, DOI 10.1109/MAES.2024.3432105
  (https://par.nsf.gov/servlets/purl/10652800) [V full text via extraction].
- Idea: track the satellite with an EKF during its first pass (receiver known), train a small network on the
  SGP4 error during the gap, and use the predicted ephemeris on the next pass.
- Hardware [V]: VectorNav VN-100 MEMS industrial-grade IMU; VHF antenna into an Ettus E312 USRP driven by a
  free-running CDA-2990 OctoClock (OCXO); Septentrio AsteRx-i V GNSS-INS as truth.
- Result [V]: ground vehicle on the CA-22 freeway, 4.05 km in 140 s, two Orbcomm satellites: 3D RMSE 1,865 m
  unaided INS, 175.5 m LEO-aided with SGP4, 18.3 m LEO-aided with NN-predicted ephemerides. Satellite position error
  from TLE 1.8 km and 5.9 km for the two satellites; tracking reduced these to 278 m and 637 m RMSE (final 199 m and
  279 m).
- Why it matters [C]: this is the first moving LEO result found with a MEMS IMU rather than a tactical one; the VN-100
  is still about an order better than an MPU6050 in bias stability, and the receiver clock was an OCXO. The method is
  the "track while GNSS is good, then predict" pattern in concrete form, with a gap of one orbit (about 100 min for
  Orbcomm).
- Sim needs [C]: per satellite, a "tracked" orbit error state that starts at the tracking residual (about 200 to 650 m
  after one pass) and grows during the gap; the 18.3 m figure over 140 s shows that two satellites plus a MEMS IMU are
  enough for tens of metres when orbit error is at the few-hundred-metre level.
- Related [S]: Hayek, Saroufim, Kozhaya, Barrett, Kassas, ION GNSS+ 2024: ground vehicle with 4 Starlink + 1 OneWeb +
  2 Orbcomm + 1 Iridium NEXT. A search summary gave "4.15 m RMSE", which looks like a mix-up with the first report's
  4.15 km trajectory (18.4 m RMSE); treat the 4.15 m as unverified.
- Not read: UT Austin final report for US DOT, "PNT Protection Through Interference Monitoring and Robust Backups to
  GNSS" (Humphreys et al., Jan 2026, https://rosap.ntl.bts.gov/view/dot/93531): the PDF exceeded the fetch size limit.
  A TRB project summary attributes "10 m-level positioning and 30 ns timing using Starlink" to the team [S], not
  confirmed.

### A.13 Starlink frame-clock numbers and other details
- Qin et al., "Timing Properties of the Starlink Ku-Band Downlink", arXiv 2501.05302 (2025) [S, search summary of the
  arXiv text]: periodic base-oscillator adjustments cause abrupt frame-timing jumps of about 120 ns on v1.0/v1.5
  satellites and about 10 ns on v2-Mini, common to all beams of one satellite; frame timing is disciplined to GPS
  only loosely, within a few ms, by adjustments every 15 s. Upgrades the first report's qualitative statement and
  radio.md's "substantially higher than 1 ns". For Doppler (not pseudorange) the relevant part is the frequency
  steering behind these jumps; the sim should give Starlink satellites a frequency-step process (TBC) rather than
  ideal clocks. OneWeb, by contrast, is consistent enough across beams of one satellite for network clock
  corrections within one footprint [S].
- Iannucci (UT Austin), GPS.gov advisory board slides 2019 [S]: error budget for a purpose-built (cooperative) LEO
  GNSS with 1 to 50 s ephemeris age: orbit 0.037 m radial / 0.057 m along-track, clock 0.271 m, iono 0.028 m, tropo
  0.050 m, noise+multipath 0.005 m; user range error about 0.31 m. Useful only as the ceiling for Xona-like services,
  not for opportunistic signals. NET.
- NOAA [V abstract, Kozhaya, Kanj, Kassas, ION GNSS+ 2023]: NOAA at 137.0 MHz was acquired and Doppler-tracked blind
  with a USRP E312 and a consumer QFH antenna over an 800 s pass, but no NOAA-only position is reported; the 5.1 m
  2D figure in A.3 is from the same paper, using nine satellites (4 Starlink, 2 OneWeb, 1 Iridium, 1 Orbcomm,
  1 NOAA), static, starting 3,600 km off, with a 60 cm Ku dish.

### A.14 Six orbit-error frameworks compared on the same kind of data (the key 2025 summary paper)
- Kassas, Saroufim, Hayek, Kozhaya, Barrett, "Towards Navigation with Non-Cooperative LEO Satellites: Resolving
  Ephemeris and Timing Errors", 2025 (OSU PDF,
  https://people.engineering.osu.edu/media/document/2025-05-19/kassas_towards_navigation_with_non_cooperative_leo_satellites_resolving_ephemeris_and_timing_errors.pdf)
  [V full text via extraction]. Frameworks: F1 open-loop TLE+SGP4; F2 differential TLE+SGP4 (base, NET); F3 STAN
  (receiver estimates satellite states too); F4 differential STAN (NET); F5 long-baseline ephemeris corrections, two
  parameters per satellite sent from a reference (NET); F6 equivalent timing error (epoch shift) estimated on board
  or at a base.

| Exp. | Platform and signals | Result |
| --- | --- | --- |
| E1 | ground vehicle, 2 Starlink + 1 OneWeb + 2 Orbcomm + 1 Iridium, industrial IMU + altimeter, 540 m in 60 s, GNSS only for the first 48 m, base 1.2 km | 3D RMSE F1 41.3 m, F2 7.1 m, F3 10.7 m, F4 6.8 m; final errors 112.6 / 5.4 / 19.5 / 10.2 m |
| E2 | stationary receiver, 7 Starlink, reference station 635 km away (St. Louis to Columbus) | from 200 km initial error to 8.8 m horizontal with F5 |
| E3 | stationary, 3 Starlink + 2 OneWeb, F6 on board | from 11.3 km mean initial error to 3.2 m (carrier phase) / 7.9 m (Doppler) mean 3D |
| E4 | DJI M600 UAV, altimeter, 2 Orbcomm carrier phase, 780 m in 90 s, GNSS lost for the last 60 s | 3D RMSE F1 76 m, F6 12.3 m |
| E5 | ground vehicle, 4 Starlink + 1 OneWeb + 2 Orbcomm + 1 Iridium, 1.58 km in 70 s, last 1.05 km without GNSS | baseline solution 110 m RMSE / 322 m final; F6 4.2 m RMSE / 8.1 m final |

- What is new for us [C]: (1) STAN without any base (F3) gets 10.7 m on a vehicle, only about 1.5x worse than
  differential, so a base station is not essential once orbit errors are estimated on board; (2) ephemeris
  corrections stay useful across a 635 km baseline when sent as two parameters per satellite (F5), i.e. one reference
  receiver could serve all of Ottawa and beyond, unlike raw measurement differencing (A.9, residual grows with
  baseline); (3) a UAV with only an altimeter and two Orbcomm satellites (carrier phase, high-end VHF antenna, Ettus
  radio) held 12.3 m over 60 s with F6. Hardware in all experiments was lab grade (USRP-class radios, OCXO or better).
- Sim needs [C]: implement F6 as one epoch-shift state per satellite (the first report already proposes this) and
  F5 as an optional NET input of two parameters per satellite at a slow rate; compare F1/F3/F6 in the sim.

### A.15 Other leads, no numbers
- ESA-funded project, UAV Navigation-Grupo Oesía with Inster, CTTC and SICWAVE (announced Oct 2026) [S]: LEO
  communication signals into a UAV autopilot, with position observables from multibeam electronically steered
  antennas; flight-representative tests planned, no results yet.
- Hasan, Kabir, Han, Shin, Poor, "Beyond GNSS: Leveraging LEO Satellite Signals of Opportunity for Doppler
  Positioning", arXiv 2611.03440, Nov 2026 [V abstract]: tutorial/survey plus a ray-tracing NTN simulator
  (SionnaNTN-RT) for Doppler positioning in urban and open sky; no numbers in abstract. Possible source of a
  multipath-aware LEO Doppler error model.
- Iridium in a high-dynamic vehicle aim, static 25 m in 5 min: Sensors 22(7):2541, 2022 [S].

### A.16 Receiver clock handling in Doppler-only solutions
- Wang, Qin, Liang, Zhang (BUAA), "Clock Error Analysis and Compensation for LEO Signal of Opportunity Positioning",
  IEEE Sensors Journal 24(8):12716-12727, 2024 [V abstract]: real Iridium captures with receivers of different clock
  quality; multi-epoch Doppler positioning is limited by poor receiver clock stability; an LSTM + error-state Kalman
  filter clock compensation improves accuracy by "one order of magnitude" over the traditional method when the clock
  is poor. No absolute numbers in the abstract. This is the only real-data study found that varies the receiver clock
  grade on LEO Doppler; it supports modelling the dongle clock as the dominant term.
- Convergence limits [S]: a Doppler-only point solution (GPS Solutions 2023, s10291-023-01466-w) needs an initial
  position within about 300 km at 550 km altitude; between-satellite differencing removes receiver clock drift and
  improves accuracy about 10 %. UAB outer-loop framework (Satellite Navigation 2026): a receiver clock error above
  50 ms becomes intolerable when the initial position error reaches 200 km. Sim implication [C]: cold start needs a
  coarse prior (last GNSS fix, or cellular), which we always have.
- Kassas group simulation [S, fragmentary]: with satellites carrying chip-scale atomic clocks and an OCXO receiver,
  28 cm (pseudorange) vs 1.94 m (Doppler) 3D; not opportunistic.

### A.17 Industry: LEO Doppler is now in fielded alternative-navigation products (no accuracy published)
- Honeywell Alternative Navigation Architecture (HANA), launched Oct 2025 [V Honeywell blog; S press]: at Army APEX
  (White Sands, Sep 2025) Honeywell flew three modalities feeding the INS, vision-aided, magnetic-anomaly and LEO
  satellite navigation; LEO signals used as "an additional ranging and timing source" [V]; constellation, platform
  and accuracy not stated [V]. Honeywell's site lists LEO navigation as available in 2026 and a trade article says it
  was shown for smaller drones at JamFest (Barcelona, Jun 2026) [S]. Relevance: the challenge sponsor already treats
  LEO as one aid among several inside an INS, not as a stand-alone fix, which matches A.14's results.
- Draper, Jun 2025 [S]: a "Signals of Opportunity" unit with a Ku-band receiver collecting LEO internet constellation
  signals flown on a twin turboprop for more than 30 h up to 25,000 ft, day and night, to validate a LEO-Doppler
  navigation design; no accuracy published.
- UAB SPCOMNAV (ENC 2025, Eng. Proc. 126:12) [S]: a synchronised multi-SDR testbed (Orbcomm SDR as master, Iridium
  and Starlink SDRs as slaves) for simultaneous multi-constellation capture; this is the shared-reference
  architecture the first report proposes for our dongles. No numbers seen (MDPI 403).
- Shi, Zhang, Li, "Revisiting Doppler positioning performance with LEO satellites", GPS Solutions 27:126, 2023 [S]:
  the source of the orbit-sensitivity table in A.2. Meter-level Doppler positioning needs satellite position errors of
  a few metres and velocity of a few cm/s; without tropospheric correction, tens of metres of degradation.
- Kassas, Barrett, Kozhaya, Marsh, "Navigating the Arctic Circle with Starlink and OneWeb LEO Satellites", IEEE
  MILCOM 2025, best unclassified paper [S, OSU news Dec 2025]: ship off west Greenland, Starlink + OneWeb + altimeter,
  no GPS: 27 m vs more than 1 km altimeter-only. No operator help. A second Arctic number beside radio.md's Baffin
  Island 123 m (Starlink only, Pi 4, no IMU); conditions (duration, hardware, orbit handling) not read.
- OneWeb signal parameters (Komodromos et al., UT Austin,
  https://radionavlab.ae.utexas.edu/wp-content/uploads/komodromos_oneweb_parameter_estimation.pdf) [S]: single-carrier
  QPSK at 230.4 MBd; a short synchronisation sequence repeating every 1 ms is what enables pseudoranges. Hardware
  implication [C]: full-band OneWeb is far beyond any RTL-SDR-class front end; only a narrowband Doppler use of a
  Ku LNB output would fit, and no paper doing narrowband OneWeb Doppler was found.
- Stock, Schwarz, Knopp (UniBw Munich), "Error Source Analysis for Doppler Shift Based Opportunistic LEO-PNT With
  Starlink Signals", IEEE/ION PLANS 2025, and slides at the IEEE LEO Sats workshop, May 2025
  (https://leosats.ieee.org/wp-content/uploads/2025/09/5-stock-doppler-shift-based-opportuni.pdf) [V slides; numbers
  only in figures, not extractable]: static stand-alone receiver, multi-epoch Doppler from consecutive Starlink PSS
  (300/100/10 PSS per estimate); budget = sqrt(freq-estimation² + orbit² + clock² + atmosphere²) x PDOP, with the
  frequency term from a modified CRB and the clock term from Allan deviation through a third-order PLL. Companion:
  Stock, Hofmann, Knopp, "Correlation-Based Doppler Shift Estimation for Opportunistic LEO-PNT With Starlink
  Signals", IEEE WiSEE 2024. This is the budget structure our sim should mirror; the values must come from elsewhere
  (A.2, A.10, radio.md 2.8).
- Orbcomm frequency estimation must model the in-burst frequency chirp; a coarse-plus-fine estimator using ephemeris
  priors (MDPI Electronics 13(24):4882, 2024) [S].

## Topic B. Iridium

### B.1 Measured frequency instability of low-cost SDRs, with and without a reference (sim values for the receiver clock)
- Bednarz, Wojtuń, Kelner, Różyc, "Frequency Instability Impact of Low-Cost SDRs on Doppler-Based Localization
  Accuracy", Sensors 24(4):1053, 2024 (PMC10892359, read via Europe PMC full-text XML) [V, first 100k characters].
- Measured at 1358 MHz (close to Iridium's 1626 MHz) against a Keysight generator; mean offset μf, standard
  deviation of instantaneous frequency σf, fractional stability sf [V]:

| SDR | free-running μf / σf (Hz) / sf | with 10 MHz Rb reference μf / σf (Hz) / sf |
| --- | --- | --- |
| ADALM-PLUTO | 16,757 / 285.9 / 2.1e-7 | -55.2 / 5.1 / 3.8e-9 |
| USRP B200mini-i | 1,437 / 5.5 / 4.6e-9 | 0.00 / 1.29 / 9.5e-10 |
| USRP N210 + WBX | 1,010 / 179.9 / 1.2e-7 | 0.01 / 0.014 / 1.0e-11 |
| USRP-2950R | 928 / 13.9 / 9.6e-9 | -0.01 / 0.012 / 8.7e-12 |
| bladeRF 2.0 micro xA4 | -37.5 / 34.7 / 2.4e-8 | -0.20 / 0.010 / 7.1e-12 |
| USRP N210 + RFX1200 | 1,180 / 78.6 / 6.1e-8 | 0.01 / 0.008 / 5.7e-12 |
| USRP-2930 | 93 / 96.3 / 7.7e-8 | 0.01 / 0.005 / 3.9e-12 |

- Effect on Doppler localization (their geometry: an airborne sensor locating a ground emitter, the reverse of
  ours) [V abstract]: an external standard cut location error from about 20 km to about 30 m (long range) and from
  about 15 km to about 2 m (short range). With σf = 95 Hz uncompensated, mean error about 15 km, max about 120 km.
  They propose a CSAC (SA.45s) with a bladeRF or B200mini for a fielded sensor.
- Sim values [C]: a free-running low-cost SDR at L band has a static offset of 0.6 to 12 ppm (1 to 17 kHz at
  1.4 GHz) and short-term jitter σ 5 to 290 Hz (3e-9 to 2e-7); RTL-SDR not tested, the PlutoSDR row is the nearest
  analogue for an uncalibrated crystal and the B200mini row for a good TCXO. Locked to a good reference, σ falls to
  0.01 to 5 Hz. At 1626 MHz, 1 Hz is 0.18 m/s of range-rate [C]. This directly supports radio.md 1.1's 80 to 100 Hz
  rover RMS with a free-running SDR, and says a shared disciplined reference buys two to four orders of magnitude.

### B.2 Broadcast satellite position and time fields: what they are worth (hobbyist measurements)
- Osmocom developer call, "Iridium update (public)", 25 Mar 2022, by the gr-iridium maintainers
  (https://people.osmocom.org/laforge/OsmoDevCall/20220325-Iridium-Update-Public.pdf) [V slides via text extraction].
- Broadcast satellite position (ring alert, IRA) is quantised to about ±4 km in X/Y/Z, so it must be interpolated
  across frames [V]. IBC frames give the Iridium time at the start of a 90 ms frame [V].
- Passive localisation from IBC frame timing (time of arrival) plus IRA satellite positions, simple least squares:
  about 1,000 m "if averaged over time" [V]. Timestamps used a USRP B200 with PPS from a GPS receiver; an unexplained
  offset of about 9.5 µs to time-of-flight-compensated Iridium time remained; a cheap GPSDO showed about 350 ns jitter
  against a lab GPS receiver [V]. The published frame structure on the internet was wrong (guard time after the last
  uplink slot 0.24 ms, not 0.22 ms) [V].
- Implication [C]: the broadcast position fields are useful for satellite identification and as a sanity check
  against TLEs (±4 km is no better than a fresh TLE), not as an ephemeris. Iridium pseudoranges from frame timing are
  km-class without GNSS-grade receiver time and still carry a µs-level unexplained offset; Doppler is the better
  observable. This upgrades radio.md 1.6 ("no accuracy for these positions found").
- Measured SDR frequency offsets at Iridium [V]: USRP B200 -5 ppm (with sample overflows) or -1.5 ppm (without),
  about 0 with GPSDO; bladeRF 0.1 ppm; rad1o -35 ppm. At 1626 MHz, 1 ppm = 1.63 kHz [C].
- Hardware note for our Pi [V]: "RPI4 GbE is noisy, USB3 as well": Raspberry Pi 4 Ethernet and USB3 radiate at
  L band into an active Iridium antenna; keep the antenna away and use good USB3 cables (they moved to an Odroid N2+).
  The RTL-SDR Blog L-band antenna has poor out-of-band rejection. A gr-iridium FFT channelizer used about 50 % of
  one Pi 4 core at 8 MS/s into 17 channels [V], so Iridium decoding at 2.4 MS/s fits on the payload Pi.

### B.3 Iridium's paid PNT service: product details (vendor claims; no independent airborne test found)
- RockBLOCK APNT data sheet, Ground Control, version RBAPNT-001-AUG26
  (https://www.groundcontrol.com/wp-content/uploads/2026/08/RockBLOCK-APNT-Data-Sheet.pdf) [V full text]: additions to
  radio.md 1.6: power 0.95 W idle, 1.2 W peak (5 V USB-C or 3.3 V); -20 to +70 °C; host protocol "proprietary
  NMEA-0183 sentences" at 115,200 baud; receive only, 1616 to 1626.5 MHz, u.FL, recommended antenna Calian
  33-HC610-28; timing stability under 50 ns and an average offset within 5 ns of UTC(NIST) over 60 days (vendor);
  position accuracy only the field medians already known (25 m at 69°N, 42 m at 19°N). No time to first fix, update
  rate, velocity output or price is stated. NET (Iridium PNT subscription; terms not published).
- Iridium PNT ASIC, model 7010, commercially available 14 Jul 2026 [S, Iridium press release]: more than 150
  organisations asked for it after the Oct 2025 unveiling; integrators named are Solace Communications ("Vector"
  assured-PNT line) and Skyband Systems (M100 LRU for business and commercial aviation). Price still unpublished.
- Ground Control "RockFLEET Assured" data sheet (Jul 2026) [S]: 95 % under 50 m at 69°N.
- Sim model [C, TBC]: a NET position source with horizontal σ about 20 to 35 m (median 25 to 42 m), latitude
  dependent (better at high latitude; Ottawa at 45°N should fall between, TBD), timing σ tens of ns, update rate TBD,
  1 W power. Independent of GNSS and of our own Doppler pipeline, so it is a clean spoof-check reference.
- Upgrade to radio.md 1.6 timing [S]: NIST, "Validating timing performance improvement from ionospheric corrections
  in Iridium PNT receivers" (ION PTTI 2026), already summarised there; NIST TN 2187 (2021) called STL capable of
  microsecond accuracy; Satelles 2017 claimed under 100 ns with a high-quality clock, differential under 250 ns.
- ATMOSPHERE PLANET 9770 PNT terminal for UAVs (Jul 2026) [S]: Iridium satcom terminal with a PNT configuration
  (manual dated 2 Jul 2026, P/N TE02405XX), 750 g, 205 x 120 x 50 mm; "validated at Jammertest 2025"; no accuracy
  published. Shows the drone-integrator route; far heavier than the 10 g board. NET.

### B.4 Iridium jamming and spoofing (additions to radio.md 1.7)
- "Systematic Security Analysis of the Iridium Satellite Radio Link", arXiv 2603.12062 (2026) [S, summary of the
  arXiv HTML]: details beyond radio.md: ring alerts can be jammed on the downlink frequencies with a continuous wave
  or with valid-looking dummy frames, within line of sight; SIM key extraction allows cloning; a nearby transmitter
  can impersonate a satellite. Sim: Iridium Doppler is not a trusted source under an adversary, only an independent
  one; the integrity layer must still check it.
- Attacks on SatIQ (RF fingerprinting of Iridium transmitters, the defence radio.md cites from SpaceSec 2024):
  arXiv 2506.06119 (Jun 2025, rev. Feb 2026) [S]: an optimised jamming signal causes 50 % authentication error at an
  attacker-to-victim power ratio as low as -30 dB; spoofing and a data-poisoning attack that makes message spoofing
  persistent are demonstrated. So fingerprinting is not a robust defence for an opportunistic Iridium receiver.
- No independent evaluation of the paid service's spoofing resistance was found (only vendor claims of cryptographic
  authentication).
