"""GNSS position spoof monitor (#173): towers or the IMU against the GNSS position, opt-in.

An integrity monitor on the EKF's `monitor` hook (`ekf.run(..., monitor=SpoofMonitor)`), like
`mhss.MHSS`. It sees each measurement before the filter does and every Estimate after it. It
holds no state the filter learns from, so nothing the filter absorbs while GNSS steers it (tower
clocks, multipath or told-position states, the receiver clock) can hide a spoof from it. Two
tests, each optional:

Tower displacement tests (`towers=True`), one per (lag, window) pair in `tower_tests`: a short
lag catches a step within its window, a long lag lets a slow ramp build up against the towers'
own error. Each runs once a second. Per tower reading, the residual against the latest
GNSS position fix (extrapolated with the filter's velocity to the reading's time):
    r = pseudorange - |p_gnss - e_tower|.
With honest GNSS, r is the site's clock and told-position bias, the common clock (our dongle's,
a builder's), multipath and noise. With GNSS displaced by d(t), r also carries -u . d(t), u the
horizontal line of sight. So:
- Over the last `lag_s + window_s`, the residuals are split into a constant per site and a
  common term per epoch (two-way least squares). That removes every clock and the constant part
  of each site's bias: tower time never counts for or against GNSS (ADR-0024), only geometry.
- Per site, delta_i = mean over the last `window_s` minus mean over the `window_s` ending
  `lag_s` earlier. A site counts if heard in at least half of each window.
- Across sites: delta_i = c + u_i . g + e_i, by least squares, with g the displacement of the
  GNSS position against the towers over `lag_s` (sign aside) and c what is common. The e_i are
  taken as independent across sites with one unknown variance (multipath and noise are per
  site; this is the assumption of the test, TBC against real captures).
- Statistic: F = (g' A^-1 g / 2) / s^2, A the (2x2) displacement block of (X'X)^-1, s^2 the
  residual variance of the fit pooled over the last `pool_s` of tests. A ramp or a jump goes
  into g, not into the residuals, so pooling cannot absorb it. Under no spoof F follows an F
  distribution with (2, dof) degrees of freedom; dof is the per-test (n - 3) times the number of
  non-overlapping windows in the pooled span (overlapping tests are not independent, so they
  are not counted twice).
- No opinion with fewer than `min_sites` sites in both windows: one to three towers cannot
  separate a GNSS displacement from the common clock (2 position unknowns and 1 clock).
- Sliding, not anchored: the test compares GNSS now with GNSS `lag_s` ago, so it needs no
  calibration from before the spoof and a slow ramp cannot be learned as normal. Its power is
  set by how much the towers' own errors change over `lag_s` (multipath correlated over tens of
  seconds), which is what limits it against a ramp (analysis/spoof_detection.py).

IMU window test (`imu=True`, for `motion="imu"`). A GNSS-free copy of the filter fed only the
IMU and the barometer, re-seeded from the main filter every `imu_window_s` in two staggered
copies (the older one is tested), only after its test has been quiet. Its horizontal position
against the main filter's, with covariance P_copy - P_main (Brenner's solution separation, as
`mhss`), is a chi-square value with 2 dof. It sees what the IMU did not: a change in GNSS
velocity without the acceleration to match (the onset of a ramp, a jump). A ramp already running
when a copy is seeded is inherited by it, so it catches acceleration, not velocity: a spoofer
who accelerates below the IMU's bias uncertainty passes it.

Thresholds (both TBC): T4 asks for at most 1 false alarm per hour. A test run every `dt` seconds
with false-alarm probability p per test raises at most 3600 p / dt false alarms per hour (union
bound over tests, ignoring that the hold needs several in a row), so `p_fa_towers` 1e-4 at 1 Hz
gives at most 0.36 per hour (split evenly between the tower tests), and `p_fa_imu` 1e-5 at the
10 Hz output gives at most 0.36. An exceedance must hold for `hold_s` (TBC, 3 s) before it
alarms.

When it fires: the filter's own spoof handling (`EKF.raise_spoof_alarm`): `spoof_suspected` and
`gnss_excluded` are flagged, GNSS position is no longer used, and a calibrated filter rolls its
tower clocks back. The filter clears the alarm once GNSS agrees with its GNSS-free estimate
again; the monitor then starts its windows afresh. The monitor does not test while the alarm
holds.
"""

from __future__ import annotations

import copy
import math
from collections import deque
from dataclasses import dataclass, field

import msgspec
import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Estimate, Measurement

SPOOF_FLAGS = ("spoof_suspected", "gnss_excluded")
GNSS_FIX_MAX_AGE_NS = 1_000_000_000  # a tower reading needs a GNSS fix this recent (TBC)
SEP_FLOOR_M = 0.1  # floor on a separation's sigma, as mhss.SEP_FLOOR_M (regression guard)


@dataclass
class Params:
    towers: bool = True
    imu: bool = False
    # Tower displacement tests (all TBC): (lag_s, window_s) pairs, each run every second. A short
    # lag catches a step within its window; a long lag lets a slow ramp build up against the
    # towers' own error. Picked on tuning seeds 100-109 of the many-tower drone case: lags of
    # (30, 60, 120, 240) s with windows of (10, 20) s, alone; (120, 20) had the shortest median
    # time to alert on the ramp with no false alarm, and (30, 10) is the shortest lag tried, for
    # steps. The false-alarm budget is split evenly between them (Bonferroni).
    tower_tests: tuple[tuple[float, float], ...] = ((30.0, 10.0), (120.0, 20.0))
    pool_s: float = 300.0  # span over which each test's residual variance is pooled
    min_sites: int = 5  # sites in both windows; n - 3 >= 2 for a variance per test
    p_fa_towers: float = 1e-4  # per second, all tower tests: <= 0.36 false alarms per hour
    # IMU window test (all TBC)
    imu_window_s: float = 20.0  # re-seed period of each GNSS-free IMU copy
    imu_quiet_s: float = 5.0  # a copy re-seeds only after its test has been quiet this long
    imu_quiet_max: float = 0.5  # quiet: the test below this fraction of its threshold
    p_fa_imu: float = 1e-5  # per epoch, at 10 Hz: <= 0.36 false alarms per hour (bound)
    hold_s: float = 3.0  # an exceedance held this long raises the alarm


@dataclass
class Report:
    """Last values of each test, for analysis (not in the ICD Estimate)."""

    t_ns: int = 0
    # per tower test ("<lag>/<window>"): (F, threshold, sites, (g_e, g_n), sigma_m), None: no
    # opinion. sigma_m: 1-sigma of g along its worst axis, the towers' own uncertainty about
    # how far the GNSS position moved over the lag
    towers: dict[str, tuple | None] = field(default_factory=dict)
    imu_q: float | None = None  # chi-square value of the IMU test, None: no opinion
    imu_thr: float = float("nan")


def f_threshold(p: float, dof: int) -> float:
    """Upper p quantile of the F(2, dof) distribution, in closed form: for 2 numerator degrees of
    freedom, P(F > x) = (1 + 2 x / dof) ** (-dof / 2)."""
    return dof / 2.0 * (p ** (-2.0 / dof) - 1.0)


def towers_test(
    rows: list[tuple[int, str, float, float, float]], t_ns: int, lag_ns: int, win_ns: int
) -> tuple[np.ndarray, np.ndarray, float, int] | None:
    """One tower displacement test over `rows` (t_ns, site, residual, u_e, u_n) ending at
    `t_ns`. Returns (g, A, s2, n): the displacement fit, its (X'X)^-1 block, the residual
    variance of the fit and the number of sites; None with fewer than 4 sites (no variance)."""
    start = t_ns - lag_ns - win_ns
    w = [r for r in rows if start < r[0] <= t_ns]
    if not w:
        return None
    epochs = sorted({r[0] for r in w})
    sites = sorted({r[1] for r in w})
    ei = {x: i for i, x in enumerate(epochs)}
    si = {s: i for i, s in enumerate(sites)}
    R = np.full((len(sites), len(epochs)), np.nan)
    U = np.zeros((len(sites), 2))
    nu = np.zeros(len(sites))
    rec_from, ref_to = t_ns - win_ns, t_ns - lag_ns
    for x, s, r, ue, un in w:
        R[si[s], ei[x]] = r
        if x > rec_from:
            U[si[s]] += (ue, un)
            nu[si[s]] += 1
    ts = np.array(epochs)
    rec, ref = ts > rec_from, ts <= ref_to
    heard = ~np.isnan(R)
    n_rec, n_ref = max(rec.sum(), 1), max(ref.sum(), 1)
    ok = (heard[:, rec].sum(1) >= n_rec / 2) & (heard[:, ref].sum(1) >= n_ref / 2) & (nu > 0)
    if ok.sum() < 4 or not rec.any() or not ref.any():
        return None
    R, U = R[ok], U[ok] / nu[ok, None]
    cols = heard[ok].any(axis=0)  # epochs where a kept site was heard
    R, rec, ref = R[:, cols], rec[cols], ref[cols]
    # two-way least squares (site constant + epoch common term) by alternating means, to 1 mm
    a = np.nanmean(R, axis=1)
    b = np.zeros(R.shape[1])
    for _ in range(100):
        b_new = np.nanmean(R - a[:, None], axis=0)
        a = np.nanmean(R - b_new[None, :], axis=1)
        done = np.max(np.abs(b_new - b)) < 1e-3
        b = b_new
        if done:
            break
    Z = R - a[:, None] - b[None, :]
    delta = np.nanmean(Z[:, rec], axis=1) - np.nanmean(Z[:, ref], axis=1)
    X = np.column_stack([np.ones(len(delta)), U])
    XtX = X.T @ X
    if np.linalg.cond(XtX) > 1e8:
        return None
    inv = np.linalg.inv(XtX)
    beta = inv @ X.T @ delta
    res = delta - X @ beta
    n = len(delta)
    return beta[1:], inv[1:, 1:], float(res @ res / (n - 3)), n


def separation_chi2(fk, f0) -> float:
    """d' S^-1 d for the horizontal separation of filter fk from f0, S = Pk - P0 (Brenner), with
    each eigenvalue taken by magnitude and floored, as `mhss._test`."""
    d = np.asarray(fk.x[:2]) - np.asarray(f0.x[:2])
    S = np.asarray(fk.P[:2, :2]) - np.asarray(f0.P[:2, :2])
    w, V = np.linalg.eigh((S + S.T) / 2)
    w = np.maximum(np.abs(w), SEP_FLOOR_M**2)
    p = V.T @ d
    return float(np.sum(p * p / w))


class SpoofMonitor:
    """Wraps a running EKF. Call `process(m)` before the filter processes m, and `estimate(est)`
    at each epoch after the filter has predicted to it."""

    def __init__(self, main, params: Params | None = None, **kw):
        self.main = main
        self.p = params or Params(**kw)
        self.report = Report()
        self.alarms: list[int] = []  # time each alarm this monitor raised
        self._tests = [(int(lag * 1e9), int(win * 1e9)) for lag, win in self.p.tower_tests]
        self._p_test = self.p.p_fa_towers / max(len(self._tests), 1)
        self._hold_ns = int(self.p.hold_s * 1e9)
        self._imu_thr = -2.0 * math.log(self.p.p_fa_imu)  # chi-square, 2 dof
        self._reset()

    def _reset(self) -> None:
        self._fix: tuple[int, np.ndarray] | None = None  # latest GNSS position fix
        self._rows: deque[tuple[int, str, float, float, float]] = deque()
        # per tower test: (t, s2, n - 3) of its recent tests, and since when it is over
        self._pools: list[deque[tuple[int, float, int]]] = [deque() for _ in self._tests]
        self._exceed: list[int | None] = [None for _ in self._tests]
        self._last_test_s: int | None = None
        self._imu_exceed: int | None = None
        self._copies: list = []  # [filter, next seed time, seed time, last loud time, q]
        self._emitters: dict[str, np.ndarray | None] = {}
        self._was_alarmed = False

    # --- measurements ------------------------------------------------------------------------
    def process(self, m: Measurement) -> None:
        main = self.main
        if main.x is None:
            return
        if self._alarmed():
            return
        if m.source == "gnss" and m.kind == "position_enu":
            self._fix = (m.t_ns, np.asarray(m.value, float))
        elif self.p.towers and m.kind == "pseudorange":
            self._tower_reading(m)
        if self.p.imu and main.imu is not None:
            if m.kind == "accel_gyro" or (m.kind == "altitude" and m.source != "gnss"):
                for c in self._copies:
                    c[0].process(m)

    def _tower_reading(self, m: Measurement) -> None:
        if self._fix is None or m.t_ns - self._fix[0] > GNSS_FIX_MAX_AGE_NS:
            return
        if m.emitter not in self._emitters:
            self._emitters[m.emitter] = emitter_enu(m.meta, self.main.origin_llh)
        e = self._emitters[m.emitter]
        if e is None:
            return
        dt = (m.t_ns - self._fix[0]) / 1e9
        p = self._fix[1] + np.asarray(self.main.x[3:6]) * dt
        d = p - e
        r = float(np.linalg.norm(d))
        h = math.hypot(d[0], d[1])
        if r <= 0 or h <= 0:
            return
        site = m.meta.get("site") or m.emitter
        self._rows.append((m.t_ns, site, m.value[0] - r, d[0] / h, d[1] / h))

    def _alarmed(self) -> bool:
        return bool(getattr(self.main, "spoof_alarm", False))

    # --- output --------------------------------------------------------------------------
    def estimate(self, est: Estimate) -> Estimate:
        t = est.t_ns
        if self._alarmed():
            self._was_alarmed = True
            return est
        if self._was_alarmed:  # the filter cleared the alarm: start every window afresh
            self._reset()
        fired = False
        if self.p.towers:
            fired |= self._tower_step(t)
        if self.p.imu and self.main.imu is not None:
            fired |= self._imu_step(t)
        if not fired:
            return est
        self.alarms.append(t)
        self.main.raise_spoof_alarm()
        self._was_alarmed = True
        flags = list(est.flags) + [f for f in SPOOF_FLAGS if f not in est.flags]
        trust = {**est.trust, "gnss": 0.0}
        return msgspec.structs.replace(est, flags=flags, trust=trust, status="degraded")

    def _held(self, attr: str, over: bool, t: int) -> bool:
        if not over:
            setattr(self, attr, None)
            return False
        if getattr(self, attr) is None:
            setattr(self, attr, t)
        return t - getattr(self, attr) >= self._hold_ns

    def _tower_step(self, t: int) -> bool:
        """Run every tower test once per second; True if any exceedance has held `hold_s`."""
        sec = t // 1_000_000_000
        if sec != self._last_test_s:
            self._last_test_s = sec
            span_max = max((lag + win for lag, win in self._tests), default=0)
            while self._rows and self._rows[0][0] <= t - span_max:
                self._rows.popleft()
            rows = list(self._rows)
            self.report.t_ns = t
            for i, (lag, win) in enumerate(self._tests):
                over = self._tower_test(i, rows, t, lag, win)
                if not over:
                    self._exceed[i] = None
                elif self._exceed[i] is None:
                    self._exceed[i] = t
        return any(e is not None and t - e >= self._hold_ns for e in self._exceed)

    def _tower_test(self, i: int, rows: list, t: int, lag: int, win: int) -> bool:
        key = f"{lag / 1e9:g}/{win / 1e9:g}"
        out = towers_test(rows, t, lag, win)
        if out is None or out[3] < self.p.min_sites:
            self.report.towers[key] = None
            return False
        g, A, s2, n = out
        pool = self._pools[i]
        pool.append((t, s2, n - 3))
        while pool[0][0] <= t - int(self.p.pool_s * 1e9):
            pool.popleft()
        s2p = float(np.mean([s for _, s, _ in pool]))
        windows = int((t - pool[0][0]) // (lag + win)) + 1  # non-overlapping spans pooled
        dof = windows * int(np.median([d for _, _, d in pool]))
        F = float(g @ np.linalg.solve(A, g)) / 2.0 / max(s2p, 1e-12)
        thr = f_threshold(self._p_test, dof)
        sigma = math.sqrt(max(float(np.linalg.eigvalsh(A)[-1]) * s2p, 0.0))
        self.report.towers[key] = (F, thr, n, (float(g[0]), float(g[1])), sigma)
        return F > thr

    def _imu_step(self, t: int) -> bool:
        main = self.main
        if main.imu.aligned_at is None:
            return False
        win = int(self.p.imu_window_s * 1e9)
        if not self._copies:
            for k in (0, 1):
                self._copies.append([copy.deepcopy(main), t + win // (k + 1), t, t, 0.0])
        for c in self._copies:
            c[0].predict(t)
            c[4] = separation_chi2(c[0], main)
            if c[4] >= self.p.imu_quiet_max * self._imu_thr:
                c[3] = t
        # the older copy (seeded first) is tested
        old = min(self._copies, key=lambda c: c[2])
        aged = t - old[2] >= win // 2
        q = old[4] if aged else None
        self.report.imu_q, self.report.imu_thr = q, self._imu_thr
        over = q is not None and q > self._imu_thr
        fired = self._held("_imu_exceed", over, t)
        quiet_ns = int(self.p.imu_quiet_s * 1e9)
        gnss_used = main.gnss_trusted()
        for c in self._copies:
            if t >= c[1] and t - c[3] >= quiet_ns and gnss_used and not over:
                c[0] = copy.deepcopy(main)
                c[1], c[2] = t + win, t
                for o in self._copies:  # keep the copies staggered by half a window
                    if o is not c:
                        o[1] = max(o[1], t + win // 2)
                break
        return fired
