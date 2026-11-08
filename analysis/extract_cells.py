"""Build data/reference/cells-ottawa.csv from ISED's spectrum licence site data (issue #8).

Download Site_Data_Extract.zip from ISED's "Download SMS data" page (the raw file stays out of
git), then run: python analysis/extract_cells.py <Site_Data_Extract.zip>

Keeps downlink carriers our RTL-SDR radios can tune to, within RADIUS_KM of Carleton, one row
per site, licensee and carrier frequency.
"""

import csv
import io
import math
import sys
import zipfile
from pathlib import Path

ORIGIN = (45.3876, -75.6960)  # Carleton campus, the scenarios' session origin
RADIUS_KM = 10.0
MIN_MHZ, MAX_MHZ = 600.0, 1750.0  # the radios' usable range for cellular bands
OUT = Path(__file__).parents[1] / "data" / "reference" / "cells-ottawa.csv"
COLUMNS = ["lat", "lon", "height_m", "carrier", "tx_mhz", "bw_mhz", "location", "dist_km"]


def distance_km(lat, lon):
    k = math.pi / 180
    dlat, dlon = (lat - ORIGIN[0]) * k, (lon - ORIGIN[1]) * k
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(ORIGIN[0] * k) * math.cos(lat * k) * math.sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main(path):
    rows = {}
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1")):
            lat, lon, freq = (
                number(r["LATITUDE"]),
                number(r["LONGITUDE"]),
                number(r["TRANSMIT_FREQ"]),
            )
            if None in (lat, lon, freq) or not MIN_MHZ <= freq <= MAX_MHZ:
                continue
            dist = distance_km(lat, lon)
            if dist > RADIUS_KM:
                continue
            ground, antenna = number(r["SITE_ELEV"]) or 0.0, number(r["TX_ANT_HT"]) or 0.0
            key = (round(lat, 5), round(lon, 5), r["LICENSEE"].strip(), freq)
            rows[key] = [
                f"{lat:.6f}",
                f"{lon:.6f}",
                f"{ground + antenna:.1f}",
                r["LICENSEE"].strip(),
                f"{freq:g}",
                r["TRANSMIT_BW"].strip(),
                " ".join(r["LOCATION"].split()),
                f"{dist:.2f}",
            ]
    ordered = sorted(rows.values(), key=lambda x: (float(x[-1]), x[3], float(x[4])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(ordered)
    print(f"wrote {OUT}: {len(ordered)} rows")


if __name__ == "__main__":
    main(sys.argv[1])
