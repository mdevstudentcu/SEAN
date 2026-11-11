"""GNSS position noise and barometer noise and drift of a static session, beside the sim (#30).

    python analysis/static_gnss_baro.py data/sessions/<session> [--out DIR]

For a receiver that did not move (ADR-0015, *Sim validity* rows *GNSS position* and
*Barometer*):

- **GNSS:** each 3D fix's ENU position minus the session's mean fix, per axis: σ, the lag-1
  autocorrelation and the time the autocorrelation takes to fall below 1/e (a white error, as the
  sim draws, falls at once), and the σ the receiver reported (gpsd's epx/epy/epv, 95 % → 1σ).
- **Barometer:** altitude minus its mean: white σ (first differences / √2), σ, the straight-line
  drift over the session, and the σ of 10 s means about that line (the slow wander).

Writes `summary.md` and `summary.json` (and `static.png` with `--out`). **Privacy:** only
deviations about the session's own mean are printed or written, never a position, a height or a
pressure, since a static session's mean is where it was recorded.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from pnt.core.measurement import Measurement
from pnt.io.mcap_log import read_session
from pnt.io.session import mcap_path, session_name

# The sim's GNSS model (`sim/models.gnss`): white, σ per epoch, 1.5 σ vertical, at 5 Hz in every
# committed scenario (sigma_m 2.5, TBC).
SIM_GNSS_SIGMA_M = 2.5
SIM_GNSS_UP_FACTOR = 1.5
# The sim's barometer (`sim/models.baro`, as every committed scenario runs it): white noise,
# `sigma_m` 0.5 at 10 Hz, plus one constant bias per run drawn with σ 1.0 m (`bias_sigma_m`),
# both TBC. `sim/sensors.BMP280` (0.3 m, 1.0 m Gauss-Markov over 600 s) is not what the
# scenarios draw; only its `noise_m` is used, as the σ the payload reports on real records.
SIM_BARO_SIGMA_M = 0.5
SIM_BARO_BIAS_SIGMA_M = 1.0
AXES = ("east", "north", "up")
COLORS = ("#2a78d6", "#eb6834", "#1baf7a")
INK, GRID = "#1f2328", "#d0d7de"


def load(path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(GNSS t s, ENU (n x 3), reported σ (n x 3), baro t s, baro altitude), times from the first
    record of either."""
    g, b = [], []
    for _, m in read_session(mcap_path(path), topics=["/meas/gnss", "/meas/baro"]):
        if not isinstance(m, Measurement):
            continue
        if m.kind == "position_enu":
            g.append((m.t_ns, m.value, m.sigma))
        elif m.kind == "altitude":
            b.append((m.t_ns, m.value[0]))
    if not g and not b:
        raise SystemExit(f"{path}: no GNSS fixes or barometer altitudes")
    g.sort(key=lambda r: r[0])
    b.sort(key=lambda r: r[0])
    t0 = min([r[0] for r in g[:1]] + [r[0] for r in b[:1]])
    gt = np.array([(r[0] - t0) / 1e9 for r in g])
    enu = np.array([r[1] for r in g], dtype=float).reshape(-1, 3)
    sig = np.array([r[2] for r in g], dtype=float).reshape(-1, 3)
    bt = np.array([(r[0] - t0) / 1e9 for r in b])
    alt = np.array([r[1] for r in b], dtype=float)
    return gt, enu, sig, bt, alt


def corr_time(x: np.ndarray, dt: float) -> float:
    """Lag (s) at which the autocorrelation of x (mean removed) first falls below 1/e; NaN if it
    never does within half the series."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = x.size
    var = float(np.dot(x, x))
    if n < 4 or var == 0:
        return float("nan")
    for lag in range(1, n // 2):
        if np.dot(x[:-lag], x[lag:]) / var < math.exp(-1):
            return lag * dt
    return float("nan")


def gnss_noise(t_s: np.ndarray, enu: np.ndarray, sig: np.ndarray) -> dict:
    """Per-axis statistics of the fixes about their mean (see module docstring)."""
    if len(t_s) < 4:
        raise ValueError("need at least 4 fixes")
    dt = float(np.median(np.diff(t_s)))
    dev = enu - enu.mean(axis=0)
    out = {"fixes": int(len(t_s)), "rate_hz": 1.0 / dt, "span_s": float(t_s[-1] - t_s[0])}
    for i, ax in enumerate(AXES):
        x = dev[:, i]
        out[ax] = {
            "sigma_m": float(np.std(x)),
            "peak_to_peak_m": float(np.ptp(x)),
            "lag1": float(np.corrcoef(x[:-1], x[1:])[0, 1]),
            "corr_time_s": corr_time(x, dt),
            "reported_sigma_m": float(np.median(sig[:, i])),
            "sim_sigma_m": SIM_GNSS_SIGMA_M * (SIM_GNSS_UP_FACTOR if ax == "up" else 1.0),
        }
    out["horizontal_rms_m"] = float(np.sqrt(np.mean(dev[:, 0] ** 2 + dev[:, 1] ** 2)))
    return out


def baro_noise(t_s: np.ndarray, alt: np.ndarray, block_s: float = 10.0) -> dict:
    """White σ, σ, straight-line drift and the wander of block means about it."""
    if len(t_s) < 4:
        raise ValueError("need at least 4 samples")
    dt = float(np.median(np.diff(t_s)))
    x = alt - alt.mean()
    slope, icpt = np.polyfit(t_s, x, 1)
    resid = x - (slope * t_s + icpt)
    blocks = np.floor((t_s - t_s[0]) / block_s).astype(int)
    full = np.bincount(blocks) >= 0.8 * block_s / dt
    means = (np.bincount(blocks, weights=resid) / np.maximum(np.bincount(blocks), 1))[full]
    return {
        "samples": int(len(t_s)),
        "rate_hz": 1.0 / dt,
        "span_s": float(t_s[-1] - t_s[0]),
        "white_sigma_m": float(np.std(np.diff(x)) / math.sqrt(2)),
        "sigma_m": float(np.std(x)),
        "drift_m_per_min": float(slope * 60.0),
        "drift_over_span_m": float(slope * (t_s[-1] - t_s[0])),
        f"wander_{block_s:g}s_means_sigma_m": float(np.std(means)) if means.size > 1 else None,
        "sim_noise_m": SIM_BARO_SIGMA_M,
        "sim_bias_sigma_m": SIM_BARO_BIAS_SIGMA_M,
    }


def markdown(name: str, commit: str, g: dict | None, b: dict | None) -> str:
    lines = [f"Session `{name}`, analysed at `{commit}`. Deviations about the session mean only."]
    if g:
        lines += [
            "",
            f"**GNSS:** {g['fixes']} fixes at {g['rate_hz']:.2f} Hz over {g['span_s']:.0f} s; "
            f"horizontal RMS {g['horizontal_rms_m']:.2f} m.",
            "",
            "| Axis | σ (m) | Peak to peak (m) | Lag-1 autocorrelation | 1/e time (s) "
            "| Reported σ, median (m) | Sim σ (m, white) |",
            "|---|---|---|---|---|---|---|",
        ]
        for ax in AXES:
            a = g[ax]
            lines.append(
                f"| {ax} | {a['sigma_m']:.2f} | {a['peak_to_peak_m']:.2f} | {a['lag1']:.3f} | "
                f"{a['corr_time_s']:.0f} | {a['reported_sigma_m']:.2f} | {a['sim_sigma_m']:.2f} |"
            )
    if b:
        w = next(k for k in b if k.startswith("wander_"))
        lines += [
            "",
            f"**Barometer:** {b['samples']} samples at {b['rate_hz']:.2f} Hz over "
            f"{b['span_s']:.0f} s.",
            "",
            "| White σ (m) | σ (m) | Drift (m/min) | Drift over span (m) | σ of 10 s means about "
            "the line (m) | Sim white σ (m) | Sim constant bias σ (m) |",
            "|---|---|---|---|---|---|---|",
            f"| {b['white_sigma_m']:.3f} | {b['sigma_m']:.3f} | {b['drift_m_per_min']:+.3f} | "
            f"{b['drift_over_span_m']:+.2f} | {b[w]:.3f} | {b['sim_noise_m']:.2f} | "
            f"{b['sim_bias_sigma_m']:.1f} |",
        ]
    return "\n".join(lines) + "\n"


def plot(path: Path, gt, enu, bt, alt, caption: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, constrained_layout=True)
    dev = enu - enu.mean(axis=0)
    for i, ax in enumerate(AXES):
        a1.plot(gt, dev[:, i], color=COLORS[i], lw=1.5, label=ax)
    a1.set_ylabel("GNSS fix − mean (m)")
    a1.legend(frameon=False, fontsize=8, ncol=3)
    a2.plot(bt, alt - alt.mean(), color=COLORS[0], lw=0.8)
    a2.set_ylabel("barometer altitude − mean (m)")
    a2.set_xlabel("time (s)")
    for ax in (a1, a2):
        ax.grid(True, color=GRID, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle(caption, fontsize=9, color=INK)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session")
    p.add_argument("--out", help="folder for summary.md, summary.json and static.png")
    a = p.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    gt, enu, sig, bt, alt = load(a.session)
    g = gnss_noise(gt, enu, sig) if len(gt) >= 4 else None
    b = baro_noise(bt, alt) if len(bt) >= 4 else None
    name = session_name(a.session)
    md = markdown(name, commit, g, b)
    print(md)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.md").write_text(md)
        js = {"session": name, "commit": commit, "gnss": g, "baro": b}
        (out / "summary.json").write_text(json.dumps(js, indent=1) + "\n")
        cap = f"{name}, real session, static, analysis at {commit}: deviations about the mean"
        plot(out / "static.png", gt, enu, bt, alt, cap)


if __name__ == "__main__":
    main()
