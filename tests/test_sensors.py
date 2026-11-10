import numpy as np
import pytest

from pnt.core.measurement import validate
from pnt.sim import sensors
from pnt.sim.sensors import BMP280, DEG, MPU6050, G

FS = 400.0


def _static(n_s=600.0, params=MPU6050, seed=0):
    t = np.arange(0.0, n_s, 1 / FS)
    f = np.tile([0.0, 0.0, G], (len(t), 1))  # level and still: accelerometer reads +g on z
    w = np.zeros((len(t), 3))
    return t, *sensors.imu(t, f, w, np.random.default_rng(seed), params)


def _allan(x: np.ndarray, m: int) -> float:
    """Non-overlapping Allan deviation for clusters of m samples."""
    k = len(x) // m
    means = x[: k * m].reshape(k, m).mean(axis=1)
    return float(np.sqrt(0.5 * np.mean(np.diff(means) ** 2)))


def test_white_noise_matches_the_datasheet_density():
    # Only white noise: no bias wander, no quantization
    p = sensors.ImuParams(**{**MPU6050.__dict__, "gyro_instability_dph": 1e-9,
                             "accel_instability_ug": 1e-9, "gyro_lsb_dps": 1e-12,
                             "accel_lsb_g": 1e-12})  # fmt: skip
    t, accel, gyro = _static(300.0, p)
    expect_g = MPU6050.gyro_noise_dps_rthz * DEG * np.sqrt(FS / 2)
    expect_a = MPU6050.accel_noise_ug_rthz * 1e-6 * G * np.sqrt(FS / 2)
    assert np.std(gyro[:, 0]) == pytest.approx(expect_g, rel=0.02)
    assert np.std(accel[:, 0]) == pytest.approx(expect_a, rel=0.02)
    # Allan deviation of white noise falls as 1/sqrt(tau)
    assert _allan(gyro[:, 0], 400) == pytest.approx(expect_g / np.sqrt(400), rel=0.15)


def test_static_reading_is_gravity_plus_small_biases():
    _, accel, gyro = _static(60.0)
    mean_a, mean_g = accel.mean(axis=0), gyro.mean(axis=0)
    assert mean_a[2] == pytest.approx(G, rel=0.05)  # scale error is ~1 %
    assert np.all(np.abs(mean_a[:2]) < 0.2)  # residual bias ~5 mg = 0.05 m/s^2
    assert np.all(np.abs(mean_g) < 0.5 * DEG)


def test_bias_wander_is_slow_and_bounded():
    p = sensors.ImuParams(**{**MPU6050.__dict__, "gyro_noise_dps_rthz": 1e-9,
                             "gyro_bias_dps": 1e-9, "gyro_lsb_dps": 1e-12})  # fmt: skip
    _, _, gyro = _static(2000.0, p)
    wander = gyro[:, 0] / DEG * 3600  # deg/h
    assert np.std(wander) == pytest.approx(MPU6050.gyro_instability_dph, rel=0.5)
    assert np.abs(np.diff(wander)).max() < 5.0  # moves slowly between samples


def test_quantization_and_range_clipping():
    t = np.arange(0.0, 1.0, 1 / FS)
    huge = np.tile([0.0, 0.0, 20 * G], (len(t), 1))  # beyond +/-8 g
    accel, gyro = sensors.imu(t, huge, np.zeros((len(t), 3)), np.random.default_rng(1))
    assert accel[:, 2].max() == pytest.approx(8 * G)
    steps = np.unique(np.round(gyro[:, 0] / (MPU6050.gyro_lsb_dps * DEG), 6))
    assert np.allclose(steps, np.round(steps))  # every reading is a whole number of LSBs


def test_vibration_appears_at_its_frequency():
    p = sensors.ImuParams(**{**MPU6050.__dict__, "vibration": {"freq_hz": 50.0,
                                                              "accel_mps2": 2.0}})  # fmt: skip
    _, accel, _ = _static(10.0, p)
    spec = np.abs(np.fft.rfft(accel[:, 0] - accel[:, 0].mean()))
    freqs = np.fft.rfftfreq(len(accel), 1 / FS)
    assert freqs[np.argmax(spec)] == pytest.approx(50.0, abs=0.2)


def test_same_seed_same_readings():
    a = _static(5.0, seed=7)
    b = _static(5.0, seed=7)
    assert np.array_equal(a[1], b[1]) and np.array_equal(a[2], b[2])


def test_measurements_follow_the_icd():
    t, accel, gyro = _static(1.0)
    ts_ns = np.round(t * 1e9).astype(np.int64)
    meas = sensors.imu_measurements(ts_ns, accel, gyro)
    assert len(meas) == len(t)
    for m in meas[:5]:
        validate(m)
        assert m.source == "imu" and m.kind == "accel_gyro" and len(m.value) == 6
    alt = sensors.baro(t, np.full(len(t), 30.0), np.random.default_rng(0))
    for m in sensors.baro_measurements(ts_ns, alt)[:5]:
        validate(m)


def test_baro_noise_and_offset_are_plausible():
    t = np.arange(0.0, 3600.0, 0.1)
    alt = sensors.baro(t, np.zeros(len(t)), np.random.default_rng(3))
    assert np.std(np.diff(alt)) == pytest.approx(BMP280.noise_m * np.sqrt(2), rel=0.1)
    assert abs(alt.mean()) < 5 * np.hypot(BMP280.offset_m, BMP280.drift_m)


def test_every_parameter_states_where_it_comes_from():
    assert MPU6050.provenance and BMP280.provenance
    assert all(v for v in MPU6050.provenance.values())
