"""Companion Foxglove file for a session (issue #6, ADR-0010): `pnt viz <session>`.

Our session records use local ENU metres and our own schemas, which Foxglove's Map panel cannot
draw. This writes a separate `viz.mcap` in Foxglove's schemas, leaving the session untouched, so
`systems/icd/session.md` does not change. Lat/lon appears only here, for display (ADR-0008).

Topics, all stamped with the session's GPS-time log time:
- /viz/truth, /viz/estimate: foxglove.LocationFix
- /viz/towers: foxglove.GeoJSON, published once, because the viewer keeps every message it draws
- /viz/nav: error, HPL, status, alarm, fault state and which towers are lost, for the panels
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml
from mcap.writer import Writer

from pnt.core.frames import emitter_enu, enu_to_llh
from pnt.core.measurement import Estimate, Measurement, Truth
from pnt.core.time import s_to_ns
from pnt.io import session as session_io
from pnt.io.mcap_log import read_metadata, read_session

ALARM_FLAGS = {"gnss_excluded", "spoof_suspected", "time_spoof_suspected"}
STATUS_CODE = {"nominal": 0, "degraded": 1, "unsafe": 2}
TOWER_HEARD_WITHIN_NS = s_to_ns(2.5)  # a tower is "heard" if it reported this recently

_TIME = {
    "type": "object",
    "title": "time",
    "properties": {"sec": {"type": "integer"}, "nsec": {"type": "integer"}},
}
_COLOR = {
    "type": "object",
    "title": "foxglove.Color",
    "properties": {c: {"type": "number"} for c in "rgba"},
}
LOCATION_FIX_SCHEMA = {
    "title": "foxglove.LocationFix",
    "type": "object",
    "properties": {
        "timestamp": _TIME,
        "frame_id": {"type": "string"},
        "latitude": {"type": "number"},
        "longitude": {"type": "number"},
        "altitude": {"type": "number"},
        "position_covariance": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 9,
            "maxItems": 9,
        },
        "position_covariance_type": {"type": "integer"},
        "color": _COLOR,
    },
    "required": [
        "timestamp",
        "frame_id",
        "latitude",
        "longitude",
        "altitude",
        "position_covariance",
        "position_covariance_type",
    ],
}
GEOJSON_SCHEMA = {
    "title": "foxglove.GeoJSON",
    "type": "object",
    "properties": {"geojson": {"type": "string"}},
    "required": ["geojson"],
}
NAV_SCHEMA = {
    "title": "pnt.VizNav",
    "type": "object",
    "properties": {
        "h_error_m": {"type": "number"},
        "hpl_m": {"type": "number"},
        "status": {"type": "string"},
        "status_code": {"type": "integer"},
        "alarm": {"type": "integer"},
        "fault_active": {"type": "integer"},
        "towers_heard": {"type": "integer"},
        "towers_lost": {"type": "string"},
        "flags": {"type": "string"},
    },
}

COVARIANCE_KNOWN = 3
COVARIANCE_UNKNOWN = 0
TRUTH_COLOR = {"r": 0.13, "g": 0.65, "b": 0.31, "a": 1.0}
ESTIMATE_COLOR = {"r": 0.95, "g": 0.45, "b": 0.10, "a": 1.0}


def default_output(path: str | Path) -> Path:
    p = Path(path)
    return p / "viz.mcap" if p.is_dir() else p.with_suffix(".viz.mcap")


def _stamp(t_ns: int) -> dict:
    return {"sec": t_ns // 1_000_000_000, "nsec": t_ns % 1_000_000_000}


def _fix(t_ns, llh, color, cov=None) -> dict:
    return {
        "timestamp": _stamp(t_ns),
        "frame_id": "wgs84",
        "latitude": float(llh[0]),
        "longitude": float(llh[1]),
        "altitude": float(llh[2]),
        "position_covariance": [float(c) for c in cov] if cov is not None else [0.0] * 9,
        "position_covariance_type": COVARIANCE_KNOWN if cov is not None else COVARIANCE_UNKNOWN,
        "color": color,
    }


def _towers_geojson(towers: dict) -> str:
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(llh[1]), float(llh[0])]},
            "properties": {"name": emitter},
        }
        for emitter, llh in sorted(towers.items())
    ]
    return json.dumps({"type": "FeatureCollection", "features": features})


class _VizWriter:
    def __init__(self, f):
        self._w = Writer(f)
        self._w.start(profile="", library="pnt-viz")
        self._channels: dict[str, int] = {}

    def channel(self, topic: str, schema: dict) -> None:
        sid = self._w.register_schema(
            name=schema["title"], encoding="jsonschema", data=json.dumps(schema).encode()
        )
        self._channels[topic] = self._w.register_channel(
            topic=topic, message_encoding="json", schema_id=sid
        )

    def write(self, topic: str, t_ns: int, payload: dict) -> None:
        self._w.add_message(
            channel_id=self._channels[topic],
            log_time=t_ns,
            publish_time=t_ns,
            data=json.dumps(payload).encode(),
        )

    def finish(self) -> None:
        self._w.finish()


def write_viz(
    session: str | Path,
    out: str | Path,
    estimator: str = "baseline",
    fault_windows: list[tuple[int, int | None]] | None = None,
) -> dict:
    """Write the companion file. `fault_windows` are (start_ns, end_ns or None). Returns counts."""
    path = session_io.mcap_path(session)
    origin = yaml.safe_load(read_metadata(path).get("origin_llh", "null"))
    if origin is None:
        raise ValueError(f"{path} has no origin_llh in its metadata, so it can't be put on a map")

    truth, estimates, heard_at, towers = {}, [], {}, {}
    nav_topic = f"/nav/{estimator}"
    for topic, rec in read_session(path, topics=["/truth", nav_topic, "/meas/"]):
        if isinstance(rec, Truth):
            truth[rec.t_ns] = rec
        elif isinstance(rec, Estimate) and topic == nav_topic:
            estimates.append(rec)
        elif isinstance(rec, Measurement) and rec.kind == "pseudorange":
            heard_at.setdefault(rec.emitter, []).append(rec.t_ns)
            if rec.emitter not in towers:
                enu = emitter_enu(rec.meta, origin)
                if enu is not None:
                    towers[rec.emitter] = enu_to_llh(enu, origin)
    if not estimates:
        raise ValueError(f"{path} has no estimates on {nav_topic}")

    heard_at = {e: np.array(sorted(t)) for e, t in heard_at.items()}
    windows = fault_windows or []

    def heard(t_ns: int) -> set[str]:
        out_set = set()
        for emitter, times in heard_at.items():
            i = np.searchsorted(times, t_ns, side="right")
            if i and t_ns - int(times[i - 1]) <= TOWER_HEARD_WITHIN_NS:
                out_set.add(emitter)
        return out_set

    with open(out, "wb") as f:
        w = _VizWriter(f)
        w.channel("/viz/truth", LOCATION_FIX_SCHEMA)
        w.channel("/viz/estimate", LOCATION_FIX_SCHEMA)
        w.channel("/viz/towers", GEOJSON_SCHEMA)
        w.channel("/viz/nav", NAV_SCHEMA)
        n_truth = 0
        if towers:
            w.write("/viz/towers", estimates[0].t_ns, {"geojson": _towers_geojson(towers)})
        for e in estimates:
            g = truth.get(e.t_ns)
            if g is not None:
                w.write(
                    "/viz/truth", e.t_ns, _fix(e.t_ns, enu_to_llh(g.pos_enu, origin), TRUTH_COLOR)
                )
                n_truth += 1
            w.write(
                "/viz/estimate",
                e.t_ns,
                _fix(e.t_ns, enu_to_llh(e.pos_enu, origin), ESTIMATE_COLOR, e.pos_cov),
            )
            current = heard(e.t_ns)
            nav = {
                "status": e.status,
                "status_code": STATUS_CODE.get(e.status, -1),
                "alarm": int(bool(ALARM_FLAGS & set(e.flags))),
                "fault_active": int(
                    any(s <= e.t_ns and (end is None or e.t_ns < end) for s, end in windows)
                ),
                "towers_heard": len(current),
                "towers_lost": ",".join(sorted(set(heard_at) - current)) or "none",
                "flags": ",".join(e.flags),
            }
            if e.hpl_m is not None:
                nav["hpl_m"] = e.hpl_m
            if g is not None:
                nav["h_error_m"] = float(np.hypot(*np.subtract(e.pos_enu, g.pos_enu)[:2]))
            w.write("/viz/nav", e.t_ns, nav)
        w.finish()
    return {"estimates": len(estimates), "truth": n_truth, "towers": len(towers)}
