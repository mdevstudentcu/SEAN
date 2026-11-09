"""Live stream from the payload or the reference station to the laptop (ADR-0009).

ZeroMQ PUB side, two-frame messages:
- `[b"meas", msgpack(Measurement)]` for every record the recorder writes
- `[b"meta", json(meta.yaml dict + receiver)]` once a second, so the laptop learns the session
  origin without being told

Dropping messages is acceptable: everything is also recorded on board (ADR-0009). An XPUB socket
is used (it sends like PUB) so the sender can tell when a subscriber has joined.

With `auth` (ADR-0026, #89) the socket is a CurveZMQ server: every message is encrypted and
authenticated, and a ZAP handler admits only the trusted laptop keys. `pnt record` requires it
unless `--insecure` is given; without `auth` the stream is plaintext (tests, private links).
"""

from __future__ import annotations

import json

from pnt.core.measurement import Measurement, msgpack_encoder

DEFAULT_ENDPOINT = "tcp://*:5556"
TOPIC_MEAS = b"meas"
TOPIC_META = b"meta"
SEND_HWM = 10_000  # messages queued per subscriber before PUB drops (ADR-0009)


class _AllowList:
    """ZAP credentials check: a client key is admitted only if it is trusted."""

    def __init__(self, keys):
        self.keys = frozenset(keys)
        self.refused = 0

    def callback(self, domain, key: bytes) -> bool:
        if key in self.keys:
            return True
        self.refused += 1
        return False


class Streamer:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, context=None, auth=None):
        """`auth`: a `pnt.io.linkauth.ServerAuth`, or None for a plaintext stream."""
        import zmq  # payload and ground extras

        self._zmq = zmq
        self.auth = auth
        self._authenticator = None
        self._allow = None
        self._own_ctx = auth is not None
        # a ZAP handler serves a whole context, so a secured stream gets a context of its own
        self.ctx = zmq.Context() if self._own_ctx else (context or zmq.Context.instance())
        if auth is not None:
            from zmq.auth.thread import ThreadAuthenticator

            self._allow = _AllowList(auth.clients.values())
            self._authenticator = ThreadAuthenticator(self.ctx)
            self._authenticator.start()  # before bind: no connection is accepted unchecked
            self._authenticator.configure_curve_callback("*", self._allow)
        self.sock = self.ctx.socket(zmq.XPUB)
        if auth is not None:
            self.sock.curve_secretkey = auth.secret
            self.sock.curve_publickey = auth.public
            self.sock.curve_server = True
        self.sock.setsockopt(zmq.SNDHWM, SEND_HWM)
        self.sock.setsockopt(zmq.LINGER, 0)
        self.sock.setsockopt(zmq.XPUB_VERBOSE, 1)  # report every subscription, not just the first
        self.sock.bind(endpoint)
        self.endpoint = self.sock.getsockopt_string(zmq.LAST_ENDPOINT)
        self.subscriptions = 0
        self.sent = 0
        self.dropped = 0

    def _poll_subscriptions(self) -> None:
        zmq = self._zmq
        while True:
            try:
                msg = self.sock.recv(zmq.NOBLOCK)
            except zmq.Again:
                return
            if msg[:1] == b"\x01":
                self.subscriptions += 1  # subscriptions seen; leaving is not tracked

    def wait_for_subscriber(self, timeout_s: float) -> bool:
        if self.sock.poll(int(timeout_s * 1000), self._zmq.POLLIN):
            self._poll_subscriptions()
        return self.subscriptions > 0

    def _send(self, frames: list[bytes]) -> None:
        self._poll_subscriptions()
        try:
            self.sock.send_multipart(frames, self._zmq.NOBLOCK)
            self.sent += 1
        except self._zmq.Again:
            self.dropped += 1

    def send(self, m: Measurement) -> None:
        self._send([TOPIC_MEAS, msgpack_encoder.encode(m)])

    def send_meta(self, meta: dict, receiver: str) -> None:
        self._send([TOPIC_META, json.dumps({**meta, "receiver": receiver}).encode()])

    @property
    def refused(self) -> int:
        """Connections whose client key was not trusted (ZAP)."""
        return self._allow.refused if self._allow else 0

    def describe(self) -> str:
        """One line for the session notes: how the stream is protected."""
        if self.auth is None:
            return "stream: NOT authenticated or encrypted (plaintext ZeroMQ)"
        refused = f"connections refused: {self.refused}"
        return f"stream: authenticated, {self.auth.describe()}; {refused}"

    def close(self) -> None:
        self.sock.close()
        if self._authenticator is not None:
            self._authenticator.stop()
        if self._own_ctx:
            self.ctx.term()
