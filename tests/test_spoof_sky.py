"""Spoof decision from the GPS sky (#206, ADR-0041, REQ-04): the sky map, the power pattern and
the cues combined."""

from datetime import UTC

import msgspec
import numpy as np
import pytest

from pnt.core.frames import ecef_to_llh, enu_to_ecef
from pnt.core.measurement import Measurement
from pnt.core.time import gps_ns_to_utc
from pnt.integrity import sky
from pnt.sim.leo import satellite_enu
from pnt.sim.scenario import T0_NS

CARLETON = [45.3876, -75.6960, 70.0]  # the scenarios' origin


class StubAlmanac:
    """Fixed elevations, so the decision's rules are tested without SGP4."""

    def __init__(self, elevation: dict[int, float]):
        self.elevation = elevation

    def elevations(self, t_ns, receiver_llh):
        return dict(self.elevation)


# A sky shaped like the real session's: C/N0 rising with elevation, spread out
REAL_EL = {3: 12.0, 4: 70.0, 9: 25.0, 16: 50.0, 26: 60.0, 27: 35.0, 28: 40.0, 31: 30.0, 5: -40.0}
REAL_SNR = {"3": 20.0, "4": 47.0, "9": 27.0, "16": 41.0, "26": 46.0, "27": 33.0, "28": 38.0,
            "31": 30.0, "5": 0.0, "70": 35.0}  # fmt: skip
FLAT_SNR = {k: (45.0 if v else 0.0) for k, v in REAL_SNR.items()}


# --- the almanac ----------------------------------------------------------------------------


def test_gps_tle_file_names_every_prn_once():
    tles = sky.read_gps_tles()
    assert len(tles) == 32 and set(tles) <= set(range(1, 33))


def test_satellite_overhead_is_at_90_degrees():
    """Stand under a satellite: its elevation is 90 deg, and the others' come out lower."""
    alm = sky.GpsAlmanac()
    look = alm.look(T0_NS, CARLETON)
    prn = max(look, key=lambda p: look[p][0][0])
    l1, l2 = alm.tles[prn]
    utc = gps_ns_to_utc(T0_NS).replace(tzinfo=UTC)
    enu, _ = satellite_enu(l1, l2, utc, np.array([0.0]), CARLETON)
    sub = ecef_to_llh(enu_to_ecef(enu[0], CARLETON))
    under = [float(sub[0]), float(sub[1]), 0.0]
    el = alm.elevations(T0_NS, under)
    assert el[prn] == pytest.approx(90.0, abs=0.01)
    assert all(e < 90.0 for p, e in el.items() if p != prn)


def test_a_gps_sky_has_a_plausible_number_of_satellites_up():
    # Regression guard, not a target: 24+ GPS satellites put roughly 8 to 12 above the horizon
    el = sky.GpsAlmanac().elevations(T0_NS, CARLETON)
    assert 6 <= sum(e > 0 for e in el.values()) <= 15


# --- the two checks -----------------------------------------------------------------------


def test_real_shaped_sky_passes_both_checks():
    c = sky.check(REAL_SNR, REAL_EL)
    assert c.below == [] and c.flat is False
    assert c.n_judged == 8 and c.n_other == 1  # PRN 70 (GLONASS) is not judged; PRN 5 untracked
    assert c.corr > 0.9 and c.spread_db > 5


def test_received_satellite_below_the_horizon_fires_the_sky_cue():
    c = sky.check({**REAL_SNR, "5": 38.0}, REAL_EL)
    assert c.below == [5]
    assert c.n_power == 8  # it does not count towards the power pattern


def test_equal_power_on_every_satellite_is_flat():
    c = sky.check(FLAT_SNR, REAL_EL)
    assert c.flat is True and c.spread_db == 0.0 and c.corr == 0.0


def test_power_uncorrelated_with_elevation_is_flat():
    # Spread like a real sky, but the strongest satellites are the lowest
    rev = {"3": 47.0, "4": 20.0, "9": 41.0, "16": 30.0, "26": 27.0, "27": 38.0, "28": 33.0}
    c = sky.check(rev, REAL_EL)
    assert c.spread_db > sky.SPREAD_MIN_DB and c.corr < sky.CORR_MIN and c.flat is True


def test_power_check_is_off_when_jammed_or_too_few():
    assert sky.check(FLAT_SNR, REAL_EL, jam=0.8).flat is None
    few = {"4": 45.0, "16": 45.0, "26": 45.0}
    c = sky.check(few, REAL_EL)
    assert c.flat is None and "power check off" in c.note


# --- the decision -------------------------------------------------------------------------


def _decision():
    return sky.SpoofDecision(almanac=StubAlmanac(REAL_EL))


def _feed(d, snrs, t0_s=0.0, period_s=5.0, flags=()):
    out = []
    for k, snr in enumerate(snrs):
        t = int((t0_s + k * period_s) * 1e9)
        d.sky(t, snr, CARLETON)
        out.append(d.decide(t, flags))
    return out


def test_clean_sky_is_not_spoofed_and_no_data_is_unknown():
    d = _decision()
    assert d.decide(0).level == "unknown"  # nothing heard: no claim either way
    s = _feed(d, [REAL_SNR] * 3)
    assert [x.level for x in s] == ["not_spoofed"] * 3 and s[-1].score == 0
    assert d.decide(int((10 + sky.STALE_S + 1) * 1e9)).level == "unknown"  # gone stale


def test_sky_cue_is_suspect_at_once_and_spoofed_when_held_then_clears():
    d = _decision()
    bad = {**REAL_SNR, "5": 40.0}
    s = _feed(d, [REAL_SNR, bad, bad, REAL_SNR])
    assert [x.level for x in s] == ["not_spoofed", "suspect", "spoofed", "not_spoofed"]
    assert s[2].cues == ["sky_below_horizon (held)"] and s[2].score == pytest.approx(1.0)


def test_flat_power_alone_is_only_suspect():
    s = _feed(_decision(), [FLAT_SNR] * 4)
    assert [x.level for x in s] == ["suspect"] * 4
    assert s[-1].cues == ["power_flat (held)"] and s[-1].score == pytest.approx(0.5)


def test_flat_power_with_a_latched_jump_guard_is_spoofed():
    s = _feed(_decision(), [FLAT_SNR] * 2, flags=["gnss_jump_latched", "gnss_excluded"])
    assert s[0].level == "suspect"  # power not held yet: 1 - 0.75 x 0.5 = 0.625
    assert s[1].level == "spoofed" and set(s[1].cues) == {"power_flat (held)", "jump_latched"}


def test_estimator_cues_combine_without_any_sky():
    d = _decision()
    assert d.decide(0, ["spoof_suspected"]).level == "suspect"
    both = d.decide(0, ["spoof_suspected", "gnss_jump_latched"])
    assert both.level == "spoofed" and both.score == pytest.approx(0.75)


def test_gnss_health_record_is_a_skyview():
    d = _decision()
    m = Measurement(
        t_ns=0, source="gnss", kind="gnss_health", value=(0.9, 8.0, 1.0), sigma=(0.0,) * 3,
        meta={"snr": FLAT_SNR},
    )  # fmt: skip
    c = d.measurement(m, CARLETON)
    assert c is not None and c.flat is None  # jammed: the power check is off
    bare = msgspec.structs.replace(m, meta={})
    assert d.measurement(bare, CARLETON) is None
