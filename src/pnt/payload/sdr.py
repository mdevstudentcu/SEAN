"""RTL-SDR IQ capture: `sdr_<x>.cu8` plus its `.json` sidecar (ICD-session, ADR-0007).

Receive only (REQ-07): `rtl_sdr` reads the dongle; RTL-SDRs cannot transmit.

`rtl_sdr` cannot start on a PPS edge, so the time of each sample comes from the host clock,
which chrony disciplines to GPS PPS (ASM-04). For every buffer read from `rtl_sdr` the sidecar
keeps `[sample_index, stamp]` (`buffers`): the buffer's first sample index in the file and its
arrival time on the host clock minus the buffer's duration, in GPS ns. Arrival is always later
than the sample, so `stamp - index / fs` is the sample-to-host latency plus a constant:

- `t_ns` (time of sample 0) is the lower envelope of that latency, fitted over the capture.
- A dropped run of samples shows as a lasting step up in it, by the dropped duration
  (`find_gaps`). The step is only as precise as the latency jitter, so suspected gaps are listed
  in `gaps_suspected`, not in `gaps` (which a reader may take as exact).

Sidecar keys follow the LTE front end's reader (`frontends/lte/capture.py`, #23):
`sample_rate_hz`, `center_freq_hz`, `t_ns`, `gain_db`, `dongle`, `buffers`, plus recorder
extras (`device`, `t_ns_method`, `rate_ppm_vs_host`, `gaps_suspected`, `stderr`).
"""

from __future__ import annotations

import fcntl
import json
import os
import queue
import select
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path

import numpy as np

from pnt.core.time import now_gps_ns

DEFAULT_CHUNK = 131_072  # samples per read: rtl_sdr's own 256 KiB output block
SIDECAR_PERIOD_S = 10.0  # rewrite the sidecar this often, so a crash keeps the timing
# A step this large in the latency envelope is called a drop. Regression guard, not a
# requirement: rtl_sdr loses whole USB transfers (tens of ms), scheduling jitter is ~ms. TBC
# against the day-1 session (#88).
GAP_THRESHOLD_NS = 5_000_000
ENVELOPE_WINDOW = 16  # buffers per lower-envelope window (~1 s at 1.92 MS/s)
F_SETPIPE_SZ = 1031  # Linux fcntl: grow the pipe so a slow write does not stall rtl_sdr


def latency_ns(buffers: np.ndarray, fs: float) -> np.ndarray:
    """`stamp - index / fs` for each buffer, ns, relative to the first buffer's stamp (float64
    cannot hold a GPS-ns time to the nanosecond, a difference it can)."""
    b = np.asarray(buffers, dtype=np.int64)
    return (b[:, 1] - b[0, 1]).astype(float) - b[:, 0] * (1e9 / fs)


def _window_minima(lat: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(lat) // w * w
    if n == 0:
        return np.array([int(np.argmin(lat))]), np.array([lat.min()])
    blocks = lat[:n].reshape(-1, w)
    arg = blocks.argmin(axis=1) + np.arange(0, n, w)
    return arg, blocks.min(axis=1)


def find_gaps(
    buffers, fs: float, threshold_ns: float = GAP_THRESHOLD_NS, window: int = ENVELOPE_WINDOW
) -> list[tuple[int, int]]:
    """Suspected drops: `[(sample_index, samples_dropped_before_it), ...]`.

    A drop is a step up in the latency's lower envelope larger than `threshold_ns` between two
    neighbouring windows. It is located at the first buffer after the earlier window's minimum
    whose latency stays above that minimum plus the threshold, and sized by the step."""
    b = np.asarray(buffers, dtype=np.int64)
    if len(b) < 2:
        return []
    lat = latency_ns(b, fs)
    arg, mins = _window_minima(lat, window)
    gaps = []
    for k in range(1, len(mins)):
        # a drop lasts: the envelope must stay up for the next windows too (a long stall that
        # catches up again is not a drop)
        step = mins[k : k + 3].min() - mins[k - 1]
        if step <= threshold_ns:
            continue
        lo, hi = int(arg[k - 1]), int(arg[k])
        below = np.flatnonzero(lat[lo : hi + 1] <= mins[k - 1] + threshold_ns)
        first = min(lo + int(below[-1]) + 1, hi)
        gaps.append((int(b[first, 0]), round(step * fs / 1e9)))
    return gaps


def estimate_t0(buffers, fs: float) -> tuple[int, float]:
    """GPS ns of sample 0 and the dongle's rate error against the host clock (ppm).

    A line through the latency's window minima before the first suspected gap: its intercept
    at sample 0 is `t_ns`, its slope the rate error."""
    b = np.asarray(buffers, dtype=np.int64)
    lat = latency_ns(b, fs)
    gaps = find_gaps(b, fs)
    stop = int(np.searchsorted(b[:, 0], gaps[0][0])) if gaps else len(b)
    arg, mins = _window_minima(lat[:stop], ENVELOPE_WINDOW)
    idx = b[arg, 0].astype(float)
    if len(mins) >= 3:
        slope, intercept = np.polyfit(idx, mins, 1)
        resid = mins - (slope * idx + intercept)
        intercept += resid.min()  # keep it a lower envelope
    else:
        slope, intercept = 0.0, float(mins.min())
    ppm = -slope * fs / 1e9 * 1e6  # latency falling = dongle samples faster than nominal
    return int(b[0, 1]) + int(round(intercept)), float(ppm)


class RtlSdrStream:
    """`rtl_sdr ... -` as a byte stream (the real reader)."""

    def __init__(self, cmd: list[str]):
        self.cmd = cmd
        pipe = subprocess.PIPE
        # own session: a Ctrl-C in the terminal reaches the recorder, which stops rtl_sdr itself
        self.proc = subprocess.Popen(
            cmd, stdout=pipe, stderr=pipe, bufsize=0, start_new_session=True
        )
        try:
            fcntl.fcntl(self.proc.stdout.fileno(), F_SETPIPE_SZ, 1 << 20)
        except OSError:
            pass  # pipe stays at the default size; drops still show in the timing
        self.stderr: deque[str] = deque(maxlen=50)
        self._err = threading.Thread(target=self._read_stderr, daemon=True)
        self._err.start()

    def _read_stderr(self) -> None:
        for line in iter(self.proc.stderr.readline, b""):
            self.stderr.append(line.decode(errors="replace").rstrip())

    def read(self, nbytes: int, stop=None) -> bytes:
        """Exactly `nbytes`; fewer at end of stream, or once `stop` is set (a stuck dongle
        cannot hold the recorder up)."""
        buf = bytearray(nbytes)
        view = memoryview(buf)
        got = 0
        fd = self.proc.stdout.fileno()
        while got < nbytes:
            if not select.select([fd], [], [], 0.5)[0]:
                if stop is not None and stop.is_set():
                    break
                continue
            n = os.readv(fd, [view[got:]])
            if n == 0:
                break
            got += n
        return bytes(view[:got])

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self._err.join(timeout=2)


class RtlSdr:
    """One dongle into `sdr_<name>.cu8` + `.json`."""

    hardware = "rtl-sdr"

    def __init__(
        self,
        name: str,
        freq_hz: float,
        rate_hz: float = 1.92e6,
        gain_db: float | None = None,
        device: str = "0",
        ppm: int = 0,
        chunk: int = DEFAULT_CHUNK,
        hardware: str = "rtl-sdr",
        stream_factory=None,
        clock=now_gps_ns,
    ):
        self.name = f"sdr_{name}"
        self.freq_hz = float(freq_hz)
        self.rate_hz = float(rate_hz)
        self.gain_db = gain_db
        self.device = str(device)
        self.ppm = int(ppm)
        self.chunk = int(chunk)
        self.hardware = hardware
        self._factory = stream_factory or RtlSdrStream
        self._clock = clock
        self.samples = 0
        self.buffers: list[list[int]] = []
        self._stream = None

    def command(self) -> list[str]:
        cmd = ["rtl_sdr", "-d", self.device, "-f", str(int(self.freq_hz))]
        cmd += ["-s", str(int(self.rate_hz)), "-b", str(2 * self.chunk)]
        if self.gain_db is not None:
            cmd += ["-g", f"{self.gain_db:g}"]
        if self.ppm:
            cmd += ["-p", str(self.ppm)]
        return [*cmd, "-"]

    def probe(self) -> str | None:
        if self._factory is RtlSdrStream and shutil.which("rtl_sdr") is None:
            return "rtl_sdr not installed (apt install rtl-sdr)"
        return None

    def status(self) -> dict:
        out = {"samples": self.samples, "buffers": len(self.buffers)}
        if len(self.buffers) > ENVELOPE_WINDOW:
            out["gaps_suspected"] = len(find_gaps(self.buffers, self.rate_hz))
        return out

    def sidecar(self) -> dict:
        out = {
            "dongle": self.name,
            "device": self.device,
            "center_freq_hz": self.freq_hz,
            "sample_rate_hz": self.rate_hz,
            "gain_db": self.gain_db if self.gain_db is not None else "auto",
            "ppm_correction": self.ppm,
            "command": " ".join(self.command()),
            "t_ns": None,
            "t_ns_method": (
                "lower envelope of host arrival times (chrony/PPS-disciplined clock) minus "
                "buffer duration; not started on a PPS edge. Bias = minimum USB/pipe latency, TBD"
            ),
            "buffers_stamp": "host GPS ns at arrival minus the buffer's duration",
            "samples": self.samples,
            "buffers": self.buffers,
            "gaps_suspected": [],
            "hops": [],
        }
        if self.buffers:
            out["t_ns"], out["rate_ppm_vs_host"] = estimate_t0(self.buffers, self.rate_hz)
            out["gaps_suspected"] = [list(g) for g in find_gaps(self.buffers, self.rate_hz)]
        if self._stream is not None and getattr(self._stream, "stderr", None):
            out["stderr"] = list(self._stream.stderr)
        return out

    def _write_sidecar(self, folder: Path) -> None:
        path = folder / f"{self.name}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.sidecar()))
        tmp.replace(path)

    def run(self, ctx) -> None:
        folder = Path(ctx.folder)
        self._stream = self._factory(self.command())
        q: queue.Queue = queue.Queue(maxsize=256)  # ~64 MB of IQ between USB and the card
        write_error: list[BaseException] = []

        def writer() -> None:
            with open(folder / f"{self.name}.cu8", "wb") as f:
                while (data := q.get()) is not None:
                    try:
                        f.write(data)
                    except OSError as exc:  # disk full: keep draining so the reader can stop
                        write_error.append(exc)

        wt = threading.Thread(target=writer, name=f"{self.name}-writer")
        wt.start()
        nbytes = 2 * self.chunk
        last_sidecar = now = self._clock()
        ctx.event(now, f"{self.name} started", command=self.command())
        try:
            while not ctx.stop.is_set() and not write_error:
                data = self._stream.read(nbytes, ctx.stop)
                t = self._clock()
                n = len(data) // 2
                if n == 0:
                    break
                self.buffers.append([self.samples, t - round(n * 1e9 / self.rate_hz)])
                self.samples += n
                q.put(data[: 2 * n])
                if t - last_sidecar > SIDECAR_PERIOD_S * 1e9:
                    last_sidecar = t
                    self._write_sidecar(folder)
        finally:
            self._stream.close()
            q.put(None)
            wt.join()
            self._write_sidecar(folder)
        if write_error:
            raise write_error[0]
        if not ctx.stop.is_set():
            tail = "; ".join(list(getattr(self._stream, "stderr", []))[-3:])
            raise RuntimeError(f"rtl_sdr stopped after {self.samples} samples: {tail}")
        ctx.event(self._clock(), f"{self.name} stopped", samples=self.samples)
