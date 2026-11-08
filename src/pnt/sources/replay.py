from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from pnt.core.measurement import Measurement
from pnt.io.mcap_log import read_session


class ReplaySource:
    """Measurements from a recorded session (`/meas/*` topics), in log-time order.

    `hide` drops sources to simulate their loss after the fact, e.g. hide={"gnss": (t0, t1)}.
    """

    def __init__(self, path: str | Path, hide: dict[str, tuple[int, int | None]] | None = None):
        self.path = Path(path)
        self.hide = hide or {}

    def __iter__(self) -> Iterator[Measurement]:
        for _, rec in read_session(self.path, topics=["/meas/"]):
            window = self.hide.get(rec.source)
            if window and rec.t_ns >= window[0] and (window[1] is None or rec.t_ns < window[1]):
                continue
            yield rec
