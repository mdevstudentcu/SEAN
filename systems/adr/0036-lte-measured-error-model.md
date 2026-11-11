# ADR-0036: The LTE error model is split into white and correlated parts, sized from real captures

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-01, REQ-02, REQ-10, ADR-0015, ADR-0022, ADR-0030, #147, #173, #183

## Context

Every LTE error size in the sim is `TBC`: 50 m white range noise at 1 Hz, 50 m Gauss-Markov multipath (30 s), tower clock drift 0.0354 m/s per builder and per site, a 0.4 ppm dongle, and records that report 2 m (`told_sigma_m`, `challenge-*`). #147 showed the filters do worse with LTE than without it when the reported sigma is optimistic.

On 2026-11-10 the payload recorded static LTE captures at two spots (one RTL-SDR, no GPS fix): 60 s per carrier, and 1,800 s on EARFCN 5060. `analysis/lte_measured_noise.py` measured what static captures without truth can show. Every number, its session and commit are in `analysis/results/lte-measured-noise/summary.md` (`fdb8fde`; how it was made: `NOTES.md` there). In short:

- **White noise of a 10 Hz record follows SNR:** robust σ 0.63 m at 13 to 16 dB, 2.4 m at −2 to 1 dB, 25 m at −14 to −11 dB; fit σ² = 0.51² + 2.46² / SNR_lin (m). The front end's reported σ is 1.2 to 2.1 times *larger* than this white part.
- **A correlated part the reported σ cannot see:** inside one arc the error grows from the white σ at 0.1 s to S(1 s) of 2.4 to 15 m (median 8.3 m) on the 9 cells with SNR above 0 dB tracked 80 % or more, and to 4.9 to 18 m at 1 s (12 to 23 m at 10 s) in pairs of sectors of one eNB, which share a clock. So it is not a clock: multipath changing at a static antenna, or the tracker's loop. Which one is `TBD`.
- **Tower clocks:** sectors of one eNB drift together within 0.5 m/s at two standard errors (−0.18 ± 0.16 m/s on the 1,800 s capture, 79 pieces, 854 s fitted; three 60 s pairs agree within their errors; two more read −9.8 and −16.3 m/s, each with one cell broken into 15 to 38 arcs, which no shared clock does: a front-end artefact). Between eNBs, the 1,800 s capture gives −1.4 ± 0.9 and +0.9 ± 0.9 m/s (1.5 and 1.0 standard errors); 60 s sessions give 1.6 to 2.4 m/s of either sign at 1.8 to 5.6 standard errors with errors that understate correlated noise: an upper bound of about 2.5 m/s (8 ppb), not a value. The sim's 0.05 m/s (pair) is inside that bound.
- **Clock Allan deviations are bounds only.** The loop-filtered CFO floors at 4e-9 (1 to 50 s) even for a same-eNB pair, so it cannot see the clocks. One cell's timing (dongle, tower, multipath change and tracker together) grows to S(100 s) = 114 m, σ_y 6.6e-9, against the sim dongle's 9.8e-10 at 100 s. Neither may replace `offset_rw_m` or `drift_rw_mps`.
- **Front-end faults** to fix or flag before real records are trusted (#183): 7 of 39 cell tracks have a carrier offset a whole multiple of 200 Hz (1 / 5 ms) from the strongest cell on the same dongle, and per-cell code-against-carrier rate disagrees by −406 to +223 ppb while doppler records report 0.01 to 0.2 m/s; weak cells (SNR below −8 dB) break 19 to 105 times a minute; even the strongest cell starts a new arc every 8 s on the 1,800 s capture (227 arcs), so the structure function inside one arc stops near 20 s; with the recorder's buffer stamps the front end flags 21 dropped-sample gaps (mostly in near-duplicate pairs) that the recorder does not, and the long-lag numbers move by factors of 2 to 4 with and without them.

A static capture cannot show bias (no position), the size of multipath (a static antenna's multipath is an offset the arc constant absorbs), how multipath changes with motion, or another site.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Keep every placeholder | Nothing moves; results stay paired with `main` | 50 m white at 1 Hz is 3 to 10 times what was seen at rest; the 2 m told σ is what #147 showed breaks the filters |
| B. Put the static numbers straight into the sim | Measured, not assumed | A static antenna is the best case: it understates multipath on a moving drone. One afternoon, two spots in one neighbourhood |
| C. Split the model: the front end reports a white σ from SNR and, apart from it, a correlated term; the sim's white noise is set from the measurement and its correlated term is kept as an upper value `TBC` until a moving capture with GPS sizes it | Each part is sized by what can measure it; the filter is told the correlated part instead of a too-small white σ | A meta field and a filter change; sim results stop pairing with `main` |

## Decision

Option C, in the steps below, each proposed for the owners.

## Consequences

1. **Front-end reported σ (10 Hz record):** σ_white² = 0.51² + 2.46² / SNR_lin (m, `TBC`, fit above), replacing `sigma_scale` × the timing statistic. In addition `sigma_corr_m` (10 m, `TBC`: the middle of the 4.9 to 18 m same-eNB S(1 s)) and `tau_corr_s` (3 s, `TBC`: S(τ) levels off between 1 and 10 s) in each record's meta, for the filter to carry as a per-cell Gauss-Markov state, never to average down as white. A 1 Hz consumer is then told about √(σ_white² / 10 + σ_corr²), 10 m for a strong cell, against 2 m today. Needs a front-end test and a change to the ICD's meta list (`icd` label).
2. **Doppler records** from a cell whose carrier offset is more than 100 Hz (`TBC`) from the strongest cell's on the same dongle are flagged `carrier_alias` and dropped by the estimators until #183 is fixed.
3. **Sim (`challenge-*`, `realistic`):** `told_sigma_m` follows (1). `sigma_m` at 1 Hz becomes 10 m (`TBC`, bounded by the measured S(1 s), median 8.3 m over the 9 cells with SNR above 0 dB tracked 80 % or more), labelled `measured: 20261110 static sessions` with the bound stated. `multipath` stays 50 m / 30 s as an upper value `TBC` until the moving capture. Tower `drift_mps` stays `TBC`: the measurement bounds it (≤ 2.5 m/s between eNBs, ≤ 0.5 m/s between sectors) and supports ADR-0022's shared site clock, but gives no value.
4. **What would reopen it:** the moving capture with GPS showing a correlated part much larger than at rest; #183's fixes changing the white σ, the 8 s arcs or the gap handling; a capture with longer unbroken arcs showing a significant inter-eNB drift.
5. **Sim validity row "LTE pseudorange"** (`verification.md`), proposed text: *Current source* "white σ against SNR and the at-rest correlated part: measured (20261110 static sessions, `analysis/results/lte-measured-noise`); multipath size, motion, told-vs-true position, dropouts in motion: TBC"; *Status* `measured` for white σ only, `placeholder` for the rest. **Shared tower clocks row:** *Real check* "sectors of one eNB drift together within 0.5 m/s (2 SE, `20261110-1759-static-out-long-e5060`, 1,800 s); between eNBs ≤ 2.5 m/s, bound only". Not edited until the owners accept.
