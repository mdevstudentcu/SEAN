# Celestial / magnetic / exotic: pass 2 (finishing topics left open by celestial-conventional.md)

- Date: 2026-11-11. Only items new or corrected relative to `reports/sources-research-20261111.md` and `celestial-conventional.md`.
- Labels: [V] read today in primary source; [S] snippet/secondary; [M] memory; [C] own arithmetic.
- Flags: TX, OPTICAL, NET.

Topics A-F of the pass-1 gaps, finished. Sections 1, 3, 4 and 5 (coverage, corrections, nothing found, judgement) are at the end, after the topic findings and section G.

## A. Magnetic-anomaly navigation (MagNav)

### A1. Licence correction (most important item in this topic)
- **MagNav Challenge data (Zenodo 12723700) is NOT freely usable.** The record's LICENSE.md says public domain, but the record also carries `DATA_SHARING_AGREEMENT.md`, "Air Force Acceptable Use Agreement (ver 20200211)" [V, read today via Zenodo preview]:
  - Licence is "limited personal, non-exclusive, non-transferable, non-assignable, and revocable", "solely for the purpose of non-profit research, non-profit education, or for government purposes". No other use licensed.
  - No redistribution: collaborators must request access separately from the Air Force. Lasts one year from approval; data must be expunged at the end.
  - "Effective as of the date of approval by Air Force"; the Air Force may refuse access. Publications must cite Cooperative Agreement FA8750-19-2-1000 and be sent to the Air Force.
  - Consequence: a hackathon entry with commercial intent is outside "non-profit research/education"; owner and probably university sign-off needed. MagNav.jl (the MIT package) auto-downloads this data on use [S], so installing and running it would trigger the download. Flag as third-party code that downloads data.
- **Canadian government maps are open.** NRCan aeromagnetic maps on open.canada.ca carry "Open Government Licence - Canada" [V, example record 4c748c57..., Ontario vertical-gradient map]. National compilation: 200 m residual total-field and first-vertical-derivative grids, plus 1000 m grid, via the Geoscience Data Repository [S, archived NRCan page]. Owner go-ahead still needed before download.

### A2. Ottawa map coverage, correction
- Eastern Ontario survey (Ontario Geological Survey Geophysical Data Set 1075, flown late 2013, released June 2014): 400 m line spacing, 12,515 km^2, 34,724 line-km, east of 76.51 W to the Quebec border [V, AAPG abstract]. Terrain clearance not stated.
- **But the highly urbanised areas of Ottawa and Cornwall were excluded from that survey** [S, GSA 2015 abstract snippet; page timed out]. So the 400 m data does not cover the city; the city falls back to the older 800 m-spaced coverage / 200 m national grid. The first pass said the survey "covers Ottawa": correct to "surrounds Ottawa, urban core excluded (TBC from the OGS GDS 1075 metadata)".
- **Diurnal correction is locally available:** NRCan's Ottawa magnetic observatory (IAGA OTT, 45.403 N, 75.552 W, since 1968). 1-minute streams relayed via GOES in bursts every 12 minutes; 1 s Level-2 data with DOI 10.48322/d1rf-a974 [S]. A live base-station correction is NET with about 12 min latency; offline replay can use the archive. Data terms not found (INTERMAGNET policy probably applies).

### A3. New flight results
| Result | Platform | Numbers | Evidence |
|---|---|---|---|
| SandboxAQ AQNav + Acubed (Airbus), Jul 2025 | Beechcraft Baron 58, unshielded, public maps, >150 flight-hours, ~200 airports, 5 months | best single 1 h flight < 74 m (mountain/forest, California); RNP 2 met 100% of time, RNP 1 95%, RNP 0.3 (550 m) 64%; beat free INS 100% of flights > 2 h | [S, press: thequantuminsider, gpsworld] |
| Q-CTRL Ironstone Opal, Jul 2026 | crewed aircraft, helicopters, drones | first quantum nav system qualified to RTCA DO-160; "validated in flight to RNP 0.3 (0.3 NM, 95%)"; UAV version previewed at Farnborough 2026; maritime trials early 2026 | [S, Q-CTRL press, Janes] |
| Canciani & Raquet 2016 (citation chase) | fixed-wing survey data | 13 m with marginalised particle filter | [S, cited in navi.717] |
| AFIT Clarke thesis 2021 | F-16 | limited compensation cuts 10,000 nT platform field to ~15 nT | [S] |
| VT thesis (indoor) | quadrotor, own indoor field map | 0.2 m in 5 of 8 flights; indoor building field, not crustal | [S] |
| SMART 2025 (IPPT PAN) | VTOL UAV, scalar magnetometer, over water | particle filter "significantly reduced" error vs dead reckoning; no number retrieved (PDF unreadable to the fetch tool) | [S] |
- Still no outdoor multirotor MagNav position number. The [S] summary of one 2025 paper lists "small-form-factor magnetometers with good stability and correct upward/downward continuation" as the open problems for drones.

### A4. Platform noise on small electric multirotors (numbers for the sim)
- DJI M300 RTK, vendor study (SPH Engineering, CNR-IREA): rigid arm at 0.5 m from airframe about 10 nT oscillation, at 1 m about 5 nT, with a clear 50 Hz EMI line; MagArrow slung 3 m below: under 1 nT [S, vendor page].
- USGS (Phelps et al. 2022, J. Applied Geophysics): multirotor sling; 5 m sling cuts noise about 4x versus 3 m; 50% of noise < 0.3 nT, 90% < 0.6 nT [S].
- Survey noise targets in the UAS literature: < 10 nT (Kaneko 2011), < 1 nT (Parvar 2016), < 2 nT (Sterligov 2016; Tuck 2018) [S].
- Compensation: PG-TLNet (Drones 2025/26): interference up to 1000 nT, residual 0-30 nT, improvement ratio up to 15, < 94 us latency [S]. TU Delft MSc 2025 (van der Meer, with TNO; fixed-wing UAV, 273 logged platform signals): extended Tolles-Lawson IR 7.31 scalar / 18.76 vector vs 4.90 / 10.19 for standard TL; adding an MLP on field-projected features helps, derivative features overfit [S]. Large UAV, South China Sea (Sensors 24:3775): 0.0385 nT SD, IR 4.17 [S]. Multirotor three-component compensation < 0.72 nT [S].
- [C] Implication: a small quad with the sensor on a 0.5-1 m mast sees 5-10 nT of platform noise after nothing more than distance; on a 0.2 m mast expect tens to hundreds of nT (cf. the 350 nT at 0.4 m in pass 1). Compare with the anomaly signal over Ottawa lowland, tens to a few hundred nT at 100 m AGL [M]. Small-quad MagNav needs a 1 m+ boom or sling, which conflicts with flight dynamics.

### A5. Map resolution, altitude and integrity
- Rule of thumb [S, arXiv 2609.27553 snippet]: "the effective resolution of the anomaly field at a given altitude is roughly that altitude"; gradients fall with altitude so observability falls. Maps can be upward-continued but not reliably downward-continued, so flying **below** the survey height (a drone at 100 m under a 150-300 m survey) loses the short-wavelength content the drone actually sees [S].
  - [C] A drone at 100 m AGL needs about 100 m map resolution; the 400 m line-spaced Eastern Ontario survey and the 200 m national grid both under-resolve it, so map error will be spatially correlated and larger than nominal.
- Sengupta, "A Horizontal Accuracy Metric for Magnetic Navigation", NAVIGATION 72(4), Dec 2025, doi 10.33012/navi.717 [V abstract/page]: MagNav error is direction-dependent (principal-axis sigma ratio about 0.4 at the example site), so ARAIM-style HPL that assumes equal axes is wrong; derives a radial limit sigma about 0.408 r_RNP; Hoyt distribution allows 20% relaxation when axis ratio <= 0.5; CRLB examples at 1000 m altitude, 85 m/s, 25 nT total uncertainty (5 nT called achievable). Directly usable for a direction-aware protection level.
- Hager, Bryne, Lillelund, Olsen, Krauser, Johansen (DTU/NTNU/Airbus), "Robust Magnetic Anomaly Navigation under Changing Magnetic Field Gradients", ECC 2026, pp. 317-324 [V abstract]: ESKF on SE2(3); gradient-adaptive measurement covariance from map variability; optimistic static noise fails at low gradient and low speed; a conservative fixed noise was most robust. Sim implication: inflate R in flat areas or the filter diverges.
- Kang et al., "Optimal Trajectory Generation for Improved Magnetic Navigation", arXiv 2609.27553 (Sep 2026, NPS): trajectories chosen for gradient give "substantial" error reduction vs straight lines; no numbers in abstract [V abstract].
- Blakely & Nielsen (AFIT), "Analysis of Magnetic Anomaly Maps and Navigation Performance Using Flight Test Data", PLANS 2025, pp. 802-808: six NGA maps differing in levelling (unlevelled, levelled, micro-levelled) and line spacing; numbers paywalled [V abstract].
- Saltus, Chulliat, Califf (CIRES), EGU26-14369: replace the "stack of upward-continued FFT grids" by an equivalent-source model so anomaly, gradient and **their uncertainty** can be queried anywhere [V abstract, no numbers]. Angappan et al., arXiv 2606.14623: unified geophysical data requirements for MagNav; says a map is "fully resolved" at an altitude only if fully sampled there; mentions a forthcoming SandboxAQ paper linking map resolution to performance bounds [V abstract/S].
- ICCP-type contour matching (Chinese literature): sim errors 100-200 m with INS scale error; gradient-ICCP 26.7 m vs 737 m classic; diverges with large initial error [S]. Particle or point-mass filters dominate recent work.

### A6. Canadian activity
- SBQuantum (Sherbrooke): about CAD 3M of DND/IDEaS contracts for quantum (NV-diamond) magnetometers aimed at jam-resistant PNT [S, aggregator press]. No DRDC MagNav publication found.

### A7. Simulator needs (consolidated, adds to pass 1)
- Measurement: scalar total-field anomaly (nT), optionally vector/gradient. Map: grid at survey height, upward-continued to flight height; a map-error field that is spatially correlated, larger where line spacing > flight height, and larger in excluded urban cores.
- Platform: residual after compensation, 1-10 nT (sling or 1 m boom) to 30+ nT (short mast, electric quad), plus a 50 Hz-class EMI line and current-correlated term.
- Temporal: diurnal and storm variation 10-50 nT (more in storms) unless OTT-corrected (NET, 12 min latency).
- Filter: particle/point-mass or factor-graph; gradient-adaptive R; direction-dependent error ellipse for PL (Sengupta); entropy-based ambiguity flag (O'Leary, pass 1).
- Failure modes: flat field (divergence), map-altitude mismatch, multimodal posterior, uncompensated manoeuvre noise.

Searches on topic A: 17. Last 8: 4 produced new items (Ottawa exclusion, OTT observatory, SBQuantum, Ironstone DO-160). **Not saturated** by the 8-in-a-row rule; returns now mostly repeats of the same 2025-26 stream.

### A8. Late additions to A (found while searching B)
- **Honeywell + DIU MagNav flight, Sep 2026** (relevant: Honeywell is the challenge sponsor). Program "Transition of Quantum Sensing" started spring 2024; 72 proposals; Honeywell Aerospace chosen. Civil Embraer 170, Seattle area to southern Alaska and back, 4 h 23 min with navigation from MagNav alone; quantum magnetometer. Headline: "89% more accurate than backup navigation" (radar mapping and visual cues), **no metres published**. C-17 demo planned later in 2026 [S, DefenseScoop 2026-09-08, Leeham 2026-09-09, ExecutiveGov].
- **SandboxAQ AQNav on Northrop Grumman Lumberjack (expendable jet drone), 2025-26:** flew under jamming with an OPM-based magnetometer plus visual navigation; announcement gives no date, route, duration or error [S, trade press].
- **Strathclyde, "Flying optically pumped magnetometers for navigation and sensing"**, Scholes et al., Proc. SPIE 13674, 1367404, Oct 2025 [V abstract]: OPM on a multirotor; hard- and soft-iron distortion of the platform; **motor noise frequency is linear in throttle, magnitude is not**; multi-motor interactions give modulated components; noise correlates with pilot inputs. No numbers in abstract.

Searches on topic A (incl. late items): 17 + 3 = 20.

## B. Exotic and bio-inspired cues (2022-2026)

| Item | What | Numbers | Use for us | Evidence |
|---|---|---|---|---|
| Boeing + AOSense quantum IMU, 2024 | six-axis atom-interferometer IMU in a full INS on a Beechcraft 1900D, 4 h without GPS; built from three lab single-axis sensors in 15 months | **no drift published**; stated aim "tens of km to tens of m" over long flights (a target, not a result) | none for small drones | [S, Boeing-derived press] |
| ONERA GIRAFE quantum gravimeter + DTU iMAR strapdown, Iceland/Greenland (Twin Otter) | Jensen et al., *Earth Syst. Sci. Data* 17:1667, 2025 | **1-2 mGal accuracy for both sensors**, depending on field roughness (cross-over analysis); earlier GIRAFE flight 0.6-1.3 mGal (arXiv 2210.07865) | **corrects pass 1** ("DTU/ONERA Greenland flights published no results"). Survey accuracy, not navigation | [S, ESSD abstract and referee report] |
| Q-CTRL gravimetric navigation at sea, Aug 2026 | Australian Navy vessel | no numbers in snippet | ships only | [S] |
| NV-diamond magnetometers | Zhejiang integrated unit 2.14-4.58 nT/sqrtHz over 1.3-625 Hz (arXiv 2508.03237); portable vector unit about 400 pT/sqrtHz (arXiv 2509.19179) | no flight navigation result | sensor noise floor for a sim | [S] |
| Distributed NV sensing for geo-localisation, Le, Guo, Liu, arXiv 2512.11300 (Dec 2025) | snapshot map matching (gradient-space Mahalanobis search) without a prior; simulated over four US/Canadian cities | "sub-kilometre median" error in high-gradient regions; corner-space search 4-8x faster in smooth areas | lost-in-space initialisation idea for MagNav; simulation only | [V abstract] |
| OPMs on drones | Strathclyde SPIE 2025 (see A8); Memphis QuSpin QTFM on a UAV (vehicle detection at 5-10 m); Leibniz Hannover hot-vapour OPM at 1 kSa/s on a drone (WOPM 2025 poster) | no navigation numbers | sensor exists in drone size; platform noise is the blocker | [S] |
| Fully neuromorphic drone, TU Delft (Paredes-Valles et al., arXiv 2023; reportedly *Science Robotics* 2024) | spiking network maps raw events to ego-motion and control; sim-to-real | relative ego-motion only | no absolute fix; note only | [S] |
| Event-based VIO with spiking networks, York PhD thesis 2025 (Mackenzie) | states no fully event-based VIO on real data exists yet | — | — | [S] |
| van Dijk, De Wagter, de Croon, "Visual route following for tiny autonomous robots", *Science Robotics* 2024 | ant-style snapshots plus odometry on a 56 g Crazyflie, microcontroller only | about 100 m routes; memory 0.65 kB or 1.16 kB per 100 m (sources disagree) | route-repeat class (like teach-and-repeat); return only | [S] |
| Bee-Nav (Nature 2026) detail | in 30 x 40 m halls cancelled drift after outbound legs up to 110 m | adds the indoor-hall condition to pass 1's numbers | — | [S] |
| BIT "brain-inspired" framework, late 2025 | insect path integrator + bird-style fusion of quantum magnetometer, polarisation compass, vision + rodent-style cognitive map | no flight numbers; preprint/review | — | [S] |
| Muon positioning update | MuWNS 3D poster (Muographers 2026): about 20 cm at about 7 m from reference detectors, reference detectors with about 30 mrad angular resolution; muon flux about 100 Hz/m^2 limits rate. ESA NAVISP MANTA (Muon-Augmented Navigation and Timing Architecture) started Feb 2026, 24 months, for underwater/underground/deep indoor | NET (reference detectors) | not for flight | [S] |
| Acoustic self-localisation | Serussi et al. 2024 (cited by arXiv 2502.20325): location from the drone's own propulsion sound picked up by a circular microphone array, transformer inverse model; extended to real recordings. Sun et al. 2025 "Acoustic Inertial Measurement": < 0.5 m over 20 m with **distributed** arrays (NET). AFRL infrasound array (ION ITM 2017): +/-3 deg bearing to impulse sources | indoor / near-structure or ground arrays | nothing for open-air drone self-location; confirms pass 1 | [S] |
| Pressure-field cues | only barometric **vertical** aids: DLR vertiport reference-station barometry for UAM (NET); pressure vs geodetic altitude can differ by hundreds of metres (Simonetti & Garcia Crespillo, NAVIGATION 2024) | — | confirms pass 1 "no horizontal pressure-pattern work" | [S] |

- Ambient seismic and Schumann-resonance navigation: nothing found.
- Quantum IMU on a small drone: nothing found (Infleqtion, Q-CTRL, Aquark, Vector Atomic searched). All 2026 "quantum navigation drone" news is magnetic-anomaly navigation, not quantum inertial.

Searches on topic B: 14. Last 6 produced only minor items (muon poster, BIT framework, acoustic). Practically saturated for anything that changes the small-drone plan; open-ended for curiosities.

## C. Polarised-skylight and sun compasses (finish)

### C1. Best new item for the sim: raw compass tails, measured
Sun, Liu, Liu, Zhao, Wang, Cao, Shen (North University of China), "Variational Bayesian Innovation Saturation Kalman Filter for MEMS-INS/Polarization Compass Integrated Navigation", *Micromachines* 16(9):1036, Sep 2025, doi 10.3390/mi16091036 [V full text via Europe PMC].
- Hardware: self-built compass, Sony IMX250MZR polarisation sensor + ZYNQ7020, using only a central 40 x 40 pixel patch. Unmanned ground vehicle, 1200 s dynamic run, clear sky, 24 Jun 2025 16:30, "high-speed movements and multiple turns".
- Heading error (deg), Table 4/5:

| Method | Max | RMS |
|---|---|---|
| MEMS INS alone | 10.66 | 4.78 |
| **Polarisation compass alone** | **153.90** | **5.65** |
| Adaptive KF | 10.64 | 4.76 |
| Huber robust KF | 152.40 | 3.60 |
| MCC KF | 151.40 | 2.56 |
| Innovation-saturation robust AKF | 9.16 | 1.10 |
| Proposed VB innovation-saturation KF | 3.59 | 0.74 |

- Noise modelled as Student-t, degrees of freedom 5; outliers attributed to lens occlusion and fast manoeuvres.
- **Sim implication:** even under a clear sky a moving compass produces gross outliers (to about 150-180 deg, i.e. the 180-deg ambiguity of the e-vector plus occlusion). Model the measurement as Student-t (nu about 5) with a core of 1-2 deg plus a few-percent outlier rate up to 180 deg; a robust filter brings the fused heading to under 1 deg RMS. This upgrades pass 1's Gaussian 0.3-1 deg proposal, which is right only after robust fusion.

### C2. Fusion results table, from a review (upgrades several pass-1 snippets)
From "Biomimetic Polarized Light Navigation Sensor: A Review", *Sensors* 23(13):5848, 2023 [V full text, first third], integrated-navigation table:

| Work | Fusion | Platform | Heading result | Conditions |
|---|---|---|---|---|
| Liu et al. 2021 | polarisation + MIMU | — | RMS 0.14 deg | clear |
| Liu et al. 2021 | polarisation + MIMU | — | RMS 0.42 deg | cloudy |
| Chu et al. 2018 | polarisation + MIMU + GPS | quadrotor | 0.2 deg | — |
| Li et al. 2022 | polarisation + MIMU + GPS | small UAV | ~0.2 deg indoor, < 2 deg outdoor | — |
| Zhao et al. 2022 | compass + GRU error model | UAV flight | RMS 0.52 deg | flight |
| Xie et al. 2021 | polarisation camera + MIMU + magnetometer | vehicle | azimuth RMS 0.9 deg; position 0.78-1.31% of distance | — |
| Fan et al. 2022 | polarisation camera + INS | car | static < 0.5 deg, dynamic < 0.7 deg | cloudy noted |
| Wang et al. 2019 | point sensor, 320-730 nm | — | +/-0.018 deg outdoor | clear |
| Dupeyroux 2019 | UV two-pixel | hexapod | AOP error 0.62 +/- 0.40 deg; works in rain and under shallow water | — |
- Review notes the approach "performs well at high altitude" but is "severely affected" near the ground (snippet; context not read).

### C3. Twilight, moonlight, canopy, overcast
- **Twilight with city glow:** Li, Wang, Zhang, Xu (BIT), "Ultraviolet bionic compass method based on non-ideality correction and statistical guidance in twilight conditions", *Optics Express* 32(13):22132, Jun 2024 [V abstract]: accuracy "severely degraded by the influence of city glow at dusk"; correction brings heading error to about 1 deg. Relevant to Ottawa: model twilight polarisation heading with a city-glow degradation term on the city side of the sky.
- **Moonlit:** Control Engineering Practice 2023 (doi 10.1016/j.conengprac.2022.105408): polarisation + INS + celestial at night, estimates a moon-azimuth bias; field tests "accurate, stable", no phase breakdown [S]. BUAA "Bioinspired polarized light compass in moonlit sky ... probability density estimation" exists [S title only]. Dung beetles orient as accurately by the moon pattern as diurnal species by the sun (PMC3049003) [S]. No moving-UAV moonlit test still.
- **Cloudy:** North University of China skylight compass better than 1 deg on cloudy days (Laser Focus World) [S]; Wang et al., *IEEE Sensors J.* 24(14):21906, 2024: multidirectional polarisation sensors + sun sensor + IMU, UAV flight test in cloudy weather, improved accuracy (no degrees in abstract) [S]. Bai et al., SPIE 13218 (2024): adaptive fusion of polarisation + sun sensor + IMU, UAV flight test [S].
- **Canopy, overcast UV:** nothing new beyond pass 1.

### C4. Hardware and prices
- IMX250MZR polarisation cameras (machine-vision, GigE/USB3): SVS-Vistek exo250ZGE US$2,255; Contrastech Mars5000S-24GMP US$3,650; Lucid Phoenix, Pixelink, IDS, Imaging Source: quote only [S, vendor listings]. A Pi-class board can read such a sensor only through USB3/GigE; the North University compass used a ZYNQ FPGA.
- AntBot rotating-filter UV compass about EUR 500 (paywalled snippet); two-photodiode UV design "considerably" cheaper, 0.3 deg clear / 1.9 deg overcast [S]. No public sub-$100 bill of materials found. SkyPASS still unpriced.
- Stürzl, "A Lightweight Single-Camera Polarization Compass with Covariance Estimation", ICCV 2017, doi 10.1109/ICCV.2017.572: VGA CMOS + three lenses with differently oriented polarisers, about 56 deg field of view; estimates sun direction **and its covariance** per frame; for MAVs [S]. Its per-frame covariance is the right interface for an EKF measurement.

### C5. Sun compass
- No 2024-26 UAV flight result with a heading number for a camera sun compass. Caltech 2.4 deg remains the only camera-alone figure (already in pass 1). Fusion with polarisation and IMU (Wang 2024, Bai 2024) is where the flight work is.

Searches on topic C: 12 (+3 fetches). Last 5 searches: 1 new (twilight city-glow), others repeats. Close to saturated for numbers that change the model.

## D. Magnetometer heading on small electric multirotors (finish)

### D1. The one measured in-flight comparison found: a constant offset dominates
PX4 forum thread "High mag accuracy possible?", Dec 2025 [V, read today; forum, single user]:
- Multirotor, RM3100 magnetometer on an arm 35 cm from other electronics and motors, calibrated away from buildings. Reference: Septentrio mosaic-go H dual antenna, 1 m baseline, reported 0.3 deg heading accuracy (30 satellites), sub-1 deg in flight.
- Magnetometer-only heading within about 5 deg of GNSS heading; over 8 steady-state samples the difference was "close to constant at 3.6 deg". Rotating the sensor by 3.6 deg (MAG0_ROT_YAW) left an average 2 deg; the offset wandered for the first 30-120 s then settled.
- **"~zero thrust to norm of mag field relationship"**: no throttle dependence at 35 cm.
- PX4 maintainer view (same thread): PX4's EKF learns mag biases online but saves them only on disarm; full hard/soft-iron and misalignment estimation is not in the core EKF because hover gives no excitation and motor interference changes. ArduPilot can calibrate in flight but needs aggressive manoeuvres.
- **Sim implication [C]:** with a 30-40 cm mast the error is a per-flight near-constant bias of 2-5 deg (residual calibration, mounting misalignment, local declination error) plus a short settling transient, not a throttle term. This is larger than pass 1's N(0, 0.5-1 deg) bias. Proposed: bias ~ N(0, 2-3 deg) per flight, settling exponential over 30-120 s, current term small at >= 30 cm.

### D2. Throttle and current terms
- Throttle disturbance on a single-motor puller fixed-wing UAV with three RM3100s: 430, 485 and 185 nT at the two wing and one tail positions; mounting position dominates (Preprints.org 202609.1116, Sep 2026; abstract via search, page 403) [S]. [C] At Ottawa's horizontal field (~18,000 nT, TBC) 485 nT perpendicular gives about 1.5 deg.
- Tuck et al. 2021 (*Geosci. Instrum. Methods Data Syst.* 10:101): interference mapped on four electric UAS types including a quadrotor; **DC cables between battery and ESCs, and servos, are the major sources**; detectable change at currents as low as 1 A; scanner error 3.1-7.4 nT; on fixed-wing, >= 50 cm from wingtips/tail for < 2 nT [S].
- Strathclyde OPM (see A8): motor-noise frequency scales linearly with throttle, magnitude does not [V abstract]. For a heading magnetometer sampled at 10-100 Hz the motor tones are aliased noise, the DC current field is the bias.
- ArduPilot CompassMot doc [V, read today]: interference is "linear with current drawn"; compensation works well only with a battery current monitor; throttle-based is "not recommended". Thresholds after CompassMot: < 30% acceptable, 31-60% grey zone, > 60% bad (move compass or fit an external one). No accuracy figure is given. COMPASS_LEARN=3 in-flight offset learning exists but the doc does not recommend it; needs GPS lock.
- Older model-based compensation: ICUAS 2014, nonlinear model from motor control inputs to field change [S]; IEEE TIE 67(10):8829, 2020, gyro-aided EKF estimating current-induced interference (pass 1 has the 2/3 reduction) [S].

### D3. Calibration residuals and in-flight calibration
- Opromolla et al., *Sensors* 20(2):538, 2020 (cooperative flight data, offline): motor-driven disturbance causes heading error "up to 10 deg" referred to apparent north; cooperative calibration from a second UAV [S] (the pass-1 "about 10 deg on MAVs" figure is this paper).
- UAV Navigation (vendor) OLHIC: hard iron estimated in flight by heading changes; soft iron treated as stable and calibrated once [S].
- Journal of Aircraft 2007 autocalibration: with soft iron and non-orthogonality one error mode is unobservable [S]. Supports pass 1's "bias not observable without a second heading source".
- arXiv 2302.00113 (low-cost quadrotor magnetic mapping): moving the magnetometer further from flight electronics cut flight-to-flight variation; a further unexplained flight-by-flight anomaly remained [S].

### D4. Not found
- A peer-reviewed multirotor study of magnetometer heading against a dual-antenna reference in flight (only the forum case above).
- A published nT-versus-distance decay curve for a quadcopter with a GPS mast.
- Ottawa D/H/Z/F values from a primary source (OTT page lists none; H about 18,000 nT stays TBC).

Searches on topic D: 7 (+3 fetches). Last 4 searches: 1 new item (Tuck cable finding), rest repeats. Practically saturated in the open literature; the gap is a genuine absence of peer-reviewed in-flight measurements.

## E. Camera bearings to landmarks and lights; registries; single-emitter fixes

### E1. Canadian obstruction lighting: what a camera would see (Transport Canada Standard 621, last amended 2021-11-02) [V, read today, first 100k chars]
| Light | Intensity | Colour | Flash rate (per min) |
|---|---|---|---|
| CL-810 | low | red | fixed |
| CL-810F | low | red | 20-40 |
| CL-864 | medium (nominal 2000 cd, per TC circular) | red | 20-40 |
| CL-865 | medium | white | 40 (night reduced to 2000 cd) |
| CL-866 / CL-885 (catenary) | medium | white / red | 60 |
| CL-856 | high (20,000 cd class) | white | 40 |
| CL-857 (catenary) | high | white | 60 |
- Height rules: <= 45 m AGL a top CL-810; above 45 m at least one CL-864 red flashing beacon on top; above 105 m intermediate levels; above 107 m at least three CL-864 per level; above 150 m day marking always required. Wind turbines > 150 m add mid-height CL-810 flashing in sync with the nacelle CL-864 [S, TC circular].
- Reporting: Aeronautical Assessment Form to Transport Canada >= 90 days before construction; Land Use Proposal to NAV CANADA; NOTAM at start of construction; **light failures reported immediately for a NOTAM** (s. 2.7). So outages of a given light are, in principle, knowable from NOTAMs.
- No public Canadian obstacle registry found (repeat of pass 1; the NAV CANADA eTOD/"Obstacle Data" product remains unverified at about $24k/yr). **ISED Spectrum Licence Site Data** (monthly refresh, public download) includes "structure height" (total height AGL of the supporting structure) and site structure type, plus antenna height AGL [S, ISED field descriptions and an ArcGIS mirror]. [C] Combined with Standard 621's 45 m rule, every ISED structure taller than 45 m should carry a red CL-864 flashing at 20-40/min: a usable night landmark list, pending a check that lighting matches the rule in practice.
- **Sim model for a lit-tower bearing [C, TBC]:** detection when the light is within the camera's range (a 2000 cd red light is visible to the eye at several km in clear air [M]); the 20-40/min flash means a detection only every 1.5-3 s unless frames are integrated; flash rate and colour help identify the class but not the individual tower, so association must use predicted bearing from the dead-reckoned position; LED lights outside camera band are not an issue for a visible-band camera.

### E2. Night and day-night image fixes (new numbers)
- Xing et al., "Long-Duration UAV Localization Across Day and Night by Fusing Dual-Vision Geo-Registration with Inertial Measurements", *Drones* 9(5):373, 2025: visible and thermal onboard images matched to a daytime visible map, fused with inertial; altitudes 700-2400 m, over 344.6 km; **RMSE < 50 m** [S, abstract via search]. Fixed-wing altitudes, not a small quad.
- PiLoT (arXiv 2603.20778, 2026): day-map/night-flight matching; median 0.46 m but on synthetic data [S].
- Tonini et al., *Applied Sciences*, Oct 2024: absolute aircraft position from two known ground points using focal length, detector size and pitch/roll; authors could not quantify the error precisely, "comparable to GNSS" [S]. The nearest thing to in-flight resection from point landmarks; no number.
- ESEN GORDES 2022 flight test (vision against map): mean horizontal error about 5 m at 1,000 ft AGL, 19 m at 10,000 ft, 23 m at 15,000 ft [S]. Mountain-terrain preprint 2025: RMSE 6.56 m (lat) / 8.02 m (lon) over 695 m at 150 m altitude [S].
- Penn State 2005 (IEEE Aerospace): inertial + bearings to fixed ground features, simulation and lab hardware only; EKF can diverge with inertial plus bearings only [S].
- Still nothing published on drones fixing position from obstruction lights, tower beacons or city lights (one more search, patents only). Night-Voyager / Night-Rider (streetlights) remain ground-robot only.

### E3. Single-emitter running fixes and bearings-only observability
- Nardone & Aidala, "Observability Criteria for Bearings-Only Target Motion Analysis", *IEEE TAES* AES-17(2):162-166, 1981 (NUSC TM 80-2059, DTIC ADA102073) [S abstract]: closed-form necessary and sufficient conditions on own-ship motion; **some manoeuvres stay unobservable even with nonzero bearing rate**. Hammel & Aidala 1985 extend to 3-D; Fogel & Gavish 1988 to Nth-order target dynamics [S]. Range-only analogue: unobservable for constant-bearing relative motion or constant own velocity/acceleration (Song) [S].
- For our case (stationary emitter at a known position, own velocity known from dead reckoning) the problem is a running fix, observable whenever own displacement has a component across the line of sight [C]. With unknown own velocity (no DR), it reverts to the TMA case and needs a manoeuvre (course change) [C from the TMA results].
- Underwater single-beacon navigation is the closest mature literature: observability degrades with range and with the angle between relative velocity and relative position (Batista, Silvestre, Oliveira; Parlangeli & Indiveri IFAC 2014) [S].
- Error model, adds to pass 1 [C]: along-line-of-sight error sigma_R about R^2 sigma_theta / (L sin phi), where L is the baseline flown between bearings and phi the angle between the baseline and the line of sight; cross-range sigma about R sigma_theta. Heading bias b adds a cross-range bias R b to every bearing and a range bias that does not average out. Example: R = 5 km, sigma_theta = 0.2 deg (camera), L = 500 m perpendicular: sigma_R about 175 m, cross-range 17 m.

Searches on topic E: 10 (+1 fetch). Last 4: 1 new (TC 621 table via fetch), 3 empty. Practically saturated; the open literature on point-light fixes for drones is empty.

## F. Ottawa-specific availability

### F1. Ottawa VOR: the VOR is gone, the DME remains (upgrades pass 1's TBC)
- NAV CANADA NAVAIDs Modernization Program page [V, read today]: Phase 11 (Montreal FIR, CZUL), **"Ottawa* (OW)" VOR, revocation date 25 January 2024**, and "Ottawa* (YOW)" NDB, same date (phase date 30 Nov 2023). Footnote: "*Revocation Date: January 25, 2024". The page lists no VOR-to-DME conversions and mentions no DME.
  - Note the identifiers: every other VOR in the table carries a three-letter ident (YCF, YQO, YSB...), and Ottawa's VOR/DME ident was YOW; two-letter idents are typical of NDBs. The table has probably swapped the Ottawa idents; either way **an Ottawa VOR was revoked on 2024-01-25** and no other Ottawa VOR appears in the remaining lists [C, inference].
- Canada Flight Supplement extracts reproduced in RPAS site surveys (MAAC) list **"NAV DME YOW 114.6 Ch 93 N45 26 30 W75 53 49"**, elevation 482 ft, in editions effective Apr-Jun 2025, 19 Mar-14 May 2026 and 9 Jul-3 Sep 2026 [S, search snippets of several PDFs; the PDFs themselves were not readable]. In CFS format a VOR/DME would be listed as "VOR/DME".
- One undated third-party airport page still lists a "VOR Rwy 14 (GNSS)" approach at CYOW [S]; NAV CANADA's 2025 Type A chart list and AIC 019/2025 mention no VOR procedure [S].
- **Conclusion:** the YOW VOR was decommissioned on 2024-01-25; the 114.6 MHz channel survives as a DME only. The `uc02-yow-approach-vor` scenarios rest on a removed station. A VOR scenario near Ottawa needs another station (TBC which VORs within range are retained; NAV CANADA publishes no retained list). Passive DME on YOW 114.6/Ch 93 remains possible in principle (pass 1: no passive DME experiment found). Confirm with the current CFS edition before any claim to judges.

### F2. Cloud by season and day/night (observation-based)
- **Toronto proxy from observing logs** (David Dunlap Observatory, Richmond Hill; logs Jul 1999-Jun 2005; cloud from Toronto Pearson 1990-1999, ECCC) [V]: overall usable efficiency 25-35% of the about 3,459 h a year between nautical twilights; summer nights better than 50% clear (July, August best); December and January cloudiest; a 1972 estimate gives about 580 photometric hours a year. [C] Ottawa's heavy-overcast normals (pass 1: 62-66% Dec-Jan, 42-46% Jul-Sep) are close to Toronto's, so use 25-35% of night hours usable for a star tracker over the year, above 50% of summer night hours, and about 20-30% in Dec-Jan (TBC).
- Quebec station-based cloud climatology (paper "How skilful are cloud cover products in representing observed cloudiness in Quebec?"): annual mean cloud fraction 0.5-0.7, autumn cloudiest at most stations; reanalysis products miss the observed seasonal pattern [S]. Supports using station normals over modelled products (WeatherSpark/NASA POWER).
- Diurnal pattern: over land the diurnal cloud cycle has about twice the ocean amplitude; warm-season low cloud peaks in early afternoon (ISCCP) [S]. [C] So in summer, nights and early mornings are clearer than afternoons; in winter the day/night difference is small. No Ottawa-specific day/night split was found; the ECCC hourly archive would give it (download, owner go-ahead).
- Cleardarksky "Ottawa" climatology is forecast-based (2006 onward), not observed [S].

### F3. Skyglow
- No Ottawa SQM or zenith-brightness measurement found (two more searches). Qualitative: from Rideau Lake, south-west of Ottawa, "the glow from Ottawa extends half way up the sky in the northeast" (RASC light-pollution guide) [S]. A Carleton GEOM2007C student report (2016) maps naked-eye star visibility over Ottawa-Gatineau in relative terms (PDF unreadable to the fetch tool) [S]. Berry's RASC Ontario sky-brightness survey (1974 onward) relates glow to city population and distance; no Ottawa number retrieved [S]. Reference: Bortle 4 is 20.4-21.3 mag/arcsec^2, Bortle 3 21.3-21.5 [S].
- [C, TBC] For the sim: treat the urban core as Bortle 7-8 and the suburbs 5-6 (typical for a 1M-population city [M]), and use pass 1's TU Delft identification-recall figures.

### F4. Magnetic relief
- OGS abstract on the Eastern Ontario survey ("The Precambrian basement of Eastern Ontario: insights from a new aeromagnetic survey", AAPG Eastern Section 2014) [V abstract]: Paleozoic cover is "magnetically transparent"; **east of the Gloucester fault, thicker cover gives "a considerably subdued magnetic grain"**; west-to-northwest faults near Ottawa strike at high angle to basement shear zones; in the Frontenac-Adirondack belt, lows are marbles/quartzites and ovoid highs are plutons. [C] The Gloucester fault runs through Ottawa's east end [M], so the eastern half of the city and the lowland toward Cornwall are the low-gradient, low-observability case (Hager et al. ECC 2026 warn of divergence there); the Gatineau Hills / Shield to the north-west are high-gradient.
- No nT amplitude range for the Ottawa area was found on the public grid (needs the grid itself, a download).
- Survey coverage: see A2 (urban Ottawa excluded from the 400 m survey, TBC).

Searches on topic F: 11 (+6 fetches). Last 6: 2 new (Gloucester-fault grain, DDO logs). VOR now resolved to the level the open web allows; skyglow and day/night cloud need downloads, not searches.

## G. Late items from the citation and thesis sweep
- **A:** "Real-time Uncertainty-Aware Motion Planning for Magnetic-based Navigation", arXiv 2407.19046 (2024): planner uses entropy maps built from the anomaly map to steer toward high-information areas [S]. Kok & Solin, "Scalable Magnetic Field SLAM in 3D Using Gaussian Process Maps" (arXiv 1804.01926): reduced-rank GP map in a Rao-Blackwellised particle filter (indoor) [S]. *Sensors* 23(8):3897, 2023: GP local magnetic map from a UAV, identifies two classes of UAV-electronics noise [S]. SandboxAQ AQNav campaign covered about 44,000 km [S].
- **B (timing, fixed sites):** Saab UK + Aquark Technologies + Royal Navy DCTO, Aug 2026: two Giraffe 1X radars produced one air picture timed only by Aquark cold-atom clocks; deliberate timing errors were injected to mimic GNSS spoofing/denial; qualitative results only [S, Saab release 12 Aug 2026, Royal Navy news]. Q-CTRL Coral Sea gravimetric trial: within 1 NM for the whole mission [S].
- **C (thesis):** Ginn, MPhil, University of Newcastle (Australia), 2016 (repository posting 2025): bee-style polarisation camera on a fixed-wing model aircraft; **heading SD about 30 deg relative to truth** despite pitch/roll handling [S]. A cautionary flight number for an uncompensated imaging compass on a manoeuvring airframe; contrast with fused 0.5-0.7 deg results.
- **D (thesis, Carleton):** Tuck, PhD Earth Sciences, Carleton University, 2019, "Characterization and compensation of magnetic interference resulting from unmanned aircraft systems" [V abstract]: mapped four electric UAS (single-motor fixed-wing, single-rotor helicopter, quadrotor, hexarotor); interference depends on motor current and mixes magnetised material with current effects; real-time compensation on a 35 kg petrol UAS: improvement ratios 8.595 (stationary calibration) and 3.989 (box), compensated TMI SD 0.075 / 0.083 nT, Figure of Merit 3.8 nT ("lowest reported for a rotary-wing UAS"). Local expertise at the host university.
- **E (thesis):** TU Delft MSc, Seth, Dec 2025, "UAV Celestial Navigation with Light Pollution Adaptation" (dynamic star-catalogue selection) [S]; likely the source of pass 1's synthetic skyglow figures. Nothing on lights-as-landmarks. Firefly (arXiv 2112.06677): drone localisation from modulated light beacons plus inertial and altitude, no camera (OPTICAL on the infrastructure side, NET: beacons placed by operator) [S].

---

## 1. Coverage table

Searches below count WebSearch calls; WebFetch reads are extra. "8-in-a-row" is the brief's saturation rule.

| Topic | Searches | Fetches | 8-in-a-row met | Practical judgement | New items | New in last ~10 searches | Blocked by |
|---|---|---|---|---|---|---|---|
| A. Magnetic-anomaly navigation | 22 | 12 | no | near saturation for numbers; stream still producing press items | 24 | 5 (OTT observatory, SBQuantum, DO-160, GP/entropy planning, 44,000 km) | preprints.org 403; IPPT PDFs and TU Delft repository unreadable/refused; PLANS 2025 paywall; GSA abstract timeout |
| B. Exotic and bio-inspired | 12 | 2 | no | practically saturated for anything relevant to a small drone | 14 | 3 (muon poster, BIT framework, Aquark timing) | none significant |
| C. Polarisation and sun compass | 11 | 4 | no | practically saturated | 12 | 3 (twilight city glow, Ginn 30 deg, heavy-tail table) | PMC cookie wall (worked via Europe PMC); paperswithcode redirect |
| D. Magnetometer heading | 7 | 5 | no | saturated in open literature (gap is real) | 9 | 2 (Tuck cable finding, Carleton thesis) | preprints.org 403 |
| E. Landmarks, lights, single emitter | 10 | 1 | no | saturated; open literature on point-light fixes is empty | 11 | 2 (TC 621 table, ISED structure height) | none |
| F. Ottawa availability | 9 | 8 | no | VOR resolved; skyglow and night cloud need downloads | 7 | 3 (VOR/DME status, Gloucester-fault grain, DDO logs) | MAAC PDFs unreadable; OGS GDS1075 record 404; ourairports TLS expired |

Total about 71 searches and about 32 fetches. The search tool never reported its budget as used up.

## 3. Corrections to the first-round report and to pass 1 (celestial-conventional.md)

1. **MagNav Challenge data licence (pass 1, topic 11, and appendix item 1).** Not public domain in practice. The record's `DATA_SHARING_AGREEMENT.md` (Air Force Acceptable Use Agreement) limits use to non-profit research, non-profit education or government purposes, forbids redistribution, needs Air Force approval, lasts one year and requires deletion afterwards [V]. MagNav.jl downloads this data automatically [S]. Treat any use as needing owner and probably university sign-off; the open NRCan grids (Open Government Licence - Canada) [V] are the safer map source.
2. **Eastern Ontario 2014 survey "covering Ottawa" (pass 1, topics 11 and 14).** The urbanised Ottawa and Cornwall areas were excluded from that survey [S, TBC from OGS GDS 1075 metadata]; east of the Gloucester fault the magnetic grain is "considerably subdued" [V abstract]. Ottawa's urban core is a poor MagNav area on two counts.
3. **YOW VOR (first round 8.2; pass 1 topic 12 and appendix item 2).** No longer "TBC": NAV CANADA's modernization page revokes an Ottawa VOR on 2024-01-25 [V], and CFS editions from 2025 to Sep 2026 list YOW 114.6 / Ch 93 as **DME** only [S, several extracts]. The first round's reading ("OW" a separate VOR, "YOW VOR/DME on no removal list") is most likely an ident swap in NAV CANADA's table. VOR scenarios at YOW should be retired or moved to another station.
4. **"DTU/ONERA flights in Greenland published no results" (pass 1, topic 11).** Published: Jensen et al., *ESSD* 17:1667, 2025, 1-2 mGal for both the quantum and strapdown gravimeters [S].
5. **Polarisation compass sim model (pass 1, topic 4: Gaussian 0.3-1 deg in flight).** A measured moving-vehicle run under clear sky gave the raw compass **RMS 5.65 deg with a 153.9 deg maximum**; robust fusion gave 0.74 deg RMS, 3.59 deg max [V]. A fixed-wing imaging compass gave about 30 deg SD in flight [S]. Model raw output as heavy-tailed (Student-t, nu about 5, with outliers to 180 deg) and keep 0.3-1 deg only for the robustly fused heading.
6. **Magnetometer bias (pass 1, topic 5: constant bias N(0, 0.5-1 deg)).** The one in-flight comparison against a 1 m dual-antenna reference showed a near-constant 3.6 deg offset (about 5 deg envelope) and no throttle dependence at 35 cm [V forum]. Raise the per-flight bias to N(0, 2-3 deg) with a 30-120 s settling transient; keep the current term small at >= 30 cm.
7. **First round 8.2 "22 m final over 365 km in the best published flight".** Still the best published number with metres, but add the operational-scale results: AQNav < 74 m best 1 h flight and RNP 0.3 for 64% of >150 h [S]; Ironstone Opal DO-160 qualified and "RNP 0.3 in flight" [S]; Honeywell/DIU 4 h 23 min MagNav-only flight, "89% better than backup navigation", no metres [S].

## 4. Searches that found nothing (this pass)
- An outdoor multirotor MagNav position result (three phrasings); a 2025 Chinese UAV geomagnetic-matching flight test with metres; a DRDC MagNav programme.
- Terrain clearance of OGS GDS 1075; the Ottawa magnetic anomaly amplitude range in nT; Ottawa D/H/Z/F from a primary source.
- A quantum IMU flight on a small drone; ambient-seismic or Schumann-resonance navigation; horizontal position from pressure patterns (again).
- A 2025-26 multirotor polarisation-compass flight with RMSE; a sub-$100 open bill of materials; SkyPASS price (again); a moonlit polarisation test on a UAV (again).
- A peer-reviewed in-flight magnetometer heading study against a dual-antenna reference; a nT-versus-distance curve for a quadcopter mast.
- Drone position fixes from obstruction lights, tower beacons or city lights (again); a public Canadian obstacle list (again).
- Ottawa SQM / zenith brightness (again); an observed Ottawa day/night cloud split.

## 5. Judgement: would more searching find anything?
- **A (medium-low).** The numbers that matter for a sim (platform noise by mount, compensation residuals, map-resolution rule, integrity metric, flat-field divergence) are now in hand. New items keep appearing as press releases from Honeywell, SandboxAQ and Q-CTRL, but they do not publish metres. The remaining unknowns (Ottawa map amplitude, survey height, urban exclusion) need the OGS/NRCan metadata or the grid itself, i.e. an owner-approved download, not searches.
- **B (low).** Every 2026 "quantum navigation" story resolved to MagNav, gravimetry at sea or clocks. Nothing changes the small-drone ranking.
- **C (low).** Chinese journals will keep adding 0.3-1 deg fused results; the useful new fact (heavy tails, twilight city glow) is found. The unread 2026 IEEE TIM review remains the single best next read.
- **D (low).** The gap is a real absence of peer-reviewed flight data. A one-hour bench and hover test on the team's own quad with a dual-antenna reference would beat any further search.
- **E (low).** Point-light fixes for drones are unpublished; the TC 621 table and ISED structure heights give enough to build the model. Novel but unvalidated.
- **F (low for searching).** VOR resolved to DME-only; confirm against the current CFS. Night cloud and skyglow need ECCC hourly data or a sky-quality-meter session, both outside web search.
