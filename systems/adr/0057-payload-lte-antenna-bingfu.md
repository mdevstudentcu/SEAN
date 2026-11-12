# ADR-0057: The payload's LTE antenna is the Bingfu

- **Status:** Accepted
- **Date:** 2026-11-12
- **Deciders:** Shrikar (owner); Mo not consulted (no contributions for a while): reopen if he disagrees
- **Traces to:** REQ-06, ADR-0018, #200, `hardware/bom.md` section 3

## Context

SDR B (NESDR SMArt v5) needs one LTE antenna on the payload. Three are in hand: the NooElec bundle's UHF mast, its telescopic (set to 25.7 cm), and the Bingfu 8 dBi LTE antenna (2-pack, rated 698–960 MHz). The 2026-11-10 A/B ([`analysis/results/antenna-ab-20261110/`](../../analysis/results/antenna-ab-20261110/README.md)) did not settle it: on a chair the Bingfu and the telescopic each tracked one cell at about +6 dB and the UHF mast none, but the UHF mast on the ground tracked a cell at +14 dB. Mounting (ground plane `TBC`) and auto gain confound the comparison, and the planned ground-plane re-test has not been run.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| Bingfu 8 dBi | Rated for the LTE bands we use (700 and 850 MHz); tracked a cell above the floor on the chair, vertical and horizontal; a spare in the 2-pack | Magnetic base and 3 m cable weigh on a 5" quad; band 71 (600 MHz) only weakly; no ground-plane comparison yet |
| Bundle UHF mast | Best single result (+14 dB), but only on the ground | Nothing above the floor on the chair; a broad UHF antenna, not an LTE one |
| Bundle telescopic (25.7 cm) | Light; one cell at +6 dB on the chair | Its length is tuned by hand; the telescopic also serves VOR |
| Wait for the ground-plane re-test | Settles it on data | Not run (`TBD`); judging is today |

## Decision

The payload uses the Bingfu on SDR B; the second Bingfu is the spare. This is an owner's call on the evidence above, not a measured win: the ground-plane re-test stays the follow-up, and its result can reopen this.

## Consequences

- `hardware/bom.md` records the Bingfu as the payload antenna; #200 is closed with this decision.
- On the drone, the magnetic base and cable need handling (stripped magnet and taped cable, or a stub antenna: `bom.md` section 3); weight is in the SWaP block.
- Captures and results name the antenna in the session notes as before, so a later change is traceable.
- Reopen if the ground-plane re-test at fixed gain shows another antenna hearing more usable cells on EARFCN 2460.
