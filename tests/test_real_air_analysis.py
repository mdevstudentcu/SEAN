"""The two scripts behind the first real-air numbers: `analysis/lte_single_cell.py` and
`analysis/adsb_avr_capture.py`. Synthetic inputs only; the sessions themselves are not in git."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_ANALYSIS = Path(__file__).parents[1] / "analysis"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ANALYSIS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


single = _load("lte_single_cell")
avr = _load("adsb_avr_capture")
vor = _load("vor_quality")


def test_noise_split_white_noise_on_a_quadratic():
    rng = np.random.default_rng(0)
    t = np.arange(500) * 0.1
    pr = 3e5 + 40.0 * t - 0.3 * t**2 + rng.normal(0.0, 0.7, t.size)
    white, wander, resid = single.noise_split(t, pr)
    assert white == pytest.approx(0.7, rel=0.1)
    assert wander == pytest.approx(0.7, rel=0.1)  # nothing slow left once the quadratic is off
    assert resid.shape == t.shape


def test_noise_split_puts_a_random_walk_in_wander_not_white():
    rng = np.random.default_rng(1)
    t = np.arange(500) * 0.1
    walk = np.cumsum(rng.normal(0.0, 0.5, t.size))
    white, wander, _ = single.noise_split(t, walk + rng.normal(0.0, 0.7, t.size))
    assert white < 1.0
    assert wander > 2.0 * white


def test_noise_split_needs_four_epochs():
    with pytest.raises(ValueError):
        single.noise_split([0.0, 0.1, 0.2], [1.0, 2.0, 3.0])


def test_spread_times_keeps_order_inside_the_span():
    t = avr.spread_times(198, 1_000_000_000, 59.4)
    assert len(t) == 198
    assert t[0] == 1_000_000_000
    assert all(b > a for a, b in zip(t, t[1:], strict=False))
    assert t[-1] < 1_000_000_000 + 59.4e9
    assert avr.spread_times(0, 0, 1.0) == []


def test_capture_span_from_the_sidecar():
    t0, span = avr.capture_span({"t_ns": 5, "samples": 2_400_000, "sample_rate_hz": 2.4e6})
    assert (t0, span) == (5, 1.0)


def test_circular_spread_tight_radials_across_north():
    assert vor.circular_std_deg([358.0, 0.0, 2.0]) == pytest.approx(1.63, abs=0.05)


def test_circular_spread_of_radials_all_round_is_large():
    assert vor.circular_std_deg(np.arange(0.0, 360.0, 30.0)) == float("inf")
    assert vor.circular_std_deg([10.0, 130.0, 250.0, 40.0]) > 60.0


def test_vor_summary_counts_idents_and_skips_bad_lines():
    line = (
        '{"timestamp": 1.0, "radial_deg": %s, "frequency_mhz": 114.6, "ident": %s,'
        ' "signal_quality": {"snr_30hz_db": 30.0, "snr_9960hz_db": %s}}'
    )
    s = vor.summarise([line % (100, '"YOW"', 12.0), line % (102, "null", -1.0), "not json"])
    assert s["windows"] == 2
    assert s["idents"] == {"YOW": 1}
    assert s["snr9960_max"] == 12.0
    assert s["freq_mhz"] == [114.6]
