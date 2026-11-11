"""Real against simulated (issue #30, ADR-0015): the same statistics from any two sessions.

A channel is one emitter's records within one tracking arc (`meta.arc`), payload receiver only.
Its residual is the measured value minus the true one:

- with `/truth` and the emitter's position in the record: the range (or height, or horizontal
  position) truth gives;
- for a static receiver whose records carry no emitter position (real LTE records, the sim's
  front-end-shaped ones): a constant, since the true range doesn't change. A session counts as
  static when its metadata says `platform: static`, or when its `/truth` moves less than
  STATIC_SPAN_M.

Ranges known only modulo `meta.ambiguity_m` are unwrapped first. Then each channel's straight-line
trend is removed, so clock offsets and drifts don't count as noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pnt.core.frames import emitter_enu, llh_to_enu
from pnt.core.measurement import Measurement, Truth
from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.sim import attacks

STATISTICS = ["residual_std", "persistence_lag1", "availability", "channels"]
KINDS = ("pseudorange", "position_enu", "altitude")
STATIC_SPAN_M = 0.5  # numerical: truth that moves less than this is a static receiver


@dataclass
class _Session:
    meas: list[Measurement]
    truth_t: np.ndarray  # (N,) ns; empty without /truth
    truth_pos: np.ndarray  # (N, 3) ENU
    origin_llh: list[float] | None
    static: bool
    meta: dict


def _load(path) -> _Session:
    meas, truth = [], []
    for _, rec in read_session(session.mcap_path(path), topics=["/meas/", "/truth"]):
        if isinstance(rec, Truth):
            truth.append(rec)
        elif isinstance(rec, Measurement):
            meas.append(rec)
    truth.sort(key=lambda t: t.t_ns)
    t = np.array([x.t_ns for x in truth], dtype=np.int64)
    pos = np.array([x.pos_enu for x in truth], dtype=float).reshape(-1, 3)
    meta = session.read_meta(path)
    moves = len(pos) > 0 and float(np.ptp(pos, axis=0).max()) >= STATIC_SPAN_M
    static = meta.get("platform") == "static" or (len(pos) > 0 and not moves)
    return _Session(meas, t, pos, meta.get("origin_llh"), static, meta)


def _truth_at(t_ns, truth_t, truth_pos) -> np.ndarray:
    x = np.asarray(t_ns, dtype=float) - truth_t[0]
    grid = (truth_t - truth_t[0]).astype(float)
    return np.column_stack([np.interp(x, grid, truth_pos[:, i]) for i in range(3)])


def _raw(group: list[Measurement]) -> np.ndarray:
    v = np.array([m.value[0] for m in group], dtype=float)
    period = group[0].meta.get("ambiguity_m")
    return np.unwrap(v, period=period) if period else v


def _residual(group: list[Measurement], s: _Session, path) -> np.ndarray:
    kind = group[0].kind
    has_truth = len(s.truth_t) > 0
    expected = _truth_at([m.t_ns for m in group], s.truth_t, s.truth_pos) if has_truth else None
    if kind == "pseudorange":
        emitter = emitter_enu(group[0].meta, s.origin_llh)
        if emitter is not None and has_truth:
            return _raw(group) - np.linalg.norm(expected - emitter, axis=1)
        if s.static:
            return _raw(group)  # the true range is constant: the trend removal takes it out
        raise ValueError(f"{path}: {group[0].emitter} has no position and the receiver moves")
    if kind == "altitude":
        return _raw(group) - (expected[:, 2] if has_truth else 0.0)
    xy = np.array([m.value[:2] for m in group], dtype=float)
    if not has_truth and not s.static:
        raise ValueError(f"{path} has no /truth, so its position residuals can't be computed")
    return np.linalg.norm(xy - (expected[:, :2] if has_truth else np.median(xy, axis=0)), axis=1)


def residuals(
    path, source: str, first_s: float | None = None
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per channel: (seconds since the source's first record, detrended residual).

    first_s keeps only the first first_s seconds of the source, so sessions of different
    lengths are compared over the same span.
    """
    s = _load(path)
    meas = [
        m for m in s.meas if m.source == source and m.kind in KINDS and m.receiver == "payload"
    ]
    if not meas:
        return {}
    start = min(m.t_ns for m in meas)
    if first_s is not None:
        meas = [m for m in meas if m.t_ns < start + first_s * 1e9]
    channels: dict[str, list[Measurement]] = {}
    for m in sorted(meas, key=lambda m: m.t_ns):
        arc = m.meta.get("arc")
        name = (m.emitter or source) + ("" if arc is None else f"#{arc}")
        channels.setdefault(f"{name}/{m.kind}", []).append(m)
    out = {}
    for name, group in channels.items():
        r = _residual(group, s, path)
        seconds = np.array([(m.t_ns - start) / 1e9 for m in group])
        if len(r) > 2:
            trend = np.polyval(np.polyfit(seconds - seconds[0], r, 1), seconds - seconds[0])
        else:
            trend = r.mean()
        out[name] = (seconds, r - trend)
    return out


def statistics(path, source: str, first_s: float | None = None) -> dict[str, float]:
    """Noise size, how long errors persist, and how often the channel is present."""
    channels = residuals(path, source, first_s)
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


def table(sim, real, source: str, first_s: float | None = None) -> str:
    a, b = statistics(sim, source, first_s), statistics(real, source, first_s)
    rows = [f"| Statistic ({source}) | Simulated | Real | Gap |", "| --- | --- | --- | --- |"]
    rows += [f"| {k} | {a[k]:.3f} | {b[k]:.3f} | {a[k] - b[k]:+.3f} |" for k in STATISTICS]
    return "\n".join(rows)


def plot(sim, real, source: str, out: str | Path, first_s: float | None = None) -> Path:
    """Both residual distributions on one figure, as ADR-0015 asks."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    for label, path in (("simulated", sim), ("real", real)):
        values = np.concatenate([r for _, r in residuals(path, source, first_s).values()])
        ax.hist(values, bins=60, density=True, histtype="step", label=label)
    span = "" if first_s is None else f", first {first_s:g} s"
    ax.set(xlabel=f"{source} residual after trend removal{span}", ylabel="density")
    ax.set_title(f"{session.session_name(sim)} vs {session.session_name(real)}", fontsize=9)
    ax.legend()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def inject(path, faults: list[dict], seed: int = 0):
    """Apply software faults to a recorded session (ADR-0015).

    Returns (measurements, t0_ns, events). Fault times count from the session's first
    measurement. Attacks that need the true position (meaconing, jamming_zone) need `/truth`.
    """
    s = _load(path)
    if not s.meas:
        raise ValueError(f"{path} has no measurements to inject faults into")
    meas = sorted(s.meas, key=lambda m: m.t_ns)
    t0 = meas[0].t_ns

    def truth_pos(seconds) -> np.ndarray:
        if not len(s.truth_t):
            raise ValueError(f"{path} has no /truth, which this fault needs")
        return _truth_at(t0 + np.atleast_1d(seconds) * 1e9, s.truth_t, s.truth_pos)

    emitters = {}  # emitter positions the records carry (attacks such as reference_moved)
    for m in meas:
        if m.emitter and m.emitter not in emitters:
            pos = emitter_enu(m.meta, s.origin_llh) if s.origin_llh is not None else None
            if pos is not None:
                emitters[m.emitter] = [float(x) for x in pos]
    ref = s.meta.get("reference")
    ctx = attacks.Context(
        t0_ns=t0,
        origin_llh=s.origin_llh,
        truth_pos=truth_pos,
        rng=np.random.default_rng(seed),
        emitters=emitters,
        # the surveyed position: a real session knows no truer one
        reference_enu=(
            llh_to_enu(ref["position_llh"], s.origin_llh) if ref and s.origin_llh else None
        ),
    )
    changed, events = attacks.apply(meas, faults, ctx)
    changed.sort(key=lambda m: (m.t_ns, m.source, m.kind, m.emitter, m.receiver))
    return changed, t0, events
