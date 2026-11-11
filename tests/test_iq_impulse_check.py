"""`analysis/iq_impulse_check.py` (#22): synthetic IQ only."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "iq_impulse_check.py"
_spec = importlib.util.spec_from_file_location("iq_impulse_check", _PATH)
iq = importlib.util.module_from_spec(_spec)
sys.modules["iq_impulse_check"] = iq
_spec.loader.exec_module(iq)


def _cu8(x: np.ndarray) -> np.ndarray:
    raw = np.empty(2 * x.size, dtype=np.uint8)
    raw[0::2] = np.clip(np.round(127.5 + x.real), 0, 255)
    raw[1::2] = np.clip(np.round(127.5 + x.imag), 0, 255)
    return raw


def test_gaussian_noise_exceeds_10x_median_in_two_to_the_minus_10():
    rng = np.random.default_rng(0)
    n = 400_000
    s = iq.impulse_stats(_cu8(8 * (rng.normal(size=n) + 1j * rng.normal(size=n))))
    assert s["samples"] == n
    assert s["frac_gt_10x"] == pytest.approx(2**-10, rel=0.25)
    assert s["frac_gt_30x"] < 1e-4


def test_one_sample_impulses_raise_the_fraction():
    rng = np.random.default_rng(1)
    n = 400_000
    x = 8 * (rng.normal(size=n) + 1j * rng.normal(size=n))
    x[::25] *= 10  # 4 % of samples, 20 dB up
    s = iq.impulse_stats(_cu8(x))
    assert 0.03 < s["frac_gt_10x"] < 0.05
    assert s["frac_gt_30x"] > 0.02
