"""`analysis/antenna_ab_table.py` (#200). Synthetic inputs only; the sessions are not in git."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_PATH = Path(__file__).parents[1] / "analysis" / "antenna_ab_table.py"
_spec = importlib.util.spec_from_file_location("antenna_ab_table", _PATH)
ab = importlib.util.module_from_spec(_spec)
sys.modules["antenna_ab_table"] = ab
_spec.loader.exec_module(ab)


def _cell(pci, snr, tracked, arcs=1):
    return {"pci": pci, "earfcn": 2460, "snr_db": snr, "tracked_s": tracked, "arcs": arcs}


def _run(lbl, cells):
    return {"label": lbl, "session": f"x-static-ant-{lbl}-y", "capture_s": 90.0,
            "gain_mode": "auto", "gain_db": None, "rms_lsb": 30.0, "clip_frac": 0.0,
            "cells": cells}  # fmt: skip


def test_label_is_the_token_after_ant():
    assert ab.label("20261110-2338-static-ant-A2-uhf-chair") == "A2"
    assert ab.label("20261110-2341-static-ant-A0b-uhf-ground-chairspot") == "A0b"
    assert ab.label("no-label-here") == "no-label-here"


def test_floor_is_the_tracker_threshold_on_the_per_re_scale():
    # 8 dB post-correlation over 2 x 62 PSS/SSS samples
    assert ab.detection_floor_db() == pytest.approx(8.0 - 10 * np.log10(124))


def test_per_run_counts_tracked_cells_and_marks_a_marginal_best():
    floor = -12.9
    r = _run("A1", [_cell(204, -11.6, 43.5, 27), _cell(220, -10.4, 12.2, 21), _cell(9, 3.0, 0.0)])
    s = ab.per_run(r, floor)
    assert (s["cells"], s["above_floor"], s["arcs"]) == (2, 0, 48)
    assert s["tracked_s"] == pytest.approx(55.7)
    assert s["best_snr_db"] == -10.4 and s["best_is_floor"]
    s = ab.per_run(_run("C", [_cell(204, 6.1, 75.3, 14)]), floor)
    assert s["above_floor"] == 1 and not s["best_is_floor"]


def test_compare_uses_only_cells_both_runs_tracked():
    a = _run("A2", [_cell(244, -11.2, 38.9, 41)])
    b = _run("A0b", [_cell(204, 14.1, 84.4, 2), _cell(244, -11.0, 10.0, 5)])
    d = ab.compare(a, b)
    assert [x["pci"] for x in d] == [244]
    assert d[0]["d_snr_db"] == pytest.approx(0.2)
    assert d[0]["d_tracked_s"] == pytest.approx(-28.9)
    assert ab.compare(_run("B", [_cell(220, 5.1, 27.3)]), b) == []


def test_table_lists_every_run_and_says_when_a_pair_has_no_cell_in_common():
    runs = [_run("A2", [_cell(244, -11.2, 38.9, 41)]), _run("A0b", [_cell(204, 14.1, 84.4, 2)])]
    md = ab.table_md(runs, [("A2", "A0b")], -12.9, "abc1234")
    assert "abc1234" in md and "| A2 |" in md and "| A0b |" in md
    assert "-11.2 floor / 38.9 / 41" in md and "14.1 / 84.4 / 2" in md
    assert "A2 -> A0b | no cell in common" in md


def test_level_counts_clipped_values_and_rms(tmp_path):
    raw = np.array([0, 255, 127, 128] * 1000, dtype=np.uint8)
    f = tmp_path / "x.cu8"
    f.write_bytes(raw.tobytes())
    lv = ab.level(f, chunk=1000)  # several chunks
    assert lv["clip_frac"] == pytest.approx(0.5)
    expect = np.sqrt(np.mean((raw.astype(float) - 127.5) ** 2))
    assert lv["rms_lsb"] == pytest.approx(expect)


def test_plot_writes_a_png(tmp_path):
    runs = [_run("A2", [_cell(244, -11.2, 38.9, 41)]), _run("A0b", [_cell(204, 14.1, 84.4, 2)])]
    ab.plot(runs, -12.9, "abc1234", tmp_path / "p.png")
    assert (tmp_path / "p.png").read_bytes()[:4] == b"\x89PNG"
