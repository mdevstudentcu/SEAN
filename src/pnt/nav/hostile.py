"""A located jammer as a low-trust coarse range beacon (P8, ADR-0025 Proposed, #93). Sim only.

The jammer's received power (`rssi` records with `meta.hostile`, `pnt.sim.hostile`) is a coarse
range to its told position through the log-distance model

    P_rx = P_tx - 10 n log10(r)        (constant losses folded into P_tx)

with P_tx a filter state. The EKF uses it only when built with `hostile=` options
(`EKF(hostile={...})`); without them the records are ignored before any prediction, so every
other estimator's output is unchanged. It is offered only behind the solution-separation monitor
(`ekf-mhss-beacon`), which holds guardrails 1 and 3. ADR-0025's guardrails, as built:

1. **Own fault hypothesis.** `pnt.integrity.mhss` gives each beacon the hypothesis
   `hostile:<emitter>` with prior `p_hostile` (TBC), far above the tower priors, and a
   sub-filter that never sees it: the all-but-hostile solution.
2. **Promotion gate.** A beacon starts as a *candidate*: its power state is learned, and its
   position is never touched. The update is on the power state alone, with the position's
   uncertainty added to the noise (a consider update), so no cross-covariance builds up. It is
   *promoted* once, over the last `promote_window_s`, it was heard throughout with at least
   `promote_min_samples` records, their mean NIS is within the 99.9 % bound (power, path loss
   and the filter's own predicted geometry agree: a stationary, steady jammer), the power state
   is known to `promote_power_sigma_db`, and our horizontal position to `promote_pos_sigma_m`.
   It is demoted back to candidate, its power forgotten, at once on one innovation over
   `demote_nis` (a power step) or after `demote_run` in a row over the 99.9 % gate, and when it
   has not been heard for `lost_s` (switch-off).
3. **Weight cap.** A promoted update's noise is inflated until a deceptive move of one sigma of
   the measurement shifts the horizontal solution by at most `cap_share` of the alert limit in
   that update. The cap is per update: what a sustained deception does over many updates is the
   monitor's job, and the honeypot scenarios measure it. *Never the only aid in any direction*
   is held by the protection level: the monitor's HPL is never below the all-but-hostile
   solution's own fault-free bound plus its separation, so the beacon can reduce the error but
   not the PL.
4. **Power as a random walk** (`power_rw_db`). There is no transmitter clock: power has none.
5. **Shown separately.** A promoted beacon's updates are counted under the trust key
   `hostile:<emitter>`, never under `gnss`, and the estimate carries the flag `hostile_beacon`
   while one is in use. Candidate updates are not counted: they carry no position information.

Not built: locating the jammer (its told position comes with the record), rogue-cell detection
(ADR-0025 sends those to ADR-0023), and use with the calibrated clock model's rollback (beacon
power states are not rolled back). Every value is TBC.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Measurement
from pnt.nav.baseline import CHI2_999

DB_PER_NEPER_RANGE = 10.0 / np.log(10.0)  # d(10 log10 r)/d(ln r)
MIN_RANGE_M = 1.0  # numerical: the log is taken of at least this range
FLAG = "hostile_beacon"


def _chi2_999_mean(dof: int) -> float:
    """99.9 % bound on a mean NIS per degree of freedom over `dof` dof (Wilson-Hilferty)."""
    z = 3.090232306167813
    a = 2.0 / (9.0 * dof)
    return (1.0 - a + z * np.sqrt(a)) ** 3


def capped_noise(a: float, s0: float, r: float, cap_m: float) -> float:
    """Measurement noise variance, at least `r`, at which one sigma of the measurement moves the
    horizontal solution by at most `cap_m` (ADR-0025 guardrail 3).

    `a` is |P H'| over the horizontal position rows and `s0` is H P H'. One sigma moves the
    solution by a sqrt(R) / (s0 + R), largest at R = s0, so the cap is met from the larger root
    of cap R - a sqrt(R) + cap s0 = 0 upwards, if it is not met already."""
    if a * np.sqrt(r) / (s0 + r) <= cap_m:
        return r
    root = (a + np.sqrt(max(a * a - 4.0 * cap_m * cap_m * s0, 0.0))) / (2.0 * cap_m)
    return max(r, root * root)


@dataclass(frozen=True)
class BeaconParams:
    """All TBC (ADR-0025 leaves them TBD); see PR #93's evidence for what they give."""

    path_loss_exponent: float = 2.0  # the sim's value (optimistic: a real filter must guess)
    power_rw_db: float = 0.05  # dB/sqrt(s): power wander, above the sim's honest 0.02
    init_power_sigma_db: float = 30.0  # first-sight power sigma
    promote_window_s: float = 30.0  # stationarity window
    promote_min_samples: int = 20
    promote_power_sigma_db: float = 1.0
    promote_pos_sigma_m: float = 30.0  # our own horizontal sigma (largest axis)
    demote_nis: float = 36.0  # one innovation of 6 sigma: a power step
    demote_run: int = 3  # this many in a row over the 99.9 % gate
    cap_share: float = 0.1  # of the alert limit, per update and one sigma of deception
    lost_s: float = 10.0  # not heard this long: switched off, dropped


@dataclass
class Beacon:
    idx: int  # its power state
    promoted: bool = False
    since_ns: int = 0  # candidate since (the stationarity window starts here)
    last_ns: int = 0  # last record
    bad_run: int = 0
    nis: deque = field(default_factory=deque)  # (t_ns, NIS) of candidate updates
    events: list = field(default_factory=list)  # (t_ns, "promoted" | "demoted: <why>")


class Beacons:
    """The hostile beacons one EKF uses (`EKF.hostile`), and their gate."""

    def __init__(self, params: BeaconParams, alert_limit_m: float):
        self.p = params
        self.cap_m = params.cap_share * alert_limit_m
        self.by_emitter: dict[str, Beacon] = {}
        self._pos: dict[str, tuple[np.ndarray, float]] = {}
        self.last_promoted_use: int | None = None

    # --- filter hooks ------------------------------------------------------------------
    def process_noise(self, Q: np.ndarray, dt: float) -> None:
        q = self.p.power_rw_db**2 * dt
        for b in self.by_emitter.values():
            Q[b.idx, b.idx] = q

    def flags(self, t_ns: int) -> list[str]:
        used = self.last_promoted_use
        return [FLAG] if used is not None and t_ns - used <= self.p.lost_s * 1e9 else []

    # --- the measurement model ------------------------------------------------------------
    def model(self, ekf, m: Measurement):
        """(innovation, H, R, gate) for a promoted beacon, else None (a candidate's own update
        is done here, on its power state only)."""
        told = self._told(m, ekf.origin_llh)
        if told is None:
            return None
        e, sigma_e = told
        d = ekf.x[:3] - e
        r = max(float(np.linalg.norm(d)), MIN_RANGE_M)
        n = self.p.path_loss_exponent
        loss = 10.0 * n * np.log10(r)
        z = m.value[0]
        b = self.by_emitter.get(m.emitter)
        if b is not None and m.t_ns - b.last_ns > self.p.lost_s * 1e9:
            self._demote(ekf, b, m.t_ns, z + loss, "not heard")
        if b is None:
            idx = ekf._append_states([z + loss], [self.p.init_power_sigma_db])
            b = self.by_emitter[m.emitter] = Beacon(idx=idx, since_ns=m.t_ns)
            b.last_ns = m.t_ns
            return None
        b.last_ns = m.t_ns
        y = z - (ekf.x[b.idx] - loss)
        hp = -n * DB_PER_NEPER_RANGE * d / (r * r)  # d(P_rx)/d(our position), dB/m
        # told position error: a consider term on the noise, horizontal
        r_meas = m.sigma[0] ** 2 + sigma_e**2 * float(hp[:2] @ hp[:2])
        if not b.promoted:
            return self._candidate(ekf, b, m.t_ns, y, hp, r_meas, z + loss)
        H = np.zeros((1, len(ekf.x)))
        H[0, :3] = hp
        H[0, b.idx] = 1.0
        ph = ekf.P @ H[0]
        s0 = float(H[0] @ ph)
        nis = y * y / (s0 + r_meas)
        if nis > self.p.demote_nis:
            self._demote(ekf, b, m.t_ns, z + loss, "power step")
            return None
        if nis > CHI2_999[1]:
            b.bad_run += 1
            if b.bad_run >= self.p.demote_run:
                self._demote(ekf, b, m.t_ns, z + loss, "run of large innovations")
            return None
        b.bad_run = 0
        R = capped_noise(float(np.hypot(ph[0], ph[1])), s0, r_meas, self.cap_m)
        self.last_promoted_use = m.t_ns
        return y, H, np.array([[R]]), False  # gated above, on the uncapped noise

    def _candidate(self, ekf, b: Beacon, t_ns: int, y: float, hp, r_meas: float, seed: float):
        """Learn the power state alone (consider update), and test for promotion."""
        p = self.p
        i = b.idx
        r_c = r_meas + float(hp @ ekf.P[:3, :3] @ hp)
        s = ekf.P[i, i] + r_c
        nis = y * y / s
        if nis > p.demote_nis:  # not steady: start the window again
            self._reset(ekf, b, t_ns, seed)
            return None
        k = ekf.P[i, i] / s
        ekf.x[i] += k * y
        ekf.P[i, i] *= 1.0 - k
        b.nis.append((t_ns, nis))
        window = int(p.promote_window_s * 1e9)
        while b.nis and b.nis[0][0] < t_ns - window:
            b.nis.popleft()
        pos_sigma = np.sqrt(np.max(np.linalg.eigvalsh(ekf.P[:2, :2])))
        if (
            t_ns - b.since_ns >= window
            and len(b.nis) >= p.promote_min_samples
            and np.mean([v for _, v in b.nis]) <= _chi2_999_mean(len(b.nis))
            and np.sqrt(ekf.P[i, i]) <= p.promote_power_sigma_db
            and pos_sigma <= p.promote_pos_sigma_m
        ):
            b.promoted, b.bad_run = True, 0
            b.events.append((t_ns, "promoted"))
        return None

    def _demote(self, ekf, b: Beacon, t_ns: int, seed: float, why: str) -> None:
        if b.promoted:
            b.events.append((t_ns, f"demoted: {why}"))
        self._reset(ekf, b, t_ns, seed)

    def _reset(self, ekf, b: Beacon, t_ns: int, seed: float) -> None:
        """Back to a candidate with its power forgotten: independent of every other state."""
        i = b.idx
        ekf.P[i, :] = 0.0
        ekf.P[:, i] = 0.0
        ekf.P[i, i] = self.p.init_power_sigma_db**2
        ekf.x[i] = seed
        b.promoted, b.bad_run, b.since_ns = False, 0, t_ns
        b.nis.clear()

    def _told(self, m: Measurement, origin_llh) -> tuple[np.ndarray, float] | None:
        if m.emitter not in self._pos:
            e = emitter_enu(m.meta, origin_llh)
            if e is None:
                return None
            self._pos[m.emitter] = (e, float(m.meta.get("emitter_sigma_m", 0.0)))
        return self._pos[m.emitter]
