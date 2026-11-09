"""Dense baseband check of the LTE chain (#124): every registered cell at realistic powers.

`lte_link_synthetic.py` (#121) hears 5 hand-picked eNBs at equal power. Here a static receiver
hears every sector on one carrier within a radius, each with its own PCI, true delay and a received
power from a link budget, through 8-bit quantisation scaled to the whole capture (so the strongest
cell sets the gain). The capture goes through the real front end, `pnt.nav.cells` and
`pnt.nav.estimate`. The 5-cell equal-power case runs in the same script on the same seeds.

    python analysis/lte_link_dense.py --seeds 5 --out /tmp/lte-dense.png

Link budget, all placeholders (`Budget`): filed power, read as EIRP at boresight in dBW; free space
to `d0`, then a log-distance exponent; a parabolic sector pattern with a front-to-back floor (empty
beamwidth = omni); an RTL-SDR noise figure over the 72-subcarrier band.

What it leaves out: multipath, shadowing, buildings, terrain, the antennas' vertical pattern,
tower clock drift and tower carrier error, unloaded cells (every data resource element is filled,
the worst case for interference), and other carriers that would use up the ADC's headroom. The
quantiser is the dongle's 8-bit output after decimation, not its ADC. The generator and the
receiver share one reading of TS 36.211. Synthetic evidence only; it shows how this front end
handles near-far, not how real towers will behave (#21).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import pathlib
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from pnt import nav
from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.frontends.lte import capture, process_file, synth
from pnt.frontends.lte import signals as sig
from pnt.nav.cells import CELL_TABLE, COLLISION, MATCHED, UNKNOWN, CellTable, attach

ORIGIN = (45.3876, -75.6960, 80.0)  # Carleton, the scenarios' session origin
TRUE_ENU = np.array([100.0, 50.0, 30.0])  # as in lte_link_synthetic.py
EARFCN, FC, FS = 2460, 875e6, 1.92e6
T0 = 1_446_000_000_000_000_000
C = 299792458.0
PPM = 0.4  # the dongle clock of lte_link_synthetic.py
BAND_HZ = 72 * sig.SUBCARRIER_HZ  # what `synth` calls in-band
WRONG_TIMING_M = C / FS  # one sample: a track further off than this is on the wrong timing
REL_BINS = (0, -3, -6, -10, -15, -20, -30, -40, -200)  # dB relative to the strongest cell
DIST_BINS = (0, 500, 1000, 2000, 3000, 5000, 10000)  # m


@dataclass(frozen=True)
class Budget:
    """Link budget. Everything except the physics is a placeholder."""

    path_loss_exponent: float = 3.5  # TBC: urban log-distance, from no measurement here
    d0_m: float = 100.0  # TBC: free space to here
    front_to_back_db: float = 25.0  # TBC: floor of the parabolic sector pattern
    noise_figure_db: float = 6.0  # TBC: RTL-SDR (R820T) at 875 MHz
    rx_gain_dbi: float = 0.0  # TBC: receive antenna, cable loss included
    # TBC: the column says dBW, but 46 is the usual macro conducted power in dBm. 0 reads it as
    # filed (EIRP in dBW); -15 reads it as dBm plus a 15 dBi antenna (TBC). Moves every cell alike.
    tx_offset_db: float = 0.0
    carrier_subcarriers: int = 600  # 10 MHz = 50 resource blocks (TS 36.101), filled evenly


@dataclass(frozen=True)
class Sector:
    pci: int
    enb_id: str
    enu: tuple[float, float, float]
    azimuth_deg: float
    beamwidth_deg: float | None  # None: empty in the table, treated as omni
    tx_power_dbw: float


def load_sectors() -> list[Sector]:
    """Every registered sector on the carrier, with the same flat-ground height as the lookup."""
    with open(CELL_TABLE, newline="") as f:
        rows = [r for r in csv.DictReader(f) if int(r["earfcn"]) == EARFCN]
    return [
        Sector(
            pci=int(r["pci"]),
            enb_id=r["enb_id"],
            enu=tuple(
                float(v)
                for v in llh_to_enu(
                    [float(r["lat"]), float(r["lon"]), ORIGIN[2] + float(r["ant_height_agl_m"])],
                    ORIGIN,
                )
            ),
            azimuth_deg=float(r["azimuth_deg"]),
            beamwidth_deg=float(r["h_beamwidth_deg"]) if r["h_beamwidth_deg"] else None,
            tx_power_dbw=float(r["tx_power_dbw"]),
        )
        for r in rows
    ]


def within(sectors: list[Sector], rx: np.ndarray, radius_m: float) -> list[Sector]:
    return [s for s in sectors if np.linalg.norm(np.array(s.enu[:2]) - rx[:2]) <= radius_m]


def path_loss_db(d_m: float, b: Budget) -> float:
    """Free space to `d0`, then log-distance. Leaves out everything in the module docstring."""
    d = max(d_m, 1.0)
    fspl = lambda x: 20 * math.log10(x) + 20 * math.log10(FC) - 147.55  # noqa: E731
    if d <= b.d0_m:
        return fspl(d)
    return fspl(b.d0_m) + 10 * b.path_loss_exponent * math.log10(d / b.d0_m)


def sector_gain_db(s: Sector, rx: np.ndarray, b: Budget) -> float:
    """Horizontal pattern relative to boresight: -min(12 (Δ/bw)², front-to-back)."""
    if s.beamwidth_deg is None:
        return 0.0
    de, dn = rx[0] - s.enu[0], rx[1] - s.enu[1]
    delta = (math.degrees(math.atan2(de, dn)) - s.azimuth_deg + 180.0) % 360.0 - 180.0
    return -min(12.0 * (delta / s.beamwidth_deg) ** 2, b.front_to_back_db)


def rx_band_power_dbm(s: Sector, rx: np.ndarray, b: Budget) -> float:
    """Power of this sector in the 72 subcarriers the front end uses (1.08 MHz)."""
    d = float(np.linalg.norm(rx - np.array(s.enu)))
    in_band = 10 * math.log10(72 / b.carrier_subcarriers)
    return (s.tx_power_dbw + 30.0 + b.tx_offset_db + in_band + sector_gain_db(s, rx, b)
            - path_loss_db(d, b) + b.rx_gain_dbi)  # fmt: skip


def noise_dbm(b: Budget) -> float:
    return -174.0 + 10 * math.log10(BAND_HZ) + b.noise_figure_db


def pick_equal_power(n: int, sectors: list[Sector]) -> list[Sector]:
    """The cells of `lte_link_synthetic.py::pick_cells`: nearest sector of each eNB within 5 km of
    the origin, unique PCI over the table, one per bearing sector."""
    enbs: dict[int, set[str]] = {}
    for s in sectors:
        enbs.setdefault(s.pci, set()).add(s.enb_id)
    best: dict[str, tuple[float, Sector]] = {}
    for s in sectors:
        if len(enbs[s.pci]) != 1:
            continue
        d = float(np.linalg.norm(s.enu[:2]))
        if d <= 5000.0 and (s.enb_id not in best or d < best[s.enb_id][0]):
            best[s.enb_id] = (d, s)
    bins: dict[int, Sector] = {}
    for _, s in sorted(best.values(), key=lambda v: v[0]):
        bins.setdefault(int((math.atan2(s.enu[1], s.enu[0]) + math.pi) // (2 * math.pi / n)), s)
    return list(bins.values())[:n]


@dataclass(frozen=True)
class Case:
    name: str
    rx: tuple[float, float, float]
    sectors: tuple[Sector, ...]
    equal_power_snr_db: float | None = None  # not None: the #122 case, all cells at this SNR
    frame_sync: bool = False  # True: every eNB on the same frame timing


@dataclass
class SectorResult:
    pci: int
    enb_id: str
    range_m: float
    rel_db: float  # relative to the strongest cell of the capture
    snr_db: float  # in-band, against thermal noise only
    searched: bool  # the search reported this PCI
    tracked: bool  # it produced pseudoranges
    n_records: int = 0
    bias_m: float = float("nan")
    rms_m: float = float("nan")
    wrong_timing: bool = False


@dataclass
class SeedResult:
    case: str
    seed: int
    sectors: list[SectorResult]
    ghosts: list[int]
    lookup_cells: Counter
    lookup_records: Counter
    matched_enbs: int
    t: np.ndarray
    err: np.ndarray
    err_no_lte: np.ndarray  # the same run without LTE records: what the filter holds alone
    elapsed_s: float
    capture_stats: dict = field(default_factory=dict)


def pseudorange_errors(records: list[Measurement], tower: synth.Tower) -> np.ndarray:
    """Record minus truth, m, wrapped to one frame (the definition in test_lte_frontend.py)."""
    L = sig.half_frame_length(FS)
    frame_m = C * sig.FRAME_S
    t = np.array([m.t_ns - T0 for m in records], float)
    v = np.array([m.value[0] for m in records])
    h = np.round((t * FS / 1e9 - tower.boundary_sample(0, FS, PPM)) / L)
    truth = C * (tower.boundary_sample(h / 2, FS, PPM) - h * L) / FS
    return (v - truth + frame_m / 2) % frame_m - frame_m / 2


def run_case(case: Case, seed: int, b: Budget, duration: float, gps_off: float) -> SeedResult:
    """One capture, as in `lte_link_synthetic.run`: same draw order for the 5-cell case."""
    t_start = time.perf_counter()
    rng = np.random.default_rng(seed)
    rx = np.array(case.rx)
    snr_db = [noise_free_snr(s, rx, b) for s in case.sectors]
    if case.equal_power_snr_db is not None:
        powers, ref_snr = [0.0] * len(case.sectors), case.equal_power_snr_db
    else:
        powers, ref_snr = snr_db, 0.0
    clocks: dict[str, float] = {}  # sectors of one eNB share their frame timing (ADR-0022)
    towers = []
    for s, p in zip(case.sectors, powers, strict=True):
        rho = float(np.linalg.norm(rx - np.array(s.enu)))
        if case.frame_sync:
            clock = 0.0
        else:
            clock = clocks.setdefault(s.enb_id, float(rng.uniform(0.0, 0.009)))
        towers.append(synth.Tower(pci=s.pci, delay_s=rho / C + clock, power_db=p))
    x = synth.synthesize(towers, duration, fs=FS, fc=FC, clock_ppm=PPM, snr_db=ref_snr, seed=seed)
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    with tempfile.TemporaryDirectory() as d:
        cap = capture.write_capture(pathlib.Path(d) / "c.cu8", capture.complex_to_cu8(x), meta)
        del x
        result = process_file(cap)

    records = list(result.measurements)
    pr: dict[int, list[Measurement]] = {}
    for m in records:
        if m.kind == "pseudorange":
            pr.setdefault(m.meta["pci"], []).append(m)
    searched = {f.pci for _, f in result.found}
    top = max(powers) if case.sectors else 0.0
    sector_results = []
    used: set[int] = set()  # the cell tracked under a PCI goes to one sector, its best-timed one
    by_pci: dict[int, list[int]] = {}
    for i, s in enumerate(case.sectors):
        by_pci.setdefault(s.pci, []).append(i)
    best_sector: dict[int, tuple[int, np.ndarray]] = {}
    for pci, recs in pr.items():
        options = [(i, pseudorange_errors(recs, towers[i])) for i in by_pci.get(pci, [])]
        if options:
            best_sector[pci] = min(options, key=lambda o: abs(float(np.median(o[1]))))
    for i, s in enumerate(case.sectors):
        res = SectorResult(
            pci=s.pci,
            enb_id=s.enb_id,
            range_m=float(np.linalg.norm(rx - np.array(s.enu))),
            rel_db=powers[i] - top,
            snr_db=snr_db[i],
            searched=s.pci in searched,
            tracked=False,
        )
        if s.pci in best_sector and best_sector[s.pci][0] == i and s.pci not in used:
            used.add(s.pci)
            err = best_sector[s.pci][1]
            bias = float(np.median(err))
            res.tracked = True
            res.n_records = err.size
            res.bias_m = bias
            res.rms_m = float(np.sqrt(np.mean((err - np.mean(err)) ** 2)))
            res.wrong_timing = abs(bias) > WRONG_TIMING_M
        sector_results.append(res)
    ghosts = sorted(set(pr) - {s.pci for s in case.sectors})

    table = CellTable.load()
    lookup_cells: Counter = Counter()
    matched_enbs: set[int] = set()
    for pci in pr:
        status, cell = table.associate(EARFCN, pci, ORIGIN)
        lookup_cells[status] += 1
        if status == MATCHED:
            matched_enbs.add(cell.enb_id)
    lookup_records: Counter = Counter()
    for _ in attach(iter(records), ORIGIN, table, lookup_records):
        pass

    for k in range(int(duration * 5)):
        t_ns = T0 + k * 200_000_000
        if k % 5 == 0 and k / 5 < gps_off:
            fix = tuple(float(v) for v in rx + rng.normal(0, 2.0, 3))
            records.append(
                Measurement(
                    t_ns=t_ns, source="gnss", kind="position_enu", value=fix, sigma=(2.0, 2.0, 2.0)
                )  # fmt: skip
            )
            records.append(
                Measurement(t_ns=t_ns, source="gnss", kind="time", value=(0.0,), sigma=(1e-7,))
            )
        alt = float(rx[2] + rng.normal(0, 1.0))
        records.append(
            Measurement(t_ns=t_ns, source="baro", kind="altitude", value=(alt,), sigma=(1.0,))
        )
    records.sort(key=lambda m: m.t_ns)
    est = list(nav.estimate("ekf", records, origin_llh=ORIGIN))
    t = np.array([(e.t_ns - T0) / 1e9 for e in est])
    err = np.array([np.linalg.norm(np.array(e.pos_enu)[:2] - rx[:2]) for e in est])
    est0 = list(nav.estimate("ekf", [m for m in records if m.source != "lte"], origin_llh=ORIGIN))
    err0 = np.array([np.linalg.norm(np.array(e.pos_enu)[:2] - rx[:2]) for e in est0])
    if len(est0) != len(est):  # the control must sit on the same epochs to be compared
        err0 = np.interp(t, [(e.t_ns - T0) / 1e9 for e in est0], err0)
    return SeedResult(
        case=case.name,
        seed=seed,
        sectors=sector_results,
        ghosts=ghosts,
        lookup_cells=lookup_cells,
        lookup_records=lookup_records,
        matched_enbs=len(matched_enbs),
        t=t,
        err=err,
        err_no_lte=err0,
        elapsed_s=time.perf_counter() - t_start,
    )


def noise_free_snr(s: Sector, rx: np.ndarray, b: Budget) -> float:
    return rx_band_power_dbm(s, rx, b) - noise_dbm(b)


# --- receiver spots -----------------------------------------------------------------------


def beside_a_tower(sectors: list[Sector]) -> np.ndarray:
    """150 m along the boresight of the sector nearest the origin (TBC: a spot, not a claim)."""
    s = min(sectors, key=lambda v: np.linalg.norm(v.enu[:2]))
    a = math.radians(s.azimuth_deg)
    return np.array([s.enu[0] + 150 * math.sin(a), s.enu[1] + 150 * math.cos(a), 30.0])


def far_from_all(sectors: list[Sector], half_box_m: float = 5000.0) -> np.ndarray:
    """The point of a 250 m grid around the origin furthest from every registered eNB."""
    xy = np.array([s.enu[:2] for s in sectors])
    g = np.arange(-half_box_m, half_box_m + 1, 250.0)
    best, far = None, -1.0
    for e in g:
        for n in g:
            d = float(np.min(np.linalg.norm(xy - [e, n], axis=1)))
            if d > far:
                best, far = (e, n), d
    return np.array([best[0], best[1], 30.0])


# --- report -------------------------------------------------------------------------------


def _p(v, q):
    return float(np.percentile(v, q)) if len(v) else float("nan")


def _post(r: SeedResult, gps_off: float, window: float | None = None, lte=True) -> np.ndarray:
    keep = r.t >= gps_off if window is None else (r.t >= gps_off) & (r.t < gps_off + window)
    return (r.err if lte else r.err_no_lte)[keep]


def case_row(name: str, rs: list[SeedResult], gps_off: float) -> str:
    def n_uniq(f):
        return np.mean([len({f(s) for s in r.sectors}) for r in rs])

    tx = n_uniq(lambda s: s.pci)
    enbs = n_uniq(lambda s: s.enb_id)
    tracked = np.mean([sum(s.tracked for s in r.sectors) for r in rs])
    tr_enb = np.mean([len({s.enb_id for s in r.sectors if s.tracked}) for r in rs])
    ghosts = sum(len(r.ghosts) for r in rs)
    wrong = sum(sum(s.wrong_timing for s in r.sectors) for r in rs)
    cells = Counter()
    for r in rs:
        cells.update(r.lookup_cells)
    n = len(rs)
    matched = cells[MATCHED] / n
    coll = cells[COLLISION] / n
    unk = cells[UNKNOWN] / n
    enb_used = np.mean([r.matched_enbs for r in rs])
    biases = np.array([abs(s.bias_m) for r in rs for s in r.sectors if s.tracked])
    rmss = np.array([s.rms_m for r in rs for s in r.sectors if s.tracked])
    p10 = _p(np.concatenate([_post(r, gps_off, 10.0) for r in rs]), 95)
    p_all = _p(np.concatenate([_post(r, gps_off) for r in rs]), 95)
    worst = max(_p(_post(r, gps_off, 10.0), 95) for r in rs)
    max_err = max(float(np.max(_post(r, gps_off))) for r in rs)
    p0 = _p(np.concatenate([_post(r, gps_off, 10.0, lte=False) for r in rs]), 95)
    return (
        f"| {name} | {tx:.0f} / {enbs:.0f} | {tracked:.1f} / {tr_enb:.1f} | {ghosts} | {wrong} | "
        f"{matched:.1f} / {coll:.1f} / {unk:.1f} | {enb_used:.1f} | "
        f"{_p(biases, 50):.1f} / {_p(biases, 95):.1f} | "
        f"{_p(rmss, 50):.1f} / {_p(rmss, 95):.1f} | "
        f"{p10:.1f} | {worst:.1f} | {p_all:.1f} | {max_err:.1f} | {p0:.1f} |"
    )


CASE_HEADER = (
    "| case | PCIs / eNBs sent | tracked cells / eNBs | ghost PCIs (sum) | wrong-timing tracks "
    "(sum) | lookup cells matched / collision / unknown | matched eNBs | range bias p50 / p95 "
    "(m) | range noise p50 / p95 (m) | p95 horiz 10 s (m) | worst-seed p95 10 s (m) | p95 horiz "
    "whole outage (m) | max horiz (m) | p95 horiz 10 s, no LTE (m) |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
)


def binned(rs: list[SeedResult], key, edges) -> list[tuple[str, int, int, int]]:
    """(label, present, searched, tracked) per bin [lo, hi); `edges` in either order."""
    out = []
    edges = sorted(edges)
    for a, b_ in zip(edges[:-1], edges[1:], strict=True):
        vals = [s for r in rs for s in r.sectors if a <= key(s) < b_]
        label = f"{a:g} to {b_:g}"
        out.append((label, len(vals), sum(s.searched for s in vals), sum(s.tracked for s in vals)))
    return [o for o in out if o[1]]


def _rel(s: SectorResult) -> float:
    return min(s.rel_db, -1e-9)  # the strongest cell (0 dB) falls in the top bin


def near_far_tables(name: str, rs: list[SeedResult]) -> str:
    lines = [f"\n**{name}: detection against power relative to the strongest cell (dB)**\n"]
    lines += ["| dB rel. strongest | sector-seeds | found by search | tracked | share tracked |",
              "| --- | --- | --- | --- | --- |"]  # fmt: skip
    rows = binned(rs, _rel, REL_BINS)
    for label, n, se, tr in reversed(rows):
        lines.append(f"| {label} | {n} | {se} | {tr} | {tr / n:.0%} |")
    lines += [f"\n**{name}: detection against distance (m)**\n",
              "| distance (m) | sector-seeds | found by search | tracked | share tracked |",
              "| --- | --- | --- | --- | --- |"]  # fmt: skip
    for label, n, se, tr in binned(rs, lambda s: s.range_m, DIST_BINS):
        lines.append(f"| {label} | {n} | {se} | {tr} | {tr / n:.0%} |")
    return "\n".join(lines)


def plot(by_case: dict[str, list[SeedResult]], commit: str, seeds: int, out: str) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for name, rs in by_case.items():
        if name.startswith("5-cell"):
            continue
        rows = binned(rs, _rel, REL_BINS)
        xs = [float(r[0].split(" to ")[0]) + 1 for r in rows]
        ax[0].plot(xs, [r[3] / r[1] for r in rows], "o-", ms=5, lw=1.8, label=name)
        rows = binned(rs, lambda s: s.range_m, DIST_BINS)
        xs = [float(r[0].split(" to ")[0]) for r in rows]
        ax[1].plot(xs, [r[3] / r[1] for r in rows], "o-", ms=5, lw=1.8, label=name)
    ax[0].set(xlabel="power relative to the strongest cell (dB, bin lower edge)",
              ylabel="share of sectors tracked", ylim=(-0.03, 1.03))  # fmt: skip
    ax[1].set(xlabel="distance to the sector (m, bin lower edge)")
    for a in ax:
        a.grid(True, alpha=0.3)
    ax[1].legend(frameon=False, fontsize=8)
    fig.suptitle(f"Dense synthetic LTE: {seeds} seeds, commit {commit} (TBC link budget)")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"\nwrote {out}")


def _run(args):
    return run_case(*args)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--gps-off", type=float, default=10.0)
    p.add_argument("--radii", default="2,3", help="km, TBC")
    p.add_argument("--spots", default="carleton", help="carleton,beside,far")
    p.add_argument("--snr", type=float, default=5.0, help="in-band dB of the 5-cell case, as #122")
    p.add_argument("--path-loss-exponent", type=float, default=Budget.path_loss_exponent)
    p.add_argument("--tx-offset-db", type=float, default=Budget.tx_offset_db)
    p.add_argument("--frame-sync", action="store_true", help="also run all eNBs frame-aligned")
    p.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    p.add_argument("--out")
    a = p.parse_args()
    b = Budget(path_loss_exponent=a.path_loss_exponent, tx_offset_db=a.tx_offset_db)
    sectors = load_sectors()
    radii = [float(v) for v in a.radii.split(",")]
    spots = {"carleton": TRUE_ENU, "beside": beside_a_tower(sectors), "far": far_from_all(sectors)}
    cases = [Case(f"5-cell equal {a.snr:g} dB", tuple(TRUE_ENU),
                  tuple(pick_equal_power(5, sectors)), equal_power_snr_db=a.snr)]  # fmt: skip
    for spot in a.spots.split(","):
        rx = spots[spot]
        for r in radii:
            secs = tuple(within(sectors, rx, r * 1e3))
            cases.append(Case(f"{spot} {r:g} km", tuple(float(v) for v in rx), secs))
            if a.frame_sync:
                cases.append(Case(f"{spot} {r:g} km frame-sync",
                                  tuple(float(v) for v in rx), secs, frame_sync=True))  # fmt: skip
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=7"], capture_output=True, text=True
    ).stdout.strip()

    t0 = time.perf_counter()
    jobs = [(c, s, b, a.duration, a.gps_off) for c in cases for s in range(a.seeds)]
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(_run, jobs))
    by_case: dict[str, list[SeedResult]] = {}
    for r in results:
        by_case.setdefault(r.case, []).append(r)
    wall = time.perf_counter() - t0

    print("## Dense baseband check of the LTE chain (#124)\n")
    print(f"Commit `{commit}`. Evidence kind: **synthetic baseband, TBC link budget**.\n")
    print(f"Settings: seeds 0..{a.seeds - 1}; {a.duration:g} s capture at {FS / 1e6:g} MS/s, GPS "
          f"off at {a.gps_off:g} s; EARFCN {EARFCN}; receiver static; dongle clock {PPM} ppm; "
          f"estimator ekf; budget {b}; noise floor {noise_dbm(b):.1f} dBm in "
          f"{BAND_HZ / 1e6:g} MHz; 8-bit `complex_to_cu8` (rms 24 LSB) scaled to the whole "
          "capture; no multipath; every eNB's frame timing uniform in 0..9 ms unless the case "
          "says frame-sync.\n")  # fmt: skip
    print(CASE_HEADER)
    for name, rs in by_case.items():
        print(case_row(name, rs, a.gps_off))
    print(f"\nCases: {[f'{c.name}: {len(c.sectors)} sectors' for c in cases]}. "
          f"Ghost = a tracked PCI that was not sent. Wrong-timing = tracked more than one sample "
          f"({WRONG_TIMING_M:.0f} m) from its truth. Range bias/noise: per tracked cell, median "
          "error and RMS about the mean, from the 10 Hz pseudoranges against synthesiser truth. "
          "`p95 horiz 10 s` pools the seeds over the 10 s after GPS off. Means are per seed; "
          "lookup and matched-eNB counts are cells, not records. `no LTE`: the same "
          "run with the LTE records removed (GNSS until GPS off, then barometer only), the "
          "control for a static receiver.\n")  # fmt: skip
    for name, rs in by_case.items():
        print(near_far_tables(name, rs))
    print("\n**Records through the lookup (sum over seeds)**\n")
    for name, rs in by_case.items():
        c = Counter()
        for r in rs:
            c.update(r.lookup_records)
        print(f"- {name}: {dict(c)}")
    print("\n**Per-seed**\n")
    for name, rs in by_case.items():
        for r in rs:
            print(f"- {name} seed {r.seed}: tracked {sum(s.tracked for s in r.sectors)}, "
                  f"ghosts {r.ghosts}, p95 10 s {_p(_post(r, a.gps_off, 10.0), 95):.1f} m, "
                  f"runtime {r.elapsed_s:.0f} s")  # fmt: skip
    print(f"\nWall time {wall:.0f} s on {a.workers} workers.")
    if a.out:
        plot(by_case, commit, a.seeds, a.out)


if __name__ == "__main__":
    main()
