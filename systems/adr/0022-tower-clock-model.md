# ADR-0022: Tower clocks are per-site offset and drift, grouped by network builder and learned while GNSS is trusted

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-01, REQ-02, REQ-03, REQ-04, ASM-01, ADR-0015, ADR-0020

## Context

`src/pnt/nav/ekf.py` gives every pseudorange emitter its own clock offset (initial σ 2,000 m, independent random walk of 0.2 m/√s) and no drift state. Nothing ties one tower's clock to another's.

Opportunistic ARAIM shows why that matters for integrity ([Jia, Khalife & Kassas, IEEE T-ITS 24(10), 2023](https://people.engineering.osu.edu/sites/default/files/2023-10/Kassas_Performance_analysis_of_opportunistic_ARAIM_for_navigation_with_GNSS_signals_fused_with_terrestrial_signals_of_opportunity.pdf)). Towers that share a clock term form one "SOP constellation" with one clock state.

- **Theorem 1:** faults in a constellation are detectable only if it has at least two measurements.
- **Theorem 2:** one pseudorange from a new constellation leaves the test statistic unchanged and raises the protection levels.

So each of our towers is a one-member constellation: it adds no fault-detection redundancy and inflates the PL. That is inferred from the theorems and is to be confirmed in sim.

What the clocks physically share:

- **Sectors of one site** share a baseband and oscillator. On one EARFCN their PCIs commonly share `PCI // 3` (a planning convention, not a rule) ([Shamaei, Khalife & Kassas, IEEE TWC 2018](https://escholarship.org/uc/item/5rw6t83d)).
- **Neighbouring FDD sites** are only frequency-locked to ±50 ppb, not phase-aligned ([3GPP TS 36.104 §6.5.1](https://www.etsi.org/deliver/etsi_ts/136100_136199/136104/)).
- **One operator's sites** showed similar clock offsets, different operators did not (Winter et al., cited in [Lapin et al., IEEE TVT 2024](https://spcomnav.uab.es/docs/journals/Base_Station_Clock_Offset_of_Cellular_Measurements_and_Its_Impact_on_Positioning.pdf)).
- **The builder, not the brand, owns the radios.** Bell and TELUS share one RAN, and TELUS builds it in Ottawa ([Inside Towers, 2020](https://insidetowers.com/?p=41263)). Our ISED extract shows 225 TELUS sites against 3 Bell within 10 km. Rogers runs its own RAN. Freedom's assets are being folded into Vidéotron ([CRTC 2025-308](https://crtc.gc.ca/fra/archive/2025/2025-308.htm)). Who built what in Ottawa is `TBC` by the Monday scan.
- **LTE clocks jump.** Over 11 days, one of two tracked towers showed a frequency jump roughly every minute, and a linear clock fitted under GNSS held only for short coasts (Lapin et al. 2024).

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. Keep one independent random-walk clock per emitter (today) | No work | No redundancy (Theorem 2); no drift state, so a free-running tower's linear drift can't be represented |
| B. Per-site offset and drift, a common term per builder, learned while GNSS is trusted | n sites in a builder give n − 1 testable ranges; drift is modelled; the calibration is what makes them testable | A builder-wide fault now moves every site together; the learned prior decays with jumps |
| C. One clock per builder, no per-site bias | Most redundancy | Wrong for FDD: sites are not phase-aligned, so per-site offsets alias into position |
| D. Base/rover differencing only (ADR-0020) | Cancels tower clocks whatever their model | Needs the base hardware; no fallback when the base is down; sim needs a model anyway |

## Decision

Each LTE site (sectors on one EARFCN grouped by `PCI // 3`) gets clock offset and drift states, sites share one common clock term per network builder (TELUS-built for Bell and TELUS, Rogers, Vidéotron/Freedom), and a calibration phase learns them while GNSS is trusted and holds them as a tight prior through the outage.

## Consequences

- **A named common-mode fault per builder.** If a builder's timing source goes into holdover, or a GNSS time spoof captures it, every site in the group moves together. That is the SoOP analogue of ARAIM's constellation fault. It must be a fault hypothesis of its own, with prior P_builder = `TBD`.
- **Each site keeps its own bias.** FDD neighbours are only frequency-locked, so the builder term carries common motion, not a shared offset. Whether a site really follows its builder's term is tested during calibration (constant difference within a `TBD` threshold). A site that fails stands alone.
- **The prior has a shelf life.** Frequency jumps cap how long a learned offset and drift hold. The process noise, the jump model and the hold time are `TBD` from our static capture (ADR-0015). A jump larger than the predicted σ is a per-site fault, not something to absorb.
- **A poisoned calibration is discarded.** The prior is only as good as the GNSS it was learned under (ASM-01). A slow spoof passes the measurement gate, so trust in GNSS is not enough. Calibration is therefore gated and can be rolled back (decided 2026-11-09):
  - **Gate:** the clocks learn only after GNSS has been trusted continuously for `calib_gate_s` (`TBC`, 30 s), and only while the evidence that does not depend on GNSS agrees with it (barometer, our own clock, and later the trust tests of #82 and #83). Tower time never counts as confirming GNSS (ADR-0024).
  - **Rollback:** the filter keeps clock snapshots for the last `calib_rollback_s` (`TBC`, 60 s). When GNSS is flagged, the clocks return to the snapshot from before the suspect window, and everything learned since is discarded.
- **Default.** The calibrated model is opt-in until, with the gate and rollback, it is no worse than per-tower clocks on the realistic scenario set and on every spoof scenario (paired 50-run evals). Then it becomes the default.
- **The sim.** The base scenarios keep independent, drift-free tower clocks as the idealised control. The realistic and worst-case sets model shared builder clocks and site clocks, and the pitch numbers come from the realistic set.
- **Each SDR is its own receiver clock.** A dongle that hears only one site of a builder adds a clock state and no redundancy, so the band plan should give each dongle at least two sites per builder (`TBC` by the scan).
- **Base/rover (ADR-0020).** With the base running, differencing cancels site and builder clocks, and this model is the single-receiver fallback and the sim default. Neither protects absolute time against a wide-area spoof that captures the builders' timing: that stays with the GNSS common-mode hypothesis.
- **Code:** `ekf.py` (#77) replaces `q_emitter` with site and builder states and a calibration phase. Site identity comes from ADR-0023. All new noise values are `TBD` until measured.
- **Reopen if:**
  - the static capture shows no common term within a builder (fall back to per-site clocks with drift)
  - jumps are frequent enough that the prior is useless within the outage lengths we target
  - the scan shows the builder split in Ottawa is not the one assumed here
