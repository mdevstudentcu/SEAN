"""Load a scenario YAML and generate truth + measurements, with faults injected (ADR-0004).

Faults live here (and in sources), never in the estimator: the estimator must not know.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement, Truth
from pnt.core.time import s_to_ns, utc_to_gps_ns
from pnt.sim import attacks, models, trajectory

SCENARIO_DIR = Path(__file__).parent / "scenarios"
# Fixed scenario start so runs are reproducible (REQ-10): judging day, 18:00 UTC.
T0_NS = utc_to_gps_ns(datetime(2026, 11, 12, 18, 0, tzinfo=UTC))


@dataclass
class SimRun:
    name: str
    spec: dict
    seed: int
    truth: list[Truth]
    measurements: list[Measurement]
    events: list[tuple[int, str]] = field(default_factory=list)
    emitters: dict[str, list[float]] = field(default_factory=dict)


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def load_named(name: str) -> dict:
    """Load a bundled scenario by plain name only (e.g. 'spoof-ramp').

    For names read from session files, which are untrusted input (AGENTS.md): no paths, no
    suffixes, so a session cannot point the loader at an arbitrary file.
    """
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"not a scenario name: {name!r}")
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no bundled scenario named {name!r}")
    return load(str(path))


def load(name_or_path: str) -> dict:
    p = Path(name_or_path)
    if not p.suffix:
        p = SCENARIO_DIR / f"{name_or_path}.yaml"
    with open(p) as f:
        spec = yaml.safe_load(f)
    spec.setdefault("name", p.stem)
    return spec


def _times(duration_s: float, rate_hz: float) -> np.ndarray:
    return np.arange(0.0, duration_s, 1.0 / rate_hz)


def generate(spec: dict, seed: int = 0) -> SimRun:
    rng = np.random.default_rng(seed)
    dur = float(spec["duration_s"])
    traj = {**spec["trajectory"], "_origin_llh": spec.get("origin_llh")}  # for points_llh

    t_truth = _times(dur, 1.0 / spec.get("dt_s", 0.1))
    pos_t, vel_t = trajectory.make(traj, t_truth)
    clock_t = _clock(spec.get("clock"), t_truth, rng)
    truth = [
        Truth(t_ns=T0_NS + s_to_ns(t), pos_enu=tuple(p), vel_enu=tuple(v), clock_bias_s=float(c))
        for t, p, v, c in zip(t_truth, pos_t, vel_t, clock_t, strict=True)
    ]

    meas: list[Measurement] = []
    emitters: dict[str, list[float]] = {}
    for source, cfg in spec.get("sources", {}).items():
        cfg = dict(cfg)
        ts = _times(dur, cfg.pop("rate_hz"))
        ts_ns = T0_NS + np.round(ts * 1e9).astype(np.int64)
        pos, _ = trajectory.make(traj, ts)
        model = cfg.pop("model", source)
        if model == "gnss":
            clock_s = np.interp(ts, t_truth, clock_t) if "clock" in spec else None
            meas += models.gnss(ts_ns, pos, rng, clock_s=clock_s, **cfg)
        elif model == "baro":
            meas += models.baro(ts_ns, pos, rng, **cfg)
        elif model == "pseudorange":
            em_llh = cfg.pop("emitters_llh", None)
            if em_llh is not None:  # real transmitter positions (data/reference)
                em = np.array([llh_to_enu(x, spec["origin_llh"]) for x in em_llh])
            else:
                em = models.synthetic_emitters(
                    rng, cfg.pop("n_emitters"), tuple(cfg.pop("ring_radius_m"))
                )
            for i, e in enumerate(em):
                emitters[f"{source}:sim{i}"] = [float(x) for x in e]
            meas += models.pseudoranges(
                ts_ns, pos, rng, source=source, emitters=em, emitters_llh=em_llh, **cfg
            )
        else:
            raise ValueError(f"unknown model {model!r} for source {source!r}")

    ctx = attacks.Context(
        t0_ns=T0_NS,
        origin_llh=spec.get("origin_llh"),
        truth_pos=lambda t: trajectory.make(traj, np.atleast_1d(t))[0],
        rng=rng,
    )
    meas, events = attacks.apply(meas, spec.get("faults", []), ctx)
    meas.sort(key=lambda m: (m.t_ns, m.source, m.kind, m.emitter))
    return SimRun(spec["name"], spec, seed, truth, meas, events, emitters)


def _clock(spec: dict | None, t: np.ndarray, rng) -> np.ndarray:
    """True local clock offset from GPS time (s): offset + drift + random walk. Zero if the
    scenario has no `clock:` block. Parameters are placeholders until measured (ADR-0015)."""
    if not spec:
        return np.zeros_like(t)
    dt = np.diff(t, prepend=t[0])
    walk = np.cumsum(rng.normal(0.0, spec.get("rw_ns", 0.0) * 1e-9 * np.sqrt(dt)))
    return spec.get("offset_s", 0.0) + spec.get("drift_ppb", 0.0) * 1e-9 * t + walk
