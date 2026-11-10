# ADR-0030: A challenge benchmark set, one leg per use case, on records shaped like real ones

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-01, REQ-02, REQ-03, REQ-04, REQ-06, REQ-10, UC-01, UC-02, UC-03, ADR-0015, ADR-0021, ADR-0022, ADR-0023

## Context

Our sets cover the challenge's themes, but their results don't say how the payload would do on real records (#126):

- Sim tower readings carry their own positions and ride the payload clock. Real records carry IDs only, name a dongle clock and wrap every 10 ms. #135 added records of that shape, used by no scenario yet.
- T3 asks for time 10 min after GPS loss. No scenario ran past 360 s.
- ADR-0021 pitches towers as things that fail with GPS. Tower holdover and IMU degradation exist as attacks (#129) on no scenario's menu.
- The shared attack menu's timings fit a 360 s run, and its `tower_clock_step` names `lte:sim1`, which no front-end record carries: it would do nothing, silently.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Keep the `realistic` set as the benchmark | No work | Sim-shaped records; T3 has no number; no holdover or IMU fault |
| B. Change the `realistic` set in place | One set | Every existing result changes and stops pairing with `main` |
| C. New `challenge-*` environments, one per use case, each with its own menu | Existing sets stay byte-identical; each leg is scored on the target it answers | Three more environments to keep; the shared menu doesn't apply to them |

## Decision

Option C: three environments in `src/pnt/sim/scenarios/sets/`, run as `pnt eval challenge-<leg>`, with every value `TBC` (ADR-0015).

## Consequences

Each point is proposed; the owners accept or change it.

1. **`challenge-drone` (UC-01, T1):** the `uc01-drone-circuit` route with front-end-shaped LTE records on Rogers EARFCN 2460, link-budget hearing (#135's defaults) and a dongle clock, and the `realistic` set's error sizes, tower clocks, GNSS, barometer and IMU.
2. **`challenge-timing` (UC-03, T3):** the drone leg's radio environment, value for value, with a static receiver 10 m up beside the origin. The sim has no static trajectory, so it is `loop` at speed 0.
3. **`challenge-approach` (UC-02, T2): synthetic geometry, labelled so wherever its number appears.** `uc02-yow-approach` starts 17 km from Carleton and `lte-cells-ottawa.csv` stops at 10 km, so it keeps uc02's ring of 6 synthetic towers (records shaped as the sim makes them). To still be flying 600 s into the outage, it starts 50.4 km out on uc02's line and comes within 10 km of Carleton only in its last 37 s. Extending the table needs an owner's go-ahead (third-party data) and is not planned.
4. **Run shape:** 60 s of GPS (as #126), a 600 s outage, then 60 s of GPS again: 720 s. So `outage_h_p95_300s_m` (T1) and `outage_time_err_600s_us` (T3) both have values, and recovery is scored.
5. **Own menus** (`shared_attacks: false`, a new environment option; every other set keeps the shared menu): nominal, the outage, spoof ramp, spoof jump, time spoof, meaconing, a jamming zone where it fits the route (not the static receiver), and, while GPS is out, a tower clock step on a real emitter ID, tower holdover, an IMU bias and barometer drift. GNSS attacks start at 150 s as on the shared menu, so T4 times compare with the other sets. The other faults start 120 s into the outage (`TBC`), so their effect is measured apart from the GPS loss.
6. **Reported sigma (drone and timing legs):** the records report `told_sigma_m` 2.0 m (`TBC`), the range noise PR #133's dense check measured on tracked cells, while the true noise is the `realistic` set's 50 m plus multipath. That is what real records are expected to say: the front end's sigma comes from timing statistics and can't see multipath (#118).
7. **No wrong-table case in the set.** Table position error per eNB (`told_position_sigma_m`) is in the environment. A moved, missing or unregistered tower needs machinery the sim lacks; PR #133's harness (`analysis/lte_real_geometry.py wrong-table`) covers it.
8. **Amendment to ADR-0022.** Its *Consequences* read: "The base scenarios keep independent, drift-free tower clocks as the idealised control. The realistic and worst-case sets model shared builder clocks and site clocks, and the pitch numbers come from the realistic set." The `challenge-*` sets also model shared builder and site clocks. ADR-0022 itself is not edited; `tests/test_tower_clocks.py` excludes `challenge-*` with `realistic-*` and `worst-*`.
9. **What it replaces:** once the owners accept this ADR and package 5's baseline exists (#126), T1 to T3 are presented from the `challenge` legs, and the `realistic` set's numbers become the comparison. Until then, nothing we present changes.
10. **Cost:** a set added to `sets/` joins `pnt results` (every bundled scenario) and the per-combination test in `tests/test_scenario_sets.py`.

**Open questions:**

- **The reported sigma (point 6) may make every filter overconfident.** In the first run (#136's PR) the filters rejected the LTE records at this sigma and the drone leg's error equalled the same run without LTE. Keep 2.0 m as the real-records case, or also score a leg told the true noise? Should #118 size the error model apart from the reported sigma?
- **60 s of GPS before the outage** (#126) leaves `ekf-calibrated` 30 s to learn the tower clocks after its 30 s gate (ADR-0022). Longer?
- **The approach leg's start** (point 3) is ours, not uc02's, and every tower is in one direction for most of the leg. Keep, or place synthetic towers along the route?
- **`pnt eval challenge`** (as #126 asks) isn't a name today: each leg runs on its own. Add a name for the three, or keep three commands?
- **Detection of holdover apart from the GPS loss** needs the report card to time alerts per fault. Its time-to-alert counts from the first fault, which here is the outage.
