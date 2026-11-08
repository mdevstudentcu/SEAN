# Simulation plan

- **Status:** Draft
- **Date:** 2026-11-08
- **Scope:** the testing environment only (`src/pnt/sim/`, its scenarios, and the tools for viewing and comparing runs). The navigation filter is out of scope here.
- **Traces to:** REQ-01 to REQ-06, REQ-10, UC-01 to UC-03, ADR-0004, ADR-0010, ADR-0013, ADR-0014, ADR-0015, RSK-02, RSK-04

This plan does not override anything else in `systems/`. New choices below are marked as open decisions until they have an ADR.

## Goal

Build a **practice world for the navigation software**. It pretends to be the drone's sensors, feeds them realistic and sometimes broken data, keeps the true position hidden from the filter, and grades the answers. Anyone on the team can open a run and see what happened.

Realism is judged the way ADR-0015 sets it: **a real recording and a simulated one should produce similar filter errors.** We add detail only where it changes a result or a decision.

## Already on `main`

Do not rebuild these:

- Attack library (`sim/attacks.py`): outage, spoof ramp, spoof jump, time spoof, meaconing, jamming zone, each with a scenario.
- Receiver `clock:` model with clock truth, GPS time and `gnss_health` measurements.
- Transmitter positions in lat/lon.
- The Sim validity table in `verification.md`.

## Main gaps

- The receiver clock does not affect tower readings yet, so every tower shares no common clock error.
- Tower errors are independent from one sample to the next, with no lingering reflection error.
- Towers never drop out, and the filter is always told the true tower position and noise level.
- There are no motion sensor measurements, and flight paths have instant turns.
- Tower locations are synthetic.

## Plan

Target days are `TBC`. Each phase ends with its scenarios opening correctly in Foxglove.

| # | Target | What gets built | Issues | References | Done when |
| --- | --- | --- | --- | --- | --- |
| 0 | Sun | **Base.** Scoring from closed PR #1 is ported in #36 (estimator option, sustained-alarm detection, false-alarm rate, time scoring, NEES, `nominal` scenario). Remaining: NEES/NIS check in CI. Session folders (#2) are owned by Shrikar, not this plan | #10 | | #36 merged; CI fails on an inconsistent filter |
| 0F | Sun–Mon | **Foxglove view.** Map of true and estimated position, error plot, HPL, flags, tower locations and status | #6 | Foxglove schemas | One session opens in the committed layout and shows all of the above |
| 1 | Mon AM | **Core realism.** Receiver clock shifts all tower readings together; separate tower clocks; lingering per-tower errors; tower dropouts; separate "true" and "told to the filter" values for tower position and noise. Every parameter labelled `datasheet`, `literature` or `measured` | new | Khalife & Kassas | Two named tests pass: a receiver clock change moves all towers together, and one tower's clock change moves only that tower |
| 2 | Mon PM | **Scenario library.** `easy`, `realistic` and `worst` sets across the attacks. New GPS-quality cases: still talking but no fix, few satellites but still good, good GPS returning. Sensor degradation | #16, #29 | PX4 GPS tests | Each set runs by name and appears in `pnt results` |
| 3 | Tue AM | **Real-world anchors.** Ottawa tower locations; error ranges bounded from published data; experiment removing one tower at a time on the same route, plus tower count, speed and oscillator grid | #8, #27, new | TU Delft, Khalife & Kassas, AERPAW, MedComNet | Report shows which towers matter most; reference files state source and date |
| 4 | Tue PM | **Minimal Iridium layer.** Iridium NEXT orbits from a TLE snapshot, visibility above an elevation mask, Doppler with a stated error bound; one scenario where it helps through a GPS outage | #15 | ADR-0013, mentor Q5 | One scenario runs with the layer on and off in `pnt eval` |
| 5 | Wed AM | **Motion.** Smooth drone paths with real turns; MPU6050 and BMP280 models including vibration; noise taken from a stationary recording of our own sensor. SITL, vehicle and YOW approach paths if time allows | #9, #14 | Aceinna | `accel_gyro` is available in a scenario, with seeded noise |
| 6 | Wed PM | **Calibrate and freeze.** Each sensor stream can be simulated or replayed from a recording; sim and real residuals on the same plot; attacks injected into real sessions; first comparison replays the same real motion data in both runs | #30, #27 | TU Delft, BYU | Sim validity table updated, final results tied to a commit |

**If time remains:** other signal models (#11), then the gated Sionna RT spike below.

**Sionna RT spike (stretch, gated).** Sionna RT installs with `pip install sionna-rt` and can run on CPU, so the install is not the obstacle. The cost is the scene: a campus model built from OpenStreetMap through Blender (blosm and mitsuba-blender add-ons, materials renamed to Sionna's convention), and its fidelity, since Ottawa building heights are often missing, trees are not modelled and materials are guessed. Conditions:
- Only after phases 1 to 3 are done.
- 4 hours total; stop if a campus scene does not load in Sionna within 2 hours.
- A human owner's go-ahead before installing anything (`AGENTS.md`, third-party code) and an ADR.
- Its per-tower blockage, excess delay and gain shape the statistical tower-error model. Ray-traced numbers are not reported as accuracy results unless checked against our measurements (ADR-0015).

## Foxglove

Foxglove is our internal viewer (ADR-0010). It shows what the simulator and filter did. It is not the operator dashboard (#25).

- **Layout:** `analysis/foxglove-layout.json`, as issue #6 specifies, plus how to load it in the README.
- **Data for the map:** Foxglove's Map panel expects `foxglove.LocationFix` and `foxglove.GeoJSON`. Our records use ENU metres, so true position, estimate and tower locations are converted for display with `pnt.core.frames` (ADR-0008 allows lat/lon for display).
- **Use in every phase:** each new effect gets checked by eye, for example a tower dropping out at the intended time.
- **To confirm:** whether free desktop use needs a sign-in, and what the free plan allows (`TBC`; not yet checked against Foxglove's pricing page).

## What we have at the end

- One command per test, for example `pnt eval realistic --runs 50`.
- A report card for any filter: position error, whether the confidence number was honest, time error, spoof detection delay and false alarms.
- A Foxglove layout that shows any run.
- A clear "before" picture. We expect the baseline filter to do badly on `realistic` and `worst`.
- Charts of which towers matter, which errors hurt most, and real against simulated.
- Every parameter traceable under ADR-0015.

## What this plan does not do

- Improve the navigation filter.
- Build the operator dashboard (#25), which REQ-05 needs and which has no owner yet.
- Fly the drone. SITL stays optional.
- Prove real-world accuracy without real radio data. If the LTE spike (#21) and survey (#20) do not deliver numbers, results must be described as simulation using estimated values.

## References

We reuse ideas and experiment designs, and write seeded code of our own (REQ-10). Downloading or copying anything below follows the third-party rule in `AGENTS.md`: a human owner's go-ahead first, license notice kept, source and license recorded in the PR, nothing copied without a published license, datasets out of git.

| Reference | License | What we take | Limits |
| --- | --- | --- | --- |
| [TU Delft uwb-simulator](https://github.com/SUPfeiffer/uwb-simulator) | MIT | Switching between logged and generated ranges; anchor and noise experiment structure | Picks anchors at random, so the one-tower-removed test is ours. Uses unseeded randomness |
| [Khalife & Kassas, IEEE TAES 2020](https://people.engineering.osu.edu/media/document/2022-10-12/kassas_opportunistic_uav_navigation_with_carrier_phase_measurements_from) | Paper | Receiver and tower clock structure; tower, speed and oscillator grid | Carrier phase, so accuracy figures do not transfer. Known tower positions, GPS at startup |
| [PX4 GPS tests](https://github.com/PX4/PX4-Autopilot/blob/main/src/modules/ekf2/test/test_EKF_gps.cpp) | BSD-3-Clause | Fault cases: fix lost, few satellites, position jump, recovery | Test PX4's own filter internals, so pass criteria are ours |
| [Aceinna gnss-ins-sim](https://github.com/Aceinna/gnss-ins-sim) | MIT | Motion plus constant bias, drifting bias, noise and vibration | Uses unseeded randomness; different coordinate conventions |
| [BYU thesis, Sweat 2025](https://scholarsarchive.byu.edu/etd/10777) | Check BYU terms | Closest low-cost hardware reference | Only the abstract has been read so far. Its figures are whole-system results on its own setup |
| [AERPAW flight + Sionna](https://datadryad.org/dataset/doi:10.5061/dryad.ttdz08m8r) | Check before redistributing | When a link is usable; how far to trust Sionna | Drone transmits, rural site. Signal strength is measured, delays are ray-traced only |
| [MedComNet 2024](https://github.com/Ita97/MedComNet2024_5G_pos_meas) | **None published** | Clear versus blocked error patterns, for comparison | Simulated data. Do not copy its data or code into this repo |
| [Sionna RT](https://github.com/NVlabs/sionna-rt) | Apache-2.0 | Delays, gains and path types along a route | Not yet installed or tested here. Needs an ADR and its own optional install, outside CI |

The [AERPAW LTE recordings](https://ieee-dataport.org/documents/lte-iq-measurement-aerpaw-platform-air-ground-propagation-modeling) are better suited to the capture work (#21, #23) and need an IEEE DataPort subscription.

## Open decisions

| ID | Decision | Proposal |
| --- | --- | --- |
| D1 | Where the Foxglove map data lives | A `pnt viz <session>` step writes a companion `viz.mcap` (LocationFix/GeoJSON, converted with `pnt.core.frames`) beside the session. Foxglove opens both together; `session.md` stays unchanged, so no `icd` PR |
| D2 | Sionna RT | Gated stretch spike only (see *Sionna RT spike*): after phases 1 to 3, 4-hour timebox, owner go-ahead and an ADR first |
| D3 | What `gnss_health` jam indicator means on real hardware | The sim already emits it, but the GPS HAT has no jamming flag (ADR-0014). Decide its real-data meaning with #22 |
| D4 | Owners for #25 (dashboard), #29 (threat model), #11 and #15 | Team to assign |
| D5 | New issues for phase 1 and the tower experiment | Open them once this plan is agreed |

## Needed from others

- LTE timing spike (#21) and RF survey (#20): towers heard, clock drift and range noise.
- Mentors: accuracy, integrity and timing targets (Q1 to Q3 in `mentor-qa.md`).
- The other software owner: review of any `icd` PR.
