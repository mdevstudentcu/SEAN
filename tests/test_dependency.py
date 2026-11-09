import pytest

from pnt.core.measurement import SOURCES, Measurement
from pnt.integrity import dependency as dep


@pytest.mark.parametrize(
    "source, expected",
    [
        ("baro", dep.INDEPENDENT),
        ("imu", dep.INDEPENDENT),
        ("vor", dep.INDEPENDENT),
        ("lte", dep.GNSS_TIMED),
        ("gnss", dep.GNSS_DERIVED),
        ("adsb", dep.GNSS_DERIVED),
    ],
)
def test_adr0024_table(source, expected):
    assert dep.tag(source) == expected


def test_every_kind_of_our_gnss_is_derived():
    for kind in ("position_enu", "time", "gnss_health"):
        assert dep.tag("gnss", kind) == dep.GNSS_DERIVED


def test_unclassified_sources_count_as_gnss_dependent():
    # ADR-0024: nr, wifi, ble, fm, leo and cam are TBD, so they must not confirm GNSS
    for source in ("nr", "wifi", "ble", "fm", "leo", "cam", "never-heard-of-it"):
        assert not dep.is_classified(source)
        assert dep.tag(source) == dep.GNSS_DERIVED


def test_every_icd_source_gets_a_tag():
    assert {dep.tag(s) for s in SOURCES} <= {dep.INDEPENDENT, dep.GNSS_TIMED, dep.GNSS_DERIVED}


def test_measurement_tag_uses_source_and_kind():
    m = Measurement(t_ns=0, source="lte", kind="pseudorange", value=(1.0,), sigma=(1.0,))
    assert dep.tag_of(m) == dep.GNSS_TIMED


def test_our_oscillator_is_independent_only_in_holdover():
    assert dep.receiver_clock_tag(gnss_excluded=True) == dep.INDEPENDENT
    assert dep.receiver_clock_tag(gnss_excluded=False) == dep.GNSS_TIMED
