import copy

import numpy as np
import pytest

from pnt import compare
from pnt.cli import main
from pnt.core.measurement import Truth
from pnt.io.mcap_log import SessionWriter
from pnt.sim.scenario import T0_NS, generate, load

# Numeric limits in this file are regression guards, not requirements.


def _record(path, name, seed=0):
    spec = load(name)
    run = generate(spec, seed=seed)
    with SessionWriter(path, metadata={"origin_llh": spec["origin_llh"], "scenario": name}) as w:
        for t in run.truth:
            w.write("/truth", t)
        for m in run.measurements:
            w.write(f"/meas/{m.source}", m)
    return path


@pytest.fixture(scope="module")
def sessions(tmp_path_factory):
    folder = tmp_path_factory.mktemp("cmp")
    return {
        "easy": _record(folder / "easy.mcap", "easy-nominal", 1),
        "easy2": _record(folder / "easy2.mcap", "easy-nominal", 2),
        "worst": _record(folder / "worst.mcap", "worst-nominal", 1),
    }


def test_same_environment_looks_the_same(sessions):
    a, b = (compare.statistics(sessions[k], "lte") for k in ("easy", "easy2"))
    assert a["residual_std"] == pytest.approx(b["residual_std"], rel=0.15)
    assert a["availability"] == pytest.approx(b["availability"], abs=0.02)


def test_a_harder_environment_is_visibly_different(sessions):
    easy, worst = (compare.statistics(sessions[k], "lte") for k in ("easy", "worst"))
    assert worst["residual_std"] > 2 * easy["residual_std"]
    assert worst["availability"] < easy["availability"]
    assert worst["persistence_lag1"] > easy["persistence_lag1"] + 0.15


def test_residual_size_matches_the_known_noise(sessions):
    assert compare.statistics(sessions["easy"], "lte")["residual_std"] == pytest.approx(
        20.0, rel=0.2
    )


def test_table_shows_both_sessions_and_the_gap(sessions):
    text = compare.table(sessions["easy"], sessions["worst"], "lte")
    assert "| Statistic (lte) | Simulated | Real | Gap |" in text and "residual_std" in text


def test_figure_is_written(sessions, tmp_path):
    pytest.importorskip("matplotlib")
    out = compare.plot(sessions["easy"], sessions["worst"], "lte", tmp_path / "a" / "cmp.png")
    assert out.stat().st_size > 1000


def test_session_without_truth_is_a_clear_error(tmp_path):
    path = tmp_path / "none.mcap"
    run = generate(load("easy-nominal"), seed=0)
    with SessionWriter(path, metadata={"origin_llh": run.spec["origin_llh"]}) as w:
        w.write("/meas/lte", next(m for m in run.measurements if m.source == "lte"))
    with pytest.raises(ValueError, match="truth"):
        compare.statistics(path, "lte")


def test_attacks_can_be_injected_into_a_recording(sessions):
    fault = [{"type": "spoof_jump", "source": "gnss", "start_s": 100, "offset_enu_m": [300, 0, 0]}]
    meas, t0 = compare.inject(sessions["easy"], fault)
    assert t0 == T0_NS
    clean, _ = compare.inject(sessions["easy"], [])
    fixes = [(a, b) for a, b in zip(clean, meas, strict=True) if a.kind == "position_enu"]
    for a, b in fixes:
        expected = 300.0 if a.t_ns >= t0 + 100_000_000_000 else 0.0
        assert b.value[0] - a.value[0] == pytest.approx(expected, abs=1e-6)


def test_replay_can_inject_a_named_scenarios_faults(sessions, capsys):
    main(["replay", str(sessions["easy"]), "--inject", "easy-spoof-jump"])
    out = capsys.readouterr().out
    assert "injected" in out
    line = next(ln for ln in out.splitlines() if "fault_h_p95_m" in ln)
    assert "nan" not in line


def test_compare_command_prints_the_table(sessions, capsys):
    main(["compare", str(sessions["easy"]), str(sessions["worst"]), "--source", "gnss"])
    assert "Statistic (gnss)" in capsys.readouterr().out


def test_a_scenario_can_replay_one_stream_from_a_recording(sessions):
    spec = copy.deepcopy(load("easy-nominal"))
    spec["replay_streams"] = {"session": str(sessions["easy2"]), "sources": ["baro"]}
    run = generate(spec, seed=9)
    recorded = generate(load("easy-nominal"), seed=2)
    a = [m for m in run.measurements if m.source == "baro"]
    b = [m for m in recorded.measurements if m.source == "baro"]
    assert a == b
    other = generate(load("easy-nominal"), seed=9)
    assert [m for m in run.measurements if m.source == "lte"] != []
    assert len([m for m in run.measurements if m.source == "lte"]) == len(
        [m for m in other.measurements if m.source == "lte"]
    )


def test_replayed_streams_are_shifted_to_the_scenario_clock(tmp_path):
    path = tmp_path / "later.mcap"
    run = generate(load("easy-nominal"), seed=0)
    shift = 5_000_000_000
    with SessionWriter(path, metadata={"origin_llh": run.spec["origin_llh"]}) as w:
        for m in run.measurements:
            if m.source == "baro":
                w.write("/meas/baro", _shifted(m, shift))
        w.write("/truth", Truth(t_ns=T0_NS, pos_enu=(0, 0, 0), vel_enu=(0, 0, 0)))
    spec = copy.deepcopy(load("easy-nominal"))
    spec["replay_streams"] = {"session": str(path), "sources": ["baro"]}
    times = [m.t_ns for m in generate(spec, seed=0).measurements if m.source == "baro"]
    assert np.min(times) == T0_NS


def _shifted(m, shift):
    import msgspec

    return msgspec.structs.replace(m, t_ns=m.t_ns + shift)
