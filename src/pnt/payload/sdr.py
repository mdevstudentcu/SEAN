"""RTL-SDR IQ capture: `sdr_<x>.cu8` plus its `.json` sidecar (ICD-session, ADR-0007).

Receive only (REQ-07): `rtl_sdr` reads the dongle; RTL-SDRs cannot transmit.

`rtl_sdr` cannot start on a PPS edge, so the time of each sample comes from the host clock,
which chrony disciplines to GPS PPS (ASM-04). For every buffer read from `rtl_sdr` the sidecar
keeps `[sample_index, stamp]` (`buffers`): the buffer's first sample index in the file and its
arrival time on the host clock minus the buffer's duration, in GPS ns. Arrival is always later
than the sample, so `stamp - index / fs` is the sample-to-host latency plus a constant:

- `t_ns` (time of sample 0) is the lower envelope of that latency, fitted over the capture.
- A dropped run of samples shows as a lasting step up in it, by the dropped duration
  (`find_gaps`). The step is only as precise as the latency jitter (ms, i.e. hundreds of km of
  range), so suspected gaps are listed in `gaps_suspected`. `gaps` is for drops known to the
  sample, which a reader applies as exact; `rtl_sdr` reports none, so it is always empty. The
  LTE front end sizes a drop it finds in the signal from `buffers` instead.

If `rtl_sdr` exits while the recording goes on (the dongle dropped off USB: `cb transfer status:
1`, `Library error -5`), the dongle is opened again, by its serial, with a growing wait between
tries (`REOPEN_BACKOFF_S`), until it streams or the recording ends (#288). Its samples go on in
the same `.cu8`, so every reader keeps one file and one sample index per dongle; the break is
listed in `outages` (ICD-session): the file index of the first sample after it and the host
times either side, which size it to the stamps' jitter only. A dongle that fails before its
first sample is not retried: that is a wrong option or a missing dongle, and it fails as before.

Indices swap when the bus re-enumerates (a replug, a reboot), so the serial is read at the drop
from `rtl_sdr`'s own device list on stderr. librtlsdr reads a `-d` that parses as a number as an
index, and two dongles can share a serial (`00000001` is common); for those the reopen tries
each index listed with the same name and serial in turn (one held by another `rtl_sdr` fails to
open), which cannot tell two identical dongles apart.

Sidecar keys are the LTE front end's (`frontends/lte/capture.py`, #23), exactly:
`sample_rate_hz`, `center_freq_hz`, `t_ns` (int), `gain_db` (float, null for AGC), `dongle`,
`earfcn` (int, only if given), `hops` (empty: one carrier per capture), `gaps` (empty, above),
`buffers` (`[[int, int], ...]`), `outages` (only if the dongle dropped). Recorder extras:
`device`, `gain_mode`, `ppm_correction`, `command`, `samples`, `t_ns_method`, `buffers_stamp`,
`rate_ppm_vs_host`, `gaps_suspected`, `stderr`.
"""

from __future__ import annotations

import fcntl
import json
import os
import queue
import re
import select
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path

import numpy as np

from pnt.core.time import gps_ns_to_utc, now_gps_ns

DEFAULT_CHUNK = 131_072  # samples per read: rtl_sdr's own 256 KiB output block
SIDECAR_PERIOD_S = 10.0  # rewrite the sidecar this often, so a crash keeps the timing
# A step this large in the latency envelope is called a drop. Regression guard, not a
# requirement: rtl_sdr loses whole USB transfers (tens of ms), scheduling jitter is ~ms. TBC
# against the day-1 session (#88).
GAP_THRESHOLD_NS = 5_000_000
ENVELOPE_WINDOW = 16  # buffers per lower-envelope window (~1 s at 1.92 MS/s)
F_SETPIPE_SZ = 1031  # Linux fcntl: grow the pipe so a slow write does not stall rtl_sdr
# Wait before each try to reopen a dongle that dropped mid-recording, s: one entry per try, the
# last repeated. TBC: on 20261111-1806-walk-lte the dongle was back on the bus about 2 s after
# its USB disconnect (#288).
REOPEN_BACKOFF_S = (0.5, 1.0, 2.0, 4.0)
STDERR_HEAD = 20  # first stderr lines kept whole: rtl_sdr's device list is there
_LISTED = re.compile(r"^\s*(\d+):\s+(.*), SN: (.*?)\s*$")  # "  0:  Realtek, RTL2838UHIDIR, SN: 1"
_USING = re.compile(r"^Using device (\d+):")


def parse_device_list(lines) -> tuple[list[tuple[str, str]], int | None]:
    """`rtl_sdr`'s device list from its stderr: `(name, serial)` by index, and the index it
    opened (None if it did not say)."""
    listed: dict[int, tuple[str, str]] = {}
    using = None
    for line in lines:
        if m := _LISTED.match(line):
            listed[int(m[1])] = (m[2], m[3])
        elif m := _USING.match(line):
            using = int(m[1])
    return [listed[i] for i in sorted(listed)], using


def reads_as_index(text: str) -> bool:
    """Whether librtlsdr takes a `-d` value as a device index (`strtol`, base 0), not a serial."""
    return re.fullmatch(r"\s*[+-]?(0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)", text) is not None


def clock_time(t_ns: int) -> str:
    """Local wall-clock time of a GPS-ns time, `HH:MM:SS`, for the notes."""
    return f"{gps_ns_to_utc(t_ns).astimezone():%H:%M:%S}"


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
        self.head: list[str] = []  # the first lines, which a long run pushes out of `stderr`
        self._err = threading.Thread(target=self._read_stderr, daemon=True)
        self._err.start()

    def _read_stderr(self) -> None:
        for line in iter(self.proc.stderr.readline, b""):
            text = line.decode(errors="replace").rstrip()
            if len(self.head) < STDERR_HEAD:
                self.head.append(text)
            self.stderr.append(text)

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
        earfcn: int | None = None,
        chunk: int = DEFAULT_CHUNK,
        hardware: str = "rtl-sdr",
        stream_factory=None,
        clock=now_gps_ns,
        backoff_s: tuple[float, ...] = REOPEN_BACKOFF_S,
    ):
        self.name = f"sdr_{name}"
        self.freq_hz = float(freq_hz)
        self.rate_hz = float(rate_hz)
        self.gain_db = gain_db
        self.device = str(device)
        self.ppm = int(ppm)
        self.earfcn = earfcn
        self.chunk = int(chunk)
        self.hardware = hardware
        self._factory = stream_factory or RtlSdrStream
        self._clock = clock
        self.samples = 0
        self.buffers: list[list[int]] = []
        self._stream = None
        self.backoff_s = tuple(backoff_s)
        self.outages: list[dict] = []  # see `_reopen`
        self._identity: tuple[str, str] | None = None  # (name, serial) as rtl_sdr listed it
        self._serial_names_it = False  # the serial picks this dongle alone for `-d`
        self._listing: list[tuple[str, str]] = []  # the latest device list seen

    def command(self, device: str | None = None) -> list[str]:
        """The `rtl_sdr` command line; `device` overrides the `-d` given (a reopen)."""
        cmd = ["rtl_sdr", "-d", device or self.device, "-f", str(int(self.freq_hz))]
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
        if self.outages:
            out["outages"] = len(self.outages)
        if len(self.buffers) > ENVELOPE_WINDOW:
            out["gaps_suspected"] = len(find_gaps(self.buffers, self.rate_hz))
        return out

    def sidecar(self) -> dict:
        out = {
            "dongle": self.name,
            "device": self.device,
            "center_freq_hz": self.freq_hz,
            "sample_rate_hz": self.rate_hz,
            "gain_db": self.gain_db,
            "gain_mode": "manual" if self.gain_db is not None else "auto",
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
            "gaps": [],
            "gaps_suspected": [],
            "hops": [],
        }
        if self.earfcn is not None:
            out["earfcn"] = int(self.earfcn)
        if self.outages:  # only then: a capture without one is as before (#288)
            out["outages"] = [dict(o) for o in self.outages]
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
                if n == 0 and self.samples and not ctx.stop.is_set():
                    data, t = self._reopen(ctx, folder, nbytes)  # dropped off USB mid-recording
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

    # --- a dongle that drops off USB mid-recording (#288) ----------------------------------
    def _learn(self, stream, identify: bool) -> None:
        """Read the device list a stream's `rtl_sdr` printed; with `identify`, the stream ran
        on this dongle, so its name and serial are this dongle's."""
        lines = getattr(stream, "head", None) or list(getattr(stream, "stderr", []))
        listing, using = parse_device_list(lines)
        if not listing:
            return
        self._listing = listing
        if identify and using is not None and using < len(listing):
            self._identity = listing[using]
            serial = self._identity[1]
            self._serial_names_it = (
                bool(serial)
                and not reads_as_index(serial)
                and ([s for _, s in listing].count(serial) == 1)
            )

    def reopen_devices(self) -> list[str]:
        """`-d` values to try in turn when reopening: the serial if it names this dongle alone,
        else every index listed with this dongle's name and serial, else the `-d` given."""
        if self._identity is None:
            return [self.device]
        if self._serial_names_it:
            return [self._identity[1]]
        same = [str(i) for i, entry in enumerate(self._listing) if entry == self._identity]
        return same or [self.device]

    def _reopen(self, ctx, folder: Path, nbytes: int) -> tuple[bytes, int]:
        """Open the dongle again after `rtl_sdr` exited mid-recording, waiting `backoff_s`
        before each try, until it streams or the recording ends. Returns the first buffer and
        its arrival time, or `b""` if the recording ended first. The break goes in `outages`:
        `sample_index` (file index of the first sample after it), `t_lost_ns` (host time the
        first missing sample was due: the last buffer's stamp plus its duration), `t_back_ns`
        (the first buffer's stamp after it; null if never back), `attempts`, `device` (the `-d`
        that worked) and `error` (`rtl_sdr`'s last words)."""
        old = self._stream
        old.close()
        self._learn(old, identify=True)
        last_index, last_stamp = self.buffers[-1]
        error = "; ".join(list(getattr(old, "stderr", []))[-3:])
        outage = {
            "sample_index": self.samples,
            "t_lost_ns": last_stamp + round((self.samples - last_index) * 1e9 / self.rate_hz),
            "t_back_ns": None,
            "attempts": 0,
            "device": None,
            "error": error,
        }
        self.outages.append(outage)
        ctx.event(self._clock(), f"{self.name} dropped", sample_index=self.samples, error=error)
        self._write_sidecar(folder)
        while True:
            wait = self.backoff_s[min(outage["attempts"], len(self.backoff_s) - 1)]
            if ctx.stop.wait(wait):
                ctx.event(self._clock(), f"{self.name} not reopened", attempts=outage["attempts"])
                return b"", self._clock()
            devices = self.reopen_devices()
            device = devices[outage["attempts"] % len(devices)]
            outage["attempts"] += 1
            self._stream = self._factory(self.command(device))
            data = self._stream.read(nbytes, ctx.stop)
            t = self._clock()
            if len(data) >= 2:
                outage["t_back_ns"] = t - round(len(data) // 2 * 1e9 / self.rate_hz)
                outage["device"] = device
                ctx.event(t, f"{self.name} reopened", device=device, attempts=outage["attempts"],
                          command=self.command(device))  # fmt: skip
                return data, t
            self._stream.close()
            self._learn(self._stream, identify=False)  # the bus as it is now

    def notes(self) -> list[str]:
        """For meta.yaml `notes` and the summary `pnt record` prints: each drop and reopen."""
        if not self.outages:
            return []
        parts = []
        for o in list(self.outages):
            text = f"dropped {clock_time(o['t_lost_ns'])}"
            if o["t_back_ns"] is not None:
                text += f", reopened {clock_time(o['t_back_ns'])} (-d {o['device']})"
            else:
                text += f", not back by the end ({o['attempts']} tries)"
            parts.append(text)
        k = len(parts)
        return [f"{self.name}: {'; '.join(parts)}; {k} outage{'s' * (k > 1)}, samples not "
                f"continuous ({self.name}.json outages)"]  # fmt: skip
