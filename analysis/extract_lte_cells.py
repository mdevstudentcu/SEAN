"""Build the LTE cell-to-site table and scan list for Ottawa from ISED's site data (issue #87).

Download the "Terrestrial Spectrum Licence Site Data Extract" (`Site_Data_Extract_FX.zip`) from
ISED's "Download SMS data" page; the raw file stays out of git. Then run:
    python analysis/extract_lte_cells.py <Site_Data_Extract_FX.zip>

Since 2026 the extract lists, for each LTE sector, its physical cell ID (PCI), its full cell ID
(PLMN-TAC-ECI) and its antenna azimuth. So a heard (EARFCN, PCI) maps to registered sites
directly (ADR-0023). Writes two files in data/reference/:
- `lte-cells-ottawa.csv`: one row per registered LTE sector we can tune, within RADIUS_KM.
- `lte-scan-list-ottawa.csv`: one row per downlink carrier, with how many sites use it.

Contact names, phone numbers, e-mail addresses and account numbers are never read out.
"""

import csv
import io
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ORIGIN = (45.3876, -75.6960)  # Carleton campus, the scenarios' session origin
RADIUS_KM = 10.0
NEAR_KM = 3.0  # "near" column in the scan list
MIN_MHZ, MAX_MHZ = 600.0, 1750.0  # the radios' usable range for cellular bands
MIN_BW_MHZ = 1.4  # PSS/SSS need an LTE carrier; narrower filings (e.g. 0.2 MHz) are not one
REF = Path(__file__).parents[1] / "data" / "reference"

# Downlink bands in range, from 3GPP TS 36.101 table 5.7.3-1: (band, F_DL_low, F_DL_high,
# N_Offs-DL). Where bands overlap, the first listed wins (B12 over B17, B5 over B26), so one
# frequency always gives one EARFCN; the radio tunes the frequency, not the band. TBC against
# what the cells broadcast.
BANDS = [
    (71, 617.0, 652.0, 68586),
    (29, 717.0, 728.0, 9660),
    (12, 729.0, 746.0, 5010),
    (13, 746.0, 756.0, 5180),
    (14, 758.0, 768.0, 5280),
    (5, 869.0, 894.0, 2400),
]
# Uplink ranges of the same bands: a filing whose "tx" falls here and whose "rx" falls in that
# band's downlink has the two swapped
UPLINK = {71: (663.0, 698.0), 12: (699.0, 716.0), 13: (777.0, 787.0), 14: (788.0, 798.0),
          5: (824.0, 849.0)}  # fmt: skip
# The extract's PLMN field drops Bell's MCC on some rows
PLMN_FIX = {"610": "302610"}

CELL_COLUMNS = [
    "earfcn", "pci", "band", "dl_mhz", "bw_mhz", "licensee", "plmn", "tac", "eci", "enb_id",
    "cell_local_id", "lat", "lon", "ant_height_agl_m", "azimuth_deg", "h_beamwidth_deg",
    "tx_power_dbw", "location", "flags", "date_last_changed", "upload_date", "dist_km",
]  # fmt: skip
SCAN_COLUMNS = [
    "earfcn", "band", "dl_mhz", "bw_mhz", "licensee", "sites", "cells", "sites_near",
    "nearest_km", "flags",
]  # fmt: skip


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


def band_of(mhz):
    for band, lo, hi, _ in BANDS:
        if lo <= mhz <= hi:
            return band
    return None


def earfcn(mhz):
    """Nearest downlink EARFCN, and whether `mhz` sits off the 100 kHz raster."""
    for _band, lo, hi, offset in BANDS:
        if lo <= mhz <= hi:
            n = round((mhz - lo) * 10)
            return offset + n, abs((mhz - lo) * 10 - n) > 1e-6
    return None, False


def downlink(tx, rx):
    """The downlink frequency of a filing, and a flag if its tx and rx were swapped."""
    if band_of(tx) is not None:
        return tx, ""
    for band, (lo, hi) in UPLINK.items():
        if lo <= tx <= hi and rx is not None and band_of(rx) == band:
            return rx, "tx_rx_swapped"
    return None, ""


def parse_cell_id(cell_id):
    """'302220-29100-51920927' -> (plmn, tac, eci)."""
    parts = cell_id.strip().split("-")
    if len(parts) != 3 or not parts[2].isdigit():
        return "", "", None
    return PLMN_FIX.get(parts[0], parts[0]), parts[1], int(parts[2])


def read(path):
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"))
        header = [h.strip().rstrip("*") for h in next(reader)]
        for row in reader:
            if len(row) == len(header):
                yield dict(zip(header, row, strict=True))


def main(path):
    cells = {}
    for r in read(path):
        if r["technology"].strip() != "LTE":
            continue
        lat, lon = number(r["latitude"]), number(r["longitude"])
        tx, rx, bw = number(r["tx_frequency"]), number(r["rx_frequency"]), number(r["bandwidth"])
        if None in (lat, lon, tx, bw) or not MIN_MHZ <= tx <= MAX_MHZ or bw < MIN_BW_MHZ:
            continue
        dist = distance_km(lat, lon)
        if dist > RADIUS_KM:
            continue
        dl, swapped = downlink(tx, rx)
        if dl is None:
            continue
        n, off_raster = earfcn(dl)
        plmn, tac, eci = parse_cell_id(r["cell_id"])
        pci = r["physical_id"].strip()
        if eci is None or not pci.isdigit():
            continue
        flags = [f for f in (swapped, "off_raster" if off_raster else "") if f]
        if bw not in (1.4, 3, 5, 10, 15, 20):
            flags.append("nonstandard_bw")
        key = (n, int(pci), eci)
        cells[key] = [
            n,
            int(pci),
            band_of(dl),
            f"{dl:g}",
            f"{bw:g}",
            r["licensee_name"].strip(),
            plmn,
            tac,
            eci,
            eci >> 8,
            eci & 0xFF,
            f"{lat:.6f}",
            f"{lon:.6f}",
            r["tx_ant_height"].strip(),
            r["tx_ant_azimuth"].strip(),
            r["tx_ant_horiz_beamwidth"].strip(),
            r["tx_power"].strip(),
            " ".join(r["location"].split()),
            ";".join(flags),
            r["date_last_changed"].strip(),
            r["upload_date"].strip(),
            f"{dist:.2f}",
        ]
    rows = sorted(cells.values(), key=lambda x: (x[0], x[1], float(x[-1])))
    write(REF / "lte-cells-ottawa.csv", CELL_COLUMNS, rows)

    carriers = defaultdict(lambda: {"sites": set(), "near": set(), "cells": 0, "km": 1e9})
    for c in rows:
        k = (c[0], c[2], c[3], c[4], c[5], c[18])
        site = (c[11], c[12])
        carriers[k]["sites"].add(site)
        carriers[k]["cells"] += 1
        carriers[k]["km"] = min(carriers[k]["km"], float(c[-1]))
        if float(c[-1]) <= NEAR_KM:
            carriers[k]["near"].add(site)
    scan = [
        [*k[:5], len(v["sites"]), v["cells"], len(v["near"]), f"{v['km']:.2f}", k[5]]
        for k, v in carriers.items()
    ]
    scan.sort(key=lambda x: (-x[7], -x[5], x[0]))
    write(REF / "lte-scan-list-ottawa.csv", SCAN_COLUMNS, scan)

    collide = defaultdict(set)
    for c in rows:
        collide[(c[0], c[1])].add(c[9])  # (earfcn, pci) -> eNBs
    shared = sum(1 for v in collide.values() if len(v) > 1)
    print(f"{len(rows)} cells, {len(scan)} carriers; {shared} of {len(collide)} (EARFCN, PCI)")
    print("pairs are used by more than one eNB within", RADIUS_KM, "km")


def write(out, columns, rows):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        w.writerows(rows)
    print(f"wrote {out}: {len(rows)} rows")


if __name__ == "__main__":
    main(sys.argv[1])
