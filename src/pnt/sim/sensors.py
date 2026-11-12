"""Sensor models for our payload's IMU and barometer (issue #9, ADR-0014), and an opt-in
magnetometer heading (#276, ADR-0051 Proposed) that the payload does not carry.

Standalone: they take true motion as arrays (specific force and body rate in the body frame, or
true altitude) and return what the sensor would report, so any trajectory source can drive them
(`trajectory.kinematics`, SITL, a recording).

Every parameter is labelled with where it comes from (ADR-0015):
- `datasheet`: InvenSense MPU-6000/6050 Product Specification rev 3.4; Bosch BMP280 datasheet
- `literature`: typical values for this class of part, not this unit
- `TBC`: a placeholder until we record our own sensor sitting still (Allan variance)
- `measured`: from our own MPU6050 sitting still (`analysis/imu_allan.py`), with the session

White noise from a noise density N (unit/sqrt(Hz)) sampled at fs: sigma = N * sqrt(fs / 2), i.e.
an ideal anti-alias filter at Nyquist. Bias instability is a first-order Gauss-Markov process.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pnt.core.measurement import Measurement

G = 9.80665
DEG = np.pi / 180.0


@dataclass(frozen=True)
class ImuParams:
    gyro_noise_dps_rthz: float  # white noise density, deg/s/sqrt(Hz)
    accel_noise_ug_rthz: float  # white noise density, micro-g/sqrt(Hz)
    gyro_bias_dps: float  # 1-sigma bias left after start-up calibration, deg/s
    accel_bias_mg: float  # 1-sigma bias left after start-up calibration, milli-g
    gyro_instability_dph: float  # 1-sigma Gauss-Markov bias wander, deg/h
    accel_instability_ug: float  # 1-sigma Gauss-Markov bias wander, micro-g
    instability_tau_s: float  # correlation time of the bias wander
    scale_error: float  # 1-sigma scale-factor error after calibration (fraction)
    gyro_range_dps: float  # full-scale range: readings clip here
    accel_range_g: float
    gyro_lsb_dps: float  # quantization step
    accel_lsb_g: float
    vibration: dict | None = None  # {freq_hz, accel_mps2, gyro_dps}: e.g. motor vibration
    provenance: dict = field(default_factory=dict)


# MPU6050 at +/-500 deg/s and +/-8 g (what ArduPilot-style drones configure).
# Measured values: our unit still on the bench overnight (ADR-0015, analysis/imu_allan.py).
_STATIC = "20261110-0306-static-bench-overnight, 1800-18000 s"
MPU6050 = ImuParams(
    gyro_noise_dps_rthz=0.005,
    accel_noise_ug_rthz=240.0,
    gyro_bias_dps=0.05,
    accel_bias_mg=5.0,
    gyro_instability_dph=16.0,
    accel_instability_ug=280.0,
    instability_tau_s=100.0,
    scale_error=0.01,
    gyro_range_dps=500.0,
    accel_range_g=8.0,
    gyro_lsb_dps=1 / 65.5,
    accel_lsb_g=1 / 4096,
    provenance={
        "gyro_noise_dps_rthz": f"measured ({_STATIC}): 0.0049-0.0053 per axis; datasheet 0.005",
        "accel_noise_ug_rthz": f"measured ({_STATIC}): 198-309 per axis, mean 240; datasheet 400",
        "gyro_bias_dps": "TBC: residual after start-up calibration; raw ZRO is +/-20 deg/s",
        "accel_bias_mg": "TBC: residual after calibration; raw zero-g offset is +/-50-80 mg",
        "gyro_instability_dph": (
            f"measured ({_STATIC}): Allan floor 3.7-5.5 deg/h, 0.78x the sim's at 20 deg/h"
        ),
        "accel_instability_ug": (
            f"measured ({_STATIC}): Allan floor 65-119 ug, 2.85x the sim's at 100 ug; the real "
            "accel also drifts at tau > 100 s, which Gauss-Markov does not make"
        ),
        "instability_tau_s": "TBC: the measured floors sit at tau 20-100 s (gyro), 4-13 s (accel)",
        "scale_error": "TBC: raw sensitivity tolerance is +/-3 %",
        "ranges_and_lsb": "datasheet, at the +/-500 deg/s and +/-8 g settings",
    },
)


@dataclass(frozen=True)
class BaroParams:
    noise_m: float  # white noise, m
    offset_m: float  # 1-sigma offset left after referencing to GNSS altitude at start-up
    drift_m: float  # 1-sigma slow wander (weather, temperature), m
    drift_tau_s: float
    provenance: dict = field(default_factory=dict)


# BMP280 referenced to GNSS altitude at start-up, on a drone (prop wash dominates the noise).
BMP280 = BaroParams(
    noise_m=0.3,
    offset_m=0.5,
    drift_m=1.0,
    drift_tau_s=600.0,
    provenance={
        "noise_m": "TBC: datasheet RMS noise is about 1.7 cm with filtering; prop wash dominates",
        "offset_m": "TBC: datasheet absolute accuracy is +/-1 hPa (~8 m) before referencing",
        "drift_m": "literature, TBC: datasheet relative accuracy is +/-0.12 hPa (~1 m)",
        "drift_tau_s": "TBC",
    },
)


def _white_sigma(density: float, fs: float) -> float:
    return density * np.sqrt(fs / 2.0)


def _gauss_markov(rng, n: int, dt: float, sigma: float, tau: float, axes: int) -> np.ndarray:
    phi = np.exp(-dt / tau)
    x = np.empty((n, axes))
    x[0] = rng.normal(0.0, sigma, axes)
    q = sigma * np.sqrt(1.0 - phi**2)
    for k in range(1, n):
        x[k] = phi * x[k - 1] + rng.normal(0.0, q, axes)
    return x


def _quantize(x: np.ndarray, step: float, limit: float) -> np.ndarray:
    return np.clip(np.round(x / step) * step, -limit, limit)


def imu(
    t_s: np.ndarray,
    specific_force_b: np.ndarray,
    omega_b: np.ndarray,
    rng: np.random.Generator,
    params: ImuParams = MPU6050,
) -> tuple[np.ndarray, np.ndarray]:
    """Accelerometer (m/s^2) and gyro (rad/s) readings at evenly spaced times t_s."""
    t_s = np.asarray(t_s, float)
    n = len(t_s)
    dt = float(np.median(np.diff(t_s))) if n > 1 else 1.0
    fs = 1.0 / dt
    p = params
    # Per-run constants: residual bias and scale error, drawn once
    gyro_bias = rng.normal(0.0, p.gyro_bias_dps * DEG, 3)
    accel_bias = rng.normal(0.0, p.accel_bias_mg * 1e-3 * G, 3)
    gyro_scale = 1.0 + rng.normal(0.0, p.scale_error, 3)
    accel_scale = 1.0 + rng.normal(0.0, p.scale_error, 3)
    # Slow bias wander
    gyro_wander = _gauss_markov(
        rng, n, dt, p.gyro_instability_dph * DEG / 3600, p.instability_tau_s, 3
    )
    accel_wander = _gauss_markov(
        rng, n, dt, p.accel_instability_ug * 1e-6 * G, p.instability_tau_s, 3
    )
    # White noise
    gyro_white = rng.normal(0.0, _white_sigma(p.gyro_noise_dps_rthz * DEG, fs), (n, 3))
    accel_white = rng.normal(0.0, _white_sigma(p.accel_noise_ug_rthz * 1e-6 * G, fs), (n, 3))

    accel = specific_force_b * accel_scale + accel_bias + accel_wander + accel_white
    gyro = omega_b * gyro_scale + gyro_bias + gyro_wander + gyro_white
    if p.vibration:
        # One sinusoid per axis at the vibration frequency, random phase per axis. Sampled at fs,
        # it aliases exactly as a real unfiltered sensor would.
        v = p.vibration
        arg = 2 * np.pi * v["freq_hz"] * t_s[:, None]
        accel = accel + v.get("accel_mps2", 0.0) * np.sin(arg + rng.uniform(0, 2 * np.pi, 3))
        gyro = gyro + v.get("gyro_dps", 0.0) * DEG * np.sin(arg + rng.uniform(0, 2 * np.pi, 3))
    accel = _quantize(accel, p.accel_lsb_g * G, p.accel_range_g * G)
    gyro = _quantize(gyro, p.gyro_lsb_dps * DEG, p.gyro_range_dps * DEG)
    return accel, gyro


def imu_measurements(
    ts_ns: np.ndarray, accel: np.ndarray, gyro: np.ndarray, params: ImuParams = MPU6050
) -> list[Measurement]:
    """`accel_gyro` records (ICD-measurement): body frame, m/s^2 then rad/s. Sigma is the
    per-sample white noise; biases are for the estimator to model, not the sigma."""
    fs = 1e9 / float(np.median(np.diff(ts_ns))) if len(ts_ns) > 1 else 1.0
    sa = _white_sigma(params.accel_noise_ug_rthz * 1e-6 * G, fs)
    sg = _white_sigma(params.gyro_noise_dps_rthz * DEG, fs)
    sigma = (sa, sa, sa, sg, sg, sg)
    return [
        Measurement(
            t_ns=int(t),
            source="imu",
            kind="accel_gyro",
            value=tuple(float(x) for x in (*a, *g)),
            sigma=sigma,
        )
        for t, a, g in zip(ts_ns, accel, gyro, strict=True)
    ]


def baro(
    t_s: np.ndarray, altitude_m: np.ndarray, rng: np.random.Generator, params: BaroParams = BMP280
) -> np.ndarray:
    """Barometric altitude (m above the session origin) at evenly spaced times."""
    t_s = np.asarray(t_s, float)
    n = len(t_s)
    dt = float(np.median(np.diff(t_s))) if n > 1 else 1.0
    offset = rng.normal(0.0, params.offset_m)
    drift = _gauss_markov(rng, n, dt, params.drift_m, params.drift_tau_s, 1)[:, 0]
    return np.asarray(altitude_m, float) + offset + drift + rng.normal(0.0, params.noise_m, n)


def baro_measurements(
    ts_ns: np.ndarray, altitude_m: np.ndarray, params: BaroParams = BMP280
) -> list[Measurement]:
    """`altitude` records. Sigma is the white noise only."""
    return [
        Measurement(
            t_ns=int(t), source="baro", kind="altitude", value=(float(a),), sigma=(params.noise_m,)
        )
        for t, a in zip(ts_ns, altitude_m, strict=True)
    ]


@dataclass(frozen=True)
class MagParams:
    """A magnetometer's heading, after hard- and soft-iron calibration and the declination
    correction to true north (#276, ADR-0051 Proposed). The payload has no magnetometer
    (ADR-0014): this is a candidate sensor, opt-in in the sim. What is left is a per-flight bias
    (motor and wiring fields, calibration and declination error), drawn once per run from a
    Student-t so that a few flights carry a much larger offset, plus white noise."""

    noise_deg: float = 1.0  # white noise 1-sigma per reading, deg
    bias_deg: float = 2.5  # scale of the per-flight bias, deg
    bias_dof: float = 4.0  # Student-t degrees of freedom of that bias (heavy-ish tails)
    provenance: dict = field(default_factory=dict)


MAG = MagParams(
    provenance={
        "noise_deg": "TBC: unsourced placeholder",
        "bias_deg": (
            "TBC, weak evidence (report sources-research-20261111 17.4, 17.10): a per-flight "
            "bias of 2-3 deg; one forum post saw a near-constant 3.6 deg on a small quad"
        ),
        "bias_dof": "TBC: unsourced; 4 gives tails heavier than Gaussian with a finite variance",
    }
)


def heading_of(rot: np.ndarray) -> np.ndarray:
    """Heading (rad, clockwise from true north) of the body x (forward) axis of each
    body-to-ENU rotation (N, 3, 3), the convention of the `heading` kind (ICD-measurement)."""
    return np.arctan2(rot[:, 0, 0], rot[:, 1, 0])


def magnetometer(
    rot: np.ndarray, rng: np.random.Generator, params: MagParams = MAG
) -> tuple[np.ndarray, float]:
    """(heading readings in rad wrapped to [-pi, pi), the run's bias in rad) for the true
    body-to-ENU rotations `rot` (N, 3, 3)."""
    bias = params.bias_deg * DEG * float(rng.standard_t(params.bias_dof))
    psi = heading_of(rot) + bias + rng.normal(0.0, params.noise_deg * DEG, len(rot))
    return (psi + np.pi) % (2 * np.pi) - np.pi, bias


def mag_measurements(ts_ns: np.ndarray, psi: np.ndarray, params: MagParams = MAG):
    """`heading` records from source `mag`. Sigma is the white noise only; the per-flight bias
    is for the estimator to model, as the IMU's biases are."""
    s = (params.noise_deg * DEG,)
    return [
        Measurement(t_ns=int(t), source="mag", kind="heading", value=(float(p),), sigma=s)
        for t, p in zip(ts_ns, psi, strict=True)
    ]
