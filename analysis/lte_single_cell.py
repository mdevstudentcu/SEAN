"""Noise of one LTE cell's pseudorange in a static capture, without a second cell to difference.

`analysis/lte_static_capture.py` needs two cells on one dongle so that the dongle clock cancels.
When only one cell is tracked, this splits that cell's own pseudorange into:

- **wander**: σ of what is left after a quadratic in time is removed (the cell's constant,
  drift and drift-rate). It holds the dongle clock's and the tower clock's wander and any slow
  multipath, which one cell cannot separate.
- **white**: σ of the epoch-to-epoch change of that residual over √2, the part that does not
  carry from one epoch to the next.

Static receiver, first arc of each cell only. Precision, not accuracy: no tower position, tower
clock or reference receiver is used, so nothing here says how far the pseudorange is from truth.

    python analysis/lte_single_cell.py data/sessions/<name>-lte [--plot residual.png]
"""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_session

INK, GRID, LINE = "#52514e", "#e4e3df", "#2a78d6"


def noise_split(t_s: np.ndarray, pr_m: np.ndarray) -> tuple[float, float, np.ndarray]:
    """(white σ, wander σ, residual) of one cell's pseudoranges at times `t_s`."""
    t = np.asarray(t_s, dtype=float)
    v = np.asarray(pr_m, dtype=float)
    if t.size < 4:
        raise ValueError("need at least 4 epochs to remove a quadratic")
    resid = v - np.polyval(np.polyfit(t - t[0], v, 2), t - t[0])
    white = float(np.std(np.diff(resid)) / np.sqrt(2.0))
    return white, float(np.std(resid)), resid


def load(path) -> dict[tuple[str, str], list[Measurement]]:
    """First-arc pseudoranges per (rx_clock, emitter), in time order."""
    out: dict[tuple[str, str], list[Measurement]] = defaultdict(list)
    for _, m in read_session(session.mcap_path(path), topics=["/meas/lte"]):
        if isinstance(m, Measurement) and m.kind == "pseudorange" and m.meta.get("arc") == 0:
            out[(m.meta.get("rx_clock", ""), m.emitter)].append(m)
    return {k: sorted(v, key=lambda m: m.t_ns) for k, v in out.items()}


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def plot(path: Path, emitter: str, t: np.ndarray, resid: np.ndarray, caption: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=110)
    ax.plot(t - t[0], resid, color=LINE, lw=1.2)
    ax.set_xlabel("time since first epoch (s)", color=INK)
    ax.set_ylabel("pseudorange − quadratic (m)", color=INK)
    ax.set_title(f"{emitter}: one cell, no difference", color=INK, fontsize=10, loc="left")
    ax.grid(color=GRID, lw=0.8)
    ax.tick_params(colors=INK)
    for s in ax.spines.values():
        s.set_color(GRID)
    fig.text(0.01, 0.01, caption, color=INK, fontsize=7)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", help="session folder or .mcap with /meas/lte records")
    p.add_argument("--plot", help="PNG of the longest cell's residual")
    a = p.parse_args()
    series = load(a.session)
    print(f"{a.session}: one cell at a time, quadratic removed (precision only, no truth)")
    print("| rx_clock | emitter | n | span (s) | median σ told (m) | white σ (m) | wander σ (m) |")
    print("|---|---|---|---|---|---|---|")
    longest = None
    for (clock, e), ms in sorted(series.items()):
        if len(ms) < 4:
            continue
        t = np.array([m.t_ns for m in ms], dtype=float) / 1e9
        white, wander, resid = noise_split(t, [m.value[0] for m in ms])
        told = float(np.median([m.sigma[0] for m in ms]))
        print(f"| {clock} | {e} | {len(ms)} | {t[-1] - t[0]:.1f} | {told:.2f} | "
              f"{white:.2f} | {wander:.2f} |")  # fmt: skip
        if longest is None or t.size > longest[1].size:
            longest = (e, t, resid)
    if a.plot and longest is not None:
        name = Path(a.session).name
        plot(Path(a.plot), longest[0], longest[1], longest[2],
             f"real session {name}, analysed at {commit()}")  # fmt: skip
        print(f"wrote {a.plot}")


if __name__ == "__main__":
    main()
