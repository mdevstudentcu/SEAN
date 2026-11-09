"""Time protection level and the report card (issues I5, I6): REQ-02, REQ-03, REQ-04."""

import math

import numpy as np
import pytest

from pnt.core.measurement import Estimate, Truth
from pnt.integrity import taxonomy
from pnt.integrity.protection import K_T, tpl
from pnt.metrics import TIME_ALERT_LIMIT_S, first_alert_s, resilience_level, score, summarize
from pnt.sim import attacks

DT_NS = 100_000_000  # 10 Hz epochs
N = 200  # 20 s


def run(spec, *, flagged=(), err=lambda i: 0.0, hpl=10.0, clock_err=0.0, clock_sigma_s=None):
    """Score hand-built epochs: `flagged` epochs carry gnss_unavailable, `err(i)` is the
    horizontal error at epoch i and `clock_err` the clock error in seconds."""
    estimates, truth = [], []
    for i in range(N):
        t = i * DT_NS
        estimates.append(
            Estimate(
                t_ns=t,
                pos_enu=(err(i), 0.0, 0.0),
                vel_enu=(0.0, 0.0, 0.0),
                pos_cov=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
                clock_bias_s=clock_err,
                clock_sigma_s=clock_sigma_s,
                hpl_m=hpl,
                flags=["gnss_unavailable"] if i in flagged else [],
            )
        )
        truth.append(Truth(t_ns=t, pos_enu=(0.0, 0.0, 0.0), vel_enu=(0.0, 0.0, 0.0)))
    return score(estimates, truth, spec, 0)


OUTAGE = {"faults": [{"type": "outage", "start_s": 5.0, "end_s": 10.0}]}


def test_time_pl_is_k_times_the_clock_sigma_req03():
    assert tpl(1e-7) == pytest.approx(K_T * 1e-7)
    assert tpl(None) is None


def test_time_pl_bound_rate_and_misleading_epochs_req03():
    # Time PL = 5.33 * 0.1 us = 0.533 us, under the 1.5 us time alert limit
    bounded = run({"faults": []}, clock_err=0.5e-6, clock_sigma_s=0.1e-6)
    assert bounded.time_pl_bound_frac == 1.0
    assert bounded.time_misleading_epochs == 0
    over = run({"faults": []}, clock_err=0.6e-6, clock_sigma_s=0.1e-6)
    assert over.time_pl_bound_frac == 0.0
    assert over.time_misleading_epochs == N and over.time_hazardous_epochs == 0
    hazardous = run({"faults": []}, clock_err=2 * TIME_ALERT_LIMIT_S, clock_sigma_s=0.1e-6)
    assert hazardous.time_hazardous_epochs == N


def test_time_metrics_need_an_estimated_clock():
    m = run({"faults": []}, clock_err=1e-6)
    assert math.isnan(m.time_pl_bound_frac) and m.time_hazardous_epochs == 0


def test_position_hazardous_epochs_need_a_claimed_bound_req02():
    # 60 m error over the 50 m alert limit: hazardous while HPL claims 10 m, not when HPL > AL
    assert run({"faults": []}, err=lambda i: 60.0, hpl=10.0).hazardous_epochs == N
    assert run({"faults": []}, err=lambda i: 60.0, hpl=80.0).hazardous_epochs == 0


def test_time_to_alert_counts_from_the_fault_start_req04():
    # Fault at 5.0 s (epoch 50); the alert switches on at epoch 57
    m = run(OUTAGE, flagged=set(range(57, 100)))
    assert m.time_to_alert_s == pytest.approx(0.7)
    assert m.alerted == 1.0


def test_an_alert_running_before_the_fault_is_not_a_response():
    m = run(OUTAGE, flagged=set(range(40, 60)))
    assert math.isnan(m.time_to_alert_s) and m.alerted == 0.0


def test_time_to_alert_does_not_apply_without_a_fault_or_to_a_false_alarm_check():
    assert math.isnan(run({"faults": []}).alerted)
    low_sats = {"faults": [{"type": "gps_low_sats", "start_s": 5.0}]}
    assert math.isnan(run(low_sats, flagged=set(range(60, 70))).alerted)


def test_first_alert_finds_the_rising_edge():
    t = np.arange(10) * DT_NS
    alert = np.array([0, 0, 0, 1, 1, 0, 1, 1, 0, 0], bool)
    assert first_alert_s(t, alert, 4 * DT_NS, 10 * DT_NS) == pytest.approx(0.2)


def test_summarize_gives_median_and_worst_time_to_alert():
    runs = [run(OUTAGE, flagged=set(range(s, 100))) for s in (51, 53, 59)]
    runs.append(run(OUTAGE))  # missed
    s = summarize(runs)
    assert s["tta_median_s"] == pytest.approx(0.3)
    assert s["tta_worst_s"] == pytest.approx(0.9)
    assert s["alerted"] == pytest.approx(0.75)


def test_resilience_levels_are_cumulative():
    assert resilience_level(True, True, True, True) == 4
    assert resilience_level(True, True, False, True) == 2
    assert resilience_level(False, True, True, True) == 0


JUMP = {"faults": [{"type": "spoof_jump", "start_s": 5.0, "end_s": 6.0}]}  # corrupts position


def test_resilience_level_from_a_run():
    # Clean before and after; 30 m error during the fault (bounded, but degraded)
    degraded = run(JUMP, err=lambda i: 30.0 if 50 <= i < 60 else 1.0 + 0.01 * i)
    # Recovery settles 30 s after the end, past this 20 s run: not tested, so not held against it
    assert degraded.recovery_tested == 0.0
    assert degraded.resilience_level == degraded.pos_resilience_level == 3.0
    assert math.isnan(degraded.time_resilience_level)  # a position spoof does not touch time
    hazardous = run(JUMP, err=lambda i: 60.0 if 50 <= i < 60 else 1.0)
    assert hazardous.resilience_level == 1.0
    assert math.isnan(run({"faults": []}).resilience_level)


def test_time_is_judged_only_where_the_fault_corrupts_it():
    # An outage takes position and time; without a clock estimate there is no time level
    m = run(OUTAGE, err=lambda i: 1.0)
    assert m.pos_resilience_level == 4.0
    assert m.time_resilience_level == 0.0 and m.resilience_level == 0.0
    spoof = {"faults": [{"type": "time_spoof", "start_s": 5.0}]}
    assert math.isnan(run(spoof).pos_resilience_level)
    held = run(spoof, err=lambda i: 1.0, clock_err=0.5e-6, clock_sigma_s=0.1e-6)
    assert held.time_resilience_level == 4.0


def test_every_registered_attack_has_a_fault_class():
    assert set(attacks._ATTACKS) <= set(taxonomy.TAXONOMY)
    assert set(taxonomy.TAXONOMY) <= set(attacks._ATTACKS)  # no stale classes either


def test_an_outage_of_towers_is_a_soop_fault_not_jamming():
    assert taxonomy.classify({"type": "outage", "source": "lte"}).cls == "SoOP fault"
    assert taxonomy.classify({"type": "outage"}).cls == "jamming / denial"
