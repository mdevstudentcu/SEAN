# Why LTE still loses to no LTE on the moving GPS cut (#214)

Evidence: **replay of real sessions**, GPS cut in software (ADR-0015). `20261111-1806-walk-lte` (handheld walk), `20261111-0151-static-fullsuite2` and `20261111-0233-static-lte-1h` (static), one NESDR on EARFCN 2460. Same cuts and scoring as `walk_gps_cut.py` (#299, `ece3e34`): walk cuts at 100, 418, 495, 818 and 1,049 s; 0151 at 100 to 300 s by 50 s; 0233 at 600 to 3,000 s by 600 s. Median over the cuts, worst cut in brackets, metres. The cuts share one recording each, so they are not independent draws. Privacy: errors, sigma, times, counts and cell names only.

LTE records (front end run from each `sdr_a.cu8`): `-final` is the weak-cell branch's default (`fcf5274`, the same front end code as this branch's default). `-keep15` is this branch (`628e9db`) with `refind_keep_arc_samples=1.5`.

## Answer: no, not on this capture

**With this receiver and the towers heard on this walk, LTE cannot beat no LTE while moving.** The records are not the main limit: the dongle's clock is. Replaced by perfect ranges, the records still lose at 300 s, unless the clock in them is held constant (`walk-oracle.md`):

| Records fed (walk) | 60 s | 120 s | 300 s |
|---|---|---|---|
| no LTE | 21 (51) | 44 (161) | 168 (484) |
| LTE as recorded | 158 (659) | 182 (2,820) | 1,463 (3,017) |
| perfect ranges + the dongle clock + a constant per cell | 14 (299) | 70 (222) | 1,689 (4,740) |
| the same, plus 78 m white noise (ADR-0036's σ) | 36 (296) | 71 (193) | 405 (3,016) |
| **perfect ranges, clock held constant** | **5 (25)** | **13 (74)** | **40 (343)** |
| real ranges less the dongle clock, arc steps taken out with truth | 61 (178) | 78 (197) | 289 (984) |

"Perfect" is the truth range (GPS fixes, interpolated) to the tower. "The dongle clock" is what an `ekf` replay with GPS on throughout estimated. Both are oracles: nothing in flight knows them.

- **The dongle clock moves faster than the towers can pin it.** From that GPS-on replay, at 1 s samples, its offset beyond its own drift changes by (std) 5 m in 1 s, 43 m in 10 s, 148 m in 30 s and 720 m in 100 s. Its drift runs from 71 to 103 m/s (5th to 95th percentile) over the walk.
- **The clock and the position can only be told apart with 3 or more tower positions in view.** With our clock unknown, a 2-D fix needs 3 ranges from different places. Of the walk's 135 windows of 10 s, 33 % heard 3 or more tower positions and 29 % had them at HDOP ≤ 3 (truth geometry; several cells share a site). The rest of the time the clock's wander goes into the position.
- **After the cut the residuals move together.** The `lte` run's per-cell range residual at the truth, less the filter's clock and bias terms, is −21 to +33 m at each cut (filter σ 8 to 26 m). 60 s after the 495 s cut, four cells sit at +604 to +625 m, and the position is 645 m off. The clock and the position drifted together.

**What it would take:**
1. **A receiver clock that holds over the outage.** Perfect ranges with a constant clock give 5 / 13 / 40 m, four times better than no LTE at 300 s. Holding 40 m over 300 s from a known start is about 1e-10 in frequency: an OCXO or better, disciplined while GPS is up. Without perfect ranges this is not measured: the real records with the GPS-on clock taken out still give 152 / 192 / 910 m.
2. **Or 3 or more tower positions with good geometry for most of the outage.** On this walk, 29 % of the time. A drone at height hears more sites. Not measured here.
3. **And the range error itself.** With the clock and the arc steps both taken out by oracle, the real ranges give 61 / 78 / 289 m: still worse than no LTE at every horizon.

## The three leads

- **(a) Arc restarts.** Cell `220` does not lose the signal every 22 s. On the walk (front end at `81e2114`, #306's branch, which gives `220` the same 64 arcs) its track went into `_relocate` 230 times. 163 searches found nothing. 67 found it again, a median 0.92 samples (p90 1.9) from its prediction, and 59 of those started a new arc because the offset was 0.5 samples or more. The search times a cell from one half-frame, which at the walk's SNR is about a sample off. `92` and `204` behave the same (79 and 32 new arcs). Removing the arc steps alone does not fix the cut: all arcs merged gives 133 / 164 / 2,476 m. Arcs aligned with truth give 49 / 166 / 521 m.
- **(b) Before the cut.** The records are told 78 m each (ADR-0036 at 10 Hz). Their innovations with GPS on are 15 to 30 m median per cell, with RMS normalised innovation 0.36 to 0.48: told more than the scatter (scratch replay, `-final` records). The pre-cut p95 rises from 1.4 to 8.4 m with LTE. It does not carry over: LTE before the cut and none after gives 24 / 50 / 139 m, the same as no LTE.
- **(c) Receiver clock handling.** ADR-0047's `observed` mode does not apply to these records. A record with `meta.rx_clock` always uses its own dongle's clock block (`ekf._pseudorange`: `use_rx = name is not None or ...`). That block's model, a wander of 0.5 m/s per √s (drift change std 1.6 m/s at 10 s, 2.7 at 30 s), is about what the GPS-on replay shows while moving: 1.7 and 2.7 m/s (scratch split by motion, `81e2114` records). Over the whole walk, still parts included, 3.4 and 5.6 m/s (`walk-oracle.md`). The clock model is not far off. The geometry cannot carry it.

## Fixes tried (each opt-in)

1. **`refind_keep_arc_samples` (front end, new, opt-in, `TBC` 1.5 samples = the code gate).** A cell re-found within it resumes from the prediction on the same arc, and the code gate finds where it is. Arcs on the walk: `220` 64 → 17, `92` 87 → 23, `204` 38 → 13. On 0233: `92` 105 → 10, `268` 64 → 30.
2. **Geometry hold (#286, existing opt-in):** `lte_max_hdop=3`, `lte_gate_mode="clock"`. A record is used for the clocks and biases only when the cells heard in the last second give HDOP over 3.

| Session | Config | 60 s | 120 s | 300 s | HPL ≥ error |
|---|---|---|---|---|---|
| walk | no LTE | 21 (51) | 44 (161) | 168 (484) | 100 % |
| walk | LTE (default) | 158 (659) | 182 (2,820) | 1,463 (3,017) | 80 % |
| walk | LTE, keep arc | 113 (448) | 206 (709) | 1,609 (2,299) | 81 % |
| walk | LTE, hold | 30 (346) | 123 (332) | 448 (1,012) | 100 % |
| walk | LTE, keep arc + hold | 21 (205) | 53 (784) | 696 (3,100) | 100 % |
| 0151 | no LTE | 0 (3) | 0 (7) | 1 (16) | 100 % |
| 0151 | LTE (default) | 172 (293) | 356 (1,166) | 1,194 (2,248) | 76 % |
| 0151 | LTE, keep arc | 141 (351) | 196 (583) | 321 (538) | 91 % |
| 0151 | LTE, hold | 173 (708) | 830 (1,424) | 2,030 (3,570) | 49 % |
| 0151 | LTE, keep arc + hold | 115 (405) | 175 (813) | 776 (883) | 47 % |
| 0233 | no LTE | 1 (1) | 1 (1) | 1 (3) | 100 % |
| 0233 | LTE (default) | 87 (515) | 96 (1,520) | 690 (2,967) | 89 % |
| 0233 | LTE, keep arc | 65 (295) | 43 (1,244) | 491 (2,776) | 93 % |
| 0233 | LTE, hold | 87 (155) | 51 (1,099) | 238 (3,243) | 89 % |
| 0233 | LTE, keep arc + hold | 56 (128) | 107 (549) | 274 (1,830) | 93 % |

- **Neither beats no LTE anywhere.** Keep arc + hold ties no LTE on the walk at 60 s (21 m) and loses at 120 and 300 s.
- **Keep arc** helps both static sessions at 300 s (1,194 → 321 m, 690 → 491 m) and the walk's worst cuts (3,017 → 2,299 m at 300 s), but not the walk's median.
- **Hold** helps the walk (1,463 → 448 m) and 0233 (690 → 238 m) and hurts 0151 (1,194 → 2,030 m, HPL ≥ error 76 → 49 %).
- Neither is proposed as a default. Static receivers favour no LTE by construction (zero velocity coasts perfectly).

## Unchanged

- Default output: `refind_keep_arc_samples` defaults to 0, and a re-find under 0.5 samples already keeps its arc, so the default path is unchanged by construction.
- The sim: nothing in it imports the front end. All 23 registered estimators on `challenge-drone-outage` and `challenge-timing-outage`, seed 0, hash the same as `6460f32`.

## Commands

```
python analysis/walk_lte_cut_oracle.py data/sessions/20261111-1806-walk-lte --lte-session <-final> --cut-at 100 418 495 818 1049 --bias --out walk-oracle.md
python analysis/walk_lte_cut_oracle.py <session> --lte-session <-final or -keep15> --cut-at ... --variants [no-lte] lte [--opt '{"lte_max_hdop": 3, "lte_gate_mode": "clock"}'] --out <session>-<config>.md
```

`walk_lte_cut_oracle.py` needs `walk_gps_cut.py` (#299) beside it. The front end per session is `process_capture` with the default `Config` (or `refind_keep_arc_samples=1.5`), then `write_session(..., copy_from=<session>)`. The arc-restart counts in lead (a), the innovations in (b) and the clock split by motion in (c) come from scratch scripts that are not committed (a front-end run that logs each `_relocate` result, and an instrumented GPS-on replay).
