"""Residual map learned while GPS is trusted (P11, #95, ADR-0032), and the place-dependent tower
error it is tested against. The paired 50-run evals are in the PR."""

import copy

import numpy as np
import pytest

from pnt.nav import ESTIMATORS, ekf, estimate
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


def _learn_cells(m, emitter, means, n=2, spread=0.0):
    """Cells 0, 1, ... along east, each with readings mean -/+ spread (n even)."""
    for i, mu in enumerate(means):
        for j in range(n):
            m.learn(emitter, (i * 10.0 + 1.0, 1.0), mu + (spread if j % 2 else -spread))


def test_map_shrinks_each_cell_by_the_emitter_spread():
    m = ResidualMap(MapParams(cell_m=10.0, min_samples=2, min_cells=5))
    sigma = 20.0
    means = [-60.0, -20.0, 0.0, 40.0, 80.0]
    _learn_cells(m, "lte:a", means[:4])
    assert m.correction("lte:a", (1.0, 1.0), sigma) == (0.0, 0.0)  # 4 cells: spread unknown
    m.learn("lte:a", (41.0, 1.0), 80.0)
    assert m.correction("lte:a", (41.0, 1.0), sigma) == (0.0, 0.0)  # one reading: not used
    m.learn("lte:a", (41.0, 1.0), 80.0)
    v = sigma**2 / 2  # each cell: two equal readings, so the reported noise sets it
    tau2 = np.var(means, ddof=1) - v
    k = tau2 / (tau2 + v)
    corr, var = m.correction("lte:a", (31.0, 9.0), sigma)
    assert corr == pytest.approx(k * 40.0)
    assert var == pytest.approx(k * v)
    assert m.correction("lte:a", (51.0, 1.0), sigma) == (0.0, 0.0)  # a cell never visited
    assert m.correction("lte:b", (1.0, 1.0), sigma) == (0.0, 0.0)  # another emitter
    # a sample variance above the reported noise sets the cell's noise
    m2 = ResidualMap(MapParams(cell_m=10.0, min_samples=2, min_cells=5))
    _learn_cells(m2, "lte:a", means, spread=30.0)
    v2 = (2 * 30.0**2) / 2  # sample variance 1800 over 2 readings
    tau2 = np.var(means, ddof=1) - v2
    assert m2.correction("lte:a", (31.0, 1.0), sigma)[1] == pytest.approx(tau2 / (tau2 + v2) * v2)


def test_map_corrects_nothing_where_cells_differ_only_by_noise():
    """No place error: cell means spread no more than their noise, so tau^2 = 0."""
    m = ResidualMap(MapParams(cell_m=10.0, min_samples=2, min_cells=5))
    _learn_cells(m, "lte:a", [-10.0, 5.0, 0.0, 8.0, -4.0])  # spread well under 20/sqrt(2)
    assert m.spread("lte:a", 20.0) == 0.0
    assert m.correction("lte:a", (1.0, 1.0), 20.0) == (0.0, 0.0)


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


def test_the_map_changes_the_filter_only_through_its_corrections(monkeypatch):
    """`ekf-map` on a place-dependent error: its corrections reach the filter's output, and with
    the map's corrections forced to zero the output is `ekf`'s, epoch for epoch."""
    spec = copy.deepcopy(load("residual-map"))
    spec["duration_s"] = 200  # one learning lap, then 80 s of the outage
    run = generate(spec, 1)
    plain = list(estimate("ekf", run.measurements, origin_llh=spec["origin_llh"]))
    mapped = list(estimate("ekf-map", run.measurements, origin_llh=spec["origin_llh"]))
    assert len(plain) == len(mapped)
    assert any(a.pos_enu != b.pos_enu for a, b in zip(plain, mapped, strict=True))
    monkeypatch.setattr(ResidualMap, "correction", lambda self, emitter, pos, sigma: (0.0, 0.0))
    off = list(estimate("ekf-map", run.measurements, origin_llh=spec["origin_llh"]))
    assert off == plain
