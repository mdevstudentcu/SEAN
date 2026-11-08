"""The main estimator (issue #12), stage 1: clock states, no IMU yet.

State (metres and metres per second throughout, so the matrix stays well conditioned):
    [ e n u | ve vn vu | c*dt  c*ddt | b_1 ... b_k ]
      position  velocity   receiver clock  one clock offset per pseudorange emitter

- Motion: constant velocity driven by white acceleration. Stage 2 replaces this with IMU
  propagation (#9 models, #14 trajectories) without changing the measurement side.
- Receiver clock: offset and drift with the standard two-state oscillator model (white
  frequency noise h0 and random-walk frequency noise h-2). Defaults are literature values for a
  TCXO-class oscillator, TBC until measured (ADR-0015).
- Measurements are a registry (`MODELS`): each kind maps to a function returning the predicted
  value, Jacobian row(s) and noise. Unknown kinds are ignored, so new sources add a model only.

The pseudorange model includes the receiver clock (c*dt), as real measurements do. The sim only
adds it when the receiver-clock option exists (#47); until then, set
`pseudorange_receiver_clock=False` for scenarios that model a clock but not its effect on towers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.protection import hpl, vpl

C = 299_792_458.0
CHI2_999 = {1: 10.83, 2: 13.82, 3: 16.27}
POS, VEL, CLK, DRIFT = slice(0, 3), slice(3, 6), 6, 7
N_CORE = 8


class EKF:
    name = "ekf"

    def __init__(
        self,
        origin_llh=None,
        q_accel: float = 1.0,  # m/s^2/sqrt(Hz): white acceleration (stage 1 motion model)
        h0: float = 2e-19,  # s: white frequency noise, TCXO-class (literature, TBC)
        h_2: float = 2e-20,  # 1/s: random-walk frequency noise, TCXO-class (literature, TBC)
        q_emitter: float = 0.2,  # m/sqrt(s): each emitter's clock random walk
        init_vel_sigma: float = 100.0,  # m/s: wide, so fast vehicles aren't locked out
        init_clock_sigma_s: float = 1e-3,
        init_drift_sigma: float = 1e-6,  # s/s (1 ppm)
        init_emitter_sigma: float = 2000.0,
        alert_limit_m: float = 50.0,  # TBC: REQ-01/REQ-02
        gnss_timeout_s: float = 2.0,
        pseudorange_receiver_clock: bool = True,
    ):
        self.origin_llh = origin_llh
        self.q_accel, self.q_emitter = q_accel, q_emitter
        self.sf, self.sg = h0 / 2.0, 2.0 * np.pi**2 * h_2  # clock noise spectral densities
        self.init_vel_sigma = init_vel_sigma
        self.init_clock_sigma_m = C * init_clock_sigma_s
        self.init_drift_sigma_m = C * init_drift_sigma
        self.init_emitter_sigma = init_emitter_sigma
        self.alert_limit_m = alert_limit_m
        self.gnss_timeout_ns = int(gnss_timeout_s * 1e9)
        self.pr_rx_clock = pseudorange_receiver_clock
        self.x: np.ndarray | None = None
        self.P: np.ndarray | None = None
        self.t_ns: int | None = None
        self.emitter_idx: dict[str, int] = {}
        self._emitter_pos: dict[str, np.ndarray | None] = {}
        self.last_used: dict[str, int] = {}
        self.last_rejected: dict[str, int] = {}

    # --- state ---------------------------------------------------------------------------
    def _init(self, m: Measurement) -> None:
        self.x = np.zeros(N_CORE)
        self.x[POS] = m.value
        self.P = np.diag(
            [
                *np.square(m.sigma),
                *([self.init_vel_sigma**2] * 3),
                self.init_clock_sigma_m**2,
                self.init_drift_sigma_m**2,
            ]
        )
        self.t_ns = m.t_ns

    def _augment(self, emitter: str, value: float) -> int:
        n = len(self.x)
        self.x = np.append(self.x, value)
        P = np.zeros((n + 1, n + 1))
        P[:n, :n] = self.P
        P[n, n] = self.init_emitter_sigma**2
        self.P = P
        self.emitter_idx[emitter] = n
        return n

    def predict(self, t_ns: int) -> None:
        dt = (t_ns - self.t_ns) / 1e9
        if dt <= 0:
            return
        n = len(self.x)
        F = np.eye(n)
        F[POS, VEL] = np.eye(3) * dt
        F[CLK, DRIFT] = dt
        Q = np.zeros((n, n))
        qa = self.q_accel**2
        Q[POS, POS] = np.eye(3) * qa * dt**3 / 3
        Q[POS, VEL] = Q[VEL, POS] = np.eye(3) * qa * dt**2 / 2
        Q[VEL, VEL] = np.eye(3) * qa * dt
        c2 = C**2
        Q[CLK, CLK] = c2 * (self.sf * dt + self.sg * dt**3 / 3)
        Q[CLK, DRIFT] = Q[DRIFT, CLK] = c2 * self.sg * dt**2 / 2
        Q[DRIFT, DRIFT] = c2 * self.sg * dt
        for i in self.emitter_idx.values():
            Q[i, i] = self.q_emitter**2 * dt
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        self.t_ns = t_ns

    def _update(self, source: str, t_ns: int, y, H, R, gate: bool = True) -> bool:
        y = np.atleast_1d(y)
        S = H @ self.P @ H.T + R
        nis = float(y @ np.linalg.solve(S, y))
        if gate and nis > CHI2_999[len(y)]:
            self.last_rejected[source] = t_ns
            return False
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        I_KH = np.eye(len(self.x)) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T  # Joseph form
        self.last_used[source] = t_ns
        return True

    # --- measurements ------------------------------------------------------------------------
    def process(self, m: Measurement) -> None:
        if self.x is None:
            if m.kind == "position_enu":
                self._init(m)
            return
        model = MODELS.get(m.kind)
        if model is None:
            return  # not modelled yet
        self.predict(m.t_ns)
        out = model(self, m)
        if out is None:
            return
        y, H, R, gate = out
        self._update(m.source, m.t_ns, y, H, R, gate)

    def _emitter(self, m: Measurement) -> np.ndarray | None:
        if m.emitter not in self._emitter_pos:
            self._emitter_pos[m.emitter] = emitter_enu(m.meta, self.origin_llh)
        return self._emitter_pos[m.emitter]

    # --- output --------------------------------------------------------------------------
    def estimate(self) -> Estimate:
        P3 = self.P[POS, POS]
        flags = []
        never = -(10**18)
        if self.t_ns - self.last_used.get("gnss", never) > self.gnss_timeout_ns:
            flags.append("gnss_unavailable")
        if self.last_rejected.get("gnss", never) > self.last_used.get("gnss", never):
            flags.append("gnss_excluded")
        h = hpl(P3)
        status = "unsafe" if h > self.alert_limit_m else ("degraded" if flags else "nominal")
        trust = {
            s: (1.0 if self.t_ns - t <= self.gnss_timeout_ns else 0.0)
            for s, t in self.last_used.items()
        }
        return Estimate(
            t_ns=self.t_ns,
            pos_enu=tuple(self.x[POS]),
            vel_enu=tuple(self.x[VEL]),
            pos_cov=tuple(P3.ravel()),
            clock_bias_s=float(self.x[CLK] / C),
            clock_sigma_s=float(np.sqrt(self.P[CLK, CLK]) / C),
            hpl_m=h,
            vpl_m=vpl(P3),
            status=status,
            trust=trust,
            flags=flags,
        )


# --- measurement models: (ekf, m) -> (innovation, H, R, gate) or None ----------------------
def _row(ekf: EKF, k: int = 1) -> np.ndarray:
    return np.zeros((k, len(ekf.x)))


def _position(ekf: EKF, m: Measurement):
    H = _row(ekf, 3)
    H[:, POS] = np.eye(3)
    return np.asarray(m.value) - ekf.x[POS], H, np.diag(np.square(m.sigma)), True


def _altitude(ekf: EKF, m: Measurement):
    H = _row(ekf)
    H[0, 2] = 1.0
    return m.value[0] - ekf.x[2], H, np.diag(np.square(m.sigma)), True


def _time(ekf: EKF, m: Measurement):
    """GNSS time solution: local clock minus GPS time, in seconds (ICD `time`)."""
    H = _row(ekf)
    H[0, CLK] = 1.0
    sigma_m = C * m.sigma[0]
    return C * m.value[0] - ekf.x[CLK], H, np.array([[sigma_m**2]]), True


def _pseudorange(ekf: EKF, m: Measurement):
    e = ekf._emitter(m)
    if e is None:
        return None
    d = ekf.x[POS] - e
    r = float(np.linalg.norm(d))
    rx = ekf.x[CLK] if ekf.pr_rx_clock else 0.0
    new = m.emitter not in ekf.emitter_idx
    i = ekf._augment(m.emitter, m.value[0] - r - rx) if new else ekf.emitter_idx[m.emitter]
    H = _row(ekf)
    H[0, POS] = d / r
    if ekf.pr_rx_clock:
        H[0, CLK] = 1.0
    H[0, i] = 1.0
    y = m.value[0] - (r + rx + ekf.x[i])
    return y, H, np.diag(np.square(m.sigma)), not new


MODELS: dict[str, Callable] = {
    "position_enu": _position,
    "altitude": _altitude,
    "time": _time,
    "pseudorange": _pseudorange,
}


def run(
    measurements: Iterable[Measurement],
    epoch_ns: int = 100_000_000,
    origin_llh=None,
    **config,
) -> Iterator[Estimate]:
    """Feed time-ordered measurements; yield an Estimate on every epoch boundary."""
    ekf = EKF(origin_llh=origin_llh, **config)
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
