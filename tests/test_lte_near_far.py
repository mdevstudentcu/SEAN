"""LTE front end next to a strong cell (#131): coherent search and weak-cell tracking.

Synthetic captures only (`pnt.frontends.lte.synth`: every data resource element filled, the
worst case for interference). The levels and bounds are regression guards from what these seeds
showed, with margin; none is a requirement or a claim about real towers (#21).
"""

import numpy as np
import pytest

from pnt.frontends.lte import Config, capture, process_file, synth, tracker
from pnt.frontends.lte import signals as sig

FS, FC, PPM = 1.92e6, 875e6, 0.4
T0 = 1_446_000_000_000_000_000
STRONG = synth.Tower(pci=8, delay_s=1.2345e-3)  # N_ID2 2
COHERENT = Config(acq_coherent=15, track_coherent=8)  # 80 ms search, 40 ms tracking blocks
SNR_DB = 30.0  # the strong cell over thermal noise


def weak(pci: int, rel_db: float) -> synth.Tower:
    return synth.Tower(pci=pci, delay_s=6.789e-3, power_db=rel_db, phase=1.0)


def samples(towers, dur, seed=3):
    x = synth.synthesize(towers, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=SNR_DB, seed=seed)
    return capture.cu8_to_complex(capture.complex_to_cu8(x))


def write(tmp, towers, dur, seed=3):
    x = synth.synthesize(towers, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=SNR_DB, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    return capture.write_capture(tmp / "c.cu8", capture.complex_to_cu8(x), meta)


def boundary_error(found, tower) -> float:
    """Found subframe-0 boundary minus truth, samples, wrapped to one frame."""
    frame = 2 * sig.half_frame_length(FS)
    return (found.boundary - tower.boundary_sample(0, FS, PPM) + frame / 2) % frame - frame / 2


def epoch_errors(result, tower):
    """Tracked frame boundary minus truth, samples, for every epoch of `tower`'s cell."""
    L = sig.half_frame_length(FS)
    b0 = tower.boundary_sample(0, FS, PPM)
    out = []
    for cell in result.cells:
        if cell.pci == tower.pci:
            for e in cell.epochs:
                c = cell.n0 + e.k * L + e.theta_meas
                out.append(c - tower.boundary_sample(round((c - b0) / L) / 2, FS, PPM))
    return np.array(out)


@pytest.mark.parametrize("pci", [11, 9], ids=["same root", "other root"])
def test_coherent_search_finds_a_cell_13_db_below_a_fully_loaded_one(pci):
    towers = [STRONG, weak(pci, -13.0)]
    x = samples(towers, 0.085)
    n = int(80e-3 * FS)
    default = tracker.search(x[:n], 0, FS, FC, Config())
    found = tracker.search(x[:n], 0, FS, FC, COHERENT)
    assert [f.pci for f in default] == [8]  # the known limit of the non-coherent search (#131)
    by_pci = {f.pci: f for f in found}
    assert set(by_pci) == {8, pci}  # and no ghost
    for t in towers:
        assert abs(boundary_error(by_pci[t.pci], t)) < 1.0


# Observed floor, a regression guard and not a target. Ladder (analysis/lte_link_dense.py
# --parts ladder, 3 seeds, 80 ms coherent search, 40 ms blocks): found and tracked 3/3 down to
# -14 dB on the same root and -13 dB on the other (2/3 at -14), against -11 dB for both before.
# Here, seeds 0-4 at -14 dB: same root tracked on seeds 1-4, other root on seeds 0-2; worst
# epoch error 0.24 sample. The synthesiser repeats its data every 80 ms, so a seed whose
# interference happens to hide the weak cell's SSS hides it in every search window.
@pytest.mark.parametrize(("pci", "at_least"), [(11, 3), (9, 2)], ids=["same root", "other root"])
def test_weak_cell_is_tracked_in_coherent_blocks_on_its_own_timing(tmp_path, pci, at_least):
    tw = weak(pci, -14.0)
    tracked = 0
    for seed in range(5):
        path = write(tmp_path, [STRONG, tw], 1.0, seed=seed)
        if seed == 1:
            assert [c.pci for c in process_file(path).cells] == [8]  # lost before (#131)
        r = process_file(path, COHERENT)
        assert {c.pci for c in r.cells} <= {8, pci}  # no ghost
        err = epoch_errors(r, tw)
        if err.size == 0:
            continue
        tracked += 1
        assert err.size >= 10  # one epoch per 40 ms block
        assert np.max(np.abs(err)) < 1.0  # on its own timing: no wrong-timing epoch
        pr = [m for m in r.measurements if m.kind == "pseudorange" and m.meta["pci"] == pci]
        assert len(pr) >= 4
        assert not any(m.kind == "doppler" and m.meta["pci"] == pci for m in r.measurements)
        # The strong cell keeps the single-epoch loop, with carrier aiding and doppler.
        assert any(m.kind == "doppler" and m.meta["pci"] == 8 for m in r.measurements)
    assert tracked >= at_least


def test_no_ghost_with_coherent_settings_on_noise_or_a_lone_strong_cell(tmp_path):
    noise = write(tmp_path, [], 0.5)
    assert process_file(noise, COHERENT).cells == []
    lone = write(tmp_path, [STRONG], 1.0)
    r = process_file(lone, COHERENT)
    assert [c.pci for c in r.cells] == [8]
    assert np.max(np.abs(epoch_errors(r, STRONG))) < 1.0
