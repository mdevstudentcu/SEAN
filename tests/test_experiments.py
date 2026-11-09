import pytest

from pnt.cli import main
from pnt.experiments import OSCILLATORS, grid, markdown, towers


def test_tower_removal_covers_each_tower_and_ranks_by_damage():
    rows = towers("ottawa-towers", runs=2)
    assert rows[0]["removed"] == "none" and rows[0]["added_m"] == 0.0
    assert len(rows) == 7
    added = [r["added_m"] for r in rows[1:]]
    assert added == sorted(added, reverse=True)


def test_losing_towers_hurts_on_average():
    rows = towers("ottawa-towers", runs=3)
    assert sum(r["added_m"] for r in rows[1:]) > 0  # regression guard, not a requirement


def test_tower_ranking_refuses_synthetic_towers():
    with pytest.raises(ValueError, match="synthetic"):
        towers("gps-outage", runs=1)


def test_grid_covers_every_combination():
    rows = grid("gps-outage", runs=1, tower_counts=(3, 6), speeds=(4.0,), oscillators=("ocxo",))
    assert [(r["towers"], r["oscillator"]) for r in rows] == [(3, "ocxo"), (6, "ocxo")]


def test_grid_responds_to_tower_count():
    # Regression guard: with towers actually used, 3 and 6 towers must not score the same
    assert set(OSCILLATORS) == {"tcxo", "ocxo"}
    rows = grid("ottawa-towers", runs=2, tower_counts=(3, 6), speeds=(8.0,), oscillators=("tcxo",))
    assert rows[0]["p95_m"] != rows[1]["p95_m"]
    assert all(r["p95_m"] == r["p95_m"] for r in rows)  # no NaN


def test_markdown_table_has_a_header_and_a_row_each():
    table = markdown([{"a": 1.0, "b": "x"}, {"a": 2.5, "b": "y"}])
    assert table.splitlines()[0] == "| a | b |" and len(table.splitlines()) == 4


def test_command_line_prints_a_table(capsys):
    main(["experiment", "towers", "ottawa-towers", "--runs", "1"])
    assert "| removed |" in capsys.readouterr().out
