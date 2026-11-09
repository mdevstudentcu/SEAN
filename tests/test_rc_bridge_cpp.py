"""The ESP32 RC bridge's C++ logic (ADR-0029), compiled and run on the host.

Runs the C++ unit tests, then checks that the C++ bridge and the Python laptop side
(pnt.flight.rc_link) agree byte for byte. Skips cleanly if g++ is missing.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from pnt.flight import rc_link as rc

FW = Path(__file__).resolve().parents[1] / "firmware" / "esp32-rc-bridge"
GXX = shutil.which("g++")
pytestmark = pytest.mark.skipif(GXX is None, reason="g++ not installed")

KEY = bytes(range(1, 33))
NONCE = 0xA5A5F00D
TIMEOUT_MS = 200  # the firmware's HB_TIMEOUT (TBC); the driver takes it as an argument


def compile_cpp(src: str, out: Path) -> Path:
    cmd = [GXX, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1"]
    cmd += ["-I", str(FW / "lib" / "rc_bridge"), str(FW / "host_test" / src), "-o", str(out)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    return compile_cpp("bridge_driver.cpp", tmp_path_factory.mktemp("rcb") / "driver")


def run_driver(driver: Path, commands: list[str]) -> list[str]:
    script = "\n".join([f"bridge {KEY.hex()} {NONCE} {TIMEOUT_MS}", *commands]) + "\n"
    res = subprocess.run([str(driver)], input=script, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return res.stdout.splitlines()


def test_cpp_unit_tests_pass(tmp_path):
    exe = compile_cpp("test_rc_bridge.cpp", tmp_path / "tests")
    res = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert "all passed" in res.stdout


def test_python_packet_accepted_and_packed_like_python(driver):
    ctl = rc.Controller()
    seq = rc.SequenceCounter(iter(range(1000, 2000)).__next__)
    pad = {1: 32767, 3: 16000, 4: -8000, 0: 1200}  # throttle down, some roll, pitch, yaw
    lines, expected = [], []
    t = 0.0
    # Disarmed (opens the bridge's arm gate), then arm, then fly a little.
    for buttons, axes in [({}, pad)] + [({4: True, 5: True}, pad)] * 60 + [({}, {1: 0})]:
        cmd = ctl.update(axes, buttons, t, link_ok=True)
        pkt = rc.build_control(KEY, NONCE, seq.next(), cmd.channels_us, cmd.flags)
        ms = int(t * 1000)
        lines += [f"pkt {ms} {pkt.hex()}", f"frame {ms}"]
        expected += ["rx 0", "frame " + rc.crsf_rc_frame(cmd.channels_us).hex()]
        t += 0.02
    assert ctl.armed  # the sequence did arm
    assert run_driver(driver, lines) == expected


def test_kill_packet_from_python(driver):
    ch = [1500] * 16
    ch[rc.CH_THROTTLE] = 1700
    ch[rc.CH_ARM] = 2000
    open_gate = rc.build_control(KEY, NONCE, 1, ch, 0)
    kill = rc.build_control(KEY, NONCE, 2, ch, rc.FLAG_ARM | rc.FLAG_KILL)
    out = run_driver(driver, [f"pkt 0 {open_gate.hex()}", f"pkt 10 {kill.hex()}", "frame 10"])
    want = list(ch)
    want[rc.CH_ARM] = 1000
    want[rc.CH_THROTTLE] = 1000
    assert out == ["rx 0", "rx 0", "frame " + rc.crsf_rc_frame(want).hex()]


def test_watchdog_replay_and_forgery(driver):
    ch = [1500] * 16
    ch[rc.CH_THROTTLE] = ch[rc.CH_ARM] = 1000
    p1 = rc.build_control(KEY, NONCE, 10, ch, 0)
    p2 = rc.build_control(KEY, NONCE, 11, ch, 0)
    forged = bytearray(rc.build_control(KEY, NONCE, 12, ch, 0))
    forged[16 + 2 * rc.CH_THROTTLE] ^= 0x80  # throttle changed, tag not
    wrong_key = rc.build_control(bytes(32), NONCE, 13, ch, 0)
    other_boot = rc.build_control(KEY, NONCE ^ 1, 14, ch, 0)
    out = run_driver(
        driver,
        [
            f"pkt 0 {p1.hex()}",
            f"pkt 50 {p2.hex()}",
            f"pkt 60 {p1.hex()}",  # replay of an older packet
            f"pkt 60 {p2.hex()}",  # replay of the latest packet
            f"pkt 100 {bytes(forged).hex()}",
            f"pkt 100 {wrong_key.hex()}",
            f"pkt 100 {other_boot.hex()}",
            "frame 249",  # 199 ms after the last valid packet: still sending
            "frame 250",  # 200 ms: silence, nothing is sent
            "frame 400",
            "status 400",
        ],
    )
    assert out[:7] == ["rx 0", "rx 0", "rx 4", "rx 4", "rx 2", "rx 2", "rx 3"]
    assert out[7].startswith("frame c818") and out[8:10] == ["frame none", "frame none"]
    status = rc.parse_status(KEY, bytes.fromhex(out[10].split()[1]))
    assert status is not None  # Python verifies the C++ status tag
    assert (status.nonce, status.last_seq, status.link, status.gate_open) == (
        NONCE,
        11,
        rc.LINK_LOST,
        False,
    )
    assert (status.accepted, status.replay, status.bad_tag, status.bad_nonce) == (2, 2, 2, 1)
