"""`pnt compare`, `pnt replay --inject` and `replay_streams` (issue #30, ADR-0015)."""

import copy

import msgspec
import numpy as np
import pytest

from pnt import compare
from pnt.cli import main
from pnt.core.measurement import Measurement, Truth
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_session
from pnt.sim.scenario import T0_NS, generate, load

# Numeric limits in this file are regression guards, not requirements.

AMBIGUITY_M = 2997924.58  # one 10 ms LTE frame, as the front end's meta.ambiguity_m


def _record(path, name, seed=0):
    spec = load(name)
    run = generate(spec, seed=seed)
    with SessionWriter(path, metadata={"origin_llh": spec["origin_llh"], "scenario": name}) as w:
        for t in run.truth:
            w.write("/truth", t)
        for m in run.measurements:
            w.write(f"/meas/{m.source}", m)
    return path


def _static_lte(path, channels, seconds=120, sigma_m=3.0, seed=0):
    """A static session without truth, shaped like a real LTE capture: per (emitter, arc), the
    range is start + drift x t + white noise, known only modulo AMBIGUITY_M."""
    rng = np.random.default_rng(seed)
    with SessionWriter(path, metadata={"platform": "static", "origin_llh": None}) as w:
        for t in range(seconds):
            for emitter, arc, start, drift in channels:
                value = (start + drift * t + rng.normal(0.0, sigma_m)) % AMBIGUITY_M
                meta = {"arc": arc, "ambiguity_m": AMBIGUITY_M}
                m = Measurement(
                    t_ns=T0_NS + t * 1_000_000_000, source="lte", kind="pseudorange",
                    emitter=emitter, value=(value,), sigma=(sigma_m,), meta=meta,
                )  # fmt: skip
                w.write("/meas/lte", m)
    return path


@pytest.fixture(scope="module")
def sessions(tmp_path_factory):
    folder = tmp_path_factory.mktemp("cmp")
    return {
        "easy": _record(folder / "easy.mcap", "easy-nominal", 1),
        "easy2": _record(folder / "easy2.mcap", "easy-nominal", 2),
        "realistic": _record(folder / "realistic.mcap", "realistic-nominal", 1),
        "worst": _record(folder / "worst.mcap", "worst-nominal", 1),
    }


def test_same_environment_looks_the_same(sessions):
    a, b = (compare.statistics(sessions[k], "lte") for k in ("easy", "easy2"))
    assert a["residual_std"] == pytest.approx(b["residual_std"], rel=0.15)
    assert a["availability"] == pytest.approx(b["availability"], abs=0.02)


def test_a_harder_environment_is_visibly_different(sessions):
    easy, realistic, worst = (
        compare.statistics(sessions[k], "lte") for k in ("easy", "realistic", "worst")
    )
    assert worst["residual_std"] > 2 * easy["residual_std"]
    assert worst["availability"] < easy["availability"]
    # realistic's 30 s multipath persists from one second to the next; easy has none. (worst's
    # 120 s multipath is mostly taken out with the trend over its short channels)
    assert realistic["persistence_lag1"] > easy["persistence_lag1"] + 0.15


def test_residual_size_matches_the_known_noise(sessions):
    # easy: sigma_m 20 plus a 0.2 m/sqrt(s) tower clock walk that the trend removal mostly takes
    std = compare.statistics(sessions["easy"], "lte")["residual_std"]
    assert std == pytest.approx(20.0, rel=0.2)


def test_a_static_session_without_truth_is_its_own_reference(tmp_path):
    # Two towers, one of them re-acquired (arc 1) after its range jumped, and one whose range
    # crosses the frame ambiguity: without per-arc channels and unwrapping, the std would be
    # hundreds of km
    path = _static_lte(
        tmp_path / "static.mcap",
        [
            ("lte:2460:1", 0, 1_000_000.0, 0.3),
            ("lte:2460:1", 1, 2_000_000.0, 0.3),
            ("lte:2460:2", 0, AMBIGUITY_M - 20.0, 0.5),
        ],
    )
    stats = compare.statistics(path, "lte")
    assert stats["channels"] == 3
    assert stats["residual_std"] == pytest.approx(3.0, rel=0.15)


def test_a_moving_session_without_truth_or_tower_positions_is_a_clear_error(tmp_path):
    path = tmp_path / "moving.mcap"
    run = generate(load("easy-nominal"), seed=0)
    with SessionWriter(path, metadata={"origin_llh": run.spec["origin_llh"]}) as w:
        for m in run.measurements:
            if m.source == "gnss":
                w.write("/meas/gnss", m)
    with pytest.raises(ValueError, match="truth"):
        compare.statistics(path, "gnss")


def test_compare_over_the_same_span(tmp_path):
    path = _static_lte(tmp_path / "s.mcap", [("lte:2460:1", 0, 1e6, 0.3)], seconds=200)
    seconds, _ = compare.residuals(path, "lte", first_s=60.0)["lte:2460:1#0/pseudorange"]
    assert seconds[-1] < 60.0 and len(seconds) == 60


def test_table_shows_both_sessions_and_the_gap(sessions):
    text = compare.table(sessions["easy"], sessions["worst"], "lte")
    assert "| Statistic (lte) | Simulated | Real | Gap |" in text and "residual_std" in text


def test_figure_is_written(sessions, tmp_path):
    pytest.importorskip("matplotlib")
    out = compare.plot(sessions["easy"], sessions["worst"], "lte", tmp_path / "a" / "cmp.png")
    assert out.stat().st_size > 1000


def test_attacks_can_be_injected_into_a_recording(sessions):
    fault = [{"type": "spoof_jump", "source": "gnss", "start_s": 100, "offset_enu_m": [300, 0, 0]}]
    meas, t0, events = compare.inject(sessions["easy"], fault)
    assert t0 == T0_NS and events
    clean, _, _ = compare.inject(sessions["easy"], [])
    fixes = [(a, b) for a, b in zip(clean, meas, strict=True) if a.kind == "position_enu"]
    assert fixes
    for a, b in fixes:
        expected = 300.0 if a.t_ns >= t0 + 100_000_000_000 else 0.0
        assert b.value[0] - a.value[0] == pytest.approx(expected, abs=1e-6)


def test_injection_into_a_session_without_truth(tmp_path):
    path = _static_lte(tmp_path / "s.mcap", [("lte:2460:1", 0, 1e6, 0.0)], sigma_m=0.0)
    step = [{"type": "tower_clock_step", "source": "lte", "emitter": "lte:2460:1",
             "start_s": 30, "offset_m": 300.0}]  # fmt: skip
    meas, t0, _ = compare.inject(path, step)
    jump = [m.value[0] - 1e6 for m in meas]
    assert jump[:30] == pytest.approx([0.0] * 30) and jump[30:] == pytest.approx([300.0] * 90)
    replay = [{"type": "meaconing", "source": "gnss", "start_s": 10, "delay_s": 5}]
    compare.inject(path, replay)  # no GNSS fixes to replay: nothing asks for the truth


def test_a_fault_that_needs_the_true_position_says_so(tmp_path):
    path = tmp_path / "fixes.mcap"
    run = generate(load("easy-nominal"), seed=0)
    with SessionWriter(path, metadata={"origin_llh": run.spec["origin_llh"]}) as w:
        for m in run.measurements:
            if m.source == "gnss":
                w.write("/meas/gnss", m)
    replay = [{"type": "meaconing", "source": "gnss", "start_s": 10, "delay_s": 5}]
    with pytest.raises(ValueError, match="truth"):
        compare.inject(path, replay)


def test_replay_can_inject_a_named_scenarios_faults(sessions, capsys):
    main(["replay", str(sessions["easy"]), "--inject", "easy-spoof-jump"])
    out = capsys.readouterr().out
    assert "injected the faults of easy-spoof-jump" in out and "spoof jump of 300 m" in out
    line = next(ln for ln in out.splitlines() if "fault_h_p95_m" in ln)
    assert "nan" not in line


def test_replay_saves_the_injected_session(tmp_path, capsys):
    path = _static_lte(tmp_path / "s.mcap", [("lte:2460:1", 0, 1e6, 0.0)], sigma_m=0.0)
    faults = tmp_path / "step.yaml"
    faults.write_text(
        "faults:\n  - {type: tower_clock_step, source: lte, emitter: 'lte:2460:1', start_s: 30,"
        " offset_m: 300.0}\n"
    )
    out = tmp_path / "injected"
    main(["replay", str(path), "--inject", str(faults), "--out", str(out)])
    assert "lte:2460:1 clock steps by 300.0 m" in capsys.readouterr().out
    assert session.read_meta(out)["platform"] == "static"
    saved = [r.value[0] for _, r in read_session(session.mcap_path(out), topics=["/meas/"])]
    assert saved[29] == pytest.approx(1e6) and saved[30] == pytest.approx(1e6 + 300.0)
    with pytest.raises(SystemExit):  # never over an existing session
        main(["replay", str(path), "--inject", str(faults), "--out", str(out)])


def test_replay_out_needs_inject(sessions, tmp_path):
    with pytest.raises(SystemExit, match="--inject"):
        main(["replay", str(sessions["easy"]), "--out", str(tmp_path / "x")])


def test_compare_command_prints_the_table(sessions, capsys):
    main(["compare", str(sessions["easy"]), str(sessions["worst"]), "--source", "gnss"])
    assert "Statistic (gnss)" in capsys.readouterr().out


def test_a_scenario_can_replay_one_stream_from_a_recording(sessions):
    spec = copy.deepcopy(load("easy-nominal"))
    spec["replay_streams"] = {"session": str(sessions["easy2"]), "sources": ["baro"]}
    run = generate(spec, seed=9)
    recorded = generate(load("easy-nominal"), seed=2)
    assert [m for m in run.measurements if m.source == "baro"] == [
        m for m in recorded.measurements if m.source == "baro"
    ]
    other = generate(load("easy-nominal"), seed=9)
    lte = [m for m in run.measurements if m.source == "lte"]
    assert lte and len(lte) == len([m for m in other.measurements if m.source == "lte"])


def test_replayed_streams_are_shifted_to_the_scenario_clock(tmp_path):
    path = tmp_path / "later.mcap"
    run = generate(load("easy-nominal"), seed=0)
    shift = 5_000_000_000
    with SessionWriter(path, metadata={"origin_llh": run.spec["origin_llh"]}) as w:
        for m in run.measurements:
            if m.source == "baro":
                w.write("/meas/baro", msgspec.structs.replace(m, t_ns=m.t_ns + shift))
        w.write("/truth", Truth(t_ns=T0_NS, pos_enu=(0, 0, 0), vel_enu=(0, 0, 0)))
    spec = copy.deepcopy(load("easy-nominal"))
    spec["replay_streams"] = {"session": str(path), "sources": ["baro"]}
    times = [m.t_ns for m in generate(spec, seed=0).measurements if m.source == "baro"]
    assert np.min(times) == T0_NS


def test_replay_streams_needs_the_stream(sessions):
    spec = copy.deepcopy(load("easy-nominal"))
    spec["replay_streams"] = {"session": str(sessions["easy"]), "sources": ["vor"]}
    with pytest.raises(ValueError, match="none of the streams"):
        generate(spec, seed=0)
