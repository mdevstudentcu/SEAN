"""Multiple-hypothesis solution separation (MHSS) with dependency-aware fault hypotheses (#82).

ARAIM-style integrity (Blanch et al., "Baseline advanced RAIM user algorithm and possible
improvements", IEEE TAES 51(1), 2015) moved onto a Kalman filter, as in Brenner's solution
separation for GPS/INS (ION GPS 1995): each fault hypothesis has a sub-filter that never sees
that hypothesis's measurements, and the protection level bounds the all-in-view error by how far
each sub-filter could be from it.

Fault hypotheses (ADR-0022, ADR-0024). Jia, Khalife & Kassas (IEEE T-ITS 2023) show that a
tower with its own unknown clock adds no detection redundancy, so faults are grouped by what
fails together, not by tower:
- `site:<id>`: one LTE site (sectors sharing a clock), or one tower when the site is unknown.
- `builder:<id>`: every site of one network builder (shared timing source).
- `layer:<source>`: a whole source type (all LTE, the barometer...), e.g. a front-end failure.
- `gnss-cm`: GNSS common mode. GNSS and everything GNSS-derived (ADS-B positions, SBAS, Remote
  ID, unclassified sources). GNSS-timed sources stay in: their geometry differences still count,
  and only their time part fails with GNSS. On the EKF on main every tower has its own free clock
  offset and the towers carry no receiver clock, so tower time never reaches our position or
  clock and there is nothing to release. A shared builder clock term (#77) must be released
  (left unconstrained) inside this hypothesis's sub-filters; see `MHSS.__init__`.
A GNSS layer hypothesis is not added: it is a subset of `gnss-cm`, whose sub-filter already
excludes it. Groupings (site and builder of each emitter) are optional inputs; by default every
emitter is its own site and there are no builder hypotheses.

Sub-filters. Each hypothesis's sub-filter is a copy of the main EKF taken when its group first
appears, fed every later measurement except the group's. The GNSS-free sub-filter cannot run
from the start: tower clocks are only learned while GNSS is trusted (ADR-0022), so it is a pair of
staggered copies re-seeded from the main filter every `gnss_window_s`. The older copy is used, so
a GNSS fault is separable for between half and one window after onset. A copy is only re-seeded
while its own test is quiet (below `reseed_test_max` of the threshold) and nothing is excluded,
so a fault already showing is never absorbed. A fault slower than that can still be absorbed
step by step: this monitor protects against faults that grow faster than about
reseed_test_max * threshold per window.

`mode="snapshot"` instead re-seeds every sub-filter from the main filter at every epoch: the
weighted-least-squares snapshot on the EKF's linearised model with the EKF prior as a
pseudo-measurement. It is kept for comparison: the prior already carries every past fault, so
a slow fault that the main filter has absorbed shows no separation.

Per epoch, horizontal only, for the all-in-view solution x0 (covariance P0) and each subset k
(xk, Pk), with N hypotheses of prior p_k:
- separation d_k = xk - x0, covariance S_k = Pk - P0 (Brenner), floored at SEP_FLOOR_M^2
- test: q_k = sqrt(d_k' S_k^-1 d_k) / c_fa, c_fa = sqrt(-2 ln(P_FA / N)); fails if q_k > 1
  (d_k' S_k^-1 d_k is chi-square with 2 dof when fault-free, so P_FA is the continuity budget)
- threshold on the error axis: T_k = c_fa * sqrt(max eig S_k)
- HPL = max(K_ff * s0, max_k (T_k + K_k * s_k)), s = sqrt(max eigenvalue) of P0 or Pk,
  K_ff = sqrt(-2 ln(PHMI / 2)), K_k = sqrt(-2 ln(PHMI / (2 N p_k))).
  This is Blanch's MHSS bound with the integrity risk split evenly (half fault-free, half over
  the N hypotheses, his conservative closed form instead of a bisection) and the horizontal error
  bounded radially through the largest eigenvalue (P(|e| > K s) <= exp(-K^2 / 2) for a 2-D
  Gaussian), the convention `protection.hpl` uses, instead of per axis.
- exclusion: if any test fails, or a GNSS alarm from the main filter has held for
  `alarm_hold_s` (then k* = gnss-cm), the output switches to the subset k* with the largest q_k.
  Under one fault, the error of x_k* is bounded by K_ff * s_k* if the fault was in k*, or by
  |x_k* - x_m| + K_m * s_m if it was in m, so HPL = the max of those over m.

All priors and budgets are `TBC`; see `Params`.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field

import msgspec

from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.dependency import GNSS_DERIVED, tag_of

GNSS_CM = "gnss-cm"
# EKF health keys (`EKF.last_used`) whose measurements say nothing about horizontal position.
# "gnss:time" is pnt.nav.ekf.GNSS_TIME (not imported: pnt.nav imports this module).
NOT_HORIZONTAL = frozenset({"baro", "gnss:time"})
# Floor on a separation's standard deviation, so a hypothesis whose sub-filter equals the main
# filter (its group is silent) doesn't divide by zero. Regression guard, not a requirement.
SEP_FLOOR_M = 0.1
# Main-filter flags that mean "GNSS is not to be trusted". `spoof_suspected` is the name
# pnt.metrics already counts as an alarm; the EKF on main raises only `gnss_excluded`.
GNSS_ALARM_FLAGS = frozenset({"gnss_excluded", "spoof_suspected"})


@dataclass
class Params:
    # Priors: probability that the fault is present at an epoch. All TBC; none is measured.
    # p_site: LTE clocks jump about once a minute in Lapin et al. (IEEE TVT 2024), and site
    #   association can be wrong (ADR-0023). Set 100x ARAIM's 1e-5 per satellite because no
    #   operator monitors these signals.
    p_site: float = 1e-3
    # p_builder: a network's timing source in holdover or captured (ADR-0022), e.g. the January
    #   2016 GPS timing fault (RNT Foundation). Same as ARAIM's constellation prior, 1e-4.
    p_builder: float = 1e-4
    # p_layer: a whole front end failing (one SDR or sensor). ARAIM constellation analogue.
    p_layer: float = 1e-4
    # p_gnss_cm: GNSS spoofed, meaconed or wrong, and everything that echoes it. Our threat model
    #   is a contested environment, so 10x the site prior's ARAIM analogue.
    p_gnss_cm: float = 1e-3
    # Integrity budget per epoch, horizontal. 1e-7 matches K_H = 5.33 in protection.py (TBC by
    # REQ-02).
    phmi: float = 1e-7
    # Continuity budget per epoch for a false exclusion, shared over hypotheses (TBC by REQ-04).
    p_fa: float = 1e-5
    # Exposure window of the GNSS-free sub-filters, and how quiet a test must be to re-seed one.
    gnss_window_s: float = 60.0  # TBC
    reseed_test_max: float = 0.5  # TBC
    reseed_quiet_s: float = 10.0  # TBC: how long the test must have stayed quiet
    alarm_hold_s: float = 1.0  # TBC, same hold as pnt.metrics.ALARM_HOLD_S
    detect_hold_s: float = 1.0  # TBC: how long a separation test must fail before it counts
    # A sub-filter that used no horizontal measurement for this long is dead reckoning, and is
    # not tested (TBC: a few LTE dropouts long)
    aided_s: float = 10.0
    alert_limit_m: float = 50.0  # TBC: REQ-02
    mode: str = "bank"  # "bank" or "snapshot"
    allocation: str = "exact"  # "exact" (bisection) or "even" (closed form)
    pl_separation: str = "actual"  # "actual" (|x_k - x_0|) or "threshold" (T_k)
    alarm_flags: frozenset = field(default=GNSS_ALARM_FLAGS)


@dataclass
class Hypothesis:
    name: str
    prior: float
    windowed: bool
    filters: list
    next_seed_ns: list[int]
    seed_ns: list[int]
    loud_ns: list[int]  # last epoch the copy's test was not quiet
    test: list[float]


@dataclass
class Report:
    """The last epoch's monitor output, for analysis and the panel (not in the ICD Estimate)."""

    t_ns: int = 0
    hpl_m: float = float("nan")
    tests: dict[str, float] = field(default_factory=dict)  # q_k; > 1 fails
    excluded: str | None = None  # the output is the subset without this hypothesis
    alarmed: str | None = None  # this hypothesis failed, but the subset without it can't serve


def _h(f) -> tuple[float, float, float, float, float]:
    """Horizontal (e, n, Pee, Pen, Pnn) of a filter, as plain floats: the per-epoch math is all
    2x2, where numpy's per-call overhead costs more than the arithmetic."""
    x, P = f.x, f.P
    return float(x[0]), float(x[1]), float(P[0, 0]), float(P[0, 1]), float(P[1, 1])


def _max_eig(a: float, b: float, d: float) -> float:
    """Largest eigenvalue of [[a, b], [b, d]], at least 0."""
    return max((a + d) / 2 + math.sqrt(((a - d) / 2) ** 2 + b * b), 0.0)


def _k(p: float) -> float:
    """Radial multiplier for a 2-D Gaussian tail probability p (0 if p >= 1)."""
    return math.sqrt(-2.0 * math.log(p)) if p < 1.0 else 0.0


@dataclass
class _Row:
    name: str
    prior: float
    q: float  # normalised test statistic, > 1 fails
    f: object  # the sub-filter
    s: float  # sqrt of the largest eigenvalue of its horizontal covariance
    sep: float  # |x_k - x_0|
    sd: float  # sqrt of the largest eigenvalue of the separation covariance
    e: float  # horizontal position of the sub-filter
    n: float


def _test(hk, h0, c_fa: float) -> tuple[float, float, float]:
    """(normalised test, |separation|, separation sigma) of a sub-filter against the main one,
    both given by `_h`.

    The separation covariance is Pk - P0 (Brenner). It is only positive semi-definite while the
    sub-filter has a subset of the main filter's information; the two gate measurements
    separately, so a sub-filter can accept one the main filter rejected. Each eigenvalue is
    therefore taken by magnitude and floored at SEP_FLOOR_M^2."""
    de, dn = hk[0] - h0[0], hk[1] - h0[1]
    a, b, d = hk[2] - h0[2], hk[3] - h0[3], hk[4] - h0[4]
    mid, rad = (a + d) / 2, math.sqrt(((a - d) / 2) ** 2 + b * b)
    f2 = SEP_FLOOR_M**2
    l1, l2 = max(abs(mid + rad), f2), max(abs(mid - rad), f2)
    # eigenvector of the larger eigenvalue (mid + rad); the other is orthogonal
    if b != 0.0:
        ux, uy = b, mid + rad - a
    else:
        ux, uy = (1.0, 0.0) if a >= d else (0.0, 1.0)
    norm = math.hypot(ux, uy)
    ux, uy = ux / norm, uy / norm
    p1, p2 = de * ux + dn * uy, -de * uy + dn * ux
    m2 = p1 * p1 / l1 + p2 * p2 / l2
    return math.sqrt(m2) / c_fa, math.hypot(de, dn), math.sqrt(max(l1, l2))


def _pl(s_ff: float, terms: list[tuple[float, float, float]], phmi: float, allocation: str):
    """Smallest L with exp(-L^2 / 2 s_ff^2) + sum p_k exp(-(L - b_k)^2 / 2 s_k^2) <= phmi.

    terms are (prior p_k, offset b_k, sigma s_k). "even" gives half the risk to the fault-free
    term and splits the rest evenly (closed form, conservative); "exact" solves by bisection,
    starting from the even split, which is always a valid upper end."""
    n = max(len(terms), 1)
    hi = max([_k(phmi / 2) * s_ff] + [b + _k(phmi / (2 * n * pk)) * sk for pk, b, sk in terms])
    if allocation == "even":
        return hi

    def risk(L: float) -> float:
        r = math.exp(-0.5 * (L / s_ff) ** 2) if s_ff > 0 else 0.0
        for pk, b, sk in terms:
            z = max(L - b, 0.0) / sk if sk > 0 else math.inf
            r += pk * math.exp(-0.5 * z * z)
        return r

    lo = 0.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if risk(mid) > phmi else (lo, mid)
    return hi


class MHSS:
    """Wraps a running EKF (`ekf.run(..., monitor=MHSS)`). Reads its x, P, process and predict.

    Call `process(m)` before the main filter processes m, and `estimate(est)` at each epoch
    after the main filter has predicted to it.
    """

    def __init__(self, main, sites=None, builders=None, params: Params | None = None):
        """`sites` maps an emitter to its site and `builders` a site to its network builder,
        the shape `pnt.sim.scenario.tower_groups` returns. Both optional: an emitter missing
        from `sites` is its own site, and a site missing from `builders` has no builder
        hypothesis."""
        self.main = main
        self.sites = dict(sites or {})
        self.builders = dict(builders or {})
        self.p = params or Params()
        self.hyps: dict[str, Hypothesis] = {}
        self.window_ns = int(self.p.gnss_window_s * 1e9)
        self.alarm_since: int | None = None
        self.fail_since: dict[str, int] = {}
        self.report = Report()

    # --- grouping -----------------------------------------------------------------------
    def groups(self, m: Measurement) -> dict[str, float]:
        """The hypotheses a measurement belongs to, with their priors."""
        if tag_of(m) == GNSS_DERIVED:
            return {GNSS_CM: self.p.p_gnss_cm}
        out = {f"layer:{m.source}": self.p.p_layer}
        if m.emitter:
            site = self.sites.get(m.emitter, m.emitter)
            out[f"site:{site}"] = self.p.p_site
            if site in self.builders:
                out[f"builder:{self.builders[site]}"] = self.p.p_builder
        return out

    def _clone(self):
        return copy.deepcopy(self.main)

    def _add(self, name: str, prior: float, t_ns: int) -> None:
        windowed = self.p.mode == "bank" and name == GNSS_CM
        n = 2 if windowed else 1
        half = self.window_ns // 2
        self.hyps[name] = Hypothesis(
            name=name,
            prior=prior,
            windowed=windowed,
            filters=[self._clone() for _ in range(n)],
            next_seed_ns=[t_ns + self.window_ns, t_ns + half][:n],
            seed_ns=[t_ns] * n,
            loud_ns=[t_ns] * n,
            test=[0.0] * n,
        )

    # --- measurements ------------------------------------------------------------------------
    def process(self, m: Measurement) -> None:
        if self.main.x is None:
            return
        mine = self.groups(m)
        for name, prior in mine.items():
            if name not in self.hyps:
                self._add(name, prior, m.t_ns)
        for h in self.hyps.values():
            if h.name not in mine:
                for f in h.filters:
                    f.process(m)

    # --- output --------------------------------------------------------------------------
    def estimate(self, est: Estimate) -> Estimate:
        t = est.t_ns
        p = self.p
        h0 = _h(self.main)
        n = max(len(self.hyps), 1)
        c_fa = _k(p.p_fa / n)
        aided_ns = int(p.aided_s * 1e9)

        rows: list[_Row] = []
        for h in self.hyps.values():
            hs, tests = [], []
            for f in h.filters:
                f.predict(t)
                hs.append(_h(f))
                tests.append(_test(hs[-1], h0, c_fa))
            # An unaided copy is dead reckoning: its covariance is only the motion model's guess,
            # so its separation is not tested (its PL term still counts)
            aided = [
                self._aided(f, max(s0, t - aided_ns))
                for f, s0 in zip(h.filters, h.seed_ns, strict=True)
            ]
            h.test = [q if a else 0.0 for (q, _, _), a in zip(tests, aided, strict=True)]
            # the older copy (longer without GNSS) is the one whose next re-seed comes first
            i = 0 if len(h.filters) == 1 else int(h.next_seed_ns[0] > h.next_seed_ns[1])
            _, sep, sd = tests[i]
            s_k = math.sqrt(_max_eig(*hs[i][2:]))
            f = h.filters[i]
            rows.append(_Row(h.name, h.prior, h.test[i], f, s_k, sep, sd, *hs[i][:2]))

        alarm = bool(p.alarm_flags & set(est.flags))
        if not alarm:
            self.alarm_since = None
        elif self.alarm_since is None:
            self.alarm_since = t
        held = alarm and t - self.alarm_since >= int(p.alarm_hold_s * 1e9)

        # A candidate for exclusion: GNSS on a held alarm, else the worst test that has failed
        # for detect_hold_s (one noisy epoch is not a detection; the PL does not wait for it)
        for r in rows:
            if r.q <= 1.0:
                self.fail_since.pop(r.name, None)
            else:
                self.fail_since.setdefault(r.name, t)
        hold_ns = int(p.detect_hold_s * 1e9)
        failed = [r for r in rows if r.q > 1.0 and t - self.fail_since[r.name] >= hold_ns]
        candidate = None
        if held and GNSS_CM in self.hyps:
            candidate = GNSS_CM
        elif failed:
            candidate = max(failed, key=lambda r: r.q).name
        # Exclude only if the subset left could serve on its own: its fault-free bound is within
        # the alert limit (as ARAIM requires an available solution after exclusion). Otherwise
        # alarm without excluding: switching to a subset whose own error is unbounded at the
        # alert limit can make the output worse, not safer.
        k_ff = _k(p.phmi / 2)
        excluded = alarmed = None
        if candidate is not None:
            row = next(r for r in rows if r.name == candidate)
            if k_ff * row.s <= p.alert_limit_m:
                excluded = candidate
            else:
                alarmed = candidate

        if excluded is None:
            out_f = self.main
            ff = math.sqrt(_max_eig(*h0[2:]))
            # After a failed test the threshold no longer bounds the separation: use the
            # separation itself (the error is within |x0 - xk| + |xk - truth|)
            actual = alarmed is not None or p.pl_separation == "actual"
            terms = [(r.prior, r.sep if actual else c_fa * r.sd, r.s) for r in rows]
        else:
            row = next(r for r in rows if r.name == excluded)
            out_f, ff = row.f, row.s
            terms = [
                (r.prior, math.hypot(row.e - r.e, row.n - r.n), r.s)
                for r in rows
                if r.name != excluded
            ]
        hpl = _pl(ff, terms, p.phmi, p.allocation)

        self.report = Report(
            t_ns=t, hpl_m=hpl, tests={r.name: r.q for r in rows}, excluded=excluded,
            alarmed=alarmed,
        )  # fmt: skip
        self._reseed(t, excluded or alarmed)
        return self._output(est, out_f, hpl, excluded, alarmed)

    def _aided(self, f, since_ns: int) -> bool:
        """Whether a sub-filter used a horizontal measurement since `since_ns`."""
        if self.p.mode == "snapshot":
            return True
        return any(t >= since_ns for k, t in f.last_used.items() if k not in NOT_HORIZONTAL)

    def _reseed(self, t: int, excluded: str | None) -> None:
        if self.p.mode == "snapshot":
            for h in self.hyps.values():
                h.filters = [self._clone()]
            return
        quiet_ns = int(self.p.reseed_quiet_s * 1e9)
        for h in self.hyps.values():
            if not h.windowed:
                continue
            for i, q in enumerate(h.test):
                if q >= self.p.reseed_test_max or excluded is not None:
                    h.loud_ns[i] = t
            for i in range(len(h.filters)):
                if t >= h.next_seed_ns[i] and t - h.loud_ns[i] >= quiet_ns:
                    h.filters[i] = self._clone()
                    h.next_seed_ns[i] = t + self.window_ns
                    h.seed_ns[i] = t
                    # keep the copies staggered: never re-seed both within half a window
                    for j in range(len(h.filters)):
                        if j != i:
                            h.next_seed_ns[j] = max(h.next_seed_ns[j], t + self.window_ns // 2)
                    break

    def _output(self, est: Estimate, f, hpl: float, excluded, alarmed) -> Estimate:
        flags = list(est.flags)
        trust = dict(est.trust)
        if alarmed is not None:
            flags.append(f"mhss_alarm:{alarmed}")
        if excluded is not None:
            flags.append(f"mhss_excluded:{excluded}")
            if excluded == GNSS_CM:
                if "gnss_excluded" not in flags:
                    flags.append("gnss_excluded")
                trust["gnss"] = 0.0
            elif excluded.startswith("layer:"):
                trust[excluded.split(":", 1)[1]] = 0.0
        status = "unsafe" if hpl > self.p.alert_limit_m else ("degraded" if flags else "nominal")
        out = msgspec.structs.replace(
            est, hpl_m=float(hpl), status=status, trust=trust, flags=flags
        )
        if f is not self.main:  # the output switches to the subset without the excluded group
            out.pos_enu = tuple(float(v) for v in f.x[:3])
            out.vel_enu = tuple(float(v) for v in f.x[3:6])
            out.pos_cov = tuple(float(v) for v in f.P[:3, :3].ravel())
        return out
