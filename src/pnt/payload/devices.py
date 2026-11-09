"""The other captures: camera, flight-controller MAVLink, and the recorder's own health.

All receive only (REQ-07). The flight-controller link is read, never written: nothing here sends
a MAVLink message.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from pnt.core.time import now_gps_ns

# --- health ---------------------------------------------------------------------------------

TRACKING_FIELDS = (
    "ref_id", "ref_name", "stratum", "ref_time", "system_time_s", "last_offset_s",
    "rms_offset_s", "freq_ppm", "resid_freq_ppm", "skew_ppm", "root_delay_s",
    "root_dispersion_s", "update_interval_s", "leap_status",
)  # fmt: skip
SOURCES_FIELDS = (
    "mode", "state", "name", "stratum", "poll", "reach", "last_rx", "adjusted_offset_s",
    "measured_offset_s", "error_s",
)  # fmt: skip


def _num(v: str):
    try:
        return float(v)
    except ValueError:
        return v


def parse_chrony_csv(text: str, fields: tuple[str, ...]) -> list[dict]:
    """`chronyc -c tracking` (one row) or `chronyc -c sources` (one row per source)."""
    rows = []
    for line in text.strip().splitlines():
        if "," not in line:  # an error message, not a CSV row
            continue
        parts = line.split(",")
        rows.append({k: _num(v) for k, v in zip(fields, parts, strict=False)})
    return rows


def _run(cmd: list[str], timeout: float = 5.0) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def clock_status() -> str:
    """One line on the host clock for meta.yaml: is chrony locked to PPS? Every timestamp in
    the session depends on it (ASM-04). The Pi has no RTC, so before lock it can be far off."""
    txt = _run(["chronyc", "-c", "tracking"])
    rows = parse_chrony_csv(txt, TRACKING_FIELDS) if txt else []
    if not rows:
        return "clock at start: chronyc not available, sync unknown"
    t = rows[0]
    ok = t.get("ref_name") == "PPS" and t.get("leap_status") == "Normal"
    return (
        f"clock at start: {'locked to PPS' if ok else 'NOT locked to PPS'} "
        f"(ref {t.get('ref_name')}, offset {t.get('system_time_s')} s, "
        f"leap {t.get('leap_status')})"
    )


def cpu_times() -> tuple[int, int] | None:
    """(busy, total) jiffies from /proc/stat."""
    try:
        with open("/proc/stat") as f:
            vals = [int(x) for x in f.readline().split()[1:]]
    except OSError:
        return None
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return sum(vals) - idle, sum(vals)


def system_info() -> dict:
    info = {"python": platform.python_version(), "kernel": platform.release()}
    try:
        info["model"] = Path("/proc/device-tree/model").read_text().strip("\x00\n")
    except OSError:
        info["model"] = platform.machine()
    try:
        import zmq

        info["zmq"] = zmq.zmq_version()
        info["zmq_curve"] = bool(zmq.has("curve"))  # ADR-0026: checked on day 1 (#88)
    except ImportError:
        info["zmq"] = None
    return info


class Health:
    """CPU load, temperature, throttling, memory, disk and chrony, once a second, to `/events`."""

    name = "health"
    hardware = "host"

    def __init__(self, folder_for_disk: str | Path = ".", period_s: float = 1.0):
        self.folder = Path(folder_for_disk)
        self.period_s = period_s
        self.samples = 0

    def probe(self) -> str | None:
        return None

    def status(self) -> dict:
        return {"samples": self.samples}

    def sample(self, prev) -> tuple[dict, tuple | None]:
        out: dict = {"text": "health"}
        cur = cpu_times()
        if cur and prev:
            busy, total = cur[0] - prev[0], cur[1] - prev[1]
            out["cpu_pct"] = round(100.0 * busy / total, 1) if total else None
        try:
            out["load1"] = os.getloadavg()[0]
        except OSError:
            pass
        try:
            out["temp_c"] = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1e3
        except (OSError, ValueError):
            pass
        try:
            st = shutil.disk_usage(self.folder)
            out["disk_free_gb"] = round(st.free / 1e9, 2)
        except OSError:
            pass
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    out["mem_avail_mb"] = int(line.split()[1]) // 1024
        except OSError:
            pass
        return out, cur

    def run(self, ctx) -> None:
        self.folder = Path(ctx.folder)
        ctx.event(now_gps_ns(), "system", **system_info())
        prev = cpu_times()
        n = 0
        while not ctx.stop.wait(self.period_s):
            data, prev = self.sample(prev)
            if n % 10 == 0:
                if (txt := _run(["chronyc", "-c", "tracking"])) is not None:
                    rows = parse_chrony_csv(txt, TRACKING_FIELDS)
                    data["chrony"] = rows[0] if rows else None
                if (txt := _run(["vcgencmd", "get_throttled"])) is not None:
                    data["throttled"] = txt.strip().split("=")[-1]
            n += 1
            self.samples += 1
            ctx.event(now_gps_ns(), **data)


# --- camera ---------------------------------------------------------------------------------


def _dies_with_parent(cmd: list[str]) -> list[str]:
    """Have the kernel send `cmd` SIGINT if the recorder is killed outright (`setpriv`, from
    util-linux, is on every Pi OS). The camera runs in its own session and writes to a file, so
    nothing else would stop it from filling the card. Linux only."""
    if sys.platform == "linux" and shutil.which("setpriv"):
        return ["setpriv", "--pdeathsig", "INT", *cmd]
    return cmd


class Camera:
    """Pi camera to `camera.mp4` with `camera.json` (ICD-session) through `rpicam-vid`.

    `camera.json` `t_ns` is the host time when the file first grew, an upper bound on the first
    frame's time; frame-accurate timing is `TBD`."""

    name = "camera"
    hardware = "pi-camera"

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30, cmd=None):
        self.width, self.height, self.fps = width, height, fps
        self.cmd = cmd
        self.proc: subprocess.Popen | None = None

    def command(self, out: Path) -> list[str]:
        if self.cmd:
            return [*self.cmd, str(out)]
        return [
            "rpicam-vid", "-n", "-t", "0", "--width", str(self.width), "--height",
            str(self.height), "--framerate", str(self.fps), "--codec", "libav", "-o", str(out),
        ]  # fmt: skip

    def probe(self) -> str | None:
        if self.cmd:
            return None
        if shutil.which("rpicam-vid") is None:
            return "rpicam-vid not installed"
        out = _run(["rpicam-hello", "--list-cameras"], timeout=15) or ""
        if "Available cameras" not in out:
            return "no camera listed by rpicam-hello --list-cameras"
        return None

    def status(self) -> dict:
        return {"running": self.proc is not None and self.proc.poll() is None}

    def run(self, ctx) -> None:
        out = Path(ctx.folder) / "camera.mp4"
        log = tempfile.TemporaryFile()  # noqa: SIM115 - closed below; tail goes to /events
        t_launch = now_gps_ns()
        self.proc = subprocess.Popen(  # own session: Ctrl-C is for the recorder, which stops it
            _dies_with_parent(self.command(out)),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        side = {"t_ns": None, "t_ns_launch": t_launch, "width": self.width,
                "height": self.height, "fps": self.fps,
                "t_ns_method": "host time the file first grew (upper bound); TBD"}  # fmt: skip
        try:
            while not ctx.stop.wait(0.05):
                if side["t_ns"] is None and out.exists() and out.stat().st_size > 0:
                    side["t_ns"] = now_gps_ns()
                    (Path(ctx.folder) / "camera.json").write_text(json.dumps(side))
                if self.proc.poll() is not None:
                    raise RuntimeError(f"rpicam-vid exited with {self.proc.returncode}")
        finally:
            if self.proc.poll() is None:
                self.proc.send_signal(signal.SIGINT)  # lets it finish the mp4
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 2000))
            tail = log.read().decode(errors="replace").splitlines()[-5:]
            log.close()
            (Path(ctx.folder) / "camera.json").write_text(json.dumps(side))
            ctx.event(now_gps_ns(), "camera stopped", output=tail)


# --- flight controller ----------------------------------------------------------------------

FC_PATTERNS = ("ArduPilot", "ardupilot", "CubePilot", "Pixhawk", "Holybro", "mRo", "fmu")


def find_fc() -> str | None:
    """A USB-connected flight controller under /dev/serial/by-id (never the GPS UART)."""
    by_id = Path("/dev/serial/by-id")
    if not by_id.is_dir():
        return None
    for p in sorted(by_id.iterdir()):
        # CubePilot boards also list a second (SLCAN) interface, if02: not MAVLink
        if any(s in p.name for s in FC_PATTERNS) and "if02" not in p.name:
            return str(p)
    return None


class FlightController:
    """ArduPilot telemetry to `/mavlink/fc`, decoded to JSON (ICD-session). Listen only."""

    name = "fc"
    hardware = "flight-controller"

    def __init__(self, device: str | None = None, baud: int = 115200):
        self.device, self.baud = device, baud
        self.messages = 0

    def probe(self) -> str | None:
        if self.device is None:
            self.device = find_fc()
        if self.device is None:
            return "no flight controller under /dev/serial/by-id (give --fc)"
        if ":" not in self.device and not Path(self.device).exists():
            return f"{self.device} does not exist"
        return None

    def status(self) -> dict:
        return {"messages": self.messages}

    def run(self, ctx) -> None:
        from pymavlink import mavutil  # payload extra

        conn = mavutil.mavlink_connection(self.device, baud=self.baud, autoreconnect=True)
        try:
            while not ctx.stop.is_set():
                msg = conn.recv_match(blocking=True, timeout=1.0)
                if msg is None or msg.get_type() == "BAD_DATA":
                    continue
                self.messages += 1
                ctx.raw("/mavlink/fc", now_gps_ns(), msg.to_dict(), "pnt.MavlinkFC")
        finally:
            conn.close()
