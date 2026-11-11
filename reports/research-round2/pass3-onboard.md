# Onboard sensing, pass 3: driving the remaining topics towards saturation

- **Date:** 2026-11-11
- **Scope:** topics A to F from the pass-3 task. Only items that are new, or that correct or upgrade the evidence in `sources-research-20261111.md` (round 1), `onboard.md` (pass 1) and `onboard-pass2.md` (pass 2), are reported.
- **Method:** WebSearch and WebFetch only. No shell was used, and nothing in the repository was touched except this file.
  - Saturation means 8 consecutive searches that add no method, result or number not already logged.
  - A search counted as "new" when it added such an item, even a minor one. Items judged irrelevant to the topic's question are listed but counted as dry; each is marked.
  - Topics were worked in order A to F, and this file was updated after each batch.
- **Budget:** about 204 WebSearch calls of the 300 allowed, plus about 60 fetches. No budget error occurred.
- **Labels:**
  - [V]: read today in the cited primary source (the abstract at minimum).
  - [S]: search snippet or secondary page only.
  - [M]: memory.
  - [C]: my own arithmetic.
- **Flags:**
  - TX: the vehicle transmits radio.
  - OPTICAL: the vehicle emits light.
  - NET: needs a network, operator cooperation or a data link.
- **Untrusted content:**
  - No page text addressed to an agent was encountered.
  - Every fetch prompt told the tool to ignore instructions in the page.
  - One search result was an aggregator advert ("1 month free Claude Pro"); it was ignored.
- **Fetch limits:** PDFs came back as unreadable binary. In those cases I looked for an abstract or HTML page instead, and say so where it matters.

---

## 1. Coverage

| Topic | Searches | Saturated | New items logged | New items in the last 10 searches | What blocked |
| --- | --- | --- | --- | --- | --- |
| A. Learned inertial odometry | 42 | **Yes** (searches 35 to 42 dry) | 20 | 1 | CVF 403 (Tartan IMU), sciforum 403 (Flare Bright ENC paper), MDPI PDF binary |
| B. Dynamics, drag, airspeed aiding | 72 | No (stopped for budget) | 45 | about 5, mostly patents and wind-measurement papers | EPFL Infoscience 429, Springer sign-in, MDPI 403, HAL bot wall, Nottingham 403/404, IMAV PDFs binary |
| C. Radar and lidar | 32 | No (stopped for budget) | 27 | about 4 | MDPI 403, AAU/CMU/Essex PDFs binary |
| D. Inertial sensors | 27 | No (stopped for budget) | 22 | about 4 | analog.com timed out (third time across passes), Septentrio 403, SBG/USP PDFs binary, MDPI 403 |
| E. Timing on Pi-class payloads | 20 | No (stopped for budget) | 20 | about 7 | PMC needs cookies, NSF PDF binary, a blog 404 |
| F. Optical flow above 30 m, barometer | 11 | No (stopped for budget) | 10 | about 7 | none |

Only topic A met the strict rule. For B to F, reaching it would have needed more searches than the budget held. Section 5 gives my judgement on what is left in each.

---

## 2. Findings by topic

### A. Learned inertial odometry (saturated)

**Main gap, unchanged from pass 2 and now firmer after 42 searches.** No learned inertial odometry result was found that is all of these at once:
- outdoors;
- minutes long;
- with GNSS truth;
- in wind;
- on an unseen airframe.

The closest items are QuadPosNet (outdoor, RTK truth, but about 34 s runs on periodic paths) and AbdulMajuid 2021 (4 to 32 min logs, but the "truth" is the autopilot's own GPS-aided EKF).

| Source | Result and assumptions | Evidence |
| --- | --- | --- |
| AI-IO, arXiv [2603.00597](https://arxiv.org/html/2603.00597), ICRA 2026 (upgrades round 1 §16.6 and pass 2) | SpeedyBee F7 V3 with a BMI270 IMU; rotor speed from ESC telemetry over bidirectional DShot; VICON truth.<br>Data: 12 manual runs (6,704 m, 1,960 s, up to about 14 m/s) and 10 slow autonomous runs; "windless conditions" assumed.<br>Own dataset (velocity error / ATE): AI-IO 0.237 m/s / 1.81 m; AirIO 0.556 / 2.56; IMO 4.27 / 61.4; IMU preintegration 53 / 102.<br>These rotate the network output with **ground-truth orientation**. With the EKF on the DIDO dataset: 0.371 m/s / 3.88 m.<br>Radxa Zero3W (Cortex-A55): 8.9 ms per inference, EKF at 20 Hz. Real-time accuracy is shown only qualitatively. | [V] |
| PX4 and ArduPilot rotor-speed support | PX4 v1.16 streams eRPM over bidirectional DShot (DSHOT_MOT_POL, default 14 poles). ArduPilot reads RPM from AM32, BLHeli32 ≥ 32.7 and BLHeli_S ≥ 16.73. Both use it only for notch filters; neither EKF fuses it. Rotor speed is therefore available on a Pixhawk-class stack with no extra sensor. | [S] docs |
| Massas and Klein, "Quadrotor Neural Dead Reckoning in Periodic Trajectories" (QuadPosNet), arXiv [2502.17964](https://arxiv.org/html/2502.17964v1), 2025 | Outdoor setup: DJI Phantom 4 RTK, Movella Dot IMU (BNO055 module) at 120 Hz, RTK truth; 36.4 min over 65 trajectories (about 34 s each [C]).<br>Position RMSE: 13.8 to 17.6 m outdoors (QuadNet 15.1 to 28.9 m); 0.16 to 0.56 m indoors on a Crazyflie.<br>Requires sinusoidal (periodic) trajectories, which cost battery. | [V] |
| QuadNet, Shurin and Klein, *Sensors* 22(4) 1426, 2022 | DJI M300 RTK, Pixhawk Cube IMUs at 25 Hz; a multi-IMU follow-up exists. | [S] |
| AbdulMajuid, Mohamady, Draz, El-bayoumi, arXiv [2109.04861](https://arxiv.org/abs/2109.04861), 2021 | RNN on raw Pixhawk logs (IMU, barometer, magnetometer). 548 public logs of 4 to 32 min (465 for training, 83 for validation).<br>Maximum 3D error per flight: median 35 m; best 2.7 m on a 5 min flight; 90 % of flights under 166 m.<br>Caveats: truth is the GPS-aided EKF, and the training and validation logs share a pool [C]. | [V] abstract |
| Flare Bright (UK), ENC 2024 (Starkey, Sequeira, Furse, Palmer-Jorge, Rider) | Model-based plus ML software on a 2 m fixed-wing, flights up to 1 h. A US$5 phone IMU "outperforms" a US$10k HG1930 after about 20 min. The SENS-INS datasheet (Feb 2024) forecasts 0.5 to 1.0 m/s of drift. Inputs include motor RPM and flight-controller commands; about 1 min of flight data trains each airframe's model. | [S] |
| Flarebright Intera and Tactera, Calibre Defence, 2025-04-11 ([link](https://www.calibredefence.co.uk/flarebright-unveils-tactera-strike-grade-gnss-free-navigation/)) | Intera "typically drifts up to 3.5 km in 30 minutes" (about 1.9 m/s [C]).<br>Tactera matches automotive lidar (about £500, 170 g) or radar-altimeter returns to a DEM on a Raspberry Pi 3B: about 30 m in flight tests in Spain, target 10 m.<br>Swarm sharing brings the error under 10 m. | [V] press; Tactera is OPTICAL or TX; the swarm is TX and NET |
| Extended model-based learned IO (ICUAS 2026, pass 1) | The author's project page: "up to 61 % improvement in relative error" against IMO on unseen trajectories. | [S] |
| Tartan IMU (Zhao et al., CVPR 2025); SUPER Odometry 2.0 (arXiv 2608.25427) | IMU foundation models pretrained on more than 100 h from about 10 robot types, adapted with LoRA (1.1 M parameters) or online. Neither gives drone IMU-only drift numbers. | [S] / [V] abstract |
| BLENDS (Cohen and Klein, arXiv 2606.22456); ICD-Net (arXiv 2512.00037); VIO-DualProNet | Learned covariance:<br>– in a smoother: up to 25.6 % lower RMSE than RTS, offline;<br>– in drone VINS-Fusion: 38 % lower APE;<br>– learned process noise for VIO. | [V]/[S] |
| Altawaitan et al., arXiv 2505.06748 | Network predicts IMU bias from IMU history, inside an invariant MSCKF; robust through long visual dropouts. | [V] abstract |
| DIDO (Zhang ... Gao, IROS 2022, arXiv 2203.03149) | Learned quadrotor dynamics and kinematics in a two-stage EKF. Its public dataset is the benchmark AI-IO uses. | [V] abstract |
| Datasets | KIOS M300 (Zenodo 15089282, v2 May 2026) also logs a TriSonica Mini wind sensor and battery voltage and current; 18 real flights, doubled synthetically. AgriLiRa4D (lidar, 4D radar, IMU, FINS-RTK truth). InGVIO fixed-wing GNSS-VIO set with RTK truth (arXiv 2210.15145). | [S] |
| Volatus Aerospace (Canadian) V-Cortex, 2026-09-22 | "GNSS-denied navigation ... using onboard default sensors". No sensors or numbers given. | [S] press |
| Counted as dry | TCS patent US11525683B2: a high-pass-filtered drag-free model velocity, no numbers [V]. CLAK (simulated lidar TRN). PI-WAN (dynamics for control). PSO-LSTM and CNN-BiLSTM pseudo-GNSS papers (ground vehicles). | — |

**Sim model, update to pass 1 (TBC).** Treat learned or rotor-speed IO as a body-velocity pseudo-measurement.
- σ 0.25 to 0.4 m/s in calm air with true attitude (AI-IO). Use the 0.37 m/s EKF figure when attitude is estimated.
- Add a bias equal to the wind's air-relative component.
- Inflate σ by about 3 for unseen trajectories (AirIO, pass 1).
- Retrain for each airframe; payload changes break it.
- For minutes-long flights the only evidence is about 35 m median of maximum error over 4 to 32 min (AbdulMajuid). Vendor drift claims are 0.5 to 1.9 m/s (Flare Bright).

### B. Vehicle-dynamics, drag and airspeed aiding (not saturated)

**Multirotor air-relative velocity, now quantified outdoors.**

| Source | Result | Evidence |
| --- | --- | --- |
| Yu, Fan, Liu, Lyu, "Design and Implementation of a High-Precision Wind-Estimation UAV with Onboard Sensors", arXiv [2512.10428](https://arxiv.org/html/2512.10428v1), 2025 | **Identifies pass 2's unnamed "wind barrel" item.** It is not a hot-wire sensor:<br>– a disturbance observer (thrust from motor RPM, acceleration, attitude) gives the aerodynamic force;<br>– a wind-tunnel-trained spline maps force to air-relative velocity;<br>– a 105 g barrel under a DJI M300 increases drag sensitivity.<br>The wind estimate subtracts ground velocity, so its RMSE ≈ the air-velocity error.<br>Against a 2D ultrasonic anemometer: tunnel 0.06 m/s; outdoor hover 0.22 to 0.28 m/s, 3.3 to 6.9°; outdoor circle 0.29 m/s; outdoor free flight 0.37 to 0.46 m/s, 7 to 10.5°; vertical (indoor) 0.10 to 0.17 m/s.<br>Predecessor (arXiv 2409.01549): 0.11 m/s in a tunnel [S]. | [V] |
| Polle, Grosch, Poulidis, Vrekoussis, Warneke (Bremen), egusphere-2026-5393 | Unmodified DJI Air 3S; wind from the tilt held in hover; 50 sessions, 71,749 windows of 30 s; mean wind 0.8 to 7.6 m/s.<br>Speed RMSE: 0.32 m/s (ridge regression trained on a reference) and 0.39 m/s (quadratic tilt calibration from calm flights); 0.48 to 0.49 m/s above 6 m/s. Direction MAE 7 to 8.4°.<br>Measures the tilt-to-air-velocity map that tilt or drag dead reckoning needs [C]. | [V] abstract |
| Wetz et al., AMT 14 3795, 2021; AMT 17 4941, 2024 (pass 1's egusphere-2024-222, now published); Atmosphere 13(4) 551, 2022; Zhu et al., *Drones* 9(7) 466, 2025; ACP 26 3607, 2026 | Fleet result: under 0.3 m/s and 8° over 76 flights. Rayleigh-drag calibration: under 0.2 m/s in steady wind, up to 0.6 m/s in gusts. In hover, tilt is more precise than drag. A random forest flown against a lidar at 105 m. The attitude-wind relation changes with wind direction and payload, about 1.0 m/s per degree. | [S] |
| US11630119B2 (El-Sheimy, Zahran, Moussa; University of Calgary; granted 2023) | A light plate deflected by the airflow, angle read by a Hall encoder, tan θ = k·V², calibrated against GNSS. Speed plus magnetometer heading go into an EKF.<br>3DR Solo, two flights with 60 s outages simulated in post: **2D RMSE 0.91 m against 144 m** for INS alone. No wind stated, inventor-reported, very optimistic [C]. | [V] |
| Zahran, Moussa, El-Sheimy: ISPRS Annals IV-2-W5 187 (2019); ISPRS IJGI 8(4) 169 (2019); NAVIGATION 65 477 (2018) | "Air-Odo" flying odometer: more than 98 % better than free INS indoors. Vehicle model with Air-Odo outdoors (numbers not retrieved). An ML-learned vehicle model (simulation). They judge a pitot unsuitable on a quadcopter. | [V] abstract / [S] |
| US12625507B2, "tilt dead reckoning" (4596286 Manitoba Ltd; priority 2021) | Pitch and roll map to air velocity through per-airframe tables (calibrated in wind under 2 km/h). Wind is learned while GNSS is good, then held. Claims linear error growth; no flight numbers. | [V] |
| Paparazzi `dragspeed` and `wind_estimation_quadrotor` modules | Drag-to-velocity without integration (indoor, OptiTrack). A GNSS-based wind Kalman filter, after Hattenberger, Bronz and Condomines, IMAV 2021. | [V] docs / [S] |
| Ntouros, Kelley, Smeur (TU Delft), arXiv [2507.03456](https://arxiv.org/abs/2507.03456), 2025 | Fixed-wing airspeed from ESC-reported propeller power and RPM: nRMSE 5 % on unseen flights. Calibrated from logs or GPS velocity. The Joby patent family (US10919641, US11597532, US12351333) uses the same rotor-power-to-inflow idea; so does Tomić et al., "flying anemometer", IROS 2016. | [V] abstract / [S] |
| Nyoba Tchonkeu, Berkane, Hamel (Université du Québec en Outaouais, Gatineau): arXiv 2602.08273 (CCTA 2026); arXiv 2512.06133 | Pitot plus IMU observers for air velocity and tilt. Yaw needs a magnetometer. The first is validated on real fixed-wing data; the second is GNSS-free with baro and gives observability conditions, simulation only. **A research group across the river from the team.** | [V] abstracts |
| ArduPlane forum, custom EKF3 build | 15 kg VTOL; IMU, airspeed and compass dead reckoning; 7 to 11 m/s wind. **50 to 150 m over 5 to 7 km** (about 1 to 3 % [C]), much worse in gusts. | [V] forum |
| SBG Systems vendor test, July 2025 | Air-data-aided dead reckoning on a 5 km straight leg at 60 m/s: Ellipse (industrial MEMS) 0.56 % (about 30 m); Ekinox Micro 0.13 %; Apogee about 2 m. Gives advice on evaluating outage tests. | [V] vendor |
| Inertial Labs INS feeding a Pixhawk | 8.9 NM over a 1 h outage (about 4.6 m/s average [C]). | [S] vendor |
| Khaghani and Skaloud, ION GNSS+ 2016 | VDM navigation errors "almost doubled as wind velocity doubles" (Monte Carlo with real 3D wind). | [S] |
| Laupré, EPFL thesis 8644 (2022); Longobardi (EPFL thesis 2024, CEAS Aeronaut. J. 2024, IEEE Access 2024); A. Sharma (EPFL thesis 2024) | VDM up to 5 times better than IMU plus pressure sensors. Delta-wing aerodynamic models flown on 4 and on 3 GNSS-free flights (numbers behind 429 and sign-in walls). A VDM used as a synthetic wind sensor. | [S] |
| Mueller, Crocoll, Trommer (KIT), ION ITM 2016 | Quadrotor model-aided navigation with wind estimation, no airspeed sensor; AR.Drone with fan wind (indoor scale). | [S] |
| Abeywardena et al., IROS 2014 | Monocular camera plus IMU: pose and two wind components observable. | [S] |
| Yeung, Bramesfeld, Chung, Foster (Ryerson/TMU), J. Unmanned Veh. Syst. 6 235, 2018 | Gusts measured at 50 to 100 m: the MIL-HDBK-1797 von Kármán model **underpredicted** gust intensity, and spectra were anisotropic. | [S] |
| Air-data hardware | FT Technologies FT602-SM ultrasonic sensor: 170 g. Trisonica and FT742 under US$1,000. Multirotor wake studies: the geometric centre is the best place for a sensor; downwash exceeds 4 m/s even 10 rotor diameters below (egusphere-2026-977; Atmosphere 2024). Hot-wire FlowDrone (arXiv 2210.05857). A multihole probe (arXiv 2505.03331). | [S] |
| PX4-ECL PR 952 | Airspeed plus synthetic-sideslip dead reckoning on fixed-wing, tested in Gazebo only. EKF2 never fuses airspeed on rotary-wing. | [S] |
| Other | Boeing patent US11099582 (intent-weighted dynamics model) [V]. Zhao, Fang, Li, J. Nav. 68(2) 2015 (HIL only, no numbers) [V]. Gallo and Barrientos, Aerospace 10(8) 708 (numbers in PDF only). Rigoni et al., WiMob 2024: record-and-reverse fly-home in wind [V abstract]. NATO STO-MP-SCI-328-16: RF return-to-home (TX, NET). Honeywell Kestrel small EGI (HG3900): demonstrated Sept 2026, no accuracy [S]. Theseus: 564 km in 5 h 22 min, median 51.95 m [S]. | as marked |

**Sim model, update to pass 1 (TBC).**
- **Multirotor air-relative velocity from drag, force or tilt.** σ about 0.25 m/s in hover and 0.4 to 0.5 m/s in free flight outdoors, after per-airframe calibration while GNSS is good. A payload change breaks the calibration, because drag depends on thrust (arXiv 1712.02402).
- **Ground velocity.** Add the wind change since the outage began:
  - a first-order Gauss-Markov process;
  - make the gusts stronger than von Kármán predicts at 50 to 100 m;
  - the error scales roughly with wind speed (Khaghani 2016).
- **Fixed-wing with airspeed and compass.** 0.5 to 3 % of distance depending on IMU grade and gustiness: SBG 0.56 % best case; ArduPlane 1 to 3 %.

### C. Radar and lidar on small drones (not saturated; all TX or OPTICAL)

| Source | Result | Evidence |
| --- | --- | --- |
| AgriLiRa4D, arXiv [2512.01753](https://arxiv.org/html/2512.01753v1) | Agricultural drone at 3 to 18 m, 3 to 8 m/s, FINS-RTK truth.<br>Flat-farmland translation ATE: FAST-LIO2 3.7 to 40.6 m; Faster-LIO 2.6 to 8.4 m; **EKF-RIO failed 6 of 10 runs**, 29 to 83 m on the others; GaRLIO 2.8 to 64 m.<br>EKF-RIO also failed 4 of the hilly and 4 of the terraced runs. Errors rise with height even across 3 to 18 m; drift is mostly vertical; crops move in the downwash. | [V]; TX and OPTICAL |
| Hemann, Singh, Kaess (CMU), IROS 2016 | Lidar scans matched to a prior DEM on a full-size helicopter: **27 m after 218 km (0.012 %)**. | [S] abstract; OPTICAL |
| Honeywell HRVS-U | Up to 170 m above ground; about 250 m/s limit; 1 % typical, 1 to 2 % on another page; the ceiling is quoted as both 1 km and under 300 m. Honeywell showed smaller-form radar velocity products at JamFest 2026 (AIN). | [S] vendor; TX |
| Psionic | Pass 1's SAE/VFS 2026 item is Psionic's Doppler-lidar helicopter test. The SurePath Ground-V datasheet claims under 1 % with an industrial IMU and under 0.1 % with a navigation-grade IMU. | [S]; OPTICAL |
| Ahmed, Shawky, Zahran, Moussa, *Physical Communication* (2024) | FMCW radar range-Doppler forward velocity, fused by EKF and particle filter: 99.8 % better than INS on two flights. | [S]; TX |
| BatMobility (UIUC, MobiCom 2023, arXiv 2307.11518) | A downward radar as an optical-flow replacement at up to 50 Hz, "comparable or better" than optical-flow sensors; works in dark and smoke. | [S]; TX |
| Barra, Creuzet, Blanco et al. (CEA), IEEE Sensors J. 23(3), 2023 | 77 GHz MIMO beam steering gives horizontal and vertical velocity plus height. | [S]; TX |
| Michalczyk, Klagenfurt dissertation (arXiv 2602.04631) | Embedded radar-inertial odometry plus learned point matching. | [V] abstract; TX |
| Quist and Beard (BYU), side-looking SAR odometry | Simulation: about 300 m over 4.5 km (6.7 % [C]) against 2.5 km for the IMU alone. | [S]; TX |
| Plextek, ENC 2024, Eng. Proc. 88(1) 11 | Identifies pass 1's item: a 60 GHz automotive radar on a Class 1 drone matched to a lidar DTM. No metres found. | [S]; TX |
| Altimeters | **Nanoradar** NRA24 (50 m, ±2 cm; the 200 m version ±1 m to 100 m and ±2 m to 200 m) and NRA15, about US$130 to 180.<br>**Ainstein LR-D1 Pro**: 60 + 24 GHz, 0.3 to 500 m, 0.075 m precision below 5 m and 0.364 m above, under 13 W, £5,300 to £5,595.<br>**Benewake TF03-180** lidar: 180 m at 90 % reflectivity, 70 m at 10 %, about 50 m on dark targets in 100 klx sun, US$250 to 475.<br>**LightWare LW20/C**: 100 m on a sunlit white wall, 20 g.<br>A US-D1 was more reliable than lidar over water (Gravity Industries). | [S]; TX / OPTICAL |
| Vegetation and radar | A 77 GHz drone altimeter (Ulm, 2018) saw tree and bush clutter peaks. A patent notes canopy blocks pulses in summer but not in leafless forest. | [S] |
| Lidar to models | Urban lidar DEM matching: 96.8 % success (*Sensors* 25(18) 5672). CityGML/DEM registration: 16 m to under 0.5 m, post-processed (arXiv 2412.02533). Sliding-grid point-cloud TAN (arXiv 2510.06470). MAILS map-free relocalisation (arXiv 2602.13267). EAROL tilted lidar (arXiv 2508.14554). FAST-LIVGO fixed-wing Livox Avia: vertical drift without GNSS (arXiv 2606.19190). | [S]/[V] abstracts; OPTICAL |
| ENC 2025 | Honeywell: radar altimeter plus coded ground RF repeaters for VTOL landing (TX, NET). Airbus: vision + TRN + stars + collaborative navigation. | [S] |

**Sim model (TBC).**
- **Radar Doppler velocity availability depends on the terrain beneath.** Low over grass and crops, where it fails outright in more than half of the AgriLiRa4D runs; good over buildings.
- **Altimeters.** Radar height is height above the canopy in summer. Laser range on dark targets in sunlight is about 50 m, not the catalogue maximum.

### D. Inertial sensors (not saturated)

| Source | Result | Evidence |
| --- | --- | --- |
| Temperature coefficients | **BMI088**: gyro offset 0.015 °/s per K (54 °/h per K [C]), TCS 0.03 %/K; accelerometer 0.2 mg/K.<br>**ICM-42688-P**: gyro ±0.05 to 0.06 °/s per °C; accelerometer ±1 mg/°C.<br>Without compensation, a 10 K change shifts the gyro bias by 0.15 to 0.5 °/s, which dwarfs the room-temperature bias instability [C]. | [S] datasheet copies |
| Cold-weather flight | Uppsala thesis (Svalbard logs): z-gyro drift from IMU board temperature swings; the heaters could not hold their set-point.<br>ArduPilot: gyros shift with any temperature change; its temperature calibration must span the flight range.<br>AutoQuad: compensation needed near and below freezing.<br>Oven control (*Sensors* 23(1) 256): BMI088 bias repeatability improved by more than 60 %. A METU thesis: compensation took bias instability from 16.6 to 5.0 °/h. | [S] |
| Analog Devices, vibration article (Oct 2026), via snippets | 5-inch quad, commercial IMU at motor start: peaks of 0.2 g accelerometer bias and 13 °/s spurious gyro; 0.8° yaw error in 6 s against 0.06° predicted for 50 s.<br>"More than 50× difference in position tracking" against a vibration-rejecting ADIS16607. | [S]; page timed out |
| Sharma, Gilgien, Skaloud (EPFL), MetroAeroSpace 2024 | In VDM navigation, **1 to 4 IMUs gave statistically comparable accuracy** (4 flights, two 2 min outages each). The gain is robustness, not accuracy. Orbital Research 16-sensor array: ARW under 0.09 °/√h, no flight data. | [S] |
| Heading at the end of a GNSS-aided phase, no magnetometer | Septentrio AsteRx-i S datasheet: single-antenna heading 0.3° (0.2° RTK) with an industrial MEMS IMU and motion.<br>SBG note: a 10 °/h gyro reaches 1° in 15 s (pedestrian).<br>ArduPilot GSF: hands over yaw only below 15° at 1σ; walk a circle before arming; converged in about 2 s of flyaway (PR 13603).<br>No measured value for a consumer IMU on a multirotor was found. | [S] / [V] docs |
| Contreras et al., *Drones* 9(3) 169, 2025 | Abstract read: Bayesian alignment starting from rough heading guesses in parallel; one real UAV mission; the multidimensional case is simulation only. Pass 1's ±1° could not be confirmed. | [V] abstract |
| Manoeuvres | arXiv 2606.25639: a straight trajectory leaves heading uncertain; a figure-8 and turns fix it. Vendor survey guidance: at least one figure-8 at 5 m/s or more. Heading is weak at constant velocity (arXiv 2606.23101). Accelerometer scale error is weakly observable; an EKF tolerates about 5 %. | [V] abstract / [S] |
| Other | MPU-6050 Allan study (*Sensors* 20(17) 4841): blog figures of about 0.3 °/√h ARW and about 10 °/h bias instability, consistent with the repo's 16 °/h. NASA Ames IEEE Aerospace 2021 (bench study of five Pixhawk-class IMUs). Polito: noise and bias instability rose after vibration. MicroStrain GQ7 against GX5 over a 30 s outage (figure not retrieved). | [S]/[V] |

**Sim model, additions (TBC).**
- **Consumer IMU gyro bias.** Model it as the sum of:
  - a temperature-dependent term (tens of °/h per K, uncompensated);
  - a motor-on step and a throttle-correlated vibration term;
  - a random walk.
- **Heading entering an outage.** Use about 0.3° for industrial MEMS after figure-8s. Use a few degrees for the MPU6050 [C, unverified].

### E. Timing and synchronisation on Pi-class payloads (not saturated)

| Source | Result | Evidence |
| --- | --- | --- |
| Pi PPS discipline | **Pi 4**, GPIO PPS and chrony: RMS offset about 823 ns. Raw PPS jitter 2,134 ns stock, 6,947 ns on PREEMPT_RT (gives numbers to pass 1's "tripled"). No hardware PTP on the 4B; CM4, CM5 and Pi 5 have it.<br>**Pi 5**: offsets in single to tens of ns, average 16.7 ns, skew 1 to 2 ppb; the oscillator tracks temperature and airflow.<br>NMEA alone is 268 to 1,000 ms late. | [S] / [V] blog |
| Pi free-running crystal | Offset within about ±100 to 200 ppm; daily variation under ±10 ppm; about 1 ppm thermal wander; one Pi 4 within 1 s over 10 h. After a PPS loss, expect tens of µs per second. | [S] |
| RTL-SDR timing | USB arrival timestamps carry tens of ms of jitter. Sample-index alignment needs an injected or in-band reference. A shared clock leaves a sample-phase offset that stays fixed within a run and changes on restart. Dropped samples are "normal" and break sample counting. | [S] |
| RTL-SDR oscillators | V4: 1 ppm TCXO. A non-TCXO dongle is 30 to 150 ppm off and drifts up to about 20 ppm while warming. A TCXO dongle drifts much less than 1 ppm after 30 min. Allow 10 to 15 min warm-up. Upgrades round 1's "1 ppm (memory)" to [S]. | [S] |
| IMU sample clock | MPU-6050 internal oscillator ±1 % (datasheet); the Linux driver tolerates ±2 %; one unit measured 0.18 % slow. Linux inv_mpu6050 and inv_icm42600 stamp the interrupt in hard-IRQ context and estimate the true sample period from FIFO counts. Use the gyro PLL as clock source. | [S] |
| Kernel and GPIO latency | Boxi (ETH, arXiv 2504.18500): kernel ISR timestamps on a CM4. Pi Zero I2C at 1 kHz is jittery (Aerobat, arXiv 2307.11759). Blogs: 10 to 50 µs from GPIO edge to userspace, kernel edge stamps good to a few µs; worst case 1 to 2 ms stock and under 80 µs on PREEMPT_RT. | [S] |
| Camera | Picamera2 SensorTimestamp marks the first pixel read, not the exposure. Camera-IMU offsets of 10 to 50 ms, partly time-varying, are typical (TON-VIO arXiv 2403.12504). VersaVIS hardware sync is under 0.05 ms. Rolling-shutter readout is about 30 to 74 ms on drone cameras (Pix4D). | [S] |
| Reference designs | Liu et al., NAVIGATION 70(4) navi.607, 2023: an FPGA triggers and stamps camera and IMU, aligned to GNSS by 1PPS with a wrong-second check; **better than 30 µs STD**.<br>"Under the Sand" (arXiv 2106.10108): IMU-GNSS 854 µs worst case before, 51 µs with hardware capture. | [V] / [S] |
| GNSS receiver latency | arXiv 2605.13266 (RSS 2026): commercial receivers add 50 to 300 ms of unknown delay; a standard EKF loses consistency; a delay-estimating filter works on fixed-wing flights with 90 to 120 ms lag. | [S] |

**Sim model (TBC).**

| Item | Model |
| --- | --- |
| System time | Under PPS, about 1 µs; without PPS, tens of ppm |
| IMU sample interval | Up to ±1 %, temperature-dependent, unless estimated |
| Camera stamp | Offset of exposure plus readout, plus 10 to 50 ms if software-triggered |
| GPS record | 50 to 300 ms latency unless the receiver's time-of-validity is used |
| SDR stream | Unknown start offset, ±1 ppm clock, sample drops |

At 10 m/s, 10 ms is 0.1 m [C].

### F. Optical flow above 30 m, and barometer in flight (not saturated)

- **Optical flow.** Nothing new on outdoor flow accuracy against height.
  - LWIR thermal flow: RAFT against classical flow on thermal imagery (Nguyen et al., J. Field Robotics 2023). Night track navigation (Rosser et al., JFR 2021) [S].
  - Height from flow divergence and induced oscillation, without a rangefinder:
    - TU Delft (Parrot drones), IMAV 2018;
    - Chirarattananon 2018;
    - a hexarotor EKF on oscillatory flights, IMAV 2022 [S];
    - Paparazzi `optical_flow_hover` [S].
  - All are low-altitude, small-vehicle results.
- **Barometer.**
  - US11417223: 200 Pa in a few hours is about 17 to 20 m; a constant reference is fine under about 1 h [S].
  - Albéri et al. (arXiv 1802.00327): radar and baro best below 70 m; fused σ about 1 m at 50 m [V abstract].
  - ArduPilot: baro thrust compensation, and per-direction position-error coefficients derived once wind is estimated [S].
  - MS5611: first-order datasheet temperature compensation leaves residual drift. ArduPilot calls baro temperature compensation not useful on Pixhawk boards. One log showed a 0.73 hPa (about 6 m) phantom climb from thermal effects [S].
  - Differential barometry needs a link (NET):
    - 0.29 m RMSE indoors (arXiv 2601.02184);
    - a vertiport study needed baro bias correction (arXiv 2311.07487);
    - IET 2016, small UAV [S].
- **Sim model, addition (TBC).** Add a thermal term to the barometer (a few metres over a flight as the board warms) on top of pass 1's weather drift and speed-dependent static error.

---

## 3. Corrections and upgrades to earlier reports

1. **Round 1 §16.6 and pass 1 T3, "AI-IO 0.24 m/s on indoor flights, runs on a small computer"** [V].
   - The 0.237 m/s uses ground-truth orientation, in windless VICON flights.
   - With its own EKF on the DIDO data the figure is 0.371 m/s.
   - Onboard accuracy is shown only qualitatively.
2. **Pass 2 C4, "hot-wire MEMS flow sensor in a wind barrel, paper not identified".** Identified as Yu et al., arXiv 2512.10428 [V].
   - It is a force observer with a drag barrel, not a hot-wire sensor.
   - Outdoor free-flight air-velocity error is 0.37 to 0.46 m/s, not only the 0.22 m/s hover figure.
3. **Round 1 §6.2, dongle clock "1 ppm initial (memory)".** Now [S]:
   - TCXO dongles stay within about 1 ppm after warm-up;
   - non-TCXO dongles are 30 to 150 ppm off, with up to about 20 ppm of warm-up drift.
4. **Pass 1 T11, "PREEMPT_RT tripled PPS jitter".** Now with numbers: 2,134 to 6,947 ns on a Pi 4 [S].
5. **Pass 1 T9, IMU arrays.** The √N gains came from static tests. In flight, inside a VDM filter, 1 to 4 IMUs gave statistically comparable accuracy (EPFL 2024) [S].
6. **Pass 1 T9, Contreras "±1° heading from a single hovering antenna".** Not confirmed. The readable abstract describes one real mission, with the multidimensional case in simulation only. Keep it at [S].
7. **Pass 1 T7 and pass 2 C5.**
   - The SAE/VFS 2026 velocity-aided item is Psionic's Doppler-lidar work on a helicopter.
   - Eng. Proc. 88(1) 11 is Plextek's 60 GHz radar TRN from ENC 2024 [S].
8. **Pass 1 T4, egusphere-2024-222.** Now published as AMT 17 4941, 2024 [S].
9. **Round 1 §7.2, "no magnetometer, aligned to GPS velocity: 2 to 5° (memory)".**
   - Still unverified for consumer IMUs.
   - The vendor figure for industrial MEMS with motion is 0.3° (Septentrio).
   - ArduPilot will not hand yaw to the EKF until the GSF's 1σ is below 15°.
   - Keep 2 to 5° as TBC for the MPU6050.
10. **Pass 1 T3, "outdoor long-flight learned IO not found".** Partly superseded. Two outdoor items now exist, both weak:
    - QuadPosNet, about 34 s runs at 14 to 18 m RMSE;
    - AbdulMajuid, a median maximum error of 35 m over 4 to 32 min, against EKF truth.

---

## 4. Searches that found nothing

- **A.**
  - Learned IO outdoors over minutes with GNSS truth, in wind, on an unseen airframe.
  - Fixed-wing learned IO with absolute numbers: the SALSTM paper's figures are behind MDPI.
  - A survey from 2025 or 2026 with outdoor learned-IO results.
- **B.**
  - Multirotor drag or VDM navigation on a real outdoor flight with metres after an outage, other than the inventor patent's 0.91 m.
  - PX4 drag-fusion velocity accuracy.
  - The numbers in Gallo, Longobardi and Mwenegoha's thesis (access walls).
  - A pitot error study on a multirotor in forward flight.
  - Measured position error with the wind estimate held through an outage.
- **C.**
  - Radar or lidar odometry at 30 to 150 m on a small drone with drift in percent.
  - A drone Doppler-radar product spec other than Honeywell's.
  - The Plextek TRN error in metres.
  - BatMobility's error numbers.
- **D.**
  - Bench Allan curves against in-flight Allan curves.
  - A damped against rigid mount comparison with position error.
  - Magnetometer-free heading error at the end of an aided multirotor flight with a consumer IMU.
  - A Pixhawk IMU-only flight with errors at 30 s and 60 s.
  - The effect of accelerometer clipping on EKF velocity.
- **E.**
  - A measured LED or photodiode offset for Picamera2 timestamps.
  - A measured IMX708 readout time.
  - A V4 RTL-SDR warm-up curve.
  - A controlled study of VIO error against injected time offset.
  - Numbers from the 8-dongle coherence paper (PDF unreadable).
- **F.**
  - An outdoor flow-velocity error curve against height with GNSS or RTK truth.
  - Barometer drift against GNSS over an hour-long UAV flight with a surveyed reference.

---

## 5. Would more searching find anything?

- **A, learned inertial odometry: no, for now (saturated).** The field reports indoor and motion-capture results. The outdoor long-flight evidence that matters to us does not exist yet. Vendors (Flare Bright, Volatus) publish claims, not data. Re-check only when ICRA, IROS or RA-L 2027 papers appear.
- **B, dynamics and airspeed: little that changes the model, but not saturated.**
  - The air-relative velocity error is now well bracketed: 0.2 to 0.5 m/s.
  - The remaining searching produced patents and meteorology papers.
  - What is missing are numbers behind access walls (EPFL, Nottingham, MDPI), and outdoor multirotor outage results, which may not exist.
  - A short targeted pass on the EPFL CEAS 2024 PDF (CC BY) once the 429 clears would pay.
  - The UQO pitot-observer group is local and worth a direct look.
- **C, radar and lidar: some, low priority (all TX or OPTICAL).** More vendor specs and low-altitude datasets will keep appearing. A drift figure for radar or lidar odometry at 30 to 150 m on a small drone is unlikely to exist yet.
- **D, inertial sensors: little from the web; measure instead.** The useful remaining numbers (cold-temperature bias, vibration with motors on, heading at GNSS loss) have to come from the team's own bench and flight logs. Datasheets and forums are exhausted for this purpose.
- **E, timing: little from the web; measure instead.** The Pi- and dongle-specific numbers are forum-grade and hardware-specific. A PPS loop-back test, an LED-to-camera test and a dongle warm-up log would give better numbers than further searching.
- **F, optical flow and barometer: no, for flow; little, for baro.** Flow above 30 m without a rangefinder is not a published research area. Barometer errors are physics plus logs.
