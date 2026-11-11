"""A detected GNSS position jump is refused, not followed (#184, REQ-04)."""

import copy
from types import SimpleNamespace

import msgspec
import numpy as np
import pytest

from pnt.integrity.jump_guard import JumpGuard
from pnt.nav import ESTIMATORS, ekf
from pnt.sim.scenario import T0_NS, generate, load

JUMP_M = 300.0
START_S = 150.0  # spoof-jump.yaml


GUARD = ESTIMATORS["ekf-guard"]  # opt-in (ADR-0038); `ekf` itself runs without the guard


def _run(spec, estimator=GUARD, seed=0):
    run = generate(spec, seed=seed)
    est = list(estimator(run.measurements, origin_llh=spec.get("origin_llh")))
    truth = {g.t_ns: g for g in run.truth}
    t = np.array([(e.t_ns - T0_NS) / 1e9 for e in est])
    err = np.array([np.subtract(e.pos_enu, truth[e.t_ns].pos_enu)[:2] for e in est])
    # GNSS in use: accepted within the timeout and not rejected since
    used = np.array([e.trust.get("gnss") == 1.0 and "gnss_excluded" not in e.flags for e in est])
    return est, t, err, used  # err: horizontal (east, north) error


def _jump(end_s=None):
    # 300 m east at 150 s, held to the end (360 s). Without towers, so that without GNSS the
    # filter dead-reckons, as on the challenge legs where it rejects the towers (#147)
    spec = copy.deepcopy(load("spoof-jump"))
    del spec["sources"]["lte"]
    if end_s is not None:
        spec["faults"][0]["end_s"] = end_s
    return spec


def _norm(err, offset=(0.0, 0.0)):
    return np.hypot(*(err - np.asarray(offset)).T)


def _at(t, x, s):
    return x[np.searchsorted(t, s - 1e-6)]


def test_detected_jump_is_not_followed_req04():
    spec = _jump()
    off = ekf.run  # the default: no guard, the code path main runs
    _, t, err_main, _ = _run(spec, off)
    _, t, err, used = _run(spec)
    after = t >= START_S + 30
    spoofed = (JUMP_M, 0.0)  # where the spoofer puts the receiver, from the truth
    assert np.all(_norm(err_main[after], spoofed) < JUMP_M / 2)  # without the guard: follows
    assert np.all(_norm(err[t >= START_S], spoofed) > JUMP_M / 2)  # with it: never near it
    assert not used[t >= START_S + 0.2].any()  # GNSS stays out to the end of the run


def test_honest_gps_returns_after_an_outage():
    spec = load("gps-outage")  # GPS lost 120 s to 240 s
    _, t, err, used = _run(spec)
    back = t[(t >= 240.0) & used]
    assert back.size and back[0] - 240.0 <= 1.0
    assert _norm(_at(t, err, 250.0)) < 10.0


@pytest.mark.parametrize("end_s", [160.0, 250.0])
def test_a_jump_that_ends_lets_gnss_back_in(end_s):
    _, t, err, used = _run(_jump(end_s=end_s))
    assert not used[(t >= START_S + 0.2) & (t < end_s)].any()
    back = t[(t >= end_s) & used]
    assert back.size and back[0] - end_s <= 1.0  # at the first fixes after the end
    assert _norm(_at(t, err, end_s + 5)) < 10.0


def test_held_offset_is_refused_however_long_the_spoofer_waits():
    # The free estimate's covariance grows without bound; the offset GNSS holds does not change.
    # Re-admission tests the offset against its own covariance, so waiting never gets it in.
    R = np.eye(3) * 2.5**2
    f = SimpleNamespace(
        x=np.zeros(6), P=np.eye(6), last_used={"gnss": 0}, gnss_timeout_ns=2 * 10**9, q_accel=1.0
    )
    g, H = JumpGuard(), np.hstack([np.eye(3), np.zeros((3, 3))])
    rng = np.random.default_rng(1)
    verdicts = []
    for k in range(1, 5 * 3600):  # an hour at 5 Hz
        f.P = np.eye(6) * (1.0 + k)  # coasting: position and velocity covariance grow
        offset = np.array([0.0 if k < 10 else 50.0, 0.0, 0.0])
        y = offset + rng.normal(0.0, 2.5, 3)
        verdicts.append(g.verdict(f, k * 200_000_000, y, H, R))
    assert verdicts[9] == "refuse" and g.latches == [10 * 200_000_000]
    assert set(verdicts[9:]) == {"refuse"}


def test_the_guard_is_opt_in():
    assert ekf.EKF().jump is None
    assert ESTIMATORS["ekf"] is ekf.run  # the default estimators are unchanged
    for name in ("ekf-guard", "ekf-imu-guard", "ekf-calibrated-guard"):
        assert ESTIMATORS[name].keywords["jump_guard"] is JumpGuard
    assert ESTIMATORS["ekf-imu-guard"].keywords["motion"] == "imu"
    assert ESTIMATORS["ekf-calibrated-guard"].func is ekf.run_calibrated


@pytest.mark.parametrize("estimator", ["ekf", "ekf-calibrated", "ekf-imu"])
def test_clean_runs_are_unchanged(estimator):
    spec = load("nominal")
    run = generate(spec, seed=0)
    fn = ESTIMATORS[f"{estimator}-guard"]
    off = ESTIMATORS[estimator]
    a = [msgspec.structs.astuple(e) for e in fn(run.measurements, origin_llh=spec["origin_llh"])]
    b = [msgspec.structs.astuple(e) for e in off(run.measurements, origin_llh=spec["origin_llh"])]
    assert repr(a) == repr(b)
