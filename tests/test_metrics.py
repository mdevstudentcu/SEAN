import math

import pytest

from pnt.cli import main
from pnt.core.measurement import Estimate, Truth
from pnt.io.mcap_log import read_session
from pnt.metrics import score, summarize
from pnt.nav import baseline
from pnt.sim.scenario import T0_NS, generate, load

DT_NS = 100_000_000  # 10 Hz epochs
N = 200  # 20 s
SPOOF = {"faults": [{"type": "spoof_ramp", "start_s": 5.0}]}
CLEAN = {"faults": []}


def scored(spec, alarmed=(), err=0.0, clock_bias_s=0.0, clock_sigma_s=None):
    """Score hand-built epochs: `alarmed` lists the epoch indices that raise gnss_excluded."""
    estimates, truth = [], []
    for i in range(N):
        t = i * DT_NS
        estimates.append(
            Estimate(
                t_ns=t,
                pos_enu=(err, 0.0, 0.0),
                vel_enu=(0.0, 0.0, 0.0),
                pos_cov=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
                clock_bias_s=clock_bias_s,
                clock_sigma_s=clock_sigma_s,
                hpl_m=10.0,
                flags=["gnss_excluded"] if i in alarmed else [],
            )
        )
        truth.append(Truth(t_ns=t, pos_enu=(0.0, 0.0, 0.0), vel_enu=(0.0, 0.0, 0.0)))
    return score(estimates, truth, spec, 0)


def test_single_rejected_epoch_is_not_a_detection():
    m = scored(SPOOF, alarmed={60})
    assert math.isnan(m.detect_delay_s)
    assert m.spoof_detected == 0.0


def test_sustained_alarm_detects_when_the_hold_time_is_reached():
    m = scored(SPOOF, alarmed=set(range(60, 100)))  # starts at 6 s, confirmed 1 s later
    assert m.detect_delay_s == pytest.approx(2.0)
    assert m.spoof_detected == 1.0
    assert m.false_alarms_per_h == 0.0


def test_sustained_alarm_before_the_spoof_is_a_false_alarm():
    m = scored(SPOOF, alarmed=set(range(10, 30)))
    assert math.isnan(m.detect_delay_s)
    assert m.false_alarms_per_h == pytest.approx(1 / (4.9 / 3600))


def test_no_spoof_means_detection_does_not_apply():
    assert math.isnan(scored(CLEAN).spoof_detected)


def test_time_metrics_score_only_an_estimated_clock():
    m = scored(CLEAN, clock_bias_s=1e-6, clock_sigma_s=2e-6)
    assert m.time_err_p95_us == pytest.approx(1.0)
    assert m.time_1sigma_bound_frac == 1.0
    assert math.isnan(scored(CLEAN, clock_bias_s=1e-6).time_err_p95_us)


def test_nees_matches_a_known_error_and_covariance():
    assert scored(CLEAN, err=3.0).h_nees_mean == pytest.approx(9.0)


def test_summarize_handles_a_scenario_with_no_faults():
    with_nans = summarize([scored(CLEAN), scored(CLEAN)])
    assert math.isnan(with_nans["worst_fault_h_max_m"])


@pytest.mark.parametrize("scenario", ["nominal", "gps-outage"])
def test_baseline_covariance_stays_roughly_consistent(scenario):
    spec = load(scenario)
    runs = []
    for seed in range(3):
        run = generate(spec, seed=seed)
        runs.append(score(list(baseline.run(run.measurements)), run.truth, spec, T0_NS))
    # Loose regression guard, not a requirement: a consistent filter averages about 2.
    assert 0.5 < summarize(runs)["h_nees_mean"] < 5.0


def test_sim_logs_under_the_chosen_estimator_and_replay_keeps_fault_windows(tmp_path, capsys):
    path = tmp_path / "s.mcap"
    main(["sim", "spoof-ramp", "--out", str(path), "--estimator", "baseline"])
    assert sum(1 for _ in read_session(path, topics=["/nav/baseline"])) > 0
    capsys.readouterr()
    main(["replay", str(path)])
    fault_line = next(ln for ln in capsys.readouterr().out.splitlines() if "fault_h_p95_m" in ln)
    assert "nan" not in fault_line


def test_unknown_estimator_is_rejected():
    with pytest.raises(SystemExit):
        main(["eval", "nominal", "--estimator", "nope"])
