"""Residual map learned while GPS is trusted (P11, #95, ADR-0032), and the place-dependent tower
error it is tested against. The paired 50-run evals are in the PR."""

import copy

import numpy as np
import pytest

from pnt.nav import ESTIMATORS, ekf
from pnt.nav.residual_map import MapParams, ResidualMap
from pnt.sim import models
from pnt.sim.scenario import T0_NS, generate, load


def test_place_error_repeats_at_a_place_and_has_its_size():
    rng = np.random.default_rng(0)
    grid = np.stack(np.meshgrid(np.arange(0, 2000, 40.0), np.arange(0, 2000, 40.0)), -1)
    pos = np.c_[grid.reshape(-1, 2), np.zeros(grid.size // 2)]
    twice = np.r_[pos[:10], pos[:10]]
    f = models.place_error(rng, 3, twice, sigma_m=20.0, corr_m=50.0)
    assert f[:, :10] == pytest.approx(f[:, 10:])  # same place, same error
    field = models.place_error(np.random.default_rng(1), 20, pos, sigma_m=20.0, corr_m=50.0)
    assert np.std(field) == pytest.approx(20.0, rel=0.15)  # regression guard on the draw
    # 40 m apart: correlation exp(-0.32) = 0.73; 400 m apart: none
    near = np.corrcoef(field[:, :-1].ravel(), field[:, 1:].ravel())[0, 1]
    far = np.corrcoef(field[:, :-10].ravel(), field[:, 10:].ravel())[0, 1]
    assert near == pytest.approx(np.exp(-(40.0**2) / (2 * 50.0**2)), abs=0.1)
    assert abs(far) < 0.1


def test_place_error_leaves_every_other_record_as_it_was():
    with_field = generate(load("residual-map"), 2).measurements
    without = generate(load("gps-outage"), 2).measurements
    assert len(with_field) == len(without)
    for a, b in zip(with_field, without, strict=True):
        assert (a.t_ns, a.source, a.kind, a.emitter, a.meta) == (
            b.t_ns,
            b.source,
            b.kind,
            b.emitter,
            b.meta,
        )
        if a.kind != "pseudorange":
            assert a == b
    assert any(a.value != b.value for a, b in zip(with_field, without, strict=True))


def test_map_cell_mean_and_variance():
    m = ResidualMap(MapParams(cell_m=10.0, min_samples=2))
    m.learn("lte:a", (3.0, 4.0), 30.0)
    assert m.correction("lte:a", (5.0, 5.0), 20.0) == (0.0, 0.0)  # one sample: not used yet
    m.learn("lte:a", (9.0, 1.0), 50.0)
    mean, var = m.correction("lte:a", (0.0, 9.9), 20.0)
    assert mean == pytest.approx(40.0)
    assert var == pytest.approx(max(200.0, 400.0) / 2)  # sample variance 200 under sigma^2
    m.learn("lte:a", (1.0, 1.0), 130.0)
    _, var = m.correction("lte:a", (1.0, 1.0), 20.0)
    assert var == pytest.approx(np.var([30.0, 50.0, 130.0], ddof=1) / 3)
    assert m.correction("lte:a", (11.0, 1.0), 20.0) == (0.0, 0.0)  # next cell
    assert m.correction("lte:b", (1.0, 1.0), 20.0) == (0.0, 0.0)  # other emitter


def test_learns_only_while_gnss_is_trusted():
    spec = copy.deepcopy(load("residual-map"))
    spec["duration_s"] = 180
    run = generate(spec, 0)
    f = ekf.EKF(origin_llh=spec["origin_llh"], residual_map={})
    counts = {}
    for m in run.measurements:
        f.process(m)
        t = (m.t_ns - T0_NS) / 1e9
        for mark in (119.0, 125.0, 179.0):  # outage 120-240 s
            if t >= mark and mark not in counts:
                counts[mark] = sum(c[0] for c in f.rmap.cells.values())
    assert counts[119.0] > 300  # one lap of six towers at 1 Hz, less first sights and rejects
    # 119-120 s, then GNSS still counts as trusted for gnss_timeout_s (2 s): 3 s of six towers
    assert counts[125.0] <= counts[119.0] + 3 * 6
    assert counts[179.0] == counts[125.0]


def test_registered():
    assert "ekf-map" in ESTIMATORS
