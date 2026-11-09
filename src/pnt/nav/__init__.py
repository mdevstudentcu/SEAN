"""See AGENTS.md for what lives in pnt.nav.

`ESTIMATORS` is the registry behind `pnt ... --estimator NAME`. An estimator is a function that
takes time-ordered Measurements and an optional `origin_llh` (the session origin, for emitters
given in lat/lon) and yields Estimates (see `baseline.run`).

`estimate` is the one place that feeds measurements to an estimator, whatever the source (sim,
replay or live, ADR-0004). It passes only the receivers the estimator models (ICD-measurement):
`payload` by default. An estimator that models more sets a `receivers` attribute, e.g.
`run.receivers = RECEIVERS` for a base/rover filter (ADR-0020). Such an estimator is also
given the session's `reference` block (ICD-session: the station's surveyed position), as the
`reference` keyword.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterable, Iterator

from pnt.core.measurement import Estimate, Measurement
from pnt.nav import base_rover, baseline, ekf

DEFAULT_RECEIVERS = frozenset({"payload"})


def configured(fn: Callable, **config) -> Callable:
    """`fn` with `config` passed to it, modelling the same receivers."""
    out = functools.partial(fn, **config)
    out.receivers = getattr(fn, "receivers", DEFAULT_RECEIVERS)
    return out


ESTIMATORS = {
    "baseline": baseline.run,
    "ekf": ekf.run,
    "ekf-base": base_rover.run,
    # Stage 2 (#12): the same filters with IMU-driven prediction (nav/imu.py)
    "ekf-imu": configured(ekf.run, motion="imu"),
    "ekf-base-imu": configured(base_rover.run, motion="imu"),
}

log = logging.getLogger(__name__)


def receivers(estimator: Callable) -> frozenset[str]:
    """The receivers an estimator models: its `receivers` attribute, else payload only."""
    return frozenset(getattr(estimator, "receivers", DEFAULT_RECEIVERS))


def estimate(
    estimator: str | Callable,
    measurements: Iterable[Measurement],
    origin_llh=None,
    reference: dict | None = None,
) -> Iterator[Estimate]:
    """Run `estimator` (a registry name or the function) over `measurements`, passing only the
    receivers it models. Records it drops are counted and logged as a warning when the run ends,
    so they are never lost silently. `reference` is the session's `reference` block; only an
    estimator that models the reference receiver is given it, and only when there is one."""
    name = estimator if isinstance(estimator, str) else getattr(estimator, "__name__", "?")
    fn = ESTIMATORS[estimator] if isinstance(estimator, str) else estimator
    keep = receivers(fn)
    dropped: dict[str, int] = {}

    def fed() -> Iterator[Measurement]:
        for m in measurements:
            if m.receiver in keep:
                yield m
            else:
                dropped[m.receiver] = dropped.get(m.receiver, 0) + 1

    extra = {"reference": reference} if reference is not None and "reference" in keep else {}
    try:
        yield from fn(fed(), origin_llh=origin_llh, **extra)
    finally:
        if dropped:
            log.warning(
                "%s models receivers %s: dropped %s",
                name,
                sorted(keep),
                ", ".join(f"{n} {r} records" for r, n in sorted(dropped.items())),
            )
