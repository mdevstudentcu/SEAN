# Onboard sensing for velocity, position and dead reckoning: second research pass

- **Date:** 2026-11-11
- **Scope:** onboard sensing for velocity, position and dead reckoning on small drones first, then larger aircraft. Heading references and radio belong to other researchers and appear here only where they affect dead reckoning.
- **Method:** web only. 121 WebSearch calls (no budget error) and about 75 fetches. Where a fetch returned a PDF, its saved copy was converted locally with `pdftotext` and read. Nothing in the repository was touched.
- **Labels:**
  - [V]: read today in the cited primary source, the abstract at minimum and the quoted passage where stated.
  - [S]: from a search snippet or secondary page only.
  - [M]: my memory, unverified.
  - [C]: my arithmetic.
- **Flags:**
  - TX: the vehicle must transmit radio.
  - OPTICAL: the vehicle emits light.
  - NET: needs a network, operator cooperation or a data link.
- **Untrusted content noticed:** one search result (the ARK Electronics docs page for ARK Flow) carried embedded instructions telling an agent to make an HTTP request. The search tool reported and ignored them. Nothing was followed.

---

## 1. Coverage

"Saturated" uses the brief's strict rule: 8 searches in a row with nothing new. No topic met it. "Near" means the last searches on the topic returned only minor or duplicate items. Section 5 gives my judgement for each topic.

| # | Topic | Searches | Saturated | Items logged | New items in last ~10 on topic | What blocked |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Optical flow | 18 | Near. The key gap, an independent outdoor study of accuracy against height, did not appear in 18 searches. | 12 | 3, all minor: chip lux floors, Chao 2013 pixel error, ARK Flow MR specs | ISIF and JNTETI PDFs came back as binary; text extracted locally |
| 2 | VIO and VO at drone altitude | 17 | Near | 20 | 3: altitude and parallax note, low-light exposure figures, low-light benchmark | MDPI 403; PA-LVIO table not extractable |
| 3 | Learned inertial odometry | 10 | Near. No outdoor long-flight absolute result was found. | 11 | 2: AI-IO dataset, self-supervised inertial odometry | MDPI 403 (SALSTM numbers) |
| 4 | Dynamics, drag and airspeed aiding | 13 | Near | 13 | 1 | MDPI 403; Khaghani RAS 2018 not reached |
| 5 | Map matching to imagery | 11, plus 3 in the venue sweep | No. The field moves monthly. | 22 | 4: Pi 5 at 9 FPS, Inertial Labs night IR, KTH/Spacemetric, building footprints | MDPI and preprints.org 403 |
| 6 | Visual place recognition and geolocalisation benchmarks | 5 | Near, for benchmarks that report metric error | 8 | 1 (IR-VL328) | none |
| 7 | Lidar and radar (TX or OPTICAL) | 10 | Near | 12 | 1 | One fetch got no safety-classifier verdict |
| 8 | Teach and repeat, visual homing | 4 | In practice yes. Every search returned the same two research groups. | 6 | 0 | none |
| 9 | Inertial sensors | 11 | Near | 12 | 2: ICM-42688 has no published Allan figures; single-antenna heading of ±1° | analog.com timed out twice |
| 10 | Barometer and altitude aids | 4 | Near. The remaining hits were forum posts. | 6 | 0 | none |
| 11 | Timing and integration on a Pi | 5 | Near | 8 | 1: camera trigger pins, millisecond camera-to-camera skew | none |
| 12 | Venue sweep and fielded systems | 13 | No. Vendor claims keep appearing. | 16 | 4 | unmannedsystemstechnology.com and preprints.org 403 |

---

## 2. Findings by topic

### T1. Optical flow

**No independent outdoor study** of flow-sensor accuracy against height, light or texture was found. What exists:
- lab rails;
- simulation;
- one fixed-wing flight set, reported in pixels;
- autopilot parameters.

| Source | Idea and result | Evidence |
| --- | --- | --- |
| Belfadel, Cain, Haessig, Chibane, "Optical Flow and IMU Fusion for Drone Horizontal Velocity Control", *J. Adv. Information Fusion* 19(2), Dec 2024 ([PDF](https://isif.org/files/isif/2025-01/optical_flow_p72.pdf)) | A truth model of the PMW3901: angular displacement quantised at 0.0015 rad per count, 50 Hz, ±21° field of view. Rail tests at 0.17 to 0.66 m. Over a true 0.6 m, dusk and direct sun gave 0.59 and 0.57 m; a checkerboard and plain wood gave 0.61 and 0.58 m. Lab only, with an ultrasonic height sensor. | [V] |
| Fathurrahman, Arifianto, Jenie, Muhammad, "Optical Flow Performance in the SUAV Flight Speed Estimation Using Farneback Method", *JNTETI* 14(1), 2025, doi 10.22146/jnteti.v14i1.15001 | Unreal simulation only: 100 m altitude, 25 m/s, downward camera. Mean speed error 0.6 m/s (σ 0.2) over a city and 0.3 m/s (σ 0.4) over forest; water failed. A ±10° camera tilt gave 1.7 to 1.9 m/s. A ±10 m height error gave 1.9 and 4.3 m/s. | [V] |
| Chao, Gu, Gross, Rhudy, Napolitano, "Flight-test evaluation of navigation information in wide-field optical flow", *JACIC* 13(11) 419–432, 2016 ([record](https://pure.psu.edu/en/publications/flight-test-evaluation-of-navigation-information-in-wide-field-op/)) | Fixed-wing, wide-angle camera, 30 to 183 m above ground, 7 flights, about 72,000 frames. Compared against GPS, laser and IMU reference motion. The abstract says only "good match". A 2013 IEEE companion paper reports a mean error of about 1.1 pixels per frame (σ about 1.1). | [V] abstract; [S] the 1.1 px |
| Rhudy et al., *J. Robotics*, 2015 | Fixed-wing; flow fused with an unscented information filter. Ground velocity within 1.3 m/s of GPS. | [S] |
| PX4 `params_optical_flow.yaml` ([source](https://raw.githubusercontent.com/PX4/PX4-Autopilot/main/src/modules/ekf2/params_optical_flow.yaml)) | EKF2_OF_N_MIN 0.15 rad/s and EKF2_OF_N_MAX 0.5 rad/s. Gate 3 SD, delay 7 ms, minimum quality 1. | [V] |
| PX4 flow sensor parameters | SENS_FLOW_MAXHGT defaults to 3 m (range 1 to 25 m); above it "accuracy will progressively degrade". SENS_FLOW_MAXR defaults to 2.5 rad/s. Holybro sets 30 m and 7.4 rad/s for the H-Flow. The PX4 flow page warns of slow oscillation in hover above about 20 m, from limited resolution. | [S] parameters; [V] the 20 m note |
| ArduPilot | Loiter on flow will not climb above RNGFND1_MAX_CM. A developer reports flow could not hold position at 100 m. Camera-based flow sent over MAVLink (a BlueOS extension) uses EK3_FLOW_DELAY 150 ms. One user flew 100 m on camera flow without GPS, with no accuracy figure. | [S] |
| Flow chips in low light | PMW3901 needs at least 60 lux. PAW3902 works to about 9 lux. PAA3905 has modes for >60, >30 and >5 lux; its lowest mode runs at 50 frames/s. Modules add an IR LED (40 mW on one PAA3905 board). | [S] vendor and reviewer pages |
| ARK Flow MR | PAA3905 flow sensor with a Broadcom AFBR-S50LX85D time-of-flight rangefinder. "Typical" range 50 m, 2°×2° beam, 5 g. Range shrinks in about 100 klx sun. The original ARK Flow reaches 30 m. | [S]; OPTICAL |
| Height without a rangefinder | Simulation only: altitude from two cameras' wide-field flow (Hiraiwa, Bando, Hokamoto, ICAS 2022). Older work scales flow with the IMU (Grabe et al., IROS 2013) or uses a barometer with a relaxed flat-ground assumption. No flight result using a barometer for flow scale above 30 m was found. | [V] ICAS abstract; [S] the rest |

**Proposed sim error model (TBC):**
- **Measurement:** body-frame angular flow in rad/s, equal to horizontal speed over height above ground, minus body rotation. This is what PX4 fuses.
- **Scale error, the dominant term:** δv/v = δh/h [C].
  - With a barometer referenced to take-off, terrain, trees and buildings enter directly. A 20 m canopy under a 100 m flight is a 20 % scale error [C].
  - The simulation above (±10 % height giving 8 to 17 % speed error) agrees in size.
  - ArduPilot's uncalibrated scale error of up to about 14 % (round 1, checked) is a separate per-sensor constant.
- **Noise:** chip quantisation at 50 Hz is 0.0015 rad per frame. Over 1 s at 100 m that is about 0.15 m/s [C], so quantisation does not dominate. Use PX4's 0.15 to 0.5 rad/s as the filter's conservative per-sample σ, and add extra noise that depends on texture.
- **Availability:**
  - Zero over calm water, fresh snow, uniform fields and glass.
  - Zero below the chip's lux floor, unless an IR LED is fitted (OPTICAL). An LED will not reach 100 m.
  - Saturates above SENS_FLOW_MAXR.
  - With a rangefinder, unusable above 30 to 50 m (OPTICAL).
- **Correlation:** the scale bias follows the terrain, so it persists along a flight leg. Model it as a first-order Gauss-Markov process with a terrain-scale correlation length, not as white noise.

### T2. Visual and visual-inertial odometry at drone altitudes

| Source | Result and assumptions | Evidence |
| --- | --- | --- |
| Ellingson, McLain, Brink, "Relative navigation of fixed-wing aircraft in GPS-denied environments", *NAVIGATION* 67(2) 255–273, 2020 ([link](https://navi.ion.org/content/67/2/255)) | Monocular VIO (an MSCKF filter) on a Jetson TX2, 1.5 m wingspan, about 6 km in 388 s. Accumulated error 5.3 % of distance over the whole flight, about 2.5 % for 150 to 350 s. IMU: a thermally calibrated InertialSense unit. | [V] |
| "Low-Rate Cross-View Map Updates for Drift-Bounded Fixed-Wing VIO in GNSS-Denied Missions", MDPI *Eng. Proc.* 163(1) 28, 2026 | On an 8.6 km flight, VIO alone drifted 1.34 % at the end, and 0.41 % with map anchoring; ATE 34.7 m. A simulated 24 km route: 0.92 % falling to 0.28 %. Drift is end-point error over distance. | [S] (403) |
| Spagnolo, Dobrevski, Skočaj, "Evaluation of Monocular SLAM Systems on High-Altitude Nadir UAV Footage", arXiv [2608.18632](https://arxiv.org/abs/2608.18632), 2026 | Monocular SLAM with no IMU. MASt3R-SLAM: 0.53 % horizontal mean error on 5 DJI flights. DROID-SLAM: 2.88 % on average. None kept the global shape on long sequences, and vertical error was poor. The authors judge monocular SLAM insufficient on its own. | [V] abstract |
| Train García, de Frutos Carro, Pulido Fernández, Torrente Delgado (UAV Navigation-Grupo Oesía), CEAS EuroGNC 2026-055, doi 10.82124/CEAS-GNC-2026-055 | On a real 36 km flight dataset, visual odometry alone drifted "around 1 %" of distance and INS alone about 4 %. | [V] |
| Stone, Petersen, Peterson, "Real-Time Thermal-Inertial Odometry on Embedded Hardware for High-Speed GPS-Denied Flight", arXiv [2603.02114](https://arxiv.org/abs/2603.02114), 2026 | Boson+ 640 long-wave IR camera with IMU, laser rangefinder for per-feature depth, barometer and magnetometer, in a fixed-lag factor graph on a Jetson Xavier NX. Drift under 2 % over kilometre-scale trajectories; closed-loop flight at 30 m/s. A GRU network corrects barometer error at speed. | [V] abstract; the rangefinder is OPTICAL |
| Sun et al., "Autonomous Quadrotor Flight despite Rotor Failure with Onboard Vision Sensors: Frames vs. Events", arXiv 2102.13406 | A frame camera needed 12 ms exposure at 50 lux (2 ms at 500 lux); the blur made frame-based VIO fail. An event camera still flew at 10 lux. | [S] |
| AERO-VIS (Burkhardt et al., *RA-L* 11(10), Oct 2026, arXiv [2605.07885](https://arxiv.org/abs/2605.07885)); Edged USLAM (Sarıözkan et al., ICRA 2026, arXiv [2603.08150](https://arxiv.org/abs/2603.08150)) | Event-camera visual-inertial SLAM onboard UAVs, flown in closed loop. No numbers in either abstract. No event-camera VIO result at altitude or over kilometres was found. EvMAPPER (arXiv 2409.18120) is a high-altitude event-camera dataset for mapping. | [V] abstracts |
| MARS-LVIG dataset, *IJRR* 2024 | 21 sequences at 80 to 130 m and 3 to 12 m/s, RTK truth. In the PA-LVIO paper (arXiv 2603.16228) the VIO baseline (LE-VINS) is worst on nearly all sequences, "mainly because of the high cruising altitude". | [S]; the table could not be extracted |
| Boxan, Lauzon, Vannini, Turgeon-Roy, Pomerleau, "One year in a forest", arXiv [2608.27628](https://arxiv.org/abs/2608.27628), 2026 | Ground robot in a subarctic Quebec forest, 64 km over a year. Visual SLAM was the most affected by season. Cross-season visual localisation often failed, even within one season; lidar succeeded. Relevant to an Ottawa winter. | [V] abstract |
| ISPRS 2026 study of winter Arctic UAV imagery | Over uniform snow, keypoints are detected but cannot be matched reliably. | [S] |
| Embedded compute | VINS-Mono on a Raspberry Pi CM4: 20 FPS, or 50 FPS with optical flow computed on the sensor (arXiv 2406.13345). VINS-Mono on a Pi 4: about 50 ms latency at half the CPU (forum). ROVIO on a Pi Zero 2 W (TU Delft). SMF-VO above 100 FPS on a Pi 5 (arXiv 2511.09072). Real-time downward VIO on a GAP9 RISC-V microcontroller (Kühne et al., *IEEE IoT J* 2025, arXiv 2509.10021). LEVIO: 3.46 m mean RMSE on EuRoC at 20 FPS within 100 mW. | [S] |
| Camera direction | Forward cameras track more features while translating. Downward or pitched cameras keep ground features at height but struggle at take-off (arXiv 2302.01867). TANGO-VIO (arXiv 2608.02079): the same translation gives weaker bearing change as altitude rises. | [S] |

**Proposed sim error model (TBC):**
- **Drift, without trajectory alignment:**
  - Monocular VIO on a Pi-class computer at 30 to 150 m: 1 to 3 % of distance; 5 % is plausible on a bad flight.
  - Stereo VIO with an industrial IMU at 40 to 100 m: keep round 1's 0.3 to 0.6 %.
  - Monocular VO with no IMU: 1 to 4 %. The 74 km GeoAnchor case in T5 was 3.8 %.
- **Heading:** keep round 1's 1 to 3° error carried into the outage, plus a slow yaw random walk. No per-minute rate was found.
- **Monocular scale:** a scale-factor random walk. Scale observability weakens with altitude because parallax shrinks.
- **Availability:**
  - Daylight only, unless the camera is thermal.
  - Fails below about 50 lux at speed (blur), over water and fresh snow, on featureless fields, and in fast yaw.
  - Model failures as whole runs that fail, not as a fraction of epochs.

### T3. Learned inertial odometry

| Source | Result and assumptions | Evidence |
| --- | --- | --- |
| AirIO, arXiv [2501.15659](https://arxiv.org/html/2501.15659) | IMU only; trained with true attitude, run with EKF attitude. Indoor drone racing (Blackbird), about 3 to 4 min per flight. ATE 0.403 m on trajectories seen in training, 1.309 m on unseen ones. Baselines: TLIO 1.189 / 3.478 m; IMO (uses thrust) 0.929 / 9.015 m; raw IMU integration 27.5 m. EuRoC held-out ATE 3.18 m. Simulated (Pegasus) runs of 317 to 559 m over 149 to 253 s: 3.64 m. All indoor or simulated with motion-capture truth. The paper does not say whether ATE is after alignment. | [V] tables |
| AirIMU, arXiv [2310.04874](https://arxiv.org/abs/2310.04874) | Learns IMU error and uncertainty; tested on a 262 km helicopter dataset. 31.6 % better in a pose-graph ablation. A drift-rate reduction of 2.2 to 4 times is reported elsewhere. | [V] abstract; [S] the factor |
| Kuruppu Arachchige, Kämäräinen, "Extended Model-Based Learned Inertial Odometry", ICUAS 2026, arXiv [2611.09584](https://arxiv.org/abs/2611.09584) | Adds body-frame torque dynamics, most informative when taken from rotor signals. Lower velocity error on held-out trajectory shapes across four public datasets. No drift figures. | [V] abstract |
| AI-IO (rotor speed plus IMU, transformer), arXiv 2603.00597, ICRA 2026 | Round 1 gave 0.24 m/s on indoor flights. The authors release a real dataset that includes rotor speed. | [S] |
| Cioffi, Bauersfeld, Scaramuzza, "HDVIO2.0", *T-RO* 2025 | A hybrid dynamics model (point mass plus a learned residual from thrust commands and IMU history) inside VIO. Translation error 57 % below plain VIO and 27 % below HDVIO. Tested in wind up to 25 km/h and fan wind up to 8 m/s. Not inertial-only. | [V] PDF |
| VeloBins, arXiv [2608.29720](https://arxiv.org/abs/2608.29720), 2026 | Estimates velocity as bins, with uncertainty from the spread. ATE 6 to 53 % below the best baseline, with the best filter consistency. Datasets include a 27 g quad and racing above 21 m/s. | [V] abstract |
| MosaicIMU, CoRL 2026, arXiv [2606.09355](https://arxiv.org/abs/2606.09355) | One expert per vehicle type. ATE 40 % below learned baselines. | [V] abstract |
| Self-Supervised Inertial Odometry, arXiv 2610.25988 | Trains without true trajectories. | [S] |
| Wang, Qu, Gao, Morin, arXiv [2505.15044](https://arxiv.org/abs/2505.15044), 2025 | Thermal anemometer with IMU, ESC data and barometer, through a GRU network. 5.7 m over 203 s indoors, with no wind. | [V] abstract |
| Wang et al., SALSTM, *Drones* 9(4) 279, 2025 | Self-attention LSTM on fixed-wing flight data. Numbers not retrieved. | [S] |
| Caltech supplementary material | A learned model overfit to the wind conditions it was trained in. | [S] |

**Main gap.** No learned inertial odometry result was found that is all of these: outdoors, over minutes, with GNSS truth, in wind, on a vehicle not seen in training.

**Proposed sim model (TBC):** treat it as a velocity pseudo-measurement.
- On a seen platform indoors: σ 0.2 to 0.5 m/s.
- Outdoors, for any method using rotor speed or thrust: add a bias equal to the unmodelled wind.
- On unseen trajectories: inflate σ by about 3, from AirIO's seen-to-unseen ATE ratio.
- Retrain for each airframe.

### T4. Vehicle-dynamics, drag and airspeed aiding

| Source | Result | Evidence |
| --- | --- | --- |
| Mwenegoha, Moore, Pinchin, Jabbal, "Error characteristics of a model-based integration approach for fixed-wing UAVs", *J. Navigation* 74(6) 1353–1366, 2021 | Monte Carlo simulation. A vehicle dynamic model is driven by autopilot commands; wind is 3.8 m/s constant plus a Gauss-Markov term. After 60 s of outage: 8.494 m, against 61 m for INS with GNSS. Yaw error 0.53 to 0.83° after outages of 10 to 90 s. | [V] PDF |
| Mwenegoha et al., "Model-Based Autonomous Navigation with Moment of Inertia Estimation for UAVs", *Sensors* 19(11) 2467, 2019 | At most 14.5 m after a 140 s outage. Roll and pitch stay within 0.06°; yaw grows to 0.65°. | [S] abstract and text snippet |
| Mwenegoha PhD thesis, Nottingham, 2021 | Real fixed-wing flight data. 43 times better than a tightly coupled INS with two satellites visible. For outages over 2 min, one to two orders of magnitude better. | [S] |
| Khaghani and Skaloud (EPFL) | ION 2017: small fixed-wing with a MEMS IMU, 3 min outage, more than 20 times the positioning autonomy of INS with GNSS. IEEE Access 2020 (doi 10.1109/access.2020.3038530): an order of magnitude better with two satellites over 100 s. | [S] |
| Ye, Zeng, Zeng, Zou, "Airspeed-Aided State Estimation Algorithm of Small Fixed-Wing UAVs in GNSS-Denied Environments", *Sensors* 22(9) 3156, 2022 | Real low-cost fixed-wing flights. Horizontal error under 30 m within 30 s (about 600 m flown) and under 50 m within 90 s (about 1800 m). Height error 0.5 m mean. | [S] abstract via snippet |
| Ye et al., arXiv [2310.01844](https://arxiv.org/abs/2310.01844) | Fixed-wing invariant EKF with a semi-aerodynamic model; an LSTM predicts angle of attack and sideslip. At most 30 m over a 130 s outage; wind is estimated. | [V] abstract |
| Advanced Navigation flight tests, vendor article, 2025-11-14 ([link](https://www.advancednavigation.com/tech-articles/real-flight-data-real-results-demonstrating-ins-aiding-technologies-for-gps-denied-resilient-pnt/)) | Light aircraft at 400 to 500 m. MEMS INS (Certus Evo) with an air-data unit (pitot and barometer): 8.8 m over more than 5 km (0.17 %); 118 m over 35 km (about 0.34 % [C]). | [V] vendor |
| Tagliabue and How, "Airflow-Inertial Odometry for Resilient State Estimation on Multirotors", ICRA 2021, arXiv [2105.13506](https://arxiv.org/abs/2105.13506) | Multirotor with bio-inspired airflow sensors. Up to 10 times less drift than IMU alone over 30 s, without wind. A wind map helps in turbulent wind. | [V] abstract |
| ANELLO X3 case study ([link](https://www.anellophotonics.com/case-studies/x3-imu-airborne)) | Hexacopter on PX4 with an optical-gyro IMU (bias instability under 0.5°/h) and an airspeed sensor. Under 20 m over a 740 m GPS-out segment of a 1,230 m route, at 10 m/s. | [V] vendor |
| Drag-based wind estimation against an ultrasonic anemometer | In hover, laminar 0 to 5 m/s wind: RMSE 0.26 to 0.29 m/s in speed and 4 to 5° in direction. A fleet calibration (egusphere-2024-222): under 0.2 m/s in steady wind, up to 0.6 m/s in gusts. Older work: 0.75 m/s and 8.9°. All of these take ground velocity from GNSS. | [S] |
| PX4 drag fusion | Parameters: EKF2_BCOEF_X/Y 0 to 200 kg/m², EKF2_MCOEF 0 to 1 1/s, EKF2_DRAG_NOISE 0.5 to 10 (m/s²)². PX4's GNSS dead-reckoning mode is experimental and states no accuracy. | [S] parameters; [V] the docs page |
| Inertial Labs with FT Technologies | An acoustic-resonance airspeed sensor in an INS, announced in 2024 as under development. | [S] |
| Gallo and Barrientos, *Aerosp. Sci. Tech.* 120 (2022); *Aerospace* 10(8) 708 (2023); arXiv 2205.13242 | Fixed-wing GNSS-denied INS using pitot, air vanes and magnetometer, with an open-source C++ simulator. No numbers in the abstracts. | [V] abstracts |
| Wind variability | Turbulence intensity over 10 min at 10 to 110 m height is mostly 0.10 to 0.16 (IEA Wind Task 41, 2025). | [S] |

**Proposed sim error model (TBC):**
- **Airspeed and drag measure velocity through the air,** so ground-velocity error equals wind-estimate error.
- **Wind at outage start:** known to σ 0.2 to 0.6 m/s from the GNSS-good phase [S].
- **Wind change during the outage:** for a 5 to 8 m/s mean wind, σ of about 0.5 to 1.3 m/s over 10 min [C, from turbulence intensity]. Model it as first-order Gauss-Markov with a time constant of a few minutes.
- **Position error from wind:** 0.5 m/s held for 300 s is about 150 m [C]. Compare the fixed-wing flights above: under 30 m in 30 s and under 50 m in 90 s.
- **Multirotors:**
  - Drag-only velocity needs a calibrated drag coefficient and degrades when the payload changes.
  - Rotor downwash corrupts a pitot tube (JSTAGE 2016) [S].

### T5. Matching imagery to satellite or orthophoto maps

| Source | Result and assumptions | Evidence |
| --- | --- | --- |
| NGPS, Sanket Sharma, arXiv [2607.18936](https://arxiv.org/abs/2607.18936), IROS 2026 | Downward camera matched to satellite imagery with learned features, fused in an adaptive UKF with VIO. Five flights at 60 to 150 m: RMSE 2.94 m; worst 6.04 m at 150 m and 2 m/s; 3.5 times better than monocular VIO. Jetson Orin NX; absolute fixes at 1 to 2 Hz, about 386 ms per match; RTK truth. Partly open source. | [V] abstract; [S] timing and truth (blog) |
| HTGL, *Drones* 10(7) 488, 2026 | Flight tests on a Jetson Orin NX: mean 7.53 m, maximum 21.08 m. The larger errors were over low texture. | [S] |
| PiLoT, Cheng et al., arXiv [2603.20778](https://arxiv.org/html/2603.20778v1), 2026 | Registers video to a georeferenced 3D mesh, not an orthophoto. Median error 0.92 m on UAVD4L-2yr (70 to 310 m, day and night), 1.27 m on UAVScenes, 1.37 m over a 10 km trajectory. Over 25 FPS on a Jetson Orin. Claims 100 % completeness across day, night and season. Needs a high-fidelity 3D model and tracking from a known start. | [V] |
| Appleget, Watson, Gray, Taylor (AFIT), "Navigating a sUAS without GNSS", *Inside GNSS*, 2023-05-29 ([link](https://insidegnss.com/?p=191313)) | One-third-scale Cub, Boson 640 IR camera pointing down, matched to satellite imagery; NovAtel PwrPak7 IMU; 400 to 600 m. Two flights of about 1 h each with no GNSS, at the PNTAX 2021 exercise. 6.79 m horizontal RMS against truth in the benign period. During jamming, within an 11 m budget at 95 %, inferred from residuals. | [V] |
| Inertial Labs white paper on Raptor-based visual positioning, May 2025 ([link](https://inertiallabs.com/gnss-denied-performance-of-vision-based-positioning-apnt-solution/)) | Cessna 172 at about 3,200 ft MSL; Maxar Precision3D maps; 1 Hz fixes into an EKF. Day: error bounded at 20 m. Night, with a Boson+ IR camera: under 15 m RMS over about 58 km. Altitude within 2 m by day and 5 m by night. GNSS denial began after figure-eight or circling manoeuvres. | [V] vendor |
| UAV Navigation-Grupo Oesía, CEAS EuroGNC 2026-055 | Real 36 km dataset: map matching held 31 ± 9 m (0.08 % of distance), against 4 % for INS and about 1 % for VO. At Jammertest 2025 it kept a 10 kg VTOL on track under spoofing; no number given. | [V] |
| Wang, Tsou, Jhan, Tang, ISPRS Archives XLIX-B1-2026 | SuperPoint and LightGlue matched to a true orthophoto and DSM at 100 to 250 m, about 13 km flown per altitude. Success depends strongly on texture and altitude; low altitude and low texture are worst. | [V] page 1 |
| GeoAnchor, GitHub, MIT licence, not peer-reviewed ([repo](https://github.com/YusufGUNEL/GeoAnchor)) | DINOv2 retrieval, LoFTR matching in a 400 m crop, particle filter with VO. On UAV-VisLoc flights at 406 to 2572 m: median 8.35 to 24.79 m where at least half the frames matched; 53 to 648 m on the three flights below that. VO alone drifted 2,803 m over 74 km. RoMa produced 341 confident inliers at wrong locations where LoFTR produced none. Extreme darkness: never initialises. Thermal at night: 6.2 % of frames correctly fixed at 95 % precision. 866 ms per frame on an RTX 3050 Ti. | [V] README |
| gnss-denied-nav, GitHub, MIT licence, not peer-reviewed ([repo](https://github.com/koksalan/gnss-denied-nav)) | No position prior: fine-tuned DINOv2 retrieval plus SuperPoint and LightGlue. Real UAV-VisLoc flights: median 24 m, 97.3 % within 100 m, and 2 of 1,987 confident fixes more than 100 m off. ArduPilot simulation jammed for 18.5 min: median 6.3 m, maximum 84 m, against 840 m without it. A distilled ViT-S model in INT8 takes 11.7 ms on a CPU. | [V] README |
| UASTHN (arXiv 2502.01035) and STHN (arXiv 2405.20470) | Thermal to satellite matching: 7 m with 97 % success within a 512 m search radius; works with about 11 % image overlap. Fails if the UAV leaves the assumed zone. | [S] |
| Cross day-night geo-registration, *Drones* 2025 (preprint 202502.0617) | Visible and thermal images matched to an RGB map and fused with INS, compensating attitude and height. RMSE under 50 m on long real flights. | [S] |
| Kinnari, Verdoja, Kyrki, *RA-L* 7(4) 10232–10239, 2022 | Matching made invariant to winter against summer, in Finland, with a real UAV demonstration. | [V] abstract; round 1 gave 12.6 to 18.7 m from the later LSVL paper |
| University of Turin (Unito) paper and LSVL | Global localisation from a 100 km² prior despite seasonal change. | [S] |
| Terlizzi and Fathian, arXiv [2609.28225](https://arxiv.org/abs/2609.28225), IROS 2026 | Matches the layout of buildings to a footprint database. Recall@1 was 100 % over 113 and 254 km², and 71.4 % over 452 km² (up to 277,000 buildings), on 7 flights. | [V] abstract |
| Sabel, Maki, Westin, Åsvärn (KTH and Spacemetric), ICAS 2022 | Simulated from Swedish orthophotos at 150 m: mean 5.5 m horizontal with a ±20 m prior; 86 m on a harder global set. Uses the 3D structure of vegetation in natural terrain. | [V] |
| SuperGlue-based drone-to-satellite matching (secondary source) | 61 % of photos within 50 m, mean 15.82 m. Worst over water and uniform fields. | [S] |
| NaviLoc (preprint; venue not confirmed) | CPU only: 9 FPS on a Raspberry Pi 5, 19.5 m mean at 50 to 150 m. | [S] only; the fetch was refused, treat as unverified |
| Compute | RaCo-ALIKED with LightGlue on a Jetson Orin Nano, fp16 TensorRT: 7.9 ms at 512 keypoints, 21.6 ms at 1024, 126.5 ms at 3072. | [S] |
| Integrity | SASGeo (arXiv 2607.07737) adds an acceptance rule that rejects ambiguous fixes; synthetic test only. Li and Waslander (arXiv 1909.08537) give an aviation-style (RAIM) protection level for visual localisation. | [S] |
| Licences | LightGlue code and weights: Apache-2.0, but SuperPoint's weights are under "a different, restrictive license". DISK: Apache-2.0. ALIKED: BSD-3-Clause. RoMa: MIT; its DINOv2 dependency is Apache-2.0. LoFTR code: Apache-2.0; licence of its weights unstated; its OT part depends on SuperGlue's restricted code. MASt3R: CC BY-NC-SA 4.0, non-commercial only. | [V] READMEs |

**Proposed sim error model (TBC):**
- **Measurement:** an absolute horizontal position fix (plus heading, if the method gives 4 degrees of freedom) at 0.5 to 2 Hz from a downward camera.
- **Accuracy:**
  - Good texture, summer, day, 60 to 250 m: σ 3 to 8 m.
  - High altitude, or retrieval-based methods: median 15 to 25 m.
  - Heavy tail when few frames match: p90 of 50 to 400 m (GeoAnchor).
  - Satellite-only maps with oblique low-altitude images: only 18.5 % within 5 m and 58.5 % within 20 m (AnyVisLoc, T6).
- **Wrong fixes:**
  - With a confidence gate: about 0.1 % more than 100 m off (2 of 1,987).
  - Without one: much higher; RoMa produces confident false inliers.
- **Availability:**
  - Visible camera at night: zero.
  - Thermal at night: 6 to 28 % of frames on a hard dataset; close to continuous in vendor flights.
  - Fresh snow or leaf-off ground against summer maps: degrades or fails. No quantified UAV-over-snow result was found.
  - Water and uniform fields: fail.
- **Prior radius:** local methods need dead reckoning to stay within about 200 to 500 m. Global retrieval works with no prior but is coarser.

### T6. Visual place recognition and geolocalisation benchmarks

- **AnyVisLoc,** arXiv [2503.10692](https://arxiv.org/html/2503.10692v1), CVPR 2026 Findings [V]. The best quantified evidence that satellite-only maps are much weaker than aerial maps at low altitude.
  - Data: 18,000 images from 7 DJI models; 30 to 300 m altitude; camera pitch 20 to 90°; 25 regions in 15 Chinese cities; day and night.
  - Best pipeline (CAMP retrieval with RoMa and re-ranking), against aerial photogrammetry maps (0.07 m): 74.1 / 87.7 / 94.2 % within 5 / 10 / 20 m.
  - Against satellite maps (0.197 m pixels with a 30 m DSM): only 18.5 / 38.7 / 58.5 %.
  - Retrieval recall@1: 61.6 % (aerial) and 42.8 % (satellite).
  - Adding 60° of yaw noise cut accuracy within 5 m by 25.7 points.
- **UAV-VisLoc,** arXiv 2405.11936 [S]: 11 Chinese sites at about 400 to 2,000 m. GeoAnchor and gnss-denied-nav were evaluated on it (T5).
- **AerialVL,** *RA-L* 9(10) 8210–8217, 2024 [V abstract]: 11 sequences, about 70 km, with baselines for place recognition, alignment and VO.
- **Others** [S]:
  - UAVScenes (arXiv 2507.22412): SALAD (DINOv2) recall@1 67.1 % against MixVPR 34.0 %.
  - LASED (arXiv 2507.15089): 1 million high-altitude images.
  - IR-VL328 (2025): 328 night IR scenes.
  - DenseUAV: 80 to 100 m.
  - UniT-1652, for changes over time.
  - A multi-weather version of University-1652.
  - University-1652 is partly simulated and has known coordinate problems.
- **Failure statistics** beyond AnyVisLoc and the GeoAnchor table were not found.

### T7. Lidar and radar (all TX or OPTICAL)

| Source | Result | Evidence |
| --- | --- | --- |
| Girod, Hauswirth, Pfreundschuh, Biasio, Siegwart, "A robust baro-radar-inertial odometry m-estimator for multicopter navigation in cities and forests", MFI 2024, arXiv [2408.05764](https://arxiv.org/abs/2408.05764) | Closed-loop multicopter flights in cities and forests: 0.5 to 3.2 % of distance. Barometer readings differenced against a ground reference cut vertical drift. | [V] abstract; TX |
| Michalczyk, Quell, Steidle, Müller, Weiss, "Tightly-Coupled Factor Graph Formulation For Radar-Inertial Odometry", IROS 2024 | TI AWR1843BOOST radar. Manual flights of 150 to 175 m (CNS-UAV set), shorter ones on ARDEA-X. Position RMSE norm 0.08 to 0.71 m; ARDEA-X mean about 0.31 m (EKF) and 0.36 m (factor graph). Code: aau-cns/aaucns_rio. | [V] PDF; TX |
| Zhu et al., "Robust 4D Radar-aided Inertial Navigation for Aerial Vehicles", arXiv [2502.15452](https://arxiv.org/abs/2502.15452), 2025 | Radar scan matching plus Doppler velocity, with keyframes matched to a prior map. No numbers in the abstract. | [V] abstract; TX |
| Advanced Navigation | Fibre-optic-gyro INS (Boreas D90) with its Laser Velocity Sensor (Doppler lidar): 29 m over more than 100 km (0.03 %) on a light aircraft. | [V] vendor; OPTICAL |
| SAE / Vertical Flight Society 2026, "Flight Test Results for Velocity Aided Navigation in GPS Denied Environments" | Doppler lidar velocity aiding in flight. | [S]; OPTICAL |
| FAST-LIO2 lidar odometry on a drone over flat grassland (arXiv 2212.07132) | Drifted 4.2 m where scan registration was under-constrained. | [S]; OPTICAL |
| Livox Mid-360 lidar | Rated to 40 m, so no ground returns from 100 m [S/C]. Lidar odometry on small drones is a low-altitude method. | OPTICAL |
| Lidar matched to elevation data: round 1's arXiv 2510.01348 (heightmaps to DEM); Quenzel et al., arXiv 2412.02533 (to CityGML and DEM) | Matching lidar scans to stored terrain or city models. | [S]; OPTICAL |
| Terrain-referenced navigation | UAV Navigation (CEAS 2026): radar altimeter against a DEM, 239 ± 16 m over 187 km (0.1 %), for low altitude. An automotive mm-wave radar on a Class 1 drone, matched to a lidar terrain map with a particle filter (MDPI *Eng. Proc.* 88(1) 11); numbers not retrieved. Flat terrain carries little information. | [V] the 239 m; [S] the rest; TX |
| Altimeters | Ainstein US-D1 radar: 0.5 to 50 m, ±0.1 m below 10 m then 1 %, US$499 since April 2024; US-D1 Pro reaches 120 m, £620. LightWare SF30/D lidar: 0.2 to 200 m (white wall, daylight), ±10 cm, about US$399. | [S]; TX and OPTICAL |
| NATO STO-MP-SET-275-15 | A manufacturer's Doppler radar module flown under jamming. | [S]; TX |

### T8. Teach and repeat, and visual homing

- **Warren, Greeff, Patel, Collier, Schoellig, Barfoot,** "There's No Place Like Home: Visual Teach and Repeat for Emergency Return of Multirotor UAVs During GPS Failure", *RA-L* 4(1) 161–, 2019 [V PDF].
  - Platform: DJI M600 Pro, gimballed ZED stereo camera, Jetson TX2.
  - Envelope: 5 to 25 m altitude, up to 55 km/h, wind up to 8 m/s, on a 450 m closed-loop path.
  - Error: under 1.5 m over most of the path, up to 4.5 m at corners (limited by the controller), with no localisation failures.
  - Altitude tolerance: about 100 matched features per keyframe even with a 6 m (50 %) altitude offset on a 12 m path.
  - The GPS failure was simulated.
- **Related work** [S]:
  - Warren et al., FSR 2017: fixed-wing localisation, across days.
  - Patel et al., ICRA 2020: localisation against a 3D reconstruction despite lighting and seasonal change, over several km of data.
  - CLOUD (Canadian Longterm Outdoor UAV Dataset; Suffield, Alberta and Montreal, 2018) was built for this problem.
- **van Dijk, De Wagter, de Croon,** "Visual route following for tiny autonomous robots", *Science Robotics* 9(92), 2024 [S]: a 56 g drone running on a microcontroller, routes up to 100 m (likely indoors), under 20 bytes per metre.
- **Ground robots in winter:** "Toward Teach and Repeat Across Seasonal Deep Snow Accumulation", arXiv 2505.01339 [S].
- **Not found:** aerial teach and repeat above 25 m, or across seasons in flight.

### T9. Inertial sensors

| Source | Result | Evidence |
| --- | --- | --- |
| Analog Devices, "Good on Paper, Drifting in Flight: Vibration Effects in Drone IMUs" | Propeller vibration turns into a quasi-steady gyro error (vibration rectification). On a 5-inch quad, a commercial IMU drifted 3.5° once the props ran, about 0.8° of yaw within 6 s of motor start. | [S] vendor; the page timed out twice |
| NASA Ames, NTRS 20205000223 | MEMS IMUs exposed to UAV-like vibration showed more noise and higher bias instability. | [S] |
| ArduPilot vibration guidance | Below 30 m/s² is acceptable; above 60 m/s² nearly always causes problems; clipping should be zero. | [S] docs |
| Waegli, Skaloud, Guerrier et al., *Meas. Sci. Technol.*, 2010 | Four MEMS triads cut noise by about 48.6 %; averaging alone predicts 50 % [C]. ARMA/GARCH weighting did better. | [S] |
| Distributed IMUs (AAS 25-436) | Static test: angle random walk 70.3 % lower, bias instability 69.8 % lower. Simulated with up to 18 IMUs, real with 5. A gyro array (PMC6187449): ARW 1.57 to 0.33 °/√h, bias drift 224.2 to 47.8 °/h. A land-vehicle EKF on a large array (arXiv 2606.29271). No IMU array flown on a drone with navigation results was found. | [S] |
| ICM-42688-P | No published Allan bias-instability or ARW figures (TDK forum, 2023 and 2025). Only noise densities: 2.8 mdps/√Hz gyro, 70 µg/√Hz accelerometer. The sim needs a bench Allan test. | [S] |
| Temperature | A Parrot patent (US10191080) describes low-cost drone IMU bias drifting with temperature, compensated from chip temperature. Soak and ramp calibration methods exist. No cold-weather Allan data for consumer parts was found. | [S] |
| Heading observability, single antenna | PX4's EKF-GSF yaw estimator (Riseborough 2020) needs a horizontal velocity change larger than the GPS velocity uncertainty. Brazeal et al., *Sensors* 2021: at ≤5 m/s a dual-antenna unit can be up to 5 times more precise in heading. Contreras et al., *Drones* 9(3) 169, 2025: claim ±1° heading from a single hovering antenna, MEMS IMU, no magnetometer. | [S] |
| Kaygısız and Şen, *J. Navigation* 68 355–366, 2015 | 10°/h gyros on a land vehicle. Heading error fell from ±90° to below 5° in 40 s, and from 180° to 4° in 180 s. | [V] PDF |
| Published free-inertial and aided drift | CEAS 2026: INS alone, 4 % of distance over a 36 km flight [V]. ANELLO hexacopter with airspeed: 20 m over 740 m (T4) [V vendor]. Advanced Navigation MEMS INS with air data: 0.17 to 0.34 % (T4) [V vendor]. Aeron van test: 254.6 m at 31.4 km [S vendor]. No peer-reviewed Pixhawk-class IMU-only flight log with errors at 30 s and 60 s was found. | as marked |

### T10. Barometer and other altitude aids

- **Bosch BMP388** [S, flyer]:
  - relative accuracy ±0.08 hPa, about ±0.66 m;
  - noise 0.03 Pa at the lowest bandwidth;
  - long-term stability ±0.33 hPa over 12 months.
- **Weather drift.** Near sea level 1 hPa is about 8.3 m [C].
  - Pressure tendency [S]: steady ±0.5 hPa per 3 h; slow fall 1 to 3 hPa per 3 h; "rapid" above 3 hPa per 3 h (aviation) or above 6.
  - In height [C]: about 1.5 to 8 m per hour normally, and 8 to 16 m per hour or more in a storm.
  - Field reports [S]: 20 m after a 105 min flight; about 10 m with a BMP388 on returning to launch.
- **Static-pressure error.** PX4 asks for under 2 m of barometric altitude drop at maximum horizontal speed before tuning the EKF2_PCOEF compensation, which assumes the error is linear in airspeed [S].
- **Differential barometry** against a ground reference cuts vertical drift (BRIO, in T7) [V abstract]. The ground reference needs a data link (NET).
- **Laser and radar altimeters:** see T7 (SF30/D, US-D1). TX and OPTICAL.
- **Proposed sim model (TBC):**
  - barometer bias as a random walk equal to 2 to 8 m per hour, plus 0.3 to 0.7 m of white noise;
  - a static error that grows with speed, up to 2 m at maximum speed, more on an unvented hull;
  - optical flow and terrain matching need height above ground, not pressure altitude, so the sim also needs a terrain model.

### T11. Timing and integration on a Raspberry Pi-class payload

- **Camera timestamps** [S]:
  - libcamera's sensor timestamp is taken from the Unicam DMA buffer and is only approximate.
  - Its wall-clock timestamps carry "many milliseconds" of jitter, depending on load.
  - Two externally triggered cameras on a Pi 5 were reported to differ by milliseconds.
  - The Raspberry Pi global-shutter camera (IMX296) has an external trigger pin (XTR); the OV9281 triggers on XVS.
  - Luxonis OAK cameras timestamp camera and IMU from one counter, to under 10 µs.
- **Real-time kernel:**
  - Giacomossi et al., "Scheduling Analysis of UAV Flight Control Workloads on PREEMPT_RT Linux Using a Raspberry Pi 5", ETFA 2026, arXiv [2604.19275](https://arxiv.org/abs/2604.19275) [V abstract]: on a 250 Hz loop under stress, the standard kernel's worst case exceeded 9 ms. PREEMPT_RT brought it under 225 µs; the rest comes from memory contention.
  - On the other hand [S]: I2C jitter was reported worse under PREEMPT_RT than on the stock Pi kernel (linux-rt-users list). One field report found PREEMPT_RT tripled PPS timestamp jitter, because interrupt handlers become threads.
- **Camera-IMU time offset:** estimating it online is standard (Li and Mourikis, IJRR 2014; Qin and Shen, 2018) [S]. It can fail when the initial offset is large.
- **Proposed sim model (TBC):**
  - a constant camera-IMU offset of 5 to 30 ms, unknown to the filter, plus 1 to 5 ms of jitter;
  - with a userspace I2C reader on the stock kernel, millisecond-level IMU sample-time jitter, reduced by hardware FIFO timestamps or interrupt timestamps;
  - at 10 m/s, a 10 ms offset is a 0.1 m camera-IMU mismatch, an error that scales with velocity [C].

### T12. Venue sweep and fielded systems

- **UAV Navigation-Grupo Oesía,** CEAS EuroGNC 2026-055 (CC BY 4.0) [V]: INS 4 %, VO about 1 %, map matching 0.08 %, radar terrain matching 0.1 % (see T2, T5, T7). Round 1 named them as a seller.
- **AFIT,** *Inside GNSS* 2023 [V]: two 1 h flights without GNSS on IR map matching, 6.79 m RMS (T5).
- **Vantor (formerly Maxar) Raptor Guide** [S vendor]: claims "demonstrated absolute accuracy <10 m RMSE in all dimensions", using its 3 m Vivid Terrain data.
  - Inertial Labs' integration showed ±20 to 25 m in GNSS-denied segments.
  - The Inertial Labs Cessna flights gave 20 m by day and under 15 m RMS at night with IR (T5).
- **Vermeer** [V article, dronexl 2026-05-29]:
  - hardware: up to four EO/IR cameras, an Nvidia edge computer, a 3D terrain database and a celestial mode;
  - about US$20k per aircraft;
  - no accuracy published.
- **OKSI OMNInav and Odyssey** [S vendor]: "drift-free" map-matching updates, tested with imagery up to 10 years old. No numbers.
- **Skydio X10D** [S vendor]: VIO "at high altitudes" and vision-based Anchor Points. No numbers.
- **UAVOS with Mira Aerospace, NAVAI** [S press]: a vision module flown at 16,000 m.
- **Sightline Intelligence and partners, 2026** [S]: CE90 under 3 m for targeting in GPS-denied flight tests.
- **Ukraine** [S]:
  - Twist Robotics' OSCAR visual navigation module;
  - TFL-1 terminal guidance;
  - per IEEE Spectrum (via Razom), visual navigation reached the battlefield only "this year".
- **Russia** [S]: adding image-based navigation to Geran drones (Euromaidan Press, 2026-10-11), and 20-element anti-jam antennas (2026-09).
- **SPRIN-D Funke challenge** (round 1, arXiv 2510.01348): won by CTU's Multi-robot Systems group with Fly4Future, using lidar heightmaps below 25 m.
- **No independent accuracy figure** was found for any battlefield system.
- **Not reached:** 2024 to 2026 theses on GNSS-denied small-UAV navigation. The one search returned only theses from before 2020.

---

## 3. Corrections and upgrades to the first-round report

1. **§7.2, "Inertial with manoeuvres before the outage: 0.65° after a 140 s outage, low-cost IMU".**
   - The 0.65° comes from a fixed-wing filter aided by a vehicle dynamic model (Mwenegoha et al., *Sensors* 19(11) 2467, 2019), not from inertial-only coasting [S, confirmed in two snippets].
   - Plain INS heading would grow faster. Relabel it "model-aided fixed-wing".
   - The 2021 *J. Navigation* follow-up gives 0.53 to 0.83° after outages of 10 to 90 s, also model-aided and in simulation [V].
2. **§7.1 and §16.6, "None of these papers gives drift in metres".**
   - AirIO does: ATE 0.40 m on seen and 1.31 m on unseen 3 to 4 min indoor flights, and 3.18 m on EuRoC [V].
   - The caution still stands: every such result is indoors or simulated, with motion-capture truth.
3. **§7.1, monocular VIO at altitude "0.5 to 2.9 %", "honest model 0.3 to 0.6 %".**
   - 0.3 to 0.6 % holds only for stereo with an industrial IMU.
   - Monocular VIO on fixed-wings measured 2.5 to 5.3 % (Ellingson 2020) and 1.34 % (8.6 km, 2026). VO alone drifted about 1 % over 36 km (CEAS 2026).
   - For a Pi-class monocular payload, use 1 to 3 % [V/S as in T2].
4. **§9.6 and §16.8, "None publishes accuracy".** Partly wrong:
   - AFIT: 6.79 m RMS over 1 h flights [V].
   - UAV Navigation: 31 ± 9 m over 36 km [V].
   - Inertial Labs: under 15 m RMS at night over 58 km (vendor) [V].
   - Vantor: "<10 m RMSE" (vendor) [S].
   - Battlefield systems still publish nothing.
5. **§16.6, teach and repeat, "snippet for the error".** Upgraded to [V]: under 1.5 m over most of the 450 m path, up to 4.5 m at corners, at 5 to 25 m altitude. The GPS failure was simulated.
6. **§7.1, "PX4 models flow noise as 0.15 to 0.5 rad/s".** Confirmed in the source parameter file [V]. These are filter tuning bounds, not measured sensor noise.
7. **§7.3, firms selling map matching (Maxar/Vantor, UAV Navigation-Grupo Oesía).** Figures now exist; see item 4.
8. **§14, "Independent accuracy tests of optical flow sensors against height and light: nothing found".** Still true for outdoor flight. Partial evidence now exists:
   - chip lux floors of 60, 9 and 5 lux [S];
   - one lab rail test [V];
   - one simulation at 100 m [V];
   - Chao et al.'s fixed-wing flights at 30 to 183 m, reported in pixels [V/S].

---

## 4. Searches that found nothing

**Optical flow**
- An outdoor flight study of flow-sensor velocity error against height (10 to 100 m) with RTK truth.
- Optical-flow velocity scaled by barometric height above 30 m, in flight.

**Visual odometry**
- Event-camera VIO over kilometres, or at altitude, with numbers.
- Thermal VIO drift figures other than "under 2 %" (arXiv 2603.02114).

**Learned and model-aided dead reckoning**
- Learned inertial odometry outdoors over minutes, with GNSS truth and wind, for multirotor or fixed-wing.
- Rotor-drag velocity RMSE against GPS in outdoor flight.

**Teach and repeat, and map matching**
- Aerial teach and repeat above 25 m, or across seasons in flight.
- UAV map matching over snow against summer imagery, quantified.
- A wrong-match rate for map matching over repetitive farmland or forest.
- SuperPoint/LightGlue runtime on a Raspberry Pi 5.

**Inertial sensors and timing**
- A peer-reviewed Pixhawk-class IMU-only flight log with errors at 30 s and 60 s.
- Allan bias instability for the ICM-42688-P or BMI088, especially in the cold.
- An IMU array of 16 to 32 units flown on a drone, with navigation results.
- A measured magnetometer-free heading error at the end of an aided phase on a multirotor.
- A measured camera-to-IMU timestamp error on a Raspberry Pi.

**Radar, lidar and products**
- A drone Doppler-radar velocity sensor, other than Honeywell's, with a percent-of-distance specification.
- Lidar odometry end-point drift on a drone over kilometres without loop closure.
- Accuracy figures for Auterion, OKSI, Skydio, Shield AI, Twist Robotics or TFL-1.

---

## 5. Would more searching find anything?

- **T1, optical flow: little.** The literature treats flow as a short-range, low-altitude sensor, so the missing outdoor height curve is a gap in the field, not in the search. A bench test and short flights on our own hardware would be worth more.
- **T2, VIO and VO: some.** Fixed-wing and monocular figures now span 0.5 to 5 %, and new papers mostly land inside that range. Per-sequence spreads (the PA-LVIO table on MARS-LVIG, the MDPI fixed-wing paper) need full-text access, not more searches.
- **T3, learned inertial odometry: unlikely.** The field publishes indoor, motion-capture results; outdoor long-flight evidence probably does not exist yet. Watch the 2026 conference proceedings.
- **T4, dynamics and airspeed: small gains.** The Khaghani RAS 2018 paper and the Mwenegoha thesis would firm up the fixed-wing model-aided figures. Outdoor numbers for drag-only multirotor velocity appear not to exist.
- **T5, map matching: yes.** This area publishes monthly; many papers here are from 2026, and vendors keep releasing figures.
  - A dedicated pass on snow, leaf-off and night would still pay.
  - The two MIT-licensed GitHub projects, evaluated on public data, are the cheapest way to our own numbers once the owners approve looking at third-party code.
- **T6, benchmarks: little** for metric results; AnyVisLoc is the key one. More would come only from reading full result tables.
- **T7, lidar and radar: little that matters,** since all of it transmits or emits light. A few more radar odometry percentages could be found.
- **T8, teach and repeat: no.** Aerial teach and repeat is one group's work, and its results were read.
- **T9, inertial sensors: small gains.** The useful next step is measurement: Allan curves of our IMU at room temperature, in the cold, and with motors running.
- **T10, barometer: no.** Physics and field reports agree; numbers would come from our own logs.
- **T11, timing: no.** Pi-specific numbers have to be measured.
- **T12, fielded systems: yes, but low quality.** Vendor claims will keep appearing. Independent figures for battlefield systems are unlikely to be made public.

---

## 6. Access problems (for the record)

- **Refused or blocked:**
  - every MDPI article (www.mdpi.com, mdpi.com): 403;
  - preprints.org: 403;
  - PMC: a captcha page;
  - doaj.org: 403 once;
  - unmannedsystemstechnology.com: 403;
  - analog.com: timed out twice.
- **PDFs returned as binary:** several WebFetch results. Their saved copies were converted locally with `pdftotext` and read.
- **Search budget:** 121 of 300 WebSearch calls used. No budget error occurred.
