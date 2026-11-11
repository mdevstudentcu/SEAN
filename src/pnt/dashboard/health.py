"""Navigation health for the operator panel (#90, P10): what is wrong, in plain words.

Reads only `Estimate` (ICD-measurement), so it works the same on sim, replay and live.

- Flags to sentences: every flag string an estimator or monitor raises today maps to a sentence
  in `FLAGS` (or, for the parameterised MHSS flags, `describe`). An unknown flag is shown raw, so
  a new flag is never hidden.
- Latched alerts: an alert starts when a flag appears or the status turns `unsafe`, and stays on
  the panel after it clears until the operator acknowledges it. Not during start-up
  (`STARTUP_MAX_S`), when every filter's first estimates are flagged.
- RNP/ANP: the alert limit plays the RNP value (as T2 does: 556 m for RNP 0.3), ANP is the 95 %
  horizontal radius from the estimate's own covariance, and HPL is the integrity bound.
- Predicted time-to-alert: the protection level's trend over the last `TREND_S`, a least-squares
  line, extrapolated to the alert limit. "Not on this trend" when it is flat or shrinking.
- Low-trust sources: sources whose `trust` is under `LOW_TRUST`, listed apart from the rest. The
  panel calls them "not in use": the estimators on main set trust to 1 for a source used within
  their timeout and 0 otherwise.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from pnt.core.measurement import Estimate
from pnt.integrity.protection import tpl

# Severity, worst last: caution (amber, expected in GPS-denied flight), warning (amber, a fault
# handled), alarm (red, the operator must act or stop trusting something)
CAUTION, WARNING, ALARM = "caution", "warning", "alarm"
_RANK = {CAUTION: 0, WARNING: 1, ALARM: 2}

# Every flag raised on main (grep `flags.append` in src/pnt/nav and src/pnt/integrity):
#   ekf / baseline: gnss_unavailable, gnss_excluded, time_spoof_suspected, spoof_suspected (#102)
#   ekf-guard and the other `-guard` estimators (ADR-0038): gnss_jump_latched (#206)
#   ekf: gnss_alt_excluded (#227, ADR-0045)
#   ekf-base (#107): base_excluded, tower_fault:<emitter>:<jump m> (in `describe`)
#   ekf-mhss (#108): mhss_alarm:<hypothesis>, mhss_excluded:<hypothesis> (in `describe`)
FLAGS: dict[str, tuple[str, str]] = {
    "gnss_unavailable": (
        CAUTION,
        "GPS not in use: no GPS position accepted recently (signal lost, or rejected). "
        "Navigating on the sources listed as in use.",
    ),
    "gnss_excluded": (
        WARNING,
        "GPS rejected: its position disagrees with the rest of the solution, so it is not used.",
    ),
    "gnss_alt_excluded": (
        CAUTION,
        "GPS height rejected: it disagrees with the barometer, so only GPS's horizontal position "
        "is used. One of the two heights is wrong; the height shown follows the barometer.",
    ),
    "spoof_suspected": (
        ALARM,
        "GPS spoofing suspected: the towers' geometry contradicts the GPS position. GPS position "
        "excluded until it agrees with the towers again.",
    ),
    "gnss_jump_latched": (
        WARNING,
        "GPS position jumped away from its own track and from the solution: GPS is refused until "
        "it steps back (jump guard). A spoofing cue.",
    ),
    "time_spoof_suspected": (
        ALARM,
        "GPS time spoofing suspected: GPS time disagrees with our clock model, so it is not used.",
    ),
    # ekf-mhss with ADS-B traffic (#91, pnt.integrity.adsb)
    "adsb_interference": (
        CAUTION,
        "GPS interference nearby: aircraft around us report degraded GPS quality. Our GPS fault "
        "risk is raised, so the protection level is wider; expect to lose GPS.",
    ),
    "adsb_spoofed_aircraft": (
        WARNING,
        "GPS spoofing nearby: an aircraft's reported track jumped while it kept high quality. Our "
        "GPS fault risk is raised, so the protection level is wider; watch for a GPS spoof.",
    ),
    "base_excluded": (
        WARNING,
        "Reference station excluded: its readings disagree with its surveyed position (moved, or "
        "its clock stepped). Coasting on the tower clocks it measured before.",
    ),
    # ekf-mhss-beacon (#93, ADR-0025): a located jammer used as a low-trust coarse range
    "hostile_beacon": (
        CAUTION,
        "Using a located jammer as a low-trust beacon: its received power gives a coarse range, "
        "capped in weight, and it never narrows the protection level.",
    ),
    "tower_fault": (  # the unparameterised form, as estimates logged before #90 carry it
        WARNING,
        "A tower's clock jumped on its own: that tower's clock estimate was restarted.",
    ),
}
STATUS: dict[str, tuple[str, str]] = {
    "degraded": (
        CAUTION,
        "A source is lost or excluded; the horizontal protection level is still within the limit.",
    ),
    "unsafe": (
        ALARM,
        "Protection level over the alert limit: do not navigate on this position.",
    ),
}
# The panel's own alert (not an estimator flag): the time PL (pnt.integrity.protection.tpl) over
# the time alert limit. The estimators' `status` judges the horizontal PL only.
TIME_OVER = "time_pl_over_limit"
# Below this trust a source is listed apart as low-trust. TBC: no requirement sets it; the
# estimators on main report trust as 0 or 1.
LOW_TRUST = 0.5
# Window of the protection-level trend behind the time-to-alert prediction. TBC: long enough to
# smooth one tower's dropout (1 Hz towers), short enough to follow a GPS loss.
TREND_S = 10.0
# A trend that reaches the limit later than this is reported as no alert ahead: a 10 s line says
# nothing about the next hour. TBC.
TTA_HORIZON_S = 600.0
# Start-up: the first estimates come from the first fix's wide covariance (HPL over the limit, GNSS
# not used yet), so alerts latch only once the filter first reports nominal, or after this long
# if it never does. Causes and status are shown live throughout. TBC.
STARTUP_MAX_S = 30.0
# A condition that clears for no longer than this and returns is the same occurrence. TBC: HPL
# saw-tooths across the limit between 1 Hz tower updates, which would otherwise count each second.
CLEAR_HOLD_S = 2.0
# 95 % radius of a circular 2-D Gaussian in sigmas (sqrt of chi-square 2 dof at 0.95). Applied
# to the major-axis sigma it is a conservative ANP for an elliptical error.
K_ANP95 = 2.4477
C_M_PER_US = 299.792458  # light travel in one microsecond (m): a clock jump in time units
# Confidence colour of the track and the current position (#207, the mentors' heat map): green
# while HPL is under this fraction of the alert limit, amber from there up to the limit, red at
# or over the limit, with no protection level, or with an alarm-severity flag (spoofing, the
# integrity monitor's alarm). TBC: no requirement sets it; 0.8 matches the panel's HPL gauge.
CONF_AMBER_FRACTION = 0.8
CONFIDENT, NEAR_LIMIT, DO_NOT_TRUST = "green", "amber", "red"


def hypothesis_words(h: str) -> str:
    """An MHSS fault hypothesis (pnt.integrity.mhss) in words."""
    if h == "gnss-cm":
        return "GPS and everything derived from it"
    kind, _, name = h.partition(":")
    if kind == "site":
        return f"tower site {_emitter_words(name)}"
    if kind == "builder":
        return f"every tower of network builder {name} (shared timing)"
    if kind == "layer":
        return f"all {name.upper()} measurements"
    if kind == "hostile":
        return f"the hostile beacon (located jammer {name.partition(':')[2] or name})"
    return h


def _emitter_words(emitter: str) -> str:
    source, _, ident = emitter.partition(":")
    return f"{source.upper()} {ident}" if ident else emitter


def describe(flag: str) -> tuple[str, str]:
    """(severity, sentence) for one flag. Unknown flags come back raw, as a caution."""
    if flag in FLAGS:
        return FLAGS[flag]
    kind, _, h = flag.partition(":")
    if kind == "tower_fault" and h:
        return WARNING, _tower_fault_words(h)
    if kind == "mhss_alarm" and h:
        return (
            ALARM,
            f"Integrity monitor: {hypothesis_words(h)} looks faulty, but excluding it would leave "
            "too little to navigate on. Solution kept; the protection level covers it.",
        )
    if kind == "mhss_excluded" and h:
        return (
            WARNING,
            f"Integrity monitor excluded {hypothesis_words(h)}: its solution separated from the "
            "others. Navigating without it.",
        )
    return CAUTION, f"Unrecognised flag: {flag}"


def _tower_fault_words(detail: str) -> str:
    """`<emitter>:<jump m>` (pnt.nav.base_rover) in words."""
    emitter, _, jump = detail.rpartition(":")
    try:
        m = float(jump)
    except ValueError:
        emitter, m = detail, None
    size = "" if m is None else f" {m:+.0f} m ({m / C_M_PER_US:+.2f} µs)"
    return (
        f"Tower {_emitter_words(emitter)}: its clock jumped{size} on its own, seen by the "
        "reference station. The jump cancels against the reference station, so the tower stays "
        "in use; its clock estimate was restarted."
    )


def anp95_m(pos_cov) -> float:
    """Actual navigation performance: a conservative 95 % horizontal radius (m)."""
    ch = np.reshape(pos_cov, (3, 3))[:2, :2]
    return float(K_ANP95 * np.sqrt(max(np.linalg.eigvalsh(ch).max(), 0.0)))


def time_to_limit_s(t_s: np.ndarray, pl: np.ndarray, limit: float) -> float | None:
    """Seconds until a protection level reaches `limit` on its least-squares trend over the
    samples given: 0 if it is already there, None if the trend is flat or falling, would take
    longer than TTA_HORIZON_S, or there are too few samples to fit."""
    if len(pl) and pl[-1] >= limit:
        return 0.0
    if len(pl) < 3 or t_s[-1] - t_s[0] <= 0:
        return None
    dt = t_s - t_s.mean()
    slope = float(dt @ (pl - pl.mean()) / (dt @ dt))  # least-squares line
    if slope <= 0:
        return None
    tta = float((limit - pl[-1]) / slope)
    return tta if tta <= TTA_HORIZON_S else None


def panel_status(est: Estimate, alert_limit_m: float) -> str:
    """The estimate's status, judged against the panel's alert limit. An estimator calls itself
    unsafe against its own built-in limit, so the panel keeps its "degraded" and "nominal" but
    decides "unsafe" here, the same way (HPL over the limit)."""
    if est.hpl_m is None:
        return est.status
    if est.hpl_m > alert_limit_m:
        return "unsafe"
    if est.status == "unsafe":
        return "degraded" if est.flags else "nominal"
    return est.status


def confidence(hpl_m: float | None, flags, alert_limit_m: float) -> str:
    """How far the position can be trusted, as the map colours it: CONFIDENT, NEAR_LIMIT or
    DO_NOT_TRUST (see CONF_AMBER_FRACTION). Position only: the time PL is judged apart."""
    if any(describe(f)[0] == ALARM for f in flags):
        return DO_NOT_TRUST
    if hpl_m is None or not np.isfinite(hpl_m) or hpl_m >= alert_limit_m:
        return DO_NOT_TRUST
    if hpl_m >= CONF_AMBER_FRACTION * alert_limit_m:
        return NEAR_LIMIT
    return CONFIDENT


@dataclass
class Alert:
    id: int
    key: str  # the flag, or "status:unsafe"
    severity: str
    text: str
    since_s: float  # first onset
    last_s: float  # last epoch it was active
    onset_s: float  # latest onset (it can clear and come back before it is acknowledged)
    count: int = 1  # onsets so far
    active: bool = True
    acked: bool = False


class HealthMonitor:
    """Turns each Estimate into the panel's health state. Feed every estimate (not only the
    ones displayed), so an alert between two screen updates still latches."""

    def __init__(self, alert_limit_m: float, time_alert_limit_s: float, t0_ns: int | None = None):
        self.al = alert_limit_m
        self.tal = time_alert_limit_s
        self.t0_ns = t0_ns
        self.alerts: dict[int, Alert] = {}
        self._open: dict[str, int] = {}  # key -> id of its alert, until acknowledged and cleared
        self._next_id = 1
        self._hpl: deque[tuple[float, float]] = deque()
        self._tpl: deque[tuple[float, float]] = deque()
        self.settled = False  # past start-up: alerts latch from here on

    def t_s(self, t_ns: int) -> float:
        if self.t0_ns is None:
            self.t0_ns = t_ns
        return (t_ns - self.t0_ns) / 1e9

    def update(self, est: Estimate) -> dict:
        t = self.t_s(est.t_ns)
        hpl, tpl_s = est.hpl_m, tpl(est.clock_sigma_s)
        current = {f: describe(f) for f in est.flags}
        if tpl_s is not None and tpl_s > self.tal:  # the estimators' status judges position only
            current[TIME_OVER] = (
                ALARM,
                "Time protection level over the time alert limit: do not rely on our time output.",
            )
        status = panel_status(est, self.al)
        if status in STATUS and status != "degraded":
            current[f"status:{status}"] = STATUS[status]
        self.settled = self.settled or status == "nominal" or t >= STARTUP_MAX_S
        for key, aid in list(self._open.items()):
            a = self.alerts[aid]
            if a.acked and not a.active and t - a.last_s > CLEAR_HOLD_S:
                self._forget(key)  # a return from here on is a new occurrence
        for key, (sev, text) in current.items() if self.settled else ():
            aid = self._open.get(key)
            if aid is None:
                aid = self._next_id
                self._next_id += 1
                self.alerts[aid] = Alert(aid, key, sev, text, t, t, t)
                self._open[key] = aid
            a = self.alerts[aid]
            if not a.active and t - a.last_s > CLEAR_HOLD_S:
                a.onset_s, a.count = t, a.count + 1
            a.active, a.last_s = True, t
        for key, aid in list(self._open.items()):
            if key not in current:
                self.alerts[aid].active = False
        tta_h = self._trend(self._hpl, t, hpl, self.al)
        tta_t = self._trend(self._tpl, t, tpl_s, self.tal)
        trust = dict(sorted(est.trust.items()))
        if status in STATUS:
            headline = STATUS[status]
        else:
            headline = (
                "ok",
                "GPS in use, no fault flagged; the horizontal protection level is within the "
                "limit. See Sources for the towers and other sources.",
            )
        return {
            "t_s": t,
            "status": status,
            "confidence": confidence(hpl, est.flags, self.al),
            "headline": headline[1],
            "causes": [
                {"flag": f, "severity": s, "text": txt}
                for f, (s, txt) in sorted(current.items(), key=lambda kv: -_RANK[kv[1][0]])
                if not f.startswith("status:")
            ],
            "alerts": [dict(vars(a)) for a in self.shown()],  # asdict deep-copies: slow
            "settled": self.settled,
            "hpl_m": hpl,
            "anp95_m": anp95_m(est.pos_cov),
            "rnp_m": self.al,
            "tta_hpl_s": tta_h,
            "tpl_s": tpl_s,
            "time_alert_limit_s": self.tal,
            "tta_tpl_s": tta_t,
            "trusted": {s: v for s, v in trust.items() if v >= LOW_TRUST},
            "low_trust": {s: v for s, v in trust.items() if v < LOW_TRUST},
        }

    def _trend(self, window: deque, t: float, pl: float | None, limit: float) -> float | None:
        if pl is None:
            window.clear()
            return None
        window.append((t, pl))
        while window[0][0] < t - TREND_S:
            window.popleft()
        ts, pls = np.array(window).T
        return time_to_limit_s(ts, pls, limit)

    def shown(self) -> list[Alert]:
        """Alerts on the panel: active ones, and cleared ones not yet acknowledged. Worst, then
        newest, first."""
        return sorted(
            (a for a in self.alerts.values() if a.active or not a.acked),
            key=lambda a: (-_RANK[a.severity], -a.id),
        )

    def acknowledge(self, alert_id: int | None = None) -> None:
        """Acknowledge one alert, or all with None. A cleared alert then leaves the panel; an
        active one stays (marked acknowledged) until it clears. Either is remembered for
        CLEAR_HOLD_S after it clears, so a brief clear does not bring it back unacknowledged."""
        for a in self.alerts.values():
            if alert_id is None or a.id == alert_id:
                a.acked = True

    def _forget(self, key: str) -> None:
        aid = self._open.pop(key, None)
        if aid is not None:
            self.alerts.pop(aid, None)
