"""Re-admit GNSS that the towers keep out only because they are overconfident (#246, ADR-0050).

Why: the EKF's chi-square gate judges a GNSS fix against the filter's own covariance. Real LTE
records told 1 to 5 m (their double differences wander 1 to 45 m) keep that covariance near a few
metres while they pull the position tens of metres off, so every GNSS fix is rejected from then
on and the rejection is never undone: the default `ekf` excluded GNSS on 100 % of the epochs of
real session 0151 before any cut (#214 §3). LTE alone kept consistent GNSS out.

The rule, for GNSS position fixes only (GNSS time keeps its own test). It acts only on a fix the
gate has just rejected; a run in which it never fires is unchanged. It re-admits when all hold:

- **An episode that began while GNSS was steering.** The gate rejected a fix while GNSS position
  had been used within the filter's `gnss_timeout_s`, and every fix since was rejected too. An
  episode that begins after a gap (GNSS returning from an outage or a jammer) is never re-admitted
  by this rule: the gate judges it as before. This keeps closed the hole #191 left closed, a
  spoofer that jams first and returns somewhere else.
- **GNSS self-consistent:** no step in the GNSS stream against its own track from the episode's
  first fix on: each fix against a line through the stream's previous `TRACK_N` fixes (at least
  2, within `TRACK_S`), with the line's covariance and the filter's unmodelled acceleration over
  it, NIS over `STEP_NIS` (the jump guard's threshold). Neither the filter's position nor its
  velocity enters, so a filter pulled off does not make honest GNSS look like it jumped (the jump
  guard's test falls back on the filter's velocity at 1 Hz). A jump (`spoof-jump`) or a replay
  delay (`meaconing`) steps the stream there and blocks the episode.
- **Long enough:** the episode has lasted `wait_s`.
- **The towers are not fit to refute it:** their gated innovations over the last `wait_s` run
  larger than their model says (mean NIS per degree of freedom over its 99.9 % bound,
  `CHI2_999_MEAN`). The spoof detector uses the same principle to disarm itself (`spoof_scale`).
  Honest towers that disagree with GNSS keep it out, as before.
- **IMU-consistent, when the filter has an IMU:** the GNSS stream's velocity (the step test's
  line) agrees with the filter's IMU-driven velocity within their covariances (`CHI2_999[3]`).
  A ramp moves the stream's velocity away from the IMU's.

On re-admission the filter takes the fix as at start-up: position and velocity, the tower clock
blocks, our radios' clocks and any arc states go back to their first-sight priors (means kept,
cross terms zeroed, `EKF.reset_for_gnss`), and the fix is used without the gate. The towers then
re-learn their clocks against GNSS. While the towers stay unfit (and the stream steering, without
a step, IMU-consistent), each fix the gate rejects is used without the gate and without another
reset: towers told too tight pull the position away again within seconds, and without this the
filter cycles between a reset and `wait_s` of exclusion (real session 0151: 5 cycles in 100 s).

Limits (stated, not handled):
- **It reopens the slow-spoof hole.** On sim `spoof-ramp` it re-admitted the ramp once in two runs
  for `ekf`, `ekf-imu`, `ekf-guard` and `ekf-imu-guard` (misleading epochs per run 1,441 to 2,026
  to 2,060), and on `challenge-drone-spoof-jump` once for `ekf-imu`: the towers' test and the IMU
  velocity check did not hold a smooth spoof (ADR-0050, `analysis/readmit_attacks.py`). Opt-in
  only; not fit to be a default.
- The window and the bounds assume Gaussian errors. `wait_s` is not derived (TBC).
"""

from __future__ import annotations

from collections import deque

import numpy as np

from pnt.integrity.jump_guard import STEP_NIS

WAIT_S = 10.0  # s: an episode lasts this long, and the towers are judged over it (TBC)
TRACK_N = 5  # the stream's track: its previous fixes, at most this many (TBC)
TRACK_S = 5.0  # s: and at most this old (TBC): 5 fixes at 1 Hz, 1 s at 5 Hz
MIN_TOWER_SAMPLES = 5  # fewer gated tower innovations in the window: no opinion (as CHECK_MIN)
CHI2_999_3 = 16.27  # chi2.isf(1e-3, 3): the IMU velocity check (the gate's CHI2_999[3])
VEL = slice(3, 6)  # pnt.nav.ekf.VEL (not imported: pnt.nav imports this package)
Z_999 = 3.090232306167813  # standard normal 99.9 % quantile


def chi2_999_mean(dof: int) -> float:
    """99.9 % bound on a mean NIS per degree of freedom over `dof` dof (Wilson-Hilferty), as
    `pnt.nav.ekf.CHI2_999_MEAN`."""
    a = 2.0 / (9.0 * dof)
    return (1.0 - a + Z_999 * np.sqrt(a)) ** 3


class GnssReadmit:
    """Re-admit GNSS kept out by towers that are not fit to refute it (module docstring).

    The filter calls `tower(t_ns, nis, dof)` with each gated tower innovation, `observe(ekf, t_ns,
    y, H, R)` with each GNSS position fix before its update, and `decide(ekf, t_ns, used)` after
    it: "reset" (reset to first-sight priors, then use the fix without the gate), "ungated" (use
    it without the gate) or None (the gate's verdict stands)."""

    def __init__(self, wait_s: float = WAIT_S):
        self.wait_ns = int(wait_s * 1e9)
        self._stepped = False
        self._steering = False
        self._fixes: deque[tuple[int, np.ndarray, np.ndarray]] = deque()  # (t, z, R), wait_s
        self.since: int | None = None  # the episode's first rejected fix
        self.blocked = False  # the episode began after a gap, or the stream stepped
        self.recovering = False  # re-admitted, and the towers have not been fit since
        self._towers: deque[tuple[int, float, int]] = deque()
        self.readmits: list[int] = []  # time of each re-admission with a reset

    def tower(self, t_ns: int, nis: float, dof: int) -> None:
        w = self._towers
        w.append((t_ns, nis, dof))
        while w[0][0] < t_ns - self.wait_ns:
            w.popleft()

    def observe(self, ekf, t_ns: int, y, H, R) -> None:
        z = H @ ekf.x + np.atleast_1d(y)  # the fix itself
        R = np.asarray(R, float)
        self._stepped = self._step(ekf, t_ns, z, R)
        f = self._fixes
        f.append((t_ns, z, R))
        while f[0][0] < t_ns - self.wait_ns:
            f.popleft()
        never = -(10**18)
        self._steering = t_ns - ekf.last_used.get("gnss", never) <= ekf.gnss_timeout_ns

    def _step(self, ekf, t_ns: int, z: np.ndarray, R: np.ndarray) -> bool:
        """Whether fix `z` steps from the line through the stream's previous fixes."""
        old = [f for f in self._fixes if f[0] >= t_ns - TRACK_S * 1e9][-TRACK_N:]
        if len(old) < 2:
            return False
        tau = np.array([(t - t_ns) / 1e9 for t, _, _ in old])
        Z = np.array([zi for _, zi, _ in old])
        tm = tau.mean()
        sxx = float(((tau - tm) ** 2).sum())
        vel = ((tau - tm) @ (Z - Z.mean(axis=0))) / sxx
        d = z - (Z.mean(axis=0) - vel * tm)  # the line at the new fix's time
        Rbar = sum(Ri for _, _, Ri in old) / len(old)
        g = 1.0 / len(tau) + tm**2 / sxx
        C = R + g * Rbar + np.eye(3) * ekf.q_accel**2 * (-tau[0]) ** 3 / 3
        return float(d @ np.linalg.solve(C, d)) > STEP_NIS

    def towers_unfit(self, t_ns: int) -> bool:
        w = [r for r in self._towers if r[0] >= t_ns - self.wait_ns]
        if len(w) < MIN_TOWER_SAMPLES:
            return False
        dof = sum(d for _, _, d in w)
        return sum(n for _, n, _ in w) / dof > chi2_999_mean(dof)

    def imu_agrees(self, ekf) -> bool:
        """The GNSS stream's velocity (a line fitted to its fixes of the last `wait_s`) against
        the filter's IMU-driven velocity, within both covariances; True without an IMU. The
        line's covariance adds the filter's unmodelled acceleration over the window (TBC)."""
        if ekf.imu is None:
            return True
        if len(self._fixes) < MIN_TOWER_SAMPLES:
            return False
        tau = np.array([t for t, _, _ in self._fixes], float) / 1e9
        Z = np.array([z for _, z, _ in self._fixes])
        tm = tau.mean()
        sxx = float(((tau - tm) ** 2).sum())
        vel = ((tau - tm) @ (Z - Z.mean(axis=0))) / sxx
        span = tau[-1] - tau[0]
        Rbar = sum(R for _, _, R in self._fixes) / len(tau)
        C = Rbar / sxx + np.eye(3) * ekf.q_accel**2 * span / 12 + ekf.P[VEL, VEL]
        d = vel - ekf.x[VEL]
        return float(d @ np.linalg.solve(C, d)) <= CHI2_999_3

    def decide(self, ekf, t_ns: int, used: bool) -> str | None:
        if used:
            self.since, self.blocked = None, False
            return None
        fit = self._steering and not self._stepped
        if self.recovering:  # still unfit towers: keep GNSS in, without another reset
            if fit and self.towers_unfit(t_ns) and self.imu_agrees(ekf):
                return "ungated"
            self.recovering = False
        if self.since is None:
            self.since = t_ns
            self.blocked = not fit
        else:
            self.blocked |= self._stepped
        if self.blocked or t_ns - self.since < self.wait_ns:
            return None
        if not self.towers_unfit(t_ns) or not self.imu_agrees(ekf):
            return None
        self.since, self.blocked, self.recovering = None, False, True
        self.readmits.append(t_ns)
        return "reset"
