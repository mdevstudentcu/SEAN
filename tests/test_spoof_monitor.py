"""GNSS position spoof monitor (#173, integrity/spoof_monitor.py), REQ-04.

The sim cases are short versions of the `challenge-drone` leg with many towers heard (every
sector within 3 km), built from the committed environment as analysis/spoof_detection.py builds
its many-tower case. Seeds are from the tuning set (100-109), never the reported 0-49."""

import copy

import numpy as np
import pytest

from pnt.integrity.spoof_monitor import SpoofMonitor, f_threshold, towers_test
from pnt.nav import ESTIMATORS, ekf, estimate
from pnt.sim.scenario import generate, load

SEED = 100


def _many_tower_case(faults: list[dict], duration_s: float = 420.0) -> dict:
    spec = copy.deepcopy(load("challenge-drone-nominal"))
    spec["sources"]["lte"]["hearing"] = {"model": "range", "hearing_km": 3}
    spec.update(duration_s=duration_s, faults=faults, name="test-many-towers")
    return spec


def _run(spec: dict, estimator: str):
    run = generate(spec, seed=SEED)
    return run, list(estimate(estimator, run.measurements, origin_llh=spec["origin_llh"]))


def _first(estimates, flag: str, t0_ns: int, after_s: float = 0.0) -> float | None:
    for e in estimates:
        s = (e.t_ns - t0_ns) / 1e9
        if s >= after_s and flag in e.flags:
            return s
    return None


def test_monitor_is_off_unless_asked_for():
    assert ESTIMATORS["ekf"] is ekf.run
    assert ESTIMATORS["ekf-calibrated"] is ekf.run_calibrated
    for name in ("ekf-spoof", "ekf-calibrated-spoof", "ekf-imu-spoof"):
        assert name in ESTIMATORS
    spec = _many_tower_case([{"type": "spoof_ramp", "source": "gnss", "start_s": 100,
                              "rate_mps": 2.0, "direction_deg": 45}], duration_s=200)  # fmt: skip
    run, plain = _run(spec, "ekf")
    assert not any("spoof_suspected" in e.flags for e in plain)


def test_ramp_is_caught_on_many_towers_req04():
    """2 m/s ramp from 100 s. Regression guard, not a target: the worst detection time on the
    reported seeds is in analysis/results/spoof-detection/summary.md, and T4's 30 s is not met."""
    start = 100.0
    spec = _many_tower_case(
        [
            {
                "type": "spoof_ramp",
                "source": "gnss",
                "start_s": start,
                "rate_mps": 2.0,
                "direction_deg": 45,
            }
        ]  # fmt: skip
    )
    run, est = _run(spec, "ekf-spoof")
    t0 = run.truth[0].t_ns
    assert _first(est, "spoof_suspected", t0) is not None
    alert = _first(est, "spoof_suspected", t0) - start
    assert 0 < alert <= 300.0
    # GNSS position is excluded once the alarm is up; its trust drops once the filter's GNSS
    # timeout (2 s) has passed without a GNSS update
    after = [e for e in est if (e.t_ns - t0) / 1e9 > start + alert + 2.5][:50]
    assert after and all("gnss_excluded" in e.flags for e in after)
    assert all(e.trust.get("gnss", 0.0) == 0.0 for e in after)


def test_jump_is_caught_on_many_towers_req04():
    start = 100.0
    spec = _many_tower_case(
        [
            {
                "type": "spoof_jump",
                "source": "gnss",
                "start_s": start,
                "offset_enu_m": [300.0, 0.0, 0.0],
            }
        ],
        duration_s=200,  # fmt: skip
    )
    run, est = _run(spec, "ekf-spoof")
    alert = _first(est, "spoof_suspected", run.truth[0].t_ns)
    assert alert is not None and start < alert <= start + 15.0  # regression guard


@pytest.mark.parametrize(
    "faults",
    [[], [{"type": "outage", "source": "gnss", "start_s": 120, "end_s": 240}]],
    ids=["nominal", "gps-outage"],
)
def test_nominal_and_plain_outage_raise_no_spoof_alarm(faults):
    spec = _many_tower_case(faults)
    run, est = _run(spec, "ekf-spoof")
    assert not any("spoof_suspected" in e.flags for e in est)


def test_tower_test_recovers_a_displacement_and_ignores_clocks():
    """Synthetic residuals: per-site constant, a common clock per epoch that wanders by
    hundreds of metres, noise, and a GNSS displacement d(t) moving every residual by -u . d."""
    rng = np.random.default_rng(1)
    n_sites, lag, win = 12, 60, 10
    ang = rng.uniform(0, 2 * np.pi, n_sites)
    u = np.column_stack([np.cos(ang), np.sin(ang)])
    a = rng.normal(0, 1000, n_sites)
    rows, v = [], np.array([2.0, -1.0])  # GNSS position drifts at v, m/s
    for k in range(lag + win + 1):
        t = k * 1_000_000_000
        clock = 300.0 * np.sin(k / 7.0) + 50.0 * k
        for i in range(n_sites):
            r = a[i] + clock - u[i] @ (v * k) + rng.normal(0, 1.0)
            rows.append((t, f"s{i}", r, u[i, 0], u[i, 1]))
    out = towers_test(rows, (lag + win) * 1_000_000_000, lag * 1_000_000_000, win * 1_000_000_000)
    assert out is not None
    g, _, s2, n = out
    assert n == n_sites
    np.testing.assert_allclose(g, -v * lag, atol=1.0)  # residuals move by -u . d
    assert s2 < 1.0


def test_f_threshold_is_the_f_quantile():
    stats = pytest.importorskip("scipy.stats")
    for dof in (2, 7, 40):
        assert f_threshold(1e-4, dof) == pytest.approx(stats.f.isf(1e-4, 2, dof), rel=1e-9)


def test_monitor_reports_no_opinion_with_few_towers():
    """The `challenge` drone leg hears one to three cells: no tower test runs."""
    spec = copy.deepcopy(load("challenge-drone-nominal"))
    spec["duration_s"] = 150
    run = generate(spec, seed=SEED)
    monitors = []

    def mon(f):
        monitors.append(SpoofMonitor(f))
        return monitors[-1]

    list(ekf.run(run.measurements, origin_llh=spec["origin_llh"], monitor=mon))
    assert monitors[0].report.towers and all(v is None for v in monitors[0].report.towers.values())
