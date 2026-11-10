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
| Spot 3, if time | Far from every tower: #133's `far_from_all` (4.7 cells tracked of 57, synthetic). Its coordinates are not printed: `TBD` (Gap 2) | `analysis/lte_link_dense.py` |
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
| 2a. Carrier scan (Pi, if time) | `bash deploy/pi/scan_carriers.sh --seconds 60 --notes "antenna <where>"` (`--dry-run` first prints the commands; `--only 2460,5145` to pick; `--gain <dB>`). 60 s per carrier is `TBC` | one session per EARFCN, `data/sessions/<YYYYmmdd-HHMM>-static-carleton-e<EARFCN>/`, each as step 1 records it: 13 unflagged carriers, about 230 MB of IQ each. Flagged rows only with `--include-flagged`. Checks free space before each; Ctrl-C ends the current capture cleanly and starts no more. Ends with the laptop commands for step 8a |
| 3. Cells on air (*laptop*, after the rsync of step 6) | `pnt frontend lte data/sessions/<s>/sdr_a.cu8` | prints one line per tracked cell: `lte:<earfcn>:<pci>`, SNR, CFO in Hz and ppm, seconds tracked, arcs; writes `data/sessions/<s>-lte/` (derived session, ICD-session). If it finds no cell it writes nothing |
| 4. Long capture (Pi) | step 1 with `--duration 3600` and notes `"#149 static 1 h ..."` | as step 1 |
| 5. Day-1 numbers (Pi) | `.venv/bin/pnt day1 data/sessions/<s>` (`day1.sh` assumes two dongles: Gap 3) | `data/sessions/<s>.day1.md` and `.json`: dropped samples, `rate_ppm_vs_host`, PPS offset, CPU, temperature, throttling |
| 6. Copy (*laptop*) | `rsync -av pi@pnt.local:~/pnt/data/sessions/ data/sessions/` | — |
| 7. Front end (*laptop*) | `pnt frontend lte data/sessions/<s>/sdr_a.cu8` | `data/sessions/<s>-lte/`, with the original's GNSS, IMU and baro records copied in. Prints the real-time factor; time for 1 h is `TBD` |
| 8. Report (*laptop*) | `.venv/bin/python analysis/lte_capture_report.py data/sessions/<s>-lte` (add `--position lat,lon,h` from step 10 if better than the mean GNSS fix) | markdown to stdout, and `report.md`, `cells.png`, `dongle_clock.png`, `pair_differences.png`, `dongle_allan.png` (≥ 30 s) in `data/sessions/<s>-lte-report/` (`--out` to change). Sections 1–6 below. Works with one cell; what one cell can't give it prints as "not measurable from this session" |
| 8a. Scan report (*laptop*) | `for s in data/sessions/<stamp>-static-carleton-e*/; do pnt frontend lte "$s/sdr_a.cu8"; done`, then `.venv/bin/python analysis/lte_capture_report.py data/sessions/<stamp>-static-carleton-e*-lte --out data/sessions/<stamp>-scan-report` | one table across the scan: cells per carrier (section 1) and identity (section 2). A carrier with no cell writes no `-lte` folder |
| 9. Cross-checks (*laptop*) | `analysis/lte_static_capture.py data/sessions/<s>-lte` (≥ 2 cells: σ of the difference to the strongest cell); `pnt replay data/sessions/<s>-lte` (warns `LTE cells: used N records, dropped {...}`) | stdout |
| 10. Spot position (*laptop*) | `pnt survey data/sessions/<s>` | `data/sessions/<s>.survey.yaml`: averaged fix and `sigma_m` (`TBD` under four 10-min batches) |

Without uv, `pnt` is `.venv/bin/pnt`. `pnt record --no-stream` needs no keys; to watch live, set up the [keys](RUNBOOK.md#keys-once-per-host) and drop `--no-stream`.

## What to read off, in order

| # | Question | Number | Where it comes from | `TBC` it replaces | What changes our plan |
| --- | --- | --- | --- | --- | --- |
| 1 | Cells tracked at a known spot, and how far below the strongest | count of `lte:2460:<pci>` lines; SNR of each minus the strongest | step 3/7 summary; **report §1** (per carrier, level re strongest, against the −13 dB floor); across carriers, step 8a. Cells not tracked can't be seen: Gap 2 for the predicted count at this spot | `LinkBudget.floor_db` −13 dB and `min_snr_db` (`src/pnt/sim/lte_front_end.py`); `MAX_RANGE_KM` 10 km (`src/pnt/nav/cells.py`); tracker regression guards (`Config` in `src/pnt/frontends/lte/tracker.py`) | 1 cell at Carleton matches #133's synthetic case (1 of 24), where LTE added nothing over no LTE: take #131's options to the owners. More cells than #133 predicts: the near-far floor is pessimistic; say so in #131 |
| 2 | Reported σ against the spread seen | `Reported σ`, `Observed σ 10 Hz`, `Ratio` | **report §3**, per cell, one cell is enough (its σ is an upper bound: it keeps dongle wander faster than the 30 s window, `TBC`). Step 9's `lte_static_capture.py` differences two cells | `Config.sigma_scale` 1.5 (`tracker.py`); sim `told_sigma_m` (#147) | ratio > 1: `sigma_scale` is too low (the script's own reading). Reported σ far below the observed spread confirms #147 on real data |
| 3 | Dongle clock: frequency error and wander | `rate_ppm_vs_host` (one fit per capture); CFO ppm per cell | step 5; **report §4**: ε = −CFO/f_c over time, drift ± 1σ, Allan deviation if ≥ 30 s (`TBC`). CFO mixes dongle and tower carrier | `Dongle.drift_ppm` 0.4, `offset_rw_m`, `drift_rw_mps` (`src/pnt/sim/lte_front_end.py`). The BOM lists a 0.5 ppm TCXO | beyond ±5 ppm: outside the search (`Config.max_ppm`), record again with `ppm=` |
| 4 | Tower clocks: per-site stability, sectors of one eNB sharing timing, Rogers frame alignment | pair drift (m/s, ppb), spread; offset per eNB (µs mod 10 ms) | **report §5**: every pair on one carrier, grouped same-eNB or not (no position needed); frame offsets per eNB need a position (mean GNSS fix or `--position`), aligned within ±5 µs `TBC`. Needs ≥ 2 cells | `tower_clocks` (`src/pnt/sim/scenarios/sets/realistic.yaml`, `worst.yaml`); *Sim validity* row "LTE tower clocks, shared" | sectors of one eNB share a clock: supports ADR-0022's site grouping. eNBs frame-aligned: the far spot falls from 4.7 to 1.0 cells (#133) |
| 5 | Tracked (EARFCN, PCI) against the table; unknown or colliding PCIs | status per (EARFCN, PCI) | **report §2**: `CellTable.associate` at the session's position: matched (eNB, site, distance, bearing), unknown, out of range, collision | EARFCN mapping `TBC` against what cells broadcast (`data/reference/README.md`) | a PCI not in the table or colliding: report in #87 and #138 with the session |
| 6 | Range noise and multipath, fixed spot, 1 h | `Observed σ 10 Hz`, `1 s`; pair spread; fraction tracked | **report §3, §5** on the 1 h session (precision only; bias against GPS truth: Gap 1). **§6** maps every number to the `TBC` it would replace | `lte.sigma_m` 50, `multipath` 50 m / 30 s, `dropout` (`realistic.yaml`, `provenance: lte_noise, multipath, dropout: TBC`); *Sim validity* row "LTE pseudorange" (`systems/verification.md`) | moves that row to `measured` with the session. Note `realistic.yaml` hears TELUS 886.25 MHz, not 2460 |

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

In priority order. Each is a missing script or option, not written here. Closed by `analysis/lte_capture_report.py` and `scan_carriers.sh` (#173): one-cell precision, tower clocks and frame alignment, dongle wander, the identity report, and the carrier scan.

1. **Bias against truth.** No script compares a cell's pseudorange with GPS truth plus the table's tower position, which is what one tracked cell (#131's Carleton case) would need; the report measures precision only, so multipath size and correlation time are not measured either.
2. **Predicted count at the real spot.** `lte_link_dense.py --cases` takes only `carleton`, `beside` and `far`, not a lat/lon, and does not print the spot coordinates.
3. **`day1.sh` with one dongle.** It always records SDR B at `dev=1`; use steps 4 and 5 instead.
4. **Disk check in `pnt record`.** It does not refuse to start when the IQ will not fit; only `scan_carriers.sh` checks, before each of its captures.
5. **Recording commit in the `-lte` folder.** `pnt frontend lte` writes its own commit to the derived `meta.yaml`; the report reads the recording's commit from the original folder beside it, and prints `TBD` if that folder is not there.
