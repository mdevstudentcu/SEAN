"""The simulated ground reference station (issue #80, ADR-0020)."""

import numpy as np
import pytest

from pnt.cli import main
from pnt.core.frames import llh_to_enu
from pnt.core.measurement import validate
from pnt.io import session
from pnt.sim.scenario import T0_NS, attack_names, expand, generate, load

C = 299_792_458.0


def _payload(run):
    return [m for m in run.measurements if m.receiver == "payload"]


def _reference(run):
    return [m for m in run.measurements if m.receiver == "reference"]


def _clean(name):
    """A with-base scenario with every random error turned off, so ranges can be checked."""
    spec = load(name)
    lte = spec["sources"]["lte"]
    lte.update(sigma_m=1e-9, told_position_sigma_m=0.0)
    for k in ("multipath", "dropout"):
        lte.pop(k, None)
    spec["reference"].update(survey_sigma_m=0.0, sources={"lte": {"sigma_m": 1e-9}})
    return spec


def test_the_station_is_repeatable_req10():
    spec = load("realistic-with-base-long-outage")
    a, b = generate(spec, seed=4), generate(load("realistic-with-base-long-outage"), seed=4)
    assert a.measurements == b.measurements
    assert a.reference == b.reference
    assert generate(spec, seed=5).reference != a.reference  # the survey error is drawn per seed


@pytest.mark.parametrize(
    "with_base, without",
    [
        ("realistic-with-base-nominal", "realistic-nominal"),
        ("realistic-with-base-outage", "realistic-outage"),
        ("realistic-with-base-tower-clock-step", "realistic-tower-clock-step"),
        ("uc01-drone-circuit-with-base", "uc01-drone-circuit"),
    ],
)
def test_adding_the_station_leaves_every_payload_record_unchanged(with_base, without):
    # The station draws from its own stream, so the payload's records match seed for seed and
    # a paired comparison with and without the base sees the same payload data
    for seed in (0, 7):
        a, b = generate(load(with_base), seed=seed), generate(load(without), seed=seed)
        assert _payload(a) == b.measurements
        assert _reference(a) and b.reference is None


def test_reference_records_are_valid_and_labelled():
    run = generate(load("realistic-with-base-nominal"), seed=0)
    ref = _reference(run)
    for m in ref:
        validate(m)
    assert {m.source for m in ref} == {"lte"} and {m.kind for m in ref} == {"pseudorange"}
    session.validate_reference(run.reference)
    assert run.reference["surveyed"] is False and run.reference["sigma_m"] == 1.0


def test_the_station_ranges_from_where_it_stands_and_shares_the_tower_clocks():
    # Noise off: payload minus base, per tower and epoch, leaves only the two receivers' clocks.
    # It is the same for every tower, so the tower clocks are shared and the base's range is
    # measured from its own position
    spec = _clean("realistic-with-base-nominal")
    run = generate(spec, seed=0)
    truth = {t.t_ns: t for t in run.truth}
    base = llh_to_enu(spec["reference"]["position_llh"], spec["origin_llh"])
    ref = {(m.t_ns, m.emitter): m.value[0] for m in _reference(run)}
    left = {}
    for m in _payload(run):
        if m.kind != "pseudorange":
            continue
        e = np.asarray(run.emitters[m.emitter])
        p = np.asarray(truth[m.t_ns].pos_enu)
        geometry = np.linalg.norm(p - e) - np.linalg.norm(base - e)
        sd = m.value[0] - ref[(m.t_ns, m.emitter)]
        left.setdefault(m.t_ns, []).append(sd - geometry - C * truth[m.t_ns].clock_bias_s)
    spread = [max(v) - min(v) for v in left.values()]
    assert max(spread) < 1e-3
    # what is left is minus the base's clock: its 100 ns offset plus a small wander
    assert np.mean([v[0] for v in left.values()]) == pytest.approx(-C * 1e-7, abs=10.0)


def test_the_survey_error_follows_sigma():
    spec = load("realistic-with-base-nominal")
    base = llh_to_enu(spec["reference"]["position_llh"], spec["origin_llh"])
    told = [
        llh_to_enu(generate(spec, seed=s).reference["position_llh"], spec["origin_llh"])
        for s in range(20)
    ]
    err = np.array(told) - base
    assert 0.3 < err.std() < 2.0  # sigma_m is 1 m; a loose regression guard, not a requirement


def test_reference_moved_changes_only_the_base_by_the_true_geometry():
    spec = _clean("realistic-with-base-long-outage-base-moved")
    moved = generate(spec, seed=0)
    spec["faults"] = [f for f in spec["faults"] if f["type"] != "reference_moved"]
    still = generate(spec, seed=0)
    assert _payload(moved) == _payload(still)
    base = llh_to_enu(spec["reference"]["position_llh"], spec["origin_llh"])
    off = np.array([40.0, 30.0, 0.0])
    start = T0_NS + 150 * 10**9
    for a, b in zip(_reference(moved), _reference(still), strict=True):
        e = np.asarray(moved.emitters[a.emitter])
        want = np.linalg.norm(base + off - e) - np.linalg.norm(base - e) if a.t_ns >= start else 0
        assert a.value[0] - b.value[0] == pytest.approx(want, abs=1e-6)


def test_a_fault_can_name_one_receiver():
    run = generate(load("realistic-with-base-long-outage-base-lost"), seed=0)
    lost = [
        m for m in run.measurements if m.source == "lte" and 150 <= (m.t_ns - T0_NS) / 1e9 < 210
    ]
    assert lost and all(m.receiver == "payload" for m in lost)


def test_with_base_variants_compose_and_only_they_get_base_attacks():
    assert "realistic-with-base-long-outage-base-moved" in expand("realistic-with-base")
    assert "long-outage-base-moved" not in attack_names()
    assert "realistic-long-outage-base-moved" not in expand("realistic")
    assert load("realistic-with-base-outage")["faults"] == load("realistic-outage")["faults"]
    with pytest.raises(FileNotFoundError):
        load("realistic-long-outage-base-moved")
    spec = load("uc01-drone-circuit-with-base")
    assert spec["name"] == "uc01-drone-circuit-with-base" and "reference" in spec


def test_sim_session_records_the_station(tmp_path, capsys):
    out = tmp_path / "s"
    main(["sim", "realistic-with-base-nominal", "--out", str(out), "--estimator", "ekf-base"])
    meta = session.read_meta(out)
    assert meta["reference"] == generate(load("realistic-with-base-nominal"), seed=0).reference
    assert session.read_meta(out / session.MCAP_NAME)["reference"] == meta["reference"]
