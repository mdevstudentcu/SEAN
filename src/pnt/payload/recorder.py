"""Session capture on the payload (or the reference station): `pnt record` (#19).

One session folder per run, laid out as `systems/icd/session.md` says. Every device runs in its
own thread (SDRs and the camera also in their own process), so a device that is missing or fails
does not stop the others. `meta.yaml` lists in `hardware` the devices that captured, and in
`notes` the ones that were absent or failed, with the reason, and anything a device adds (an
SDR that dropped off USB and was reopened).

Only one thread touches the MCAP writer and the stream socket: devices hand records to it
through a queue.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

import msgspec

from pnt.core.measurement import Measurement, validate
from pnt.core.time import now_gps_ns
from pnt.io import session
from pnt.io.mcap_log import SessionWriter

REPO = Path(__file__).resolve().parents[3]
COMMIT_FILE = REPO / ".pnt-commit"  # written by `just pi-deploy`: the Pi copy has no .git
STATUS_PERIOD_S = 10.0  # device counters to /events this often
META_PERIOD_S = 1.0  # session meta on the stream this often
# End the MCAP chunk in progress this often, so a cut-off session loses at most this long of
# records even when they come too slowly to fill a chunk. Regression guard, not a requirement.
FLUSH_PERIOD_S = 5.0


class Device(Protocol):
    """One capture: a sensor, an SDR, the camera, the flight controller."""

    name: str  # unique in the session, e.g. "imu", "sdr_a"
    hardware: str  # entry for meta.yaml `hardware`, e.g. "mpu6050"

    def probe(self) -> str | None:
        """None if the device is there; else why it is absent."""

    def run(self, ctx: Context) -> None:
        """Capture until `ctx.stop` is set. Raising marks the device failed; others go on."""

    def status(self) -> dict:
        """Counters for `/events` (samples, drops, ...)."""


@dataclass
class Fix:
    """The latest GNSS fix, shared with devices that reference to it (the barometer)."""

    t_ns: int
    llh: tuple[float, float, float]
    up_m: float  # height above the session origin


class Context:
    """What a device sees of the recorder: the folder, the stop flag and the output queue."""

    def __init__(self, folder: Path, receiver: str, origin_llh=None):
        self.folder = folder
        self.receiver = receiver
        self.stop = threading.Event()
        self.queue: queue.Queue = queue.Queue(maxsize=100_000)
        self._lock = threading.Lock()
        self._origin = tuple(origin_llh) if origin_llh is not None else None
        self.origin_changed = threading.Event()
        self.last_fix: Fix | None = None
        self.dropped = 0  # records lost because the queue was full

    @property
    def origin_llh(self) -> tuple[float, float, float] | None:
        return self._origin

    def set_origin_once(self, llh) -> tuple[float, float, float]:
        """The session origin: the one given on the command line, else the first 3D fix."""
        with self._lock:
            if self._origin is None:
                self._origin = tuple(float(x) for x in llh)
                self.origin_changed.set()
            return self._origin

    def emit(self, m: Measurement) -> None:
        if m.receiver != self.receiver:
            m = msgspec.structs.replace(m, receiver=self.receiver)
        validate(m)
        self._put(("meas", m))

    def event(self, t_ns: int, text: str, **data) -> None:
        self._put(("json", "/events", t_ns, {"text": text, **data}, "pnt.Event"))

    def raw(self, topic: str, t_ns: int, data: dict, schema: str) -> None:
        self._put(("json", topic, t_ns, data, schema))

    def _put(self, item) -> None:
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            self.dropped += 1


@dataclass
class DeviceState:
    device: Device
    state: str = "pending"  # pending | absent | running | stopped | failed
    reason: str = ""
    thread: threading.Thread | None = field(default=None, repr=False)


def commit() -> str:
    """The code version for meta.yaml (REQ-10): git if there is a checkout, else the file
    `just pi-deploy` writes, else `unknown`."""
    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    if COMMIT_FILE.exists():
        return COMMIT_FILE.read_text().strip() or "unknown"
    return "unknown"


def session_name(platform: str, place: str, when: datetime | None = None) -> str:
    """`20261110-1430-handheld-carleton` (ICD-session), local time."""
    when = when or datetime.now()
    return f"{when:%Y%m%d-%H%M}-{platform}-{place}"


class Recorder:
    """Runs devices into one session folder and, if given, onto the live stream."""

    def __init__(
        self,
        folder: str | Path,
        devices: list[Device],
        platform: str = "handheld",
        receiver: str = "payload",
        origin_llh=None,
        reference: dict | None = None,
        notes: str = "",
        streamer=None,
    ):
        self.folder = Path(folder)
        names = [d.name for d in devices]
        if len(set(names)) != len(names):
            raise ValueError(f"device names must be unique: {names}")
        session.validate_reference(reference)
        self.devices = [DeviceState(d) for d in devices]
        self.platform = platform
        self.reference = reference
        self.notes = notes
        self.streamer = streamer
        self.ctx = Context(self.folder, receiver, origin_llh)
        self.counts: dict[str, int] = {}
        self._writer_thread: threading.Thread | None = None
        self._abandon = threading.Event()  # set when a device would not stop: finish without it
        self.clock_note = ""
        self.write_errors = 0
        self._log_error: OSError | None = None  # the write that ended the MCAP (disk full)
        self._failures: dict[str, str] = {}  # what could not be done: why

    # --- metadata --------------------------------------------------------------------------
    def meta(self) -> dict:
        captured = [s.device.hardware for s in self.devices if s.state in ("running", "stopped")]
        lines = [self.notes] if self.notes else []
        lines.append(f"receiver: {self.ctx.receiver}")
        describe = getattr(self.streamer, "describe", None)
        if describe:
            lines.append(describe())  # whether the stream is authenticated (ADR-0026)
        lines.append(self.clock_note)
        lines += [
            f"{s.state}: {s.device.name} ({s.device.hardware}): {s.reason}"
            for s in self.devices
            if s.state in ("absent", "failed")
        ]
        for s in self.devices:  # what a device has to add: an SDR's drops and reopens (#288)
            notes = getattr(s.device, "notes", None)
            if notes is not None:
                lines += notes()
        if self.ctx.dropped:
            lines.append(f"records dropped (queue full): {self.ctx.dropped}")
        if self.write_errors:
            lines.append(f"records that could not be written: {self.write_errors}")
        if self._log_error is not None:
            lines.append(f"session.mcap stopped at a write error: {self._log_error!r}")
        lines += [f"could not {what}: {why}" for what, why in self._failures.items()]
        origin = self.ctx.origin_llh
        return {
            "name": self.folder.name,
            "platform": self.platform,
            "origin_llh": list(origin) if origin else None,
            "simulated": False,
            "scenario": None,
            "seed": None,
            "commit": self._commit,
            "hardware": sorted(set(captured)),
            "reference": self.reference,
            "notes": "\n".join(lines),
        }

    def _write_meta(self) -> None:
        session.write_meta(self.folder, self.meta())

    # --- running ---------------------------------------------------------------------------
    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=False)
        self._commit = commit()
        from pnt.payload.devices import clock_status

        self.clock_note = clock_status()
        self._writer = SessionWriter(
            self.folder / session.MCAP_NAME,
            metadata={"name": self.folder.name, "platform": self.platform, "commit": self._commit},
        )
        t0 = now_gps_ns()
        for s in self.devices:
            try:
                reason = s.device.probe()
            except Exception as exc:  # a probe must never stop the recorder
                reason = f"probe error: {exc!r}"
            if reason:
                s.state, s.reason = "absent", reason
                self.ctx.event(t0, f"{s.device.name} absent", device=s.device.name, reason=reason)
                continue
            s.state = "running"
            # daemon: a device stuck in a driver call cannot keep the process alive after stop()
            s.thread = threading.Thread(
                target=self._run_device, args=(s,), name=s.device.name, daemon=True
            )
        self._write_meta()
        self._writer_thread = threading.Thread(target=self._drain, name="writer")
        self._writer_thread.start()
        for s in self.devices:
            if s.thread:
                s.thread.start()

    def _run_device(self, s: DeviceState) -> None:
        try:
            s.device.run(self.ctx)
            s.state = "stopped"
        except Exception as exc:
            s.state, s.reason = "failed", repr(exc)
            self.ctx.event(now_gps_ns(), f"{s.device.name} failed", error=repr(exc))

    def _drain(self) -> None:
        """The one thread that writes the MCAP and the stream."""
        last_status = last_meta = last_flush = time.monotonic()
        while True:
            try:
                item = self.ctx.queue.get(timeout=0.2)
            except queue.Empty:
                item = None
            if item is not None:
                try:
                    self._handle(item)
                except Exception as exc:  # one bad record must not end the recording
                    self.write_errors += 1
                    if self.write_errors % 1000 == 1:
                        self._say(f"record: cannot write {item[:2]!r}: {exc!r}")
            now = time.monotonic()
            if self.ctx.origin_changed.is_set():
                self.ctx.origin_changed.clear()
                self._guarded("write meta.yaml", self._write_meta)
            if now - last_flush >= FLUSH_PERIOD_S:
                last_flush = now
                self._log(self._writer.flush)
            if self.streamer and now - last_meta >= META_PERIOD_S:
                last_meta = now
                self._guarded("stream the session meta", self._send_meta)
            if now - last_status >= STATUS_PERIOD_S:
                last_status = now
                self._guarded("log device status", self._status_event)
            if item is None and self._finished():
                break

    def _say(self, text: str) -> None:
        try:
            print(text)
        except OSError:  # the terminal has gone (a dropped ssh): the recording goes on
            pass

    def _guarded(self, what: str, fn, *args) -> None:
        """Housekeeping that must not take the recording down; the failure goes in the notes."""
        try:
            fn(*args)
        except Exception as exc:
            if what not in self._failures:
                self._say(f"record: could not {what}: {exc!r}")
            self._failures[what] = repr(exc)

    def _log(self, fn, *args) -> bool:
        """One MCAP write. The first OSError (disk full) ends writing: the mcap writer would
        retry the failed chunk on every later record, holding it all in memory. Devices and the
        stream go on; True if the record was written."""
        if self._log_error is not None:
            self.write_errors += 1
            return False
        try:
            fn(*args)
        except OSError as exc:
            self._log_error = exc
            self.write_errors += 1
            self._say(f"record: session.mcap can no longer be written: {exc!r}")
            return False
        return True

    def _send_meta(self) -> None:
        self.streamer.send_meta(self.meta(), self.ctx.receiver)

    def _handle(self, item) -> None:
        if item[0] == "meas":
            m = item[1]
            if self._log(self._writer.write, f"/meas/{m.source}", m):
                self.counts[m.source] = self.counts.get(m.source, 0) + 1
            if self.streamer:
                self.streamer.send(m)
        else:
            _, topic, t_ns, data, schema = item
            self._log(self._writer.write_json, topic, t_ns, data, schema)

    def _finished(self) -> bool:
        return self.ctx.stop.is_set() and (
            self._abandon.is_set()
            or not any(s.thread and s.thread.is_alive() for s in self.devices)
        )

    def _status_event(self) -> None:
        devices = {}
        for s in self.devices:
            entry = {"state": s.state}
            if s.state not in ("absent", "pending"):
                try:
                    entry.update(s.device.status())
                except Exception as exc:
                    entry["status_error"] = repr(exc)
            devices[s.device.name] = entry
        self._log(
            self._writer.write_json,
            "/events",
            now_gps_ns(),
            {"text": "status", "devices": devices, "records": dict(self.counts),
             "queue_dropped": self.ctx.dropped},
            "pnt.Event",
        )  # fmt: skip

    def stop(self) -> dict:
        """Stop every device, close the files, write the final meta.yaml; returns it."""
        self.ctx.stop.set()
        for s in self.devices:
            if s.thread:
                s.thread.join(timeout=15)
                if s.thread.is_alive():
                    s.state, s.reason = "failed", "did not stop within 15 s"
        self._abandon.set()
        if self._writer_thread:
            self._writer_thread.join()
        self._guarded("log device status", self._status_event)
        self._guarded("close session.mcap", self._writer.close)
        if self.streamer:
            self._guarded("stream the session meta", self._send_meta)
        meta = self.meta()
        self._guarded("write meta.yaml", session.write_meta, self.folder, meta)
        return meta

    def run(self, duration_s: float | None = None, stop: threading.Event | None = None) -> dict:
        """Record until `duration_s` passes, `stop` is set, or Ctrl-C."""
        self.start()
        t_end = None if duration_s is None else time.monotonic() + duration_s
        try:
            while t_end is None or time.monotonic() < t_end:
                if stop is not None and stop.is_set():
                    break
                if all(s.state in ("absent", "failed") for s in self.devices):
                    break  # nothing left to record
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        return self.stop()
