"""Tower clock models in the EKF (ADR-0022, Proposed): site and builder grouping, calibration
while GNSS is trusted, and coasting on the learned clocks when it is lost."""

from collections import deque

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import ekf

C = ekf.C
TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
DRIFTS = np.array([0.4, -0.3, 0.25, -0.35])  # m/s: each tower clock's drift


def M(t_ns, source, kind, value, sigma, emitter="", meta=None):  # noqa: N802
    return Measurement(
        t_ns=t_ns, source=source, kind=kind, value=value, sigma=sigma, emitter=emitter,
        meta=meta or {},
    )  # fmt: skip


def _pr(t_ns, emitter, tower, rho, sigma=5.0):
    meta = {"emitter_enu": [float(x) for x in tower]}
    return M(t_ns, "lte", "pseudorange", (float(rho),), (sigma,), emitter, meta)


def _drifting_towers(outage=(120.0, 420.0), duration=420.0, seed=0):
    """Receiver circling the origin; four towers whose clocks have an offset and a constant
    drift, as an unsynchronised or free-running tower does. GNSS position at 5 Hz outside the
    outage, barometer at 10 Hz and every tower at 1 Hz throughout. Returns (measurements, truth
    (t_s, pos))."""
    rng = np.random.default_rng(seed)
    baro_rng = np.random.default_rng(seed + 1000)  # separate, so the other draws don't change
    offsets = rng.uniform(-500, 500, len(TOWERS))
    meas, truth = [], []
    for k in range(int(duration * 10)):
        t = k / 10
        t_ns = int(round(t * 1e9))
        a = 0.05 * t
        pos = np.array([100 * np.cos(a), 100 * np.sin(a), 30.0])
        truth.append((t, pos))
        meas.append(M(t_ns, "baro", "altitude", (30.0 + baro_rng.normal(0, 0.5),), (0.5,)))
        if k % 2 == 0 and not outage[0] <= t < outage[1]:
            fix = tuple(pos + rng.normal(0, 2, 3))
            meas.append(M(t_ns, "gnss", "position_enu", fix, (2.0, 2.0, 2.0)))
        if k % 10 == 0:
            for i, e in enumerate(TOWERS):
                rho = np.linalg.norm(pos - e) + offsets[i] + DRIFTS[i] * t + rng.normal(0, 5)
                meas.append(_pr(t_ns, f"lte:{i}", e, rho))
    return meas, truth


def _feed(f: ekf.EKF, meas, until_s: float = np.inf) -> None:
    for m in meas:
        if m.t_ns / 1e9 >= until_s:
            break
        f.process(m)


def _started(**config) -> ekf.EKF:
    f = ekf.EKF(**config)
    f.process(M(0, "gnss", "position_enu", (0.0, 0.0, 30.0), (2.0, 2.0, 2.0)))
    return f


@pytest.mark.parametrize("model, width", [("independent", 1), ("calibrated", 2)])
def test_two_sectors_of_one_site_share_one_clock(model, width):
    f = _started(clock_model=model, sites={"lte:0a": "A", "lte:0b": "A"})
    e = TOWERS[0]
    f.process(_pr(1_000_000_000, "lte:0a", e, 2500.0))
    f.process(_pr(1_000_000_000, "lte:0b", e, 2500.0))
    f.process(_pr(1_000_000_000, "lte:1", TOWERS[1], 2500.0))  # not mapped: its own site
    assert sorted(f.clock_idx) == ["site:A", "site:lte:1"]
    assert len(f.x) == ekf.N_CORE + 2 * width
    assert f.clock_offsets("lte:0a", 0.0) == f.clock_offsets("lte:0b", 0.0) == ([8], False)


def test_default_is_one_clock_per_emitter():
    f = _started()
    for i, e in enumerate(TOWERS[:2]):
        f.process(_pr(1_000_000_000, f"lte:{i}", e, 2500.0))
    assert len(f.x) == ekf.N_CORE + 2  # unchanged model: one offset state per emitter


def test_sites_of_one_builder_share_a_common_clock():
    sites = {"lte:0": "A", "lte:1": "B"}
    f = _started(clock_model="calibrated", sites=sites, builders={"A": "acme", "B": "acme"})
    a, new_a = f.clock_offsets("lte:0", 700.0)
    b, new_b = f.clock_offsets("lte:1", 650.0)
    assert new_a and new_b
    assert sorted(f.clock_idx) == ["builder:acme", "site:A", "site:B"]
    builder = f.clock_idx["builder:acme"]
    assert a == [builder, f.clock_idx["site:A"]] and b == [builder, f.clock_idx["site:B"]]
    assert len(f.x) == ekf.N_CORE + 3 * 2
    # The builder takes the first reading; each site starts as a residual on it, with the
    # tighter residual prior rather than the wide one
    assert f.x[builder] == 700.0 and f.x[b[1]] == -50.0
    assert np.sqrt(np.diag(f.P)[b[1] : b[1] + 2]) == pytest.approx([300.0, 0.1])
    assert np.sqrt(f.P[builder, builder]) == pytest.approx(2000.0)


def test_pseudorange_jacobian_with_builder_and_drift_states():
    f = _started(clock_model="calibrated", sites={"lte:0": "A"}, builders={"A": "acme"})
    m = _pr(0, "lte:0", [3000, 4000, 30], 5000.0)
    ekf.MODELS["pseudorange"](f, m)  # first sight: adds the builder and site blocks
    x0 = f.x.copy()
    y0, H, _, gate = ekf.MODELS["pseudorange"](f, m)
    assert gate
    for j in range(len(x0)):
        f.x = x0.copy()
        f.x[j] += 1e-3
        y1 = ekf.MODELS["pseudorange"](f, m)[0]
        assert -(y1 - y0) / 1e-3 == pytest.approx(H[0, j], abs=1e-5)


def test_unknown_clock_model_is_refused():
    with pytest.raises(ValueError, match="clock_model"):
        ekf.EKF(clock_model="magic")


def test_tower_clocks_calibrate_while_gnss_is_trusted():
    meas, _ = _drifting_towers()
    f = ekf.EKF(clock_model="calibrated")
    _feed(f, meas, until_s=120.0)
    assert f.calibrating
    for i, drift in enumerate(DRIFTS):
        k = f.clock_idx[f"site:lte:{i}"] + 1
        sigma = np.sqrt(f.P[k, k])
        assert sigma < 0.1  # m/s; regression guard, not a requirement
        assert abs(f.x[k] - drift) < 4 * sigma


def test_coasting_holds_the_learned_clocks_as_a_tight_prior():
    meas, _ = _drifting_towers()
    f = ekf.EKF(clock_model="calibrated")
    _feed(f, meas, until_s=120.0)
    k = f.clock_idx["site:lte:0"]
    F = np.array([[1.0, 60.0], [0.0, 1.0]])
    carried = F @ f.P[k : k + 2, k : k + 2] @ F.T  # the learned prior, carried 60 s
    added_cal = _predicted(f, gnss_lost=False)[k : k + 2, k : k + 2] - carried
    added_coast = _predicted(f, gnss_lost=True)[k : k + 2, k : k + 2] - carried
    # Over the same 60 s without measurements, coasting adds only the tower oscillator noise:
    # a small fraction of what calibrating adds (regression guard on the TBC noise values)
    assert np.all(np.diag(added_cal) > 0) and np.all(np.diag(added_coast) > 0)
    assert np.all(np.diag(added_coast) < 0.01 * np.diag(added_cal))


def test_the_clock_mode_follows_gnss():
    meas, _ = _drifting_towers(outage=(120.0, 300.0))
    f = ekf.EKF(clock_model="calibrated")
    _feed(f, meas, until_s=119.0)
    assert f.calibrating
    _feed(f, [m for m in meas if 119e9 <= m.t_ns < 200e9])
    assert not f.calibrating
    _feed(f, [m for m in meas if m.t_ns >= 200e9])
    assert f.calibrating


def _predicted(f: ekf.EKF, gnss_lost: bool) -> np.ndarray:
    """Covariance after 60 s of prediction alone from f's state, with GNSS lost or still
    arriving. Works on a copy, so f is unchanged. The gate's delay and checks are off: this
    measures the two noise models, not the gate."""
    g = ekf.EKF(clock_model="calibrated", calib_gate_s=0.0, calib_checks=(lambda _: True,))
    g.x, g.P, g.t_ns, g.clock_idx = f.x.copy(), f.P.copy(), f.t_ns, dict(f.clock_idx)
    t0 = f.t_ns
    for s in range(60):
        g.last_used = {"gnss": t0 - 10**10 if gnss_lost else t0 + s * 10**9}
        g.predict(t0 + (s + 1) * 10**9)
    return g.P


def _outage_error(meas, truth, outage=(120.0, 420.0), **config) -> float:
    est = list(ekf.run(meas, **config))
    true = {int(round(t * 1e9)): p for t, p in truth}
    late = [e for e in est if outage[1] - 60 <= e.t_ns / 1e9 < outage[1]]
    return float(np.mean([np.hypot(*(np.subtract(e.pos_enu, true[e.t_ns])[:2])) for e in late]))


def test_calibrated_clocks_grow_less_error_in_a_long_outage():
    # Regression guard on a deterministic case, not a requirement: 5 min without GNSS, towers
    # with drifting clocks. Learned drifts keep the towers usable; random-walk clocks don't.
    meas, truth = _drifting_towers()
    independent = _outage_error(meas, truth, clock_model="independent")
    calibrated = _outage_error(meas, truth, clock_model="calibrated")
    assert calibrated < 0.5 * independent
    assert calibrated < 20.0  # m, mean horizontal error over the last minute of the outage


# --- calibration gate and rollback ---------------------------------------------------------
ALWAYS = (lambda _: True,)  # a check that always confirms: lets a spoof through the gate


def _calibrating_at(f: ekf.EKF, meas, times_s) -> list[bool]:
    out, it = [], iter(meas)
    m = next(it, None)
    for t in times_s:
        while m is not None and m.t_ns / 1e9 < t:
            f.process(m)
            m = next(it, None)
        out.append(f.calibrating)
    return out


def test_the_gate_waits_for_gnss_to_be_trusted_for_calib_gate_s():
    meas, _ = _drifting_towers()
    f = ekf.EKF(clock_model="calibrated", calib_gate_s=30.0)
    times = np.arange(0.5, 120.0, 0.5)
    on = _calibrating_at(f, meas, times)
    assert not any(on[: np.searchsorted(times, 30.0)])
    # A GNSS rejection restarts the wait: calibration starts 30 s after GNSS was last trusted
    first = times[on.index(True)]
    assert 30.0 <= first - f._trusted_since / 1e9 <= 30.5
    assert all(on[on.index(True) :])


def test_the_gate_stays_shut_while_the_barometer_disagrees():
    meas, _ = _drifting_towers()
    biased = [
        M(m.t_ns, m.source, m.kind, (m.value[0] + 20.0,), m.sigma) if m.source == "baro" else m
        for m in meas
    ]
    f = ekf.EKF(clock_model="calibrated")
    assert not any(_calibrating_at(f, biased, np.arange(5.0, 120.0, 5.0)))
    assert ekf.baro_agrees(f) is False


def test_the_gate_needs_independent_confirmation():
    # Without a barometer nothing independent of GNSS confirms it (ADR-0024), so no calibration
    meas, _ = _drifting_towers()
    no_baro = [m for m in meas if m.source != "baro"]
    f = ekf.EKF(clock_model="calibrated")
    assert not any(_calibrating_at(f, no_baro, np.arange(5.0, 120.0, 5.0)))


def test_tower_and_receiver_clock_checks_only_refute():
    f = _started(clock_model="calibrated")
    f._nis = {"towers": deque([(0, 0.5, 1)] * 10), "rx_clock": deque([(0, 0.5, 1)] * 10)}
    # Consistent innovations are no objection, never a confirmation (ADR-0024)
    assert ekf.towers_consistent(f) is None and ekf.rx_clock_consistent(f) is None
    f._nis["towers"].extend([(0, 50.0, 1)] * 5)
    f._nis["rx_clock"].extend([(0, 50.0, 1)] * 5)
    assert ekf.towers_consistent(f) is False and ekf.rx_clock_consistent(f) is False


def test_an_added_check_can_veto_calibration():
    meas, _ = _drifting_towers()
    checks = (*ekf.CALIB_CHECKS, lambda _: False)  # e.g. a trust test from #82 or #83
    f = ekf.EKF(clock_model="calibrated", calib_checks=checks)
    assert not any(_calibrating_at(f, meas, np.arange(5.0, 120.0, 5.0)))


def _slow_spoof(start=100.0, rate=1.0, alarm=160.0, jump=300.0, late_tower_s=130.0):
    """_drifting_towers with GNSS dragged east at `rate` m/s from `start`, then jumped at
    `alarm` (so GNSS is excluded). A fifth tower is first heard at `late_tower_s`."""
    meas, _ = _drifting_towers(duration=170.0, outage=(1e9, 1e9))
    late = np.array([1500.0, 1500.0, 50.0])
    out = []
    for m in meas:
        s = m.t_ns / 1e9
        if m.source == "gnss" and s >= start:
            drag = [rate * (s - start) + (jump if s >= alarm else 0.0), 0.0, 0.0]
            m = M(m.t_ns, "gnss", "position_enu", tuple(np.add(m.value, drag)), m.sigma)
        out.append(m)
        if m.source == "lte" and m.emitter == "lte:0" and s >= late_tower_s:
            out.append(_pr(m.t_ns, "lte:late", late, 2121.3 + 100.0))
    return out


def _refutes_between(t0_s: float, t1_s: float, every_s: float = np.inf):
    """A check that confirms GNSS, except that it refutes it from t0_s to t1_s, repeated every
    `every_s`: brief signs of trouble, as a slow spoof gives while it grows."""

    def check(f: ekf.EKF) -> bool:
        t = f.t_ns / 1e9
        return not (t >= t0_s and (t - t0_s) % every_s < t1_s - t0_s)

    return (check,)


SLOW_SPOOF_SIGNS = _refutes_between(110.0, 110.5, every_s=8.0)  # gaps shorter than calib_check_s


def _run_spoof(until_s: float, checks=SLOW_SPOOF_SIGNS, **config):
    """Run _slow_spoof up to `until_s`, or to just after the first rollback if `until_s` is
    None. Returns the filter and each clock's drift when the spoof started."""
    config = {"spoof_p": None, **config}  # the GNSS jump raises the alarm, not the towers
    f = ekf.EKF(clock_model="calibrated", calib_checks=checks, **config)
    pre = None
    for m in _slow_spoof():
        if pre is None and m.t_ns >= 100e9:
            pre = {k: float(f.x[i + 1]) for k, i in f.clock_idx.items()}
        if (until_s is None and f.rollbacks) or (until_s is not None and m.t_ns / 1e9 >= until_s):
            break
        f.process(m)
    return f, pre


def test_rollback_after_a_slow_spoof_restores_the_pre_spoof_drifts():
    # The spoof mostly passes the gate, so the drifts learn it. A check refutes GNSS briefly
    # every 8 s from 110 s, so one episode lasts until the alarm at 160 s. The alarm rolls back
    # to the snapshot calib_rollback_margin_s (10 s) before the first sign: 100 s, the onset.
    rolled, pre = _run_spoof(None)  # GNSS excluded from 160 s, held 1 s
    kept, _ = _run_spoof(rolled.t_ns / 1e9 + 1e-3, calib_rollback_s=None)
    assert rolled.t_ns == kept.t_ns == 161_000_000_000
    assert len(rolled.rollbacks) == 1
    alarm, snap = rolled.rollbacks[0]
    assert alarm == 160_000_000_000 and 99e9 <= snap <= 100e9
    assert rolled.trouble_since == 110_000_000_000
    err_rolled = [abs(rolled.x[rolled.clock_idx[k] + 1] - v) for k, v in pre.items()]
    err_kept = [abs(kept.x[kept.clock_idx[k] + 1] - v) for k, v in pre.items()]
    assert max(err_rolled) < 0.02  # m/s; regression guard, not a requirement
    assert max(err_kept) > 0.3  # without rollback the spoof stays in the drifts
    # The tower first heard during the spoof is back to its first-sight prior
    i = rolled.clock_idx["site:lte:late"]
    assert np.sqrt(np.diag(rolled.P)[i : i + 2]) == pytest.approx(
        [rolled.init_emitter_sigma, rolled.init_tower_drift_sigma]
    )


def test_rollback_keeps_the_clean_calibration_before_the_episode():
    # No sign of trouble before the alarm at 160 s (a sudden spoof such as meaconing): the
    # rollback reaches only the margin before the alarm, not a fixed time, so the calibration
    # learned from clean GNSS before it is kept.
    rolled, _ = _run_spoof(None, checks=ALWAYS)
    alarm, snap = rolled.rollbacks[0]
    assert alarm == 160_000_000_000 and 149e9 <= snap <= 150e9


def test_a_quiet_spell_ends_the_suspicious_episode():
    # One sign at 50 s, then calib_check_s (10 s) without one: the episode is over and the
    # alarm at 160 s does not reach back to it
    rolled, _ = _run_spoof(None, checks=_refutes_between(50.0, 51.0))
    assert 149e9 <= rolled.rollbacks[0][1] <= 150e9


@pytest.mark.parametrize("builders", [None, {"lte:0": "acme", "lte:1": "acme"}])
def test_covariance_stays_symmetric_and_psd_through_a_rollback(builders):
    for until_s in (None, 170.0):  # just after the rollback, and after more updates
        f, _ = _run_spoof(until_s, builders=builders)
        assert len(f.rollbacks) == 1
        assert np.allclose(f.P, f.P.T, rtol=0, atol=1e-9)
        eig = np.linalg.eigvalsh(f.P)
        assert eig.min() > 0  # strictly positive here: the restored blocks add coast noise


def test_the_independent_model_ignores_the_calibration_settings():
    meas, _ = _drifting_towers()
    a = list(ekf.run(meas))
    b = list(ekf.run(meas, calib_gate_s=0.0, calib_checks=(), calib_rollback_s=1.0))
    assert a == b


def test_the_independent_model_matches_main():
    # Values from origin/main (3949f4c) on this fixture: the default model is unchanged
    meas, _ = _drifting_towers()
    est = list(ekf.run(meas))
    assert len(est) == 4199
    assert est[-1].pos_enu == pytest.approx(
        (-140.80565176860358, 191.81836675488827, 29.932267624492354), rel=1e-9
    )
    assert est[-1].hpl_m == pytest.approx(26.943874643141232, rel=1e-9)
    assert float(np.sum([e.pos_enu for e in est])) == pytest.approx(203689.58730246662, rel=1e-9)


# --- towers-vs-GNSS spoof detector (#83) ---------------------------------------------------
def _spoofed(rate=2.0, start=150.0, end=np.inf, tower_step=None, duration=300.0):
    """_drifting_towers without an outage, GNSS dragged north-east at `rate` m/s from `start`
    to `end` (then honest again). `tower_step` = (emitter index, metres): that tower's
    pseudorange steps from `start` instead."""
    meas, truth = _drifting_towers(outage=(1e9, 1e9), duration=duration)
    u = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    out = []
    for m in meas:
        s = m.t_ns / 1e9
        if m.source == "gnss" and start <= s < end:
            m = M(m.t_ns, "gnss", "position_enu", tuple(np.add(m.value, rate * (s - start) * u)),
                  m.sigma)  # fmt: skip
        if tower_step and m.emitter == f"lte:{tower_step[0]}" and s >= start:
            m = _pr(m.t_ns, m.emitter, m.meta["emitter_enu"], m.value[0] + tower_step[1])
        out.append(m)
    return out, truth


def _alarm_times(meas, **config) -> list[float]:
    est = list(ekf.run(meas, clock_model="calibrated", **config))
    return [e.t_ns / 1e9 for e in est if "spoof_suspected" in e.flags]


def test_towers_detect_a_2_mps_position_ramp_req04():
    # T4 (systems/plan.md, TBC): a 2 m/s ramp detected within 30 s. Regression guard on this
    # fixture (four towers, 5 m noise), not evidence for the target: that is the paired eval.
    meas, _ = _spoofed()
    on = _alarm_times(meas)
    assert on and 150.0 < on[0] <= 180.0


def test_no_spoof_alarm_on_clean_gnss_req04():
    meas, _ = _drifting_towers(outage=(1e9, 1e9), duration=300.0)
    assert _alarm_times(meas) == []


def test_one_faulty_tower_does_not_raise_the_gnss_alarm():
    # A single tower clock step is a tower fault: leaving each site out in turn removes it
    meas, _ = _spoofed(rate=0.0, tower_step=(0, 300.0))
    assert _alarm_times(meas) == []


def test_the_alarm_excludes_gnss_and_rolls_the_clocks_back():
    meas, _ = _spoofed()
    f = ekf.EKF(clock_model="calibrated")
    _feed(f, meas, until_s=200.0)
    assert f.spoof_alarm and f.spoof_alarms
    raised = f.spoof_alarms[0]
    assert f.rollbacks and f.rollbacks[0][0] <= raised + f.alarm_hold_ns
    assert {"gnss_excluded", "spoof_suspected"} <= set(f.estimate().flags)
    assert f.last_used["gnss"] <= raised  # never used again while the alarm holds


def test_the_alarm_clears_once_gnss_agrees_again():
    meas, _ = _spoofed(end=200.0, duration=300.0)
    on = _alarm_times(meas)
    assert on and on[-1] < 300.0 - 1.0  # cleared before the end of the run
    assert on[-1] >= 200.0 + 30.0  # but not before spoof_clear_s of agreement


def test_the_detector_is_not_armed_before_it_has_learned_its_null_scale():
    meas, _ = _spoofed(start=20.0)  # spoof before spoof_learn_s of quiet data
    f = ekf.EKF(clock_model="calibrated")
    _feed(f, meas, until_s=60.0)
    assert f.spoof_stat is None and not f.spoof_alarm
