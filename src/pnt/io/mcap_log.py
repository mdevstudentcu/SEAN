"""MCAP session logs (ADR-0007, systems/icd/session.md).

Records are JSON-encoded with a JSON schema, so Foxglove opens the files directly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import msgspec
from mcap.reader import make_reader
from mcap.writer import Writer

from pnt.core.measurement import Estimate, Measurement, Record, Truth, to_json

_json_enc = msgspec.json.Encoder()

_TYPES: dict[str, type[Record]] = {
    "pnt.Measurement": Measurement,
    "pnt.Estimate": Estimate,
    "pnt.Truth": Truth,
}


class SessionWriter:
    """Write records to an MCAP file; one channel per topic."""

    def __init__(self, path: str | Path, metadata: dict | None = None):
        self._file = open(path, "wb")  # noqa: SIM115 - closed in close()
        self._writer = Writer(self._file)
        self._writer.start(profile="", library="pnt")
        self._schemas: dict[str, int] = {}
        self._channels: dict[str, int] = {}
        if metadata:
            self._writer.add_metadata("session", {k: str(v) for k, v in metadata.items()})

    def _schema_id(self, record_type: type[Record]) -> int:
        name = f"pnt.{record_type.__name__}"
        if name not in self._schemas:
            schema = msgspec.json.schema(record_type)
            self._schemas[name] = self._writer.register_schema(
                name=name, encoding="jsonschema", data=json.dumps(schema).encode()
            )
        return self._schemas[name]

    def write(self, topic: str, record: Record) -> None:
        if topic not in self._channels:
            self._channels[topic] = self._writer.register_channel(
                topic=topic, message_encoding="json", schema_id=self._schema_id(type(record))
            )
        t = max(record.t_ns, 0)
        self._writer.add_message(
            channel_id=self._channels[topic], log_time=t, publish_time=t, data=to_json(record)
        )

    def write_json(self, topic: str, t_ns: int, data: dict, schema: str = "pnt.Event") -> None:
        """A record that is not a `Record` (ICD-session): `/events` markers and `/mavlink/fc`
        messages. `read_session` skips these; `read_json` reads them."""
        if topic not in self._channels:
            if schema not in self._schemas:
                self._schemas[schema] = self._writer.register_schema(
                    name=schema, encoding="jsonschema", data=b'{"type": "object"}'
                )
            self._channels[topic] = self._writer.register_channel(
                topic=topic, message_encoding="json", schema_id=self._schemas[schema]
            )
        t = max(int(t_ns), 0)
        self._writer.add_message(
            channel_id=self._channels[topic],
            log_time=t,
            publish_time=t,
            data=_json_enc.encode({"t_ns": int(t_ns), **data}),
        )

    def close(self) -> None:
        self._writer.finish()
        self._file.close()

    def __enter__(self) -> SessionWriter:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_metadata(path: str | Path) -> dict[str, str]:
    """The session metadata written by SessionWriter ({} if the file has none)."""
    with open(path, "rb") as f:
        for record in make_reader(f).iter_metadata():
            if record.name == "session":
                return dict(record.metadata)
    return {}


def read_session(
    path: str | Path, topics: list[str] | None = None
) -> Iterator[tuple[str, Record]]:
    """Yield (topic, record) in log-time order. `topics` filters by exact name or prefix ending
    in '/' (e.g. '/meas/')."""
    with open(path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages(log_time_order=True):
            if topics and not any(
                channel.topic == t or (t.endswith("/") and channel.topic.startswith(t))
                for t in topics
            ):
                continue
            record_type = _TYPES.get(schema.name if schema else "")
            if record_type is None:
                continue
            yield channel.topic, msgspec.json.decode(message.data, type=record_type)


def read_json(path: str | Path, topics: list[str]) -> Iterator[tuple[str, dict]]:
    """Yield (topic, dict) for JSON topics written by `SessionWriter.write_json`, in log-time
    order. `topics` match as in `read_session`."""
    with open(path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages(log_time_order=True):
            if schema is None or schema.name in _TYPES:
                continue
            if any(
                channel.topic == t or (t.endswith("/") and channel.topic.startswith(t))
                for t in topics
            ):
                yield channel.topic, json.loads(message.data)
