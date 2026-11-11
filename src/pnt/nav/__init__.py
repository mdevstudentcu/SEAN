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
from functools import partial

from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.jump_guard import JumpGuard
from pnt.integrity.mhss import MHSS
from pnt.nav import base_rover, baseline, cells, ekf

DEFAULT_RECEIVERS = frozenset({"payload"})


def configured(fn: Callable, **config) -> Callable:
    """`fn` with `config` passed to it, modelling the same receivers."""
    out = functools.partial(fn, **config)
    out.receivers = getattr(fn, "receivers", DEFAULT_RECEIVERS)
    return out


ESTIMATORS = {
    "baseline": baseline.run,
    "ekf": ekf.run,
    "ekf-calibrated": ekf.run_calibrated,  # opt-in: ADR-0022 clocks and the tower error model
    "ekf-base": base_rover.run,
    # ekf-mhss: the same EKF, with solution-separation protection levels and exclusion (#82)
    "ekf-mhss": partial(ekf.run, monitor=MHSS),
    # ekf-mhss-beacon: ekf-mhss that may use a located jammer as a low-trust beacon (#93,
    # ADR-0025). Only behind the monitor, which holds the beacon's own fault hypothesis
    "ekf-mhss-beacon": partial(ekf.run, monitor=MHSS, hostile={}),
    # Stage 2 (#12): the same filters with IMU-driven prediction (nav/imu.py)
    "ekf-imu": configured(ekf.run, motion="imu"),
    "ekf-base-imu": configured(base_rover.run, motion="imu"),
    # Opt-in jump guard (#184, ADR-0038 Proposed): the same filters, refusing a detected GNSS
    # position jump until it is undone
    "ekf-guard": configured(ekf.run, jump_guard=JumpGuard),
    "ekf-imu-guard": configured(ekf.run, motion="imu", jump_guard=JumpGuard),
    "ekf-calibrated-guard": configured(ekf.run_calibrated, jump_guard=JumpGuard),
    # opt-in (#147, ADR-0039): learn a radio's LTE range noise from its innovations
    "ekf-learned-noise": configured(ekf.run, noise_tau_s=ekf.NOISE_TAU_S),
    "ekf-calibrated-learned-noise": configured(
        ekf.run_calibrated, noise_tau_s=ekf.CALIBRATED_NOISE_TAU_S
    ),
    # Opt-in (#147, ADR-0043 Proposed): a radio's LTE records told ADR-0036's measured sigma
    # from their SNR instead of the front end's (nav/told_sigma.py)
    "ekf-measured-sigma": configured(ekf.run, told_sigma_model="adr0036"),
    "ekf-calibrated-measured-sigma": configured(ekf.run_calibrated, told_sigma_model="adr0036"),
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
        for m in cells.attach(measurements, origin_llh):
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
