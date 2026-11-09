"""Real tower geometry and wrong tower tables, through the cell lookup and the filter (#124).

Measurement level. The UC-01 drone circuit flies over Carleton while real Rogers eNB positions
from `lte-cells-ottawa.csv` are heard on one carrier. Truth, GNSS, barometer and IMU come from
the simulator (its own LTE records are dropped); LTE records are generated here, shaped as
`pnt.frontends.lte` writes them (`lte:<earfcn>:<pci>`, no tower position, one dongle clock,
values known only modulo one frame). They go through `cells.attach` and `nav.estimate`, and are
scored with `pnt.metrics`, so the numbers mean what `pnt eval` means.

    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \\
        python analysis/lte_real_geometry.py geometry --seeds 10 --out /tmp/geometry.png
    (same prefix) python analysis/lte_real_geometry.py wrong-table --seeds 10 --out /tmp/wt.png

`geometry` asks whether T1 is met on real geometry; `wrong-table` asks whether a wrong table
leaves the filter honest or confidently wrong. The thread limits matter: each worker otherwise
starts one BLAS thread per core. ekf-mhss runs a sub-filter per site and is the expensive one.

Evidence kind: simulation over real tower positions. No real signals: range errors are white
noise and per-site clocks only, so multipath, NLOS, blockage, sector patterns, tower clock jumps
and link budgets are not in it. Every eNB within the hearing range is heard, always. The record
rate and every clock and noise value here are `TBC` until the radio test replaces them
(ADR-0015). Only pseudoranges are generated: the front end's Doppler records are left out, and
the reported sigma equals the true noise. `nav.estimate` has no table argument, so the lookup is
run here first with `cells.attach(table=..., counts=...)`, which is also how its counts are read;
the attach inside `nav.estimate` then passes the records through untouched.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import numpy as np

from pnt import metrics, nav
from pnt.core.frames import enu_to_llh, llh_to_enu
from pnt.core.measurement import Measurement
from pnt.nav import cells
from pnt.nav.cells import COLLISION, MATCHED, OUT_OF_RANGE, UNKNOWN, CellTable
from pnt.sim import models, scenario, trajectory

C = 299_792_458.0
FRAME_M = C * 0.01  # one 10 ms LTE frame, as the front end sets `ambiguity_m`
T0 = scenario.T0_NS
T1_LIMIT_M = 25.0  # T1, TBC (systems/plan.md)
ESTIMATORS = ("ekf", "ekf-calibrated", "ekf-imu", "ekf-mhss")
WRONG_TABLE_ESTIMATORS = ("ekf", "ekf-calibrated", "ekf-mhss")
HORIZONS_S = (60.0, 120.0, 300.0)
# Random streams of their own, so a case changes only what it changes and seeds stay paired
_NOISE, _SITE_CLOCK, _RX_CLOCK, _TABLE, _ROGUE = 1241, 1242, 1243, 1244, 1245

# Clock values, all TBC. Site clocks take the ADR-0022 form with the realistic set's sizes
# (scenarios/sets/realistic.yaml): a builder clock (one builder, Rogers) plus a site residual.
BUILDER_CLOCK = {"drift_mps": 0.0354, "drift_rw_mps": 2.7e-4}  # TBC, realistic set
SITE_CLOCK = {  # TBC, realistic set, but the offset can be anywhere in the frame (FDD)
    "offset_m": FRAME_M,
    "drift_mps": 0.0354,
    "offset_rw_m": 0.2,
    "drift_rw_mps": 2.7e-4,
}


@dataclass(frozen=True)
class World:
    """What the records are generated from."""

    scenario: str = "uc01-drone-circuit"
    earfcn: int = 2460  # Rogers, 875 MHz
    hearing_km: float = 3.0  # TBC: no capture yet shows real link range
    sigma_m: float = 20.0  # TBC: the sim's placeholder (RSK-02); also the reported sigma
    rate_hz: float = 1.0  # TBC: UC-01's LTE rate
    gps_off_s: float = 120.0  # as UC-01
    outage_s: float = 300.0  # T1 needs 300 s; UC-01's own outage is 120 s
    tail_s: float = 60.0  # GPS back, to see recovery
    rx_drift_ppm: float = 0.4  # TBC: the dongle's frequency error (120 m/s of range rate)
    rx_offset_rw_m: float = 0.6  # TBC: m/sqrt(s), the realistic set's 2 ns/sqrt(s) receiver clock
    rx_wander_mps: float = 0.05  # TBC: m/s/sqrt(s), dongle frequency wander
    rogue_km: float = 1.0  # TBC: how far the unregistered tower is from the one it imitates


@dataclass(frozen=True)
class Case:
    """How the table, or what is on air, differs from the truth."""

    name: str = "correct table"
    kind: str = "none"  # none, move, jitter, missing, missing-control, rogue
    param: float | str = 0.0


@dataclass(frozen=True)
class Job:
    world: World
    case: Case
    estimator: str
    seed: int
    keep_series: bool = False


@dataclass
class Row:
    job: Job
    error: str = ""
    whole: metrics.RunMetrics | None = None
    outage: metrics.RunMetrics | None = None
    horizons: dict[float, float] = field(default_factory=dict)
    median_hpl_m: float = float("nan")
    available: float = float("nan")  # fraction of outage epochs with HPL within the alert limit
    counts: dict[str, int] = field(default_factory=dict)
    heard: dict[str, int] = field(default_factory=dict)  # status -> distinct cells heard
    alarms: dict[str, int] = field(default_factory=dict)  # MHSS hypothesis -> flagged epochs
    excluded: dict[str, int] = field(default_factory=dict)
    first_flag_s: float = float("nan")  # after GPS loss; nan if never flagged
    # After GPS returns and metrics.RECOVERY_SETTLE_S: p95 error, and the fraction of epochs
    # flagged gnss_excluded (the filter refusing GNSS that is back and correct)
    recovered_p95_m: float = float("nan")
    gnss_refused: float = float("nan")
    outage_err: np.ndarray | None = None  # horizontal error per outage epoch, for pooling
    series: tuple | None = None  # (t since GPS loss, error, HPL), for the plot
    runtime_s: float = 0.0


@dataclass(frozen=True)
class Sector:
    enb: int
    pci: int
    enu: tuple[float, float, float]


@lru_cache(maxsize=1)
def _rows() -> tuple[dict, ...]:
    with open(cells.CELL_TABLE, newline="") as f:
        return tuple(csv.DictReader(f))


def _origin(w: World) -> list[float]:
    return [float(x) for x in scenario.load(w.scenario)["origin_llh"]]


def spec_for(w: World) -> dict:
    """UC-01 with the sim's own LTE dropped and an outage long enough for T1."""
    spec = deepcopy(scenario.load(w.scenario))
    spec["sources"].pop("lte", None)
    spec["duration_s"] = w.gps_off_s + w.outage_s + w.tail_s
    spec["faults"] = [
        {
            "type": "outage",
            "source": "gnss",
            "start_s": w.gps_off_s,
            "end_s": w.gps_off_s + w.outage_s,
        }
    ]
    return spec


def sectors_on_air(w: World) -> list[Sector]:
    """Every registered sector on the carrier, at its real position. Same flat-ground height as
    the lookup uses (`cells.attach`), so the height assumption is not under test here."""
    origin = _origin(w)
    out = []
    for r in _rows():
        if int(r["earfcn"]) != w.earfcn:
            continue
        llh = [float(r["lat"]), float(r["lon"]), origin[2] + float(r["ant_height_agl_m"])]
        out.append(
            Sector(
                int(r["enb_id"]), int(r["pci"]), tuple(float(x) for x in llh_to_enu(llh, origin))
            )
        )
    return out


def _track(w: World, spec: dict, ts: np.ndarray) -> np.ndarray:
    return trajectory.make({**spec["trajectory"], "_origin_llh": spec["origin_llh"]}, ts)[0]


def _times(w: World, spec: dict) -> np.ndarray:
    return np.arange(0.0, float(spec["duration_s"]), 1.0 / w.rate_hz)


@lru_cache(maxsize=16)
def victim(w: World) -> tuple[int, tuple[int, ...]]:
    """The eNB a wrong-table case hits: the one nearest the circuit that is heard all run, and
    all of whose sectors are matched by the lookup. (eNB id, its PCIs on the carrier.)"""
    spec = spec_for(w)
    track = _track(w, spec, _times(w, spec))
    secs = sectors_on_air(w)
    enbs_of_pci: dict[int, set[int]] = {}
    for s in secs:
        enbs_of_pci.setdefault(s.pci, set()).add(s.enb)
    centre = track[:, :2].mean(axis=0)
    best = None
    for enb in sorted({s.enb for s in secs}):
        mine = [s for s in secs if s.enb == enb]
        p = np.array(mine[0].enu[:2])
        heard_all_run = np.linalg.norm(track[:, :2] - p, axis=1).max() <= w.hearing_km * 1e3
        if heard_all_run and all(len(enbs_of_pci[s.pci]) == 1 for s in mine):
            d = float(np.linalg.norm(centre - p))
            if best is None or d < best[0]:
                best = (d, enb, tuple(s.pci for s in mine))
    if best is None:
        raise ValueError(f"no eNB is matched and heard all run within {w.hearing_km} km")
    return best[1], best[2]


def _pr(t_ns: int, w: World, pci: int, value: float, dongle: str) -> Measurement:
    meta = {
        "dongle": dongle,
        "rx_clock": dongle,
        "earfcn": w.earfcn,
        "pci": pci,
        "arc": 0,
        "ambiguity_m": FRAME_M,
        "flags": [],
    }
    return Measurement(
        t_ns=t_ns,
        source="lte",
        kind="pseudorange",
        emitter=f"lte:{w.earfcn}:{pci}",
        value=(float(value) % FRAME_M,),
        sigma=(w.sigma_m,),
        meta=meta,
    )


def lte_records(w: World, spec: dict, seed: int, case: Case) -> list[Measurement]:
    """One dongle's records of every sector whose eNB is within hearing range, epoch by epoch.

    All sectors of the table's carrier are drawn whether heard or not, so a different hearing
    range or case leaves the draws of everything else alone."""
    ts = _times(w, spec)
    t_ns = T0 + np.round(ts * 1e9).astype(np.int64)
    track = _track(w, spec, ts)
    secs = sectors_on_air(w)
    z = np.random.default_rng([seed, _NOISE]).normal(0.0, 1.0, (len(secs), len(ts)))
    rng_clk = np.random.default_rng([seed, _SITE_CLOCK])
    builder = models.oscillator(rng_clk, ts, **BUILDER_CLOCK)
    site_clock = {
        enb: builder + models.oscillator(rng_clk, ts, **SITE_CLOCK)
        for enb in sorted({s.enb for s in secs})
    }
    rng_rx = np.random.default_rng([seed, _RX_CLOCK])
    rx = (
        rng_rx.uniform(0.0, FRAME_M)
        + w.rx_drift_ppm * 1e-6 * C * ts
        + models.oscillator(rng_rx, ts, offset_rw_m=w.rx_offset_rw_m, drift_rw_mps=w.rx_wander_mps)
    )
    mute: set[int] = set()
    rogue = None
    if case.kind == "rogue":
        enb, pcis = victim(w)
        mute = set(pcis if case.param == "all" else pcis[:1])
        rng_rogue = np.random.default_rng([seed, _ROGUE])
        bearing = rng_rogue.uniform(0.0, 2.0 * np.pi)
        anchor = next(s for s in secs if s.enb == enb).enu
        offset = w.rogue_km * 1e3 * np.array([np.cos(bearing), np.sin(bearing), 0.0])
        rogue = (
            np.array(anchor) + offset,
            sorted(mute),
            builder + models.oscillator(rng_rogue, ts, **SITE_CLOCK),
            rng_rogue.normal(0.0, 1.0, (len(mute), len(ts))),
        )
    limit = w.hearing_km * 1e3
    out: list[Measurement] = []
    for i, s in enumerate(secs):
        if s.pci in mute:
            continue
        e = np.array(s.enu)
        heard = np.linalg.norm(track[:, :2] - e[:2], axis=1) <= limit
        rho = np.linalg.norm(track - e, axis=1) + rx + site_clock[s.enb] + w.sigma_m * z[i]
        out += [_pr(int(t_ns[k]), w, s.pci, rho[k], "rtl0") for k in np.flatnonzero(heard)]
    if rogue is not None:
        e, pcis, clock, noise = rogue
        heard = np.linalg.norm(track[:, :2] - e[:2], axis=1) <= limit
        for j, pci in enumerate(pcis):
            rho = np.linalg.norm(track - e, axis=1) + rx + clock + w.sigma_m * noise[j]
            out += [_pr(int(t_ns[k]), w, pci, rho[k], "rtl0") for k in np.flatnonzero(heard)]
    return out


def edited_table(w: World, case: Case, seed: int, directory: str) -> CellTable | None:
    """A modified copy of the committed CSV, or None if this case's table is correct."""
    if case.kind not in ("move", "jitter", "missing"):
        return None
    rows = [dict(r) for r in _rows()]
    origin = _origin(w)
    rng = np.random.default_rng([seed, _TABLE])

    def shift(enb_ids: set[str], dE: float, dN: float) -> None:
        for r in rows:
            if r["enb_id"] in enb_ids:
                e = llh_to_enu([float(r["lat"]), float(r["lon"]), origin[2]], origin)
                llh = enu_to_llh([e[0] + dE, e[1] + dN, e[2]], origin)
                r["lat"], r["lon"] = f"{llh[0]:.7f}", f"{llh[1]:.7f}"

    if case.kind == "move":
        enb, _ = victim(w)
        bearing = rng.uniform(0.0, 2.0 * np.pi)
        shift({str(enb)}, float(case.param) * np.cos(bearing), float(case.param) * np.sin(bearing))
    elif case.kind == "jitter":
        for enb in sorted({r["enb_id"] for r in rows}):
            shift({enb}, *rng.normal(0.0, float(case.param), 2))
    else:  # missing
        gone = _missing_cells(w, case)
        rows = [r for r in rows if (int(r["earfcn"]), int(r["pci"])) not in gone]
    path = Path(directory) / f"table-{seed}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return CellTable.load(path)


def _missing_cells(w: World, case: Case) -> set[tuple[int, int]]:
    enb, pcis = victim(w)
    return {(w.earfcn, p) for p in (pcis if case.param == "enb" else pcis[:1])}


def _stream(w: World, spec: dict, sim, seed: int, case: Case) -> list[Measurement]:
    lte = lte_records(w, spec, seed, case)
    if case.kind == "missing-control":
        gone = {f"lte:{e}:{p}" for e, p in _missing_cells(w, case)}
        lte = [m for m in lte if m.emitter not in gone]
    return sorted(
        [*sim.measurements, *lte], key=lambda m: (m.t_ns, m.source, m.kind, m.emitter, m.receiver)
    )


def _window(estimates, start_ns: int, end_ns: int) -> list:
    return [e for e in estimates if start_ns <= e.t_ns < end_ns]


def _flags(estimates, prefix: str) -> Counter:
    return Counter(f[len(prefix) :] for e in estimates for f in e.flags if f.startswith(prefix))


def _heard_cells(w: World, records: list[Measurement], table: CellTable) -> dict:
    """Distinct cells heard, by the status the lookup gave them."""
    out: Counter = Counter()
    origin = _origin(w)
    for emitter in {m.emitter for m in records if m.source == "lte"}:
        _, earfcn, pci = emitter.split(":")
        out[table.associate(int(earfcn), int(pci), origin)[0]] += 1
    return dict(out)


def run_job(job: Job) -> Row:
    start = time.perf_counter()
    row = Row(job)
    try:
        w = job.world
        spec = spec_for(w)
        sim = scenario.generate(spec, job.seed)
        stream = _stream(w, spec, sim, job.seed, job.case)
        counts: Counter = Counter()
        with tempfile.TemporaryDirectory() as d:
            table = edited_table(w, job.case, job.seed, d)
            used = table if table is not None else CellTable.load()
            attached = list(cells.attach(stream, spec["origin_llh"], table=used, counts=counts))
        estimates = list(nav.estimate(job.estimator, attached, origin_llh=spec["origin_llh"]))
        loss, back = T0 + int(w.gps_off_s * 1e9), T0 + int((w.gps_off_s + w.outage_s) * 1e9)
        outage = _window(estimates, loss, back)
        row.whole = metrics.score(estimates, sim.truth, spec, T0)
        row.outage = metrics.score(outage, sim.truth, spec, T0)
        settled = [e for e in estimates if e.t_ns >= back + int(metrics.RECOVERY_SETTLE_S * 1e9)]
        if settled:
            row.recovered_p95_m = metrics.score(settled, sim.truth, spec, T0).h_p95_m
            row.gnss_refused = float(np.mean(["gnss_excluded" in e.flags for e in settled]))
        for h in HORIZONS_S:
            if h <= w.outage_s:
                part = _window(outage, loss, loss + int(h * 1e9))
                row.horizons[h] = metrics.score(part, sim.truth, spec, T0).h_p95_m
        truth = {t.t_ns: t for t in sim.truth}
        err = np.array(
            [np.linalg.norm(np.subtract(e.pos_enu, truth[e.t_ns].pos_enu)[:2]) for e in outage]
        )
        hpl = np.array([e.hpl_m for e in outage])
        row.median_hpl_m = float(np.median(hpl))
        row.available = float(np.mean(hpl <= metrics.ALERT_LIMIT_M))
        row.counts = dict(counts)
        row.heard = _heard_cells(w, stream, used)
        row.alarms = dict(_flags(estimates, "mhss_alarm:"))
        row.excluded = dict(_flags(estimates, "mhss_excluded:"))
        flagged = [
            (e.t_ns - loss) / 1e9
            for e in estimates
            if any(f.startswith(("mhss_alarm:", "mhss_excluded:")) for f in e.flags)
        ]
        row.first_flag_s = flagged[0] if flagged else float("nan")
        row.outage_err = err
        if job.keep_series:
            row.series = (
                np.array([(e.t_ns - loss) / 1e9 for e in estimates[::10]]),
                np.array(
                    [
                        np.linalg.norm(np.subtract(e.pos_enu, truth[e.t_ns].pos_enu)[:2])
                        for e in estimates[::10]
                    ]
                ),
                np.array([e.hpl_m for e in estimates[::10]]),
            )
    except Exception:
        row.error = traceback.format_exc(limit=3)
    row.runtime_s = time.perf_counter() - start
    return row


def run_all(jobs: list[Job], n_jobs: int) -> list[Row]:
    if n_jobs <= 1:
        return [run_job(j) for j in jobs]
    with ProcessPoolExecutor(n_jobs) as pool:
        return list(pool.map(run_job, jobs, chunksize=1))


def commit() -> str:
    return subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=7"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    ).stdout.strip()


def _ok(rows: list[Row]) -> list[Row]:
    return [r for r in rows if r.whole is not None]


def _nanmean(v: list[float]) -> float:
    a = np.array(v, float)
    return float(np.nanmean(a)) if a.size and not np.all(np.isnan(a)) else float("nan")


def seed_results(rows: list[Row]) -> tuple[list[float], list[float]]:
    """Per-seed outage p95s and T1 ok flags (a run meets T1 if its outage p95 is within it)."""
    p95s = [r.outage.h_p95_m for r in rows]
    return p95s, [float(p <= T1_LIMIT_M) for p in p95s]


def result_row(estimator: str, rows: list[Row]) -> str:
    good = _ok(rows)
    fails = len(rows) - len(good)
    if not good:
        return f"| {estimator} | **failed in all {fails} runs** | | | | | | | | |"
    p95s, met = seed_results(good)
    pooled = float(np.percentile(np.concatenate([r.outage_err for r in good]), 95))
    horizons = " / ".join(
        f"{_nanmean([r.horizons.get(h, float('nan')) for r in good]):.1f}" for h in HORIZONS_S
    )
    cover = [r.outage.hpl_bound_frac for r in good]
    whole = [r.whole.hpl_bound_frac for r in good]
    return (
        f"| {estimator} | {_nanmean(p95s):.1f} / {max(p95s):.1f} / {pooled:.1f} | {horizons} | "
        f"{int(sum(met))}/{len(met)} | {_nanmean(cover) * 100:.2f} / {min(cover) * 100:.2f} | "
        f"{min(whole) * 100:.2f} | "
        f"{sum(r.whole.hazardous_epochs for r in good)} ({sum(r.outage.hazardous_epochs for r in good)}) | "  # noqa: E501
        f"{sum(r.whole.misleading_epochs for r in good)} | "
        f"{_nanmean([r.median_hpl_m for r in good]):.0f} m, "
        f"{_nanmean([r.available for r in good]) * 100:.0f}% | {_recovery(good)} |"
        + (f" {fails} failed" if fails else "")
    )


RECOVERY_HEAD = (
    f"after GPS returns (+{metrics.RECOVERY_SETTLE_S:.0f} s): p95 m (mean / worst run), "
    "runs refusing GNSS in > half the epochs"
)


def _recovery(good: list[Row]) -> str:
    p95 = [r.recovered_p95_m for r in good]
    refused = sum(r.gnss_refused > 0.5 for r in good)
    return f"{_nanmean(p95):.1f} / {np.nanmax(p95):.1f}, {refused}/{len(good)}"


HEADER = (
    "| estimator | outage p95 m (mean per run / worst run / pooled) | p95 m in first 60 / 120 / "
    "300 s | seeds with outage p95 ≤ 25 m | HPL ≥ error in outage, % (mean / worst run) | "
    "whole-run HPL ≥ error, worst run % | hazardous epochs, all runs (of which in outage) | "
    "misleading epochs, all runs | median HPL, epochs with HPL ≤ 50 m | " + RECOVERY_HEAD + " |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
)


def group(rows: list[Row], *keys) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(tuple(k(r) for k in keys), []).append(r)
    return out


def report_header(args, w: World) -> None:
    print(f"commit {commit()}; argv: {' '.join(sys.argv[1:])}")
    print(
        f"seeds 0..{args.seeds - 1}; UC-01 circuit, GPS off at {w.gps_off_s:.0f} s for "
        f"{w.outage_s:.0f} s; EARFCN {w.earfcn}; records {w.rate_hz:g} Hz (TBC); dongle "
        f"{w.rx_drift_ppm} ppm (TBC), wander {w.rx_wander_mps} m/s/sqrt(s) (TBC); site clocks "
        f"ADR-0022 form, realistic-set sizes (TBC). Evidence: sim over real tower positions."
    )


def counts_line(rows: list[Row]) -> str:
    good = _ok(rows)
    if not good:
        return "no successful run"
    c = good[0].counts
    h = good[0].heard
    stat = (MATCHED, COLLISION, UNKNOWN, OUT_OF_RANGE)
    return (
        "lookup (first run; records): "
        + ", ".join(f"{s} {c.get(s, 0)}" for s in stat)
        + "; distinct cells: "
        + ", ".join(f"{s} {h.get(s, 0)}" for s in stat)
    )


def t1_verdict(by_estimator: dict) -> None:
    for name, rows in by_estimator.items():
        good = _ok(rows)
        if not good:
            print(f"- {name}: failed, T1 not assessed")
            continue
        p95s, met = seed_results(good)
        verdict = "MET" if all(met) and len(good) == len(rows) else "NOT MET"
        pooled = float(np.percentile(np.concatenate([r.outage_err for r in good]), 95))
        avail = _nanmean([r.available for r in good]) * 100
        print(
            f"- {name}: T1 error target {verdict} on this run (TBC target, sim): "
            f"{int(sum(met))}/{len(met)} seeds have outage p95 ≤ {T1_LIMIT_M:.0f} m; mean "
            f"per-run p95 {_nanmean(p95s):.1f} m, pooled over runs {pooled:.1f} m. "
            f"HPL within the 50 m alert limit in "
            f"{avail:.0f}% of outage epochs"
        )


def run_geometry(args) -> None:
    base = World(hearing_km=args.hearing_km, sigma_m=args.sigma, outage_s=args.outage,
                 rx_wander_mps=args.rx_wander)  # fmt: skip
    jobs = [
        Job(base, Case(), est, s, keep_series=s == 0)
        for est in args.estimators
        for s in range(args.seeds)
    ]
    sweeps: list[World] = []
    if args.sweep:
        sweeps += [replace(base, hearing_km=h) for h in args.sweep_hearing if h != base.hearing_km]
        sweeps += [replace(base, sigma_m=s) for s in args.sweep_sigma if s != base.sigma_m]
        jobs += [Job(w, Case(), est, s) for w in sweeps for est in args.sweep_estimators
                 for s in range(args.seeds)]  # fmt: skip
    t0 = time.perf_counter()
    rows = run_all(jobs, args.jobs)
    wall = time.perf_counter() - t0
    report_header(args, base)
    print(f"\nhearing range {base.hearing_km:g} km (TBC); range noise {base.sigma_m:g} m (TBC)\n")
    main_rows = [r for r in rows if r.job.world == base]
    by_est = {k[0]: v for k, v in group(main_rows, lambda r: r.job.estimator).items()}
    print(HEADER)
    for est in args.estimators:
        print(result_row(est, by_est.get(est, [])))
    print()
    print(counts_line(main_rows))
    print("\nT1 verdict (95% horizontal error ≤ 25 m for ≥ 300 s, TBC):")
    t1_verdict(by_est)
    _mhss_lines(main_rows)
    _errors(rows)
    if sweeps:
        print("\nsweep (paired draws; hearing range, then noise):\n")
        for w in sweeps:
            print(f"\nhearing {w.hearing_km:g} km, noise {w.sigma_m:g} m (TBC)\n")
            sub = [r for r in rows if r.job.world == w]
            print(HEADER)
            for k, v in group(sub, lambda r: r.job.estimator).items():
                print(result_row(k[0], v))
            print()
            print(counts_line(sub))
    print(f"\nruntime {wall:.0f} s wall, {len(jobs)} runs, {args.jobs} jobs")
    if args.out:
        _plot_geometry(main_rows, base, args.out)


def _mhss_lines(rows: list[Row]) -> None:
    for (est,), v in group(rows, lambda r: r.job.estimator).items():
        good = _ok(v)
        if est == "ekf-mhss" and good:
            n = sum(bool(r.alarms or r.excluded) for r in good)
            print(f"- ekf-mhss flagged a hypothesis in {n}/{len(good)} runs with a correct table")


def _errors(rows: list[Row]) -> None:
    bad = [r for r in rows if r.error]
    if bad:
        print(f"\n{len(bad)} runs failed; first failure ({bad[0].job.estimator}):")
        print(f"```\n{bad[0].error}```")


def _plot_geometry(rows: list[Row], w: World, path: str) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = {"ekf": "#20639b", "ekf-calibrated": "#3caea3", "ekf-imu": "#a05195",
              "ekf-mhss": "#b5442e"}  # fmt: skip
    for r in _ok(rows):
        if r.series is None:
            continue
        t, e, h = r.series
        c = colors.get(r.job.estimator, "0.3")
        ax.plot(t, e, color=c, lw=1.3, label=f"{r.job.estimator} error (seed 0)")
        ax.plot(t, h, color=c, lw=0.8, ls=":", label=f"{r.job.estimator} HPL")
    ax.axvline(0.0, color="0.4", ls="--", lw=1)
    ax.axhline(T1_LIMIT_M, color="0.6", lw=0.8)
    ax.axhline(metrics.ALERT_LIMIT_M, color="0.6", lw=0.8, ls="-.")
    ax.set(xlabel="time since GPS loss (s)", ylabel="horizontal error, HPL (m)", yscale="log",
           title=f"UC-01 on real Rogers eNBs, {w.hearing_km:g} km, {w.sigma_m:g} m noise (TBC), "
                 f"sim, commit {commit()}")  # fmt: skip
    ax.grid(True, which="major", alpha=0.3)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print("wrote", path)


def wrong_table_cases(args) -> list[Case]:
    cases = [Case()]
    cases += [Case(f"one eNB filed {m:g} m off", "move", m) for m in args.offsets]
    cases += [Case(f"all eNBs {args.position_sigma:g} m 1σ off", "jitter", args.position_sigma)]
    cases += [
        Case("one sector missing", "missing", "sector"),
        Case("control: that sector not heard", "missing-control", "sector"),
        Case("whole eNB missing", "missing", "enb"),
        Case("control: that eNB not heard", "missing-control", "enb"),
        Case("rogue on one PCI", "rogue", "one"),
        Case("rogue on all the eNB's PCIs", "rogue", "all"),
    ]
    return cases


def wrong_table_row(est: str, case: Case, rows: list[Row], victim_site: str) -> str:
    good = _ok(rows)
    if not good:
        return f"| {case.name} | {est} | **failed** | | | | | | | |"
    p95s = [r.outage.h_p95_m for r in good]
    pooled = float(np.percentile(np.concatenate([r.outage_err for r in good]), 95))
    cover = [r.outage.hpl_bound_frac for r in good]
    worst = max(r.outage.fault_h_max_m for r in good)
    text = (
        f"| {case.name} | {est} | {_nanmean(p95s):.1f} / {max(p95s):.1f} / {pooled:.1f} | "
        f"{worst:.0f} | {_nanmean(cover) * 100:.1f} / {min(cover) * 100:.1f} | "
        f"{sum(r.outage.hazardous_epochs for r in good)} / "
        f"{sum(r.whole.hazardous_epochs for r in good)} | "
        f"{sum(r.outage.misleading_epochs for r in good)} | "
        f"{_nanmean([r.median_hpl_m for r in good]):.0f} m, "
        f"{_nanmean([r.available for r in good]) * 100:.0f}% | {_recovery(good)} |"
    )
    if est == "ekf-mhss":
        bad_flag = sum(
            bool(r.alarms.get(victim_site) or r.excluded.get(victim_site)) for r in good
        )
        other = sum(any(k != victim_site for k in {**r.alarms, **r.excluded}) for r in good)
        ff = [r.first_flag_s for r in good if r.alarms or r.excluded]
        first = f", first flag {min(ff):+.0f} s" if ff else ""
        text += f" flagged bad site in {bad_flag}/{len(good)}; other hypothesis {other}/{len(good)}{first} |"  # noqa: E501
    else:
        text += " |"
    return text


def run_wrong_table(args) -> None:
    w = World(hearing_km=args.hearing_km, sigma_m=args.sigma, rx_wander_mps=args.rx_wander,
              rogue_km=args.rogue_km, outage_s=args.outage)  # fmt: skip
    enb, pcis = victim(w)
    site = f"site:enb:{enb}"
    cases = wrong_table_cases(args)
    jobs = [Job(w, c, est, s) for c in cases for est in args.estimators for s in range(args.seeds)]
    t0 = time.perf_counter()
    rows = run_all(jobs, args.jobs)
    wall = time.perf_counter() - t0
    report_header(args, w)
    print(
        f"\nhearing {w.hearing_km:g} km (TBC); noise {w.sigma_m:g} m (TBC); wrong-table target: "
        f"eNB {enb} (PCIs {pcis}; nearest the circuit, heard all run); rogue "
        f"{w.rogue_km:g} km from it (TBC)\n"
    )
    print(
        "| case | estimator | outage p95 m (mean / worst / pooled) | worst error m | "
        "HPL ≥ error %, outage (mean / worst run) | hazardous epochs, all runs (outage / "
        "whole run) | misleading epochs in outage, all runs | median HPL, HPL ≤ 50 m | "
        + RECOVERY_HEAD
        + " | MHSS |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    by = group(rows, lambda r: r.job.case.name, lambda r: r.job.estimator)
    for c in cases:
        for est in args.estimators:
            print(wrong_table_row(est, c, by.get((c.name, est), []), site))
    print()
    for c in cases:
        sub = [r for r in rows if r.job.case.name == c.name]
        print(f"- {c.name}: {counts_line(sub)}")
    print()
    if "ekf-mhss" in args.estimators:
        print("MHSS hypotheses flagged (alarm or exclusion), epochs summed over runs, top 3:")
        for c in cases:
            flagged: Counter = Counter()
            for r in _ok(by.get((c.name, "ekf-mhss"), [])):
                flagged.update(r.alarms)
                flagged.update(r.excluded)
            top = ", ".join(f"{k} {n}" for k, n in flagged.most_common(3)) or "none"
            print(f"- {c.name}: {top}")
        print()
    missing_matches(by, cases, args.estimators)
    _errors(rows)
    print(f"\nruntime {wall:.0f} s wall, {len(jobs)} runs, {args.jobs} jobs")
    if args.out:
        _plot_wrong_table(by, cases, args.estimators, args.out, w)


def missing_matches(by: dict, cases: list[Case], estimators) -> None:
    """A missing cell must behave exactly as a cell that was never heard."""
    for pair in (("one sector missing", "control: that sector not heard"),
                 ("whole eNB missing", "control: that eNB not heard")):  # fmt: skip
        for est in estimators:
            a, b = (sorted(by.get((n, est), []), key=lambda r: r.job.seed) for n in pair)
            if not _ok(a) or not _ok(b):
                continue
            d = max(abs(x.outage.h_p95_m - y.outage.h_p95_m) for x, y in zip(a, b, strict=True))
            print(f"- {pair[0]} vs its control, {est}: largest p95 difference {d:.6f} m")


def _plot_wrong_table(by: dict, cases: list[Case], estimators, path: str, w: World) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4.8))
    width = 0.8 / len(estimators)
    x = np.arange(len(cases))
    for j, est in enumerate(estimators):
        vals = []
        for c in cases:
            good = _ok(by.get((c.name, est), []))
            vals.append(_nanmean([r.outage.h_p95_m for r in good]) if good else float("nan"))
        ax.bar(x + j * width, vals, width, label=est)
    ax.axhline(T1_LIMIT_M, color="0.5", lw=0.8)
    ax.axhline(metrics.ALERT_LIMIT_M, color="0.5", lw=0.8, ls="-.")
    ax.set_xticks(
        x + 0.4 - width / 2, [c.name for c in cases], rotation=25, ha="right", fontsize=8
    )
    title = f"Wrong cell table on UC-01, real Rogers eNBs, sim, commit {commit()}"
    ax.set(ylabel="outage p95 horizontal error (m)", yscale="log", title=title)
    ax.grid(True, axis="y", which="major", alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print("wrote", path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    for name in ("geometry", "wrong-table"):
        s = sub.add_parser(name)
        s.add_argument("--seeds", type=int, default=10)
        s.add_argument("--jobs", type=int, default=3, help="worker processes; keep this small")
        s.add_argument("--hearing-km", type=float, default=3.0, help="TBC")
        s.add_argument("--sigma", type=float, default=20.0, help="range noise, m (TBC)")
        s.add_argument("--outage", type=float, default=300.0, help="GPS outage, s (T1: 300)")
        s.add_argument("--rx-wander", type=float, default=0.05, help="m/s/sqrt(s) (TBC)")
        s.add_argument("--out")
    g = sub.choices["geometry"]
    g.add_argument("--estimators", nargs="+", default=list(ESTIMATORS))
    g.add_argument("--sweep", action="store_true", help="also sweep hearing range and noise")
    g.add_argument("--sweep-hearing", type=float, nargs="+", default=[2.0, 3.0, 5.0], help="TBC")
    g.add_argument("--sweep-sigma", type=float, nargs="+", default=[5.0, 20.0, 50.0], help="TBC")
    g.add_argument("--sweep-estimators", nargs="+", default=["ekf", "ekf-calibrated"])
    d = sub.choices["wrong-table"]
    d.add_argument("--estimators", nargs="+", default=list(WRONG_TABLE_ESTIMATORS))
    d.add_argument("--offsets", type=float, nargs="+", default=[50.0, 100.0, 200.0, 500.0, 2000.0],
                   help="m")  # fmt: skip
    d.add_argument("--position-sigma", type=float, default=30.0, help="m, 1σ per axis (TBC)")
    d.add_argument("--rogue-km", type=float, default=1.0, help="TBC")
    args = p.parse_args()
    {"geometry": run_geometry, "wrong-table": run_wrong_table}[args.mode](args)


if __name__ == "__main__":
    main()
