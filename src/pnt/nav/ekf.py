"""The main estimator (issue #12): clock states (stage 1) and an optional IMU motion model
(stage 2).

State (metres and metres per second throughout, so the matrix stays well conditioned):
    [ e n u | ve vn vu | c*dt  c*ddt | (IMU: dθ b_a b_g) | tower clocks ... ]
      position  velocity   receiver clock  motion="imu" only  one block per tower clock

- Motion (`motion`): "cv" (default), constant velocity driven by white acceleration; or "imu",
  strapdown propagation of the payload's IMU (stage 2, `nav/imu.py`), which adds attitude error
  and accelerometer and gyro bias states after the receiver clock. The measurement side is the
  same for both.
- Receiver clock: offset and drift with the standard two-state oscillator model (white
  frequency noise h0 and random-walk frequency noise h-2). Defaults are literature values for a
  TCXO-class oscillator, TBC until measured (ADR-0015).
- Measurements are a registry (`MODELS`): each kind maps to a function returning the predicted
  value, Jacobian row(s) and noise. Unknown kinds are ignored, so new sources add a model only.

Receiver clock in pseudoranges: a real radio's tower ranges all carry our clock offset (c*dt).
The realistic and worst sets add it (`receiver_clock: true`); the base scenarios don't, and
`pseudorange_receiver_clock` defaults to False to match them. Left off against data that has the
term, every tower's clock has to absorb our clock's drift. Turned on, the clock that all towers
share is one more unknown: without GNSS time it is observable only as one common term across the
towers, which costs one tower's worth of geometry, as a GNSS receiver needs a fourth satellite
for its clock. While GNSS time is trusted it anchors the split between our clock and the towers'.

A real record names its radio's clock in `meta.rx_clock` (#121). An RTL-SDR is its own oscillator,
not the GNSS-disciplined clock above, so each name gets its own (offset, drift) block, used in
place of `c*dt` for that record. Its offset starts at zero with a tight prior, because only
differences between dongle and site clocks are observable. `meta.site`, if present, adds the
emitter to `sites`.

Tower clocks (ADR-0022, Proposed) have two models, picked with `clock_model`:
- "independent" (default, the model before ADR-0022): one clock offset per clock, a random walk
  (`q_emitter`). Such a clock is free to absorb its own tower's error, so it adds no
  fault-detection redundancy (Jia, Khalife & Kassas, IEEE T-ITS 2023).
- "calibrated": offset and drift per clock, on the two-state oscillator model. While the
  calibration gate is open the filter is *calibrating*: the clock gets extra process noise
  (`calib_q_offset`, `calib_q_drift`) so offset and drift track what the towers show. Otherwise
  it *coasts*: the learned offset and drift are the prior and only the oscillator noise
  (`tower_h0`, `tower_h_2`) is added, so they stay tight.
Either model can group clocks:
- `sites`: emitter -> site. Sectors of one site share one clock. Default: each emitter is a site.
- `builders`: site -> network builder. A builder's sites share a common clock block, and each
  site keeps a residual block on top of it (initial sigma `init_residual_sigma`, TBC). Off by
  default. How builder identity reaches the filter in real data is open (I3/ICD).

New site clocks (`seed_site_drift`, off by default, on in `CALIBRATED`; calibrated model, ungrouped
sites): a site first heard once two or more sites have calibrated (drift sigma under half its
prior) takes their mean drift as its prior, with their spread and uncertainty as its sigma (at
least `site_drift_floor`, TBC), rather than a fixed (0, `init_tower_drift_sigma`). A drift every
site shows (our clock's while it is not modelled, a builder's) then carries over instead of
making the new site look faulty.

Tower error model (`CALIBRATED`; each part off by default, every value TBC until the radio test
and published data replace it, ADR-0015). Beyond the white noise each reading reports:
- Multipath (`multipath_ratio`, `multipath_tau_s`): a first-order Gauss-Markov state per
  emitter, steady-state sigma `multipath_ratio` times the reported sigma, as `ekf-base` sizes its
  difference bias. A reflection stays wrong for tens of seconds, so treating it as white noise
  makes the filter overconfident in an outage.
- Told position (`tower_position_sigma_m`): the published tower position is off by a constant
  (east, north) error per site. The part along the first line of sight is a constant range bias
  that the site clock already absorbs; the states carry only how the bias changes as the line
  of sight turns (see `tower_states`).
- Clock process noise: `CALIBRATED` sets the tower offset noise (`tower_h0`) and our clock's
  (`h0`, `h_2`) to the realistic set's placeholders rather than literature TCXO values.
These states are learned while GNSS is trusted, like the clocks, and roll back with them.
Cost: a slow drag that a reflection could explain is absorbed by the multipath states before
the towers-vs-GNSS test sees it, so that test loses power against slow ramps (PR evidence).

Calibration gate (calibrated model only). It opens when both hold:
- GNSS has been trusted (position accepted recently, no exclusion, no time alarm) continuously
  for `calib_gate_s`.
- The checks in `calib_checks` agree. Each check is a predicate `(ekf) -> True | False | None`:
  True confirms GNSS, False refutes it, None has no opinion (no recent data). The gate needs at
  least one True and no False. Only evidence that does not fail with GNSS may return True
  (ADR-0024). GNSS-timed evidence (towers) and our GNSS-disciplined clock may only refute.
  The defaults (`CALIB_CHECKS`) use the mean NIS over the last `calib_check_s`:
  - `baro_agrees`: barometer against the filter's altitude. Independent, so it can confirm.
  - `rx_clock_consistent`: GNSS time against our clock model. Refutes only.
  - `towers_consistent`: tower pseudorange innovations. Refutes only. Tower time follows GNSS
    time, so the tower clocks never confirm GNSS.
  With no barometer (or other confirming check) the clocks never calibrate.
  - `towers_agree_with_gnss`: the spoof detector's statistic (below). Refutes only.
  More trust tests (#82) are added by appending a predicate to `calib_checks`.

Rollback (calibrated model only). A slow spoof can still pass the gate, so the filter keeps a
ring buffer of clock snapshots (mean and covariance of every clock block, about 1 Hz). It also
tracks the current suspicious episode: it starts at the first sign of trouble (a gate check
refutes GNSS, GNSS position or time is rejected, or the spoof detector's statistic is over its
threshold) and ends after `calib_check_s` without one, the memory of the windowed checks. When
GNSS is flagged (exclusion or time alarm) for `calib_alarm_hold_s`, and the clocks have
calibrated since the last rollback:
- The rollback reaches `calib_rollback_margin_s` before the start of the episode (or of the
  alarm, if that is earlier), and never further back than `calib_rollback_s`. Clean calibration
  from before the episode is kept; a fixed reach would throw it away when the alarm is quick.
- Each clock block that existed at that snapshot is restored from it and carried to now on the
  coast model: the mean moves by the learned drift and the covariance grows by the tower
  oscillator noise. Everything learned after the snapshot is discarded.
- A clock block first seen after that snapshot goes back to its first-sight prior (its mean is
  kept, its covariance is reset): everything it knows was learned after the snapshot.
- Cross-covariance: zeroed between the clocks and the other states (position, velocity,
  receiver clock), and those other states keep their covariance. The restored clocks become an
  independent prior, the same assumption a clock makes at first sight (`_augment`). Why:
  - The filter's cross terms describe today's clocks, which are being discarded, and the
    snapshot's describe the other states as they were a rollback ago. Neither is right now.
  - The restored clocks depend only on measurements from before the snapshot. Today's
    position and velocity have been re-fixed since by the GNSS or tower updates after it, so
    the correlation left is small. It is not zero: this is an approximation.
  - P stays symmetric and positive semidefinite: it is block diagonal with PSD blocks.
  - The bound that holds for any correlation, covariance intersection (both blocks doubled),
    was tried and rejected: doubling the position covariance just as GNSS is flagged makes the
    flagged GNSS easier to accept again, and misleading epochs rose on meaconing and spoof-ramp
    (numbers in PR #102).
- The snapshot buffer restarts from the restored state, so a later alarm never reaches back
  past the rollback into the discarded history.

Spoof detector (calibrated model only, #83). Calibrated tower clocks hold still, so towers that
disagree with the GNSS-steered position are evidence against GNSS, never for it. ADR-0024: tower
time can't confirm GNSS; differences between towers, their geometry, can refute it.
- Statistic: over the last `spoof_window_s`, the tower innovations taken while GNSS steers the
  position are fitted (weighted least squares on their line-of-sight rows) to a common
  horizontal position offset plus one common clock term per builder. The clock term is tower
  time (our clock, a builder's timing), which counts neither way; the offset's chi-square value
  (2 dof) is the statistic. Each site is left out in turn and the smallest value kept, so one
  faulty tower or site clock can't raise it. No opinion (None) with fewer than
  `SPOOF_MIN_SITES` sites, or when the towers disagree among themselves: the fit's residual
  over its 99.9 % chi-square bound.
- Tower faults: a site the filter keeps rejecting for `calib_check_s` while GNSS is trusted and
  the statistic is under its threshold (a jump, a badly learned clock) is left out until it is
  accepted again.
- Arming: the statistic's mean over quiet windows (GNSS trusted, no suspicious episode) is
  learned. The detector is armed after `spoof_learn_s` of it, and only while that mean is no
  larger than an honest chi-square's (2): towers whose errors run larger than their model says
  (unmodelled multipath, our clock in the towers) are not fit to refute GNSS.
- Threshold: the chi-square quantile for `spoof_p` per test (TBC), held for `spoof_persist_s`
  (TBC). Over the threshold at all is a sign of trouble (it closes the calibration gate through
  `towers_agree_with_gnss`); held, it raises the alarm.
- Alarm: `spoof_alarm` is True, the estimate carries `spoof_suspected` (and `gnss_excluded`),
  GNSS position is not used, and the clocks roll back. GNSS time keeps its own test. The alarm
  clears once GNSS position has agreed with the tower-steered estimate (mean NIS within its
  99.9 % bound over `spoof_window_s`) for `spoof_clear_s`. `spoof_alarms` lists when each was
  raised. This is the output for integrity (#82).

GNSS position and GNSS time are tracked separately for health, so rejecting one is never hidden
by accepting the other at the same instant.

Hostile beacon (`hostile`, off by default, #93, ADR-0025 Proposed): a located jammer's received
power (`rssi` records with `meta.hostile`) as a low-trust coarse range, behind a promotion gate
and a weight cap (`nav/hostile.py`). Off, those records are dropped before any prediction, so the
output is exactly as without them. Its health key is `hostile:<emitter>`, never `gnss`.
Jump guard (#184, `pnt.integrity.jump_guard`; opt-in: `jump_guard=JumpGuard` turns it on, as in
`ekf-guard`, `ekf-imu-guard` and `ekf-calibrated-guard`; ADR-0038). Without it the
gate rejects a jumped GNSS fix only until the coasting covariance has grown enough to accept it.
With it, a fix that jumps away from both the GNSS stream's own track and the filter, while GNSS
steers the position, is refused, with the fixes after it, until the stream steps back. Until it
latches it changes nothing, so a run without such a jump is unchanged.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

import numpy as np

from pnt.core.frames import emitter_enu
from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.jump_guard import JumpGuard
from pnt.integrity.protection import hpl, vpl
from pnt.nav.baseline import CHI2_999
from pnt.nav.hostile import BeaconParams, Beacons
from pnt.nav.imu import ImuMotion

C = 299_792_458.0
GNSS_TIME = "gnss:time"  # health key for GNSS time, separate from GNSS position ("gnss")
POS, VEL, CLK, DRIFT = slice(0, 3), slice(3, 6), 6, 7
N_CORE = 8
CLOCK_MODELS = ("independent", "calibrated")
MOTIONS = ("cv", "imu")
SNAPSHOT_NS = 1_000_000_000  # clock snapshots for rollback, about 1 Hz
CHECK_MIN_SAMPLES = 5  # a windowed check with fewer innovations has no opinion
SPOOF_MIN_SITES = 4  # every site left out still leaves 3: enough for 2 offsets and a clock


def CHI2_999_MEAN(dof: int) -> float:  # noqa: N802
    """99.9 % bound on a mean NIS per degree of freedom over `dof` dof (Wilson-Hilferty)."""
    z = 3.090232306167813  # standard normal 99.9 % quantile
    a = 2.0 / (9.0 * dof)
    return (1.0 - a + z * np.sqrt(a)) ** 3


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
        rx_clock_drift_sigma: float = 150.0,  # m/s (0.5 ppm): a dongle's first-sight drift (TBC)
        rx_clock_wander: float = 0.5,  # m/s per sqrt(s): dongle frequency wander (TBC, day-1)
        tower_h0: float = 2.6e-22,  # s: tower oscillator, coasting (Shamaei 2018, TBC)
        tower_h_2: float = 4e-26,  # 1/s: tower oscillator, coasting (Shamaei 2018, TBC)
        calib_q_offset: float = 0.2,  # m/sqrt(s): extra offset noise while calibrating (TBC)
        calib_q_drift: float = 0.01,  # m/s/sqrt(s): extra drift noise while calibrating (TBC)
        init_tower_drift_sigma: float = 1.0,  # m/s (3 ppb): a tower clock's drift (TBC)
        init_residual_sigma: tuple[float, float] = (300.0, 0.1),  # m, m/s: site vs builder (TBC)
        calib_gate_s: float = 30.0,  # s: GNSS trusted this long before calibrating (TBC)
        calib_check_s: float = 10.0,  # s: window of the gate's NIS checks (TBC)
        calib_nis_max: float = 3.0,  # mean NIS above which baro or GNSS time disagrees (TBC)
        calib_tower_nis_max: float = 3.0,  # mean NIS above which the towers disagree (TBC)
        calib_checks: Sequence[Callable[[EKF], bool | None]] | None = None,  # CALIB_CHECKS
        calib_rollback_s: float | None = 300.0,  # s: longest rollback reach; None: off (TBC)
        calib_rollback_margin_s: float = 10.0,  # s: rollback reaches this far before trouble (TBC)
        calib_alarm_hold_s: float = 1.0,  # s: alarm held this long rolls back (TBC)
        spoof_window_s: float = 10.0,  # s: window of the towers-vs-GNSS test (TBC)
        spoof_p: float | None = 1e-3,  # P(one test over threshold | no spoof); None: off (TBC)
        spoof_persist_s: float = 3.0,  # s: exceedance held this long raises the alarm (TBC)
        spoof_clear_s: float = 30.0,  # s: GNSS consistent this long clears the alarm (TBC)
        spoof_learn_s: float = 60.0,  # s: null scale learned this long before arming (TBC)
        multipath_ratio: float = 0.0,  # tower multipath sigma / reported sigma; 0: off (TBC)
        multipath_tau_s: float = 30.0,  # s: tower multipath correlation time (TBC)
        tower_position_sigma_m: float = 0.0,  # m per horizontal axis: told position; 0: off (TBC)
        seed_site_drift: bool = False,  # seed a new site's drift from the calibrated sites
        site_drift_floor: float = 0.1,  # m/s: least drift sigma of a seeded new site (TBC)
        motion: str = "cv",  # or "imu" (stage 2, nav/imu.py)
        imu: Mapping | None = None,  # ImuMotion options when motion="imu"
        hostile: Mapping | None = None,  # BeaconParams options: use hostile beacons (#93)
        jump_guard: Callable[[], JumpGuard] | None = None,  # JumpGuard: refuse GNSS jumps (#184)
    ):
        if clock_model not in CLOCK_MODELS:
            raise ValueError(f"clock_model must be one of {CLOCK_MODELS}, not {clock_model!r}")
        if motion not in MOTIONS:
            raise ValueError(f"motion must be one of {MOTIONS}, not {motion!r}")
        self.imu = ImuMotion(**(imu or {})) if motion == "imu" else None
        self.hostile = None if hostile is None else Beacons(BeaconParams(**hostile), alert_limit_m)
        self.n_core = N_CORE  # states before the first clock block (IMU states included)
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
        self.rx_idx: dict[str, int] = {}  # meta.rx_clock -> index of its (offset, drift) block
        self.rx_prior = (1.0, rx_clock_drift_sigma)  # m, m/s
        self.s_rx = (0.1, rx_clock_wander**2)  # m^2/s (TBC), m^2/s^3
        self.s_tower = (C**2 * tower_h0 / 2.0, C**2 * 2.0 * np.pi**2 * tower_h_2)  # m^2/s, m^2/s^3
        self.s_calib = (calib_q_offset**2, calib_q_drift**2)
        self.init_tower_drift_sigma = init_tower_drift_sigma
        self.init_residual_sigma = init_residual_sigma
        self.calib_gate_ns = int(calib_gate_s * 1e9)
        self.calib_check_ns = int(calib_check_s * 1e9)
        self.calib_nis_max, self.calib_tower_nis_max = calib_nis_max, calib_tower_nis_max
        self.calib_checks = tuple(CALIB_CHECKS if calib_checks is None else calib_checks)
        self.rollback_ns = None if calib_rollback_s is None else int(calib_rollback_s * 1e9)
        self.margin_ns = int(calib_rollback_margin_s * 1e9)
        self.alarm_hold_ns = int(calib_alarm_hold_s * 1e9)
        self.spoof_window_ns = int(spoof_window_s * 1e9)
        self.detect_spoof = spoof_p is not None
        self.spoof_threshold = -2.0 * np.log(spoof_p or 1.0)  # chi-square, 2 dof: P(T > thr) = p
        self.spoof_persist_ns = int(spoof_persist_s * 1e9)
        self.spoof_clear_ns = int(spoof_clear_s * 1e9)
        self.spoof_learn_ns = int(spoof_learn_s * 1e9)
        self.x: np.ndarray | None = None
        self.P: np.ndarray | None = None
        self.t_ns: int | None = None
        self.clock_idx: dict[str, int] = {}  # clock block ("site:..", "builder:..") -> index
        self.calibrating = False  # tower clocks calibrating (gate open) or coasting
        self.rollbacks: list[tuple[int, int]] = []  # (alarm start, snapshot time) per rollback
        self._clock_prior: dict[str, tuple[float, float]] = {}  # block -> first-sight sigmas
        self._trusted_since: int | None = None
        self._alarm_since: int | None = None
        self.trouble_since: int | None = None  # first sign of trouble in the current episode
        self._trouble_last: int | None = None
        self._learned = False  # calibrated since the last rollback
        self._snaps: deque[tuple[int, np.ndarray, np.ndarray]] = deque()  # (t, x_c, P_cc)
        self._nis: dict[str, deque[tuple[int, float, int]]] = {}  # check -> (t, NIS, dof)
        self._nis_mean: dict[str, tuple] = {}  # check -> (first, last, count, mean) cache
        self._last_nis = (0.0, 0)
        self._emitter_pos: dict[str, np.ndarray | None] = {}
        # Spoof detector (calibrated model, #83): see the module docstring
        self.spoof_alarm = False  # GNSS excluded because the towers refute it
        self.spoof_alarms: list[int] = []  # time each alarm was raised
        self.spoof_stat: float | None = None  # latest test statistic, None: no opinion
        self._tower_innov: deque[tuple[int, str, np.ndarray, float, float]] = deque()
        self._exceed_since: int | None = None
        self._gnss_nis: deque[tuple[int, float, int]] = deque()  # while alarmed, for recovery
        self._clear_since: int | None = None
        self._last_innov: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._null = [0.0, 0, None]  # sum and count of quiet statistics, first quiet time
        self._site_bad: dict[str, tuple[int | None, bool]] = {}  # (rejected since, faulty)
        self.last_used: dict[str, int] = {}
        self.last_rejected: dict[str, int] = {}
        # Honest tower error model (see the module docstring): per-emitter multipath and
        # per-site told-position error states, added on first sight
        self.multipath_ratio, self.multipath_tau_s = multipath_ratio, multipath_tau_s
        self.tower_position_sigma_m = tower_position_sigma_m
        self.seed_site_drift, self.site_drift_floor = seed_site_drift, site_drift_floor
        self.multipath_idx: dict[str, int] = {}  # emitter -> its multipath state
        self.multipath_sigma: dict[int, float] = {}  # state -> steady-state sigma (m)
        self.position_idx: dict[str, tuple] = {}  # site -> (told-position error state, los0)
        self.bearing_bias_idx: dict[str, int] = {}  # station -> its constant bearing bias state
        self.jump = jump_guard() if jump_guard is not None else None  # #184, integrity/jump_guard

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
        if self.imu is not None:
            self.imu.augment(self, POS, VEL)
        self.n_core = len(self.x)

    def _append_states(self, mean, sigma) -> int:
        """Add independent states with the given means and sigmas; returns the first index."""
        n, w = len(self.x), len(mean)
        self.x = np.append(self.x, mean)
        P = np.zeros((n + w, n + w))
        P[:n, :n] = self.P
        P[n:, n:] = np.diag(np.square(sigma))
        self.P = P
        return n

    def _augment(
        self, key: str, value: float, sigma: tuple[float, float], drift: float = 0.0, prior=None
    ) -> int:
        """Add a clock block (offset, and drift if calibrated) with the given initial sigmas.
        `prior` (default `sigma`) is what a rollback resets it to if it is first seen after the
        snapshot: a seed taken from other sites then may itself have learned the spoof."""
        w = self.width
        n = self._append_states([value, drift][:w], sigma[:w])
        self.clock_idx[key] = n
        self._clock_prior[key] = tuple(float(v) for v in (prior or sigma))
        return n

    def site_drift_prior(self) -> tuple[float, float]:
        """Drift prior (mean, sigma) for a new ungrouped site clock (calibrated model). Seeded from
        the sites already calibrated (drift sigma under half its prior): their mean drift, with
        their spread and their own uncertainty, at least `site_drift_floor` and at most the wide
        `init_tower_drift_sigma`. With fewer than two such sites: (0, init_tower_drift_sigma).
        A drift common to every site (our own clock's, a builder's) then carries over to the new
        site instead of being rejected as a fault."""
        wide = self.init_tower_drift_sigma
        d, v = [], []
        for key, i in self.clock_idx.items():
            if key.startswith("site:") and self.P[i + 1, i + 1] < (wide / 2) ** 2:
                d.append(self.x[i + 1])
                v.append(self.P[i + 1, i + 1])
        if len(d) < 2:
            return 0.0, wide
        sigma = np.sqrt(np.var(d, ddof=1) + np.mean(v))
        return float(np.mean(d)), float(np.clip(sigma, self.site_drift_floor, wide))

    def tower_states(
        self, emitter: str, sigma: float, los: np.ndarray
    ) -> tuple[int | None, tuple[int, np.ndarray] | None]:
        """This emitter's multipath state, and its site's told-position error states with the
        horizontal line of sight they were added at, adding them on first sight (`los`: the line
        of sight now, tower to receiver); None where that part of the model is off.
        - Multipath: a first-order Gauss-Markov state per emitter, steady-state sigma
          `multipath_ratio` times the reported `sigma`, time constant `multipath_tau_s`.
        - Told position: a constant (east, north) error per site, prior `tower_position_sigma_m`
          per axis, shared by the site's sectors. It moves the range by -(los - los0) . error:
          the part along the first line of sight, los0, is a constant range bias that the site's
          clock offset already carries. Modelling it twice would let any common position offset
          (a spoof dragging GNSS) be explained as every tower having moved."""
        mp = pos = None
        if self.multipath_ratio > 0:
            mp = self.multipath_idx.get(emitter)
            if mp is None:
                s = self.multipath_ratio * sigma
                mp = self.multipath_idx[emitter] = self._append_states([0.0], [s])
                self.multipath_sigma[mp] = s
        if self.tower_position_sigma_m > 0:
            site = self.sites.get(emitter, emitter)
            pos = self.position_idx.get(site)
            if pos is None:
                s = self.tower_position_sigma_m
                i = self._append_states([0.0, 0.0], [s, s])
                pos = self.position_idx[site] = (i, np.array(los[:2], float))
        return mp, pos

    def rx_clock_block(self, name: str) -> int:
        """Index of the (offset, drift) block of the radio clock `name`, added on first sight."""
        if name not in self.rx_idx:
            self.rx_idx[name] = self._append_states([0.0, 0.0], self.rx_prior)
        return self.rx_idx[name]

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
            if builder is None and self.calibrated and self.seed_site_drift:
                drift, sigma = self.site_drift_prior()
                self._augment(skey, residual, (wide[0], sigma), drift, prior=wide)
            elif builder is None:
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

    def gnss_flagged(self) -> bool:
        """GNSS position excluded or GNSS time alarmed: the alarms that trigger a rollback."""
        never = -(10**18)
        return self.last_rejected.get("gnss", never) > self.last_used.get(
            "gnss", never
        ) or self.last_rejected.get(GNSS_TIME, never) > self.last_used.get(GNSS_TIME, never)

    def calibration_allowed(self) -> bool:
        """The calibration gate: GNSS trusted for `calib_gate_s` and the checks agree."""
        votes = [check(self) for check in self.calib_checks]
        self._note_trouble(False in votes)
        if not self.gnss_trusted():
            self._trusted_since = None
            return False
        if self._trusted_since is None:
            self._trusted_since = self.t_ns
        if self.t_ns - self._trusted_since < self.calib_gate_ns:
            return False
        return True in votes and False not in votes

    def _note_trouble(self, sign: bool) -> None:
        """Track the current suspicious episode: it starts at the first sign of trouble (a check
        refutes GNSS, or GNSS is rejected) and ends after `calib_check_s` without one, the memory
        of the windowed checks."""
        if sign:
            if self.trouble_since is None:
                self.trouble_since = self.t_ns
            self._trouble_last = self.t_ns
        elif self.trouble_since is not None:
            if self.t_ns - self._trouble_last > self.calib_check_ns:
                self.trouble_since = self._trouble_last = None

    def windowed_nis(self, check: str) -> float | None:
        """Mean NIS per degree of freedom of one check's innovations over `calib_check_s`, or
        None with fewer than CHECK_MIN_SAMPLES of them."""
        w = self._nis.get(check)
        if w is None:
            return None
        while w and w[0][0] < self.t_ns - self.calib_check_ns:
            w.popleft()
        if len(w) < CHECK_MIN_SAMPLES:
            return None
        cached = self._nis_mean.get(check)  # same window as last time: same mean
        if cached and cached[0] is w[0] and cached[1] is w[-1] and cached[2] == len(w):
            return cached[3]
        mean = sum(n for _, n, _ in w) / sum(d for _, _, d in w)
        self._nis_mean[check] = (w[0], w[-1], len(w), mean)
        return mean

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
        nav = None if self.imu is None else self.imu.propagate(self, t_ns, F, Q)
        if self.calibrated:
            self.calibrating = self.calibration_allowed()
            self._learned |= self.calibrating
        self._tower_process(F, Q, dt, self.calibrating)
        if self.hostile is not None:
            self.hostile.process_noise(Q, dt)
        self.x = F @ self.x
        if nav is not None:
            self.x[nav[0]] = nav[1]  # the nonlinear mean of position, velocity and attitude
        self.P = F @ self.P @ F.T + Q
        self.t_ns = t_ns
        if self.calibrated and self.rollback_ns is not None:
            self._snapshot()

    def _tower_process(self, F, Q, dt: float, calibrating: bool, base: int = 0) -> None:
        """Fill in the tower states' transition and process noise over dt: the clock blocks
        (`calibrating` adds the calibration noise), and the multipath states (Gauss-Markov).
        Told-position errors are constant. `base` is subtracted from the state indices, for a
        matrix that starts at that state (rollback's clock-and-tower block)."""
        if self.calibrated:
            s_off, s_drift = self.s_tower
            if calibrating:
                s_off, s_drift = s_off + self.s_calib[0], s_drift + self.s_calib[1]
            q = _two_state_q(s_off, s_drift, dt)
            for i in self.clock_idx.values():
                F[i - base, i - base + 1] = dt
                Q[i - base : i - base + 2, i - base : i - base + 2] = q
        else:
            for i in self.clock_idx.values():
                Q[i - base, i - base] = self.q_emitter**2 * dt
        if self.multipath_sigma:
            phi = np.exp(-dt / self.multipath_tau_s)
            for i, s in self.multipath_sigma.items():
                F[i - base, i - base] = phi
                Q[i - base, i - base] = s**2 * (1.0 - phi**2)
        for i in self.rx_idx.values():
            F[i - base, i - base + 1] = dt
            Q[i - base : i - base + 2, i - base : i - base + 2] = _two_state_q(*self.s_rx, dt)

    # --- rollback (calibrated model) -----------------------------------------------------------
    def _snapshot(self) -> None:
        if self._snaps and self.t_ns - self._snaps[-1][0] < SNAPSHOT_NS:
            return
        c = self.n_core
        self._snaps.append((self.t_ns, self.x[c:].copy(), self.P[c:, c:].copy()))
        # Keep the newest snapshot old enough for the reach of an alarm now: the margin before
        # the current episode (or before a hold ago, if there is none), at most `calib_rollback_s`
        start = self.trouble_since
        if start is None:
            start = self.t_ns - self.alarm_hold_ns
        horizon = max(start - self.margin_ns, self.t_ns - self.rollback_ns) - SNAPSHOT_NS
        while len(self._snaps) > 1 and self._snaps[1][0] <= horizon:
            self._snaps.popleft()

    def _watch_alarm(self) -> None:
        if not self.gnss_flagged():
            self._alarm_since = None
            return
        if self._alarm_since is None:
            self._alarm_since = self.t_ns
        if self._learned and self.t_ns - self._alarm_since >= self.alarm_hold_ns:
            self.rollback(self._alarm_since)

    def rollback(self, alarm_ns: int) -> None:
        """Restore the clocks from the snapshot `calib_rollback_margin_s` before the first sign of
        trouble in the current episode, or before `alarm_ns` if that is earlier (the oldest kept,
        if none is that old). See the module docstring for the covariance. Public so that a spoof
        alarm from another detector (#82) can call it too."""
        if not self._snaps:
            return
        start = alarm_ns if self.trouble_since is None else min(alarm_ns, self.trouble_since)
        target = start - self.margin_ns
        t_s, xc, Pcc = self._snaps[0]
        for snap in self._snaps:
            if snap[0] > target:
                break
            t_s, xc, Pcc = snap
        dt = (self.t_ns - t_s) / 1e9
        k = len(xc)
        c = self.n_core
        m = len(self.x) - c
        F, Q = np.eye(m), np.zeros((m, m))
        self._tower_process(F, Q, dt, calibrating=False, base=c)  # the coast model
        F, Q = F[:k, :k], Q[:k, :k]
        old = slice(c, c + k)
        P = np.zeros_like(self.P)  # cross terms zeroed: see the module docstring
        P[:c, :c] = self.P[:c, :c]
        P[old, old] = F @ Pcc @ F.T + Q
        for key, i in self.clock_idx.items():
            if i >= c + k:  # first seen after the snapshot: back to its first-sight prior
                P[i : i + 2, i : i + 2] = np.diag(np.square(self._clock_prior[key]))
        for i in self.rx_idx.values():
            if i >= c + k:
                P[i : i + 2, i : i + 2] = np.diag(np.square(self.rx_prior))
        for i, s in self.multipath_sigma.items():  # the same for the tower error states
            if i >= c + k:
                P[i, i] = s**2
        for i, _ in self.position_idx.values():
            if i >= c + k:
                P[i, i] = P[i + 1, i + 1] = self.tower_position_sigma_m**2
        for i in self.bearing_bias_idx.values():
            if i >= c + k:
                P[i, i] = BEARING_BIAS_SIGMA_RAD**2
        self.x[old] = F @ xc
        self.P = (P + P.T) / 2
        self.rollbacks.append((alarm_ns, t_s))
        self._learned = False
        self._snaps.clear()
        self._snapshot()

    def _update(self, key: str, t_ns: int, y, H, R, gate: bool = True) -> bool:
        y = np.atleast_1d(y)
        S = H @ self.P @ H.T + R
        S_inv = 1.0 / S if S.shape == (1, 1) else np.linalg.inv(S)
        nis = float(y @ S_inv @ y)
        self._last_nis = (nis, len(y))
        self._last_innov = (y, S, H)
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
        if m.kind == "accel_gyro":  # IMU samples drive the prediction, never an update
            if self.imu is not None:
                self.imu.add(self, m)
            return
        if self.x is None:
            if m.kind == "position_enu":
                self._init(m)
            return
        model = MODELS.get(m.kind)
        if model is None:
            return  # not modelled yet
        if m.kind == "rssi" and (self.hostile is None or not m.meta.get("hostile")):
            return  # only a hostile beacon's power is modelled, and only when asked for
        self.predict(m.t_ns)
        out = model(self, m)
        if out is None:
            return
        y, H, R, gate = out
        key = GNSS_TIME if (m.source, m.kind) == ("gnss", "time") else m.source
        if m.kind == "rssi":
            key = f"hostile:{m.emitter}"  # shown apart from GNSS (ADR-0025 guardrail 5)
        if self.spoof_alarm and key == "gnss":
            self._excluded_gnss(key, m.t_ns, y, H, R)
            return
        verdict = "gate"  # or, for a GNSS position jump (#184): "refuse" or "readmit"
        if key == "gnss" and self.jump is not None:
            verdict = self.jump.verdict(self, m.t_ns, y, H, R)
        if verdict == "refuse":  # a detected jump not yet undone: as a gate rejection
            used = False
            self.last_rejected[key] = m.t_ns
        else:  # "readmit": GNSS is back on its own pre-jump track, so the gate is skipped
            used = self._update(key, m.t_ns, y, H, R, gate and verdict == "gate")
        if self.calibrated:
            if key in ("gnss", GNSS_TIME) and not used:
                self._note_trouble(True)  # an alarm precursor: GNSS rejected
            self._record(m, key, gate)
            if m.kind == "pseudorange" and gate and self.detect_spoof:
                self._spoof_test(m, used)
            if self.rollback_ns is not None:
                self._watch_alarm()

    # --- spoof detector (calibrated model, #83) ------------------------------------------------
    def _spoof_test(self, m: Measurement, used: bool) -> None:
        """Add this tower innovation to the window and run the towers-vs-GNSS test."""
        never = -(10**18)
        site = self.sites.get(m.emitter, m.emitter)
        if self.gnss_trusted() and self._exceed_since is None:
            # A site the filter keeps rejecting for calib_check_s while GNSS is trusted and the
            # towers as a whole don't refute it has a tower fault (a jump, a badly learned
            # clock): it is no evidence about GNSS until accepted again. Frozen while the
            # statistic is over its threshold, when a spoof makes good towers look bad.
            since = self._site_bad.get(site, (None, False))[0]
            since = None if used else (self.t_ns if since is None else since)
            bad = since is not None and self.t_ns - since >= self.calib_check_ns
            self._site_bad[site] = (since, bad)
        if self.t_ns - self.last_used.get("gnss", never) > self.gnss_timeout_ns:
            self._tower_innov.clear()  # only innovations taken while GNSS steers the position
            self.spoof_stat = self._exceed_since = None
            return
        if self._site_bad.get(site, (None, False))[1]:
            return
        y, S, H = self._last_innov
        self._tower_innov.append((self.t_ns, site, H[0, :2].copy(), float(y[0]), float(S[0, 0])))
        while self._tower_innov[0][0] < self.t_ns - self.spoof_window_ns:
            self._tower_innov.popleft()
        raw = self.towers_vs_gnss()
        if raw is not None and self.gnss_trusted() and self.trouble_since is None:
            self._null[0] += raw  # quiet: learn the statistic's null scale
            self._null[1] += 1
            if self._null[2] is None:
                self._null[2] = self.t_ns
        armed = self._null[2] is not None and self.t_ns - self._null[2] >= self.spoof_learn_ns
        armed = armed and self.spoof_scale() <= 1.0  # the towers behave as their model says
        self.spoof_stat = raw if armed else None
        if self.spoof_stat is None or self.spoof_stat <= self.spoof_threshold:
            self._exceed_since = None
            return
        self._note_trouble(True)  # an alarm precursor
        if self._exceed_since is None:
            self._exceed_since = self.t_ns
        if self.t_ns - self._exceed_since >= self.spoof_persist_ns:
            self._raise_spoof_alarm()

    def spoof_scale(self) -> float:
        """How much larger the statistic runs with no spoof than an honest chi-square (mean 2)
        would: its mean over quiet windows, over 2, and never below 1. Unmodelled tower errors
        (multipath correlated over tens of seconds, our clock in the towers) inflate it."""
        total, n, _ = self._null
        return max(1.0, total / n / 2.0) if n else 1.0

    def towers_vs_gnss(self) -> float | None:
        """The test statistic: the horizontal position offset that the windowed tower innovations
        point to, as a chi-square value with 2 dof. Weighted least squares on the line-of-sight
        rows, with one common clock term per builder (or one for all ungrouped sites) as a
        nuisance: a shift common to the towers (our own clock, a builder's timing) is tower time,
        which never counts for or against GNSS (ADR-0024); only the differences between towers,
        their geometry, do. Each site in turn is left out and the smallest value kept, so one
        faulty tower or site clock can't raise it alone. None (no opinion) with fewer than
        SPOOF_MIN_SITES sites, or when the sites left can't fix the offset."""
        per_site: dict[str, list] = {}
        rss = 0.0
        for _, site, u, y, s in self._tower_innov:
            h = np.array([u[0], u[1], 1.0])
            acc = per_site.setdefault(site, [np.zeros((3, 3)), np.zeros(3)])
            acc[0] += np.outer(h, h) / s
            acc[1] += h * (y / s)
            rss += y * y / s
        if len(per_site) < SPOOF_MIN_SITES:
            return None
        groups = sorted({self.builders.get(site, "") for site in per_site})
        k = 2 + len(groups)
        N, b = np.zeros((k, k)), np.zeros(k)
        cols = {}
        for site, (n_s, b_s) in per_site.items():
            idx = [0, 1, 2 + groups.index(self.builders.get(site, ""))]
            cols[site] = np.ix_(idx, idx), idx
            N[cols[site][0]] += n_s
            b[idx] += b_s
        # The towers must first agree among themselves: after the offset and clock fit, their
        # residual is within its 99.9 % chi-square bound. Otherwise they disagree with each
        # other (a tower fault, unmodelled errors) and hold no opinion about GNSS.
        dof = len(self._tower_innov) - k
        w = np.linalg.eigvalsh(N)
        if dof < 1 or w[0] <= 1e-9 * w[-1]:
            return None
        if (rss - b @ np.linalg.solve(N, b)) / dof > CHI2_999_MEAN(dof):
            return None
        stat = np.inf
        for site, (n_s, b_s) in per_site.items():
            N_o, b_o = N.copy(), b.copy()
            N_o[cols[site][0]] -= n_s
            b_o[cols[site][1]] -= b_s
            w = np.linalg.eigvalsh(N_o)
            if w[0] <= 1e-9 * w[-1]:  # the sites left can't fix the offset and the clocks
                return None
            x = np.linalg.solve(N_o, b_o)
            cov_p = np.linalg.inv(N_o)[:2, :2]
            stat = min(stat, float(x[:2] @ np.linalg.solve(cov_p, x[:2])))
        return stat

    def _raise_spoof_alarm(self) -> None:
        self.spoof_alarm = True
        self.spoof_alarms.append(self.t_ns)
        self.last_rejected["gnss"] = self.t_ns  # GNSS excluded from now
        self._tower_innov.clear()
        self._gnss_nis.clear()
        self.spoof_stat = self._exceed_since = self._clear_since = None

    def _excluded_gnss(self, key: str, t_ns: int, y, H, R) -> None:
        """GNSS position while the spoof alarm holds: never used. (GNSS time keeps its own test
        against our clock: the towers do not observe our clock unless `pseudorange_receiver_clock`
        is on, so they hold no evidence about GNSS time.) The alarm clears once GNSS position has
        agreed with the tower-steered estimate (mean NIS within its chi-square bound) for
        `spoof_clear_s`."""
        self.last_rejected[key] = t_ns
        y = np.atleast_1d(y)
        nis = float(y @ np.linalg.solve(H @ self.P @ H.T + R, y))
        w = self._gnss_nis
        w.append((t_ns, nis, len(y)))
        while w[0][0] < t_ns - self.spoof_window_ns:
            w.popleft()
        dof = sum(d for _, _, d in w)
        full = t_ns - w[0][0] >= self.spoof_window_ns - SNAPSHOT_NS
        if not full or sum(n for _, n, _ in w) > CHI2_999_MEAN(dof) * dof:
            self._clear_since = None
            return
        if self._clear_since is None:
            self._clear_since = t_ns
        if t_ns - self._clear_since >= self.spoof_clear_ns:
            self.spoof_alarm = False
            self._clear_since = None

    def _record(self, m: Measurement, key: str, gated: bool) -> None:
        """Log the NIS of the innovations the gate's default checks read."""
        if m.kind == "altitude" and m.source != "gnss":
            check = "baro"
        elif key == GNSS_TIME:
            check = "rx_clock"
        elif m.kind == "pseudorange" and gated:  # not first sight: that NIS says nothing
            check = "towers"
        else:
            return
        w = self._nis.setdefault(check, deque())
        w.append((m.t_ns, *self._last_nis))
        while w[0][0] < m.t_ns - self.calib_check_ns:
            w.popleft()

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
        if self.spoof_alarm:
            flags.append("spoof_suspected")  # the towers refute GNSS (#83)
        if self.hostile is not None:
            flags += self.hostile.flags(self.t_ns)
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


# --- calibration gate checks: (ekf) -> True (confirms GNSS), False (refutes), None ------------
def baro_agrees(ekf: EKF) -> bool | None:
    """Barometer against the filter's (GNSS-driven) altitude. Independent of GNSS (ADR-0024), so
    it is the one default check that can confirm."""
    r = ekf.windowed_nis("baro")
    return None if r is None else r <= ekf.calib_nis_max


def rx_clock_consistent(ekf: EKF) -> bool | None:
    """GNSS time against our own clock model. Refutes only: our oscillator is GNSS-disciplined
    while GNSS is available (ADR-0024), so agreement is not independent evidence."""
    r = ekf.windowed_nis("rx_clock")
    return False if r is not None and r > ekf.calib_nis_max else None


def towers_consistent(ekf: EKF) -> bool | None:
    """Tower pseudorange innovations. Refutes only: tower time is GNSS-timed (ADR-0024), so the
    tower clocks never confirm GNSS, but towers that disagree with it are evidence against it."""
    r = ekf.windowed_nis("towers")
    return False if r is not None and r > ekf.calib_tower_nis_max else None


def towers_agree_with_gnss(ekf: EKF) -> bool | None:
    """The spoof detector's statistic over its threshold (before persistence): the towers'
    geometry points to a position offset. Refutes only (ADR-0024)."""
    s = ekf.spoof_stat
    return False if s is not None and s > ekf.spoof_threshold else None


CALIB_CHECKS: tuple[Callable[[EKF], bool | None], ...] = (
    baro_agrees,
    rx_clock_consistent,
    towers_consistent,
    towers_agree_with_gnss,
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
    u = d / r  # line of sight, tower to receiver
    if "site" in m.meta:
        ekf.sites.setdefault(m.emitter, m.meta["site"])
    mp, pos = ekf.tower_states(m.emitter, m.sigma[0], u)
    name = m.meta.get("rx_clock")
    rx_i = CLK if name is None else ekf.rx_clock_block(name)
    use_rx = name is not None or ekf.pr_rx_clock
    rx = ekf.x[rx_i] if use_rx else 0.0
    h = u  # d(range)/d(position)
    if mp is not None:
        rx += ekf.x[mp]  # the residual and the prediction carry the tower error states too
    if pos is not None:
        i, los0 = pos
        err = ekf.x[i : i + 2]
        h_pos = los0 - u[:2]  # d(range)/d(told-position error), less the clock's part
        rx += float(h_pos @ err)
        h = u - err @ (np.eye(3) - np.outer(u, u))[:2] / r  # the line of sight turns
    idx, new = ekf.clock_offsets(m.emitter, m.value[0] - r - rx)
    H = _row(ekf)
    H[0, POS] = h
    if use_rx:
        H[0, rx_i] = 1.0
    if mp is not None:
        H[0, mp] = 1.0
    if pos is not None:
        H[0, i : i + 2] = h_pos
    H[0, idx] = 1.0
    y = m.value[0] - (r + rx + float(np.sum(ekf.x[idx])))
    return y, H, np.diag(np.square(m.sigma)), not new


def _doppler(ekf: EKF, m: Measurement):
    """Range rate (m/s, ICD `doppler`): the rate of the emitter-to-receiver range, plus the clock
    drifts that the matching pseudorange carries.

    - Geometry: u . (v - v_e), with u the line of sight from emitter to receiver and v_e the
      emitter's velocity (`meta.emitter_vel_enu`, a satellite's; zero if absent). Its position is
      read from each record, since a moving emitter's changes.
    - Our clock: the drift of the radio's own block (`meta.rx_clock`), or of `c*dt` when
      `pseudorange_receiver_clock` is on, as in `_pseudorange`.
    - The emitter's clock: its site's drift, when the calibrated model has one learned (a tower
      seen in pseudoranges). A satellite's is not modelled; its records carry none.
    Gated as every update is (`CHI2_999`, one degree of freedom)."""
    moving = "emitter_vel_enu" in m.meta
    e = emitter_enu(m.meta, ekf.origin_llh) if moving else ekf._emitter(m)
    if e is None:
        return None
    v_e = np.asarray(m.meta["emitter_vel_enu"], float) if moving else np.zeros(3)
    d = ekf.x[POS] - e
    r = float(np.linalg.norm(d))
    u = d / r
    name = m.meta.get("rx_clock")
    rx = None  # index of our clock's drift; a new radio's block is added before H is sized
    if name is not None or ekf.pr_rx_clock:
        rx = (CLK if name is None else ekf.rx_clock_block(name)) + 1
    dv = ekf.x[VEL] - v_e
    rate = float(u @ dv)
    H = _row(ekf)
    H[0, VEL] = u
    H[0, POS] = (dv - rate * u) / r  # the line of sight turns as the receiver moves
    if rx is not None:
        rate += ekf.x[rx]
        H[0, rx] = 1.0
    if ekf.calibrated:
        site = ekf.sites.get(m.emitter, m.emitter)
        for key in (f"builder:{ekf.builders.get(site)}", f"site:{site}"):
            if key in ekf.clock_idx:
                i = ekf.clock_idx[key] + 1
                rate += ekf.x[i]
                H[0, i] = 1.0
    return m.value[0] - rate, H, np.diag(np.square(m.sigma)), True


BEARING_MIN_RANGE_M = 100.0  # TBC: closer than this the bearing turns too fast to linearise
BEARING_BIAS_SIGMA_RAD = float(np.deg2rad(1.0))  # TBC: literature, a VOR's site error, 1-sigma


def _bearing(ekf: EKF, m: Measurement):
    """Bearing from a station to us, clockwise from true north (ICD `bearing`, e.g. a VOR
    radial), plus a constant bias state per station (its site error, added on first sight).
    The record's sigma is the white noise only. Horizontal position only; the innovation is
    wrapped to [-pi, pi)."""
    e = ekf._emitter(m)
    if e is None:
        return None
    de, dn = ekf.x[0] - e[0], ekf.x[1] - e[1]
    r2 = de * de + dn * dn
    if r2 < BEARING_MIN_RANGE_M**2:
        return None
    b = ekf.bearing_bias_idx.get(m.emitter)
    if b is None:
        b = ekf.bearing_bias_idx[m.emitter] = ekf._append_states([0.0], [BEARING_BIAS_SIGMA_RAD])
    H = _row(ekf)
    H[0, 0], H[0, 1] = dn / r2, -de / r2  # d(atan2(de, dn)) / d(e, n)
    H[0, b] = 1.0
    y = (m.value[0] - np.arctan2(de, dn) - ekf.x[b] + np.pi) % (2 * np.pi) - np.pi
    return y, H, np.diag(np.square(m.sigma)), True


def _rssi(ekf: EKF, m: Measurement):
    """A hostile beacon's received power (`nav/hostile.py`); `process` passes only those."""
    return ekf.hostile.model(ekf, m)


MODELS: dict[str, Callable] = {
    "position_enu": _position,
    "bearing": _bearing,
    "altitude": _altitude,
    "time": _time,
    "pseudorange": _pseudorange,
    "doppler": _doppler,
    "rssi": _rssi,
}


# The calibrated clock model with our clock in the tower ranges and the tower error model
# (`ekf-calibrated`). Every value is TBC: set to the realistic set's placeholders (ADR-0015), so
# the filter's model matches the environment we pitch; sensitivity to them is in the PR.
CALIBRATED: dict = {
    "clock_model": "calibrated",
    "pseudorange_receiver_clock": True,
    "h0": 8e-18,  # s: our clock's white frequency noise, 2 ns/sqrt(s) (realistic set, TBC)
    "h_2": 2e-23,  # 1/s: our clock's frequency wander; the sim has none (TBC)
    "tower_h0": 8.9e-19,  # s: tower offset random walk, 0.2 m/sqrt(s) (both sets, TBC)
    "multipath_ratio": 1.0,  # multipath sigma = reported sigma (realistic set, TBC)
    "multipath_tau_s": 30.0,  # s (realistic set, TBC)
    "tower_position_sigma_m": 100.0,  # m per axis (realistic set, TBC)
    "seed_site_drift": True,
}


def run_calibrated(
    measurements: Iterable[Measurement], epoch_ns: int = 100_000_000, origin_llh=None, **config
) -> Iterator[Estimate]:
    """`run` with the `CALIBRATED` settings; `config` overrides them."""
    return run(measurements, epoch_ns, origin_llh, **{**CALIBRATED, **config})


def run(
    measurements: Iterable[Measurement],
    epoch_ns: int = 100_000_000,
    origin_llh=None,
    monitor=None,
    **config,
) -> Iterator[Estimate]:
    """Feed time-ordered measurements; yield an Estimate on every epoch boundary.

    `monitor`, if given, is called with the filter and returns an integrity monitor that sees each
    measurement first (`process`) and may rewrite each Estimate (`estimate`), e.g.
    `pnt.integrity.mhss.MHSS`. Without it the output is exactly the filter's."""
    ekf = EKF(origin_llh=origin_llh, **config)
    mon = monitor(ekf) if monitor is not None else None
    next_epoch = None
    for m in measurements:
        if ekf.x is not None:
            if next_epoch is None:
                next_epoch = (ekf.t_ns // epoch_ns + 1) * epoch_ns
            while next_epoch <= m.t_ns:
                ekf.predict(next_epoch)
                yield ekf.estimate() if mon is None else mon.estimate(ekf.estimate())
                next_epoch += epoch_ns
        if mon is not None:
            mon.process(m)
        ekf.process(m)
