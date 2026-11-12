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


def baro(
    ts_ns,
    pos,
    rng,
    sigma_m: float,
    bias_sigma_m: float = 1.0,
    temp_m_per_k: float = 0.0,
    temperature_k: np.ndarray | None = None,
    **_,
) -> list[Measurement]:
    """Barometric altitude: truth + one bias per run + white noise. Optionally (#278, off by
    default) the chip tracks its own temperature: `temp_m_per_k` times the board's temperature
    change since start-up (`temperature_k`, `board_temperature`), with no draw of its own."""
    bias = rng.normal(0.0, bias_sigma_m)
    alt = pos[:, 2] + bias + rng.normal(0.0, sigma_m, len(pos))
    if temp_m_per_k:
        if temperature_k is None:
            raise ValueError("baro temp_m_per_k needs a `board_temperature:` block")
        alt = alt + temp_m_per_k * temperature_k
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
    clock_rw_m: float | None = None,
    init_bias_m: float | None = None,
    emitters_llh=None,
    told_emitters: np.ndarray | None = None,
    told_sigma_m: float | None = None,
    clock_s: np.ndarray | None = None,
    drift_sigma_mps: float = 0.0,
    multipath: dict | None = None,
    dropout: dict | None = None,
    ray_table: dict | None = None,
    max_excess_m: float = 300.0,
    tower_clock_m: np.ndarray | None = None,
    place_error_m: np.ndarray | None = None,
    receiver: str = "payload",
    tower_clocks_out: list | None = None,
    troposphere_m_per_km: np.ndarray | None = None,
    **_,
) -> list[Measurement]:
    """Range to each emitter + clock terms + lingering error + white noise.

    Models terrestrial SoOP (LTE, NR) whose transmitter clocks are unknown to us. Each tower's
    clock is either its own (a uniform offset within init_bias_m plus a clock_rw_m random walk),
    or given whole as `tower_clock_m` (towers x samples, m), which the scenario's `tower_clocks:`
    block builds from shared builder and site clocks (ADR-0022). Not both. Beyond the base model,
    each of these is optional and off by default (issue #46):
    - clock_s: the receiver's clock offset (s). It shifts every tower's reading together.
    - drift_sigma_mps: each tower's own constant clock drift, drawn per tower.
    - multipath: {sigma_m, tau_s}, a first-order Gauss-Markov error per tower, as a reflection
      that stays wrong for many seconds.
    - dropout: {availability, block_s}, each tower heard or lost in random blocks of time.
    - told_emitters / told_sigma_m: what the filter is told, when that differs from the truth.
      `emitters` and `sigma_m` always describe the truth.
    - place_error_m: (towers x samples, m) an error that depends only on where the receiver is
      (`place_error`), added as given.
    - ray_table: {tower index: (times, excess delay m, NaN if no path)}, from a ray tracer. Adds
      the excess delay of the nearest sample in time, and loses the tower with no path or beyond
      max_excess_m (TBC).
    - troposphere_m_per_km: (towers,) the troposphere's excess delay per km of true range, per
      tower (`troposphere`, #278): a near-horizontal path's delay grows with its length.

    A second receiver hearing the same towers (the reference station, ADR-0020) shares their
    clocks: pass a list as `tower_clocks_out` and each tower's clock (m, one row per tower, own
    or given) is appended to it; give those rows back as `tower_clock_m` for the other receiver.
    `receiver` labels the records.
    """
    own_clock = (clock_rw_m, init_bias_m, drift_sigma_mps or None)
    if tower_clock_m is None and None in own_clock[:2]:
        raise ValueError("pseudoranges need clock_rw_m and init_bias_m, or tower_clocks")
    if tower_clock_m is not None and any(x is not None for x in own_clock):
        raise ValueError("tower_clocks replaces clock_rw_m, init_bias_m and drift_sigma_mps")
    out: list[Measurement] = []
    t_s = (ts_ns - ts_ns[0]) / 1e9
    dt = np.diff(ts_ns, prepend=ts_ns[0]) / 1e9
    reported_sigma = sigma_m if told_sigma_m is None else told_sigma_m
    for i, e in enumerate(emitters):
        if tower_clock_m is None:
            bias = rng.uniform(-init_bias_m, init_bias_m) + np.cumsum(
                rng.normal(0.0, clock_rw_m * np.sqrt(np.maximum(dt, 1e-9)))
            )
        else:
            bias = tower_clock_m[i]
        geometric = np.linalg.norm(pos - e, axis=1)
        rho = geometric + bias + rng.normal(0.0, sigma_m, len(pos))
        if troposphere_m_per_km is not None:
            rho = rho + troposphere_m_per_km[i] * 1e-3 * geometric
        if clock_s is not None:
            rho = rho + C_MPS * clock_s
        if drift_sigma_mps and tower_clock_m is None:
            drift = rng.normal(0.0, drift_sigma_mps) * t_s
            rho = rho + drift
            bias = bias + drift
        if tower_clocks_out is not None:
            tower_clocks_out.append(bias)
        if multipath:
            rho = rho + _gauss_markov(rng, dt, multipath["sigma_m"], multipath["tau_s"])
        keep = _available(rng, t_s, dropout) if dropout else np.ones(len(ts_ns), bool)
        if place_error_m is not None:
            rho = rho + place_error_m[i]
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
                receiver=receiver,
                value=(float(r),),
                sigma=(reported_sigma,),
                meta=meta,
            )
            for t, r in zip(ts_ns[keep], rho[keep], strict=True)
        ]
    return out


def bearings(
    ts_ns,
    pos,
    rng,
    source: str,
    emitters: np.ndarray,
    sigma_deg: float,
    bias_deg: float = 0.0,
    max_range_m: float | None = None,
    cone_deg: float | None = None,
    emitters_llh=None,
) -> list[Measurement]:
    """VOR-style bearings (ICD `bearing`): from each station to the receiver, clockwise from true
    north, in rad.

    Each station has a fixed bias drawn once (site error, `bias_deg` 1-sigma) and white noise
    (`sigma_deg`). Nothing is reported beyond `max_range_m` (line of sight, service volume) or
    inside the cone of confusion above the station: elevation from the station over `cone_deg`.
    The reported sigma is the white noise only: the bias is for the estimator to model, as for
    the IMU (`pnt.sim.sensors`) and the tower clocks."""
    t_pos = np.asarray(pos, float)
    out: list[Measurement] = []
    sigma = np.deg2rad(sigma_deg)
    for i, e in enumerate(np.asarray(emitters, float)):
        d = t_pos - e
        horiz = np.hypot(d[:, 0], d[:, 1])
        keep = horiz > 0.0
        if max_range_m is not None:
            keep &= np.linalg.norm(d, axis=1) <= max_range_m
        if cone_deg is not None:
            keep &= np.degrees(np.arctan2(d[:, 2], horiz)) <= cone_deg
        truth = np.arctan2(d[:, 0], d[:, 1])  # east over north: clockwise from north
        bias = np.deg2rad(rng.normal(0.0, bias_deg)) if bias_deg else 0.0
        theta = truth + bias + np.deg2rad(rng.normal(0.0, sigma_deg, len(truth)))
        theta = np.mod(theta, 2 * np.pi)
        if emitters_llh is not None:
            meta = {"emitter_llh": [float(x) for x in emitters_llh[i]]}
        else:
            meta = {"emitter_enu": [float(x) for x in e]}
        out += [
            Measurement(
                t_ns=int(t),
                source=source,
                kind="bearing",
                emitter=f"{source}:sim{i}",
                value=(float(v),),
                sigma=(float(sigma),),
                meta=meta,
            )
            for t, v in zip(np.asarray(ts_ns)[keep], theta[keep], strict=True)
        ]
    return out


def oscillator(
    rng,
    t_s: np.ndarray,
    offset_m: float = 0.0,
    drift_mps: float = 0.0,
    offset_rw_m: float = 0.0,
    drift_rw_mps: float = 0.0,
) -> np.ndarray:
    """One clock's offset (m) at times t_s: the two-state (offset, drift) oscillator model of
    Shamaei, Khalife & Kassas (IEEE TWC 2018), started from a random offset and drift.

    - offset_m: initial offset, uniform in +-offset_m.
    - drift_mps: initial drift, normal with this std (m/s; 1 m/s is 3.3 ppb).
    - offset_rw_m: white frequency noise, m/sqrt(s), a random walk in offset. c * sqrt(h0 / 2).
    - drift_rw_mps: random-walk frequency noise, m/s/sqrt(s). c * sqrt(2 pi^2 h_-2).
    Drawn exactly per step, so any time spacing works. All zero: zeros, and nothing is drawn.
    """
    if not (offset_m or drift_mps or offset_rw_m or drift_rw_mps):
        return np.zeros(len(t_s))
    dt = np.diff(t_s, prepend=t_s[0])
    x0 = rng.uniform(-offset_m, offset_m)
    y0 = rng.normal(0.0, drift_mps)
    n = rng.normal(0.0, 1.0, (3, len(t_s)))
    w_drift = drift_rw_mps * np.sqrt(dt) * n[0]
    # The drift noise also moves the offset within a step: its exact share, given w_drift, is
    # dt/2 * w_drift plus an independent part of variance drift_rw^2 dt^3 / 12.
    w_offset = (
        offset_rw_m * np.sqrt(dt) * n[1]
        + dt / 2 * w_drift
        + drift_rw_mps * np.sqrt(dt**3 / 12) * n[2]
    )
    drift = y0 + np.cumsum(w_drift)
    drift_before = np.concatenate([[y0], drift[:-1]])
    return x0 + np.cumsum(drift_before * dt + w_offset)


def troposphere(rng, n: int, m_per_km) -> np.ndarray:
    """Each of `n` towers' tropospheric excess delay per km of range (m/km, #278).

    On a near-horizontal path the refractivity of the air near the ground (about 300 ppm) adds
    about 0.3 to 0.4 m per km of range (sources-research-20261111.md 18.2), and differently per
    tower: `m_per_km` is that value, or a [low, high] range drawn uniformly per tower (the
    spread stands for each path's own air). A tower clock absorbs the delay's constant part; the
    part that changes as the receiver moves stays."""
    if np.ndim(m_per_km) == 0:
        return np.full(n, float(m_per_km))
    low, high = (float(x) for x in m_per_km)
    if not 0.0 <= low <= high:
        raise ValueError(f"troposphere m_per_km needs 0 <= low <= high, not {m_per_km!r}")
    return rng.uniform(low, high, n)


def steering(rng, t_s: np.ndarray, jump_rate_hz: float, drift_mps: float) -> np.ndarray:
    """A GNSS-steered tower clock's offset (m) at times t_s: piecewise-constant drift (#278).

    Lapin et al. (IEEE TVT 2024) watched two LTE towers for 11 days: the clock's drift jumped
    about once a minute, by up to about 1 ppb, and about 20 m built up between jumps. Here jumps
    come as a Poisson process at `jump_rate_hz`. The first drift is uniform in +-`drift_mps`; at
    each jump a step uniform in [0, `drift_mps`] moves the drift towards steering the offset
    back to zero, and the drift stays within +-`drift_mps`. The offset starts at zero (the
    tower's constant offset is its other clock terms'), so it stays bounded, as a steered clock
    does. Draws nothing when `jump_rate_hz` or `drift_mps` is zero."""
    t_s = np.asarray(t_s, float)
    if not (jump_rate_hz and drift_mps) or len(t_s) == 0:
        return np.zeros(len(t_s))
    span = float(t_s[-1] - t_s[0])
    gaps = rng.exponential(1.0 / jump_rate_hz, int(span * jump_rate_hz * 3) + 20)
    jumps = t_s[0] + np.cumsum(gaps)
    jumps = jumps[jumps < t_s[-1]]
    steps = rng.uniform(0.0, drift_mps, len(jumps))
    drift = rng.uniform(-drift_mps, drift_mps)
    edges = np.concatenate([[t_s[0]], jumps])
    offsets, drifts = [0.0], [drift]
    for j, t_jump in enumerate(jumps):
        x = offsets[-1] + drifts[-1] * (t_jump - edges[j])
        drift = float(np.clip(drift - np.sign(x) * steps[j], -drift_mps, drift_mps))
        offsets.append(x)
        drifts.append(drift)
    seg = np.searchsorted(jumps, t_s, side="right")
    return np.asarray(offsets)[seg] + np.asarray(drifts)[seg] * (t_s - edges[seg])


def board_temperature(t_s: np.ndarray, change_k: float, tau_s: float) -> np.ndarray:
    """The payload board's temperature change since start-up (K) at times t_s (#278): a
    first-order approach to `change_k` with time constant `tau_s`, zero at t = 0, when the
    sensors are calibrated."""
    if tau_s <= 0.0:
        raise ValueError(f"board_temperature tau_s must be positive, not {tau_s!r}")
    return change_k * (1.0 - np.exp(-np.asarray(t_s, float) / tau_s))


# Random Fourier features per tower for `place_error`. Numerical, not a model value: enough
# that the field's covariance is close to its target (Rahimi & Recht, NeurIPS 2007).
PLACE_ERROR_WAVES = 256


def place_error(rng, n_towers: int, pos: np.ndarray, sigma_m: float, corr_m: float) -> np.ndarray:
    """A pseudorange error that depends only on where the receiver is (towers x samples, m).

    Reflections and blocked direct paths repeat every time the receiver passes the same place
    (what a ray tracer gives, ADR-0016), unlike `multipath`, which is a process in time. Each
    tower gets its own zero-mean Gaussian random field over horizontal position, with standard
    deviation `sigma_m` and squared-exponential correlation of length `corr_m`
    (sigma^2 exp(-d^2 / 2 corr^2)), drawn as random Fourier features. Same place, same error."""
    k = PLACE_ERROR_WAVES
    out = np.empty((n_towers, len(pos)))
    for i in range(n_towers):
        w = rng.normal(0.0, 1.0 / corr_m, (k, 2))
        b = rng.uniform(0.0, 2.0 * np.pi, k)
        out[i] = sigma_m * np.sqrt(2.0 / k) * np.cos(pos[:, :2] @ w.T + b).sum(axis=1)
    return out


def _gauss_markov(rng, dt: np.ndarray, sigma: float, tau_s: float) -> np.ndarray:
    """First-order Gauss-Markov sequence with steady-state std `sigma` and time constant tau."""
    phi = np.exp(-dt / tau_s)
    x = np.empty(len(dt))
    x[0] = rng.normal(0.0, sigma)
    # All steps' noise in one draw: the same stream, in the same order, as one draw per step.
    # phi**2 per element as a scalar (C pow), which can differ from the array square in the
    # last bit; the recursion then runs on Python floats, the same IEEE operations as before.
    phi_k = phi[1:].tolist()
    w = rng.normal(0.0, sigma * np.sqrt(1.0 - np.array([p**2 for p in phi_k]))).tolist()
    v = float(x[0])
    col = []
    for p, wk in zip(phi_k, w, strict=True):
        v = p * v + wk
        col.append(v)
    x[1:] = col
    return x


def _available(rng, t_s: np.ndarray, dropout: dict) -> np.ndarray:
    """True where a tower is heard: on or off for whole blocks, independently per block."""
    blocks = (t_s // dropout["block_s"]).astype(int)
    return (rng.random(blocks.max() + 1) < dropout["availability"])[blocks]
