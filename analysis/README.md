# Analysis

Scripts that turn scenarios and sessions into the figures and tables we present.

- `pnt eval <scenario> --runs N`: Monte Carlo summary
- `pnt results`: regenerates the results table in `systems/verification.md`
- `pnt plot <session.mcap>` (`just plot`): for one estimator in the session (`--estimator`, default the first `/nav/*` topic), writes to `results/<session>/`:
  - `error.png`: horizontal error and HPL over time, fault windows shaded (jamming zones where the truth is near the jammer), alarm flags marked
  - `stanford.png`: HPL against true error with the nominal, misleading, hazardous and unavailable counts (`--alert-limit`, 50 m TBC)
  - `trust.png`: per-source trust over time
  - `time.png`: clock error and ±1σ, only when the estimator estimates the clock
- `python analysis/figures.py --estimator NAME --runs N` (`just figures NAME N`): the four results figures for one estimator, from committed scenarios at seeds 0..N-1 (paired), with the numbers behind them in `summary.md` and `summary.json`. Writes to `results/figures-<estimator>/`:
  - `error_after_gps_loss.png`: error (median, 95th percentile) and HPL against time since GPS loss (REQ-01, T1), on `--outage` (default `realistic-long-outage`)
  - `stanford.png`: HPL against error pooled over `--stanford` (default the `realistic` set) (REQ-02)
  - `ablation.png`: fault-window p95 with all SoOP removed and with each other aid removed (REQ-06)
  - `holdover.png`: clock error and time protection level after GPS loss (REQ-03), when the estimator has a clock
- Planned: timing holdover from real sessions. No real session exists yet; `summary.md` keeps a marked placeholder for them

## Viewing a run in Foxglove

1. `pnt sim gps-outage --out data/sessions/demo`
2. `pnt viz data/sessions/demo` writes `data/sessions/demo.viz.mcap`, beside the session folder. It refuses to overwrite an existing file unless you pass `--force`, and never writes into the session folder.
3. Open `demo.viz.mcap` on its own in [Foxglove](https://foxglove.dev) (`Cmd/Ctrl+O`, or drag it in).
4. In the Layouts menu choose **Import from file...** and pick `analysis/foxglove-layout.json`.

The layout shows true (green) and estimated (orange) position on a map with the towers, error against HPL, towers heard, fault and alarm state, and status, flags and lost towers over time. Plots fill in as the file loads. Foxglove is our internal viewer; the operator display is the dashboard (ADR-0010).

The viz file is stamped in Unix time, so the viewer's clock shows the real date and time. The session file stays in GPS time (ADR-0008), which Foxglove would place about 10 years earlier, so don't open the two together: they would not overlap on the timeline.

Takes a session folder or a bare `.mcap`, which needs an `origin_llh`. If the session has no estimates on `/nav/<estimator>` (a real recording, or a sim run with another `--estimator`), `pnt viz` re-runs that estimator over the measurements, as `pnt replay` does. Truth, error and fault state appear only when the session has them.

Rules: every figure's caption names its scenario (or session) and commit (REQ-10). Figures go in `results/`; bulky run data in `results/runs/` (ignored). Images that only back a PR description go in `pr-evidence/<n>/` (`systems/quality.md`).
