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
- spoof_zone: position moved by offset_enu_m within radius_m of a fixed place, quality untouched
  (a spoofer at a fixed place)
- gps_no_fix: position and time stop but the receiver keeps reporting health
- gps_low_sats: few satellites reported while the position stays good (false-alarm check)
- baro_drift: the barometer drifts at rate_mps (sensor degradation)
- tower_clock_step: one tower's clock offset changes by offset_m (not an attack on GNSS: a
  tower fault that a filter must not confuse with a receiver clock change). Both receivers hear
  the same tower, so it reaches the reference station's records too.
- reference_moved: the reference station's antenna moves by offset_enu_m while the session keeps
  its old surveyed position (a knocked mast, a wrong survey). Not an attack on GNSS: the base as
  its own fault hypothesis (ADR-0020)
- reference_clock_step: the reference station's clock steps by offset_m
- tower_holdover: towers lose GNSS with the payload (wide-area jamming) and their clocks drift in
  holdover from start_s: a growing clock error on their pseudoranges (ADR-0022, ADR-0024)
- imu_degradation: the IMU's bias steps or ramps, its noise grows, it sticks, or it drops out
  (sensor degradation)
- hostile_power: a jammer's transmit power steps, ramps or is modulated (ADR-0025: the adversary
  controls its power). Touches the hostile beacon's `rssi` records (`sim/hostile.py`)
- hostile_moves: a jammer moves from where it was located, at velocity_enu_mps (a honeypot
  that tries to drag a filter using it as a beacon). Its `rssi` records follow the true geometry
  while the told position stays put

Any fault may name a `receiver` (`payload` or `reference`) to touch only that receiver's records;
without one it touches both.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import msgspec
import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.core.time import s_to_ns
from pnt.sim import models
from pnt.sim.sensors import DEG, G

# Nominal GNSS health reported outside any jamming: (jam indicator 0..1, satellites, HDOP)
NOMINAL_HEALTH = (0.0, 10.0, 1.0)
NO_FIX_HDOP = 99.0  # what receivers conventionally report with no geometry


@dataclass
class Context:
    t0_ns: int
    origin_llh: list[float] | None
    truth_pos: Callable[[np.ndarray], np.ndarray]  # seconds since t0 -> (N, 3) ENU
    rng: np.random.Generator
    emitters: dict[str, list[float]] = field(default_factory=dict)  # true ENU, by emitter ID
    reference_enu: np.ndarray | None = None  # the reference station's true position
    # (sites, builders) as `scenario.tower_groups` gives them, when the scenario groups its tower
    # clocks (`tower_clocks:`, ADR-0022); None otherwise
    tower_groups: tuple[dict[str, str], dict[str, str]] | None = None
    # Jammers placed by `jamming_zone` faults when the scenario measures their power
    # (`jammer_power`, #93): emitter -> {"enu": true position, "n": path-loss exponent}
    jammers: dict[str, dict] = field(default_factory=dict)


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
        m.source == f.get("source", "gnss")
        and m.t_ns >= start
        and (end is None or m.t_ns < end)
        and f.get("receiver", m.receiver) == m.receiver
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


@attack("gps_no_fix")
def gps_no_fix(meas, f, ctx, start, end):
    """The receiver keeps reporting, but has no position or time to give."""
    out = []
    for m in meas:
        if _active(m, f, start, end):
            if m.kind in ("position_enu", "time"):
                continue
            if m.kind == "gnss_health":
                m = _replace(m, value=(m.value[0], 0.0, NO_FIX_HDOP))
        out.append(m)
    return out, [(start, f"GPS reports no fix{_window(f, end)}")]


@attack("gps_low_sats")
def gps_low_sats(meas, f, ctx, start, end):
    """Few satellites and poor geometry, while the position stays good: a false-alarm check."""
    sats, hdop = float(f.get("satellites", 3)), float(f.get("hdop", 4.0))
    out = [
        _replace(m, value=(m.value[0], sats, hdop))
        if _active(m, f, start, end) and m.kind == "gnss_health"
        else m
        for m in meas
    ]
    return out, [(start, f"GPS down to {sats:.0f} satellites{_window(f, end)}")]


@attack("baro_drift")
def baro_drift(meas, f, ctx, start, end):
    """A barometer reading that drifts away at rate_mps (sensor degradation)."""
    out = [
        _replace(m, value=(m.value[0] + f["rate_mps"] * _since(m, start),))
        if _active(m, f, start, end) and m.kind == "altitude"
        else m
        for m in meas
    ]
    return out, [(start, f"barometer drifts at {f['rate_mps']} m/s{_window(f, end)}")]


@attack("tower_clock_step")
def tower_clock_step(meas, f, ctx, start, end):
    out = [
        _replace(m, value=(m.value[0] + f["offset_m"],))
        if _active(m, f, start, end) and m.kind == "pseudorange" and m.emitter == f["emitter"]
        else m
        for m in meas
    ]
    return out, [(start, f"{f['emitter']} clock steps by {f['offset_m']} m{_window(f, end)}")]


@attack("reference_moved")
def reference_moved(meas, f, ctx, start, end):
    """The base's antenna is offset_enu_m from where the session says it is: each of its ranges
    changes by the true geometry, while the told survey stays put."""
    if ctx.reference_enu is None:
        raise ValueError("reference_moved needs a scenario with a `reference:` station")
    base = np.asarray(ctx.reference_enu, float)
    moved = base + np.asarray(f["offset_enu_m"], float)
    f = {**f, "receiver": "reference"}
    shift = {
        e: float(np.linalg.norm(moved - pos) - np.linalg.norm(base - pos))
        for e, pos in ctx.emitters.items()
    }
    out = [
        _replace(m, value=(m.value[0] + shift[m.emitter],))
        if _active(m, f, start, end) and m.kind == "pseudorange"
        else m
        for m in meas
    ]
    off = np.linalg.norm(f["offset_enu_m"])
    return out, [(start, f"reference station moved {off:.0f} m from its survey{_window(f, end)}")]


@attack("reference_clock_step")
def reference_clock_step(meas, f, ctx, start, end):
    f = {**f, "receiver": "reference"}
    out = [
        _replace(m, value=(m.value[0] + f["offset_m"],))
        if _active(m, f, start, end) and m.kind == "pseudorange"
        else m
        for m in meas
    ]
    return out, [(start, f"reference clock steps by {f['offset_m']} m{_window(f, end)}")]


@attack("jamming_zone")
def jamming_zone(meas, f, ctx, start, end):
    """A jammer at a fixed place. Between onset_m and radius_m from it, accuracy degrades
    smoothly (noise and reported sigma grow up to max_sigma_scale, health worsens); inside
    radius_m, position and time are lost. The jammer's own received power (`rssi`, the hostile
    beacon's records) is never lost: jamming raises it."""
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
        elif m.kind == "rssi":
            continue  # the jammer's power: what the jamming raises, not loses
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


@attack("spoof_zone")
def spoof_zone(meas, f, ctx, start, end):
    """A spoofer at a fixed place: within radius_m of it the position is moved by offset_enu_m,
    and the reported sigma is left alone (spoofing keeps the quality indicators high). The
    aircraft around us see the same zone (`pnt.sim.adsb`)."""
    center = llh_to_enu(f["center_llh"], ctx.origin_llh)
    off = np.asarray(f["offset_enu_m"], dtype=float)
    idx = [i for i, m in enumerate(meas) if _active(m, f, start, end) and m.kind == "position_enu"]
    out = list(meas)
    if idx:
        t = np.array([(meas[i].t_ns - ctx.t0_ns) / 1e9 for i in idx])
        dist = np.linalg.norm(ctx.truth_pos(t)[:, :2] - center[:2], axis=1)
        for i, d in zip(idx, dist, strict=True):
            if d < f["radius_m"]:
                out[i] = _replace(meas[i], value=tuple(np.add(meas[i].value, off)))
    c = ", ".join(f"{x:.4f}" for x in f["center_llh"][:2])
    moved = f"moved {np.linalg.norm(off):.0f} m within {f['radius_m']} m"
    return out, [(start, f"spoof zone at ({c}): {moved}")]


# Holdover classes of a tower's timing reference, as the frequency offset it has when it loses
# GNSS (drift_mps: 1-sigma, drawn per oscillator at onset) and its frequency wander afterwards
# (drift_rw_mps, m/s/sqrt(s)), in the units of `models.oscillator`. 1 m/s is 3.34 ppb. All TBC.
HOLDOVER_GRADES = {
    "ocxo": {
        # TBC. "In holdover an OCXO-class reference drifts by microseconds per hour" (research.md,
        # finding 4, citing Sharma, Owens & Kiernan, arXiv 2607.11398, 2026). 1 us/h as the
        # 1-sigma onset frequency offset: 2.78e-10 x c = 0.083 m/s. The low end of that phrase.
        "drift_mps": 0.083,
        # TBC. h_-2 = 4e-26 for an OCXO (Shamaei, Khalife & Kassas, IEEE TWC 2018), the value the
        # realistic and worst sets' tower_clocks use: c sqrt(2 pi^2 h_-2) = 2.7e-4 m/s/sqrt(s)
        "drift_rw_mps": 2.7e-4,
    },
    "rubidium": {
        # TBC, unsourced: systems/research.md gives no rubidium holdover figure (its summary of
        # Winter 2024 names a rubidium reference, no holdover drift). 1 us/day: 1.16e-11 x c
        # = 0.0035 m/s
        "drift_mps": 0.0035,
        # TBC, unsourced: a tenth of the OCXO wander
        "drift_rw_mps": 2.7e-5,
    },
}
# TBC: no source gives a builder's share. The variance share of the holdover drift and wander that
# all towers of one builder have in common (a builder-wide timing source in holdover, ADR-0022),
# the same even split the realistic and worst sets use for their tower clocks.
HOLDOVER_BUILDER_SHARE = 0.5
_HOLDOVER_GRID_S = 1.0  # numerical: holdover clocks are drawn on this grid and interpolated


def _holdover_towers(f: dict, ctx, source: str) -> list[str]:
    towers = [e for e in ctx.emitters if e.startswith(f"{source}:")]
    if "emitters" in f:
        unknown = set(f["emitters"]) - set(towers)
        if unknown:
            raise ValueError(f"tower_holdover: no {source} emitters {sorted(unknown)}")
        return [e for e in towers if e in f["emitters"]]
    if "fraction" in f:
        k = int(round(float(f["fraction"]) * len(towers)))
        return [towers[i] for i in sorted(ctx.rng.choice(len(towers), k, replace=False))]
    return towers


@attack("tower_holdover")
def tower_holdover(meas, f, ctx, start, end):
    """Wide-area jamming takes GNSS from the towers' timing references too (ADR-0024: GNSS-timed).
    From start_s each affected tower's clock leaves its disciplined state and drifts as a
    `models.oscillator` started at zero offset (no step at onset) with a frequency offset drawn at
    onset and frequency wander. The error adds to the sim's normal tower clock.

    - grade: `ocxo` (default) or `rubidium` (HOLDOVER_GRADES); drift_mps and drift_rw_mps
      override it.
    - emitters (IDs) or fraction (of the source's towers, drawn with the seed) leave the rest
      untouched: not every site is GNSS-timed. Default: all.
    - When the scenario groups its tower clocks (`tower_clocks:`), builder_share of the variance
      is one oscillator per builder, shared by its towers, and the rest one per site. Otherwise
      each tower drifts alone. Each tower's own spread is the same either way.
    - After end_s the error stays where it reached (TBC: relocking and slewing back is not
      modelled). Both receivers hear the same tower, so the reference station's ranges move too.
    """
    f = {"source": "lte", **f}
    source = f["source"]
    grade = f.get("grade", "ocxo")
    if grade not in HOLDOVER_GRADES:
        raise ValueError(f"tower_holdover grade {grade!r} (known: {sorted(HOLDOVER_GRADES)})")
    size = {**HOLDOVER_GRADES[grade], **{k: f[k] for k in ("drift_mps", "drift_rw_mps") if k in f}}
    towers = _holdover_towers(f, ctx, source)

    sites, builders = ctx.tower_groups or ({}, {})
    share = float(f.get("builder_share", HOLDOVER_BUILDER_SHARE)) if ctx.tower_groups else 0.0
    site_of = {e: sites.get(e, e) for e in towers}
    builder_of = {e: builders.get(site_of[e]) for e in towers}

    hit = [i for i, m in enumerate(meas) if _active(m, f, start, None)]
    hit = [i for i in hit if meas[i].kind == "pseudorange" and meas[i].emitter in site_of]
    out = list(meas)
    if hit:
        last = max(meas[i].t_ns for i in hit) if end is None else end
        span = (last - start) / 1e9
        grid = np.append(np.arange(0.0, span, _HOLDOVER_GRID_S), span)

        def draw(var_share: float) -> np.ndarray:
            k = np.sqrt(var_share)
            return models.oscillator(
                ctx.rng,
                grid,
                drift_mps=k * size["drift_mps"],
                drift_rw_mps=k * size["drift_rw_mps"],
            )

        by_builder = {b: draw(share) for b in sorted({b for b in builder_of.values() if b})}
        by_site = {s: draw(1.0 - share) for s in sorted(set(site_of.values()))}
        clock = {
            e: by_site[site_of[e]] + by_builder.get(builder_of[e], 0.0) for e in sorted(site_of)
        }
        for i in hit:
            m = meas[i]
            err = np.interp(_since(m, start), grid, clock[m.emitter])  # holds after end_s
            out[i] = _replace(m, value=(m.value[0] + float(err),))
    return out, [
        (start, f"{len(towers)} {source} towers drift in {grade} holdover{_window(f, end)}")
    ]


# IMU degradation sizes, all TBC. Bias steps default to the raw offsets the MPU-6050 datasheet
# allows before start-up calibration (sim/sensors.py provenance): as if that calibration were lost.
# TBC. Datasheet zero-g offset +/-50-80 mg (MPU-6000/6050 rev 3.4), the low end
IMU_ACCEL_STEP_MG = 50.0
IMU_GYRO_STEP_DPS = 20.0  # TBC. Datasheet zero-rate output +/-20 deg/s (MPU-6000/6050 rev 3.4)
IMU_NOISE_SCALE = 3.0  # TBC, unsourced: white noise this many times the nominal
_IMU_AXES = {"accel": (0, 1, 2), "gyro": (3, 4, 5)}  # columns of an accel_gyro value
_IMU_MODES = ("bias", "noise", "stuck", "dropout")


@attack("imu_degradation")
def imu_degradation(meas, f, ctx, start, end):
    """The IMU degrades in the window. Records keep their shape, timestamps, sigma and meta, so
    nothing tells the estimator (except `dropout`, whose records are gone).

    - mode `bias`: accel_step_mg / gyro_step_dps from start_s, plus accel_rate_mg_per_s /
      gyro_rate_dps_per_s times the time since start_s (a ramp; set the step to 0 for a pure
      ramp). Defaults: IMU_ACCEL_STEP_MG, IMU_GYRO_STEP_DPS, no ramp.
    - mode `noise`: the white noise becomes noise_scale times the nominal. Only the noisy samples
      exist, so it adds white noise of sigma sqrt(noise_scale^2 - 1) x the record's sigma. Not
      re-quantized or clipped to the sensor's range.
    - mode `stuck`: the last reading before start_s repeats (the first in the window if none).
    - mode `dropout`: the records are lost.
    - sensor: `accel`, `gyro` or `both` (default); axes: body axes 0-2 (default all). They pick
      the columns bias, noise and stuck touch.
    """
    f = {"source": "imu", **f}
    mode = f.get("mode", "bias")
    if mode not in _IMU_MODES:
        raise ValueError(f"imu_degradation mode {mode!r} (known: {list(_IMU_MODES)})")
    sensor = f.get("sensor", "both")
    sensors_ = ("accel", "gyro") if sensor == "both" else (sensor,)
    if any(s not in _IMU_AXES for s in sensors_):
        raise ValueError(f"imu_degradation sensor {sensor!r} (known: accel, gyro, both)")
    axes = [int(a) for a in f.get("axes", (0, 1, 2))]
    cols = [_IMU_AXES[s][a] for s in sensors_ for a in axes]
    desc = f"IMU {mode} ({sensor}, axes {axes}){_window(f, end)}"

    hit = [i for i, m in enumerate(meas) if _active(m, f, start, end) and m.kind == "accel_gyro"]
    if mode == "dropout":
        drop = set(hit)
        return [m for i, m in enumerate(meas) if i not in drop], [(start, desc)]
    out = list(meas)
    if not hit:
        return out, [(start, desc)]
    vals = np.array([meas[i].value for i in hit], float)
    if mode == "bias":
        t = np.array([_since(meas[i], start) for i in hit])
        accel = (
            (f.get("accel_step_mg", IMU_ACCEL_STEP_MG) + f.get("accel_rate_mg_per_s", 0.0) * t)
            * 1e-3
            * G
        )
        gyro = (
            f.get("gyro_step_dps", IMU_GYRO_STEP_DPS) + f.get("gyro_rate_dps_per_s", 0.0) * t
        ) * DEG
        for c in cols:
            vals[:, c] += accel if c < 3 else gyro
    elif mode == "noise":
        k = float(f.get("noise_scale", IMU_NOISE_SCALE))
        if k < 1.0:
            raise ValueError("imu_degradation noise_scale below 1 would remove noise")
        sigma = np.array([meas[i].sigma for i in hit], float)
        vals[:, cols] += ctx.rng.normal(0.0, 1.0, (len(hit), len(cols))) * (
            sigma[:, cols] * np.sqrt(k**2 - 1.0)
        )
    else:  # stuck
        first = min((meas[i] for i in hit), key=lambda m: m.t_ns)
        before = [
            m
            for m in meas
            if m.kind == "accel_gyro"
            and m.source == first.source
            and m.receiver == first.receiver
            and m.t_ns < start
        ]
        held = np.array(max(before, key=lambda m: m.t_ns).value if before else first.value)
        vals[:, cols] = held[cols]
    for k, i in enumerate(hit):
        out[i] = _replace(meas[i], value=tuple(float(x) for x in vals[k]))
    return out, [(start, desc)]


def _hostile_records(meas, f, start, end) -> list[int]:
    """Indices of the hostile beacon's records the fault touches: `emitter` (default every
    jammer), in the window."""
    f = {"source": "gnss", **f}
    return [
        i
        for i, m in enumerate(meas)
        if _active(m, f, start, end)
        and m.kind == "rssi"
        and m.meta.get("hostile")
        and f.get("emitter", m.emitter) == m.emitter
    ]


@attack("hostile_power")
def hostile_power(meas, f, ctx, start, end):
    """The jammer changes its transmit power from start_s: step_db, plus rate_db_per_s times the
    time since start_s, plus a square wave of amplitude_db and period_s (power modulation, which
    widens jammer localisation error: ADR-0025). Defaults 0. `emitter` picks one jammer."""
    step, rate = float(f.get("step_db", 0.0)), float(f.get("rate_db_per_s", 0.0))
    amp, period = float(f.get("amplitude_db", 0.0)), float(f.get("period_s", 0.0))
    if amp and period <= 0:
        raise ValueError("hostile_power: amplitude_db needs a positive period_s")
    out = list(meas)
    for i in _hostile_records(meas, f, start, end):
        t = _since(meas[i], start)
        square = amp * (1.0 if (t % period) < period / 2 else -1.0) if amp else 0.0
        out[i] = _replace(meas[i], value=(meas[i].value[0] + step + rate * t + square,))
    desc = f"jammer power: {step} dB step, {rate} dB/s, {amp} dB square wave"
    return out, [(start, desc + _window(f, end))]


@attack("hostile_moves")
def hostile_moves(meas, f, ctx, start, end):
    """The jammer drives off at velocity_enu_mps from start_s (and stops at end_s), while the
    position it was located at stays what its records say. Each record's power changes by the
    true geometry, with the path-loss exponent the sim used. The GNSS denial footprint
    (`jamming_zone`) does not move with it: a limit of this fault."""
    if not ctx.jammers:
        raise ValueError("hostile_moves needs a jammer_power source")
    v = np.asarray(f["velocity_enu_mps"], float)
    idx = _hostile_records(meas, f, start, None)
    out = list(meas)
    if idx:
        t = np.array([(meas[i].t_ns - ctx.t0_ns) / 1e9 for i in idx])
        rx = ctx.truth_pos(t)
        for k, i in enumerate(idx):
            m = meas[i]
            j = ctx.jammers[m.emitter]
            moved_s = (
                _since(m, start) if end is None else min(_since(m, start), (end - start) / 1e9)
            )
            now = j["enu"] + v * moved_s
            d0 = max(float(np.linalg.norm(rx[k] - j["enu"])), 1.0)
            d1 = max(float(np.linalg.norm(rx[k] - now)), 1.0)
            out[i] = _replace(m, value=(m.value[0] - 10.0 * j["n"] * np.log10(d1 / d0),))
    speed = float(np.linalg.norm(v))
    return out, [(start, f"jammer moves at {speed:.1f} m/s{_window(f, end)}")]
