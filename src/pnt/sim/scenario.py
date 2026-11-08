"""Load a scenario YAML and generate truth + measurements, with faults injected (ADR-0004).

Faults live here (and in sources), never in the estimator: the estimator must not know.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from pnt.core.measurement import Measurement, Truth
from pnt.core.time import s_to_ns, utc_to_gps_ns
from pnt.sim import models, trajectory

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
    traj = spec["trajectory"]

    t_truth = _times(dur, 1.0 / spec.get("dt_s", 0.1))
    pos_t, vel_t = trajectory.make(traj, t_truth)
    truth = [
        Truth(t_ns=T0_NS + s_to_ns(t), pos_enu=tuple(p), vel_enu=tuple(v))
        for t, p, v in zip(t_truth, pos_t, vel_t, strict=True)
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
            meas += models.gnss(ts_ns, pos, rng, **cfg)
        elif model == "baro":
            meas += models.baro(ts_ns, pos, rng, **cfg)
        elif model == "pseudorange":
            em = models.synthetic_emitters(
                rng, cfg.pop("n_emitters"), tuple(cfg.pop("ring_radius_m"))
            )
            for i, e in enumerate(em):
                emitters[f"{source}:sim{i}"] = [float(x) for x in e]
            meas += models.pseudoranges(ts_ns, pos, rng, source=source, emitters=em, **cfg)
        else:
            raise ValueError(f"unknown model {model!r} for source {source!r}")

    meas, events = apply_faults(meas, spec.get("faults", []))
    meas.sort(key=lambda m: (m.t_ns, m.source, m.emitter))
    return SimRun(spec["name"], spec, seed, truth, meas, events, emitters)


def apply_faults(meas: list[Measurement], faults: list[dict]):
    events: list[tuple[int, str]] = []
    for f in faults:
        start = T0_NS + s_to_ns(f["start_s"])
        end = T0_NS + s_to_ns(f["end_s"]) if "end_s" in f else None

        def active(m, f=f, start=start, end=end):
            return m.source == f["source"] and m.t_ns >= start and (end is None or m.t_ns < end)

        if f["type"] == "outage":
            meas = [m for m in meas if not active(m)]
            events.append((start, f"{f['source']} outage starts"))
            if end:
                events.append((end, f"{f['source']} outage ends"))
        elif f["type"] == "spoof_ramp":
            d = np.radians(f.get("direction_deg", 0.0))
            u = np.array([np.sin(d), np.cos(d), 0.0])  # direction clockwise from north
            out = []
            for m in meas:
                if active(m) and m.kind == "position_enu":
                    off = f["rate_mps"] * (m.t_ns - start) / 1e9 * u
                    m = Measurement(
                        t_ns=m.t_ns,
                        source=m.source,
                        kind=m.kind,
                        value=tuple(np.add(m.value, off)),
                        sigma=m.sigma,
                        emitter=m.emitter,
                        meta=m.meta,
                    )
                out.append(m)
            meas = out
            events.append((start, f"{f['source']} spoof ramp starts ({f['rate_mps']} m/s)"))
        else:
            raise ValueError(f"unknown fault type {f['type']!r}")
    return meas, events
