"""Dense baseband check of the LTE chain (#124): every registered cell at realistic powers.

`lte_link_synthetic.py` (#121) hears 5 hand-picked eNBs at equal power. Here a static receiver
hears every sector on one carrier within a radius, each with its own PCI, true delay and a received
power from a link budget, through 8-bit quantisation scaled to the whole capture (so the strongest
cell sets the gain). The capture goes through the real front end, `pnt.nav.cells` and
`pnt.nav.estimate`. The 5-cell equal-power case runs in the same script on the same seeds.

    python analysis/lte_link_dense.py --seeds 3 --workers 2 --out /tmp/lte-dense.png

Three parts, each in the printed summary (`--parts`): `chain` (20 s captures through the front end,
the lookup and the EKF, with the near-far tables), `factors` (one change at a time on a short
capture, to say why cells are lost) and `ladder` (two controlled cells, the receiver's floor).

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
import pathlib
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace

import numpy as np

from pnt import nav
from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.frontends.lte import Config, capture, process_capture, synth, tracker
from pnt.frontends.lte import signals as sig
from pnt.nav.cells import (
    CELL_TABLE,
    COLLISION,
    MATCHED,
    OUT_OF_RANGE,
    UNKNOWN,
    CellTable,
    attach,
)

ORIGIN = (45.3876, -75.6960, 80.0)  # Carleton, the scenarios' session origin
TRUE_ENU = np.array([100.0, 50.0, 30.0])  # as in lte_link_synthetic.py
EARFCN, FC, FS = 2460, 875e6, 1.92e6
T0 = 1_446_000_000_000_000_000
C = 299792458.0
PPM = 0.4  # the dongle clock of lte_link_synthetic.py
BAND_HZ = 72 * sig.SUBCARRIER_HZ  # what `synth` calls in-band
WRONG_TIMING_M = C / FS  # one sample: a track further off than this is on the wrong timing
REL_BINS = (0, -3, -6, -10, -13, -15, -20, -30, -40, -200)  # dB relative to the strongest cell
SIR_BINS = (30, 0, -3, -6, -9, -12, -15, -20, -30, -200)  # dB against the sum of all the others
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
class Knobs:
    """One thing changed at a time. The defaults are the realistic case."""

    noise: bool = True
    quantise: bool = True
    frame_sync: bool = False  # every eNB on the same frame timing instead of uniform in 0..9 ms
    data_db: float = 0.0  # level of the non-sync symbols against PSS/SSS (0: fully loaded cells)
    drop_strongest: int = 0  # leave out the k strongest cells: what is left if they were cancelled
    config: tuple[tuple[str, int | float], ...] = ()  # front-end `Config` fields overridden
    # Distinct QPSK frames the synthesiser cycles (its default 8 repeats the data every 80 ms,
    # so interference integrated over longer than that adds up coherently, unlike real traffic)
    filler_frames: int = 8


@dataclass(frozen=True)
class Case:
    name: str
    rx: tuple[float, float, float]
    sectors: tuple[Sector, ...]
    equal_power_snr_db: float | None = None  # not None: the #122 case, all cells at this SNR
    knobs: Knobs = Knobs()


@dataclass
class SectorResult:
    pci: int
    enb_id: str
    range_m: float
    rel_db: float  # relative to the strongest cell of the capture
    sir_db: float  # against the sum of every other cell of the capture
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
    ghosts: list[int]  # tracked PCIs that were not sent
    search_ghosts: list[int]  # PCIs the search reported that were not sent
    candidates: list[tuple[int, int, float, float, bool]]  # (root, pci, PSS, SSS, true) at 80 ms
    lookup_cells: Counter
    lookup_records: Counter
    matched_enbs: int
    t: np.ndarray
    err: np.ndarray
    err_no_lte: np.ndarray  # the same run without LTE records: what the filter holds alone
    elapsed_s: float


def pseudorange_errors(records: list[Measurement], tower: synth.Tower) -> np.ndarray:
    """Record minus truth, m, wrapped to one frame (the definition in test_lte_frontend.py)."""
    L = sig.half_frame_length(FS)
    frame_m = C * sig.FRAME_S
    t = np.array([m.t_ns - T0 for m in records], float)
    v = np.array([m.value[0] for m in records])
    h = np.round((t * FS / 1e9 - tower.boundary_sample(0, FS, PPM)) / L)
    truth = C * (tower.boundary_sample(h / 2, FS, PPM) - h * L) / FS
    return (v - truth + frame_m / 2) % frame_m - frame_m / 2


class _NoAdcCapture(capture.Capture):
    """Complex samples read directly: the front end without the 8-bit quantiser."""

    def __init__(self, x: np.ndarray):
        super().__init__(
            path=pathlib.Path("c.cu8"),
            raw=np.empty(0, np.uint8),
            fs=FS,
            t0_ns=T0,
            dongle="c",
            segments=[capture.Segment(0, x.size, FC, EARFCN)],
        )
        rms = math.sqrt(float(np.mean(x.real**2 + x.imag**2)) / 2) or 1.0
        self.x = (x * (24.0 / rms / 128.0)).astype(
            np.complex64
        )  # the level `complex_to_cu8` gives

    @property
    def n_samples(self) -> int:
        return self.x.size

    def read(self, start: int, count: int) -> np.ndarray:
        return self.x[max(0, start) : start + count]

    def gather(self, idx: np.ndarray) -> np.ndarray:
        return self.x[np.asarray(idx, dtype=np.int64)]


@contextmanager
def filler_frames(n: int):
    """Let the synthesiser cycle `n` distinct data frames instead of its 8 (nothing in `src/`
    changes). More frames draw more random numbers, so the signals differ from the default."""
    original = synth._FILLER_FRAMES
    synth._FILLER_FRAMES = n
    try:
        yield
    finally:
        synth._FILLER_FRAMES = original


@contextmanager
def data_level(db: float):
    """Scale the symbols that carry no PSS/SSS by `db`: a partly loaded cell, for the factors.

    Reaches into `synth._symbol_table` because the synthesiser has no load setting; nothing
    in `src/` changes. TBC: the mapping from this level to a real cell's traffic load."""
    if db == 0.0:
        yield
        return
    original = synth._symbol_table
    n_sym = synth._FILLER_FRAMES * sig.SYMBOLS_PER_FRAME
    sync = np.zeros(n_sym, bool)
    for f in range(synth._FILLER_FRAMES):
        for slot in (0, 10):
            base = f * sig.SYMBOLS_PER_FRAME + slot * sig.SYMBOLS_PER_SLOT
            sync[[base + sig.SSS_SYMBOL, base + sig.PSS_SYMBOL]] = True

    def table(pci: int, rng: np.random.Generator) -> np.ndarray:
        t = original(pci, rng).copy()
        t[:, ~sync] *= 10 ** (db / 20)
        return t

    synth._symbol_table = table
    try:
        yield
    finally:
        synth._symbol_table = original


def search_candidates(cap, towers: list[synth.Tower], cfg: Config) -> list[tuple]:
    """Every PSS peak over the threshold in the first search window, whatever the SSS says.

    The SSS check is off and the per-root cap is 30, so this shows what the front end looks at,
    not what it keeps: one entry per decoded PCI, (root, pci, PSS metric, SSS metric, true). `true`
    needs the PCI sent and the timing within 2 samples of that cell's frame, since a ghost can
    decode to a sent PCI by chance."""
    open_cfg = replace(cfg, sss_peak_to_mean=-1e9, max_cells_per_root=30)
    n = int(open_cfg.acq_ms * 1e-3 * FS)
    found = tracker.search(cap.read(0, n), 0, FS, FC, open_cfg)
    frame = 2 * sig.half_frame_length(FS)

    def is_true(f) -> bool:
        return any(
            t.pci == f.pci
            and abs((f.boundary - t.boundary_sample(0, FS, PPM) + frame / 2) % frame - frame / 2)
            < 2
            for t in towers
        )

    return [(f.n_id2, f.pci, f.pss_metric, f.sss_metric, is_true(f)) for f in found]


def run_case(
    case: Case, seed: int, b: Budget, duration: float, gps_off: float, nav_eval: bool = True
) -> SeedResult:
    """One capture, as in `lte_link_synthetic.run`: same draw order for the 5-cell case.
    `nav_eval=False` stops after the front end and the lookup (the short factor captures)."""
    t_start = time.perf_counter()
    rng = np.random.default_rng(seed)
    rx = np.array(case.rx)
    k_ = case.knobs
    cfg = replace(Config(), **dict(k_.config))
    budget_snr = [noise_free_snr(s, rx, b) for s in case.sectors]
    if case.equal_power_snr_db is not None:
        powers, ref_snr = [0.0] * len(case.sectors), case.equal_power_snr_db
    else:
        powers, ref_snr = budget_snr, 0.0
    clocks: dict[str, float] = {}  # sectors of one eNB share their frame timing (ADR-0022)
    towers = []
    for s, p in zip(case.sectors, powers, strict=True):
        rho = float(np.linalg.norm(rx - np.array(s.enu)))
        clock = (
            0.0 if k_.frame_sync else clocks.setdefault(s.enb_id, float(rng.uniform(0.0, 0.009)))
        )
        towers.append(synth.Tower(pci=s.pci, delay_s=rho / C + clock, power_db=p))
    # Sent cells only from here on. The draws above stay the same whatever is dropped.
    keep = sorted(range(len(towers)), key=lambda i: -powers[i])[k_.drop_strongest :]
    keep.sort()
    sectors = [case.sectors[i] for i in keep]
    towers = [towers[i] for i in keep]
    powers = [powers[i] for i in keep]
    budget_snr = [budget_snr[i] for i in keep]
    snr_arg = ref_snr if k_.noise else None
    with filler_frames(k_.filler_frames), data_level(k_.data_db):
        x = synth.synthesize(
            towers, duration, fs=FS, fc=FC, clock_ppm=PPM, snr_db=snr_arg, seed=seed
        )
    meta = {"sample_rate_hz": FS, "center_freq_hz": FC, "t_ns": T0}
    sent_pcis = {s.pci for s in sectors}
    with tempfile.TemporaryDirectory() as d:
        if k_.quantise:
            path = capture.write_capture(
                pathlib.Path(d) / "c.cu8", capture.complex_to_cu8(x), meta
            )
            del x
            cap = capture.open_capture(path)
        else:
            cap = _NoAdcCapture(x)
        candidates = search_candidates(cap, towers, cfg)
        result = process_capture(cap, cfg)

    records = list(result.measurements)
    pr: dict[int, list[Measurement]] = {}
    for m in records:
        if m.kind == "pseudorange":
            pr.setdefault(m.meta["pci"], []).append(m)
    searched = {f.pci for _, f in result.found}
    top = max(powers) if sectors else 0.0
    power_w = np.array([10 ** (p / 10) for p in powers])
    sector_results = []
    used: set[int] = set()  # the cell tracked under a PCI goes to one sector, its best-timed one
    by_pci: dict[int, list[int]] = {}
    for i, s in enumerate(sectors):
        by_pci.setdefault(s.pci, []).append(i)
    best_sector: dict[int, tuple[int, np.ndarray]] = {}
    for pci, recs in pr.items():
        options = [(i, pseudorange_errors(recs, towers[i])) for i in by_pci.get(pci, [])]
        if options:
            best_sector[pci] = min(options, key=lambda o: abs(float(np.median(o[1]))))
    for i, s in enumerate(sectors):
        others = float(power_w.sum() - power_w[i])
        res = SectorResult(
            pci=s.pci,
            enb_id=s.enb_id,
            range_m=float(np.linalg.norm(rx - np.array(s.enu))),
            rel_db=powers[i] - top,
            sir_db=powers[i] - 10 * math.log10(others) if others > 0 else float("inf"),
            snr_db=ref_snr if case.equal_power_snr_db is not None else budget_snr[i],
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
    ghosts = sorted(set(pr) - sent_pcis)
    search_ghosts = sorted(searched - sent_pcis)

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

    if not nav_eval:
        return SeedResult(
            case=case.name,
            seed=seed,
            sectors=sector_results,
            ghosts=ghosts,
            search_ghosts=search_ghosts,
            candidates=candidates,
            lookup_cells=lookup_cells,
            lookup_records=lookup_records,
            matched_enbs=len(matched_enbs),
            t=np.zeros(0),
            err=np.zeros(0),
            err_no_lte=np.zeros(0),
            elapsed_s=time.perf_counter() - t_start,
        )

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
        search_ghosts=search_ghosts,
        candidates=candidates,
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
    s_ghosts = sum(len(r.search_ghosts) for r in rs)
    wrong = sum(sum(s.wrong_timing for s in r.sectors) for r in rs)
    cells = Counter()
    for r in rs:
        cells.update(r.lookup_cells)
    n = len(rs)
    matched = cells[MATCHED] / n
    coll = cells[COLLISION] / n
    unk = cells[UNKNOWN] / n
    oor = cells[OUT_OF_RANGE] / n
    enb_used = np.mean([r.matched_enbs for r in rs])
    biases = np.array([abs(s.bias_m) for r in rs for s in r.sectors if s.tracked])
    rmss = np.array([s.rms_m for r in rs for s in r.sectors if s.tracked])
    p10 = _p(np.concatenate([_post(r, gps_off, 10.0) for r in rs]), 95)
    p_all = _p(np.concatenate([_post(r, gps_off) for r in rs]), 95)
    worst = max(_p(_post(r, gps_off, 10.0), 95) for r in rs)
    max_err = max(float(np.max(_post(r, gps_off))) for r in rs)
    p0 = _p(np.concatenate([_post(r, gps_off, 10.0, lte=False) for r in rs]), 95)
    return (
        f"| {name} | {tx:.0f} / {enbs:.0f} | {tracked:.1f} / {tr_enb:.1f} | {ghosts} / {s_ghosts} "
        f"| {wrong} | {matched:.1f} / {coll:.1f} / {unk:.1f} / {oor:.1f} | {enb_used:.1f} | "
        f"{_p(biases, 50):.1f} / {_p(biases, 95):.1f} | "
        f"{_p(rmss, 50):.1f} / {_p(rmss, 95):.1f} | "
        f"{p10:.1f} | {worst:.1f} | {p_all:.1f} | {max_err:.1f} | {p0:.1f} |"
    )


CASE_HEADER = (
    "| case | PCIs / eNBs sent | tracked cells / eNBs | ghost PCIs tracked / searched (sum) | "
    "wrong-timing tracks (sum) | lookup cells matched / collision / unknown / out of range | "
    "matched eNBs | range bias p50 / p95 "
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
    lines = [f"\n**{name}: cells present against power relative to the strongest (dB)**\n"]
    lines += ["| dB rel. strongest | sector-seeds | found by search | tracked | share tracked |",
              "| --- | --- | --- | --- | --- |"]  # fmt: skip
    for label, n, se, tr in reversed(binned(rs, _rel, REL_BINS)):
        lines.append(f"| {label} | {n} | {se} | {tr} | {tr / n:.0%} |")
    lines += [f"\n**{name}: cells present against the sum of every other cell (dB)**\n",
              "| SIR (dB) | sector-seeds | found by search | tracked | share tracked |",
              "| --- | --- | --- | --- | --- |"]  # fmt: skip
    for label, n, se, tr in reversed(binned(rs, lambda s: s.sir_db, SIR_BINS)):
        lines.append(f"| {label} | {n} | {se} | {tr} | {tr / n:.0%} |")
    lines += [f"\n**{name}: cells present against distance (m)**\n",
              "| distance (m) | sector-seeds | found by search | tracked | share tracked |",
              "| --- | --- | --- | --- | --- |"]  # fmt: skip
    for label, n, se, tr in binned(rs, lambda s: s.range_m, DIST_BINS):
        lines.append(f"| {label} | {n} | {se} | {tr} | {tr / n:.0%} |")
    n_sec = len(rs[0].sectors)
    tracked = [k for k in range(n_sec) if any(r.sectors[k].tracked for r in rs)]
    lines += [f"\n**{name}: every cell tracked in any seed (range error against truth)**\n",
              "| PCI | eNB | range (m) | dB rel. strongest | SIR (dB) | seeds tracked | "
              "bias, median over seeds (m) | worst bias (m) | noise, median (m) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    for k in sorted(tracked, key=lambda k: -rs[0].sectors[k].rel_db):
        hits = [r.sectors[k] for r in rs if r.sectors[k].tracked]
        s0 = rs[0].sectors[k]
        bias = [h.bias_m for h in hits]
        lines.append(
            f"| {s0.pci} | {s0.enb_id} | {s0.range_m:.0f} | {s0.rel_db:.1f} | {s0.sir_db:.1f} | "
            f"{len(hits)}/{len(rs)} | {np.median(bias):.1f} | {max(bias, key=abs):.1f} | "
            f"{np.median([h.rms_m for h in hits]):.1f} |"
        )
    return "\n".join(lines)


def budget_lines(cases: list[Case], b: Budget) -> str:
    """The link budget in numbers, before any signal: the gap the receiver has to span."""
    out = ["| case | sectors | strongest (dBm in band) | its SNR (dB) | dB rel. strongest, top 8 "
           "| sectors within 13 dB of strongest | SIR of strongest (dB) | sectors with SIR above "
           "-13 dB |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    for c in cases:
        rx = np.array(c.rx)
        p = np.sort([rx_band_power_dbm(s, rx, b) for s in c.sectors])[::-1]
        w = 10 ** (p / 10)
        sir = 10 * np.log10(w / np.maximum(w.sum() - w, 1e-30))
        out.append(
            f"| {c.name} | {len(c.sectors)} | {p[0]:.1f} | {p[0] - noise_dbm(b):.1f} | "
            f"{', '.join(f'{v - p[0]:.1f}' for v in p[:8])} | {int(np.sum(p >= p[0] - 13))} | "
            f"{sir[0]:.1f} | {int(np.sum(sir >= -13))} |"
        )
    return "\n".join(out)


def receiver_floors(cfg: Config) -> tuple[float, float]:
    """The weakest cell each stage can accept next to fully loaded interference, dB per RE.

    Search: the folded PSS metric is 1 + 62 ρ for a cell at ρ of the interference, because the
    mean it is divided by holds that interference. Tracker: the 124 PSS+SSS elements give
    `snr_post` = 124 ρ, against `detect_snr_db`. An approximation; `ladder` measures it."""
    return (
        10 * math.log10((cfg.acq_peak_to_mean - 1.0) / sig.N_SYNC),
        cfg.detect_snr_db - 10 * math.log10(2 * sig.N_SYNC),
    )


# --- factors and ladder ------------------------------------------------------------------


FACTORS: list[tuple[str, Knobs]] = [
    ("as modelled", Knobs()),
    ("no thermal noise", Knobs(noise=False)),
    ("no 8-bit quantiser", Knobs(quantise=False)),
    ("neither noise nor quantiser", Knobs(noise=False, quantise=False)),
    ("every eNB frame-aligned", Knobs(frame_sync=True)),
    ("data symbols at -10 dB (partial load, TBC)", Knobs(data_db=-10.0)),
    ("data symbols at -20 dB (light load, TBC)", Knobs(data_db=-20.0)),
    ("search over 320 ms, not 80", Knobs(config=(("acq_ms", 320.0),))),
    ("search cap 30 per root, not 6", Knobs(config=(("max_cells_per_root", 30),))),
    ("data at -20 dB and search cap 300",
     Knobs(data_db=-20.0, config=(("max_cells_per_root", 300),))),
    ("search 2.5, tracker 3 dB gates (counterfactual)",
     Knobs(config=(("acq_peak_to_mean", 2.5), ("detect_snr_db", 3.0)))),
    ("strongest cell not sent", Knobs(drop_strongest=1)),
    ("3 strongest cells not sent", Knobs(drop_strongest=3)),
]  # fmt: skip

LADDER_DB = (-3.0, -6.0, -8.0, -10.0, -11.0, -12.0, -13.0, -14.0, -16.0, -20.0, -25.0)


def factor_table(name: str, by_case: dict[str, list[SeedResult]], labels: list[str]) -> str:
    out = [f"\n**Factors, {name}: one change at a time**\n",
           "| change | cells sent | found by search (mean) | tracked (mean) | "
           "ghost PCIs tracked / searched (sum) | wrong-timing (sum) | weakest tracked: dB rel. "
           "strongest sent | weakest tracked: SIR (dB) |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    for label in labels:
        rs = by_case.get(f"{name} / {label}")
        if rs is None:
            continue
        tracked = [s for r in rs for s in r.sectors if s.tracked]
        sent = np.mean([len(r.sectors) for r in rs])
        found = np.mean([sum(s.searched for s in r.sectors) for r in rs])
        mean_tr = np.mean([sum(s.tracked for s in r.sectors) for r in rs])
        ghosts = sum(len(r.ghosts) for r in rs)
        s_ghosts = sum(len(r.search_ghosts) for r in rs)
        wrong = sum(s.wrong_timing for r in rs for s in r.sectors)
        rel = f"{min(s.rel_db for s in tracked):.1f}" if tracked else "none"
        sir = f"{min(s.sir_db for s in tracked):.1f}" if tracked else "none"
        out.append(f"| {label} | {sent:.0f} | {found:.1f} | {mean_tr:.1f} | {ghosts} / {s_ghosts} "
                   f"| {wrong} | {rel} | {sir} |")  # fmt: skip
    return "\n".join(out)


def candidate_lines(name: str, rs: list[SeedResult]) -> str:
    out = [f"\n**Search candidates, {name} as modelled (first window, SSS check off, cap 30 "
           "per root): PCI (PSS metric / SSS metric); `*` = a sent cell at its own timing**\n"
           ]  # fmt: skip
    for r in rs:
        by_root: dict[int, list[str]] = {0: [], 1: [], 2: []}
        for root, pci, pss, sss, sent in sorted(r.candidates, key=lambda c: -c[2]):
            by_root[root].append(f"{pci}{'*' if sent else ''} ({pss:.1f}/{sss:.1f})")
        parts = [f"root {k}: {len(v)} [{', '.join(v[:6])}{'...' if len(v) > 6 else ''}]"
                 for k, v in by_root.items()]  # fmt: skip
        out.append(f"- seed {r.seed}: " + "; ".join(parts))
    return "\n".join(out)


def ladder_cases(sectors: list[Sector], b: Budget) -> list[Case]:
    """Two cells, the weak one at a set level under the strong one: the receiver's own floor."""
    rx = TRUE_ENU
    near = sorted(within(sectors, rx, 2000.0), key=lambda s: -rx_band_power_dbm(s, rx, b))
    strong, weak = near[0], next(s for s in near[1:] if s.enb_id != near[0].enb_id)
    same = replace(weak, pci=strong.pci + 3)  # one N_ID1 up: the same PSS root
    other = weak if weak.pci % 3 != strong.pci % 3 else replace(weak, pci=weak.pci + 1)
    ref = rx_band_power_dbm(strong, rx, b)
    out = []
    for rel in LADDER_DB:
        for root, w in (("same root", same), ("other root", other)):
            shift = ref + rel - rx_band_power_dbm(w, rx, b)
            pair = (strong, replace(w, tx_power_dbw=w.tx_power_dbw + shift))
            out.append(Case(f"ladder {root} {rel:g}", tuple(float(v) for v in rx), pair))
    return out


def ladder_table(rs_by: dict[str, list[SeedResult]], seeds: int) -> str:
    out = ["\n**Ladder: two cells, the weak one at a set level (no other cell)**\n",
           "| weak cell (dB rel. strong) | same root: found / tracked of "
           f"{seeds} | same root: weak-cell bias, median (m) | other root: found / tracked of "
           f"{seeds} | other root: weak-cell bias, median (m) | ghost PCIs (sum) |",
           "| --- | --- | --- | --- | --- | --- |"]  # fmt: skip
    for rel in LADDER_DB:
        cols, ghosts = [], 0
        for root in ("same root", "other root"):
            rs = rs_by[f"ladder {root} {rel:g}"]
            weak = [r.sectors[1] for r in rs]
            ghosts += sum(len(r.ghosts) + len(r.search_ghosts) for r in rs)
            tracked = [w.bias_m for w in weak if w.tracked]
            cols.append(f"{sum(w.searched for w in weak)} / {sum(w.tracked for w in weak)} | "
                        f"{np.median(tracked) if tracked else float('nan'):.1f}")  # fmt: skip
        out.append(f"| {rel:g} | {cols[0]} | {cols[1]} | {ghosts} |")
    return "\n".join(out)


def plot(by_case: dict[str, list[SeedResult]], commit: str, a, out: str) -> None:
    """Left: every sector sent, by distance and power relative to the strongest; filled if
    tracked in any seed. Right: median horizontal error over the seeds, with and without LTE."""
    import matplotlib.pyplot as plt

    colors = ["#20639b", "#b5442e", "#3c8d2f", "#7b4fa0", "#c98a00", "#4a4a4a", "#1b9e9e"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    for i, (name, rs) in enumerate(by_case.items()):
        col = colors[i % len(colors)]
        if not name.startswith("5-cell"):
            n = len(rs[0].sectors)
            dist = np.array([s.range_m for s in rs[0].sectors]) / 1e3
            rel = np.maximum([s.rel_db for s in rs[0].sectors], -60.0)
            hit = np.array([any(r.sectors[k].tracked for r in rs) for k in range(n)])
            ax[0].scatter(dist[~hit], rel[~hit], s=22, facecolors="none", edgecolors=col, lw=0.9)
            ax[0].scatter(dist[hit], rel[hit], s=30, color=col, label=f"{name} (filled: tracked)")
        t = rs[0].t
        same = all(len(r.t) == len(t) for r in rs)
        if same:
            ax[1].plot(t, np.median([r.err for r in rs], axis=0), color=col, lw=1.6, label=name)
            ax[1].plot(t, np.median([r.err_no_lte for r in rs], axis=0), color=col, lw=1.0,
                       ls=":")  # fmt: skip
    ax[0].set(xlabel="distance to the sector (km)", ylim=(-62, 3),
              ylabel="power relative to the strongest cell (dB, floor -60)")  # fmt: skip
    ax[0].legend(frameon=False, fontsize=7, loc="lower left")
    ax[1].axvline(a.gps_off, color="0.4", ls="--", lw=1)
    ax[1].set(xlabel="time (s)", ylabel="median horizontal error over seeds (m)", yscale="log",
              title="solid: with LTE; dotted: same run without LTE")  # fmt: skip
    ax[1].title.set_fontsize(9)
    ax[1].legend(frameon=False, fontsize=7)
    for x in ax:
        x.grid(True, alpha=0.3)
    fig.suptitle(f"Dense synthetic LTE (TBC link budget): seeds 0..{a.seeds - 1}, "
                 f"commit {commit}")  # fmt: skip
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"\nwrote {out}")


def _run(args):
    return run_case(*args)


def _build_case(spec: str, sectors: list[Sector], spots: dict[str, np.ndarray]) -> Case:
    """`spot:radius_km`, e.g. `carleton:2` or `far:5`."""
    spot, radius = spec.split(":")
    rx = spots[spot]
    secs = tuple(within(sectors, rx, float(radius) * 1e3))
    return Case(f"{spot} {float(radius):g} km", tuple(float(v) for v in rx), secs)


def _parse_config(spec: str) -> tuple[tuple[str, int | float], ...]:
    """`name=value,...` into `Knobs.config` pairs; ints stay ints."""
    out = []
    for item in filter(None, spec.split(",")):
        name, value = item.split("=")
        if name not in Config.__dataclass_fields__:
            raise SystemExit(f"--config: no Config field {name!r}")
        out.append((name, int(value) if value.lstrip("-").isdigit() else float(value)))
    return tuple(out)


def _with_config(case: Case, base: tuple, filler: int = 8) -> Case:
    """`case` with `base` Config fields under its own (its own win) and `filler` data frames."""
    merged = {**dict(base), **dict(case.knobs.config)}
    knobs = replace(case.knobs, config=tuple(merged.items()), filler_frames=filler)
    return replace(case, knobs=knobs)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--duration", type=float, default=20.0, help="s, the chain part")
    p.add_argument("--gps-off", type=float, default=10.0)
    p.add_argument(
        "--cases", default="carleton:2,beside:2,far:2,far:5", help="spot:radius km, TBC"
    )
    p.add_argument("--factor-cases", default="carleton:2,far:5", help="spot:radius km, TBC")
    p.add_argument("--factor-duration", type=float, default=2.0, help="s, factors and ladder")
    p.add_argument("--parts", default="chain,factors,ladder", help="chain,factors,ladder")
    p.add_argument("--snr", type=float, default=5.0, help="in-band dB of the 5-cell case, as #122")
    p.add_argument("--path-loss-exponent", type=float, default=Budget.path_loss_exponent)
    p.add_argument("--tx-offset-db", type=float, default=Budget.tx_offset_db)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument(
        "--config",
        default="",
        help="front-end `Config` fields for every case, e.g. acq_coherent=15,track_coherent=8; "
        "a factor's own fields win",
    )
    p.add_argument(
        "--filler-frames",
        type=int,
        default=8,
        help="distinct data frames in the synthesiser, every case (default 8)",
    )
    p.add_argument("--out")
    a = p.parse_args()
    b = Budget(path_loss_exponent=a.path_loss_exponent, tx_offset_db=a.tx_offset_db)
    sectors = load_sectors()
    spots = {"carleton": TRUE_ENU, "beside": beside_a_tower(sectors), "far": far_from_all(sectors)}
    parts = a.parts.split(",")
    equal = Case(f"5-cell equal {a.snr:g} dB", tuple(TRUE_ENU),
                 tuple(pick_equal_power(5, sectors)), equal_power_snr_db=a.snr)  # fmt: skip
    chain = [equal] + [_build_case(c, sectors, spots) for c in a.cases.split(",")]
    factor_bases = [_build_case(c, sectors, spots) for c in a.factor_cases.split(",")]
    base_cfg = _parse_config(a.config)
    chain = [_with_config(c, base_cfg, a.filler_frames) for c in chain]
    factor_bases = [_with_config(c, base_cfg, a.filler_frames) for c in factor_bases]
    jobs = []
    if "chain" in parts:
        jobs += [(c, s, b, a.duration, a.gps_off, True) for c in chain for s in range(a.seeds)]
    factor_labels = [label for label, _ in FACTORS]
    if "factors" in parts:
        for base in factor_bases:
            for label, knobs in FACTORS:
                c = replace(
                    base,
                    name=f"{base.name} / {label}",
                    knobs=_with_config(
                        replace(base, knobs=knobs), base_cfg, a.filler_frames
                    ).knobs,
                )
                jobs += [(c, s, b, a.factor_duration, a.factor_duration, False)
                         for s in range(a.seeds)]  # fmt: skip
    ladder = (
        [_with_config(c, base_cfg, a.filler_frames) for c in ladder_cases(sectors, b)]
        if "ladder" in parts
        else []
    )
    jobs += [(c, s, b, a.factor_duration, a.factor_duration, False) for c in ladder
             for s in range(a.seeds)]  # fmt: skip
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=7"], capture_output=True, text=True,
        cwd=pathlib.Path(__file__).resolve().parent,
    ).stdout.strip()  # fmt: skip

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(_run, jobs))
    by_case: dict[str, list[SeedResult]] = {}
    for r in results:
        by_case.setdefault(r.case, []).append(r)
    wall = time.perf_counter() - t0

    print("## Dense baseband check of the LTE chain (#124)\n")
    print(f"Commit `{commit}`. Evidence kind: **synthetic baseband, TBC link budget**.\n")
    if base_cfg:
        print(f"Front-end `Config` overrides for every case: {dict(base_cfg)}.\n")
    if a.filler_frames != 8:
        print(f"Synthesiser data frames: {a.filler_frames} (default 8).\n")
    print(f"Settings: seeds 0..{a.seeds - 1}; chain {a.duration:g} s capture at "
          f"{FS / 1e6:g} MS/s, GPS off at {a.gps_off:g} s; factors and ladder "
          f"{a.factor_duration:g} s; EARFCN "
          f"{EARFCN}; receiver static; dongle clock {PPM} ppm; estimator ekf; budget {b}; noise "
          f"floor {noise_dbm(b):.1f} dBm in {BAND_HZ / 1e6:g} MHz; 8-bit `complex_to_cu8` (rms 24 "
          "LSB) scaled to the whole capture; no multipath; every eNB's frame timing uniform in "
          "0..9 ms, one per eNB; every data resource element filled.\n")  # fmt: skip
    print("**Link budget before any signal (TBC)**\n")
    print(
        budget_lines(
            chain[1:] + [c for c in factor_bases if c.name not in {x.name for x in chain}], b
        )
    )  # noqa: E501
    search_floor, track_floor = receiver_floors(Config())
    print(f"\nReceiver floors from `Config`, against fully loaded interference: search "
          f"{search_floor:.1f} dB (`acq_peak_to_mean` {Config().acq_peak_to_mean}), tracker "
          f"{track_floor:.1f} dB (`detect_snr_db` {Config().detect_snr_db}). A cell below these "
          "cannot be kept whatever the noise and the quantiser do. `ladder` measures them.\n"
          )  # fmt: skip

    if "chain" in parts:
        print("### Chain\n")
        print(CASE_HEADER)
        for c in chain:
            print(case_row(c.name, by_case[c.name], a.gps_off))
        print(f"\nCases: {[f'{c.name}: {len(c.sectors)} sectors' for c in chain]}. "
              f"Ghost = a PCI that was not sent. Wrong-timing = tracked more than one sample "
              f"({WRONG_TIMING_M:.0f} m) from its truth. Range bias/noise: per tracked cell, "
              "median error and RMS about the mean, from the 10 Hz pseudoranges against "
              "synthesiser truth. `p95 horiz 10 s` pools the seeds over the 10 s after GPS off. "
              "Means are per seed; lookup and matched-eNB counts are cells, not records. `no "
              "LTE`: the same run with the LTE records removed (GNSS until GPS off, then "
              "barometer only), the control for a static receiver.\n")  # fmt: skip
        table = CellTable.load()
        print("**How the lookup splits every cell sent (table, session origin Carleton)**\n")
        for c in chain:
            st = Counter(
                table.associate(EARFCN, pci, ORIGIN)[0] for pci in {s.pci for s in c.sectors}
            )
            print(f"- {c.name}: {dict(st)}")
        print()
        for c in chain:
            print(near_far_tables(c.name, by_case[c.name]))
        print("\n**Records through the lookup (sum over seeds)**\n")
        for c in chain:
            cnt = Counter()
            for r in by_case[c.name]:
                cnt.update(r.lookup_records)
            print(f"- {c.name}: {dict(cnt)}")
        print("\n**Per-seed**\n")
        for c in chain:
            for r in by_case[c.name]:
                print(f"- {c.name} seed {r.seed}: tracked {sum(s.tracked for s in r.sectors)}, "
                      f"ghosts {r.ghosts}, search ghosts {r.search_ghosts}, p95 10 s "
                      f"{_p(_post(r, a.gps_off, 10.0), 95):.1f} m, "
                      f"runtime {r.elapsed_s:.0f} s")  # fmt: skip
    if "factors" in parts:
        print("\n### Factors (short captures)\n")
        for base in factor_bases:
            print(factor_table(base.name, by_case, factor_labels))
            print(candidate_lines(base.name, by_case[f"{base.name} / as modelled"]))
    if ladder:
        print("\n### Ladder (short captures)\n")
        print(ladder_table(by_case, a.seeds))
    print(f"\nWall time {wall:.0f} s on {a.workers} workers.")
    if a.out and "chain" in parts:
        plot({c.name: by_case[c.name] for c in chain}, commit, a, a.out)


if __name__ == "__main__":
    main()
