"""The phase and frequency maths of analysis/lte_carrier_phase.py (#277), on synthetic IQ and
seeded series. No hardware, no session data. Tolerances are regression guards on estimators of
known quantities, not requirements.
"""

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from pnt.frontends.lte import capture, synth

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lte_carrier_phase", REPO / "analysis" / "lte_carrier_phase.py"
)
cp = importlib.util.module_from_spec(spec)
sys.modules["lte_carrier_phase"] = cp
spec.loader.exec_module(cp)

FS, FC, PPM = 1.92e6, 875e6, 0.4  # a 350 Hz carrier offset
T0 = 1_446_000_000_000_000_000


def _capture(tmp, towers, dur=3.0, snr=10.0, delta=0.0, seed=1):
    """A written capture; with `delta`, the first tower's second half-frame (subframes 5 to 9)
    is turned by `delta` rad, as an eNB sending them through another antenna would."""
    x = synth.synthesize(towers, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=snr, seed=seed)
    if delta:
        t0 = towers[0]
        n = np.arange(x.size)
        f = 0
        while (b := t0.boundary_sample(f, FS, PPM)) < x.size:
            mid = t0.boundary_sample(f + 0.5, FS, PPM)
            end = t0.boundary_sample(f + 1, FS, PPM)
            sel = (n >= mid) & (n < end)
            x[sel] *= np.complex64(np.exp(1j * delta))
            f += 1
            assert b < end
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    return capture.write_capture(tmp / "sdr_a.cu8", capture.complex_to_cu8(x), meta)


def _cells(path):
    data = cp.collect(path)
    m = data["meta"]
    out = {}
    for pci in np.unique(data["pci"]):
        c = cp.analyse_cell(data, np.flatnonzero(data["pci"] == pci), FS, m["L"], FC)
        out[int(pci)] = c
    cp.align_aliases(out)
    for c in out.values():
        cp.finish_cell(c)
    return out


def _freqs(c):
    """1 s carrier frequency per window, the mean of the two streams."""
    rows = {}
    for st in c["streams"]:
        for w, hz, _ in zip(*cp.window_freq(st["t"], st["u"], st["lab"]), strict=True):
            rows.setdefault(int(w), []).append(hz)
    return {w: float(np.mean(v)) for w, v in rows.items()}


def _truth_hz(tower):
    return -FC * tower.range_rate_dimless(PPM)


def test_carrier_frequency_and_phase_noise_of_one_tower(tmp_path):
    tower = synth.Tower(pci=92, delay_s=3e-6)
    c = _cells(_capture(tmp_path, [tower]))[92]
    f = _freqs(c)
    assert len(f) >= 2
    for hz in f.values():
        assert abs(hz - _truth_hz(tower)) < 0.05
    snr = float(np.median(c["snr"]))
    bound = 1 / math.sqrt(2 * cp.N_SSS * snr)
    for st in c["streams"]:
        dd, _ = cp.second_diff(st["e"] // 2, st["u"], st["lab"], 1)
        assert cp.robust_s(dd) < 1.4 * bound
        assert st["slips"] == 0
    # the code rate gives the same clock within a few Hz
    assert np.all(np.abs(c["car_minus_code_hz"]) < 5.0)


def test_subframe_phase_offset_is_measured_and_does_not_alias(tmp_path):
    """Subframes 0 and 5 arriving 2.5 rad apart: the 5 ms series would fit a 100 Hz alias as
    well; the two 10 ms streams keep the frequency and δ comes out as sent."""
    tower = synth.Tower(pci=92, delay_s=3e-6)
    c = _cells(_capture(tmp_path, [tower], delta=2.5))[92]
    for hz in _freqs(c).values():
        assert abs(hz - _truth_hz(tower)) < 0.05
    assert abs(cp.wrap(c["delta"]["mean_rad"] - 2.5)) < 0.1


def test_two_towers_frequency_difference(tmp_path):
    """A tower moving 2 ppb against another reads 2 ppb (1.75 Hz) apart; the dongle cancels."""
    a = synth.Tower(pci=92, delay_s=3e-6)
    b = synth.Tower(pci=204, delay_s=7e-6, delay_rate=2e-9, power_db=-3.0)
    cells = _cells(_capture(tmp_path, [a, b]))
    fa, fb = _freqs(cells[92]), _freqs(cells[204])
    common = sorted(set(fa) & set(fb))
    assert common
    want = _truth_hz(b) - _truth_hz(a)
    for w in common:
        assert abs((fb[w] - fa[w]) - want) < 0.05


def test_unwrap_follows_a_drifting_dongle_from_a_seed_40_hz_off():
    rng = np.random.default_rng(0)
    t = np.arange(3000) * 0.01  # 30 s of one 10 ms stream
    f = -200.0 - 2.5 * t  # the dongle warming up: 75 Hz in 30 s, more than one alias
    truth = 2 * np.pi * np.cumsum(np.r_[0.0, f[:-1] * 0.01]) + 1.0
    phi = cp.wrap(truth + rng.normal(0, 0.1, t.size))
    u, fr = cp.track_unwrap(t, phi, f_init=-160.0)
    err = u - truth
    settled = slice(100, None)
    assert np.ptp(np.rint((err[settled] - err[-1]) / (2 * np.pi))) == 0  # no slip
    assert abs(fr[-1] - f[-1]) < 1.0


@pytest.mark.parametrize("step", [0.0, 2 * np.pi, -4 * np.pi])
def test_slip_detector_finds_whole_cycles_only_where_they_are(step):
    rng = np.random.default_rng(1)
    u = 0.3 * np.arange(2000) * 0.01 + rng.normal(0, 0.15, 2000)  # a slope and white noise
    u[1200:] += step
    pos, size = cp.slips(u, np.zeros(u.size, np.int64))
    if step == 0:
        assert pos.size == 0
    else:
        assert pos.size == 1 and abs(int(pos[0]) - 1200) <= 2
        assert round(float(size[0])) == round(step / (2 * np.pi))


def test_alias_alignment_follows_the_confident_run():
    """A short sub-run 100 Hz off (a loop seeded on the wrong alias) is moved onto the
    frequency that a longer, stronger overlapping run sets."""
    t = np.arange(0, 20, 0.01)
    f = -300.0
    lam = 299_792_458.0 / FC

    def cell(t, hz, snr):
        u = 2 * np.pi * hz * (t - t[0])
        st = {
            "e": np.rint(t / 0.005).astype(np.int64),
            "t": t,
            "u": u,
            "snr": np.full(t.size, snr),
            "lab": np.zeros(t.size, np.int64),
            "code_raw_m": -u * lam / (2 * np.pi),
            "slips": 0,
        }
        return {"lam": lam, "streams": [st]}

    # each run's code agrees with its own carrier, so code alone would keep the short run
    # 100 Hz off; the long run is placed by its code, the short one by the long one
    cells = {1: cell(t, f, 30.0), 2: cell(t[500:900], f + 100.0, 3.0)}
    counts = cp.align_aliases(cells)
    st = cells[2]["streams"][0]
    hz = np.polyfit(st["t"], st["u"], 1)[0] / (2 * np.pi)
    assert abs(hz - f) < 1e-6
    assert counts["by_code"] == 1 and counts["by_others"] == 1 and counts["code_disagrees"] == 1


def test_frequency_slip_onto_the_next_alias_is_found():
    """A loop that jumps 100 Hz and keeps tracking leaves no phase step, only a kink."""
    t = np.arange(1000) * 0.01
    u = 2 * np.pi * (-200.0 * t)
    u[400:] += 2 * np.pi * 100.0 * (t[400:] - t[400])
    assert list(cp.freq_slips(t, u)) == [400]
    assert cp.freq_slips(t, 2 * np.pi * (-200.0 * t - 1.25 * t**2)).size == 0  # drift alone


def test_records_keep_large_run_labels_apart():
    """Single-difference labels pack two runs into one integer; records must not merge them."""
    e = np.arange(40)
    lab = np.where(e < 20, 3_000_007, 4_000_007)
    q, v, label, _ = cp.records(e, e.astype(float), lab, np.ones(40), min_n=10)
    assert list(q) == [0, 1] and list(label) == [3_000_007, 4_000_007]
