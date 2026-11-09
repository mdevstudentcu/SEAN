"""Estimators see only the receivers they model (ICD-measurement, ADR-0020)."""

import logging

import msgspec
import pytest

from pnt.cli import main
from pnt.core.measurement import RECEIVERS
from pnt.io import session
from pnt.io.mcap_log import SessionWriter
from pnt.nav import ESTIMATORS, baseline, estimate, receivers
from pnt.sim.scenario import generate, load
from pnt.sources.replay import ReplaySource


def _reference_copies(measurements):
    """A reference record next to every LTE pseudorange, 30 m off: inside the innovation gate, so
    a leak moves the fix (a 1 km offset is gated out and hides it from the replay metrics)."""
    return [
        msgspec.structs.replace(m, receiver="reference", value=(m.value[0] + 30.0,))
        for m in measurements
        if m.source == "lte" and m.kind == "pseudorange"
    ]


def _write(path, run, extra=()):
    meas = sorted([*run.measurements, *extra], key=lambda m: m.t_ns)  # stable: payload first
    with SessionWriter(path) as w:
        for t in run.truth:
            w.write("/truth", t)
        for m in meas:
            w.write(f"/meas/{m.source}", m)
    return path


# Every estimator that models the payload only (ekf-base models both, tests/test_base_rover.py)
PAYLOAD_ONLY = sorted(n for n, fn in ESTIMATORS.items() if receivers(fn) == {"payload"})


@pytest.mark.parametrize("name", PAYLOAD_ONLY)
def test_reference_records_do_not_change_any_estimate(tmp_path, caplog, name):
    spec = load("gps-outage")
    run = generate(spec, seed=0)
    ref = _reference_copies(run.measurements)
    mixed = _write(tmp_path / "mixed.mcap", run, ref)
    clean = _write(tmp_path / "clean.mcap", run)
    origin = spec["origin_llh"]
    with caplog.at_level(logging.WARNING, logger="pnt.nav"):
        got = list(estimate(name, ReplaySource(mixed), origin_llh=origin))
    assert f"dropped {len(ref)} reference records" in caplog.text
    assert got == list(estimate(name, ReplaySource(clean), origin_llh=origin))


def test_replay_of_a_mixed_session_matches_the_clean_one(tmp_path, capsys):
    spec = load("gps-outage")
    run = generate(spec, seed=0)
    meta = {"scenario": "gps-outage", "origin_llh": spec["origin_llh"]}
    for folder, extra in (("mixed", _reference_copies(run.measurements)), ("clean", ())):
        (tmp_path / folder).mkdir()
        session.write_meta(tmp_path / folder, {"name": folder, **meta})
        _write(tmp_path / folder / session.MCAP_NAME, run, extra)
    outputs = []
    for folder in ("mixed", "clean"):
        main(["replay", str(tmp_path / folder)])
        outputs.append(capsys.readouterr().out.replace(str(tmp_path / folder), "<s>"))
    assert outputs[0] == outputs[1]


def test_an_estimator_that_opts_in_sees_both_receivers():
    run = generate(load("gps-outage"), seed=0)
    meas = sorted([*run.measurements, *_reference_copies(run.measurements)], key=lambda m: m.t_ns)
    seen = {}

    def payload_only(ms, origin_llh=None):
        seen["default"] = {m.receiver for m in ms}
        return iter(())

    def base_rover(ms, origin_llh=None):
        seen["opted_in"] = {m.receiver for m in ms}
        return iter(())

    base_rover.receivers = RECEIVERS
    list(estimate(payload_only, meas))
    list(estimate(base_rover, meas))
    assert seen == {"default": {"payload"}, "opted_in": {"payload", "reference"}}


def test_payload_only_sessions_run_exactly_as_before(caplog):
    spec = load("gps-outage")
    run = generate(spec, seed=0)
    with caplog.at_level(logging.WARNING, logger="pnt.nav"):
        got = list(estimate("baseline", run.measurements, origin_llh=spec["origin_llh"]))
    assert got == list(baseline.run(run.measurements, origin_llh=spec["origin_llh"]))
    assert caplog.text == ""  # nothing dropped, nothing logged
