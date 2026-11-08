# Analysis

Scripts that turn scenarios and sessions into the figures and tables we present.

- `pnt eval <scenario> --runs N`: Monte Carlo summary
- `pnt results`: regenerates the results table in `systems/verification.md`
- Planned: error-vs-time after GPS loss, Stanford plot (HPL vs error), ablation table (REQ-06), timing holdover plot

Rules: every figure's caption names its scenario (or session) and commit (REQ-10). Figures go in `results/`; bulky run data in `results/runs/` (ignored).
