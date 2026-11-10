# ADR-0023: Tower identity comes from the ISED registry, an EARFCN and PCI scan, and a mapper for the rest

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-04, REQ-06, REQ-08, ASM-02, ADR-0011, ADR-0015, ADR-0022

## Context

To range on a tower we must know which physical site sent the signal. Our RTL-SDRs sample at up to 2.4 MS/s.

- **What they can decode:** PSS and SSS give the physical cell ID (PCI = 3·N_ID1 + N_ID2, 0–503), and the PBCH gives the MIB. All three sit in the central 1.08 MHz of the carrier ([3GPP TS 36.211](https://www.etsi.org/deliver/etsi_ts/136200_136299/136211/); [MathWorks, cell search and MIB recovery](https://www.mathworks.com/help/lte/ug/cell-search-mib-and-sib1-recovery.html)).
- **What they can't:** SIB1 carries the ECGI (eNB ID and cell ID), PLMN and TAC. Finding it means decoding the PDCCH across the whole carrier: at least 7.68 MS/s for 5 MHz and 15.36 MS/s for 10 MHz. MathWorks states that for RTL-SDR "only MIB decoding is supported" ([Scan and Decode LTE Waveform](https://www.mathworks.com/help/lte/ug/scan-and-decode-lte-waveform.html)).
- **The registry has sites but no PCI.** [`cells-ottawa.csv`](../../data/reference/cells-ottawa.csv) (ISED, file dated 2024-10-30) gives each site's licensee, centre frequency and bandwidth. These map to candidate EARFCNs ([3GPP TS 36.101](https://www.etsi.org/deliver/etsi_ts/136100_136199/136101/)). Some filings are off the 100 kHz raster or in uplink ranges, so a scan must confirm them.
- **PCI is reused** across distant sites by design (Shamaei et al., [IEEE TWC 2018](https://escholarship.org/uc/item/5rw6t83d)).
- **Crowd databases:**
  - [OpenCelliD](https://wiki.opencellid.org/wiki/Database_format) lists PCI per cell with an estimated position. That position is a centroid of phone fixes, not the mast. The data is CC BY-SA 4.0 and a download needs an API token ([downloads](https://opencellid.org/downloads.php)).
  - [CellMapper's terms](https://www.cellmapper.net/TOS) forbid redistribution and educational or academic use.
- **Update 2026-11-09: the 2026 extract lists PCI.** ISED's renamed *Terrestrial Spectrum Licence Site Data Extract* (`Site_Data_Extract_FX.zip`, dated 2026-11-03) gives each LTE sector its PCI (`physical_id`), full cell ID (PLMN-TAC-ECI, so eNB ID = ECI >> 8) and antenna azimuth. [`lte-cells-ottawa.csv`](../../data/reference/lte-cells-ottawa.csv) holds the 4,059 tunable sectors within 10 km of Carleton. 152 of their 3,904 (EARFCN, PCI) pairs are used by more than one eNB, so a heard cell is usually one registered sector, and sometimes a short list. The bullet above describes the 2024 file.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| A. ISED → EARFCN scan list → PCI scan → (EARFCN, PCI) → site table, plus a mapper for unmatched cells | Uses what our radios decode; registry data is already committed with source and date | Association is a hypothesis, not a fact; PCI collisions and registry staleness become fault modes |
| B. OpenCelliD positions as the site source | PCI already linked to cell ID | Centroids, not masts; ShareAlike would spread to committed derived files; download needs owner approval |
| C. CellMapper | Rich coverage | Its terms rule it out |
| D. Decode SIB1 for ECGI with a wideband SDR | Confirms eNB ID, so sector grouping and builder are facts | No receive-only wideband SDR in hand (HackRF is excluded by `safety.md` because it can transmit); the known decoders are AGPL and a new dependency |
| E. Mapper only, no registry | No database | One receiver on a 150 m loop gives poor geometry to km-distant towers; slow |

## Decision

Identify each heard cell by (EARFCN, PCI) through a scan list built from the ISED registry and a committed (EARFCN, PCI) → site table, learn the cells that don't match with a mapper while GNSS is trusted, and treat every association as a hypothesis with its own fault prior.

The pipeline:

1. ISED registry → candidate EARFCNs per licensee.
2. Scan those EARFCNs for PCIs (PSS/SSS, MIB, SNR, timing) and record the session (REQ-10).
3. Match each (EARFCN, PCI) to a registered site of that licensee within link range, and group sectors by `PCI // 3` plus co-timing (ADR-0022).
4. Hand unmatched cells to a mapper: the ISED sites of that licensee are the position prior, and position and clock are learned while GNSS is trusted.

## Consequences

- **Data:** the site table goes in `data/reference/` with its source and date (#87). The emitter ID stays `lte:<earfcn>:<pci>`, so the ICD does not change; the site mapping is nav-side data.
- **The mapper:** a mapped cell is not used for navigation until it converges (threshold `TBD`). Its position prior σ is `TBD`.
- **OpenCelliD** is a clustering hint only (eNB ID = cell ID >> 8), never a position. Downloading it needs owner approval. The raw file stays in ignored `data/`, and any committed derived file carries the CC BY-SA attribution.
- **Conflict with ASM-02:** ASM-02 names OpenCelliD as a source of transmitter locations. If this ADR is accepted, ASM-02 needs updating.
- **CellMapper** is not used, not even for manual look-ups that feed the table.
- **Privacy (ADR-0011, REQ-08):** we decode only broadcast system information: PSS, SSS and MIB now, and SIB messages on SI-RNTI if SIB1 ever comes. We never decode user data or paging (C-RNTI, P-RNTI).
- **Association errors are integrity fault modes,** each with a prior (`TBD`):
  - PCI collisions
  - moved or missing sites (the registry is two years old)
  - one eNB feeding radios at different places
  - a filing on a different carrier than the one on air
  - a rogue cell copying a real PCI

  They are detected through residuals and through clock consistency against the learned clock (ADR-0022). An excluded cell drops back to mapper status. Rogue cells exist only as software fault injection in `sim/` (ADR-0001).
- **Step 3, link range (2026-11-10, #138):** the lookup (`pnt.nav.cells`) runs before the estimator and does not know where the receiver is. An (EARFCN, PCI) used by more than one eNB anywhere in the table is a collision, not only when both are in range of the session origin: a receiver that has travelled from the origin can hear the far one. Link range from the origin (`MAX_RANGE_KM`, `TBC`) only rules out a cell whose one eNB is beyond it. Ranging from the receiver's current estimate was not chosen: the estimate is what a spoof or a wrong match corrupts. From Carleton nothing changes, since the whole table is within 10 km of it.
- **Roadmap:** a wideband SIB1 survey with a receive-only SDR at ≥ 7.68 MS/s. Its decoder would run as a separate process and needs owner sign-off for the dependency and its licence.
- **Reopen if:**
  - the scan shows PCI collisions on one EARFCN common enough to break matching
  - a receive-only wideband SDR becomes available
  - a re-pulled ISED file disagrees with the table
