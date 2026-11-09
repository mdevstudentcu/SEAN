"""LTE front end (#21, #23) on synthetic RTL-SDR captures: no hardware, seeded.

Captures come from `pnt.frontends.lte.synth` (TS 36.211 PSS/SSS in a 1.4 MHz frame with QPSK
filler), quantised to 8-bit `.cu8` like the dongle. Accuracy bounds are regression guards set
against the Cramér-Rao bound, not requirements.
"""

import math
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from pnt.cli import main
from pnt.core.measurement import validate
from pnt.frontends.lte import capture, process_file, synth
from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.frontend import emit
from pnt.frontends.lte.tracker import CellTrack, Config, Epoch, GapMap
from pnt.io.mcap_log import read_session
from pnt.sources.replay import ReplaySource

FS, FC, PPM = 1.92e6, 875e6, 0.4  # 0.4 ppm at 875 MHz: a 350 Hz carrier offset
M_PER_SAMPLE = synth.C / FS
T0 = 1_446_000_000_000_000_000


def crb_m(snr_db: float, symbols: int) -> float:
    """Ranging bound for `symbols` known sync symbols (62 subcarriers) at in-band SNR."""
    from pnt.frontends.lte.tracker import BETA_HZ

    e_n0 = symbols * sig.N_SYNC * 10 ** (snr_db / 10)
    return synth.C / (2 * math.pi * BETA_HZ * math.sqrt(2 * e_n0))


def write(tmp, name, towers, dur, snr, drops=(), fs=FS, fc=FC, seed=1, **sidecar):
    x = synth.synthesize(towers, dur, fs=fs, fc=fc, clock_ppm=PPM, snr_db=snr, seed=seed,
                         drops=drops)  # fmt: skip
    meta = {"sample_rate_hz": fs, "center_freq_hz": fc, "t_ns": T0, **sidecar}
    return capture.write_capture(tmp / f"{name}.cu8", capture.complex_to_cu8(x), meta)


def splice(tmp, name, first, second, at_s, dur, snr, seed=1, **sidecar):
    """A capture of towers `first` becoming towers `second` at `at_s` (same noise and clock)."""
    x, y = (synth.synthesize(t, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=snr, seed=seed)
            for t in (first, second))  # fmt: skip
    at = round(at_s * FS)
    z = np.r_[x[:at], y[at:]]
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0, **sidecar}
    return capture.write_capture(tmp / f"{name}.cu8", capture.complex_to_cu8(z), meta)


def epoch_errors(result, tower, fs=FS):
    """Tracker frame-boundary estimate minus truth, samples, for each 5 ms epoch."""
    L = sig.half_frame_length(fs)
    b0 = tower.boundary_sample(0, fs, PPM)
    errs = []
    for cell in result.cells:
        if cell.pci != tower.pci:
            continue
        for e in cell.epochs:
            c = cell.n0 + e.k * L + e.theta_meas
            h = round((c - b0) / L)
            errs.append(c - tower.boundary_sample(h / 2, fs, PPM))
    return np.array(errs)


# --- standard -----------------------------------------------------------------------------


def test_pss_is_the_punctured_zadoff_chu_of_ts_36_211():
    for n_id2, u in enumerate(sig.PSS_ROOTS):
        d = sig.pss(n_id2)
        assert d.shape == (62,) and np.allclose(np.abs(d), 1)
        zc = np.exp(-1j * np.pi * u * np.arange(63) * np.arange(1, 64) / 63)
        assert np.allclose(d, np.delete(zc, 31))  # length 63, DC element removed


def test_sss_groups_are_distinct_and_match_the_table():
    assert [sig.sss_indices(g) for g in (0, 1, 29, 30, 167)] == [
        (0, 1), (1, 2), (29, 30), (0, 2), (2, 9)]  # fmt: skip
    assert len({sig.sss_indices(g) for g in range(168)}) == 168
    for n_id2 in range(3):
        rows = sig.sss_table(n_id2).reshape(336, 62)
        assert set(np.unique(rows)) == {-1.0, 1.0}
        gram = rows @ rows.T / 62
        assert np.max(np.abs(gram - np.eye(336))) < 0.5  # 336 distinct sequences


def test_earfcn_matches_the_cell_table_convention():
    # Values from the #87 scan list (analysis/extract_lte_cells.py), including its rounding
    # of an off-raster filing (886.25 MHz -> 2572).
    cases = {875.0: 2460, 742.5: 5145, 753.5: 5255, 720.0: 9690, 731.5: 5035, 639.5: 68811,
             619.5: 68611, 885.0: 2560, 886.25: 2572, 746.0: 5180}  # fmt: skip
    for mhz, n in cases.items():
        assert capture.earfcn(mhz)[0] == n
    assert capture.earfcn(886.25)[1] and not capture.earfcn(875.0)[1]
    assert capture.earfcn(1900.0) == (None, False)
    assert capture.dl_hz(2460) == 875e6


def test_cu8_round_trip_keeps_the_waveform():
    rng = np.random.default_rng(0)
    x = (rng.normal(size=(4096, 2)) @ [1, 1j]).astype(np.complex64)
    y = capture.cu8_to_complex(capture.complex_to_cu8(x, rms_lsb=24))
    scale = np.vdot(x, y).real / np.vdot(x, x).real
    assert np.std(y / scale - x) < 0.03  # 8-bit quantisation noise


# --- front end on synthetic captures ------------------------------------------------------

TOWER = synth.Tower(pci=8, delay_s=1.234567e-3, delay_rate=10 / synth.C)  # fractional, moving


@pytest.fixture(scope="module")
def single(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lte")
    return {snr: process_file(write(tmp, f"s{snr}", [TOWER], 1.0, snr)) for snr in (-10, 0, 10)}


@pytest.mark.parametrize("snr", [-10, 0, 10])
def test_finds_the_pci_and_frame_timing(single, snr):
    r = single[snr]
    assert [c.pci for c in r.cells] == [8]
    err = epoch_errors(r, TOWER)
    assert err.size > 100
    # Frame timing: every epoch on the right half-frame (an error would be ±9600 samples).
    assert np.max(np.abs(err)) < 2.0
    # SNR estimate (per resource element = in-band) within 1 dB
    assert abs(r.cells[0].snr_db - snr) < 1.0


@pytest.mark.parametrize("snr", [-10, 0, 10])
def test_toa_error_is_near_the_ranging_bound(single, snr):
    err = epoch_errors(single[snr], TOWER) * M_PER_SAMPLE
    bound = crb_m(snr, 2)  # one PSS + one SSS per 5 ms epoch
    assert np.std(err) < 1.3 * bound  # regression guard: 1.05-1.15x on these seeds
    assert abs(np.mean(err)) < 0.3 * bound


def test_measurements_follow_the_icd_and_carry_the_clock(single):
    r = single[0]
    pr = [m for m in r.measurements if m.kind == "pseudorange"]
    dop = [m for m in r.measurements if m.kind == "doppler"]
    # 10 Hz after the 200 ms first-path check; doppler once the carrier aiding locks
    assert len(pr) >= 7 and len(dop) >= 3
    for m in r.measurements:
        validate(m)
        assert m.source == "lte" and m.emitter == "lte:2460:8"
        assert {"snr_db", "cfo_hz", "dongle", "sample_index", "rx_clock"} <= set(m.meta)
    t = np.array([m.t_ns for m in pr])
    assert np.all(np.diff(t) > 90_000_000) and np.all(np.diff(t) < 110_000_000)
    # Doppler is the raw pseudorange rate: range rate plus c x the dongle's clock drift.
    truth = TOWER.range_rate_dimless(PPM) * synth.C  # 10 m/s + 0.4 ppm (120 m/s)
    for m in dop:
        assert abs(m.value[0] - truth) < 5 * m.sigma[0] + 0.05
        assert abs(m.meta["cfo_hz"] + truth / synth.C * FC) < 2.0
    # Pseudorange: c x frame-boundary arrival, so its rate matches the doppler.
    v = np.array([m.value[0] for m in pr])
    rate = np.polyfit((t - t[0]) / 1e9, v, 1)[0]
    assert abs(rate - truth) < 5.0


def test_pseudorange_is_continuous_across_frames_and_matches_truth(single):
    pr = [m for m in single[10].measurements if m.kind == "pseudorange"]
    cell = single[10].cells[0]
    L = sig.half_frame_length(FS)
    for m in pr:
        # Truth: the boundary arrival (local samples) at this time, minus whole frames since
        # the arc's reference boundary, as the front end defines the pseudorange.
        c = (m.t_ns - T0) * FS / 1e9
        h = round((c - TOWER.boundary_sample(0, FS, PPM)) / L)
        truth_c = TOWER.boundary_sample(h / 2, FS, PPM)
        k = round((truth_c - cell.n0) / L)
        truth = synth.C * (cell.n0 % (2 * L) + truth_c - cell.n0 - k * L) / FS
        assert abs(m.value[0] - truth) < 4 * m.sigma[0] + 1.0
        assert m.value[0] < 2 * synth.C * sig.FRAME_S  # no frame jumps (3000 km each)


def test_second_tower_sharing_the_pss_root_is_separated(tmp_path):
    towers = [
        TOWER,
        synth.Tower(pci=2, delay_s=3.4567e-3, delay_rate=-5 / synth.C, power_db=-6, phase=1.0),
        synth.Tower(pci=9, delay_s=7.891e-3, power_db=-3, phase=2.0),
    ]
    assert {t.pci % 3 for t in towers[:2]} == {2}  # PCI 2 and 8 share N_ID2 (one PSS root)
    r = process_file(write(tmp_path, "multi", towers, 1.2, 10.0))
    assert sorted(c.pci for c in r.cells) == [2, 8, 9]
    for t in towers:
        err = epoch_errors(r, t) * M_PER_SAMPLE
        assert err.size > 100 and np.std(err) < 60 and abs(np.mean(err)) < 10
    assert {m.emitter for m in r.measurements} == {"lte:2460:2", "lte:2460:8", "lte:2460:9"}


def test_earliest_path_beats_a_later_stronger_echo(tmp_path):
    echo = synth.Path(delay_s=6 / FS, power_db=6.0, phase=0.7)  # 940 m later, 4x the power
    tower = synth.Tower(pci=8, delay_s=1.234567e-3, echoes=(echo,))
    r = process_file(write(tmp_path, "mp", [tower], 1.0, 10.0))
    err = epoch_errors(r, tower) * M_PER_SAMPLE
    assert err.size > 100
    # On the first path: the echo's sidelobe biases it by ~-54 m; the echo itself is +937 m.
    assert np.max(np.abs(err)) < 120


@pytest.mark.parametrize("stamped", [False, True])
def test_sample_drop_is_detected_and_sized(tmp_path, stamped):
    at = int(0.6 * FS) + 777
    n = 131_072 if stamped else 1234  # a whole USB buffer needs the host stamps to size
    extra = {}
    if stamped:  # host GPS-ns stamp per 16384-sample buffer, ±0.5 ms jitter
        rng = np.random.default_rng(5)
        f = np.arange(0, int(1.3 * FS), 16384)
        local = f + np.where(f >= at, n, 0)
        host = T0 + np.round(local * 1e9 / FS + rng.uniform(-5e5, 5e5, f.size)).astype(int)
        extra = {"buffers": [[int(a), int(b)] for a, b in zip(f, host, strict=True)]}
    r = process_file(write(tmp_path, "gap", [TOWER], 1.3, 0.0, drops=((at, n),), **extra))
    assert len(r.gaps) == 1
    g = r.gaps[0]
    assert g.n == n and g.at <= at <= g.until and g.ambiguous is (not stamped)
    err = epoch_errors(r, TOWER)
    assert np.max(np.abs(err)) < 1.0  # epochs after the gap are timed right
    pr = [m for m in r.measurements if m.kind == "pseudorange"]
    flagged = [m for m in pr if "sample_gap" in m.meta["flags"]]
    assert len(flagged) == 1
    v = np.array([m.value[0] for m in pr])
    assert np.all(np.abs(np.diff(v)) < 50)  # continuous: ~13 m per 100 ms of clock drift
    arcs = {m.meta["arc"] for m in pr}
    assert arcs == ({0} if stamped else {0, 1})  # unsized gap: the arc restarts


@pytest.mark.parametrize("n", [12_000, 131_072])
def test_unstamped_drop_past_half_a_frame_is_still_flagged(tmp_path, n):
    # n mod 19200 > 9600 looks like the cell arriving late. 131072 is rtl_sdr's default buffer.
    at = int(0.6 * FS) + 777
    r = process_file(write(tmp_path, "gap", [TOWER], 1.3, 0.0, drops=((at, n),)))
    assert len(r.gaps) == 1
    g = r.gaps[0]
    assert g.ambiguous and g.n == n % (2 * sig.half_frame_length(FS)) and g.at <= at
    assert np.max(np.abs(epoch_errors(r, TOWER))) < 1.0  # regression guard: timed right after it
    pr = [m for m in r.measurements if m.kind == "pseudorange"]
    assert sum("gap_ambiguous" in m.meta["flags"] for m in pr) == 1
    assert {m.meta["arc"] for m in pr} == {0, 1}


def test_cell_found_a_little_late_is_a_new_arc_not_a_gap(tmp_path):
    late = replace(TOWER, delay_s=TOWER.delay_s + 3 / FS)  # past the code gate, within a CP
    r = process_file(splice(tmp_path, "late", [TOWER], [late], 0.6, 1.3, 10.0))
    assert r.gaps == []
    pr = [m for m in r.measurements if m.kind == "pseudorange"]
    assert not any(m.meta["flags"] for m in pr)
    assert {m.meta["arc"] for m in pr} == {0, 1}


@pytest.mark.parametrize("stamped", [False, True])
def test_path_found_a_little_early_is_not_a_gap(tmp_path, stamped):
    early = replace(TOWER, delay_s=TOWER.delay_s - 3 / FS)  # past the code gate, within a CP
    extra = {}
    if stamped:  # no drop, but the host stamps jitter by ±0.5 ms
        rng = np.random.default_rng(5)
        f = np.arange(0, int(1.3 * FS), 16384)
        host = T0 + np.round(f * 1e9 / FS + rng.uniform(-5e5, 5e5, f.size)).astype(int)
        extra = {"buffers": [[int(a), int(b)] for a, b in zip(f, host, strict=True)]}
    r = process_file(splice(tmp_path, "early", [TOWER], [early], 0.6, 1.3, 10.0, **extra))
    assert r.gaps == []
    pr = [m for m in r.measurements if m.kind == "pseudorange"]
    assert not any(m.meta["flags"] for m in pr)
    assert {m.meta["arc"] for m in pr} == {0, 1}


@pytest.mark.parametrize("stamped", [False, True])
def test_gap_reaches_every_tracked_cell(tmp_path, stamped):
    at = int(0.6 * FS) + 777
    n = 131_072 if stamped else 1234
    towers = [TOWER, synth.Tower(pci=9, delay_s=7.891e-3, power_db=-3, phase=2.0)]
    extra = {}
    if stamped:
        f = np.arange(0, int(1.3 * FS), 16384)
        host = T0 + np.round((f + np.where(f >= at, n, 0)) * 1e9 / FS).astype(int)
        extra = {"buffers": [[int(a), int(b)] for a, b in zip(f, host, strict=True)]}
    r = process_file(write(tmp_path, "gap", towers, 1.3, 10.0, drops=((at, n),), **extra))
    assert len(r.gaps) == 1
    for emitter in ("lte:2460:8", "lte:2460:9"):
        pr = [m for m in r.measurements if m.kind == "pseudorange" and m.emitter == emitter]
        flagged = [m for m in pr if "sample_gap" in m.meta["flags"]]
        assert len(flagged) == 1
        assert ("gap_ambiguous" in flagged[0].meta["flags"]) is (not stamped)
        assert {m.meta["arc"] for m in pr} == ({0} if stamped else {0, 1})


def _epochs(n0, t_s, arc):
    """Twenty 5 ms epochs of one arc, its k counted from 0, starting at `t_s`."""
    L = sig.half_frame_length(FS)
    return [
        Epoch(k=k, c_ref=t_s * FS + k * L, theta_meas=0.0, nu=0.0, sigma=0.1, snr_post=100.0,
              psi=0.0, n_ref=t_s * FS + k * L + 1000, locked=False, arc=arc, n0=n0)
        for k in range(20)
    ]  # fmt: skip


def _capture_stub(t0_ns=T0):
    return SimpleNamespace(t0_ns=t0_ns, fs=FS, dongle="sdr_a")


def test_arcs_with_overlapping_half_frame_counts_are_emitted_separately():
    # A cell re-found with new timing restarts k at 0, so the two arcs' k ranges overlap.
    cell = CellTrack(2460, FC, 8, 5000.0, arc=1, epochs=[*_epochs(1000.0, 0.0, 0),
                                                         *_epochs(5000.0, 30.0, 1)])  # fmt: skip
    pr = emit([cell], _capture_stub(), GapMap(), Config())
    assert [m.meta["arc"] for m in pr] == [0, 1]
    # Each arc keeps its own frame reference.
    assert [m.value[0] for m in pr] == pytest.approx([synth.C * n / FS for n in (1000, 5000)])


def test_t_ns_is_exact_integer_gps_time():
    # A float64 near 1.4e18 ns can only hold multiples of 256 ns.
    t0 = T0 + 1
    cell = CellTrack(2460, FC, 8, 1000.0, epochs=_epochs(1000.0, 0.0, 0))
    pr = emit([cell], _capture_stub(t0), GapMap(), Config())
    assert pr[0].t_ns == t0 + 50_000_000  # the middle epoch: k = 10, 5 ms each


def test_band_hop_tracks_each_carrier_and_continues_the_arc(tmp_path):
    fc2 = 731.5e6
    other = synth.Tower(pci=9, delay_s=2.2345678e-3)
    a, b = round(0.5 * FS), round(1.0 * FS)
    x, y = (synth.synthesize([t], 1.5, fs=FS, fc=f, clock_ppm=PPM, snr_db=10.0, seed=1)
            for t, f in ((TOWER, FC), (other, fc2)))  # fmt: skip
    hops = [{"sample_index": i, "center_freq_hz": f} for i, f in ((0, FC), (a, fc2), (b, FC))]
    meta = {"sample_rate_hz": FS, "t_ns": T0, "hops": hops}
    z = capture.complex_to_cu8(np.r_[x[:a], y[a:b], x[b:]])
    r = process_file(capture.write_capture(tmp_path / "hop.cu8", z, meta))
    pr = {e: [m for m in r.measurements if m.kind == "pseudorange" and m.emitter == e]
          for e in ("lte:2460:8", "lte:5035:9")}  # fmt: skip
    assert all(pr.values()) and sum(map(len, pr.values())) == sum(
        m.kind == "pseudorange" for m in r.measurements
    )
    # The first carrier is left for 0.5 s and picked up again on the same arc and timing.
    times = np.array([(m.t_ns - T0) / 1e9 for m in pr["lte:2460:8"]])
    assert times.min() < 0.5 and times.max() > 1.0 and not np.any((times > 0.55) & (times < 0.95))
    assert {m.meta["arc"] for m in pr["lte:2460:8"]} == {0}
    assert np.max(np.abs(epoch_errors(r, TOWER))) < 1.0  # regression guard


def test_sample_rate_2_4_msps(tmp_path):
    tower = synth.Tower(pci=9, delay_s=2.2345678e-3, delay_rate=-20 / synth.C)
    r = process_file(write(tmp_path, "fs24", [tower], 0.8, 0.0, fs=2.4e6, fc=731.5e6))
    assert [(c.pci, c.earfcn) for c in r.cells] == [(9, 5035)]
    err = epoch_errors(r, tower, fs=2.4e6) * synth.C / 2.4e6
    assert np.std(err) < 1.3 * crb_m(0, 2)


def test_noise_only_capture_finds_nothing(tmp_path):
    r = process_file(write(tmp_path, "noise", [], 0.5, 0.0))
    assert r.cells == [] and r.measurements == []


def test_cli_writes_a_session_that_replay_reads(tmp_path, capsys):
    cu8 = write(tmp_path, "sdr_a", [TOWER], 0.6, 10.0)
    out = tmp_path / "session-lte"
    main(["frontend", "lte", str(cu8), "--out", str(out)])
    assert "lte:2460:8" in capsys.readouterr().out
    recs = list(ReplaySource(out / "session.mcap"))
    assert recs and all(m.source == "lte" for m in recs)
    assert {t for t, _ in read_session(out / "session.mcap")} == {"/meas/lte"}
    with pytest.raises(SystemExit):
        main(["frontend", "lte", str(cu8), "--out", str(out)])  # never overwrites


def test_cli_says_so_when_a_capture_is_too_short(tmp_path):
    cu8 = write(tmp_path, "short", [TOWER], 0.05, 10.0)  # under one 80 ms search window
    out = tmp_path / "session-lte"
    with pytest.raises(SystemExit, match="no LTE cells"):
        main(["frontend", "lte", str(cu8), "--out", str(out)])
    assert not out.exists()
