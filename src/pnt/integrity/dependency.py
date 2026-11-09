"""GNSS-dependency tags (ADR-0024): does a measurement fail together with GPS?

- independent: the signal and its timing owe nothing to GNSS. Can confirm or refute GNSS.
- gnss-timed: the signal is independent, but the transmitter's clock is GNSS-disciplined. Its
  geometry survives a GNSS fault; its time does not.
- gnss-derived: the content is someone's GNSS fix. Never confirms GNSS.

The tag belongs to the source type, so it is a lookup table keyed by `source`, or by
`(source, kind)` where a kind differs from its source. A source not in the table is treated as
GNSS-derived, the conservative default, until it is classified (ADR-0024 lists `nr`, `wifi`,
`ble`, `fm`, `leo` and `cam` as `TBD`).
"""

from __future__ import annotations

from pnt.core.measurement import Measurement

INDEPENDENT = "independent"
GNSS_TIMED = "gnss-timed"
GNSS_DERIVED = "gnss-derived"
UNCLASSIFIED = GNSS_DERIVED  # ADR-0024: unclassified sources count as GNSS-dependent

# Keys are a source, or (source, kind) where a kind's tag differs from its source's.
# `dme`, `ils`, `p25`, `sbas` and `remote_id` are not in the ICD source registry yet; they are
# listed so their class is on record (ADR-0024: P25 is never received, SBAS and Remote ID are sim
# only).
TAGS: dict[str | tuple[str, str], str] = {
    "baro": INDEPENDENT,
    "imu": INDEPENDENT,
    "vor": INDEPENDENT,
    "dme": INDEPENDENT,
    "ils": INDEPENDENT,
    "lte": GNSS_TIMED,
    "p25": GNSS_TIMED,
    "gnss": GNSS_DERIVED,  # our own receiver: position, time and health
    "adsb": GNSS_DERIVED,  # aircraft report their own GNSS position
    "sbas": GNSS_DERIVED,
    "remote_id": GNSS_DERIVED,
}


def tag(source: str, kind: str | None = None) -> str:
    """The ADR-0024 tag of a source (and kind), or the conservative default if unclassified."""
    if kind is not None and (source, kind) in TAGS:
        return TAGS[(source, kind)]
    return TAGS.get(source, UNCLASSIFIED)


def tag_of(m: Measurement) -> str:
    return tag(m.source, m.kind)


def is_classified(source: str) -> bool:
    return source in TAGS


def receiver_clock_tag(gnss_excluded: bool) -> str:
    """Our own oscillator: GNSS-disciplined while GNSS is used, independent only in holdover."""
    return INDEPENDENT if gnss_excluded else GNSS_TIMED
