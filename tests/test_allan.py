"""Allan deviation and the figures read off it (ADR-0015), on curves whose answer is known."""

import numpy as np
import pytest

from pnt.sim import allan, sensors
from pnt.sim.sensors import DEG, MPU6050, G

FS = 100.0  # what the payload records the MPU6050 at


def test_white_noise_falls_as_one_over_root_tau():
    sigma = 0.3
    x = np.random.default_rng(0).normal(0.0, sigma, 200_000)
    tau, adev = allan.overlapping_adev(x, FS)
    expect = sigma / np.sqrt(FS * tau)
    keep = tau <= tau[-1] / 10  # the longest taus have few clusters
    np.testing.assert_allclose(adev[keep], expect[keep], rtol=0.1)


def test_a_constant_bias_does_not_show():
    x = np.random.default_rng(1).normal(0.0, 1.0, 50_000)
    _, a = allan.overlapping_adev(x, FS)
    _, b = allan.overlapping_adev(x + 123.0, FS)
    np.testing.assert_allclose(a, b, rtol=1e-9)


def test_cluster_sizes_stop_at_a_tenth_of_the_record():
    m = allan.cluster_sizes(100_000)
    assert m[0] == 1 and m[-1] == 10_000
    assert np.all(np.diff(m) > 0)
    with pytest.raises(ValueError):
        allan.cluster_sizes(9)


def _static_sim(seconds: float, params, seed: int = 0):
    t = np.arange(0.0, seconds, 1 / FS)
    f = np.tile([0.0, 0.0, G], (len(t), 1))
    return sensors.imu(t, f, np.zeros((len(t), 3)), np.random.default_rng(seed), params)


def test_fit_recovers_the_sims_white_noise_density():
    # The round trip that matters: a density read off a curve, put back in the sim, gives the
    # same curve. White noise only, no quantization.
    p = sensors.ImuParams(**{**MPU6050.__dict__, "gyro_instability_dph": 1e-9,
                             "accel_instability_ug": 1e-9, "gyro_lsb_dps": 1e-12,
                             "accel_lsb_g": 1e-12})  # fmt: skip
    accel, gyro = _static_sim(1200.0, p)
    f = allan.fit(*allan.overlapping_adev(gyro[:, 0], FS))
    assert allan.density_from_white(f["white_adev_1s"]) / DEG == pytest.approx(
        MPU6050.gyro_noise_dps_rthz, rel=0.1
    )
    f = allan.fit(*allan.overlapping_adev(accel[:, 2], FS))
    assert allan.density_from_white(f["white_adev_1s"]) / (1e-6 * G) == pytest.approx(
        MPU6050.accel_noise_ug_rthz, rel=0.1
    )
    assert f["bias_floor_reached"] is False  # pure white noise keeps falling


def test_fit_finds_the_floor_and_the_rate_random_walk():
    rng = np.random.default_rng(2)
    n, k = 400_000, 1e-3  # rate random walk K: avar = K^2 tau / 3
    rrw = np.cumsum(rng.normal(0.0, k / np.sqrt(FS), n))
    x = rng.normal(0.0, 0.05, n) + rrw
    tau, adev = allan.overlapping_adev(x, FS)
    f = allan.fit(tau, adev)
    assert f["bias_floor_reached"] is True
    assert 1.0 < f["floor_tau_s"] < tau[-1]
    assert f["floor"] == pytest.approx(adev.min())
    assert f["rrw_adev_3s"] == pytest.approx(k, rel=0.25)
    assert f["white_adev_1s"] == pytest.approx(0.05 / np.sqrt(FS), rel=0.1)


def test_no_figure_without_the_slope_it_needs():
    tau = np.logspace(-2, 3, 30)
    flat = np.full_like(tau, 1e-3)
    f = allan.fit(tau, flat)
    assert f["white_adev_1s"] is None and f["rrw_adev_3s"] is None


def test_psd_density_ignores_a_vibration_below_the_band():
    # A 5 Hz vibration (as on our bench, 2026-11-10) over the sim's white noise: the Allan curve
    # bends, the spectrum's 10-30 Hz floor still gives the density.
    p = sensors.ImuParams(**{**MPU6050.__dict__, "gyro_instability_dph": 1e-9,
                             "accel_instability_ug": 1e-9, "gyro_lsb_dps": 1e-12,
                             "accel_lsb_g": 1e-12})  # fmt: skip
    _, gyro = _static_sim(600.0, p, seed=3)
    t = np.arange(len(gyro)) / FS
    x = gyro[:, 0] + 0.5 * DEG * np.sin(2 * np.pi * 5.0 * t)
    assert allan.psd_density(x, FS) / DEG == pytest.approx(MPU6050.gyro_noise_dps_rthz, rel=0.1)
    with pytest.raises(ValueError):
        allan.psd_density(x, 10.0)  # Nyquist 5 Hz: nothing in the band
