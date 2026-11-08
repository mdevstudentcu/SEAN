from __future__ import annotations

from collections.abc import Iterator

from pnt.core.measurement import Measurement
from pnt.sim.scenario import SimRun, generate, load


class SimSource:
    """Measurements from a scenario YAML, faults already injected."""

    def __init__(self, scenario: str, seed: int = 0):
        self.run: SimRun = generate(load(scenario), seed=seed)

    def __iter__(self) -> Iterator[Measurement]:
        return iter(self.run.measurements)
