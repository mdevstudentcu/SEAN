# Heading, celestial, conventional and exotic navigation: saturation pass

Status: IN PROGRESS (raw notes; final structure written at end). Partial work is saved as it goes.

Labels: [V] read today in primary source; [S] snippet/secondary; [M] memory; [C] own arithmetic.

## Raw notes

### T1 star trackers
- Marbel, Ben-Moshe, Yozevitch, "Star-Tracker Algorithm for Smartphones and Commercial Micro-Drones", Sensors 20(4):1106, 2020. [V via EuropePMC full text] Phones (Nexus 5x, Galaxy S6-S9), RPi cam V2.1 (IMX219, 1 s exposure ISO 160), DJI Mavic Pro/Mavic 2/Phantom 4 detect stars in 30 Hz video; typical angular error 0.1-0.3 deg; 1/50 deg projected on calibrated phones, not measured; city light pollution + full moon tested with S7. No drone in-flight accuracy number.
- SOST (Gutierrez et al., IEEE Access 2020): RPi + open-source astrometry; sub-arcminute, 1-3 solutions/min lost-in-space [S]. Handgraaf TU Delft thesis RPi cam 0.025 deg 1-sigma, light pollution noted [S].
- Teague & Chahl Drones 2023 7(1):52: long-exposure star trails, strapdown, attitude error < 0.13 deg yaw, 0.06 deg pitch/roll (3 sigma) [S]. Teague & Chahl Drones 2024 8:652: 4 km, "1 deg attitude error ~ 100 km" (paper text via snippet) [S]; averaging over a full orbit cancels camera bias; no 2025 follow-up found.
- Event cameras: Chin et al. 2018 (arXiv 1812.02895); EBS-EKF Kitware/U Dayton 2025, up to 1000 Hz, Prophesee EVK4-HD next to a space star tracker [S]; e-STURT dataset 2025 (jitter) [S]. All space-oriented; no atmospheric/drone result.
- Urban skyglow: TU Delft thesis (synthetic): 71.5% identification recall at mag 7 (Bortle 3); under heavy pollution fixed catalogue fails, adaptive gets 27.6% at mag 5.0 and 4.5% at mag 4.5 [S]. No field failure-rate vs Bortle found.
- Rate limit: large-FOV star sensor dynamic range ~3-5 deg/s; <1-1.5 deg/s little effect [S, secondary].
- PiFinder (open hobby, RPi + HQ cam, tetra3/cedar-solve): 0.25-1.5 s exposure, ~1 solve/s [S].

### T2 celestial on aircraft
- Sodern Astradia: few arcsec, <3 kg, 176x185x207 mm, 1 Hz, ~EUR 250k, available June 2025 [S multiple press].
- SkyPASS (Polaris Sensor Technologies) night mode: angles-only star fix; position <3 km at start-up without averaging, 100 m with time averaging/better INS, needs time to <1 s [V InsideGNSS 2023-06-14].
- Honeywell celestial (stars + RSOs) on Embraer E170: 25 m CEP50, 38% better than earlier test [S]; HG2800 flight tests planned 2024, outcome not found.
- Xiong, Zhou, Wei, Sensors 2022 22:6992: LOS to LEO satellites + stars, IMU, QLEKF, near-space UAV, CRLB+sim only; FOV ~10x10 deg, ~mag 8 [S].
- Globalstar optical sightings ground test 250 m RMS (MDPI Sensors 25(19):6149) [S] - already in first round.
- Daytime SWIR near ground: Changsha 69 m altitude, 1.48 um, stars brighter than H -0.1 at 10:00 [S]; US patent 7349804: 5 cm aperture sea level -> H mag 1; low-noise camera -> H mag 2 [S]; 20 km airborne prototype >2.7 H mag, >10 stars [S]. Mode switch ~20 km (Ni et al.) [S]. => daytime star tracking near ground needs 5-6 cm aperture InGaAs and only a handful of stars brighter than H~1-2; not for small drones [C judgement].
- Patent claims 30 m (daytime stellar imager, sats+stars) and 5 m/20 m marine (unverified) [S].

### T3 sun sensors
- nanoSSOC-D60/A60 (Solar MEMS): +/-60 deg FOV, <0.5 deg 3-sigma accuracy, <0.1 deg precision, 3.7-6.5 g, EUR 2,500 (A60) / 4,110 (D60) reseller [S]. Space part; in atmosphere diffuse sky light and albedo bias (not quantified) [M].
- Furgale, Enright, Barfoot TAES 2011 sun sensor rover: absolute heading within a few degrees, error falls with integration time [S]; Lambert et al. JFR 2012 VO + sun sensor + inclinometer 10 km Devon Island [S].
- Sun-BCNN (Peretroukhin 2016/2018): sun direction from RGB median ~12 deg KITTI, <8 deg Devon; cut VO drift up to 42%/32% [S].
- Tilt compensation for polarization/sun heading on UAV: Applied Sciences 2025 15(9):5060, horizon detection, horizontal attitude error <0.3 deg, heading improved 77.4% [S].

### T4 polarization
- SkyPASS Gen3N [V InsideGNSS 2023]: 0.1 deg RMS clear to partly cloudy, static; sun altitude window -4 to 35 deg; twilight ~30 min beyond sunrise/sunset; zenith cloud -> no heading; fog severely degraded; tilt limit 13 deg (full-image algorithms beyond 15 deg); 4.1x3.9x3.2 in, 20 oz, <5 W, 1 Hz; price not stated.
- Moonlit polarization: Chinese J Aeronautics 2022 (10.1016/j.cja.2021.03.005): heading SD 0.32 deg clear night, 0.47 deg cloudy night [S]. Quarter moon pol. signal 1/3 of full, crescent 1/5 (beetle study) [S].
- Gkanias et al. Communications Engineering 2023 (insect-eye UV photodiode compass): 5.89 deg global / 2.77 deg local RMSE clear sky sun >10 deg; 8 UV photodiode analysers + RPi; thin/broken cloud little effect, thick cloud degrades [V].
- Dupeyroux et al. IROS 2017 UV pol compass hexapod: 0.3 deg clear, 1.9 deg overcast [S].
- Iterative segmentation (BUAA): cloudy/overcast mean error 11.7 -> 1.4 deg [S].
- Foliage: pol compass 1.58 deg RMSE dynamic vehicle with 0.028% sky visible [S]; Optics Express 2022 robust CKF 0.36 deg RMSE vs 1.19 deg [S].
- Quadrotor: Sensors 2018 18(1):158 polarization + accel EKF, yaw RMSE 1.25 deg vs APM 3.01 deg, near HV lines [S]. Zhao et al IEEE Sensors 2024 drone dusty days 0.51 deg RMSE [S]. Acta Electronica Sinica 2020 quadrotor pol+MIMU+GPS 50.4% better position under magnetic interference [S].
- IMAV 2024 TU Delft DNN: 4.30 deg median mostly cloudy, open dataset [S, first round checked].
- 2026 IEEE TIM review of solar polarization navigation (BUAA/Renmin) - accuracy table not read [S].

### T5 magnetometer
- Motor-current bias ~ throttle^2 (DIY), yaw up to 10 deg uncompensated [S forum/blog]. ArduPilot: interference linear with current; CompassMOT only good with current monitor; forum compassmot 1-58%, ~100% "bad" [S].
- ArduPilot forum (long-range quad, Li-ion): 50 mm from power wires off-scale; 120 mm boom -> 32% at 75% throttle [V forum].
- Sensors 2021 21(11):3582 (two quads, carrier-phase drone-to-drone + vision calibration): calibrated heading <1 deg; DJI onboard magnetic/multi-sensor heading "several degrees" [S].
- Measurement+Control 2020 (DOAJ 33a3bc83...) LM calibration multirotor: static yaw error 1.2 -> 0.4 deg [S].
- IEEE TIE 2019 (10.1109/TIE.2019.2950841): gyro-aided EKF calibration, yaw error cut ~2/3 in flight [S].
- Interference vs distance: 5 kg hexarotor 350 nT peak at 0.4 m; fixed-wing sources 30-100 nT at 0.38-0.55 m; 21.4-574.2 nT mapped (Tuck 2018) [S]. [C] Ottawa horizontal field ~18,500 nT (TBC from WMM) -> 350 nT perpendicular = 1.1 deg, 574 nT = 1.8 deg.
- Drones 2025 (doaj af26cc39...; mdpi 2504-446X/9/4/255) micro coaxial drone GNSS+IMU+mag heading ~1.01 deg after takeoff, alignment 43% faster [S].
- PX4 EKF-GSF: yaw from GNSS velocity alone; needs horizontal velocity change > velocity uncertainty; no degree figure [S]. Septentrio: COG unusable on multirotors; single-antenna alignment with any dynamic motion [S].
- AMO-HEAD arXiv 2510.10979 (Oct 2025): adaptive MARG EKF, indoor flights, no number in abstract [V abstract].

### T6 other heading
- Dual-antenna GNSS: Wuerzburg (Strohmeier) 50x50 cm array UAV flight mean heading error <1 deg; 48 cm static ~0.25 deg/m-class; 92 cm geodetic 0.2 deg [S]. u-blox 0.1-1.0 deg depending on baseline; ArduSimple 0.14 deg at 1 m, 0.03 deg at 5 m (vendor) [S]. 27 cm LC29HEA forum: never fixed [S]. Needs real GNSS -> calibration only.
- MEMS north finding (static): carouseling 0.229 deg in 6 min; maytagging 0.5 deg in 3 min; virtual maytagging 0.204 deg 5 min at 28.2 deg lat (Microsystems & Nanoeng 2023) [S]; rotation modulation static 0.66 deg, dynamic repeatability 1 deg (Sensors 2017) [S]. All static, need high-end MEMS. [C] At Ottawa (45.4 N) horizontal Earth rate = 15.04*cos45.4 = 10.6 deg/h; heading error ~ bias/10.6 rad, so MPU6050 (16 deg/h) cannot gyrocompass at all; BMI088 (2 deg/h) -> ~11 deg; need <0.02 deg/h for 0.1 deg.
- Heading from imagery: Bearing-UAV arXiv 2603.22153 regresses position+heading from satellite tiles, 90k pairs; no number retrieved [S].
- Radio DOA heading: narrowband DF gives 2 DOF (Lafayette/Wallace TAES 2019) [S]; LF radio polarization heading (Cambridge, J Nav?) not read [S].

### T7 landmarks/lights
- AFIT terrestrial illumination matching (Shockley & Bettinger, IEEE MetroAeroSpace 2021; AIAA 2020; patent US 11,873,123, Jan 2024): city lights as star field using VIIRS Black Marble (500 m); aircraft example images every 15 min; no accuracy number retrieved [S]. Spacecraft-oriented.
- Night-Rider (arXiv 2402.00330) and Night-Voyager (arXiv 2502.20054): ground robot localisation in streetlight / object maps with InEKF [S]. No UAV point-pattern light matching found.
- Lights Out (arXiv 2604.26201): already in first round.
- Karpenko et al. Sensors 2015 15(12):29768: UAV control from 3D landmark bearings, pseudo-measurement KF, simulation [S].
- ISPRS Archives XLIX-B1-2026-55 (Wang et al.): UAV-to-orthophoto+DSM matching then spatial resection, metre-level [S].
- Obstacle registries: FAA Digital Obstacle File: 56-day cycle, accuracy codes from +/-20 ft to +/-1 NM, lighting L/N/U, DOF coverage of Canada limited; MDPI Sensors 2024 24(5):1686 Delaware mean horizontal uncertainty 206 ft -> 56 ft after correlation [S]. Canada: no public registry found; TC Aeronautical Assessment Form; NAV CANADA obstacle data paid (~$24k/yr per a TC internal wiki, unverified), TC obstacle data free bi-monthly (unverified) [S]. ISED antenna site data (already used for towers) is the practical landmark list [M].

### T8 RDF
- Pseudo-Doppler multipath sim (patent, 5.8 GHz): max error 8 deg clean, 9/26/24 deg with one half-amplitude echo depending on phase [S].
- Perera et al arXiv 2003.00386: multirotor gyrating with directional antenna, pseudo-bearings from RSS, 5 m tag localisation outdoors [S].
- JHU APL Tech Digest 32-03 Bamberger: pseudo-Doppler on small UAS, flight demo, no bearing error number [S].
- UCC (Cork) UAV SDR + 4-dipole array: handset located to 100 m from >1.5 km in minutes [S].
- KrakenSDR docs: bearings "several degrees", multipath [S].
- Bearings-only own-ship observability: unobservable until own-ship manoeuvres (NUSC memo ADA102073) [S]; bearing+frequency (Doppler) single platform avoids manoeuvre (patent US5406291) [S].
- ADF/NDB: accuracy "variable", night/twilight sky-wave, coastal refraction [S, training pages]. ICAO figure not retrieved; +/-5 deg [M].
- UAV airframe distorts DF pattern; quadrotor pattern measured 3.6 dB RMS (arXiv 2604.02827) [S].

### T9 passive radar turned around
- No paper found using passive radar for receiver self-location. Adjacent: Channel-SLAM (DLR, Gentner et al. IEEE TWC 2016): multipath components as virtual transmitters, positioning with one physical transmitter; pedestrian and outdoor tests, numbers not retrieved [S]. Airborne DVB-T passive radar clutter studies (Fraunhofer, ONERA motorglider 2019) [S] - platform motion spreads clutter Doppler, an unused ego-velocity cue [C idea].

### T10 TRN
- Plextek, ENC 2024 (Engineering Proceedings 88(1):11, sciforum 19347): TRN on a class-1 drone with a 60 GHz automotive radar, radar ground profile vs UK DEFRA lidar DTM (1 m horiz, 15 cm vert) in a particle filter; "accurate"; metres not retrieved [S]. TX (radar).
- Linkoping 2009 Yamaha RMax: radar altimeter profile + geo-referenced imagery; low speed -> little altitude variation (flat-terrain weakness) [S].
- SITAN diverges if initial uncertainty > several hundred metres; parallel SITAN for larger; acquisition example 2100 m CEP with 57 filters 525 m apart [S].
- arXiv 2510.01348 (SPRIN-D winner) matches heightmap gradients, not absolute baro heights, because baro is noisy [S, already first round]. Baro-only DEM matching: no drone accuracy found; baro gives altitude above datum, not terrain clearance, so cannot sense terrain without a ranging sensor [C reasoning].

### T11 gravity / magnetic
- MagNav best: Muradoglu et al. (Q-CTRL) arXiv 2504.08167 (Apr 2025) [V abstract]: airborne up to 19,000 ft on fixed-wing drones and an airliner avionics bay, onboard and outboard quantum magnetometers, best 22 m final = 0.006% of distance; >=11x better than INS in airborne trials; ground vehicle 7x; online learning without calibration manoeuvres.
- O'Leary et al. arXiv 2610.38047 (27 Oct 2026) [V abstract]: forward-backward map matching on factor graph, synthetic INS+scalar mag over the Renfrew_395 map: median 32.7 m vs 362 m inertial drift; 43% better than EKF and PF; entropy flags 94% of segments >3 cells at 10% false alarm. Map is the MagNav challenge Renfrew map (Ottawa area).
- MagNav Challenge data (Gnadt et al. arXiv 2007.12158; Zenodo 10.5281/zenodo.12723700) [V Zenodo page; S for flight details]: flown by Sander Geophysics with a Cessna 208B near Ottawa, regions Renfrew, Eastern Ontario, Figure-of-Merit (north of Arnprior); 400-800 m altitude; 5 Cs scalar + 4 fluxgates; 2020 flights 1002-1007, 2021 flights 2001-2017; 1.2 GB HDF5; licence "public domain (17 USC 105)" plus a DATA_SHARING_AGREEMENT.md not read. Owner go-ahead needed before download.
- Srinivasan & Nielsen arXiv 2510.15113: temporal (space-weather) disturbance from distant reference station, <10 nT RMS typical, median <5 nT [V abstract]. Matters because diurnal variation (tens of nT) is the same size as anomalies.
- Anomaly signal 10-100 nT over km; platform interference 100-1000x (arXiv 2007.12158 per snippet) [S].
- UAV aeromagnetics Ontario (Walter et al. 2020): 25 m line spacing UAV surveys reach industry-standard TMI [S]; suspended sensor swing noise <1-5 nT [S]; 9 m suspension needed on hybrid multirotor [S].
- Gravity: marine 1-3 nmi with 1'x1' map and 1-2 mGal gravimeter [S]; Q-CTRL vessel trial bounded 1 nmi over 83 km, >10x better than nav-grade INS (press) [S]; strapdown quantum gravimeter arXiv 2608.25563 0.67 mGal residual RMS over 83 km [S]. GIRAFE cold-atom airborne gravimetry ATR-42 2019 [S]; DTU/ONERA Greenland flights 2023 no results found [S]. No aircraft navigation accuracy found. Not for small drones.

### T12 legacy aids
- VOR via SDR [V Marzioli et al. 2021 preprint, STRATONAV, BEXUS 22 balloon 2016]: SDRplay RSP1 + COTS receiver, V antenna; above 18 km, SDR mean error 0.76-1.84 deg, SD 0.57-1.21 deg for stations 119-353 km; COTS 0.26-2.16 deg mean with SD up to 9 deg; distant/low-elevation stations 10-94 deg errors; systematic error from receiver oscillator temperature: 5 deg radial shift for ~50 C heating (COTS); VOR standard +/-1.4 deg modern, +/-4 deg original.
- Hobby RTL-SDR VOR decoder +/-3 deg at three sites; another showed a persistent ~-30 deg offset [S].
- D-VOR improved azimuth method (Adv. Radio Sci. 2021) [S].
- YOW 114.6 MHz Ch 93 listed in Feb 2023 directory; CFS extract valid 2 Oct - 27 Nov 2025 lists YOW DME 114.6 (labelled DME, not VOR/DME) [S]. => YOW VOR status still TBC; possibility the VOR was removed and DME kept.
- Passive DME: heartbeat carrier-phase (Cornell, ION GNSS 2014) - simulation (first round); Stanford (Lo) DME pseudolite message design ENC 2020 needs synchronised transponders, modification-free; FAA APNT white paper [S]. No experiment found.
- eLoran: UK Anthorn timing only; six-site UK network, FOC by 2030; UK MOD "Urgent Compass" May 2026 two-year programme [S]; South Korea IOC 2023 [S]; US "3 sites in western US" forum claim unverified [S]; Germany mobile transmitter test [S]; Canada nothing. NautelNav (Nova Scotia) deployable eLoran concept [S].
- VLF Navy stations NLK, NML drift 0.072-0.079 deg/s phase and power changes up to 7% (AVID, IEEE 2025) [S] -> not phase-stable; would need a reference receiver (NET) [C].
- WWVB phase modulation: ~0.3 us second-to-second jumps; carrier time shifts several us over days [S].
- Lightning sferics: Kovar, Pucicer, Mikes J Nav 2024: TOA positioning with WWLLN historical data, 10 s windows, availability >80%, median GDOP ~1 except south polar [S abstract]; strike location accuracy 1-4 km (3-sensor) to ~9 km [S]. Needs network-located strikes in real time (NET).

### T13 exotic
- Muons: MuWNS-V vector muometric wireless navigation, Sci Rep 2024: 3.9 cm RMS prototype [S]; muPS vector, Sci Rep 2023 (s41598-023-41910-y) [S]; earlier MuWNS 2-25 m, range up to 100 m underground [S]. Needs reference trackers within ~100 m (NET/infrastructure); rate-limited. Not for drones.
- CRoNS (Chilingarian et al. arXiv 2406.18608, Jun 2024): EAS muon showers + network of sensors + central AI; no accuracy [V abstract]. NET.
- Bee-Nav, TU Delft MAVLab, Nature 653:1039-1046 (13 May 2026): path integration + 42 kB visual homing network after a learning flight; within 0.5 m of home in 100% of 30-110 m flights, 70% of 200-600 m flights in wind; wind tilt hurts images [S, press + MAVLab page]. Return-home only.
- Edinburgh aerial biorobot: path integration homing drift 1.5 m per 100 m flown outdoors [S].
- Cold-atom: QinetiQ RJ100 flight May 2024 with Infleqtion Tiqker optical clock + quantum inertial sensor elements, no drift numbers [S]; aircraft atom accel one-shot 2.3e-4 g [S]; Strathclyde 2025 single-axis Rb demonstrator [S].
- Kongsberg/Silicon Sensing SGH03 north-seeking MEMS (Mar 2026), tactical grade, no magnetometer; no numbers published [S].
- HRG: no small-drone HRG product data found [S].
- CSAC (Microchip SA65): aging <9e-10/month, temp sensitivity +/-3e-10 over -40..+80 C [S datasheet]. [C] 1e-10 = 8.64 us/day; holdover error dominated by residual frequency offset: 1e-11 -> 0.9 us/day, 3e-10 -> 26 us/day.
- NV-diamond magnetometers: Zhejiang integrated nT-level UAV unit (arXiv 2508.03237) 13x26 cm; hand-held 400 pT/rtHz (arXiv 2509.19179); Element Six van 0.5 nT/rtHz (arXiv 2401.16090); SBQuantum fixed-wing drone campaign (SPIE 13202, 2024) [S].
- Wearable FID optically pumped magnetometer, walking >500 m in 360 s, 2.24 m radial error with dead reckoning (Scholes et al. arXiv 2606.24612, Jun 2026) [V abstract].
- Acoustic: all ground-microphone-array methods (NET) [S]; no ambient-sound or infrasound self-localisation found.
- Pressure-pattern navigation: nothing modern; barometric weather-model altitude for GNSS integrity (Simonetti & Crespillo, NAVIGATION 2024) [S].

### T14 Ottawa
- Observed heavy-overcast (80-100% cover) hours, ECCC Canadian Climate Normals 1981-2010 via currentresults.com [V page; S underlying]: annual 4,708 h (= 53.7% of hours [C]); January 458 h (61.6%); July 314 h (42.2%); September 328 h (45.6%); December 488 h (65.6%). Days with no sun: 65/yr; Dec 13, Jan 8, Jul 0, Sep 2.
- Modelled (NASA POWER) monthly cloud 58-73%, cloudiest Nov-Dec [S]; WeatherSpark January overcast/mostly cloudy 69% [S]; clearer season ~24 May to 26 Oct [S].
- Skyglow: no Ottawa SQM measurement found; SQM underestimates LED skyglow [S].
- Magnetic: Eastern Ontario aeromagnetic survey 2014 at 400 m line spacing, 12,515 km2 east of 76.51 W to Quebec border (covers Ottawa) [S]; earlier 800 m [S]; national 200 m grid (2005) [S]; OGS Renfrew 2014 airborne magnetic maps 1:50k [S]; MagNav challenge data flown over Renfrew/Eastern Ontario at 400-800 m [S].
- Terrain: HRDEM 1 m lidar DTM/DSM covers 244 of 250 largest Canadian cities (Ottawa coverage not explicitly confirmed) [S].

### Saturation probes (round 2)
- T1: Izadmehr & Ghom arXiv 1808.00221: static portable star tracker, target <6 arcsec (200 m), 50 nights, 80-100 stars/image [V abstract]; 1806.00607 lat/long ~0.5-0.8 arcmin, north 1 arcmin [S]. Jannin & Felicetti (Cranfield) 2024: ground/airborne star tracking atmospheric extinction calibration [S, 403]. ArduPilot forum "digital sextant" thread: no results [V]. No multirotor star tracker flight found.
- T3: spacecraft albedo error up to 20 deg in coarse analog sun sensors, 5-10 deg diffuse (NASA) [S]; Stuerzl & Carey 2012: four fisheye cameras with polarisers on a quadcopter, sun position incl. elevation with clouds, preliminary [S]; visual sun compass 2012 [S]; FIDO rover sun sensor 3-4x heading improvement [S].
- T4: Fan et al. Opt. Eng. 2018 multicamera polarization: 0.28 deg static, 0.81 deg dynamic vehicle RMS with obstacle removal [S]; urban sky inpainting improved 90.2% of 174 cases (Li et al. Opt Express 2021) [S]; outdoor point-source sensors +/-0.2 to +/-0.42 deg after calibration (review) [S]. No vendor price found except SkyPASS (not priced).
- T5: raw indoor magnetometer heading errors tens of degrees at disturbance peaks (AMO-HEAD) [S]; MAV magnetic interference up to ~10 deg (Sensors 2020 20(2):538) [S]; six Pixhawk mags 25-116 mG peak-to-peak in Helmholtz cage (WEVJ 13(5):85) [S]; steel/bridge: anecdotes only.
