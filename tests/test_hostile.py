"""The hostile beacon (P8, ADR-0025, #93): its sim records, its faults and the EKF's gate.

Short runs (90 s) keep this file fast; the paired 50-run evals are in the PR."""

import copy

import numpy as np
import pytest

from pnt.core.measurement import validate
from pnt.integrity.mhss import MHSS
from pnt.nav import ESTIMATORS, ekf
from pnt.nav.hostile import FLAG, capped_noise
from pnt.sim import hostile
from pnt.sim.scenario import T0_NS, generate, load

QUIET = {
    "shadowing_sigma_db": 0.0,
    "noise_sigma_db": 0.0,
    "power_rw_db": 0.0,
    "told_position_sigma_m": 0.0,
}


def _spec(name="hostile-beacon", duration_s=90, jam_start_s=10.0, faults=(), jammer=None):
    """A short copy of a beacon scenario: the jammer on from jam_start_s, plus `faults`."""
    spec = copy.deepcopy(load(name))
    spec["duration_s"] = duration_s
    spec["faults"][0]["start_s"] = jam_start_s
    spec["faults"] = [spec["faults"][0], *faults]
    if jammer is not None:
        spec["sources"]["jammer"].update(jammer)
    return spec


def _rssi(run):
    return [m for m in run.measurements if m.kind == "rssi"]


def _t(m):
    return (m.t_ns - T0_NS) / 1e9


def _square(t):
    """The 3 dB, 20 s square wave from 40 s of `test_power_faults_step_modulate_and_move`."""
    return 0.0 if t < 40 else (3.0 if (t - 40) % 20 < 10 else -3.0)


def _run_ekf(spec, seed=0, **config):
    run = generate(spec, seed)
    f = None

    def keep(main):
        nonlocal f
        f = main
        return MHSS(main)

    est = list(ekf.run(run.measurements, origin_llh=spec["origin_llh"], monitor=keep, **config))
    return run, est, f


def test_records_follow_the_path_loss_model_while_the_jammer_is_on():
    spec = _spec(jammer=QUIET)
    run = generate(spec, 0)
    recs = _rssi(run)
    assert recs and all(_t(m) >= 10.0 for m in recs)
    jam = hostile.jammers(spec)[0]
    truth = {t.t_ns: np.asarray(t.pos_enu) for t in run.truth}
    for m in recs:
        validate(m)
        assert (m.source, m.emitter, m.meta["hostile"]) == ("gnss", "jammer:sim0", True)
        assert m.meta["emitter_enu"] == pytest.approx(jam.enu.tolist())
        d = np.linalg.norm(truth[m.t_ns] - jam.enu)
        expected = 20.0 - hostile.LOSS_1M_DB - 20.0 * np.log10(d)
        assert m.value[0] == pytest.approx(expected, abs=1e-9)


def test_beacon_records_leave_every_other_record_as_it_was():
    """Own random stream, and kept inside the jamming zone's lost radius."""
    with_beacon = generate(load("jamming-zone-beacon"), 3)
    without = generate(load("jamming-zone"), 3)
    assert [m for m in with_beacon.measurements if m.kind != "rssi"] == without.measurements
    assert len(_rssi(with_beacon)) == 360  # 1 Hz for 360 s: none lost near the jammer


def test_power_faults_step_modulate_and_move():
    base = _rssi(generate(_spec(jammer=QUIET), 0))
    step = {"type": "hostile_power", "start_s": 40, "step_db": 6.0}
    wave = {"type": "hostile_power", "start_s": 40, "amplitude_db": 3.0, "period_s": 20.0}
    moves = {"type": "hostile_moves", "start_s": 40, "velocity_enu_mps": [0.0, 2.0, 0.0]}
    for fault, check in [
        (step, lambda t, d: d == pytest.approx(6.0 if t >= 40 else 0.0)),
        (wave, lambda t, d: d == pytest.approx(_square(t))),
        (moves, lambda t, d: (d == pytest.approx(0.0)) if t <= 40 else d != pytest.approx(0.0)),
    ]:  # fmt: skip
        hit = _rssi(generate(_spec(jammer=QUIET, faults=[fault]), 0))
        assert len(hit) == len(base)
        for a, b in zip(base, hit, strict=True):
            assert check(_t(a), b.value[0] - a.value[0]), (fault["type"], _t(a))
    # moving: the power follows the true geometry while the told position stays put
    spec = _spec(jammer=QUIET, faults=[moves])
    run = generate(spec, 0)
    truth = {t.t_ns: np.asarray(t.pos_enu) for t in run.truth}
    jam = hostile.jammers(spec)[0].enu
    m = _rssi(run)[-1]
    now = jam + np.array([0.0, 2.0, 0.0]) * (_t(m) - 40)
    d = np.linalg.norm(truth[m.t_ns] - now)
    assert m.value[0] == pytest.approx(20.0 - hostile.LOSS_1M_DB - 20.0 * np.log10(d), abs=1e-9)
    assert m.meta["emitter_enu"] == pytest.approx(jam.tolist())


def test_jammer_power_needs_a_jammer_and_known_settings():
    spec = _spec()
    spec["faults"] = []
    with pytest.raises(ValueError, match="needs a jamming_zone"):
        generate(spec)
    with pytest.raises(ValueError, match="unknown settings"):
        generate(_spec(jammer={"tx_power_w": 1.0}))


def test_without_the_beacon_option_the_records_change_nothing():
    """ekf-mhss on a scenario with beacon records equals ekf-mhss on the same records without."""
    spec = _spec(duration_s=60)
    run = generate(spec, 1)
    plain = [m for m in run.measurements if m.kind != "rssi"]
    a = list(ESTIMATORS["ekf-mhss"](run.measurements, origin_llh=spec["origin_llh"]))
    b = list(ESTIMATORS["ekf-mhss"](plain, origin_llh=spec["origin_llh"]))
    assert a == b


def test_steady_jammer_is_promoted_after_the_window_and_shown_apart_from_gnss():
    run, est, f = _run_ekf(_spec(), hostile={})
    b = f.hostile.by_emitter["jammer:sim0"]
    assert [e for _, e in b.events] == ["promoted"]
    t_promoted = (b.events[0][0] - T0_NS) / 1e9
    assert t_promoted >= 10.0 + 30.0  # first heard at 10 s, window 30 s (TBC)
    last = est[-1]
    assert FLAG in last.flags and last.trust["hostile:jammer:sim0"] == 1.0
    assert "hostile:jammer:sim0" in f.last_used and "jammer:sim0" not in f.last_used
    flagged = [(e.t_ns - T0_NS) / 1e9 for e in est if FLAG in e.flags]
    assert min(flagged) >= t_promoted


def test_large_power_step_demotes_at_once():
    step = {"type": "hostile_power", "start_s": 60, "step_db": 30.0}
    _, _, f = _run_ekf(_spec(faults=[step]), hostile={})
    b = f.hostile.by_emitter["jammer:sim0"]
    events = [((t - T0_NS) / 1e9, e) for t, e in b.events]
    assert events[0][1] == "promoted" and events[0][0] < 60
    assert events[1] == (60.0, "demoted: power step")
    assert not b.promoted  # the 30 s window has not passed again by the end (90 s)


def test_monitor_holds_the_beacon_as_its_own_hypothesis():
    spec = _spec(duration_s=40)
    run = generate(spec, 0)
    mons = {}
    for name, config in [("plain", {}), ("beacon", {"hostile": {}})]:

        def keep(main, name=name):
            mons[name] = MHSS(main)
            return mons[name]

        list(ekf.run(run.measurements, origin_llh=spec["origin_llh"], monitor=keep, **config))
    assert "hostile:jammer:sim0" in mons["beacon"].hyps
    assert not any(h.startswith("hostile:") for h in mons["plain"].hyps)
    assert set(mons["plain"].hyps) == set(mons["beacon"].hyps) - {"hostile:jammer:sim0"}


def test_beacon_never_shrinks_the_hpl_below_its_subset_bound():
    """ADR-0025 guardrail 3: the HPL holds as if the beacon were certainly lying."""
    spec = _spec(duration_s=70)
    run = generate(spec, 0)
    checked = []

    class Checked(MHSS):
        def estimate(self, est):
            out = super().estimate(est)
            h = self.hyps.get("hostile:jammer:sim0")
            if h is not None and self.report.excluded is None:
                x0, f = self.main.x, h.filters[0]
                sep = float(np.hypot(*(f.x[:2] - x0[:2])))
                s = float(np.sqrt(np.max(np.linalg.eigvalsh(f.P[:2, :2]))))
                k_ff = np.sqrt(-2.0 * np.log(self.p.phmi / 2))
                assert out.hpl_m >= sep + k_ff * s - 1e-6
                checked.append(FLAG in out.flags)
            return out

    list(ekf.run(run.measurements, origin_llh=spec["origin_llh"], monitor=Checked, hostile={}))
    assert len(checked) > 400 and any(checked)  # checked while the beacon was in use too


@pytest.mark.parametrize(("a", "s0", "r"), [(100.0, 4.0, 9.0), (30.0, 1.0, 1.0), (0.5, 0.01, 9.0)])
def test_weight_cap_bounds_one_sigma_of_deception(a, s0, r):
    cap = 5.0
    R = capped_noise(a, s0, r, cap)
    assert R >= r
    assert a * np.sqrt(R) / (s0 + R) <= cap * (1 + 1e-9)
    if a * np.sqrt(r) / (s0 + r) <= cap:
        assert R == r  # never inflated when already within the cap
