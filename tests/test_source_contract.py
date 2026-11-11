"""The contract every `Source` keeps (ADR-0004, ADR-0008): the same assertions on all three.

Ported from #64 (AceAtDev). `live` runs the payload's own `Streamer` into `LiveSource` over
ZeroMQ's in-process transport on a private context: no network, no port, no hardware. It shows
that `LiveSource` delivers what the streamer sent, in time order. It does not exercise TCP,
CurveZMQ or the Pi; `tests/test_payload.py` covers the recorder-to-laptop round trip on loopback.

One test per source, each building its source once, so the suite runs every source a single time
however xdist splits it.
"""

from collections import Counter

import pytest

from pnt.core.measurement import Measurement, to_json, validate
from pnt.core.time import NS
from pnt.io.mcap_log import SessionWriter
from pnt.sim.scenario import T0_NS, generate, load
from pnt.sources.live import LiveSource
from pnt.sources.replay import ReplaySource
from pnt.sources.sim import SimSource

zmq = pytest.importorskip("zmq")

# gps-outage carries IMU, baro, GNSS (with a gap) and LTE records, so every record shape is seen.
SCENARIO = "gps-outage"
SEED = 7
# Live records are sent out of order inside blocks this long, as several devices would send them,
# so `LiveSource` has to put them back. Inside its reorder window (`REORDER_S`). Test setting.
SHUFFLE_BLOCK_NS = NS // 4
LIVE_TIMEOUT_S = 10.0  # hang guard, not a requirement


def _expected() -> list[Measurement]:
    return generate(load(SCENARIO), seed=SEED).measurements


def _keeps_the_contract(got: list[Measurement], expected: list[Measurement]) -> None:
    assert got, "source yielded nothing"
    for m in got:
        assert type(m) is Measurement, f"yielded {type(m).__name__}, not Measurement"
        validate(m)
        assert type(m.t_ns) is int, f"t_ns is {type(m.t_ns).__name__}, not int: {m}"
        assert -(2**63) <= m.t_ns < 2**63, f"t_ns overflows int64: {m}"
    # The scenario fixes the true window, so a wrong unit (s, us) or epoch (Unix) lands outside it.
    end_ns = T0_NS + int(load(SCENARIO)["duration_s"] * NS)
    outside = [m.t_ns for m in got if not T0_NS <= m.t_ns < end_ns]
    assert not outside, f"{len(outside)} times are not GPS ns in the run, first {outside[0]}"
    times = [m.t_ns for m in got]
    back = next((i for i in range(1, len(times)) if times[i] < times[i - 1]), None)
    assert back is None, f"not time-ordered at record {back}: {times[back - 1]} > {times[back]}"
    # Interchangeable (ADR-0004): the records the scenario made, compared as their ICD encoding
    # (a tuple read back from JSON as a list is the same record). Records sharing a time may come
    # in either order: the contract is time order, not tie order.
    assert len(got) == len(expected), f"{len(got)} records, expected {len(expected)}"
    assert Counter(map(to_json, got)) == Counter(map(to_json, expected)), "records differ"


def test_sim_source_keeps_the_contract():
    _keeps_the_contract(list(SimSource(SCENARIO, seed=SEED)), _expected())


def test_replay_source_keeps_the_contract(tmp_path):
    expected = _expected()
    path = tmp_path / "session.mcap"
    with SessionWriter(path) as w:
        for m in expected:
            w.write(f"/meas/{m.source}", m)
    _keeps_the_contract(list(ReplaySource(path)), expected)


def _streamed_order(records: list[Measurement]) -> list[Measurement]:
    blocks: dict[int, list[Measurement]] = {}
    for m in records:
        blocks.setdefault((m.t_ns - T0_NS) // SHUFFLE_BLOCK_NS, []).append(m)
    return [m for k in sorted(blocks) for m in reversed(blocks[k])]


def test_live_source_keeps_the_contract():
    from pnt.payload.streamer import Streamer

    expected = _expected()
    sent = _streamed_order(expected)
    assert sent != expected, "the stand-in stream is already in order: nothing to put back"
    ctx = zmq.Context()
    ctx.setsockopt(zmq.RCVHWM, 0)  # the whole run waits in the subscriber's queue: drop nothing
    streamer = Streamer("inproc://source-contract", context=ctx)
    try:
        live = LiveSource(streamer.endpoint, context=ctx, idle_timeout_s=0.3)
        live.connect()
        assert streamer.wait_for_subscriber(LIVE_TIMEOUT_S), "LiveSource never subscribed"
        for m in sent:
            streamer.send(m)
        assert streamer.dropped == 0, f"streamer dropped {streamer.dropped} records"
        got = list(live)
    finally:
        streamer.close()
        ctx.destroy(linger=0)
    assert live.stats["late"] == 0 and live.stats["bad"] == 0, live.stats
    _keeps_the_contract(got, expected)
