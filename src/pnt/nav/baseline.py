"""Baseline estimator: a deliberately simple EKF.

State: ENU position and velocity (constant-velocity model) plus one clock-bias state per
pseudorange emitter, learned while other sources constrain the position.

It is the reference the real work is compared against. It trusts GNSS naively (only a
per-measurement innovation gate), so a slow spoof drags it along: that is intended.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.protection import hpl, vpl

CHI2_999 = {1: 10.83, 2: 13.82, 3: 16.27}  # 99.9 % innovation gates by dimension


class BaselineEKF:
    name = "baseline"

    def __init__(
        self,
        q_accel: float = 1.0,  # m/s^2 / sqrt(Hz), white-acceleration process noise
        q_bias: float = 0.2,  # m / sqrt(s), emitter clock random walk
        init_bias_sigma: float = 2000.0,
        init_vel_sigma: float = 100.0,  # m/s: start unsure of speed, up to aircraft speeds
        alert_limit_m: float = 50.0,  # TBC: from REQ-01/REQ-02 targets
        gnss_timeout_s: float = 2.0,
        origin_llh=None,  # session origin; needed for measurements that carry emitter_llh
    ):
        self.q_accel, self.q_bias = q_accel, q_bias
        self.init_bias_sigma = init_bias_sigma
        self.init_vel_sigma = init_vel_sigma
        self.alert_limit_m = alert_limit_m
        self.gnss_timeout_ns = int(gnss_timeout_s * 1e9)
        self.x: np.ndarray | None = None
        self.P: np.ndarray | None = None
        self.t_ns: int | None = None
        self.bias_idx: dict[str, int] = {}
        self.last_used: dict[str, int] = {}
        self.last_rejected: dict[str, int] = {}
        self.nis_log: list[tuple[str, int, float]] = []  # (source, dim, NIS) per gated update
        self.origin_llh = origin_llh
        self._emitter_cache: dict[str, np.ndarray | None] = {}

    # --- state handling ---------------------------------------------------------------
    def _init(self, m: Measurement) -> None:
        self.x = np.zeros(6)
        self.x[:3] = m.value
        # A tight initial velocity at 0 locks GNSS out at aircraft speeds: every fix fails the
        # gate before velocity converges (found on uc02-yow-approach).
        self.P = np.diag([*(np.square(m.sigma)), *([self.init_vel_sigma**2] * 3)])
        self.t_ns = m.t_ns

    def _augment(self, emitter: str, bias0: float) -> int:
        n = len(self.x)
        self.x = np.append(self.x, bias0)
        P = np.zeros((n + 1, n + 1))
        P[:n, :n] = self.P
        P[n, n] = self.init_bias_sigma**2
        self.P = P
        self.bias_idx[emitter] = n
        return n

    def predict(self, t_ns: int) -> None:
        dt = (t_ns - self.t_ns) / 1e9
        if dt <= 0:
            return
        n = len(self.x)
        F = np.eye(n)
        F[:3, 3:6] = np.eye(3) * dt
        Q = np.zeros((n, n))
        q = self.q_accel**2
        Q[:3, :3] = np.eye(3) * q * dt**3 / 3
        Q[:3, 3:6] = Q[3:6, :3] = np.eye(3) * q * dt**2 / 2
        Q[3:6, 3:6] = np.eye(3) * q * dt
        for i in self.bias_idx.values():
            Q[i, i] = self.q_bias**2 * dt
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        self.t_ns = t_ns

    def _update(self, m: Measurement, z, h, H, R, gate_dim: int, gate: bool = True) -> bool:
        y = np.atleast_1d(z - h)
        S = H @ self.P @ H.T + R
        nis = float(y @ np.linalg.solve(S, y))
        if gate:
            # Logged before the gate decision on purpose: rejected updates still show
            # over-confidence, which is exactly when the gate starts rejecting
            self.nis_log.append((m.source, gate_dim, nis))
        if gate and nis > CHI2_999[gate_dim]:
            self.last_rejected[m.source] = m.t_ns
            return False
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        I_KH = np.eye(len(self.x)) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T  # Joseph form
        self.last_used[m.source] = m.t_ns
        return True

    # --- measurement handling --------------------------------------------------------
    def _emitter(self, m: Measurement) -> np.ndarray | None:
        # Emitters don't move: convert once per emitter (ADR-0008, one conversion point)
        if m.emitter not in self._emitter_cache:
            self._emitter_cache[m.emitter] = emitter_enu(m.meta, self.origin_llh)
        return self._emitter_cache[m.emitter]

    def process(self, m: Measurement) -> None:
        if m.kind == "accel_gyro":
            return  # the IMU: not modelled here, and a predict per sample would cost 100 Hz
        if self.x is None:
            if m.kind == "position_enu":
                self._init(m)
            return
        self.predict(m.t_ns)
        n = len(self.x)
        if m.kind == "position_enu":
            H = np.zeros((3, n))
            H[:, :3] = np.eye(3)
            self._update(m, np.array(m.value), self.x[:3], H, np.diag(np.square(m.sigma)), 3)
        elif m.kind == "altitude":
            H = np.zeros((1, n))
            H[0, 2] = 1.0
            self._update(m, m.value[0], self.x[2], H, np.diag(np.square(m.sigma)), 1)
        elif m.kind == "pseudorange" and (e := self._emitter(m)) is not None:
            d = self.x[:3] - e
            r = float(np.linalg.norm(d))
            new = m.emitter not in self.bias_idx
            i = self._augment(m.emitter, m.value[0] - r) if new else self.bias_idx[m.emitter]
            n = len(self.x)
            H = np.zeros((1, n))
            H[0, :3] = d / r
            H[0, i] = 1.0
            h = r + self.x[i]
            self._update(m, m.value[0], h, H, np.diag(np.square(m.sigma)), 1, gate=not new)
        # other kinds: ignored by the baseline

    def estimate(self) -> Estimate:
        P3 = self.P[:3, :3]
        flags = []
        gnss_age = self.t_ns - self.last_used.get("gnss", -(10**18))
        if gnss_age > self.gnss_timeout_ns:
            flags.append("gnss_unavailable")
        if self.last_rejected.get("gnss", -(10**18)) > self.last_used.get("gnss", -(10**18)):
            flags.append("gnss_excluded")
        h = hpl(P3)
        status = "unsafe" if h > self.alert_limit_m else ("degraded" if flags else "nominal")
        trust = {
            s: (1.0 if self.t_ns - t <= self.gnss_timeout_ns else 0.0)
            for s, t in self.last_used.items()
        }
        return Estimate(
            t_ns=self.t_ns,
            pos_enu=tuple(self.x[:3]),
            vel_enu=tuple(self.x[3:6]),
            pos_cov=tuple(P3.ravel()),
            hpl_m=h,
            vpl_m=vpl(P3),
            status=status,
            trust=trust,
            flags=flags,
        )


def run(
    measurements: Iterable[Measurement],
    epoch_ns: int = 100_000_000,
    ekf: BaselineEKF | None = None,
    origin_llh=None,
) -> Iterator[Estimate]:
    """Feed time-ordered measurements; yield an Estimate on every epoch boundary."""
    ekf = ekf or BaselineEKF(origin_llh=origin_llh)
    next_epoch = None
    for m in measurements:
        if ekf.x is not None:
            if next_epoch is None:
                next_epoch = (ekf.t_ns // epoch_ns + 1) * epoch_ns
            while next_epoch <= m.t_ns:
                ekf.predict(next_epoch)
                yield ekf.estimate()
                next_epoch += epoch_ns
        ekf.process(m)
