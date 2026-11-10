"""Day-1 checks on the Pi 4B (#88, #17): numbers only, from a named session.

- `report(session)`: IMU sample jitter, CPU load and temperature, free memory (the board has
  1 GB, ADR-0018), dropped SDR samples, PPS offset
  and chrony statistics, from what `pnt record` captured; USB current is typed in from the
  DPS-150. ADR-0018's thresholds are `TBD`, so this reports values and makes no pass/fail call.
- `pps_check()`: `ppstest` and `chronyc` run and parsed (#17, RSK-05).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_json, read_session
from pnt.payload.devices import SOURCES_FIELDS, TRACKING_FIELDS, parse_chrony_csv
from pnt.payload.sdr import estimate_t0, find_gaps, latency_ns

SOURCESTATS_FIELDS = (
    "name", "np", "nr", "span_s", "freq_ppm", "freq_skew_ppm", "offset_s", "std_dev_s",
)  # fmt: skip


def _stats(x, scale: float = 1.0, digits: int = 3) -> dict | None:
    """Summary of the numbers in `x` (None and text are skipped)."""
    vals = [v for v in x if isinstance(v, int | float | np.number) and not isinstance(v, bool)]
    x = np.asarray(vals, float) * scale
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return None
    return {
        "n": int(len(x)),
        "mean": round(float(x.mean()), digits),
        "std": round(float(x.std()), digits),
        "p99_abs": round(float(np.percentile(np.abs(x), 99)), digits),
        "max_abs": round(float(np.abs(x).max()), digits),
    }


def imu_timing(t_ns) -> dict | None:
    """Sample interval jitter (ms) and missed samples of a user-space-sampled IMU."""
    t = np.sort(np.asarray(t_ns, dtype=np.int64))
    if len(t) < 3:
        return None
    dt = np.diff(t) / 1e6
    nominal = float(np.median(dt))
    return {
        "samples": int(len(t)),
        "rate_hz": round(1e3 / nominal, 2),
        "interval_ms": round(nominal, 3),
        "jitter_ms": _stats(dt - nominal),
        "intervals_over_1.5x": int((dt > 1.5 * nominal).sum()),
        "max_interval_ms": round(float(dt.max()), 3),
    }


def sdr_timing(sidecar: dict) -> dict:
    """Dropped samples and timing of one SDR capture, from its sidecar."""
    fs = float(sidecar["sample_rate_hz"])
    b = np.asarray(sidecar.get("buffers") or [], dtype=np.int64).reshape(-1, 2)
    out = {"dongle": sidecar.get("dongle"), "samples": sidecar.get("samples"), "rate_hz": fs}
    if len(b) < 2:
        return {**out, "note": "fewer than 2 buffers"}
    gaps = find_gaps(b, fs)
    t0, ppm = estimate_t0(b, fs)
    lat = latency_ns(b, fs)
    for idx, n in gaps:  # a drop moves the envelope up for good: take it out
        lat[b[:, 0] >= idx] -= n * 1e9 / fs
    lat = lat - lat.min()
    span_s = (b[-1, 1] - b[0, 1]) / 1e9
    return {
        **out,
        "duration_s": round(float(span_s), 1),
        "gaps": len(gaps),
        "dropped_samples_est": int(sum(g[1] for g in gaps)),
        "first_gaps": gaps[:10],
        "rate_ppm_vs_host": round(ppm, 3),
        "latency_above_envelope_ms": _stats(lat, 1e-6),
        "t_ns": t0,
    }


def _events(path, text: str) -> list[dict]:
    return [e for _, e in read_json(session.mcap_path(path), ["/events"]) if e.get("text") == text]


def report(path: str | Path, usb_current_a: float | None = None) -> dict:
    """Day-1 numbers for a recorded session (folder)."""
    folder = Path(path)
    meta = session.read_meta(folder)
    mcap = session.mcap_path(folder)
    imu_t = [
        r.t_ns
        for _, r in read_session(mcap, topics=["/meas/imu"])
        if isinstance(r, Measurement) and r.kind == "accel_gyro"
    ]
    sdrs = [sdr_timing(json.loads(p.read_text())) for p in sorted(folder.glob("sdr_*.json"))]
    pps = _events(folder, "pps")
    health = _events(folder, "health")
    chrony = [h["chrony"] for h in health if isinstance(h.get("chrony"), dict)]
    status = _events(folder, "status")
    system = _events(folder, "system")
    out = {
        "session": folder.name,
        "commit": meta.get("commit"),
        "hardware": meta.get("hardware"),
        "notes": meta.get("notes"),
        "system": system[0] if system else None,
        "imu": imu_timing(imu_t),
        "sdr": sdrs,
        "pps": {
            "edges": len(pps),
            "offset_us": _stats([e["offset_ns"] for e in pps], 1e-3),
        },
        "chrony": {
            "system_time_us": _stats([c.get("system_time_s") for c in chrony], 1e6),
            "rms_offset_us": _stats([c.get("rms_offset_s") for c in chrony], 1e6),
            "ref_names": sorted({str(c.get("ref_name")) for c in chrony}),
        },
        "cpu": {
            "cpu_pct": _stats([h.get("cpu_pct") for h in health], 1.0, 1),
            "temp_c_max": max((h["temp_c"] for h in health if "temp_c" in h), default=None),
            "throttled": sorted({h["throttled"] for h in health if "throttled" in h}),
            "disk_free_gb_min": min(
                (h["disk_free_gb"] for h in health if "disk_free_gb" in h), default=None
            ),
            "mem_avail_mb_min": min(
                (h["mem_avail_mb"] for h in health if "mem_avail_mb" in h), default=None
            ),
        },
        "queue_dropped": status[-1].get("queue_dropped") if status else None,
        "usb_current_a": usb_current_a if usb_current_a is not None else "TBD (DPS-150)",
        "thresholds": "TBD (ADR-0018): values only, no pass/fail",
    }
    return out


def to_markdown(r: dict) -> str:
    def row(k, v):
        return f"| {k} | {v} |"

    lines = [
        f"# Day-1 report: {r['session']}",
        "",
        f"Commit `{r['commit']}`. Hardware: {r['hardware']}. Thresholds: {r['thresholds']}.",
        "",
        "| Quantity | Value |",
        "| --- | --- |",
    ]
    imu = r["imu"] or {}
    jit = imu.get("jitter_ms") or {}
    lines += [
        row("IMU rate (Hz)", imu.get("rate_hz")),
        row("IMU jitter std / p99 / max (ms)",
            f"{jit.get('std')} / {jit.get('p99_abs')} / {jit.get('max_abs')}"),
        row("IMU intervals > 1.5x nominal", imu.get("intervals_over_1.5x")),
    ]  # fmt: skip
    if not r["sdr"]:
        lines.append(row("SDR captures", "none in this session"))
    for s in r["sdr"]:
        lat = s.get("latency_above_envelope_ms") or {}
        lines += [
            row(f"{s['dongle']} gaps / dropped samples (est.)",
                f"{s.get('gaps')} / {s.get('dropped_samples_est')}"),
            row(f"{s['dongle']} rate vs host (ppm)", s.get("rate_ppm_vs_host")),
            row(f"{s['dongle']} latency p99 / max (ms)",
                f"{lat.get('p99_abs')} / {lat.get('max_abs')}"),
        ]  # fmt: skip
    pps = r["pps"]["offset_us"] or {}
    cpu = r["cpu"]["cpu_pct"] or {}
    rms = r["chrony"]["rms_offset_us"] or {}
    lines += [
        row("PPS edges seen (gpsd)", r["pps"]["edges"]),
        row("PPS offset mean / std / max (µs)",
            f"{pps.get('mean')} / {pps.get('std')} / {pps.get('max_abs')}"),
        row("chrony RMS offset mean / max (µs)", f"{rms.get('mean')} / {rms.get('max_abs')}"),
        row("chrony reference", ", ".join(r["chrony"]["ref_names"]) or None),
        row("CPU % mean / max", f"{cpu.get('mean')} / {cpu.get('max_abs')}"),
        row("Max SoC temperature (°C)", r["cpu"]["temp_c_max"]),
        row("Throttled flags", ", ".join(r["cpu"]["throttled"]) or None),
        row("Min free disk (GB)", r["cpu"]["disk_free_gb_min"]),
        row("Min available memory (MB)", r["cpu"].get("mem_avail_mb_min")),
        row("Records dropped (queue)", r["queue_dropped"]),
        row("USB current (A)", r["usb_current_a"]),
        row("libzmq CURVE", (r["system"] or {}).get("zmq_curve")),
    ]  # fmt: skip
    if r.get("notes"):
        lines += ["", "Notes:", "", *[f"- {n}" for n in str(r["notes"]).splitlines()]]
    return "\n".join(lines) + "\n"


# --- PPS check (#17) ------------------------------------------------------------------------

_ASSERT = re.compile(r"assert (\d+)\.(\d{9}), sequence: (\d+)")


def parse_ppstest(text: str) -> list[int]:
    """Assert times (Unix ns, host clock) from `ppstest` output."""
    return [int(a) * 1_000_000_000 + int(b) for a, b, _ in _ASSERT.findall(text)]


def pps_summary(asserts_ns: list[int]) -> dict:
    """Rate, interval jitter and offset of the host clock at each edge (µs).

    With chrony locked to PPS the edges land on whole seconds of the host clock, so the
    fraction of a second at each edge (wrapped to +/-0.5 s) is the clock's offset."""
    a = np.asarray(asserts_ns, dtype=np.int64)
    if len(a) < 2:
        return {"edges": int(len(a))}
    frac = ((a + 500_000_000) % 1_000_000_000 - 500_000_000) / 1e3
    iv = np.diff(a) / 1e9
    return {
        "edges": int(len(a)),
        "rate_hz": round(float(1 / np.median(iv)), 4),
        "interval_jitter_us": _stats((iv - 1.0) * 1e6),
        "offset_us": _stats(frac),
    }


def _capture(cmd: list[str], seconds: float) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds)
        return res.stdout + res.stderr
    except subprocess.TimeoutExpired as exc:  # ppstest runs until stopped
        out = exc.stdout or b""
        return out.decode() if isinstance(out, bytes) else out
    except OSError as exc:
        return f"error: {exc}"


def pps_check(seconds: float = 30.0, device: str = "/dev/pps0") -> dict:
    """Run `ppstest` for `seconds` and read chrony's view (needs the Pi; `sudo -n` for ppstest)."""
    text = _capture(["sudo", "-n", "ppstest", device], seconds)
    sources = parse_chrony_csv(_capture(["chronyc", "-c", "sources"], 10), SOURCES_FIELDS)
    stats = parse_chrony_csv(_capture(["chronyc", "-c", "sourcestats"], 10), SOURCESTATS_FIELDS)
    tracking = parse_chrony_csv(_capture(["chronyc", "-c", "tracking"], 10), TRACKING_FIELDS)
    pps_src = next((s for s in sources if s.get("name") == "PPS"), None)
    return {
        "ppstest": pps_summary(parse_ppstest(text)),
        "ppstest_tail": text.strip().splitlines()[-3:],
        "chronyc_ok": bool(tracking),
        "pps_source": pps_src,
        "pps_selected": bool(pps_src and pps_src.get("state") == "*"),
        "pps_sourcestats": next((s for s in stats if s.get("name") == "PPS"), None),
        "tracking": tracking[0] if tracking else None,
    }
