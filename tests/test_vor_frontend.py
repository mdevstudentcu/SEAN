"""VOR front end (#22) on Voracious output: no SDR, no Voracious, no network.

`fixtures/vor/voracious.jsonl` is in the JSON Lines form Voracious 0.4.1 documents
(https://docs.rs/crate/voracious/0.4.1/source/readme.md, MIT). Its first line is that README's
example (station ARL) as published; the rest are hand-written for two SYNTHETIC stations, TST
and QQQ, placed 10 km and 7 km from the session origin. Their radials are the true radials to
the origin plus a few tenths of a degree, so the test knows the answer. Not a recording.
"""

import json
import math
from pathlib import Path

import pytest

from pnt.core import frames
from pnt.core.measurement import validate
from pnt.core.time import unix_ns_to_gps_ns
from pnt.frontends import vor

FIXTURE = Path(__file__).parent / "fixtures" / "vor" / "voracious.jsonl"
ORIGIN = (45.3876, -75.6960, 70.0)
# SYNTHETIC stations: positions and variation made up for the test, not real navaids
TST = vor.Station("TST", 113.0, 45.333569, -75.593946, 157.8, -13.0)
QQQ = vor.Station("QQQ", 115.5, 45.342594, -75.759794, 133.9, -13.0)


def true_bearing_deg(st: vor.Station, llh=ORIGIN) -> float:
    """From the station to `llh`, clockwise from true north at the station."""
    e, n, _ = frames.llh_to_enu(llh, (st.lat, st.lon, st.h))
    return math.degrees(math.atan2(e, n)) % 360


def run(**kw):
    return vor.process(FIXTURE.read_text().splitlines(), [TST, QQQ], **kw)


def test_radials_become_true_bearings_from_the_station():
    r = run()
    for m in r.measurements:
        validate(m)
    assert [m.emitter for m in r.measurements] == ["vor:TST"] * 4 + ["vor:QQQ"]
    for m in r.measurements:
        st = TST if m.emitter == "vor:TST" else QQQ
        err = (math.degrees(m.value[0]) - true_bearing_deg(st) + 180) % 360 - 180
        assert abs(err) < 0.3  # the fixture's radials are within 0.25 deg of the truth
        assert m.value[0] == pytest.approx(math.radians(m.meta["radial_deg"] + st.magvar_deg))
        assert m.meta["emitter_llh"] == [st.lat, st.lon, st.h]
        assert m.sigma == (math.radians(vor.BEARING_SIGMA_DEG),)
    assert r.measurements[0].t_ns == unix_ns_to_gps_ns(1_794_321_003 * 10**9)
    assert r.measurements[0].meta["signal_quality"]["snr_30hz_db"] == 31.2


def test_unknown_or_contradictory_stations_are_dropped_and_counted():
    r = run()
    # ARL is not in the table; "QQQ" on TST's frequency names two stations at once
    assert r.unmatched == 2
    assert r.unreadable == 2  # a line that is not JSON, and one with no radial
    # the record with no ident is matched by frequency, and says so
    no_ident = [m for m in r.measurements if not m.meta["ident_decoded"]]
    assert len(no_ident) == 1 and no_ident[0].emitter == "vor:TST"


def test_ident_alone_is_not_enough_when_two_stations_share_a_frequency():
    twin = vor.Station("TWN", 113.0, 45.0, -75.0, 100.0, -13.0)
    r = vor.process(FIXTURE.read_text().splitlines(), [TST, twin])
    assert [m.emitter for m in r.measurements] == ["vor:TST"] * 3  # the no-ident one is dropped


def test_bearing_wraps_into_0_to_2pi():
    st = vor.Station("WRP", 112.0, 45.0, -75.0, 0.0, 5.0)
    rec = {"timestamp": 1794321000.0, "radial_deg": 359.0, "frequency_mhz": 112.0, "ident": "WRP"}
    line = json.dumps(rec)
    (m,) = vor.process([line], [st]).measurements
    assert m.value[0] == pytest.approx(math.radians(4.0))


def test_file_times_come_from_the_capture_clock():
    t0_gps = 1_478_000_000_000_000_000
    r = run(file_t0=(1_794_321_000.0, t0_gps))
    assert r.measurements[0].t_ns == t0_gps + 3 * 10**9


def test_a_real_station_is_resolved_from_the_navaids_table():
    """YOW (114.6 MHz) from data/reference/navaids.csv, by ident and by frequency alone."""
    (yow,) = [s for s in vor.load_stations() if s.ident == "YOW"]
    assert yow.freq_mhz == pytest.approx(114.6)
    assert yow.magvar_deg == -14.0  # the slaved variation its radials use, not today's -13.4
    radial = (true_bearing_deg(yow) - yow.magvar_deg) % 360  # what YOW radiates toward Carleton
    lines = [
        json.dumps({"timestamp": 1794321000.0, "radial_deg": radial, "frequency_mhz": 114.6, **x})
        for x in ({"ident": "YOW"}, {})
    ]
    r = vor.process(lines)  # no stations passed: the table is the default
    assert r.unmatched == 0 and len(r.measurements) == 2
    for m in r.measurements:
        validate(m)
        assert m.emitter == "vor:YOW"
        assert m.meta["emitter_llh"] == [yow.lat, yow.lon, yow.h]
        assert math.degrees(m.value[0]) == pytest.approx(true_bearing_deg(yow), abs=1e-9)
