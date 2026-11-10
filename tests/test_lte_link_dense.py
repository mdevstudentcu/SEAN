"""The dense LTE baseband check (analysis/lte_link_dense.py, #124): link budget and a tiny run.

Synthetic signals only. Thresholds are regression guards set from what the script showed on these
seeds, with margin; none is a requirement.
"""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "analysis" / "lte_link_dense.py"


@pytest.fixture(scope="module")
def dense():
    spec = importlib.util.spec_from_file_location("lte_link_dense", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up by name
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def test_link_budget_puts_a_near_boresight_sector_above_a_far_back_lobe_one(dense):
    b = dense.Budget()
    rx = np.array([0.0, 0.0, 30.0])
    near = dense.Sector(1, "a", (0.0, 300.0, 40.0), 180.0, 60.0, 46.0)  # 300 m, facing rx
    far = dense.Sector(2, "b", (0.0, 3000.0, 40.0), 0.0, 60.0, 46.0)  # 3 km, facing away
    omni = dense.Sector(3, "c", (0.0, 3000.0, 40.0), 0.0, None, 46.0)  # empty beamwidth
    assert dense.sector_gain_db(near, rx, b) == 0.0
    assert dense.sector_gain_db(far, rx, b) == -b.front_to_back_db
    assert dense.sector_gain_db(omni, rx, b) == 0.0
    p_near, p_far, p_omni = (dense.rx_band_power_dbm(s, rx, b) for s in (near, far, omni))
    # Exponent 3.5 over a 10x distance is 35 dB, plus the 25 dB back lobe: 60 dB.
    assert p_near - p_far == pytest.approx(10 * 3.5 + 25, abs=0.5)
    assert p_omni - p_far == pytest.approx(25, abs=1e-9)
    assert dense.noise_dbm(b) == pytest.approx(-174 + 10 * np.log10(1.08e6) + 6, abs=1e-9)


def test_near_far_ladder_through_the_chain(dense):
    """Three registered eNBs at 0, -6 and -14 dB relative to the strongest, through the front end,
    the lookup and the EKF (3 s, GPS off at 2 s, seed 0)."""
    b = dense.Budget()
    rx = dense.TRUE_ENU
    picked = dense.pick_equal_power(5, dense.load_sectors())[:3]
    ref = dense.rx_band_power_dbm(picked[0], rx, b)
    ladder = tuple(
        replace(s, tx_power_dbw=s.tx_power_dbw + ref + rel - dense.rx_band_power_dbm(s, rx, b))
        for s, rel in zip(picked, (0.0, -6.0, -14.0), strict=True)
    )
    r = dense.run_case(dense.Case("ladder", tuple(rx), ladder), 0, b, 3.0, 2.0)
    by_rel = {round(s.rel_db): s for s in r.sectors}
    assert r.ghosts == []
    assert by_rel[0].tracked and by_rel[-6].tracked
    assert not any(s.wrong_timing for s in r.sectors)
    # Regression guard from this seed's run, with margin. Not a requirement.
    assert abs(by_rel[0].bias_m) < 5.0 and abs(by_rel[-6].bias_m) < 30.0
    # Known limit (#124), observed, not a target: a cell about 13 dB or more below a fully loaded
    # one is lost by the search and the tracker. See the `ladder` part of the script.
    assert not by_rel[-14].searched and not by_rel[-14].tracked
    assert r.lookup_cells == {dense.MATCHED: 2}


def test_near_far_floor_holds_without_the_noise_or_the_quantiser(dense):
    """Known limit (#124): the -16 dB cell is lost even with noise and quantiser off, so neither
    causes it (one strong cell, 1 s, seed 0). The -6 dB cell stays, as a check the path works."""
    b = dense.Budget()
    rx = dense.TRUE_ENU
    strong, weak = dense.pick_equal_power(5, dense.load_sectors())[:2]
    ref = dense.rx_band_power_dbm(strong, rx, b)
    off = dense.Knobs(noise=False, quantise=False)
    tracked = {}
    for rel in (-6.0, -16.0):
        w = replace(
            weak, tx_power_dbw=weak.tx_power_dbw + ref + rel - dense.rx_band_power_dbm(weak, rx, b)
        )
        case = dense.Case("two cells", tuple(rx), (strong, w), knobs=off)
        r = dense.run_case(case, 0, b, 1.0, 1.0, nav_eval=False)
        assert r.sectors[0].tracked and r.ghosts == []
        tracked[rel] = r.sectors[1].tracked
    assert tracked == {-6.0: True, -16.0: False}
