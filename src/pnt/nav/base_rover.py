"""Base/rover estimator (issue #81, ADR-0020): the `ekf` filter, differenced against a ground
reference station that hears the same towers.

A tower's reading at the payload (d) and at the base (b), in metres:
    rho_d = |p - e| + c dt_d + T + noise_d        rho_b = |b - e| + c dt_b + T + noise_b
where T is the tower's clock. Their single difference, at the same epoch,
    rho_d - rho_b = |p - e| - |b - e| + (c dt_d - c dt_b) + noise_d - noise_b
has no tower clock: a wandering, drifting or stepping tower clock cancels, and only the relative
receiver clock remains. The filter keeps `ekf`'s states (position, velocity, payload clock) and
adds four: the base's survey error (3, constant, prior from the session's `sigma_m`) and the
base's clock offset (a random walk). Both are learned while GPS is trusted.

Three things can go wrong, and each has its own answer:
- **The base misses a tower** (dropout, link loss): the payload's reading is differenced against
  the base's last view of that tower's clock, coasted forward with a growing variance (the tower
  clock monitor below). A tower the base has never heard uses `ekf`'s own single-receiver model.
- **One tower's clock jumps** (a tower fault): it cancels in the difference. The monitor sees it
  as one tower jumping alone, restarts that tower's clock and flags `tower_fault`.
- **The base itself is wrong** (moved, a wrong survey, a clock step: ADR-0020's base fault
  hypothesis): its readings disagree with its surveyed position across several towers at once.
  The filter flags `base_excluded`, stops differencing for the rest of the run, and coasts on the
  tower clocks the base measured before the fault.

The tower clock monitor is one small filter per tower, outside the main state: the base's
reading minus its surveyed range, `z = rho_b - |b_told - e|` (the tower clock plus the base's
clock), as a random walk. Its innovations, averaged over a short window, are the base check.

The base check needs the base's surveyed position, which the session gives in its `reference`
block (ICD-session). Without one, or with no reference records, this is `ekf` with the payload's
receiver clock in its tower readings.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator

import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import RECEIVERS, Estimate, Measurement
from pnt.nav.ekf import CLK, EKF, POS, C

# 99.9 % chi-square quantiles by degrees of freedom (the gate the rest of nav uses)
CHI2_999 = {1: 10.83, 2: 13.82, 3: 16.27, 4: 18.47, 5: 20.52, 6: 22.46, 7: 24.32, 8: 26.12}


class _Monitor:
    """The base's view of one tower's clock (plus the base clock): a scalar random walk."""

    def __init__(self, t_ns: int, z: float, r: float):
        self.t_ns, self.x, self.p = t_ns, z, r

    def predicted(self, t_ns: int, q: float) -> tuple[float, float]:
        return self.x, self.p + q**2 * max(t_ns - self.t_ns, 0) / 1e9

    def update(self, t_ns: int, z: float, r: float, q: float) -> tuple[float, float]:
        """Fold in a reading; returns (innovation, its variance)."""
        x, p = self.predicted(t_ns, q)
        s = p + r
        k = p / s
        nu = z - x
        self.t_ns, self.x, self.p = t_ns, x + k * nu, (1 - k) * p
        return nu, s

    def copy(self) -> _Monitor:
        return _Monitor(self.t_ns, self.x, self.p)


class BaseRoverEKF(EKF):
    name = "ekf-base"

    def __init__(
        self,
        origin_llh=None,
        reference: dict | None = None,
        unknown_survey_sigma_m: float = 30.0,  # TBC: used when the session's sigma_m is TBD
        base_clock_sigma_s: float = 1e-6,  # TBC: prior on the base's clock before calibration
        q_base_clock: float = 0.3,  # m/sqrt(s), TBC: a PPS-disciplined clock's wander
        q_monitor: float = 0.5,  # m/sqrt(s), TBC: tower clock wander as the base sees it
        check_window_s: float = 10.0,  # TBC: base check averaging window
        check_min_samples: int = 5,  # TBC: a tower needs this many readings in the window
        **config,
    ):
        config.setdefault("pseudorange_receiver_clock", True)
        super().__init__(origin_llh=origin_llh, **config)
        self.base_told: np.ndarray | None = None
        self.survey_sigma_m = unknown_survey_sigma_m
        if reference and origin_llh is not None:
            self.base_told = np.asarray(llh_to_enu(reference["position_llh"], origin_llh), float)
            sigma = reference.get("sigma_m")
            if isinstance(sigma, int | float) and not isinstance(sigma, bool):
                self.survey_sigma_m = float(sigma)
        self.base_clock_sigma_m = C * base_clock_sigma_s
        self.q_base_clock, self.q_monitor = q_base_clock, q_monitor
        self.check_window_ns = int(check_window_s * 1e9)
        self.check_min_samples = check_min_samples
        self.bpos: slice | None = None  # base survey error states
        self.bclk: int | None = None  # base clock state
        self.pending: list[Measurement] = []
        self.monitor: dict[str, _Monitor] = {}
        self.history: dict[str, deque] = {}  # recent (t_ns, innovation, variance) per tower
        self.snapshots: deque = deque()  # (t_ns, monitor copy), for rolling back on a base fault
        self.base_fault_t: int | None = None
        self.tower_fault_t: dict[str, int] = {}

    # --- state ---------------------------------------------------------------------------
    @property
    def has_base(self) -> bool:
        return self.base_told is not None

    @property
    def differencing(self) -> bool:
        return self.has_base and self.base_fault_t is None

    def _init(self, m: Measurement) -> None:
        super()._init(m)
        if not self.has_base:
            return
        n = len(self.x)
        self.x = np.append(self.x, np.zeros(4))
        P = np.zeros((n + 4, n + 4))
        P[:n, :n] = self.P
        P[n : n + 3, n : n + 3] = np.eye(3) * self.survey_sigma_m**2
        P[n + 3, n + 3] = self.base_clock_sigma_m**2
        self.P = P
        self.bpos, self.bclk = slice(n, n + 3), n + 3

    def predict(self, t_ns: int) -> None:
        dt = (t_ns - self.t_ns) / 1e9
        super().predict(t_ns)
        if dt > 0 and self.bclk is not None:
            self.P[self.bclk, self.bclk] += self.q_base_clock**2 * dt

    # --- measurements ----------------------------------------------------------------------
    def settle(self, t_ns: int) -> None:
        """Process the tower readings held for an epoch before `t_ns`."""
        if self.pending and self.pending[0].t_ns < t_ns:
            self._flush()

    def process(self, m: Measurement) -> None:
        self.settle(m.t_ns)
        if m.kind == "pseudorange" and self.x is not None and self.has_base:
            self.pending.append(m)  # paired with the base's reading of the same epoch
            return
        if m.receiver != "payload":
            return  # the base's other records, and its towers before we have a fix
        super().process(m)

    def _flush(self) -> None:
        pending, self.pending = self.pending, []
        t = pending[0].t_ns
        self.predict(t)
        payload: dict[str, Measurement] = {}
        base: dict[str, Measurement] = {}
        for m in pending:
            if self._emitter(m) is not None:
                (base if m.receiver == "reference" else payload)[m.emitter] = m
        if self.differencing:
            self._check_base(t, base)
        for emitter, d in payload.items():
            b = base.get(emitter) if self.differencing else None
            if b is not None:
                self._difference(d, b.value[0], b.sigma[0] ** 2)
            elif emitter in self.monitor:
                z, r = self.monitor[emitter].predicted(t, self.q_monitor)
                self._difference(d, z + self._told_range(d), r)
            else:
                super().process(d)  # no base view of this tower: single-receiver model
        if self.differencing:
            for emitter, b in base.items():
                self._monitor(t, emitter, b)

    def _told_range(self, m: Measurement) -> float:
        return float(np.linalg.norm(self.base_told - self._emitter(m)))

    def _difference(self, d: Measurement, rho_b: float, r_b: float) -> None:
        """Payload minus base for one tower: no tower clock, the relative receiver clock left."""
        e = self._emitter(d)
        dp = self.x[POS] - e
        b = self.base_told + self.x[self.bpos]
        db = b - e
        rp, rb = float(np.linalg.norm(dp)), float(np.linalg.norm(db))
        H = np.zeros((1, len(self.x)))
        H[0, POS] = dp / rp
        H[0, self.bpos] = -db / rb
        H[0, CLK] = 1.0 if self.pr_rx_clock else 0.0
        H[0, self.bclk] = -1.0
        rx = self.x[CLK] if self.pr_rx_clock else 0.0
        y = (d.value[0] - rho_b) - (rp - rb + rx - self.x[self.bclk])
        self._update(d.source, d.t_ns, y, H, np.array([[d.sigma[0] ** 2 + r_b]]))

    # --- the base as its own fault hypothesis ---------------------------------------------
    def _monitor(self, t: int, emitter: str, b: Measurement) -> None:
        z, r = b.value[0] - self._told_range(b), b.sigma[0] ** 2
        mon = self.monitor.get(emitter)
        if mon is None:
            self.monitor[emitter] = _Monitor(t, z, r)
            return
        nu, s = mon.update(t, z, r, self.q_monitor)
        self.history.setdefault(emitter, deque()).append((t, nu, s))
        if not self.snapshots or t - self.snapshots[-1][0] >= 1_000_000_000:
            self.snapshots.append((t, {k: v.copy() for k, v in self.monitor.items()}))
        while self.snapshots and t - self.snapshots[0][0] > 3 * self.check_window_ns:
            self.snapshots.popleft()

    def _check_base(self, t: int, base: dict[str, Measurement]) -> None:
        """Windowed mean of each tower's monitor innovation, against its spread. One tower out:
        that tower's clock jumped (it cancels in the difference), so restart its monitor.
        Several out together: the base is inconsistent with its survey, so exclude it."""
        stats: dict[str, float] = {}
        for emitter, h in self.history.items():
            while h and t - h[0][0] > self.check_window_ns:
                h.popleft()
            if len(h) >= self.check_min_samples:
                nu = np.array([x[1] for x in h])
                s = np.array([x[2] for x in h])
                stats[emitter] = float(nu.mean() ** 2 / (s.mean() / len(h)))
        if not stats:
            return
        total = sum(stats.values())
        if total <= CHI2_999[min(len(stats), 8)]:
            return
        worst = max(stats, key=stats.get)
        rest = total - stats[worst]
        if len(stats) == 1 or rest <= CHI2_999[min(len(stats) - 1, 8)]:
            self.tower_fault_t[worst] = t
            self.monitor.pop(worst, None)
            self.history.pop(worst, None)
            for _, snap in self.snapshots:
                snap.pop(worst, None)
            return
        self.base_fault_t = t
        before = [snap for ts, snap in self.snapshots if ts <= t - 2 * self.check_window_ns]
        if before:
            self.monitor = before[-1]  # the tower clocks as the base saw them before the fault
        self.history.clear()

    # --- output --------------------------------------------------------------------------
    def estimate(self) -> Estimate:
        est = super().estimate()
        if not self.has_base:
            return est
        flags = list(est.flags)
        if self.base_fault_t is not None:
            flags.append("base_excluded")
        if any(self.t_ns - ts <= self.gnss_timeout_ns for ts in self.tower_fault_t.values()):
            flags.append("tower_fault")
        status = est.status
        if status == "nominal" and flags:
            status = "degraded"
        trust = {**est.trust, "reference": 0.0 if self.base_fault_t is not None else 1.0}
        return Estimate(
            t_ns=est.t_ns,
            pos_enu=est.pos_enu,
            vel_enu=est.vel_enu,
            pos_cov=est.pos_cov,
            clock_bias_s=est.clock_bias_s,
            clock_sigma_s=est.clock_sigma_s,
            hpl_m=est.hpl_m,
            vpl_m=est.vpl_m,
            status=status,
            trust=trust,
            flags=flags,
        )


def run(
    measurements: Iterable[Measurement],
    epoch_ns: int = 100_000_000,
    origin_llh=None,
    reference: dict | None = None,
    **config,
) -> Iterator[Estimate]:
    """Feed time-ordered measurements from both receivers; yield an Estimate every epoch."""
    f = BaseRoverEKF(origin_llh=origin_llh, reference=reference, **config)
    next_epoch = None
    for m in measurements:
        f.settle(m.t_ns)
        if f.x is not None:
            if next_epoch is None:
                next_epoch = (f.t_ns // epoch_ns + 1) * epoch_ns
            while next_epoch <= m.t_ns:
                f.predict(next_epoch)
                yield f.estimate()
                next_epoch += epoch_ns
        f.process(m)


run.receivers = RECEIVERS
