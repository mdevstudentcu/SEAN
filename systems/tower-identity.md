# How we know which tower we hear and where it is

A plain-words explainer for the mentor's question of 2026-11-10: "how can you identify between the towers, how do you know where they are located?" (`transcript-speakers.srt_v1.md`). The decisions behind it are [ADR-0022](adr/0022-tower-clock-model.md) (tower clocks) and [ADR-0023](adr/0023-tower-identity.md) (tower identity), both `Proposed`. Every value is as committed on the date of this file; anything not yet measured is `TBC` or `TBD`.

**Short answer.** The government licence register tells us where every tower is. The two sync signals every LTE cell broadcasts tell us which cell we hear (its carrier and its cell number), and the register maps that pair to one mast. The arrival time of those sync signals, not their strength, gives the range. Each mast's clock error is learned while GPS is still good. A cell we can't place for certain is left out.

## 1. Where the towers are: the ISED licence register

- Every licensed transmitter in Canada is filed with ISED (Innovation, Science and Economic Development Canada), with its position, antenna height, azimuth, beamwidth and power. Since 2026 the public extract also lists each LTE sector's physical cell ID (PCI) and full cell ID (ECGI: network, area code and the eNB ID that names the mast).
- [`data/reference/lte-cells-ottawa.csv`](../data/reference/lte-cells-ottawa.csv) holds the 4,059 LTE sectors within 10 km of Carleton that our radios can tune (600–1750 MHz). Source: ISED *Terrestrial Spectrum Licence Site Data Extract*, `Site_Data_Extract_FX.zip`, file dated 2026-11-03, retrieved 2026-11-09, SHA-256 in [`data/reference/README.md`](../data/reference/README.md). Built by [`analysis/extract_lte_cells.py`](../analysis/extract_lte_cells.py) (commit `591a1e5`). This is the cell-to-site table.
- Public licence data only: no crowd-sourced database. CellMapper's terms rule it out; OpenCelliD positions are phone-fix centroids, not masts (ADR-0023).
- So we do know each mast's exact registered position, to the filing's precision (the answer on the call said we did not). How far a filing can be off is modelled as `told_position_sigma_m`, 100 m per mast (`TBC`), in the challenge legs.
- The older 2024 extract, [`cells-ottawa.csv`](../data/reference/cells-ottawa.csv), has sites but no PCI or carrier number, so it cannot identify a cell. The scan list and the cell table are built from the 2026 extract instead.

## 2. What to listen to: the scan list

- [`data/reference/lte-scan-list-ottawa.csv`](../data/reference/lte-scan-list-ottawa.csv): the 23 carriers (EARFCN and licensee) in the cell table, with how many sites use each and how many are within 3 km. One RTL-SDR listens to one carrier at a time.
- It is generated from the cell table (`scan_list` in `analysis/extract_lte_cells.py`); `tests/test_tower_identity.py` rebuilds it from the committed table and checks it is identical.

## 3. Which tower it is: carrier + PCI → mast

- Our receiver decodes only the two broadcast sync signals of LTE, PSS and SSS ([3GPP TS 36.211](https://www.etsi.org/deliver/etsi_ts/136200_136299/136211/)). Together they give the cell's PCI, a number from 0 to 503. We tuned the carrier, so we know its EARFCN. We never decode user traffic or paging (ADR-0011, `safety.md`).
- The front end names the cell `lte:<EARFCN>:<PCI>` ([`src/pnt/frontends/lte/`](../src/pnt/frontends/lte/__init__.py)). The lookup ([`src/pnt/nav/cells.py`](../src/pnt/nav/cells.py)) finds that pair in the cell table:
  - **one eNB in the table uses it**: matched. The record gets that mast's latitude, longitude and antenna height, and its site name (`enb:<id>`).
  - **more than one eNB uses it** (a PCI collision): not used. 152 of the table's 3,904 (EARFCN, PCI) pairs are reused by more than one eNB. A receiver that has moved could hear either, so the lookup never guesses (#138).
  - **no eNB in the table uses it**: not used, counted as unknown (section 6).
- **Grouping sectors into one mast uses the eNB ID, not PCI / 3.** The eNB ID comes from the registered cell ID (ECI >> 8). #87 and ADR-0023 step 3 proposed grouping by `PCI // 3`, a common planning convention. In Ottawa it never holds: of the 1,370 (carrier, eNB) groups with more than one PCI, none keeps its PCIs in one `PCI // 3` group (`tests/test_tower_identity.py`). The sectors of one mast share one clock (ADR-0022), so the grouping matters. *Open for the owners:* ADR-0023 step 3 still names `PCI // 3` (section 7).
- A match is a hypothesis, not a fact: an eNB beyond 10 km, a moved mast or one missing from the register can reuse a PCI. ADR-0023 lists these as integrity fault modes, caught by range residuals and clock consistency.

## 4. How far away it is: timing, not signal strength

- **We range on timing.** PSS and SSS mark the start of every 10 ms LTE radio frame. The front end tracks when each frame boundary arrives, every 5 ms, and reports a pseudorange: the speed of light times that arrival time on our clock ([`frontend.py`](../src/pnt/frontends/lte/frontend.py)). It is known only modulo one frame (about 3,000 km); the lookup aligns it from epoch to epoch.
- **Signal strength is not used for range.** Received power swings by tens of dB with walls, terrain and antenna pattern, which is kilometres of range error. We use SNR only to decide which cells can be tracked and how much to trust each reading. (The answer given on the call said signal strength; that was wrong for this design.)
- A pseudorange is range plus clock errors, the same idea as GPS: `pseudorange = distance + mast clock offset + our receiver clock offset + noise`. The next section is how the two clocks are handled.

## 5. Clocks: learned while GPS is good

- **Our clock.** All cells heard by one dongle share its clock (`meta.rx_clock`), so it is one unknown common to every tower, like a GPS receiver's clock: it costs one tower's worth of geometry ([`src/pnt/nav/ekf.py`](../src/pnt/nav/ekf.py) docstring).
- **Each mast's clock.** LTE FDD masts are frequency-locked to ±50 ppb but not time-aligned ([3GPP TS 36.104](https://www.etsi.org/deliver/etsi_ts/136100_136199/136104/)), so each mast has its own offset and drift. Sectors of one mast share it; masts built by one operator may share a common drift (ADR-0022).
- **Learned while GPS is good.** While GPS is trusted the filter knows where it is, so each heard mast's pseudorange residual is its clock. `ekf-calibrated` (ADR-0022) learns an offset and a drift per mast once GPS has been trusted for 30 s (`calib_gate_s`, `TBC`) and the barometer agrees with it; when GPS is lost or distrusted it stops learning and coasts each clock on its learned drift. The default `ekf` instead lets each mast's clock wander as a random walk (0.2 m/√s, `TBC`).
- How well the clocks hold after GPS loss sets how long towers keep us within the target (T1, ADR-0034). Measured so far at rest: sectors of one mast drift together to within 0.5 m/s over 1,800 s (PR #190, unmerged, ADR-0036 `Proposed`).

## 6. A tower we can't place

- An (EARFCN, PCI) that is not in the table, or that collides, is **dropped and counted, never guessed** (`pnt.nav.cells.attach`; the counts are logged at the end of a run). A wrong tower position is worse than one tower fewer.
- The planned fix is a *mapper* (ADR-0023 step 4): learn the unknown cell's position and clock while GPS is trusted, starting from the licensee's registered sites as the prior, and use it only once it has converged (threshold `TBD`). **It is not built.**
- A moved or wrong table entry is tested in sim with `analysis/lte_real_geometry.py wrong-table` (PR #133).

## 7. What we have heard so far

Real captures, static, one RTL-SDR on one carrier at a time. Only the cells and their table match are listed. The receiver's position, and any distance or bearing from it, is never committed: the captures were made at a private location (REQ-08).

Laptop captures, front end on main (`analysis/lte_scan_table.py`):

| Carrier | PCIs heard → eNB (registered site) | Result |
| --- | --- | --- |
| 2460, Rogers (850 MHz, band 5) | 204, 220 → 36122 (Mooney's Bay); 244 → 30066 (Albion & Heathrington); 92 → 30015 (Billings Bridge); 90, 106 → 36118 (Prince of Wales & Dynes); 268 → 30111 (Ottawa Airport Pkwy), found but never tracked | [`lte-scan-20261110`](../analysis/results/lte-scan-20261110/summary.md), [`lte-scan-20261111`](../analysis/results/lte-scan-20261111/summary.md) |
| 2535, TELUS (band 5) | none found in 29.5 s | `lte-scan-20261110` |
| 5145, TELUS (band 12) | 188, 189 → 219003 (1245 Walkley Rd); 175 → 219076 (1501 Bank St) | `lte-scan-20261110` |
| 5255, TELUS (band 13) | 175 → 219076 (1501 Bank St); 188 → 219003 (1245 Walkley Rd) | `lte-scan-20261110` |

Every cell above is a `unique` match: one eNB in the table uses it. The 9.7-minute capture of 2026-11-11 (`20261111-0040-static-fullsuite`) heard four Rogers masts on 2460 (five cells), all weak (SNR −8 to −12 dB, up to 247 re-acquisitions).

Carrier scan on the Pi (Mo, 2026-11-10, sessions `1610-*`, `1623-*`, `1759-*`). Its cells are in PR #190's `analysis/results/lte-measured-noise/summary.md`, **unmerged and not reproduced here** (the IQ is on the Pi only). The eNBs below are this file's lookup of those cells:

| Carrier | PCIs heard → eNB (registered site) |
| --- | --- |
| 2460, Rogers | 90 → 36118; 92 → 30015; 220 → 36122; 244 → 30066 |
| 5060, Vidéotron (band 12) | 4, 492 → 102790 (Walkley Square Apts); 92, 204 not in the table |
| 5145, TELUS | 85 → 219129 (2660 Norberry Cres); 175, 347 → 219076; 188, 189 → 219003 |
| 5205, Vidéotron (band 13) | 20 → 202753 (1365 Bank St); 309, 325 → 202790 (Walkley Square Apts); 330 → 202754 (2660 Norberry Cres); 32 is a collision (two eNBs) |
| 5255, TELUS | 85 → 219129; 175, 347 → 219076 |
| 2560, TELUS (band 5) | 175, 347 not in the table on 2560 (on 5145 and 5255 these PCIs are 219076, 1501 Bank St: possibly a carrier the register does not list there, `TBC`) |

PR #190's `NOTES.md` lists no cell found on 2535, 5035, 5085 and 68611. Whether the scan list's other carriers were scanned on the Pi is `TBD`.

- The 850 MHz layer (Rogers EARFCN 2460, band 5) is on air: it was heard on every capture tuned to it.
- Real data agrees with section 3: sectors of one mast carry PCIs in different `PCI // 3` groups (204 and 220 on eNB 36122, 90 and 106 on 36118, 188 and 189 on 219003).
- **For the owners:** ADR-0023 step 3 (and #87's text) groups sectors by `PCI // 3`. The table (0 of 1,370 groups) and these captures say to group by the registered eNB ID instead, as `pnt.nav.cells` already does. ADR-0023 is not amended here.

## Files

| What | File |
| --- | --- |
| Cell-to-site table (source and date) | `data/reference/lte-cells-ottawa.csv`, `data/reference/README.md` |
| Scan list | `data/reference/lte-scan-list-ottawa.csv` |
| Builder of both | `analysis/extract_lte_cells.py` |
| Lookup (carrier + PCI → mast) | `src/pnt/nav/cells.py` |
| Front end (PSS/SSS timing → pseudorange) | `src/pnt/frontends/lte/` |
| Tower clocks | `src/pnt/nav/ekf.py`, ADR-0022 |
| Scan results | `analysis/results/lte-scan-*/summary.md`, made by `analysis/lte_scan_table.py` |
