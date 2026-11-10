"""The simulated Starlink Doppler layer (P13, #97): its snapshot, its records, its visibility, a
hand-checked range rate, and its seeding. Numeric limits are regression guards, not
requirements; every Starlink value in the scenarios is TBC."""

from datetime import UTC, datetime

import numpy as np
import pytest

pytest.importorskip("sgp4")

from pnt.core.frames import llh_to_enu  # noqa: E402
from pnt.nav import ESTIMATORS  # noqa: E402
from pnt.sim import leo, trajectory  # noqa: E402
from pnt.sim.scenario import REFERENCE_DIR, T0_NS, generate, load  # noqa: E402

TLE = REFERENCE_DIR / "tle-starlink-20261110.txt"
ORIGIN = [45.3876, -75.6960, 70.0]
MASK_DEG = 25.0


def _ts(seconds):
    return T0_NS + (np.asarray(seconds) * 1e9).astype(np.int64)


def _still(n):
    return np.tile([0.0, 0.0, 30.0], (n, 1)), np.zeros((n, 3))


def _elevation_deg(m, rx) -> float:
    los = np.array(m.meta["emitter_enu"]) - rx
    return float(np.degrees(np.arcsin(los[2] / np.linalg.norm(los))))


@pytest.fixture(scope="module")
def run():
    return generate(load("starlink-outage"), seed=0)


def test_snapshot_is_a_small_dated_starlink_subset_with_its_source_recorded():
    sats = leo.read_tles(TLE)
    assert len(sats) >= 100 and all(name.startswith("STARLINK-") for name, _, _ in sats)
    assert TLE.stat().st_size < 200_000
    readme = (REFERENCE_DIR / "README.md").read_text()
    row = next(line for line in readme.splitlines() if TLE.name in line)
    assert "celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle" in row
    assert "2026-11-10" in row and "extract_starlink_tles.py" in row


def test_satellites_are_at_starlink_altitude_and_speed():
    earth_centre = llh_to_enu([ORIGIN[0], ORIGIN[1], -6_371_000.0], ORIGIN)
    utc = datetime(2026, 11, 12, 18, tzinfo=UTC)
    for _, l1, l2 in leo.read_tles(TLE)[::50]:
        pos, vel = leo.satellite_enu(l1, l2, utc, np.array([0.0, 60.0]), ORIGIN)
        altitude = np.linalg.norm(pos - earth_centre, axis=1) - 6_371_000.0
        assert np.all((altitude > 200e3) & (altitude < 650e3))
        assert np.all((np.linalg.norm(vel, axis=1) > 6800) & (np.linalg.norm(vel, axis=1) < 8000))


def test_records_are_leo_doppler_with_their_satellite_and_carrier(run):
    spec = load("starlink-outage")
    cfg = spec["sources"]["leo"]
    leo_recs = [m for m in run.measurements if m.source == "leo"]
    assert leo_recs and {m.kind for m in leo_recs} == {"doppler"}
    for m in leo_recs[:: max(1, len(leo_recs) // 200)]:
        assert m.emitter.startswith("leo:STARLINK-") and m.receiver == "payload"
        assert len(m.value) == 1 and m.sigma == (cfg["sigma_mps"],)
        assert set(m.meta) == {"emitter_enu", "emitter_vel_enu", "carrier_hz"}
        assert m.meta["carrier_hz"] == pytest.approx(11.325e9)
    # Every Starlink value is labelled as unconfirmed, the orbits as published
    assert spec["provenance"]["leo_orbits"] == "literature"
    for key in ("leo_noise", "elevation_mask", "pass_availability", "carrier"):
        assert spec["provenance"][key] == "TBC"


def test_only_satellites_above_the_mask_are_reported_and_enough_are(run):
    spec = load("starlink-outage")
    traj = {**spec["trajectory"], "_origin_llh": spec["origin_llh"]}
    leo_recs = [m for m in run.measurements if m.source == "leo"]
    t = (np.array([m.t_ns for m in leo_recs]) - T0_NS) / 1e9
    pos, _ = trajectory.make(traj, t)
    assert min(_elevation_deg(m, p) for m, p in zip(leo_recs, pos, strict=True)) >= MASK_DEG - 1e-6
    per_epoch = np.bincount(np.round(t).astype(int))
    assert per_epoch.min() >= 15  # ~59 above 25 deg, half of them heard (seed 0: 24-34)


def test_range_rate_sign_and_size_against_a_hand_check(monkeypatch):
    """A satellite flying north at 7 km/s, 550 km up, over a still receiver: range rate
    v * (-1000) / hypot(1000, 550) km = -6133.5 m/s while it approaches, 0 overhead, positive
    after. At 11.325 GHz that is a Doppler shift of +231.7 kHz on approach."""

    def straight(_l1, _l2, _utc, t_s, _origin):
        pos = np.column_stack([np.zeros_like(t_s), -1e6 + 7000.0 * t_s, np.full_like(t_s, 550e3)])
        return pos, np.tile([0.0, 7000.0, 0.0], (len(t_s), 1))

    monkeypatch.setattr(leo, "read_tles", lambda _p: [("STARLINK-TEST", "", "")])
    monkeypatch.setattr(leo, "satellite_enu", straight)
    seconds = np.array([0.0, 1e6 / 7000.0, 2e6 / 7000.0])  # approaching, overhead, receding
    pos, vel = np.zeros((3, 3)), np.zeros((3, 3))
    args = (ORIGIN, TLE, 0.0, MASK_DEG)
    out = leo.doppler(_ts(seconds), pos, vel, None, *args, carrier_hz=11.325e9)
    assert [m.t_ns for m in out] == list(_ts(seconds))  # elevation 28.8, 90, 28.8 deg: all seen
    rates = [m.value[0] for m in out]
    assert rates[0] == pytest.approx(-7000.0 * 1e6 / np.hypot(1e6, 550e3), abs=1e-6)
    assert rates[0] == pytest.approx(-6133.5, abs=0.1)
    assert rates[1] == pytest.approx(0.0, abs=1e-6) and rates[2] == pytest.approx(-rates[0])
    assert -out[0].meta["carrier_hz"] * rates[0] / leo.C_MPS == pytest.approx(231.7e3, rel=1e-3)
    # The receiver flying north at 10 m/s, as the satellite does, closes 10 m/s less
    vel[:, 1] = 10.0
    moving = leo.doppler(_ts(seconds[:1]), pos[:1], vel[:1], None, ORIGIN, TLE, 0.0, MASK_DEG)
    assert moving[0].value[0] == pytest.approx(rates[0] + 10.0 * 1e6 / np.hypot(1e6, 550e3))


def test_doppler_matches_how_fast_the_range_really_changes():
    seconds = np.arange(0.0, 120.0, 1.0)
    pos, vel = _still(len(seconds))
    out = leo.doppler(_ts(seconds), pos, vel, None, ORIGIN, TLE, 0.0, MASK_DEG)
    tracks: dict[str, list] = {}
    for m in out:
        tracks.setdefault(m.emitter, []).append(m)
    tracks = {k: v for k, v in tracks.items() if len(v) > 30}
    assert len(tracks) > 20
    for track in tracks.values():
        ranges = [np.linalg.norm(np.array(m.meta["emitter_enu"]) - pos[0]) for m in track]
        rates = np.array([m.value[0] for m in track])
        assert np.max(np.abs(np.diff(ranges) - 0.5 * (rates[1:] + rates[:-1]))) < 2.0
        assert np.all(np.abs(rates) < 8000)


def test_pass_availability_hears_a_seeded_share_and_one_makes_no_draw():
    seconds = np.arange(0.0, 30.0, 1.0)
    pos, vel = _still(len(seconds))
    args = (_ts(seconds), pos, vel)

    def heard(availability, seed):
        rng = np.random.default_rng(seed)
        out = leo.doppler(*args, rng, ORIGIN, TLE, 1.0, MASK_DEG, pass_availability=availability)
        return out, {m.emitter for m in out}

    full, every = heard(1.0, 0)
    assert full == leo.doppler(*args, np.random.default_rng(0), ORIGIN, TLE, 1.0, MASK_DEG)
    half_a, some_a = heard(0.5, 0)
    assert some_a < every and 0.3 < len(some_a) / len(every) < 0.7
    assert heard(0.5, 0)[0] == half_a  # same seed, same records
    assert heard(0.5, 1)[1] != some_a  # another seed hears other satellites
    with pytest.raises(ValueError, match="pass_availability"):
        heard(0.0, 0)


def test_the_layer_is_deterministic_per_seed_and_changes_no_other_source(run):
    again = generate(load("starlink-outage"), seed=0)
    assert again.measurements == run.measurements
    other = generate(load("starlink-outage"), seed=1)
    assert [m for m in other.measurements if m.source == "leo"] != [
        m for m in run.measurements if m.source == "leo"
    ]
    # The layer comes last, so with it off (ottawa-towers) every other record is the same: the
    # paired comparisons drop the Doppler records instead of regenerating
    towers = generate(load("ottawa-towers"), seed=0)
    assert [m for m in run.measurements if m.source != "leo"] == towers.measurements


def test_both_layers_record_as_leo_and_iridium_is_unchanged():
    both = generate(load("iridium-starlink-outage"), seed=0)
    iridium = generate(load("iridium-outage"), seed=0)
    emitters = {m.emitter for m in both.measurements if m.source == "leo"}
    assert any(e.startswith("leo:IRIDIUM") for e in emitters)
    assert any(e.startswith("leo:STARLINK-") for e in emitters)
    assert [m for m in both.measurements if not m.emitter.startswith("leo:STARLINK")] == (
        iridium.measurements
    )


@pytest.mark.parametrize("estimator", ["baseline", "ekf"])
def test_estimators_run_on_the_starlink_scenario(run, estimator):
    spec = load("starlink-outage")
    estimates = list(ESTIMATORS[estimator](run.measurements, origin_llh=spec["origin_llh"]))
    assert len(estimates) > 3000  # regression guard: ~360 s at 10 Hz
