# How these results were made (#173)

Evidence: **real sessions**, static, payload Pi, one NESDR SMArt v5, recorded on 2026-11-10 at the change that is `ee20817` on `main` (each `meta.yaml` names the local commit it had then), with no GPS fix (no position truth; NTP, not PPS, time). Raw IQ stays in `data/sessions/` (not in git).

## Commands

Analysis at `2408c19`. Front end at `3e97678` for the 60 s and 30 s sessions and at `060445f` for the 1,800 s one; no file under `src/` differs between the three. These are the commits on `main`. The runs were made on the branch before it was rebased twice and rebase-merged; each commit named here has the same change as the branch commit it ran at (`git patch-id`, `just recite`). The second rebase brought in #171's coherent LTE integration. #171 changed `src/pnt/frontends/lte/tracker.py` and `frontend.py`; its default output was checked identical on 10 real captures in #171. Re-run at the twice-rebased branch head, whose `src/` and `analysis/lte_measured_noise.py` are those of `9b129aa`, on the three sessions on the laptop (`20261110-1305-lte-outside`, `20261110-lte-outside-5145`, `-5255`): their 13 rows in `summary.md` (3 session, 6 cell, 4 pair) came out identical but for the commit columns, as they did after the first rebase. The other 12 sessions are on the Pi only: **regenerate everything at the merged commit** with the commands below, so that `summary.md` names a commit on `main`.

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

## The white-σ fit: SNR ≥ −8 dB only

`summary.md`, `summary.json` and `white_vs_snr.png` still show the first fit, over every SNR bin: σ² = 0.51² + 2.46² / SNR_lin. Below −8 dB it read 7.8 m against the measured 12.4 m (−11 to −8 dB) and 9.5 m against 24.7 m (−14 to −11 dB), so the script now fits only the bins at or above `FIT_MIN_SNR_DB` (−8 dB, `TBC`; from `ff51d65`) and keeps each weaker bin's measured σ. The per-bin values the fit uses (`snr_median_db`, `white_robust_m`, `n`) are in `summary.json`, so the same `fit_white` gives the new fit without the sessions: σ² = 0.64² + 2.28² / SNR_lin (m, 10 Hz), within 0.79 to 1.23 of each fitted bin. The same call on every bin returns 0.507 and 2.460, the committed fit, so the rounded JSON values do not move it at this precision.

```bash
PYTHONPATH=src python -c "
import importlib.util, json, sys
s = importlib.util.spec_from_file_location('lmn', 'analysis/lte_measured_noise.py')
m = importlib.util.module_from_spec(s); sys.modules['lmn'] = m; s.loader.exec_module(m)
b = json.load(open('analysis/results/lte-measured-noise/summary.json'))['snr_bins']
print(m.fit_white(b), m.fit_white(b, snr_min_db=-1e9))"
```

A regeneration (above) replaces the three files with the −8 dB fit.

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
