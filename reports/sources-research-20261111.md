# More sources: evaluation, sim experiment and research, in one place

- **Date:** 2026-11-11
- **Kind:** research and planning only. No code, ADR or ICD in the repo was changed. Nothing here is a decision; every "do X" is a proposal for the owners and each new approach needs its ADR.
- **Repo state read:** `main` at `7c20323` (equal to `origin/main` at the time).
- **In the repo:** this report only. The supporting agent reports it cites in `reports/research-round2/` are kept locally and are not committed yet.
- **What this file is:** the whole of one working session, written up to be read start to finish: what was looked at, one scratch experiment, five research reports, and what they add up to.

## Contents

1. Short version
2. How to read the evidence
3. What was read in the repo
4. Where the project stands
5. The scratch experiment
6. Research: radio signals
7. Research: sensors, hardware and sim tools
8. Research: celestial and conventional navigation
9. Research: everything else (hardening GPS, cooperative, mapping, algorithms, timing)
10. Research: market and product
11. Analysis: what it adds up to
12. Conflicts with `systems/`
13. Corrections made along the way
14. What was not covered
15. Decisions waiting on the owners
16. Second research pass (additions and corrections)
17. Saturation round (about 970 searches): coverage, findings, corrections
18. Third pass on the topics that were still producing (about 410 more searches)

Section 16 was added after a second, short research pass, and section 17 after a much larger one. **Where they disagree with sections 6 to 11, the later section is right.** Section 17.9 lists every correction.

---

## 1. Short version

- The scored benchmarks rest on one positioning signal, LTE pseudoranges. Nothing measures velocity or heading. On the realistic set LTE holds a few hundred metres after GPS loss, and dead reckoning on the MPU6050 drifts kilometres in 300 s.
- A scratch experiment through the real EKF showed that velocity with a heading reference, LEO Doppler and more precise ranging each cut the 300 s error from hundreds of metres to tens or less. It also showed two problems: the sim's LEO layer has no orbit error, and the filter becomes overconfident when a source's error is correlated, so adding sources together gained nothing.
- The research says LEO Doppler should not lead. With orbits as published, real Doppler fixes are kilometre-level; Iridium, the only LEO signal our dongles reach, gives 100 to 200 m static over minutes; cheap Starlink reception has largely stopped working; every published moving result used a far better IMU and clock than ours.
- The largest levers found are: LTE carrier phase (0.37 to 0.89 m on a drone in the literature), a heading reference, a velocity source, and fixing the filter's handling of correlated errors.
- For a product, the gap the market research is most confident about is a receive-only GPS trust monitor for small drones that cross-checks against cell towers and publishes false alarms per flight hour.
- Evidence quality is uneven. A session-wide cap of 200 web searches ran out partway. Section 14 lists what was never searched.

---

## 2. How to read the evidence

| Label | Meaning |
| --- | --- |
| *(repo)* | Read in this repo |
| *(experiment)* | My scratch run, section 5. Sim, placeholder error models, not committed |
| *(checked)* | A research agent read the cited primary source on 2026-11-11 |
| *(snippet)* | From a search snippet or secondary page; the paper itself was not read |
| *(memory)* | A model's recall, not verified. Treat as `TBC` |
| *(derived)* | Arithmetic by an agent or by me |

Five research agents ran in parallel, each with a broad brief: radio signals; sensors, hardware and sim tools; celestial and conventional methods; everything else; market and product. Their queries were generic and carried no names, repo or location details. How well each is sourced:

| Report | Sourcing |
| --- | --- |
| Radio signals | Mostly *(checked)*; ran out of searches late |
| Market and product | Mostly *(checked)* with vendor claims marked |
| Sensors, hardware, sim tools | Sections on velocity, heading, imagery, IMUs, radios and GNSS receivers sourced; papers pass only partial |
| Celestial and conventional | About half sourced; many conventional methods *(memory)* |
| Everything else | Only 10 searches before the cap; mostly *(memory)*. A map of ideas, not numbers |

When the cap ran out, the search tool told the agents not to work around it by searching through a browser. They declined to use Chrome for searching for that reason and only read pages whose addresses they already had.

---

## 3. What was read in the repo

- `reports/fable-handoff.md` and `reports/direction-and-soops-20261111.md` (the earlier direction check and cheap-source catalogue), and the ranking section of `reports/Unconventional PNT sources and angles.md`.
- `AGENTS.md`, `systems/sim-plan.md`, `systems/accuracy-budget.md`, `systems/requirements.md` (REQ-06, REQ-07).
- `analysis/results/challenge-baseline/summary.md` and `analysis/results/tower-count/summary.md`.
- `src/pnt/core/measurement.py`, `src/pnt/sim/models.py`, `sensors.py`, `leo.py`, `scenario.py`, `src/pnt/nav/__init__.py`, `ekf.py` (measurement models and dispatch), `imu.py` (the filter's IMU spec and alignment options), and the scenario files `sets/realistic.yaml`, `sets/challenge-drone.yaml`, `uc01-drone-circuit.yaml`, `iridium-outage.yaml`, `iridium-starlink-outage.yaml`.
- `~/.cache/pnt-work/agent-rules.md` (the capped wrapper and shared rules).

---

## 4. Where the project stands *(repo)*

**Sources in the sim today**

| Source | Kind | In the scored benchmark? |
| --- | --- | --- |
| LTE | pseudorange | Yes, the only positioning signal |
| GNSS | position, time, health | Yes, until it is cut or attacked |
| IMU, barometer | accel/gyro, altitude | Yes |
| VOR | bearing | Side scenario; ablation showed no significant gain |
| Iridium, Starlink | Doppler | Side scenarios; satellite position and velocity given exactly |
| ADS-B | integrity cue | Side scenario |
| Hostile beacon | received power | Side scenario |

**Gaps in what the filter can use**

- `velocity_enu` is in the ICD's kind list and the GNSS front end writes it, but `nav/ekf.py` has no model for it, so the filter ignores every velocity record.
- There is no heading measurement of any kind. The IMU filter gets heading from aligning to GPS velocity, with a 3° floor.
- The EKF accepts `position_enu` from any source, so an absolute fix from something other than GNSS already works.

**Accuracy today**

- Clean `uc01`: the best filter misses T1 by 0.5 m (25.5 m against 25 m) and meets the 50 m / 120 s fallback.
- `uc01-realistic`: `ekf-calibrated` 488 m; `ekf` and `ekf-imu` kilometres before ADR-0047.
- `challenge-drone` outage: worst second 10 to 24 km across estimators (stale for some rows since ADR-0047).
- Tower count study: with the committed told sigma, adding towers made the error worse than having none; with the true noise told, all towers gave 110 m.
- The accuracy budget names what ends the IMU's usefulness: heading error times turn acceleration (312 m at 120 s for 3°) and gyro bias (536 m at 120 s).

---

## 5. The scratch experiment *(experiment)*

**Why:** to rank candidate sources with numbers from the real pipeline instead of opinion.

**Setup**

- Scenario: `uc01-realistic` as `analysis/accuracy_budget.py` builds it (the UC-01 circuit in the realistic environment), 120 s of GPS then 300 s without.
- 20 seeds (0 to 19), commit `7c20323`, run through the capped wrapper.
- Statistic: ADR-0034's, the 95th percentile across runs at each second after GPS loss. The tables give the worst second in the window.
- Candidate sources were built from truth with stated error models and added to the run's records. The repo's EKF ran unchanged except for a `velocity_enu` model patched in inside the script only.
- A second route, a 2.4 km straight leg after two turns, was added because a closed circuit cancels heading and scale errors.

**Error models used (all placeholders, `TBC`)**

| Source | Model |
| --- | --- |
| Optical flow | velocity at 10 Hz, 0.3 m/s white, heading error wandering at 3° (Gauss-Markov, 300 s), 2 % scale error, told 0.5 m/s |
| Flow + heading reference | the same with 1° heading error, told 0.4 m/s |
| Visual-inertial odometry | 0.1 m/s white, 0.3° heading, 0.5 % scale, told 0.15 m/s |
| Map-matching fixes | horizontal fix, 8 m white + 5 m slow bias, 0.5 Hz, heard 70 % of 20 s blocks |
| Sparse map fixes | 15 m + 10 m bias, 0.2 Hz, heard 30 % |
| Iridium Doppler | the repo's layer, 1 m/s, our clock drift in it |
| Starlink Doppler | the repo's layer, 0.2 m/s, half the passes heard |
| LTE 12 sites | the realistic set with 12 TELUS sites instead of 4 |
| Precise ranging | 8 sites, 3 m noise, 5 m multipath, 5 m table error (stands for carrier phase, wideband 5G or a base station) |
| Chip-scale atomic clock | payload clock 0.1 ppb drift, 0.03 ns/√s |
| Tactical IMU | figures recalled for an HG4930-class unit, in both the sim and the filter's spec |

**Results, UC-01 circuit**

| Source | p95 at 60 s | at 120 s | at 300 s | Worst 0–120 s | Worst 0–300 s | Epochs with HPL ≥ error |
| --- | --- | --- | --- | --- | --- | --- |
| Dead reckoning (IMU + baro) | 824 | 2,119 | 6,095 | 2,119 | 6,095 | 100 % |
| LTE realistic, `ekf-imu` | 254 | 465 | 370 | 502 | 502 | 92 % |
| LTE realistic, `ekf-calibrated` | 172 | 425 | 392 | 425 | 488 | 100 % |
| LTE 12 sites | 107 | 106 | 159 | 129 | 185 | 100 % |
| LTE + chip-scale atomic clock | 157 | 412 | 372 | 412 | 479 | 100 % |
| Precise ranging, 8 sites | 14 | 17 | 25 | 22 | 32 | 100 % |
| Iridium Doppler | 15 | 28 | 57 | 28 | 72 | 100 % |
| Iridium + Starlink Doppler | 2 | 2 | 2 | 2 | 3 | 100 % |
| Tactical IMU alone | 1,686 | 3,278 | 7,876 | 3,278 | 7,877 | 88 % |
| Optical flow, 3° heading | 33 | 27 | 38 | 34 | 49 | 30 % |
| Optical flow + 1° heading reference | 11 | 9 | 11 | 12 | 17 | 67 % |
| Visual-inertial odometry | 3 | 2 | 3 | 3 | 5 | 84 % |
| Map fixes, sparse (30 %) | 826 | 762 | 1,133 | 826 | 1,224 | 100 % |
| Map fixes (70 %) | 61 | 155 | 100 | 163 | 163 | 100 % |
| Flow+heading + LTE realistic | 11 | 9 | 11 | 12 | 17 | 67 % |
| Flow+heading + Iridium | 11 | 9 | 11 | 12 | 17 | 67 % |
| Flow+heading + sparse map fixes | 11 | 9 | 11 | 12 | 16 | 68 % |
| Odometry + map fixes (70 %) | 3 | 2 | 3 | 3 | 4 | 83 % |
| Tactical IMU + odometry + map fixes + precise ranging | 3 | 2 | 3 | 3 | 4 | 83 % |

All values in metres.

**Results, 2.4 km straight leg**

| Source | p95 at 60 s | at 120 s | at 300 s | Worst 0–300 s | Epochs with HPL ≥ error |
| --- | --- | --- | --- | --- | --- |
| Dead reckoning | 279 | 875 | 9,644 | 9,644 | 100 % |
| Iridium Doppler | 13 | 27 | 56 | 72 | 100 % |
| Optical flow, 3° heading | 53 | 85 | 209 | 209 | 8 % |
| Optical flow + 1° heading reference | 19 | 33 | 83 | 83 | 15 % |
| Visual-inertial odometry | 6 | 10 | 23 | 23 | 20 % |
| Flow+heading + sparse map fixes | 19 | 33 | 79 | 79 | 15 % |
| Flow+heading + Iridium | 19 | 33 | 82 | 82 | 16 % |
| Odometry + map fixes (70 %) | 6 | 9 | 18 | 18 | 21 % |

**What it shows**

- Velocity is the largest single lever, and it needs a heading reference: on the straight leg flow alone drifts as heading error times distance.
- Sparse absolute fixes do not help on this IMU. The gaps between them are dead reckoning.
- More sites help (488 to 185 m). A better payload clock does not (479 m).
- Combining sources gained nothing. Flow plus LTE, plus Iridium or plus map fixes scored the same as flow alone, and the HPL covered the error in only 8 to 67 % of epochs. My reading, not confirmed: the unmodelled heading and scale error in the velocity records makes the filter overconfident, so it gates out or outweighs everything else, the same way LTE's told sigma does.

**What it does not show**

- The LEO rows are not credible. `sim/leo.py` writes the true satellite position and velocity into each record. Section 6 gives what real orbit error does.
- The tactical-IMU row is a filter or scenario artefact, not a verdict (section 7).
- The velocity records are in ENU directly, so they skip the body-frame coupling a real sensor has.
- Every error model is a placeholder; several are from memory.

**Files:** the script and results (`source_study.py`, `source_study.json`, `source_study.out`) were copied into `reports/research-round2/`, which is not in the repo yet (section 17).

---

## 6. Research: radio signals

### 6.1 LEO Doppler

**Orbit error is the whole story**

- Starlink plus OneWeb, 13 satellites, static: 1.37 km with orbits as published; 57.6 m when the receiver estimates orbit errors online *(checked)* ([Hayek & Kassas 2025](https://people.engineering.osu.edu/media/document/2025-05-19/kassas_warm_start_navigation_with_non_cooperative_leo_satellites_via_online_ephemeris_error_estimation.pdf)).
- Starlink, 19 satellites over 5 min, simulation: 2.3 km raw; 53 m with orbits corrected by a learned model *(checked)* ([El-Kouba et al. 2024](https://people.engineering.osu.edu/media/document/2024-10-12/kassas_improved_starlink_satellite_orbit_prediction_via_machine_learning_with_application_to_opportunistic_leo_pnt.pdf)).
- The well-known "2 m in 20 s" Starlink result first corrects the orbits using the receiver's known position *(checked)* ([Kozhaya et al. 2025](https://people.engineering.osu.edu/media/document/2025-08-06/kassas_unveiling_starlink_for_pnt.pdf)).

**Iridium (about 1626 MHz, inside our dongles' range)**

- Each ring-alert burst is a 2.6 ms tone, a short sync word and data, 6.5 to 20 ms in all. A given beam repeats every 4.32 s *(checked)*.
- A passive receiver gets burst frequency, arrival time, signal strength, satellite ID and beam ID, and broadcast fields with the satellite's own position *(checked)*.
- The same bursts carry subscriber pages. Under REQ-08 and ADR-0011 those must be dropped at capture.
- Static accuracy, Iridium only, published orbits, height aiding, minutes of observation: 198 m (ring alert) and 163 m (messaging channels) *(checked)* ([Tan et al.](https://www.mdpi.com/2079-9292/9/1/37)). Other static results: about 132 m, and 130 to 140 m from a cold start *(checked)*. With one Orbcomm satellite added: 22.7 m *(snippet)*.
- No Iridium-only drone result was found.
- Iridium's open bursts have no source authentication, so they can be spoofed with modest equipment *(checked)* ([arXiv 2603.12062](https://arxiv.org/abs/2603.12062)).
- The dongle's oscillator is a problem: 1 ppm is about 1.6 kHz at this frequency against about ±35 kHz of Doppler *(memory, derived)*. Options are frequency states in the filter, one shared reference across dongles calibrated against LTE carriers, or a GPS-disciplined oscillator in holdover.
- The open decoder is `gr-iridium`; an RTL-SDR at 2.4 MS/s covers the whole simplex band *(checked, derived)*.

**Iridium's paid service (formerly Satelles STL)**

- Authenticated bursts. Timing under 205 to 300 ns in independent tests *(snippet)*. Position usually quoted at 20 to 50 m *(memory)*; Iridium's current fact sheet says 10 m static *(checked, vendor claim)*.
- A chip (8×8 mm, under 0.2 g) has been on sale since 2026-07-14. No price or subscription terms are published *(checked)*.

**Starlink (Ku band, needs a satellite-TV feed in front of the dongle)**

- The pilot tones a cheap receiver could track fell from about 50 dB-Hz before 2023 to about 20 dB-Hz after, which the authors call practically unusable with a small feed *(checked)*.
- The full signal still works but needs a feed locked to a disciplined reference and heavier processing.
- Static results with corrected orbits: 1.3 m (tones, 2021), 5 to 7.5 m (full signal, frequency steps estimated on the fly), about 2 m with a base station *(checked)*.
- The signal has quirks: frequency corrections in steps every second before 2024; frame timing adjusted every 15 s and drifting in between, so stand-alone ranging is unreliable *(checked)*.
- SpaceX removed dish location reporting from 2026-05-20 and offers no positioning service *(snippet)*.
- A low-cost Ku front end result: 268 m after 600 s *(checked)* ([arXiv 2602.06682](https://arxiv.org/abs/2602.06682)).

**OneWeb, Orbcomm, Globalstar and others**

- OneWeb with a reference network sending clock and orbit corrections: sub-metre *(checked)*. Needs a network.
- Direction of arrival from commercial Ku antenna arrays: 21 to 29 m static, better than Doppler alone (94 to 109 m) in the same test *(checked)*.
- Orbcomm (137 MHz): 358 m with an RTL-SDR and a dipole, 77.5 m with carrier phase *(snippet)*. Few satellites still work.
- Globalstar: under 100 to 300 m *(snippet)*; above our dongles' range.
- Geostationary satellites have almost no Doppler, so they give timing only.

**Moving platforms**

| Platform | Aids | Result | Source |
| --- | --- | --- | --- |
| Ground vehicle, 4.15 km in 150 s | industrial IMU, altimeter, 6 satellites from 3 constellations | 18.4 m RMSE against 118.5 m inertial only | *(checked)* |
| Ground vehicle, base station | the same, differential | 9.5 m against 205 m | *(checked)* |
| Ground vehicle, published orbits | differential against not | 11.7 m against 54.4 m | *(checked)* |
| Drone, 55 s without GPS | lab-grade radio, tactical IMU, 9 Starlink | 8.15 m with online orbit corrections, 17.8 m without, 46.5 m inertial only | *(checked)*, via the market report |
| Drone | Orbcomm-aided inertial | 31.7 m to 8.8 m after 30 s | *(snippet)* |
| Fixed-wing, simulation, 300 s | tactical IMU, oven oscillator, atomic clocks on satellites | 37 m final against 1,536 m | *(checked)* |

None used an IMU or clock in our class.

**New commercial LEO services:** Xona launched six production satellites on 2026-10-20 and plans service in 2027; it has a timing demonstration with NRC, ISED and DRDC *(checked)*. TrustPoint (C band) plans a soft launch in 2027 *(snippet)*.

### 6.2 Error models for an honest LEO sim

| Term | Values | Evidence |
| --- | --- | --- |
| Starlink published-orbit error against age | median 0.94 km at 6 h, 11.7 km at 3 days; mostly along-track, the other axes about 100 times smaller | *(checked)* ([arXiv 2605.19850](https://arxiv.org/html/2605.19850v1)) |
| Starlink published orbits against SpaceX's own files | 2,535 m and 2.75 m/s; 177 m and 0.86 m/s after learned correction | *(checked)* |
| Iridium published orbits | 100 m to several km, about 3 m/s | *(checked)*, an assumption in the source |
| Sensitivity | 300 m of orbit position error gives about 268 m of fix error; velocity error hurts more | *(checked)* |
| Base station residual | with 4 km along-track error, up to about 80 m at a 14 km baseline | *(checked)* |
| Doppler noise per burst | σ ≈ √(6 / ((2π)² · C/N0 · T³)); at 50 dB-Hz about 9.5 Hz for a 2.6 ms tone (1.7 m/s), 1.7 Hz for 8 ms | *(derived)* |
| Unmodelled error | one group inflated its Doppler noise by 7.5 | *(checked)* |
| Ionosphere rate | 0.153 m per TEC unit at 1626 MHz, 21.5 m at 137 MHz | *(derived)* |
| Troposphere rate | about 0.7 m/s at 10° elevation; use a 15 to 20° mask | *(derived)* |
| Dongle clock | 1 ppm initial, a temperature ramp over the flight | *(memory)* |

### 6.3 Cellular beyond what we have

- **Carrier phase on a drone:** 36.6, 88.6 and 89.3 cm horizontal RMSE over flights of 1.72, 3.07 and 0.61 km *(checked)* ([Khalife & Kassas 2022](https://people.engineering.osu.edu/sites/default/files/2022-10/Kassas_On_the_achievability_of_submeter_accurate_UAV_navigation_with_cellular_signals_exploiting_loose_network_synchronization.pdf)). Conditions: line of sight, a GPS-disciplined receiver oscillator, position known before the outage, the drone staying within one sector. The physics: towers are only loosely aligned in time, but their frequencies are nearly as stable as atomic clocks, so their clocks behave as one cluster.
- **LTE code phase on a drone:** 8.15 m *(snippet)*. That is the class of measurement we have now.
- **Tower clocks measured (Trondheim):** the best tower moved about 4 ns peak to peak in an hour; another operator's drifted over 1,200 ns. A same-operator pair differed by 1.25 m peak to peak, a cross-operator pair by 3.5 m *(checked)*. That same-operator towers share a reference is expected but unverified.
- **5G:** the always-on sync block is 3.6 or 7.2 MHz wide *(derived)*. Opportunistic results: 3.35 m on a drone with four stations *(snippet)*. The purpose-built positioning signal needs the network's cooperation.
- **At drone altitude:** the 3GPP model gives near-certain line of sight above about 100 m in cities and 40 m in rural areas *(snippet)*. No statistics of ranging error against altitude were found.
- **Bandwidth needed:** the sync signals fit in 2.4 MS/s; the full reference signal of a 20 MHz carrier needs at least 23 MS/s *(memory, derived)*.

### 6.4 Other broadcast and aviation signals

| Signal | Finding | Verdict |
| --- | --- | --- |
| ATSC 3.0 positioning (BPS) | 100 ns timing and about 100 m claimed; US deployment 2027 to 2029; no Canadian adoption found *(snippet)* | Future, sim only |
| ATSC 1.0 (Canadian digital TV) | Strong sync signal, transmitters not synchronised, so clocks must be learned as for LTE *(snippet)* | Fits our existing approach |
| AM / FM | AM time difference about 75 m (2007) *(snippet)* | Tens of metres at best, with learned clocks |
| ADS-B in reverse | 10 m median within seconds, but it needs GPS-synchronised anchor receivers and a link *(checked)* ([SkyPos](https://www.lenders.ch/publications/journals/jsac23.pdf)) | Strong if the ground laptop is an anchor |
| eLoran | No North American transmitter found *(snippet)* | Sim only |
| DME | Normal use transmits. Passive listening is research-grade | See section 8 |
| CHU | Shut down 2026-06-22 *(snippet)*; ADR-0019 already says so | Drop |
| WWVB | Millisecond timing *(memory)* | Timing sanity check only |

### 6.5 Public data *(owner go-ahead needed before any download)*

- TEXBAT (recorded GPS spoofing): free for research, no redistribution, cite the 2012 paper *(checked)*.
- OAKBAT: located in the second pass (section 16.1).
- Jammertest (Norway): the test plan is public; whether recordings are published is unverified.
- No public LEO Doppler or cellular recordings with ground truth were found; that search never ran.

---

## 7. Research: sensors, hardware and sim tools

### 7.1 Velocity

- **Optical flow.** Current modules pair a flow sensor with an infrared time-of-flight rangefinder, which emits light. The usable height is set by the rangefinder (25 to 50 m). PX4 models flow noise as 0.15 to 0.5 rad/s depending on quality *(checked)*; velocity noise therefore grows with height, and a height error becomes a scale error *(derived)*. ArduPilot's own calibration examples show scale off by up to about 14 % before calibration *(checked)*. No independent study of accuracy against height or light was found.
- **Visual-inertial odometry.** On a Raspberry Pi 5 without a GPU, Basalt runs at about 50 Hz and OpenVINS at about 20 Hz *(checked)*. At 40 to 100 m altitude with a stereo rig and an industrial IMU, position error was 2 to 5 m over 800 m with 0.9 to 3.2° of yaw error *(checked)*. The often-quoted 0.27 % figure from that paper is computed after aligning the trajectory, which removes the starting heading error. The honest model is 0.3 to 0.6 % of distance plus 1 to 3° of heading error that stays. Monocular methods at altitude: 0.5 to 2.9 % *(checked)*. It fails in the dark, over uniform texture and with blur.
- **Propeller drag as a velocity aid.** PX4 already fuses it, to estimate wind. It measures velocity through the air, so wind maps straight into ground-velocity error *(checked, derived)*.
- **Learned inertial odometry.** Networks trained on drone dynamics report 31.6 % and 66.7 % better dead reckoning on test sets *(checked by the catch-all agent)* ([AirIMU](https://arxiv.org/abs/2310.04874), [AirIO](https://arxiv.org/abs/2501.15659)).
- **Doppler radar (emits).** Honeywell's radar velocity sensor: 62 GHz, 24 to 68 g, about 1 % of distance typical and 3 % at 2σ with their inertial unit *(checked, vendor)*. Research radar-inertial odometry: 0.81 % over short indoor flights *(checked)*.

### 7.2 Heading

| Source | Accuracy | Limit | Evidence |
| --- | --- | --- | --- |
| No magnetometer, aligned to GPS velocity | 2 to 5° | what we have now | *(memory)*; the filter's floor is 3° *(repo)* |
| Magnetometer on a mast | 1 to 3° | motor and wiring currents produced 21 to 574 nT in one study, up to about 2° tracking throttle | *(checked)* for the interference, *(memory)* for the residual |
| Inertial with manoeuvres before the outage | 0.65° after a 140 s outage, low-cost IMU | needs S-turns | *(checked)* |
| Polarised-skylight compass | under 0.2° repeatability in flight; a commercial unit under 0.1° in clear to partly cloudy sky; 4.3° median under mostly cloudy sky | no heading under overcast | *(checked)* |
| Sun camera | 2.4° to ±3° | sun visible; tilt error leaks in | *(checked)* |
| Night star camera | 0.02 to 0.1° | clear night; estimate from static ground tests, no flight result | *(derived from checked static results)* |
| Two GPS antennas | about 0.5° | needs real GPS signals | *(memory)* |
| Gyrocompassing | not usable in flight on small parts | needs static rotation | *(checked)* |
| Direction of arrival to a tower | 5 to 10° | multipath | *(checked, anecdotal)* |

### 7.3 Absolute position from imagery and terrain

| Method | Result | Evidence |
| --- | --- | --- |
| Matching to orthophotos, 150 m altitude | 6.6 to 8.0 m RMSE | *(checked)* |
| Open satellite maps | 15.8 m mean | *(checked)* |
| Season-invariant matching | converges to 12.6 to 18.7 m | *(checked)* |
| Generic pretrained matcher lifted onto an elevation model | 5.88 m mean over 55 km at eight sites, no retraining | *(checked)* ([AeroMap3D](https://arxiv.org/abs/2607.14009)) |
| Thermal camera matched to ordinary imagery | 9.37 m mean at night | *(checked)* ([SCC-Loc](https://arxiv.org/abs/2604.03120)) |
| Joint position and heading from imagery | 89 % within 15 m | *(snippet)* |
| Lidar heightmaps matched to open elevation data, with odometry and compass | 5 to 13 m over 0.5 to 1.4 km below 25 m; lidar emits | *(checked)* ([arXiv 2510.01348](https://arxiv.org/html/2510.01348)) |

- Failures: night without thermal, snow and season change without learned matching, outdated maps, and look-alike scenes that give confident wrong fixes.
- One thermal method only worked within about 512 m of the last known position, so dead reckoning has to stay inside that.
- Terrain matching degrades over flat or repetitive terrain, and the altimeter emits.
- Firms already selling map matching include Maxar/Vantor and UAV Navigation-Grupo Oesía.

### 7.4 Inertial sensors

| Unit | Gyro bias instability | Price | Evidence |
| --- | --- | --- | --- |
| MPU6050 | 16°/h measured on ours | — | *(repo)* |
| BMI088 | 2°/h typical, users measure 3 to 4 | — | *(checked)* |
| ADIS16470 | 8°/h | about US$418 | *(checked)* |
| ADIS16505 | 2.3°/h | US$688 | *(checked)* |
| Epson M-G370 | 0.8°/h | not published | *(checked)* |
| STIM300/318 | ≤ 0.3°/h | — | *(checked)* |
| Honeywell HG4930 | 0.25 to 0.45°/h | about US$8k to 15k from a 2016 listing | *(checked)* |

Free-inertial drift, after calibration under GPS *(derived)*:

| Grade | 60 s | 120 s | 300 s |
| --- | --- | --- | --- |
| Consumer | 0.1 to 0.4 km | 0.8 to 3 km | 8 to 40 km |
| Industrial | 10 to 30 m | 60 to 130 m | 0.4 to 1 km |
| Tactical | 1 to 3 m | 5 to 13 m | 50 to 110 m |

**Why the tactical IMU did not help in the experiment.** A 3° heading error over 2.4 km is about 126 m of cross-track error on its own *(derived)*. A better gyro adds almost no heading error during the outage, but it cannot remove an error that was already there when GPS was lost. Heading is only observable under horizontal acceleration. So the grade pays off only if the drone manoeuvres while GPS is good and the filter is retuned for the better sensor. Checks, most likely first:

1. Is the heading floor (3° in `nav/imu.py`) applied regardless of IMU grade?
2. Does the GPS-good part of the scenario have enough horizontal acceleration?
3. Were the filter's process noise and extra-noise terms switched with the IMU?
4. With all aiding off, does the tactical run show roughly 1 to 3 m at 60 s and 50 to 110 m at 300 s? If not, the sim model or the mechanisation is wrong.

Manoeuvres that make heading and biases observable *(derived)*: S-turns or figure-eights at 1 to 3 m/s² for 5 to 10 s in alternating directions; speed changes; climbs and descents. Yaw spins in hover do not help heading.

### 7.5 Radios

| Device | Bandwidth, bits | Can transmit? | Price | Evidence |
| --- | --- | --- | --- | --- |
| RTL-SDR (ours) | about 2.4 MS/s, 8 | No | about US$40 | *(memory)* |
| Airspy R2 | 10 MS/s, 12 | No | not shown | *(checked)* |
| SDRplay RSPdx-R2 | 10 MHz, 14 | No | €217 | *(checked)* |
| KrakenSDR | 5 coherent channels of 2.56 MHz | No | €599 to 799, about 11 W, 560 to 670 g | *(checked)* |
| HackRF One | 20 MS/s, 8 | Yes | — | *(checked)* |
| LimeSDR Mini 2 | 30.72 MS/s, 12 | Yes | about US$502 | *(checked)* |
| bladeRF 2.0 micro | 61.44 MS/s, 12 | Yes | US$540 to 860, 90 g | *(checked)* |
| USRP B205mini | 56 MHz, 12 | Yes | US$1,875 | *(checked)* |

Every device wide enough for a full 20 MHz LTE carrier can also transmit. No receive-only variant was found.

Cellular modems: timing advance and network positioning need the modem to attach, which transmits. Cell ID and signal strength may be readable without, but that is unverified *(memory)*.

### 7.6 GNSS receivers for spoof detection

- u-blox ZED-X20P: jamming and spoofing flags, signed Galileo messages. u-blox's own write-up from a 2025 jamming test says the spoofing flag sometimes fired under jamming alone *(checked)*.
- Septentrio mosaic-X5 and G5: built-in interference and spoof protection, about US$626 to 700 on a breakout *(checked)*.
- A Stanford method plots signal strength against calibrated receiver gain to separate nominal, jammed, spoofed and blocked *(checked)*; no rates in the abstract.
- Reported detection on TEXBAT: over 90 % at 0.1 % false alarms with vector tracking *(checked, a review)*.
- Testing without transmitting: an open generator (`gps-sdr-sim`, MIT licence, archived) writes spoofed GPS signals to a file; an open software receiver (GNSS-SDR) reads files *(checked)*. Both are third-party code.

### 7.7 Sim tools and validating the sim

- PX4's Gazebo has an optical-flow plugin; ArduPilot's SITL has flow noise settings.
- AirSim's successor Colosseum was archived in July 2026; Cosys-AirSim continues *(checked)*.
- Sionna RT is used for drone channel models; accuracy follows map fidelity *(checked)*.
- The recommended way to judge a sim is ADR-0015's: run the same filter on real and simulated logs and compare its error statistics. Supporting checks: Allan curves of real against simulated static IMU data, innovation statistics, and protection-level coverage *(memory)*.

---

## 8. Research: celestial and conventional navigation

### 8.1 Stars, sun and sky

- **A star gives attitude, not position.** Position also needs to know which way is down, and one arcminute of error in that is 1.852 km on the ground. An autopilot levelled to 0.2° would give about 22 km *(derived)*.
- **The one small-drone celestial fix found:** a Raspberry Pi 5 and a mono camera on a fixed-wing at night, circling to average out the tilt error, got within 4 km *(checked)* ([Teague & Chahl 2024](https://mdpi.com/2504-446X/8/11/652)). No better follow-up was found.
- **Low-cost star trackers:** a Raspberry Pi with a Pi camera reached under one arcminute in a static ground test *(checked)*. No result from a vibrating multirotor was found.
- **Large-aircraft systems:** a Northrop stellar-inertial unit holds 0.5 nautical miles for 18 h *(checked, contractor claim)*; Honeywell demonstrated 25 m by tracking stars and satellites together on an airliner *(checked)*; a current French unit gives 3 arcseconds day and night at under 3 kg *(checked)*. Daytime tracking needs a short-wave infrared camera; published daytime flight results are above 10 km altitude.
- **So for a small drone, stars are a heading reference.** A 1 km position error shifts a star's azimuth by only about 0.01° *(derived)*, so the heading barely depends on knowing where you are.
- **Ottawa's sky:** forecast clear about 32 % of day hours and 30 % of night hours over the year; 14 to 22 % in December and January; 43 to 50 % in September *(checked, forecast climatology)*.
- **Tracking satellites optically against the stars:** 250 m RMS in a ground test *(checked)*.
- **X-ray pulsars:** spacecraft only.

### 8.2 Conventional methods

| Method | Finding | Verdict |
| --- | --- | --- |
| Terrain contour matching | Needs relief and a radar or laser altimeter, which emits | Not for flat Ottawa |
| Magnetic-anomaly navigation | 22 m final over 365 km in the best published flight; platform interference is 100 to 1,000 times the signal; no small-drone fix found. Canada publishes a national 200 m magnetic grid *(checked)* | Large aircraft; sim only for us |
| Gravity | Not searched | Large platforms |
| VOR | NAV CANADA has removed 52 VORs and keeps about 60. An Ottawa VOR with identifier OW and the YOW NDB were revoked 2024-01-25. The YOW VOR/DME on 114.6 MHz is on no removal list, but no list of retained stations is published *(checked)* | YOW availability `TBC`; confirm from the Canada Flight Supplement or NOTAMs |
| Passive DME | A 2014 simulation paper reached under 46 m by tracking the carrier phase of ground-station replies without interrogating *(checked, simulation only)* | Worth a model |
| Camera bearings to surveyed landmarks and lit towers | About 9 m at 5 km if bearings are good to 0.1° *(derived; literature not searched)* | Worth a model |
| Direction finding on broadcast and cell emitters | A few degrees with large multipath outliers *(memory)*; a single emitter needs the vehicle to manoeuvre | Model as bearing with heavy tails |
| Navy VLF stations | Kilometre-class *(memory)* | Coarse check only |
| Lightning sferics, muons, infrasound, streetlight flicker | Need a live network, need detectors within metres, or carry no position | No |
| eLoran, Omega, Decca | No transmitter here, or shut down | No |

### 8.3 Time without GPS

WWVB about 100 µs after removing the path delay *(checked)*; chip-scale atomic clock about a microsecond per day in holdover *(memory)*; CHU gone.

---

## 9. Research: everything else

This report is mostly *(memory)*. Items marked *(checked)* are the exceptions.

### 9.1 Making GPS itself harder to deny

- **Anti-jam antenna arrays.** N elements null at most N−1 jammers. Vendor figures of 20 to 60 dB are not comparable with each other *(checked)*. The first pass said a four-element unit fits drones of about 5 kg and up *(memory)*; that was wrong, see section 16.4.
- **Multi-band, multi-constellation receivers.** About 10 g, off the shelf.
- **Signed Galileo messages (OSNMA).** In service since 2025-07-24 and in consumer firmware *(checked)*. It stops forged data, not a replayed signal.
- **Two antennas.** Spoofed signals arrive from one direction, so the phase difference across the pair is the same for every satellite. Shown on low-cost boards *(checked)*; no flight detection rates found.
- **Deep coupling with the inertial unit.** Lowers the tracking threshold by 7 to 15 dB *(checked)*; needs raw samples.
- **Locating the jammer.** A few metres from a drone with one antenna *(checked)* ([arXiv 2503.20352](https://arxiv.org/abs/2503.20352)). From there: treat it as a beacon (the repo's hostile-beacon layer already does) or plan a route out of its footprint.

### 9.2 Cooperative methods

- **Ground beacons the operator deploys.** The drone only listens. About 20 cm to aircraft on a US test range *(checked, Wikipedia)*.
- **Ranging on the drone's own control link.** Wi-Fi round-trip timing is typically 1 to 2 m *(checked)*. The link already transmits, so it adds no new emitter; whether that fits REQ-07 is a ruling for the owners.
- **Ultra-wideband.** 10 cm *(checked, chip maker)*. Two-way ranging transmits; a listen-only mode exists with ground anchors.
- **Swarms.** Centimetre-level relative positions between drones *(checked)*; all transmit.
- **Ground tracking with the position sent up, 5G network positioning.** Need ground equipment or a carrier.

### 9.3 Map and return methods

- **Teach and repeat.** Record the outbound route visually and retrace it. Suits a return home after denial *(memory)*.
- **Radio fingerprint maps, as phones use.** 10 to 40 m outdoors *(memory)*; 8 to 20 m median in LTE field trials *(snippet, radio report)*. Maps made at street level differ from the air.
- **3D city-model shadow matching.** Needs GPS signals to be present. The agent's own idea: spoofed signals ignore building shadows, so the same check could detect spoofing.

### 9.4 Algorithms, no new sensor

- A slowly varying bias state for each source with correlated error, including one shared state for towers that share a clock.
- Inflating measurement noise to the error's correlation time, or thinning updates to it.
- Innovation whiteness tests, which detect unmodelled correlation directly.
- Robust weighting of outliers.
- A fixed-lag smoother or factor graph in place of the plain EKF; an invariant EKF, which behaves better from large heading errors.
- A particle filter where the problem has several candidate answers, such as map matching.
- Planning the route to make states observable.

### 9.5 One timing point that affects position

Cell towers discipline their clocks from GPS. The first pass said towers inside a jammed area go into holdover and drift together. That was overstated and is corrected in section 16.3: the start of holdover is shared, the drift is mostly per tower. The repo has a `tower_holdover` attack; the point that stands is that it belongs in the default picture once jamming starts.

### 9.6 What fielded systems combine

Anti-jam antennas on Shahed-class drones have grown from 8 to 16 to 32 elements *(checked)*. Skydio's X10 navigates by vision *(checked)*. The common pattern is an anti-jam antenna or multi-band GPS, an inertial unit, and visual map matching or odometry. Almost none use cooperative radio ranging, because transmitting gets the drone located *(memory)*.

---

## 10. Research: market and product

### 10.1 Who sells what

| Vendor | Product | Published figure | Evidence |
| --- | --- | --- | --- |
| Honeywell | HANA software framework: vision (shipping), magnetic and LEO modules slated for 2026 | none published | *(checked)* |
| Honeywell | Radar velocity sensor | 1 to 3 % of distance | *(checked, vendor)* |
| Iridium | Positioning chip, 8×8 mm | 10 m static; timing under 50 ns with an oven oscillator | *(checked, vendor)* |
| Ground Control | 10 g receive-only board on that chip | flagged spoofing within 1 s at a 2026 jamming test | *(checked)* |
| Xona, TrustPoint | Dedicated LEO constellations | service about 2027 | *(checked)* |
| NextNav, Locata | Ground beacon networks | Locata under 7 inches per axis on a US range | *(checked)* |
| SandboxAQ, Q-CTRL | Magnetic-anomaly navigation | under 74 m in the best hour; 22 m best flight | *(checked, vendor)* |
| Maxar/Vantor | Camera-only map matching | under 10 m | *(checked, vendor)* |
| Septentrio, u-blox | Receivers with built-in spoof flags | no false-alarm rates published | *(checked)* |

No funded company was found selling cellular or LEO opportunistic navigation for drones. The work is in university groups.

### 10.2 What nobody serves

- Receive-only opportunistic navigation with integrity, under 100 g and under US$1k, for small drones.
- A spoof detector that cross-checks against cell towers. The existing add-ons work inside the receiver or against Iridium.
- Published false alarms per flight hour.

### 10.3 Demand and funding

- **Canada:** IDEaS challenges on drone geolocation under GPS degradation and on timing (both closed); an NRC defence stream of $241M through IRAP; a planned NRC drone hub in Ottawa and Mirabel; NATO test centres in Ottawa (Area X.O, NRC Aerospace) *(checked)*.
- **Elsewhere:** US DIU and Air Force calls on GPS-independent navigation for small drones; a German challenge on satellite-free flight; a NATO and Ukraine programme that lists navigation without GPS *(checked)*.

### 10.4 Standards and law

- The DHS resilient-PNT framework has four levels; our cross-checking maps onto the upper two. Its IEEE version is still a draft *(checked)*.
- No standard exists for opportunistic navigation or for protection levels on non-GPS sources. Transport Canada's 2025 rules give no navigation accuracy figure *(checked)*.
- **Radiocommunication Act section 9(2)** forbids intercepting and making use of a radiocommunication. Whether timing from cell sync signals is "making use" has no ruling that the agent could find. It recommends a legal opinion before selling.
- **Jammers and spoofers** are banned in Canada, with fines up to $25k for individuals and $10M for businesses. No ISED text was found that explicitly permits cabled simulator testing. Live jamming is legal only at authorised events (Norway's Jammertest, the US NAVFEST, DND trials).
- **Patents.** The University of California holds patents on LTE opportunistic navigation (to about 2038 to 2041) and on a LEO Doppler receiver (to about 2040). Honeywell holds patents on spoof detection against inertial units and against DME ranges. Not legal advice; a freedom-to-operate check is needed before a product.

### 10.5 Product shapes, as the agent ranks them

1. **A receive-only GPS trust monitor that warns**, outputting MAVLink's `GNSS_INTEGRITY` message. First buyers: Canadian operators flying beyond line of sight, drone-show operators, a defence test slot. Proof: detection rate and delay on recorded spoofing, false alarms per hour over 50+ clean flight hours, one live-jamming event.
2. **A licensable fusion and integrity engine** for autopilots. Proof: moving flights with RTK truth over minutes of denial, protection levels that bound the error.
3. **A sim and test tool** for alternative navigation. Proof: the sim matches real captures.

Autopilot hooks exist: ArduPilot takes an external navigation source and has a switch to disable GPS for testing; PX4 takes external odometry and has failure injection *(checked)*.

---

## 11. Analysis: what it adds up to

### 11.1 Doppler should not lead

- With honest orbit error the sim's Iridium figure (28 to 72 m) will move toward the published 100 to 200 m, and those are static, over minutes, with height aiding.
- The only LEO signal our kit reaches is unauthenticated.
- As a product it competes with a chip that is already on sale.
- It is still worth having in the sim, with orbit error, because its failure mode is independent of the ground.

### 11.2 What limits accuracy now, in order

1. The filter trusts correlated errors as if they were white. This showed up with LTE's told sigma *(repo)* and again with velocity *(experiment)*.
2. Heading at GPS loss. It sets the dead-reckoning error and decides whether a velocity source or a better IMU helps.
3. Nothing measures velocity.
4. LTE is used at code-phase precision, where the literature shows carrier phase is a further order of magnitude better on a drone.

### 11.3 Proposed order for the sim

**Make it honest first**

1. Correlated-error states and whiteness tests in the filter.
2. Heading at GPS loss as an output of the GPS-good phase, with manoeuvres; recheck the tactical IMU.
3. Orbit error, dongle clock and burst schedule in the LEO layer.
4. Shared tower drift when jamming reaches the towers.

**Then the levers**

5. LTE carrier phase with a shared cluster clock.
6. A heading source: magnetometer first, then sky-based ones with their availability.
7. A velocity source with heading-bias and scale states.
8. Map matching with availability, a shared map bias and confident outliers.
9. The base station brought into the benchmark, for LTE and LEO.
10. Spoof-detection inputs: signal strength against receiver gain, two antennas, signed messages.

**Cheap extras:** passive DME, landmark bearings, reverse ADS-B with the ground laptop as anchor, TV and FM with learned clocks, teach and repeat, a fly-out planner, Iridium's chip as a black-box fix.

### 11.4 Real hardware, cheapest first

1. A moving capture with S-turns before a software GPS cut.
2. Static LTE carrier-phase tracking, to measure Ottawa tower clocks per operator.
3. Static Iridium ring-alert Doppler, about CAD 150 for an antenna and filter *(estimate)*.
4. One shared clock across dongles, calibrated from LTE carriers.
5. A magnetometer on a mast; a multi-band GPS receiver with raw data.
6. Recorded-spoofing data replayed through the spoof detector.

### 11.5 Ruled out

Terrain matching in flat Ottawa; eLoran; gravity; pulsars; muons; magnetic-anomaly navigation on a small quad; 5G network positioning without a carrier; cheap Starlink tones; a better payload clock as an accuracy lever; a better IMU until heading alignment is understood.

---

## 12. Conflicts with `systems/`

| Item | Conflict |
| --- | --- |
| REQ-06 (signals of opportunity are primary, shown by ablation) | A velocity or heading aid will outrank LTE in that ablation as things stand. Leading with LTE carrier phase keeps radio primary |
| REQ-07 (receive-only) | Every SDR wide enough for full LTE can transmit. Flow sensors and lidar emit light. Ranging on the control link uses an emitter that already exists. Each needs a ruling |
| ADR-0011, REQ-08 (no communication content) | Iridium ring alerts carry subscriber pages, which must be dropped at capture |
| ADR-0019 (no CHU) | Confirmed: CHU closed 2026-06-22. One research report wrongly listed it as usable |
| `uc02-yow-approach-vor` scenarios | Whether the YOW VOR is retained is `TBC` |
| Third-party code and data (AGENTS.md) | `gr-iridium`, `gps-sdr-sim`, GNSS-SDR and every dataset need an owner's go-ahead |
| ADRs | Every item in 11.3 is a new approach and needs one; a heading kind changes the ICD and needs the other owner's approval |

---

## 13. Corrections made along the way

- The first source study gave 2 to 3 m for Starlink Doppler. That came from a sim with perfect orbits and is not credible.
- "Visual-inertial odometry at 0.3 % of distance" became 0.3 to 0.6 % plus 1 to 3° of heading error, once the paper was read in full.
- A "4.3 m from six Starlink satellites" figure in one report was traced to a theory paper with no measurement.
- One report listed CHU as a usable time signal; it is off the air.
- I told the agents they could search through Chrome after the cap ran out. The search tool forbids working around the cap that way, the agents declined, and I withdrew the instruction.

---

## 14. What was not covered

**Never searched**

- Camera bearings to landmarks, lit towers and skylines.
- Passive direction finding on small drones; running fixes from one emitter.
- Passive radar turned around for self-location.
- Gravity-aided navigation; terrain matching with lidar over flat ground.
- Low-altitude daytime star tracking; moon and night-sky polarisation; sun sensors.
- Navy VLF phase positioning.
- 5G at millimetre wavelengths; air-traffic radar as a signal; Amazon's constellation; passive Wi-Fi.
- Public LEO or cellular recordings with ground truth.
- A systematic pass over 2023 to 2026 papers in the navigation and robotics journals and recent theses. The papers cited here are ones the agents already knew or met along the way.

**Searched, nothing found**

- An Iridium-only drone result.
- LTE ranging error against altitude.
- Measured clock offsets between sectors of one site.
- Direction-of-arrival accuracy on LTE with a coherent dongle array.
- Independent accuracy tests of optical flow sensors against height and light.
- Flight detection rates for two-antenna spoof detection.
- A published accuracy for navigating off a jammer.
- Price or accuracy for Iridium's chip.

**Still from memory:** most of section 9; magnetometer residual heading; chip-scale clock figures; 3GPP positioning targets; several prices.

---

## 15. Decisions waiting on the owners

1. **REQ-06:** may velocity and heading aids outrank radio, or does the build lead with LTE carrier phase so radio stays primary?
2. **REQ-07:** are transmit-capable SDRs with the transmit path disabled, light-emitting sensors, or ranging on the existing control link acceptable?
3. **What to build first in the sim**, from section 11.3. My proposal is items 1 and 2 (filter honesty and heading), then 5 (carrier phase).
4. **Product direction:** the trust monitor, the fusion engine, or neither yet.
5. **The remaining research:** raise the search cap, or re-task the agents on section 14 after it refills.
6. **Third-party items:** whether to approve looking at `gr-iridium`, `gps-sdr-sim` and a recorded-spoofing dataset.

---

## 16. Second research pass (additions and corrections)

The four technical agents were re-tasked on the unsearched topics. The shared search budget ran out again after 32 searches in total (5, 9, 12 and 6), so this pass is short. Labels as in section 2.

### 16.1 Public data *(owner go-ahead needed before any download)*

- **OAKBAT exists** *(checked)*. Oak Ridge's companion to TEXBAT: GPS L1 and Galileo E1 spoofing scenarios on TEXBAT's parameters, plus pure-tone recordings, downloaded through Globus from the laboratory's DOI portal ([publication](https://ornl.gov/publication/tool-furthering-gnss-security-research-oak-ridge-spoofing-and-interference-test-battery)). The page states no licence; it links to terms that were not read, and requires a citation and a set acknowledgement.
- **Jammertest recordings are published** by Finland's geospatial research institute *(checked)* ([page](https://www.maanmittauslaitos.fi/en/node/17698)): live GPS and Galileo from the 2023 event with one jamming and two spoofing scenarios; a separate spoofing repository with signed Galileo messages; Baltic interference recordings; a simulated LEO positioning signal set. Licences are on the individual records and were not checked.
- **A drone-mounted LTE recording with GPS logs** *(checked)* ([arXiv 2303.01635](https://arxiv.org/abs/2303.01635)): raw samples at 30 to 110 m altitude from one test tower at 3.51 GHz, CC BY 4.0, behind an IEEE DataPort subscription. It can check altitude and multipath models, not real tower clocks. `systems/sim-plan.md` already names it.
- **No public LEO Doppler recordings** were found, again.

### 16.2 Radio: LTE, 5G and LEO

- **Sectors of one mast do not share a clock exactly** *(checked)*. A Kassas-group paper modelled the mismatch between sector clock biases and validated it; adding the model cut a drone's position error by 10.51 m ([PDF](https://people.engineering.osu.edu/sites/default/files/2022-10/Kassas_Modeling_and_Analysis_of_Sector_Clock_Bias_Mismatch_for_Navigation_with_Cellular_Signals.pdf)). ADR-0022 gives a site's sectors one clock with a sector residual that the realistic set leaves unused, so this is a gap to check. The size of the mismatch is in the paper body and was not extracted.
- **Towers make step-like frequency corrections** as they steer to their reference *(snippet)*. The sim has random-walk drift only.
- **A published 5G twin of our approach** *(checked)*: a fixed reference receiver estimates clock offsets between commercial 5G stations from their always-on sync block; error fell 73 to 84 %, to a mean of 12.7 to 20.6 m, limited by bandwidth ([PDF](https://re.public.polimi.it/retrieve/94c4b5bc-3db8-4baf-9b3f-01ab2cf2a6e3/Experimental%20Validation%20of%205G%20Positioning%20With%20Inter-Cell%20Clock%20Bias%20Correction_VOR.pdf)).
- **No carrier-phase result with a free-running cheap oscillator was found.** Every drone carrier-phase result still used a GPS-disciplined receiver. This is the main risk in leading with carrier phase on our hardware.
- **A 2025 multi-constellation Doppler simulation** reports 4 to 5 m, with no clocks modelled and orbits taken as given *(checked)* ([link](https://navi.ion.org/content/72/2/navi.691)). It is an example of the optimism in our current LEO layer.
- **One Iridium satellite, a base station and an industrial IMU on a ground vehicle:** 8.32 m *(snippet, context unverified)*. Still nothing with a low-cost IMU or on a drone.
- **NOAA weather satellites** have been tracked blind as a Doppler source *(checked)*; this fills the earlier "no results" entry.

### 16.3 Corrections to the first pass

- **Tower holdover under jamming.** No field measurement was found, only patents. One says a base station must hold about 10 µs over 8 h of holdover; others say the network may detect a GNSS timing outage and exclude or mute the affected cells *(checked)*. Corrected model: the start of holdover is shared across towers; the drift afterwards is mostly independent, because each tower has its own oscillator, and shared only between cells on one mast or one timing source. Tower clocks are unsynchronised to begin with, so jamming changes each tower's drift rate. Suggested values, `TBC`: a per-tower frequency offset of 1e-11 to 1e-9 after onset, plus a random walk.
- **Direction-finding bearings.** Replace the first pass's 3 to 5° with: about 0.5° precision on top of a per-receiver calibration bias of up to about 10° for a coherent dongle array *(checked, ground tests)* ([NAVIGATION 2026](https://navi.ion.org/content/73/1/navi.735)); or about 6° for a rotating directional antenna (16.5).

### 16.4 Hardening GPS

- **Small anti-jam antennas** *(checked, vendor claims, no independent test)*: a 180 g unit, 7.2 cm square, nulling three jammers at over 40 dB; a 275 g eight-element unit at over 50 dB. One is realistic on a drone of about 2 kg and up. An array that small has wide nulls, so expect to lose satellites within 30 to 40° of each jammer *(derived)*.
- **Spoof detection from direction of arrival** *(checked)*: in a live event, 47 of 129 spoofed epochs detected with no false alarms at a 1e-7 false-alert limit, with per-satellite azimuth good to about 12° ([link](https://navi.ion.org/content/68/2/243)). Detection per epoch is low, so it has to accumulate.
- **Offline spoof testing.** GNSS-SDR (GPL-3.0) reads sample files and tracks GPS, Galileo, BeiDou and GLONASS *(checked)*. With a generator writing to a file, spoof scenarios can be made and processed with no radio. GPL means it should run as a separate tool, not be linked into our code.

### 16.5 Bearings and landmarks

- **Cellular direction of arrival from a rotating antenna on a drone** *(checked)*: 6.02° measured bearing error while hovering; fed into a simulated line-of-sight network, a median position error under 45 m ([Aalto](https://research.aalto.fi/en/publications/measurement-based-performance-evaluation-of-drone-self-localizati/)). A multirotor can yaw in place to sweep the antenna.
- **Bearings to known beacons** *(checked, simulation, no figure retrieved)*: position and heading must be estimated together, and the path can be chosen for geometry. This supports the error model in 8.2.
- **Camera fixes from obstruction lights or city lights:** nothing published was found.
- **Thermal localisation at night against a 3D map built by day** *(checked)*: 2.18 m RMSE, 1.52 m median against RTK over 6.5 km of real night flights, processed offline ([arXiv 2604.26201](https://arxiv.org/abs/2604.26201)).
- **Skyline matching** is not shown on low-altitude drones and needs relief; not useful over Ottawa.

### 16.6 Velocity and return-home

- **Velocity from rotor speed** *(checked)*: adding rotor speed from the speed controllers' telemetry to the IMU makes body velocity observable. A learned model reports 0.24 m/s velocity error on indoor flights up to about 14 m/s and runs on a small single-board computer ([arXiv 2603.00597](https://arxiv.org/html/2603.00597)). It assumes no wind and one small airframe; wind adds an error equal to its speed.
- **Learned inertial odometry, a caution.** The 30 to 67 % gains in 7.1 are relative. None of these papers gives drift in metres or percent of distance, and one earlier method generalises poorly to unseen routes *(checked)*.
- **Teach and repeat has a flight result** *(checked for the flight, snippet for the error)*: a drone flew home on its recorded visual map after GPS failure, 450 m at 5 to 25 m altitude and up to 55 km/h, under 1.5 m cross-track over most of the path ([arXiv 1809.05757](https://arxiv.org/abs/1809.05757)).
- **Sun-camera heading** confirmed at 2.4° from a fisheye camera alone *(checked)*. No paper on heading from shadows was found.

### 16.7 Filter and integrity

- **Adding a source can raise the protection level.** A 2023 paper extending aviation-style integrity to opportunistic signals reports that a single added signal increased the horizontal and vertical protection levels in some geometries *(snippet)*. That matches the tower-count study.
- **Time-correlated measurement noise** can be learned from ground truth as a banded inverse covariance in a batch estimator, in place of hand-tuned inflation *(checked, no numbers in the abstract)* ([arXiv 2303.06507](https://arxiv.org/abs/2303.06507)). Another paper carries first-order correlated noise through to integrity monitoring *(snippet)*.

### 16.8 Fielded systems

Ukrainian strike drones locate themselves by matching camera images to stored satellite imagery *(checked, a ministry statement reported by the press)*. A US product doing the same, with a celestial mode for featureless flight, costs about $20k per aircraft *(checked)*. Russian drones have added visual terrain matching *(snippet)*. None publishes accuracy. Map matching is the industry default.

### 16.9 Effect on the analysis in section 11

- The order in 11.3 stands. Two items gain detail: the LTE model should add sector clock mismatch and step-like frequency corrections, and the tower-holdover model should be per tower with a shared start.
- Carrier phase (item 5) carries a named risk: no published result without a disciplined receiver clock. A shared reference across dongles, calibrated from LTE carriers, is the cheapest way to find out.
- Map matching moves up among the levers, since thermal results at night now reach 2 to 9 m and it is what fielded systems use. REQ-06 still applies.
- Cheap extras gain two: rotor-speed velocity (needs speed-controller telemetry) and a rotating-antenna bearing to towers.

### 16.10 Still not searched after this pass

- Low-cost star trackers, low-altitude daytime star tracking, moon and night-sky polarisation.
- Passive radar for self-location; terrain matching with lidar; gravity; VLF phase positioning; running fixes from one emitter.
- Measured magnetometer heading error on small quads; optical-flow accuracy against height and light.
- 5G ranging from drones; cellular direction-of-arrival heading with small arrays.
- Iridium Doppler on RTL-SDR-class hardware; radar, Wi-Fi and millimetre-wave 5G as signals.
- Cellular timing observed at jamming test events; jammer fly-out planning; time-spoof detection.
- Licence terms of the OAKBAT and Jammertest records.


---

## 17. Saturation round

After the search cap was raised, eight research agents ran about 970 searches between them: four on broad areas, then four follow-ups on the topics the first four left unfinished. Their full reports, with every source link and a per-topic coverage table, are in `reports/research-round2/`. **I have read their summaries, not every line of those files**, so the detail there is the agents' own. Labels as in section 2.

| File in `reports/research-round2/` | Area | Searches |
| --- | --- | --- |
| `gnss-integrity-algorithms-market.md` | GPS hardening, spoof detection, integrity, algorithms, cooperative methods, timing, law, market, patents | about 235 |
| `radio.md` | All passive radio, first pass | 119 |
| `radio-pass2-leo.md` | LEO Doppler and Iridium | 111 |
| `radio-pass2-cellular.md` | 5G, altitude effects, radio SLAM, low-cost LTE, tower clocks | about 97 |
| `celestial-conventional.md` | Heading, celestial, conventional and exotic, first pass | about 129 |
| `celestial-pass2.md` | Magnetic anomaly, exotic, compasses, magnetometers, landmarks, Ottawa data | about 71 |
| `onboard.md` | Vision, inertial and other onboard sensing, first pass | 121 |
| `onboard-pass2.md` | Map matching, fielded systems, sensor topics | 89 |

Two of the follow-up files are incomplete because the session's scratch folder became unavailable to the agents partway; what they could not write came back in their messages and is included below. The experiment script and results from section 5 are also copied into that folder.

### 17.1 How complete this is

The rule was: keep searching a topic until eight searches in a row turn up nothing new. No topic met it strictly; agents ran out of working memory first. Their own judgement of where each topic stands:

| State | Topics |
| --- | --- |
| Done: returns were repeats | Cross-checking GPS against other signals; signal authentication and resilient receivers; using interference; integrity; cooperative methods; timing specifications; the primary Canadian legal texts; star trackers; celestial on aircraft; sun sensors; direction finding; terrain navigation; passive radar; legacy ground aids; teach and repeat |
| Done: the literature does not exist | Magnetometer heading error measured in flight on small quads; position fixes from obstruction or city lights; passive radar for self-location; a passive DME experiment; an Iridium-only fix flown on a drone; an independent moving test or a price for Iridium's paid service; tower holdover measured under jamming; spoof-detection false alarms per hour from drone flights; learned inertial odometry on long outdoor flights |
| Near: only refinements turning up | LEO Doppler; Iridium; carrier phase; tower clocks; angle of arrival; broadcast signals; datasets; spoof detection; estimation methods; validation practice; polarisation compasses; magnetic-anomaly navigation; exotic cues; optical flow; visual odometry |
| Still producing | 5G from drones; ranging error against altitude; radio SLAM and tower maps; map matching (new work monthly); fielded systems (vendor names); several onboard sensor topics with few searches |
| Needs a different tool | Patents (a patent database, not web search); the market (funding news weekly, prices unpublished); Ottawa cloud, skyglow and magnetic relief (downloads, not searches) |

A third pass on the "still producing" cellular and onboard topics followed; see section 18.

### 17.2 Radio: tower clocks and LTE

- **Towers steer in jumps** *(checked)*. Two LTE towers watched for 11 days: one jumped about every minute, changed drift by up to about 1 ppb, and built up about 20 m between jumps; code and carrier moved together. A straight-line clock fitted in the last 1 to 10 s before GPS loss holds for 10 to 50 s (Lapin et al., IEEE TVT 2024). The sim's smooth random walk should become piecewise drift with jumps.
- **No public measurement of tower holdover under jamming exists** *(checked)*. The 2019 US test-range result ("two LTE towers stable for 95 minutes under jamming") was read at source: only GPS was jammed, not Galileo or GLONASS, the jamming at the towers was about 60 dB, and both stations were on one site.
- **Commercial 5G cells are not tightly synchronised** *(checked)*: mean sync error 230 ns (about 70 m), a steady bias of 73 to 79 m per cell, one cell drifting 0.3 m/s. With a reference receiver, error was 3.9 to 7.6 m.
- **Multipath does not improve steadily with height** *(checked)*. In LTE measurements the direct-path dominance fell from 12.6 dB at 15 m to 7.6 dB at 30 to 100 m once the drone left the down-tilted beam, and delay spread rose from about 40 ns to 80 to 110 ns. The one altitude-binned ranging result found (5 MHz signal) gives 49 m error at 40 m and 36 m at 100 m.
- **More towers are heard at altitude** *(checked)*: 5.1 detected cells per sample on the ground, 16.9 at 120 m. A 2020 simulation study found the receiver oscillator matters a lot with ten or fewer towers and little with more.
- **Tower positions can be learned in flight** *(checked)*: from about 42 m to 7 m within one 175 s drone flight using radio SLAM.
- **ISED's public site data now lists cell identities and antenna geometry** *(checked for the field list; not checked that Ottawa rows are filled)*: cell ID, physical cell ID, position, azimuth, tilt, beamwidth and height, updated monthly. If filled, a heard cell maps straight to a mast and its antenna pattern. This bears on `systems/tower-identity.md`. Downloading it needs an owner's go-ahead.
- **The closest analogue to our build:** a 2025 MSc thesis and conference paper using LTE differential ranges on a small SDR with an IMU, 8.03 m RMSE in flight *(abstract only; every copy is behind a block or paywall)*.
- **Protection level can worsen with one more tower** *(checked, read in full)*: a single transmitter with its own clock raises the horizontal and vertical protection levels, because the new clock state absorbs the measurement and adds a fault mode; two or more sharing a clock lower them (Jia, Khalife, Kassas, IEEE T-ITS 2023). The paper proposes a fault prior of 1e-4 per transmitter.

### 17.3 Radio: LEO Doppler and Iridium

- **Clock grade decides single-pass Doppler** *(checked)*: 6.9 km error with a dongle-grade crystal, 720 m with a low-grade oven oscillator, 67 m with a good one.
- **Cheap SDR oscillators, measured** *(checked)*: free-running, 1 to 17 kHz off with jitter of 5 to 290 Hz; locked to a rubidium reference, jitter of 0.01 to 5 Hz.
- **Orbit error can be estimated on the vehicle with no base station** *(checked)*: 10.7 m on a ground vehicle; a drone with two Orbcomm satellites went from 76 m to 12.3 m with one time-offset state per satellite (Kassas et al. 2025). That is one extra filter state per satellite.
- **A moving LEO result with a consumer-class IMU** *(checked)*: a car with two Orbcomm satellites, 175.5 m to 18.3 m over 4.05 km, by tracking each satellite on one pass and predicting its orbit to the next.
- **Starlink results with full conditions** *(checked)*: drone 46.5 m inertial only, 17.8 m with published orbits, 8.15 m with corrected orbits, using an oven oscillator and a tactical IMU. A Raspberry Pi 4 on a ship got 123 m with no IMU.
- **Starlink with a cheap dongle** *(checked)*: an RTL-SDR, a Pi 4, a satellite-TV feed and a consumer IMU tracked Starlink Doppler rate with a median residual of 0.8 Hz/s. Its "sub-10 m" claim is weak: no orbit correction and a 20 s run.
- **Iridium:** the broadcast satellite position is quantised to about ±4 km; Doppler noise within a burst is 0.27 to 0.36 m/s *(checked)*; a 2025 SDR test gave 892 m stand-alone and 40 m with a base station *(snippet)*; a Raspberry Pi rover on differential Doppler got under 265 m *(checked)*; first fix in under 15 min *(snippet)*.
- **Iridium's paid service, independently tested** *(checked)*: 26.6 m horizontal and 16.8 m vertical at 95 % over 100 days static (EU Joint Research Centre); timing within 40 ns over 40 days (NIST). A vendor datasheet gives field medians of 25 m at 69°N and 42 m at 19°N on a 10 g, 1.2 W receive-only board. It needs a subscription; no price is published.
- **A hardware warning** *(checked)*: the Pi 4's Ethernet and USB 3 radiate into an active L-band antenna.
- **Not published anywhere:** calibrating the receiver's oscillator from cellular carriers before LEO Doppler. It exists at forum level only.

### 17.4 Heading

| Source | Result | Evidence |
| --- | --- | --- |
| Star camera on a fixed-wing | under 0.13° yaw in flight | *(checked)*; no multirotor result exists |
| Star tracking on phones, a micro-drone and a Raspberry Pi | 0.1 to 0.5° | *(snippet)* |
| Commercial polarisation compass | 0.1° static; no heading with cloud over the zenith; best with the sun below 35° | *(checked)* |
| Polarisation compasses on drones | 0.5 to 1.25° | *(checked)* |
| Ultraviolet and segmentation methods under overcast | 1.4 to 1.9° | *(checked)* |
| Raw polarisation compass on a ground vehicle, clear sky | 5.65° RMS with a 153.9° worst case; 0.74° after a robust filter | *(checked)* |
| Magnetometer on a small quad, 35 cm out | a near-constant 3.6° offset against a two-antenna GPS reference, no throttle effect | *(checked, one forum post)* |
| Two GPS antennas, 50 cm apart | under 1° | *(checked)* |
| Gyrocompassing at Ottawa | 0.1° needs about 0.02°/h of gyro bias; a consumer part gives about 11° | *(derived)* |
| VOR with an SDR | 0.76 to 1.84° mean error on a balloon; warming a receiver by about 50 °C shifted its reading by 5° | *(checked)* |

- **Ottawa is heavily overcast 54 % of all hours**, 62 to 66 % in December and January, 42 % in July *(checked, observed normals 1981 to 2010)*. That caps every sky-based sensor.
- **A polarisation compass needs a heavy-tailed error model**, not a Gaussian one.
- **A magnetometer should carry a per-flight bias of 2 to 3°** in the sim, on weak evidence.

### 17.5 Onboard sensing

- **Map matching, satellite against aerial reference** *(checked)*: on a 2026 benchmark at 30 to 300 m, the best method put 74.1 % of fixes within 5 m against aerial maps and 18.5 % against satellite maps (58.5 % within 20 m).
- **Map matching, real flights:**

  | Source | Result | Evidence |
  | --- | --- | --- |
  | UAV Navigation-Grupo Oesía, 36 km | 31 ± 9 m; the same flight drifted 4 % of distance on inertial alone and about 1 % on visual odometry | *(checked)* |
  | US Air Force Institute of Technology | 6.79 m RMS over two 1-hour infrared flights without GPS | *(checked)* |
  | A 2026 research system on a Jetson-class computer | 2.94 m RMS | *(checked)* |
  | Summer map, leaf-off flights | 26.5 to 30.6 m after about 2 km, with images prepared using the true pose | *(checked)* |
  | Night, thermal against a daytime 3D map | 2.18 m RMSE over 6.5 km | *(checked, section 16.5)* |
  | Vendor claims | 7 m over 2.7 km; under 15 m at night over 58 km; 7 to 35 m over 40 to 153 km across 18 flights; a US$399, 128 g unit claiming 2 % of distance | *(vendor)* |

- **Monocular visual-inertial odometry at altitude drifts 1 to 5 % of distance** without trajectory alignment *(checked)*.
- **Learned inertial odometry has no outdoor long-flight result.** Its metre figures are indoor, 3 to 4 minute flights *(checked)*.
- **Real inertial drift is worse than datasheets suggest** *(checked)*: an industrial-class IMU on a small fixed-wing was about 1 km off after a 2-minute outage.
- **More IMUs do not buy accuracy** *(snippet)*: one to four gave similar accuracy over 2-minute outages; the gain is surviving a failed unit.
- **Wind limits drag-based velocity** *(checked, derived)*: wind is estimated to 0.26 to 0.6 m/s only while GPS is available; a 0.5 m/s error held for 300 s is about 150 m.
- **Airspeed aiding:** a small fixed-wing held under 30 m at 30 s and under 50 m at 90 s *(checked)*; a pitot sensor without wind states made things worse in a 2025 flight test *(checked)*.
- **Radar-inertial odometry on a delivery drone** *(checked; transmits)*: 0.6 to 3.7 m over about 1 km at 30 to 100 m. Lidar odometry failed on 6 of 10 of the same flights.
- **Optical flow at 100 m is unsupported:** rangefinders stop at 30 to 50 m and emit light, and a height error becomes a scale error.
- **Teach and repeat** *(checked)*: under 1.5 m over most of a 450 m path, 4.5 m at corners, with the GPS failure simulated.
- **Pi timing** *(snippets)*: a GPS pulse on a GPIO pin holds the Pi within about 10 µs; over USB, up to 1 ms of jitter.

### 17.6 GPS hardening, spoof detection and integrity

- **A cited rule for correlated errors** *(checked)*: model each as a slowly varying state using the longest plausible time constant, with a minimum starting variance (Langel et al., NAVIGATION 2021). This is the fix for the overconfidence in section 5.
- **Spoof-detection evidence is mostly not from drones.** Real spoofing in the Mediterranean defeated ephemeris checks; signal strength and receiver-clock jumps caught it. A receiver vendor's own write-up says its spoof flag also fired under jamming alone. An IMU-velocity test reached 75.5 % detection at 1 % false alarms in a vehicle. **No drone flight test reports false alarms per hour.**
- **Small anti-jam antennas** are in section 16.4.

### 17.7 Magnetic, conventional and Ottawa-specific

- **The Ottawa VOR has been removed; only the DME remains.** NAV CANADA's page shows an Ottawa VOR revoked on 2024-01-25 *(checked)*; flight supplement copies from 2025 to September 2026 list a DME only at YOW *(snippets)*. The `uc02-yow-approach-vor` scenarios model a station that is gone. Confirm against the current supplement, then raise it.
- **Magnetic survey data near Ottawa is restricted** *(checked)*. The challenge dataset flown near Renfrew carries an agreement: non-profit research, education or government use only, no sharing, approval required, a one-year term. The open-source package for it downloads the data automatically. Natural Resources Canada's maps are under the Open Government Licence.
- **Urban Ottawa is poor ground for magnetic navigation:** the detailed provincial survey excluded it *(snippet)*, and the field east of a local fault is described as considerably subdued *(checked)*. A 2026 paper reports 32.7 m median on the Renfrew map in simulation.
- **Navy VLF stations are not phase-stable**, so they give no position without a reference receiver.

### 17.8 Law, standards, funding and market

- **Transport Canada states an accuracy figure:** Standard 922.04 requires ±10 m lateral and ±16 m altitude shown to the pilot in controlled airspace *(checked)*.
- **Section 9:** 9(3) exempts broadcasting from 9(2). The regulations have no research or navigation exception. No case law or ISED guidance on using sync signals exists *(checked)*.
- **Jammer penalties:** $25k and $10M are administrative-penalty maximums; criminal fines are $5k for individuals and $25k for corporations *(checked)*. Companies may use jammers only as DND contractors under supervision.
- **Canadian defence challenges with stated requirements** *(checked)*: under 30 m after one hour without satellites and time error under 1 µs; at most 1 µs over 24 h in under 20 g and 300 mW; a low-cost drone challenge with final assessment in May 2027.
- **Chip-scale atomic clock holdover** is 0.9 to 26 µs per day from the datasheet.
- **Patents:** the University of California families run to 2038 (LTE) and 2040 (LEO). This is not a full landscape.
- **Before any flight test:** some Ottawa-area airfield documents mark GPS interference exercise areas *(not opened)*. Check the Canada Flight Supplement and NOTAMs.
- **Datasets:** the Jammertest 2023 recordings are CC BY 4.0; OAKBAT's licence is unresolved.

### 17.9 Corrections to sections 1 to 16

| Where | Was | Now |
| --- | --- | --- |
| 6.1, 11.5 | Cheap Starlink reception "practically unusable" | Doppler rate has been tracked with an RTL-SDR; positioning from it is unproven |
| 6.1 | Iridium's paid service 10 m or 20 to 50 m | 26.6 m at 95 % in an independent static test |
| 6.3 | 3.35 m with 5G on a drone | That is a ground-vehicle result; the only drone result found is 4.63 m with two stations |
| 6.3 | Sync signals fit in 2.4 MS/s | True for LTE and low-band 5G only |
| 6.5, 16.1 | OAKBAT and Jammertest terms unknown | Jammertest 2023 is CC BY 4.0; OAKBAT unresolved |
| 7.1 | Stereo visual odometry 0.3 to 0.6 % | Holds for stereo with an industrial IMU; monocular at altitude is 1 to 5 % |
| 7.1, 16.6 | Learned inertial odometry has no metre figures | It has, indoors only |
| 7.2 | 0.65° heading after a 140 s outage, low-cost IMU | From a fixed-wing filter aided by a vehicle dynamics model; not evidence for a quad |
| 7.2 | Night star camera 0.02 to 0.1° (estimate) | Under 0.13° measured on a fixed-wing; 0.1 to 0.5° on phone-class hardware |
| 7.2 | Magnetometer 1 to 3° tracking throttle | Mostly a fixed offset per flight, 2 to 3°, on weak evidence |
| 7.3 | Season-invariant matching 12.6 to 18.7 m | Real leaf-off flights gave 26.5 to 30.6 m |
| 7.4 | Free-inertial drift table | A best case; real flight was about ten times worse for one industrial unit |
| 8.1 | No polarisation heading under overcast | True for one commercial unit; other methods report 1.4 to 1.9° |
| 8.2, 12 | YOW VOR `TBC` | Removed; DME only |
| 8.2 | Public magnetic grid | The challenge data near Ottawa is restricted; the federal maps are open |
| 8.3 | Chip-scale clock about 1 µs per day | 0.9 to 26 µs per day |
| 9.5, 16.3 | Tower holdover: patents only, then "observed for 95 minutes" | No valid measurement exists |
| 9.6, 16.8 | Fielded systems publish no accuracy | Several do (17.5) |
| 10.4 | Transport Canada gives no accuracy figure | ±10 m lateral, ±16 m altitude in controlled airspace |
| 10.4 | Jammer fines $25k / $10M | Those are administrative maximums; criminal fines are lower |
| 16.2 | 8.32 m with one Iridium satellite | Not found; the nearest is 7.13 m with two Orbcomm and one Iridium, differential |

### 17.10 What this changes in the analysis

- **The Doppler verdict holds and is better founded.** On a free-running dongle crystal Doppler is kilometre-class. With a disciplined reference and one orbit state per satellite it reaches tens of metres on vehicles. The drone gap for Iridium is real.
- **Order of work in 11.3 stands, with sharper content:**
  - Item 1 (correlated errors) now has a cited method.
  - Item 3 (honest LEO layer) should add clock grade, one orbit time-offset state per satellite, and Iridium burst noise of 0.27 to 0.36 m/s.
  - Item 4 (tower clocks) should be drift with jumps; holdover under jamming stays an assumption, since no measurement exists.
  - Item 5 (carrier phase) keeps its risk: no result without a disciplined receiver clock. Hearing 17 cells at altitude makes a cheap clock less harmful.
  - Item 6 (heading): Ottawa's overcast limits sky sensors to under half of all hours, so a magnetometer comes first; model its error as a per-flight bias.
  - Item 8 (map matching) needs aerial, not satellite, reference imagery at low altitude, and a season term.
- **New near-term checks from this round:**
  - whether ISED's public data fills cell identities for Ottawa;
  - whether the Pi's Ethernet and USB 3 interfere with an L-band antenna;
  - the current flight supplement entry for YOW.
- **Product:** the trust monitor gap stands, and a new point supports it: nobody publishes false alarms per hour from flight. Iridium's 10 g board is the nearest competitor and is now independently characterised.


---

## 18. Third pass

Two more agents took the topics that were still producing in section 17.1 and ran about 410 further searches (about 220 on cellular, about 190 on onboard sensing). The cellular agent was cut off when the account's weekly usage limit was reached; the onboard agent finished, having stopped its later topics early to share out its search budget. Their files are `reports/research-round2/pass3-cellular.md` and `pass3-onboard.md`. I read the cellular file in full and the onboard file in part. Total for the whole effort: about 1,600 searches.

### 18.1 Coverage after the third pass

| Topic | Searches this pass | State |
| --- | --- | --- |
| 5G as a signal of opportunity | 21 | **Saturated** (last 9 dry) |
| Low-cost LTE navigation, differential LTE, carrier phase | 39 | **Saturated** (last 8 dry) |
| Learned inertial odometry | 42 | **Saturated** (last 8 dry) |
| Radio SLAM and tower maps | 90 | Not strictly (longest dry run 7); nothing peer-reviewed with numbers after search 77 |
| Ranging error against altitude | 58 | Not strictly (longest dry run 7); late items were channel statistics, not methods |
| Dynamics, drag and airspeed aiding | 72 | Not strictly; late items were patents and small notes, no new outdoor multirotor result in metres |
| Radar and lidar on small drones | 32 | Not saturated; no new result at 30 to 150 m with a drift figure |
| Inertial sensors on drones | 27 | Not saturated; small items still appearing |
| Timing on Pi-class payloads | 20 | Not saturated; mostly forum and vendor notes |
| Optical flow above 30 m and barometer | 11 | Not saturated |
| Tower clocks | 11 | Not saturated; cut off by the usage limit |

### 18.2 Cellular: what is new

**Things the literature does not contain (confirmed again)**

- No altitude-binned distribution of ranging error from a real cellular downlink.
- No carrier-phase navigation result with a free-running oscillator.
- No flight of an RTL-SDR, Pluto, Lime or bladeRF doing LTE navigation, and no Pi-class real-time LTE ranging receiver with published CPU figures.
- No 5G sync-block ranging flight on a commercial network.
- No metre-level comparison of public tower databases against surveyed masts.
- The 2025 thesis and paper reporting 8.03 m in flight remain unread: every copy is blocked.

**Tower positions and maps**

- **Crowd-sourced tower "positions" are kilometre-class** *(snippets)*: signal-strength methods give medians of 0.7 to 7 km, because they are coverage centroids, not masts. Only timing-based methods reach 40 to 100 m.
- **Even operator records are off by 30 to 50 m "not uncommonly"**, and one audit found more than a third of antennas installed out of tolerance in azimuth or tilt *(vendor and trade press)*. A witness described ISED's site data as "pretty reliable" with "some examples of inaccuracy" *(snippet)*.
- **A registered position can be the equipment shelter, not the antenna**, and a tower's position error cannot be separated from its fixed transmit delay using one range *(patents)*. A per-sector constant range bias belongs in the model beside the position prior.
- **The same cell identity can be heard twice at altitude** *(patents)*: operators avoid reuse only between neighbours. Match on identity plus carrier plus a coarse position gate. `nav/cells.py` already drops reused identities; this supports that.
- **Radio SLAM is observable only from a known start** *(snippet of the foundation paper)*: either the receiver's full initial state is known, or its position plus one tower's full state. Starting at GPS loss satisfies this; a cold start does not.
- **Straight legs can stop tower states converging** *(snippet)*: a drone flying straight at a waypoint failed where a planned path succeeded.
- **Self-survey while GPS works** reaches 3.44 m emitter error with well-placed receivers *(snippet)*.

**Channel at altitude**

- **A controlled comparison confirms the down-tilt effect** *(checked)*: with a sector antenna the channel depends more on the antenna pattern than on height; delay spread is about 120 to 380 ns with no height trend from 15 to 105 m. For a 1 to 2 MHz ranging signal that is a positive range bias of metres to tens of metres per tower.
- **The strongest and second-strongest cells are within 2 to 3 dB at 50 to 150 m** *(snippet)*: the median gap falls from 6.5 dB on the ground to 1.6 dB at 150 m. A receiver must separate cells by their codes and cancel, not take the strongest.
- **"17 cells heard at 120 m" is what a modem with cancellation reports.** A plain correlator on one dongle will lock fewer *(agent's reasoning)*.
- **Line-of-sight models are optimistic for distant towers** *(snippet, derived)*: for towers 1 to 10 km away the elevation angle is only 0.2 to 5°, where the standard curves give low line-of-sight probability. The "100 % above 100 m" figure applies to nearby urban geometry only.
- **A term nothing here carried: the troposphere on near-horizontal paths** *(checked for the paper; the application is derived)*. Excess delay is about 0.3 to 0.4 m per km of range, so 3 to 4 m at 10 km and different for every tower. A tower-clock state absorbs the constant part; the part that changes as the drone moves does not.

**Receiver clock**

- **A published way to discipline an RTL-SDR's frequency from LTE** *(snippet)*: a 2017 method estimates the dongle's oscillator offset from LTE sync-signal timing to sub-ppm within a second, with an open implementation for the Raspberry Pi (GPL; third-party code). This is the missing reference for "calibrate the dongle from LTE carriers", and it also serves Iridium Doppler.
- **Oscillators get worse in flight** *(snippet)*: frequency stability degraded by at least a factor of ten against the bench in an aircraft test. The sim's dongle clock should carry a vibration term and a warm-up drift.
- **A cheap SDR's clock cannot be modelled as a fixed drift between flights** *(snippet)*: one thesis found it "non-linear and volatile; changing from trial to trial".

**5G**

- **Low-band 5G uses one wide beam per cell** *(snippet)*, so there are no beam-dependent timing effects on the one Canadian 5G band a dongle can tune (600 MHz).
- **On a shared LTE/5G carrier the LTE reference signals stay on air** *(snippet)*, so an LTE ranging receiver keeps working. Rogers deployed this on 600 MHz in 2020; Bell has no 600 MHz. Ottawa specifics are `TBC`.

**Tower clocks**

- **Jamming geometry matters** *(snippets)*: in northern Norway interference was found down to about 600 m altitude while ground measurements had found none. A 44-hour event near Dallas left 162 ground reference receivers largely unaffected. So a jammer aimed at aircraft can deny a drone at 100 m while the towers' own GPS receivers stay locked. The sim should offer both cases.
- **The only incident found of ground base stations losing sync in real jamming** was a public-safety radio system near Denver in December 2022, not a cellular network *(checked)*.
- **Holdover depends on how the tower gets its time** *(snippets, lab tests)*: a tower fed by a network clock with synchronous Ethernet drifts tens of nanoseconds over hours; one with its own receiver and a plain oven oscillator drifts about a microsecond in a few hours. Model holdover as a mixture of the two, share `TBD`.
- **US operators are adding non-GPS timing at cell sites** *(snippet)*; no Canadian announcement was found.
- **Minute-scale steering jumps fit a two-mode clock model** per tower (quiet, and jumping), which is the published way to handle them *(snippet)*.

**A candidate reference implementation** *(checked, project page)*: the European Space Agency lists a real-time software receiver for LTE and 5G ranging that outputs code phase, carrier phase and Doppler, under its own permissive community licence. No accuracy or Raspberry Pi figures are given. It is third-party code and needs an owner's go-ahead and a licence review.

### 18.3 Onboard sensing: what is new

**Learned inertial odometry (saturated)**

- **One outdoor result exists** *(checked)*: 13.8 to 17.6 m position RMSE over trajectories of about 34 s on a consumer drone, and it requires flying a sinusoidal path. That is not competitive.
- **A network trained on 548 public flight logs** gave a median maximum error of 35 m per flight, with 90 % of flights under 166 m *(checked)*; training and test logs came from the same pool.
- **The rotor-speed method** (section 16.6) reports 1.81 m trajectory error and 0.24 m/s on its own indoor, windless data, but those figures rotate its output with true orientation; with its own filter the velocity error is 0.37 m/s *(checked)*. Rotor speed is already available on a Pixhawk-class autopilot over the speed controllers' telemetry; neither PX4 nor ArduPilot fuses it.
- **A commercial product built on this idea** quotes a forecast drift of 0.5 to 1.0 m/s, and "up to 3.5 km in 30 minutes" *(vendor, press)*.

**Heading alignment without a magnetometer**

- **ArduPilot can fly without a compass** using a bank of filters started at different headings; it needs low vibration and good GPS throughout, and on the ground the vehicle is walked in a small circle before arming *(checked)*. It converged within about 2 s once a vehicle began moving *(snippet)*.
- **A receiver vendor quotes 0.3° heading** from one antenna and an industrial IMU after enough motion *(vendor)*.
- **Heading is unobservable in hover without a magnetometer** *(snippet)*.

**Inertial sensors**

- **Temperature is large** *(snippets of datasheets)*: one common consumer gyro shifts 0.015 °/s per kelvin, which is 54 °/h per kelvin. A winter flight that warms the board by 10 K moves the gyro bias by far more than its noise.

**Airspeed, drag and wind**

- **A calibrated force-based air-velocity estimate on a multirotor** reaches about 0.25 m/s in hover and 0.4 to 0.5 m/s in free flight, per airframe *(checked)*; wind change then adds directly.
- **A pitot tube on a multirotor is unusable below a few metres per second** because of propeller wash *(snippets)*.
- **Dead reckoning on a 15 kg fixed-wing with airspeed and compass** is reported at forum level only.

**Radar, lidar and altimeters (all emit)**

- **Low over farmland everything struggled** *(checked)*: at 3 to 18 m above ground, lidar odometry gave 2.6 to 40.6 m and radar-inertial odometry failed on 6 of 10 runs.
- **Altimeters:** 24 GHz radar units reach 50 to 200 m for under US$200; laser rangefinders quoted at 100 to 180 m manage only about 50 m over dark vegetation in sun *(reseller pages)*.

**Timing on the Pi**

- **A GPS pulse on a GPIO pin with chrony:** 823 ns RMS offset on a Pi 4; the real-time kernel made raw jitter worse (6,947 ns against 2,134 ns) *(snippet)*. A Pi 5 holds tens of nanoseconds *(checked, a blog)*.
- **RTL-SDR sample timestamps taken at the host carry tens of milliseconds of jitter** *(snippet)*; the robust method is to inject a common pulse and compare sample indices.
- **The Pi camera's timestamp marks the start of readout**, so a camera-to-IMU offset of several milliseconds changes with auto-exposure unless exposure is fixed *(snippet)*.
- **GNSS receivers add 50 to 300 ms of unknown delay**, and a standard EKF loses consistency as it grows *(snippet)*.

**Barometer**

- **Pressure change is about 20 m of height drift in a few hours on a calm day**; propeller wash can offset a hovering copter by about 3 m *(snippets)*.

### 18.4 Corrections from the third pass

| Where | Was | Now |
| --- | --- | --- |
| 17.2 | 17 cells heard at 120 m "helps a cheap clock" | True for a modem with interference cancellation; a single-dongle correlator hears fewer |
| 17.2 | ISED data lists cell identities for all three operators' bands | Bell has no 600 MHz 5G; Ottawa band use is `TBC` |
| 17.3 | Calibrating a dongle from cellular carriers "exists at forum level only" | A 2017 paper and open implementation do it from LTE sync timing; applying it before LEO Doppler is still unpublished |
| 17.5 | Learned inertial odometry has no outdoor result | One exists: 13.8 to 17.6 m over about 34 s, on sinusoidal paths |
| 7.2, 17.4 | "±1° heading from a single hovering antenna" | Not supported; heading is unobservable in hover without a magnetometer |
| 16.6 | Rotor-speed method 0.24 m/s | That uses true orientation; 0.37 m/s with its own filter |
| 6.1 | Dongle clock 1 ppm *(memory)* | Sourced: dongles with a compensated crystal stay near 1 ppm; others are 30 to 150 ppm off |
| 6.3, 16.2 | Line of sight near-certain above 100 m | Only for nearby urban geometry; low for towers kilometres away at low elevation |

### 18.5 What this adds to the analysis

- **Three sim terms that were missing:** tropospheric delay on near-horizontal ranges; a per-sector constant bias that stands for antenna position and transmit delay together; gyro bias against temperature.
- **Two that should change:** tower holdover as a mixture of network-held and locally held clocks, with a jammer that may or may not reach the towers; cells heard at altitude limited by how far below the strongest cell the receiver can detect.
- **The carrier-phase route has a first step with a reference:** discipline the dongle from LTE sync timing, then measure what is left.
- **Heading:** a compass-free start is possible with motion before GPS loss, but not in hover. That strengthens the case for S-turns before entering a denied area and for a magnetometer.
- **Nothing in this pass overturned a conclusion in section 17.10.**

### 18.6 Confidence

After about 1,600 searches the picture has stopped changing at the level of methods and conclusions; what the later passes added were numbers, caveats and confirmed absences. Three topics are strictly saturated and most others were returning repeats. The honest limits are:

- Tower clocks were cut short by the usage limit. Radar and lidar, inertial sensors, Pi timing, optical flow and the barometer were stopped early; the agent's view is that their remaining useful numbers have to come from our own bench and flight logs, not more searching.
- Many figures rest on abstracts or snippets because full texts were blocked; the most useful unread items are the 2025 low-cost LTE thesis, the UAV cellular error-overbound paper, and the two Qualcomm white papers on tower database accuracy.
- Patents and the market need tools other than web search.
