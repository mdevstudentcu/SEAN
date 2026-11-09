"""The tower error model of the calibrated EKF (`ekf.CALIBRATED`): our clock in the tower ranges,
multipath as a Gauss-Markov state, told-position error, and new site clocks seeded from the
calibrated ones. Consistency on the realistic set is the claim that matters (REQ-02)."""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.metrics import score
from pnt.nav import ESTIMATORS, ekf
from pnt.sim.scenario import T0_NS, generate, load

TOWER = [3000.0, 4000.0, 30.0]


def _pr(t_ns, emitter, rho, sigma=20.0, tower=TOWER):
    meta = {"emitter_enu": [float(x) for x in tower]}
    return Measurement(
        t_ns=t_ns, source="lte", kind="pseudorange", value=(float(rho),), sigma=(sigma,),
        emitter=emitter, meta=meta,
    )  # fmt: skip


def _started(**config) -> ekf.EKF:
    f = ekf.EKF(**{**ekf.CALIBRATED, **config})
    fix = (0.0, 0.0, 30.0)
    f.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=fix, sigma=(2.0,) * 3))
    return f


def test_registered_as_an_opt_in_estimator():
    assert ESTIMATORS["ekf"] is ekf.run  # the default is unchanged
    assert ESTIMATORS["ekf-calibrated"] is ekf.run_calibrated


def test_first_sight_adds_multipath_and_told_position_states():
    f = _started()
    f.process(_pr(0, "lte:0", 5000.0))
    mp = f.multipath_idx["lte:0"]
    pos, los0 = f.position_idx["lte:0"]
    assert np.sqrt(f.P[mp, mp]) == pytest.approx(20.0)  # multipath_ratio x reported sigma
    assert np.sqrt(np.diag(f.P)[pos : pos + 2]) == pytest.approx([100.0, 100.0])
    assert los0 == pytest.approx([-0.6, -0.8])  # tower to receiver, horizontal part


def test_pseudorange_jacobian_with_every_tower_error_state():
    f = _started()
    m = _pr(0, "lte:0", 5000.0)
    ekf.MODELS["pseudorange"](f, m)  # first sight: adds the blocks
    f.x[ekf.POS] = [40.0, -25.0, 30.0]  # the line of sight has turned since first sight
    pos = f.position_idx["lte:0"][0]
    f.x[pos : pos + 2] = [30.0, -60.0]
    x0 = f.x.copy()
    y0, H, _, gate = ekf.MODELS["pseudorange"](f, m)
    assert gate and H[0, ekf.CLK] == 1.0 and H[0, f.multipath_idx["lte:0"]] == 1.0
    assert np.any(H[0, pos : pos + 2] != 0.0)
    for j in range(len(x0)):
        f.x = x0.copy()
        f.x[j] += 1e-3
        y1 = ekf.MODELS["pseudorange"](f, m)[0]
        assert -(y1 - y0) / 1e-3 == pytest.approx(H[0, j], abs=1e-5)


def test_told_position_error_has_no_effect_along_the_first_line_of_sight():
    # That part is a constant range bias, which the site clock carries: modelled twice, any
    # common position offset could be explained as every tower having moved
    f = _started()
    m = _pr(0, "lte:0", 5000.0)
    ekf.MODELS["pseudorange"](f, m)
    _, H, _, _ = ekf.MODELS["pseudorange"](f, m)  # same place as at first sight
    pos = f.position_idx["lte:0"][0]
    assert H[0, pos : pos + 2] == pytest.approx([0.0, 0.0], abs=1e-12)


def test_multipath_state_is_a_stationary_gauss_markov_process():
    f = _started()
    f.process(_pr(0, "lte:0", 5000.0))
    mp = f.multipath_idx["lte:0"]
    f.x[mp] = 50.0
    f.P[mp, mp] = 4.0
    f.predict(int(f.multipath_tau_s * 1e9))
    assert f.x[mp] == pytest.approx(50.0 * np.exp(-1.0))
    phi2 = np.exp(-2.0)
    assert f.P[mp, mp] == pytest.approx(4.0 * phi2 + 20.0**2 * (1 - phi2), rel=1e-6)


def test_a_new_site_takes_its_drift_prior_from_the_calibrated_sites():
    f = _started()
    for i in range(3):
        f.process(_pr(0, f"lte:{i}", 5000.0))
    drifts = [5.8, 6.0, 6.2]
    for i, d in zip(f.clock_idx.values(), drifts, strict=True):
        f.x[i + 1] = d
        f.P[i + 1, i + 1] = 0.05**2
    mean, sigma = f.site_drift_prior()
    assert mean == pytest.approx(6.0)
    assert sigma == pytest.approx(np.sqrt(0.2**2 + 0.05**2))
    f.process(_pr(0, "lte:new", 5000.0))
    i = f.clock_idx["site:lte:new"]
    assert f.x[i + 1] == pytest.approx(6.0) and np.sqrt(f.P[i + 1, i + 1]) == pytest.approx(sigma)
    # A rollback resets it to the wide prior: the seed may have been learned during a spoof
    assert f._clock_prior["site:lte:new"] == (f.init_emitter_sigma, f.init_tower_drift_sigma)


def test_without_two_calibrated_sites_the_drift_prior_is_wide():
    f = _started()
    f.process(_pr(0, "lte:0", 5000.0))
    assert f.site_drift_prior() == (0.0, f.init_tower_drift_sigma)


def test_drift_seeding_is_off_unless_asked_for():
    # clock_model="calibrated" alone keeps the fixed prior; only CALIBRATED seeds
    f = _started(seed_site_drift=False)
    for i in range(3):
        f.process(_pr(0, f"lte:{i}", 5000.0))
    for i, d in zip(f.clock_idx.values(), [5.8, 6.0, 6.2], strict=True):
        f.x[i + 1] = d
        f.P[i + 1, i + 1] = 0.05**2
    f.process(_pr(0, "lte:new", 5000.0))
    i = f.clock_idx["site:lte:new"]
    assert f.x[i + 1] == 0.0 and np.sqrt(f.P[i + 1, i + 1]) == f.init_tower_drift_sigma


def test_gnss_free_covariance_is_honest_on_the_realistic_set_req02():
    # Regression guard, not a requirement: mean horizontal NEES over the GNSS-free part of the
    # realistic long outage, 2 for an honest filter. The model before this change gave ~5,000
    # (independent clocks) and ~20 (calibrated, our clock modelled, no tower error model).
    spec = load("realistic-long-outage")
    nees = []
    for seed in range(2):
        run = generate(spec, seed=seed)
        est = list(ekf.run_calibrated(run.measurements, origin_llh=spec["origin_llh"]))
        assert score(est, run.truth, spec, T0_NS).hpl_bound_frac == 1.0
        truth = {t.t_ns: t for t in run.truth}
        for e in est:
            if "gnss_unavailable" in e.flags and e.t_ns in truth:
                d = np.subtract(e.pos_enu, truth[e.t_ns].pos_enu)[:2]
                nees.append(d @ np.linalg.solve(np.reshape(e.pos_cov, (3, 3))[:2, :2], d))
    assert 0.5 < np.mean(nees) < 5.0
