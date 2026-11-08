import numpy as np

from pnt.sim.scenario import generate, load, load_ray_table

# Numeric limits in this file are regression guards, not requirements.


def _towers(name, seed=3):
    run = generate(load(name), seed=seed)
    return {(m.emitter, m.t_ns): m for m in run.measurements if m.kind == "pseudorange"}


def test_table_covers_every_tower_along_the_route():
    table = load_ray_table("sionna-campus-route.csv")
    assert sorted(table) == list(range(6))
    assert all(len(t) == 72 and t[0] == 0.0 for t, _ in table.values())


def test_blocked_towers_are_lost_for_part_of_the_route():
    assert len(_towers("ottawa-sionna")) < len(_towers("ottawa-towers"))


def test_measurements_kept_are_never_earlier_than_the_true_range():
    plain, traced = _towers("ottawa-towers"), _towers("ottawa-sionna")
    extra = [traced[k].value[0] - plain[k].value[0] for k in traced]
    assert min(extra) >= -1e-6 and max(extra) <= 300.0 + 1e-6
    assert max(extra) > 0.5


def test_excess_delay_stays_within_the_limit_in_the_table():
    for _, excess in load_ray_table("sionna-campus-route.csv").values():
        assert np.nanmin(excess) >= 0.0
