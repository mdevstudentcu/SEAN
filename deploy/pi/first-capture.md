# First real LTE capture: checklist (#149)

What the first capture on real towers has to answer, and how. Follow it with the Pi in hand. Commands run **on the Pi in `~/pnt`** unless they say *laptop*. It extends [`RUNBOOK.md`](RUNBOOK.md) section C for one dongle. Nothing in the repo has seen a real LTE capture yet, so every LTE value it replaces is `TBC` today.

## Before leaving

| Check | How | Good |
| --- | --- | --- |
| Pi set up, PPS locked | [RUNBOOK](RUNBOOK.md) section A, all checks. With one NESDR, `rtl_test -t` lists only `0:` | every row of the A4 table good |
| PPS time base | `.venv/bin/pnt pps-check --seconds 30 --out data/sessions/<date>-pps.json` | `"rate_hz": 1.0`, `"pps_selected": true` |
| Deployed from a clean commit | *laptop:* `git status` clean, then `just pi-deploy`. `meta.yaml` `commit` comes from `.pnt-commit` | no `-dirty` in `~/pnt/.pnt-commit` |
| Disk | `df -h ~/pnt/data` | ≥ 14 GB free per hour of IQ (below) |
| Power | 5 V ≥ 3 A for the Pi 4B (ADR-0018). The field power bank is `TBC` (`hardware/bom.md` §4); its draw is `TBD` | runs the capture without throttling (`pnt day1` row) |
| Antennas | GPS active antenna (in hand). LTE antenna for 875 MHz: in hand is `TBC` (`hardware/bom.md` *In hand*: bundle antennas or the Bingfu, 698–960 MHz) | both SMA, LTE antenna vertical and clear of the Pi's USB 3 ports (RSK-06) |

**IQ size.** `.cu8` is 2 bytes per complex sample (`pnt.payload.sdr`, `rtl_sdr` 8-bit I/Q). At the default 1.92 MS/s (`pnt.payload.config.parse_sdr`): 3.84 MB/s, **13.8 GB per hour**, 3.5 GB per 15 min. Open PR #142 reports the payload SD card at 32 GB with 23 GB free (`TBC` until merged): one 1 h capture fits, two do not. Copy off before the next one. The recorder does not check free space before it starts; a full disk ends the SDR file.

## Where and what

| Item | Value | Source |
| --- | --- | --- |
| Spot 1 | Outdoors at Carleton, GPS sky view. No surveyed marker is in the repo: the spot's position comes from `pnt survey` of the capture's own fixes (below). Rogers' nearest eNB on EARFCN 2460 is 30018, CARLETON UNIVERSITY (GLENGARRY HOUSE), 0.18 km from the scenario origin, PCIs 300, 308, 316 | `data/reference/lte-cells-ottawa.csv` |
| Spot 2, if time | Beside a tower: #133 used 150 m along a sector's boresight (`beside_a_tower` in `analysis/lte_link_dense.py`). Glengarry House sectors point 40°, 160°, 260° | same CSV |
| Spot 3, if time | Far from every tower: #133's `far_from_all` (4.7 cells tracked of 57, synthetic). Its coordinates are not printed: `TBD` (Gap 4) | `analysis/lte_link_dense.py` |
| EARFCN first | **2460** (Rogers, 875 MHz, 10 MHz): top of the scan list (19 sites within 3 km, nearest 0.18 km), and the carrier of #131/#133 and RUNBOOK C. Next if time, by `sites_near`: 5145 (742.5 MHz), 5255 (753.5), 2535 (882.5), all TELUS | `data/reference/lte-scan-list-ottawa.csv` (`dl_mhz` gives the `--sdr` frequency) |
| Sample rate | 1.92e6 (default). The front end needs a multiple of 15 kHz and a whole number of samples per 5 ms (`frontends/lte/signals.py`); whether another rate helps is `TBC` | `--sdr ...:rate=` |
| Gain | `TBC`. Without `:gain=<dB>` the dongle runs AGC; the sidecar records `gain_mode` and `gain_db` either way | `--sdr ...:gain=` |
| Frequency correction | leave `ppm` unset (0), so the measured offset is the dongle's own. The front end searches ±5 ppm (`Config.max_ppm`, `TBC`) | `--sdr ...:ppm=` |
| Duration | Short check 120 s (`TBC`), then **3600 s** static, antenna not touched (#21: one hour from a fixed spot) | `--duration` |

## Commands

| Step | Command | Writes |
| --- | --- | --- |
| 1. Short check (Pi) | `.venv/bin/pnt record --platform static --place carleton --duration 120 --no-stream --no-camera --no-fc --sdr a:875e6:rate=1.92e6:dev=0:earfcn=2460 --notes "#149 check, antenna <where>, gain <auto or dB>"` | `data/sessions/<YYYYmmdd-HHMM>-static-carleton/`: `meta.yaml`, `session.mcap` (GNSS, IMU, baro, events), `sdr_a.cu8`, `sdr_a.json` |
| 2. Did it record (Pi) | Summary line `captured: ... rtl-sdr`; in `sdr_a.json`, `"samples"` near 1.92e6 × 120 and `"gaps_suspected": []` | — |
| 3. Cells on air (*laptop*, after the rsync of step 6) | `pnt frontend lte data/sessions/<s>/sdr_a.cu8` | prints one line per tracked cell: `lte:<earfcn>:<pci>`, SNR, CFO in Hz and ppm, seconds tracked, arcs; writes `data/sessions/<s>-lte/` (derived session, ICD-session). If it finds no cell it writes nothing |
| 4. Long capture (Pi) | step 1 with `--duration 3600` and notes `"#149 static 1 h ..."` | as step 1 |
| 5. Day-1 numbers (Pi) | `.venv/bin/pnt day1 data/sessions/<s>` (`day1.sh` assumes two dongles: Gap 6) | `data/sessions/<s>.day1.md` and `.json`: dropped samples, `rate_ppm_vs_host`, PPS offset, CPU, temperature, throttling |
| 6. Copy (*laptop*) | `rsync -av pi@pnt.local:~/pnt/data/sessions/ data/sessions/` | — |
| 7. Front end (*laptop*) | `pnt frontend lte data/sessions/<s>/sdr_a.cu8` | `data/sessions/<s>-lte/`, with the original's GNSS, IMU and baro records copied in. Prints the real-time factor; time for 1 h is `TBD` |
| 8. Precision (*laptop*) | `.venv/bin/python analysis/lte_static_capture.py data/sessions/<s>-lte` | table to stdout, per cell: SNR, reported σ, σ of the difference to the strongest cell at 10 Hz and 1 s, ratio achieved/reported. Needs ≥ 2 cells on the dongle |
| 9. Identity (*laptop*) | `pnt replay data/sessions/<s>-lte` | prints the estimate count; warns `LTE cells: used N records, dropped {...}` (by `unknown`, `out_of_range`, `collision`) if any record did not match the table |
| 10. Spot position (*laptop*) | `pnt survey data/sessions/<s>` | `data/sessions/<s>.survey.yaml`: averaged fix and `sigma_m` (`TBD` under four 10-min batches) |

Without uv, `pnt` is `.venv/bin/pnt`. `pnt record --no-stream` needs no keys; to watch live, set up the [keys](RUNBOOK.md#keys-once-per-host) and drop `--no-stream`.

## What to read off, in order

| # | Question | Number | Where it comes from | `TBC` it replaces | What changes our plan |
| --- | --- | --- | --- | --- | --- |
| 1 | Cells tracked at a known spot, and how far below the strongest | count of `lte:2460:<pci>` lines; SNR of each minus the strongest | step 3/7 summary. Cells not tracked can't be seen: Gap 4 for the predicted count at this spot | `LinkBudget.floor_db` −13 dB and `min_snr_db` (`src/pnt/sim/lte_front_end.py`); `MAX_RANGE_KM` 10 km (`src/pnt/nav/cells.py`); tracker regression guards (`Config` in `src/pnt/frontends/lte/tracker.py`) | 1 cell at Carleton matches #133's synthetic case (1 of 24), where LTE added nothing over no LTE: take #131's options to the owners. More cells than #133 predicts: the near-far floor is pessimistic; say so in #131 |
| 2 | Reported σ against the spread seen | `reported σ`, `diff σ 10 Hz`, `ratio` | step 8 (≥ 2 cells; one cell: Gap 1) | `Config.sigma_scale` 1.5 (`tracker.py`); sim `told_sigma_m` (#147) | ratio > 1: `sigma_scale` is too low (the script's own reading). Reported σ far below the observed spread confirms #147 on real data |
| 3 | Dongle clock: frequency error and wander | `rate_ppm_vs_host` (one fit per capture); CFO ppm per cell | step 5; step 7 summary (CFO mixes dongle and tower carrier). Wander: Gap 3 | `Dongle.drift_ppm` 0.4, `offset_rw_m`, `drift_rw_mps` (`src/pnt/sim/lte_front_end.py`). The BOM lists a 0.5 ppm TCXO | beyond ±5 ppm: outside the search (`Config.max_ppm`), record again with `ppm=` |
| 4 | Tower clocks: per-site stability, sectors of one eNB sharing timing, Rogers frame alignment | — | **Gap 2.** Step 8 removes a quadratic per difference and does not report it | `tower_clocks` (`src/pnt/sim/scenarios/sets/realistic.yaml`, `worst.yaml`); *Sim validity* row "LTE tower clocks, shared" | sectors of one eNB share a clock: supports ADR-0022's site grouping. eNBs frame-aligned: the far spot falls from 4.7 to 1.0 cells (#133) |
| 5 | Tracked (EARFCN, PCI) against the table; unknown or colliding PCIs | pairs from step 3/7; dropped counts from step 9 | by hand: `grep '^2460,<pci>,' data/reference/lte-cells-ottawa.csv`. Per-cell report: Gap 5 | EARFCN mapping `TBC` against what cells broadcast (`data/reference/README.md`) | a PCI not in the table or colliding: report in #87 and #138 with the session |
| 6 | Range noise and multipath, fixed spot, 1 h | `diff σ 10 Hz`, `diff σ 1 s` over the hour | step 8 on the 1 h session (precision only; bias against GPS truth: Gap 1) | `lte.sigma_m` 50, `multipath` 50 m / 30 s, `dropout` (`realistic.yaml`, `provenance: lte_noise, multipath, dropout: TBC`); *Sim validity* row "LTE pseudorange" (`systems/verification.md`) | moves that row to `measured` with the session. Note `realistic.yaml` hears TELUS 886.25 MHz, not 2460 |

## Afterwards

- **Keep the session.** The folder name is the session name (ICD-session, [`systems/icd/session.md`](../../systems/icd/session.md)); `pnt frontend lte` writes a new `<s>-lte` folder and never rewrites the original. Keep the raw `.cu8` on the laptop until every value it feeds is replaced; second copy location `TBD`.
- **Commit only small things.** Tables in issues; figures in `analysis/results/` per [`analysis/README.md`](../../analysis/README.md). Never `.cu8`, `.mcap` or `data/sessions/` (ignored; AGENTS.md).
- **Cite** every number as session name plus the commit in its `meta.yaml` (REQ-10), and the laptop commit that ran the front end (in the `-lte` folder's `meta.yaml`).
- **Update:** #21 (noise, drift, go/no-go), #30 and the *Sim validity* rows, #131 (cells tracked), #147 (reported vs observed σ); #87 and #138 for identity. A changed `TBC` value lands in a PR naming the session.

## Legal and safety

- Receive-only: RTL-SDRs cannot transmit (REQ-07, ADR-0001, [`systems/safety.md`](../../systems/safety.md)).
- The front end uses PSS and SSS only, which are broadcast sync signals. Nothing decodes user or communication content (REQ-08). Raw IQ never leaves our machines or goes in git.
- This capture uses no Wi-Fi scan (`--wifi` off). If enabled, BSSIDs are hashed at capture (ADR-0011).
- Where: `safety.md` sets no rule for ground captures. Its airspace rule is for flights (Carleton is likely inside YOW controlled airspace, ASM-06): this capture is static on the ground.

## Gaps

In priority order. Each is a missing script or option, not written here.

1. **Single cell, and bias against truth.** `lte_static_capture.py` needs ≥ 2 cells on one dongle and measures precision only. No script compares a cell's pseudorange with GPS truth plus the table's tower position, which is what one tracked cell (#131's Carleton case) would need.
2. **Tower clocks.** No script reports per-site clock drift and stability, a common term across sectors of one eNB, or frame alignment between eNBs.
3. **Dongle wander.** `rate_ppm_vs_host` is one linear fit per capture; host stamps jitter by ms (`pnt.payload.sdr`), so its precision is `TBD`. No time series or Allan deviation of the dongle frequency.
4. **Predicted count at the real spot.** `lte_link_dense.py --cases` takes only `carleton`, `beside` and `far`, not a lat/lon, and does not print the spot coordinates.
5. **Identity report.** No script lists each tracked (EARFCN, PCI) as matched, unknown, out of range or colliding; `pnt replay` counts records only, and only when some are dropped.
6. **`day1.sh` with one dongle.** It always records SDR B at `dev=1`; use steps 4 and 5 instead.
7. **Disk check.** `pnt record` does not refuse to start when the IQ will not fit.
8. **Carrier scan.** One carrier per `pnt record`; scanning the list means one run per EARFCN.
