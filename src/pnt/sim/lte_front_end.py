"""LTE records shaped as the front end writes them, for the simulator (#134, ADR-0023).

`pnt.frontends.lte` names a heard cell `lte:<earfcn>:<pci>`, gives no tower position, names its
dongle's clock in `meta.rx_clock` and knows each range only modulo one 10 ms frame. Records made
here have that shape, so they go through `pnt.nav.cells.attach` exactly as a capture's do. Opt in
with `record_shape: front_end` on a pseudorange source (`scenario.generate`).

What is on air: every sector of one EARFCN in a cell table (`cells_from`), PCI reuse included. A
PCI that more than one eNB uses is heard as one cell per epoch (the strongest, or the nearest),
as the front end tracks one cell per PCI. The lookup never matches it, wherever its eNBs are
(#138): it is a collision, or out of range if none is within `cells.MAX_RANGE_KM` of the origin.

Which cells are heard (`hearing`):
- `range`: every sector within `hearing_km` of the truth, horizontally, at that epoch.
- `link_budget`: each sector's in-band power from its filed power, distance and sector pattern
  (`LinkBudget`, as `analysis/lte_link_dense.py`). A sector is heard at an epoch if it is above
  the noise floor and within `floor_db` of the strongest sector heard then (the front end's
  near-far floor). Computed at every record epoch, not on a coarser grid.

Error terms, each drawn for every sector or eNB whether heard or not, on a random stream of its
own, so a change to one term or to the hearing model leaves every other draw as it was:
- the dongle's clock (`Dongle`), apart from the payload's `clock:`
- site clocks from the scenario's `tower_clocks:` (ADR-0022): per eNB, shared by its sectors
- white noise per sector (`sigma_m`); the records report `told_sigma_m` when it is given (#118)
- multipath and dropout per eNB: the sectors of one mast share its path to the receiver. A
  dropout acts as a blockage: the eNB is neither heard nor sets the near-far floor
- table position error per eNB (`told_position_sigma_m`): the table is what the filter is told,
  and the true mast is that plus a horizontal error

`meta` carries the front end's fields where the sim has the quantity: `snr_db` (link budget
only: against noise and every other sector on air, fully loaded), `cfo_hz` (from the rate of
geometry and clocks), `n_epochs` (5 ms epochs per record), `sigma_crb_m` (the reported sigma).
`sample_index` is left out: there is no capture file to index. `flags` is empty. `arc` is 0
unless `arcs:` is on (below): re-acquisition after a gap in hearing is not what starts an arc
here (TBC); the lookup aligns values across the frame ambiguity either way. Only pseudoranges are
made, not the front end's dopplers.

Opt-in terms of #278, each off by default and drawn on a stream of its own:
- `troposphere: {m_per_km}`: excess delay per km of true range, per eNB (`models.troposphere`).
- `arcs: {}` (or any `Arcs` field): each sector's front end re-finds the cell and starts a new
  arc (`meta.arc` counts them) at the rate measured on real static sessions, and each arc
  carries a range offset of its own (`Arcs`; the model of #262's measured-noise ladder).
- A constant range bias per sector is `tower_clocks: sector: {offset_m}` (scenario.py).

Carrier hopping (#173): `cells_from.earfcn` may list several carriers, with a `hop:` block
(`Hop`). One dongle, one clock, dwells on each carrier in the list's order in turn, from t = 0.
- Record epochs follow the dwells (`dwell_schedule`): none in the first `reacquire_s` of each
  dwell (retune, settling, a search window), then one at the start of what is left and more at
  `rate_hz` while the dwell lasts. A dwell shorter than 1 / `rate_hz` still gets one record, so
  dwells under 1 s at 1 Hz make more records per second than one carrier does.
- At an epoch only the dwelled carrier's sectors are on air: hearing, the near-far floor, the
  one-cell-per-PCI rule and `snr_db` are all within that carrier.
- Every sector of every carrier is drawn as before: site clocks per registered eNB across its
  carriers (ADR-0022; `scenario.tower_groups`), multipath, dropout and table position error per
  eNB, so the sectors of one eNB share them on every carrier.
- `arc` stays 0 across dwells. The front end carries a cell across a retune (`frontend._start`)
  and continues its arc when the re-found timing is within 3 sigma + 2 samples of the loop's
  prediction, which at dwell cycles of seconds it should be (TBC, no capture has hopped).
- With one carrier there is no retune: `hop:` changes nothing and the records are the
  single-EARFCN form's.

Every value is TBC (ADR-0015).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist

import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.sim import models

FRAME_S = 0.01  # one LTE radio frame (3GPP TS 36.211 4.1)
AMBIGUITY_M = models.C_MPS * FRAME_S  # the front end's `meta.ambiguity_m`
EPOCH_S = 0.005  # the front end's tracking epoch, half a frame: `meta.n_epochs` counts these
# Random streams of their own, apart from scenario.py's (220 to 222) and the run's main stream
_DONGLE_STREAM, _NOISE_STREAM, _MULTIPATH_STREAM, _DROPOUT_STREAM, _POSITION_STREAM = range(
    223, 228
)
KEYS = frozenset(
    {
        "cells_from",
        "hearing",
        "dongle",
        "sigma_m",
        "told_sigma_m",
        "multipath",
        "dropout",
        "told_position_sigma_m",
        "hop",
        "troposphere",
        "arcs",
    }
)
# Streams of the opt-in terms of #278 (scenario.py uses 250 to 252)
_TROPO_STREAM, _ARC_STREAM = 253, 254
_NEEDS_HOP = "several carriers need a hop: block (one dongle hears one carrier at a time)"


@dataclass(frozen=True)
class Dongle:
    """The front end's receiver clock: the RTL-SDR's own TCXO, not the payload's `clock:`.

    Its offset is uniform within one frame (any value is the same after wrapping), its frequency
    error is drawn once, normal with std `drift_ppm`, and both wander (`models.oscillator`)."""

    name: str = "rtl0"  # meta.rx_clock and meta.dongle
    # TBC: the 0.4 ppm dongle of analysis/lte_link_synthetic.py (#121), unsourced for a unit
    drift_ppm: float = 0.4
    # TBC: m/sqrt(s), white frequency noise. The realistic set's 2 ns/sqrt(s) payload clock, as
    # analysis/lte_real_geometry.py (PR #133) uses it; unsourced for a dongle
    offset_rw_m: float = 0.6
    drift_rw_mps: float = 0.05  # TBC, unsourced: m/s/sqrt(s), as lte_real_geometry.py (PR #133)


# Arc restarts of the front end on `main` after the re-acquisition fix (#245; front end at
# `ea72f6a`), on two real static sessions with GPS truth: analysis/results/lte-reacq-steps/
# summary.json, "after". Per session: (new arcs, 10 Hz pseudorange records, re-find steps, their
# median in m, their share over 100 m). Steps are |double-difference change| when one cell of a
# pair starts a new arc.
_REACQ_AFTER = {
    "20261111-0151-static-fullsuite2": (53, 15457, 64, 9.44, 0.15625),
    "20261111-0233-static-lte-1h": (197, 92342, 192, 10.07, 0.171875),
}
_ARC_RATE_HZ = sum(r[0] for r in _REACQ_AFTER.values()) / (
    sum(r[1] for r in _REACQ_AFTER.values()) * 0.1
)  # per second of tracked cell time: 250 arcs in 10,780 s, one per 43 s
# TBC, chosen in #262 (ADR-0049, Proposed): puts the model's step p90 (about 0.4 x this) between
# the two sessions' (462 and 1,033 m)
_ARC_FAR_M = 1500.0
_STEPS_OVER_100M = sum(r[2] * r[4] for r in _REACQ_AFTER.values()) / sum(
    r[2] for r in _REACQ_AFTER.values()
)
# A step over 100 m needs either arc far, 1 - (1 - q)^2, less the far-to-anything steps that
# still land within 100 m (about 100 m / _ARC_FAR_M of them)
_ARC_FAR_SHARE = 1.0 - math.sqrt(1.0 - _STEPS_OVER_100M / (1.0 - 100.0 / _ARC_FAR_M))
# The steps' median is reached by the near-to-near steps, |N(0, sqrt(2) s)|, a share (1 - q)^2
_ARC_NEAR_SIGMA_M = float(np.mean([r[3] for r in _REACQ_AFTER.values()])) / (
    math.sqrt(2.0) * NormalDist().inv_cdf(0.5 + 0.25 / (1.0 - _ARC_FAR_SHARE) ** 2)
)


@dataclass(frozen=True)
class Arcs:
    """Arc restarts of a sector's front end (`arcs:`, #278; #233, #262). Restarts are a Poisson
    process in run time at `rate_hz`, whether the sector is heard or not; each arc, the first
    included, carries one range offset: with probability `far_share` uniform within +-`far_m`
    (the re-search found another path or peak), otherwise normal with `near_sigma_m`. A step is
    the difference of two arcs' offsets. Defaults: the measured rate and step sizes above."""

    rate_hz: float = _ARC_RATE_HZ  # measured: 0.023 per s
    far_share: float = _ARC_FAR_SHARE  # from the measured share of steps over 100 m: 0.094
    far_m: float = _ARC_FAR_M  # TBC (above)
    near_sigma_m: float = _ARC_NEAR_SIGMA_M  # from the measured step median: 8.0 m


def arc_offsets(rng, t_s: np.ndarray, arcs: Arcs) -> tuple[np.ndarray, np.ndarray]:
    """One sector's arc at each of times t_s (0 first) and the range offset (m) of that arc."""
    span = float(t_s[-1]) if len(t_s) else 0.0
    gaps = rng.exponential(1.0 / arcs.rate_hz, int(span * arcs.rate_hz * 3) + 20)
    starts = np.cumsum(gaps)
    starts = starts[starts < span]
    n = len(starts) + 1
    far = rng.random(n) < arcs.far_share
    offset = np.where(
        far, rng.uniform(-arcs.far_m, arcs.far_m, n), rng.normal(0.0, arcs.near_sigma_m, n)
    )
    arc = np.searchsorted(starts, t_s, side="right")
    return arc, offset[arc]


@dataclass(frozen=True)
class LinkBudget:
    """The `link_budget` hearing model. Values as `Budget` in analysis/lte_link_dense.py."""

    path_loss_exponent: float = 3.5  # TBC, unsourced: urban log-distance beyond d0_m
    d0_m: float = 100.0  # TBC: free space to here
    front_to_back_db: float = 25.0  # TBC: floor of the parabolic sector pattern
    noise_figure_db: float = 6.0  # TBC: RTL-SDR (R820T) at 875 MHz
    rx_gain_dbi: float = 0.0  # TBC: receive antenna, cable loss included
    # TBC: added to the filed `tx_power_dbw`, read as EIRP at boresight in dBW. -15 would read it
    # as dBm plus a 15 dBi antenna. Moves every sector alike, so only the noise floor sees it
    tx_offset_db: float = 0.0
    carrier_subcarriers: int = 600  # 10 MHz = 50 resource blocks (3GPP TS 36.101), filled evenly
    # TBC: the front end's near-far floor below the strongest cell, measured on synthetic
    # baseband in PR #133 (analysis/lte_link_dense.py `ladder`)
    floor_db: float = -13.0
    # TBC: in-band SNR over thermal noise to be heard. The front end's search and tracker gates
    # against fully loaded interference (`receiver_floors` in lte_link_dense.py: -13.2 and
    # -12.9 dB at the default Config), taken to hold against noise too. Not measured
    min_snr_db: float = -13.0

    def noise_dbm(self) -> float:
        """Thermal noise plus the noise figure, over the 72 subcarriers the front end uses."""
        return -174.0 + 10 * np.log10(72 * 15e3) + self.noise_figure_db


@dataclass(frozen=True)
class Sector:
    """One registered sector of the cell table."""

    key: str  # its emitter ID, or `<emitter>@<site>` when another eNB uses the same PCI
    earfcn: int
    pci: int
    enb_id: int
    lat: float
    lon: float
    height_agl_m: float
    azimuth_deg: float | None
    beamwidth_deg: float | None  # None: empty in the table, treated as omni
    tx_power_dbw: float | None
    fc_hz: float
    licensee: str

    @property
    def emitter(self) -> str:
        return f"lte:{self.earfcn}:{self.pci}"

    @property
    def site(self) -> str:
        return f"enb:{self.enb_id}"  # as pnt.nav.cells names it

    @property
    def collides(self) -> bool:
        return self.key != self.emitter


def _float(text: str) -> float | None:
    return float(text) if text.strip() else None


@lru_cache(maxsize=8)
def _rows_by_earfcn(path: Path) -> dict[int, list[dict]]:
    """A cell table's rows by EARFCN, in file order: read once, not once per carrier."""
    out: dict[int, list[dict]] = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault(int(r["earfcn"]), []).append(r)
    return out


@lru_cache(maxsize=128)
def sectors(path: Path, earfcn: int) -> tuple[Sector, ...]:
    """Every sector on `earfcn` in a cell table laid out as `lte-cells-ottawa.csv`, sorted by
    (eNB, PCI). A repeated (eNB, PCI) row keeps its first filing. Raises if none match."""
    rows = _rows_by_earfcn(path).get(int(earfcn), [])
    if not rows:
        raise ValueError(f"no sectors on EARFCN {earfcn} in {path}")
    first: dict[tuple[int, int], dict] = {}
    for r in rows:
        first.setdefault((int(r["enb_id"]), int(r["pci"])), r)
    enbs_of_pci: dict[int, set[int]] = {}
    for enb, pci in first:
        enbs_of_pci.setdefault(pci, set()).add(enb)
    out = []
    for (enb, pci), r in sorted(first.items()):
        emitter = f"lte:{int(earfcn)}:{pci}"
        out.append(
            Sector(
                key=emitter if len(enbs_of_pci[pci]) == 1 else f"{emitter}@enb:{enb}",
                earfcn=int(earfcn),
                pci=pci,
                enb_id=enb,
                lat=float(r["lat"]),
                lon=float(r["lon"]),
                height_agl_m=float(r["ant_height_agl_m"]),
                azimuth_deg=_float(r["azimuth_deg"]),
                beamwidth_deg=_float(r["h_beamwidth_deg"]),
                tx_power_dbw=_float(r["tx_power_dbw"]),
                fc_hz=float(r["dl_mhz"]) * 1e6,
                licensee=r["licensee"],
            )
        )
    return tuple(out)


def carriers(cells_from: dict) -> tuple[int, ...]:
    """The EARFCNs a front-end source names (`cells_from.earfcn`: one, or a list to hop)."""
    earfcn = cells_from["earfcn"]
    out = tuple(int(e) for e in earfcn) if isinstance(earfcn, list | tuple) else (int(earfcn),)
    if not out or len(set(out)) != len(out):
        raise ValueError(f"cells_from.earfcn needs distinct carriers, not {earfcn!r}")
    return out


def sectors_of(path: Path, earfcns: tuple[int, ...]) -> tuple[Sector, ...]:
    """Every sector of each carrier in turn (`sectors`), in the order the carriers are listed."""
    return tuple(s for e in earfcns for s in sectors(path, e))


@dataclass(frozen=True)
class Hop:
    """One dongle dwelling on each carrier of `cells_from.earfcn` in turn (#173). No defaults:
    the scenario states both (TBC)."""

    dwell_s: float  # time on one carrier, its dead time included
    reacquire_s: float  # dead time at the start of each dwell: retune, settling, a search


@dataclass(frozen=True)
class Schedule:
    """Record epochs of a hopping dongle (`dwell_schedule`)."""

    ts: np.ndarray  # record epochs (s)
    carrier: np.ndarray  # index into the carrier list dwelled on at each epoch
    n_epochs: int  # the front end's 5 ms epochs per record


def _hop(cfg: dict | None) -> Hop:
    if not isinstance(cfg, dict) or set(cfg) != {"dwell_s", "reacquire_s"}:
        raise ValueError(f"hop needs dwell_s and reacquire_s, not {cfg!r}")
    hop = Hop(float(cfg["dwell_s"]), float(cfg["reacquire_s"]))
    if not 0.0 <= hop.reacquire_s < hop.dwell_s:
        raise ValueError(f"hop needs 0 <= reacquire_s < dwell_s, not {cfg!r}")
    return hop


def dwell_schedule(cfg: dict, duration_s: float, rate_hz: float) -> Schedule | None:
    """Record epochs for a front-end source that hops (module docstring), or None when it hears
    one carrier: then the epochs are the source's own `rate_hz` grid, as without `hop:`."""
    n = len(carriers(cfg["cells_from"]))
    if "hop" not in cfg:
        if n > 1:
            raise ValueError(_NEEDS_HOP)
        return None
    hop = _hop(cfg["hop"])
    if n == 1:
        return None
    ts, on = [], []
    for k in range(int(np.ceil(duration_s / hop.dwell_s))):
        start = k * hop.dwell_s
        end = min(start + hop.dwell_s, duration_s)
        offsets = np.arange(0.0, hop.dwell_s - hop.reacquire_s, 1.0 / rate_hz)
        t = start + hop.reacquire_s + offsets
        t = t[t < end]
        ts.append(t)
        on.append(np.full(len(t), k % n))
    usable = min(1.0 / rate_hz, hop.dwell_s - hop.reacquire_s)
    return Schedule(np.concatenate(ts), np.concatenate(on).astype(int), round(usable / EPOCH_S))


def table_enu(secs, origin_llh) -> np.ndarray:
    """Sector positions (ENU m) as the lookup places them: the origin's height plus the antenna's
    above ground (`pnt.nav.cells.attach`)."""
    return np.array(
        [llh_to_enu([s.lat, s.lon, origin_llh[2] + s.height_agl_m], origin_llh) for s in secs]
    )


def path_loss_db(d_m: np.ndarray, fc_hz: np.ndarray, b: LinkBudget) -> np.ndarray:
    """Free space to `d0_m`, then log-distance with `path_loss_exponent`."""
    d = np.maximum(d_m, 1.0)
    fspl = 20 * np.log10(np.minimum(d, b.d0_m)) + 20 * np.log10(fc_hz) - 147.55
    beyond = 10 * b.path_loss_exponent * np.log10(np.maximum(d / b.d0_m, 1.0))
    return fspl + beyond


def sector_gain_db(secs, sec_enu: np.ndarray, rx_enu: np.ndarray, b: LinkBudget) -> np.ndarray:
    """Horizontal pattern relative to boresight, -min(12 (delta / beamwidth)^2, front-to-back),
    per (epoch, sector). A sector with no beamwidth or azimuth is omni."""
    de = rx_enu[:, None, 0] - sec_enu[None, :, 0]
    dn = rx_enu[:, None, 1] - sec_enu[None, :, 1]
    az = np.array([np.nan if s.azimuth_deg is None else s.azimuth_deg for s in secs])
    bw = np.array([np.nan if s.beamwidth_deg is None else s.beamwidth_deg for s in secs])
    delta = (np.degrees(np.arctan2(de, dn)) - az + 180.0) % 360.0 - 180.0
    gain = -np.minimum(12.0 * (delta / bw) ** 2, b.front_to_back_db)
    return np.where(np.isnan(gain), 0.0, gain)


def rx_power_dbm(secs, sec_enu: np.ndarray, rx_enu: np.ndarray, b: LinkBudget) -> np.ndarray:
    """In-band power (dBm, the 72 subcarriers the front end uses) per (epoch, sector)."""
    if any(s.tx_power_dbw is None for s in secs):
        raise ValueError("link_budget hearing needs tx_power_dbw for every sector")
    tx = np.array([s.tx_power_dbw for s in secs]) + 30.0 + b.tx_offset_db
    fc = np.array([s.fc_hz for s in secs])
    d = np.linalg.norm(rx_enu[:, None, :] - sec_enu[None, :, :], axis=2)
    in_band = 10 * np.log10(72 / b.carrier_subcarriers)
    gain = sector_gain_db(secs, sec_enu, rx_enu, b)
    return tx + in_band + gain - path_loss_db(d, fc[None, :], b) + b.rx_gain_dbi


def heard_by_link_budget(power_dbm: np.ndarray, on_air: np.ndarray, b: LinkBudget) -> np.ndarray:
    """(epoch, sector) heard: on air, above the noise floor by `min_snr_db`, and within
    `floor_db` of the strongest sector that passes those two at that epoch."""
    above = on_air & (power_dbm >= b.noise_dbm() + b.min_snr_db)
    strongest = np.where(above, power_dbm, -np.inf).max(axis=1, keepdims=True)
    return above & (power_dbm >= strongest + b.floor_db)


def heard_by_range(sec_enu: np.ndarray, rx_enu: np.ndarray, hearing_km: float) -> np.ndarray:
    """(epoch, sector) heard: within `hearing_km` of the receiver, horizontally."""
    d = np.linalg.norm(rx_enu[:, None, :2] - sec_enu[None, :, :2], axis=2)
    return d <= hearing_km * 1e3


def one_per_pci(heard: np.ndarray, score: np.ndarray, pcis) -> np.ndarray:
    """`heard` with, per epoch, only the best-scoring heard sector of each PCI kept."""
    out = heard.copy()
    pcis = np.asarray(pcis)
    for pci in np.unique(pcis):
        cols = np.flatnonzero(pcis == pci)
        if len(cols) < 2:
            continue
        s = np.where(heard[:, cols], score[:, cols], -np.inf)
        best = cols[np.argmax(s, axis=1)]
        keep = np.zeros_like(heard[:, cols])
        keep[np.arange(len(heard)), np.searchsorted(cols, best)] = True
        out[:, cols] &= keep
    return out


def _hearing(cfg: dict | None):
    cfg = dict(cfg or {})
    model = cfg.pop("model", None)
    if model == "range":
        if set(cfg) != {"hearing_km"}:
            raise ValueError(f"range hearing takes hearing_km only, not {sorted(cfg)}")
        return float(cfg["hearing_km"])
    if model == "link_budget":
        unknown = set(cfg) - {f.name for f in fields(LinkBudget)}
        if unknown:
            raise ValueError(f"link_budget hearing has no {sorted(unknown)}")
        return LinkBudget(**cfg)
    raise ValueError(f"hearing model must be range or link_budget, not {model!r}")


def _arcs(cfg: dict | None) -> Arcs:
    unknown = set(cfg or {}) - {f.name for f in fields(Arcs)}
    if unknown:
        raise ValueError(f"arcs has no {sorted(unknown)}")
    return Arcs(**{k: float(v) for k, v in (cfg or {}).items()})


def _dongle(cfg: dict | None) -> Dongle:
    unknown = set(cfg or {}) - {f.name for f in fields(Dongle)}
    if unknown:
        raise ValueError(f"dongle has no {sorted(unknown)}")
    return Dongle(**(cfg or {}))


def records(
    cfg: dict,
    *,
    source: str,
    cells_file: Path,
    ts: np.ndarray,
    ts_ns: np.ndarray,
    pos: np.ndarray,
    t_truth: np.ndarray,
    origin_llh,
    seed: int,
    tower_clocks: dict[str, np.ndarray],
    schedule: Schedule | None = None,
) -> tuple[list[Measurement], dict[str, list[float]], dict[str, np.ndarray]]:
    """One dongle's records of the heard sectors at times `ts` (s; `ts_ns` as GPS ns), receiver
    at `pos`. `tower_clocks` holds each sector's clock (m) at `t_truth`, by `Sector.key`. A
    source that hops passes its `dwell_schedule`, whose epochs `ts` must be.

    Returns (records, emitters, rx_clocks): `emitters` maps each emitter ID that one eNB alone
    uses to its true position (ENU m); `rx_clocks` maps the dongle's name to its clock (m) at
    `t_truth`."""
    unknown = set(cfg) - KEYS
    if unknown:
        raise ValueError(
            f"record_shape front_end has no {sorted(unknown)} (known: {sorted(KEYS)})"
        )
    if source != "lte":
        raise ValueError(f"front-end records are LTE: name the source lte, not {source!r}")
    if not tower_clocks:
        raise ValueError("record_shape front_end needs a `tower_clocks:` block")
    earfcns = carriers(cfg["cells_from"])
    secs = sectors_of(cells_file, earfcns)
    if len(earfcns) > 1 and "hop" not in cfg:
        raise ValueError(_NEEDS_HOP)
    if (schedule is not None) != (len(earfcns) > 1):
        raise ValueError("a source that hops needs its dwell_schedule, and only such a source")
    if schedule is not None and not np.array_equal(schedule.ts, ts):
        raise ValueError("ts must be the dwell schedule's epochs")
    hearing = _hearing(cfg.get("hearing"))
    dongle = _dongle(cfg.get("dongle"))
    sigma_m = float(cfg["sigma_m"])
    reported = sigma_m if cfg.get("told_sigma_m") is None else float(cfg["told_sigma_m"])
    n_s, n_t = len(secs), len(ts)
    enbs = sorted({s.enb_id for s in secs})
    of_enb = np.array([enbs.index(s.enb_id) for s in secs])

    told = table_enu(secs, origin_llh)
    rng_pos = np.random.default_rng([seed, _POSITION_STREAM])
    shift = rng_pos.normal(0.0, float(cfg.get("told_position_sigma_m", 0.0)), (len(enbs), 2))
    true_enu = told + np.column_stack([shift[of_enb], np.zeros(n_s)])

    rng_rx = np.random.default_rng([seed, _DONGLE_STREAM])
    rx_truth = models.oscillator(
        rng_rx,
        t_truth,
        offset_m=AMBIGUITY_M / 2,
        drift_mps=dongle.drift_ppm * 1e-6 * models.C_MPS,
        offset_rw_m=dongle.offset_rw_m,
        drift_rw_mps=dongle.drift_rw_mps,
    )
    rx = np.interp(ts, t_truth, rx_truth)
    site_clock = np.array([np.interp(ts, t_truth, tower_clocks[s.key]) for s in secs])

    noise = np.random.default_rng([seed, _NOISE_STREAM]).normal(0.0, sigma_m, (n_s, n_t))
    dt = np.diff(ts, prepend=ts[0])
    multipath = np.zeros((len(enbs), n_t))
    if cfg.get("multipath"):
        mp, rng_mp = cfg["multipath"], np.random.default_rng([seed, _MULTIPATH_STREAM])
        for j in range(len(enbs)):
            multipath[j] = models._gauss_markov(rng_mp, dt, mp["sigma_m"], mp["tau_s"])
    on_air = np.ones((len(enbs), n_t), bool)
    if cfg.get("dropout"):
        rng_do = np.random.default_rng([seed, _DROPOUT_STREAM])
        for j in range(len(enbs)):
            on_air[j] = models._available(rng_do, ts, cfg["dropout"])
    on_air = on_air[of_enb].T  # (epoch, sector)
    if schedule is not None:  # only the dwelled carrier is on air for the dongle
        of_carrier = np.array([earfcns.index(s.earfcn) for s in secs])
        on_air = on_air & (schedule.carrier[:, None] == of_carrier[None, :])
    pcis = [s.earfcn * 1024 + s.pci for s in secs]  # one cell per PCI within each carrier

    distance = np.linalg.norm(pos[None, :, :] - true_enu[:, None, :], axis=2)  # (sector, epoch)
    if isinstance(hearing, LinkBudget):
        power = rx_power_dbm(secs, true_enu, pos, hearing)
        heard = heard_by_link_budget(power, on_air, hearing)
        lin = np.where(on_air, 10 ** (power / 10), 0.0)
        others = lin.sum(axis=1, keepdims=True) - lin + 10 ** (hearing.noise_dbm() / 10)
        snr_db = power - 10 * np.log10(others)  # against noise and every other sector on air
        heard = one_per_pci(heard, power, pcis)
    else:
        heard = heard_by_range(true_enu, pos, hearing) & on_air
        snr_db = None  # no power model
        heard = one_per_pci(heard, -distance.T, pcis)

    clean = distance + site_clock + rx  # what the carrier sees: geometry and clocks
    if cfg.get("troposphere"):  # per eNB: the sectors of one mast share its path
        rng_tropo = np.random.default_rng([seed, _TROPO_STREAM])
        k = models.troposphere(rng_tropo, len(enbs), **cfg["troposphere"])
        clean = clean + k[of_enb, None] * 1e-3 * distance
    rate = np.gradient(clean, ts, axis=1) if n_t > 1 else np.zeros_like(clean)
    measured = clean + noise + multipath[of_enb]
    arc = np.zeros((n_s, n_t), int)
    if cfg.get("arcs") is not None:
        arcs = _arcs(cfg["arcs"])
        rng_arc = np.random.default_rng([seed, _ARC_STREAM])
        arc_m = np.zeros((n_s, n_t))
        for i in range(n_s):
            arc[i], arc_m[i] = arc_offsets(rng_arc, ts, arcs)
        measured = measured + arc_m
    value = np.mod(measured, AMBIGUITY_M)
    n_epochs = round((float(np.median(dt[1:])) if n_t > 1 else 1.0) / EPOCH_S)  # per record
    if schedule is not None:
        n_epochs = schedule.n_epochs

    out: list[Measurement] = []
    # Python ints and floats in one conversion per array, rather than one per record
    t_list = np.asarray(ts_ns).astype(np.int64).tolist()
    for i, s in enumerate(secs):
        ks = np.flatnonzero(heard[:, i])
        cfo = (-s.fc_hz / models.C_MPS * rate[i])[ks].tolist()
        snr = [None] * len(ks) if snr_db is None else snr_db[ks, i].tolist()
        per = zip(ks.tolist(), snr, cfo, arc[i, ks].tolist(), value[i, ks].tolist(), strict=True)
        for k, snr_k, cfo_k, arc_k, value_k in per:
            meta = {
                "snr_db": None if snr_k is None else round(snr_k, 2),
                "cfo_hz": round(cfo_k, 3),
                "dongle": dongle.name,
                "rx_clock": dongle.name,
                "earfcn": s.earfcn,
                "pci": s.pci,
                "fc_hz": s.fc_hz,
                "n_epochs": n_epochs,
                "arc": arc_k,  # 0 unless `arcs:` is on (module docstring)
                "sigma_crb_m": round(reported, 3),
                "sigma_obs_m": None,
                "ambiguity_m": AMBIGUITY_M,
                "flags": [],
            }
            out.append(
                Measurement(
                    t_ns=t_list[k],
                    source=source,
                    kind="pseudorange",
                    emitter=s.emitter,
                    value=(value_k,),
                    sigma=(reported,),
                    meta=meta,
                )
            )
    emitters = {
        s.key: [float(x) for x in true_enu[i]] for i, s in enumerate(secs) if not s.collides
    }
    return out, emitters, {dongle.name: rx_truth}
