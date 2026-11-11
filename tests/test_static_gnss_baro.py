"""`analysis/static_gnss_baro.py`: GNSS and barometer noise of a static session (#30).
Synthetic inputs only; sessions are not in git."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "static_gnss_baro.py"
_spec = importlib.util.spec_from_file_location("static_gnss_baro", _PATH)
sgb = importlib.util.module_from_spec(_spec)
sys.modules["static_gnss_baro"] = sgb
_spec.loader.exec_module(sgb)


def test_gnss_noise_of_white_fixes_has_no_memory():
    rng = np.random.default_rng(0)
    t = np.arange(600.0)
    enu = np.array([1e5, -2e4, 70.0]) + rng.normal(0, [1.0, 2.0, 3.0], (600, 3))
    g = sgb.gnss_noise(t, enu, np.full((600, 3), 1.5))
    assert g["fixes"] == 600 and g["rate_hz"] == pytest.approx(1.0)
    assert [g[a]["sigma_m"] for a in sgb.AXES] == pytest.approx([1.0, 2.0, 3.0], rel=0.1)
    assert abs(g["east"]["lag1"]) < 0.15
    assert g["east"]["corr_time_s"] == pytest.approx(1.0)
    assert g["up"]["sim_sigma_m"] == pytest.approx(2.5 * 1.5)


def test_gnss_noise_sees_a_slow_wander():
    rng = np.random.default_rng(1)
    t = np.arange(600.0)
    phi = np.exp(-1 / 60.0)  # Gauss-Markov, 60 s
    x = np.zeros(600)
    for k in range(1, 600):
        x[k] = phi * x[k - 1] + rng.normal(0, 0.3)
    enu = np.c_[x, x, x]
    g = sgb.gnss_noise(t, enu, np.ones((600, 3)))
    assert g["north"]["lag1"] > 0.9
    assert 20 < g["north"]["corr_time_s"] < 150


def test_baro_noise_splits_white_noise_and_drift():
    rng = np.random.default_rng(2)
    t = np.arange(6000) * 0.1
    alt = 312.0 + 0.5 / 60 * t + rng.normal(0, 0.2, t.size)
    b = sgb.baro_noise(t, alt)
    assert b["white_sigma_m"] == pytest.approx(0.2, rel=0.1)
    assert b["drift_m_per_min"] == pytest.approx(0.5, abs=0.02)
    assert b["wander_10s_means_sigma_m"] == pytest.approx(0.2 / np.sqrt(100), rel=0.3)


def test_markdown_writes_deviations_only():
    rng = np.random.default_rng(3)
    t = np.arange(100.0)
    enu = np.array([12345.6, 7890.1, 98.7]) + rng.normal(0, 1, (100, 3))
    alt = 321.9 + rng.normal(0, 0.1, 100)
    md = sgb.markdown(
        "s", "abc", sgb.gnss_noise(t, enu, np.ones((100, 3))), sgb.baro_noise(t, alt)
    )
    for absolute in ("12345", "7890", "98.7", "321.9"):
        assert absolute not in md


def test_sim_values_are_what_the_scenarios_draw():
    """The comparison columns are the models the committed scenarios run (`sim/models.py`), not
    `sim/sensors.BMP280`, which no scenario draws from."""
    import inspect

    from pnt.sim import models
    from pnt.sim.scenario import load

    for name in ("uc01-drone-circuit", "challenge-drone-outage", "realistic-nominal"):
        src = load(name)["sources"]
        assert src["baro"]["sigma_m"] == sgb.SIM_BARO_SIGMA_M
        assert src["gnss"]["sigma_m"] == sgb.SIM_GNSS_SIGMA_M
    bias = inspect.signature(models.baro).parameters["bias_sigma_m"].default
    assert bias == sgb.SIM_BARO_BIAS_SIGMA_M
    b = sgb.baro_noise(np.arange(100) * 0.1, np.zeros(100) + np.arange(100) * 1e-3)
    assert b["sim_noise_m"] == 0.5 and b["sim_bias_sigma_m"] == 1.0
