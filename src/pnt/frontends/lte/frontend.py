"""Capture -> LTE `Measurement`s (ICD-measurement): the front end's public entry point.

Per cell and output period (10 Hz by default) it emits:

- `pseudorange` (m): c · (frame-boundary arrival in local time, unwrapped across the 10 ms frame
  ambiguity). The value carries an unknown constant per arc: the tower's frame timing, modulo
  c · 10 ms (`meta.ambiguity_m`). A tower clock state seeded from the first residual absorbs it.
  The value is the carrier-aided weighted mean of the period's 5 ms epochs, so successive outputs
  have independent noise; smoothing beyond that is the navigation filter's job.
- `doppler` (m/s): -c · CFO / fc, the raw pseudorange rate seen through the dongle's clock, from
  the carrier phase over the period. Emitted only while carrier aiding is on.

`meta.rx_clock` names the receiver clock. The RTL-SDR's tuner LO and ADC run from one TCXO, so
every record with the same `rx_clock` shares one clock offset and drift: the drift appears in the
doppler as c · (clock drift) and in the pseudoranges' rate identically.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pnt.core.measurement import Measurement
from pnt.frontends.lte import signals as sig
from pnt.frontends.lte.capture import Capture, Segment, open_capture
from pnt.frontends.lte.tracker import (
    C,
    CellTrack,
    Config,
    Found,
    Gap,
    GapMap,
    State,
    _Track,
    search,
)


@dataclass
class Result:
    measurements: list[Measurement]
    cells: list[CellTrack]
    gaps: list[Gap]
    capture_s: float
    elapsed_s: float
    found: list[tuple[int, Found]] = field(default_factory=list)  # (file index, cell) per search

    @property
    def realtime_factor(self) -> float:
        return self.capture_s / max(self.elapsed_s, 1e-9)


def process_file(path: str | Path, cfg: Config | None = None, **kw) -> Result:
    """Open a `.cu8` capture with its sidecar and run the front end on it."""
    earfcn = kw.pop("earfcn", None)
    return process_capture(open_capture(path, kw.pop("sidecar", None), earfcn), cfg, **kw)


def process_capture(cap: Capture, cfg: Config | None = None, receiver: str = "payload") -> Result:
    t_start = time.perf_counter()
    r = _process(cap, cfg, receiver, list(cap.gaps))
    # A drop of a whole number of frames leaves the signal's timing unchanged, so the tracker
    # can't see it; only the recorder's buffer stamps can. Put any such drop in as a known gap
    # and run again (once).
    extra = _unexplained_stalls(cap, r.gaps)
    if extra:
        r = _process(cap, cfg, receiver, [*cap.gaps, *extra])
    r.elapsed_s = time.perf_counter() - t_start
    return r


# Buffers each side of a stamp step whose latency floor is compared (TBC). A real drop moves the
# floor for good; a stall that catches up does not.
STALL_WINDOW = 8


def _unexplained_stalls(cap: Capture, found: list) -> list[tuple[int, int]]:
    """Drops the buffer stamps show (latency floor up by at least half a frame) that no gap the
    tracker found explains, as (file index, samples). The signal saw no jump there, so each is a
    whole number of frames: the stamps' size, rounded to one. Sizes more than a quarter frame
    from a whole frame are left out (not a clean frame drop: the tracker should have seen it)."""
    if cap.buffers is None or len(cap.buffers) < 2:
        return []
    L = sig.half_frame_length(cap.fs)
    frame = 2 * L
    idx = cap.buffers[:, 0]
    lat = (cap.buffers[:, 1] - cap.buffers[0, 1]) - idx * 1e9 / cap.fs  # ns, minus a constant
    out, prev = [], False
    for i in range(1, len(idx)):
        before = lat[max(0, i - STALL_WINDOW) : i].min()
        after = lat[i : i + STALL_WINDOW].min()
        n_host = (after - before) * cap.fs / 1e9
        step = n_host >= L
        if step and not prev:
            at = int(idx[i])
            k = round(n_host / frame)
            near = any(abs(g.at - at) <= 2 * frame for g in found)
            if k >= 1 and abs(n_host - k * frame) < L / 2 and not near:
                out.append((at, k * frame))
        prev = step
    return out


def _process(cap: Capture, cfg: Config | None, receiver: str, known: list) -> Result:
    cfg = cfg or Config()
    t_start = time.perf_counter()
    gaps = GapMap([Gap(at=a, n=n, until=a) for a, n in known])
    carry: dict[tuple, tuple[CellTrack, State]] = {}
    cells: list[CellTrack] = []
    found_log: list[tuple[int, Found]] = []
    for seg in cap.segments:
        for cell in _segment(cap, seg, gaps, cfg, carry, found_log):
            if all(cell is not c for c in cells):  # a cell carried across hops is listed once
                cells.append(cell)
    meas = emit(cells, cap, gaps, cfg, receiver)
    return Result(
        measurements=meas,
        cells=cells,
        gaps=list(gaps.gaps),
        capture_s=cap.n_samples / cap.fs,
        elapsed_s=time.perf_counter() - t_start,
        found=found_log,
    )


def _segment(cap: Capture, seg: Segment, gaps: GapMap, cfg: Config, carry, found_log):
    fs, fc = cap.fs, seg.center_freq_hz
    L = sig.half_frame_length(fs)
    n_acq = int(cfg.acq_ms * 1e-3 * fs)
    trk = _Track(cap, seg, gaps, cfg)
    c_stop = float(gaps.to_corrected(np.int64(seg.stop - 1)))
    first = seg.start + (round(cfg.settle_s * fs) if seg.start > 0 else 0)
    step = max(int(cfg.search_period_s * fs), n_acq)
    tracked_until: dict[int, float] = {}
    out: list[CellTrack] = []
    for f_s in range(first, seg.stop - n_acq, step):
        f_s = _clear_of_gaps(gaps, f_s, n_acq)
        if f_s + n_acq > seg.stop:
            break
        c0 = int(gaps.to_corrected(np.int64(f_s)))
        found = search(cap.read(f_s, n_acq), c0, fs, fc, cfg)
        found_log += [(f_s, f) for f in found]
        for f in found:
            if tracked_until.get(f.pci, -np.inf) >= c0:
                continue
            key = (seg.earfcn, f.pci)
            cell, st = _start(key, f, fc, L, carry, seg, cfg)
            st = trk.run(cell, f.n_id1, f.n_id2, st, c_stop)
            carry[key] = (cell, st)
            tracked_until[f.pci] = cell.n0 + st.k * L + st.theta
            if cell not in out:
                out.append(cell)
    return out


def _clear_of_gaps(gaps: GapMap, f: int, n: int) -> int:
    for g in gaps.gaps:
        if f < g.until and g.at < f + n:
            f = g.until
    return f


def _start(
    key, f: Found, fc: float, L: int, carry, seg: Segment, cfg: Config
) -> tuple[CellTrack, State]:
    """A loop state for a found cell: continuing its earlier arc if the timing predicts it."""
    prev = carry.get(key)
    if prev is not None:
        cell, st = prev
        k = 2 * round((f.boundary - cell.n0 - st.theta) / (2 * L))
        st = st.copy()
        st.predict(k, L, L / sig.HALF_FRAME_S, (cfg.accel_ms2 / C) ** 2)
        resid = f.boundary - cell.n0 - k * L - st.theta
        if abs(resid) < 3 * math.sqrt(max(st.p00, 0.0)) + 2.0:
            st.theta += resid
            st.p00 = 0.25
            return cell, st
        cell.arc += 1
        cell.n0 = f.boundary
        nu = -f.f_hz / fc
        return cell, State(0.0, nu, 0.3**2, 0.0, (f.sigma_f_hz / fc) ** 2, 0)
    cell = CellTrack(earfcn=seg.earfcn, fc=fc, pci=f.pci, n0=f.boundary)
    nu = -f.f_hz / fc
    return cell, State(0.0, nu, 0.3**2, 0.0, (f.sigma_f_hz / fc) ** 2, 0)


def emit(
    cells: list[CellTrack], cap: Capture, gaps: GapMap, cfg: Config, receiver: str = "payload"
) -> list[Measurement]:
    """Turn 5 ms epochs into `pseudorange` and `doppler` Measurements, one per period."""
    fs, L = cap.fs, sig.half_frame_length(cap.fs)
    period_ns = round(cfg.output_period_s * 1e9)
    out: list[Measurement] = []
    for cell in cells:
        if not cell.epochs:
            continue
        ep = sorted(cell.epochs, key=lambda e: (e.arc, e.k))  # k restarts when n0 moves
        a = {
            name: np.array([getattr(e, name) for e in ep])
            for name in ("k", "c_ref", "theta_meas", "nu", "sigma", "snr_post", "psi", "n_ref",
                         "locked", "arc", "n0")
        }  # fmt: skip
        arc_shift, marks = _gap_effects(a["n_ref"], gaps)
        a["arc"] = a["arc"] + arc_shift
        a["t"] = cap.t0_ns + np.rint(a["c_ref"] * 1e9 / fs).astype(np.int64)  # int64 GPS ns
        key = a["t"] // period_ns * 1_000_000 + a["arc"]
        cuts = np.r_[0, np.nonzero(np.diff(key))[0] + 1, len(ep)]
        for lo, hi in zip(cuts[:-1], cuts[1:], strict=True):
            g = {name: v[lo:hi] for name, v in a.items()}
            flags = sorted({f for i in range(int(lo), int(hi)) for f in marks.get(i, ())})
            out += _outputs(cell, g, flags, cap, gaps, cfg, receiver, L)
    out.sort(key=lambda m: (m.t_ns, m.emitter, m.kind))
    return out


def _gap_effects(n_ref: np.ndarray, gaps: GapMap) -> tuple[np.ndarray, dict[int, set[str]]]:
    """What the capture's gaps do to one cell, whichever cell found them: per epoch, how many
    arcs its unsized gaps have started, and the flags of the first epoch after each gap. Only a
    gap with epochs of this cell on both sides counts."""
    shift = np.zeros(n_ref.size, np.int64)
    marks: dict[int, set[str]] = {}
    for gap, end in zip(gaps.gaps, gaps.corrected_ends(), strict=True):
        after = n_ref >= end
        if after.all() or not after.any():
            continue
        first = int(np.flatnonzero(after)[np.argmin(n_ref[after])])
        marks.setdefault(first, set()).add("sample_gap")
        if gap.ambiguous:
            marks[first].add("gap_ambiguous")
            shift[after] += 1
    return shift, marks


def _outputs(cell, g, flags, cap, gaps, cfg, receiver, L) -> list[Measurement]:
    fs, fc = cap.fs, cell.fc
    n = g["k"].size
    if n < 2:
        return []
    ref = n // 2
    t, t_ref = g["t"], g["t"][ref]
    base = g["n0"] % (2 * L)
    rho = C * (base + g["theta_meas"]) / fs
    sig_m = cfg.sigma_scale * C * g["sigma"] / fs
    w = 1 / sig_m**2
    aligned = rho - C * g["nu"] * (t - t_ref) / 1e9
    value = float(np.sum(w * aligned) / np.sum(w))
    sigma_crb = float(1 / math.sqrt(np.sum(w)))
    sigma_obs = float(np.std(aligned - value, ddof=1) / math.sqrt(n)) if n >= 5 else float("nan")
    sigma = max(sigma_crb, sigma_obs) if not math.isnan(sigma_obs) else sigma_crb
    snr = float(np.mean(g["snr_post"])) / (2 * sig.N_SYNC)
    nu = float(np.mean(g["nu"]))
    emitter = f"lte:{cell.earfcn}:{cell.pci}" if cell.earfcn is not None else f"lte::{cell.pci}"
    f_idx = int(gaps.to_file(np.int64(math.floor(g["c_ref"][ref])))[0])
    meta = {
        "snr_db": round(10 * math.log10(max(snr, 1e-6)), 2),
        "cfo_hz": round(-nu * fc, 3),
        "dongle": cap.dongle,
        "rx_clock": cap.dongle,
        "sample_index": f_idx,
        "earfcn": cell.earfcn,
        "pci": cell.pci,
        "fc_hz": fc,
        "n_epochs": n,
        "arc": int(g["arc"][0]),
        "sigma_crb_m": round(sigma_crb, 3),
        "sigma_obs_m": None if math.isnan(sigma_obs) else round(sigma_obs, 3),
        "ambiguity_m": C * sig.FRAME_S,
        "flags": flags,
    }
    t_ns = int(t_ref)
    out = [
        Measurement(t_ns=t_ns, source="lte", kind="pseudorange", emitter=emitter,
                    receiver=receiver, value=(value,), sigma=(sigma,), meta=meta)
    ]  # fmt: skip
    dop = _doppler(g, fs, fc)
    if dop is not None:
        out.append(Measurement(t_ns=t_ns, source="lte", kind="doppler", emitter=emitter,
                               receiver=receiver, value=(dop[0],), sigma=(dop[1],),
                               meta=meta))  # fmt: skip
    return out


def _doppler(g, fs: float, fc: float) -> tuple[float, float] | None:
    """Range rate (m/s) and its σ from a least-squares fit of the carrier phase."""
    lk = g["locked"].astype(bool)
    if lk.sum() < 4:
        return None
    f_hat = -float(np.mean(g["nu"][lk])) * fc
    n = g["n_ref"][lk] - g["n_ref"][lk][0]
    psi = np.unwrap(g["psi"][lk] - 2 * np.pi * f_hat * n / fs)
    w = 2 * np.maximum(g["snr_post"][lk], 1e-3)  # 1 / var(phase)
    nb = np.sum(w * n) / np.sum(w)
    sxx = np.sum(w * (n - nb) ** 2)
    slope = np.sum(w * (n - nb) * (psi - np.sum(w * psi) / np.sum(w))) / sxx
    f = f_hat + slope * fs / (2 * np.pi)
    sigma_f = math.sqrt(1 / sxx) * fs / (2 * np.pi)
    return float(-C * f / fc), float(C * sigma_f / fc)


def write_session(
    result: Result,
    cap: Capture,
    out: Path,
    commit: str,
    copy_from: Path | None = None,
) -> Path:
    """Write the measurements as a session (ICD-session) that `pnt replay` reads.

    `out` is a new folder (meta.yaml + session.mcap) or a bare `.mcap`. With `copy_from` (the
    capture's own session folder), its meta and every record except this dongle's earlier
    `/meas/lte` output are copied too, so the new session replays with IMU, baro and GNSS."""
    from pnt.io import session
    from pnt.io.mcap_log import SessionWriter, read_session

    src_meta: dict = {}
    records: list = []
    if copy_from is not None and (copy_from / session.MCAP_NAME).exists():
        src_meta = session.read_meta(copy_from)
        for topic, rec in read_session(copy_from / session.MCAP_NAME):
            drop = topic == "/meas/lte" and getattr(rec, "meta", {}).get("rx_clock") == cap.dongle
            if not drop:
                records.append((topic, rec))
    note = f"LTE front end on {cap.path.name} at {commit}"
    meta = {k: src_meta.get(k) for k in session.META_KEYS}
    meta.update(
        name=out.stem if out.suffix == ".mcap" else out.name,
        commit=commit,
        simulated=bool(src_meta.get("simulated", False)),
        hardware=src_meta.get("hardware") or [],
        notes=(f"{src_meta['notes']}; {note}" if src_meta.get("notes") else note),
    )
    if out.suffix == ".mcap":
        mcap = out
    else:
        out.mkdir(parents=True, exist_ok=True)
        session.write_meta(out, meta)
        mcap = out / session.MCAP_NAME
    mcap_meta = {k: v for k, v in meta.items() if v is not None and k != "name"}
    with SessionWriter(mcap, metadata=mcap_meta) as w:
        for topic, rec in records:
            w.write(topic, rec)
        for m in result.measurements:
            w.write("/meas/lte", m)
    return out


def summary(result: Result, cap: Capture) -> str:
    lines = [
        f"{cap.path.name}: {result.capture_s:.1f} s at {cap.fs / 1e6:g} MS/s, "
        f"{len(cap.segments)} segment(s), dongle {cap.dongle}",
        f"processed in {result.elapsed_s:.1f} s ({result.realtime_factor:.1f}x real time)",
    ]
    for c in result.cells:
        pr = [e for e in c.epochs]
        cfo = -np.mean([e.nu for e in pr]) * c.fc if pr else float("nan")
        lines.append(
            f"  lte:{c.earfcn}:{c.pci}  SNR {c.snr_db:6.1f} dB  CFO {cfo:8.1f} Hz "
            f"({cfo / c.fc * 1e6:+.3f} ppm)  {len(pr) * 5 / 1000:6.1f} s tracked  arcs {c.arc + 1}"
        )
    for g in result.gaps:
        kind = "ambiguous (no buffer stamps)" if g.ambiguous else "sized"
        lines.append(f"  gap at sample {g.at}: {g.n} samples dropped, {kind}")
    n_pr = sum(m.kind == "pseudorange" for m in result.measurements)
    n_dop = sum(m.kind == "doppler" for m in result.measurements)
    lines.append(f"{n_pr} pseudoranges, {n_dop} dopplers")
    return "\n".join(lines)
