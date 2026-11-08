"""GNSS attack library (issue #4): faults injected in software, never transmitted.

ADR-0001 keeps the payload receive-only; ADR-0004 keeps faults out of the estimator. Each
attack rewrites the GNSS measurements a scenario (or a replayed real session) produced, the
way a real attack would show up at the receiver output. Which attacks matter most per use case
is the threat model's job (#29).

Attacks (`type` in a scenario's `faults:` list):
- outage: measurements removed in a window (jamming, blockage)
- spoof_ramp: position drifts at rate_mps (carry-off spoofing)
- spoof_jump: position offset by offset_enu_m (crude takeover)
- time_spoof: receiver time offset steps/ramps, position untouched (timing attack)
- meaconing: position and time lag by delay_s (record-and-rebroadcast)
- jamming_zone: accuracy degrades near a fixed place, lost inside it (e.g. in-car jammer)
- tower_clock_step: one tower's clock offset changes by offset_m (not an attack on GNSS: a
  tower fault that a filter must not confuse with a receiver clock change)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import msgspec
import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.core.time import s_to_ns

# Nominal GNSS health reported outside any jamming: (jam indicator 0..1, satellites, HDOP)
NOMINAL_HEALTH = (0.0, 10.0, 1.0)


@dataclass
class Context:
    t0_ns: int
    origin_llh: list[float] | None
    truth_pos: Callable[[np.ndarray], np.ndarray]  # seconds since t0 -> (N, 3) ENU
    rng: np.random.Generator


Event = tuple[int, str]
_ATTACKS: dict[str, Callable] = {}


def attack(name: str):
    def register(fn):
        _ATTACKS[name] = fn
        return fn

    return register


def apply(meas: list[Measurement], faults: list[dict], ctx: Context):
    """Apply each fault in order. Returns (measurements, events)."""
    events: list[Event] = []
    for f in faults:
        fn = _ATTACKS.get(f["type"])
        if fn is None:
            raise ValueError(f"unknown fault type {f['type']!r} (known: {sorted(_ATTACKS)})")
        start = ctx.t0_ns + s_to_ns(f.get("start_s", 0.0))
        end = ctx.t0_ns + s_to_ns(f["end_s"]) if "end_s" in f else None
        meas, ev = fn(meas, f, ctx, start, end)
        events += ev
    return meas, events


def _active(m: Measurement, f: dict, start: int, end: int | None) -> bool:
    return (
        m.source == f.get("source", "gnss") and m.t_ns >= start and (end is None or m.t_ns < end)
    )


def _replace(m: Measurement, **changes) -> Measurement:
    return msgspec.structs.replace(m, **changes)


def _since(m: Measurement, start: int) -> float:
    return (m.t_ns - start) / 1e9


def _window(f: dict, end: int | None) -> str:
    return f" until t={f['end_s']} s" if end is not None else ""


@attack("outage")
def outage(meas, f, ctx, start, end):
    out = [m for m in meas if not _active(m, f, start, end)]
    events = [(start, f"{f.get('source', 'gnss')} outage starts")]
    if end is not None:
        events.append((end, f"{f.get('source', 'gnss')} outage ends"))
    return out, events


@attack("spoof_ramp")
def spoof_ramp(meas, f, ctx, start, end):
    d = np.radians(f.get("direction_deg", 0.0))
    u = np.array([np.sin(d), np.cos(d), 0.0])  # clockwise from north
    out = []
    for m in meas:
        if _active(m, f, start, end) and m.kind == "position_enu":
            m = _replace(m, value=tuple(np.add(m.value, f["rate_mps"] * _since(m, start) * u)))
        out.append(m)
    return out, [(start, f"spoof ramp starts ({f['rate_mps']} m/s){_window(f, end)}")]


@attack("spoof_jump")
def spoof_jump(meas, f, ctx, start, end):
    off = np.asarray(f["offset_enu_m"], dtype=float)
    out = [
        _replace(m, value=tuple(np.add(m.value, off)))
        if _active(m, f, start, end) and m.kind == "position_enu"
        else m
        for m in meas
    ]
    return out, [(start, f"spoof jump of {np.linalg.norm(off):.0f} m{_window(f, end)}")]


@attack("time_spoof")
def time_spoof(meas, f, ctx, start, end):
    step = f.get("step_ns", 0.0) * 1e-9
    rate = f.get("rate_ns_per_s", 0.0) * 1e-9
    out = [
        _replace(m, value=(m.value[0] + step + rate * _since(m, start),))
        if _active(m, f, start, end) and m.kind == "time"
        else m
        for m in meas
    ]
    desc = f"time spoof: {f.get('step_ns', 0)} ns step + {f.get('rate_ns_per_s', 0)} ns/s"
    return out, [(start, desc + _window(f, end))]


@attack("meaconing")
def meaconing(meas, f, ctx, start, end):
    """Signals recorded and rebroadcast delay_s later: the receiver reports where it was."""
    delay = float(f["delay_s"])
    hit = [i for i, m in enumerate(meas) if _active(m, f, start, end) and m.kind == "position_enu"]
    out = list(meas)
    if hit:
        t = np.array([(meas[i].t_ns - ctx.t0_ns) / 1e9 for i in hit])
        now, then = ctx.truth_pos(t), ctx.truth_pos(t - delay)
        for k, i in enumerate(hit):
            noise = np.subtract(meas[i].value, now[k])  # keep the receiver's own noise
            out[i] = _replace(meas[i], value=tuple(then[k] + noise))
    out = [
        _replace(m, value=(m.value[0] + delay,))
        if _active(m, f, start, end) and m.kind == "time"
        else m
        for m in out
    ]
    return out, [(start, f"meaconing: GNSS replayed {delay} s late{_window(f, end)}")]


@attack("tower_clock_step")
def tower_clock_step(meas, f, ctx, start, end):
    out = [
        _replace(m, value=(m.value[0] + f["offset_m"],))
        if _active(m, f, start, end) and m.kind == "pseudorange" and m.emitter == f["emitter"]
        else m
        for m in meas
    ]
    return out, [(start, f"{f['emitter']} clock steps by {f['offset_m']} m{_window(f, end)}")]


@attack("jamming_zone")
def jamming_zone(meas, f, ctx, start, end):
    """A jammer at a fixed place. Between onset_m and radius_m from it, accuracy degrades
    smoothly (noise and reported sigma grow up to max_sigma_scale, health worsens); inside
    radius_m, position and time are lost."""
    center = llh_to_enu(f["center_llh"], ctx.origin_llh)
    r_in, r_on = float(f["radius_m"]), float(f["onset_m"])
    k_max = float(f.get("max_sigma_scale", 10.0))
    idx = [i for i, m in enumerate(meas) if _active(m, f, start, end)]
    if not idx:
        return meas, []
    t = np.array([(meas[i].t_ns - ctx.t0_ns) / 1e9 for i in idx])
    truth = ctx.truth_pos(t)
    dist = np.linalg.norm(truth[:, :2] - center[:2], axis=1)

    out: list[Measurement | None] = list(meas)
    for k, i in enumerate(idx):
        m, d = meas[i], dist[k]
        if d >= r_on:
            continue
        frac = 1.0 if d < r_in else (r_on - d) / (r_on - r_in)  # 0 at onset, 1 at the edge
        if m.kind == "gnss_health":
            jam, nsat, hdop = NOMINAL_HEALTH
            out[i] = _replace(
                m,
                value=(frac, 0.0 if d < r_in else round(nsat * (1 - 0.7 * frac)), hdop + 4 * frac),
            )
        elif d < r_in:
            out[i] = None  # lost lock
        elif m.kind == "position_enu":
            scale = 1 + (k_max - 1) * frac
            err = np.subtract(m.value, truth[k]) * scale
            out[i] = _replace(
                m, value=tuple(truth[k] + err), sigma=tuple(s * scale for s in m.sigma)
            )
    c = ", ".join(f"{x:.4f}" for x in f["center_llh"][:2])
    return [m for m in out if m is not None], [
        (start, f"jamming zone at ({c}): lost within {r_in:.0f} m, degraded within {r_on:.0f} m")
    ]
