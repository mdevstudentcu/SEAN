from __future__ import annotations

from collections.abc import Iterator

import msgspec

from pnt.core.measurement import Measurement


class LiveSource:
    """Measurements streamed by the payload over ZeroMQ (ADR-0009). Not exercised yet."""

    def __init__(self, endpoint: str = "tcp://pnt.local:5556"):
        self.endpoint = endpoint

    def __iter__(self) -> Iterator[Measurement]:
        import zmq  # ground extra

        sock = zmq.Context.instance().socket(zmq.SUB)
        sock.connect(self.endpoint)
        sock.setsockopt(zmq.SUBSCRIBE, b"meas")
        dec = msgspec.msgpack.Decoder(Measurement)
        while True:
            _topic, payload = sock.recv_multipart()
            yield dec.decode(payload)
