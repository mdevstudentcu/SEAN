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
- Low-trust sources: sources whose `trust` is under `LOW_TRUST`, listed apart from the rest.
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
#   ekf-base (#107): base_excluded, tower_fault
#   ekf-mhss (#108): mhss_alarm:<hypothesis>, mhss_excluded:<hypothesis> (in `describe`)
FLAGS: dict[str, tuple[str, str]] = {
    "gnss_unavailable": (
        CAUTION,
        "GPS lost: no GNSS position used recently. Navigating on towers and barometer.",
    ),
    "gnss_excluded": (
        WARNING,
        "GPS rejected: its position disagrees with the rest of the solution, so it is not used.",
    ),
    "spoof_suspected": (
        ALARM,
        "GPS spoofing suspected: the towers' geometry contradicts the GPS position. GPS position "
        "excluded until it agrees with the towers again.",
    ),
    "time_spoof_suspected": (
        ALARM,
        "GPS time spoofing suspected: GPS time disagrees with our clock model, so it is not used.",
    ),
    "base_excluded": (
        WARNING,
        "Reference station excluded: its readings disagree with its surveyed position (moved, or "
        "its clock stepped). Coasting on the tower clocks it measured before.",
    ),
    "tower_fault": (
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
    return h


def _emitter_words(emitter: str) -> str:
    source, _, ident = emitter.partition(":")
    return f"{source.upper()} {ident}" if ident else emitter


def describe(flag: str) -> tuple[str, str]:
    """(severity, sentence) for one flag. Unknown flags come back raw, as a caution."""
    if flag in FLAGS:
        return FLAGS[flag]
    kind, _, h = flag.partition(":")
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
        self._open: dict[str, int] = {}  # key -> id of its unacknowledged or still-active alert
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
        if est.status in STATUS and est.status != "degraded":
            current[f"status:{est.status}"] = STATUS[est.status]
        self.settled = self.settled or est.status == "nominal" or t >= STARTUP_MAX_S
        for key, (sev, text) in current.items() if self.settled else ():
            aid = self._open.get(key)  # a cleared, acknowledged alert is already forgotten
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
                if self.alerts[aid].acked:
                    self._forget(key)
        tta_h = self._trend(self._hpl, t, hpl, self.al)
        tta_t = self._trend(self._tpl, t, tpl_s, self.tal)
        trust = dict(sorted(est.trust.items()))
        if est.status in STATUS:
            headline = STATUS[est.status]
        else:
            headline = (
                "ok",
                "All sources in use; the horizontal protection level is within the limit.",
            )
        return {
            "t_s": t,
            "status": est.status,
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
        active one stays (marked acknowledged) until it clears."""
        for a in list(self.alerts.values()):
            if alert_id is None or a.id == alert_id:
                a.acked = True
                if not a.active:
                    self._forget(a.key)

    def _forget(self, key: str) -> None:
        aid = self._open.pop(key, None)
        if aid is not None:
            self.alerts.pop(aid, None)
