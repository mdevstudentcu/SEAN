"""Filter consistency in CI (issue #10, RSK-03): does the filter's confidence match its errors?

NIS checks both directions: it averages 1 per dimension when the reported uncertainty is honest,
and moves far from 1 when the filter is over- or under-confident. NEES is only used as an upper
limit, because the constant-velocity model keeps it from falling much when noise is overstated.

The limits are regression guards, not requirements. They sit between honest filters and filters
whose stated noise is wrong by a factor of 2, and every run uses a fixed seed (REQ-10).
"""

from collections import defaultdict
from functools import cache

import msgspec
import numpy as np
import pytest

from pnt.metrics import score
from pnt.nav import baseline
from pnt.sim.scenario import T0_NS, generate, load

SEEDS = range(5)
# Regression guards, not requirements: between honest filters and noise misstated by 2x
NIS_PER_DIM_LIMITS = (0.6, 1.6)
NEES_MAX = 5.0
FUSED_KINDS = {"position_enu", "altitude", "pseudorange"}


def _misstate_noise(measurements, scale):
    """Tell the filter each sensor's noise is `scale` times its true value."""
    return [
        msgspec.structs.replace(m, sigma=tuple(s * scale for s in m.sigma))
        if m.kind in FUSED_KINDS
        else m
        for m in measurements
    ]


@cache  # deterministic; each misstated-noise test asks for the same run twice
def _stats(scenario, sigma_scale=1.0):
    """Mean horizontal NEES and per-source mean NIS per dimension, over SEEDS."""
    spec = load(scenario)
    nees, per_source = [], defaultdict(list)
    for seed in SEEDS:
        run = generate(spec, seed=seed)
        ekf = baseline.BaselineEKF(origin_llh=spec.get("origin_llh"))
        estimates = list(baseline.run(_misstate_noise(run.measurements, sigma_scale), ekf=ekf))
        nees.append(score(estimates, run.truth, spec, T0_NS).h_nees_mean)
        for source, dim, nis in ekf.nis_log:
            per_source[source].append(nis / dim)
    return float(np.mean(nees)), {s: float(np.mean(v)) for s, v in per_source.items()}


def _problems(scenario, sigma_scale=1.0):
    nees, nis = _stats(scenario, sigma_scale)
    low, high = NIS_PER_DIM_LIMITS
    problems = [f"{s}: NIS/dim {v:.2f}" for s, v in sorted(nis.items()) if not low <= v <= high]
    if nees > NEES_MAX:
        problems.append(f"NEES {nees:.2f}")
    return problems


@pytest.mark.parametrize("scenario", ["nominal", "gps-outage"])
def test_baseline_filter_is_consistent(scenario):
    assert _problems(scenario) == []


@pytest.mark.parametrize("scenario", ["nominal", "gps-outage"])
@pytest.mark.parametrize("sigma_scale", [0.5, 2.0], ids=["over-confident", "under-confident"])
def test_check_catches_a_filter_with_misstated_noise(scenario, sigma_scale):
    assert _problems(scenario, sigma_scale) != []
    # ...and for the right reason: understated noise pushes NIS up, overstated pushes it down
    _, nis = _stats(scenario, sigma_scale)
    low, high = NIS_PER_DIM_LIMITS
    if sigma_scale < 1:
        assert any(v > high for v in nis.values())
    else:
        assert any(v < low for v in nis.values())
