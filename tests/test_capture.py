"""Board capture faults (issue #53): what a busy payload board does to the data."""

import copy

import numpy as np

from pnt.sim.scenario import T0_NS, generate, load

# Numeric limits in this file are regression guards, not requirements.


def _radio(run):
    return [m for m in run.measurements if m.source == "lte"]


def _faulted(name="easy-nominal", **values):
    spec = copy.deepcopy(load(name))
    base = {"gaps_per_min": 0.0, "gap_s": 1.0, "timestamp_jitter_ms": 0.0, "stream_loss": 0.0}
    spec["faults"] = [{"type": "capture_faults", "board": "test", **base, **values}]
    return spec


def test_the_pi4b_profile_is_on_the_shared_menu():
    (fault,) = load("realistic-capture-pi4b")["faults"]
    assert fault["type"] == "capture_faults" and fault["board"] == "pi4b"


def test_no_faults_means_unchanged_data():
    clean = generate(load("easy-nominal"), seed=2)
    assert generate(_faulted(), seed=2).measurements == clean.measurements


def test_gaps_remove_radio_data_only():
    clean = generate(load("easy-nominal"), seed=2)
    run = generate(_faulted(gaps_per_min=5.0, gap_s=3.0), seed=2)
    assert len(_radio(run)) < len(_radio(clean))
    for source in ("gnss", "baro"):
        kept = [m for m in run.measurements if m.source == source]
        assert kept == [m for m in clean.measurements if m.source == source]


def test_jitter_moves_radio_timestamps_at_the_requested_size():
    clean = _radio(generate(load("easy-nominal"), seed=2))
    run = _radio(generate(_faulted(timestamp_jitter_ms=5.0), seed=2))
    assert len(clean) == len(run)
    assert sorted(m.t_ns for m in clean) != sorted(m.t_ns for m in run)
    t = np.array([m.t_ns for m in run]) - T0_NS  # LTE records sit on whole seconds in `easy`
    offsets = (t + 500_000_000) % 1_000_000_000 - 500_000_000
    assert 0.003 < np.std(offsets) / 1e9 < 0.007


def test_stream_loss_drops_a_share_of_every_source():
    clean = generate(load("easy-nominal"), seed=2)
    run = generate(_faulted(stream_loss=0.2), seed=2)
    assert 0.75 < len(run.measurements) / len(clean.measurements) < 0.85
    for source in ("gnss", "baro", "lte"):
        assert any(m.source == source for m in run.measurements)


def test_the_reference_station_is_another_board_and_keeps_its_records():
    clean = generate(load("realistic-with-base-nominal"), seed=3)
    run = generate(_faulted("realistic-with-base-nominal", gaps_per_min=5.0, stream_loss=0.2), 3)

    def ref(r):
        return [m for m in r.measurements if m.receiver == "reference"]

    assert ref(clean) and ref(run) == ref(clean)
    assert len(run.measurements) < len(clean.measurements)


def test_measurements_stay_in_time_order():
    run = generate(load("realistic-capture-pi4b"), seed=1)
    times = [m.t_ns for m in run.measurements]
    assert times == sorted(times)
