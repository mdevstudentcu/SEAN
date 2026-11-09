"""Operator panel (#25) and its navigation-health logic (#90)."""

import json
import re
import socket
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from pnt.core.measurement import Estimate
from pnt.dashboard import health
from pnt.dashboard.feed import frames, paced, sim_feed
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


def _raised_flags() -> set[str]:
    """Every flag string the estimators and monitors append, read from the source."""
    found = set()
    for path in [*SRC.glob("nav/*.py"), *SRC.glob("integrity/*.py")]:
        text = path.read_text()
        found |= set(re.findall(r'flags\.append\("([a-z_]+)"\)', text))
        found |= {f"{p}:gnss-cm" for p in re.findall(r'flags\.append\(f"([a-z_]+):\{', text)}
    return found


def test_every_raised_flag_has_a_sentence():
    flags = _raised_flags()
    # the flags on main when this was written, so a broken grep can't pass vacuously
    assert {"gnss_excluded", "spoof_suspected", "base_excluded", "tower_fault"} <= flags
    assert {"mhss_alarm:gnss-cm", "mhss_excluded:gnss-cm"} <= flags
    for f in flags:
        assert not describe(f)[1].startswith("Unrecognised"), f


def test_unknown_flag_is_shown_raw():
    sev, text = describe("brand_new_flag")
    assert sev == health.CAUTION and "brand_new_flag" in text


def test_mhss_hypotheses_in_words():
    assert "LTE tower" not in describe("mhss_alarm:site:lte:sim3")[1]  # site, then emitter
    assert "tower site LTE sim3" in describe("mhss_alarm:site:lte:sim3")[1]
    assert "GPS and everything derived" in describe("mhss_excluded:gnss-cm")[1]
    assert "network builder rogers" in describe("mhss_alarm:builder:rogers")[1]


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
    mon.update(_est(0.0, status="unsafe", hpl=80.0))
    mon.acknowledge()
    s = mon.update(_est(0.1, status="unsafe", hpl=80.0))
    assert s["alerts"][0]["acked"] and s["alerts"][0]["active"]
    assert mon.update(_est(0.2))["alerts"] == []
    # it comes back after acknowledgement: a new alert
    s = mon.update(_est(5.0, status="unsafe", hpl=80.0))
    assert len(s["alerts"]) == 1 and not s["alerts"][0]["acked"]


def test_brief_clear_is_the_same_occurrence():
    mon = HealthMonitor(50.0, 1.5e-6)
    for t, on in [(0.0, True), (0.5, False), (1.0, True), (10.0, False), (20.0, True)]:
        s = mon.update(_est(t, status="unsafe" if on else "nominal", hpl=60.0 if on else 40.0))
    (a,) = s["alerts"]
    assert a["count"] == 2 and a["since_s"] == 0.0 and a["onset_s"] == 20.0


def test_low_trust_listed_apart():
    s = HealthMonitor(50.0, 1.5e-6).update(_est(0.0, trust={"gnss": 0.0, "lte": 1.0}))
    assert s["low_trust"] == {"gnss": 0.0} and s["trusted"] == {"lte": 1.0}


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
