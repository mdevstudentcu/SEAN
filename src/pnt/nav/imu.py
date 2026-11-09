"""IMU motion model for the EKF (issue #12, stage 2): `EKF(motion="imu")`.

Replaces the constant-velocity prediction with strapdown mechanisation of the payload's IMU
(`accel_gyro` records: body-frame specific force and angular rate, ICD-measurement). The
measurement side of the EKF is unchanged.

States added to the EKF (after position, velocity and receiver clock, before any clock block):
    [ dθ (3) | b_a (3) | b_g (3) ]
- dθ: attitude error, a small rotation in ENU. The attitude itself, a body-to-ENU rotation
  matrix, is kept outside the state vector (multiplicative EKF). After every update the error is
  folded into it and reset to zero, at the start of the next prediction.
- b_a, b_g: accelerometer and gyro biases in the body frame, m/s^2 and rad/s, each a random
  constant plus a random walk.

Mechanisation, with the simplifications it makes and why they hold for a drone near Ottawa:
- Local-level ENU, flat and non-rotating, constant gravity (9.80665 m/s^2). Earth rate
  (15 deg/h) and Coriolis (2 Ω v ≈ 1e-4 g at 10 m/s) are below the MEMS gyro and accelerometer
  biases; local gravity differs from the constant by about 1e-4 g (TBC: Ottawa's value).
- No lever arm: the IMU and the antennas share a point. On a 0.5 m payload the rotation term is
  millimetres.
- No scale-factor or misalignment states. On a flight that is mostly level the accelerometer's
  vertical scale error and the gyro's yaw-rate scale error look like biases and are absorbed by
  the bias states; the rest is covered by `ImuSpec.accel_extra` and `gyro_extra` (TBC).
- First-order sampling: each sample is held until the next (forward zero-order hold), the
  attitude is integrated with the exact rotation of each held rate, and coning and sculling are
  ignored (fine at 100 Hz on a slow drone).

Pre-integration: IMU samples are buffered as they arrive, and the EKF integrates them only when
it predicts (every measurement and every output epoch, about 10-30 Hz). The mean goes through
every sample; the covariance is propagated once per prediction with a transition built from the
samples, split into steps of at most `max_step_s`. So a 100 Hz IMU costs one full-size matrix
product per prediction, as the constant-velocity model does.

IMU dropouts: a sample is held for at most `max_hold_s`. Beyond that, until the next sample, the
prediction falls back to constant velocity driven by the EKF's `q_accel`, with attitude and
biases held (the attitude error still grows with the gyro noise).

Alignment. The MPU6050 has no magnetometer, so heading must come from motion. Until aligned the
EKF runs its constant-velocity model, while GNSS steers it. Over `align_window_s` with GNSS in
use and the filter's velocity within `align_vel_sigma`, the gyro-integrated specific force (in
the body frame at the start of the window) is fitted to the filter's velocity change minus
gravity (a Wahba problem, solved by SVD, both sides centred so an error in the starting velocity
drops out). A window that GNSS leaves or an IMU gap breaks starts over. Then the attitude error
gets `tilt_sigma_deg` for roll and pitch, the biases their priors, and the IMU takes over.

Heading is weak on a multirotor. Its thrust, and so its specific force, is along its own z axis
whatever its heading, so heading shows only through how the tilt changes, and a drone in a
gentle turn tilts a few degrees. The heading 1-sigma after alignment is the tilt error the
window can carry (gyro bias over the window, velocity noise over g times the window) over the
largest tilt change in it, between `min_yaw_sigma_deg` and `max_yaw_sigma_deg`; in a steady
circle that is tens of degrees. The attitude noise `ImuSpec.gyro_extra` keeps the filter from
learning more heading than the linearised model really has (tuning, see `ImuSpec`).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from pnt.core.measurement import Measurement

if TYPE_CHECKING:
    from pnt.nav.ekf import EKF

G = 9.80665
GRAVITY = np.array([0.0, 0.0, -G])  # m/s^2, ENU
DEG = math.pi / 180.0
N_STATES = 9  # dθ, b_a, b_g
NEVER = -(10**18)


@dataclass(frozen=True)
class ImuSpec:
    """What the filter assumes about the IMU. Defaults: the payload's MPU6050 (ADR-0014) at the
    same settings as the sim's `sensors.MPU6050`, but kept separate: the filter's assumptions are
    tuning, the sim's are the truth they are tested against."""

    accel_noise: float = 400e-6 * G  # m/s^2/sqrt(Hz): datasheet power spectral density
    gyro_noise: float = 0.005 * DEG  # rad/s/sqrt(Hz): datasheet rate noise spectral density
    accel_bias: float = 5e-3 * G  # m/s^2, 1-sigma left after start-up calibration (TBC)
    gyro_bias: float = 0.05 * DEG  # rad/s, 1-sigma left after start-up calibration (TBC)
    # Bias instability as a random walk, sigma * sqrt(2 / tau): 100 ug and 20 deg/h over 100 s,
    # literature values for this class of part (TBC until our Allan variance)
    accel_bias_rw: float = 100e-6 * G * math.sqrt(2 / 100.0)  # m/s^2/sqrt(s)
    gyro_bias_rw: float = 20.0 * DEG / 3600 * math.sqrt(2 / 100.0)  # rad/s/sqrt(s)
    # Unmodelled errors, as extra white noise on top of the sensor's own: scale factor,
    # misalignment, vibration, sampling, and the linearisation error of a poorly known heading.
    # TBC: tuning, not measured. Picked for consistency (horizontal NEES near 2, no misleading
    # epochs) on seeds 100-139, held out from the seeds 0-49 the results use. uc01-drone-circuit
    # with the gyro term at 0, 0.02 or 0.1 deg/s/sqrt(Hz): NEES 15, 7 or 2.4, and misleading
    # epochs in 10/16, 7/16 or 2/40 runs; at 0.2 and 0.4, none in 40. The accelerometer term
    # trades the other way: 0.05 or 0.1 m/s^2/sqrt(Hz) gave back most of the gain in long outages.
    accel_extra: float = 0.02  # m/s^2/sqrt(Hz)
    gyro_extra: float = 0.2 * DEG  # rad/s/sqrt(Hz)

    def scaled(self, k: float) -> ImuSpec:
        """A grade `k` times worse: every noise and bias term times k."""
        return ImuSpec(*(k * v for v in self.__dict__.values()))


MPU6050 = ImuSpec()


def skew(v) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def rotation(phi) -> np.ndarray:
    """Rotation matrix of the rotation vector `phi` (Rodrigues)."""
    a = math.sqrt(phi[0] * phi[0] + phi[1] * phi[1] + phi[2] * phi[2])
    K = skew(phi)
    if a < 1e-9:
        return np.eye(3) + K
    return np.eye(3) + (math.sin(a) / a) * K + ((1.0 - math.cos(a)) / (a * a)) * (K @ K)


def rotations(phi: np.ndarray) -> np.ndarray:
    """`rotation` of each row of `phi` (n, 3), as (n, 3, 3)."""
    a = np.linalg.norm(phi, axis=1)
    small = a < 1e-9
    a_safe = np.where(small, 1.0, a)
    s = np.where(small, 1.0, np.sin(a_safe) / a_safe)
    c = np.where(small, 0.5, (1.0 - np.cos(a_safe)) / a_safe**2)
    K = np.zeros((len(phi), 3, 3))
    K[:, 0, 1], K[:, 0, 2], K[:, 1, 2] = -phi[:, 2], phi[:, 1], -phi[:, 0]
    K[:, 1, 0], K[:, 2, 0], K[:, 2, 1] = phi[:, 2], -phi[:, 1], phi[:, 0]
    return np.eye(3) + s[:, None, None] * K + c[:, None, None] * (K @ K)


def wahba(u: np.ndarray, w: np.ndarray) -> np.ndarray:
    """The rotation R minimising sum |w_i - R u_i|^2 (rows of u and w are vector pairs)."""
    U, _, Vt = np.linalg.svd(w.T @ u)
    d = np.sign(np.linalg.det(U @ Vt))
    return U @ np.diag([1.0, 1.0, d]) @ Vt


class ImuMotion:
    """The IMU half of `EKF(motion="imu")`: buffers samples, aligns, and propagates the mean and
    the transition of position, velocity, attitude and biases. See the module docstring."""

    def __init__(
        self,
        spec: ImuSpec = MPU6050,
        max_hold_s: float = 0.1,  # s: a sample is held this long, then constant velocity (TBC)
        max_step_s: float = 0.1,  # s: longest step of the covariance transition
        align_window_s: float = 10.0,  # s: alignment window (TBC)
        align_vel_sigma: float = 2.0,  # m/s: the filter's velocity must be this good first (TBC)
        tilt_sigma_deg: float = 2.0,  # roll/pitch 1-sigma after alignment (TBC)
        min_yaw_sigma_deg: float = 3.0,  # floor on heading 1-sigma after alignment (TBC)
        max_yaw_sigma_deg: float = 180.0,  # cap on heading 1-sigma: half a turn
    ):
        self.spec = spec
        self.max_hold_ns = int(max_hold_s * 1e9)
        self.max_step_s = max_step_s
        self.align_window_ns = int(align_window_s * 1e9)
        self.align_vel_sigma = align_vel_sigma
        self.tilt_sigma, self.min_yaw_sigma = tilt_sigma_deg * DEG, min_yaw_sigma_deg * DEG
        self.max_yaw_sigma = max_yaw_sigma_deg * DEG
        self.R: np.ndarray | None = None  # body-to-ENU attitude; None until aligned
        self.aligned_at: int | None = None
        self.att = self.ba = self.bg = slice(0, 0)
        self.nav: np.ndarray | None = None  # state indices: position, velocity, dθ, b_a, b_g
        self.buf: deque[tuple[int, np.ndarray, np.ndarray]] = deque()
        self.last: tuple[int, np.ndarray, np.ndarray] | None = None
        self.dropped = 0  # samples older than the filter's time when they arrived
        self._al: dict | None = None  # alignment window in progress

    # --- state ---------------------------------------------------------------------------
    def augment(self, ekf: EKF, pos: slice, vel: slice) -> None:
        """Append the 9 IMU states to a freshly initialised EKF. They stay frozen (identity
        transition, no noise, no correlation) until alignment sets their priors."""
        n = len(ekf.x)
        ekf.x = np.append(ekf.x, np.zeros(N_STATES))
        P = np.zeros((n + N_STATES, n + N_STATES))
        P[:n, :n] = ekf.P
        s = self.spec
        P[n:, n:] = np.diag(
            np.square([*[self.tilt_sigma] * 3, *[s.accel_bias] * 3, *[s.gyro_bias] * 3])
        )
        ekf.P = P
        self.att, self.ba, self.bg = slice(n, n + 3), slice(n + 3, n + 6), slice(n + 6, n + 9)
        self.nav = np.r_[np.arange(pos.start, pos.stop), np.arange(vel.start, vel.stop)]
        self.nav = np.r_[self.nav, np.arange(n, n + N_STATES)]

    def add(self, ekf: EKF, m: Measurement) -> None:
        """Buffer one `accel_gyro` sample."""
        s = (m.t_ns, np.asarray(m.value[:3], float), np.asarray(m.value[3:6], float))
        if ekf.t_ns is not None and m.t_ns <= ekf.t_ns:
            if self.last is None or m.t_ns >= self.last[0]:
                self.last = s  # the latest reading, held from now on
            else:
                self.dropped += 1
            return
        if self.buf and m.t_ns < self.buf[-1][0]:
            self.dropped += 1  # out of order
            return
        self.buf.append(s)

    def _segments(self, t0: int, t1: int) -> list[tuple[float, np.ndarray | None, np.ndarray]]:
        """Split (t0, t1] into (duration, accel, gyro) pieces, each with the sample held over it
        (None: no sample fresh enough, constant velocity)."""
        segs: list = []
        cur = t0
        while self.buf and self.buf[0][0] <= t1:
            s = self.buf.popleft()
            if s[0] > cur:
                segs += self._hold(cur, s[0])
                cur = s[0]
            self.last = s
        segs += self._hold(cur, t1)
        return segs

    def _hold(self, a: int, b: int) -> list:
        if b <= a:
            return []
        if self.last is None:
            return [((b - a) / 1e9, None, None)]
        t, f, w = self.last
        lim = t + self.max_hold_ns
        if b <= lim:
            return [((b - a) / 1e9, f, w)]
        if a >= lim:
            return [((b - a) / 1e9, None, None)]
        return [((lim - a) / 1e9, f, w), ((b - lim) / 1e9, None, None)]

    # --- prediction ----------------------------------------------------------------------
    def propagate(self, ekf: EKF, t_ns: int, F: np.ndarray, Q: np.ndarray):
        """Called by `EKF.predict` before it applies F and Q. Fills the position, velocity and IMU
        blocks of F and Q, and returns (indices, values) for the mean of position, velocity and
        attitude error, which `predict` sets after F @ x. Returns None while not aligned: the
        constant-velocity blocks stand and the IMU states stay frozen."""
        segs = self._segments(ekf.t_ns, t_ns)
        if self.R is None:
            self._align(ekf, t_ns, segs)
            return None
        x = ekf.x
        dtheta = x[self.att]
        if dtheta.any():  # fold the last updates' attitude error into the attitude
            self.R = rotation(dtheta) @ self.R
            x[self.att] = 0.0
        p, v = x[self.nav[0:3]].copy(), x[self.nav[3:6]].copy()
        ba, bg = x[self.ba], x[self.bg]
        Phi, Qn = np.eye(15), np.zeros((15, 15))
        chunk: list = []
        for seg in segs + [None]:
            if seg is not None and (
                not chunk
                or ((seg[1] is None) == (chunk[0][1] is None))
                and sum(s[0] for s in chunk) < self.max_step_s
            ):
                chunk.append(seg)
                continue
            if chunk:
                p, v, Phi_c, Q_c = self._chunk(chunk, p, v, ba, bg, ekf.q_accel)
                Phi = Phi_c @ Phi
                Qn = Phi_c @ Qn @ Phi_c.T + Q_c
            chunk = [seg]
        if any(s[1] is not None for s in segs):
            ekf.last_used["imu"] = t_ns
        ix = np.ix_(self.nav, self.nav)
        F[ix] = Phi
        Q[ix] = Qn
        return self.nav[:9], np.r_[p, v, 0.0, 0.0, 0.0]

    def _chunk(self, chunk, p, v, ba, bg, q_accel):
        """Integrate the mean through one homogeneous chunk; return its transition and noise in
        the local order (p, v, dθ, b_a, b_g)."""
        T = sum(h for h, _, _ in chunk)
        Phi, Qc = np.eye(15), np.zeros((15, 15))
        I3 = np.eye(3)
        Phi[0:3, 3:6] = I3 * T
        if chunk[0][1] is None:  # no IMU: constant velocity, attitude and biases held
            p = p + v * T
            qa = q_accel**2
            Qc[0:3, 0:3] = I3 * qa * T**3 / 3
            Qc[0:3, 3:6] = Qc[3:6, 0:3] = I3 * qa * T**2 / 2
            Qc[3:6, 3:6] = I3 * qa * T
        else:
            h = np.array([c[0] for c in chunk])
            f = np.array([c[1] for c in chunk]) - ba
            dR = rotations((np.array([c[2] for c in chunk]) - bg) * h[:, None])
            Rs = np.empty_like(dR)  # attitude at the start of each sample
            R = self.R
            for k in range(len(h)):
                Rs[k] = R
                R = R @ dR[k]
            self.R = R
            a_nav = np.einsum("kij,kj->ki", Rs, f)
            dv = (a_nav + GRAVITY) * h[:, None]
            v_start = v + np.cumsum(dv, axis=0) - dv  # velocity at the start of each sample
            p = p + np.sum(v_start * h[:, None] + 0.5 * dv * h[:, None], axis=0)
            v = v + dv.sum(axis=0)
            Rm = np.einsum("k,kij->ij", h, Rs) / T
            A = skew(h @ a_nav / T)
            Phi[3:6, 6:9] = -A * T
            Phi[0:3, 6:9] = -A * T**2 / 2
            Phi[3:6, 9:12] = -Rm * T
            Phi[0:3, 9:12] = -Rm * T**2 / 2
            Phi[6:9, 12:15] = -Rm * T
            Phi[3:6, 12:15] = A @ Rm * T**2 / 2
            Phi[0:3, 12:15] = A @ Rm * T**3 / 6
            s = self.spec
            qa = s.accel_noise**2 + s.accel_extra**2
            qg = s.gyro_noise**2 + s.gyro_extra**2
            Qc[0:3, 0:3] = I3 * qa * T**3 / 3
            Qc[0:3, 3:6] = Qc[3:6, 0:3] = I3 * qa * T**2 / 2
            Qc[3:6, 3:6] = I3 * qa * T + (A @ A.T) * qg * T**3 / 3
            Qc[3:6, 6:9] = -A * qg * T**2 / 2
            Qc[6:9, 3:6] = Qc[3:6, 6:9].T
        s = self.spec
        Qc[6:9, 6:9] = np.eye(3) * (s.gyro_noise**2 + s.gyro_extra**2) * T
        Qc[9:12, 9:12] = I3 * s.accel_bias_rw**2 * T
        Qc[12:15, 12:15] = I3 * s.gyro_bias_rw**2 * T
        return p, v, Phi, Qc

    # --- alignment -----------------------------------------------------------------------
    def _align(self, ekf: EKF, t_ns: int, segs) -> None:
        """One step of the in-flight alignment (module docstring). At the filter's current time,
        record a (gyro-integrated specific force, velocity change minus gravity) pair, then
        integrate the samples up to t_ns."""
        steering = ekf.t_ns - ekf.last_used.get("gnss", NEVER) <= ekf.gnss_timeout_ns and (
            ekf.last_rejected.get("gnss", NEVER) <= ekf.last_used.get("gnss", NEVER)
        )
        al = self._al
        v = ekf.x[self.nav[3:6]]
        sd_v = math.sqrt(max(ekf.P[self.nav[3], self.nav[3]], ekf.P[self.nav[4], self.nav[4]]))
        if not steering or sd_v > self.align_vel_sigma:
            self._al = None
            return
        if al is None:
            al = self._al = {"t0": ekf.t_ns, "v0": v.copy(), "C": np.eye(3), "S": np.zeros(3)}
            al["u"], al["w"], al["z"], al["t"] = [], [], [], ekf.t_ns
        elif ekf.t_ns - al["t"] >= 1_000_000_000:
            al["u"].append(al["S"].copy())
            al["z"].append(al["C"][:, 2].copy())  # body z axis, in the window's first body frame
            al["w"].append(v - al["v0"] - GRAVITY * ((ekf.t_ns - al["t0"]) / 1e9))
            al["t"] = ekf.t_ns
        C, S = al["C"], al["S"]
        for h, f, w in segs:
            if f is None:  # an IMU gap breaks the window
                self._al = None
                return
            S += C @ f * h
            C = C @ rotation(w * h)
        al["C"] = C
        span = al["t"] - al["t0"]
        if span < self.align_window_ns:
            return
        z = np.array(al["z"])
        swing = float(np.arccos(np.clip(np.min(z @ z.T), -1.0, 1.0)))  # largest tilt change
        u, w = np.array(al["u"]), np.array(al["w"])
        # Centred: an error in the starting velocity shifts every pair alike and drops out
        R0 = wahba(u - u.mean(axis=0), w - w.mean(axis=0))
        self.R = R0 @ C
        self.aligned_at = t_ns
        self._al = None
        # Heading 1-sigma: the tilt error the window can carry (gyro bias over the window, and
        # velocity noise over g times the window) over the tilt change that carries heading
        s = self.spec
        T = span / 1e9
        yaw = (s.gyro_bias * T + sd_v / (G * T)) / max(swing, 1e-6)
        yaw = min(max(yaw, self.min_yaw_sigma), self.max_yaw_sigma)
        # The IMU states start from their priors, uncorrelated with the rest
        k = np.r_[np.arange(self.att.start, self.bg.stop)]
        ekf.x[k] = 0.0
        ekf.P[k, :] = 0.0
        ekf.P[:, k] = 0.0
        sig = [self.tilt_sigma, self.tilt_sigma, yaw, *[s.accel_bias] * 3, *[s.gyro_bias] * 3]
        ekf.P[k, k] = np.square(sig)
