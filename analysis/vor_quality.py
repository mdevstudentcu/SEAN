"""Did Voracious lock onto a VOR? A summary of its JSON Lines, one row per file.

`pnt.frontends.vor` turns every Voracious radial into a `bearing` record and thresholds nothing
(Voracious calls its quality fields relative within one run). Before a capture's radials are
used, this shows whether there was anything to lock onto:

- `ident`: windows in which Voracious decoded a Morse identifier, how many different ones, and
  the commonest. A station gives the same ident again and again; idents that never repeat are
  noise decoded as Morse
- 30 Hz and 9960 Hz SNR (dB), median and max: the AM reference and the FM subcarrier that
  carries the variable phase; a radial needs both
- radial spread (deg): circular standard deviation of the radials. A static receiver locked on
  one station gives a few degrees; radials spread over the circle are noise.

    python analysis/vor_quality.py <voracious output>.jsonl [...]

Voracious (MIT, https://github.com/xoolive/desperado) runs outside this repo:
`voracious <session>/sdr_a.cu8 -f cu8 -s <rate> -c <centre MHz> -v <VOR MHz> > out.jsonl`.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np


def circular_std_deg(deg) -> float:
    """Circular standard deviation, degrees: about the linear one for tight radials, and
    growing without bound as they spread over the whole circle."""
    a = np.radians(np.asarray(deg, dtype=float))
    if a.size == 0:
        return float("nan")
    r = math.hypot(float(np.mean(np.cos(a))), float(np.mean(np.sin(a))))
    return float(np.degrees(math.sqrt(-2.0 * math.log(r)))) if r > 1e-12 else float("inf")


def summarise(lines) -> dict:
    recs = []
    for line in lines:
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    q = [r.get("signal_quality") or {} for r in recs]
    idents = Counter(
        str(r["ident"]).strip().upper() for r in recs if (r.get("ident") or "").strip()
    )
    radials = [float(r["radial_deg"]) for r in recs if "radial_deg" in r]
    s30 = [float(x["snr_30hz_db"]) for x in q if "snr_30hz_db" in x]
    s99 = [float(x["snr_9960hz_db"]) for x in q if "snr_9960hz_db" in x]
    return {
        "windows": len(recs),
        "freq_mhz": sorted({float(r["frequency_mhz"]) for r in recs if "frequency_mhz" in r}),
        "idents": idents,
        "snr30_med": float(np.median(s30)) if s30 else float("nan"),
        "snr9960_med": float(np.median(s99)) if s99 else float("nan"),
        "snr9960_max": float(np.max(s99)) if s99 else float("nan"),
        "radial_spread_deg": circular_std_deg(radials),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("files", nargs="+", help="Voracious JSON Lines output")
    a = p.parse_args()
    print("| file | MHz | windows | ident: windows / distinct / commonest | 30 Hz SNR med (dB) "
          "| 9960 Hz SNR med / max (dB) | radial spread (deg) |")  # fmt: skip
    print("|---|---|---|---|---|---|---|")
    for f in a.files:
        s = summarise(Path(f).read_text().splitlines())
        mhz = ",".join(f"{x:g}" for x in s["freq_mhz"])
        ids = s["idents"]
        top = "{} x{}".format(*ids.most_common(1)[0]) if ids else "-"
        print(f"| {Path(f).name} | {mhz} | {s['windows']} | "
              f"{sum(ids.values())} / {len(ids)} / {top} | "
              f"{s['snr30_med']:.1f} | {s['snr9960_med']:.1f} / {s['snr9960_max']:.1f} | "
              f"{s['radial_spread_deg']:.0f} |")  # fmt: skip


if __name__ == "__main__":
    main()
