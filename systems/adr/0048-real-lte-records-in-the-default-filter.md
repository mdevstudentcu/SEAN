# ADR-0048: What the EKF does with a real capture's LTE records

- **Status:** Proposed
- **Date:** 2026-11-11
- **Deciders:** team (the owners)
- **Traces to:** REQ-01, REQ-02, REQ-04, ADR-0004, ADR-0015, ADR-0036, ADR-0038, ADR-0044, #147, #191, #214, #246

## Context

#245's front end fixed the ~700 m re-acquisition walks (median re-find step now about 10 m). Replaying the two real static sessions with GPS cut in software (#214's `analysis/real_gps_cut.py`, pseudoranges only) still gives LTE-aided errors of kilometres, where no LTE gives about 1 m:

- The default `ekf` believes the front end's σ (1 to 5 m at high SNR) while two cells' double difference wanders 1 to 45 m. It pulls the position off and keeps its covariance tight, and its χ² gate then rejects every GNSS fix. GNSS is excluded on 100 % (0151) and 28 % (0233) of the epochs before the cut (#246). LTE alone keeps consistent GNSS out.
- 16 to 17 % of re-finds still step more than 100 m.

ADR-0044 kept every default on the reported σ until a moving session decides. This ADR asks the owners to change two defaults **for a real capture's records only**, and proposes two opt-in guards and one alternative.

**Which records count as a real capture's:** those with `meta.sample_index`, the record's place in its IQ file. `pnt.frontends.lte` writes it; `sim/lte_front_end.py` leaves it out because there is no file (`told_sigma.from_capture`). This is a branch on where a record came from, which ADR-0004 asks the estimator to avoid. The right home for both defaults is the front end (ADR-0036 consequence 1, ADR-0044 consequence 1), which would remove the branch. Until then, keying on `sample_index` is the only way to change real behaviour and leave every sim output bit-identical.

## What each change bought

Real static sessions `20261111-0151-static-fullsuite2` (600 s) and `20261111-0233-static-lte-1h`, #245's records (front end `ea72f6a`), `ekf`. Each change alone on `main`'s `ekf`, then on top of (a). Five cut times per session; median (worst) horizontal error in m 300 s after the cut. Script [`analysis/real_lte_filter.py`](../../analysis/real_lte_filter.py), results in [`analysis/results/real-lte-filter`](../../analysis/results/real-lte-filter/NOTES.md).

| | 0151, 300 s | 0233, 300 s | HPL ≥ error (0151 / 0233) | GNSS excluded before the cut |
|---|---|---|---|---|
| no LTE | 0.6 (16) | 1.3 (3.2) | 100 % / 100 % | 0 % / 0 % |
| `main` | 21,553 (29,463) | 10,718 (98,706) | 0 % / 14 % | 100 % / 28 % |
| a: ADR-0036's σ | 205 (5,130) | 1,513 (4,655) | 65 % / 49 % | 0 % / 0 % |
| b: GNSS re-admission | 4,710 (5,192) | 3,524 (9,493) | 16 % / 21 % | 0 % / 1 % |
| c: a bias per new arc | 6,253 (8,592) | 1,680 (2,429) | 0 % / 2 % | 100 % / 96 % |
| c2: a new arc's first 5 s at 10 × σ | 12,031 (12,211) | 7,600 (35,015) | 0 % / 31 % | 100 % / 26 % |
| d: heard-cell bound, 10 km | 9,171 (9,752) | 8,992 (11,130) | 0 % / 27 % | 100 % / 31 % |
| a+b, a+d | = a | = a | = a | = a |
| **a+c (the proposed default)** | **595 (1,536)** | **364 (1,582)** | **76 % / 75 %** | **0 % / 0 %** |
| a+c2 | 138 (9,298) | 137 (900) | 73 % / 58 % | 0 % / 0 % |

The cut times share one recording per session, so they are not independent draws. Both receivers are static, which favours no LTE by construction.

## Decision (Proposed)

1. **(a) default, real captures only:** a real capture's LTE pseudoranges are told ADR-0036's σ (`capture_sigma_model="adr0036"`, as `ekf-measured-sigma` does for every radio record). It removes the GNSS latch on both sessions and takes the 300 s error from 11 to 22 km to 0.2 to 1.5 km (median). Not in `ekf-calibrated-measured`, which carries ADR-0036's correlated part as a state already.
2. **(c) default, real captures only:** a real capture's new arc gets its own range bias (`arc_bias=None`: on for those records). On top of (a) it cuts the worst run from 4.7 to 5.1 km to 1.5 to 1.6 km and raises the HPL bound rate from 49 to 65 % to 75 to 76 %. The median on 0151 rises (205 to 595 m); on 0233 it falls (1,513 to 364 m). Chosen over (c2), which has better medians but a 9.3 km worst run on 0151: this ADR prefers the bounded worst case and the more honest HPL (REQ-02).
3. **(b) opt-in** (`gnss_readmit=GnssReadmit`, `integrity/gnss_readmit.py`). GNSS that the gate rejects is re-admitted, with the filter reset to first-sight priors, when all of these hold:
   - the rejection began while GNSS was steering (never after a gap, so #191's hole stays closed);
   - the GNSS stream has not stepped since, against a line through its own previous fixes (a jump or a replay delay blocks it);
   - it has lasted `wait_s` (10 s, `TBC`);
   - the towers' innovations over that window run larger than their model says (mean NIS over its 99.9 % bound), so they are not fit to refute GNSS;
   - with an IMU, the stream's velocity agrees with the filter's.

   Alone it removes the latch (100 % to 0 %, 28 % to 1 %) but leaves kilometres after the cut. With (a) it never fires on these sessions. **It fails the attack check, so it stays opt-in and is not proposed as a default:** on sim `spoof-ramp` (seeds 0 and 1) it re-admitted the ramp once for `ekf`, `ekf-imu`, `ekf-guard` and `ekf-imu-guard`, raising misleading epochs per run from 1,441 to 2,026 to 2,060, and on `challenge-drone-spoof-jump` once for `ekf-imu`. `spoof-jump`, `meaconing`, `gps-outage` and the challenge drone ramp and meaconing legs are unchanged. The owners decide whether to keep it at all.
4. **(d) opt-in** (`heard_cell_radius_m`). A heard cell keeps the position within the radius of its site: outside it, the horizontal distance is told the radius with σ a tenth of it, at most once a second per cell. **10 km (`TBC`)** is `cells.MAX_RANGE_KM`, the radius the lookup already assumes when it matches a cell to a site, so it adds no new assumption. A link budget for EARFCN 2460 (band 5, 875 MHz) does not support a tighter value: an assumed 32 dBm EIRP per resource element (43 dBm over 10 MHz, 17 dBi sector, `TBC`), detection at −14 dB SNR (the lowest measured bin) over a −126 dBm noise floor per resource element (6 dB noise figure, `TBC`), and Okumura-Hata (30 m mast, 1.5 m receiver) put the reach at 22 km (urban) to 38 km (suburban), more from a drone. Per band and EARFCN it is `TBD`. It binds only beyond 10 km, so it helps `main` (worst run 29 to 10 km on 0151) and does nothing on top of (a).
5. **(c2) opt-in** (`arc_settle_s`), the alternative to (c) for the owners.
6. **The sim is unchanged.** Every registered estimator hashes the same as on `main` on the challenge legs, `gps-outage`, `realistic-long-outage`, `meaconing`, `spoof-jump` and `spoof-ramp`, seeds 0 and 1 (PR evidence). Telling the sim's front-end-shaped records (a) as well is a separate option for the owners (#147). ADR-0044 measured it on the sim drone leg before ADR-0047 (T1 worst p95 9,435 to 2,561 m, NEES 270 to 48); it was not rerun here.

## Consequences

- With LTE, the default still does not beat no LTE on a static receiver (hundreds of metres against 1 m at 300 s), and the HPL still misses a quarter of the withheld fixes. LTE-aided coasting on real data is not yet fit to show as a result. ADR-0044 option 6 (leave radio LTE out of the default solution until #183) remains open.
- (c) resets a cell's range information at every new arc, so a cell that re-finds often adds little after a GPS cut (ADR-0044 consequence 4).
- Reopen when a moving session with GPS truth exists, when the front end reports ADR-0036's σ itself (then (a) and the `sample_index` branch go), or when a tighter rule for (b) passes the attack runs (`analysis/readmit_attacks.py`).
