from datetime import UTC, datetime

import numpy as np
import pytest

pytest.importorskip("sgp4")

from pnt.core.frames import llh_to_enu  # noqa: E402
from pnt.nav import ESTIMATORS
from pnt.sim import leo  # noqa: E402
from pnt.sim.scenario import REFERENCE_DIR, T0_NS, generate, load  # noqa: E402

TLE = REFERENCE_DIR / "tle-iridium-20261108.txt"
ORIGIN = [45.3876, -75.6960, 70.0]
# Numeric limits in this file are regression guards, not requirements.


def _ts(seconds):
    return T0_NS + (np.asarray(seconds) * 1e9).astype(np.int64)


def _still(n):
    return np.tile([0.0, 0.0, 30.0], (n, 1)), np.zeros((n, 3))


def test_snapshot_is_the_iridium_next_constellation():
    assert len(leo.read_tles(TLE)) >= 66


def test_satellites_are_at_iridium_altitude_and_speed():
    name, l1, l2 = leo.read_tles(TLE)[0]
    utc = datetime(2026, 11, 12, 18, tzinfo=UTC)
    pos, vel = leo.satellite_enu(l1, l2, utc, np.array([0.0, 60.0]), ORIGIN)
    earth_centre = llh_to_enu([ORIGIN[0], ORIGIN[1], -6_371_000.0], ORIGIN)
    altitude = np.linalg.norm(pos - earth_centre, axis=1) - 6_371_000.0
    assert np.all((altitude > 700e3) & (altitude < 860e3))
    assert np.all((np.linalg.norm(vel, axis=1) > 6500) & (np.linalg.norm(vel, axis=1) < 7700))


def test_only_satellites_above_the_mask_are_reported():
    seconds = np.arange(0.0, 300.0, 5.0)
    pos, vel = _still(len(seconds))
    rng = np.random.default_rng(0)
    out = leo.doppler(_ts(seconds), pos, vel, rng, ORIGIN, TLE, 0.0, elevation_mask_deg=20.0)
    assert out
    for m in out:
        los = np.array(m.meta["emitter_enu"]) - pos[0]
        assert np.degrees(np.arcsin(los[2] / np.linalg.norm(los))) >= 20.0 - 1e-6


def test_doppler_matches_how_fast_the_range_really_changes():
    seconds = np.arange(0.0, 600.0, 1.0)
    pos, vel = _still(len(seconds))
    rng = np.random.default_rng(0)
    out = leo.doppler(_ts(seconds), pos, vel, rng, ORIGIN, TLE, 0.0, elevation_mask_deg=10.0)
    by_sat = {}
    for m in out:
        by_sat.setdefault(m.emitter, []).append(m)
    tracks = [v for v in by_sat.values() if len(v) > 30]
    assert tracks
    for track in tracks:
        ranges = [np.linalg.norm(np.array(m.meta["emitter_enu"]) - pos[0]) for m in track]
        rates = np.array([m.value[0] for m in track])
        numeric = np.diff(ranges) / 1.0
        assert np.max(np.abs(numeric - 0.5 * (rates[1:] + rates[:-1]))) < 2.0
        assert np.all(np.abs(rates) < 7700)


def test_receiver_clock_drift_shifts_doppler():
    seconds = np.arange(0.0, 60.0, 1.0)
    pos, vel = _still(len(seconds))
    args = (ORIGIN, TLE, 0.0, 8.2)
    plain = leo.doppler(_ts(seconds), pos, vel, np.random.default_rng(0), *args)
    drifting = leo.doppler(
        _ts(seconds), pos, vel, np.random.default_rng(0), *args, clock_s=1e-8 * seconds
    )
    assert plain and len(plain) == len(drifting)
    for a, b in zip(plain, drifting, strict=True):
        assert b.value[0] - a.value[0] == pytest.approx(leo.C_MPS * 1e-8, abs=1e-3)


@pytest.mark.parametrize("estimator", sorted(ESTIMATORS))
def test_scenario_produces_iridium_measurements_and_the_filter_still_runs(estimator):
    spec = load("iridium-outage")
    run = generate(spec, seed=0)
    dopplers = [m for m in run.measurements if m.source == "leo"]
    assert dopplers and all(m.kind == "doppler" for m in dopplers)
    estimates = list(ESTIMATORS[estimator](run.measurements, origin_llh=spec["origin_llh"]))
    assert len(estimates) > 3000  # regression guard: ~360 s at 10 Hz, Doppler ignored
