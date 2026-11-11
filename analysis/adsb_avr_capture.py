"""ADS-B reports from a recorded 1090 MHz IQ capture that readsb decoded to AVR text.

On the payload, readsb (Debian 3.14.1630, no RTL-SDR support) decodes the capture file after
the fact (`deploy/pi/RUNBOOK.md`):

    readsb --device-type ifile --ifile sdr_a.cu8 --iformat UC8 --raw --quiet > frames-avr.txt

Its `*<hex>;` lines carry **no time**. The ADS-B front end (`pnt.frontends.adsb`) needs one per
frame, so this spreads the frames evenly over the capture's span, in file order, starting at
the sidecar's `t_ns`. Order is kept; each time is wrong by up to the span (about a minute). The
front end only uses time to pair even/odd CPR frames (10 s window) and to age its local
reference (30 s), so the script also reruns with the frames squeezed into a tenth of the span:
if the report count moves, it depends on the made-up times.

Ranges are from `--origin` (default: the scenarios' Carleton origin), not from the receiver,
whose position is not recorded in the session.

    python analysis/adsb_avr_capture.py <session folder> [--plot track.png]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

from pnt.frontends import adsb

CARLETON = (45.3876, -75.6960, 70.0)  # src/pnt/sim/scenarios/*.yaml origin_llh
INK, GRID, LINE = "#52514e", "#e4e3df", "#2a78d6"


def spread_times(n: int, t0_ns: int, span_s: float) -> list[int]:
    """`n` frame times, evenly spaced in [t0, t0 + span), in order: a stand-in for real ones."""
    if n <= 0:
        return []
    step = span_s * 1e9 / n
    return [int(t0_ns + i * step) for i in range(n)]


def capture_span(sidecar: dict) -> tuple[int, float]:
    """(GPS ns of sample 0, seconds of samples) from an rtl_sdr sidecar."""
    return int(sidecar["t_ns"]), float(sidecar["samples"]) / float(sidecar["sample_rate_hz"])


def decode(lines: list[str], t0_ns: int, span_s: float, origin) -> tuple[adsb.Decoder, list]:
    dec = adsb.Decoder(tuple(origin))
    out = [
        m
        for t, line in zip(spread_times(len(lines), t0_ns, span_s), lines, strict=True)
        if (m := dec.add(t, line)) is not None
    ]
    return dec, out


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def plot(path: Path, by: dict, caption: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.6, 4.6), dpi=110)
    for e, ms in by.items():
        v = np.array([m.value for m in ms])
        ax.plot(v[:, 0] / 1e3, v[:, 1] / 1e3, "o-", color=LINE, ms=4, lw=1.2)
        ax.annotate(e, (v[-1, 0] / 1e3, v[-1, 1] / 1e3), color=INK, fontsize=8,
                    xytext=(4, 4), textcoords="offset points")  # fmt: skip
    ax.plot([0], [0], "+", color=INK, ms=10)
    ax.annotate("origin (Carleton)", (0, 0), color=INK, fontsize=8, xytext=(4, -10),
                textcoords="offset points")  # fmt: skip
    ax.set_xlabel("east of origin (km)", color=INK)
    ax.set_ylabel("north of origin (km)", color=INK)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(color=GRID, lw=0.8)
    ax.tick_params(colors=INK)
    for s in ax.spines.values():
        s.set_color(GRID)
    fig.text(0.01, 0.01, caption, color=INK, fontsize=7)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", help="folder with frames-avr.txt and sdr_a.json")
    p.add_argument("--origin", type=float, nargs=3, default=CARLETON, metavar=("LAT", "LON", "H"))
    p.add_argument("--plot", help="PNG of the reported positions about the origin")
    a = p.parse_args()
    folder = Path(a.session)
    lines = (folder / "frames-avr.txt").read_text().splitlines()
    t0, span = capture_span(json.loads((folder / "sdr_a.json").read_text()))
    dec, out = decode(lines, t0, span, a.origin)
    print(f"{folder.name}: {len(lines)} frames over {span:.1f} s; DF17/18 with good CRC "
          f"{dec.decoded}, other {dec.skipped}; {len(out)} reports")  # fmt: skip
    by: dict[str, list] = defaultdict(list)
    for m in out:
        by[m.emitter].append(m)
    print("| emitter | reports | altitude (m, as reported) | alt type | range from origin (km) "
          "| NACp | NIC |")  # fmt: skip
    print("|---|---|---|---|---|---|---|")
    for e, ms in sorted(by.items()):
        v = np.array([m.value for m in ms])
        h = [m.meta["llh"][2] for m in ms]
        rng = np.hypot(v[:, 0], v[:, 1]) / 1e3
        print(f"| {e} | {len(ms)} | {min(h):.0f}-{max(h):.0f} | "
              f"{','.join(sorted({m.meta['alt_type'] for m in ms}))} | "
              f"{rng.min():.1f}-{rng.max():.1f} | "
              f"{','.join(f'{x:g}' for x in sorted(set(v[:, 3])))} | "
              f"{','.join(f'{x:g}' for x in sorted(set(v[:, 4])))} |")  # fmt: skip
    _, squeezed = decode(lines, t0, span / 10, a.origin)
    print(f"times squeezed into {span / 10:.1f} s: {len(squeezed)} reports "
          f"({'same' if len(squeezed) == len(out) else 'DIFFERENT'} count)")  # fmt: skip
    if a.plot:
        plot(Path(a.plot), by, f"real session {folder.name}, at {commit()};\n"
             "frame times spread evenly (readsb gave none)")  # fmt: skip
        print(f"wrote {a.plot}")


if __name__ == "__main__":
    main()
