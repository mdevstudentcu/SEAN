"""GNSS-dependency tags (ADR-0024): does a measurement fail together with GPS?

- independent: the signal and its timing owe nothing to GNSS. Can confirm or refute GNSS.
- gnss-timed: the signal is independent, but the transmitter's clock is GNSS-disciplined. Its
  geometry survives a GNSS fault; its time does not.
- gnss-derived: the content is someone's GNSS fix. Never confirms GNSS.

The tag belongs to the source type, so it is a lookup table keyed by `source`, or by
`(source, kind)` where a kind differs from its source. A source not in the table is treated as
GNSS-derived, the conservative default, until it is classified (ADR-0024 lists `nr`, `wifi`,
`ble`, `fm`, `leo` and `cam` as `TBD`).

A prior learned from someone's GNSS carries its class too. A tower map handed on by a drone
(P12, `nav/tower_map.py`) is GNSS-derived (ADR-0048): its clocks and told-position errors are
fitted to the drone's GNSS position, so a spoof of that position poisons them. `tag_of(m,
priors=[TOWER_MAP])` gives the class of a reading used against such a prior.
"""

from __future__ import annotations

from collections.abc import Iterable

from pnt.core.measurement import Measurement

INDEPENDENT = "independent"
GNSS_TIMED = "gnss-timed"
GNSS_DERIVED = "gnss-derived"
UNCLASSIFIED = GNSS_DERIVED  # ADR-0024: unclassified sources count as GNSS-dependent
ORDER = (INDEPENDENT, GNSS_TIMED, GNSS_DERIVED)  # least to most dependent on GNSS

TOWER_MAP = "tower_map"  # not a Measurement source: a drone's learned tower map (ADR-0048)

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
    TOWER_MAP: GNSS_DERIVED,  # fitted to the drone's GNSS position (ADR-0048)
}


def tag(source: str, kind: str | None = None) -> str:
    """The ADR-0024 tag of a source (and kind), or the conservative default if unclassified."""
    if kind is not None and (source, kind) in TAGS:
        return TAGS[(source, kind)]
    return TAGS.get(source, UNCLASSIFIED)


def most_dependent(tags: Iterable[str]) -> str:
    """The most GNSS-dependent of `tags` (independent if there are none)."""
    return max(tags, key=ORDER.index, default=INDEPENDENT)


def tag_of(m: Measurement, priors: Iterable[str] = ()) -> str:
    """The tag of a measurement's evidence. `priors`: the sources of priors it is used against
    (for example `TOWER_MAP`); evidence is as GNSS-dependent as the most dependent of them."""
    return most_dependent([tag(m.source, m.kind), *(tag(p) for p in priors)])


def is_classified(source: str) -> bool:
    return source in TAGS


def receiver_clock_tag(gnss_excluded: bool) -> str:
    """Our own oscillator: GNSS-disciplined while GNSS is used, independent only in holdover."""
    return INDEPENDENT if gnss_excluded else GNSS_TIMED
