# How these results were made (#173)

Evidence: **real sessions**, static, payload Pi, one NESDR SMArt v5, recorded at `4d3598b` on 2026-11-10 with no GPS fix (no position truth; NTP, not PPS, time). Raw IQ stays in `data/sessions/` (not in git).

## Commands

Analysis at `fdb8fde`. Front end at `92e6bac` for the 60 s and 30 s sessions and at `0276028` for the 1,800 s one; no file under `src/` differs between the three.

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
for s in 20261110-1305-lte-outside 20261110-lte-outside-{5145,5255} \
         20261110-1610-static-site1-e{2460,5060,5145,5205,5255} \
         20261110-1623-static-out-e{2460,2560,5060,5145,5205,5255} \
         20261110-1759-static-out-long-e5060; do
  pnt frontend lte data/sessions/$s/sdr_a.cu8 --out <out>/$s-lte
done
python analysis/lte_measured_noise.py <out>/*-lte --raw-root data/sessions
```

Every session uses the recorder's own `sdr_a.json`. Carriers with no cell found (nothing written): 2535 (both spots and the first spot), 5035, 5085, 68611.

## Buffer stamps and the 1,800 s capture

With the recorder's buffer stamps the front end flags 21 dropped-sample gaps of one to six frames on `20261110-1759-static-out-long-e5060`. Most come in pairs about 7,777 samples apart with sizes one sample either side of a whole number of frames (19,199 and 19,201, ...). The recorder's own `gaps` and `gaps_suspected` are empty. Whether any are real drops is `TBD`.

For comparison only (not in these results), the same file without the `buffers` field gives, for the strongest pairs and cells:

| Quantity | With stamps (these results) | Without stamps |
|---|---|---|
| Arcs, PCI 4 / 204 / 492 | 227 / 510 / 39 | 186 / 759 / 36 |
| Same-eNB drift 492 − 4 (m/s) | −0.18 ± 0.16 | −0.02 ± 0.11 |
| Same-eNB S(10 s), 492 − 4 (m) | 23.3 | 6.9 |
| One cell S(100 s), 492 (m) | 114 | 256 |

The long-lag values depend on the gap handling by factors of 2 to 4, so they are bounds that a front-end fix can move. In an earlier run on the first 979 s alone (copy interrupted), stamps made the timing look much worse; on the full file the effect is mixed, as above.

## Read with

- Availability ("Tracked (of IQ)") is 10 Hz records × 0.1 s over the IQ on disk (`.cu8` bytes / 2 / `sample_rate_hz`), not over the first-to-last record span.
- The Allan rows (one cell's timing, and the loop-filtered CFO) are **upper bounds** on the clocks: the CFO floor is the same for a same-eNB pair, which shares one clock. They must not replace `offset_rw_m` or `drift_rw_mps`.
- eNB identity is by the table alone (`lte-cells-ottawa.csv`, a PCI registered once on that EARFCN), not checked against a position: `TBC`.
- `summary.json` is rounded to four significant figures and keeps the track breaks as a summary only.
