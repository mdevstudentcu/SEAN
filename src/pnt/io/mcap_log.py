"""MCAP session logs (ADR-0007, systems/icd/session.md).

Records are JSON-encoded with a JSON schema, so Foxglove opens the files directly.

A session that was cut off (power loss, `kill -9`, a full disk) has no footer. Every chunk the
writer finished is still in the file, so the readers below fall back to reading those in order
and warn. What such a cut loses is the chunk in progress: at most `CHUNK_SIZE` bytes of
uncompressed records, plus, on power loss, whatever the kernel had not yet written to the card.
`pnt record` also ends a chunk every few seconds (`recorder.FLUSH_PERIOD_S`), which bounds the
loss in time at low data rates.
"""

from __future__ import annotations

import json
import os
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO

import msgspec
from mcap.reader import NonSeekingReader, make_reader
from mcap.writer import MCAP0_MAGIC, Writer

from pnt.core.measurement import Estimate, Measurement, Record, Truth, to_json

_json_enc = msgspec.json.Encoder()
CHUNK_SIZE = 1024 * 1024  # uncompressed bytes per chunk (the mcap writer's default)

_TYPES: dict[str, type[Record]] = {
    "pnt.Measurement": Measurement,
    "pnt.Estimate": Estimate,
    "pnt.Truth": Truth,
}


class TruncatedSessionWarning(UserWarning):
    """A session file has no footer: it was cut off before `SessionWriter.close`."""


class SessionWriter:
    """Write records to an MCAP file; one channel per topic.

    Each finished chunk is passed to the operating system at once, so a killed process loses
    only the chunk in progress."""

    def __init__(self, path: str | Path, metadata: dict | None = None):
        self._file = open(path, "wb")  # noqa: SIM115 - closed in close()
        self._writer = Writer(self._file, chunk_size=CHUNK_SIZE)
        self._writer.start(profile="", library="pnt")
        self._schemas: dict[str, int] = {}
        self._channels: dict[str, int] = {}
        if metadata:
            self._writer.add_metadata("session", {k: str(v) for k, v in metadata.items()})
        self._file.flush()

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
        self._file.flush()  # no system call unless the writer just finished a chunk

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
        self._file.flush()

    def flush(self) -> None:
        """End the chunk in progress and hand it to the operating system (no fsync)."""
        self._writer.flush()

    def close(self) -> None:
        self._writer.finish()
        self._file.close()

    def __enter__(self) -> SessionWriter:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def is_complete(path: str | Path) -> bool:
    """True if the file ends in MCAP's closing magic: `SessionWriter.close` finished."""
    with open(path, "rb") as f:
        return _has_footer(f)


def _has_footer(f: IO[bytes]) -> bool:
    size = f.seek(0, os.SEEK_END)
    if size < 2 * len(MCAP0_MAGIC):
        f.seek(0)
        return False
    f.seek(-len(MCAP0_MAGIC), os.SEEK_END)
    closed = f.read() == MCAP0_MAGIC
    f.seek(0)
    return closed


def _salvage(f: IO[bytes], path, keep: Callable[[str], bool]) -> list:
    """The messages of every complete chunk of a file with no footer, in log-time order.

    `iter_messages` must run with `log_time_order=False`: with True it sorts first, so the end
    of file raises before a single message is returned."""
    out = []
    total = 0
    try:
        for item in NonSeekingReader(f, validate_crcs=True).iter_messages(log_time_order=False):
            total += 1
            if keep(item[1].topic):
                out.append(item)
    except Exception:  # whatever the torn tail looks like, the good chunks end here
        pass
    warnings.warn(
        f"{path} was cut off before it was closed (no MCAP footer): read {total} records, up "
        f"to the last complete chunk",
        TruncatedSessionWarning,
        stacklevel=3,
    )
    out.sort(key=lambda item: item[2].log_time)
    return out


def _messages(f: IO[bytes], path, keep: Callable[[str], bool]) -> Iterator[tuple]:
    """(schema, channel, message) for the wanted topics, in log-time order."""
    if not _has_footer(f):
        yield from _salvage(f, path, keep)
        return
    for item in make_reader(f).iter_messages(log_time_order=True):
        if keep(item[1].topic):
            yield item


def _topic_filter(topics: list[str] | None) -> Callable[[str], bool]:
    """Exact names, or prefixes ending in '/'."""

    def keep(topic: str) -> bool:
        return not topics or any(
            topic == t or (t.endswith("/") and topic.startswith(t)) for t in topics
        )

    return keep


def read_metadata(path: str | Path) -> dict[str, str]:
    """The session metadata written by SessionWriter ({} if the file has none)."""
    with open(path, "rb") as f:
        reader = make_reader(f) if _has_footer(f) else NonSeekingReader(f)
        try:
            for record in reader.iter_metadata():
                if record.name == "session":
                    return dict(record.metadata)
        except Exception:  # no footer: the end of what was written
            pass
    return {}


def read_session(
    path: str | Path, topics: list[str] | None = None
) -> Iterator[tuple[str, Record]]:
    """Yield (topic, record) in log-time order. `topics` filters by exact name or prefix ending
    in '/' (e.g. '/meas/'). A session cut off before close yields its complete chunks and
    warns (`TruncatedSessionWarning`)."""
    with open(path, "rb") as f:
        for schema, channel, message in _messages(f, path, _topic_filter(topics)):
            record_type = _TYPES.get(schema.name if schema else "")
            if record_type is None:
                continue
            yield channel.topic, msgspec.json.decode(message.data, type=record_type)


def read_json(path: str | Path, topics: list[str]) -> Iterator[tuple[str, dict]]:
    """Yield (topic, dict) for JSON topics written by `SessionWriter.write_json`, in log-time
    order. `topics` match as in `read_session`; a cut-off session is read as there."""
    with open(path, "rb") as f:
        for schema, channel, message in _messages(f, path, _topic_filter(topics)):
            if schema is None or schema.name in _TYPES:
                continue
            yield channel.topic, json.loads(message.data)
