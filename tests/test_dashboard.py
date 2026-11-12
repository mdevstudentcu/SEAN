"""Operator panel (#25) and its navigation-health logic (#90)."""

import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Estimate
from pnt.dashboard import health
from pnt.dashboard.feed import Feed, frames, live_feed, paced, sim_feed
from pnt.dashboard.health import HealthMonitor, describe, time_to_limit_s

SRC = Path(__file__).resolve().parents[1] / "src" / "pnt"
SMALL = """
name: small
duration_s: 30
dt_s: 0.1
origin_llh: [45.3876, -75.6960, 70.0]
trajectory: {type: loop, radius_m: 150, speed_mps: 8, altitude_m: 30}
sources:
  gnss: {rate_hz: 5, sigma_m: 2.5}
  baro: {rate_hz: 10, sigma_m: 0.5}
  lte: {model: pseudorange, rate_hz: 1, n_emitters: 5, ring_radius_m: [800, 3000],
        sigma_m: 20.0, clock_rw_m: 0.2, init_bias_m: 1000.0}
faults:
  - {type: outage, source: gnss, start_s: 12, end_s: 22}
"""


def _est(t_s: float, flags=(), status="nominal", hpl=5.0, trust=None) -> Estimate:
    return Estimate(
        t_ns=int(t_s * 1e9),
        pos_enu=(0.0, 0.0, 0.0),
        vel_enu=(0.0, 0.0, 0.0),
        pos_cov=(1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0),
        hpl_m=hpl,
        status=status,
        flags=list(flags),
        trust=trust or {},
    )


# One example per parameterised flag: a new parameterised flag fails the test below until it is
# given an example here, and with it a sentence in `describe`
FLAG_EXAMPLES = {
    "mhss_alarm": "gnss-cm",
    "mhss_excluded": "gnss-cm",
    "tower_fault": "lte:sim1:+316",
}


def _raised_flags() -> set[str]:
    """Every flag string the estimators and monitors append, read from the source."""
    found = set()
    for path in [*SRC.glob("nav/*.py"), *SRC.glob("integrity/*.py")]:
        text = path.read_text()
        found |= set(re.findall(r'flags\.append\("([a-z_]+)"\)', text))
        found |= set(re.findall(r'^FLAG = "([a-z_]+)"', text, re.M))  # raised through a constant
        for p in re.findall(r'flags\.append\(f"([a-z_]+):\{', text):
            found.add(f"{p}:{FLAG_EXAMPLES.get(p, 'no-example')}")
    return found


def test_every_raised_flag_has_a_sentence():
    flags = _raised_flags()
    # the flags on main when this was written, so a broken grep can't pass vacuously
    assert {"gnss_excluded", "spoof_suspected", "base_excluded"} <= flags
    assert "hostile_beacon" in flags  # raised through `nav.hostile.FLAG`, not a literal
    assert {"mhss_alarm:gnss-cm", "mhss_excluded:gnss-cm", "tower_fault:lte:sim1:+316"} <= flags
    assert not any(f.endswith(":no-example") for f in flags), flags
    for f in flags:
        assert not describe(f)[1].startswith("Unrecognised"), f


def test_tower_fault_names_the_tower_and_the_jump():
    sev, text = describe("tower_fault:lte:sim1:+316")
    assert sev == health.WARNING
    assert "Tower LTE sim1" in text and "+316 m (+1.05 µs)" in text
    assert "Tower LTE sim1" in describe("tower_fault:lte:sim1")[1]  # no size: still named


def test_unknown_flag_is_shown_raw():
    sev, text = describe("brand_new_flag")
    assert sev == health.CAUTION and "brand_new_flag" in text


def test_mhss_hypotheses_in_words():
    assert "LTE tower" not in describe("mhss_alarm:site:lte:sim3")[1]  # site, then emitter
    assert "tower site LTE sim3" in describe("mhss_alarm:site:lte:sim3")[1]
    assert "GPS and everything derived" in describe("mhss_excluded:gnss-cm")[1]
    assert "network builder rogers" in describe("mhss_alarm:builder:rogers")[1]
    hostile = describe("mhss_excluded:hostile:jammer:sim0")[1]  # ADR-0025, #93
    assert "hostile beacon (located jammer sim0)" in hostile and "hostile:" not in hostile


def test_no_latching_during_start_up():
    mon = HealthMonitor(50.0, 1.5e-6)
    s = mon.update(_est(0.0, flags=["gnss_unavailable"], status="unsafe", hpl=90.0))
    assert s["alerts"] == [] and s["causes"] and not s["settled"]
    assert mon.update(_est(0.1))["settled"]
    stuck = HealthMonitor(50.0, 1.5e-6, t0_ns=0)  # never nominal: latches after STARTUP_MAX_S
    assert stuck.update(_est(0.0, flags=["gnss_unavailable"], status="degraded"))["alerts"] == []
    s = stuck.update(_est(health.STARTUP_MAX_S, flags=["gnss_unavailable"], status="degraded"))
    assert [a["key"] for a in s["alerts"]] == ["gnss_unavailable"]


def test_alert_latches_until_acknowledged():
    mon = HealthMonitor(50.0, 1.5e-6)
    mon.update(_est(0.0))
    s = mon.update(_est(1.0, flags=["gnss_excluded"]))
    assert [a["key"] for a in s["alerts"]] == ["gnss_excluded"]
    s = mon.update(_est(2.0))  # the flag clears: the alert stays, inactive
    assert s["causes"] == [] and s["alerts"][0]["active"] is False
    mon.acknowledge(s["alerts"][0]["id"])
    assert mon.update(_est(3.0))["alerts"] == []


def test_acknowledged_active_alert_stays_until_it_clears():
    mon = HealthMonitor(50.0, 1.5e-6)
    mon.update(_est(-1.0))  # settled
    mon.update(_est(0.0, status="unsafe", hpl=80.0))
    mon.acknowledge()
    s = mon.update(_est(0.1, status="unsafe", hpl=80.0))
    assert s["alerts"][0]["acked"] and s["alerts"][0]["active"]
    assert mon.update(_est(0.2))["alerts"] == []
    # it comes back after acknowledgement: a new alert
    s = mon.update(_est(5.0, status="unsafe", hpl=80.0))
    assert len(s["alerts"]) == 1 and not s["alerts"][0]["acked"]


def test_acknowledged_alert_survives_a_brief_clear():
    mon = HealthMonitor(50.0, 1.5e-6, t0_ns=0)
    mon.update(_est(-1.0))  # settled
    on, off = {"status": "unsafe", "hpl": 60.0}, {"status": "nominal", "hpl": 40.0}
    first = mon.update(_est(0.0, **on))["alerts"][0]["id"]
    mon.acknowledge()
    assert mon.update(_est(0.5, **off))["alerts"] == []  # cleared and acknowledged: off the panel
    (a,) = mon.update(_est(1.0, **on))["alerts"]  # back within CLEAR_HOLD_S: the same alert
    assert a["id"] == first and a["acked"] and a["count"] == 1


def test_acknowledging_during_a_brief_clear_holds_too():
    mon = HealthMonitor(50.0, 1.5e-6, t0_ns=0)
    mon.update(_est(-1.0))
    on, off = {"status": "unsafe", "hpl": 60.0}, {"status": "nominal", "hpl": 40.0}
    first = mon.update(_est(0.0, **on))["alerts"][0]["id"]
    mon.update(_est(0.5, **off))
    mon.acknowledge()
    (a,) = mon.update(_est(1.0, **on))["alerts"]
    assert a["id"] == first and a["acked"]


def test_acknowledged_alert_is_forgotten_after_the_hold():
    mon = HealthMonitor(50.0, 1.5e-6, t0_ns=0)
    mon.update(_est(-1.0))
    on, off = {"status": "unsafe", "hpl": 60.0}, {"status": "nominal", "hpl": 40.0}
    first = mon.update(_est(0.0, **on))["alerts"][0]["id"]
    mon.acknowledge()
    mon.update(_est(0.5, **off))
    # no epoch in between: a return later than CLEAR_HOLD_S is still a new alert
    (a,) = mon.update(_est(health.CLEAR_HOLD_S + 0.5, **on))["alerts"]
    assert a["id"] != first and not a["acked"] and a["count"] == 1


def test_brief_clear_is_the_same_occurrence():
    mon = HealthMonitor(50.0, 1.5e-6, t0_ns=0)
    mon.update(_est(-1.0))  # settled
    for t, on in [(0.0, True), (0.5, False), (1.0, True), (10.0, False), (20.0, True)]:
        s = mon.update(_est(t, status="unsafe" if on else "nominal", hpl=60.0 if on else 40.0))
    (a,) = s["alerts"]
    assert a["count"] == 2 and a["since_s"] == 0.0 and a["onset_s"] == 20.0


def test_time_pl_over_its_limit_raises_an_alert():
    mon = HealthMonitor(50.0, 1.5e-6)
    est = _est(0.0)
    est.clock_sigma_s = 1e-6  # time PL 5.33 us
    s = mon.update(est)
    assert [c["flag"] for c in s["causes"]] == [health.TIME_OVER]
    assert s["alerts"][0]["severity"] == health.ALARM


def test_status_follows_the_panels_alert_limit():
    tight = HealthMonitor(20.0, 1.5e-6)
    tight.update(_est(0.0))  # settled
    s = tight.update(_est(1.0, status="nominal", hpl=40.0))
    assert s["status"] == "unsafe" and "within the limit" not in s["headline"]
    assert [a["key"] for a in s["alerts"]] == ["status:unsafe"]
    wide = HealthMonitor(556.0, 1.5e-6)
    wide.update(_est(0.0))
    s = wide.update(_est(1.0, status="unsafe", hpl=100.0))  # the estimator's own 50 m limit
    assert s["status"] == "nominal" and s["alerts"] == []
    s = wide.update(_est(2.0, status="unsafe", hpl=100.0, flags=["gnss_unavailable"]))
    assert s["status"] == "degraded"


def test_status_without_a_protection_level_is_the_estimators():
    s = HealthMonitor(50.0, 1.5e-6).update(_est(0.0, status="degraded", hpl=None))
    assert s["status"] == "degraded"


def test_nominal_headline_makes_no_claim_about_the_towers():
    s = HealthMonitor(50.0, 1.5e-6).update(_est(0.0, trust={"gnss": 1.0, "lte": 0.0}))
    assert s["status"] == "nominal" and s["low_trust"] == {"lte": 0.0}
    assert "All sources" not in s["headline"] and "GPS in use" in s["headline"]


def test_gps_lost_sentence_names_no_source_it_may_not_be_using():
    # On the challenge legs the towers are out of use most of the time, and the flag is raised
    # while a spoofed GPS is being rejected too: the sentence must not say "towers" or only "lost"
    sev, text = describe("gnss_unavailable")
    assert sev == "caution" and "towers" not in text and "rejected" in text


def test_sources_rows_speak_to_the_operator_not_the_repo():
    # The operator reads the tooltips on stage: "on main" names a git branch, not the system
    page = (SRC / "dashboard" / "web" / "index.html").read_text()
    titles = re.findall(r'title="([^"]*)"', page)
    assert titles and not any(re.search(r"\bmain\b", t) for t in titles)


def test_low_trust_listed_apart():
    s = HealthMonitor(50.0, 1.5e-6).update(_est(0.0, trust={"gnss": 0.0, "lte": 1.0}))
    assert s["low_trust"] == {"gnss": 0.0} and s["trusted"] == {"lte": 1.0}


def test_confidence_colour_by_hpl_against_the_alert_limit():
    # #207: green well within, amber near, red at or over the limit. The 0.8 split is TBC
    # (health.CONF_AMBER_FRACTION); the test follows the constant rather than picking a target
    al = 50.0
    amber = health.CONF_AMBER_FRACTION * al
    assert health.confidence(5.0, [], al) == health.CONFIDENT
    assert health.confidence(amber - 0.01, [], al) == health.CONFIDENT
    assert health.confidence(amber, [], al) == health.NEAR_LIMIT
    assert health.confidence(al - 0.01, [], al) == health.NEAR_LIMIT
    assert health.confidence(al, [], al) == health.DO_NOT_TRUST
    assert health.confidence(10 * al, [], al) == health.DO_NOT_TRUST


def test_confidence_red_without_a_bound_or_with_an_alarm_flag():
    al = 50.0
    assert health.confidence(None, [], al) == health.DO_NOT_TRUST
    assert health.confidence(float("nan"), [], al) == health.DO_NOT_TRUST
    for flag in ["spoof_suspected", "time_spoof_suspected", "mhss_alarm:gnss-cm"]:
        assert health.confidence(5.0, [flag], al) == health.DO_NOT_TRUST, flag
    # a caution or a handled fault leaves the colour to the protection level: GPS-denied
    # flight on towers inside the limit is still green
    for flag in ["gnss_unavailable", "gnss_excluded", "mhss_excluded:gnss-cm"]:
        assert health.confidence(5.0, [flag], al) == health.CONFIDENT, flag


def test_monitor_reports_confidence_against_the_panels_limit():
    s = HealthMonitor(20.0, 1.5e-6).update(_est(0.0, hpl=17.0))
    assert s["confidence"] == health.NEAR_LIMIT  # 17 m is near a 20 m limit
    s = HealthMonitor(556.0, 1.5e-6).update(_est(0.0, hpl=17.0, status="unsafe"))
    assert s["confidence"] == health.CONFIDENT  # the estimator's own limit does not colour it


def test_time_to_alert_from_the_trend():
    t = np.arange(0.0, 10.0, 0.1)
    assert time_to_limit_s(t, 10.0 + 2.0 * t, 50.0) == pytest.approx((50.0 - 29.8) / 2.0)
    assert time_to_limit_s(t, np.full_like(t, 10.0), 50.0) is None
    assert time_to_limit_s(t, 45.0 - t, 50.0) is None  # falling: no alert on this trend
    assert time_to_limit_s(t, 40.0 + 2.0 * t, 50.0) == 0.0  # already over


def test_anp_is_95_percent_radius():
    assert health.anp95_m((4.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0)) == pytest.approx(2.4477 * 2.0)


def _frames(n: int, dt: float = 0.1) -> list[dict]:
    return [{"t_s": i * dt, "new_emitters": [{"id": f"e{i}"}] if i == 3 else []} for i in range(n)]


def test_paced_holds_to_speed_and_thins():
    now = [0.0]
    sent = list(
        paced(
            _frames(101),  # 10 s of data at 10 Hz
            speed=4.0,
            max_rate_hz=2.0,
            clock=lambda: now[0],
            sleep=lambda s: now.__setitem__(0, now[0] + s),
        )
    )
    assert now[0] == pytest.approx(10.0 / 4.0)  # held to 4x real time
    assert len(sent) <= 2 * 2.5 + 2 and sent[-1]["t_s"] == pytest.approx(10.0)
    assert [e["id"] for f in sent for e in f["new_emitters"]] == ["e3"]  # carried, not lost


def test_paced_unheld_when_not_pacing():
    slept = []
    out = list(paced(_frames(50), speed=1.0, pace=False, sleep=slept.append))
    assert not slept and out


def _small(tmp_path) -> str:
    p = tmp_path / "small.yaml"
    p.write_text(SMALL)
    return str(p)


def test_frames_from_sim_are_json_and_raise_the_outage(tmp_path):
    feed = sim_feed(_small(tmp_path), seed=0, estimator="ekf", preflight=False)
    out = list(frames(feed, HealthMonitor(50.0, 1.5e-6)))
    for f in out:
        json.dumps(f, allow_nan=False)
    assert {e["id"] for f in out for e in f["new_emitters"]} == {f"lte:sim{i}" for i in range(5)}
    keys = {a["key"] for a in out[-1]["health"]["alerts"]}
    assert "gnss_unavailable" in keys  # latched from the outage, still shown after it ends
    assert all(f["err_h_m"] is not None for f in out)
    # the track colour (#207) rides on every frame, judged against the panel's limit
    assert all(f["confidence"] == health.confidence(f["hpl_m"], f["flags"], 50.0) for f in out)
    assert feed.info(50.0, 1.5e-6)["confidence_amber_m"] == health.CONF_AMBER_FRACTION * 50.0


def test_front_end_lte_cells_are_drawn_at_their_registered_site():
    # Front-end-shaped records (as real captures are) name a cell and carry no position: the
    # panel places them through the registry lookup, as the estimator does, and the estimates
    # are the same as without the panel
    from pnt.core.frames import llh_to_enu
    from pnt.nav import estimate
    from pnt.nav.cells import CellTable
    from pnt.sim.scenario import generate, load

    spec = {**load("challenge-drone-nominal"), "duration_s": 20.0}
    run = generate(spec, seed=0)
    origin = spec["origin_llh"]
    feed = Feed("front-end", "sim", run.measurements, "ekf", origin_llh=origin)
    out = list(frames(feed, HealthMonitor(50.0, 1.5e-6)))
    drawn = {e["id"]: e for f in out for e in f["new_emitters"]}
    assert drawn and all(re.fullmatch(r"lte:2460:\d+", k) for k in drawn)
    assert set().union(*(f["heard"] for f in out)) <= set(drawn)
    table = CellTable.load()
    for em in drawn.values():
        _, earfcn, pci = em["id"].split(":")
        _, cell = table.associate(int(earfcn), int(pci), origin)
        e, n, _ = llh_to_enu([cell.lat, cell.lon, origin[2]], origin)
        assert (em["e"], em["n"]) == pytest.approx((e, n), abs=0.5)
    alone = list(estimate("ekf", run.measurements, origin_llh=origin))
    assert np.allclose([f["pos"] for f in out], [a.pos_enu for a in alone])


def test_replay_with_hide_origin_keeps_the_location_out_of_the_stream(tmp_path, capsys):
    # #264: a real capture's origin and tower sites locate it. `pnt dash --hide-origin` leaves
    # them out of everything the page receives; the estimates and the relative track stay
    from pnt.cli import main
    from pnt.dashboard.feed import replay_feed

    out = tmp_path / "session"
    main(["sim", _small(tmp_path), "--out", str(out)])
    capsys.readouterr()
    shown = replay_feed(out, preflight=False)
    hidden = replay_feed(out, preflight=False, hide_origin=True)
    a = list(frames(shown, HealthMonitor(50.0, 1.5e-6)))
    b = list(frames(hidden, HealthMonitor(50.0, 1.5e-6)))
    assert shown.info(50.0, 1.5e-6)["origin_llh"] == [45.3876, -75.696, 70.0]
    assert any(f["new_emitters"] for f in a) and any(f["heard"] for f in a)
    info = hidden.info(50.0, 1.5e-6)
    assert info["origin_llh"] is None
    assert all(not f["new_emitters"] and not f["heard"] for f in b)
    assert [f["pos"] for f in b] == [f["pos"] for f in a]
    assert [f["status"] for f in b] == [f["status"] for f in a]
    stream = json.dumps([info, b], allow_nan=False)
    assert "45.38" not in stream and "-75.69" not in stream


def test_frames_carry_the_spoof_decision(tmp_path):
    # #206, ADR-0041: no sky in a frame says unknown; a sky says not spoofed, then a faked sky
    # (every satellite at one power) is named on the panel
    plain = list(frames(sim_feed(_small(tmp_path), preflight=False), HealthMonitor(50.0, 1.5e-6)))
    assert {f["spoof"]["level"] for f in plain} == {"unknown"}
    p = tmp_path / "sky.yaml"
    sky = SMALL.replace("sigma_m: 2.5}", "sigma_m: 2.5, health: true, sky: true}")
    fault = "type: fake_sky, start_s: 12, flat_cn0_dbhz: 45"
    p.write_text(sky.replace("type: outage, source: gnss, start_s: 12, end_s: 22", fault))
    out = list(frames(sim_feed(str(p), preflight=False), HealthMonitor(50.0, 1.5e-6)))
    json.dumps([f["spoof"] for f in out], allow_nan=False)
    level = {round(f["t_s"]): f["spoof"]["level"] for f in out}
    assert level[5] == level[11] == "not_spoofed"
    # Skyviews every 5 s: the first faked one is at 15 s. The power cue alone is never red
    assert level[14] == "not_spoofed" and level[16] == level[29] == "suspect"
    assert out[-1]["spoof"]["cues"] == ["power_flat (held)"]


def test_live_stream_gives_the_panel_what_the_sim_does(tmp_path):
    # ADR-0004: the same run, streamed over ZeroMQ as the payload does (loopback), gives the panel
    # the same frames as the sim feed, less the truth
    pytest.importorskip("zmq")
    from pnt.payload.streamer import Streamer
    from pnt.sources.live import LiveSource

    sim = sim_feed(_small(tmp_path), seed=0, estimator="ekf", preflight=False)
    records = list(sim.measurements)
    streamer = Streamer("tcp://127.0.0.1:*")
    live = LiveSource(streamer.endpoint, idle_timeout_s=1.5)
    live.connect()
    assert streamer.wait_for_subscriber(5.0)
    for m in records:
        streamer.send(m)
    feed = live_feed(live, "loopback", "ekf", sim.origin_llh)
    got = list(frames(feed, HealthMonitor(50.0, 1.5e-6)))
    streamer.close()
    want = list(frames(sim_feed(_small(tmp_path), seed=0, estimator="ekf", preflight=False),
                       HealthMonitor(50.0, 1.5e-6)))  # fmt: skip
    assert feed.info(50.0, 1.5e-6)["kind"] == "live" and not feed.pace
    assert streamer.dropped == 0 and len(got) == len(want)
    assert np.allclose([f["pos"] for f in got], [f["pos"] for f in want], atol=1e-6)
    assert [f["health"]["alerts"] for f in got] == [f["health"]["alerts"] for f in want]
    assert all(f["truth"] is None and f["err_h_m"] is None for f in got)


def test_hub_tells_how_long_the_feed_has_been_quiet(tmp_path):
    # How a live page sees a stopped stream, even when it is opened after the stream stopped
    pytest.importorskip("fastapi")  # ground extra
    from pnt.dashboard.server import Hub

    hub = Hub({"kind": "live"})
    assert hub.quiet() == {"s": None} and "quiet" not in dict(hub.snapshot())
    feed = sim_feed(_small(tmp_path), seed=0, estimator="ekf", preflight=False)
    hub.publish("frame", next(frames(feed, HealthMonitor(50.0, 1.5e-6))))
    assert hub.history[-1][10] == hub.latest["confidence"]  # a late page redraws the colours
    hub.latest_mono -= 5.0  # the last frame came 5 s ago
    assert dict(hub.snapshot())["quiet"]["s"] >= 5.0


def test_frames_and_preflight_use_the_panels_alert_limit(tmp_path):
    def run(limit):
        feed = sim_feed(_small(tmp_path), seed=0, estimator="ekf", alert_limit_m=limit)
        return feed, list(frames(feed, HealthMonitor(limit, 1.5e-6)))

    feed, out = run(1e6)
    assert feed.preflight["unavailable"] == [] and "unsafe" not in {f["status"] for f in out}
    feed, out = run(0.01)  # below any HPL: every epoch is over it
    assert feed.preflight["unavailable"] and {f["status"] for f in out} == {"unsafe"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_streams_a_sim_run_and_takes_acks(tmp_path):
    pytest.importorskip("fastapi")  # ground extra
    import uvicorn

    from pnt.dashboard.server import create_app

    feed = sim_feed(_small(tmp_path), seed=0, estimator="ekf", preflight=False)
    app = create_app(feed, speed=float("inf"))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert b"<canvas" in urllib.request.urlopen(base + "/").read()
        events = []
        with urllib.request.urlopen(base + "/api/stream", timeout=30) as r:
            event = None
            for line in r:
                line = line.decode().rstrip("\n")
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    events.append((event, json.loads(line[6:])))
                    if event == "end":
                        break
        kinds = [e for e, _ in events]
        assert kinds[0] == "info" and "frame" in kinds and kinds[-1] == "end"
        last = [d for e, d in events if e == "frame"][-1]
        assert last["t_s"] > 25.0
        n = len(last["health"]["alerts"])
        assert n > 0
        req = urllib.request.Request(
            base + "/api/ack", data=b"{}", headers={"Content-Type": "application/json"}
        )
        shown = json.loads(urllib.request.urlopen(req).read())["alerts"]
        assert len(shown) < n and all(a["active"] for a in shown)
    finally:
        server.should_exit = True
        thread.join(5)


@contextmanager
def _serving(tmp_path, **kwargs):
    """A panel on a real uvicorn server, its short sim run finished: (app, base URL, port)."""
    pytest.importorskip("fastapi")  # ground extra
    import uvicorn

    from pnt.dashboard.server import create_app

    feed = sim_feed(_small(tmp_path), seed=0, estimator="ekf", preflight=False)
    app = create_app(feed, speed=float("inf"), **kwargs)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(400):
            if server.started and app.state.hub.done:
                break
            time.sleep(0.05)
        assert app.state.hub.done
        yield app, f"http://127.0.0.1:{port}", port
    finally:
        server.should_exit = True
        thread.join(5)


def _post_ack(base: str, headers: dict) -> int:
    req = urllib.request.Request(base + "/api/ack", data=b"", headers=headers, method="POST")
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


def test_ack_refuses_cross_site_requests(tmp_path):
    with _serving(tmp_path) as (app, base, port):
        n = len(app.state.monitor.shown())
        assert n > 0
        own = f"127.0.0.1:{port}"
        assert _post_ack(base, {"Origin": "https://evil.example"}) == 403
        assert _post_ack(base, {"Origin": "null"}) == 403
        rebound = f"evil.example:{port}"  # DNS rebinding: Origin and Host agree, on a hostile name
        assert _post_ack(base, {"Origin": f"http://{rebound}", "Host": rebound}) == 403
        assert len(app.state.monitor.shown()) == n  # none of them acknowledged anything
        assert _post_ack(base, {"Origin": f"http://{own}", "Host": own}) == 200  # the page's own
        assert len(app.state.monitor.shown()) < n


def test_ack_without_origin_still_works(tmp_path):
    with _serving(tmp_path) as (_, base, _port):
        assert _post_ack(base, {}) == 200


def test_ack_on_a_wildcard_bind_checks_origin_only(tmp_path):
    with _serving(tmp_path, host="0.0.0.0") as (_, base, _port):
        lan = "192.168.1.5:8050"
        assert _post_ack(base, {"Origin": f"http://{lan}", "Host": lan}) == 200
        assert _post_ack(base, {"Origin": "https://evil.example", "Host": lan}) == 403


def test_banner_is_opt_in_and_reaches_the_page(tmp_path, monkeypatch):
    """`--banner` (the judging demo's simulation-study label, #266) goes from `pnt sim --dash`
    to the info every browser gets; without it the page shows none."""
    pytest.importorskip("fastapi")  # ground extra
    from pnt import cli
    from pnt.dashboard import server

    served = []
    monkeypatch.setattr(server, "serve", lambda app, host, port: served.append(app))
    scenario = _small(tmp_path)
    cli.main(["sim", scenario, "--dash", "--banner", "Simulation study: not on the payload."])
    cli.main(["sim", scenario, "--dash"])
    with_banner, without = (app.state.hub.info for app in served)
    assert with_banner["banner"] == "Simulation study: not on the payload."
    assert without["banner"] is None
    page = (SRC / "dashboard" / "web" / "index.html").read_text()
    assert 'id="banner" class="banner" hidden' in page  # hidden unless info carries one
    assert "i.banner" in (SRC / "dashboard" / "web" / "app.js").read_text()


# ---- GPS trust (health.gps_trust): the panel's answer to "is GPS telling the truth?" ----------


def test_gps_trust_reads_the_flags_and_the_spoof_decision():
    gt, on = health.gps_trust, {"gnss": 1.0}
    assert gt([], on)["level"] == health.GPS_TRUSTED
    # Rejected while its trust is still 1 (the estimators keep it for a few seconds): not trusted
    g = gt(["gnss_excluded"], on)
    assert g["level"] == health.GPS_NOT_TRUSTED and "disagrees" in g["reasons"][0]
    assert not health.gps_in_use(["gnss_excluded"], on)
    # The jump guard (ADR-0038) is named first, whatever order the estimator flags in
    g = gt(["gnss_unavailable", "gnss_excluded", "gnss_jump_latched"], {"gnss": 0.0})
    assert g["level"] == health.GPS_NOT_TRUSTED and "jump guard" in g["reasons"][0]
    assert len(g["reasons"]) == 2  # gnss_unavailable is no reason to distrust
    for flag in ["spoof_suspected", "time_spoof_suspected", "mhss_excluded:gnss-cm"]:
        assert gt([flag], on)["level"] == health.GPS_NOT_TRUSTED, flag
    for flag in ["gnss_alt_excluded", "mhss_alarm:gnss-cm", "adsb_interference"]:
        assert gt([flag], on)["level"] == health.GPS_CHECKING, flag


def test_gps_trust_names_the_sky_cues():
    # ADR-0041: a held below-horizon satellite is spoofed on its own; a first flat power is a doubt
    sky = {"level": "spoofed", "cues": ["sky_below_horizon (held)"]}
    g = health.gps_trust([], {"gnss": 1.0}, sky)
    assert g["level"] == health.GPS_NOT_TRUSTED and "below the horizon" in g["reasons"][0]
    sky = {"level": "suspect", "cues": ["power_flat"]}
    g = health.gps_trust([], {"gnss": 1.0}, sky)
    assert g["level"] == health.GPS_CHECKING and "same power" in g["reasons"][0]
    # Flag cues are not repeated from the spoof decision: the flag already gives the reason
    sky = {"level": "suspect", "cues": ["jump_latched"]}
    g = health.gps_trust(["gnss_jump_latched"], {"gnss": 1.0}, sky)
    assert len(g["reasons"]) == 1
    # Unknown sky (no skyview) says nothing against GPS
    assert (
        health.gps_trust([], {"gnss": 1.0}, {"level": "unknown", "cues": []})["level"] == "trusted"
    )


def test_gps_lost_is_absent_not_a_lie():
    # GPS lost is not GPS lying: the panel says there is no GPS, and for how long
    g = health.gps_trust(["gnss_unavailable"], {"gnss": 0.0}, None, 12.0)
    assert g["level"] == health.GPS_ABSENT and g["unused_s"] == 12.0
    assert "accepted recently" in g["reasons"][0]
    assert "yet" in health.gps_trust([], {}, None, None)["reasons"][0]  # never used so far


def test_every_gps_flag_has_a_trust_reading():
    # A new GPS flag must not leave the GPS trust saying TRUSTED by default: classify it
    known = set(health.GPS_DISTRUST) | set(health.GPS_DOUBT) | {"gnss_unavailable"}
    gps = {f for f in _raised_flags() if f.startswith(("gnss", "spoof", "time_spoof"))}
    assert gps and gps <= known, gps - known


def test_monitor_times_how_long_gps_has_been_unused():
    m = HealthMonitor(50.0, 1.5e-6)
    assert m.update(_est(0.0, ["gnss_unavailable"], trust={"gnss": 0.0}))["gps_unused_s"] is None
    assert m.update(_est(1.0, trust={"gnss": 1.0}))["gps_unused_s"] is None
    s = m.update(_est(3.5, ["gnss_unavailable"], trust={"gnss": 0.0}))
    assert s["gps_unused_s"] == pytest.approx(2.5)
    # rejected while its trust is still 1: not in use either
    assert m.update(_est(4.0, ["gnss_excluded"], trust={"gnss": 1.0}))["gps_unused_s"] == 3.0
    assert m.update(_est(5.0, trust={"gnss": 1.0}))["gps_unused_s"] is None


def test_frames_carry_the_gps_trust(tmp_path):
    # SMALL: GPS lost from 12 s to 22 s, nothing lies: trusted, then absent with a growing time
    out = list(frames(sim_feed(_small(tmp_path), preflight=False), HealthMonitor(50.0, 1.5e-6)))
    json.dumps([f["gps_trust"] for f in out], allow_nan=False)
    by_t = {round(f["t_s"], 1): f["gps_trust"] for f in out}
    assert by_t[5.0]["level"] == health.GPS_TRUSTED
    lost = [f["gps_trust"] for f in out if 15 <= f["t_s"] <= 20]
    assert {g["level"] for g in lost} == {health.GPS_ABSENT}
    assert lost[-1]["unused_s"] > lost[0]["unused_s"] > 0
    assert out[-1]["gps_trust"]["level"] == health.GPS_TRUSTED


def test_page_keeps_the_runbook_cues_and_shows_the_gps_trust():
    # deploy/demo/RUNBOOK.md points the presenter at these by name: keep them on the page
    page = (SRC / "dashboard" / "web" / "index.html").read_text()
    for name in [
        'id="status-word"',
        'id="kind"',
        "Error against truth",
        "Horizontal protection level against the alert limit",
        "What is wrong now",
        "Alerts (latched until acknowledged)",
        "Sources",
        "In use",
        "Not in use",
    ]:
        assert name in page, name
    js = (SRC / "dashboard" / "web" / "app.js").read_text()
    assert 'id="gps-trust"' in page and "f.gps_trust" in js
    assert "f.status.toUpperCase()" in js  # NOMINAL / DEGRADED / UNSAFE, as the runbook says
    # The runbook's "where to look": the status first, HPL and the error against truth under it,
    # then what is wrong and the alerts, down one rail
    order = ['id="status-word"', 'id="big-hpl"', "Error against truth", "What is wrong now"]
    order += ["Alerts (latched until acknowledged)", "Sources"]
    rail = page[page.index('class="rail"') :]
    assert [rail.index(name) for name in order] == sorted(rail.index(name) for name in order)
    # ADR-0041: the spoof decision stays on the panel, next to the status (with the GPS trust)
    assert rail.index('id="status"') < rail.index('id="spoof"') < rail.index("What is wrong now")
    # Which estimator is on screen (a plain one takes a spoofed GPS back, ADR-0038), and the
    # true error called out when it is outside the bound: the page must keep both
    assert 'id="guard"' in page and "jump guard" in js
    assert 'id="err-check"' in page and "OUTSIDE THE BOUND" in js
