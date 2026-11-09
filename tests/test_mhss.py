import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.integrity.mhss import GNSS_CM, MHSS
from pnt.nav import ESTIMATORS, ekf
from pnt.sim.scenario import T0_NS, generate, load

AL = 50.0


def M(source, kind, emitter=""):  # noqa: N802
    return Measurement(
        t_ns=0, source=source, kind=kind, value=(0.0,), sigma=(1.0,), emitter=emitter
    )


def _run(name, seed=0, **monitor_kw):
    spec = load(name)
    run = generate(spec, seed=seed)
    mons = []

    def monitor(f):
        mons.append(MHSS(f, **monitor_kw))
        return mons[0]

    est = list(ekf.run(run.measurements, origin_llh=spec.get("origin_llh"), monitor=monitor))
    truth = {t.t_ns: t for t in run.truth}
    err = np.array([np.hypot(*np.subtract(e.pos_enu, truth[e.t_ns].pos_enu)[:2]) for e in est])
    hpl = np.array([e.hpl_m for e in est])
    return run, est, err, hpl, mons[0]


def test_registered_and_opt_in():
    assert "ekf-mhss" in ESTIMATORS
    assert ESTIMATORS["ekf"] is ekf.run


def test_groups_follow_adr0024():
    mon = MHSS(None, sites={"lte:a": "S1"}, builders={"S1": "TELUS"})
    assert set(mon.groups(M("gnss", "position_enu"))) == {GNSS_CM}
    assert set(mon.groups(M("gnss", "time"))) == {GNSS_CM}
    assert set(mon.groups(M("adsb", "adsb_report"))) == {GNSS_CM}  # GNSS-derived
    assert set(mon.groups(M("wifi", "rssi"))) == {GNSS_CM}  # unclassified: GNSS-dependent
    assert set(mon.groups(M("baro", "altitude"))) == {"layer:baro"}
    # a GNSS-timed tower keeps its geometry: it is not in the GNSS common-mode hypothesis
    assert set(mon.groups(M("lte", "pseudorange", "lte:a"))) == {
        "layer:lte",
        "site:S1",
        "builder:TELUS",
    }
    # site unknown: the tower is its own site, and there is no builder hypothesis
    assert set(mon.groups(M("lte", "pseudorange", "lte:b"))) == {"layer:lte", "site:lte:b"}


def test_without_a_fault_the_monitor_leaves_the_solution_alone():
    spec = load("nominal")
    run = generate(spec, seed=0)
    plain = list(ekf.run(run.measurements, origin_llh=spec["origin_llh"]))
    mhss = list(ESTIMATORS["ekf-mhss"](run.measurements, origin_llh=spec["origin_llh"]))
    assert len(plain) == len(mhss)
    for a, b in zip(plain, mhss, strict=True):
        assert b.pos_enu == a.pos_enu and b.clock_bias_s == a.clock_bias_s
        assert b.hpl_m >= a.hpl_m  # MHSS also bounds the fault hypotheses


def test_nominal_has_no_exclusion_and_bounds_the_error():
    _, est, err, hpl, mon = _run("nominal")
    assert not any(f.startswith("mhss_excluded") for e in est for f in e.flags)
    assert np.all(hpl >= err)
    assert set(mon.report.tests) >= {GNSS_CM, "layer:lte", "layer:baro"}


@pytest.mark.parametrize("name", ["spoof-ramp", "spoof-jump"])
def test_gnss_spoof_is_flagged_and_never_hazardously_misleading(name):
    # REQ-02 / T5: no epoch with error over the alert limit while the HPL is within it
    run, est, err, hpl, _ = _run(name)
    start = T0_NS + 150 * 10**9
    flagged = [
        e.t_ns for e in est if {f"mhss_excluded:{GNSS_CM}", f"mhss_alarm:{GNSS_CM}"} & set(e.flags)
    ]
    assert flagged and flagged[0] >= start  # nothing before the attack
    assert not ((err > AL) & (hpl <= AL)).any()
    assert np.all(hpl >= err)


def test_monitor_does_not_degrade_the_solution_in_a_gps_outage():
    # Sub-filters gate on their own, so their covariance can dip below the main filter's; that
    # must not turn into exclusions that move the output. Regression guard: 1 m.
    spec = load("gps-outage")
    run = generate(spec, seed=0)
    truth = {t.t_ns: t for t in run.truth}

    def p95(est):
        e = [np.hypot(*np.subtract(x.pos_enu, truth[x.t_ns].pos_enu)[:2]) for x in est]
        return np.percentile(e, 95)

    plain = list(ekf.run(run.measurements, origin_llh=spec["origin_llh"]))
    mhss = list(ESTIMATORS["ekf-mhss"](run.measurements, origin_llh=spec["origin_llh"]))
    assert p95(mhss) <= p95(plain) + 1.0


def test_a_spoof_alarm_attribute_on_the_filter_takes_gnss_out():
    # #102 gives the EKF a boolean `spoof_alarm`; MHSS must treat it as a GNSS alarm
    spec = load("nominal")
    run = generate(spec, seed=0)

    def monitor(f):
        f.spoof_alarm = True
        return MHSS(f)

    est = list(ekf.run(run.measurements, origin_llh=spec["origin_llh"], monitor=monitor))
    flagged = {f"mhss_excluded:{GNSS_CM}", f"mhss_alarm:{GNSS_CM}"}
    assert all(flagged & set(e.flags) for e in est[20:])
