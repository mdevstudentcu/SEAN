# ADR-0046: Carry the slow part of a radio's LTE error as a state, so the bound stays honest after GPS loss

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** the two owners (each point below is theirs to accept or change)
- **Traces to:** REQ-02, T5 (ADR-0034), ADR-0015, ADR-0036, ADR-0038, ADR-0039, #222, #226, #228

## Context

T5's figure (#222): on the drone leg the true error was above HPL in 43.7 % of epochs for `ekf` (sim, seeds 0–49), 75.0 % on a held GNSS jump. REQ-02 and T5 ask for ≥ 99.9 % with no hazardously misleading epoch (`TBC`).

Diagnosis (#226, sim, tuning seeds 1000–1049 only; numbers in `analysis/results/honest-bound/summary.md`, *Diagnosis*):

1. **`ekf` believes the 2 m the records report.** The true range error is 50 m white plus 50 m Gauss-Markov multipath (30 s) (`challenge-drone`, `TBC`). The gate rejects about 95 % of LTE records after GPS loss and each one it accepts at 2 m collapses the covariance: mean horizontal NEES in the hundreds against 2 for an honest filter. That is the 43.7 %. Learned noise (ADR-0039) addresses it.
2. **`ekf-learned-noise` still takes the whole error as white.** Its learned variance is right in size, but an error correlated over 30 s is averaged down as if every 1 Hz record were independent, so the stated covariance shrinks below the error as the outage goes on: on `challenge-drone-outage` (1 carrier), error above HPL in 2.66 % of epochs from GPS loss, 22.3 % in the worst run, mean horizontal NEES 7.1, NEES over K² on 5.5 % of epochs. With the slow error as a state: 0.43 %, 8.3 %, NEES 2.8, 0.78 %. `ekf-calibrated-learned-noise`, which already carries a multipath state per emitter, is at 0.04 % on the same entry and seeds.
3. **`realistic-long-outage` (#228): our clock in the ranges, not the barometer.** That set puts our receiver clock (20 ppb) in every range and `ekf` does not model it (`pseudorange_receiver_clock` off), so the tower clocks and then the position take its drift: error above HPL in 91 % of epochs after GPS loss. Modelling it brings that to 7.7 %, and the slow error as a state to 0.36 %. The barometer's untold 1 m bias changes no horizontal number (bias sigma 1 → 0: identical); dropping its records before the filter (paired draws) lowers `ekf`'s error a little only because the free vertical then absorbs part of the unmodelled clock, and raises it once the clock is modelled. #228's ablation removed the barometer from the sim, which changes every later source's draws.
4. **What is left:** the worst runs (3 of 50 tuning runs above 1 %) escape when the position is already 1 to 1.4 km off and new cells are first heard: their clocks are initialised at the wrong position and a few of their ranges then pull the covariance in (a linearisation-point problem). Starting their slow state at its learned share did not help (0.59 %, worst 8.6 %; not adopted).
5. **Not the cause:** coasting process noise (the circuit's acceleration matches `q_accel` = 1 m/s²/√Hz within a factor 2.2 in variance at 20–60 s; 1.5 closes the worst runs on tuning seeds, worst 3.2 %, but costs 12 % in p95 error and puts tightness at 3.00: the trade-off rows in the summary), tower clock noise (q_emitter 0.2 → 1 m/√s changes little) and the multiplier (K_H = 5.33 is right if the covariance is: NEES is near 2 once the slow error is a state).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Keep `ekf-learned-noise` as it is | Nothing new | Bound escapes on 1 and 6 carriers (2.7 %, 0.2 % from loss; worst runs 22 %, 1.8 %) |
| B. Inflate HPL (bigger K) after GPS loss, calibrated on tuning seeds | One number | Hides a model error; empirical; fails where the averaging is longer than tuned |
| C. Larger coasting process noise | Physical knob | Not the term that is wrong; inflates HPL everywhere (tightness above 3 with C + D) |
| D. Carry the slow part of a radio's range error as a Gauss-Markov state per emitter (the tower error model's multipath state), sized in the stated ratio to the white part | The model the sets state; no empirical factor; the learned variance is split, not added to | Two settings (`TBC`); one more state per heard emitter |

## Decision

Option D, **opt-in**: `ekf-honest` = `ekf-learned-noise` with `multipath_ratio` 1.0, `multipath_tau_s` 30 s and our clock in the ranges (`pseudorange_receiver_clock`) where the records carry it (`ekf.HONEST`), and `ekf-honest-guard` with the jump guard (ADR-0038). It is the filter half of ADR-0036's option C, sized from the challenge sets' placeholders until real records carry their correlated part.

## Consequences

1. **`multipath_ratio` = 1.0 (`TBC`):** slow / white sigma of a radio's range error, the sets' 50 m / 50 m (`challenge-drone`, `realistic`; the same placeholder `CALIBRATED` uses). Not fitted to any run. The learned variance is split in this ratio (`range_noise`).
2. **`multipath_tau_s` = 30 s (`TBC`):** the sets' multipath correlation time. ADR-0036 measured an at-rest correlated part levelling off between 1 and 10 s (3 s, `TBC`); the sweep runs 3 s too.
3. **`pseudorange_receiver_clock` on (no value to choose):** the `realistic` and `challenge-approach` sets put our clock in every range. A radio's records (`meta.rx_clock`: every `challenge-drone` and `-timing` record) use their dongle's own clock either way, so on those legs it changes nothing (`tests/test_ekf_honest.py`).
4. **No empirical inflation:** K_H stays 5.33, q_accel 1.
5. **Unchanged:** every default estimator (hashes in the summary), `ekf-learned-noise`, the guard, the hop model and `ekf-calibrated`'s tower model.
6. **Not covered:** an undetected GNSS fault (2 m/s ramp, 5 s meaconing). While GNSS is trusted and wrong, a fault-free bound cannot hold; solution separation (`ekf-mhss`'s monitor) does, at a cost in size (summary, `mhss`).
7. **Sim only.** On real static replays (PR #233, PR #240) every LTE-aided run was worse than no LTE, and learned noise's HPL held on 94 % and 48 % of epochs: new front-end arcs start hundreds of metres from where the last ended, which no part of this model carries. Nothing here says the bound holds on real data.
8. **Reopen if:** a moving capture with GPS sizes the correlated part (ADR-0036); the held-out bars fail on an entry not yet run; a default-on proposal.

## Checks

Filled from `analysis/results/honest-bound/summary.md` at the commit it names.
