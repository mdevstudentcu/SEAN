# ADR-0048: A drone's tower map is built with the jump guard, withheld if flagged, and GNSS-derived

- **Status:** Accepted (2026-11-11, owners)
- **Date:** 2026-11-11
- **Deciders:** the two owners
- **Traces to:** REQ-02, REQ-04, ADR-0024, ADR-0034, ADR-0037, ADR-0038, ADR-0041, #96, #173, #253

## Context

P12 (#96, sim only) hands a tower map from a drone with GPS to a ground user without it (`nav/tower_map.py`). The map is learned against the drone's GNSS, so a spoof during the build is in it. #253 measured that (`analysis/p12_spoofed_map.py`, `p12-drone-map-handoff` and its `-spoof-ramp` / `-spoof-jump` variants, sim, `ekf-calibrated` user, map age 0, seeds 0-19; `analysis/results/p12-spoofed-map/summary.md`) and left three questions open:

1. Export policy. Running the jump guard (ADR-0038) during the build rolls the tower clocks back to before a detected jump. Refusing to export (`MapWithheld`) when the drone raised a spoof cue leaves the user with no aid. Both were opt-in.
2. ADR-0024 class of a learned map. Its clocks are GNSS-timed, but the map's clocks and told-position errors are fitted to the drone's GNSS *position*, so a position spoof poisons them as it would GNSS-derived content. ADR-0024 says tower clocks learned while GNSS is trusted are GNSS-timed; it did not consider a map handed to another user.
3. The 2 m/s ramp raises no cue on P12's four towers.

T1 statistic over 0-300 s after the user's GPS loss (ADR-0034), from the summary above:

| Ground user's case | T1 0-120 s (m) | T1 0-300 s (m) | Map withheld |
| --- | --- | --- | --- |
| No aid | 277.7 | 617.8 | - |
| Honest map | 290.5 | 416.0 | - |
| Jump-spoofed map, no guard, no refusal | 594.9 | 705.8 | - |
| Jump-spoofed map, guarded build, exported | 338.9 | 452.3 | - |
| Jump-spoofed map, guarded build + refusal | 277.7 | 617.8 | 20/20 |
| Ramp-spoofed map, any of the three | 635.2 | 751.0 | 0/20 |

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Export whatever was learned (before) | Nothing to decide | A jump-spoofed map costs the user 706 m against 618 m with no aid |
| B. Guarded build only | 452 m against 416 m honest: the rolled-back map keeps most of its value | Hands on a map from a drone that knew it had been spoofed |
| C. Refusal only | A flagged map never leaves the drone | Without the guard the drone flags no jump (0/20 with `ekf-calibrated`'s own detector), so nothing is refused |
| **D. Both: guarded build, and refuse if flagged** | The jump is caught (guard) and the map withheld; an unflagged build is the guarded map | The user loses the rolled-back map's value (618 m, no aid, instead of 452 m at 0-300 s) |

Class of a learned map: GNSS-timed (its clocks' origin) or GNSS-derived (what a position spoof does to it).

## Decision

The P12 map export defaults to option D: the drone builds its map with the jump guard on and exports that map, and withholds it (`MapWithheld`) if the guard latched or `spoof_suspected` fired during the build; a learned tower map is GNSS-derived in ADR-0024's classes.

## Consequences

- **Code:** `tower_map.learn` runs the jump guard by default (`tower_map.BUILD`), and `learn` and `export` refuse a flagged build by default. `jump_guard=None` and `refuse_flagged=False` turn each off, for analysis only (`p12_spoofed_map.py` uses them for its comparison rows).
- **Dependency:** `integrity.dependency` tags `TOWER_MAP` as GNSS-derived (a prior, not an ICD source), and `tag_of(m, priors=[TOWER_MAP])` gives the class of a reading used against the map: GNSS-derived. Nothing that uses a map counts as GNSS-independent evidence. `TowerMap.dependency` returns the class. MHSS does not pass the map's prior yet; no registered estimator uses a map.
- **Scope:** P12 only. The jump guard stays opt-in for every registered estimator (ADR-0038), and no default estimator output changes.
- **ADR-0024 refined:** its consequence that tower clocks learned while GNSS is trusted are GNSS-timed still holds for a filter's own calibration. A map handed to another user is GNSS-derived.
- **Remaining gap:** a slow spoof the drone does not flag is still handed on. The 2 m/s ramp on P12's four towers raises no cue: the jump guard sees no step, `ekf-calibrated`'s detector does not fire, and the tower monitor (ADR-0037) needs at least five sites (`min_sites = 5`), so it has no opinion. Its map costs the user 751 m against 416 m honest. More sites per drone, for example from carrier hopping (#173, ADR-0040), would give the monitor an opinion. A ground user that checks the map against its own towers is not built.
- **Reopen if:** a detector catches the slow ramp on four towers, the guard's false-latch rate on honest builds withholds useful maps, or real tower data shows the guarded map's rollback is not clean.
