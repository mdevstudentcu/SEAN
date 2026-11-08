# ADR-0015: The simulation is calibrated against real measurements

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** team
- **Traces to:** REQ-01, REQ-02, REQ-04, REQ-10, mentor Q4 (`mentor-qa.md`)

## Context

Mentors accept simulated or injected spoofing and interference, but "be clear in the architecture how the SIM aligns to reality". Today every error parameter in `sim/scenarios/*.yaml` is a datasheet or literature placeholder marked TBC.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Pure simulation, literature parameters | Fast | Judges can't tell whether results transfer to the real world |
| Calibrate each sim model against real recordings, and run attacks on real sessions too | Results are anchored in measured behaviour; gaps are explicit | Needs real sessions early (RF survey, static and walk logs) |

## Decision

Every simulated error model carries the provenance of its parameters and is checked against real recordings; attack results are shown on both pure-sim and real-sessions-with-injected-faults.

## Consequences

- Each sim parameter is labelled `datasheet`, `literature` or `measured` (with the session that measured it) in the scenario YAML or the model's docstring.
- For every source we capture in the real world, we compare simulated and real residual distributions (same statistic, same plot) and record the gap in `verification.md` → *Sim validity*.
- Where we cannot measure (Iridium, crewed aircraft), we say so and explain the bound we used.
- Reopen if a trusted lab becomes available for conducted (cabled) spoofing tests: real receiver behaviour under attack would replace part of the simulated attack model.
