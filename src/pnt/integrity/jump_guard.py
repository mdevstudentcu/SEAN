"""Refuse a detected GNSS position jump instead of following it (#184).

Why: the filter's GNSS gate (`CHI2_999`, 3 dof) rejects a jumped fix, but every rejection leaves
the filter coasting, so its position covariance grows. Once it has grown enough the same jumped
fix passes the same gate, one fix pulls the estimate most of the way, and from then on GNSS is
followed. On the `challenge` drone leg (`ekf`, tuning seeds 100-102) a 25 m jump gets in after
3 to 4 s and a 300 m jump after 28 s. Waiting is all a spoofer has to do.

The rule, for GNSS position fixes only (GNSS time keeps its own test). Until a latch is set it
answers "gate" for every fix, and a latching fix is one the gate rejects anyway, so a run in
which no latch is set is unchanged:

- **Step.** At each fix, the mean of the newest 1 to `STEP_K` fixes is compared with where the
  GNSS stream's own track before them puts them: a line fitted to its fixes of the last
  `TRACK_S` since its last step (with fewer than `TRACK_MIN` of them, the last carried on by the
  stream's velocity from its last line). A difference beyond the noise of the fixes and the track
  (NIS over `STEP_NIS`) is a step of the stream. Neither the filter's position nor its velocity
  enters (except before the stream's first line), so the test does not depend on how far the
  filter has drifted. Averaging up to `STEP_K` fixes catches a step one noisy fix would hide.
- **Latch.** A step, at a fix whose NIS against the filter is also over `JUMP_NIS`, while GNSS
  was used within the filter's `gnss_timeout_s`: GNSS steered the position until a moment ago and
  its stream jumped away from both its own track and the filter. A fix returning after an outage
  never latches; the ordinary gate judges it, as before. The step is the first value of the
  offset `O` that GNSS is taken to hold, with its covariance.
- **While latched,** GNSS position is never used (the fix counts as rejected, so the estimate
  carries `gnss_excluded`). Each further step of the stream is added to `O`, and its covariance
  to `O`'s. A slower change is not a step and leaves `O` alone.
- **Re-admission** (`readmit="undo"`, the default): once `O` is consistent with zero against its
  own covariance (NIS within `ADMIT_NIS`), GNSS is back on its pre-jump track and the latch is
  released. That fix, and the next ones until the filter has agreed with GNSS (NIS within
  `ADMIT_NIS`) for `TRACK_S`, skip the gate: after a long refusal the coasting filter's
  covariance can be far smaller than its true error, and the gate then keeps honest GNSS out
  (on tuning seed 100, with one ungated fix only, it rejected every fix again from 1.2 s on).
  A new step in that time ends it, and latches again if it is a jump.

Why a spoofer cannot get in by waiting: `O`'s covariance grows only when a step is detected,
never with time, and a spoofer that holds its offset leaves `O` at the jump, whose NIS was over
`STEP_NIS > ADMIT_NIS` when it latched. Honest GNSS after the spoof ends: the end is a step back
by the jump, measured against the stream's own track over a few seconds, so it is resolved
however far the filter has drifted; GNSS is re-admitted at that fix.

Limits (stated, not handled):
- A slow change of the offset is not a step, so it never moves `O`: a spoofer that walks GNSS
  back to the truth slowly stays refused, and one that ramps while latched and then jumps back
  by the original jump is let in with the ramp's offset. The ramp is the slow-spoof problem
  (#173).
- A jump or a return spread over more than `STEP_K` fixes (a receiver that smooths its
  solution) may be missed, and a return across a long gap is carried on by an aged velocity whose
  uncertainty may hide it; GNSS then stays refused.
- A jump too small to cross `JUMP_NIS` (about 15 m on the challenge legs) never latches and is
  followed as on `main`. A spoofer that first jams GNSS for longer than `gnss_timeout_s` is
  judged by the ordinary gate when it reappears, as on `main`.
- The thresholds assume Gaussian errors and honest covariances. A false latch costs little: a
  single outlying fix is followed by a step back that undoes it at the next fix.

Alternatives, for the owners' choice (PR evidence): `readmit="never"` keeps a latch for the rest
of the run; `readmit="lr"` re-admits when a likelihood-ratio test of "GNSS honest" against "GNSS
still offset by the jump", on the fix's innovation against the filter's covariance, favours
honest by `LR_ETA`. Its false re-admission probability under a held offset is at most
Phi(-sqrt(2 eta)) per test however long the spoofer waits, but only if the filter's covariance
is honest, which a long coast on the challenge legs is not.

Thresholds (3 dof, GNSS position; every value TBC until REQ-04's false-alarm budget is set):
- `JUMP_NIS` = 30.66: the chi-square 3-dof quantile for 1e-6 per honest fix (about 0.02 per hour
  at 5 Hz) of the filter's innovation, if its covariance is honest.
- `STEP_NIS` = 30.66: the same quantile, 1e-6 per test, so a false step at most 3e-6 per fix
  over the `STEP_K` tests (union bound). A false step during a held spoof moves `O` by about the
  noise and widens its covariance, so it must be rare.
- `ADMIT_NIS` = 16.27: the filter gate's own 99.9 % bound (`CHI2_999[3]`): an honest return is
  refused with probability 1e-3. It must stay under `STEP_NIS`.
- `LR_ETA` = 4.77 (`lr` only): Phi(-sqrt(2 eta)) = 1e-3.
- `TRACK_S` = 2 s, `TRACK_MIN` = 5 fixes, `STEP_K` = 3: not derived, TBC. At 5 Hz a line over
  2 s predicts the next fix with about half a fix's variance, and the vehicle's unmodelled
  acceleration over 2 s (the filter's `q_accel`, in the covariance) stays near a fix's variance.
  Chosen while looking at tuning seeds 100-109, never at the reporting seeds.
"""

from __future__ import annotations

from collections import deque

import numpy as np

JUMP_NIS = 30.66  # chi2.isf(1e-6, 3): false latch 1e-6 per honest fix (TBC)
STEP_NIS = 30.66  # chi2.isf(1e-6, 3): false step 1e-6 per fix (TBC)
ADMIT_NIS = 16.27  # chi2.isf(1e-3, 3), the gate's CHI2_999[3]: honest return refused 1e-3 (TBC)
LR_ETA = 4.77  # norm.isf(1e-3)**2 / 2: held offset re-admitted at most 1e-3 per test (TBC)
TRACK_S = 2.0  # s: the GNSS stream's own track is fitted over this long (TBC)
TRACK_MIN = 5  # fixes in the track before a line is fitted to it
STEP_K = 3  # a step is looked for at the newest 1 to STEP_K fixes
READMIT = ("undo", "never", "lr")
VEL = slice(3, 6)  # pnt.nav.ekf.VEL (not imported: pnt.nav imports this package)


class JumpGuard:
    """Latch on a GNSS position jump and refuse GNSS until the jump is undone (module docstring).

    `verdict(ekf, t_ns, y, H, R)` is called with each GNSS position fix's innovation before the
    filter's update: "refuse" (do not use it), "gate" (the filter's ordinary gate decides) or
    "readmit" (GNSS is back on its pre-jump track: use it without the gate). It reads the
    filter's state and covariance, `last_used`, `gnss_timeout_ns` and `q_accel`, and changes
    nothing."""

    def __init__(self, readmit: str = "undo"):
        if readmit not in READMIT:
            raise ValueError(f"readmit must be one of {READMIT}, not {readmit!r}")
        self.readmit = readmit
        self.latched = False
        self.recovering = False  # released, and the filter has not yet agreed with GNSS
        self._agree_since: int | None = None  # while recovering: the filter agrees since
        self.latches: list[int] = []  # time each latch was set
        self.releases: list[int] = []  # time each latch was released
        self.jump: np.ndarray | None = None  # the step that set the latch
        self.offset: np.ndarray | None = None  # O: the offset GNSS is taken to hold
        self.offset_cov: np.ndarray | None = None
        self._track: deque[tuple[int, np.ndarray, np.ndarray]] = deque()  # (t, z, R) since a step
        self._vel: tuple | None = None  # the stream's velocity, its covariance, when fitted

    def find_step(self, ekf, t_ns: int, z: np.ndarray, R: np.ndarray):
        """Add the fix `z` to the GNSS stream's track and look for a step at its newest fixes:
        the mean of the newest k (1 to `STEP_K`) less where the track before them puts them,
        tested against its covariance. Returns (step, covariance) of the first k over
        `STEP_NIS`, after which the track restarts from those k fixes; else None.

        Where the track puts them: with `TRACK_MIN` earlier fixes in the last `TRACK_S`, a
        straight line fitted to those, so neither the filter's position nor its velocity enters;
        with fewer (just after a step), the last of them carried on by the stream's velocity from
        its last fitted line (by the filter's velocity before the first one)."""
        tr = self._track
        tr.append((t_ns, z, np.asarray(R, float)))
        while t_ns - tr[0][0] > TRACK_S * 1e9:
            tr.popleft()
        q2 = ekf.q_accel**2
        items = list(tr)
        found = None
        for k in range(1, min(STEP_K, len(items) - 1) + 1):
            old, new = items[:-k], items[-k:]
            tn = np.mean([t for t, _, _ in new])
            zn = np.mean([zi for _, zi, _ in new], axis=0)
            Rn = sum(Ri for _, _, Ri in new) / k**2  # covariance of the mean of k fixes
            if len(old) >= TRACK_MIN:
                tau = np.array([(t - tn) / 1e9 for t, _, _ in old])
                Z = np.array([zi for _, zi, _ in old])
                tm = tau.mean()
                sxx = float(((tau - tm) ** 2).sum())
                vel = ((tau - tm) @ (Z - Z.mean(axis=0))) / sxx
                pred = Z.mean(axis=0) - vel * tm  # the line at the new fixes' mean time
                Rbar = sum(Ri for _, _, Ri in old) / len(old)
                g = 1.0 / len(tau) + tm**2 / sxx
                # Unmodelled acceleration bends the track away from a line (the filter's q)
                C = Rn + g * Rbar + np.eye(3) * q2 * (-tau[0]) ** 3 / 3
                if k == 1:
                    self._vel = (vel, Rbar / sxx, t_ns)
            else:
                t0, z0, R0 = old[-1]
                dt = (tn - t0) / 1e9
                if self._vel is None:
                    v, Pv = ekf.x[VEL], ekf.P[VEL, VEL]
                else:  # the stream's velocity, aged by the motion noise since it was fitted
                    age = (t_ns - self._vel[2]) / 1e9
                    v, Pv = self._vel[0], self._vel[1] + np.eye(3) * q2 * age
                pred = z0 + v * dt
                C = Rn + R0 + Pv * dt**2 + np.eye(3) * q2 * dt**3 / 3
            d = zn - pred
            if float(d @ np.linalg.solve(C, d)) > STEP_NIS:
                found = (d, C)
                for _ in range(len(old)):
                    tr.popleft()  # the fixes after the step make a new track
                break
        return found

    def verdict(self, ekf, t_ns: int, y, H, R) -> str:
        y = np.atleast_1d(y)
        if len(y) != 3:
            return "gate"
        z = H @ ekf.x + y  # the fix itself
        out = self.find_step(ekf, t_ns, z, R)
        stepped = out is not None
        S = H @ ekf.P @ H.T + R
        nis = float(y @ np.linalg.solve(S, y))
        if not self.latched:
            never = -(10**18)
            steering = t_ns - ekf.last_used.get("gnss", never) <= ekf.gnss_timeout_ns
            if steering and stepped and nis > JUMP_NIS:
                self.latched, self.recovering = True, False
                self.latches.append(t_ns)
                self.jump, self.offset, self.offset_cov = out[0], out[0], out[1]
                return "refuse"
            if not self.recovering or stepped:
                self.recovering = False
                return "gate"
            # Back on the pre-jump track: GNSS skips the gate until the filter has agreed with it
            # for TRACK_S, so a coasting filter that is wrong and overconfident catches up
            if nis > ADMIT_NIS:
                self._agree_since = None
                return "readmit"
            if self._agree_since is None:
                self._agree_since = t_ns
            if t_ns - self._agree_since >= TRACK_S * 1e9:
                self.recovering = False
            return "gate"
        if stepped:
            self.offset, self.offset_cov = self.offset + out[0], self.offset_cov + out[1]
        if self._readmit(y, S):
            self.latched, self.recovering, self._agree_since = False, True, None
            self.releases.append(t_ns)
            return "readmit"
        return "refuse"

    def _readmit(self, d: np.ndarray, S: np.ndarray) -> bool:
        if self.readmit == "undo":
            off = self.offset
            return float(off @ np.linalg.solve(self.offset_cov, off)) <= ADMIT_NIS
        if self.readmit == "lr":  # log p(d | honest) - log p(d | the jump still held)
            w = np.linalg.solve(S, self.jump)
            return 0.5 * float(self.jump @ w) - float(d @ w) > LR_ETA
        return False
