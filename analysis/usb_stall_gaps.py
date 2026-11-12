"""USB stalls against dropped samples in a capture's buffer stamps (#306).

    python analysis/usb_stall_gaps.py <session> [<session> ...] [--fig FILE.png] [--out FILE.md]

Reads each session's `sdr_a.json` sidecar (`buffers`: each USB buffer's first sample index and
host GPS-ns stamp, `payload/sdr.py`). The latency of a buffer is its stamp less its sample time
(`pnt.frontends.lte.tracker.latency`). A dropped transfer moves the latency floor up for good;
a stall that catches up delays some buffers and the floor comes back. Per session:

- stalls: consecutive stamps more than half a frame (9,600 samples at 1.92 MS/s) further apart
  than their samples; the largest; the longest catch-up (from the stall until a buffer's latency
  is back within half a frame of the floor before it);
- onsets where the floor after a buffer is at least half a frame above the floor before it,
  compared over 8 buffers each side (the front end before #306) and over `FLOOR_WINDOW_S`
  (after): each would be a drop.

`--fig` plots the latency around the session's largest stall (first session only).

Privacy: sample counts and times only. No position, track, origin, range or bearing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.tracker import FLOOR_WINDOW_S, latency

OLD_WINDOW = 8  # buffers each side: the front end's window before #306


def load(session: Path) -> tuple[np.ndarray, float]:
    meta = json.loads((session / "sdr_a.json").read_text())
    return np.asarray(meta["buffers"], dtype=np.int64), float(meta["sample_rate_hz"])


def floor_steps(lat: np.ndarray, idx: np.ndarray, fs: float, buffers: int | None) -> np.ndarray:
    """Floor after less floor before, at each buffer: `buffers` each side, or `FLOOR_WINDOW_S`."""
    if buffers is None:
        w = FLOOR_WINDOW_S * fs
        lo = np.searchsorted(idx, idx - w, side="left")
        hi = np.searchsorted(idx, idx + w, side="right")
    else:
        lo = np.maximum(np.arange(idx.size) - buffers, 0)
        hi = np.minimum(np.arange(idx.size) + buffers, idx.size)
    out = np.zeros(idx.size)
    for i in range(1, idx.size):
        out[i] = lat[i : hi[i]].min() - lat[lo[i] : i].min()
    return out


def onsets(step: np.ndarray, half: int) -> int:
    big = step >= half
    return int(np.sum(big[1:] & ~big[:-1]) + big[0])


def report(session: Path) -> dict:
    b, fs = load(session)
    idx = b[:, 0]
    lat = latency(b, fs)
    half = sig.half_frame_length(fs)
    excess = np.diff(lat)  # samples: each stamp step beyond its samples
    stalls = np.nonzero(excess >= half)[0]
    catch = 0.0
    for j in stalls:
        pre = lat[max(0, j - 16) : j + 1].min()
        k = j + 1
        while k < lat.size and lat[k] > pre + half:
            k += 1
        catch = max(catch, (idx[min(k, idx.size - 1)] - idx[j + 1]) / fs)
    return {
        "session": session.name,
        "buffers": int(idx.size),
        "stalls": int(stalls.size),
        "largest_stall": int(excess.max()) if excess.size else 0,
        "catch_up_s": catch,
        "old_onsets": onsets(floor_steps(lat, idx, fs, OLD_WINDOW), half),
        "new_onsets": onsets(floor_steps(lat, idx, fs, None), half),
        "new_max_step": float(floor_steps(lat, idx, fs, None).max()),
    }


def figure(session: Path, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    b, fs = load(session)
    idx = b[:, 0]
    lat = latency(b, fs)
    j = int(np.argmax(np.diff(lat))) + 1
    sel = slice(max(0, j - 40), min(idx.size, j + 80))
    t = (idx[sel] - idx[j]) / fs
    old = floor_steps(lat, idx, fs, OLD_WINDOW)[sel]
    new = floor_steps(lat, idx, fs, None)[sel]
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)
    ax[0].plot(t, lat[sel] - lat[max(0, j - 40) : j].min(), ".-", color="#2a78d6", lw=1, ms=3)
    ax[0].set_ylabel("latency less floor\n(samples)")
    ax[0].set_title(f"{session.name}: the largest stall, caught up, no samples dropped")
    ax[1].plot(t, old, color="#eb6834", label="floor step, 8 buffers each side (before)")
    ax[1].plot(t, new, color="#1baf7a", label=f"floor step, {FLOOR_WINDOW_S:g} s each side (#306)")
    ax[1].axhline(sig.half_frame_length(fs), color="#6b7280", ls="--", lw=1, label="half a frame")
    ax[1].set_ylabel("samples")
    ax[1].set_xlabel("s from the stall")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+", type=Path)
    ap.add_argument("--fig", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    lines = [
        "| Session | Buffers | Stalls ≥ ½ frame | Largest (samples) | Longest catch-up (s) "
        f"| Floor steps ≥ ½ frame, 8 buffers | Floor steps ≥ ½ frame, {FLOOR_WINDOW_S:g} s |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in args.sessions:
        r = report(s)
        lines.append(
            f"| `{r['session']}` | {r['buffers']} | {r['stalls']} | {r['largest_stall']:,} "
            f"| {r['catch_up_s']:.2f} | {r['old_onsets']} | {r['new_onsets']} "
            f"(largest step {r['new_max_step']:,.0f}) |"
        )
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        args.out.write_text(text)
    if args.fig:
        figure(args.sessions[0], args.fig)


if __name__ == "__main__":
    main()
