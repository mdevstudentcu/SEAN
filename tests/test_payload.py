"""Payload recorder, live stream and day-1 tools (#19), with fake devices: no hardware.

The fakes stand in for the lowest layer only (the I2C bus, the rtl_sdr byte stream, the gpsd
socket), so the recorder code that runs on the Pi is the code under test."""

import errno
import json
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml
from mcap.reader import make_reader

from pnt.cli import main
from pnt.core import frames
from pnt.core.measurement import Measurement
from pnt.core.time import now_gps_ns
from pnt.io import mcap_log, session
from pnt.io.mcap_log import (
    SessionWriter,
    TruncatedSessionWarning,
    is_complete,
    read_json,
    read_metadata,
    read_session,
)
from pnt.payload import day1, recorder, wifi
from pnt.payload.devices import TRACKING_FIELDS, FlightController, Health, parse_chrony_csv
from pnt.payload.gpsd import Gpsd, tpv_measurements
from pnt.payload.i2c import Bmp280, Mpu6050, bmp280_compensate
from pnt.payload.recorder import Recorder
from pnt.payload.sdr import RtlSdr, estimate_t0, find_gaps
from pnt.payload.streamer import Streamer
from pnt.payload.survey import average, load_reference, survey_session, write_survey
from pnt.payload.wifi import WifiScan, hash_bssid, parse_scan
from pnt.sources.live import LiveSource

zmq = pytest.importorskip("zmq")

ORIGIN = (45.3876, -75.6960, 70.0)
BMP_CAL = (27504, 26435, -1000, 36477, -10685, 3024, 2855, 140, -7, 15500, -14600, 6000)


# --- fakes ------------------------------------------------------------------------------------


class FakeI2C:
    """Registers of an MPU6050 (0x68) and a BMP280 (0x76) at rest."""

    path = "/dev/i2c-fake"

    def __init__(self):
        imu = struct.pack(">7h", 0, 0, 4096, 0, 0, 0, 0)  # 1 g on z, no rotation
        # datasheet example: adc_P = 415148, adc_T = 519888
        p, t = 415148, 519888
        baro = bytes([p >> 12, (p >> 4) & 0xFF, (p & 0xF) << 4, t >> 12, (t >> 4) & 0xFF, 0])
        self.regs = {
            (0x68, 0x75): b"\x68",
            (0x68, 0x3B): imu,
            (0x76, 0xD0): b"\x58",
            (0x76, 0x88): struct.pack("<HhhHhhhhhhhh", *BMP_CAL),
            (0x76, 0xF7): baro,
        }
        self.writes = []

    def read(self, addr, reg, n):
        if (addr, reg) not in self.regs:
            raise OSError(121, "Remote I/O error")
        return self.regs[(addr, reg)][:n]

    def write(self, addr, reg, data):
        self.writes.append((addr, reg, bytes(data)))


class FakeSdrStream:
    """Paced like a dongle: one chunk per chunk-duration of real time, with `drop_s` of samples
    lost before chunk `drop_at` (time passes, the samples never arrive).

    `now()` is the host clock the recorder stamps buffers with: the chunk's due time plus a
    fixed 1 ms latency, so the stamps do not depend on how busy the test machine is."""

    T0_NS = 1_478_356_218_000_000_000

    def __init__(self, cmd, drop_at=30, drop_s=0.3):
        self.fs = float(cmd[cmd.index("-s") + 1])
        self.k = 0
        self.t0 = time.monotonic()
        self.drop_at, self.drop_s = drop_at, drop_s
        self.stderr = ["Found 1 device(s): fake"]
        self._now = self.T0_NS

    def now(self) -> int:
        return self._now

    def read(self, nbytes, stop=None):
        due = (self.k + 1) * (nbytes / 2) / self.fs
        if self.k >= self.drop_at:
            due += self.drop_s
        time.sleep(max(0.0, self.t0 + due - time.monotonic()))
        self._now = self.T0_NS + round(due * 1e9) + 1_000_000
        self.k += 1
        return bytes([127, 128]) * (nbytes // 2)

    def close(self):
        pass


def fake_sdr(**kw) -> RtlSdr:
    """An RtlSdr reading a FakeSdrStream and stamping with its clock."""
    holder = {}

    def factory(cmd):
        holder["s"] = FakeSdrStream(cmd, **kw)
        return holder["s"]

    return RtlSdr("a", 875e6, rate_hz=48_000, chunk=1200, stream_factory=factory,
                  clock=lambda: holder["s"].now() if "s" in holder else now_gps_ns())  # fmt: skip


class FakeGpsd:
    """A gpsd on loopback: TPV at 10 Hz for a walk east at 1.4 m/s, PPS and SKY once a second,
    all stamped with the real current time."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen()
        self.port = self.srv.getsockname()[1]
        self.stop = threading.Event()
        self.t_start = time.time()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self.stop.is_set():
            self.srv.settimeout(0.2)
            try:
                conn, _ = self.srv.accept()
            except TimeoutError:
                continue
            except OSError:  # closed
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        conn.recv(1024)  # ?WATCH
        send = lambda d: conn.sendall((json.dumps(d) + "\n").encode())  # noqa: E731
        send({"class": "DEVICES", "devices": [{"path": "/dev/serial0"}]})
        k = 0
        try:
            while not self.stop.is_set():
                now = time.time()
                east = 1.4 * (now - self.t_start)
                lat, lon, h = frames.enu_to_llh(np.array([east, 0.0, 0.0]), ORIGIN)
                iso = datetime.fromtimestamp(now, UTC).isoformat().replace("+00:00", "Z")
                send({"class": "TPV", "mode": 3, "time": iso, "lat": lat, "lon": lon,
                      "altHAE": h, "epx": 3.0, "epy": 3.0, "epv": 6.0, "speed": 1.4,
                      "track": 90.0, "climb": 0.0, "eps": 0.5, "epc": 1.0})  # fmt: skip
                if k % 10 == 0:
                    sec = int(now)
                    send({"class": "PPS", "real_sec": sec, "real_nsec": 0, "clock_sec": sec,
                          "clock_nsec": 1234, "precision": -20})  # fmt: skip
                    send(
                        {
                            "class": "SKY",
                            "hdop": 0.9,
                            "satellites": [
                                {"PRN": 5, "ss": 40, "used": True},
                                {"PRN": 7, "ss": 30, "used": False},
                            ],
                        }
                    )
                k += 1
                time.sleep(0.1)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.stop.set()
        self.srv.close()


class Broken:
    name, hardware = "camera", "pi-camera"

    def probe(self):
        return None

    def run(self, ctx):
        raise RuntimeError("boom")

    def status(self):
        return {}


# --- the round trip ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    """A 3 s handheld walk recorded with fake devices, streamed over loopback at the same time."""
    folder = tmp_path_factory.mktemp("sessions") / "20261110-1430-handheld-test"
    gpsd = FakeGpsd()
    bus = FakeI2C()
    sdr = fake_sdr()
    devices = [
        Health(),
        Gpsd(port=gpsd.port),
        Mpu6050(bus=bus),
        Bmp280(bus=bus),
        sdr,
        Broken(),
        FlightController("/dev/does-not-exist"),
    ]
    streamer = Streamer("tcp://127.0.0.1:*")
    live = LiveSource(streamer.endpoint, reorder_s=1.0, idle_timeout_s=1.5)
    live.connect()
    assert streamer.wait_for_subscriber(5.0)
    got: list[Measurement] = []
    consumer = threading.Thread(target=lambda: got.extend(live))
    consumer.start()
    rec = Recorder(folder, devices, platform="handheld", streamer=streamer)
    meta = rec.run(duration_s=3.0)
    streamer.close()
    gpsd.close()
    consumer.join(timeout=10)
    return {"folder": folder, "meta": meta, "live": got, "live_source": live, "rec": rec}


def test_record_writes_a_session_folder_per_the_icd(recorded):
    folder = recorded["folder"]
    assert sorted(p.name for p in folder.iterdir()) == [
        "meta.yaml",
        "sdr_a.cu8",
        "sdr_a.json",
        "session.mcap",
    ]
    meta = yaml.safe_load((folder / "meta.yaml").read_text())
    assert list(meta) == list(session.META_KEYS)
    assert meta["name"] == folder.name and meta["simulated"] is False
    assert meta["origin_llh"] == pytest.approx(ORIGIN, abs=1e-5)  # the first 3D fix
    assert {"mpu6050", "bmp280", "adafruit-gps-hat", "rtl-sdr", "host"} <= set(meta["hardware"])


def test_one_failing_or_absent_device_does_not_stop_the_others(recorded):
    notes = recorded["meta"]["notes"]
    assert "failed: camera (pi-camera): RuntimeError('boom')" in notes
    assert "absent: fc (flight-controller): /dev/does-not-exist does not exist" in notes
    counts = recorded["rec"].counts
    # Regression guard, not a requirement: 3 s of nominal 100 Hz, 10 Hz and 20 records/s, set
    # well below nominal because these fakes run in real time on a busy test machine.
    assert counts["imu"] > 150 and counts["baro"] > 20 and counts["gnss"] > 40


def test_recorded_measurements_follow_the_icd(recorded):
    meas = [r for _, r in read_session(recorded["folder"] / "session.mcap", topics=["/meas/"])]
    kinds = {(m.source, m.kind) for m in meas}
    assert kinds == {
        ("imu", "accel_gyro"),
        ("baro", "altitude"),
        ("gnss", "position_enu"),
        ("gnss", "velocity_enu"),
    }
    assert all(isinstance(m.t_ns, int) and m.receiver == "payload" for m in meas)
    # read_session sorts, so look at the file itself: each IMU sample is later than the last
    with open(recorded["folder"] / "session.mcap", "rb") as f:
        written = [
            json.loads(msg.data)["t_ns"]
            for _, channel, msg in make_reader(f).iter_messages(log_time_order=False)
            if channel.topic == "/meas/imu"
        ]
    assert written and all(a < b for a, b in zip(written, written[1:], strict=False))
    imu = next(m for m in meas if m.source == "imu")
    assert imu.value == pytest.approx((0, 0, 9.80665, 0, 0, 0))
    # times are GPS ns of now, not of 1970 or of the sim's epoch
    assert abs(meas[-1].t_ns - now_gps_ns()) < 60e9
    baro = [m for m in meas if m.source == "baro"]
    assert baro[0].value[0] == pytest.approx(0.0, abs=1.0)  # referenced to the first fix
    assert baro[0].meta["pressure_pa"] == pytest.approx(100653.27, abs=0.01)


def test_sdr_sidecar_has_buffer_stamps_that_show_the_planted_drop(recorded):
    side = json.loads((recorded["folder"] / "sdr_a.json").read_text())
    # the LTE front end's sidecar keys and types (frontends/lte/capture.py, #23)
    assert isinstance(side["sample_rate_hz"], float) and isinstance(side["center_freq_hz"], float)
    assert isinstance(side["t_ns"], int) and side["dongle"] == "sdr_a"
    assert side["gain_db"] is None and side["gain_mode"] == "auto"  # AGC
    assert side["hops"] == [] and side["gaps"] == []  # no drop is known to the sample
    assert all(isinstance(v, int) for b in side["buffers"] for v in b)
    assert side["samples"] * 2 == (recorded["folder"] / "sdr_a.cu8").stat().st_size
    assert side["buffers"][0][0] == 0
    (gap,) = side["gaps_suspected"]
    assert gap[0] == 30 * 1200  # the fake stream lost samples just before chunk 30
    assert gap[1] == 0.3 * 48_000
    assert side["t_ns"] == FakeSdrStream.T0_NS + 1_000_000  # the latency floor


def test_recorded_walk_replays_through_pnt_replay(recorded, capsys):
    main(["replay", str(recorded["folder"])])
    out = capsys.readouterr().out
    n = int(out.split(":")[1].split()[0])
    assert n > 20, out  # regression guard, not a requirement: the walk produced estimates


def test_live_stream_equals_what_was_recorded(recorded):
    """ADR-0004: the live source yields the recorded records, time-ordered, nothing late."""
    live = recorded["live"]
    rec = [r for _, r in read_session(recorded["folder"] / "session.mcap", topics=["/meas/"])]
    assert [m.t_ns for m in live] == sorted(m.t_ns for m in live)
    key = lambda m: (m.t_ns, m.source, m.kind, m.value)  # noqa: E731
    assert sorted(map(key, live)) == sorted(map(key, rec))
    src = recorded["live_source"]
    assert src.stats["late"] == 0 and src.stats["bad"] == 0
    assert src.meta["payload"]["origin_llh"] == pytest.approx(ORIGIN, abs=1e-5)


def test_events_hold_pps_health_and_device_status(recorded):
    events = [e for _, e in read_json(recorded["folder"] / "session.mcap", ["/events"])]
    texts = {e["text"] for e in events}
    assert {"pps", "health", "status", "system", "gnss_sky", "camera failed"} <= texts
    pps = next(e for e in events if e["text"] == "pps")
    assert pps["offset_ns"] == 1234


def test_day1_report_from_the_recorded_session(recorded, tmp_path):
    r = day1.report(recorded["folder"], usb_current_a=1.23)
    # Regression guards, not requirements: ADR-0018's thresholds are TBD, and this is a fake IMU
    # sampled in real time for 3 s at a nominal 100 Hz.
    assert r["imu"]["rate_hz"] == pytest.approx(100, rel=0.05)
    assert r["imu"]["jitter_ms"]["n"] > 200
    assert r["sdr"][0]["gaps"] == 1
    assert r["pps"]["edges"] >= 2 and r["pps"]["offset_us"]["mean"] == pytest.approx(1.234)
    assert r["usb_current_a"] == 1.23
    md = day1.to_markdown(r)
    assert "USB current (A) | 1.23" in md and "IMU jitter" in md
    out = tmp_path / "r.day1.md"
    main(["day1", str(recorded["folder"]), "--out", str(out)])
    assert out.exists() and out.with_suffix(".json").exists()


# --- units ------------------------------------------------------------------------------------


def _stamps(rng, n_buf=2000, chunk=131072, fs=1.92e6, drop_at=700, drop=200_000, ppm=2.0):
    idx = np.arange(n_buf) * chunk
    t_true = 1_446_000_000_123_456_789 + idx / fs * 1e9 * (1 - ppm * 1e-6)
    t_true[drop_at:] += drop / fs * 1e9
    lat = 1e6 + rng.exponential(2e6, n_buf)  # 1 ms floor, a few ms of jitter
    return np.c_[idx, (t_true + lat).astype(np.int64)]


def test_find_gaps_locates_and_sizes_a_drop():
    b = _stamps(np.random.default_rng(0))
    assert find_gaps(b, 1.92e6) == [(700 * 131072, pytest.approx(200_000, abs=2000))]
    assert find_gaps(b[:600], 1.92e6) == []


def test_t0_is_the_latency_floor_and_rate_error_is_measured():
    # 136 s at 20 ppm: 2.7 ms of drift, against ms of latency jitter
    b = _stamps(np.random.default_rng(1), drop=0, ppm=20.0)
    t0, ppm = estimate_t0(b, 1.92e6)
    assert (t0 - 1_446_000_000_123_456_789) / 1e6 == pytest.approx(1.0, abs=0.2)  # 1 ms floor
    assert ppm == pytest.approx(20.0, abs=2.0)


def test_a_stall_that_catches_up_is_not_a_drop():
    b = _stamps(np.random.default_rng(2), drop=0)
    b[500:510, 1] += 150_000_000  # 150 ms scheduling stall, then the backlog drains
    assert find_gaps(b, 1.92e6) == []


def test_bmp280_compensation_matches_the_datasheet_example():
    temp, p = bmp280_compensate(519888, 415148, BMP_CAL)
    assert temp == pytest.approx(25.08, abs=0.01) and p == pytest.approx(100653.27, abs=0.01)


def test_mpu6050_scaling():
    raw = struct.pack(">7h", 4096, -4096, 0, 0, 655, 0, -655)
    value, temp = Mpu6050.decode(raw)
    assert value == pytest.approx((9.80665, -9.80665, 0, np.radians(10), 0, -np.radians(10)))
    assert temp == pytest.approx(36.53)


def test_absent_i2c_sensors_say_why():
    bus = FakeI2C()
    bus.regs.clear()
    assert "no MPU6050" in Mpu6050(bus=bus).probe()
    assert "no BMP280" in Bmp280(bus=bus).probe()


def test_gpsd_fix_becomes_enu_with_95pct_errors_as_sigma():
    lat, lon, h = frames.enu_to_llh(np.array([10.0, -5.0, 2.0]), ORIGIN)
    tpv = {"class": "TPV", "mode": 3, "time": "2026-11-10T14:30:00.000Z", "lat": lat,
           "lon": lon, "altHAE": h, "epx": 3.92, "epy": 3.92, "epv": 7.84}  # fmt: skip
    (m,) = tpv_measurements(tpv, ORIGIN)
    assert m.kind == "position_enu" and m.value == pytest.approx((10, -5, 2), abs=1e-3)
    assert m.sigma == pytest.approx((2.0, 2.0, 4.0))
    assert m.t_ns == 1_478_356_218_000_000_000  # 2026-11-10 14:30:00 UTC + 18 leap s
    assert tpv_measurements({**tpv, "mode": 2}, ORIGIN) == []  # 2D fix: no height, not used


def test_bssids_are_hashed_at_capture_req08():
    scan = (
        "BSS 00:11:22:33:44:55(on wlan0)\n\tfreq: 2412\n\tsignal: -48.00 dBm\n\tSSID: home\n"
        "BSS aa:bb:cc:dd:ee:ff(on wlan0) -- associated\n\tfreq: 5180\n\tsignal: -71.00 dBm\n"
    )
    aps = parse_scan(scan, salt=b"s" * 32)
    assert [a["rssi_dbm"] for a in aps] == [-48.0, -71.0]
    assert aps[0]["bssid_hash"] == hash_bssid("00:11:22:33:44:55", b"s" * 32)
    assert aps[0]["bssid_hash"] != hash_bssid("00:11:22:33:44:55", b"t" * 32)  # salted
    text = json.dumps(aps)
    for raw in ("00:11:22", "001122", "aa:bb", "aabbcc", "home"):
        assert raw not in text


def test_live_source_reorders_and_counts_late_records():
    pub = Streamer("tcp://127.0.0.1:*")
    src = LiveSource(pub.endpoint, reorder_s=1.0, idle_timeout_s=0.5)
    src.connect()
    assert pub.wait_for_subscriber(5.0)

    def m(t):
        return Measurement(t_ns=int(t), source="baro", kind="altitude", value=(0.0,), sigma=(1,))

    out = []
    consumer = threading.Thread(target=lambda: out.extend(x.t_ns for x in src))
    consumer.start()
    for t in (0, 2e8, 1e8, 5e9, 10e9):  # out of order inside the 1 s window: sorted
        pub.send(m(t))
    time.sleep(0.3)  # 5e9 is released (10e9 - 1 s is past it) ...
    pub.send(m(4e9))  # ... so 4e9 is late
    consumer.join(timeout=5)
    pub.close()
    assert out == [0, 1e8, 2e8, 5e9, 10e9]
    assert src.stats["late"] == 1 and src.stats["received"] == 6


def test_survey_sigma_comes_from_batch_means_not_sqrt_n():
    rng = np.random.default_rng(0)
    n = 7200  # 2 h of 1 Hz fixes
    ar = np.zeros((n, 3))
    phi = np.exp(-1 / 300)  # errors correlated over 5 min, 2 m
    for k in range(1, n):
        ar[k] = phi * ar[k - 1] + rng.normal(0, 2 * np.sqrt(1 - phi**2), 3)
    t = np.arange(n) * 1_000_000_000
    res = average(t, ar)
    naive = 2 / np.sqrt(n)
    assert res["stats"]["batches"] == 12
    # Regression guard, not a requirement: batch means must sit clearly above the sqrt(N) figure
    assert res["sigma_m"] > 5 * naive
    assert np.abs(res["mean_enu"]).max() < 4 * res["sigma_m"]
    assert average(t[:1800], ar[:1800])["sigma_m"] == "TBD"  # 30 min: 3 batches


def test_survey_from_a_session_writes_a_valid_reference_block(tmp_path):
    folder = tmp_path / "base"
    folder.mkdir()
    session.write_meta(folder, {"name": "base", "origin_llh": list(ORIGIN)})
    rng = np.random.default_rng(1)
    with SessionWriter(folder / "session.mcap") as w:
        for k in range(3000):
            e = rng.normal(0, 2, 3) + (1.0, 2.0, 3.0)
            w.write("/meas/gnss", Measurement(t_ns=k * 10**9, source="gnss",
                    kind="position_enu", value=tuple(e), sigma=(2, 2, 3),
                    receiver="reference"))  # fmt: skip
    res = survey_session(folder)
    ref = res["reference"]
    assert ref["surveyed"] is True and isinstance(ref["sigma_m"], float)
    expect = frames.enu_to_llh(np.array([1.0, 2.0, 3.0]), ORIGIN)
    assert ref["position_llh"][:2] == pytest.approx(list(expect[:2]), abs=1e-6)  # ~0.1 m
    assert ref["position_llh"][2] == pytest.approx(expect[2], abs=0.2)
    out = write_survey(res, tmp_path / "s.yaml")
    assert load_reference(out) == ref


def test_ppstest_and_chrony_output_parse():
    text = (
        'trying PPS source "/dev/pps0"\nfound PPS source "/dev/pps0"\n'
        "ok, found 1 source(s), now start fetching data...\n"
        "source 0 - assert 1762785000.000000412, sequence: 100 - clear  0.000000000, sequence: 0\n"
        "source 0 - assert 1762785000.999999700, sequence: 101 - clear  0.000000000, sequence: 0\n"
        "source 0 - assert 1762785002.000000100, sequence: 102 - clear  0.000000000, sequence: 0\n"
    )
    s = day1.pps_summary(day1.parse_ppstest(text))
    assert s["edges"] == 3 and s["rate_hz"] == pytest.approx(1.0, abs=1e-3)
    assert s["offset_us"]["max_abs"] == pytest.approx(0.412)
    row = parse_chrony_csv(
        "50505300,PPS,1,1762785000.1,0.000000012,0.000000034,0.000000210,-12.3,0.001,0.010,"
        "0.000000001,0.000010,16.0,Normal\n",
        TRACKING_FIELDS,
    )[0]
    assert row["ref_name"] == "PPS" and row["rms_offset_s"] == pytest.approx(2.1e-7)


def test_pnt_record_cli_notes_every_absent_device(tmp_path, capsys):
    """On a machine with none of the hardware, `pnt record` still writes a valid session."""
    out = tmp_path / "s"
    with socket.socket() as s:  # a port with no gpsd behind it
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    args = ["record", "--out", str(out), "--duration", "1.5", "--no-stream", "--gpsd-port"]
    args += [str(port), "--fc", "/dev/does-not-exist", "--sdr", "a:875e6:dev=7"]
    main(args)
    meta = session.read_meta(out)
    assert meta["hardware"] == ["host"]
    for name in ("gnss", "fc", "imu", "baro", "camera"):
        assert f"absent: {name} " in meta["notes"]
    assert "sdr_a " in meta["notes"]  # absent (no rtl_sdr) or failed (no dongle at index 7)
    assert "recording" in capsys.readouterr().out


def test_payload_code_needs_only_the_payload_extra():
    """quality.md: Pi code needs only the `payload` extra. Import it with the ground-only
    packages blocked."""

    code = (
        "import sys, importlib.abc\n"
        "class B(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name.split('.')[0] in {'scipy','matplotlib','fastapi','uvicorn','pyModeS',"
        "'sgp4','numba'}:\n"
        "            raise ImportError(name)\n"
        "sys.meta_path.insert(0, B())\n"
        "import pnt.cli, pnt.payload.config, pnt.payload.day1, pnt.payload.survey\n"
        "import pnt.payload.streamer, pnt.sources.live, pnt.io.linkauth, zmq.auth.thread\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


# A stand-in for rtl_sdr: 10 chunks of IQ, then silence like a stuck dongle.
STUCK_SDR = (
    "import sys, time\n"
    "sys.stderr.write('Found 1 device(s)\\n'); sys.stderr.flush()\n"
    "for _ in range(10):\n"
    "    sys.stdout.buffer.write(bytes(2400)); sys.stdout.buffer.flush(); time.sleep(0.05)\n"
    "time.sleep(60)\n"
)
# A stand-in for rpicam-vid: writes to its output until SIGINT, then exits cleanly.
FAKE_CAMERA = (
    "import signal, sys, time\n"
    "signal.signal(signal.SIGINT, lambda *a: sys.exit(0))\n"
    "f = open(sys.argv[1], 'wb')\n"
    "while True:\n"
    "    f.write(b'frame'); f.flush(); time.sleep(0.05)\n"
)


def test_real_readers_stop_cleanly_even_when_a_dongle_is_stuck(tmp_path):
    """The pipe reader and the camera process, through their real code paths (a Python
    stand-in replaces the binary). A dongle that stops sending must not hang the recorder."""
    from pnt.payload.devices import Camera
    from pnt.payload.sdr import RtlSdrStream

    stand_in = [sys.executable, "-c", STUCK_SDR]
    sdr = RtlSdr(
        "a", 48e3, rate_hz=48e3, chunk=1200, stream_factory=lambda _: RtlSdrStream(stand_in)
    )
    cam = Camera(cmd=[sys.executable, "-c", FAKE_CAMERA])
    t = time.monotonic()
    meta = Recorder(tmp_path / "s", [sdr, cam]).run(duration_s=1.5)
    assert time.monotonic() - t < 10
    assert set(meta["hardware"]) == {"rtl-sdr", "pi-camera"}, meta["notes"]
    side = json.loads((tmp_path / "s" / "sdr_a.json").read_text())
    assert side["samples"] == 10 * 1200 and side["stderr"] == ["Found 1 device(s)"]
    cam_json = json.loads((tmp_path / "s" / "camera.json").read_text())
    assert cam_json["t_ns"] >= cam_json["t_ns_launch"]
    assert (tmp_path / "s" / "camera.mp4").stat().st_size > 0


def test_pnt_live_runs_the_estimator_on_the_stream_and_records_it(tmp_path, capsys):
    """`pnt live` over loopback: origin from the payload's meta, estimates printed, the stream
    and the estimates recorded to a session that `pnt replay` reads. The stream is authenticated
    (ADR-0026), as `pnt live` requires by default; both sessions say so."""
    if not zmq.has("curve"):
        pytest.skip("libzmq built without CURVE")
    from pnt.io import linkauth

    pi_keys, laptop_keys = tmp_path / "pi-keys", tmp_path / "laptop-keys"
    linkauth.trust("laptop", linkauth.generate("laptop", laptop_keys).decode(), pi_keys)
    linkauth.trust("payload", linkauth.generate("payload", pi_keys).decode(), laptop_keys)
    gpsd = FakeGpsd()
    bus = FakeI2C()
    streamer = Streamer("tcp://127.0.0.1:*", auth=linkauth.server_auth("payload", pi_keys))
    rec = Recorder(tmp_path / "pi", [Gpsd(port=gpsd.port), Mpu6050(bus=bus), Bmp280(bus=bus)],
                   streamer=streamer)  # fmt: skip
    pi = threading.Thread(target=rec.run, kwargs={"duration_s": 5.0})
    pi.start()
    out = tmp_path / "live"
    main(["live", "--connect", streamer.endpoint, "--duration", "4", "--out", str(out),
          "--keys", str(laptop_keys)])  # fmt: skip
    pi.join()
    streamer.close()
    gpsd.close()
    printed = capsys.readouterr().out
    assert "enu=(" in printed and "'late': 0" in printed
    meta = session.read_meta(out)
    assert meta["origin_llh"] == pytest.approx(ORIGIN, abs=1e-5)
    assert "stream: authenticated, CurveZMQ" in meta["notes"]
    assert "stream: authenticated, CurveZMQ" in session.read_meta(tmp_path / "pi")["notes"]
    topics = {t for t, _ in read_session(out / "session.mcap")}
    assert {"/meas/gnss", "/meas/imu", "/nav/baseline"} <= topics


def test_reference_station_records_are_tagged_reference(tmp_path):
    """The base runs the same recorder with `--receiver reference` (ADR-0020, ICD-measurement):
    every record and its stream metadata carry that receiver."""
    gpsd = FakeGpsd()
    streamer = Streamer("tcp://127.0.0.1:*")
    live = LiveSource(streamer.endpoint, idle_timeout_s=1.5)
    live.connect()
    assert streamer.wait_for_subscriber(5.0)
    got = []
    consumer = threading.Thread(target=lambda: got.extend(live))
    consumer.start()
    ref = {"position_llh": list(ORIGIN), "surveyed": True, "sigma_m": 0.4}
    Recorder(tmp_path / "base", [Gpsd(port=gpsd.port, hardware="neo-6m")], receiver="reference",
             origin_llh=ORIGIN, reference=ref, streamer=streamer).run(duration_s=2.0)  # fmt: skip
    streamer.close()
    gpsd.close()
    consumer.join(timeout=10)
    recorded = [r for _, r in read_session(tmp_path / "base" / "session.mcap")]
    assert recorded and {r.receiver for r in recorded} == {"reference"}
    assert got and {r.receiver for r in got} == {"reference"}
    assert live.meta["reference"]["reference"] == ref
    assert session.read_meta(tmp_path / "base")["hardware"] == ["neo-6m"]


def test_gpsd_repeats_of_one_fix_are_fused_once():
    class Ctx:
        origin_llh = ORIGIN
        last_fix = None

        def __init__(self):
            self.out = []

        def set_origin_once(self, llh):
            return ORIGIN

        def emit(self, m):
            self.out.append(m)

    tpv = {"class": "TPV", "mode": 3, "time": "2026-11-10T14:30:00.000Z", "lat": ORIGIN[0],
           "lon": ORIGIN[1], "altHAE": ORIGIN[2], "epx": 3.0, "epy": 3.0, "epv": 6.0}  # fmt: skip
    ctx, g = Ctx(), Gpsd()
    for msg in (tpv, tpv, {**tpv, "time": "2026-11-10T14:30:01.000Z"}):
        g.handle(msg, ctx)
    assert [m.t_ns for m in ctx.out] == [1_478_356_218_000_000_000, 1_478_356_219_000_000_000]
    assert g.status()["repeated_tpv"] == 1


# --- sessions cut off without close -----------------------------------------------------------

CUT_OFF_WRITER = """
import os, sys
from pnt.core.measurement import Measurement
from pnt.io.mcap_log import SessionWriter

w = SessionWriter(sys.argv[1], metadata={"name": "cut"})
for k in range(int(sys.argv[2])):
    w.write("/meas/imu", Measurement(t_ns=k * 10**7, source="imu", kind="accel_gyro",
            value=(0.1 * k, 0.2, 9.8, 0.0, 0.0, 0.0), sigma=(1.0,) * 6))
    w.write_json("/events", k * 10**7, {"text": "tick", "k": k})
os._exit(0)  # no close: what a kill or a crash leaves
"""


@pytest.fixture(scope="module")
def cut_off(tmp_path_factory):
    """A session whose writer process ended without closing it."""

    path = tmp_path_factory.mktemp("cut") / "session.mcap"
    n = 30_000
    subprocess.run([sys.executable, "-c", CUT_OFF_WRITER, str(path), str(n)], check=True)
    return path, n


def test_cut_off_session_is_read_up_to_its_last_complete_chunk(cut_off):
    path, n = cut_off
    assert not is_complete(path)
    with pytest.warns(TruncatedSessionWarning, match="cut off"):
        recs = [r for _, r in read_session(path, topics=["/meas/"])]
    with pytest.warns(TruncatedSessionWarning):
        events = [e for _, e in read_json(path, ["/events"])]
    # the records are a gapless prefix of what was written
    assert [r.t_ns for r in recs] == [k * 10**7 for k in range(len(recs))]
    assert [e["k"] for e in events] == list(range(len(events)))
    # at most one chunk in progress is lost: each pair is at least 150 bytes of JSON
    assert n - len(recs) <= mcap_log.CHUNK_SIZE / 150
    assert len(recs) > 0
    assert read_metadata(path) == {"name": "cut"}


def test_pnt_replay_reads_a_cut_off_session_and_says_so(cut_off, capsys):
    path, _ = cut_off
    with pytest.warns(TruncatedSessionWarning, match="cut off"):
        main(["replay", str(path)])
    assert "replayed" in capsys.readouterr().out


def test_torn_chunk_is_dropped_and_records_come_back_in_time_order(tmp_path):
    """A cut in the middle of a chunk: the torn chunk is left out, the earlier ones are read,
    and records logged out of order still come back in log-time order."""
    path = tmp_path / "torn.mcap"

    def m(t):
        return Measurement(t_ns=t, source="baro", kind="altitude", value=(0.0,), sigma=(1.0,))

    with SessionWriter(path) as w:
        for t in (30, 10, 20):
            w.write("/meas/baro", m(t))
        w.flush()
        first_chunk_end = path.stat().st_size
        for t in (60, 50):
            w.write("/meas/baro", m(t))
    data = path.read_bytes()
    path.write_bytes(data[: first_chunk_end + 20])
    with pytest.warns(TruncatedSessionWarning):
        assert [r.t_ns for _, r in read_session(path)] == [10, 20, 30]


def test_read_session_returns_log_time_order_whatever_the_write_order(tmp_path):
    path = tmp_path / "order.mcap"
    with SessionWriter(path) as w:
        for t in (30, 10, 20):
            w.write("/meas/baro", Measurement(t_ns=t, source="baro", kind="altitude",
                                              value=(0.0,), sigma=(1.0,)))  # fmt: skip
    assert [r.t_ns for _, r in read_session(path)] == [10, 20, 30]


def test_empty_file_reads_as_an_empty_truncated_session(tmp_path):
    path = tmp_path / "empty.mcap"
    path.touch()
    with pytest.warns(TruncatedSessionWarning):
        assert list(read_session(path)) == []
    assert read_metadata(path) == {}


def test_closed_session_is_still_complete_valid_mcap(tmp_path):
    path = tmp_path / "ok.mcap"
    with SessionWriter(path) as w:
        w.write_json("/events", 5, {"text": "x"})
        w.flush()  # a flush mid-file changes the chunking only
        w.write_json("/events", 6, {"text": "y"})
    assert is_complete(path)
    with open(path, "rb") as f:
        reader = make_reader(f, validate_crcs=True)
        assert reader.get_summary().statistics.message_count == 2
        assert len(list(reader.iter_messages())) == 2


def test_killed_recorder_leaves_a_session_that_replays(tmp_path):
    """`kill -9` of a running `pnt record`, no devices: the file has its header, and
    `pnt replay` reports the cut instead of crashing."""

    out = tmp_path / "s"
    code = "import sys; from pnt.cli import main; main(sys.argv[1:])"
    cmd = [sys.executable, "-u", "-c", code, "record", "--out", str(out), "--no-stream",
           "--no-gnss", "--no-imu", "--no-baro", "--no-camera", "--no-fc"]  # fmt: skip
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    try:
        assert "recording" in proc.stdout.readline()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not (out / "meta.yaml").exists():
            time.sleep(0.05)
        proc.kill()
    finally:
        proc.kill()
        proc.wait()
        proc.stdout.close()
    assert (out / "session.mcap").stat().st_size > 0
    assert not is_complete(out / "session.mcap")
    with pytest.warns(TruncatedSessionWarning, match="cut off"):
        main(["replay", str(out)])


# --- disk full --------------------------------------------------------------------------------


class Chatty:
    """Emits a record every few ms until told to stop."""

    name, hardware = "imu", "chatty"

    def probe(self):
        return None

    def status(self):
        return {}

    def run(self, ctx):
        k = 0
        while not ctx.stop.wait(0.002):
            k += 1
            ctx.emit(Measurement(t_ns=k, source="baro", kind="altitude", value=(0.0,),
                                 sigma=(1.0,)))  # fmt: skip


class FakeStream:
    def __init__(self):
        self.sent = 0

    def send(self, m):
        self.sent += 1

    def send_meta(self, meta, receiver):
        pass


def test_disk_full_keeps_the_drain_alive_and_stop_still_finishes(tmp_path, monkeypatch):
    enospc = OSError(errno.ENOSPC, "No space left on device")

    class FullDisk(SessionWriter):
        """Every write fails after the first few, as on a card that has just filled."""

        calls = 0
        close_attempts = 0

        def write(self, *a):
            FullDisk.calls += 1
            if FullDisk.calls > 20:
                raise enospc
            super().write(*a)

        def write_json(self, *a):
            if FullDisk.calls > 20:
                raise enospc
            super().write_json(*a)

        def close(self):
            FullDisk.close_attempts += 1
            self._file.close()
            raise enospc

    died = []
    monkeypatch.setattr(threading, "excepthook", lambda a: died.append(a.exc_value))
    monkeypatch.setattr(recorder, "SessionWriter", FullDisk)
    monkeypatch.setattr(recorder, "STATUS_PERIOD_S", 0.05)
    stream = FakeStream()
    folder = tmp_path / "s"
    meta = Recorder(folder, [Chatty()], streamer=stream).run(duration_s=0.5)
    assert died == []
    assert FullDisk.close_attempts == 1
    assert stream.sent > 20  # the live stream outlasts the log
    on_disk = session.read_meta(folder)
    assert on_disk["notes"] == meta["notes"]  # the final meta.yaml was written
    assert "could not close session.mcap" in meta["notes"]
    assert "records that could not be written" in meta["notes"]
    assert "No space left" in meta["notes"]


def test_a_failed_meta_write_leaves_the_last_good_meta(tmp_path, monkeypatch):
    session.write_meta(tmp_path, {"name": "good"})

    def full(self, text):
        open(self, "w").close()  # opened for writing and truncated, then no space
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "write_text", full)
    with pytest.raises(OSError):
        session.write_meta(tmp_path, {"name": "new"})
    monkeypatch.undo()
    assert session.read_meta(tmp_path)["name"] == "good"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["meta.yaml"]


# --- signals ----------------------------------------------------------------------------------

# `pnt record` with a device that takes a second to stop and a stand-in camera.
RECORD_HARNESS = """
import sys, time
from pnt.payload import config
from pnt.payload.devices import Camera, Health

CAMERA = sys.argv.pop(1)


class SlowToStop:
    name, hardware = "slow", "slow"

    def probe(self):
        return None

    def status(self):
        return {}

    def run(self, ctx):
        ctx.stop.wait()
        print("stopping", flush=True)
        time.sleep(1.0)


config.build = lambda args: [Health(), SlowToStop(), Camera(cmd=[sys.executable, "-c", CAMERA])]
from pnt.cli import main

main(sys.argv[1:])
"""
# A stand-in for rpicam-vid that leaves a mark when SIGINT reaches it.
MARKING_CAMERA = (
    "import signal, sys, time\n"
    "out = sys.argv[1]\n"
    "def done(*a):\n"
    "    open(out + '.sigint', 'w').close(); sys.exit(0)\n"
    "signal.signal(signal.SIGINT, done)\n"
    "f = open(out, 'wb')\n"
    "while True:\n"
    "    f.write(b'frame'); f.flush(); time.sleep(0.05)\n"
)


def _start_recording(folder):
    """`pnt record` in its own process, returned once the camera is writing."""

    cmd = [sys.executable, "-u", "-c", RECORD_HARNESS, MARKING_CAMERA, "record", "--out",
           str(folder), "--no-stream"]  # fmt: skip
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 30
    video = folder / "camera.mp4"
    while time.monotonic() < deadline and not (video.exists() and video.stat().st_size > 0):
        time.sleep(0.02)
    assert video.exists(), "the stand-in camera never started"
    return proc


def _assert_finished_cleanly(proc, folder):
    try:
        assert proc.wait(timeout=30) == 0
    finally:
        proc.kill()
        proc.stdout.close()
    assert is_complete(folder / "session.mcap")
    assert "pi-camera" in session.read_meta(folder)["hardware"]
    assert (folder / "camera.mp4.sigint").exists()  # stopped, not left running


def test_sighup_still_finishes_the_session(tmp_path):
    """A dropped ssh session must not cut the recording off."""
    folder = tmp_path / "s"
    proc = _start_recording(folder)
    proc.send_signal(signal.SIGHUP)
    _assert_finished_cleanly(proc, folder)


def test_a_second_ctrl_c_while_stopping_still_finishes_the_session(tmp_path):
    folder = tmp_path / "s"
    proc = _start_recording(folder)
    proc.send_signal(signal.SIGINT)
    while "stopping" not in proc.stdout.readline():
        pass
    proc.send_signal(signal.SIGINT)  # impatient: while the devices are still stopping
    _assert_finished_cleanly(proc, folder)


@pytest.mark.skipif(sys.platform != "linux", reason="PR_SET_PDEATHSIG is Linux only")
def test_camera_does_not_outlive_a_killed_recorder(tmp_path):
    folder = tmp_path / "s"
    proc = _start_recording(folder)
    proc.kill()
    proc.wait()
    proc.stdout.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not (folder / "camera.mp4.sigint").exists():
        time.sleep(0.05)
    assert (folder / "camera.mp4.sigint").exists()


# --- Wi-Fi scans ------------------------------------------------------------------------------

IW_OUTPUT = "BSS 00:11:22:33:44:55(on wlan0)\n\tfreq: 2412\n\tsignal: -48.00 dBm\n"


class ScanCtx:
    """One scan's worth of recorder context: stops as soon as the scan has run."""

    def __init__(self):
        self.stop = threading.Event()
        self.records = []

    def emit(self, m):
        self.records.append(m)

    def event(self, t_ns, text, **data):
        pass


def _run_one_scan(monkeypatch, on_scan=lambda cmd: None):
    ctx = ScanCtx()

    def fake_run(cmd, **kw):
        on_scan(cmd)
        ctx.stop.set()
        return subprocess.CompletedProcess(cmd, 0, stdout=IW_OUTPUT, stderr="")

    monkeypatch.setattr(wifi.subprocess, "run", fake_run)
    WifiScan(salt=b"s" * 32).run(ctx)
    return ctx


def test_wifi_records_are_stamped_after_the_scan(monkeypatch):
    clock = {"now": 1_000}
    monkeypatch.setattr(wifi, "now_gps_ns", lambda: clock["now"])
    ctx = _run_one_scan(monkeypatch, lambda cmd: clock.update(now=9_000_000_000))
    assert [m.t_ns for m in ctx.records] == [9_000_000_000]


def test_wifi_scan_asks_for_a_passive_scan_req07(monkeypatch):
    """Without `passive`, `iw` sends probe requests: a transmission REQ-07 does not allow."""
    seen = []
    _run_one_scan(monkeypatch, seen.append)
    (cmd,) = seen
    assert cmd[cmd.index("scan") :] == ["scan", "passive"]


# --- pnt live --out metadata ------------------------------------------------------------------

ORIGIN_ARG = ",".join(map(str, ORIGIN))


def test_pnt_live_with_origin_fills_in_the_payloads_meta_when_it_arrives(tmp_path):
    gpsd = FakeGpsd()
    streamer = Streamer("tcp://127.0.0.1:*")
    rec = Recorder(tmp_path / "pi", [Gpsd(port=gpsd.port)], platform="vehicle", streamer=streamer)
    pi = threading.Thread(target=rec.run, kwargs={"duration_s": 4.0})
    pi.start()
    out = tmp_path / "live"
    main(["live", "--connect", streamer.endpoint, "--origin", ORIGIN_ARG, "--duration", "3",
          "--out", str(out), "--insecure"])  # fmt: skip
    pi.join()
    streamer.close()
    gpsd.close()
    meta = session.read_meta(out)
    assert meta["platform"] == "vehicle" and meta["hardware"] == ["adafruit-gps-hat"]
    assert f"payload commit {rec.meta()['commit']}" in meta["notes"]


def test_pnt_live_with_origin_says_unknown_if_the_payload_never_spoke(tmp_path):
    out = tmp_path / "live"
    main(["live", "--connect", "tcp://127.0.0.1:9", "--origin", ORIGIN_ARG, "--duration", "0.3",
          "--out", str(out), "--insecure"])  # fmt: skip
    meta = session.read_meta(out)
    assert meta["platform"] == "unknown" and meta["hardware"] == ["unknown"]
    assert "payload commit unknown" in meta["notes"] and "None" not in meta["notes"]


def test_survey_without_fixes_exits_cleanly(tmp_path):
    # A session recorded with no GPS (e.g. on a laptop) has no origin: one clear line, no traceback
    from pnt.cli import main
    from pnt.io.mcap_log import SessionWriter
    from pnt.io.session import write_meta

    folder = tmp_path / "s"
    folder.mkdir()
    SessionWriter(folder / "session.mcap").close()
    write_meta(folder, {"platform": "static"})
    with pytest.raises(SystemExit) as e:
        main(["survey", str(folder)])
    assert str(e.value).startswith("survey: ")


def test_each_session_gets_its_own_wifi_salt():
    # ADR-0011: a session's BSSID hashes can't be linked to another session's
    from pnt.payload.wifi import new_salt

    a, b = new_salt(), new_salt()
    assert a != b and len(a) == 32
    assert hash_bssid("00:11:22:33:44:55", a) != hash_bssid("00:11:22:33:44:55", b)
