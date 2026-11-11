"""LTE front end in a frame-synchronised network (#183): cells that share a PSS root.

Every cell in the 2026-11-10/11 captures arrives within a few µs of the others (the operators
synchronise their eNBs), so a cell's PSS, which only depends on N_ID2, is added to by every
other cell with the same N_ID2. Only the SSS is the cell's own. Synthetic captures
(`pnt.frontends.lte.synth`); the bounds are regression guards from these seeds, not
requirements.
"""

import numpy as np
import pytest

from pnt.frontends.lte import capture, process_file, synth
from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.tracker import Config

FS, FC, PPM = 1.92e6, 875e6, 0.4
T0 = 1_446_000_000_000_000_000
DELAY = 1.234567e-3


def write(tmp, towers, dur, snr, seed=1):
    x = synth.synthesize(towers, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=snr, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    return capture.write_capture(tmp / "c.cu8", capture.complex_to_cu8(x), meta)


def epoch_errors_m(result, tower):
    """Tracked frame boundary minus truth (m) for every epoch of `tower`'s cell."""
    L = sig.half_frame_length(FS)
    b0 = tower.boundary_sample(0, FS, PPM)
    out = []
    for cell in result.cells:
        if cell.pci == tower.pci:
            for e in cell.epochs:
                c = cell.n0 + e.k * L + e.theta_meas
                out.append(c - tower.boundary_sample(round((c - b0) / L) / 2, FS, PPM))
    return np.array(out) * synth.C / FS


def test_carrier_offset_is_the_dongles_when_a_co_timed_cell_shares_the_pss_root(tmp_path):
    # Two cells 0.2 µs apart on one PSS root (PCI 8 and 2: N_ID2 2). The PSS the search sees is
    # their sum, so the SSS-to-PSS phase the search turns into a carrier offset is off by
    # ~2 kHz. Before #183 the loop trusted it and locked its carrier on a 200 Hz alias.
    towers = [
        synth.Tower(pci=8, delay_s=DELAY),
        synth.Tower(pci=2, delay_s=DELAY + 0.2e-6, power_db=-1.0, phase=2.0),
    ]
    r = process_file(write(tmp_path, towers, 1.0, 10.0), Config(doppler=True))
    truth = -PPM * 1e-6 * FC  # -350 Hz: the dongle's 0.4 ppm, nothing else moves
    locked = [e for c in r.cells for e in c.epochs if e.locked]
    assert len(locked) > 50
    cfo = np.array([-e.nu * FC for e in locked])
    assert np.max(np.abs(cfo - truth)) < 20.0  # regression guard; an alias is 200 Hz off
    for m in r.measurements:
        if m.kind == "doppler":
            assert abs(m.meta["cfo_hz"] - truth) < 20.0


@pytest.mark.parametrize("appears_s", [0.0, 0.6], ids=["from the start", "after 0.6 s"])
def test_cell_3_us_behind_one_on_its_pss_root_keeps_its_own_timing_and_arc(tmp_path, appears_s):
    # PCI 268 sits 3.2 µs (6 samples) behind PCI 244, both N_ID2 1, 4 dB down: as on the
    # 20261110-1305 capture. 244's PSS in 268's delay window looked like an earlier path of
    # 268, so before #183 the first-path check moved 268 onto 244: 960 m early here, and a new
    # arc when 244 shows up after 268 has settled (in the real capture 268 never settled and
    # was tracked 0 s).
    strong = synth.Tower(pci=244, delay_s=DELAY)
    weak = synth.Tower(pci=268, delay_s=DELAY + 3.2e-6, power_db=-4.0, phase=1.0)
    x = synth.synthesize([strong, weak], 2.0, fs=FS, fc=FC, clock_ppm=PPM, snr_db=15.0, seed=1)
    if appears_s:  # 268 alone first, same noise and clock
        alone = synth.synthesize([weak], 2.0, fs=FS, fc=FC, clock_ppm=PPM, snr_db=15.0, seed=1)
        at = round(appears_s * FS)
        x = np.r_[alone[:at], x[at:]]
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    r = process_file(capture.write_capture(tmp_path / "c.cu8", capture.complex_to_cu8(x), meta))
    err = epoch_errors_m(r, weak)
    assert err.size > 200  # > 1 s of 5 ms epochs
    assert np.max(np.abs(err)) < 150  # regression guard: on its own path, not 960 m off
    assert [c.arc for c in r.cells if c.pci == 268] == [0]


def test_faded_cell_does_not_walk_onto_its_neighbours_sync_signals(tmp_path):
    # A tracked cell fades 12 dB below two co-timed neighbours on other PSS roots. Their PSS and
    # SSS correlate with its sequences at every delay, a floor the reserved-bin noise does not
    # see and averaging does not lower. Before the fix the first-path check took bumps of that
    # floor for earlier paths: the track moved 4 to 6 samples earlier every 200 ms, each move a
    # new arc, 2 km off within 1.5 s. On the real static captures 20261111-0151 and -0233 this
    # was 87 to 93 % of the new arcs, and the ~700 m "re-acquisition" steps of #214.
    cell = synth.Tower(pci=8, delay_s=DELAY)
    others = [
        synth.Tower(pci=13, delay_s=DELAY + 1.1e-6, phase=1.0),
        synth.Tower(pci=30, delay_s=DELAY - 0.7e-6, power_db=-3.0, phase=2.0),
    ]
    faded = synth.Tower(pci=8, delay_s=DELAY, power_db=-12.0)
    kw = {"fs": FS, "fc": FC, "clock_ppm": PPM, "snr_db": 20.0, "seed": 1}
    x = synth.synthesize([cell, *others], 2.0, **kw)
    y = synth.synthesize([faded, *others], 2.0, **kw)
    at = round(0.6 * FS)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    z = capture.complex_to_cu8(np.r_[x[:at], y[at:]])
    r = process_file(capture.write_capture(tmp_path / "c.cu8", z, meta))
    err = epoch_errors_m(r, cell)
    assert err.size > 300  # tracked through the fade
    assert np.max(np.abs(err)) < 100  # regression guard: 30 m seen; the walk reached 2 km
    assert [c.arc for c in r.cells if c.pci == 8] == [0]
