"""The contract every `Source` keeps (ADR-0004, ADR-0008): the same assertions on all three.

`live` runs over ZeroMQ's in-process transport, so it needs no network or hardware. The publisher
here is a stand-in for the payload streamer, which does not exist yet: this checks `LiveSource`,
not the Pi. The stand-in sends records in order, so for `live` the ordering test only shows that
`LiveSource` keeps the order it receives.
"""

from itertools import islice
from threading import Thread

import pytest
import zmq

from pnt.core.measurement import Measurement, msgpack_encoder, validate
from pnt.core.time import NS
from pnt.io.mcap_log import SessionWriter
from pnt.sim.scenario import T0_NS, generate, load
from pnt.sources.live import LiveSource
from pnt.sources.replay import ReplaySource
from pnt.sources.sim import SimSource

SCENARIO = "gps-outage"
SEED = 7
LIVE_RECORDS = 200  # enough to see order, and below ZeroMQ's default queue limit of 1000
LIVE_TIMEOUT_S = 10  # hang guard, not a requirement


def _expected() -> list[Measurement]:
    return generate(load(SCENARIO), seed=SEED).measurements


def _read_sim(_tmp_path) -> list[Measurement]:
    return list(SimSource(SCENARIO, seed=SEED))


def _read_replay(tmp_path) -> list[Measurement]:
    path = tmp_path / "s.mcap"
    with SessionWriter(path) as w:
        for meas in _expected():
            w.write(f"/meas/{meas.source}", meas)
    return list(ReplaySource(path))


def _read_live(_tmp_path) -> list[Measurement]:
    sent = _expected()[:LIVE_RECORDS]
    endpoint = "inproc://source-contract"
    # XPUB reports the subscription, so nothing is sent before LiveSource is listening.
    pub = zmq.Context.instance().socket(zmq.XPUB)
    pub.linger = 0
    pub.bind(endpoint)
    received: list[Measurement] = []
    errors: list[Exception] = []

    def consume() -> None:
        try:
            received.extend(islice(LiveSource(endpoint), len(sent)))
        except Exception as e:  # re-raised in the test thread
            errors.append(e)

    # LiveSource blocks forever without data, so it runs where the test can give up on it.
    thread = Thread(target=consume, daemon=True)
    thread.start()
    try:
        assert pub.poll(LIVE_TIMEOUT_S * 1000), "LiveSource never subscribed"
        pub.recv()
        for meas in sent:
            pub.send_multipart([b"meas", msgpack_encoder.encode(meas)])
        thread.join(LIVE_TIMEOUT_S)
    finally:
        pub.close()
    assert not thread.is_alive(), f"LiveSource delivered {len(received)}/{len(sent)} records"
    if errors:
        raise errors[0]
    return received


@pytest.fixture(
    scope="module",
    params=[_read_sim, _read_replay, _read_live],
    ids=["sim", "replay", "live"],
)
def records(request, tmp_path_factory) -> list[Measurement]:
    got = request.param(tmp_path_factory.mktemp("source"))
    assert got, "source yielded nothing"
    return got


def test_yields_valid_measurements(records):
    for m in records:
        assert type(m) is Measurement
        validate(m)


def test_times_are_int64(records):
    for m in records:
        assert type(m.t_ns) is int
        assert -(2**63) <= m.t_ns < 2**63


def test_times_are_gps_nanoseconds(records):
    # The scenario fixes the true window, so a wrong unit or epoch lands outside it.
    end_ns = T0_NS + int(load(SCENARIO)["duration_s"]) * NS
    assert all(T0_NS <= m.t_ns < end_ns for m in records)


def test_time_ordered(records):
    times = [m.t_ns for m in records]
    assert times == sorted(times)


def test_sources_are_interchangeable(records):
    assert records == _expected()[: len(records)]
