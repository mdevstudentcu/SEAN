import numpy as np
import pytest

from pnt.cli import main
from pnt.metrics import score
from pnt.nav import baseline
from pnt.sim import scenario
from pnt.sim.scenario import T0_NS, attack_names, expand, generate, load, load_named, set_names

LABELS = {"datasheet", "literature", "measured", "TBC"}
# Numeric limits in this file are regression guards, not requirements.


def _kind(run, kind):
    return [m for m in run.measurements if m.kind == kind]


def _seconds(m):
    return (m.t_ns - T0_NS) / 1e9


def test_the_environments_exist():
    # realistic-with-base: realistic plus a ground reference station (ADR-0020, issue #80)
    # challenge-*: the challenge benchmark set, one leg per use case (ADR-0030, issue #136)
    # challenge-drone-hop: the drone leg hopping LTE carriers, a study leg (#173, ADR-0037)
    assert set_names() == [
        "challenge-approach",
        "challenge-drone",
        "challenge-drone-hop",
        "challenge-timing",
        "easy",
        "realistic",
        "realistic-with-base",
        "worst",
    ]


def test_a_set_name_expands_to_every_attack():
    names = expand("realistic")
    assert len(names) == len(attack_names())
    assert "realistic-spoof-ramp" in names
    assert expand("gps-outage") == ["gps-outage"]


@pytest.mark.parametrize("name", [n for s in set_names() for n in expand(s)])
def test_every_combination_runs_and_is_repeatable_req10(name):
    spec = load(name)
    first = generate(spec, seed=1)
    assert spec["name"] == name
    assert first.measurements == generate(load(name), seed=1).measurements
    estimates = list(baseline.run(first.measurements, origin_llh=spec["origin_llh"]))
    assert score(estimates, first.truth, spec, T0_NS).n > 3000


@pytest.mark.parametrize("name", set_names())
def test_every_environment_states_where_its_numbers_come_from(name):
    labels = load(f"{name}-nominal")["provenance"]
    assert labels and set(labels.values()) <= LABELS


def test_environments_get_harder():
    lte = {s: load(f"{s}-nominal")["sources"]["lte"] for s in set_names()}
    assert lte["easy"]["sigma_m"] < lte["realistic"]["sigma_m"] < lte["worst"]["sigma_m"]
    count = lte["realistic"]["towers_from"]["count"], lte["worst"]["towers_from"]["count"]
    assert lte["easy"]["n_emitters"] > count[0] > count[1]


def test_session_names_can_refer_to_combinations_but_not_arbitrary_paths():
    assert load_named("worst-outage")["faults"][0]["type"] == "outage"
    with pytest.raises(ValueError):
        load_named("../../etc/passwd")
    with pytest.raises(FileNotFoundError):
        load_named("realistic-teleport")


def test_gps_no_fix_stops_position_but_the_receiver_keeps_reporting():
    run = generate(load("easy-gps-no-fix"), seed=0)
    positions = [_seconds(m) for m in _kind(run, "position_enu")]
    assert not any(120 <= t < 240 for t in positions)
    health = [m for m in _kind(run, "gnss_health") if 120 <= _seconds(m) < 240]
    assert health and all(m.value[1] == 0.0 for m in health)


def test_gps_low_sats_changes_health_but_not_position():
    clean, low = (generate(load(f"easy-{a}"), seed=0) for a in ("nominal", "gps-low-sats"))
    assert _kind(clean, "position_enu") == _kind(low, "position_enu")
    health = [m for m in _kind(low, "gnss_health") if 120 <= _seconds(m) < 240]
    assert health and all(m.value[1] == 3.0 for m in health)


def test_gps_returns_to_normal_after_a_jump():
    clean, jump = (generate(load(f"easy-{a}"), seed=0) for a in ("nominal", "gps-return"))
    for a, b in zip(_kind(clean, "position_enu"), _kind(jump, "position_enu"), strict=True):
        expected = 300.0 if 150 <= _seconds(a) < 200 else 0.0
        assert b.value[0] - a.value[0] == pytest.approx(expected, abs=1e-6)


def test_baro_drift_grows_after_it_starts():
    clean, drift = (generate(load(f"easy-{a}"), seed=0) for a in ("nominal", "baro-drift"))
    for a, b in zip(_kind(clean, "altitude"), _kind(drift, "altitude"), strict=True):
        expected = 0.2 * max(_seconds(a) - 120, 0.0)
        assert b.value[0] - a.value[0] == pytest.approx(expected, abs=1e-6)


def test_eval_runs_a_whole_set_by_name(capsys, monkeypatch):
    monkeypatch.setattr(scenario, "attack_names", lambda: ["nominal", "outage"])
    main(["eval", "easy", "--runs", "1"])
    out = capsys.readouterr().out
    assert "scenario easy-nominal" in out and "scenario easy-outage" in out


def test_realistic_towers_really_drop_out():
    run = generate(load("realistic-nominal"), seed=0)
    per_tower = {}
    for m in _kind(run, "pseudorange"):
        per_tower.setdefault(m.emitter, []).append(m.t_ns)
    assert any(np.max(np.diff(t)) > 20_000_000_000 for t in per_tower.values())
