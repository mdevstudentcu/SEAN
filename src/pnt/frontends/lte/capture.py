"""RTL-SDR IQ captures: `.cu8` samples plus their `.json` sidecar (ICD-session).

The `.cu8` file is 8-bit unsigned interleaved I/Q, as `rtl_sdr` writes it. ICD-session names the
sidecar's contents (centre frequency, sample rate, gain, t_ns of the first sample, band hops with
their t_ns) but not its keys, so this reader proposes them (an open question for the recorder,
#19):

```json
{
  "sample_rate_hz": 1920000,       // required
  "center_freq_hz": 875000000,     // required unless `hops` gives it from sample 0
  "t_ns": 1446000000000000000,     // required: GPS ns of sample 0, PPS-aligned (ADR-0008)
  "gain_db": 40.2,                 // optional, recorded only
  "dongle": "sdr_a",               // optional: receiver clock id (default: the file stem)
  "earfcn": 2460,                  // optional: overrides the EARFCN computed from the frequency
  "hops": [{"sample_index": 0, "t_ns": 1446000000000000000, "center_freq_hz": 875000000}],
  "gaps": [[1234567, 131072]],     // optional: [sample_index, samples dropped before it]
  "buffers": [[0, 1446000000000000000], [131072, 1446000000068266667]],
                                   // optional: host GPS-ns stamp of each USB buffer
  "outages": [{"sample_index": 1934491648, "t_lost_ns": 1446000840000000000,
               "t_back_ns": 1446000843000000000}]
                                   // optional: the dongle was reopened (#288); more keys
}
```

`gaps` is for a recorder that knows its drops. `buffers` lets the front end size a drop it finds
in the signal to the whole frame (a drop shows in the signal only modulo 10 ms). `outages` are
breaks the recorder knows the place of exactly (`sample_index`) but the length only from its host
clock (`t_back_ns - t_lost_ns`): the dongle dropped off USB and was opened again. One never
reopened (`t_back_ns` null) ends the file, so it has no samples after it and is left out.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Downlink bands an RTL-SDR can hear, from 3GPP TS 36.101 Table 5.7.3-1:
# (band, F_DL_low MHz, F_DL_high MHz, N_Offs-DL). Where bands overlap, the first listed wins, so
# one frequency always gives one EARFCN. This table and `earfcn()` must stay identical to
# `analysis/extract_lte_cells.py` (#87), so a heard cell's emitter id matches the cell table.
BANDS = [
    (71, 617.0, 652.0, 68586),
    (29, 717.0, 728.0, 9660),
    (12, 729.0, 746.0, 5010),
    (13, 746.0, 756.0, 5180),
    (14, 758.0, 768.0, 5280),
    (5, 869.0, 894.0, 2400),
]


def earfcn(mhz: float) -> tuple[int | None, bool]:
    """Nearest downlink EARFCN of `mhz`, and whether `mhz` sits off the 100 kHz raster.
    (None, False) outside the bands above."""
    for _band, lo, hi, offset in BANDS:
        if lo <= mhz <= hi:
            n = round((mhz - lo) * 10)
            return offset + n, abs((mhz - lo) * 10 - n) > 1e-6
    return None, False


def dl_hz(n: int) -> float:
    """Downlink centre frequency of EARFCN `n`, Hz (inverse of `earfcn`)."""
    for _band, lo, hi, offset in BANDS:
        f = lo + (n - offset) / 10
        if offset <= n and lo <= f <= hi:
            return f * 1e6
    raise ValueError(f"EARFCN {n} is not in a band this front end knows")


@dataclass(frozen=True)
class Segment:
    """One dwell on one carrier: file samples [start, stop)."""

    start: int
    stop: int
    center_freq_hz: float
    earfcn: int | None


@dataclass
class Capture:
    """An opened `.cu8` capture. Samples are read lazily through a memory map."""

    path: Path
    raw: np.ndarray  # uint8 memmap, interleaved I, Q
    fs: float
    t0_ns: int
    dongle: str
    segments: list[Segment]
    gaps: list[tuple[int, int]] = field(default_factory=list)  # (file index, samples dropped)
    buffers: np.ndarray | None = None  # (n, 2) int64: file sample index, host GPS ns
    # Reopens (file index, samples missing by the host clock), sized only to its jitter
    outages: list[tuple[int, int]] = field(default_factory=list)
    gain_db: float | None = None

    @property
    def n_samples(self) -> int:
        return self.raw.size // 2

    def read(self, start: int, count: int) -> np.ndarray:
        """Complex64 samples [start, start + count), clipped to the file."""
        start = max(0, start)
        stop = min(self.n_samples, start + count)
        if stop <= start:
            return np.zeros(0, np.complex64)
        return cu8_to_complex(self.raw[2 * start : 2 * stop])

    def gather(self, idx: np.ndarray) -> np.ndarray:
        """Complex64 samples at file indices `idx` (any shape; all must be in the file)."""
        i = 2 * np.asarray(idx, dtype=np.int64)
        re = self.raw[i].astype(np.float32)
        im = self.raw[i + 1].astype(np.float32)
        return ((re - 127.5) + 1j * (im - 127.5)).astype(np.complex64) / np.float32(128.0)


def cu8_to_complex(raw: np.ndarray) -> np.ndarray:
    x = np.asarray(raw, dtype=np.float32) - np.float32(127.5)
    return (x[0::2] + 1j * x[1::2]).astype(np.complex64) / np.float32(128.0)


def complex_to_cu8(x: np.ndarray, rms_lsb: float = 24.0) -> np.ndarray:
    """Quantise like the dongle's 8-bit ADC: scale to `rms_lsb` per component, round, clip."""
    x = np.asarray(x)
    rms = math.sqrt(float(np.mean(x.real**2 + x.imag**2)) / 2) or 1.0
    scale = rms_lsb / rms
    out = np.empty(2 * x.size, np.uint8)
    out[0::2] = np.clip(np.round(127.5 + x.real * scale), 0, 255)
    out[1::2] = np.clip(np.round(127.5 + x.imag * scale), 0, 255)
    return out


def sidecar_path(cu8: str | Path) -> Path:
    return Path(cu8).with_suffix(".json")


def write_capture(path: str | Path, raw: np.ndarray, sidecar: dict) -> Path:
    """Write a `.cu8` file and its `.json` sidecar (for tests and synthetic captures)."""
    path = Path(path)
    np.asarray(raw, np.uint8).tofile(path)
    sidecar_path(path).write_text(json.dumps(sidecar, indent=2))
    return path


def open_capture(
    path: str | Path, sidecar: str | Path | None = None, earfcn_override: int | None = None
) -> Capture:
    """Open a `.cu8` capture and parse its sidecar (format in the module docstring)."""
    path = Path(path)
    meta = json.loads(Path(sidecar or sidecar_path(path)).read_text())
    for key in ("sample_rate_hz", "t_ns"):
        if key not in meta:
            raise ValueError(f"{path}: sidecar has no {key!r}")
    raw = np.memmap(path, dtype=np.uint8, mode="r")
    if raw.size % 2:
        raise ValueError(f"{path}: odd byte count; not interleaved I/Q")
    fs = float(meta["sample_rate_hz"])
    t0 = int(meta["t_ns"])
    n = raw.size // 2

    hops = sorted(meta.get("hops") or [], key=lambda h: _hop_index(h, t0, fs))
    if not hops or _hop_index(hops[0], t0, fs) > 0:
        if "center_freq_hz" not in meta:
            raise ValueError(f"{path}: sidecar has no center_freq_hz and no hop at sample 0")
        hops.insert(0, {"sample_index": 0, "center_freq_hz": meta["center_freq_hz"]})
    segments = []
    for i, h in enumerate(hops):
        start = _hop_index(h, t0, fs)
        stop = _hop_index(hops[i + 1], t0, fs) if i + 1 < len(hops) else n
        fc = float(h["center_freq_hz"])
        e = h.get("earfcn", meta.get("earfcn") if len(hops) == 1 else None)
        if earfcn_override is not None:
            e = earfcn_override
        if e is None:
            e, off_raster = earfcn(fc / 1e6)
            if off_raster:
                print(f"note: {fc / 1e6:.4f} MHz is off the 100 kHz raster; EARFCN {e} is nearest")
        segments.append(Segment(start, min(stop, n), fc, None if e is None else int(e)))

    buffers = meta.get("buffers")
    return Capture(
        path=path,
        raw=raw,
        fs=fs,
        t0_ns=t0,
        dongle=str(meta.get("dongle") or path.stem),
        segments=[s for s in segments if s.stop > s.start],
        gaps=[(int(a), int(b)) for a, b in meta.get("gaps") or []],
        buffers=None if not buffers else np.asarray(buffers, dtype=np.int64),
        outages=[
            (int(o["sample_index"]), round((int(o["t_back_ns"]) - int(o["t_lost_ns"])) * fs / 1e9))
            for o in meta.get("outages") or []
            if o.get("t_back_ns") is not None and int(o["sample_index"]) < n
        ],
        gain_db=meta.get("gain_db"),
    )


def _hop_index(hop: dict, t0_ns: int, fs: float) -> int:
    if "sample_index" in hop:
        return int(hop["sample_index"])
    return round((int(hop["t_ns"]) - t0_ns) * fs / 1e9)
