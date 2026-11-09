"""Laptop side of the ESP32 RC bridge (ADR-0029): packets, gamepad mapping, arm and kill."""

import argparse
import hashlib
import hmac
import io
import struct

import pytest

from pnt.flight import rc_link as rc

KEY = bytes(range(1, 33))
NONCE = 0xA5A5F00D

# Buttons and axes in the default PadMap.
LB, RB, KILL, BTN_X, BTN_A, BTN_Y = 4, 5, 1, 2, 0, 3
THROTTLE_AXIS = 1
THROTTLE_DOWN = {THROTTLE_AXIS: 32767}  # Linux reports stick down as positive


def neutral() -> list[int]:
    ch = [rc.US_MID] * rc.CHANNELS
    ch[rc.CH_THROTTLE] = rc.US_LOW
    ch[rc.CH_ARM] = rc.US_LOW
    return ch


# --- CRSF ---------------------------------------------------------------------------


def test_crc8_check_value():
    assert rc.crc8_dvb_s2(b"123456789") == 0xBC  # CRC-8/DVB-S2 catalogue check value


def test_us_to_crsf_endpoints_and_clamp():
    assert [rc.us_to_crsf(u) for u in (1000, 1500, 2000, 900, 2500)] == [
        192,
        992,
        1792,
        192,
        1792,
    ]


def test_crsf_frame_centred_known_vector():
    f = rc.crsf_rc_frame([1500] * 16)
    assert f[:3] == bytes([0xC8, 24, 0x16]) and len(f) == rc.CRSF_FRAME_LEN
    assert f[3:25].hex() == "e0031ff8c0073ef0810f7c" * 2
    assert f[25] == rc.crc8_dvb_s2(f[2:25])


# --- Packets ------------------------------------------------------------------------


def test_control_packet_layout_and_tag():
    ch = neutral()
    pkt = rc.build_control(KEY, NONCE, 7, ch, rc.FLAG_ARM)
    assert len(pkt) == rc.CONTROL_LEN == 66
    body = pkt[:50]
    assert body[:4] == b"RC\x01\x01"
    assert struct.unpack_from("<IQ", body, 4) == (NONCE, 7)
    assert list(struct.unpack_from("<16H", body, 16)) == ch
    assert body[48:50] == bytes([rc.FLAG_ARM, 0])
    # The tag is HMAC-SHA256 over the whole header, channels and flags, cut to 16 bytes.
    assert pkt[50:] == hmac.new(KEY, body, hashlib.sha256).digest()[:16]


def test_control_round_trip():
    ch = neutral()
    got = rc.parse_control(KEY, rc.build_control(KEY, NONCE, 9, ch, rc.FLAG_KILL))
    assert got == rc.Control(NONCE, 9, tuple(ch), rc.FLAG_KILL)


def test_any_changed_byte_breaks_the_tag():
    pkt = rc.build_control(KEY, NONCE, 9, neutral(), 0)
    for i in range(len(pkt)):
        bad = bytearray(pkt)
        bad[i] ^= 0x01
        assert rc.parse_control(KEY, bytes(bad)) is None, f"byte {i}"
    assert rc.parse_control(bytes(32), pkt) is None  # wrong key
    assert rc.parse_control(KEY, pkt[:-1]) is None


def test_sequence_strictly_increasing_and_survives_restart():
    clock = [1_000_000]
    first = rc.SequenceCounter(lambda: clock[0])
    seqs = [first.next() for _ in range(5)]  # clock stands still: still increasing
    assert seqs == sorted(set(seqs)) and seqs[0] == 1_000_000
    clock[0] += 1_000_000  # one second later, the program restarts
    assert rc.SequenceCounter(lambda: clock[0]).next() > seqs[-1]


def test_load_key(tmp_path):
    h = tmp_path / "secrets.h"
    h.write_text(f'#define RCB_PSK_HEX "{KEY.hex()}"\n')
    assert rc.load_key(h) == KEY
    raw = tmp_path / "key.hex"
    raw.write_text(KEY.hex().upper() + "\n")
    assert rc.load_key(raw) == KEY
    raw.write_text("abc")
    with pytest.raises(ValueError):
        rc.load_key(raw)


def test_status_parse_and_forgery():
    body = rc.STATUS_BODY.pack(b"RC", 1, rc.TYPE_STATUS, NONCE, 42, 10, 1, 2, 3, 4, 1, 1, 0, 0)
    good = body + hmac.new(KEY, body, hashlib.sha256).digest()[:16]
    s = rc.parse_status(KEY, good)
    assert s is not None and s.nonce == NONCE and s.last_seq == 42
    assert (s.accepted, s.rejected, s.link, s.gate_open, s.armed_out) == (10, 10, 1, True, False)
    assert rc.parse_status(bytes(32), good) is None
    forged = bytearray(good)
    forged[36] = rc.LINK_LIVE ^ 3
    assert rc.parse_status(KEY, bytes(forged)) is None


# --- Gamepad --------------------------------------------------------------------------


def test_js_events_and_axis_mapping():
    ev = rc.JS_EVENT
    data = (
        ev.pack(0, 1, rc.JS_BUTTON | rc.JS_INIT, KILL)
        + ev.pack(5, -32767, rc.JS_AXIS, THROTTLE_AXIS)
        + ev.pack(6, 0, rc.JS_BUTTON, KILL)
    )
    axes, buttons = {}, {}
    rc.apply_js_events(data + b"\x00\x01", axes, buttons)  # a trailing fragment is ignored
    assert axes == {THROTTLE_AXIS: -32767} and buttons == {KILL: False}
    assert rc.axis_to_us(-32767, invert=True) == 2000  # stick up -> high
    assert rc.axis_to_us(32767, invert=True) == 1000
    assert rc.axis_to_us(-32768) == 1000  # clamped
    assert rc.axis_to_us(0) == 1500


def test_sticks_map_to_aetr():
    ctl = rc.Controller()
    axes = {3: 32767, 4: -32767, 1: 0, 0: -32767}  # roll right, pitch up, throttle mid, yaw left
    cmd = ctl.update(axes, {}, 0.0, link_ok=True)
    assert cmd.channels_us[:4] == (2000, 2000, 1500, 1000)


# --- Arming and kill rules --------------------------------------------------------------


def hold(ctl, buttons, t0, t1, axes=THROTTLE_DOWN, link_ok=True, step=0.02):
    t, cmd = t0, None
    while t <= t1 + 1e-9:
        cmd = ctl.update(axes, buttons, t, link_ok)
        t += step
    return cmd


def test_boot_disarmed_and_arm_needs_hold():
    ctl = rc.Controller()
    cmd = ctl.update(THROTTLE_DOWN, {}, 0.0, True)
    assert not cmd.armed and cmd.flags == 0 and cmd.channels_us[rc.CH_ARM] == 1000
    cmd = hold(ctl, {LB: True, RB: True}, 0.02, 0.9)
    assert not cmd.armed  # held for less than ARM_HOLD_S
    cmd = hold(ctl, {LB: True, RB: True}, 0.92, 1.1)
    assert cmd.armed and cmd.flags == rc.FLAG_ARM and cmd.channels_us[rc.CH_ARM] == 2000


def test_one_arm_button_is_not_enough():
    ctl = rc.Controller()
    ctl.update(THROTTLE_DOWN, {}, 0.0, True)
    assert not hold(ctl, {LB: True}, 0.02, 3.0).armed


def test_arm_buttons_held_at_start_never_arm():
    ctl = rc.Controller()
    assert not hold(ctl, {LB: True, RB: True}, 0.0, 3.0).armed


def test_arm_needs_low_throttle_and_live_link():
    ctl = rc.Controller()
    ctl.update(THROTTLE_DOWN, {}, 0.0, True)
    assert not hold(ctl, {LB: True, RB: True}, 0.02, 3.0, axes={THROTTLE_AXIS: 0}).armed
    ctl = rc.Controller()
    ctl.update(THROTTLE_DOWN, {}, 0.0, False)
    assert not hold(ctl, {LB: True, RB: True}, 0.02, 3.0, link_ok=False).armed


def test_kill_always_wins():
    ctl = rc.Controller()
    ctl.update(THROTTLE_DOWN, {}, 0.0, True)
    hold(ctl, {LB: True, RB: True}, 0.02, 1.2)
    assert ctl.armed
    # Kill while armed, with the arm buttons still held and the throttle up.
    cmd = ctl.update({THROTTLE_AXIS: -32767}, {LB: True, RB: True, KILL: True}, 1.3, True)
    assert cmd.kill and not cmd.armed
    assert cmd.flags == rc.FLAG_KILL
    assert cmd.channels_us[rc.CH_ARM] == 1000 and cmd.channels_us[rc.CH_THROTTLE] == 1000
    # Releasing kill with the arm buttons still held does not re-arm.
    assert not hold(ctl, {LB: True, RB: True}, 1.32, 4.0).armed
    # A fresh press does.
    ctl.update(THROTTLE_DOWN, {}, 4.1, True)
    assert hold(ctl, {LB: True, RB: True}, 4.12, 5.2).armed


def test_kill_during_arm_hold_cancels_it():
    ctl = rc.Controller()
    ctl.update(THROTTLE_DOWN, {}, 0.0, True)
    hold(ctl, {LB: True, RB: True}, 0.02, 0.5)
    ctl.update(THROTTLE_DOWN, {LB: True, RB: True, KILL: True}, 0.52, True)
    assert not hold(ctl, {LB: True, RB: True}, 0.54, 3.0).armed


def test_external_disarm_needs_fresh_press():
    ctl = rc.Controller()
    ctl.update(THROTTLE_DOWN, {}, 0.0, True)
    hold(ctl, {LB: True, RB: True}, 0.02, 1.2)
    ctl.disarm("bridge rebooted")
    assert ctl.last_disarm == "bridge rebooted"
    assert not hold(ctl, {LB: True, RB: True}, 1.22, 4.0).armed


def test_mode_buttons():
    ctl = rc.Controller()
    assert ctl.update({}, {}, 0.0, True).channels_us[rc.CH_MODE] == rc.MODE_ANGLE
    assert ctl.update({}, {BTN_Y: True}, 0.1, True).channels_us[rc.CH_MODE] == rc.MODE_POSHOLD
    assert ctl.update({}, {}, 0.2, True).mode_us == rc.MODE_POSHOLD  # latched
    assert ctl.update({}, {BTN_A: True}, 0.3, True).mode_us == rc.MODE_ALTHOLD
    assert ctl.update({}, {BTN_X: True}, 0.4, True).mode_us == rc.MODE_ANGLE


def test_no_gamepad_throttle_defaults_low():
    cmd = rc.Controller().update({}, {}, 0.0, True)
    assert cmd.channels_us[rc.CH_THROTTLE] == 1000


# --- CLI ------------------------------------------------------------------------------


def args(**kw):
    p = argparse.ArgumentParser()
    rc.add_arguments(p)
    ns = p.parse_args([])
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_dry_run_prints_signed_packets(tmp_path):
    key_file = tmp_path / "secrets.h"
    key_file.write_text(f'#define RCB_PSK_HEX "{KEY.hex()}"\n')
    out = io.StringIO()
    code = rc.run(args(dry_run=True, device="none", key_file=key_file, count=3, rate=1000.0), out)
    lines = out.getvalue().splitlines()
    assert code == 0 and len(lines) == 3
    pkts = [rc.parse_control(KEY, bytes.fromhex(line.split("| ")[1])) for line in lines]
    assert all(p is not None and p.nonce == 0 and p.flags == 0 for p in pkts)
    assert pkts[0].seq < pkts[1].seq < pkts[2].seq


def test_live_run_refuses_without_key_or_gamepad(tmp_path):
    out = io.StringIO()
    assert rc.run(args(key_file=tmp_path / "missing.h"), out) == 2
    key_file = tmp_path / "secrets.h"
    key_file.write_text(KEY.hex())
    assert rc.run(args(key_file=key_file, device="none"), out) == 2
