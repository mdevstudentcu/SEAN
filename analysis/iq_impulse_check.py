"""Impulsive interference in an RTL-SDR `.cu8` capture: a check before ADS-B captures (#22).

Per sample, power |I + jQ|^2 about mid-scale (127.5); prints the median power and the fraction
of samples more than 10x and 30x above it. For Gaussian noise the power is exponential, so
2^-10 (0.1 %) of samples exceed 10x the median and 2^-30 exceed 30x; impulsive interference
raises both. The pass level is `TBC` (`deploy/pi/RUNBOOK.md` H). Needs only numpy, so it
runs on the Pi from `~/pnt`:

    .venv/bin/python analysis/iq_impulse_check.py /tmp/check.cu8 [--seconds 10 --rate 2.4e6]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def impulse_stats(raw: np.ndarray, ratios: tuple[float, ...] = (10.0, 30.0)) -> dict:
    """`raw` is interleaved unsigned 8-bit I/Q. Median power and, for each ratio, the fraction
    of samples whose power exceeds ratio x median."""
    raw = np.asarray(raw, dtype=np.uint8)
    n = raw.size // 2
    x = raw[: 2 * n].astype(np.float32) - 127.5
    p = x[0::2] ** 2 + x[1::2] ** 2
    med = float(np.median(p)) if n else float("nan")
    out = {"samples": int(n), "median_power": med}
    for r in ratios:
        out[f"frac_gt_{r:g}x"] = float(np.mean(p > r * med)) if n else float("nan")
    return out


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("capture", type=Path, help=".cu8 file")
    a.add_argument("--seconds", type=float, default=None, help="only the first N seconds")
    a.add_argument("--rate", type=float, default=2.4e6, help="sample rate, S/s (with --seconds)")
    a.add_argument("--skip", type=float, default=0.5, help="seconds skipped at the start")
    o = a.parse_args()
    start = 2 * int(o.skip * o.rate)
    count = -1 if o.seconds is None else 2 * int(o.seconds * o.rate)
    raw = np.fromfile(o.capture, dtype=np.uint8, count=count, offset=start)
    print(json.dumps({"capture": o.capture.name, **impulse_stats(raw)}))


if __name__ == "__main__":
    main()
