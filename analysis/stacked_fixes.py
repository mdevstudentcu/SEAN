"""Stacked fixes on the drone leg (#218), sim: what learned LTE noise (ADR-0039), carrier hopping
(ADR-0040) and the jump guard (ADR-0038) buy alone and together, against T1 (25 m for 300 s) and
the mentors' fallback (50 m for 120 s), ADR-0034.

Only committed scenario entries and existing opt-in estimators. A combination with no registered
name (learned noise + guard) is built from the registered pieces' own configuration hooks,
`configured(ekf.run, noise_tau_s=ekf.NOISE_TAU_S, jump_guard=JumpGuard)`; no filter behaviour is
added here.

Rows, paired seeds (each seed gives every row on a scenario the same records):
- outage, `challenge-drone-outage` (1 carrier, 2460) and `challenge-drone-hop-outage` cut to its
  first 6 or all 13 carriers (`hopping_study.spec_of`): no LTE (control), today (told the
  reported 2 m), + learned noise, + hopping, learned noise + hopping (the stack), the stack + the
  jump guard, and told the true noise on 13 carriers (a ceiling: no real receiver knows it);
  each for `ekf` and `ekf-calibrated`;
- held 300 m jump from 150 s, `challenge-drone-spoof-jump` and `challenge-drone-hop-spoof-jump`
  (13 carriers): default, `-guard`, and guard + learned noise.

Scored as ADR-0034's amendment: at each whole second after GPS loss (after the jump starts, on the
jump rows) the 95th percentile of horizontal error across runs; a target holds if the worst second
of its window is within it (`worst_in`). Also per row: the median over seeds of each run's own p95
(the older tables' statistic), hazardous epochs, the HPL bound share and, on jump rows, whether
the estimate sits on the spoofed position at +120 s.

    python analysis/stacked_fixes.py --seeds 0-49 --jobs 10 --host g14   # committed results
    python analysis/stacked_fixes.py --seeds 100-109 --jobs 3 --out <dir>
    python analysis/stacked_fixes.py --redraw    # summary and figure from rows.json

`--study measured` (#257) runs the same statistic on a study variant of the drone leg whose LTE
white noise is sized from our real static captures instead of the leg's 50 m (see
`MEASURED_SIZES`), beside the assumed sizes on the same seeds, with one sensitivity row for each
size no capture measures. No committed scenario entry or default changes: the variant is the
committed entry with `sigma_m: 0` and its records post-processed here (`measured_records`).

    python analysis/stacked_fixes.py --study measured --families ekf --seeds 0-49 --jobs 6
    python analysis/stacked_fixes.py --study measured --families ekf-calibrated --seeds 0-49 \
        --jobs 6    # merged into the same rows.json when commit and seeds match

Committed results need a clean tree; per-run data goes to the git-ignored `results/runs/`.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import platform
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from statistics import NormalDist

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hopping_study  # noqa: E402
import lte_noise_eval  # noqa: E402
from msgspec.structs import replace  # noqa: E402

from pnt.cli import _commit  # noqa: E402
from pnt.experiments import _map  # noqa: E402
from pnt.integrity.jump_guard import JumpGuard  # noqa: E402
from pnt.metrics import ALERT_LIMIT_M, gps_loss, score  # noqa: E402
from pnt.nav import ESTIMATORS, configured, ekf, estimate, told_sigma  # noqa: E402
from pnt.sim.lte_front_end import AMBIGUITY_M  # noqa: E402
from pnt.sim.scenario import T0_NS, generate, load  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "stacked-fixes"
RUNS = HERE / "results" / "runs" / "stacked-fixes"  # git-ignored
# ADR-0034: T1 (ours, TBC) and the mentors' fallback; both 95 % horizontal error after GPS loss
FALLBACK_M, FALLBACK_S = 50.0, 120
T1_M, T1_S = 25.0, 300
HORIZON_S = T1_S
SPOOF_AT_S = 120.0  # s after the jump: is the estimate on the spoofed position?
# Each run is cut 1 s after its 300 s window: the filters are causal, so every estimate in the
# window is the full run's, and the calibrated filter on 13 carriers needs half the time and
# memory (its memory grows with run length, about 2 GB at 720 s)
CUT_AFTER_S = HORIZON_S + 1

# Scenario specs, each generated once per seed
SPECS = {
    "nolte": "no LTE records (`challenge-drone-outage` without `sources.lte`)",
    "1c": "`challenge-drone-outage` (1 carrier, 2460)",
    "6c": "`challenge-drone-hop-outage`, first 6 carriers",
    "13c": "`challenge-drone-hop-outage` (13 carriers)",
    "13c-true": "`challenge-drone-hop-outage` (13 carriers), told the true noise",
    "jump-1c": "`challenge-drone-spoof-jump` (300 m, 1 carrier)",
    "jump-13c": "`challenge-drone-hop-spoof-jump` (300 m, 13 carriers)",
}

# Estimators: registered names, or the two combinations built from the same hooks the registry uses
COMBOS = {
    "ekf-learned-noise+guard": configured(
        ekf.run, noise_tau_s=ekf.NOISE_TAU_S, jump_guard=JumpGuard
    ),
    "ekf-calibrated-learned-noise+guard": configured(
        ekf.run_calibrated, noise_tau_s=ekf.CALIBRATED_NOISE_TAU_S, jump_guard=JumpGuard
    ),
}
FAMILIES = {  # family -> (default, learned noise, guard, learned noise + guard)
    "ekf": ("ekf", "ekf-learned-noise", "ekf-guard", "ekf-learned-noise+guard"),
    "ekf-calibrated": (
        "ekf-calibrated",
        "ekf-calibrated-learned-noise",
        "ekf-calibrated-guard",
        "ekf-calibrated-learned-noise+guard",
    ),
}


def estimator(name: str):
    return COMBOS[name] if name in COMBOS else ESTIMATORS[name]


def rows() -> list[dict]:
    """Every row, in table order. `ladder`: its place in the figure (None: table only)."""
    out = []
    for fam, (dflt, learned, guard, both) in FAMILIES.items():
        outage = [
            ("no-lte", "no LTE (control)", "nolte", dflt, 0),
            ("today", "today: 1 carrier, told 2 m", "1c", dflt, 1),
            ("learned", "+ learned noise", "1c", learned, 2),
            ("hop6", "+ hopping 6 carriers", "6c", dflt, 3),
            ("hop13", "+ hopping 13 carriers", "13c", dflt, 4),
            ("learned-hop6", "learned noise + 6 carriers", "6c", learned, None),
            ("stack", "learned noise + 13 carriers", "13c", learned, 5),
            ("stack-guard", "all three: + jump guard", "13c", both, 6),
            ("ceiling", "told the true noise, 13 carriers (not available)", "13c-true", dflt, 7),
        ]
        for key, label, spec, est, ladder in outage:
            out.append({"key": f"{fam}:{key}", "family": fam, "kind": "outage", "label": label,
                        "spec": spec, "estimator": est, "ladder": ladder})  # fmt: skip
        for spec, where in (("jump-1c", "1 carrier"), ("jump-13c", "13 carriers")):
            for key, label, est in (
                ("default", "default", dflt),
                ("guard", "jump guard", guard),
                ("guard-learned", "jump guard + learned noise", both),
            ):
                out.append({"key": f"{fam}:{spec}:{key}", "family": fam, "kind": "jump",
                            "label": f"held 300 m jump, {where}: {label}", "spec": spec,
                            "estimator": est, "ladder": None})  # fmt: skip
    return out


def spec_of(key: str) -> dict:
    if key.startswith("m-"):
        return measured_spec_of(key)
    cfgs = {c["key"]: c for c in hopping_study.configs()}
    if key == "nolte":
        return lte_noise_eval._spec(hopping_study.ONE_CARRIER, "nolte")
    if key == "1c":
        return hopping_study.spec_of(cfgs["one-carrier"], "committed")
    if key == "6c":
        return hopping_study.spec_of(cfgs["scan-6-1s"], "committed")
    if key == "13c":
        return hopping_study.spec_of(cfgs["scan-13-1s"], "committed")
    if key == "13c-true":
        return hopping_study.spec_of(cfgs["scan-13-1s"], "true-noise")
    if key == "jump-1c":
        return copy.deepcopy(load("challenge-drone-spoof-jump"))
    if key == "jump-13c":
        return copy.deepcopy(load("challenge-drone-hop-spoof-jump"))
    raise KeyError(key)


# --- the measured-sizes variant (#257) ---------------------------------------------------------
MEASURED_OUT = HERE / "results" / "stacked-fixes-measured"
MEASURED_RUNS = HERE / "results" / "runs" / "stacked-fixes-measured"  # git-ignored
# Random streams of the post-processing, apart from the sim's (220 to 228): each term draws on a
# stream of its own per cell, on a 10 ms grid of the run, so one term's draws do not depend on
# which records another term keeps, and every variant of a seed sees the same draws
_WHITE_STREAM, _ARC_STREAM, _HOP_LOSS_STREAM = 240, 241, 242
_GRID_S = 0.01

# Arc restarts of the LTE front end on `main` (#245 and the re-acquisition fix, front end at
# `ea72f6a`) on two real static sessions with GPS truth: `analysis/results/lte-reacq-steps/
# summary.json`, "after". Per session: new arcs, 10 Hz pseudorange records (tracked cell time x
# 10), and the re-find steps (|double-difference change| when one cell of a pair starts a new
# arc): their number, median (m), 90th percentile (m) and share over 100 m.
REACQ_AFTER = {
    "20261111-0151-static-fullsuite2": {
        "new_arcs": 53, "records_10hz": 15457, "steps": 64, "step_median_m": 9.44,
        "step_p90_m": 1033.4, "steps_over_100m": 0.15625,
    },
    "20261111-0233-static-lte-1h": {
        "new_arcs": 197, "records_10hz": 92342, "steps": 192, "step_median_m": 10.07,
        "step_p90_m": 461.5, "steps_over_100m": 0.171875,
    },
}  # fmt: skip
# The arc model (sensitivity row only; ADR-0049, Proposed). A cell starts new arcs at the pooled
# measured rate, in wall time; each arc carries one range offset for as long as it lasts, drawn
# independently: "far" with probability ARC_FAR_SHARE, uniform within +/- ARC_FAR_M, otherwise
# normal with ARC_NEAR_SIGMA_M. A step is the difference of two arcs' offsets, so a step over
# 100 m needs either arc far (1 - (1 - q)^2, about the measured share); two near arcs give the
# median.
ARC_RATE_HZ = sum(r["new_arcs"] for r in REACQ_AFTER.values()) / (
    sum(r["records_10hz"] for r in REACQ_AFTER.values()) * 0.1
)
_STEPS_OVER_100M = sum(r["steps"] * r["steps_over_100m"] for r in REACQ_AFTER.values()) / sum(
    r["steps"] for r in REACQ_AFTER.values()
)
# TBC, chosen (ADR-0049): puts the model's step p90 (about 0.4 x this) between the two sessions'
# (462 and 1,033 m). The fix's notes put the far steps at 0.5 to 1 km p90, from the re-search.
ARC_FAR_M = 1500.0
# A step involving a far arc is still under 100 m with probability about 100 m / ARC_FAR_M (the
# other arc's offset falls within 100 m of the uniform one), so 1 - (1 - q)^2 is a little more
# than the measured share
ARC_FAR_SHARE = 1.0 - math.sqrt(1.0 - _STEPS_OVER_100M / (1.0 - 100.0 / ARC_FAR_M))
# Near offsets: the steps' median (9.4 and 10.1 m on the two sessions, averaged) is reached by
# the near-to-near steps, a share (1 - q)^2 of all, below their own quantile 0.5 / (1 - q)^2;
# a near-to-near step is |N(0, sqrt(2) s)|
ARC_NEAR_SIGMA_M = float(np.mean([r["step_median_m"] for r in REACQ_AFTER.values()])) / (
    math.sqrt(2.0) * NormalDist().inv_cdf(0.5 + 0.25 / (1.0 - ARC_FAR_SHARE) ** 2)
)
# TBC, a sweep point, not a value (ADR-0049): share of hop dwells in which a cell is not re-found
HOP_LOSS = 0.5
# Sensitivity points for the sizes no capture measures (ADR-0049)
TOWER_SWEEP_M = (50.0, 20.0)  # main row: the leg's 100 m
MULTIPATH_AT_REST = {"sigma_m": told_sigma.SIGMA_CORR_M, "tau_s": told_sigma.TAU_CORR_S}

# Every size the measured rows use, against the leg's: (term, assumed, measured rows, source)
MEASURED_SIZES = (
    ("White range noise per record", "50 m at 1 Hz, every record",
     "ADR-0036 law from the record's SNR: σ² = 0.64² + 2.28² / SNR_lin (10 Hz, SNR ≥ −8 dB), "
     "12.4 m (−11 to −8 dB), 24.7 m (−14 to −11 dB), × √(20 / n_epochs); 1 Hz record: 0.2 to "
     "7.8 m; below −14 dB 49.4 m (× 0.32 at 1 Hz = 15.6 m)",
     "measured at −14 dB and up: `analysis/results/lte-measured-noise/summary.json`, 15 real "
     "static sessions `20261110-*`, front end and analysis at `e9a9053`; ADR-0036 consequence 1; "
     "`pnt.nav.told_sigma.white_sigma_m`. Below −14 dB not measured: ADR-0044's 49.4 m (`TBC`)"),
    ("Correlated range error (multipath)", "50 m, 30 s Gauss-Markov per eNB",
     "50 m, 30 s (unchanged: no capture measures it on the move)",
     "assumed (`challenge-drone.yaml`, `TBC`). Sensitivity: ADR-0036's at-rest 10 m, 3 s "
     "(same-eNB S(1 s) 4.9 to 18 m, `20261110-*`), a floor for a moving drone, not a value"),
    ("Tower table position error", "100 m per axis per eNB", "100 m (unchanged)",
     "assumed (`TBC`, ASM-02 `TBD`; not measurable at rest). Sensitivity: 50 m, 20 m"),
    ("Arc restarts and steps", "none (`arc` always 0)", "none (unchanged)",
     "Sensitivity: restarts at the measured rate with steps sized from "
     "`analysis/results/lte-reacq-steps/summary.json` (after, front end `ea72f6a`; real static "
     "sessions `20261111-0151-static-fullsuite2`, `20261111-0233-static-lte-1h`, GPS truth); "
     "far-offset size `TBC` (ADR-0049)"),
    ("Hop re-acquisition loss", "none (0.15 s dead time per dwell)", "none (unchanged)",
     "not modelled, no hopped capture (ADR-0040). Sensitivity: half of the dwells lose the cell"),
    ("Told sigma (today, + 13 carriers)", "2 m", "2 m (unchanged)", "`challenge-drone.yaml`"),
    ("Dropout, tower clocks, dongle, GNSS, IMU, baro, trajectory", "as the leg", "as the leg",
     "assumed (`TBC`). Tower clocks: the leg's 0.035 m/s per site is inside ADR-0036's "
     "same-eNB bound (0.5 m/s); between eNBs `TBD`"),
)  # fmt: skip

# Spec keys of the measured study: the generated spec and what is done to its records
MEASURED_SPECS = {
    "m-1c": "`1c` with the measured white noise",
    "m-13c": "`13c` with the measured white noise",
    "m-13c-true": "`m-13c`, told the true noise (each record's white σ and the multipath)",
    "m-13c-tp50": "`m-13c`, tower position error 50 m",
    "m-13c-tp20": "`m-13c`, tower position error 20 m",
    "m-13c-mprest": "`m-13c`, multipath at the at-rest 10 m, 3 s",
    "m-13c-arcs": "`m-13c` with arc restarts and steps",
    "m-13c-hoploss": "`m-13c` with half of the hop dwells lost",
}
_MEASURED_GEN = {  # spec key -> the key whose generated run it post-processes
    "m-13c-true": "m-13c",
    "m-13c-arcs": "m-13c",
    "m-13c-hoploss": "m-13c",
}


def gen_of(key: str) -> str:
    """The spec key whose generated run `key` uses (itself, or a post-processed sibling's)."""
    return _MEASURED_GEN.get(key, key)


def measured_rows() -> list[dict]:
    """The measured study's rows, in table order. `ladder`: the figure line; `sizes`: assumed,
    measured, both (no LTE) or sensitivity (one size moved from the measured stack)."""
    out = []
    for fam, (dflt, learned, _guard, _both) in FAMILIES.items():
        ladder = [
            ("no-lte", "no LTE (control)", "nolte", dflt),
            ("today", "today: 1 carrier, told 2 m", "1c", dflt),
            ("learned", "+ learned noise", "1c", learned),
            ("hop13", "+ 13 carriers", "13c", dflt),
            ("stack", "learned noise + 13 carriers", "13c", learned),
            ("ceiling", "ceiling: told the true noise, 13 carriers", "13c-true", dflt),
        ]
        for i, (key, label, spec, est) in enumerate(ladder):
            for sizes in ("assumed", "measured") if spec != "nolte" else ("both",):
                s = f"m-{spec}" if sizes == "measured" else spec
                out.append({"key": f"{fam}:{sizes}:{key}", "family": fam, "kind": "outage",
                            "label": label, "sizes": sizes, "spec": s, "estimator": est,
                            "ladder": i})  # fmt: skip
        sens = [
            ("tp50", "stack, tower position 50 m", "m-13c-tp50"),
            ("tp20", "stack, tower position 20 m", "m-13c-tp20"),
            ("mprest", "stack, multipath at rest (10 m, 3 s)", "m-13c-mprest"),
            ("arcs", "stack, arc restarts and steps", "m-13c-arcs"),
            ("hoploss", "stack, half of hop dwells lost", "m-13c-hoploss"),
        ]
        for j, (key, label, spec) in enumerate(sens):
            out.append({"key": f"{fam}:sensitivity:{key}", "family": fam, "kind": "outage",
                        "label": label, "sizes": "sensitivity", "spec": spec,
                        "estimator": learned, "ladder": len(ladder) + j})  # fmt: skip
    return out


def measured_spec_of(key: str) -> dict:
    """The spec generated for a measured key: the committed entry with `sigma_m: 0` (white noise
    is added per record by `measured_records`) and, for a sensitivity key, the one size moved."""
    base = "1c" if key == "m-1c" else "13c"
    spec = spec_of(base)
    lte = spec["sources"]["lte"]
    lte["sigma_m"] = 0.0
    if key == "m-13c-tp50":
        lte["told_position_sigma_m"] = TOWER_SWEEP_M[0]
    elif key == "m-13c-tp20":
        lte["told_position_sigma_m"] = TOWER_SWEEP_M[1]
    elif key == "m-13c-mprest":
        lte["multipath"] = dict(MULTIPATH_AT_REST)
    elif key not in ("m-1c", "m-13c"):
        raise KeyError(key)
    return spec


def arc_offsets(rng: np.random.Generator, duration_s: float) -> tuple[np.ndarray, np.ndarray]:
    """One cell's arcs over a run: (start time of arcs 1, 2, ... in s; offset of each arc in m,
    arc 0 first). Restarts are a Poisson process at ARC_RATE_HZ; offsets as ARC_FAR_SHARE."""
    gaps = rng.exponential(1.0 / ARC_RATE_HZ, int(duration_s * ARC_RATE_HZ * 3) + 20)
    starts = np.cumsum(gaps)
    starts = starts[starts < duration_s]
    n = len(starts) + 1
    far = rng.random(n) < ARC_FAR_SHARE
    offset = np.where(far, rng.uniform(-ARC_FAR_M, ARC_FAR_M, n),
                      rng.normal(0.0, ARC_NEAR_SIGMA_M, n))  # fmt: skip
    return starts, offset


def _cell_rng(seed: int, stream: int, meta: dict) -> np.random.Generator:
    return np.random.default_rng([seed, stream, int(meta["earfcn"]), int(meta["pci"])])


def measured_records(
    records: list, seed: int, spec: dict, *, true_told: bool = False, arcs: bool = False,
    hop_loss: float = 0.0,
) -> list:  # fmt: skip
    """`records` (generated with LTE `sigma_m: 0`) with each LTE pseudorange given white noise of
    `told_sigma.white_sigma_m(snr_db, n_epochs)`; optionally told the true noise (that white σ
    and the spec's multipath σ together), given arc restarts and steps (`meta.arc` counts them),
    or with each cell's record dropped in a share `hop_loss` of dwells. Other records as given."""
    duration = float(spec["duration_s"])
    n = int(round(duration / _GRID_S)) + 2
    mp = float((spec["sources"]["lte"].get("multipath") or {}).get("sigma_m", 0.0))
    cells: dict[tuple[int, int], tuple] = {}
    out = []
    for m in records:
        if m.source != "lte" or m.kind != "pseudorange":
            out.append(m)
            continue
        cell = (int(m.meta["earfcn"]), int(m.meta["pci"]))
        if cell not in cells:
            z = _cell_rng(seed, _WHITE_STREAM, m.meta).standard_normal(n)
            u = _cell_rng(seed, _HOP_LOSS_STREAM, m.meta).random(n)
            arc = arc_offsets(_cell_rng(seed, _ARC_STREAM, m.meta), duration)
            cells[cell] = (z, u, arc)
        z, u, (starts, offset) = cells[cell]
        t_s = (m.t_ns - T0_NS) / 1e9
        i = int(round(t_s / _GRID_S))
        if hop_loss and u[i] < hop_loss:
            continue
        white = told_sigma.white_sigma_m(float(m.meta["snr_db"]), int(m.meta["n_epochs"]))
        value = m.value[0] + white * z[i]
        meta = m.meta
        if arcs:
            k = int(np.searchsorted(starts, t_s, side="right"))
            value += offset[k]
            meta = {**meta, "arc": k}
        sigma = (math.hypot(white, mp),) if true_told else m.sigma
        out.append(replace(m, value=(float(value % AMBIGUITY_M),), sigma=sigma, meta=meta))
    return out


def records_of(key: str, records: list, seed: int, spec: dict) -> list:
    """The records a row on spec `key` sees, from the run generated for `gen_of(key)`."""
    if not key.startswith("m-"):
        return records
    return measured_records(
        records, seed, spec, true_told=key == "m-13c-true", arcs=key == "m-13c-arcs",
        hop_loss=HOP_LOSS if key == "m-13c-hoploss" else 0.0,
    )  # fmt: skip


STUDIES = {  # study -> (rows, spec description, default output, per-run data)
    "stack": (rows, SPECS, OUT, RUNS),
    "measured": (measured_rows, {**{k: SPECS[k] for k in ("nolte", "1c", "13c", "13c-true")},
                                 **MEASURED_SPECS}, MEASURED_OUT, MEASURED_RUNS),
}  # fmt: skip


def window_start(spec: dict) -> tuple[int, list[float] | None]:
    """(t_ns the clock of a row starts, the jump offset ENU or None): GPS loss, else the jump."""
    loss = gps_loss(spec, T0_NS)
    if loss is not None:
        return loss[0], None
    (f,) = [f for f in spec["faults"] if f["type"] == "spoof_jump"]
    return T0_NS + int(round(f["start_s"] * 1e9)), [float(v) for v in f["offset_enu_m"]]


# --- the statistic (ADR-0034 amendment) --------------------------------------------------------
def p95_by_second(curves: np.ndarray) -> np.ndarray:
    """The 95th percentile across runs (axis 0) at each second (axis 1)."""
    return np.percentile(np.asarray(curves, float), 95, axis=0)


def worst_in(curve: np.ndarray, window_s: float) -> float:
    """The largest 95 % error in the first `window_s` s after GPS loss (seconds 0 to window_s
    included): a target "<= X m for >= T s" holds only if the whole window is within X. Same
    definition as `worst_in` in PR #178's `analysis/accuracy_budget.py`, not on this base."""
    return float(np.max(curve[: int(window_s) + 1]))


def worst_second(curve: np.ndarray, window_s: float) -> int:
    return int(np.argmax(curve[: int(window_s) + 1]))


# --- one seed ----------------------------------------------------------------------------------
def run_task(gen_key: str, family: str, seed: int, study: str = "stack") -> list[dict]:
    """Every row of `study` and `family` whose spec is generated as `gen_key`, on one seed's
    records (post-processed per spec by `records_of`)."""
    spec = spec_of(gen_key)
    sim = generate(spec, seed=seed)
    start, offset = window_start(spec)
    cut = start + CUT_AFTER_S * 1_000_000_000
    kept = [m for m in sim.measurements if m.t_ns <= cut]
    out = []
    for row in STUDIES[study][0]():
        if gen_of(row["spec"]) != gen_key or row["family"] != family:
            continue
        records = records_of(row["spec"], kept, seed, spec)
        t0 = time.perf_counter()
        est = list(
            estimate(estimator(row["estimator"]), records,
                     origin_llh=spec.get("origin_llh"), reference=sim.reference)
        )  # fmt: skip
        m = score(est, sim.truth, spec, T0_NS)
        truth = {g.t_ns: g for g in sim.truth}
        pairs = [(e, truth[e.t_ns]) for e in est if e.t_ns in truth]
        t = np.array([e.t_ns for e, _ in pairs])
        err = np.array([math.dist(e.pos_enu[:2], g.pos_enu[:2]) for e, g in pairs])
        hpl = np.array([e.hpl_m for e, _ in pairs])
        at = {int(tt): i for i, tt in enumerate(t)}
        curve = [err[at[start + k * 1_000_000_000]] for k in range(HORIZON_S + 1)]
        r = {"row": row["key"], "seed": seed, "curve": [round(float(x), 2) for x in curve]}
        for s in (FALLBACK_S, T1_S):
            w = (t >= start) & (t < start + s * 1_000_000_000)
            r[f"run_p95_{s}s"] = float(np.percentile(err[w], 95))
        w = (t >= start) & (t < start + T1_S * 1_000_000_000)
        r["hpl_bound_300s"] = float(np.mean(hpl[w] >= err[w]))
        r["hazardous_epochs"] = int(m.hazardous_epochs)
        if offset is not None:
            i = at[start + int(SPOOF_AT_S * 1e9)]
            e, g = pairs[i]
            spoofed = (g.pos_enu[0] + offset[0], g.pos_enu[1] + offset[1])
            r["from_spoof_120s"] = float(math.dist(e.pos_enu[:2], spoofed))
            r["on_spoof_120s"] = bool(r["from_spoof_120s"] < math.hypot(*offset[:2]) / 2)
        r["run_s"] = round(time.perf_counter() - t0, 1)
        out.append(r)
    return out


def tasks(seeds: list[int], study: str = "stack", families=None) -> list[tuple]:
    rs = [r for r in STUDIES[study][0]() if families is None or r["family"] in families]
    pairs = sorted({(gen_of(r["spec"]), r["family"]) for r in rs})
    # Longest first: the 13-carrier calibrated filters take the most time
    pairs.sort(key=lambda p: ("13c" not in p[0], p[1] != "ekf-calibrated"))
    return [(s, f, seed, study) for s, f in pairs for seed in seeds]


# --- aggregate ---------------------------------------------------------------------------------
def aggregate(runs: list[dict], study: str = "stack") -> list[dict]:
    out = []
    for row in STUDIES[study][0]():
        mine = sorted((r for r in runs if r["row"] == row["key"]), key=lambda r: r["seed"])
        if not mine:
            continue
        curve = p95_by_second([r["curve"] for r in mine])
        hz = [r["hazardous_epochs"] for r in mine]
        bound = [r["hpl_bound_300s"] for r in mine]
        a = {
            **row,
            "runs": len(mine),
            "worst_120s_m": worst_in(curve, FALLBACK_S),
            "worst_120s_at_s": worst_second(curve, FALLBACK_S),
            "worst_300s_m": worst_in(curve, T1_S),
            "worst_300s_at_s": worst_second(curve, T1_S),
            "median_run_p95_120s_m": float(np.median([r["run_p95_120s"] for r in mine])),
            "median_run_p95_300s_m": float(np.median([r["run_p95_300s"] for r in mine])),
            "hazardous_epochs": int(sum(hz)),
            "hazardous_seeds": [r["seed"] for r in mine if r["hazardous_epochs"] > 0],
            "hpl_bound_300s_median": float(np.median(bound)),
            "hpl_bound_300s_min": float(min(bound)),
            "p95_curve_m": [round(float(x), 1) for x in curve],
        }
        if row["kind"] == "jump":
            a["on_spoof_120s"] = int(sum(r["on_spoof_120s"] for r in mine))
        out.append(a)
    return out


# --- outputs -----------------------------------------------------------------------------------
def _m(x: float) -> str:
    return f"{x:,.0f}" if x >= 10 else f"{x:.1f}"


def _seeds_text(seeds: list[int]) -> str:
    if seeds == list(range(seeds[0], seeds[-1] + 1)):
        return f"{seeds[0]}–{seeds[-1]}"
    return ", ".join(map(str, seeds))


def summary(data: dict) -> str:
    rs = data["rows"]
    lines = [
        "# Stacked fixes on the drone leg (#218)",
        "",
        f"**Sim, every value `TBC`** (ADR-0015; LTE noise, hop set, dwell and the learned-noise "
        f"prior are not sized from real data). `{data['command']}` at {data['commit']} on "
        f"{data['host']}, seeds {_seeds_text(data['seeds'])} (paired), "
        f"{data['elapsed_min']:.1f} min. Hopping is a study leg (ADR-0040): the payload cannot "
        "hop yet. Learned noise (ADR-0039) and the jump guard (ADR-0038) are opt-in estimators; "
        "learned noise + guard has no registered name and is "
        "`configured(ekf.run[_calibrated], noise_tau_s=..., jump_guard=JumpGuard)`.",
        "",
        "Scenario entries: " + "; ".join(f"`{k}` = {v}" for k, v in SPECS.items()) + ".",
        "",
        "**Statistic (ADR-0034 amendment):** at each whole second after GPS loss (after the jump "
        "starts, on jump rows) the 95th percentile of horizontal error across the "
        f"{rs[0]['runs']} runs; the worst second of 0–{FALLBACK_S} s is scored against the "
        f"fallback ({FALLBACK_M:.0f} m) and of 0–{T1_S} s against T1 ({T1_M:.0f} m). With "
        "this many runs the per-second 95th percentile moves by several metres from one second to "
        "the next. *Median run p95*: median over seeds of each run's own p95 over the window "
        "(older tables). *Hazardous*: epochs from the run's start to the end of the 300 s "
        "window (each run is cut there) with error over the "
        f"{ALERT_LIMIT_M:.0f} m alert limit while HPL is under it (total, seeds). *HPL bound*: "
        "share of the first 300 s with HPL >= error, median (min) over seeds.",
        "",
        f"| Row | Estimator | Scenario | Worst second 0–{FALLBACK_S} s (m) | "
        f"<= {FALLBACK_M:.0f} m | Worst second 0–{T1_S} s (m) | <= {T1_M:.0f} m | "
        f"Median run p95 {FALLBACK_S} / {T1_S} s (m) | "
        "Hazardous (seeds) | HPL bound 300 s | On spoof +120 s |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rs:
        hz = r["hazardous_seeds"]
        more = ", …" if len(hz) > 6 else ""
        seeds = f" ({', '.join(map(str, hz[:6]))}{more})" if hz else ""
        lines.append(
            f"| {r['label']} | `{r['estimator']}` | `{r['spec']}` | "
            f"{_m(r['worst_120s_m'])} (s {r['worst_120s_at_s']}) | "
            f"{'yes' if r['worst_120s_m'] <= FALLBACK_M else 'no'} | "
            f"{_m(r['worst_300s_m'])} (s {r['worst_300s_at_s']}) | "
            f"{'yes' if r['worst_300s_m'] <= T1_M else 'no'} | "
            f"{_m(r['median_run_p95_120s_m'])} / {_m(r['median_run_p95_300s_m'])} | "
            f"{r['hazardous_epochs']:,} [{len(hz)}/{r['runs']}]{seeds} | "
            f"{r['hpl_bound_300s_median']:.2f} ({r['hpl_bound_300s_min']:.2f}) | "
            + (f"{r['on_spoof_120s']}/{r['runs']}" if r["kind"] == "jump" else "–")
            + " |"
        )
    lines += [
        "",
        "Notes:",
        "",
        "- Hazardous seeds list at most the first six.",
        "- The ceiling row is told the sim's true LTE noise (white and multipath together), which "
        "no real receiver knows: an upper bound on what better noise knowledge could buy, not a "
        "result.",
        "- On the outage rows the jump guard has nothing to refuse (no GNSS fix arrives before "
        "the cut), so *all three* equals the stack.",
        "- Jump rows: the clock starts at the jump (150 s), GPS stays on (spoofed), and the error "
        "includes following the jump (about 300 m). *On spoof*: within half the jump of where the "
        "spoofer puts the receiver. A guarded estimate can land there while coasting with GNSS "
        "excluded: seen on tuning seed 105; the reported seeds' cases were not inspected.",
        "",
        "## Not checked",
        "",
        "- Any real capture: no hopped capture exists, and the learned-noise prior (40 m) and "
        "memories (60 s, 120 s) were chosen on sim tuning seeds 100–109 (ADR-0039).",
        "- `ekf-imu` and other estimators: no learned-noise variant is registered for them.",
        "- Jump guard + learned noise on clean (no jump) runs beyond the outage rows here, and "
        "false alarms.",
        "",
    ]
    return "\n".join(lines)


def plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colours = {"ekf": "#2a78d6", "ekf-calibrated": "#eb6834"}  # categorical slots 1, 2
    markers = {"ekf": "o", "ekf-calibrated": "s"}
    ink, grid = "#52514e", "#e4e3df"
    lad = [r for r in data["rows"] if r["ladder"] is not None]
    labels = {r["ladder"]: r["label"] for r in lad}
    n = len(labels)
    assert n <= 8, "at most 8 rows per panel"
    fig, axes = plt.subplots(1, 2, figsize=(16, 8.2), dpi=120, sharey=True)
    for ax, (key, t_s, target, who) in zip(
        axes,
        (("worst_120s_m", FALLBACK_S, FALLBACK_M, "mentors' fallback"),
         ("worst_300s_m", T1_S, T1_M, "T1")),
        strict=True,
    ):  # fmt: skip
        vals = [r[key] for r in lad]
        lo, hi = min(vals + [target]) / 2.5, max(vals) * 4
        for fam, dy in (("ekf", -0.16), ("ekf-calibrated", 0.16)):
            pts = sorted((r for r in lad if r["family"] == fam), key=lambda r: r["ladder"])
            y = [r["ladder"] + dy for r in pts]
            x = [r[key] for r in pts]
            ax.plot(x, y, markers[fam], color=colours[fam], ms=13, mec="white", mew=1.5,
                    label=fam, zorder=3)  # fmt: skip
            for xi, yi in zip(x, y, strict=True):
                ax.text(xi * 1.13, yi, f"{xi:,.0f} m", va="center", fontsize=13, color=ink)
        ax.axvline(target, color=ink, lw=2, ls="--", zorder=1)
        ax.text(target * 1.08, -0.45, f"{target:.0f} m ({who})", ha="left", va="center",
                fontsize=14, color=ink)  # fmt: skip
        ax.set_xscale("log")
        ax.set_xlim(lo, hi)
        ax.set_title(f"worst second of 0–{t_s} s after GPS loss", fontsize=16, loc="left")
        ax.set_xlabel("95 % horizontal error across runs (m, log)", fontsize=14)
        ax.tick_params(labelsize=13)
        ax.grid(True, axis="x", which="major", color=grid, lw=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(range(n), [textwrap.fill(labels[i], 30) for i in range(n)], fontsize=14)
    axes[0].set_ylim(n - 0.4, -0.6)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="upper right", bbox_to_anchor=(0.995, 0.995), ncol=2,
               fontsize=14, frameon=False, markerscale=0.8)  # fmt: skip
    fig.suptitle(
        "Drone leg, stacked fixes: worst-second 95 % error after GPS loss\n"
        f"{data['rows'][0]['runs']} runs per row (seeds {_seeds_text(data['seeds'])}), "
        f"{data['commit']} (sim, every value TBC; hopping is a study leg)",
        fontsize=15,
        x=0.01,
        y=0.995,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def _yes(x: float, target: float) -> str:
    return "yes" if x <= target else "no"


def measured_summary(data: dict) -> str:
    rs = data["rows"]
    parts = "; ".join(
        f"`{p['command']}` on {p['host']}, {p['elapsed_min']:.1f} min" for p in data["parts"]
    )
    lines = [
        "# Stacked fixes with LTE error sizes from our captures (#257)",
        "",
        "**Sim, a study variant of the drone leg** (ADR-0015; no committed scenario entry or "
        f"default changed). At {data['commit']}: {parts}. Seeds {_seeds_text(data['seeds'])}, "
        "paired: on a seed every row sees the same trajectory, GNSS, IMU, baro, dongle, tower "
        "clocks, multipath, dropout and table error draws, so *assumed* and *measured* differ "
        "only in the LTE white noise (and a sensitivity row in its one moved size). Only the "
        "white noise is measured, and at rest (ADR-0036): the measured rows keep every other "
        "size at the leg's assumed value. Hopping is a study leg (ADR-0040): the payload "
        "cannot hop yet. Choices of this study: ADR-0049 (Proposed).",
        "",
        "## Sizes",
        "",
        "| Term | Assumed rows (the leg) | Measured rows | Source |",
        "|---|---|---|---|",
    ]
    lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in MEASURED_SIZES]
    lines += [
        "",
        f"Arc model of the sensitivity row (ADR-0049): restarts every {1 / ARC_RATE_HZ:.0f} s "
        f"per cell on average (Poisson; {sum(r['new_arcs'] for r in REACQ_AFTER.values())} new "
        "arcs over "
        f"{sum(r['records_10hz'] for r in REACQ_AFTER.values()) / 10:,.0f} tracked cell-seconds"
        f"); each arc's offset is far with probability {ARC_FAR_SHARE:.3f} (uniform within "
        f"±{ARC_FAR_M:,.0f} m, `TBC`), else normal with σ {ARC_NEAR_SIGMA_M:.1f} m. This gives "
        f"{_STEPS_OVER_100M:.1%} of steps over 100 m and a median step of about 10 m, as "
        "measured (`tests/test_stacked_fixes.py` checks the model against "
        "`REACQ_AFTER`). The default filters ignore `meta.arc` (`arc_bias` is off).",
        "",
        "Specs: " + "; ".join(f"`{k}` = {v}" for k, v in STUDIES["measured"][1].items()) + ".",
        "",
        "**Statistic (ADR-0034 amendment):** at each whole second after GPS loss the 95th "
        f"percentile of horizontal error across the {rs[0]['runs']} runs; the worst second of "
        f"0–{FALLBACK_S} s is scored against the fallback ({FALLBACK_M:.0f} m) and of "
        f"0–{T1_S} s against T1 ({T1_M:.0f} m). *Median run p95*: median over seeds of each "
        "run's own p95 over the window. *Hazardous*: epochs to the end of the 300 s window "
        f"with error over the {ALERT_LIMIT_M:.0f} m alert limit while HPL is under it (total "
        "[seeds]). *HPL bound*: share of the first 300 s with HPL >= error, median (min) over "
        "seeds.",
        "",
        "## Ladder: assumed against measured",
        "",
    ]
    fams = [f for f in FAMILIES if any(r["family"] == f for r in rs)]
    by = {(r["family"], r["sizes"], r["ladder"]): r for r in rs}
    head = "| Row |" + "".join(
        f" `{f}` {sz} {FALLBACK_S} / {T1_S} s (m) |"
        for f in fams
        for sz in ("assumed", "measured")
    )
    lines += [head, "|---|" + "---|---|" * len(fams)]
    for i in range(6):
        cells = []
        label = None
        for f in fams:
            for sizes in ("assumed", "measured"):
                r = by.get((f, sizes, i)) or by.get((f, "both", i))
                label = label or (r["label"] if r else None)
                cells.append(f"{_m(r['worst_120s_m'])} / {_m(r['worst_300s_m'])}" if r else "–")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Every row",
        "",
        f"| Row | Sizes | Estimator | Spec | Worst second 0–{FALLBACK_S} s (m) | "
        f"<= {FALLBACK_M:.0f} m | Worst second 0–{T1_S} s (m) | <= {T1_M:.0f} m | "
        f"Median run p95 {FALLBACK_S} / {T1_S} s (m) | Hazardous [seeds] | HPL bound 300 s |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rs:
        hz = r["hazardous_seeds"]
        more = ", …" if len(hz) > 6 else ""
        seeds = f" ({', '.join(map(str, hz[:6]))}{more})" if hz else ""
        lines.append(
            f"| {r['label']} | {r['sizes']} | `{r['estimator']}` | `{r['spec']}` | "
            f"{_m(r['worst_120s_m'])} (s {r['worst_120s_at_s']}) | "
            f"{_yes(r['worst_120s_m'], FALLBACK_M)} | "
            f"{_m(r['worst_300s_m'])} (s {r['worst_300s_at_s']}) | "
            f"{_yes(r['worst_300s_m'], T1_M)} | "
            f"{_m(r['median_run_p95_120s_m'])} / {_m(r['median_run_p95_300s_m'])} | "
            f"{r['hazardous_epochs']:,} [{len(hz)}/{r['runs']}]{seeds} | "
            f"{r['hpl_bound_300s_median']:.2f} ({r['hpl_bound_300s_min']:.2f}) |"
        )
    lines += [
        "",
        "## Read with",
        "",
        "- The measured white noise is at rest, on one RTL-SDR, at two spots in one "
        "neighbourhood, before #245 (ADR-0036's amendment says its bins will move). Below "
        "−14 dB nothing was measured; ADR-0044's 49.4 m (`TBC`) stands there.",
        "- A static capture cannot size multipath on a moving drone, tower table error, bias, "
        "or arc restarts in motion; those stay at the leg's values in the measured rows and "
        "are moved one at a time in the sensitivity rows. The multipath-at-rest row is a floor "
        "for a moving drone, not a value.",
        "- The arc row uses the front end on `main` after its re-acquisition fix. Before it, "
        "the real GPS-cut replays (#214, ADR-0044) saw 90 of 103 new arcs at SNR ≥ −8 dB step "
        "more than 100 m (median 874 m); that front end is not modelled here.",
        "- The ceiling is told each record's true white σ and the multipath σ, which no real "
        "receiver knows: a bound on what noise knowledge could buy, not a result.",
        "- The learned-noise prior and memories were chosen on the assumed leg (ADR-0039, "
        "seeds 100–109); nothing was retuned for the measured sizes.",
        "",
    ]
    return "\n".join(lines)


def measured_plot(data: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colours = {"assumed": "#2a78d6", "measured": "#eb6834", "both": "#52514e",
               "sensitivity": "#eb6834"}  # fmt: skip
    ink, grid = "#52514e", "#e4e3df"
    rs = data["rows"]
    fams = [f for f in FAMILIES if any(r["family"] == f for r in rs)]
    marker = {"ekf": "o", "ekf-calibrated": "s"}
    offsets = {}
    for j, f in enumerate(fams):
        base = (j - (len(fams) - 1) / 2) * 0.34
        offsets |= {(f, "assumed"): base - 0.09, (f, "measured"): base + 0.09,
                    (f, "both"): base, (f, "sensitivity"): base}  # fmt: skip
    labels = {r["ladder"]: r["label"] for r in rs}
    n = max(labels) + 1
    fig, axes = plt.subplots(1, 2, figsize=(17, 10), dpi=120, sharey=True)
    for ax, (key, t_s, target, who) in zip(
        axes,
        (("worst_120s_m", FALLBACK_S, FALLBACK_M, "mentors' fallback"),
         ("worst_300s_m", T1_S, T1_M, "T1")),
        strict=True,
    ):  # fmt: skip
        vals = [r[key] for r in rs]
        ax.set_xscale("log")
        ax.set_xlim(min(vals + [target]) / 2.5, max(vals) * 5)
        ax.axhspan(5.5, n - 0.4, color="#f4f3f0", zorder=0)
        for r in rs:
            y = r["ladder"] + offsets[(r["family"], r["sizes"])]
            ax.plot(r[key], y, marker[r["family"]], color=colours[r["sizes"]], ms=11,
                    mec="white", mew=1.5, zorder=3)  # fmt: skip
            ax.text(r[key] * 1.14, y, f"{r[key]:,.0f}", va="center", fontsize=11, color=ink)
        ax.axvline(target, color=ink, lw=2, ls="--", zorder=1)
        ax.text(target * 1.08, -0.75, f"{target:.0f} m ({who})", ha="left", va="center",
                fontsize=13, color=ink)  # fmt: skip
        ax.set_title(f"worst second of 0–{t_s} s after GPS loss", fontsize=15, loc="left")
        ax.set_xlabel("95 % horizontal error across runs (m, log)", fontsize=13)
        ax.tick_params(labelsize=12)
        ax.grid(True, axis="x", which="major", color=grid, lw=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(range(n), [textwrap.fill(labels[i], 32) for i in range(n)], fontsize=12)
    axes[0].set_ylim(n - 0.4, -1.1)
    axes[0].text(axes[0].get_xlim()[0] * 1.1, 5.56, "sensitivity: one assumed size moved "
                 "from the measured stack", fontsize=11, color=ink, va="top")  # fmt: skip
    handles = [
        Line2D([], [], ls="", marker="o", color=colours["assumed"], ms=10,
               label="assumed sizes (50 m white)"),
        Line2D([], [], ls="", marker="o", color=colours["measured"], ms=10,
               label="measured white noise (at rest)"),
    ]  # fmt: skip
    handles += [Line2D([], [], ls="", marker=marker[f], color=ink, ms=10, label=f) for f in fams]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.995, 0.995), ncol=2,
               fontsize=12, frameon=False)  # fmt: skip
    fig.suptitle(
        "Drone leg, stacked fixes: assumed against measured LTE white noise\n"
        f"{rs[0]['runs']} runs per row (seeds {_seeds_text(data['seeds'])}), {data['commit']} "
        "(sim; white noise measured at rest, every other size assumed, TBC)",
        fontsize=14, x=0.01, y=0.995, ha="left",
    )  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def _clean(commit: str, untracked: str = "") -> bool:
    """True for the hash of a clean tree (`_commit()` gives `<hash>-dirty` otherwise), as in
    PR #170's `analysis/challenge_baseline.py`, with no untracked file outside .gitignore
    (`untracked`: `git status --porcelain` output), which `--dirty` does not see."""
    return len(commit) >= 7 and all(c in "0123456789abcdef" for c in commit) and not untracked


def _untracked() -> str:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=HERE, capture_output=True, text=True
    )
    return out.stdout.strip() if out.returncode == 0 else "no git"


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def merged(old: dict | None, new: dict) -> dict:
    """`new`'s rows, plus `old`'s rows of other families when both are the same study, commit and
    seeds (a family run apart, e.g. `ekf` first and `ekf-calibrated` later); `parts` keeps each
    run's command, host and time."""
    same = old is not None and all(old.get(k) == new[k] for k in ("study", "commit", "seeds"))
    if not same:
        return new
    fams = {r["family"] for r in new["rows"]}
    keep = [r for r in old["rows"] if r["family"] not in fams]
    parts = [p for p in old.get("parts", []) if not set(p["families"]) & fams]
    order = {r["key"]: i for i, r in enumerate(STUDIES[new["study"]][0]())}
    return {**new, "rows": sorted(keep + new["rows"], key=lambda r: order[r["key"]]),
            "parts": parts + new["parts"]}  # fmt: skip


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--study", choices=sorted(STUDIES), default="stack")
    p.add_argument("--families", default=",".join(FAMILIES), help="e.g. ekf (default: both)")
    p.add_argument("--seeds", default="0-49", help="e.g. 0-49 (reported) or 100-109 (tuning)")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--host", default=f"{platform.system()} {platform.machine()}")
    p.add_argument("--out", type=Path, default=None, help="default: the study's results folder")
    p.add_argument("--redraw", action="store_true", help="from rows.json, without running")
    args = p.parse_args(argv)
    _, _, default_out, runs_dir = STUDIES[args.study]
    out = args.out or default_out
    families = [f for f in args.families.split(",") if f]
    if unknown := set(families) - set(FAMILIES):
        raise SystemExit(f"unknown families {sorted(unknown)}")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "rows.json"
    if args.redraw:
        data = json.loads(path.read_text())
    else:
        commit = _commit()
        # The study's own results may be untracked: a family run later merges into them
        own = f"{default_out.relative_to(HERE.parent).as_posix()}/"
        untracked = "\n".join(
            line for line in _untracked().splitlines() if not line[3:].startswith(own)
        )
        if out.resolve() == default_out.resolve() and not _clean(commit, untracked):
            raise SystemExit(
                f"tree is {commit}: commit first, the committed results must name a clean commit "
                "(or write elsewhere with --out)"
            )
        seeds = parse_seeds(args.seeds)
        todo = tasks(seeds, args.study, families)
        t0 = time.perf_counter()
        runs = [r for rs in _map(run_task, todo, args.jobs) for r in rs]
        elapsed = (time.perf_counter() - t0) / 60
        study_flag = "" if args.study == "stack" else f" --study {args.study}"
        fam_flag = "" if set(families) == set(FAMILIES) else f" --families {args.families}"
        command = (
            f"python analysis/stacked_fixes.py{study_flag}{fam_flag} --seeds {args.seeds} "
            f"--jobs {args.jobs}"
        )
        data = {
            "study": args.study,
            "command": command,
            "commit": commit,
            "host": args.host,
            "seeds": seeds,
            "elapsed_min": elapsed,
            "parts": [
                {
                    "families": families,
                    "command": command,
                    "host": args.host,
                    "elapsed_min": elapsed,
                }
            ],  # fmt: skip
            "rows": aggregate(runs, args.study),
        }
        if path.exists():
            data = merged(json.loads(path.read_text()), data)
        runs_dir.mkdir(parents=True, exist_ok=True)
        tag = "" if set(families) == set(FAMILIES) else f"-{'+'.join(families)}"
        per_run = runs_dir / f"{commit}-seeds-{args.seeds}{tag}.json"
        per_run.write_text(json.dumps({"commit": commit, "runs": runs}))
        print(f"wrote {per_run}")
        path.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    if data.get("study", "stack") == "measured":
        (out / "summary.md").write_text(measured_summary(data))
        measured_plot(data, out / "ladder.png")
    else:
        (out / "summary.md").write_text(summary(data))
        plot(data, out / "ladder.png")


if __name__ == "__main__":
    main()
