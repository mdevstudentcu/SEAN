"""Sensitivity experiments over scenarios (issue #50, REQ-06).

- towers: remove one tower at a time on the same route and rank them by the damage.
- grid: sweep tower count, speed and receiver oscillator, as Khalife & Kassas (IEEE TAES 2020)
  do for their carrier-phase filter. Their accuracy figures do not transfer to our pseudoranges.
"""

from __future__ import annotations

import copy
import itertools

import numpy as np

from pnt.metrics import score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

# Oscillator grades for the grid, as a clock drift in ppb. TBC until our radio's is measured.
OSCILLATORS = {"tcxo": 100.0, "ocxo": 5.0}


def _run(spec: dict, estimator: str, seed: int, drop: str | None = None):
    run = generate(spec, seed=seed)
    meas = [m for m in run.measurements if drop is None or m.emitter != drop]
    estimates = estimate(estimator, meas, origin_llh=spec.get("origin_llh"))
    return run, score(list(estimates), run.truth, spec, T0_NS)


def _error(metrics) -> float:
    """The fault-window error if the scenario has a fault, otherwise the whole run's."""
    return (
        metrics.fault_h_p95_m
        if metrics.fault_h_p95_m == metrics.fault_h_p95_m
        else metrics.h_p95_m
    )


def towers(scenario: str, runs: int = 10, estimator: str = "baseline") -> list[dict]:
    """One row per tower, most damaging to lose first, plus the 'all towers' reference.

    Needs real tower positions: synthetic towers are drawn per seed, so a name like `lte:sim2`
    is a different tower in every run and averaging its removal means nothing."""
    spec = load(scenario)
    lte = spec.get("sources", {}).get("lte", {})
    if "towers_from" not in lte and "emitters_llh" not in lte:
        raise ValueError(f"{scenario} has synthetic towers; tower ranking needs real ones")
    names = list(generate(spec, seed=0).emitters)
    reference = np.array([_error(_run(spec, estimator, s)[1]) for s in range(runs)])
    rows = [{"removed": "none", "p95_m": float(reference.mean()), "added_m": 0.0}]
    for name in names:
        errors = np.array([_error(_run(spec, estimator, s, drop=name)[1]) for s in range(runs)])
        rows.append(
            {
                "removed": name,
                "p95_m": float(errors.mean()),
                "added_m": float((errors - reference).mean()),
            }
        )
    return rows[:1] + sorted(rows[1:], key=lambda r: -r["added_m"])


def _with_towers(spec: dict, count: int) -> None:
    lte = spec["sources"]["lte"]
    if "towers_from" in lte:
        lte["towers_from"]["count"] = count
    else:
        lte["n_emitters"] = count


def grid(
    scenario: str,
    runs: int = 10,
    estimator: str = "baseline",
    tower_counts=(3, 4, 6),
    speeds=(4.0, 8.0, 13.0),
    oscillators=tuple(OSCILLATORS),
) -> list[dict]:
    """One row per combination. The receiver clock follows the scenario.

    The oscillator only reaches the towers when the scenario sets `receiver_clock`, and that only
    means something once the estimator models a clock shared by all towers (#12). Forcing it on
    here made every row a GPS-only filter."""
    base = load(scenario)
    rows = []
    for count, speed, grade in itertools.product(tower_counts, speeds, oscillators):
        spec = copy.deepcopy(base)
        _with_towers(spec, count)
        spec["trajectory"]["speed_mps"] = speed
        spec["clock"] = {**spec.get("clock", {"rw_ns": 2.0}), "drift_ppb": OSCILLATORS[grade]}
        results = [_run(spec, estimator, s)[1] for s in range(runs)]
        rows.append(
            {
                "towers": count,
                "speed_mps": speed,
                "oscillator": grade,
                "p95_m": float(np.mean([_error(r) for r in results])),
                "hpl_bound_worst": float(min(r.hpl_bound_frac for r in results)),
            }
        )
    return rows


def markdown(rows: list[dict]) -> str:
    keys = list(rows[0])
    fmt = lambda v: f"{v:.2f}" if isinstance(v, float) else str(v)  # noqa: E731
    lines = ["| " + " | ".join(keys) + " |", "| " + " | ".join("---" for _ in keys) + " |"]
    lines += ["| " + " | ".join(fmt(r[k]) for k in keys) + " |" for r in rows]
    return "\n".join(lines)
