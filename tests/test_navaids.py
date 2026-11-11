"""data/reference/navaids.csv (#7): the subset rule and bands hold for every row.

The file is committed reference data, so this reads it directly: no network.
"""

import csv
import math
from pathlib import Path

from pnt.core import frames

NAVAIDS = Path(__file__).resolve().parents[1] / "data" / "reference" / "navaids.csv"
ORIGIN = (45.3876, -75.6960, 70.0)  # Carleton, the scenarios' session origin
MAX_RANGE_KM = 150.0  # the subset rule in analysis/extract_navaids.py
VHF_TYPES = {"VOR", "VOR-DME", "VORTAC", "DME"}  # a DME's frequency is its paired VHF one


def rows():
    with open(NAVAIDS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_only_the_wanted_types_within_150_km():
    rs = rows()
    assert rs
    for r in rs:
        assert r["type"] in VHF_TYPES | {"NDB"}, r["ident"]
        e, n, _ = frames.llh_to_enu((float(r["lat"]), float(r["lon"]), ORIGIN[2]), ORIGIN)
        d_km = math.hypot(e, n) / 1000
        assert d_km <= MAX_RANGE_KM, r["ident"]
        assert abs(d_km - float(r["distance_km"])) <= 0.05, r["ident"]


def test_every_frequency_is_in_its_type_band():
    for r in rows():
        f_khz = float(r["frequency_khz"])
        if r["type"] == "NDB":
            assert 190 <= f_khz <= 1750, r["ident"]
        else:
            assert 108_000 <= f_khz <= 118_000, r["ident"]


def test_yow_vor_is_on_114_6_mhz():
    (yow,) = [r for r in rows() if r["ident"] == "YOW"]
    assert yow["type"] == "VOR-DME"
    assert float(yow["frequency_khz"]) == 114_600
