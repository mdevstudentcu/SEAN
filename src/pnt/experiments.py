"""Sensitivity experiments over scenarios (issue #50, REQ-06).

- towers: remove one tower at a time on the same route and rank them by the damage.
- grid: sweep tower count, speed and receiver oscillator, as Khalife & Kassas (IEEE TAES 2020)
  do for their carrier-phase filter. Their accuracy figures do not transfer to our pseudoranges.
- sweep: change one error-model value at a time from the committed scenario (issue #128).
"""

from __future__ import annotations

import copy
import itertools
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from pnt.metrics import score
from pnt.nav import estimate
from pnt.sim.scenario import T0_NS, generate, load

# Oscillator grades for the grid, as a clock drift in ppb. TBC until our radio's is measured.
OSCILLATORS = {"tcxo": 100.0, "ocxo": 5.0}

# The sweep's pseudo-path for the tower count, set through `_with_towers`
TOWERS = "towers"
# Multiples of the committed value for the default sweep (TBC): they bracket it.
FACTORS = (0.25, 0.5, 2.0, 4.0)
# Default sweep (TBC): the LTE error model of the `realistic` set, one parameter at a time.
# `times` multiplies the committed value; `values` are absolute where a multiple makes no sense.
# Entries the scenario does not have are skipped.
DEFAULT_SWEEP: tuple[dict, ...] = (
    {"path": "sources.lte.sigma_m", "times": FACTORS},  # range noise: the truth only
    # the range noise the filter is told; below the truth it is told less than there is
    {"path": "sources.lte.told_sigma_m", "times": FACTORS},
    {"path": "sources.lte.multipath.sigma_m", "times": FACTORS},  # multipath size
    {"path": "sources.lte.multipath.tau_s", "times": FACTORS},  # multipath time constant
    # share of time each tower is heard: a fraction, so absolute values up to 1
    {"path": "sources.lte.dropout.availability", "values": (0.5, 0.9, 1.0)},
    {"path": "sources.lte.told_position_sigma_m", "times": FACTORS},  # told tower position error
    {"path": TOWERS, "values": (2, 3, 6, 8)},  # tower count: a count, so absolute values
    {"path": "clock.drift_ppb", "times": FACTORS},  # receiver clock drift
    {"path": "tower_clocks.site.drift_rw_mps", "times": FACTORS},  # tower clock wander, per site
    {"path": "tower_clocks.builder.drift_rw_mps", "times": FACTORS},  # same, shared by builder
)


def _run(spec: dict, estimator: str, seed: int, drop: str | None = None):
    run = generate(spec, seed=seed)
    meas = [m for m in run.measurements if drop is None or m.emitter != drop]
    estimates = estimate(
        estimator, meas, origin_llh=spec.get("origin_llh"), reference=run.reference
    )
    return run, score(list(estimates), run.truth, spec, T0_NS)


def _run_metrics(spec: dict, estimator: str, seed: int, drop: str | None = None):
    """Only the metrics, so a worker process doesn't send the whole run back."""
    return _run(spec, estimator, seed, drop)[1]


def _run_error(spec: dict, estimator: str, seed: int, drop: str | None = None) -> float:
    return _error(_run_metrics(spec, estimator, seed, drop))


def _map(fn, tasks: list[tuple], jobs: int | None) -> list:
    """`fn(*task)` for every task, in order; across `jobs` processes when `jobs` > 1 (None: every
    core). Each task is one independent seed, so the results match a serial run. Workers start
    from a forkserver, so a script calling this with `jobs` > 1 needs an `if __name__ ==
    "__main__":` guard."""
    jobs = (os.cpu_count() or 1) if jobs is None else jobs
    if jobs <= 1 or len(tasks) <= 1:
        return [fn(*t) for t in tasks]
    # forkserver: forking a process that already runs threads (pytest-xdist, BLAS) can deadlock
    ctx = multiprocessing.get_context("forkserver")
    with ProcessPoolExecutor(min(jobs, len(tasks)), mp_context=ctx) as pool:
        return list(pool.map(fn, *zip(*tasks, strict=True)))


def _error(metrics) -> float:
    """The fault-window error if the scenario has a fault, otherwise the whole run's."""
    return (
        metrics.fault_h_p95_m
        if metrics.fault_h_p95_m == metrics.fault_h_p95_m
        else metrics.h_p95_m
    )


def towers(
    scenario: str, runs: int = 10, estimator: str = "baseline", jobs: int | None = 1
) -> list[dict]:
    """One row per tower, most damaging to lose first, plus the 'all towers' reference.

    Needs real tower positions: synthetic towers are drawn per seed, so a name like `lte:sim2`
    is a different tower in every run and averaging its removal means nothing."""
    spec = load(scenario)
    lte = spec.get("sources", {}).get("lte", {})
    if "towers_from" not in lte and "emitters_llh" not in lte:
        raise ValueError(f"{scenario} has synthetic towers; tower ranking needs real ones")
    names = list(generate(spec, seed=0).emitters)
    tasks = [(spec, estimator, s, drop) for drop in [None, *names] for s in range(runs)]
    errs = np.array(_map(_run_error, tasks, jobs)).reshape(len(names) + 1, runs)
    reference = errs[0]
    rows = [{"removed": "none", "p95_m": float(reference.mean()), "added_m": 0.0}]
    for name, errors in zip(names, errs[1:], strict=True):
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
    jobs: int | None = 1,
) -> list[dict]:
    """One row per combination. The receiver clock follows the scenario.

    The oscillator only reaches the towers when the scenario sets `receiver_clock`, and that only
    means something once the estimator models a clock shared by all towers (#12). Forcing it on
    here made every row a GPS-only filter."""
    base = load(scenario)
    combos = list(itertools.product(tower_counts, speeds, oscillators))
    specs = []
    for count, speed, grade in combos:
        spec = copy.deepcopy(base)
        _with_towers(spec, count)
        spec["trajectory"]["speed_mps"] = speed
        spec["clock"] = {**spec.get("clock", {"rw_ns": 2.0}), "drift_ppb": OSCILLATORS[grade]}
        specs.append(spec)
    tasks = [(spec, estimator, s) for spec in specs for s in range(runs)]
    metrics = _map(_run_metrics, tasks, jobs)
    rows = []
    for i, (count, speed, grade) in enumerate(combos):
        results = metrics[i * runs : (i + 1) * runs]
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


def _tower_count(spec: dict) -> int:
    lte = spec.get("sources", {}).get("lte", {})
    if "towers_from" in lte:
        return int(lte["towers_from"]["count"])
    if "n_emitters" in lte:
        return int(lte["n_emitters"])
    raise KeyError(TOWERS)


def _pseudorange_source(spec: dict, path: str, leaf: str) -> dict | None:
    """The source's config if `path` is `sources.<name>.<leaf>` of a pseudorange source, the only
    model with a told sigma; otherwise None."""
    parts = path.split(".")
    if len(parts) != 3 or parts[0] != "sources" or parts[2] != leaf:
        return None
    cfg = spec.get("sources", {}).get(parts[1])
    return cfg if isinstance(cfg, dict) and cfg.get("model", parts[1]) == "pseudorange" else None


def get_param(spec: dict, path: str) -> float:
    """The number at a dotted path in a loaded spec (`towers`: the tower count). A pseudorange
    source's `told_sigma_m`, if the spec has none, is its `sigma_m`, which is what its records
    report then. A path that is not there, or that does not end on a number, is a ValueError
    naming it."""
    told = _pseudorange_source(spec, path, "told_sigma_m")
    if told is not None and "told_sigma_m" not in told and "sigma_m" in told:
        return told["sigma_m"]
    try:
        if path == TOWERS:
            return _tower_count(spec)
        node = spec
        for key in path.split("."):
            node = node[key]
    except (KeyError, TypeError):
        raise ValueError(f"{spec.get('name', 'scenario')} has no parameter {path!r}") from None
    if isinstance(node, bool) or not isinstance(node, int | float):
        raise ValueError(f"{path!r} is not a number in {spec.get('name', 'scenario')}: {node!r}")
    return node


def set_param(spec: dict, path: str, value: float) -> dict:
    """A copy of `spec` with only the value at `path` changed (checked as `get_param`)."""
    get_param(spec, path)
    spec = copy.deepcopy(spec)
    if path == TOWERS:
        _with_towers(spec, int(value))
        return spec
    # Without a `told_sigma_m` the sim reports `sigma_m` in every record, and the filter sizes
    # its noise and multipath models from that. Pin it to the committed value, or a row meant to
    # change the true noise would also change what the filter is told.
    source = _pseudorange_source(spec, path, "sigma_m")
    if source is not None:
        source.setdefault("told_sigma_m", source["sigma_m"])
    *parents, leaf = path.split(".")
    node = spec
    for key in parents:
        node = node[key]
    node[leaf] = value
    return spec


def default_params(spec: dict) -> dict[str, list[float]]:
    """DEFAULT_SWEEP made concrete for one spec, skipping what it doesn't have."""
    out = {}
    for entry in DEFAULT_SWEEP:
        try:
            base = get_param(spec, entry["path"])
        except ValueError:
            continue
        out[entry["path"]] = (
            [base * k for k in entry["times"]] if "times" in entry else list(entry["values"])
        )
    return out


def _mean(xs) -> float:
    v = np.array(list(xs), float)
    return float(np.nanmean(v)) if not np.all(np.isnan(v)) else float("nan")


def sweep(
    scenario: str | dict,
    params: dict[str, list[float]] | None = None,
    runs: int = 10,
    estimator: str = "baseline",
    jobs: int | None = 1,
) -> list[dict]:
    """One-at-a-time sensitivity: the scenario as committed, then each value of each parameter
    with everything else as committed. Every row runs seeds 0..runs-1, so rows are paired.

    `scenario` is a name or an already loaded spec. `params` maps a dotted path into the loaded
    spec (or `towers`) to its values; None uses DEFAULT_SWEEP. The estimator is not told about
    the change and keeps its own model, except that `told_sigma_m` is exactly what it is told."""
    base = load(scenario) if isinstance(scenario, str) else scenario
    params = default_params(base) if params is None else params
    cases: list[tuple[str, float | None, dict]] = [("baseline", None, base)]
    for path, values in params.items():
        cases += [(path, v, set_param(base, path, v)) for v in values]
    tasks = [(spec, estimator, s) for _, _, spec in cases for s in range(runs)]
    metrics = _map(_run_metrics, tasks, jobs)
    rows = []
    for i, (path, value, _) in enumerate(cases):
        results = metrics[i * runs : (i + 1) * runs]
        committed = get_param(base, path) if value is not None else None
        rows.append(
            {
                "parameter": path if value is not None else "baseline (as committed)",
                "value": value if value is not None else float("nan"),
                "relative": (
                    1.0 if value is None else value / committed if committed else float("nan")
                ),
                "fault_p95_m": _mean(r.fault_h_p95_m for r in results),
                "outage_p95_300s_m": _mean(r.outage_h_p95_300s_m for r in results),
                "hpl_bound_worst": float(min(r.hpl_bound_frac for r in results)),
                "hazardous_epochs": int(sum(r.hazardous_epochs for r in results)),
                "fault_time_err_p95_us": _mean(r.fault_time_err_p95_us for r in results),
            }
        )
    return rows


def markdown(rows: list[dict], fmt=None) -> str:
    """`rows` as a Markdown table; `fmt` formats each value (default: floats to 2 places)."""
    keys = list(rows[0])
    fmt = fmt or (lambda v: f"{v:.2f}" if isinstance(v, float) else str(v))
    lines = ["| " + " | ".join(keys) + " |", "| " + " | ".join("---" for _ in keys) + " |"]
    lines += ["| " + " | ".join(fmt(r[k]) for k in keys) + " |" for r in rows]
    return "\n".join(lines)
