"""The main estimator (issue #12), stage 1: clock states, no IMU yet.

State (metres and metres per second throughout, so the matrix stays well conditioned):
    [ e n u | ve vn vu | c*dt  c*ddt | tower clocks ... ]
      position  velocity   receiver clock  one block per tower clock, added on first sight

- Motion: constant velocity driven by white acceleration. Stage 2 replaces this with IMU
  propagation (#9 models, #14 trajectories) without changing the measurement side.
- Receiver clock: offset and drift with the standard two-state oscillator model (white
  frequency noise h0 and random-walk frequency noise h-2). Defaults are literature values for a
  TCXO-class oscillator, TBC until measured (ADR-0015).
- Measurements are a registry (`MODELS`): each kind maps to a function returning the predicted
  value, Jacobian row(s) and noise. Unknown kinds are ignored, so new sources add a model only.

Receiver clock in pseudoranges: a real radio's tower ranges all carry our clock offset (c*dt).
The sim doesn't add it yet (#47), so `pseudorange_receiver_clock` defaults to False to match the
data. Turned on against data without the term, a drifting clock makes the filter reject nearly
every tower. Turn it on when the sim (or real data) has the term, and only with a time source:
towers alone can't separate our clock from theirs, so its variance grows without bound.

Tower clocks (ADR-0022, Proposed) have two models, picked with `clock_model`:
- "independent" (default, the model before ADR-0022): one clock offset per clock, a random walk
  (`q_emitter`). Such a clock is free to absorb its own tower's error, so it adds no
  fault-detection redundancy (Jia, Khalife & Kassas, IEEE T-ITS 2023).
- "calibrated": offset and drift per clock, on the two-state oscillator model. While GNSS is
  trusted (position accepted recently, no exclusion, no time alarm) the filter is *calibrating*:
  the clock gets extra process noise (`calib_q_offset`, `calib_q_drift`) so offset and drift
  track what the towers show. Otherwise it *coasts*: the learned offset and drift are the prior
  and only the oscillator noise (`tower_h0`, `tower_h_2`) is added, so they stay tight.
  "Trusted" only means "accepted", so a slow spoof that passes the gate is calibrated into the
  tower clocks too: stronger GNSS trust tests are I9/I10's job.
Either model can group clocks:
- `sites`: emitter -> site. Sectors of one site share one clock. Default: each emitter is a site.
- `builders`: site -> network builder. A builder's sites share a common clock block, and each
  site keeps a residual block on top of it (initial sigma `init_residual_sigma`, TBC). Off by
  default. How builder identity reaches the filter in real data is open (I3/ICD).

GNSS position and GNSS time are tracked separately for health, so rejecting one is never hidden
by accepting the other at the same instant.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping

import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.protection import hpl, vpl
from pnt.nav.baseline import CHI2_999

C = 299_792_458.0
GNSS_TIME = "gnss:time"  # health key for GNSS time, separate from GNSS position ("gnss")
POS, VEL, CLK, DRIFT = slice(0, 3), slice(3, 6), 6, 7
N_CORE = 8
CLOCK_MODELS = ("independent", "calibrated")


def _two_state_q(s_off: float, s_drift: float, dt: float) -> np.ndarray:
    """Process noise of an (offset, drift) clock over dt, from the white offset noise PSD s_off
    (m^2/s) and the drift random-walk PSD s_drift (m^2/s^3)."""
    return np.array(
        [
            [s_off * dt + s_drift * dt**3 / 3, s_drift * dt**2 / 2],
            [s_drift * dt**2 / 2, s_drift * dt],
        ]
    )


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
        pseudorange_receiver_clock: bool = False,  # True once the sim models it (#47)
        clock_model: str = "independent",  # or "calibrated" (ADR-0022, Proposed)
        sites: Mapping[str, str] | None = None,  # emitter -> site; default one site per emitter
        builders: Mapping[str, str] | None = None,  # site -> network builder; default none
        tower_h0: float = 2.6e-22,  # s: tower oscillator, coasting (Shamaei 2018, TBC)
        tower_h_2: float = 4e-26,  # 1/s: tower oscillator, coasting (Shamaei 2018, TBC)
        calib_q_offset: float = 0.2,  # m/sqrt(s): extra offset noise while calibrating (TBC)
        calib_q_drift: float = 0.01,  # m/s/sqrt(s): extra drift noise while calibrating (TBC)
        init_tower_drift_sigma: float = 1.0,  # m/s (3 ppb): a tower clock's drift (TBC)
        init_residual_sigma: tuple[float, float] = (300.0, 0.1),  # m, m/s: site vs builder (TBC)
    ):
        if clock_model not in CLOCK_MODELS:
            raise ValueError(f"clock_model must be one of {CLOCK_MODELS}, not {clock_model!r}")
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
        self.calibrated = clock_model == "calibrated"
        self.width = 2 if self.calibrated else 1  # states per clock block: offset (, drift)
        self.sites = dict(sites or {})
        self.builders = dict(builders or {})
        self.s_tower = (C**2 * tower_h0 / 2.0, C**2 * 2.0 * np.pi**2 * tower_h_2)  # m^2/s, m^2/s^3
        self.s_calib = (calib_q_offset**2, calib_q_drift**2)
        self.init_tower_drift_sigma = init_tower_drift_sigma
        self.init_residual_sigma = init_residual_sigma
        self.x: np.ndarray | None = None
        self.P: np.ndarray | None = None
        self.t_ns: int | None = None
        self.clock_idx: dict[str, int] = {}  # clock block ("site:..", "builder:..") -> index
        self.calibrating = False  # tower clocks calibrating (GNSS trusted) or coasting
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

    def _augment(self, key: str, value: float, sigma: tuple[float, float]) -> int:
        """Add a clock block (offset, and drift if calibrated) with the given initial sigmas."""
        n, w = len(self.x), self.width
        self.x = np.append(self.x, [value, 0.0][:w])
        P = np.zeros((n + w, n + w))
        P[:n, :n] = self.P
        P[n:, n:] = np.diag(np.square(sigma[:w]))
        self.P = P
        self.clock_idx[key] = n
        return n

    def clock_offsets(self, emitter: str, residual: float) -> tuple[list[int], bool]:
        """State indices of the clock offsets in this emitter's pseudorange, adding blocks on
        first sight. `residual` (pseudorange minus range and receiver clock) seeds a new block.
        Returns (indices, whether the emitter's site clock is new)."""
        site = self.sites.get(emitter, emitter)
        builder = self.builders.get(site)
        wide = (self.init_emitter_sigma, self.init_tower_drift_sigma)
        idx = []
        if builder is not None:
            bkey = f"builder:{builder}"
            if bkey not in self.clock_idx:
                self._augment(bkey, residual, wide)
            idx.append(self.clock_idx[bkey])
        skey = f"site:{site}"
        new = skey not in self.clock_idx
        if new:
            if builder is None:
                self._augment(skey, residual, wide)
            else:
                self._augment(skey, residual - self.x[idx[0]], self.init_residual_sigma)
        idx.append(self.clock_idx[skey])
        return idx, new

    def gnss_trusted(self) -> bool:
        """GNSS position accepted recently, and neither GNSS position nor time rejected since."""
        never = -(10**18)
        used = self.last_used.get("gnss", never)
        return (
            self.t_ns - used <= self.gnss_timeout_ns
            and self.last_rejected.get("gnss", never) <= used
            and self.last_rejected.get(GNSS_TIME, never) <= self.last_used.get(GNSS_TIME, never)
        )

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
        if self.calibrated:
            self.calibrating = self.gnss_trusted()
            s_off, s_drift = self.s_tower
            if self.calibrating:
                s_off, s_drift = s_off + self.s_calib[0], s_drift + self.s_calib[1]
            q = _two_state_q(s_off, s_drift, dt)
            for i in self.clock_idx.values():
                F[i, i + 1] = dt
                Q[i : i + 2, i : i + 2] = q
        else:
            for i in self.clock_idx.values():
                Q[i, i] = self.q_emitter**2 * dt
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        self.t_ns = t_ns

    def _update(self, key: str, t_ns: int, y, H, R, gate: bool = True) -> bool:
        y = np.atleast_1d(y)
        S_inv = np.linalg.inv(H @ self.P @ H.T + R)
        nis = float(y @ S_inv @ y)
        if gate and nis > CHI2_999[len(y)]:
            self.last_rejected[key] = t_ns
            return False
        K = self.P @ H.T @ S_inv
        self.x = self.x + K @ y
        I_KH = np.eye(len(self.x)) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T  # Joseph form
        self.last_used[key] = t_ns
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
        key = GNSS_TIME if (m.source, m.kind) == ("gnss", "time") else m.source
        self._update(key, m.t_ns, y, H, R, gate)

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
        if self.last_rejected.get(GNSS_TIME, never) > self.last_used.get(GNSS_TIME, never):
            flags.append("time_spoof_suspected")  # GNSS time disagrees with our clock model
        h = hpl(P3)
        status = "unsafe" if h > self.alert_limit_m else ("degraded" if flags else "nominal")
        trust = {
            s: (1.0 if self.t_ns - t <= self.gnss_timeout_ns else 0.0)
            for s, t in self.last_used.items()
            if s != GNSS_TIME
        }
        # The clock is only estimated once a time source has observed it (ICD: null otherwise)
        observed = GNSS_TIME in self.last_used
        return Estimate(
            t_ns=self.t_ns,
            pos_enu=tuple(self.x[POS]),
            vel_enu=tuple(self.x[VEL]),
            pos_cov=tuple(P3.ravel()),
            clock_bias_s=float(self.x[CLK] / C) if observed else 0.0,
            clock_sigma_s=float(np.sqrt(self.P[CLK, CLK]) / C) if observed else None,
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
    """GNSS time solution: local clock minus GPS time, in seconds (ICD `time`).

    Only GNSS for now. Broadcast time (WWVB, FM RDS) is UTC plus a propagation delay, so it needs
    the leap-second offset and its own model before it can update this state."""
    if m.source != "gnss":
        return None
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
    idx, new = ekf.clock_offsets(m.emitter, m.value[0] - r - rx)
    H = _row(ekf)
    H[0, POS] = d / r
    if ekf.pr_rx_clock:
        H[0, CLK] = 1.0
    H[0, idx] = 1.0
    y = m.value[0] - (r + rx + float(np.sum(ekf.x[idx])))
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
