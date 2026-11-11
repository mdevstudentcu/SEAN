"""LTE capture report (#173 part 2) and the carrier scan script, on short synthetic captures.

Captures come from `pnt.frontends.lte.synth` inside a session folder with GNSS fixes, so the
front end's derived `-lte` session is what a real capture would give. Margins are regression
guards around the values the synthetic truth sets, not requirements.
"""

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import pnt.cli
from pnt.core import frames
from pnt.core.measurement import Measurement
from pnt.frontends.lte import capture, synth
from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.frontend import write_session
from pnt.io import session
from pnt.io.mcap_log import SessionWriter
from pnt.nav.cells import CellTable

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "lte_capture_report", REPO / "analysis" / "lte_capture_report.py"
)
lcr = importlib.util.module_from_spec(spec)
sys.modules["lte_capture_report"] = lcr  # dataclasses look their module up by name
spec.loader.exec_module(lcr)

FS, FC, PPM = 1.92e6, 875e6, 0.4
T0 = 1_446_000_000_000_000_000
ORIGIN = [45.3876, -75.6960, 70.0]
OFFSET_S = 1.0e-3  # every tower's frame timing in the aligned capture
DRIFT = 50e-9  # PCI 308's clock relative to the others: 50 ppb = 14.99 m/s


def tower_delay(pci: int) -> float:
    """Geometric range to the table's antenna (as the report computes it) / c + OFFSET_S."""
    _, cell = CellTable.load().associate(2460, pci, ORIGIN)
    llh = [cell.lat, cell.lon, ORIGIN[2] + cell.height_agl_m]
    return float(np.linalg.norm(frames.llh_to_enu(llh, ORIGIN))) / synth.C + OFFSET_S


def make_session(tmp: Path, name: str, towers, dur: float, seed: int):
    """A source session (meta + GNSS fixes at the origin) with a capture, then its -lte."""
    src = tmp / name
    src.mkdir()
    session.write_meta(
        src,
        {
            "name": name,
            "platform": "static",
            "origin_llh": ORIGIN,
            "simulated": True,
            "commit": "rec1234",
        },
    )
    with SessionWriter(src / session.MCAP_NAME) as w:
        for i in range(10):
            w.write(
                "/meas/gnss",
                Measurement(
                    t_ns=T0 + i * 200_000_000,
                    source="gnss",
                    kind="position_enu",
                    value=(0.0, 0.0, 0.0),
                    sigma=(2.5, 2.5, 5.0),
                ),
            )
    x = synth.synthesize(towers, dur, fs=FS, fc=FC, clock_ppm=PPM, snr_db=10.0, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0, "earfcn": 2460}
    cu8 = capture.write_capture(src / "sdr_a.cu8", capture.complex_to_cu8(x), meta)
    cap = capture.open_capture(cu8)
    from pnt.frontends.lte.frontend import process_capture

    result = process_capture(cap)
    out = write_session(result, cap, tmp / f"{name}-lte", "fe5678", copy_from=src)
    return out, result


TOWERS = [
    synth.Tower(pci=300, delay_s=tower_delay(300)),  # eNB 30018, the strongest
    synth.Tower(pci=308, delay_s=tower_delay(308), delay_rate=DRIFT, power_db=-3, phase=1.0),
    synth.Tower(pci=9, delay_s=tower_delay(9), power_db=-6, phase=2.0),  # eNB 36666
    synth.Tower(pci=42, delay_s=3.3e-3, power_db=-4, phase=0.5),  # two eNBs in range: collision
]
ALONE = [synth.Tower(pci=1, delay_s=2.2e-3)]  # PCI 1 is not on 2460 in the table


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("report")
    multi, r_multi = make_session(tmp, "20261110-1200-static-carleton-e2460", TOWERS, 5.0, 1)
    single, _ = make_session(tmp, "20261110-1210-static-carleton-alone", ALONE, 3.0, 2)
    paths = [multi, single]
    sessions = [lcr.load(p, None) for p in paths]
    table, names = CellTable.load(), lcr._site_names()
    for s in sessions:
        lcr.identify(s, table, names)
    res = lcr.analyse(sessions)
    text = lcr.run(paths, tmp / "out")
    return {"sessions": sessions, "res": res, "text": text, "out": tmp / "out", "result": r_multi}


def _by(rows, key, session_sub, label):
    return next(r for r in rows if session_sub in r["session"] and r[key].label == label)


def test_cells_tracked_and_levels(runs):
    rows = runs["res"]["cells"]
    multi = {r["cell"].pci: r for r in rows if "e2460" in r["session"]}
    assert set(multi) == {300, 308, 9, 42}
    assert multi[300]["level_db"] == 0.0
    # -3, -4, -6 dB sent; the SNR estimate includes the other cells' interference
    assert -5.5 < multi[308]["level_db"] < -1.5
    assert -9.0 < multi[9]["level_db"] < -4.0
    for r in multi.values():
        assert r["tracked_s"] > 3.5 and r["arcs"] == 1


def test_identity_against_the_table(runs):
    st = {c.pci: c for s in runs["sessions"] for c in s.cells}
    assert st[300].status == "matched" and st[300].enb == 30018
    assert abs(st[300].dist_m - 180) < 30  # Glengarry House, 0.18 km (first-capture.md)
    assert "GLENGARRY" in st[300].site_name
    assert st[9].status == "matched" and st[9].enb == 36666
    assert st[42].status == "collision" and st[1].status == "unknown"
    assert runs["sessions"][0].position_from == "mean of 10 GNSS fixes"


def test_dongle_frequency_error_is_recovered(runs):
    clk = {r["session"]: r for r in runs["res"]["clock"]}
    for r in clk.values():
        assert abs(r["median_ppm"] - PPM) < 0.02  # truth 0.4 ppm; PCI 308 adds 0.05 to one cell
    assert all("adev" not in r for r in clk.values())  # 3-5 s < 30 s
    assert runs["text"].count("not measurable from this session: ") >= 2


def test_pair_drift_and_frame_alignment(runs):
    pairs = {(r["a"].pci, r["b"].pci): r for r in runs["res"]["pairs"]}
    same = pairs[(300, 308)]
    assert same["same_enb"] is True
    assert abs(same["drift_mps"] - DRIFT * synth.C) < 1.0  # truth 14.99 m/s
    assert abs(same["drift_ppb"] - 50) < 3.5
    other = pairs[(300, 9)]
    assert other["same_enb"] is False and abs(other["drift_mps"]) < 1.0  # truth 0
    assert "same_enb" not in pairs[(300, 42)]  # collision: not matched
    offs = {r["cell"].pci: r["offset_us"] for r in runs["res"]["frames"]}
    assert set(offs) == {300, 308, 9}  # the collision is left out
    assert abs(offs[9]) < 0.1  # truth 0 µs: same frame timing after geometry
    assert abs(offs[308]) < 0.3  # 50 ppb over 2.5 s to mid-capture: 0.125 µs
    assert "| yes |" in runs["text"]


def test_observed_sigma_matches_the_true_error(runs):
    """The report's observed σ equals the true error's spread after the same quadratic."""
    r = runs["result"]
    L = sig.half_frame_length(FS)
    half_m = synth.C * L / FS
    for tower in TOWERS[:3]:
        cell = next(c for c in r.cells if c.pci == tower.pci)
        pr = [m for m in r.measurements if m.kind == "pseudorange" and m.meta["pci"] == tower.pci]
        b0 = tower.boundary_sample(0, FS, PPM)
        err = []
        for m in pr:
            c = (m.t_ns - T0) * FS / 1e9
            h = round((c - b0) / L)
            err.append(m.value[0] - synth.C * tower.boundary_sample(h / 2, FS, PPM) / FS)
        err = np.array(err)
        err = err[0] + (err - err[0] + half_m / 2) % half_m - half_m / 2
        t = np.array([m.t_ns - T0 for m in pr]) / 1e9
        x = t - t.mean()
        true_sd = np.std(err - np.polyval(np.polyfit(x, err, 2), x), ddof=1)
        row = _by(runs["res"]["sigma"], "cell", "e2460", f"lte:2460:{tower.pci}")
        assert abs(row["obs_10hz"] / true_sd - 1) < 0.1  # same residuals up to the truth model
        assert row["reported"] == pytest.approx(np.median([m.sigma[0] for m in pr]))
        assert cell.pci == tower.pci


def test_single_cell_degrades_gracefully(runs):
    text = runs["text"]
    alone = next(s for s in runs["sessions"] if "alone" in s.name)
    assert len(alone.cells) == 1
    assert f"{alone.name}: not measurable from this session: one cell per carrier" in text
    row = _by(runs["res"]["sigma"], "cell", "alone", "lte:2460:1")
    assert "obs_10hz" in row  # section 3 works with one cell
    # every number names its session and the commits
    assert "`rec1234`" in text and "`fe5678`" in text and "| simulated |" in text
    for n in ("report.md", "cells.png", "dongle_clock.png", "pair_differences.png"):
        assert (runs["out"] / n).stat().st_size > 0
    assert "## 6. What this would replace" in text and "`Config.sigma_scale` 1.5" in text
    # one cell's spread includes the correlated part: the ratio alone does not size sigma_scale
    assert "above 1, `Config.sigma_scale` is too low" not in text and "ADR-0036" in text


def test_no_position_says_not_measurable(runs, tmp_path):
    s = lcr.load(runs["sessions"][1].path, None)
    s.position, s.position_from = None, "none"
    lcr.identify(s, CellTable.load(), {})
    assert s.cells[0].status.startswith("not measurable")


def write_records(folder: Path, t_s, cfo_hz, pci: int = 1, dongle: str = "sdr_a") -> Path:
    """A derived `-lte` session written directly: one cell's 10 Hz pseudorange records (as
    `pnt frontend lte` writes them) without synthesising and tracking IQ."""
    folder.mkdir()
    session.write_meta(folder, {"name": folder.name, "simulated": True, "commit": "fe5678"})
    with SessionWriter(folder / session.MCAP_NAME) as w:
        for t, f in zip(t_s, cfo_hz, strict=True):
            meta = {"snr_db": 10.0, "cfo_hz": float(f), "rx_clock": dongle, "earfcn": 2460,
                    "pci": pci, "fc_hz": FC, "n_epochs": 20, "arc": 0}  # fmt: skip
            w.write(
                "/meas/lte",
                Measurement(t_ns=T0 + round(t * 1e9), source="lte", kind="pseudorange",
                            emitter=f"lte:2460:{pci}", value=(1000.0,), sigma=(5.0,), meta=meta),
            )  # fmt: skip
    return folder


def write_sidecar(folder: Path, seconds: float, dongle: str = "sdr_a") -> None:
    folder.mkdir(exist_ok=True)
    sidecar = {"dongle": dongle, "sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0,
               "samples": round(seconds * FS)}  # fmt: skip
    (folder / f"{dongle}.json").write_text(json.dumps(sidecar))


def test_availability_is_over_the_capture_not_the_record_span(tmp_path):
    """Tracked 3 s at the end of a 10 s capture: 30 %, not the 100 % of its own record span."""
    t = 7.0 + np.arange(30) * 0.1  # 30 records x 20 half frames x 5 ms = 3.0 s tracked
    lte = write_records(tmp_path / "20261110-1400-static-x-lte", t, np.full(t.size, -PPM * FC))
    write_sidecar(tmp_path / "20261110-1400-static-x", 10.0)
    s = lcr.load(lte, None)
    assert s.capture_s == {"sdr_a": pytest.approx(10.0)} and s.span_s == pytest.approx(3.0)
    (row,) = lcr.analyse([s])["cells"]
    assert row["avail"] == pytest.approx(0.30)
    text = lcr.run([lte], None)
    assert "| 3.0 | 30% |" in text and "median 30%, lowest 30%" in text

    # the same records with no original session beside them: not measurable, not a guess
    alone = tmp_path / "elsewhere"
    alone.mkdir()
    moved = lte.rename(alone / "20261110-1400-static-x-lte-fixed")
    (row,) = lcr.analyse([lcr.load(moved, None)])["cells"]
    assert row["avail"] is None
    text = lcr.run([moved], None)
    assert "| 3.0 | not measurable (no capture length) |" in text
    assert "not measurable from this session: no capture length" in text
    # ... unless the original session is named
    s = lcr.load(moved, None, original=tmp_path / "20261110-1400-static-x")
    assert lcr.analyse([s])["cells"][0]["avail"] == pytest.approx(0.30)


def test_allan_deviation_from_a_30_s_record(tmp_path):
    """32 s of 10 Hz records, constant 0.4 ppm plus white frequency noise at the level the
    tracker's loop gave on a 32 s synthetic capture (5.6e-11 at 1 s): σ_y(τ) ∝ τ^-1/2."""
    t = np.arange(317) * 0.1  # 31.6 s from first to last record
    sd = 5.6e-11 * np.sqrt(1.0 / 0.1)  # white FM: σ_y(τ) = σ_y(τ0) · √(τ0 / τ)
    eps = PPM * 1e-6 + np.random.default_rng(3).normal(0.0, sd, t.size)
    long = write_records(tmp_path / "20261110-1300-static-carleton-long-lte", t, -eps * FC)
    (clk,) = lcr.analyse([lcr.load(long, None)])["clock"]
    assert [tau for tau, _ in clk["adev"]] == [1.0, 2.0, 4.0, 8.0]  # up to a third of 31.6 s
    for tau, a in clk["adev"]:
        assert 0.6 < a / (5.6e-11 / np.sqrt(tau)) < 1.4  # few independent samples at 8 s
    assert all(a < 2e-10 for _, a in clk["adev"])
    assert abs(clk["median_ppm"] - PPM) < 0.005
    s = lcr.load(  # 29.9 s of record: below ADEV_MIN_S, no Allan deviation
        write_records(tmp_path / "short-lte", t[:300], -eps[:300] * FC), None
    )
    assert "adev" not in lcr.analyse([s])["clock"][0]


# --- scan script --------------------------------------------------------------------------

SCAN = REPO / "deploy" / "pi" / "scan_carriers.sh"


def test_scan_script_parses():
    subprocess.run(["bash", "-n", str(SCAN)], check=True)


def test_scan_dry_run_commands_parse_with_the_real_cli(monkeypatch):
    out = subprocess.run(
        ["bash", str(SCAN), "--dry-run", "--seconds", "20"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    cmds = [ln.removeprefix("+ ") for ln in out.splitlines() if ln.startswith("+ ")]
    record = [c for c in cmds if " record " in c]
    # unflagged rows of the scan list, each EARFCN once: 2460 first
    earfcns = [c.split("earfcn=")[1].split()[0].split(":")[0] for c in record]
    assert earfcns[0] == "2460" and len(earfcns) == len(set(earfcns)) == 13
    assert "9690" not in earfcns and "68811" not in earfcns  # flagged rows are left out
    seen = []
    monkeypatch.setattr(pnt.cli, "cmd_record", seen.append)  # parse only, record nothing
    for c in record:
        argv = shlex.split(c)
        assert argv[0].endswith("pnt")
        pnt.cli.main(argv[1:])
        a = seen[-1]
        assert a.cmd == "record" and a.duration == 20 and a.no_stream and a.out
        assert a.out.endswith(f"-e{a.sdr[0].split('earfcn=')[1]}")
    flagged = subprocess.run(
        ["bash", str(SCAN), "--dry-run", "--include-flagged"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "earfcn=9690" in flagged


def test_scan_rejects_unknown_options():
    r = subprocess.run(["bash", str(SCAN), "--bogus"], capture_output=True, text=True)
    assert r.returncode != 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
