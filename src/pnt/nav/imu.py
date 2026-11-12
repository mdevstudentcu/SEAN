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
gravity, one pair a second (a Wahba problem, solved by SVD, both sides centred so an error in the
starting velocity drops out). A window that GNSS leaves or an IMU gap breaks starts over. Then
the attitude error gets `tilt_sigma_deg` for roll and pitch, the biases their priors, and the IMU
takes over.

Velocity lag (#119). In a turn the constant-velocity filter's velocity lags the truth, and a
lagged velocity looks to the fit like a heading error (6 to 22 deg on a 14 deg-tilt turn with
1 m GNSS). At steady state that filter's velocity lags by K_p / K_v = 2 P_pv / P_vv, read from
its covariance, so each velocity change is paired with the specific force that much earlier
(at most `max_lag_s`). `lag_error` of that correction, times the turn rate, stays in the
heading 1-sigma.

Heading is weak on a multirotor. Its thrust, and so its specific force, is along its own z axis
whatever its heading, so heading shows only through how the tilt changes: in the horizontal
spread of the velocity changes, and a drone in a gentle turn tilts a few degrees. The heading
1-sigma after alignment (#119) is the error of one velocity change over that spread (root mean
square, m/s), plus gyro bias over half the window, plus the lag term, from `min_yaw_sigma_deg`
up. The error of one velocity change is the larger of what the fit left over and what the
filter's velocity sigma and the gyro bias allow; both are smooth over a window, so they are not
averaged down over its pairs. The spread is taken from the specific force side, less what gyro
bias alone puts there (the tilt error it grows, times g, over the window), so a noisier gyro
cannot make heading look better known. When nothing is left (hover, a straight line) heading is
unobservable, and when the 1-sigma is over `max_yaw_sigma_deg`, alignment is refused and a new
window starts (`refused` counts them). Holding the constant-velocity model is honest; a heading
from noise is not. The attitude noise `ImuSpec.gyro_extra` keeps the filter from learning more
heading than the linearised model really has (tuning, see `ImuSpec`).
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
        max_yaw_sigma_deg: float = 180.0,  # alignment refused above this heading 1-sigma (TBC)
        max_lag_s: float = 3.0,  # s: longest velocity lag the fit corrects (TBC)
        lag_error: float = 0.5,  # fraction of the lag correction counted as heading error (TBC)
        still_calibration: bool = True,  # start-up bias calibration while still (ADR-0053)
        still_radius_m: float = 3.0,  # m: still while the filter stays this close (TBC)
        still_min_s: float = 20.0,  # s: shortest still stretch that calibrates (TBC)
        still_guard_s: int = 5,  # s: still after this long; the last ones left out (TBC)
    ):
        self.spec = spec
        self.max_hold_ns = int(max_hold_s * 1e9)
        self.max_step_s = max_step_s
        self.align_window_ns = int(align_window_s * 1e9)
        self.align_vel_sigma = align_vel_sigma
        self.tilt_sigma, self.min_yaw_sigma = tilt_sigma_deg * DEG, min_yaw_sigma_deg * DEG
        self.max_yaw_sigma = max_yaw_sigma_deg * DEG
        self.max_lag_s, self.lag_error = max_lag_s, lag_error
        self.R: np.ndarray | None = None  # body-to-ENU attitude; None until aligned
        self.aligned_at: int | None = None
        self.yaw_sigma: float | None = None  # rad: heading 1-sigma given at alignment
        self.refused = 0  # full windows whose heading was unobservable or too uncertain
        self.att = self.ba = self.bg = slice(0, 0)
        self.nav: np.ndarray | None = None  # state indices: position, velocity, dθ, b_a, b_g
        self.buf: deque[tuple[int, np.ndarray, np.ndarray]] = deque()
        self.last: tuple[int, np.ndarray, np.ndarray] | None = None
        self.dropped = 0  # samples older than the filter's time when they arrived
        self._al: dict | None = None  # alignment window in progress
        self.still_calibration, self.still_radius = still_calibration, still_radius_m
        self.still_min_s, self.still_guard = still_min_s, still_guard_s
        self._still: dict | None = None  # still stretch in progress
        # Start-up calibration (ADR-0053): the latest still stretch's biases and their 1-sigma
        self.cal: dict | None = None

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
        record the gyro-integrated specific force and the velocity change minus gravity, then
        integrate the samples up to t_ns. Once the window is full, fit and align, or refuse."""
        steering = ekf.t_ns - ekf.last_used.get("gnss", NEVER) <= ekf.gnss_timeout_ns and (
            ekf.last_rejected.get("gnss", NEVER) <= ekf.last_used.get("gnss", NEVER)
        )
        al = self._al
        v = ekf.x[self.nav[3:6]]
        sd_v = math.sqrt(max(ekf.P[self.nav[3], self.nav[3]], ekf.P[self.nav[4], self.nav[4]]))
        still = self.still_calibration and self._still_step(ekf, steering, segs)
        # A still window cannot show heading: an uncalibrated gyro bias turning the integrated
        # specific force would pass for it (#214), so a window never runs while still
        if not steering or sd_v > self.align_vel_sigma or still:
            self._al = None
            return
        if al is None:
            al = self._al = {"t0": ekf.t_ns, "v0": v.copy(), "C": np.eye(3), "S": np.zeros(3)}
            al["t"], al["u"], al["w"], al["yaw"] = [], [], [], []
        C, S = al["C"], al["S"]
        # Turn about the body z axis since the window began, unwrapped (lag term of the fit)
        yaw = math.atan2(C[1, 0], C[0, 0])
        if al["yaw"]:
            yaw = al["yaw"][-1] + (yaw - al["yaw"][-1] + math.pi) % (2 * math.pi) - math.pi
        al["yaw"].append(yaw)
        al["t"].append(ekf.t_ns)
        al["u"].append(S.copy())
        al["w"].append(v - al["v0"] - GRAVITY * ((ekf.t_ns - al["t0"]) / 1e9))
        ba, bg = (
            (np.zeros(3), np.zeros(3)) if self.cal is None else (self.cal["ba"], self.cal["bg"])
        )
        for h, f, w in segs:
            if f is None:  # an IMU gap breaks the window
                self._al = None
                return
            f, w = f - ba, w - bg
            S += C @ f * h
            C = C @ rotation(w * h)
        al["C"] = C
        if al["t"][-1] - al["t0"] < self.align_window_ns:
            return
        self._al = None
        fit = self._fit(ekf, al, sd_v)
        if fit is None:  # heading unobservable or too uncertain: refuse, start a new window
            self.refused += 1
            return
        R0, yaw = fit
        self.R = R0 @ C
        self.aligned_at = t_ns
        self.yaw_sigma = yaw
        # The IMU states start from their priors, uncorrelated with the rest: the start-up
        # calibration's biases if there was one (ADR-0053), else zero with the spec's 1-sigma
        k = np.r_[np.arange(self.att.start, self.bg.stop)]
        ekf.x[k] = 0.0
        ekf.P[k, :] = 0.0
        ekf.P[:, k] = 0.0
        sa, sg = self._bias_sigmas()
        if self.cal is not None:
            ekf.x[self.ba], ekf.x[self.bg] = self.cal["ba"], self.cal["bg"]
        ekf.P[k, k] = np.square([self.tilt_sigma, self.tilt_sigma, yaw, *sa, *sg])

    def _bias_sigmas(self) -> tuple[np.ndarray, np.ndarray]:
        """Accelerometer and gyro bias 1-sigma per axis: the calibration's, else the spec's."""
        if self.cal is not None:
            return self.cal["sa"], self.cal["sg"]
        s = self.spec
        return np.full(3, s.accel_bias), np.full(3, s.gyro_bias)

    def _still_step(self, ekf: EKF, steering: bool, segs) -> bool:
        """Start-up calibration (ADR-0053); returns whether the receiver is still. A stretch
        lasts while GNSS steers, no IMU sample is missing, and the filter's horizontal position
        stays within `still_radius_m` of where it began; the receiver is still once the stretch
        has lasted `still_guard_s` (so anything faster than radius / guard never is). The
        stretch's samples are summed in 1 s blocks, less the last `still_guard_s` of them (a
        receiver about to move may already be turning). Once the rest lasts `still_min_s`, it
        is the calibration, updated as the stretch goes on:
        gyro bias the mean rate (a still receiver does not turn), accelerometer bias the mean
        specific force's excess over gravity, along it (tilt hides the other two axes). Each
        1-sigma is the standard error of the 1 s means, at least the spec's: a hand-held
        receiver sways, and sway does not average out as white noise does. A later stretch
        replaces an earlier one (biases drift with temperature)."""
        p = ekf.x[self.nav[0:2]]
        st = self._still
        if not steering or any(f is None for _, f, _ in segs):
            self._still = None
            return False
        if st is None or math.hypot(*(p - st["p0"])) >= self.still_radius:
            st = self._still = {"p0": p.copy(), "blk": [], "cur": np.zeros(7)}
        cur = st["cur"]  # duration, specific force and rate sums of the block in progress
        for h, f, w in segs:
            cur += np.r_[h, f * h, w * h]
            if cur[0] >= 1.0:
                st["blk"].append(cur.copy())
                cur[:] = 0.0
        still = len(st["blk"]) >= self.still_guard
        blk = np.array(st["blk"][: len(st["blk"]) - self.still_guard])
        if len(blk) < 2 or blk[:, 0].sum() < self.still_min_s:
            return still
        T = blk[:, 0].sum()
        f, w = blk[:, 1:4].sum(axis=0) / T, blk[:, 4:7].sum(axis=0) / T
        g = float(np.linalg.norm(f))
        means = blk[:, 1:] / blk[:, :1]
        sem = means.std(axis=0, ddof=1) / math.sqrt(len(blk))
        s = self.spec
        self.cal = {
            "t_ns": ekf.t_ns,
            "span_s": float(T),
            "bg": w,
            "ba": f / g * (g - G),
            "sa": np.maximum(sem[:3], s.accel_bias),
            "sg": np.maximum(sem[3:], s.gyro_bias),
        }
        return still

    def _lag(self, ekf: EKF) -> float:
        """How far (s) the constant-velocity filter's velocity lags the truth: for a filter at
        steady state, twice the position-velocity covariance over the velocity variance (module
        docstring), mean of east and north, between 0 and `max_lag_s`."""
        p, v = self.nav[0:2], self.nav[3:5]
        tau = np.mean(2.0 * ekf.P[p, v] / np.maximum(ekf.P[v, v], 1e-12))
        return float(np.clip(tau, 0.0, self.max_lag_s))

    def _fit(self, ekf: EKF, al: dict, sd_v: float) -> tuple[np.ndarray, float] | None:
        """(R0, heading 1-sigma) from a full window, or None if heading is unobservable or its
        1-sigma is above `max_yaw_sigma_deg`. See the module docstring."""
        t = (np.array(al["t"]) - al["t0"]) / 1e9
        T = float(t[-1])
        tau = self._lag(ekf)
        tj = np.arange(0.0, T - tau + 1e-9, 1.0)  # one pair a second
        if len(tj) < 4:
            return None
        U, W = np.array(al["u"]), np.array(al["w"])
        u = np.column_stack([np.interp(tj, t, U[:, i]) for i in range(3)])
        w = np.column_stack([np.interp(tj + tau, t, W[:, i]) for i in range(3)])
        # Centred: an error in the starting velocity shifts every pair alike and drops out
        uc, wc = u - u.mean(axis=0), w - w.mean(axis=0)
        R0 = wahba(uc, wc)
        n = len(tj)
        gyro_bias = float(np.max(self._bias_sigmas()[1]))
        a = uc @ R0.T  # the specific force side, in ENU
        # What the gyro bias alone can put into one velocity change (m/s): a tilt error growing
        # as bias times time, carrying g, over the window
        drift = G * gyro_bias * T**2 / 2
        # Heading shows only in the horizontal spread of the velocity changes (mean square).
        # Less what the gyro bias alone could give: none left means heading is unobservable
        spread = float(np.mean(np.sum(np.square(a[:, :2]), axis=1))) - drift**2
        if spread <= 0.0:
            return None
        # Error of one velocity change (m/s, per axis): the larger of what the fit left over and
        # what the filter's velocity and the gyro bias allow. Both are smooth over the window,
        # so they are not averaged down over the pairs
        var_fit = float(np.sum(np.square(wc - a))) / max(3 * (n - 1) - 3, 1)
        var_w = max(var_fit, sd_v**2 + drift**2)
        dt, dyaw = np.diff(t), np.diff(al["yaw"])
        rate = math.sqrt(float(np.sum(np.square(dyaw[dt > 0]) / dt[dt > 0])) / T)  # rms, rad/s
        yaw = math.sqrt(
            var_w / spread + (gyro_bias * T / 2) ** 2 + (self.lag_error * tau * rate) ** 2
        )
        yaw = max(yaw, self.min_yaw_sigma)
        return None if yaw > self.max_yaw_sigma else (R0, yaw)
