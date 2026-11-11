# Heading, celestial, conventional and exotic navigation: second-round saturation pass

- **Date:** 2026-11-11
- **Scope:** topics 1 to 14 of the brief (heading references, celestial, conventional and legacy aids, exotic cues, Ottawa availability).
- **Baseline read first:** `reports/sources-research-20261111.md` sections 6 to 10, 14, 16 (read-only). Items already there are not repeated unless upgraded or corrected.
- **Budget used:** about 129 WebSearch calls (3 in "extended" mode) and about 35 WebFetch / PDF reads. The search tool never reported its budget as used up.
- **Labels:** [V] read today in the cited primary source (abstract at minimum, full text where stated). [S] search snippet or secondary page only. [M] memory, unverified. [C] my own arithmetic.
- **Flags:** TX = vehicle must transmit; OPTICAL = vehicle emits light; NET = needs a network, operator cooperation or a data link.
- Raw working notes were kept in the session scratchpad and were not saved.

---

## 1. Coverage table

"Saturated" uses the brief's rule (8 consecutive searches with nothing new). That rule was **not met on any topic**. Where returns had dropped to repeats and background, I give a practical judgement, explained in section 5.

| # | Topic | Searches | 8-in-a-row met | Practical judgement | New items | New in last ~10 searches of topic | Blocked by |
|---|---|---|---|---|---|---|---|
| 1 | Low-cost star trackers | 12 | no | practically saturated | 9 | 2 (minor, static) | MDPI 403; Cranfield 403; Bohrium WAF |
| 2 | Celestial on aircraft, daytime SWIR, satellites vs stars | 9 | no | saturated for small drones | 8 | 1 | MDPI 403; paywalled Chinese journals |
| 3 | Sun sensors | 8 | no | practically saturated | 8 | 2 | none |
| 4 | Polarised-skylight compasses | 13 | no | nearly | 15 | 3 | SPIE paywall (SkyPASS paper) |
| 5 | Magnetometer heading on electric multirotors | 9 | no | nearly | 11 | 2 | MDPI 403 |
| 6 | Other heading sources | 8 | no | practically saturated | 9 | 2 | core.ac.uk 403 |
| 7 | Camera bearings to landmarks and lights | 9 | no | nearly | 9 | 2 | AFIT papers paywalled |
| 8 | Radio direction finding | 8 | no | practically saturated | 9 | 1 | none |
| 9 | Passive radar turned around | 7 | no (5 of last 7 empty) | yes: no self-location work found in open literature | 5 adjacent | 1 adjacent | TU Delft repository refused connection |
| 10 | Terrain-referenced navigation | 6 | no | saturated for small drones | 6 | 1 | MDPI 403 (Plextek numbers) |
| 11 | Gravity and magnetic-anomaly | 10 | no | not saturated for magnetic (active 2025-26 arXiv stream); saturated for gravity | 14 | 4 | none |
| 12 | Legacy ground aids, time signals | 11 | no | practically saturated | 13 | 2 | NAV CANADA publishes no retained list |
| 13 | Exotic and bio-inspired | 16 | no | not saturated (open-ended) | 17 | 3 | WARF PDF 403 |
| 14 | Ottawa availability | 4 + 6 fetches | no | partial | 7 | 3 | no observed night-cloud or SQM data found |

---

## 2. Findings per topic

### Topic 1. Star trackers at low cost and low altitude

**Smartphone, Raspberry Pi and micro-drone star tracking.** Marbel, Ben-Moshe and Yozevitch, "Star-Tracker Algorithm for Smartphones and Commercial Micro-Drones", *Sensors* 20(4):1106, 2020 ([EuropePMC full text](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7070887/fullTextXML)) [V full text].
- **Method:** sub-pixel star centroids, triangle hashing against the Yale Bright Star catalogue (magnitude < 5), lost-in-space solve on phones and a Pi.
- **Results:**
  - Phones detect stars in real time: Nexus 5x at 5-10 Hz, Galaxy S6 to S9.
  - The Pi camera v2.1 (IMX219) works at 1 s exposure, ISO 160.
  - DJI Mavic Pro, Mavic 2 and Phantom 4 cameras detect stars in 30 Hz video.
  - Typical orientation error is 0.1-0.3°. The 1/50° figure for calibrated phones is projected, not measured.
  - A Galaxy S7 worked under city light pollution with a full moon.
  - No in-flight drone accuracy is reported.
- **Sim model:** attitude measurement with σ 0.1-0.3° per frame for an uncalibrated wide-FOV consumer camera. Lens distortion adds a bias of up to 0.5-1.5° if the camera is uncalibrated.

**Teague and Chahl, fixed-wing star camera.**
- *Drones* 7(1):52, 2023 (long-exposure strapdown imagery; star-trail correlation corrects INS attitude): yaw error < 0.13° and pitch/roll < 0.06° (3σ) [S]. This is an **in-flight result on a fixed-wing**, which upgrades the first round's "no flight result". No multirotor result exists.
- *Drones* 8:652, 2024: position within 4 km. The paper states that a 1° attitude error corresponds to about 100 km of position error [S]. Three searches found no 2025-26 follow-up.

**Other low-cost trackers (all static):**

| Tracker | Result | Evidence |
| --- | --- | --- |
| SOST (*IEEE Access* 2020) | sub-arcminute, 1-3 solutions/min | [S] |
| TU Delft thesis, Pi camera | 0.025° (1σ) under light pollution | [S] |
| StarberrySense (arXiv 2207.03087) | 30-60 arcsec at 0.05 Hz | [S] |
| arXiv 1808.00221 | target < 6 arcsec ("200 m"), 50 nights, 80-100 stars per image | [V abstract] |
| arXiv 1806.00607 | latitude/longitude 0.5-0.8 arcmin; north to 1 arcmin | [S] |
| PiFinder (hobby) | 0.25-1.5 s exposure, about 1 solve/s | [S] |

**Event cameras.** Chin et al. 2018 (arXiv 1812.02895), EBS-EKF (Kitware and U. Dayton, 2025, up to 1000 Hz) and the e-STURT jitter dataset (arXiv 2505.12588) [S]. All are for spacecraft; none has an atmospheric or drone result.

**Limits.**
- **Body rate:** a large-FOV star sensor tolerates about 3-5 °/s; below 1-1.5 °/s star smear is small [S, secondary].
- **Urban skyglow:** only a synthetic study exists (TU Delft) [S]. At Bortle 3, star identification recall is 71.5%. Under heavy pollution, a fixed catalogue fails, while an adaptive catalogue recovers 27.6% (magnitude 5.0) and 4.5% (magnitude 4.5). No field failure rate by Bortle class was found.
- **Atmosphere:** Jannin and Felicetti (Cranfield, 2024) calibrate atmospheric extinction effects for ground and airborne star tracking [S; page returned 403].
- **Multirotor:** no result found. Searches covered quadcopter, multicopter and hexacopter. An ArduPilot forum "digital sextant" thread has no results [V].

**Sim model, star heading on a small drone (`TBC`):**
- Heading σ 0.05-0.15° at 1-5 Hz when at least 5 stars are identified.
- Available only with a clear sky, at night (sun below -12°) and at body rates under 1-3 °/s. The urban core cuts the star count.
- Failure modes: rare but large misidentifications under skyglow, cloud gaps, moon glare.
- Do not model position from stars on a small drone: one arcminute of vertical error is 1.85 km [C, first round].

### Topic 2. Celestial navigation on aircraft, daytime, satellites against stars

- **Sodern Astradia** [S, press May 2025]:
  - Daytime star tracker working in short-wave infrared (SWIR), accurate to a few arcseconds.
  - Under 3 kg, 176 × 185 × 207 mm, 1 Hz output.
  - Indicative price about EUR 250,000, on sale from June 2025.
  - In late 2020, four flights on a government plane detected and tracked stars.
- **Polaris SkyPASS night mode** ([InsideGNSS, 2023-06-14](https://insidegnss.com/?p=191384)) [V]:
  - Angles-only star fix from 4 matched stars.
  - Position under 3 km at start-up without averaging; down to 100 m with time averaging or a better INS.
  - Needs time to within 1 s; a 10 s error visibly degrades the fix.
  - 100 m position needs angle measurements better than 0.001°.
- **Honeywell, stars plus satellites (resident space objects), on an Embraer E170:** 25 m CEP50, 38% better than its previous test [S]. Flight tests with the HG2800 IMU were planned for 2024; no result found.
- **Daytime SWIR near the ground** [S]:
  - Changsha, 69 m altitude, 1.48 µm: only stars brighter than H ≈ -0.1 were detected at 10:00.
  - US patent 7349804: a 5 cm aperture at sea level reaches H magnitude 1, or magnitude 2 with a 13 e⁻ camera.
  - A Chinese airborne prototype under 1.5 kg saw more than 10 stars, down to H > 2.7, at 20 km.
  - Designs switch to strapdown mode around 20 km.
  - [C] Below a few km, daytime star tracking needs an InGaAs camera with at least a 5 cm aperture and sees only a handful of stars. It is not a small-drone option.
- **Satellites against stars:**
  - Xiong, Zhou and Wei, *Sensors* 22:6992, 2022 [S]: IMU plus a star camera measuring the direction to LEO satellites, fused in a QLEKF filter. Near-space UAV, Cramér-Rao bound and simulation only. Assumes a 10 × 10° field of view and magnitude-8 sensitivity.
  - Patents claim 30 m (daytime stellar imager) and 5 m day / 20 m night at sea [S, unverified claims].
  - The 250 m RMS ground test (Globalstar) is already in the first round.
- All passive.

### Topic 3. Sun sensors and sun cameras

- **Small commercial units:** Solar MEMS nanoSSOC-A60 and D60 [S, reseller]:
  - ±60° field of view, under 0.5° accuracy (3σ), under 0.1° precision, 3.7-6.5 g.
  - EUR 2,500 (A60) and 4,110 (D60).
  - These are spacecraft parts. In the atmosphere, diffuse skylight and ground reflection bias analog sensors. In orbit, reflection from Earth causes up to 20° of error in coarse analog sensors, and a NASA study puts diffuse-light error at 5-10° [S].
  - No terrestrial field test of a photodiode sun sensor under haze or cloud was found.
- **Rover sun sensors:**
  - Furgale, Enright and Barfoot, *IEEE TAES* 2011: absolute heading "within a few degrees"; error falls with longer integration [S].
  - Lambert et al., *JFR* 2012: visual odometry plus sun sensor plus inclinometer over 10 km on Devon Island [S].
  - NASA FIDO rover: heading 3-4 times better than from odometry [S].
- **Sun direction learned from ordinary images:** Sun-BCNN (Peretroukhin et al.) [S]:
  - Median error 12° on KITTI and under 8° on Devon Island.
  - Cut visual-odometry drift by up to 42% in translation and 32% in rotation.
- **Fisheye and multi-camera:**
  - Caltech thesis, 2.4°: already in the first round.
  - Stürzl and Carey 2012: four fisheye cameras with polarisers on a quadcopter give sun azimuth and elevation, even with clouds. Preliminary test only [S].
  - A 2012 fisheye "visual sun compass" prototype [S].
- **Tilt coupling:** *Applied Sciences* 15(9):5060, 2025 [S]:
  - Horizon detection gives roll and pitch to within 0.3°.
  - This improves polarisation and sun heading on a UAV by about 77%.
- **Shadows:**
  - Shadow azimuth is used in photogrammetry (ASPRS 1952, 1986) and by Clements and Zakhor (ICIP 2014) [S].
  - No result was found for a drone finding its own heading from shadows.
- **Sim model:**
  - Heading σ 1-3° from a camera.
  - Tilt coupling ≈ roll/pitch error × tan(sun elevation) [C, geometry].
  - Unavailable when the sun is hidden.
  - Degrades as the sun nears the zenith; Ottawa's summer noon sun is at about 68° [C].

### Topic 4. Polarised-skylight compasses

| Source | Platform / conditions | Result | Evidence |
|---|---|---|---|
| SkyPASS Gen3N (Polaris) | static | 0.1° RMS clear to partly cloudy; ideal sun altitude -4° to 35°; works about 30 min beyond sunrise/sunset; no heading if cloud covers the zenith; fog "severely degraded"; tilt limit 13° (over 15° with full-image algorithms); 4.1 × 3.9 × 3.2 in, 20 oz, < 5 W, 1 Hz; price not published | [V] [InsideGNSS](https://insidegnss.com/?p=191384) |
| Gkanias et al., *Communications Engineering* 2:82, 2023 | 8 UV photodiode analysers + Raspberry Pi on a TurtleBot | 5.89° global / 2.77° local RMSE, clear sky, sun > 10°; thin or broken cloud has little effect; thick cloud degrades; open design | [V] ([PMC10955862](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10955862/fullTextXML)) |
| Dupeyroux et al., IROS 2017 | UV two-pixel compass, hexapod robot | 0.3° clear, 1.9° overcast | [S] |
| BUAA iterative segmentation | cloudy / overcast | mean error 11.7° → 1.4° | [S] |
| Fan et al., *Opt. Eng.* 57(4), 2018 | multicamera, vehicle, obstacle removal | 0.28° static, 0.81° dynamic RMS | [S] |
| Li et al., *Opt. Express* 2021 | filling in sky hidden by buildings | 90.2% of 174 cases improved | [S] |
| Polarised-light compass under foliage, 2017 | vehicle, 0.028% of sky visible | 1.58° RMSE | [S] |
| *Opt. Express* 2022, robust filter | vehicle among trees and buildings | 0.36° vs 1.19° RMSE | [S] |
| *Sensors* 18(1):158, 2018 | quadrotor, polarisation + accelerometer EKF, near high-voltage lines | yaw RMSE 1.25° vs 3.01° for the stock ArduPilot (APM) estimate | [S] |
| Zhao et al., *IEEE Sensors J.* 2024 | drone, dusty days | 0.51° RMSE | [S] |
| Single-point (non-imaging) sensors, review | outdoors, after calibration | ±0.2° to ±0.42° | [S] |
| *Chinese J. Aeronautics* 2022 (10.1016/j.cja.2021.03.005) | night, moonlit sky | heading SD 0.32° clear, 0.47° cloudy | [S] |
| Moon phase (biology) | | quarter moon gives 1/3 and crescent 1/5 of the full-moon polarisation signal | [S] |

- **UV versus visible:** UV degrades less under overcast. A French group reports that visible-band compasses are corrupted on overcast days [S].
- **Commercial and open hardware:**
  - SkyPASS is the only commercial unit with published numbers, and it has no published price.
  - Open designs: the Gkanias components are listed in the paper, and the IMAV 2024 TU Delft dataset is open.
  - Sony IMX250MZR polarisation sensors reach sub-percent polarimetric accuracy after calibration (arXiv 2405.07864) [S].
- **Review not read:** a 2026 *IEEE TIM* review of solar polarisation navigation (BUAA and Renmin) gives sensor advice by weather. Its tables were not read [S].
- **Sim model (proposal):**
  - Heading σ 0.3-1° in flight under clear sky or thin cloud; 1.5-5° under broken or mostly cloudy sky.
  - Overcast zenith: no output (SkyPASS behaviour), or 2-12° with UV sensors and special algorithms.
  - Tilt coupling unless roll and pitch are fed in.
  - Availability set by sun altitude (best below about 35°), into twilight until about 30 min after sunset, and at night only with at least a quarter moon.

### Topic 5. Magnetometer heading on small electric multirotors

- **Interference source and scaling:**
  - ArduPilot: interference is linear with current drawn, so its motor compensation (CompassMot) only works well with a battery current monitor [S].
  - DIY studies use throttle² as a stand-in for current; uncompensated yaw error reaches 10° [S].
  - Forum CompassMot results range from 1% to 58%; about 100% is called "bad" [S].
- **Mast length:** one ArduPilot user's long-range quad [V forum]:
  - At 50 mm from the power wires, interference was off-scale.
  - A 120 mm boom brought it down to 32% at 75% throttle.
- **Field strengths:**
  - A 5 kg hexarotor peaked at 350 nT at 0.4 m [S].
  - Fixed-wing sources gave 30-100 nT at 0.38-0.55 m [S].
  - A mapping study measured 21.4-574.2 nT (Tuck 2018) [S].
  - [C] Taking Ottawa's horizontal field as about 18,500 nT (`TBC`, from WMM [M]): 350 nT perpendicular to the field gives 1.1° of heading error, and 574 nT gives 1.8°.
- **Calibration residuals:**
  - *Measurement + Control* 2020 (Levenberg-Marquardt calibration, multirotor): static yaw error 1.2° → 0.4° [S].
  - IEEE TIE 2019: gyro-aided EKF calibration cut yaw error in flight by about two-thirds [S].
  - *Sensors* 21(11):3582, 2021 (two quads, carrier-phase GNSS between drones plus vision): calibrated heading under 1°, against "several degrees" for DJI's onboard solution [S].
  - Six Pixhawk magnetometers in a Helmholtz cage varied 25-116 mG peak-to-peak [S].
  - Magnetic interference on micro air vehicles reaches about 10° (*Sensors* 20(2):538) [S].
  - Raw indoor heading errors reach tens of degrees at disturbance peaks (AMO-HEAD, arXiv 2510.10979) [S].
- **Without a magnetometer:**
  - PX4's EKF-GSF estimates yaw from GNSS velocity alone; it needs a change in horizontal velocity larger than the velocity noise [S].
  - Septentrio: direction of travel over the ground does not give heading on a multirotor [S].
  - A micro coaxial drone reached 1.01° after takeoff (*Drones* 2025) [S].
- **Near steel and power lines:** anecdotes only. A handheld compass deviated by up to 140° near high-voltage wires on a bridge [S].
- **Sim model (proposal):**
  - Constant bias from residual calibration error, N(0, 0.5-1°).
  - Current-proportional term k × I. Full throttle gives 0.5-2° with a 10-15 cm mast and 3-10° without one.
  - Slow random walk.
  - Rare large outliers near steel and power lines.
  - Flag that the bias cannot be observed without a second heading source.

### Topic 6. Other heading sources

- **Two GNSS antennas** (calibration only; needs real GNSS):
  - Würzburg: a 50 × 50 cm array gave mean heading error under 1° in UAV flight [S].
  - 92 cm baseline with geodetic antennas: 0.2° [S].
  - u-blox quotes 0.1-1.0° depending on baseline [S].
  - ArduSimple quotes 0.14° at 1 m and 0.03° at 5 m (vendor) [S].
  - A 27 cm setup never reached a fixed solution (forum) [S].
  - UAV Navigation: 0.3° RMS in a vehicle test [S].
- **MEMS north-finding from Earth rotation (gyrocompassing), static only:**
  - Carouseling: 0.229° in 6 min [S].
  - Four-position rotation ("maytagging"): 0.5° in 3 min [S].
  - Virtual maytagging: 0.204° in 5 min at 28.2° latitude (*Microsystems & Nanoengineering* 2023) [S].
  - Rotation modulation: 0.66° static, 1° dynamic repeatability (*Sensors* 2017) [S].
  - Kongsberg and Silicon Sensing announced a tactical-grade north-seeking MEMS gyro (SGH03) in March 2026, with no published numbers [S].
  - [C] At Ottawa (45.4° N), the horizontal Earth rate is 15.04 × cos 45.4° = 10.6 °/h. Heading error ≈ residual gyro bias ÷ 10.6, in radians. Static results:

    | IMU | Gyro bias | Heading error |
    | --- | --- | --- |
    | BMI088 | 2 °/h | ≈ 11° |
    | Epson M-G370 | 0.8 °/h | ≈ 4.3° |
    | STIM300 | 0.3 °/h | ≈ 1.6° |
    | HG4930 | 0.25 °/h | ≈ 1.4° |

    0.1° needs about 0.02 °/h of residual bias. Rotation schemes are therefore mandatory, and gyrocompassing in flight is ruled out for small drones.
- **Horizon-based attitude:**
  - Dusha et al., *JFR* 2011: 0.42° pitch and 0.71° roll in UAV flight [S].
  - Carrio et al. 2018: thermal horizon under 1.7° RMS at 48 Hz [S].
  - Gives roll and pitch only, which is exactly what sun and polarisation heading need for tilt compensation.
- **Heading from imagery:** Bearing-UAV (arXiv 2603.22153) regresses position and heading from satellite tiles. Its numbers were not retrieved [S].
- **Heading from radio direction of arrival:**
  - Narrowband direction finding gives two of the three angles; the third needs another sensor (Lafayette, *TAES* 2019) [S].
  - No paper was found on yaw from cellular base-station angle of arrival with known sites.
  - 5G NR angle of arrival on USRP hardware shows that array calibration dominates the error (*IEEE TIM* 2025) [S].

### Topic 7. Camera bearings to surveyed landmarks, lit towers, city lights

- **Matching city lights like a star field (AFIT):**
  - Shockley and Bettinger: IEEE MetroAeroSpace 2021, AIAA 2020, patent US 11,873,123 (Jan 2024) [S].
  - Matches camera images of city lights to VIIRS Black Marble night imagery (500 m pixels).
  - The patent's example is an aircraft at night imaging every 15 min.
  - No accuracy figure retrieved; the work is spacecraft-oriented.
- **Streetlight maps for ground robots:** Night-Rider (arXiv 2402.00330) and Night-Voyager (arXiv 2502.20054) associate camera detections with a 3D streetlight map in an invariant EKF [S]. No UAV equivalent was found.
- **Night thermal:**
  - *IJAEOG*, Dec 2024: mean absolute error under 7 m at night against satellite imagery [S].
  - Lights Out (arXiv 2604.26201) is already in the first round.
- **Runway and approach lights:**
  - 2018: approach and PAPI lights detected and mapped to runway coordinates [S].
  - BYU thesis 2024: GPS-denied eVTOL landing on modulated infrared lights, flight-tested [S]. The lights are placed by the operator (NET).
  - *Aerospace* 2022: night runway detection, simulation only, 0.675° rotation error [S].
- **Bearings to landmarks:**
  - Karpenko et al., *Sensors* 15(12):29768, 2015: simulation only [S].
  - ISPRS Archives XLIX-B1-2026-55: UAV images matched to orthophoto and DSM, then position by resection; metre-level [S].
  - No flight result was found for fixing position from point landmarks such as towers or obstruction lights.
- **Landmark databases:**
  - FAA Digital Obstacle File: 56-day update cycle; horizontal accuracy codes from ±20 ft to ±1 NM; lighting flagged as lit, unlit or unknown; little coverage of Canada [S].
  - A Delaware study cut mean horizontal uncertainty from 206 ft to 56 ft by correlation (*Sensors* 24(5):1686) [S].
  - Canada: no public obstacle or lit-tower registry found. New obstacles go through Transport Canada's Aeronautical Assessment Form. NAV CANADA sells obstacle data, about $24k a year according to an internal Transport Canada wiki (unverified) [S].
  - Obstruction beacons flash 20-40 times a minute, which can tag them in video. Many LED obstruction lights fall outside night-vision-goggle bands [S].
  - ISED's transmitter-site data, already used for towers, is the practical list [M].
- **Sim model (proposal):**
  - Bearing σ 0.05-0.2° from a calibrated camera.
  - The vehicle's heading error is shared by all bearings.
  - Landmark position error of 5-60 m (Digital Obstacle File class) as a bias per landmark.
  - Occasional misassociation outliers.

### Topic 8. Radio direction finding

- **Measured and simulated bearing errors:**
  - Pseudo-Doppler in multipath (5.8 GHz patent simulation): maximum error 8° with no echo; 9°, 26° and 24° with one half-amplitude echo at 0°, 90° and 180° phase [S].
  - Perera et al., arXiv 2003.00386: a multirotor circles while turning a directional antenna and takes bearings from signal strength; radio tags located to 5 m [S].
  - JHU APL Tech Digest 32-03 (Bamberger): pseudo-Doppler on small drones was flight-demonstrated, with no bearing error published [S].
  - University College Cork: a UAV with an SDR and a four-dipole array located a handset to 100 m from more than 1.5 km away [S].
  - Watson-Watt: vendors quote 2-10°, against 1-3° for interferometers. An AFRL small-drone DF project published no error figure [S].
  - KrakenSDR docs: bearings are off by "several degrees", mainly from multipath [S].
- **Airframe effects:** the drone's frame distorts antenna patterns; one quadrotor pattern was measured to 3.6 dB RMS (arXiv 2604.02827) [S].
- **One emitter, own manoeuvres:**
  - Bearings from a single sensor cannot fix position until the vehicle manoeuvres (NUSC report, DTIC ADA102073) [S].
  - Adding Doppler to the bearing removes the need to manoeuvre (patent US 5406291) [S].
  - Flight paths can be optimised by Fisher information (Xiao et al., arXiv 2606.09188) [S].
- **ADF and NDB:** accuracy is "variable", with sky-wave errors at night and twilight and refraction at coastlines [S]. ICAO ±5° is from memory [M].
- **[C] Error model:**
  - Cross-range σ = R × σθ. Example: 10 km at 2° gives 349 m.
  - Range from one emitter along a perpendicular baseline L: σR ≈ R² × σθ / L. Example: 10 km, 2°, L = 1 km gives 3.5 km.
  - Heading error acts as a common bias on all bearings.

### Topic 9. Passive radar turned around

- **No open-literature paper uses passive radar for the receiver's own position.** Seven differently worded searches found only adjacent work.
- **Adjacent work:**
  - Channel-SLAM (DLR, Gentner et al., *IEEE TWC* 2016): treats each reflected path as a virtual transmitter, so position works from a single physical transmitter. Pedestrian and outdoor tests [S].
  - DLR (Becker, Fiebig and Schalk, 2021) solves the inverse problem [V first pages]. With known transmitter and receiver positions and a 3D building model, it locates the reflecting surfaces from each reflection's delay and Doppler.
  - Airborne passive radar imaging (SAR) from DVB-T TV transmitters exists: PASSAT (Birmingham), Gromek et al., Fang et al. (*TGRS* 2020), and a UAV receiver (arXiv 2010.00179) [S]. Such images could in principle be matched to maps, but no navigation result was found.
  - On a moving platform, ground echoes spread in Doppler according to the vehicle's own velocity. No paper uses this to estimate own velocity [S].
- **Not read:** a TU Delft survey, "Passive RF Self-Localization of UAVs Using Signals of Opportunity" (record dated 2026; connection refused) [S].
- **Sim value:** low. A model that matches echo delay and Doppler to a map would be a research project, not a model of known performance.

### Topic 10. Terrain-referenced navigation

- **Small drone:** Plextek, ENC 2024 (*Eng. Proc.* 88(1):11) [S]. A class-1 drone carries a 60 GHz automotive radar. Its ground profile is matched in a particle filter against a UK lidar terrain model (1 m horizontal, 15 cm vertical). The paper calls the result "accurate"; the metre figures were not retrieved. **TX.**
- **Classic limits:**
  - The SITAN terrain-matching filter diverges if the starting uncertainty exceeds several hundred metres [S].
  - Parallel SITAN example: a 2,100 m CEP covered by 57 filters spaced 525 m apart [S].
  - Linköping 2009 (Yamaha RMax helicopter): radar altimeter plus imagery; at low speed the terrain under the track varies too little to match [S].
- **Urban:** Hebel, Arens and Stilla (TUM and Fraunhofer) match lidar-detected planes to city models for helicopters and UAVs [S]. A 2019 study fuses UAS laser ranges to building facades in an iterated EKF, in simulation [S]. **OPTICAL.**
- **Barometer only:** a barometer gives altitude, not height above the ground, so it cannot sense terrain on its own. No drone result was found [C reasoning].
- **Seabed analogue:**
  - HUGIN AUV stayed within about 5 m over 5 h [S].
  - A Southern Ocean AUV held errors to hundreds of metres, against 40 km of dead-reckoning drift, with a 50 m map [S].
- **Ottawa terrain:** a flat lowland, with the Gatineau Hills to the north-west. NRCan's HRDEM 1 m lidar terrain and surface models cover 244 of Canada's 250 largest cities; Ottawa coverage was not explicitly confirmed [S].

### Topic 11. Gravity and magnetic-anomaly navigation

- **Best magnetic-anomaly (MagNav) result:** Muradoglu et al. (Q-CTRL), arXiv 2504.08167, Apr 2025 [V abstract]:
  - Airborne trials up to 19,000 ft on fixed-wing drones and in an airliner's avionics bay, with quantum magnetometers inside and outside the airframe.
  - Best final error 22 m, or 0.006% of distance flown.
  - At least 11 times better than the INS in airborne trials; 7 times on a ground vehicle.
  - Learns the aircraft's magnetic model online, without calibration manoeuvres.
- **New and Ottawa-relevant: public MagNav Challenge data** ([Zenodo 10.5281/zenodo.12723700](https://zenodo.org/records/12723700)) [V record page; S for flight details]:
  - Flown by Sander Geophysics in a Cessna 208B near Ottawa, over Renfrew, Eastern Ontario and a test area north of Arnprior.
  - 400-800 m altitude; 5 caesium scalar and 4 fluxgate magnetometers; flights in 2020 and 2021; 1.2 GB of HDF5.
  - The licence text says public domain (17 USC 105). A separate `DATA_SHARING_AGREEMENT.md` was not read. **Owner go-ahead needed before any download.**
- **Recent algorithm papers:**
  - O'Leary et al., arXiv 2610.38047, 27 Oct 2026 [V abstract]: map matching by forward-backward inference over a factor graph. Simulated INS and scalar magnetometer over the Renfrew_395 map gave a median error of 32.7 m, against 362 m of inertial drift, and 43% better than an EKF or particle filter. The entropy of the position estimate flags 94% of segments with error over 3 map cells, at a 10% false-alarm rate. A truth-free ambiguity measure like this is directly useful for protection levels.
  - Hager et al., arXiv 2603.08265, Mar 2026 [V abstract]: online calibration (Tolles-Lawson physics model plus a neural network) inside an EKF, needing no calibration flight. Tested on the MagNav data.
  - PG-TLNet, *Drones* 10(4):252, 2026, for UAV swarms [S]; arXiv 2608.26525, compensation without a map [S]; UAV compensation with GA-BP networks and Transformers, 2025 [S].
- **Space weather:** Srinivasan and Nielsen, arXiv 2510.15113 [V abstract]. Time-varying field disturbance estimated from a distant reference station to under 10 nT RMS, median under 5 nT. Daily variation is as large as the anomalies, so a base station or model term is needed (NET if live).
- **Small UAVs:**
  - No position result for magnetic navigation on a small drone was found.
  - UAV magnetic surveys hang the sensor up to 9 m below or mount it on long booms to reach survey-grade noise. A suspended sensor's swing adds under 1-5 nT [S].
  - NV-diamond magnetometers sized for UAVs: Zhejiang's integrated nT-level unit, 13 × 26 cm (arXiv 2508.03237); SBQuantum's fixed-wing drone campaign (SPIE 13202, 2024) [S].
  - A wearable optically pumped magnetometer reached 2.24 m radial error over more than 500 m of walking with dead reckoning (arXiv 2606.24612) [V abstract].
- **Maps for Ottawa:**
  - National 200 m grid, 2005 [S].
  - Eastern Ontario survey, 2014: 400 m line spacing over 12,515 km² east of 76.51° W to the Quebec border, covering Ottawa [S].
  - Ontario Geological Survey Renfrew surveys, 2014 [S].
- **Gravity:**
  - Marine gravity matching: 1-3 nmi with a 1′ map and a 1-2 mGal gravimeter [S].
  - Q-CTRL vessel trial: error held within 1 nmi over 83 km, more than 10 times better than a navigation-grade INS (press) [S].
  - Strapdown quantum gravimeter: 0.67 mGal residual over 83 km (arXiv 2608.25563) [S].
  - Cold-atom gravimetry has flown on an ATR-42 (GIRAFE, 2019) [S]. DTU/ONERA flights in Greenland (2023) have published no results.
  - No accuracy for gravity navigation on aircraft was found. Not for small drones.
- **Sim model (larger aircraft only):**
  - Scalar anomaly measured against the map.
  - Map error of 5-20 nT (survey-dependent), spatially correlated.
  - Platform residual of 1-10 nT after compensation.
  - Daily variation of 10-50 nT unless corrected.
  - Position estimate can have several candidate answers.
  - Fails over magnetically flat ground: compare Ottawa's lowland with the Canadian Shield to the north-west.

### Topic 12. Legacy and remaining ground aids, time signals

- **VOR received with an SDR in flight (new):** Marzioli et al., 2021 preprint ([PDF](https://iris.uniroma1.it/bitstream/11573/1448408/4/Marzioli_preprint_Experimental_2021.pdf)) [V full text]. The STRATONAV experiment flew an SDRplay RSP1 and a commercial VOR receiver on the BEXUS 22 balloon.
  - Above 18 km, SDR mean radial errors were 0.76-1.84°, with SD 0.57-1.21°, for stations 119-353 km away.
  - Commercial receiver: 0.26-2.16° mean, SD up to 9°.
  - Distant, low-elevation stations: 10-94° errors.
  - The commercial receiver's radial shifted 5° when heated by about 50 °C, from oscillator drift.
  - Standard: modern VOR ±1.4°; original ±4°.
- **Hobby RTL-SDR decoders:** one reported ±3° at three sites; another showed a persistent -30° offset [S].
- **Ottawa VOR (YOW):**
  - A Canada Flight Supplement extract valid 2 Oct to 27 Nov 2025 lists **YOW as "DME"** on 114.6 MHz. A Feb 2023 directory listed 114.6 MHz, channel 93 [S].
  - This suggests the VOR may have been removed and the DME kept. `TBC` from the current CFS.
  - NAV CANADA keeps a VOR only as the recovery aid where radar coverage is insufficient (NAVAIDs Modernization FAQ) [S]. It publishes no list of retained stations.
- **Passive DME:**
  - Still no experiment found.
  - Stanford's DME pseudolite (Lo, ENC 2020; ION ITM 2016) modulates existing pulse pairs and needs synchronised transponders [S].
  - LDACS ranging beat DME in DLR flights [S]. DME supports 0.5 NM total system error (Vitan) [S].
- **eLoran:**
  - UK: Anthorn is timing only. A six-site network should reach full capability by 2030. The UK MOD started a two-year programme, "Urgent Compass", in May 2026 [S].
  - South Korea reached initial operational capability in 2023 [S].
  - US: the Wildwood test signal ran 2015-2016. A 2025 forum claim of "3 western US sites" is unverified [S].
  - Canada: nothing found. NautelNav (Nova Scotia) has a deployable eLoran concept [S].
- **Navy VLF:** stations NLK and NML drift 0.072-0.079 °/s in phase and vary in power by up to 7% (AVID, 2025) [S]. Positioning from their phase therefore needs a reference receiver (NET) [C].
- **WWVB:** its phase modulation jumps about 0.3 µs from second to second, and the carrier time shifts by several µs over days [S].
- **Lightning (sferics):**
  - Kovář, Puričer and Mikeš, *J. Navigation* 2024 [S abstract]: positioning by time of arrival using historical WWLLN lightning data, 10 s windows, over 80% availability, median geometry factor (GDOP) about 1 except near the south pole.
  - Lightning networks locate strikes to 1-4 km (3 sensors), up to about 9 km [S].
  - Needs strikes located by the network in real time (NET).

### Topic 13. Exotic and bio-inspired cues

- **Bee-Nav**, TU Delft MAVLab, *Nature* 653:1039-1046, 13 May 2026 [S, MAVLab page and press]:
  - After a learning flight, the drone flies out by path integration and returns using a 42 kB visual homing network.
  - Returned within 0.5 m of home in 100% of 30-110 m flights and 70% of 200-600 m flights, in wind.
  - Return-home only; no absolute position.
- **Edinburgh flying robot:** path-integration homing drifts 1.5 m per 100 m outdoors [S].
- **Muons:**
  - MuWNS-V, *Sci. Rep.* 2024: 3.9 cm RMS with a prototype [S]. muPS (vector method), *Sci. Rep.* 2023 [S]. The earlier MuWNS gave 2-25 m with up to 100 m range underground [S].
  - All need reference detectors nearby (NET).
  - CRoNS (arXiv 2406.18608) uses cosmic-ray air-shower muons with a sensor network and central AI; no accuracy given [V abstract]. NET.
- **Radio emission from the sky:**
  - WARF patent application US 2025/0044095 A1 (Hanson) [S]. An interferometric antenna array images the galactic plane and the sun, then matches a template for heading and location, through cloud, day and night.
  - A historical Navy/Collins radio sextant tracked the sun or moon through cloud at 8 mm wavelength [S].
  - Worth an open question; no accuracy known.
- **Cold-atom inertial sensors:**
  - QinetiQ RJ100 flights (May 2024) carried Infleqtion's Tiqker optical clock and parts of a quantum inertial sensor; no drift numbers [S].
  - An atom accelerometer on an aircraft reached 2.3e-4 g in a single shot [S].
- **Clocks:** Microchip SA65 chip-scale atomic clock: aging under 9e-10 per month, temperature sensitivity ±3e-10 over -40 to +80 °C [S datasheet]. [C] 1e-10 is 8.64 µs/day, so holdover drift is set by the remaining frequency offset: 1e-11 gives 0.9 µs/day and 3e-10 gives 26 µs/day.
- **Quantum magnetometers:** see topic 11.
- **Acoustic:** every published drone acoustic method uses microphone arrays on the ground (NET) [S]. No self-localisation from ambient sound or infrasound was found.
- **Magnetic navigation without a map (bio-inspired):** reinforcement learning on field gradients (arXiv 2410.15837), simulation only. It needs the field's intensity and inclination gradients to point in different directions [S].
- **Pressure-pattern navigation:** no modern work. Barometer plus weather-model altitude has been used for GNSS integrity (Simonetti and Crespillo, NAVIGATION 2024) [S].
- **Position from skylight polarisation:** *Applied Sciences* 15(13):7287, 2025, simulation with a true-north instrument; errors mostly under 14 m [S]. Implausible without a very precise vertical (see topic 1) [C].

### Topic 14. Ottawa-specific availability

**Observed heavy overcast** (80-100% cloud cover), from ECCC Canadian Climate Normals 1981-2010 via currentresults.com ([annual](https://www.currentresults.com/Weather/Canada/Cities/cloud-annual-average.php)) [V page; S underlying]:

| Period | Heavy-overcast hours | Share of hours [C] | Days with no sun |
|---|---|---|---|
| Year | 4,708 | 53.7% | 65 |
| January | 458 | 61.6% | 8 |
| July | 314 | 42.2% | 0 |
| September | 328 | 45.6% | 2 |
| December | 488 | 65.6% | 13 |

- **Sunshine:** 2,083.7 h a year at the airport (1981-2010), 82.6 h in December and 279.0 h in July [S, Wikipedia table]. [C] About 47% of possible daylight hours.
- **Modelled cloud:**
  - NASA POWER: 58-73% monthly, cloudiest in November and December [S].
  - WeatherSpark: January is overcast or mostly cloudy 69% of the time [S].
  - The clearer season runs from about 24 May to 26 October [S].
- **Not found:** observed night-time cloud cover, and any SQM sky-brightness measurement for Ottawa. Sky-quality meters also under-report skyglow from LED lighting [S].
- **Magnetic maps:** Eastern Ontario 2014 survey at 400 m line spacing; MagNav Challenge flights around Renfrew and Eastern Ontario (topic 11).
- **Terrain:** flat lowland; HRDEM lidar coverage likely but not confirmed [S].
- **[C] Availability for sky sensors (proposal, `TBC`):**
  - Hours that are not heavily overcast: about 34-38% in December and January, about 54-58% in July to September.
  - Star tracking needs night and clear sky, so plan on well below that. The first round's forecast climatology gave 14-22% in December and January and 43-50% in September.

---

## 3. Corrections to the first-round report

1. **8.1 and 7.2, "night star camera … no flight result":** a fixed-wing in-flight result exists. Teague and Chahl, *Drones* 7(1):52, 2023, report under 0.13° yaw and under 0.06° pitch/roll (3σ) [S]. Still nothing on a multirotor.
2. **7.2, "polarised-skylight compass: no heading under overcast":**
   - True for SkyPASS, which gives no output when cloud covers the zenith [V].
   - UV and segmentation methods report 1.4-1.9° under overcast [S].
   - SkyPASS's 0.1° is static, with tilt under 13°. Its ideal sun altitude is -4° to 35°, it works about 30 min into twilight, and it weighs 20 oz at under 5 W [V].
3. **7.2, "magnetometer on a mast 1-3° (memory)":**
   - Now evidenced: under 1° calibrated against an external reference; 0.4° static after calibration; DJI's onboard solution "several degrees"; up to about 10° uncompensated [S].
   - 350-574 nT of interference is about 1.1-1.8° at Ottawa [C].
   - A 120 mm boom still showed 32% interference at 75% throttle [V forum].
4. **7.2, "two GPS antennas about 0.5° (memory)":** a 50 cm array gave under 1° mean in UAV flight; about 1 m gives 0.1-0.2° (vendor); baselines under 30 cm may never fix [S].
5. **7.2, "gyrocompassing not usable in flight":** confirmed and quantified [C]. At Ottawa, 0.1° needs about 0.02 °/h of residual bias. Even static, a BMI088 gives about 11° and an HG4930 about 1.4°.
6. **8.2, magnetic-anomaly "sim only for us":**
   - Stands for the small quad.
   - A sim can now run over the **real Ottawa-area map** using the public MagNav Challenge data, with an owner go-ahead.
   - arXiv 2610.38047 already reports a 32.7 m median error on the Renfrew map in simulation.
7. **8.2, VOR, "YOW VOR/DME on no removal list":** a late-2025 CFS extract lists YOW as **DME** on 114.6 MHz [S]. The VOR may be gone. Keep the `uc02-yow-approach-vor` scenarios `TBC` until the current CFS is checked.
8. **8.2, "Navy VLF kilometre-class (memory)":** the stations drift in phase (about 0.07 °/s) and in power (up to 7%) [S]. Phase positioning therefore needs a reference receiver (NET).
9. **8.3, "chip-scale atomic clock about a microsecond per day (memory)":** the datasheet gives 0.9-26 µs/day, depending on the remaining frequency offset and on temperature [C from S].
10. **8.1, "Ottawa clear about 32% of day hours (forecast climatology)":** add the observed normals. Heavy overcast covers 54% of all hours (62-66% in December and January, 42-46% in July to September), and 65 days a year have no sunshine [V page, S underlying]. The two sources are consistent.
11. **16.5, "camera fixes from obstruction lights or city lights: nothing published":** still nothing for drones. Adjacent work exists: AFIT's patent on matching city lights (2024) and streetlight-map localisation for ground robots (2024-25) [S].
12. **8.1, "large-aircraft systems … daytime results above 10 km":**
    - Consistent.
    - Add Sodern Astradia's indicative price of EUR 250k [S].
    - Add that at sea level, a 5 cm aperture detects only stars of about H magnitude 1-2 or brighter by day [S].

---

## 4. Searches that found nothing

**Celestial and sky sensors**
- A star tracker flown on any multirotor, with an accuracy figure.
- A field failure rate for star identification by Bortle class.
- A field test of a photodiode sun sensor on the ground under haze or cloud.
- A drone finding its own heading from shadows.
- SkyPASS figures under overcast, or its price; any other commercial polarisation compass with a price.
- A moonlit polarisation compass tested on a moving vehicle or UAV.

**Magnetic and inertial heading**
- Quadrotor magnetometer heading error measured in flight against a two-antenna GNSS reference.
- Measured compass deviation near steel structures.
- Gyrocompassing in flight on any small platform.

**Radio heading and direction finding**
- Heading from the angle of arrival of cellular base stations with known sites.
- Watson-Watt or Adcock bearing accuracy measured on a small UAV.

**Landmarks and lights**
- A UAV fixing its position from point landmarks (towers, obstruction lights), with a flight result.
- A drone localising itself from streetlights or city lights.
- A public Canadian registry of obstacles or lit towers.

**Other position methods**
- Any use of passive radar for the receiver's own position.
- Metre figures for the Plextek drone radar terrain navigation.
- Barometer-only terrain matching on a drone.
- A position result for magnetic-anomaly navigation on a small drone.
- An accuracy figure for gravity navigation on aircraft.

**Legacy aids and time**
- A passive DME experiment, any year.
- NAV CANADA's list of retained VORs.
- Any Canadian eLoran plan; the current status of the US Wildwood transmitter.
- A 2023-26 result for positioning from VLF phase.
- WWVB timing measurements newer than 2016.

**Exotic**
- Self-localisation from ambient sound or infrasound.
- Product data for a hemispherical resonator gyro suited to small drones.

**Ottawa**
- Observed night-time cloud cover.
- SQM sky-brightness measurements.

---

## 5. Judgement: would more searching find anything?

1. **Star trackers (low).** Three phrasings for a multirotor result returned only the UniSA fixed-wing work. Static low-cost results are plentiful and agree (arcseconds to 0.3°).
2. **Celestial on aircraft (low for small drones).** The daytime-SWIR physics (aperture, H-band magnitude) agrees across Chinese, NASA and patent sources. Vendors have not published flight numbers.
3. **Sun sensors (low).** Searches returned rover and spacecraft work already logged. The one gap, a ground-based photodiode sensor under haze, looks genuinely unpublished.
4. **Polarisation (medium).** A large Chinese literature (*Optics Express*, *IEEE Sensors*, Chinese journals) keeps producing 0.3-1.5° vehicle and drone results. More rows, probably no change to the model. The unread 2026 *IEEE TIM* review is the best next read.
5. **Magnetometer (low to medium).** The numbers are thin and mostly from forums. Reading *Sensors* 2021 and IEEE TIE 2019 in full would add more than further searches.
6. **Other heading sources (low).** Each is either physics-limited (gyrocompassing) or needs GNSS (two antennas). The SGH03 gyro datasheet is worth watching.
7. **Landmarks and lights (medium).** Nine searches found nothing on drones fixing position from point lights. The open literature is probably genuinely empty, which makes the idea novel but unvalidated.
8. **Direction finding (low).** Classical and well covered. Flight bearing statistics on small drones appear unpublished, likely because the work is defence.
9. **Passive radar turned around (low).** Only adjacent work in seven searches. The TU Delft survey is the one remaining check.
10. **Terrain navigation (low for small drones).** Sensors that emit and flat terrain dominate. Plextek is the only small-drone item.
11. **Magnetic and gravity (medium to high for magnetic).** A few searches surfaced four 2025-26 arXiv MagNav papers, two of them using the Ottawa-area data. The stream is active and more would surface. Gravity is saturated for our purposes.
12. **Legacy aids (low).** YOW's status needs the current Canada Flight Supplement, which is a document check, not a search. eLoran, VLF and WWVB searches returned only repeats.
13. **Exotic (medium).** Open-ended: each new phrasing found something (sky radio-emission patent, CRoNS, wearable optically pumped magnetometer). None changes the ranking for a small drone.
14. **Ottawa (medium).** The observed overcast normals are solid. Observed night cloud and sky brightness need ECCC hourly data, which is a download and needs an owner go-ahead, not more searching.

---

## Appendix: five items most likely to change the sim or the plan

1. **Public magnetic data near Ottawa.** The MagNav Challenge flights and the Renfrew map are near Ottawa. With an owner go-ahead, a sim of magnetic-anomaly navigation on the real local map is possible, for larger platforms (topic 11).
2. **YOW may have lost its VOR.** A late-2025 Canada Flight Supplement extract lists YOW 114.6 MHz as a DME, not a VOR/DME, so the VOR scenarios may rest on a removed station (topic 12).
3. **SDR VOR accuracy measured in flight.** About 1-2° mean error with about 1° SD, plus up to 5° of oscillator bias driven by temperature (topic 12).
4. **Sky-sensor heading now has numbers.** The models for stars, sun and polarisation have figures for each condition (topics 1, 3, 4). Ottawa availability comes from observed normals: heavy overcast 54% of hours a year, 62-66% in December and January (topic 14).
5. **Magnetic and gyro heading quantified.** Gyrocompassing is ruled out for any IMU we could fly. Motor current leaves about 1-2° of magnetometer error at realistic mast lengths (topics 5 and 6).
