"""MPU6050 IMU and BMP280 barometer on the Pi's I2C bus (ADR-0014, ADR-0018).

Read through Linux `/dev/i2c-N` with the standard library only (no new dependency). Both
sensors are sampled from user space, so each sample is stamped with the host clock at the read
(the midpoint of the transfer). The jitter this gives is what the day-1 test measures (#88).

Settings match the sim's sensor models (`pnt.sim.sensors`): MPU6050 at +/-500 deg/s and +/-8 g;
sigmas are the same white-noise figures the sim uses.
"""

from __future__ import annotations

import fcntl
import math
import os
import struct
import threading
import time

from pnt.core.measurement import Measurement
from pnt.core.time import now_gps_ns
from pnt.sim.sensors import BMP280, DEG, MPU6050, G

I2C_SLAVE = 0x0703  # linux/i2c-dev.h


class LinuxI2C:
    """One open `/dev/i2c-<bus>` per device address."""

    def __init__(self, bus: int = 1):
        self.path = f"/dev/i2c-{bus}"
        self._fd: int | None = None
        self._addr: int | None = None
        self._lock = threading.Lock()

    def _open(self, addr: int) -> int:
        if self._fd is None:
            self._fd = os.open(self.path, os.O_RDWR)
        if self._addr != addr:
            fcntl.ioctl(self._fd, I2C_SLAVE, addr)
            self._addr = addr
        return self._fd

    def read(self, addr: int, reg: int, n: int) -> bytes:
        with self._lock:
            fd = self._open(addr)
            os.write(fd, bytes([reg]))
            return os.read(fd, n)

    def write(self, addr: int, reg: int, data: bytes) -> None:
        with self._lock:
            os.write(self._open(addr), bytes([reg, *data]))

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def _white_sigma(density: float, fs: float) -> float:
    """Per-sample sigma of white noise with density N at rate fs (as `pnt.sim.sensors`)."""
    return density * math.sqrt(fs / 2)


class _Periodic:
    """Sample at a fixed rate against absolute deadlines (no drift from read time)."""

    def __init__(self, rate_hz: float, sleep=time.sleep, monotonic=time.monotonic):
        self.period = 1.0 / rate_hz
        self.sleep, self.monotonic = sleep, monotonic
        self.next = None
        self.overruns = 0

    def wait(self) -> None:
        now = self.monotonic()
        if self.next is None:
            self.next = now
        self.next += self.period
        delay = self.next - now
        if delay > 0:
            self.sleep(delay)
        elif delay < -self.period:  # fell more than a sample behind: skip, count it
            self.overruns += int(-delay / self.period)
            self.next = now


class Mpu6050:
    """`imu` `accel_gyro` records in the sensor's own axes (body frame mounting `TBC`)."""

    name = "imu"
    hardware = "mpu6050"
    WHO_AM_I = 0x75
    IDS = (0x68, 0x70, 0x72, 0x98)  # genuine part and common clones

    def __init__(self, bus=None, addr: int = 0x68, rate_hz: float = 100.0, clock=now_gps_ns):
        self.bus = bus if bus is not None else LinuxI2C(1)
        self.addr, self.rate_hz, self.clock = addr, rate_hz, clock
        self.samples = 0
        self.errors = 0
        self.timer = _Periodic(rate_hz)
        fs = rate_hz
        sa = _white_sigma(MPU6050.accel_noise_ug_rthz * 1e-6 * G, fs)
        sg = _white_sigma(MPU6050.gyro_noise_dps_rthz * DEG, fs)
        self.sigma = (sa, sa, sa, sg, sg, sg)

    def probe(self) -> str | None:
        try:
            who = self.bus.read(self.addr, self.WHO_AM_I, 1)[0]
        except OSError as exc:
            return f"no MPU6050 at 0x{self.addr:02x} on {getattr(self.bus, 'path', 'i2c')}: {exc}"
        if who not in self.IDS:
            return f"0x{self.addr:02x} answered WHO_AM_I=0x{who:02x}, not an MPU6050"
        return None

    def configure(self) -> None:
        self.bus.write(self.addr, 0x6B, b"\x01")  # wake, clock from the X gyro PLL
        time.sleep(0.1)
        self.bus.write(self.addr, 0x1A, b"\x03")  # DLPF 44 Hz (accel) / 42 Hz (gyro)
        self.bus.write(self.addr, 0x19, b"\x04")  # internal sample rate 1 kHz / (1 + 4) = 200 Hz
        self.bus.write(self.addr, 0x1B, b"\x08")  # gyro +/-500 deg/s: 65.5 LSB per deg/s
        self.bus.write(self.addr, 0x1C, b"\x10")  # accel +/-8 g: 4096 LSB per g

    @staticmethod
    def decode(raw: bytes) -> tuple[tuple[float, ...], float]:
        """14 bytes from 0x3B -> (ax, ay, az m/s^2, gx, gy, gz rad/s), temperature degC."""
        ax, ay, az, temp, gx, gy, gz = struct.unpack(">7h", raw)
        acc = tuple(v / 4096.0 * G for v in (ax, ay, az))
        gyr = tuple(v / 65.5 * DEG for v in (gx, gy, gz))
        return (*acc, *gyr), temp / 340.0 + 36.53

    def status(self) -> dict:
        return {"samples": self.samples, "errors": self.errors, "overruns": self.timer.overruns}

    def run(self, ctx) -> None:
        self.configure()
        while not ctx.stop.is_set():
            self.timer.wait()
            t_a = self.clock()
            try:
                raw = self.bus.read(self.addr, 0x3B, 14)
            except OSError as exc:
                self.errors += 1
                if self.errors % 100 == 1:
                    ctx.event(t_a, "imu read error", error=repr(exc), errors=self.errors)
                continue
            t = (t_a + self.clock()) // 2
            value, temp = self.decode(raw)
            self.samples += 1
            ctx.emit(
                Measurement(
                    t_ns=t,
                    source="imu",
                    kind="accel_gyro",
                    value=value,
                    sigma=self.sigma,
                    meta={"temp_c": round(temp, 2)},
                )
            )


def bmp280_compensate(adc_t: int, adc_p: int, cal: tuple) -> tuple[float, float]:
    """Bosch BMP280 datasheet section 8.1 (floating point): temperature degC, pressure Pa."""
    t1, t2, t3, p1, p2, p3, p4, p5, p6, p7, p8, p9 = cal
    v1 = (adc_t / 16384.0 - t1 / 1024.0) * t2
    v2 = (adc_t / 131072.0 - t1 / 8192.0) ** 2 * t3
    t_fine = v1 + v2
    temp = t_fine / 5120.0
    v1 = t_fine / 2.0 - 64000.0
    v2 = v1 * v1 * p6 / 32768.0
    v2 = v2 + v1 * p5 * 2.0
    v2 = v2 / 4.0 + p4 * 65536.0
    v1 = (p3 * v1 * v1 / 524288.0 + p2 * v1) / 524288.0
    v1 = (1.0 + v1 / 32768.0) * p1
    if v1 == 0:
        return temp, float("nan")
    p = 1048576.0 - adc_p
    p = (p - v2 / 4096.0) * 6250.0 / v1
    v1 = p9 * p * p / 2147483648.0
    v2 = p * p8 / 32768.0
    return temp, p + (v1 + v2 + p7) / 16.0


def pressure_altitude_m(p_pa: float) -> float:
    """International standard atmosphere height for pressure p (only differences are used)."""
    return 44330.0 * (1.0 - (p_pa / 101325.0) ** (1 / 5.255))


class Bmp280:
    """`baro` `altitude` records: height above the session origin.

    Referenced to the first GNSS fix it sees (height of that fix above the origin, against the
    pressure at that moment), as the sim's model assumes (`pnt.sim.sensors.BMP280`). Until then
    nothing is emitted, unless `start_up_m` gives the start height above the origin. Every
    record keeps the raw pressure in `meta`, so it can be re-referenced later."""

    name = "baro"
    hardware = "bmp280"
    CHIP_ID = 0xD0
    IDS = (0x58,)  # BMP280 (a BME280 answers 0x60 and also works)

    def __init__(
        self,
        bus=None,
        addr: int | None = None,
        rate_hz: float = 10.0,
        start_up_m: float | None = None,
        clock=now_gps_ns,
    ):
        self.bus = bus if bus is not None else LinuxI2C(1)
        self.addr, self.rate_hz, self.clock = addr, rate_hz, clock
        self.start_up_m = start_up_m
        self.ref: tuple[float, float] | None = None  # (pressure altitude, up above origin)
        self.samples = 0
        self.errors = 0
        self.timer = _Periodic(rate_hz)
        self.cal: tuple | None = None

    def probe(self) -> str | None:
        for addr in (self.addr,) if self.addr else (0x76, 0x77):
            try:
                chip = self.bus.read(addr, self.CHIP_ID, 1)[0]
            except OSError:
                continue
            if chip in (*self.IDS, 0x60):
                self.addr = addr
                return None
        return "no BMP280 at 0x76 or 0x77"

    def configure(self) -> None:
        self.cal = struct.unpack("<HhhHhhhhhhhh", self.bus.read(self.addr, 0x88, 24))
        self.bus.write(self.addr, 0xF5, b"\x10")  # standby 0.5 ms, IIR filter x16
        self.bus.write(self.addr, 0xF4, b"\x57")  # temp x2, pressure x16, normal mode

    def status(self) -> dict:
        return {"samples": self.samples, "errors": self.errors, "referenced": self.ref is not None}

    def run(self, ctx) -> None:
        self.configure()
        while not ctx.stop.is_set():
            self.timer.wait()
            t = self.clock()
            try:
                d = self.bus.read(self.addr, 0xF7, 6)
            except OSError as exc:
                self.errors += 1
                if self.errors % 100 == 1:
                    ctx.event(t, "baro read error", error=repr(exc), errors=self.errors)
                continue
            adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
            adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
            temp, p = bmp280_compensate(adc_t, adc_p, self.cal)
            h = pressure_altitude_m(p)
            if self.ref is None:
                fix = ctx.last_fix
                if fix is not None:
                    self.ref = (h, fix.up_m)
                elif self.start_up_m is not None:
                    self.ref = (h, self.start_up_m)
                else:
                    continue
                ctx.event(t, "baro referenced", pressure_pa=p, up_m=self.ref[1])
            self.samples += 1
            ctx.emit(
                Measurement(
                    t_ns=t,
                    source="baro",
                    kind="altitude",
                    value=(h - self.ref[0] + self.ref[1],),
                    sigma=(BMP280.noise_m,),
                    meta={"pressure_pa": round(p, 2), "temp_c": round(temp, 2)},
                )
            )
