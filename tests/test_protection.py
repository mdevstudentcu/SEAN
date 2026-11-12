"""The protection-level factors match the integrity risk they are stated for (ADR-0056)."""

import math

import numpy as np

from pnt.integrity import mhss, protection


def test_horizontal_factor_bounds_a_two_dimensional_error_at_the_stated_risk():
    # A horizontal error is two-dimensional: on the major-axis sigma, P(r > k sigma) <= exp(-k^2/2)
    risk = mhss.Params().phmi
    assert math.exp(-(protection.K_H**2) / 2) <= risk
    assert protection.K_H == round(math.sqrt(2 * math.log(1 / risk)), 2)  # 5.68, no larger


def test_vertical_and_time_factors_are_the_one_dimensional_value():
    two_sided = math.erfc(protection.K_V / math.sqrt(2))
    assert two_sided <= 1e-7 < math.erfc((protection.K_V - 0.01) / math.sqrt(2))
    assert protection.K_T == protection.K_V


def test_hpl_scales_the_major_axis_sigma():
    cov = np.diag([9.0, 4.0, 1.0])  # sigma 3 m east, 2 m north
    assert protection.hpl(cov) == protection.K_H * 3.0
