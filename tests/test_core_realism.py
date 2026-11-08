import copy

import numpy as np
import pytest

from pnt.core.frames import emitter_enu
from pnt.sim import models
from pnt.sim.scenario import T0_NS, generate, load

ORIGIN = [45.3876, -75.6960, 70.0]
# Numeric limits in this file are regression guards, not requirements.


def _spec(**lte):
    spec = copy.deepcopy(load("gps-outage"))
    spec["clock"] = {"drift_ppb": 50, "rw_ns": 2.0}
    spec["sources"]["lte"].update(lte)
    return spec


def _ranges(run):
    return {(m.emitter, m.t_ns): m for m in run.measurements if m.kind == "pseudorange"}


def test_receiver_clock_moves_every_tower_together():
    without = _ranges(generate(_spec(), seed=1))
    run = generate(_spec(receiver_clock=True), seed=1)
    with_clock = _ranges(run)
    clock = {t.t_ns: t.clock_bias_s for t in run.truth}
    assert with_clock.keys() == without.keys()
    shifts = {}
    for key, m in with_clock.items():
        shift = m.value[0] - without[key].value[0]
        shifts.setdefault(key[1], []).append(shift)
        assert shift == pytest.approx(models.C_MPS * clock[key[1]], abs=1e-3)
    assert all(np.ptp(s) < 1e-6 for s in shifts.values())
    assert max(abs(s[0]) for s in shifts.values()) > 1.0


def test_one_tower_clock_change_moves_only_that_tower():
    spec = _spec()
    base = _ranges(generate(spec, seed=1))
    stepped = copy.deepcopy(spec)
    stepped["faults"] = spec["faults"] + [
        {
            "type": "tower_clock_step",
            "source": "lte",
            "emitter": "lte:sim2",
            "offset_m": 300.0,
            "start_s": 100.0,
        }
    ]
    changed = _ranges(generate(stepped, seed=1))
    start = T0_NS + 100_000_000_000
    for key, m in changed.items():
        expected = 300.0 if key[0] == "lte:sim2" and key[1] >= start else 0.0
        assert m.value[0] - base[key].value[0] == pytest.approx(expected, abs=1e-6)


def test_settings_left_off_change_nothing():
    base = generate(load("gps-outage"), seed=4).measurements
    spec = copy.deepcopy(load("gps-outage"))
    spec["sources"]["lte"].update(
        drift_sigma_mps=0.0, told_position_sigma_m=0.0, receiver_clock=False
    )
    assert generate(spec, seed=4).measurements == base


def test_receiver_clock_needs_a_clock_model():
    spec = copy.deepcopy(load("gps-outage"))
    spec["sources"]["lte"]["receiver_clock"] = True
    with pytest.raises(ValueError, match="clock"):
        generate(spec, seed=0)


def test_lingering_error_has_the_requested_size_and_memory():
    rng = np.random.default_rng(0)
    x = models._gauss_markov(rng, np.ones(200_000), sigma=30.0, tau_s=30.0)
    assert np.std(x) == pytest.approx(30.0, rel=0.05)
    assert np.corrcoef(x[:-1], x[1:])[0, 1] == pytest.approx(np.exp(-1 / 30), abs=0.01)


def test_tower_drift_grows_with_time():
    a = _ranges(generate(_spec(), seed=2))
    b = _ranges(generate(_spec(drift_sigma_mps=5.0), seed=2))
    assert a.keys() == b.keys()
    late = [k for k in a if k[1] > T0_NS + 300_000_000_000]
    assert any(abs(b[k].value[0] - a[k].value[0]) > 50 for k in late)


def test_dropouts_remove_whole_blocks_at_the_requested_rate():
    t = np.arange(0.0, 300_000.0)
    keep = models._available(np.random.default_rng(0), t, {"availability": 0.7, "block_s": 30.0})
    assert keep.mean() == pytest.approx(0.7, abs=0.02)
    for block in (0, 1, 7):
        assert len(set(keep[(t // 30).astype(int) == block])) == 1


def test_dropouts_make_towers_disappear_and_return():
    run = generate(_spec(dropout={"availability": 0.5, "block_s": 30.0}), seed=3)
    full = generate(_spec(), seed=3)
    assert len(_ranges(run)) < len(_ranges(full))
    per_tower = {}
    for emitter, t in _ranges(run):
        per_tower.setdefault(emitter, []).append(t)
    assert any(np.max(np.diff(sorted(t))) > 20_000_000_000 for t in per_tower.values())


def test_filter_is_told_wrong_tower_positions_while_truth_is_kept():
    run = generate(_spec(told_position_sigma_m=200.0), seed=5)
    m = next(iter(_ranges(run).values()))
    told = emitter_enu(m.meta, ORIGIN)
    assert 1.0 < np.linalg.norm(told - np.array(run.emitters[m.emitter])) < 2000.0


def test_told_positions_work_for_towers_given_in_lat_lon():
    towers = [[45.40, -75.70, 100.0], [45.38, -75.66, 90.0], [45.36, -75.72, 80.0]]
    spec = _spec(told_position_sigma_m=200.0, emitters_llh=towers)
    run = generate(spec, seed=5)
    m = next(iter(_ranges(run).values()))
    assert "emitter_llh" in m.meta
    told = emitter_enu(m.meta, spec["origin_llh"])
    assert 1.0 < np.linalg.norm(told - np.array(run.emitters[m.emitter])) < 2000.0


def test_filter_can_be_told_the_wrong_noise_level():
    run = generate(_spec(told_sigma_m=7.0), seed=0)
    assert all(m.sigma == (7.0,) for m in _ranges(run).values())
