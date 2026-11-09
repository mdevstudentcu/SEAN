"""Gamepad to ESP32 RC bridge over Wi-Fi (ADR-0029). Tethered indoor hover only.

Reads a Linux gamepad (``/dev/input/js*``), turns it into stick, arm, kill and mode
values, and sends them as authenticated UDP packets to the ESP32 RC bridge. The bridge
turns them into CRSF frames for INAV.

The wire format and the bridge's own rules live in
``firmware/esp32-rc-bridge/lib/rc_bridge/rc_bridge.h``. This file must agree with it
byte for byte; ``tests/test_rc_bridge_cpp.py`` checks that.

Safety rules on this side (the bridge enforces its own as well):

- **KILL always wins.** While it is held, ARM is off and throttle is low, and the
  armed state is cleared.
- **Boot is disarmed.** Arming needs both arm buttons pressed afresh and held for
  ``ARM_HOLD_S``, with the throttle stick at the bottom and a live link to the bridge.
- **Silence means failsafe.** If the gamepad goes away, or the program stops, nothing
  more is sent; the bridge then goes silent and INAV runs its failsafe (LAND).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import socket
import struct
import sys
import time
from collections.abc import Mapping as MappingType
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# --- Wire format (rc_bridge.h) ------------------------------------------------------

MAGIC = b"RC"
VERSION = 1
TYPE_CONTROL = 1
TYPE_STATUS = 2
KEY_LEN = 32
TAG_LEN = 16
CHANNELS = 16

CONTROL_BODY = struct.Struct("<2sBBIQ16HBB")  # 50 bytes, then a 16-byte tag
CONTROL_LEN = CONTROL_BODY.size + TAG_LEN
STATUS_BODY = struct.Struct("<2sBBIQ5IBBBB")  # 40 bytes, then a 16-byte tag
STATUS_LEN = STATUS_BODY.size + TAG_LEN

FLAG_ARM = 0x01
FLAG_KILL = 0x02

# INAV's default `map AETR`, then AUX1 = arm, AUX2 = mode.
CH_ROLL, CH_PITCH, CH_THROTTLE, CH_YAW, CH_ARM, CH_MODE = range(6)
US_LOW, US_MID, US_HIGH = 1000, 1500, 2000

# AUX2 positions. Which INAV modes they select is set in INAV (README, `TBC`).
MODE_ANGLE, MODE_ALTHOLD, MODE_POSHOLD = 1000, 1500, 2000
MODE_NAMES = {MODE_ANGLE: "ANGLE", MODE_ALTHOLD: "ALTHOLD", MODE_POSHOLD: "POSHOLD"}

LINK_NONE, LINK_LIVE, LINK_LOST = 0, 1, 2
LINK_NAMES = {LINK_NONE: "none", LINK_LIVE: "LIVE", LINK_LOST: "LOST"}

CRSF_SYNC = 0xC8
CRSF_TYPE_RC_CHANNELS = 0x16
CRSF_FRAME_LEN = 26

# --- Operating values (ADR-0029). TBC: proposed, not confirmed -----------------------

RATE_HZ = 50.0  # TBC: control packets per second
ARM_HOLD_S = 1.0  # TBC: how long both arm buttons must be held
ARM_THROTTLE_MAX_US = 1050  # TBC: throttle must be at the bottom to arm
STATUS_FRESH_S = 0.5  # TBC: a bridge status older than this means "no link"

DEFAULT_BRIDGE = "192.168.4.1:14650"  # the ESP32's own access point (main.cpp)
DEFAULT_DEVICE = "/dev/input/js0"
REPO = Path(__file__).resolve().parents[3]
DEFAULT_KEY_FILE = REPO / "firmware" / "esp32-rc-bridge" / "include" / "secrets.h"
DRY_RUN_KEY = bytes(KEY_LEN)  # all zeros: only ever used with --dry-run and no key file


# --- CRSF -----------------------------------------------------------------------------


def crc8_dvb_s2(data: bytes) -> int:
    """CRC-8/DVB-S2 (polynomial 0xD5, init 0), as CRSF uses."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def us_to_crsf(us: int) -> int:
    """1000 us -> 192, 1500 -> 992, 2000 -> 1792; clamped. Same integer maths as C++."""
    us = min(max(int(us), US_LOW), US_HIGH)
    return ((us - US_LOW) * 8 + 2) // 5 + 192


def crsf_rc_frame(channels_us: Sequence[int]) -> bytes:
    """A CRSF RC_CHANNELS_PACKED frame: 16 x 11-bit channels, LSB first."""
    if len(channels_us) != CHANNELS:
        raise ValueError(f"need {CHANNELS} channels, got {len(channels_us)}")
    bits = 0
    for i, us in enumerate(channels_us):
        bits |= (us_to_crsf(us) & 0x7FF) << (11 * i)
    body = bytes([CRSF_TYPE_RC_CHANNELS]) + bits.to_bytes(22, "little")
    return bytes([CRSF_SYNC, len(body) + 1]) + body + bytes([crc8_dvb_s2(body)])


# --- Packets --------------------------------------------------------------------------


def _tag(key: bytes, body: bytes) -> bytes:
    return hmac.new(key, body, hashlib.sha256).digest()[:TAG_LEN]


def build_control(
    key: bytes, nonce: int, seq: int, channels_us: Sequence[int], flags: int
) -> bytes:
    """One control packet: header, channels, flags, then a truncated HMAC-SHA256 tag."""
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes")
    if len(channels_us) != CHANNELS:
        raise ValueError(f"need {CHANNELS} channels, got {len(channels_us)}")
    us = [min(max(int(c), US_LOW), US_HIGH) for c in channels_us]
    body = CONTROL_BODY.pack(MAGIC, VERSION, TYPE_CONTROL, nonce, seq, *us, flags, 0)
    return body + _tag(key, body)


@dataclass(frozen=True)
class Control:
    nonce: int
    seq: int
    channels_us: tuple[int, ...]
    flags: int


def parse_control(key: bytes, data: bytes) -> Control | None:
    """Format and tag check only (the bridge also checks the nonce and sequence)."""
    if len(data) != CONTROL_LEN:
        return None
    body, tag = data[: CONTROL_BODY.size], data[CONTROL_BODY.size :]
    magic, version, kind, nonce, seq, *rest = CONTROL_BODY.unpack(body)
    if (magic, version, kind, rest[-1]) != (MAGIC, VERSION, TYPE_CONTROL, 0):
        return None
    if not hmac.compare_digest(tag, _tag(key, body)):
        return None
    return Control(nonce, seq, tuple(rest[:CHANNELS]), rest[CHANNELS])


@dataclass(frozen=True)
class Status:
    nonce: int
    last_seq: int
    accepted: int
    bad_format: int
    bad_tag: int
    bad_nonce: int
    replay: int
    link: int
    gate_open: bool
    armed_out: bool

    @property
    def rejected(self) -> int:
        return self.bad_format + self.bad_tag + self.bad_nonce + self.replay


def parse_status(key: bytes, data: bytes) -> Status | None:
    """The bridge's status reply, or None if it is malformed or not signed with key."""
    if len(data) != STATUS_LEN:
        return None
    body, tag = data[: STATUS_BODY.size], data[STATUS_BODY.size :]
    magic, version, kind, nonce, last_seq, *counts, link, gate, armed, reserved = (
        STATUS_BODY.unpack(body)
    )
    if (magic, version, kind, reserved) != (MAGIC, VERSION, TYPE_STATUS, 0):
        return None
    if not hmac.compare_digest(tag, _tag(key, body)):
        return None
    return Status(nonce, last_seq, *counts, link, bool(gate), bool(armed))


class SequenceCounter:
    """Strictly increasing sequence numbers that also survive a laptop restart.

    Each number is at least the wall clock in microseconds, so a restarted program
    starts above anything the bridge has already accepted (while the clock is sane).
    """

    def __init__(self, clock_us=lambda: time.time_ns() // 1000) -> None:
        self._clock_us = clock_us
        self._last = 0

    def next(self) -> int:
        self._last = max(self._last + 1, int(self._clock_us()))
        return self._last


def load_key(path: Path) -> bytes:
    """The pre-shared key: RCB_PSK_HEX from secrets.h, or a file of 64 hex digits."""
    text = Path(path).read_text()
    m = re.search(r'RCB_PSK_HEX\s+"([0-9a-fA-F]*)"', text)
    hex_key = m.group(1) if m else text.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", hex_key):
        raise ValueError(f"{path}: the key must be 64 hex digits (RCB_PSK_HEX)")
    return bytes.fromhex(hex_key)


# --- Gamepad --------------------------------------------------------------------------

JS_EVENT = struct.Struct("<IhBB")  # struct js_event: time, value, type, number
JS_BUTTON, JS_AXIS, JS_INIT = 0x01, 0x02, 0x80


def apply_js_events(data: bytes, axes: dict[int, int], buttons: dict[int, bool]) -> None:
    """Fold raw Linux joystick events into axis and button state."""
    for off in range(0, len(data) - len(data) % JS_EVENT.size, JS_EVENT.size):
        _t, value, kind, number = JS_EVENT.unpack_from(data, off)
        kind &= ~JS_INIT
        if kind == JS_AXIS:
            axes[number] = value
        elif kind == JS_BUTTON:
            buttons[number] = bool(value)


class Gamepad:
    """Non-blocking reader for /dev/input/jsN (Linux joydev)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.axes: dict[int, int] = {}
        self.buttons: dict[int, bool] = {}

    def poll(self) -> None:
        """Read every pending event. Raises OSError once the gamepad is gone."""
        while True:
            try:
                data = os.read(self.fd, JS_EVENT.size * 64)
            except BlockingIOError:
                return
            if not data:
                raise OSError(f"{self.path}: closed")
            apply_js_events(data, self.axes, self.buttons)

    def close(self) -> None:
        os.close(self.fd)


class NeutralPad:
    """No gamepad (``--device none``, dry run only): sticks centred, throttle low."""

    def __init__(self) -> None:
        self.axes: dict[int, int] = {}
        self.buttons: dict[int, bool] = {}

    def poll(self) -> None:
        pass

    def close(self) -> None:
        pass


# --- Controller -----------------------------------------------------------------------


@dataclass(frozen=True)
class PadMap:
    """Gamepad layout. Defaults follow the Linux xpad layout (Xbox-style), `TBC` on the
    team's gamepad: check them with ``pnt rc --dry-run`` before the bench test."""

    roll_axis: int = 3  # right stick X
    pitch_axis: int = 4  # right stick Y
    throttle_axis: int = 1  # left stick Y
    yaw_axis: int = 0  # left stick X
    arm_buttons: tuple[int, ...] = (4, 5)  # LB + RB, held together
    kill_button: int = 1  # B
    mode_buttons: tuple[tuple[int, int], ...] = (
        (2, MODE_ANGLE),  # X
        (0, MODE_ALTHOLD),  # A
        (3, MODE_POSHOLD),  # Y
    )


def axis_to_us(value: int, invert: bool = False) -> int:
    """A joystick axis (-32767..32767) to 1000..2000 us."""
    v = -value if invert else value
    return min(max(US_MID + round(500 * v / 32767), US_LOW), US_HIGH)


@dataclass(frozen=True)
class Command:
    channels_us: tuple[int, ...]
    flags: int
    armed: bool
    kill: bool
    mode_us: int


@dataclass
class Controller:
    """Gamepad state to channels and flags, with the arming and kill rules."""

    pad: PadMap = field(default_factory=PadMap)
    arm_hold_s: float = ARM_HOLD_S
    armed: bool = False
    mode_us: int = MODE_ANGLE
    last_disarm: str = ""
    # True at start, so arm buttons already held when the program starts never arm.
    _prev_combo: bool = True
    _hold_since: float | None = None

    def disarm(self, reason: str) -> None:
        """Drop the armed state. Re-arming needs a fresh press of both arm buttons."""
        if self.armed:
            self.last_disarm = reason
        self.armed = False
        self._hold_since = None
        self._prev_combo = True

    def update(
        self,
        axes: MappingType[int, int],
        buttons: MappingType[int, bool],
        now_s: float,
        link_ok: bool,
    ) -> Command:
        p = self.pad
        kill = bool(buttons.get(p.kill_button, False))
        combo = all(buttons.get(b, False) for b in p.arm_buttons)
        # Sticks up give high values; Linux reports up as negative, hence the inversions.
        roll = axis_to_us(axes.get(p.roll_axis, 0))
        pitch = axis_to_us(axes.get(p.pitch_axis, 0), invert=True)
        yaw = axis_to_us(axes.get(p.yaw_axis, 0))
        throttle = (
            axis_to_us(axes[p.throttle_axis], invert=True) if p.throttle_axis in axes else US_LOW
        )

        for button, mode in p.mode_buttons:
            if buttons.get(button, False):
                self.mode_us = mode

        if kill:
            self.disarm("kill")
        elif not self.armed:
            if combo and not self._prev_combo:
                self._hold_since = now_s
            if not combo or not link_ok or throttle > ARM_THROTTLE_MAX_US:
                self._hold_since = None
            if self._hold_since is not None and now_s - self._hold_since >= self.arm_hold_s:
                self.armed = True
                self._hold_since = None
        self._prev_combo = combo

        armed = self.armed and not kill
        channels = [US_MID] * CHANNELS
        channels[CH_ROLL] = roll
        channels[CH_PITCH] = pitch
        channels[CH_THROTTLE] = US_LOW if kill else throttle
        channels[CH_YAW] = yaw
        channels[CH_ARM] = US_HIGH if armed else US_LOW
        channels[CH_MODE] = self.mode_us
        flags = (FLAG_ARM if armed else 0) | (FLAG_KILL if kill else 0)
        return Command(tuple(channels), flags, armed, kill, self.mode_us)


# --- Link to the bridge ---------------------------------------------------------------


class Link:
    """UDP to the bridge: sends control packets, reads its signed status replies."""

    def __init__(self, key: bytes, addr: tuple[str, int]) -> None:
        self.key = key
        self.addr = addr
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.nonce = 0  # learnt from the bridge; 0 is never valid
        self.status: Status | None = None
        self.status_at = float("-inf")
        self.received = 0  # authentic status replies
        self.forged_status = 0
        self.send_errors = 0

    def send(self, packet: bytes) -> None:
        try:
            self.sock.sendto(packet, self.addr)
        except OSError:  # Wi-Fi down: nothing reaches the bridge, which then goes silent
            self.send_errors += 1

    def receive(self, now_s: float) -> bool:
        """Read pending status replies. Returns True if the bridge's nonce changed."""
        changed = False
        while True:
            try:
                data, _src = self.sock.recvfrom(256)
            except (BlockingIOError, InterruptedError):
                return changed
            except ConnectionRefusedError:  # ICMP from a bridge that is not listening
                continue
            except OSError:  # e.g. Wi-Fi down
                return changed
            status = parse_status(self.key, data)
            if status is None:
                self.forged_status += 1
                continue
            if status.nonce != self.nonce:
                self.nonce = status.nonce
                changed = True
            self.status = status
            self.status_at = now_s
            self.received += 1

    def ok(self, now_s: float) -> bool:
        s = self.status
        return (
            s is not None
            and now_s - self.status_at <= STATUS_FRESH_S
            and s.nonce == self.nonce
            and s.link == LINK_LIVE
        )

    def describe(self, now_s: float) -> str:
        s = self.status
        if s is None:
            return f"LINK waiting for the bridge (send errors {self.send_errors})"
        age = now_s - self.status_at
        state = LINK_NAMES.get(s.link, "?") if age <= STATUS_FRESH_S else "NO STATUS"
        return (
            f"LINK {state} gate {'open' if s.gate_open else 'closed'} "
            f"ok {s.accepted} rejected {s.rejected} "
            f"(tag {s.bad_tag}, replay {s.replay}, nonce {s.bad_nonce}, format {s.bad_format})"
        )


def describe_command(cmd: Command) -> str:
    state = "KILL" if cmd.kill else ("ARMED" if cmd.armed else "disarmed")
    c = cmd.channels_us
    return (
        f"{state:8s} {MODE_NAMES.get(cmd.mode_us, '?'):7s} "
        f"R {c[CH_ROLL]} P {c[CH_PITCH]} T {c[CH_THROTTLE]} Y {c[CH_YAW]}"
    )


# --- Bench check of the bridge's packet checks ----------------------------------------


def link_test(key: bytes, link, out=sys.stdout, clock=time.monotonic, sleep=time.sleep) -> int:
    """Send a replayed, a forged and an old-boot packet and check the bridge drops each.

    Every packet is disarmed with the throttle low. Returns 0 if the bridge's counters
    moved exactly as expected.
    """
    channels = [US_MID] * CHANNELS
    channels[CH_THROTTLE] = channels[CH_ARM] = US_LOW
    seq = SequenceCounter()

    def packet(nonce: int) -> bytes:
        return build_control(key, nonce, seq.next(), channels, 0)

    def probe() -> Status | None:
        # The bridge replies at most every 100 ms, to the latest datagram.
        sleep(0.15)
        seen = link.received
        link.send(packet(link.nonce))
        deadline = clock() + 1.0
        while clock() < deadline:
            link.receive(clock())
            if link.received != seen:
                return link.status
            sleep(0.01)
        return None

    if probe() is None:  # nonce still 0: rejected, but the reply carries the nonce
        print("FAIL: no signed reply from the bridge (key, address or Wi-Fi?)", file=out)
        return 1
    before = probe()
    if before is None or before.link != LINK_LIVE:
        print("FAIL: the bridge did not accept a valid packet", file=out)
        return 1
    valid = packet(link.nonce)
    forged = bytearray(packet(link.nonce))
    forged[16 + 2 * CH_THROTTLE] ^= 0x80  # throttle changed, tag not
    link.send(valid)
    link.send(valid)  # replay
    link.send(bytes(forged))
    link.send(packet(link.nonce ^ 1))  # signed, but for another boot of the bridge
    after = probe()
    if after is None:
        print("FAIL: no reply after the test packets", file=out)
        return 1
    got = {
        "accepted": after.accepted - before.accepted,
        "replay": after.replay - before.replay,
        "bad_tag": after.bad_tag - before.bad_tag,
        "bad_nonce": after.bad_nonce - before.bad_nonce,
        "bad_format": after.bad_format - before.bad_format,
    }
    want = {"accepted": 2, "replay": 1, "bad_tag": 1, "bad_nonce": 1, "bad_format": 0}
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: counter changes {got}, expected {want}", file=out)
    return 0 if ok else 1


# --- CLI ------------------------------------------------------------------------------


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true", help="print packets, send nothing")
    p.add_argument("--device", default=DEFAULT_DEVICE, help="gamepad; 'none' for dry runs")
    p.add_argument("--bridge", default=DEFAULT_BRIDGE, help="host:port of the ESP32 bridge")
    p.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE, help="secrets.h or hex")
    p.add_argument("--rate", type=float, default=RATE_HZ, help="packets per second (TBC)")
    p.add_argument("--count", type=int, help="stop after this many packets")
    p.add_argument(
        "--link-test",
        action="store_true",
        help="bench check: the bridge rejects replayed, forged and old-boot packets",
    )


def cmd_rc(args: argparse.Namespace) -> None:
    raise SystemExit(run(args))


def run(args: argparse.Namespace, out=sys.stdout) -> int:
    if args.key_file.exists():
        key = load_key(args.key_file)
    elif args.dry_run:
        print(f"dry run: {args.key_file} not found, using an all-zero key", file=out)
        key = DRY_RUN_KEY
    else:
        print(
            f"no key: create {args.key_file} from secrets.h.example "
            "(firmware/esp32-rc-bridge/README.md)",
            file=out,
        )
        return 2
    if args.link_test:
        host, _, port = args.bridge.rpartition(":")
        return link_test(key, Link(key, (host, int(port))), out)
    if args.device == "none" and not args.dry_run:
        print("--device none is for dry runs only", file=out)
        return 2

    try:
        pad = NeutralPad() if args.device == "none" else Gamepad(args.device)
    except OSError as e:
        print(f"no gamepad: {e}", file=out)
        return 2
    host, _, port = args.bridge.rpartition(":")
    link = None if args.dry_run else Link(key, (host, int(port)))
    ctl = Controller()
    seq = SequenceCounter()
    period = 1.0 / args.rate
    next_t = time.monotonic()
    last_shown = float("-inf")
    sent = 0
    try:
        while args.count is None or sent < args.count:
            now = time.monotonic()
            if now < next_t:
                time.sleep(next_t - now)
                continue
            next_t = max(next_t + period, now - 5 * period)
            try:
                pad.poll()
            except OSError as e:
                print(f"\ngamepad lost ({e}): sending stopped, INAV will fail safe", file=out)
                return 1
            if link is not None and link.receive(now):
                ctl.disarm("bridge rebooted")
            s = link.status if link is not None else None
            if s is not None and ctl.armed and (s.link != LINK_LIVE or not s.gate_open):
                ctl.disarm("bridge lost the link")
            link_ok = True if link is None else link.ok(now)
            cmd = ctl.update(pad.axes, pad.buttons, now, link_ok)
            nonce = 0 if link is None else link.nonce
            n = seq.next()
            packet = build_control(key, nonce, n, cmd.channels_us, cmd.flags)
            sent += 1
            if link is None:
                print(f"seq {n} {describe_command(cmd)} | {packet.hex()}", file=out)
                continue
            link.send(packet)
            if now - last_shown >= 0.2:
                last_shown = now
                note = f" (last disarm: {ctl.last_disarm})" if ctl.last_disarm else ""
                line = f"{link.describe(now)} | {describe_command(cmd)}{note}"
                print(f"\r{line:<120s}", end="", file=out, flush=True)
    except KeyboardInterrupt:
        print("\nstopped: sending stopped, INAV will fail safe (LAND)", file=out)
    finally:
        pad.close()
    return 0
