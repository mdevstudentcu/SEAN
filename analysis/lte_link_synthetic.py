"""End-to-end check of the LTE chain on synthetic baseband (#121).

A static receiver hears registered Ottawa eNBs (real positions from `lte-cells-ottawa.csv`) on one
carrier, through one RTL-SDR with a 0.4 ppm clock. Baseband is synthesised, written as a `.cu8`
capture, run through the real front end, resolved with `pnt.nav.cells` and fed to an estimator
with simulated GNSS position and time (until `--gps-off`) and barometer. Writes the error over
time, with and without the dongle clock state, and prints the numbers.

    python analysis/lte_link_synthetic.py --seeds 5 --out /tmp/lte-link.png

Synthetic only: no multipath, no real towers, and the generator and receiver share one reading of
TS 36.211. It shows that the pieces connect, not how well real towers will range (#21).
"""

import argparse
import csv
import pathlib
import subprocess
import tempfile

import msgspec
import numpy as np

from pnt import nav
from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.frontends.lte import capture, process_file, synth
from pnt.nav.cells import CELL_TABLE

ORIGIN = (45.3876, -75.6960, 80.0)  # Carleton, the scenarios' session origin
TRUE_ENU = np.array([100.0, 50.0, 30.0])
EARFCN, FC, FS = 2460, 875e6, 1.92e6
T0 = 1_446_000_000_000_000_000
C = 299792458.0


def pick_cells(n: int) -> list[tuple[int, np.ndarray]]:
    """`n` nearby eNBs on the carrier, spread around the receiver, each with a unique PCI."""
    with open(CELL_TABLE, newline="") as f:
        rows = [r for r in csv.DictReader(f) if int(r["earfcn"]) == EARFCN]
    enbs: dict[int, set[str]] = {}
    for r in rows:
        enbs.setdefault(int(r["pci"]), set()).add(r["enb_id"])
    best: dict[str, tuple[float, int, np.ndarray]] = {}
    for r in rows:
        if len(enbs[int(r["pci"])]) != 1:
            continue  # a collision would be left out by the lookup
        e = llh_to_enu(
            [float(r["lat"]), float(r["lon"]), ORIGIN[2] + float(r["ant_height_agl_m"])], ORIGIN
        )
        d = float(np.linalg.norm(e[:2]))
        if d <= 5000.0 and (r["enb_id"] not in best or d < best[r["enb_id"]][0]):
            best[r["enb_id"]] = (d, int(r["pci"]), e)
    sectors = {}  # one per bearing sector, nearest first, so that the geometry is not one-sided
    for _, pci, e in sorted(best.values(), key=lambda v: v[0]):
        sectors.setdefault(int((np.arctan2(e[1], e[0]) + np.pi) // (2 * np.pi / n)), (pci, e))
    return list(sectors.values())[:n]


def run(seed: int, towers, duration: float, gps_off: float, snr: float, estimator: str = "ekf"):
    rng = np.random.default_rng(seed)
    cells_ = []
    for pci, e in towers:
        rho = float(np.linalg.norm(TRUE_ENU - e))
        clock = float(rng.uniform(0.0, 0.009))  # any frame timing: tests the 10 ms ambiguity
        cells_.append(synth.Tower(pci=pci, delay_s=rho / C + clock))
    x = synth.synthesize(cells_, duration, fs=FS, fc=FC, clock_ppm=0.4, snr_db=snr, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    with tempfile.TemporaryDirectory() as d:
        cap = capture.write_capture(pathlib.Path(d) / "c.cu8", capture.complex_to_cu8(x), meta)
        result = process_file(cap)
    records = list(result.measurements)
    for k in range(int(duration * 5)):
        t_ns = T0 + k * 200_000_000
        if k % 5 == 0 and k / 5 < gps_off:
            fix = tuple(float(v) for v in TRUE_ENU + rng.normal(0, 2.0, 3))
            records.append(
                Measurement(
                    t_ns=t_ns, source="gnss", kind="position_enu", value=fix, sigma=(2.0, 2.0, 2.0)
                )  # fmt: skip
            )
        if k % 5 == 0 and k / 5 < gps_off:  # GNSS disciplines the host clock, not a dongle
            records.append(
                Measurement(t_ns=t_ns, source="gnss", kind="time", value=(0.0,), sigma=(1e-7,))
            )
        alt = float(TRUE_ENU[2] + rng.normal(0, 1.0))
        records.append(
            Measurement(t_ns=t_ns, source="baro", kind="altitude", value=(alt,), sigma=(1.0,))
        )
    records.sort(key=lambda m: m.t_ns)
    stripped = [m if m.source != "lte" else _without_clock(m) for m in records]
    out = {}
    for name, stream in (("with", records), ("without", stripped)):
        est = list(nav.estimate(estimator, stream, origin_llh=ORIGIN))
        t = np.array([(e.t_ns - T0) / 1e9 for e in est])
        err = np.array([np.linalg.norm(np.array(e.pos_enu)[:2] - TRUE_ENU[:2]) for e in est])
        alarms = sum("time_spoof_suspected" in e.flags for e in est)
        out[name] = (t, err, alarms)
    heard = sorted({m.emitter for m in result.measurements if m.kind == "pseudorange"})
    return out, heard


def _without_clock(m: Measurement) -> Measurement:
    return msgspec.structs.replace(m, meta={k: v for k, v in m.meta.items() if k != "rx_clock"})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--gps-off", type=float, default=10.0)
    p.add_argument("--snr", type=float, default=5.0, help="in-band dB")
    p.add_argument("--cells", type=int, default=5)
    p.add_argument("--estimator", default="ekf")
    p.add_argument("--out")
    a = p.parse_args()
    towers = pick_cells(a.cells)
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=7"], capture_output=True, text=True
    ).stdout.strip()
    print(f"commit {commit}; pcis {[t[0] for t in towers]}; ranges (m) "
          f"{[round(float(np.linalg.norm(TRUE_ENU - t[1]))) for t in towers]}")  # fmt: skip
    runs = []
    for seed in range(a.seeds):
        out, heard = run(seed, towers, a.duration, a.gps_off, a.snr, a.estimator)
        runs.append(out)
        w, wo = (o[1][o[0] >= a.gps_off] for o in (out["with"], out["without"]))
        print(f"seed {seed}: heard {len(heard)} cells; after GPS off, p95 error "
              f"{np.percentile(w, 95):.1f} m with the dongle clock, "
              f"{np.percentile(wo, 95):.1f} m without; GNSS-time alarms "
              f"{out['with'][2]} with, {out['without'][2]} without")  # fmt: skip
    pool = {n: np.concatenate([r[n][1][r[n][0] >= a.gps_off] for r in runs]) for n in runs[0]}
    print({n: round(float(np.percentile(v, 95)), 1) for n, v in pool.items()})
    if a.out:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        for name, color, label in (("without", "#b5442e", "without the dongle clock"),
                                   ("with", "#20639b", "with the dongle clock")):  # fmt: skip
            for i, r in enumerate(runs):
                ax.plot(r[name][0], r[name][1], color=color, lw=1.2, alpha=0.7,
                        label=label if i == 0 else None)  # fmt: skip
        ax.axvline(a.gps_off, color="0.4", ls="--", lw=1)
        ax.text(a.gps_off + 0.15, ax.get_ylim()[1] * 0.92, "GPS off", color="0.3")
        ax.set(xlabel="time (s)", ylabel="horizontal error (m)", yscale="log",
               title=f"Synthetic LTE chain: {a.seeds} seeds, commit {commit}")  # fmt: skip
        ax.grid(True, which="major", alpha=0.3)
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(a.out, dpi=130)
        print("wrote", a.out)


if __name__ == "__main__":
    main()
