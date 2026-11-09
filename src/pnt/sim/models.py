"""Per-source measurement models for simulation.

Each model takes truth at its own sample times and returns Measurements. Error parameters come
from the scenario YAML; values marked TBC there should be replaced with numbers measured in the
RF survey and real sessions.
"""

from __future__ import annotations

import numpy as np

from pnt.core.measurement import Measurement

C_MPS = 299_792_458.0


def gnss(
    ts_ns,
    pos,
    rng,
    sigma_m: float,
    clock_s=None,
    time_sigma_ns: float | None = None,
    health: bool = False,
    **_,
) -> list[Measurement]:
    """Receiver fixes. Optionally also the receiver's time solution (`time`: local clock minus
    GPS time, needs `clock_s`, the true local clock offset at each sample) and a health report
    (`gnss_health`: jam indicator 0..1, satellites used, HDOP)."""
    noisy = pos + rng.normal(0.0, sigma_m, pos.shape) * np.array([1.0, 1.0, 1.5])
    sig = (sigma_m, sigma_m, 1.5 * sigma_m)
    out = [
        Measurement(t_ns=int(t), source="gnss", kind="position_enu", value=tuple(p), sigma=sig)
        for t, p in zip(ts_ns, noisy, strict=True)
    ]
    if time_sigma_ns is not None:
        if clock_s is None:
            raise ValueError("time_sigma_ns needs a `clock:` model in the scenario")
        meas_t = clock_s + rng.normal(0.0, time_sigma_ns * 1e-9, len(ts_ns))
        out += [
            Measurement(
                t_ns=int(t),
                source="gnss",
                kind="time",
                value=(float(c),),
                sigma=(time_sigma_ns * 1e-9,),
            )  # fmt: skip
            for t, c in zip(ts_ns, meas_t, strict=True)
        ]
    if health:
        from pnt.sim.attacks import NOMINAL_HEALTH

        out += [
            Measurement(
                t_ns=int(t),
                source="gnss",
                kind="gnss_health",
                value=NOMINAL_HEALTH,
                sigma=(0.0, 0.0, 0.0),
            )  # fmt: skip
            for t in ts_ns
        ]
    return out


def baro(ts_ns, pos, rng, sigma_m: float, bias_sigma_m: float = 1.0, **_) -> list[Measurement]:
    bias = rng.normal(0.0, bias_sigma_m)
    alt = pos[:, 2] + bias + rng.normal(0.0, sigma_m, len(pos))
    return [
        Measurement(t_ns=int(t), source="baro", kind="altitude", value=(a,), sigma=(sigma_m,))
        for t, a in zip(ts_ns, alt, strict=True)
    ]


def synthetic_emitters(rng, n: int, ring_radius_m: tuple[float, float], height_m=(30.0, 60.0)):
    """SYNTHETIC transmitter positions. Replace with data/reference extracts for real geometry."""
    ang = rng.uniform(0, 2 * np.pi, n)
    r = rng.uniform(*ring_radius_m, n)
    h = rng.uniform(*height_m, n)
    return np.column_stack([r * np.cos(ang), r * np.sin(ang), h])


def pseudoranges(
    ts_ns,
    pos,
    rng,
    source: str,
    emitters: np.ndarray,
    sigma_m: float,
    clock_rw_m: float,
    init_bias_m: float,
    emitters_llh=None,
    told_emitters: np.ndarray | None = None,
    told_sigma_m: float | None = None,
    clock_s: np.ndarray | None = None,
    drift_sigma_mps: float = 0.0,
    multipath: dict | None = None,
    dropout: dict | None = None,
    ray_table: dict | None = None,
    max_excess_m: float = 300.0,
    **_,
) -> list[Measurement]:
    """Range to each emitter + clock terms + lingering error + white noise.

    Models terrestrial SoOP (LTE, NR) whose transmitter clocks are unknown to us. Beyond the base
    model, each of these is optional and off by default (issue #46):
    - clock_s: the receiver's clock offset (s). It shifts every tower's reading together.
    - drift_sigma_mps: each tower's own constant clock drift, drawn per tower.
    - multipath: {sigma_m, tau_s}, a first-order Gauss-Markov error per tower, as a reflection
      that stays wrong for many seconds.
    - dropout: {availability, block_s}, each tower heard or lost in random blocks of time.
    - told_emitters / told_sigma_m: what the filter is told, when that differs from the truth.
      `emitters` and `sigma_m` always describe the truth.
    - ray_table: {tower index: (times, excess delay m, NaN if no path)}, from a ray tracer. Adds
      the excess delay of the nearest sample in time, and loses the tower with no path or beyond
      max_excess_m (TBC).
    """
    out: list[Measurement] = []
    t_s = (ts_ns - ts_ns[0]) / 1e9
    dt = np.diff(ts_ns, prepend=ts_ns[0]) / 1e9
    reported_sigma = sigma_m if told_sigma_m is None else told_sigma_m
    for i, e in enumerate(emitters):
        bias = rng.uniform(-init_bias_m, init_bias_m) + np.cumsum(
            rng.normal(0.0, clock_rw_m * np.sqrt(np.maximum(dt, 1e-9)))
        )
        rho = np.linalg.norm(pos - e, axis=1) + bias + rng.normal(0.0, sigma_m, len(pos))
        if clock_s is not None:
            rho = rho + C_MPS * clock_s
        if drift_sigma_mps:
            rho = rho + rng.normal(0.0, drift_sigma_mps) * t_s
        if multipath:
            rho = rho + _gauss_markov(rng, dt, multipath["sigma_m"], multipath["tau_s"])
        keep = _available(rng, t_s, dropout) if dropout else np.ones(len(ts_ns), bool)
        if ray_table is not None:
            times, excess = ray_table[i]
            at = excess[np.searchsorted((times[1:] + times[:-1]) / 2, t_s)]
            keep &= ~np.isnan(at) & (np.nan_to_num(at) <= max_excess_m)
            rho = rho + np.nan_to_num(at)
        if emitters_llh is not None:  # real transmitter: carry lat/lon, as a front-end would
            meta = {"emitter_llh": [float(x) for x in emitters_llh[i]]}
        else:
            told = e if told_emitters is None else told_emitters[i]
            meta = {"emitter_enu": [float(x) for x in told]}
        out += [
            Measurement(
                t_ns=int(t),
                source=source,
                kind="pseudorange",
                emitter=f"{source}:sim{i}",
                value=(float(r),),
                sigma=(reported_sigma,),
                meta=meta,
            )
            for t, r in zip(ts_ns[keep], rho[keep], strict=True)
        ]
    return out


def _gauss_markov(rng, dt: np.ndarray, sigma: float, tau_s: float) -> np.ndarray:
    """First-order Gauss-Markov sequence with steady-state std `sigma` and time constant tau."""
    phi = np.exp(-dt / tau_s)
    x = np.empty(len(dt))
    x[0] = rng.normal(0.0, sigma)
    for k in range(1, len(dt)):
        x[k] = phi[k] * x[k - 1] + rng.normal(0.0, sigma * np.sqrt(1.0 - phi[k] ** 2))
    return x


def _available(rng, t_s: np.ndarray, dropout: dict) -> np.ndarray:
    """True where a tower is heard: on or off for whole blocks, independently per block."""
    blocks = (t_s // dropout["block_s"]).astype(int)
    return (rng.random(blocks.max() + 1) < dropout["availability"])[blocks]
