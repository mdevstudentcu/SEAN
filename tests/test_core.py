from datetime import UTC, datetime

import numpy as np
import pytest

from pnt.core import frames
from pnt.core.measurement import Estimate, Measurement, from_json, to_json, validate
from pnt.core.time import (
    LEAP_SECONDS,
    gps_ns_to_unix_ns,
    gps_ns_to_utc,
    gps_ns_to_week_tow,
    utc_to_gps_ns,
)

ORIGIN = (45.3876, -75.6960, 70.0)


def test_measurement_json_roundtrip_with_numpy_values():
    m = Measurement(
        t_ns=1,
        source="lte",
        kind="pseudorange",
        value=(np.float64(1.5),),
        sigma=(2.0,),
        emitter="lte:sim0",
        meta={"emitter_enu": np.array([1.0, 2, 3])},
    )
    back = from_json(to_json(m), Measurement)
    assert back.value == (1.5,) and back.meta["emitter_enu"] == [1.0, 2.0, 3.0]


def test_validate_rejects_unknown_kind_and_bad_sigma():
    with pytest.raises(ValueError):
        validate(Measurement(t_ns=0, source="lte", kind="vibes", value=(1,), sigma=(1,)))
    with pytest.raises(ValueError):
        validate(Measurement(t_ns=0, source="lte", kind="range", value=(1, 2), sigma=(1,)))


def test_estimate_roundtrip():
    e = Estimate(t_ns=5, pos_enu=(1, 2, 3), vel_enu=(0, 0, 0), pos_cov=tuple(range(9)))
    assert from_json(to_json(e), Estimate).pos_enu == (1, 2, 3)


def test_gps_time_roundtrip_and_known_week():
    dt = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)
    t = utc_to_gps_ns(dt)
    assert gps_ns_to_utc(t) == dt
    week, _ = gps_ns_to_week_tow(t)
    assert week == 2444  # GPS week of 2026-11-12


def test_gps_to_unix_time():
    assert gps_ns_to_unix_ns(0) == (315_964_800 - LEAP_SECONDS) * 1_000_000_000
    dt = datetime(2026, 11, 12, 18, 0, 0, 123456, tzinfo=UTC)
    assert gps_ns_to_unix_ns(utc_to_gps_ns(dt) + 789) == int(dt.timestamp()) * 10**9 + 123_456_789


def test_enu_roundtrip_and_origin_is_zero():
    assert np.allclose(frames.llh_to_enu(ORIGIN, ORIGIN), 0, atol=1e-6)
    enu = np.array([1234.5, -678.9, 42.0])
    llh = frames.enu_to_llh(enu, ORIGIN)
    assert np.allclose(frames.llh_to_enu(llh, ORIGIN), enu, atol=1e-4)


def test_one_degree_of_latitude_is_about_111_km():
    north = frames.llh_to_enu((ORIGIN[0] + 1, ORIGIN[1], ORIGIN[2]), ORIGIN)
    assert 111_000 < north[1] < 111_300


def test_receiver_defaults_to_payload():
    m = Measurement(t_ns=0, source="lte", kind="pseudorange", value=(1.0,), sigma=(1.0,))
    assert m.receiver == "payload"
    validate(m)


def test_record_without_receiver_field_decodes_as_payload():
    # JSON as written before the field existed
    old = b'{"t_ns":1,"source":"lte","kind":"pseudorange","value":[1.5],"sigma":[2.0],"meta":{}}'
    assert from_json(old, Measurement).receiver == "payload"


def test_validate_accepts_reference_and_rejects_unknown_receiver():
    m = Measurement(
        t_ns=0, source="lte", kind="pseudorange", value=(1,), sigma=(1,), receiver="reference"
    )
    validate(m)
    assert from_json(to_json(m), Measurement).receiver == "reference"
    with pytest.raises(ValueError, match="receiver"):
        validate(
            Measurement(t_ns=0, source="lte", kind="range", value=(1,), sigma=(1,), receiver="x")
        )
