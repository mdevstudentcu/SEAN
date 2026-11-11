"""The simulated GPS sky and the fake-sky fault (#206, ADR-0041, REQ-04): software fault
injection only, never a transmit path (ADR-0001)."""

import copy

import msgspec
import pytest

from pnt.integrity import sky
from pnt.sim.scenario import T0_NS, generate, load

# --- the sim's sky and the fake-sky fault -------------------------------------------------


def _skyviews(run):
    return [m for m in run.measurements if m.kind == "gnss_health" and m.meta.get("snr")]


def _without_sky_fault(name="spoof-jump-sky"):
    spec = copy.deepcopy(load(name))
    spec["faults"] = [f for f in spec["faults"] if f["type"] != "fake_sky"]
    return spec


def test_sim_sky_passes_and_draws_from_its_own_stream():
    spec = _without_sky_fault()
    run = generate(spec, seed=3)
    views = _skyviews(run)
    assert len(views) == spec["duration_s"] / 5  # one every 5 s
    d = sky.SpoofDecision()
    levels = []
    for m in views:
        d.measurement(m, spec["origin_llh"])
        levels.append(d.decide(m.t_ns).level)
    assert set(levels) == {"not_spoofed"}
    # The sky leaves every other draw alone
    bare = copy.deepcopy(spec)
    del bare["sources"]["gnss"]["sky"]
    plain = generate(bare, seed=3)

    def strip(ms):
        return [msgspec.structs.replace(m, meta={}) if m.kind == "gnss_health" else m for m in ms]

    assert strip(run.measurements) == strip(plain.measurements)


def test_fake_sky_is_caught_on_the_sim():
    spec = _without_sky_fault()
    spec["faults"].append(
        {"type": "fake_sky", "start_s": 150, "flat_cn0_dbhz": 45, "below_horizon": 2}
    )
    run = generate(spec, seed=0)
    d = sky.SpoofDecision()
    first_spoofed = None
    for m in _skyviews(run):
        c = d.measurement(m, spec["origin_llh"])
        t = (m.t_ns - T0_NS) / 1e9
        level = d.decide(m.t_ns).level
        if t < 150:
            assert level == "not_spoofed"
        else:
            assert len(c.below) == 2 and c.flat
            if level == "spoofed" and first_spoofed is None:
                first_spoofed = t
    assert first_spoofed == 155.0  # held on the second skyview after the onset


def test_fake_sky_needs_something_to_fake():
    spec = _without_sky_fault()
    spec["faults"].append({"type": "fake_sky", "start_s": 150})
    with pytest.raises(ValueError, match="fake_sky needs"):
        generate(spec, seed=0)


def test_sky_needs_health_records():
    spec = _without_sky_fault()
    del spec["sources"]["gnss"]["health"]
    with pytest.raises(ValueError, match="health: true"):
        generate(spec, seed=0)
