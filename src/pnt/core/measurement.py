"""Pipeline records (systems/icd/measurement.md, ADR-0006).

These three structs are the contract between capture/front-ends and nav/integrity.
Change them only together with the ICD, approved by both software owners.
"""

from __future__ import annotations

import msgspec

# Registries mirror systems/icd/measurement.md. They are open: add new names there first.
SOURCES = frozenset(
    {"gnss", "imu", "baro", "lte", "nr", "adsb", "vor", "wifi", "ble", "fm", "leo", "cam"}
)
KINDS = frozenset(
    {
        "position_enu",
        "velocity_enu",
        "accel_gyro",
        "altitude",
        "pseudorange",
        "range",
        "doppler",
        "bearing",
        "rssi",
        "time",
        "gnss_health",
        "adsb_report",
    }
)
# Which receiver produced a measurement (ADR-0020). Records written before this field existed
# decode as "payload", so every older session still loads unchanged.
RECEIVERS = frozenset({"payload", "reference"})


class Measurement(msgspec.Struct, frozen=True, kw_only=True):
    """One observable from one source."""

    t_ns: int
    source: str
    kind: str
    value: tuple[float, ...]
    sigma: tuple[float, ...]
    emitter: str = ""
    receiver: str = "payload"  # one of RECEIVERS
    meta: dict = {}


class Estimate(msgspec.Struct, kw_only=True):
    """Navigation output at one epoch."""

    t_ns: int
    pos_enu: tuple[float, float, float]
    vel_enu: tuple[float, float, float]
    pos_cov: tuple[float, ...]  # row-major 3x3, m^2
    clock_bias_s: float = 0.0
    clock_sigma_s: float | None = None  # None = not estimated (JSON has no NaN)
    hpl_m: float | None = None
    vpl_m: float | None = None
    status: str = "nominal"  # nominal | degraded | unsafe
    trust: dict[str, float] = {}
    flags: list[str] = []


class Truth(msgspec.Struct, frozen=True, kw_only=True):
    """Ground truth (simulation, or RTK in real sessions)."""

    t_ns: int
    pos_enu: tuple[float, float, float]
    vel_enu: tuple[float, float, float]
    clock_bias_s: float = 0.0


Record = Measurement | Estimate | Truth


def _enc_hook(obj):
    """Let numpy scalars and arrays through (producers often build values with numpy)."""
    if hasattr(obj, "item") and getattr(obj, "ndim", 1) == 0:
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise NotImplementedError(f"cannot encode {type(obj)}")


_json_enc = msgspec.json.Encoder(enc_hook=_enc_hook)
msgpack_encoder = msgspec.msgpack.Encoder(enc_hook=_enc_hook)


def to_json(record: Record) -> bytes:
    return _json_enc.encode(record)


def from_json(data: bytes, record_type: type[Record]) -> Record:
    return msgspec.json.decode(data, type=record_type)


def validate(m: Measurement) -> None:
    """Raise ValueError if a measurement breaks the ICD's basic rules."""
    if m.source not in SOURCES:
        raise ValueError(f"unknown source {m.source!r} (add it to the ICD first)")
    if m.kind not in KINDS:
        raise ValueError(f"unknown kind {m.kind!r} (add it to the ICD first)")
    if m.receiver not in RECEIVERS:
        raise ValueError(f"unknown receiver {m.receiver!r} (add it to the ICD first)")
    if len(m.value) != len(m.sigma):
        raise ValueError("value and sigma must have the same length")
    if any(s < 0 for s in m.sigma):
        raise ValueError("sigma must be non-negative")
