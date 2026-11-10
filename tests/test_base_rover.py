"""Base/rover differencing with collaborative integrity (issue #81, ADR-0020)."""

import numpy as np

from pnt.core.measurement import RECEIVERS
from pnt.io import session
from pnt.io.mcap_log import SessionWriter
from pnt.nav import ESTIMATORS, base_rover, ekf, estimate, receivers
from pnt.sim.scenario import T0_NS, generate, load
from pnt.sources.replay import ReplaySource


def _filter(name, seed, **config):
    """Run the filter object over a scenario; returns (filter, run)."""
    spec = load(name)
    run = generate(spec, seed=seed)
    f = base_rover.BaseRoverEKF(origin_llh=spec["origin_llh"], reference=run.reference, **config)
    for m in run.measurements:
        f.process(m)
    f.settle(run.measurements[-1].t_ns + 1)
    return f, run


def _flags(name, seed):
    spec = load(name)
    run = generate(spec, seed=seed)
    est = estimate("ekf-base", run.measurements, spec["origin_llh"], reference=run.reference)
    return [(e.t_ns, set(e.flags)) for e in est]


def test_registered_for_both_receivers():
    assert ESTIMATORS["ekf-base"] is base_rover.run
    assert receivers(base_rover.run) == RECEIVERS


def test_without_a_base_it_is_the_single_receiver_ekf():
    # No reference block, no reference records: the fallback is `ekf` with the payload's clock
    # in its tower readings, epoch for epoch
    spec = load("realistic-outage")
    run = generate(spec, seed=2)
    o = spec["origin_llh"]
    a = list(base_rover.run(run.measurements, origin_llh=o))
    b = list(ekf.run(run.measurements, origin_llh=o, pseudorange_receiver_clock=True))
    assert len(a) == len(b)
    assert np.allclose([e.pos_enu for e in a], [e.pos_enu for e in b])


def test_a_tower_clock_step_cancels_in_the_difference():
    # 300 m step on lte:sim1 at 150 s, GPS out since 60 s. Differenced, the tower keeps being
    # used; alone, the payload's filter rejects it from the step on
    step = T0_NS + 150 * 10**9
    based, _ = _filter("realistic-with-base-long-outage-tower-clock-step", seed=0)
    spec = load("realistic-with-base-long-outage-tower-clock-step")
    alone = ekf.EKF(origin_llh=spec["origin_llh"], pseudorange_receiver_clock=True)
    for m in generate(spec, seed=0).measurements:
        if m.receiver == "payload":
            alone.process(m)
    assert based.last_used["lte"] > step + 100 * 10**9
    assert alone.last_rejected["lte"] > step + 100 * 10**9
    assert "lte:sim1" in based.tower_fault_t  # the base's own view flags the tower
    # the jump it reports, against the scenario's 300 m: a regression guard, not a target
    assert abs(based.tower_jump_m["lte:sim1"] - 300.0) < 50.0
    assert based.base_fault_t is None


def test_a_moved_base_is_excluded_and_a_stepped_base_clock_too():
    for name in ("realistic-with-base-long-outage-base-clock-step",):
        f, _ = _filter(name, seed=0)
        assert f.base_fault_t is not None and f.base_fault_t >= T0_NS + 150 * 10**9
        flags = _flags(name, seed=0)
        assert any("base_excluded" in fl for _, fl in flags)


def test_tower_fault_flag_names_the_tower_and_its_jump():
    epochs = _flags("realistic-with-base-long-outage-tower-clock-step", seed=0)
    flags = {f for _, fl in epochs for f in fl}
    named = [f for f in flags if f.startswith("tower_fault")]
    assert named and all(f.startswith("tower_fault:lte:sim1:+") for f in named), flags


def test_no_base_fault_on_a_clean_run():
    for seed in range(3):
        f, _ = _filter("realistic-with-base-long-outage", seed=seed)
        assert f.base_fault_t is None


def test_base_dropouts_fall_back_to_the_base_last_view():
    f, run = _filter("realistic-with-base-long-outage-base-lost", seed=0)
    assert f.base_fault_t is None
    assert f.last_used["lte"] > T0_NS + 200 * 10**9


def test_replay_of_a_two_receiver_session_matches_the_sim(tmp_path):
    # ADR-0004: the estimator gets the same records and the same reference block from a replayed
    # session as from the sim
    spec = load("realistic-with-base-long-outage")
    run = generate(spec, seed=1)
    folder = tmp_path / "s"
    folder.mkdir()
    session.write_meta(folder, {"name": "s", "origin_llh": spec["origin_llh"],
                                "reference": run.reference})  # fmt: skip
    with SessionWriter(folder / session.MCAP_NAME) as w:
        for m in run.measurements:
            w.write(f"/meas/{m.source}", m)
    meta = session.read_meta(folder)
    replayed = list(
        estimate("ekf-base", ReplaySource(folder / session.MCAP_NAME), meta["origin_llh"],
                 reference=meta["reference"])
    )  # fmt: skip
    direct = list(estimate("ekf-base", run.measurements, spec["origin_llh"], run.reference))
    assert [e.pos_enu for e in replayed] == [e.pos_enu for e in direct]


def test_an_unknown_survey_accuracy_is_not_assumed():
    # ICD-session: sigma_m TBD or absent means the accuracy is unknown, so the survey error's
    # prior carries no information; a number is used as given
    spec = load("realistic-with-base-nominal")
    run = generate(spec, seed=0)
    priors = {}
    for label, sigma in (("given", 1.0), ("tbd", "TBD"), ("absent", None)):
        ref = {k: v for k, v in run.reference.items() if k != "sigma_m"}
        if sigma is not None:
            ref["sigma_m"] = sigma
        f = base_rover.BaseRoverEKF(origin_llh=spec["origin_llh"], reference=ref)
        for m in run.measurements:
            f.process(m)
            if f.bpos is not None:
                break
        priors[label] = np.sqrt(np.diag(f.P[f.bpos, f.bpos]))
    assert np.allclose(priors["given"], 1.0)
    assert np.all(priors["tbd"] >= 1e3)
    assert np.allclose(priors["tbd"], priors["absent"])
