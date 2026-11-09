"""LTE front end: achieved TOA σ against SNR on synthetic captures, against the ranging bound.

Synthetic evidence only (`pnt.frontends.lte.synth`): TS 36.211 PSS/SSS in a 1.4 MHz frame with
QPSK filler, AWGN, a 0.4 ppm dongle clock and 10 m/s motion, quantised to 8-bit `.cu8`. Real
captures add multipath, interference and the dongle's own impairments, so these numbers are a
floor until the day-1 static capture (TBC).

    python analysis/lte_frontend_sigma.py [--seeds 5] [--out analysis/pr-evidence/<branch>]

Writes `lte-sigma-vs-snr.png` and `lte-sigma-vs-snr.json`, and prints the table.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np

from pnt.frontends.lte import capture, synth
from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.frontend import process_capture
from pnt.frontends.lte.tracker import BETA_HZ, Config

FS, FC, PPM, T0 = 1.92e6, 875e6, 0.4, 1_446_000_000_000_000_000
SNRS = (-10, -5, 0, 10)
DURATION_S = 2.0
TOWER = synth.Tower(pci=8, delay_s=1.234567e-3, delay_rate=10 / synth.C)
REPO = Path(__file__).resolve().parents[1]


def crb_m(snr_db: float, symbols: int) -> float:
    """σ_τ >= 1 / (2π β sqrt(2 E/N0)), E/N0 = symbols · 62 · SNR (the report's assumptions)."""
    return synth.C / (2 * math.pi * BETA_HZ * math.sqrt(2 * symbols * 62 * 10 ** (snr_db / 10)))


def _capture(tmp: Path, name: str, snr: float, seed: int, ppm: float, tower=TOWER, dur=DURATION_S):
    x = synth.synthesize([tower], dur, fs=FS, fc=FC, clock_ppm=ppm, snr_db=snr, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    return capture.open_capture(
        capture.write_capture(tmp / f"{name}.cu8", capture.complex_to_cu8(x), meta)
    )


def _truth_boundary(c: float, tower, ppm: float) -> float:
    L = sig.half_frame_length(FS)
    h = round((c - tower.boundary_sample(0, FS, ppm)) / L)
    return tower.boundary_sample(h / 2, FS, ppm)


def run_one(args) -> dict:
    snr, seed = args
    with tempfile.TemporaryDirectory() as d:
        cap = _capture(Path(d), "c", snr, seed, PPM)
        r = process_capture(cap)
    L = sig.half_frame_length(FS)
    m = synth.C / FS
    cell = next(c for c in r.cells if c.pci == TOWER.pci)
    ep = [cell.n0 + e.k * L + e.theta_meas for e in cell.epochs]
    epoch_err = [(c - _truth_boundary(c, TOWER, PPM)) * m for c in ep]
    out_err, out_sigma = [], []
    for meas in r.measurements:
        if meas.kind != "pseudorange":
            continue
        c = (meas.t_ns - T0) * FS / 1e9
        tc = _truth_boundary(c, TOWER, PPM)
        k = round((tc - cell.n0) / L)
        truth = synth.C * (cell.n0 % (2 * L) + tc - cell.n0 - k * L) / FS
        out_err.append(meas.value[0] - truth)
        out_sigma.append(meas.sigma[0])
    return {"snr": snr, "seed": seed, "epoch_err": epoch_err, "out_err": out_err,
            "out_sigma": out_sigma, "snr_est": cell.snr_db, "rt": r.realtime_factor}  # fmt: skip


def run_interp(interp: int) -> dict:
    """+20 dB, 1 ppm clock: the true arrival sweeps through every fractional sample position."""
    ppm = 1.0
    tower = synth.Tower(pci=8, delay_s=1.234567e-3)
    with tempfile.TemporaryDirectory() as d:
        cap = _capture(Path(d), "i", 20.0, 7, ppm, tower, 3.0)
        r = process_capture(cap, replace(Config(), interp=interp))
    L = sig.half_frame_length(FS)
    cell = r.cells[0]
    frac, err = [], []
    for e in cell.epochs:
        c = cell.n0 + e.k * L + e.theta_meas
        t = _truth_boundary(c, tower, ppm)
        frac.append(t - math.floor(t))
        err.append((c - t) * synth.C / FS)
    return {"interp": interp, "frac": frac, "err": err}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument(
        "--out", default=str(REPO / "analysis/pr-evidence/shrikar-feat-23-lte-frontend")
    )
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=7"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()  # fmt: skip
    jobs = [(s, seed) for s in SNRS for seed in range(a.seeds)]
    with ProcessPoolExecutor() as ex:
        runs = list(ex.map(run_one, jobs))
        interp = list(ex.map(run_interp, [8, 1]))

    rows = []
    for s in SNRS:
        rs = [r for r in runs if r["snr"] == s]
        e = np.concatenate([r["epoch_err"] for r in rs])
        o = np.concatenate([r["out_err"] for r in rs])
        sg = np.concatenate([r["out_sigma"] for r in rs])
        rows.append({
            "snr_db": s,
            "snr_est_db": float(np.mean([r["snr_est"] for r in rs])),
            "epoch_sigma_m": float(np.std(e)), "epoch_bias_m": float(np.mean(e)),
            "crb_epoch_m": crb_m(s, 2), "crb_10ms_m": crb_m(s, 4),
            "out_sigma_m": float(np.std(o)), "out_bias_m": float(np.mean(o)),
            "crb_out_m": crb_m(s, 40), "reported_sigma_m": float(np.mean(sg)),
            "crb_1s_m": crb_m(s, 400), "n_epochs": int(e.size), "n_out": int(o.size),
            "worst_out_err_m": float(np.max(np.abs(o))),
        })  # fmt: skip
    ip = {r["interp"]: r for r in interp}
    interp_summary = {
        str(k): {"rms_m": float(np.sqrt(np.mean(np.square(v["err"])))),
                 "max_abs_m": float(np.max(np.abs(v["err"])))}
        for k, v in ip.items()
    }  # fmt: skip
    result = {"commit": commit, "seeds": a.seeds, "duration_s": DURATION_S, "fs": FS,
              "fc": FC, "clock_ppm": PPM, "rows": rows, "interp_20db": interp_summary}  # fmt: skip
    (out / "lte-sigma-vs-snr.json").write_text(json.dumps(result, indent=2))

    print(f"commit {commit}, {a.seeds} seeds x {DURATION_S} s per SNR, synthetic (sim)")
    print("| In-band SNR | SNR est. | Epoch σ (5 ms, 2 sym) | Bound | 10 Hz σ (achieved) | "
          "Bound (40 sym) | 10 Hz σ reported (mean) | Worst 10 Hz error |")  # fmt: skip
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['snr_db']:+d} dB | {r['snr_est_db']:+.1f} dB | {r['epoch_sigma_m']:.1f} m | "
              f"{r['crb_epoch_m']:.1f} m | {r['out_sigma_m']:.2f} m | {r['crb_out_m']:.2f} m | "
              f"{r['reported_sigma_m']:.2f} m | {r['worst_out_err_m']:.1f} m |")  # fmt: skip
    for k, v in interp_summary.items():
        print(f"+20 dB, interp 1/{k} sample: RMS {v['rms_m']:.2f} m, max {v['max_abs_m']:.2f} m")
    _plot(rows, ip, commit, out / "lte-sigma-vs-snr.png")


def _plot(rows, ip, commit, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    blue, orange, aqua, grid_c, ink, ink2 = (
        "#2a78d6",
        "#eb6834",
        "#1baf7a",
        "#e4e3df",
        "#0b0b0b",
        "#52514e",
    )
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": ink2, "axes.labelcolor": ink,
                         "xtick.color": ink2, "ytick.color": ink2})  # fmt: skip
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.6), facecolor="#fcfcfb")
    snr = [r["snr_db"] for r in rows]
    fine = np.linspace(min(snr) - 1, max(snr) + 1, 50)
    a1.plot(fine, [crb_m(s, 2) for s in fine], color=ink2, lw=1.2, ls="--",
            label="Bound, one 5 ms epoch (PSS+SSS)")  # fmt: skip
    a1.plot(fine, [crb_m(s, 40) for s in fine], color=ink2, lw=1.2, ls=":",
            label="Bound, one 100 ms output (40 symbols)")  # fmt: skip
    a1.plot(snr, [r["epoch_sigma_m"] for r in rows], "o-", color=blue, lw=2, ms=8,
            label="Achieved, 5 ms epoch")  # fmt: skip
    a1.plot(snr, [r["out_sigma_m"] for r in rows], "s-", color=orange, lw=2, ms=8,
            label="Achieved, 10 Hz output")  # fmt: skip
    a1.plot(snr, [r["reported_sigma_m"] for r in rows], "D", color=aqua, ms=8, mfc="none",
            mew=2, label="Reported σ, 10 Hz output (mean)")  # fmt: skip
    a1.set_yscale("log")
    a1.set_xlabel("In-band SNR (dB)")
    a1.set_ylabel("Pseudorange error σ (m)")
    a1.set_title("TOA σ vs SNR", loc="left", color=ink)
    a1.grid(True, which="both", color=grid_c, lw=0.6)
    a1.legend(frameon=False, fontsize=8.5)
    for fr, er, col, lab in (
        (ip[1]["frac"], ip[1]["err"], orange, "Parabola on raw samples"),
        (ip[8]["frac"], ip[8]["err"], blue, "Band-limited, 1/8-sample grid (used)"),
    ):
        a2.plot(fr, er, "o", color=col, ms=3, alpha=0.6, label=lab)
    a2.axhline(0, color=ink2, lw=0.8)
    a2.set_xlabel("Fractional sample position of the true arrival")
    a2.set_ylabel("Epoch error (m)")
    a2.set_title("Sub-sample interpolation at +20 dB", loc="left", color=ink)
    a2.grid(True, color=grid_c, lw=0.6)
    a2.legend(frameon=False, fontsize=8.5, loc="upper right")
    for ax in (a1, a2):
        ax.set_facecolor("#fcfcfb")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.text(0.01, 0.01, f"Synthetic captures (sim): 1.92 MS/s, 875 MHz, 0.4 ppm clock, 10 m/s, "
             f"8-bit; {rows[0]['n_epochs']} epochs per SNR. "
             f"analysis/lte_frontend_sigma.py at {commit}", fontsize=8, color=ink2)  # fmt: skip
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
