"""`ekf-calibrated-measured` (#118, ADR-0043): the calibrated EKF with no value from a sim set,
and the T1 statistic of `analysis/calibrated_measured.py` (ADR-0034's amendment)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import ESTIMATORS, ekf
from pnt.sim.scenario import load

_PATH = Path(__file__).parents[1] / "analysis" / "calibrated_measured.py"
_SPEC = importlib.util.spec_from_file_location("calibrated_measured", _PATH)
cm = importlib.util.module_from_spec(_SPEC)
sys.modules["calibrated_measured"] = cm
_SPEC.loader.exec_module(cm)

M = ekf.CALIBRATED_MEASURED


def _pr(t_ns, emitter, rho, sigma):
    meta = {"emitter_enu": [3000.0, 4000.0, 30.0]}
    return Measurement(
        t_ns=t_ns, source="lte", kind="pseudorange", value=(float(rho),), sigma=(sigma,),
        emitter=emitter, meta=meta,
    )  # fmt: skip


def _started(**config) -> ekf.EKF:
    f = ekf.EKF(**{**M, **config})
    fix = (0.0, 0.0, 30.0)
    f.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=fix, sigma=(2.0,) * 3))
    return f


def test_registered_as_a_new_opt_in_estimator():
    assert ESTIMATORS["ekf-calibrated-measured"] is ekf.run_calibrated_measured
    assert ESTIMATORS["ekf-calibrated"] is ekf.run_calibrated  # unchanged
    assert ESTIMATORS["ekf"] is ekf.run


def test_no_value_comes_from_the_realistic_set():
    # CALIBRATED's values that the realistic set generates with are left to EKF's defaults
    for key in ("h0", "h_2", "tower_h0", "multipath_ratio"):
        assert key not in M
    spec = load("realistic-long-outage")
    lte = spec["sources"]["lte"]
    assert M["multipath_sigma_m"] != lte["multipath"]["sigma_m"]
    assert M["multipath_tau_s"] != lte["multipath"]["tau_s"]
    assert M["tower_position_sigma_m"] != lte["told_position_sigma_m"]
    # ADR-0036 (1): sigma_corr 10 m, tau_corr 3 s, measured at rest (TBC)
    assert (M["multipath_sigma_m"], M["multipath_tau_s"]) == (10.0, 3.0)


def test_absolute_multipath_sigma_ignores_the_reported_sigma():
    f = _started()
    f.process(_pr(0, "lte:0", 5000.0, sigma=50.0))
    f.process(_pr(0, "lte:1", 5000.0, sigma=2.0))
    for e in ("lte:0", "lte:1"):
        mp = f.multipath_idx[e]
        assert np.sqrt(f.P[mp, mp]) == pytest.approx(10.0)
    assert not f.position_idx  # told-position states off (TBD)


def test_absolute_multipath_is_a_gauss_markov_with_its_own_tau():
    f = _started()
    f.process(_pr(0, "lte:0", 5000.0, sigma=50.0))
    mp = f.multipath_idx["lte:0"]
    f.x[mp], f.P[mp, mp] = 8.0, 1.0
    f.predict(int(3.0 * 1e9))
    phi2 = np.exp(-2.0)
    assert f.x[mp] == pytest.approx(8.0 * np.exp(-1.0))
    assert f.P[mp, mp] == pytest.approx(phi2 + 10.0**2 * (1 - phi2), rel=1e-6)


def test_ratio_still_sizes_multipath_when_no_absolute_sigma_is_given():
    f = ekf.EKF(**ekf.CALIBRATED)
    f.process(Measurement(t_ns=0, source="gnss", kind="position_enu", value=(0.0, 0.0, 30.0),
                          sigma=(2.0,) * 3))  # fmt: skip
    f.process(_pr(0, "lte:0", 5000.0, sigma=20.0))
    mp = f.multipath_idx["lte:0"]
    assert np.sqrt(f.P[mp, mp]) == pytest.approx(20.0)


def test_tuning_and_report_seeds_are_declared_and_disjoint():
    assert not set(cm.TUNING_SEEDS) & set(cm.REPORT_SEEDS)
    assert list(cm.REPORT_SEEDS) == list(range(50))


@pytest.mark.parametrize(
    ("scenario", "seconds"),
    [("realistic-long-outage", 300), ("worst-long-outage", 300), ("ottawa-sionna", 120)],
)
def test_t1_window_is_300_s_or_the_outage(scenario, seconds):
    assert cm.t1_window(load(scenario))[1] == seconds


def test_t1_is_the_worst_second_of_the_per_second_95th_percentile():
    # 20 runs x 3 s: second 1 has one large error among 20 runs, second 2 has three
    err = np.ones((20, 3))
    err[0, 1] = 100.0
    err[:3, 2] = 50.0
    runs = [
        {"nees": 2.0, "hpl_bound": 1.0, "misleading": 0, "hazardous": 0, "time_misleading": 0,
         "fault_p95_m": 1.0, "err_per_s": e,
         "win_p95_m": 1.0, "win_nees": 2.0, "win_hpl_bound": 1.0}
        for e in err.tolist()
    ]  # fmt: skip
    a = cm.aggregate(runs, list(range(20)))
    curve = np.percentile(err, 95, axis=0)
    assert a["t1_worst_p95_m"] == pytest.approx(curve.max())
    assert a["t1_worst_second"] == 2  # 3 of 20 runs over is more than 5 %: second 2 decides
    assert a["t1_worst_p95_m"] == pytest.approx(50.0)
