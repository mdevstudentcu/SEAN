"""Real against simulated (issue #30, ADR-0015): the same statistics from any two sessions.

A session needs `/truth` (from GPS in real sessions) to have residuals. For towers, each tower's
residual has its own straight-line trend removed first, so clock offsets don't count as noise.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Measurement, Truth
from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.sim import attacks

STATISTICS = ["residual_std", "persistence_lag1", "availability", "channels"]


def _load(path) -> tuple[list[Measurement], np.ndarray, np.ndarray, list | None]:
    mcap = session.mcap_path(path)
    meas, truth = [], []
    for _, rec in read_session(mcap, topics=["/meas/", "/truth"]):
        (truth if isinstance(rec, Truth) else meas).append(rec)
    if not truth:
        raise ValueError(f"{path} has no /truth, so its residuals can't be computed")
    truth.sort(key=lambda t: t.t_ns)
    t = np.array([x.t_ns for x in truth], dtype=np.int64)
    return meas, t, np.array([x.pos_enu for x in truth]), session.read_meta(path).get("origin_llh")


def _truth_at(t_ns, truth_t, truth_pos) -> np.ndarray:
    x = np.asarray(t_ns, dtype=float) - truth_t[0]
    grid = (truth_t - truth_t[0]).astype(float)
    return np.column_stack([np.interp(x, grid, truth_pos[:, i]) for i in range(3)])


def residuals(path, source: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per channel: (time in seconds, detrended residual) against truth."""
    meas, truth_t, truth_pos, origin = _load(path)
    channels: dict[str, list[Measurement]] = {}
    for m in meas:
        if m.source == source and m.kind in ("pseudorange", "position_enu", "altitude"):
            channels.setdefault(m.emitter or source, []).append(m)
    out = {}
    for name, group in channels.items():
        t_ns = np.array([m.t_ns for m in group], dtype=np.int64)
        expected = _truth_at(t_ns, truth_t, truth_pos)
        if group[0].kind == "pseudorange":
            emitter = emitter_enu(group[0].meta, origin)
            r = np.array([m.value[0] for m in group]) - np.linalg.norm(expected - emitter, axis=1)
        elif group[0].kind == "altitude":
            r = np.array([m.value[0] for m in group]) - expected[:, 2]
        else:
            r = np.linalg.norm(np.array([m.value for m in group])[:, :2] - expected[:, :2], axis=1)
        seconds = (t_ns - t_ns[0]) / 1e9
        trend = np.polyval(np.polyfit(seconds, r, 1), seconds) if len(r) > 2 else r.mean()
        out[name] = (seconds, r - trend)
    return out


def statistics(path, source: str) -> dict[str, float]:
    """Noise size, how long errors persist, and how often the channel is present."""
    channels = residuals(path, source)
    if not channels:
        raise ValueError(f"{path} has no usable {source} measurements")
    stds, lags, availability = [], [], []
    for seconds, r in channels.values():
        stds.append(float(np.std(r)))
        if len(r) > 2 and np.std(r) > 0:
            lags.append(float(np.corrcoef(r[:-1], r[1:])[0, 1]))
        step = float(np.median(np.diff(seconds))) if len(seconds) > 1 else 1.0
        span = float(seconds[-1] - seconds[0]) + step
        availability.append(min(len(seconds) * step / span, 1.0) if span > 0 else 1.0)
    return {
        "residual_std": float(np.mean(stds)),
        "persistence_lag1": float(np.mean(lags)) if lags else float("nan"),
        "availability": float(np.mean(availability)),
        "channels": len(channels),
    }


def table(sim, real, source: str) -> str:
    a, b = statistics(sim, source), statistics(real, source)
    rows = [f"| Statistic ({source}) | Simulated | Real | Gap |", "| --- | --- | --- | --- |"]
    rows += [f"| {k} | {a[k]:.3f} | {b[k]:.3f} | {a[k] - b[k]:+.3f} |" for k in STATISTICS]
    return "\n".join(rows)


def plot(sim, real, source: str, out: str | Path) -> Path:
    """Both residual distributions on one figure, as ADR-0015 asks."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    for label, path in (("simulated", sim), ("real", real)):
        values = np.concatenate([r for _, r in residuals(path, source).values()])
        ax.hist(values, bins=60, density=True, histtype="step", label=label)
    ax.set(xlabel=f"{source} residual after trend removal", ylabel="density")
    ax.set_title(f"{session.session_name(sim)} vs {session.session_name(real)}", fontsize=9)
    ax.legend()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def inject(path, faults: list[dict], seed: int = 0) -> tuple[list[Measurement], int]:
    """Apply software faults to a recorded session (ADR-0015). Returns (measurements, t0_ns).

    Fault times count from the session's first measurement.
    """
    meas, truth_t, truth_pos, origin = _load(path)
    meas.sort(key=lambda m: m.t_ns)
    t0 = meas[0].t_ns
    ctx = attacks.Context(
        t0_ns=t0,
        origin_llh=origin,
        truth_pos=lambda s: _truth_at(t0 + np.atleast_1d(s) * 1e9, truth_t, truth_pos),
        rng=np.random.default_rng(seed),
    )
    changed, _ = attacks.apply(meas, faults, ctx)
    changed.sort(key=lambda m: (m.t_ns, m.source, m.kind, m.emitter))
    return changed, t0
