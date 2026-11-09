"""How good are the LTE pseudoranges of a static capture? (day-1 test, #21)

Reads the `/meas/lte` records that `pnt frontend lte` wrote and, for a receiver that did not move:

- removes the dongle clock by differencing every cell against the strongest cell on the same
  `rx_clock` (both see the same clock, so it cancels; dongles are never differenced together)
- removes a quadratic per difference (tower clock offset, drift and its slow change)
- reports the residual σ of each difference at 10 Hz and over 1 s, next to the σ the front end
  reported (root-sum-square of the two cells' σ), so the ratio says whether `sigma_scale` holds.

This measures precision (noise and fast multipath), not accuracy: tower positions and absolute
clock offsets are not needed and not checked.

    python analysis/lte_static_capture.py data/sessions/<name>-lte
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np

from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_session


def load(path) -> dict[tuple[str, str], list[Measurement]]:
    """Pseudoranges per (rx_clock, emitter)."""
    out: dict[tuple[str, str], list[Measurement]] = defaultdict(list)
    for _, m in read_session(session.mcap_path(path), topics=["/meas/lte"]):
        if isinstance(m, Measurement) and m.kind == "pseudorange":
            out[(m.meta.get("rx_clock", ""), m.emitter)].append(m)
    return out


def analyse(series: dict[tuple[str, str], list[Measurement]]) -> list[dict]:
    rows = []
    for clock in sorted({c for c, _ in series}):
        cells = {e: ms for (c, e), ms in series.items() if c == clock}
        ref = max(
            cells, key=lambda e: (len(cells[e]), np.median([m.meta["snr_db"] for m in cells[e]]))
        )
        ref_ms = [m for m in cells[ref] if m.meta["arc"] == 0]
        rt = np.array([m.t_ns for m in ref_ms], dtype=float) / 1e9
        rv = np.array([m.value[0] for m in ref_ms])
        rs = np.array([m.sigma[0] for m in ref_ms])
        for e, ms in sorted(cells.items()):
            row = {
                "rx_clock": clock,
                "emitter": e,
                "snr_db": float(np.median([m.meta["snr_db"] for m in ms])),
                "n": len(ms),
                "reported_sigma_m": float(np.median([m.sigma[0] for m in ms])),
                "ref": ref,
            }
            # The reference cell interpolated to this cell's times (the dongle clock is smooth
            # over 100 ms), only where both are in their first arc and 10 Hz apart at most.
            use = [m for m in ms if m.meta["arc"] == 0] if e != ref and rt.size > 1 else []
            t = np.array([m.t_ns for m in use], dtype=float) / 1e9
            j = np.searchsorted(rt, t)
            ok = (j > 0) & (j < rt.size)
            ok[ok] &= (rt[j[ok]] - rt[j[ok] - 1]) < 0.15
            if ok.sum() >= 20:
                t = t[ok]
                d = np.array([m.value[0] for m in use])[ok] - np.interp(t, rt, rv)
                resid = d - np.polyval(np.polyfit(t - t[0], d, 2), t - t[0])
                told = np.hypot(np.array([m.sigma[0] for m in use])[ok], np.interp(t, rt, rs))
                n1 = resid.size // 10 * 10
                row.update(
                    diff_sigma_10hz_m=float(np.std(resid)),
                    diff_told_m=float(np.median(told)),
                    diff_sigma_1s_m=float(np.std(resid[:n1].reshape(-1, 10).mean(1)))
                    if n1 >= 20
                    else float("nan"),
                    span_s=float(t[-1] - t[0]),
                )
            rows.append(row)
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", help="session folder or .mcap with /meas/lte records")
    a = p.parse_args()
    rows = analyse(load(a.session))
    print(f"{a.session}: precision of LTE pseudoranges, differenced against the strongest cell")
    print("| rx_clock | emitter | SNR (dB) | n | reported σ (m) | diff σ 10 Hz (m) | "
          "told σ of diff (m) | ratio | diff σ 1 s (m) | span (s) |")  # fmt: skip
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if "diff_sigma_10hz_m" not in r:
            note = "reference" if r["emitter"] == r["ref"] else "too few common epochs"
            print(f"| {r['rx_clock']} | {r['emitter']} | {r['snr_db']:.1f} | {r['n']} | "
                  f"{r['reported_sigma_m']:.2f} | {note} | | | | |")  # fmt: skip
            continue
        print(f"| {r['rx_clock']} | {r['emitter']} | {r['snr_db']:.1f} | {r['n']} | "
              f"{r['reported_sigma_m']:.2f} | {r['diff_sigma_10hz_m']:.2f} | "
              f"{r['diff_told_m']:.2f} | {r['diff_sigma_10hz_m'] / r['diff_told_m']:.2f} | "
              f"{r['diff_sigma_1s_m']:.2f} | {r['span_s']:.0f} |")  # fmt: skip
    print("ratio = achieved / reported σ of the difference: above 1 means sigma_scale is too low.")


if __name__ == "__main__":
    main()
