"""Outage slices in the report card (issue #128): T1 and T3 scored from GPS loss."""

import math

import numpy as np
import pytest

from pnt.core.measurement import Estimate, Truth
from pnt.metrics import score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

DT_NS = 100_000_000  # 10 Hz epochs
LOSS_S = 10.0
SLICES = ("outage_h_p95_60s_m", "outage_h_p95_120s_m", "outage_h_p95_300s_m")
NEW = (*SLICES, "outage_hpl_bound_300s", "outage_time_err_600s_us", "outage_time_sigma_bound_600s")


def scored(faults, duration_s, *, hpl=30.05, clock_sigma_s=0.5005e-6):
    """Hand-built run: no error before GPS loss, then horizontal error growing 1 m/s and clock
    error growing 1 ns/s from the loss. `clock_sigma_s=None`: the clock is not estimated."""
    estimates, truth = [], []
    for i in range(round(duration_s * 1e9 / DT_NS)):
        t = i * DT_NS
        since = max(0.0, (t - LOSS_S * 1e9) / 1e9)
        estimates.append(
            Estimate(
                t_ns=t,
                pos_enu=(since, 0.0, 0.0),
                vel_enu=(0.0, 0.0, 0.0),
                pos_cov=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
                clock_bias_s=since * 1e-9,
                clock_sigma_s=clock_sigma_s,
                hpl_m=hpl,
            )
        )
        truth.append(Truth(t_ns=t, pos_enu=(0.0, 0.0, 0.0), vel_enu=(0.0, 0.0, 0.0)))
    return score(estimates, truth, {"faults": faults}, 0)


def gnss_outage(end_s=None, type_="outage"):
    f = {"type": type_, "source": "gnss", "start_s": LOSS_S}
    return [f] if end_s is None else [{**f, "end_s": end_s}]


def p95_of_ramp(length_s, rate=1.0, offset=0.0):
    """numpy's p95 of offset + rate * (0, 0.1, ..., length - 0.1): the epochs of one slice."""
    return offset + rate * 0.1 * 0.95 * (round(length_s * 10) - 1)


def test_each_slice_is_the_p95_of_its_first_seconds_after_loss():
    m = scored(gnss_outage(), LOSS_S + 700)
    assert m.outage_h_p95_60s_m == pytest.approx(p95_of_ramp(60))
    assert m.outage_h_p95_120s_m == pytest.approx(p95_of_ramp(120))
    assert m.outage_h_p95_300s_m == pytest.approx(p95_of_ramp(300))
    # HPL 30.05 m bounds the error for its first 30 s: epochs 0..300 of the slice's 3000
    assert m.outage_hpl_bound_300s == pytest.approx(301 / 3000)


def test_time_error_at_600s_is_the_p95_of_the_10s_ending_there():
    m = scored(gnss_outage(), LOSS_S + 700)
    # 590.0 .. 599.9 ns
    assert m.outage_time_err_600s_us == pytest.approx(p95_of_ramp(10, offset=590.0) * 1e-3)
    # sigma 500.5 ns bounds the error for its first 500.5 s: epochs 0..5005 of 6000
    assert m.outage_time_sigma_bound_600s == pytest.approx(5006 / 6000)


def test_a_120s_outage_never_reports_a_300s_number():
    m = scored(gnss_outage(end_s=LOSS_S + 120), LOSS_S + 700)
    assert m.outage_h_p95_60s_m == pytest.approx(p95_of_ramp(60))
    assert m.outage_h_p95_120s_m == pytest.approx(p95_of_ramp(120))
    for k in ("outage_h_p95_300s_m", "outage_hpl_bound_300s", "outage_time_err_600s_us"):
        assert math.isnan(getattr(m, k)), k
    assert math.isnan(m.outage_time_sigma_bound_600s)


def test_a_run_that_ends_too_soon_has_no_slice_but_one_that_ends_on_it_has():
    short = scored(gnss_outage(), LOSS_S + 299.9)
    assert not math.isnan(short.outage_h_p95_120s_m)
    assert math.isnan(short.outage_h_p95_300s_m) and math.isnan(short.outage_hpl_bound_300s)
    # Epochs 0 .. loss + 299.9 s are a run that lasts to loss + 300 s
    exact = scored(gnss_outage(), LOSS_S + 300)
    assert exact.outage_h_p95_300s_m == pytest.approx(p95_of_ramp(300))
    assert math.isnan(exact.outage_time_err_600s_us)


def test_time_slices_need_an_estimated_clock():
    m = scored(gnss_outage(), LOSS_S + 700, clock_sigma_s=None)
    assert math.isnan(m.outage_time_err_600s_us) and math.isnan(m.outage_time_sigma_bound_600s)
    assert not math.isnan(m.outage_h_p95_300s_m)


def test_gps_no_fix_is_gps_loss_but_other_faults_are_not():
    no_fix = scored(gnss_outage(type_="gps_no_fix"), LOSS_S + 700)
    assert no_fix.outage_h_p95_300s_m == pytest.approx(p95_of_ramp(300))
    for faults in (
        [],
        [{"type": "outage", "source": "lte", "start_s": LOSS_S}],
        [{"type": "spoof_ramp", "source": "gnss", "start_s": LOSS_S, "rate_mps": 1.0}],
    ):
        m = scored(faults, LOSS_S + 700)
        assert all(math.isnan(getattr(m, k)) for k in NEW), faults


def test_the_first_gps_loss_starts_the_clock():
    later = {"type": "outage", "source": "gnss", "start_s": 200.0}
    m = scored([later, *gnss_outage()], LOSS_S + 700)
    assert m.outage_h_p95_60s_m == pytest.approx(p95_of_ramp(60))


# Every field RunMetrics had before #128, scored on origin/main 0cfa2fd, seed 0 (issue #128:
# the outage slices must not change any of them).
BEFORE_0CFA2FD = {
    ("gps-outage", "baseline"): {
        "n": 3599,
        "h_rmse_m": 6.726957006363384,
        "h_p95_m": 15.95271500762771,
        "h_max_m": 30.880750149087017,
        "fault_h_p95_m": 21.523691795134685,
        "fault_h_max_m": 30.880750149087017,
        "hpl_bound_frac": 1.0,
        "misleading_epochs": 0,
        "detect_delay_s": math.nan,
        "spoof_detected": math.nan,
        "false_alarms_per_h": 0.0,
        "h_nees_mean": 1.609056662718437,
        "time_err_p95_us": math.nan,
        "fault_time_err_p95_us": math.nan,
        "time_1sigma_bound_frac": math.nan,
        "hazardous_epochs": 0,
        "time_pl_bound_frac": math.nan,
        "time_misleading_epochs": 0,
        "time_hazardous_epochs": 0,
        "time_to_alert_s": 1.9,
        "alerted": 1.0,
        "resilience_level": 0.0,
        "pos_resilience_level": 3.0,
        "time_resilience_level": 0.0,
        "recovery_tested": 1.0,
    },
    ("realistic-long-outage", "ekf-calibrated"): {
        "n": 3599,
        "h_rmse_m": 125.4587652014683,
        "h_p95_m": 212.69473699091122,
        "h_max_m": 242.2590096750868,
        "fault_h_p95_m": 223.49213226829224,
        "fault_h_max_m": 242.2590096750868,
        "hpl_bound_frac": 1.0,
        "misleading_epochs": 0,
        "detect_delay_s": math.nan,
        "spoof_detected": math.nan,
        "false_alarms_per_h": 0.0,
        "h_nees_mean": 1.5759101089059242,
        "time_err_p95_us": 0.01733505797312231,
        "fault_time_err_p95_us": 0.017582924697273863,
        "time_1sigma_bound_frac": 0.9338705195887747,
        "hazardous_epochs": 0,
        "time_pl_bound_frac": 1.0,
        "time_misleading_epochs": 0,
        "time_hazardous_epochs": 0,
        "time_to_alert_s": 1.9,
        "alerted": 1.0,
        "resilience_level": 2.0,
        "pos_resilience_level": 2.0,
        "time_resilience_level": 4.0,
        "recovery_tested": 0.0,
    },
}


@pytest.mark.parametrize("scenario, estimator", list(BEFORE_0CFA2FD))
def test_existing_fields_keep_their_values(scenario, estimator):
    spec = load(scenario)
    run = generate(spec, seed=0)
    est = estimate(estimator, run.measurements, origin_llh=spec.get("origin_llh"))
    got = score(list(est), run.truth, spec, T0_NS).as_dict()
    before = BEFORE_0CFA2FD[(scenario, estimator)]
    assert list(got)[: len(before)] == list(before)  # same fields, same order, new ones after
    for k, v in before.items():
        assert got[k] == pytest.approx(v, rel=1e-9, nan_ok=True), k
    assert set(got) - set(before) == set(NEW)
    # The 300 s slice of a 300 s outage is the whole fault window
    if scenario == "realistic-long-outage":
        assert got["outage_h_p95_300s_m"] == pytest.approx(got["fault_h_p95_m"])
        assert np.isnan(got["outage_time_err_600s_us"])  # a 360 s run has no 600 s point
