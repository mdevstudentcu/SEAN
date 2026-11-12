"""Pins what the scenario generator draws, so that a change to its random-stream order or its
arithmetic shows up here rather than as quietly different results (#255).

The generator was sped up keeping its outputs bit-identical: noise drawn in one call in the
same stream order, recursions on Python floats. If a change here is intended (a new model, a
new draw), say so in the PR and update the pins."""

from __future__ import annotations

import hashlib

import numpy as np

from pnt.core.measurement import msgpack_encoder
from pnt.sim import models, sensors
from pnt.sim.scenario import generate, load

# challenge-drone-hop-outage cut to 20 s, seed 0: waypoint truth, IMU, baro, GNSS and hopping
# front-end LTE records with multipath. First 16 hex digits of the sha256 of each kind's records
# (msgpack, in generated order).
PINNED = {
    ("baro", "altitude"): "3f7b1f98d8dec1c6",
    ("gnss", "gnss_health"): "e078df280e25f9c4",
    ("gnss", "position_enu"): "512435e26c611fa7",
    ("gnss", "time"): "8a97ddd582b0b9bb",
    ("imu", "accel_gyro"): "38dae6ee3ee7af4c",
    ("lte", "pseudorange"): "b4824cfa109db825",
    "truth": "64f3721bf62900a4",
}


def _digest(records) -> str:
    h = hashlib.sha256()
    for r in records:
        h.update(msgpack_encoder.encode(r))
    return h.hexdigest()[:16]


def test_short_hop_scenario_generates_the_pinned_records():
    spec = load("challenge-drone-hop-outage")
    spec["duration_s"] = 20
    run = generate(spec, seed=0)
    got = {
        k: _digest([m for m in run.measurements if (m.source, m.kind) == k])
        for k in {(m.source, m.kind) for m in run.measurements}
    }
    got["truth"] = _digest(run.truth)
    assert got == PINNED


def _per_step_sensors(rng, n, dt, sigma, tau, axes):
    """sensors._gauss_markov as it was: one draw of `axes` per step."""
    phi = np.exp(-dt / tau)
    x = np.empty((n, axes))
    x[0] = rng.normal(0.0, sigma, axes)
    q = sigma * np.sqrt(1.0 - phi**2)
    for k in range(1, n):
        x[k] = phi * x[k - 1] + rng.normal(0.0, q, axes)
    return x


def _per_step_models(rng, dt, sigma, tau_s):
    """models._gauss_markov as it was: one draw per step, phi**2 as a scalar."""
    phi = np.exp(-dt / tau_s)
    x = np.empty(len(dt))
    x[0] = rng.normal(0.0, sigma)
    for k in range(1, len(dt)):
        x[k] = phi[k] * x[k - 1] + rng.normal(0.0, sigma * np.sqrt(1.0 - phi[k] ** 2))
    return x


def test_gauss_markov_draws_match_one_draw_per_step_bit_for_bit():
    for seed, (n, axes) in enumerate([(1, 3), (2, 1), (5000, 3)]):
        a, b = np.random.default_rng(seed), np.random.default_rng(seed)
        old = _per_step_sensors(a, n, 0.01, 2e-5, 100.0, axes)
        new = sensors._gauss_markov(b, n, 0.01, 2e-5, 100.0, axes)
        assert np.array_equal(old, new)
        assert a.random() == b.random()  # and the stream is left where it was
    # Uneven steps, where a scalar phi**2 and the array square differ in the last bit
    dt = np.random.default_rng(9).uniform(0.0, 4.0, 20_000)
    dt[0] = 0.0
    for seed, tau in enumerate([0.5, 3.0, 600.0]):
        a, b = np.random.default_rng(seed), np.random.default_rng(seed)
        assert np.array_equal(
            _per_step_models(a, dt, 7.0, tau), models._gauss_markov(b, dt, 7.0, tau)
        )
        assert a.random() == b.random()
