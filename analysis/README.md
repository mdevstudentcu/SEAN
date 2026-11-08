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

## Viewing a run in Foxglove

1. `pnt sim gps-outage --out data/sessions/demo`
2. `pnt viz data/sessions/demo` writes `data/sessions/demo/viz.mcap`
3. Open that `viz.mcap` in [Foxglove](https://foxglove.dev) (`Cmd/Ctrl+O`, or drag it in). To see raw measurements too, select it together with the session file.
4. In the Layouts menu choose **Import from file...** and pick `analysis/foxglove-layout.json`.

The layout shows true (green) and estimated (orange) position on a map with the towers, error against HPL, towers heard, fault and alarm state, and status, flags and lost towers over time. The clock in the viewer reads about ten years early, because logs use GPS time and the viewer treats it as Unix time. Plots fill in as the file loads. Foxglove is our internal viewer; the operator display is the dashboard (ADR-0010).

Rules: every figure's caption names its scenario (or session) and commit (REQ-10). Figures go in `results/`; bulky run data in `results/runs/` (ignored). Images that only back a PR description go in `pr-evidence/<n>/` (`systems/quality.md`).
