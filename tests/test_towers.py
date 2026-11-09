import csv
import importlib.util
import zipfile
from pathlib import Path

import numpy as np
import pytest

from pnt.core.frames import llh_to_enu
from pnt.sim.scenario import (
    REFERENCE_DIR,
    SAME_SITE_M,
    generate,
    load,
    select_towers,
    tower_height_m,
)

CSV = REFERENCE_DIR / "cells-ottawa.csv"
ORIGIN = [45.3876, -75.6960, 70.0]
EXTRACTOR = Path(__file__).parents[1] / "analysis" / "extract_cells.py"


def _rows():
    with open(CSV, newline="") as f:
        return list(csv.DictReader(f))


def test_reference_file_only_has_nearby_tunable_carriers():
    rows = _rows()
    assert rows
    assert all(600 <= float(r["tx_mhz"]) <= 1750 for r in rows)
    assert all(float(r["dist_km"]) <= 10 for r in rows)


def test_selection_is_deterministic_nearest_first_and_respects_minimum():
    a = select_towers("cells-ottawa.csv", "TELUS", 886.25, count=6, min_km=0.8)
    assert a == select_towers("cells-ottawa.csv", "TELUS", 886.25, count=6, min_km=0.8)
    distances = [np.linalg.norm(llh_to_enu(x, ORIGIN)[:2]) for x in a]
    assert distances == sorted(distances) and distances[0] >= 750
    assert len({(x[0], x[1]) for x in a}) == 6


def test_asking_for_too_many_towers_is_a_clear_error():
    with pytest.raises(ValueError, match="sites match"):
        select_towers("cells-ottawa.csv", "TELUS", 886.25, count=100_000)


@pytest.mark.parametrize("name", ["realistic-nominal", "worst-nominal", "ottawa-towers"])
def test_scenarios_use_real_towers(name):
    run = generate(load(name), seed=0)
    towers = [m for m in run.measurements if m.kind == "pseudorange"]
    assert towers and all("emitter_llh" in m.meta for m in towers)
    for position in run.emitters.values():
        assert 750 < np.linalg.norm(position[:2]) < 10_500


def test_extractor_filters_and_deduplicates(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("extract_cells", EXTRACTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    header = "LICENSEE,TRANSMIT_FREQ,TRANSMIT_BW,LOCATION,LATITUDE,LONGITUDE,SITE_ELEV,TX_ANT_HT"
    rows = [
        'TELUS,886.25,5,"Near  Site",45.40,-75.70,80,30',
        'TELUS,886.25,5,"Near  Site",45.40,-75.70,80,30',
        "TELUS,2110,5,Too high,45.40,-75.70,80,30",
        "TELUS,886.25,5,Too far,46.40,-75.70,80,30",
    ]
    source = tmp_path / "raw.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("raw.csv", "\n".join([header, *rows]) + "\n")
    out = tmp_path / "out.csv"
    monkeypatch.setattr(module, "OUT", out)
    module.main(source)
    with open(out, newline="") as f:
        result = list(csv.DictReader(f))
    assert len(result) == 1
    assert result[0]["location"] == "Near Site" and result[0]["height_m"] == "110.0"


def test_a_site_filed_twice_counts_once():
    # Two TELUS filings for one Bank St mast sit 0.37 m apart in the ISED data
    towers = select_towers("cells-ottawa.csv", "TELUS", 886.25, count=6, min_km=0.8)
    for i, a in enumerate(towers):
        for b in towers[i + 1 :]:
            north = (a[0] - b[0]) * 111_132.0
            east = (a[1] - b[1]) * 111_320.0 * np.cos(np.radians(a[0]))
            assert np.hypot(north, east) >= SAME_SITE_M


def test_heights_without_ground_elevation_get_the_scenario_ground():
    assert tower_height_m(24.0, ground_m=70.0) == 94.0  # antenna height alone
    assert tower_height_m(108.0, ground_m=70.0) == 108.0  # ground already included
    towers = select_towers("cells-ottawa.csv", "TELUS", 886.25, count=6, min_km=0.8, ground_m=70)
    assert min(t[2] for t in towers) >= 70.0  # no tower below the ground it stands on
