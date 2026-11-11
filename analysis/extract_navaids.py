"""Build data/reference/navaids.csv from OurAirports' navaids.csv (issue #7).

Download https://davidmegginson.github.io/ourairports-data/navaids.csv (public domain, about
11,000 navaids and 1.5 MB; the full file stays out of git), then run:

    python -I analysis/extract_navaids.py <navaids.csv> data/reference/navaids.csv

Keeps the VOR, VOR-DME, VORTAC, DME and NDB rows within MAX_RANGE_KM (horizontal, WGS84) of
Carleton, the scenarios' session origin, nearest first. Values are copied as published, in the
source's units (kHz, feet); `distance_km` is computed. Standard library only, so it runs with
`python -I` on the untrusted download.
"""

import csv
import math
import sys

ORIGIN = (45.3876, -75.6960, 70.0)  # Carleton campus, the scenarios' session origin
MAX_RANGE_KM = 150.0
TYPES = ("VOR", "VOR-DME", "VORTAC", "DME", "NDB")
# (output column, source column)
COLUMNS = (
    ("ident", "ident"),
    ("name", "name"),
    ("type", "type"),
    ("frequency_khz", "frequency_khz"),
    ("lat", "latitude_deg"),
    ("lon", "longitude_deg"),
    ("elevation_ft", "elevation_ft"),
    ("slaved_variation_deg", "slaved_variation_deg"),
    ("magnetic_variation_deg", "magnetic_variation_deg"),
    ("dme_channel", "dme_channel"),
    ("country", "iso_country"),
    ("airport", "associated_airport"),
    ("ourairports_id", "id"),
)

A = 6378137.0  # WGS84
F = 1 / 298.257223563
E2 = F * (2 - F)


def ecef(lat: float, lon: float, h: float) -> tuple[float, float, float]:
    la, lo = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return (
        (n + h) * math.cos(la) * math.cos(lo),
        (n + h) * math.cos(la) * math.sin(lo),
        (n * (1 - E2) + h) * math.sin(la),
    )


def horizontal_km(lat: float, lon: float) -> float:
    """East-north distance from ORIGIN, at the origin's height (as pnt.core.frames.llh_to_enu)."""
    x0, y0, z0 = ecef(*ORIGIN)
    x, y, z = ecef(lat, lon, ORIGIN[2])
    dx, dy, dz = x - x0, y - y0, z - z0
    la, lo = math.radians(ORIGIN[0]), math.radians(ORIGIN[1])
    e = -math.sin(lo) * dx + math.cos(lo) * dy
    n = -math.sin(la) * math.cos(lo) * dx - math.sin(la) * math.sin(lo) * dy + math.cos(la) * dz
    return math.hypot(e, n) / 1000.0


def main(src: str, out: str) -> None:
    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    kept = []
    for r in rows:
        if r["type"] not in TYPES or not r["latitude_deg"] or not r["longitude_deg"]:
            continue
        d = horizontal_km(float(r["latitude_deg"]), float(r["longitude_deg"]))
        if d <= MAX_RANGE_KM:
            kept.append((d, r))
    kept.sort(key=lambda dr: (dr[0], dr[1]["ident"]))
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow([c for c, _ in COLUMNS] + ["distance_km"])
        for d, r in kept:
            w.writerow([r[s] for _, s in COLUMNS] + [f"{d:.1f}"])
    print(f"kept {len(kept)} of {len(rows)} navaids -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
