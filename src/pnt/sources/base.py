from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from pnt.core.measurement import Measurement


class Source(Protocol):
    """Anything that yields time-ordered Measurements."""

    def __iter__(self) -> Iterator[Measurement]: ...
