"""Pre-flight integrity prediction (#92): RAIM prediction for signals of opportunity."""

import copy

import numpy as np
import pytest
import yaml

from pnt.integrity import preflight
from pnt.sim.scenario import generate

SPEC = yaml.safe_load(
    """
name: small
duration_s: 40
dt_s: 0.1
origin_llh: [45.3876, -75.6960, 70.0]
trajectory: {type: loop, radius_m: 150, speed_mps: 8, altitude_m: 30}
sources:
  gnss: {rate_hz: 5, sigma_m: 2.5}
  baro: {rate_hz: 10, sigma_m: 0.5}
  lte: {model: pseudorange, rate_hz: 1, n_emitters: 5, ring_radius_m: [800, 3000],
        sigma_m: 20.0, clock_rw_m: 0.2, init_bias_m: 1000.0}
faults:
  - {type: outage, source: gnss, start_s: 12, end_s: 30}
  - {type: spoof_jump, source: gnss, start_s: 35, offset_enu_m: [300, 0, 0]}
"""
)


def test_plan_keeps_planned_denial_and_drops_attacks():
    spec = {**SPEC, "sources": {**SPEC["sources"]}}
    spec["sources"]["lte"] = {
        **SPEC["sources"]["lte"],
        "dropout": {"availability": 0.5, "block_s": 5},
    }
    planned, availability, kept, dropped = preflight.plan(spec)
    assert kept == ["outage"] and dropped == ["spoof_jump"]
    assert availability == {"lte": 0.5}
    assert planned["sources"]["lte"]["dropout"]["availability"] == 1.0
    assert spec["sources"]["lte"]["dropout"]["availability"] == 0.5  # the input is untouched


def test_reference_station_dropout_is_its_own():
    spec = copy.deepcopy(SPEC)
    spec["sources"]["lte"]["dropout"] = {"availability": 0.25, "block_s": 5}
    spec["reference"] = {
        "position_llh": [45.38625, -75.693446, 80.0],
        "sources": {"lte": {"sigma_m": 16.0, "dropout": {"availability": 0.64, "block_s": 5}}},
    }
    planned, availability, _, _ = preflight.plan(spec)
    assert availability == {"lte": 0.25, "reference:lte": 0.64}
    assert planned["reference"]["sources"]["lte"]["dropout"]["availability"] == 1.0
    run = generate(planned, seed=0)
    n_towers, n_epochs = 5, 40  # 1 Hz for 40 s: every record is scheduled, no draw removes any
    from_station = [m for m in run.measurements if m.receiver == "reference"]
    assert len(from_station) == n_towers * n_epochs
    meas, _ = preflight.noise_free(run, availability)
    sigmas = {(m.receiver, round(m.sigma[0], 6)) for m in meas if m.kind == "pseudorange"}
    assert sigmas == {("payload", 40.0), ("reference", 20.0)}  # 20 / 0.5, 16 / 0.8


def test_noise_free_values_are_the_truth():
    planned, availability, _, _ = preflight.plan(SPEC)
    run = generate(planned, seed=0)
    meas, passthrough = preflight.noise_free(run, availability)
    truth = {t.t_ns: t for t in run.truth}
    gnss = [m for m in meas if m.kind == "position_enu"]
    assert gnss and all(np.allclose(m.value, truth[m.t_ns].pos_enu) for m in gnss)
    pr = next(m for m in meas if m.kind == "pseudorange")
    e = np.asarray(pr.meta["emitter_enu"])
    assert pr.value[0] == pytest.approx(np.linalg.norm(np.subtract(truth[pr.t_ns].pos_enu, e)))
    assert passthrough == {}


def test_prediction_is_deterministic_and_flags_the_outage():
    a = preflight.predict(SPEC, seed=0)
    b = preflight.predict(SPEC, seed=0)
    assert np.array_equal(a.hpl_m, b.hpl_m)
    assert a.dropped_faults == ["spoof_jump"]
    during = (a.t_s > 14) & (a.t_s < 30)
    before = (a.t_s > 5) & (a.t_s < 12)
    assert np.all(a.hpl_m[during] > a.hpl_m[before].max())  # GPS lost: HPL grows


def test_prediction_matches_real_runs_without_attacks():
    spec = {**SPEC, "faults": SPEC["faults"][:1]}  # the planned outage only
    rows = [preflight.compare_one(spec, seed, "ekf", 50.0) for seed in (0, 1)]
    s = preflight.summarize(rows, 50.0)
    # regression guards, not requirements: the EKF covariance barely depends on the noise
    assert 0.95 < s["ratio_median"] < 1.05
    assert s["ratio_p05"] > 0.8 and s["ratio_p95"] < 1.2
    assert s["availability_agree"] > 0.95


def test_unavailable_windows_merge_saw_tooth():
    p = preflight.Prediction(
        "x", 0, "ekf", 50.0, np.arange(0, 10, 0.5), np.array([40.0, 60.0] * 10),
        np.zeros(20), np.zeros(20),
    )  # fmt: skip
    assert p.unavailable() == [(0.5, 9.5)]
    assert len(p.unavailable(merge_s=0.0)) == 10


def test_series_time_axis_is_scenario_seconds():
    p = preflight.predict(SPEC, seed=0)
    assert p.t_s[0] >= 0 and p.t_s[-1] <= SPEC["duration_s"]
