"""LTE front end in a frame-synchronised network (#183): cells that share a PSS root.

Every cell in the 2026-11-10/11 captures arrives within a few µs of the others (the operators
synchronise their eNBs), so a cell's PSS, which only depends on N_ID2, is added to by every
other cell with the same N_ID2. Only the SSS is the cell's own. Synthetic captures
(`pnt.frontends.lte.synth`); the bounds are regression guards from these seeds, not
requirements.
"""

import numpy as np

from pnt.frontends.lte import capture, process_file, synth

FS, FC, PPM = 1.92e6, 875e6, 0.4
T0 = 1_446_000_000_000_000_000
DELAY = 1.234567e-3


def write(tmp, towers, dur, snr, seed=1):
    x = synth.synthesize(towers, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=snr, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    return capture.write_capture(tmp / "c.cu8", capture.complex_to_cu8(x), meta)


def test_carrier_offset_is_the_dongles_when_a_co_timed_cell_shares_the_pss_root(tmp_path):
    # Two cells 0.2 µs apart on one PSS root (PCI 8 and 2: N_ID2 2). The PSS the search sees is
    # their sum, so the SSS-to-PSS phase the search turns into a carrier offset is off by
    # ~2 kHz. Before #183 the loop trusted it and locked its carrier on a 200 Hz alias.
    towers = [
        synth.Tower(pci=8, delay_s=DELAY),
        synth.Tower(pci=2, delay_s=DELAY + 0.2e-6, power_db=-1.0, phase=2.0),
    ]
    r = process_file(write(tmp_path, towers, 1.0, 10.0))
    truth = -PPM * 1e-6 * FC  # -350 Hz: the dongle's 0.4 ppm, nothing else moves
    locked = [e for c in r.cells for e in c.epochs if e.locked]
    assert len(locked) > 50
    cfo = np.array([-e.nu * FC for e in locked])
    assert np.max(np.abs(cfo - truth)) < 20.0  # regression guard; an alias is 200 Hz off
    for m in r.measurements:
        if m.kind == "doppler":
            assert abs(m.meta["cfo_hz"] - truth) < 20.0
