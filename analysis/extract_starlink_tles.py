"""Build data/reference/tle-starlink-<date>.txt from CelesTrak's Starlink GP file (issue #97).

Download https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle (the full file,
about 10,000 satellites and 1.8 MB, stays out of git), then run:

    python analysis/extract_starlink_tles.py <starlink.tle> <out.txt>

Keeps only the satellites that rise above MIN_ELEVATION_DEG over Carleton at some time in the
scenarios' window (scenario.T0_NS, for WINDOW_S), checked every STEP_S. Each kept satellite's
three lines are copied unchanged (CRLF line ends, as served), in the input's order. The margin
below the scenarios' TBC mask (25 deg) leaves room to study a lower mask without a new snapshot.
"""

import sys
from pathlib import Path

import numpy as np

from pnt.core.time import gps_ns_to_utc
from pnt.sim import leo
from pnt.sim.scenario import T0_NS

ORIGIN = (45.3876, -75.6960, 70.0)  # Carleton campus, the scenarios' session origin
MIN_ELEVATION_DEG = 10.0
WINDOW_S = 900.0  # scenarios up to 15 min from T0
STEP_S = 5.0  # a Starlink pass above 10 deg lasts minutes; 5 s cannot miss one


def rises(line1: str, line2: str, utc, t_s: np.ndarray) -> bool:
    try:
        pos, _ = leo.satellite_enu(line1, line2, utc, t_s, ORIGIN)
    except ValueError:  # SGP4 cannot propagate it (e.g. decayed): not usable
        return False
    elevation = np.degrees(np.arcsin(pos[:, 2] / np.linalg.norm(pos, axis=1)))
    return bool(np.any(elevation >= MIN_ELEVATION_DEG))


def main(src: str, out: str) -> None:
    raw = Path(src).read_bytes().decode("ascii").splitlines(keepends=True)
    lines = [ln for ln in raw if ln.strip()]
    utc = gps_ns_to_utc(T0_NS).replace(microsecond=0)  # T0 is a whole second
    t_s = np.arange(0.0, WINDOW_S + STEP_S, STEP_S)
    kept = []
    for i in range(0, len(lines) - 2, 3):
        if rises(lines[i + 1].rstrip(), lines[i + 2].rstrip(), utc, t_s):
            kept += lines[i : i + 3]
    Path(out).write_bytes("".join(kept).encode("ascii"))
    print(f"kept {len(kept) // 3} of {len(lines) // 3} satellites -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
