# How these results were made (#173)

Evidence: **real sessions**, static, payload Pi, one NESDR SMArt v5, recorded at `4d3598b` on 2026-11-10 with no GPS fix (no position truth; NTP, not PPS, time). Raw IQ stays in `data/sessions/` (not in git).

## Commands, at `c1bbc39` (front end at `92e6bac`; no file under `src/` differs between the two)

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
for s in 20261110-1305-lte-outside 20261110-lte-outside-{5145,5255} \
         20261110-1610-static-site1-e{2460,5060,5145,5205,5255} \
         20261110-1623-static-out-e{2460,2560,5060,5145,5205,5255}; do
  pnt frontend lte data/sessions/$s/sdr_a.cu8 --out <out>/$s-lte
done
pnt frontend lte data/sessions/20261110-1759-static-out-long-e5060/sdr_a.cu8 \
  --sidecar <prefix-sidecar> --out <out>/20261110-1759-static-out-long-e5060-partial979s-lte
python analysis/lte_measured_noise.py <out>/*-lte --raw-root data/sessions
```

Carriers with no cell found (nothing written): 2535 (both spots and the first spot), 5035, 5085, 68611.

## The 30-minute capture is partial

`20261110-1759-static-out-long-e5060` recorded 1,800 s, but only the first 3,759,636,480 bytes of `sdr_a.cu8` were copied off the Pi before the link dropped: **979.07 s**. Every number from it covers that prefix only, and its rows say `partial979s`.

`<prefix-sidecar>` is the recorder's `sdr_a.json` with `samples` set to the prefix and **the `buffers` stamps removed**:

```python
d = json.load(open("data/sessions/20261110-1759-static-out-long-e5060/sdr_a.json"))
d["samples"] = 3759636480 // 2
d.pop("buffers")
```

Why without stamps: with the stamps (cut to the prefix) the front end flags 14 dropped-sample gaps of one to four frames, several in pairs 7,777 samples apart with sizes 19,199 and 19,201 (one drop counted twice?), while the recorder's own `gaps` and `gaps_suspected` are empty. With them, the strongest cell's S(10 s) is 91 m and the same-eNB pair 492 − 4 reads 186 m at 10 s; without them, 6.3 m and 6.7 m. The stamped run is kept in the report below as a front-end finding, not used for the numbers. Whether real drops happened in the prefix is `TBD`.

## Read with

- Availability ("Tracked (of IQ)") is 10 Hz records × 0.1 s over the IQ on disk (`.cu8` bytes / 2 / `sample_rate_hz`), not over the first-to-last record span.
- The Allan rows (one cell's timing, and the loop-filtered CFO) are **upper bounds** on the clocks: the CFO floor is the same for a same-eNB pair, which shares one clock. They must not replace `offset_rw_m` or `drift_rw_mps`.
- eNB identity is by the table alone (`lte-cells-ottawa.csv`, a PCI registered once on that EARFCN), not checked against a position: `TBC`.
