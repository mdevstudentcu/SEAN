"""Per-source measurement models for simulation.

Each model takes truth at its own sample times and returns Measurements. Error parameters come
from the scenario YAML; values marked TBC there should be replaced with numbers measured in the
RF survey and real sessions.
"""

from __future__ import annotations

import numpy as np

from pnt.core.measurement import Measurement


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
    **_,
) -> list[Measurement]:
    """Range to each emitter + that emitter's clock bias (random walk) + white noise.

    Models terrestrial SoOP (LTE, NR) whose transmitter clocks are unknown to us.
    """
    out: list[Measurement] = []
    dt = np.diff(ts_ns, prepend=ts_ns[0]) / 1e9
    for i, e in enumerate(emitters):
        bias = rng.uniform(-init_bias_m, init_bias_m) + np.cumsum(
            rng.normal(0.0, clock_rw_m * np.sqrt(np.maximum(dt, 1e-9)))
        )
        rho = np.linalg.norm(pos - e, axis=1) + bias + rng.normal(0.0, sigma_m, len(pos))
        if emitters_llh is not None:  # real transmitter: carry lat/lon, as a front-end would
            meta = {"emitter_llh": [float(x) for x in emitters_llh[i]]}
        else:
            meta = {"emitter_enu": [float(x) for x in e]}
        out += [
            Measurement(
                t_ns=int(t),
                source=source,
                kind="pseudorange",
                emitter=f"{source}:sim{i}",
                value=(float(r),),
                sigma=(sigma_m,),
                meta=meta,
            )
            for t, r in zip(ts_ns, rho, strict=True)
        ]
    return out
