# Reading the measured-noise ladder (#257)

Evidence: **sim**, a study variant of the drone leg, `ekf` family, seeds 0–49 paired, at `7e50b2f` on g14. `summary.md` is generated; this file is the reading. Choices: ADR-0049 (Proposed).

## What changed between the two columns

Only the LTE white noise: 50 m on every 1 Hz record (assumed) against ADR-0036's law from each record's SNR (measured at rest, 15 static sessions `20261110-*`). Multipath (50 m, 30 s), the tower table error (100 m), dropout, clocks and everything else stay at the leg's assumed values in both columns. The assumed rows give #247's numbers exactly (2,909 / 12,507 / 2,474 / 132 / 111 m at 300 s), so the rebase onto `main` did not move them.

## Result (`ekf`, worst second, 95 % across runs)

- **No row meets either target.** Best: the measured stack with multipath at the at-rest 10 m / 3 s, 51 m over 0–120 s (target 50 m) and 51 m over 0–300 s (target 25 m).
- **The measured white noise moves the stack little:** 132 → 105 m, and the ceiling 111 → 101 m. The leg's 50 m / 30 s multipath, which no capture has sized on a moving drone, dominates both.
- **Multipath is the size that matters:** at ADR-0036's at-rest value the stack halves (105 → 51 m). That value is a floor for a moving drone, not a value.
- **Tower table error does not matter here:** 100, 50 and 20 m give 105, 104 and 107 m at 300 s; the order is not monotonic, so the 3 m spread is not read as an effect.
- **Arc restarts at the post-fix rate and sizes:** 105 → 151 m (300 s). Before the re-acquisition fix, the real GPS-cut replays saw much larger steps (median 874 m, ADR-0044); that front end is not modelled.
- **Half of the hop dwells lost:** 105 → 118 m.
- **Without learned noise, integrity gets worse with the measured white noise** although the 300 s error falls (today 12,507 → 6,604 m, + 13 carriers 11,894 → 11,098 m). Told 2 m, `ekf` has hazardous epochs on 19 of 50 seeds (1 carrier) and 31 of 50 (13 carriers), against 5 and 7 with the assumed noise; HPL bound median 0.31 and 0.08. Why was not examined (a guess: smaller white noise makes the told 2 m look consistent while the 50 m multipath is still there). Learned noise alone (1 carrier) is worse with the measured white noise (2,474 → 4,024 m at 300 s); its prior and memories were chosen on the assumed leg (ADR-0039) and were not retuned.

## Not checked

- `ekf-calibrated`: finished on g14 at the same commit (222.8 min) after this was written and is in `summary.md` and `rows.json`; its rows are not read here. Its assumed rows equal #247's `ekf-calibrated` numbers.
- `ekf-honest` (#251): its branch had not been rebased onto `main` when this study started.
- Two unmeasured sizes moved together (e.g. at-rest multipath with arc restarts): each sensitivity row moves one size.
- A moving capture: every size here is at rest or assumed.
