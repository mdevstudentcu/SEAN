"""What one real LTE capture says, section by section (#173 part 2, the checklist's questions).

Reads one or more derived LTE sessions (`pnt frontend lte` output, `<session>-lte`): their
`/meas/lte` pseudoranges, and their `/meas/gnss` fixes if the original session's records were
copied in. Prints a markdown report and writes it, with figures, to `--out`.

    python analysis/lte_capture_report.py data/sessions/<s>-lte [--out DIR] [--position lat,lon,h]
    python analysis/lte_capture_report.py data/sessions/<scan>-e*-lte --out <dir>   # a scan
    python analysis/lte_capture_report.py <dir>/<s>-lte --original data/sessions/<s>

Availability is tracked time over the capture length, `samples / sample_rate_hz` from the
original session's sidecar (`<dongle>.json`), found beside `<s>-lte` or given by `--original`
(once per session, in order). Without it, availability is reported as not measurable.

Sections: 1 cells tracked, 2 identity against the cell table, 3 reported against observed σ,
4 dongle clock, 5 tower timing, 6 the `TBC` values each number would replace.

Uses only what the front end already wrote from PSS and SSS (broadcast sync signals, REQ-08):
timing, SNR and carrier offset per cell. Reads no IQ and writes only text and figures.

Trends removed, and why: a cell's pseudorange carries the dongle's clock (one TCXO, offset and
a drift of up to a few ppm, i.e. hundreds of m/s) and the tower's frame timing and drift. A
quadratic per window of `WINDOW_S` removes the offset, drift and drift rate of both inside the
window; what is left is noise, fast multipath, and clock wander faster than the window. One
cell's residual therefore bounds its noise from above; the difference of two cells on one dongle
(section 5) cancels the dongle and leaves the two towers.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np

from pnt.cli import _commit
from pnt.core import frames
from pnt.core.measurement import Measurement
from pnt.frontends.lte.tracker import Config
from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.nav import cells as celltab
from pnt.sim.lte_front_end import Dongle, LinkBudget

C = 299_792_458.0
FRAME_M = C * 0.010  # one 10 ms frame: the pseudorange ambiguity (meta.ambiguity_m)
WINDOW_S = 30.0  # TBC: detrending window. Short enough that dongle wander inside it is small
MIN_PTS = 20  # records in a window before a quadratic is fitted (3 parameters, 17 dof left)
BRACKET_S = 0.15  # pair differences: interpolate only between records at most this far apart
ADEV_MIN_S = 30.0  # TBC: shortest record for an Allan deviation (tau 1 s up to a third of it)
ALIGN_TOL_US = 5.0  # TBC: eNBs "frame-aligned" if their offsets agree within this
NEAR_FAR_DB = LinkBudget().floor_db  # -13 dB, TBC (sim/lte_front_end.py)
# Fixed categorical colours (analysis/figures.py slots 1 and 2, then the repo's others)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#7b4fa0", "#1b9e9e", "#b5442e"]
INK, GRID = "#52514e", "#e4e3df"


@dataclass
class Cell:
    session: str
    rx_clock: str
    emitter: str
    earfcn: int | None
    pci: int
    t: np.ndarray  # s since the session's first LTE record
    value: np.ndarray  # pseudorange, m
    sigma: np.ndarray  # reported σ, m
    arc: np.ndarray
    snr: np.ndarray
    cfo_hz: np.ndarray
    fc_hz: float
    tracked_s: float
    status: str = "not checked"
    cell: celltab.Cell | None = None
    dist_m: float = float("nan")
    bearing_deg: float = float("nan")
    site_name: str = ""

    @property
    def label(self) -> str:
        return self.emitter

    @property
    def enb(self) -> int | None:
        return self.cell.enb_id if self.cell is not None else None


@dataclass
class Session:
    path: Path
    name: str
    commit_fe: str  # the commit that ran the front end (the -lte folder's meta.yaml)
    commit_rec: str  # the commit that recorded the original session
    span_s: float  # first to last LTE record, plus one output period
    cells: list[Cell]
    capture_s: dict[str, float] = field(default_factory=dict)  # per dongle, from its sidecar
    capture_from: str = "TBD (original session not found)"
    simulated: bool = False
    position: tuple[float, float, float] | None = None
    position_from: str = "none"
    extra: dict = field(default_factory=dict)


# --- loading --------------------------------------------------------------------------------


def _original_dir(path: Path, original: str | Path | None) -> Path | None:
    """The original session: `original` if given, else the folder beside `<s>-lte`."""
    if original is not None:
        orig = Path(original)
        if not orig.is_dir():
            raise SystemExit(f"{orig}: no such original session")
        return orig
    if path.name.endswith("-lte"):
        orig = path.with_name(path.name[: -len("-lte")])
        if orig.is_dir():
            return orig
    return None


def _original_commit(orig: Path | None) -> str:
    """The recording's commit, from the original session's meta.yaml."""
    if orig is not None and (orig / session.META_NAME).exists():
        return str(session.read_meta(orig).get("commit") or "TBD")
    return "TBD (original session not found)"


def capture_lengths(orig: Path | None) -> dict[str, float]:
    """Capture length (s) per dongle: `samples / sample_rate_hz` from each IQ sidecar.
    A sidecar without `samples` falls back to the `.cu8` size (two bytes per sample)."""
    out: dict[str, float] = {}
    for js in sorted(orig.glob("*.json")) if orig is not None else []:
        try:
            meta = json.loads(js.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or not meta.get("sample_rate_hz"):
            continue
        n = meta.get("samples")
        if n is None and js.with_suffix(".cu8").exists():
            n = js.with_suffix(".cu8").stat().st_size // 2
        if n:
            out[str(meta.get("dongle") or js.stem)] = int(n) / float(meta["sample_rate_hz"])
    return out


def load(
    path: str | Path,
    position: tuple[float, float, float] | None,
    original: str | Path | None = None,
) -> Session:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"{path}: no such session (pass the `<session>-lte` folder)")
    meta = session.read_meta(path)
    series: dict[tuple[str, str], list[Measurement]] = defaultdict(list)
    fixes: list[Measurement] = []
    for topic, m in read_session(session.mcap_path(path), topics=["/meas/lte", "/meas/gnss"]):
        if not isinstance(m, Measurement):
            continue
        if topic == "/meas/lte" and m.kind == "pseudorange":
            series[(m.meta.get("rx_clock", ""), m.emitter)].append(m)
        elif topic == "/meas/gnss" and m.kind == "position_enu":
            fixes.append(m)
    if not series:
        raise SystemExit(f"{path}: no /meas/lte pseudoranges (run `pnt frontend lte` first)")
    t0 = min(ms[0].t_ns for ms in series.values())
    t1 = max(ms[-1].t_ns for ms in series.values())
    out = []

    def order(item):  # by dongle, EARFCN, PCI (numerically), not by the emitter string
        (clock, _), ms = item
        return clock, ms[0].meta.get("earfcn") or 0, ms[0].meta.get("pci", -1)

    for (clock, emitter), ms in sorted(series.items(), key=order):
        ms.sort(key=lambda m: m.t_ns)
        md = ms[0].meta
        out.append(
            Cell(
                session=session.session_name(path),
                rx_clock=clock,
                emitter=emitter,
                earfcn=md.get("earfcn"),
                pci=int(md.get("pci", -1)),
                t=np.array([m.t_ns - t0 for m in ms], dtype=np.float64) / 1e9,
                value=np.array([m.value[0] for m in ms]),
                sigma=np.array([m.sigma[0] for m in ms]),
                arc=np.array([m.meta.get("arc", 0) for m in ms]),
                snr=np.array([m.meta["snr_db"] for m in ms]),
                cfo_hz=np.array([m.meta["cfo_hz"] for m in ms]),
                fc_hz=float(md["fc_hz"]),
                tracked_s=sum(m.meta.get("n_epochs", 20) for m in ms) * 0.005,
            )
        )
    orig = _original_dir(path, original)
    capture = capture_lengths(orig)
    s = Session(
        path=path,
        name=session.session_name(path),
        commit_fe=str(meta.get("commit") or "TBD"),
        commit_rec=_original_commit(orig),
        span_s=(t1 - t0) / 1e9 + Config().output_period_s,
        cells=out,
        simulated=bool(meta.get("simulated", False)),
        capture_s=capture,
        capture_from="TBD (original session not found)"
        if orig is None
        else "TBD (no IQ sidecar in the original session)",
    )
    origin = meta.get("origin_llh")
    if position is not None:
        s.position, s.position_from = position, "--position"
    elif fixes and origin is not None:
        enu = np.mean([m.value for m in fixes], axis=0)
        s.position = tuple(float(x) for x in frames.enu_to_llh(enu, origin))
        s.position_from = f"mean of {len(fixes)} GNSS fixes"
    elif origin is not None:
        s.position = tuple(float(x) for x in origin)
        s.position_from = "session origin (first 3D fix; accuracy TBD)"
    return s


# --- numbers --------------------------------------------------------------------------------


def detrend(t: np.ndarray, v: np.ndarray, window: float = WINDOW_S):
    """Residuals of a quadratic fitted per window (windows with < MIN_PTS records skipped), and
    the residuals' 1 s means. Returns (t, resid, means_1s)."""
    ts, rs, ms = [], [], []
    if t.size == 0:
        return np.array([]), np.array([]), np.array([])
    k = np.floor((t - t[0]) / window).astype(int)
    for w in np.unique(k):
        sel = k == w
        if sel.sum() < MIN_PTS:
            continue
        tw, vw = t[sel], v[sel]
        x = tw - tw.mean()
        r = vw - np.polyval(np.polyfit(x, vw, 2), x)
        ts.append(tw)
        rs.append(r)
        sec = np.floor(tw - tw[0]).astype(int)
        for b in np.unique(sec):
            if (sec == b).sum() >= 5:
                ms.append(r[sec == b].mean())
    if not rs:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(ts), np.concatenate(rs), np.array(ms)


def wrap(x, around: float = 0.0):
    """Values moved by whole frames to within half a frame of `around`."""
    return around + (np.asarray(x) - around + FRAME_M / 2) % FRAME_M - FRAME_M / 2


def pair_difference(a: Cell, b: Cell) -> tuple[np.ndarray, np.ndarray]:
    """b - a at b's times, `a` interpolated between records at most BRACKET_S apart, wrapped
    to one frame (both cells' values are known modulo a frame; the dongle cancels)."""
    if a.t.size < 2 or b.t.size == 0:
        return np.array([]), np.array([])
    j = np.searchsorted(a.t, b.t)
    ok = (j > 0) & (j < a.t.size)
    ok[ok] &= (a.t[j[ok]] - a.t[j[ok] - 1]) <= BRACKET_S
    if not ok.any():
        return np.array([]), np.array([])
    t = b.t[ok]
    # a's value continued across its frame wraps before interpolating
    va = a.value[0] + np.cumsum(np.r_[0, wrap(np.diff(a.value))])
    d = wrap(b.value[ok] - np.interp(t, a.t, va), b.value[ok][0] - np.interp(t[0], a.t, va))
    d = d[0] + np.cumsum(np.r_[0, wrap(np.diff(d))])  # continuous
    return t, d


def oadev(y: np.ndarray, tau0: float, taus: list[float]) -> list[tuple[float, float]]:
    """Overlapping Allan deviation of fractional frequency samples `y` (spacing `tau0`)."""
    out = []
    cs = np.r_[0.0, np.cumsum(y)]
    for tau in taus:
        m = int(round(tau / tau0))
        if m < 1 or y.size < 3 * m:
            continue
        avg = (cs[m:] - cs[:-m]) / m
        d = avg[m:] - avg[:-m]
        out.append((m * tau0, float(np.sqrt(0.5 * np.mean(d**2)))))
    return out


def identify(s: Session, table: celltab.CellTable, names: dict) -> None:
    for c in s.cells:
        if c.earfcn is None:
            c.status = "unknown (no EARFCN in the record)"
            continue
        if s.position is None:
            c.status = "not measurable: no position (no GNSS fixes, no origin, no --position)"
            continue
        c.status, c.cell = table.associate(c.earfcn, c.pci, s.position)
        if c.cell is not None:
            e, n, _ = frames.llh_to_enu([c.cell.lat, c.cell.lon, s.position[2]], s.position)
            c.dist_m = float(math.hypot(e, n))
            c.bearing_deg = float(math.degrees(math.atan2(e, n)) % 360)
            c.site_name = names.get((c.earfcn, c.pci, c.cell.enb_id), "")


def _site_names(path: Path = celltab.CELL_TABLE) -> dict:
    import csv

    with open(path, newline="") as f:
        return {
            (int(r["earfcn"]), int(r["pci"]), int(r["enb_id"])): r["location"]
            for r in csv.DictReader(f)
        }


def geometric_range(c: Cell, pos) -> float:
    """3D range from `pos` to the cell's antenna (height: pos height + antenna AGL, as
    pnt.nav.cells: the table has no ground elevation, flat ground TBC)."""
    llh = [c.cell.lat, c.cell.lon, pos[2] + c.cell.height_agl_m]
    return float(np.linalg.norm(frames.llh_to_enu(llh, pos)))


def analyse(sessions: list[Session]) -> dict:
    res: dict = {"cells": [], "sigma": [], "clock": [], "pairs": [], "frames": []}
    for s in sessions:
        groups: dict[tuple, list[Cell]] = defaultdict(list)
        for c in s.cells:
            groups[(c.rx_clock, c.earfcn)].append(c)
        # 1. cells tracked
        for (_clock, _earfcn), cs in groups.items():
            top = max(float(np.median(c.snr)) for c in cs)
            for c in cs:
                snr = float(np.median(c.snr))
                res["cells"].append(
                    {
                        "session": s.name,
                        "cell": c,
                        "snr_db": snr,
                        "level_db": snr - top,
                        "arcs": int(np.unique(c.arc).size),
                        "tracked_s": c.tracked_s,
                        "avail": (
                            min(c.tracked_s / s.capture_s[c.rx_clock], 1.0)
                            if c.rx_clock in s.capture_s
                            else None
                        ),
                        "cfo_hz": float(np.median(c.cfo_hz)),
                        "cfo_ppm": float(np.median(c.cfo_hz)) / c.fc_hz * 1e6,
                        "n_carrier": len(cs),
                    }
                )
        # 3. reported against observed σ, one cell at a time
        for c in s.cells:
            row = {"session": s.name, "cell": c, "reported": float(np.median(c.sigma))}
            parts = [detrend(c.t[c.arc == a], c.value[c.arc == a]) for a in np.unique(c.arc)]
            r = np.concatenate([p[1] for p in parts])
            m1 = np.concatenate([p[2] for p in parts])
            if r.size >= MIN_PTS:
                row.update(obs_10hz=float(np.std(r, ddof=1)), n=int(r.size))
                row["obs_1s"] = float(np.std(m1, ddof=1)) if m1.size >= 3 else float("nan")
            res["sigma"].append(row)
        # 4. dongle clock: frequency error from the CFO, eps = -CFO / fc (dongle fast: eps > 0)
        for clock in sorted({c.rx_clock for c in s.cells}):
            cs = [c for c in s.cells if c.rx_clock == clock]
            dt = Config().output_period_s
            bins: dict[int, list[float]] = defaultdict(list)
            for c in cs:
                for t, f in zip(c.t, c.cfo_hz, strict=True):
                    bins[int(round(t / dt))].append(-f / c.fc_hz)
            k = np.array(sorted(bins))
            y = np.array([np.median(bins[i]) for i in k])
            t = k * dt
            row = {
                "session": s.name,
                "rx_clock": clock,
                "t": t,
                "y": y,
                "n_cells": len(cs),
                "median_ppm": float(np.median(y)) * 1e6,
                "span_s": float(t[-1] - t[0]),
            }
            if t.size >= 4:
                (slope, _), cov = np.polyfit(t, y, 1, cov=True)
                row["slope_ppb_per_h"] = float(slope) * 1e9 * 3600
                row["slope_se_ppb_per_h"] = float(np.sqrt(cov[0, 0])) * 1e9 * 3600
            if row["span_s"] >= ADEV_MIN_S:
                full = np.arange(k[0], k[-1] + 1)
                yf = np.interp(full, k, y)  # missing 10 Hz bins filled linearly (TBC)
                taus = [2.0**i for i in range(0, 20) if 2.0**i <= row["span_s"] / 3]
                row["adev"] = oadev(yf, dt, taus)
                row["filled"] = int(full.size - k.size)
            res["clock"].append(row)
        # 5. tower timing: pairs on one dongle and one carrier
        for (_clock, _earfcn), cs in groups.items():
            cs = sorted(cs, key=lambda c: -float(np.median(c.snr)))
            for a, b in combinations(cs, 2):
                t, d = pair_difference(a, b)
                row = {"session": s.name, "a": a, "b": b, "t": t, "d": d}
                if t.size >= MIN_PTS:
                    slope = float(np.polyfit(t, d, 1)[0])
                    _, r, m1 = detrend(t, d)
                    row.update(
                        drift_mps=slope,
                        drift_ppb=slope / C * 1e9,
                        spread_m=float(np.std(r, ddof=1)) if r.size else float("nan"),
                        spread_1s_m=float(np.std(m1, ddof=1)) if m1.size >= 3 else float("nan"),
                        span_s=float(t[-1] - t[0]),
                    )
                if a.enb is not None and b.enb is not None:
                    row["same_enb"] = a.enb == b.enb
                res["pairs"].append(row)
            # frame timing per eNB, relative to the strongest matched cell (needs a position)
            matched = [c for c in cs if c.cell is not None]
            if s.position is None or len(matched) < 2:
                continue
            ref = matched[0]
            r_ref = geometric_range(ref, s.position)
            for c in matched:
                if c is ref:
                    off = 0.0
                else:
                    t, d = pair_difference(ref, c)
                    if t.size == 0:
                        continue
                    off = float(wrap(np.median(d) - (geometric_range(c, s.position) - r_ref)))
                res["frames"].append(
                    {"session": s.name, "ref": ref, "cell": c, "offset_us": off / C * 1e6}
                )
    return res


# --- report ---------------------------------------------------------------------------------


def _f(x, fmt=".2f", unit="") -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:{fmt}}{unit}"


NOT = "not measurable from this session"


def report(sessions: list[Session], res: dict, commit: str) -> str:
    L: list[str] = []
    add = L.append
    names = ", ".join(s.name for s in sessions)
    add(f"# LTE capture report: {names}")
    add("")
    add(
        f"Analysed by `analysis/lte_capture_report.py` at commit `{commit}`. Every number below "
        "names its session; recording and front-end commits per session:"
    )
    add("")
    add(
        "| Session | Evidence | Recorded at | Front end at | Record span (s) | Capture (s) | "
        "Position used |"
    )
    add("|---|---|---|---|---|---|---|")
    for s in sessions:
        pos = (
            f"{s.position[0]:.6f}, {s.position[1]:.6f}, {s.position[2]:.1f} ({s.position_from})"
            if s.position
            else "none"
        )
        kind = "simulated" if s.simulated else "real session"
        cap = ", ".join(f"{d} {v:.2f}" for d, v in s.capture_s.items()) or s.capture_from
        add(
            f"| {s.name} | {kind} | `{s.commit_rec}` | `{s.commit_fe}` | {s.span_s:.1f} | {cap} | "
            f"{pos} |"
        )
    add("")
    add(
        "Record span: first to last LTE record. Capture: `samples / sample_rate_hz` from the "
        "original session's IQ sidecar, per dongle. Evidence: from each session's meta.yaml "
        "`simulated`. "
        "All tolerances marked `TBC` are proposals, not requirements."
    )

    # 1
    add("")
    add("## 1. Cells tracked (question 1)")
    add("")
    add(
        "| Session | Cell | Tracked (s) | Of capture | Arcs | SNR (dB) | Re strongest (dB) | "
        "CFO (Hz) | CFO (ppm) |"
    )
    add("|---|---|---|---|---|---|---|---|---|")
    for r in res["cells"]:
        flag = " (beyond the floor)" if r["level_db"] < NEAR_FAR_DB else ""
        avail = "not measurable (no capture length)" if r["avail"] is None else f"{r['avail']:.0%}"
        add(
            f"| {r['session']} | {r['cell'].label} | {r['tracked_s']:.1f} | {avail} | "
            f"{r['arcs']} | {r['snr_db']:.1f} | {r['level_db']:.1f}{flag} | "
            f"{r['cfo_hz']:.1f} | {r['cfo_ppm']:+.3f} |"
        )
    add("")
    per = defaultdict(int)
    for r in res["cells"]:
        per[(r["session"], r["cell"].earfcn)] += 1
    add("Per carrier: " + "; ".join(f"{s} EARFCN {e}: {n} cell(s)" for (s, e), n in per.items()))
    weakest = min((r["level_db"] for r in res["cells"]), default=float("nan"))
    add(
        f"Weakest tracked cell: {weakest:.1f} dB below the strongest on its carrier; the sim's "
        f"near-far floor is {NEAR_FAR_DB:.0f} dB (`TBC`). Cells below the floor are not tracked, "
        "so the floor itself is not measured: a cell tracked beyond it means the floor is "
        "pessimistic. The level is a difference of the front end's post-correlation SNR "
        "estimates (interference included), not a power measurement: in the synthetic test a "
        "cell sent 4 dB below the strongest read 9.6 dB below, so treat levels as approximate "
        "(`TBC`)."
    )

    # 2
    add("")
    add("## 2. Identity against the cell table (question 5)")
    add("")
    add(
        f"`CellTable.associate` (`src/pnt/nav/cells.py`, {celltab.MAX_RANGE_KM:g} km range, `TBC`)"
        " at each session's position above."
    )
    add("")
    add("| Session | Cell | Status | eNB | Site | Distance (km) | Bearing (°) |")
    add("|---|---|---|---|---|---|---|")
    for s in sessions:
        for c in s.cells:
            add(
                f"| {s.name} | {c.label} | {c.status} | {c.enb or '—'} | {c.site_name or '—'} | "
                f"{_f(c.dist_m / 1e3, '.2f')} | {_f(c.bearing_deg, '.0f')} |"
            )

    # 3
    add("")
    add("## 3. Reported against observed σ (questions 2 and 6)")
    add("")
    add(
        f"Per cell: the front end's reported σ (median) against the spread of its pseudorange "
        f"after a quadratic per {WINDOW_S:.0f} s window (`TBC`; removes the dongle's and the "
        "tower's clock offset, drift and drift rate). One cell's spread includes dongle wander "
        "faster than the window, so it bounds the noise from above; section 5 cancels the dongle. "
        "Precision only: no bias against truth."
    )
    add("")
    add(
        "| Session | Cell | n | Reported σ (m) | Observed σ 10 Hz (m) | Ratio "
        "| Observed σ 1 s (m) |"
    )
    add("|---|---|---|---|---|---|---|")
    for r in res["sigma"]:
        if "obs_10hz" not in r:
            add(
                f"| {r['session']} | {r['cell'].label} | {r['cell'].t.size} | "
                f"{r['reported']:.2f} | {NOT}: fewer than {MIN_PTS} records in any "
                f"{WINDOW_S:.0f} s window | | |"
            )
            continue
        add(
            f"| {r['session']} | {r['cell'].label} | {r['n']} | {r['reported']:.2f} | "
            f"{r['obs_10hz']:.2f} | {r['obs_10hz'] / r['reported']:.2f} | "
            f"{_f(r['obs_1s'])} |"
        )
    add("")
    add(
        "Ratio = observed / reported at 10 Hz. The observed spread includes the correlated "
        "part (dongle and tower wander, multipath change, the tracker's loop), so a ratio "
        "above 1 does not by itself mean `Config.sigma_scale` is too low: split the white part "
        "from the correlated part first (`analysis/lte_single_cell.py`; #190 / ADR-0036, "
        "Proposed, finds the white part below the reported σ on the 2026-11-10 captures). "
        "The 1 s value is the spread of 1 s means inside each window (the window's quadratic "
        "absorbs some of it at long correlation times)."
    )

    # 4
    add("")
    add("## 4. Dongle clock (question 3)")
    add("")
    add(
        "Frequency error ε = −CFO / f_c, median across the cells at each 10 Hz epoch (ε > 0: the "
        "dongle runs fast). It mixes the dongle's error with each tower's carrier error "
        "(±0.05 ppm allowed for a wide-area eNB, 3GPP TS 36.104). The CFO comes from the "
        "tracker's loop, so short-τ values show the loop as well as the dongle."
    )
    add("")
    add(
        "| Session | rx_clock | Cells | Median ε (ppm) | Drift ± 1σ (ppb/h) | Span (s) | "
        "Allan deviation |"
    )
    add("|---|---|---|---|---|---|---|")
    for r in res["clock"]:
        if "adev" in r:
            ad = ", ".join(f"σ_y({tau:g} s) = {a:.2e}" for tau, a in r["adev"]) or "—"
        else:
            ad = f"{NOT}: {r['span_s']:.0f} s of record, needs ≥ {ADEV_MIN_S:.0f} s (`TBC`)"
        drift = (
            f"{r['slope_ppb_per_h']:+.1f} ± {r['slope_se_ppb_per_h']:.1f}"
            if "slope_ppb_per_h" in r
            else "—"
        )
        add(
            f"| {r['session']} | {r['rx_clock']} | {r['n_cells']} | {r['median_ppm']:+.3f} | "
            f"{drift} | {r['span_s']:.0f} | {ad} |"
        )
    add("")
    add(
        f"Outside ±{Config().max_ppm:g} ppm (`Config.max_ppm`) the search would not have found "
        "the cells: record again with `ppm=`. The drift is a straight line through ε over the "
        "record; over a short record its 1σ is large, and only the Allan deviation separates "
        "drift from wander."
    )

    # 5
    add("")
    add("## 5. Tower timing (question 4)")
    add("")
    add(
        "For every pair of cells on one dongle and one carrier, b − a of their pseudoranges: the "
        "dongle cancels, leaving the two towers' timing (and the range difference, constant for a "
        "receiver that does not move). Drift and spread need **no position**. Frame offsets "
        "between eNBs need **a position** and the table's tower positions."
    )
    add("")
    singles = [
        s.name
        for s in sessions
        if all(
            len([c for c in s.cells if (c.rx_clock, c.earfcn) == (x.rx_clock, x.earfcn)]) < 2
            for x in s.cells
        )
    ]
    if singles:
        add(f"{', '.join(singles)}: {NOT}: one cell per carrier, no pair to difference.")
        add("")
    if res["pairs"]:
        add(
            "| Session | a | b | Same eNB | Drift (m/s) | Drift (ppb) | Spread 10 Hz (m) | "
            "Spread 1 s (m) | Span (s) |"
        )
        add("|---|---|---|---|---|---|---|---|---|")
        for r in res["pairs"]:
            same = {True: "yes", False: "no"}.get(r.get("same_enb"), "unknown (unmatched)")
            if "drift_mps" not in r:
                add(
                    f"| {r['session']} | {r['a'].label} | {r['b'].label} | {same} | {NOT}: "
                    f"fewer than {MIN_PTS} common epochs | | | | |"
                )
                continue
            add(
                f"| {r['session']} | {r['a'].label} | {r['b'].label} | {same} | "
                f"{r['drift_mps']:+.3f} | {r['drift_ppb']:+.2f} | {_f(r['spread_m'])} | "
                f"{_f(r['spread_1s_m'])} | {r['span_s']:.0f} |"
            )
        add("")
        add(
            f"Spread: after a quadratic per {WINDOW_S:.0f} s window. Same-eNB pairs should be "
            "flat (drift near 0) if a site's sectors share one clock (ADR-0022)."
        )
    add("")
    if res["frames"]:
        add(
            f"Frame timing offset modulo 10 ms, relative to the strongest matched cell, after "
            f"removing the geometric range difference; aligned if within ±{ALIGN_TOL_US:g} µs "
            "(`TBC`; a table position 100 m off moves it by 0.3 µs)."
        )
        add("")
        add("| Session | Reference | Cell | eNB | Offset (µs) | Aligned |")
        add("|---|---|---|---|---|---|")
        for r in res["frames"]:
            ok = "yes" if abs(r["offset_us"]) <= ALIGN_TOL_US else "no"
            add(
                f"| {r['session']} | {r['ref'].label} | {r['cell'].label} | {r['cell'].enb} | "
                f"{r['offset_us']:+.3f} | {ok} |"
            )
        enbs = summarise_enbs(res["frames"])
        add("")
        add(
            "Per eNB (median of its sectors): "
            + "; ".join(f"{s} eNB {e}: {o:+.3f} µs" for (s, e), o in enbs.items())
        )
    else:
        add(
            f"Frame offsets between eNBs: {NOT}: needs a position and at least two cells on one "
            "carrier matched to the table."
        )

    # 6
    add("")
    add("## 6. What this would replace")
    add("")
    add(
        "Mapping from `deploy/pi/first-capture.md`. A measured value lands in a PR naming the "
        "session and commit (ADR-0015); this table changes no file. *From* names the session "
        "that gave the number; its commits are in the table at the top. The dongle clock rows "
        "(Allan deviation of the tracker's loop-filtered CFO, tower carrier error mixed in) are "
        "indicative only and must not replace the sim's `TBC` values."
    )
    add("")
    add("| Quantity | Measured | From | `TBC` now | Where |")
    add("|---|---|---|---|---|")
    for row in replacements(sessions, res):
        add("| " + " | ".join(row) + " |")
    return "\n".join(L) + "\n"


def summarise_enbs(frames_rows: list[dict]) -> dict:
    by: dict[tuple, list[float]] = defaultdict(list)
    for r in frames_rows:
        by[(r["session"], r["cell"].enb)].append(r["offset_us"])
    return {k: float(np.median(v)) for k, v in by.items()}


def replacements(sessions: list[Session], res: dict) -> list[list[str]]:
    """Rows: quantity, measured, the session(s) it comes from, the `TBC` now, where."""
    every = sessions[0].name if len(sessions) == 1 else f"all {len(sessions)} sessions"
    cells, sig, clk, pairs = res["cells"], res["sigma"], res["clock"], res["pairs"]
    got = [r for r in sig if "obs_10hz" in r]
    sim, yml = "`src/pnt/sim/lte_front_end.py`", "`src/pnt/sim/scenarios/sets/realistic.yaml`"
    rows = []
    if cells:
        w = min(cells, key=lambda r: r["level_db"])
        rows.append(
            [
                "Near-far floor below the strongest",
                f"weakest tracked {w['level_db']:.1f} dB (a bound: the floor is at or below it)",
                w["session"],
                f"`LinkBudget.floor_db` {NEAR_FAR_DB:g} dB",
                sim,
            ]
        )
        lo = min(cells, key=lambda r: r["snr_db"])
        rows.append(
            [
                "Lowest SNR tracked",
                f"{lo['snr_db']:.1f} dB (a bound)",
                lo["session"],
                f"`LinkBudget.min_snr_db` {LinkBudget().min_snr_db:g} dB",
                sim,
            ]
        )
    far = [(c.dist_m, c.session) for s in sessions for c in s.cells if c.cell is not None]
    rows.append(
        [
            "Farthest matched cell",
            f"{max(far)[0] / 1e3:.2f} km (a bound)" if far else f"{NOT}: no matched cell",
            max(far)[1] if far else every,
            f"`MAX_RANGE_KM` {celltab.MAX_RANGE_KM:g} km",
            "`src/pnt/nav/cells.py`",
        ]
    )
    tracker = "`src/pnt/frontends/lte/tracker.py`"
    if got:
        ratio = float(np.median([r["obs_10hz"] / r["reported"] for r in got]))
        rows.append(
            [
                "Observed / reported σ, median over cells",
                f"{ratio:.2f} (one cell's observed σ is an upper bound)",
                every,
                f"`Config.sigma_scale` {Config().sigma_scale:g}",
                tracker,
            ]
        )
        rows.append(
            [
                "Reported σ, median over cells",
                f"{np.median([r['reported'] for r in got]):.2f} m",
                every,
                "sim `told_sigma_m` (#147)",
                sim,
            ]
        )
        o10 = float(np.median([r["obs_10hz"] for r in got]))
        o1 = float(np.nanmedian([r["obs_1s"] for r in got]))
        rows.append(
            [
                "Pseudorange spread at 10 Hz / 1 s, median over cells",
                f"{o10:.2f} m / {_f(o1)} m (precision only)",
                every,
                "`lte.sigma_m` 50 m (at 1 Hz)",
                yml,
            ]
        )
    else:
        rows.append(
            [
                "Observed / reported σ",
                f"{NOT}: too few records",
                every,
                f"`Config.sigma_scale` {Config().sigma_scale:g}",
                tracker,
            ]
        )
    rows.append(
        [
            "Multipath size and correlation time",
            f"{NOT}: needs bias against a known position over ≥ 1 h (Gap 1)",
            every,
            "`multipath` 50 m / 30 s",
            yml,
        ]
    )
    if cells:
        known = [r for r in cells if r["avail"] is not None]
        if known:
            av = min(known, key=lambda r: r["avail"])
            got_avail = (
                f"median {np.median([r['avail'] for r in known]):.0%}, lowest "
                f"{av['avail']:.0%} ({av['cell'].label}, {av['session']})"
            )
            if len(known) < len(cells):
                got_avail += f"; {len(cells) - len(known)} cell(s) without a capture length"
        else:
            got_avail = f"{NOT}: no capture length (original session's sidecar not found)"
        rows.append(
            [
                "Fraction of the capture each cell was tracked",
                got_avail,
                every,
                "`dropout.availability` 0.75",
                yml,
            ]
        )
    if clk:
        e = max(clk, key=lambda r: abs(r["median_ppm"]))
        rows.append(
            [
                "Dongle frequency error, largest magnitude",
                f"{e['median_ppm']:+.3f} ppm (tower carrier error mixed in)",
                e["session"],
                f"`Dongle.drift_ppm` {Dongle().drift_ppm:g}",
                sim,
            ]
        )
        ad = [r for r in clk if r.get("adev")]
        if ad:
            r = max(ad, key=lambda r: r["span_s"])
            tau1, a1 = r["adev"][0]
            taun, an = r["adev"][-1]
            rows.append(
                [
                    "Dongle white FM: c·σ_y(τ)·√τ at the shortest τ",
                    f"{C * a1 * math.sqrt(tau1):.2f} m/√s at τ = {tau1:g} s (indicative: not a "
                    "replacement)",
                    r["session"],
                    f"`Dongle.offset_rw_m` {Dongle().offset_rw_m:g}",
                    sim,
                ]
            )
            rows.append(
                [
                    "Dongle random-walk FM: c·σ_y(τ)·√(3/τ) at the longest τ",
                    f"{C * an * math.sqrt(3 / taun):.3f} m/s/√s at τ = {taun:g} s "
                    "(indicative: not a replacement)",
                    r["session"],
                    f"`Dongle.drift_rw_mps` {Dongle().drift_rw_mps:g}",
                    sim,
                ]
            )
        else:
            rows.append(
                [
                    "Dongle wander (Allan deviation)",
                    f"{NOT}: shorter than {ADEV_MIN_S:.0f} s",
                    every,
                    f"`Dongle.offset_rw_m` {Dongle().offset_rw_m:g}, `drift_rw_mps` "
                    f"{Dongle().drift_rw_mps:g}",
                    sim,
                ]
            )
    diff = [r for r in pairs if "drift_mps" in r and r.get("same_enb") is False]
    same = [r for r in pairs if "drift_mps" in r and r.get("same_enb") is True]
    clocks = "`tower_clocks` builder and site `drift_mps` 0.0354 each"
    if diff:
        d = np.array([r["drift_mps"] for r in diff])
        rows.append(
            [
                "Tower drift per tower: rms of different-eNB pair drifts / √2",
                f"{float(np.sqrt(np.mean(d**2) / 2)):.3f} m/s from {len(diff)} pair(s) "
                "(pairs sharing a cell are not independent)",
                every,
                clocks,
                f"{yml}, `worst.yaml`",
            ]
        )
    else:
        rows.append(
            [
                "Tower drift",
                f"{NOT}: no matched pair on different eNBs",
                every,
                clocks,
                f"{yml}, `worst.yaml`",
            ]
        )
    row22 = 'ADR-0022 grouping; *Sim validity* row "LTE tower clocks, shared"'
    if same:
        m = max(same, key=lambda r: abs(r["drift_mps"]))
        rows.append(
            [
                "Sectors of one eNB share a clock",
                f"largest same-eNB drift {m['drift_mps']:+.3f} m/s "
                f"({m['b'].label} − {m['a'].label}), largest spread "
                f"{max(r['spread_m'] for r in same):.2f} m",
                every,
                row22,
                "`systems/verification.md`",
            ]
        )
    else:
        rows.append(
            [
                "Sectors of one eNB share a clock",
                f"{NOT}: no same-eNB pair",
                every,
                row22,
                "`systems/verification.md`",
            ]
        )
    far_spot = "#133 far-spot count (4.7 cells if not aligned, 1.0 if aligned)"
    if res["frames"]:
        offs = [abs(o) for o in summarise_enbs(res["frames"]).values()]
        n_al = sum(o <= ALIGN_TOL_US for o in offs)
        rows.append(
            [
                "eNBs frame-aligned",
                f"{n_al} of {len(offs)} eNBs within ±{ALIGN_TOL_US:g} µs of the reference (`TBC`)",
                every,
                far_spot,
                "`analysis/lte_link_dense.py`",
            ]
        )
    else:
        rows.append(
            [
                "eNBs frame-aligned",
                f"{NOT}: needs a position and two matched cells",
                every,
                far_spot,
                "`analysis/lte_link_dense.py`",
            ]
        )
    st = [c.status for s in sessions for c in s.cells]
    rows.append(
        [
            "(EARFCN, PCI) against the table",
            ", ".join(f"{k} {st.count(k)}" for k in sorted(set(st))),
            every,
            "EARFCN mapping `TBC`",
            "`data/reference/README.md`",
        ]
    )
    return rows


# --- figures --------------------------------------------------------------------------------


def figures(sessions: list[Session], res: dict, out: Path, commit: str) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    title = ", ".join(s.name for s in sessions)
    if len(title) > 70:
        title = f"{sessions[0].name} and {len(sessions) - 1} more"
    written = []

    def finish(fig, ax, name, what):
        ax.grid(True, color=GRID, lw=0.6)
        fig.suptitle(f"{what}\n{title}, analysed at {commit}", fontsize=9, x=0.01, ha="left")
        fig.tight_layout()
        p = out / name
        fig.savefig(p)
        plt.close(fig)
        written.append(p)

    rows = res["cells"]
    order = {s.name: i + 1 for i, s in enumerate(sessions)}
    many = len(sessions) > 1
    fig, ax = plt.subplots(figsize=(7, 0.3 * len(rows) + 1.8), dpi=130)
    y = np.arange(len(rows))
    lv = [r["level_db"] for r in rows]
    ax.hlines(y, lv, 0, color=PALETTE[0], lw=1.5)
    ax.plot(lv, y, "o", color=PALETTE[0], ms=5, label="tracked cell")
    ax.axvline(NEAR_FAR_DB, color=INK, ls=":", lw=1, label=f"sim floor {NEAR_FAR_DB:g} dB (TBC)")
    labels = [r["cell"].label + (f" [{order[r['session']]}]" if many else "") for r in rows]
    ax.set_yticks(y, labels, fontsize=7)
    ax.set_xlabel("level relative to the strongest cell on its carrier (dB)")
    ax.set_xlim(min(NEAR_FAR_DB, *lv) - 2, 1)
    ax.legend(fontsize=7, loc="lower left")
    what = "Cells tracked: level below the strongest (SNR difference)"
    if many:
        what += "; [n] = n-th session in report.md"
    finish(fig, ax, "cells.png", what)

    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=130)
    for i, r in enumerate(res["clock"]):
        ax.plot(
            r["t"],
            r["y"] * 1e6,
            ".",
            ms=2,
            color=PALETTE[i % len(PALETTE)],
            label=f"{r['session']} {r['rx_clock']}",
        )
    ax.set_xlabel("time since first LTE record (s)")
    ax.set_ylabel("dongle frequency error ε (ppm)")
    if len(res["clock"]) > 1:
        ax.legend(fontsize=7)
    finish(fig, ax, "dongle_clock.png", "Dongle frequency error from the cells' CFO")

    pairs = [r for r in res["pairs"] if "drift_mps" in r]
    if pairs:
        fig, ax = plt.subplots(figsize=(7, 3.2), dpi=130)
        for i, r in enumerate(pairs):
            same = {True: "same eNB", False: "other eNB"}.get(r.get("same_enb"), "unmatched")
            ax.plot(
                r["t"],
                r["d"] - r["d"][0],
                lw=1,
                color=PALETTE[i % len(PALETTE)],
                ls="-" if r.get("same_enb") else "--",
                label=f"{r['b'].label} − {r['a'].label} ({same})",
            )
        ax.set_xlabel("time since first LTE record (s)")
        ax.set_ylabel("b − a, minus its first value (m)")
        if len(pairs) > 1:
            ax.legend(fontsize=6)
        finish(
            fig, ax, "pair_differences.png", "Tower timing: pseudorange differences, one dongle"
        )

    ad = [r for r in res["clock"] if r.get("adev")]
    if ad:
        fig, ax = plt.subplots(figsize=(6, 3.6), dpi=130)
        for i, r in enumerate(ad):
            tau, a = zip(*r["adev"], strict=True)
            ax.loglog(tau, a, "o-", ms=3, color=PALETTE[i % len(PALETTE)], label=r["session"])
        ax.set_xlabel("τ (s)")
        ax.set_ylabel("overlapping Allan deviation of ε")
        if len(ad) > 1:
            ax.legend(fontsize=7)
        finish(fig, ax, "dongle_allan.png", "Dongle frequency stability (CFO, tower error mixed)")
    return written


# --- main -----------------------------------------------------------------------------------


def run(paths, out: Path | None, position=None, make_figures: bool = True, originals=None) -> str:
    originals = list(originals or [None] * len(paths))
    if len(originals) != len(paths):
        raise SystemExit(f"--original given {len(originals)} times for {len(paths)} session(s)")
    sessions = [load(p, position, o) for p, o in zip(paths, originals, strict=True)]
    table, names = celltab.CellTable.load(), _site_names()
    for s in sessions:
        identify(s, table, names)
    res = analyse(sessions)
    commit = _commit()
    text = report(sessions, res, commit)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(text)
        if make_figures:
            figs = figures(sessions, res, out, commit)
            text += "\nFigures: " + ", ".join(f"`{p}`" for p in figs) + "\n"
        text += f"Written to `{out / 'report.md'}`.\n"
    return text


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("sessions", nargs="+", help="derived LTE session(s): <session>-lte")
    p.add_argument(
        "--out",
        help="folder for report.md and figures "
        "(default: <first session>-report beside it; never commit raw data)",
    )
    p.add_argument("--position", help="receiver lat,lon,h (default: mean GNSS fix, else origin)")
    p.add_argument(
        "--original",
        action="append",
        help="original session folder (with the IQ sidecar), once per session in order "
        "(default: <session> beside <session>-lte)",
    )
    p.add_argument("--no-figures", action="store_true")
    a = p.parse_args(argv)
    pos = None
    if a.position:
        pos = tuple(float(x) for x in a.position.split(","))
        if len(pos) != 3:
            raise SystemExit(f"--position wants lat,lon,h: {a.position!r}")
    first = Path(a.sessions[0])
    out = Path(a.out) if a.out else first.with_name(f"{first.name}-report")
    print(run(a.sessions, out, pos, not a.no_figures, a.original))


if __name__ == "__main__":
    main()
