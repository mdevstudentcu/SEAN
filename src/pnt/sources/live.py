from __future__ import annotations

import heapq
import json
import time
from collections.abc import Iterator, Sequence

import msgspec

from pnt.core.measurement import Measurement

DEFAULT_ENDPOINT = "tcp://pnt.local:5556"
# How long a record may arrive after a later-stamped one and still be put in order. GNSS fixes
# arrive ~0.1-1 s after their time of validity; IMU samples at once. Latency cost on REQ-05:
# TBC on the day-1 session (#88).
REORDER_S = 1.0


class LiveSource:
    """Measurements streamed by the payload and the reference station over ZeroMQ (ADR-0009).

    Subscribes to every endpoint (one per Pi). Records from different devices arrive slightly
    out of order, so they are held for `reorder_s` and released in time order: the stream this
    yields is time-ordered like sim and replay (ADR-0004). A record older than one already
    released is dropped and counted in `stats["late"]`.

    `meta` holds the latest session metadata each receiver sent (origin, hardware, notes).
    With `idle_timeout_s`, iteration ends after that long with nothing received.

    With `auth` (a `pnt.io.linkauth.ClientAuth`, ADR-0026) each endpoint is reached over CurveZMQ
    with its server key pinned: only a host holding that key's secret completes the handshake,
    so nothing from an impersonator or a tampered connection is ever read.
    """

    def __init__(
        self,
        endpoints: str | Sequence[str] = DEFAULT_ENDPOINT,
        reorder_s: float = REORDER_S,
        idle_timeout_s: float | None = None,
        context=None,
        auth=None,
    ):
        self.endpoints = [endpoints] if isinstance(endpoints, str) else list(endpoints)
        self.auth = auth
        if auth is not None:
            unpinned = [ep for ep in self.endpoints if ep not in auth.servers]
            if unpinned:
                raise ValueError(f"no server key pinned for {unpinned}")
        self.reorder_ns = int(reorder_s * 1e9)
        self.idle_timeout_s = idle_timeout_s
        self.context = context
        self.meta: dict[str, dict] = {}
        self.stats = {"received": 0, "late": 0, "bad": 0, "yielded": 0}
        self._sock = None
        self._stopped = False
        self._pending: list = []  # heap of (t_ns, arrival count, Measurement)
        self._newest: int | None = None
        self._dec = msgspec.msgpack.Decoder(Measurement)

    def connect(self):
        """Open the subscription now (it is opened on first iteration otherwise), so that no
        message sent after this call is missed for want of a subscriber."""
        import zmq  # ground and payload extras

        if self._sock is None:
            ctx = self.context or zmq.Context.instance()
            sock = ctx.socket(zmq.SUB)
            sock.setsockopt(zmq.LINGER, 0)
            for topic in (b"meas", b"meta"):
                sock.setsockopt(zmq.SUBSCRIBE, topic)
            if self.auth is not None:
                sock.curve_publickey = self.auth.public
                sock.curve_secretkey = self.auth.secret
            for ep in self.endpoints:
                if self.auth is not None:  # options are taken per connection, at connect()
                    sock.curve_serverkey = self.auth.servers[ep][1]
                sock.connect(ep)
            self._sock = sock
        return self._sock

    def describe(self) -> str:
        """One line for the session notes: how the stream was protected."""
        if self.auth is None:
            return "stream: NOT authenticated or encrypted (plaintext ZeroMQ, --insecure)"
        return f"stream: authenticated, {self.auth.describe()}"

    def stop(self) -> None:
        """End iteration after flushing what is held (call from another thread)."""
        self._stopped = True

    def wait_for_meta(self, receiver: str = "payload", timeout_s: float = 30.0) -> dict | None:
        """Block until `receiver` has sent its metadata (or time out). Measurements that arrive
        meanwhile are kept for iteration."""
        sock = self.connect()
        end = time.monotonic() + timeout_s
        while receiver not in self.meta and time.monotonic() < end:
            if sock.poll(100):
                self._drain(sock)
        return self.meta.get(receiver)

    def _drain(self, sock) -> bool:
        """Take every message waiting on the socket; True if there was any."""
        import zmq

        got = False
        while True:
            try:
                frames = sock.recv_multipart(zmq.NOBLOCK)
            except zmq.Again:
                return got
            got = True
            self._take(frames)

    def _take(self, frames) -> None:
        if len(frames) != 2:
            self.stats["bad"] += 1
            return
        topic, payload = frames
        if topic == b"meta":
            try:
                meta = json.loads(payload)
                self.meta[meta.get("receiver", "payload")] = meta
            except (ValueError, AttributeError):
                self.stats["bad"] += 1
            return
        try:
            m = self._dec.decode(payload)
        except msgspec.DecodeError:
            self.stats["bad"] += 1
            return
        self.stats["received"] += 1
        self._newest = m.t_ns if self._newest is None else max(self._newest, m.t_ns)
        heapq.heappush(self._pending, (m.t_ns, self.stats["received"], m))

    def __iter__(self) -> Iterator[Measurement]:
        sock = self.connect()
        pending = self._pending
        last_out = None
        last_rx = time.monotonic()
        while True:
            if sock.poll(100) and self._drain(sock):
                last_rx = time.monotonic()
            idle = time.monotonic() - last_rx
            ending = self._stopped or (
                self.idle_timeout_s is not None and idle >= self.idle_timeout_s
            )
            # release what is older than the newest record by more than the window; on a quiet
            # stream (nothing for the window) or when ending, release everything
            flush_all = ending or idle * 1e9 >= self.reorder_ns
            while pending and (flush_all or pending[0][0] <= self._newest - self.reorder_ns):
                t, _, m = heapq.heappop(pending)
                if last_out is not None and t < last_out:
                    self.stats["late"] += 1
                    continue
                last_out = t
                self.stats["yielded"] += 1
                yield m
            if ending:
                return
