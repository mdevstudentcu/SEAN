# Analysis

Scripts that turn scenarios and sessions into the figures and tables we present.

- `pnt eval <scenario> --runs N`: Monte Carlo summary
- `pnt results`: regenerates the results table in `systems/verification.md`
- `pnt plot <session.mcap>` (`just plot`): for one estimator in the session (`--estimator`, default the first `/nav/*` topic), writes to `results/<session>/`:
  - `error.png`: horizontal error and HPL over time, fault windows shaded (jamming zones where the truth is near the jammer), alarm flags marked
  - `stanford.png`: HPL against true error with the nominal, misleading, hazardous and unavailable counts (`--alert-limit`, 50 m TBC)
  - `trust.png`: per-source trust over time
  - `time.png`: clock error and ±1σ, only when the estimator estimates the clock
- Planned: ablation table (REQ-06), timing holdover from real sessions

Rules: every figure's caption names its scenario (or session) and commit (REQ-10). Figures go in `results/`; bulky run data in `results/runs/` (ignored).
