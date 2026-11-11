"""`analysis/false_alarm_rate.py` (#274): known onsets and exposure give the right rate and
upper bound. Synthetic alarm series only; no scenario or session is run."""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "false_alarm_rate.py"
_spec = importlib.util.spec_from_file_location("false_alarm_rate", _PATH)
far = importlib.util.module_from_spec(_spec)
sys.modules["false_alarm_rate"] = far
_spec.loader.exec_module(far)

S = 1_000_000_000


def _hour():
    """One hour at 10 Hz (36001 epochs, 3600 s of steps) and an all-clear alarm series."""
    t = np.arange(36001, dtype=np.int64) * (S // 10)
    return t, np.zeros(len(t), bool)


def _on(t, alarm, a_s, b_s):
    alarm[(t >= a_s * S) & (t < b_s * S)] = True


def test_known_onsets_and_exposure_give_the_rate_and_bound():
    t, alarm = _hour()
    _on(t, alarm, 100, 102)  # held 2 s: one onset
    _on(t, alarm, 200, 200.5)  # 0.5 s, under the 1 s hold: not an alarm
    _on(t, alarm, 300, 305)  # one onset, however long it lasts
    _on(t, alarm, 1000, 1010)  # inside the spoof window: a detection, not a false alarm
    window = [(900 * S, 1100 * S)]
    onsets, hours = far.count(t, alarm, window)
    assert [x / S for x in onsets] == [101.0, 301.0]  # where each run reached the hold
    assert hours == pytest.approx(3400 / 3600)  # the 200 s spoof window is not clean
    row = far.rate_row(len(onsets), hours)
    assert row["rate_per_h"] == pytest.approx(2 / (3400 / 3600))
    # exact one-sided 95 % Poisson bound for 2 events: chi2(0.95, 6) / 2 = 6.2958
    assert row["upper_per_h"] == pytest.approx(6.29579 / (3400 / 3600), rel=1e-5)


def test_zero_events_bound_is_three_over_t():
    t, alarm = _hour()
    onsets, hours = far.count(t, alarm)
    assert onsets == [] and hours == pytest.approx(1.0)
    row = far.rate_row(0, 10 * hours)
    assert row["rate_per_h"] == 0.0
    assert row["upper_per_h"] == pytest.approx(-math.log(0.05) / 10)  # 2.996 / T, "3/T"


def test_start_up_epochs_neither_alarm_nor_count_as_exposure():
    t, alarm = _hour()
    _on(t, alarm, 0, 20)  # the first fix's wide HPL: start-up, not an alert
    _on(t, alarm, 500, 503)
    valid = t >= 30 * S
    onsets, hours = far.count(t, alarm, valid=valid)
    assert [x / S for x in onsets] == [501.0]
    # steps count by the epoch they end on, as metrics.score: 30.0 s to 3600 s is 3570.1 s
    assert hours == pytest.approx(3570.1 / 3600)
