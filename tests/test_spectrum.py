"""rtl_power sweeps to band power for the RF survey (#20), on hand-made CSV rows."""

import numpy as np
import pytest

from pnt.frontends import spectrum

STEP = 100e3


def _rows(lo_mhz: float, hi_mhz: float, power, stamp="2026-11-10, 03:00:00") -> list[str]:
    """rtl_power rows of 2 MHz hops; `power(f_hz)` gives each bin's dB."""
    rows = []
    for lo in np.arange(lo_mhz, hi_mhz, 2.0):
        lo_hz = lo * 1e6
        f = lo_hz + np.arange(20) * STEP
        vals = ", ".join(f"{power(x):.2f}" for x in f)
        rows.append(f"{stamp}, {lo_hz:.0f}, {lo_hz + 2e6:.0f}, {STEP:.2f}, 1000, {vals}")
    return rows


def _quiet_with_lte(f):
    return -40.0 + (20.0 if 869e6 <= f <= 894e6 else 0.0)


def test_sweep_merges_passes_and_files(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("\n".join(_rows(800, 900, _quiet_with_lte)) + "\n")
    # a second pass, 2 dB higher everywhere, plus an unreadable row and a nan bin
    rows = _rows(800, 900, lambda f: _quiet_with_lte(f) + 2.0)
    rows[0] = rows[0].replace("-38.00", "nan", 1)
    b.write_text("\n".join(rows + ["garbage"]) + "\n")
    s = spectrum.read_rtl_power([a, b])
    assert np.all(np.diff(s.freq_hz) > 0)
    assert s.freq_hz[0] == pytest.approx(800e6) and s.freq_hz[-1] == pytest.approx(899.9e6)
    assert s.passes == 1  # the nan bin has one value; every other bin has two
    assert s.floor_db == pytest.approx(-39.0)  # median of -40 and -38


def test_band_power_finds_the_lte_band_and_leaves_the_rest_quiet(tmp_path):
    p = tmp_path / "power.csv"
    p.write_text("\n".join(_rows(500, 1700, _quiet_with_lte)) + "\n")
    bands = {b.name: b for b in spectrum.band_power(spectrum.read_rtl_power(p))}
    lte = bands["LTE B5 (850)"]
    assert lte.bins > 200
    assert lte.median_above_floor_db == pytest.approx(20.0)
    assert lte.occupied_frac == pytest.approx(1.0)
    assert bands["LTE B13 (700 C)"].occupied_frac == 0.0
    assert bands["GPS L1"].peak_above_floor_db == pytest.approx(0.0)
    fm = bands["FM broadcast"]  # below the sweep
    assert fm.bins == 0 and fm.median_above_floor_db is None


def test_empty_file_is_an_error(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    with pytest.raises(ValueError):
        spectrum.read_rtl_power(p)


def test_bands_are_ordered_and_within_the_tuner():
    for lo, hi in spectrum.BANDS.values():
        assert 24.0 <= lo < hi <= 1766.0
