# How these results were made (#173)

Evidence: **real sessions**, static, payload Pi, one NESDR SMArt v5, recorded on 2026-11-10 at the change that is `ee20817` on `main` (each `meta.yaml` names the local commit it had then), with no GPS fix (no position truth; NTP, not PPS, time). Raw IQ stays in `data/sessions/` (not in git).

## Commands

Front end and analysis at `e9a9053` on `main`, on all 15 sessions (run on the laptop, 2026-11-11). Each session's `meta.yaml` names the payload Pi's local commit, which is not on `main`; `summary.md` and `summary.json` cite its twin on `main`, `ee20817` (same patch by `git patch-id`), as `python analysis/recite.py --write` rewrites it (last line below; it re-cites every other result that needs it too).

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
for s in 20261110-1305-lte-outside 20261110-lte-outside-{5145,5255} \
         20261110-1610-static-site1-e{2460,5060,5145,5205,5255} \
         20261110-1623-static-out-e{2460,2560,5060,5145,5205,5255} \
         20261110-1759-static-out-long-e5060; do
  pnt frontend lte data/sessions/$s/sdr_a.cu8 --out <out>/$s-lte
done
python analysis/lte_measured_noise.py <out>/*-lte --raw-root data/sessions
python analysis/recite.py --write
```

Every session uses the recorder's own `sdr_a.json`. Carriers with no cell found (nothing written): 2535 (both spots and the first spot), 5035, 5085, 68611.

Against the first results (analysis at `2408c19`, front end at `3e97678` and `060445f`, run on the branch before its rebase-merge; under `src/` only the dashboard, `payload/gpsd.py` and `_attacks.yaml` differ from `e9a9053`): every SNR bin, cell, pair, track-break and Allan value is the same except the fit (below) and three values in the fourth significant figure: `20261110-1610-static-site1-e5255` PCI 175 white σ robust 10.08 → 10.09 m, `20261110-1759-static-out-long-e5060` PCI 4 white σ RMS 3.194 → 3.195 m (`summary.json`), and its 492 − 4 drift −0.1751 → −0.175 m/s (`summary.json`).

## The white-σ fit: SNR ≥ −8 dB only

The script fits only the bins at or above `FIT_MIN_SNR_DB` (−8 dB, `TBC`; from `ff51d65`) and keeps each weaker bin's measured σ: σ² = 0.64² + 2.28² / SNR_lin (m, 10 Hz), within 0.79 to 1.23 of each fitted bin. The first fit, over every bin, was σ² = 0.51² + 2.46² / SNR_lin; below −8 dB it read 7.8 m against the measured 12.4 m (−11 to −8 dB) and 9.5 m against 24.7 m (−14 to −11 dB). Both come back from the per-bin values in `summary.json` (`snr_median_db`, `white_robust_m`, `n`) without the sessions:

```bash
PYTHONPATH=src python -c "
import importlib.util, json, sys
s = importlib.util.spec_from_file_location('lmn', 'analysis/lte_measured_noise.py')
m = importlib.util.module_from_spec(s); sys.modules['lmn'] = m; s.loader.exec_module(m)
b = json.load(open('analysis/results/lte-measured-noise/summary.json'))['snr_bins']
print(m.fit_white(b), m.fit_white(b, snr_min_db=-1e9))"
```

It prints 0.642 and 2.280, then 0.507 and 2.460.

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
