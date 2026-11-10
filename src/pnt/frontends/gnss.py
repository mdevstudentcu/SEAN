"""GNSS front end (#22): gpsd reports -> `gnss` records, including `gnss_health` (ADR-0031).

Two inputs, both in gpsd's JSON protocol (https://gpsd.io/gpsd_json.html):

- **A recorded session.** The payload (`pnt.payload.gpsd`) already writes `position_enu` and
  `velocity_enu` to `/meas/gnss`, and each SKY report to `/events` as `gnss_sky` (per-PRN SNR,
  satellites used, HDOP), stamped on arrival. `derive_session` turns those events into
  `gnss_health` records in a new session (ICD-session, *Derived sessions*).
- **A gpsd log**: one gpsd report per line, as `gpspipe -w` prints them. `from_gpsd_json` gives
  `position_enu` and `velocity_enu` through the payload's own TPV parser, so both paths agree,
  and `gnss_health` from each SKY report.

`gnss_health` value (ICD-measurement): `(jam_indicator, n_sats, hdop)`.

- `jam_indicator` in [0, 1] (ADR-0031): how far the strongest satellites' C/N0 has fallen from
  its open-sky level. `S` is the mean of the `TOP_K` strongest C/N0 values; a satellite missing
  from those `TOP_K` counts as `LOW_CN0_DBHZ`. Then `(REF_CN0_DBHZ - S) / (REF - LOW)`, clipped:
  0 at or above the open-sky level, 1 at the level where satellites are lost.
  It cannot tell jamming from blockage: both lower C/N0.
- `n_sats`: satellites used in the fix. `hdop`: gpsd's, or `NO_FIX_HDOP` when it gives none.

gpsd's SKY `satellites` list is optional (https://gpsd.io/gpsd_json.html). A SKY report without
one says nothing about C/N0, so it gives no record: in a log, the list is absent; in a recorded
event, `n_seen` is 0 while `hdop` is given (`has_skyview`). An empty list with no DOPs is a sky
with nothing in it, and gives indicator 1. If gpsd sends no SKY at all, there is no record.

The MediaTek receiver on the GPS HAT reports C/N0 per satellite in NMEA GSV, which gpsd passes
on as `ss` (dB-Hz); it has no jamming flag of its own (ADR-0014). Only broadcast navigation
fields are read (ADR-0011).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import msgspec

from pnt.core.measurement import Measurement
from pnt.payload import gpsd

# ADR-0031. All three are TBC until a static open-sky session with the GPS HAT measures them.
REF_CN0_DBHZ = 40.0  # TBC: open-sky mean C/N0 of the TOP_K strongest satellites
LOW_CN0_DBHZ = 25.0  # TBC: C/N0 at which the receiver loses satellites (indicator 1)
TOP_K = 4  # TBC: the satellites a 3D fix needs
# What receivers conventionally report with no geometry (the sim's `NO_FIX_HDOP` too).
NO_FIX_HDOP = 99.0
# Schemas of the JSON topics the recorder writes (ICD-session), kept when a session is copied.
JSON_SCHEMAS = {"/mavlink/fc": "pnt.MavlinkFC"}


def jam_indicator(
    snr_dbhz: Iterable[float | None],
    ref: float = REF_CN0_DBHZ,
    low: float = LOW_CN0_DBHZ,
    k: int = TOP_K,
) -> float:
    """C/N0 drop of the `k` strongest satellites, scaled to [0, 1] (ADR-0031).

    `snr_dbhz` is every satellite gpsd lists; `None` or 0 means not tracked."""
    if not ref > low or k < 1:
        raise ValueError("need ref > low and k >= 1")
    tracked = sorted((float(s) for s in snr_dbhz if s is not None and s > 0), reverse=True)
    top = tracked[:k] + [low] * max(0, k - len(tracked))
    s = sum(top) / k
    return min(1.0, max(0.0, (ref - s) / (ref - low)))


def has_skyview(sky: dict) -> bool:
    """False for a recorded `gnss_sky` event made from a SKY report with DOPs but no satellite
    list: it carries no C/N0 to judge."""
    return bool(sky.get("n_seen")) or sky.get("hdop") is None


def health(t_ns: int, sky: dict, receiver: str = "payload", **params) -> Measurement:
    """One `gnss_health` record from a `gnss_sky` event (`pnt.payload.gpsd.sky_event`).

    `params` are `jam_indicator`'s `ref`, `low` and `k`."""
    snr = sky.get("snr") or {}
    hdop = sky.get("hdop")
    jam = jam_indicator(snr.values(), **params)
    return Measurement(
        t_ns=int(t_ns),
        source="gnss",
        kind="gnss_health",
        receiver=receiver,
        value=(jam, float(sky.get("n_used") or 0), NO_FIX_HDOP if hdop is None else float(hdop)),
        sigma=(0.0, 0.0, 0.0),  # a report, as in the sim: no noise model of its own
        meta={
            "device": "gpsd",
            "n_seen": sky.get("n_seen"),
            "snr": snr,
            "ref_cn0_dbhz": params.get("ref", REF_CN0_DBHZ),
        },
    )


def from_gpsd_json(
    lines: Iterable[str], origin_llh, receiver: str = "payload", **params
) -> list[Measurement]:
    """`gpspipe -w` output -> `position_enu`, `velocity_enu` and `gnss_health` records.

    TPV becomes fixes as on the payload, skipping repeated reports of one fix. A SKY report is
    stamped with its own `time`, or else with the last TPV's (gpsd sends SKY after the TPV of
    the same epoch); one before any TPV, or with no satellite list, is skipped."""
    out: list[Measurement] = []
    last_tpv_t: int | None = None
    last_tpv: str | None = None
    for line in lines:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        cls = msg.get("class") if isinstance(msg, dict) else None
        if cls == "TPV" and msg.get("time"):
            if msg["time"] == last_tpv:
                continue
            last_tpv = msg["time"]
            last_tpv_t = gpsd.parse_time(msg["time"])
            out += gpsd.tpv_measurements(msg, origin_llh)
        elif cls == "SKY" and "satellites" in msg:
            t = gpsd.parse_time(msg["time"]) if msg.get("time") else last_tpv_t
            if t is not None:
                out.append(health(t, gpsd.sky_event(msg), **params))
    if receiver != "payload":
        out = [msgspec.structs.replace(m, receiver=receiver) for m in out]
    return out


def derive_session(src: Path, out: Path, commit: str, **params) -> list[Measurement]:
    """Add `gnss_health` from `src`'s `gnss_sky` events and write a new session to `out`.

    `src` is never changed. Every record and JSON message (`/events`, `/mavlink/fc`) of `src` is
    copied, except earlier `gnss_health` records, which these replace. The new records take
    the receiver of `src`'s own `/meas/gnss` records (`payload` if it has none). Returns them."""
    from pnt.io import session
    from pnt.io.mcap_log import SessionWriter, read_json, read_session

    src = Path(src)
    mcap = src / session.MCAP_NAME
    records = [
        (topic, r)
        for topic, r in read_session(mcap)
        if not (topic == "/meas/gnss" and getattr(r, "kind", "") == "gnss_health")
    ]
    events = list(read_json(mcap, []))
    receiver = _session_receiver(records)
    new = [
        health(d["t_ns"], d, receiver=receiver, **params)
        for topic, d in events
        if topic == "/events" and d.get("text") == "gnss_sky" and "t_ns" in d and has_skyview(d)
    ]
    src_meta = session.read_meta(src)
    note = f"GNSS health front end on {src.name} at {commit}"
    meta = {k: src_meta.get(k) for k in session.META_KEYS}
    meta.update(
        name=out.name,
        commit=commit,
        notes=f"{src_meta['notes']}; {note}" if src_meta.get("notes") else note,
    )
    out.mkdir(parents=True, exist_ok=True)
    session.write_meta(out, meta)
    mcap_meta = {k: v for k, v in meta.items() if v is not None and k != "name"}
    with SessionWriter(out / session.MCAP_NAME, metadata=mcap_meta) as w:
        for topic, r in records:
            w.write(topic, r)
        for m in new:
            w.write("/meas/gnss", m)
        for topic, d in events:
            data = {k: v for k, v in d.items() if k != "t_ns"}
            w.write_json(topic, d["t_ns"], data, JSON_SCHEMAS.get(topic, "pnt.Event"))
    return new


def _session_receiver(records) -> str:
    """The receiver of the session's own GNSS fixes (`payload` if it has none)."""
    for topic, r in records:
        if topic == "/meas/gnss":
            return getattr(r, "receiver", "payload")
    return "payload"


def summary(records: list[Measurement]) -> str:
    h = [m for m in records if m.kind == "gnss_health"]
    if not h:
        return "no gnss_health records (no SKY reports)"
    jam = sorted(m.value[0] for m in h)
    sats = [m.value[1] for m in h]
    return (
        f"{len(h)} gnss_health records: jam indicator min {jam[0]:.2f}, "
        f"median {jam[len(jam) // 2]:.2f}, max {jam[-1]:.2f}; "
        f"satellites used {min(sats):.0f} to {max(sats):.0f}"
    )
