"""What the panel shows, independent of how it reaches the browser (#25).

A `Feed` is any measurement source (sim, replay, live: ADR-0004) plus the estimator to run on
it, and truth when it is known. `frames` runs the estimator and turns every Estimate into one
JSON-ready dict; `paced` holds those frames to the data's own clock (times `speed`) and thins
them to what a screen can show. The server only moves the frames: a live stream (`pnt live`,
ADR-0009) is one more Feed, with `pace=False`.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

import numpy as np

from pnt.core.frames import emitter_enu, enu_to_llh, llh_to_enu
from pnt.core.measurement import Measurement, Truth
from pnt.dashboard.health import CONF_AMBER_FRACTION, HealthMonitor, gps_trust
from pnt.integrity.sky import SpoofDecision
from pnt.metrics import ALERT_LIMIT_M
from pnt.nav import cells, estimate

# An emitter counts as heard on the map if one of its records is this recent. TBC: two missed
# readings of a 1 Hz tower.
HEARD_S = 2.5
# Most frames per wall-clock second sent to the browser; every estimate still goes through the
# health monitor. TBC: REQ-05 asks for >= 1 Hz (TBC); 10 Hz is the estimators' epoch rate.
MAX_RATE_HZ = 10.0


@dataclass
class Feed:
    name: str
    kind: str  # "sim" | "replay" | "live"
    measurements: Iterable[Measurement]
    estimator: str = "ekf"
    origin_llh: list[float] | None = None
    reference: dict | None = None  # ICD-session `reference` block
    truth: dict[int, Truth] | None = None  # by t_ns
    preflight: dict | None = None  # {"t_s": [...], "hpl_m": [...]} from pnt.integrity.preflight
    pace: bool = True  # False for live: the data arrive in real time already
    notes: list[str] = field(default_factory=list)
    # Opt-in (#264): keep what locates the capture off the page and out of the stream: the
    # session origin and the towers (a registered site drawn in ENU locates the origin). The
    # estimator still gets the origin. The track stays: ENU metres about the origin, relative.
    hide_origin: bool = False

    def info(self, alert_limit_m: float, time_alert_limit_s: float) -> dict:
        """The static part of the panel: sent once to every browser that connects."""
        ref = None
        if self.reference and self.origin_llh is not None:
            ref = [float(v) for v in llh_to_enu(self.reference["position_llh"], self.origin_llh)]
        return {
            "name": self.name,
            "kind": self.kind,
            "estimator": self.estimator,
            "origin_llh": None if self.hide_origin else self.origin_llh,
            "reference_enu": ref,
            "has_truth": bool(self.truth),
            "alert_limit_m": alert_limit_m,
            "time_alert_limit_s": time_alert_limit_s,
            "confidence_amber_m": CONF_AMBER_FRACTION * alert_limit_m,  # the map legend's split
            "preflight": self.preflight,
            "notes": self.notes,
        }


def replay_feed(
    path,
    estimator: str = "ekf",
    preflight: bool = True,
    alert_limit_m: float = ALERT_LIMIT_M,
    hide_origin: bool = False,
) -> Feed:
    """A recorded session (folder or .mcap). Truth if it has a `/truth` topic. A simulated
    session also gets its scenario's pre-flight prediction (`pnt.integrity.preflight`).
    `hide_origin`: see `Feed.hide_origin`."""
    from pnt.io import session
    from pnt.io.mcap_log import read_session
    from pnt.sources.replay import ReplaySource

    mcap = session.mcap_path(path)
    meta = session.read_meta(path)
    truth = {r.t_ns: r for _, r in read_session(mcap, topics=["/truth"])}
    feed = Feed(
        name=session.session_name(path),
        kind="replay",
        measurements=ReplaySource(mcap),
        estimator=estimator,
        origin_llh=meta.get("origin_llh"),
        reference=meta.get("reference"),
        truth=truth or None,
        hide_origin=hide_origin,
    )
    if preflight and meta.get("scenario"):
        seed = int(meta.get("seed") or 0)
        _add_preflight(feed, meta["scenario"], seed, alert_limit_m, named=True)
    return feed


def sim_feed(
    scenario: str,
    seed: int = 0,
    estimator: str = "ekf",
    preflight: bool = True,
    alert_limit_m: float = ALERT_LIMIT_M,
) -> Feed:
    """A scenario run straight from the sim: nothing is recorded."""
    from pnt.sources.sim import SimSource

    src = SimSource(scenario, seed=seed)
    run = src.run
    feed = Feed(
        name=f"{run.name} (seed {seed})",
        kind="sim",
        measurements=src,
        estimator=estimator,
        origin_llh=run.spec.get("origin_llh"),
        reference=run.reference,
        truth={t.t_ns: t for t in run.truth},
        notes=[f"{_clock_s(t)}: {text}" for t, text in run.events],
    )
    if preflight:
        _add_preflight(feed, run.spec, seed, alert_limit_m)
    return feed


def live_feed(
    measurements: Iterable[Measurement],
    name: str,
    estimator: str = "ekf",
    origin_llh=None,
    reference: dict | None = None,
    notes: list[str] | None = None,
) -> Feed:
    """The payload's live stream (`pnt.sources.live.LiveSource`, ADR-0009): no truth, no
    pre-flight strip, and no pacing, since the records arrive in real time already."""
    return Feed(
        name=name,
        kind="live",
        measurements=measurements,
        estimator=estimator,
        origin_llh=None if origin_llh is None else list(origin_llh),
        reference=reference,
        pace=False,
        notes=list(notes or []),
    )


def _clock_s(t_ns: int) -> str:
    from pnt.sim.scenario import T0_NS

    return f"T+{(t_ns - T0_NS) / 1e9:.0f} s"


def _add_preflight(
    feed: Feed, scenario, seed: int, alert_limit_m: float, named: bool = False
) -> None:
    """The predicted HPL strip, on the panel's clock (seconds since the first estimate)."""
    from pnt.integrity import preflight
    from pnt.sim.scenario import load_named

    try:
        spec = load_named(scenario) if named else scenario  # session files are untrusted input
        p = preflight.predict(spec, seed, feed.estimator, alert_limit_m)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        feed.notes.append(f"no pre-flight prediction: {exc}")
        return
    if not len(p.t_s):
        return
    t0 = p.t_s[0]  # the panel's clock starts at the first estimate, as the prediction's does
    feed.preflight = {
        "t_s": [round(float(t - t0), 2) for t in p.t_s],
        "hpl_m": [None if v != v else round(float(v), 2) for v in p.hpl_m],
        "unavailable": [(a - t0, b - t0) for a, b in p.unavailable()],
        "dropped_faults": p.dropped_faults,
    }


class _Watch:
    """Passes measurements through to the estimator, noting each emitter's position and when it
    was last heard (payload receiver only: the reference station is drawn from the session).
    It watches records after the registry lookup (`pnt.nav.cells.attach`), so a real or
    front-end-shaped LTE cell, which carries no position of its own, is drawn at its registered
    site; `estimate` then passes the placed records through unchanged.
    With `spoof`, each GPS skyview (a `gnss_health` with per-PRN C/N0) goes to the spoof
    decision, seen from the latest estimate (`pos_enu`); it needs the session origin."""

    def __init__(self, measurements: Iterable[Measurement], origin_llh, spoof=None):
        self.it = iter(measurements)
        self.origin_llh = origin_llh
        self.spoof = spoof
        self.pos_enu = (0.0, 0.0, 0.0)  # the latest estimate's position
        self.last: dict[str, int] = {}
        self.new: list[dict] = []
        self._known: set[str] = set()

    def __iter__(self) -> Iterator[Measurement]:
        for m in self.it:
            if self.spoof is not None and self.origin_llh is not None and m.receiver == "payload":
                if m.kind == "gnss_health" and m.meta.get("snr"):
                    self.spoof.measurement(m, enu_to_llh(self.pos_enu, self.origin_llh))
            if m.emitter and m.receiver == "payload":
                if m.emitter not in self._known:
                    self._known.add(m.emitter)
                    pos = emitter_enu(m.meta, self.origin_llh) if m.meta else None
                    if pos is not None:
                        e, n = (float(v) for v in pos[:2])
                        self.new.append({"id": m.emitter, "source": m.source, "e": e, "n": n})
                self.last[m.emitter] = m.t_ns
            yield m


def _num(x) -> float | None:
    """JSON has no NaN: None instead."""
    return None if x is None or not math.isfinite(x) else float(x)


def frames(feed: Feed, monitor: HealthMonitor, lock=None) -> Iterator[dict]:
    """One frame per Estimate. `lock`, if given, guards the monitor (the server acknowledges
    alerts from another thread)."""
    spoof = SpoofDecision()  # advisory (ADR-0041): reads the estimates, never changes them
    watch = _Watch(cells.attach(feed.measurements, feed.origin_llh), feed.origin_llh, spoof)
    heard_ns = int(HEARD_S * 1e9)
    run = estimate(
        feed.estimator, watch, origin_llh=feed.origin_llh, reference=feed.reference, whiteness=True
    )  # the panel shows the whiteness flag (ADR-0055)
    for est in run:
        if lock is not None:
            with lock:
                health = monitor.update(est)
        else:
            health = monitor.update(est)
        cov = np.reshape(est.pos_cov, (3, 3))
        truth = feed.truth.get(est.t_ns) if feed.truth else None
        err = None
        if truth is not None:
            err = float(np.hypot(*np.subtract(est.pos_enu, truth.pos_enu)[:2]))
        new, watch.new = watch.new, []
        watch.pos_enu = est.pos_enu
        heard = sorted(e for e, t in watch.last.items() if est.t_ns - t <= heard_ns)
        if feed.hide_origin:
            new, heard = [], []
        sp = spoof.decide(est.t_ns, est.flags).to_dict()
        yield {
            "t_s": health["t_s"],
            "pos": [float(v) for v in est.pos_enu],
            "vel": [float(v) for v in est.vel_enu[:2]],
            "cov": [float(cov[0, 0]), float(cov[0, 1]), float(cov[1, 1])],  # ee, en, nn (m^2)
            "hpl_m": _num(est.hpl_m),
            "vpl_m": _num(est.vpl_m),
            "clock_bias_s": _num(est.clock_bias_s),
            "clock_sigma_s": _num(est.clock_sigma_s),
            "status": health["status"],  # against the panel's limit (health.panel_status)
            "confidence": health["confidence"],  # track colour (health.confidence)
            "flags": list(est.flags),
            "truth": None if truth is None else [float(v) for v in truth.pos_enu],
            "truth_clock_s": None if truth is None else _num(truth.clock_bias_s),
            "err_h_m": err,
            "health": {k: _num(v) if isinstance(v, float) else v for k, v in health.items()},
            "heard": heard,
            "new_emitters": new,
            "spoof": sp,
            # the panel's GPS trust (health.gps_trust): presentation of the above, nothing new
            "gps_trust": gps_trust(est.flags, est.trust, sp, health["gps_unused_s"]),
        }


def paced(
    source: Iterable[dict],
    speed: float = 1.0,
    max_rate_hz: float = MAX_RATE_HZ,
    pace: bool = True,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[dict]:
    """Frames held to the data's clock times `speed` (no holding with `pace=False` or an
    infinite speed), thinned to at most `max_rate_hz` per wall second. A thinned-out frame's new
    emitters ride on the next frame sent; the last frame is always sent. Each frame sent carries
    `lag_s`: how far behind its due time it went out (> 0 when the estimator is slower than the
    requested speed)."""
    hold = pace and math.isfinite(speed)
    gap = 1.0 / max_rate_hz
    start = t_first = None
    last_sent = -math.inf
    pending: list[dict] = []
    frame = None
    for frame in source:
        now = clock()
        if start is None:
            start, t_first = now, frame["t_s"]
        due = start + (frame["t_s"] - t_first) / speed if hold else now
        if due > now:
            sleep(due - now)
            now = due
        pending += frame["new_emitters"]
        if now - last_sent < gap:
            continue
        last_sent = now
        frame["new_emitters"], pending = pending, []
        frame["lag_s"] = max(0.0, clock() - due)
        yield frame
        frame = None
    if frame is not None:  # the last frame was thinned out: send it anyway
        frame["new_emitters"] = pending
        frame["lag_s"] = 0.0
        yield frame
