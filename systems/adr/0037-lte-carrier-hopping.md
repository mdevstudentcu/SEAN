# ADR-0037: LTE carrier hopping with one dongle is a modelled option and a study leg, not part of the benchmark

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** team (the owners accept or change each point below)
- **Traces to:** REQ-01, REQ-10, UC-01, ADR-0015, ADR-0018, ADR-0022, ADR-0023, ADR-0030, #173

## Context

The drone leg of the challenge set (`challenge-drone`, ADR-0030) hears one carrier, Rogers EARFCN 2460. #173 asked how much more one RTL-SDR would hear, and how much better the outage error would be, if it dwelled on several carriers in turn. PR #179 added that to the sim:

- `sim/lte_front_end.py`: `cells_from.earfcn` may list several carriers, with a `hop: {dwell_s, reacquire_s}` block. One dongle and one dongle clock dwell on each carrier in list order. No records in the first `reacquire_s` of a dwell. At an epoch only the dwelled carrier's sectors are on air (hearing, near-far floor, one cell per PCI and SNR within that carrier). `arc` stays 0 across dwells.
- `scenario.tower_groups`: every sector of a registered eNB, on every carrier, shares one site clock, multipath, dropout and table position error.
- A new environment, `sets/challenge-drone-hop.yaml`: `challenge-drone` with 13 carriers.
- A study script, `analysis/hopping_study.py` (first named `accuracy_budget.py`; renamed so it does not collide with the per-term accuracy budget ADR-0034 asks for, PR #178).

Three things in it are engineering choices with no decision behind them:

1. **One clock per eNB across carriers.** ADR-0022 defines a site as "sectors on one EARFCN grouped by `PCI // 3`". The sim already keys a site by registered eNB ID on one carrier. Hopping extends that: the sectors of one eNB on different carriers share one clock. One baseband serving several carriers would do that. Separate radio units or basebands per band on one mast would not. Nothing we have measured says which.
2. **The dwell and dead time.** See *Values* below.
3. **Where the leg sits.** Every file in `sets/` joins `pnt results` (ADR-0030 point 10) and the per-combination tests. The `challenge-` prefix makes it read as part of the benchmark set.

The payload cannot hop today:

- **Recorder:** `payload/sdr.py` runs `rtl_sdr -f <freq>` for the whole capture and writes `hops` empty ("one carrier per capture").
- **Front end:** it can read a hopped capture. `frontends/lte/capture.py` splits a capture at the sidecar's `hops` (ICD-session), and `frontend._start` continues a cell's arc across a retune when the re-found timing is within 3 sigma + 2 samples of the prediction. That has been tested only on synthetic baseband (`tests/test_lte_frontend.py::test_band_hop_tracks_each_carrier_and_continues_the_arc`, one hop out and back).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Drop hopping from the sim until the payload can hop | Nothing modelled that we can't record | Loses the only estimate of what hopping is worth, which is what decides whether to build it |
| B. Hopping as a modelled option, and `challenge-drone-hop` as a study leg reported apart from the benchmark | Answers #173 now; the benchmark stays what the payload can record; single-carrier scenarios are unchanged | One more environment in `pnt results` and the tests; its numbers can be mistaken for benchmark numbers unless labelled |
| C. Make hopping the drone leg (replace 2460 alone in `challenge-drone`) | The benchmark shows the most the hardware could hear | Every `challenge-drone` result changes; the benchmark then claims a capability the recorder lacks and that no capture has shown |

## Decision

Option B: carrier hopping stays in the sim as an option (`hop:`), and `challenge-drone-hop` is a study leg that does not count toward the ADR-0030 benchmark until the payload can hop and a hopped capture has been checked against the model.

## Consequences

Each point is proposed; the owners accept or change it.

1. **Not in the benchmark.** T1 to T3 are presented from `challenge-drone`, `challenge-timing` and `challenge-approach` only (`tests/test_challenge_set.py` `LEGS`). The set registry cannot leave the file out: every `sets/*.yaml` is in `pnt results` and in `tests/test_scenario_sets.py`. So its rows appear in the results table of `verification.md`, labelled by name (`challenge-drone-hop-*`), and the *Sim validity* table there marks it as a study leg. Wherever a hop number is shown, it says "sim, study leg, the payload cannot hop yet". Renaming it out of the `challenge-` prefix is the alternative. That would also take it out of `tests/test_tower_clocks.py`'s shared-clock group, which it needs, so it is not proposed.
2. **One clock per eNB across its carriers: `TBC`.** Held as an assumption, not a finding. The check is a static capture hopping two carriers of one eNB: is the difference of the two carriers' clock terms constant within the noise? If not, each (eNB, carrier) gets its own site clock, and the study is re-run.
3. **Values, all `TBC` (ADR-0015):**

   | Value | In the leg | Source |
   | --- | --- | --- |
   | Hop set | 13 carriers: 2460, 5145, 5255, 2535, 5035, 5085, 5205, 5060, 68611, 68661, 2560, 68711, 68761 | Every unflagged carrier of `data/reference/lte-scan-list-ottawa.csv`, in that file's order (sites within 3 km). Flagged carriers stay out until a capture confirms them |
   | `dwell_s` | 1.0 s | Unsourced: chosen so records come at the drone leg's 1 Hz. The study also runs 0.5 s and 2 s at 4 carriers |
   | `reacquire_s` | 0.15 s | `settle_s` 20 ms and `acq_ms` 80 ms (`frontends/lte/tracker.py` `Config`, both `TBC`), plus 50 ms allowed for the RTL-SDR's retune over USB, which is not measured |

4. **Single-carrier scenarios are unchanged.** With one carrier, `hop:` and the list form change nothing (`tests/test_sim_lte_hop.py::test_a_single_carrier_scenario_is_unchanged`).
5. **What it would take for the payload to hop:**
   - a recorder that retunes one dongle on a schedule without stopping the stream, and writes each retune's `sample_index` and `center_freq_hz` into `hops`. `rtl_sdr` cannot retune mid-capture. A librtlsdr binding (for example `pyrtlsdr`) would be a new dependency and needs an owner's sign-off;
   - the retune and settling time on the Pi 4B, measured, to replace `reacquire_s`;
   - a hopped capture from a fixed spot, run through the front end, to check point 2 and that arcs continue across dwells of seconds;
   - then an amendment here, or a new ADR, to bring the leg into the benchmark.
6. **Evidence so far (sim only, registry geometry, every value `TBC`).** From `analysis/results/hopping-study/` (seeds 0–19, run at fb62912, which is not in the repo; where it was reproduced is in that folder's `summary.md`):
   - **Told sigma as committed (2 m), every configuration:** median p95 error at 120 s is over 1 km with both filters. Hopping does not fix the overconfidence ADR-0030 raised as an open question.
   - **Told the true noise (if #147 is solved), `ekf`, median p95 at 120 s:** 374 m with 2460 alone (2 masts per 10 s), 83 m with 8 carriers (18 masts), 68 m with 13 carriers (26.5 masts). Every tower within 3 km heard on 2460 gives 64 m (13 masts).
   - **Targets (ADR-0034):** 50 m at 120 s is met on at most 4 of 20 seeds in any configuration, and 25 m at 300 s on none.
   - So in this sim, more masts help only once the filter is told the true noise. Even then, hopping alone does not reach either target.
7. **Reopen if:** a hopped capture contradicts point 2 or the dead time; the recorder learns to hop (bring the leg into the benchmark); or the owners want hopping as the drone leg (option C).

**Open questions:**

- Is a 1 s dwell right for the front end's loop? Dwells of seconds keep the arc in the sim by construction (TBC). The real loop's prediction over a full cycle of n dwells is untested beyond one 0.5 s hop.
- Hop order: the scan list's order, or distinct eNB sets first (the study's alternative order)?
