"""Allan deviation of a static IMU session, beside the sim's MPU6050 model (ADR-0015).

The comparison `systems/verification.md` asks for (*Sim validity*, IMU row): the same statistic
on our sensor sitting still and on the sim's model run for the same length at the same rate.

    python analysis/imu_allan.py data/sessions/<session> [--skip-s S] [--no-sim] [--out DIR]

Writes to `results/<session>-allan/` (or --out): `allan.png`, `summary.md`, `summary.json`.
`--skip-s` drops the first S seconds (warm-up drift); the default keeps everything.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from pnt.io.mcap_log import read_session
from pnt.io.session import mcap_path, read_meta, session_name
from pnt.sim import allan, sensors
from pnt.sim.sensors import DEG, MPU6050, G

# Categorical slots 1-3 (one per axis) and recessive ink, as in analysis/figures.py
AXIS_COLORS = ("#2a78d6", "#eb6834", "#1baf7a")
INK, GRID = "#52514e", "#e4e3df"
AXES = ("x", "y", "z")
GAP_FACTOR = 1.5  # an interval longer than this times the median is a gap


def load_imu(session: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """(t_ns, n x 6 values: accel m/s^2 then gyro rad/s) of the session's accel_gyro records."""
    rows = [
        (m.t_ns, m.value)
        for _, m in read_session(mcap_path(session), ["/meas/imu"])
        if m.kind == "accel_gyro"
    ]
    if not rows:
        raise SystemExit(f"{session}: no accel_gyro records on /meas/imu")
    t = np.array([r[0] for r in rows], np.int64)
    v = np.array([r[1] for r in rows], float)
    order = np.argsort(t, kind="stable")
    return t[order], v[order]


def timing(t_ns: np.ndarray) -> dict:
    dt = np.diff(t_ns) / 1e9
    med = float(np.median(dt))
    return {
        "samples": int(len(t_ns)),
        "span_s": float((t_ns[-1] - t_ns[0]) / 1e9),
        "rate_hz": 1.0 / med,
        "gaps": int(np.sum(dt > GAP_FACTOR * med)),
        "longest_gap_s": float(dt.max()),
    }


def sim_static(n: int, fs: float, seed: int = 0) -> np.ndarray:
    """The sim's MPU6050, level and still, for n samples at fs: n x 6 like `load_imu`."""
    t = np.arange(n) / fs
    f = np.tile([0.0, 0.0, G], (n, 1))
    accel, gyro = sensors.imu(t, f, np.zeros((n, 3)), np.random.default_rng(seed), MPU6050)
    return np.hstack([accel, gyro])


def curves(v: np.ndarray, fs: float) -> list[tuple[np.ndarray, np.ndarray]]:
    return [allan.overlapping_adev(v[:, i], fs) for i in range(6)]


def spectral_peak(x: np.ndarray, fs: float) -> float:
    """Frequency (Hz) of the largest peak above 0.5 Hz in the Welch spectrum: a vibration or
    other periodic signal shows here, and bends the Allan curve away from white noise."""
    from scipy.signal import welch

    f, p = welch(x - x.mean(), fs=fs, nperseg=min(len(x), 4096))
    band = f > 0.5
    return float(f[band][np.argmax(p[band])])


def figures(cs, v: np.ndarray, fs: float) -> list[dict]:
    """Per axis, in the sim's units: densities, floors and rate random walk."""
    out = []
    for i, (tau, adev) in enumerate(cs):
        gyro = i >= 3
        unit = DEG if gyro else 1e-6 * G  # deg/s or micro-g
        f = allan.fit(tau, adev)
        w = f["white_adev_1s"]
        out.append(
            {
                "sensor": "gyro" if gyro else "accel",
                "axis": AXES[i % 3],
                "noise_density": allan.psd_density(v[:, i], fs) / unit,
                "allan_density": None if w is None else allan.density_from_white(w) / unit,
                "noise_density_unit": "deg/s/sqrt(Hz)" if gyro else "ug/sqrt(Hz)",
                "white_slope": f["white_slope"],
                # the floor in deg/h (gyro) or micro-g (accel), and where it is
                "floor": f["floor"] / unit * (3600.0 if gyro else 1.0),
                "floor_unit": "deg/h" if gyro else "ug",
                "floor_tau_s": f["floor_tau_s"],
                "floor_reached": f["bias_floor_reached"],
                "rrw_3s": None if f["rrw_adev_3s"] is None else f["rrw_adev_3s"] / unit,
            }
        )
    return out


def plot(path: Path, real, sim, caption: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1, 2, figsize=(10, 4.4), constrained_layout=True)
    for k, (ax, name, scale, unit) in enumerate(
        [
            (axs[0], "Gyro", 3600.0 / DEG, "deg/h"),
            (axs[1], "Accelerometer", 1e6 / G, "µg"),
        ]
    ):
        first = 3 if k == 0 else 0
        for a in range(3):
            tau, adev = real[first + a]
            ax.loglog(tau, adev * scale, color=AXIS_COLORS[a], lw=2, label=f"{AXES[a]}: ours")
            if sim is not None:
                tau_s, adev_s = sim[first + a]
                ax.loglog(tau_s, adev_s * scale, color=AXIS_COLORS[a], lw=1.2, ls="--",
                          label=f"{AXES[a]}: sim model")  # fmt: skip
        ax.set_title(f"{name} Allan deviation", loc="left", fontsize=11)
        ax.set_xlabel("averaging time τ (s)")
        ax.set_ylabel(f"Allan deviation ({unit})")
        ax.grid(True, which="major", color=GRID, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.legend(fontsize=8, frameon=False, ncol=2 if sim is not None else 1)
    fig.text(0.01, -0.02, caption, fontsize=7, color=INK, ha="left", va="top")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def repo_commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def markdown(name, meta, tm, real_f, sim_f, statics, peaks, commit, skip_s) -> str:
    lines = [
        f"# IMU Allan deviation: {name}",
        "",
        f"Session `{name}` (recorded at commit `{meta.get('commit', '?')}`), analysed at commit "
        f"`{commit}`. Hardware: {meta.get('hardware')}. First {skip_s:g} s dropped.",
        "",
        f"{tm['samples']} samples over {tm['span_s']:.0f} s at {tm['rate_hz']:.1f} Hz; "
        f"{tm['gaps']} intervals > {GAP_FACTOR}x nominal, longest {tm['longest_gap_s']:.3f} s.",
        "",
        "| Sensor | Axis | Noise density | Allan check (slope) | Sim model | Floor | at τ (s) "
        "| Floor reached | Static mean | Spectral peak (Hz) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    def num(x, fmt):
        return "—" if x is None else format(x, fmt)

    for i, f in enumerate(real_f):
        gyro = f["sensor"] == "gyro"
        model = MPU6050.gyro_noise_dps_rthz if gyro else MPU6050.accel_noise_ug_rthz
        sim_floor = "" if sim_f is None else f" (sim {num(sim_f[i]['floor'], '.3g')})"
        mean_unit = "deg/s" if gyro else "m/s²"
        lines.append(
            f"| {f['sensor']} | {f['axis']} | {num(f['noise_density'], '.3g')} "
            f"{f['noise_density_unit']} | {num(f['allan_density'], '.3g')} "
            f"({num(f['white_slope'], '.2f')}) | {model:g} | "
            f"{num(f['floor'], '.3g')} {f['floor_unit']}{sim_floor} | {f['floor_tau_s']:.3g} | "
            f"{'yes' if f['floor_reached'] else 'no'} | {statics[i]:.4g} {mean_unit} | "
            f"{peaks[i]:.2f} |"
        )
    g_mag = float(np.linalg.norm(statics[:3]))
    lines += [
        "",
        f"Mean |accel| {g_mag:.4f} m/s² against g = {G} ({(g_mag / G - 1) * 100:+.1f} %): "
        "scale and bias together; a single static pose cannot separate them.",
        "",
        f"Noise density is the median spectrum in {allan.PSD_BAND_HZ[0]:g}-"
        f"{allan.PSD_BAND_HZ[1]:g} Hz, in the sim's convention (`pnt.sim.sensors`: "
        "sigma = N·sqrt(fs/2)), so it can replace the `ImuParams` value. *Allan check* is the "
        "same density from the curve's slope -1/2 stretch (its slope in brackets); a vibration "
        "(see the spectral peak) bends the curve and makes it disagree. *Floor reached: no* means "
        "the curve was still falling at the longest τ: the record is too short to see the bias "
        "instability.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--skip-s", type=float, default=0.0, help="drop the first S seconds")
    ap.add_argument("--no-sim", action="store_true", help="skip the sim model's curve")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    name = session_name(args.session)
    meta = read_meta(args.session)
    t, v = load_imu(args.session)
    keep = t >= t[0] + int(args.skip_s * 1e9)
    t, v = t[keep], v[keep]
    tm = timing(t)
    fs = tm["rate_hz"]
    real = curves(v, fs)
    sim_v = None if args.no_sim else sim_static(len(v), fs)
    sim = None if sim_v is None else curves(sim_v, fs)
    real_f = figures(real, v, fs)
    sim_f = None if sim_v is None else figures(sim, sim_v, fs)
    statics = v.mean(axis=0)
    statics_out = np.concatenate([statics[:3], statics[3:] / DEG])  # gyro in deg/s
    peaks = [spectral_peak(v[:, i], fs) for i in range(6)]

    out = args.out or Path(__file__).parent / "results" / f"{name}-allan"
    out.mkdir(parents=True, exist_ok=True)
    commit = repo_commit()
    caption = (
        f"Session {name} (recorded at {meta.get('commit', '?')}), analysed at {commit}. "
        f"Solid: our MPU6050, still; dashed: the sim's MPU6050 model, same length and rate."
    )
    plot(out / "allan.png", real, sim, caption)
    (out / "summary.md").write_text(
        markdown(name, meta, tm, real_f, sim_f, statics_out, peaks, commit, args.skip_s)
    )
    (out / "summary.json").write_text(
        json.dumps(
            {
                "session": name,
                "session_commit": meta.get("commit"),
                "commit": commit,
                "skip_s": args.skip_s,
                "timing": tm,
                "static_mean": statics_out.tolist(),
                "spectral_peak_hz": peaks,
                "ours": real_f,
                "sim": sim_f,
                "sim_model": dict(MPU6050.__dict__),
            },
            indent=2,
            default=str,
        )
    )
    print(f"wrote {out}/allan.png, summary.md, summary.json")


if __name__ == "__main__":
    main()
