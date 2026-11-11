# How these results were made (#173)

Evidence: **real sessions**, static, payload Pi, one NESDR SMArt v5, recorded on 2026-11-10 at the change that is `ee20817` on `main` (each `meta.yaml` names the local commit it had then), with no GPS fix (no position truth; NTP, not PPS, time). Raw IQ stays in `data/sessions/` (not in git).

## Commands

Front end and analysis at `8892fca` on `main` (#245's merge: #183's fixes and the re-acquisition fix, ADR-0036's amendment of 2026-11-11), on all 15 sessions (run on the laptop, 2026-11-11). The front end's defaults, so no doppler records (`Config.doppler` off); nothing here reads them (the carrier offset is each pseudorange's `meta.cfo_hz`). The previous results, front end and analysis at `e9a9053`, are in this folder's history (`2877bf1`); what moved is in ADR-0036's amendment. Each session's `meta.yaml` names the payload Pi's local commit, which is not on `main`; `summary.md` and `summary.json` cite its twin on `main`, `ee20817` (same patch by `git patch-id`), as `python analysis/recite.py --write` rewrites it (last line below; it re-cites every other result that needs it too).

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

Every session uses the recorder's own `sdr_a.json`. Carriers with no cell found (no record at `e9a9053` and again at `8892fca`, `--no-copy`): 2535, 5035, 5085 and 68611 in both `20261110-1610-static-site1-e*` and `20261110-1623-static-out-e*` (the `1610` 68611 IQ is 26.2 s), 68661, 68711 and 68761 in `1623` only, and `20261110-lte-outside-2535`.

At `e9a9053`, against the first results (analysis at `2408c19`, front end at `3e97678` and `060445f`, run on the branch before its rebase-merge; under `src/` only the dashboard, `payload/gpsd.py` and `_attacks.yaml` differ from `e9a9053`): every SNR bin, cell, pair, track-break and Allan value is the same except the fit (below) and three values in the fourth significant figure: `20261110-1610-static-site1-e5255` PCI 175 white σ robust 10.08 → 10.09 m, `20261110-1759-static-out-long-e5060` PCI 4 white σ RMS 3.194 → 3.195 m (`summary.json`), and its 492 − 4 drift −0.1751 → −0.175 m/s (`summary.json`).

## The white-σ fit: SNR ≥ −8 dB only

The script fits only the bins at or above `FIT_MIN_SNR_DB` (−8 dB, `TBC`; from `ff51d65`) and keeps each weaker bin's measured σ: σ² = 0.74² + 2.32² / SNR_lin (m, 10 Hz), within 0.82 to 1.18 of each fitted bin. A fit over every bin gives 0.72² + 2.34² / SNR_lin; below −8 dB it reads 6.6 m against the measured 10.9 m (−11 to −8 dB) and 8.8 m against 22.5 m (−14 to −11 dB, 43 records only). At `e9a9053` the fit was 0.64² + 2.28² / SNR_lin (within 0.79 to 1.23), and the first fit, over every bin, 0.51² + 2.46² / SNR_lin (7.8 m against 12.4 m, 9.5 m against 24.7 m). Both come back from the per-bin values in `summary.json` (`snr_median_db`, `white_robust_m`, `n`) without the sessions:

```bash
PYTHONPATH=src python -c "
import importlib.util, json, sys
s = importlib.util.spec_from_file_location('lmn', 'analysis/lte_measured_noise.py')
m = importlib.util.module_from_spec(s); sys.modules['lmn'] = m; s.loader.exec_module(m)
b = json.load(open('analysis/results/lte-measured-noise/summary.json'))['snr_bins']
print(m.fit_white(b), m.fit_white(b, snr_min_db=-1e9))"
```

It prints 0.742 and 2.320, then 0.723 and 2.343.

## Buffer stamps and the 1,800 s capture

With the recorder's buffer stamps the front end at `8892fca` flags 2 dropped-sample gaps on `20261110-1759-static-out-long-e5060` (19,201 samples each, at samples 1,116,451,901 and 1,785,111,382); at `e9a9053` it flagged 21, mostly in pairs about 7,777 samples apart with sizes one sample either side of a whole number of frames. The recorder's own `gaps` and `gaps_suspected` are empty. Whether the two are real drops is `TBD`.

For comparison only (not in these results), the same file through the same front end with the `buffers` field removed from a copy of `sdr_a.json` (`--sidecar`), then the same script on that one session:

| Quantity | With stamps (these results) | Without stamps | At `e9a9053`: with / without |
|---|---|---|---|
| Gaps flagged | 2 | 0 | 21 / not recorded |
| Arcs, PCI 4 / 204 / 492 | 181 / 86 / 22 | 183 / 86 / 23 | 227 / 510 / 39, 186 / 759 / 36 |
| Same-eNB drift 492 − 4 (m/s) | −0.15 ± 0.16 | −0.11 ± 0.16 | −0.18 ± 0.16, −0.02 ± 0.11 |
| Same-eNB S(10 s), 492 − 4 (m) | 8.2 | 8.3 | 23.3, 6.9 |
| One cell S(100 s), 492 (m) | 141 | 135 | 114, 256 |

At `8892fca` the long-lag values no longer depend on the gap handling (S(10 s) and S(100 s) within 5 %, the drift within a quarter of its standard error; factors of 2 to 4 at `e9a9053`). They stay bounds: S(100 s) holds the dongle, the tower, multipath change and the tracker together.

## Read with

- Availability ("Tracked (of IQ)") is 10 Hz records × 0.1 s over the IQ on disk (`.cu8` bytes / 2 / `sample_rate_hz`), not over the first-to-last record span.
- The Allan rows (one cell's timing, and the loop-filtered CFO) are **upper bounds** on the clocks: the CFO floor is the same for a same-eNB pair, which shares one clock. They must not replace `offset_rw_m` or `drift_rw_mps`.
- eNB identity is by the table alone (`lte-cells-ottawa.csv`, a PCI registered once on that EARFCN), not checked against a position: `TBC`.
- `summary.json` is rounded to four significant figures and keeps the track breaks as a summary only.
