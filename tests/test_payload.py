"""Payload recorder, live stream and day-1 tools (#19), with fake devices: no hardware.

The fakes stand in for the lowest layer only (the I2C bus, the rtl_sdr byte stream, the gpsd
socket), so the recorder code that runs on the Pi is the code under test."""

import json
import socket
import struct
import threading
import time
from datetime import UTC, datetime

import numpy as np
import pytest
import yaml

from pnt.cli import main
from pnt.core import frames
from pnt.core.measurement import Measurement
from pnt.core.time import now_gps_ns
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_json, read_session
from pnt.payload import day1
from pnt.payload.devices import TRACKING_FIELDS, FlightController, Health, parse_chrony_csv
from pnt.payload.gpsd import Gpsd, tpv_measurements
from pnt.payload.i2c import Bmp280, Mpu6050, bmp280_compensate
from pnt.payload.recorder import Recorder
from pnt.payload.sdr import RtlSdr, estimate_t0, find_gaps
from pnt.payload.streamer import Streamer
from pnt.payload.survey import average, load_reference, survey_session, write_survey
from pnt.payload.wifi import hash_bssid, parse_scan
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
    assert [m.t_ns for m in meas] == sorted(m.t_ns for m in meas)
    imu = next(m for m in meas if m.source == "imu")
    assert imu.value == pytest.approx((0, 0, 9.80665, 0, 0, 0))
    # times are GPS ns of now, not of 1970 or of the sim's epoch
    assert abs(meas[-1].t_ns - now_gps_ns()) < 60e9
    baro = [m for m in meas if m.source == "baro"]
    assert baro[0].value[0] == pytest.approx(0.0, abs=1.0)  # referenced to the first fix
    assert baro[0].meta["pressure_pa"] == pytest.approx(100653.27, abs=0.01)


def test_sdr_sidecar_has_buffer_stamps_that_show_the_planted_drop(recorded):
    side = json.loads((recorded["folder"] / "sdr_a.json").read_text())
    for key in ("sample_rate_hz", "center_freq_hz", "t_ns", "buffers", "dongle"):
        assert key in side
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
    assert n > 20, out


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
    import subprocess
    import sys

    code = (
        "import sys, importlib.abc\n"
        "class B(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name.split('.')[0] in {'scipy','matplotlib','fastapi','uvicorn','pyModeS',"
        "'sgp4','numba'}:\n"
        "            raise ImportError(name)\n"
        "sys.meta_path.insert(0, B())\n"
        "import pnt.cli, pnt.payload.config, pnt.payload.day1, pnt.payload.survey\n"
        "import pnt.payload.streamer, pnt.sources.live\n"
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
    import sys

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
    and the estimates recorded to a session that `pnt replay` reads."""
    gpsd = FakeGpsd()
    bus = FakeI2C()
    streamer = Streamer("tcp://127.0.0.1:*")
    rec = Recorder(tmp_path / "pi", [Gpsd(port=gpsd.port), Mpu6050(bus=bus), Bmp280(bus=bus)],
                   streamer=streamer)  # fmt: skip
    pi = threading.Thread(target=rec.run, kwargs={"duration_s": 5.0})
    pi.start()
    out = tmp_path / "live"
    main(["live", "--connect", streamer.endpoint, "--duration", "4", "--out", str(out)])
    pi.join()
    streamer.close()
    gpsd.close()
    printed = capsys.readouterr().out
    assert "enu=(" in printed and "'late': 0" in printed
    meta = session.read_meta(out)
    assert meta["origin_llh"] == pytest.approx(ORIGIN, abs=1e-5)
    topics = {t for t, _ in read_session(out / "session.mcap")}
    assert {"/meas/gnss", "/meas/imu", "/nav/baseline"} <= topics
