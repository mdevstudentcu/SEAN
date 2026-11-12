"""Innovation whiteness test per source (#275, ADR-0055): report only."""

import msgspec
import numpy as np
import pytest

from pnt.core.measurement import Estimate
from pnt.dashboard import health
from pnt.integrity.whiteness import FLAG, Whiteness, WhitenessParams, advisory
from pnt.nav import estimate
from pnt.sim.scenario import generate, load

S = 1_000_000_000


def _feed(w: Whiteness, z: np.ndarray, source="lte", emitters=3, sigma=1.0) -> None:
    """z[k, e]: emitter e's innovation at second k, told variance sigma^2."""
    for k, row in enumerate(z):
        for e, v in enumerate(row[:emitters]):
            w.add(k * S, source, f"lte:{e}", "pseudorange", v * sigma, np.array([[sigma**2]]))


def _ar1(rng, n, emitters, phi):
    z = np.zeros((n, emitters))
    z[0] = rng.normal(size=emitters)
    for k in range(1, n):
        z[k] = phi * z[k - 1] + np.sqrt(1 - phi**2) * rng.normal(size=emitters)
    return z


def test_white_innovations_raise_no_flag():
    rng = np.random.default_rng(0)
    w = Whiteness()
    _feed(w, rng.normal(size=(120, 3)))
    r, T, n = w.stats(120 * S)["lte"]
    assert n == pytest.approx(3 * 59, abs=3)  # 60 s window, one pair per emitter per second
    assert abs(r) < 0.2 and abs(T) < 3
    assert w.flags(120 * S) == []


def test_correlated_innovations_raise_the_source_flag():
    w = Whiteness()
    _feed(w, _ar1(np.random.default_rng(1), 120, 3, phi=0.9))
    r, T, _ = w.stats(120 * S)["lte"]
    assert r > 0.7 and T > WhitenessParams().threshold
    assert w.flags(120 * S) == [f"{FLAG}:lte"]


def test_statistic_ignores_the_told_sigma_size():
    """A told sigma wrong in size alone is a consistency (NIS) matter, not a correlation."""
    z = np.random.default_rng(2).normal(size=(120, 3))
    a, b = Whiteness(), Whiteness()
    _feed(a, z)
    _feed(b, z * 30.0)  # innovations 30x what the filter expects
    assert a.stats(120 * S)["lte"][:2] == pytest.approx(b.stats(120 * S)["lte"][:2])


def test_streams_are_paired_within_themselves_and_close_in_time():
    w = Whiteness(WhitenessParams(max_gap_s=2.0))
    y1 = np.array([[1.0]])
    w.add(0, "lte", "a", "pseudorange", 1.0, y1)
    w.add(S, "lte", "b", "pseudorange", 1.0, y1)  # another emitter: no pair with "a"
    w.add(5 * S, "lte", "a", "pseudorange", 1.0, y1)  # 5 s after its last: too far
    assert "lte" not in w.stats(5 * S)
    w.add(6 * S, "lte", "a", "pseudorange", 1.0, y1)
    assert w.stats(6 * S + 1)["lte"][2] == 1


def test_window_forgets_and_running_sums_stay_exact():
    rng = np.random.default_rng(3)
    w = Whiteness(WhitenessParams(window_s=10.0))
    _feed(w, _ar1(rng, 600, 3, phi=0.95))
    for k, row in enumerate(rng.normal(size=(30, 3)), start=600):
        for e, v in enumerate(row):
            w.add(k * S, "lte", f"lte:{e}", "pseudorange", v, np.array([[1.0]]))
    t = 630 * S
    w.stats(t)
    pairs = w._pairs["lte"]
    assert all(p[0] > t - 10 * S for p in pairs)
    sp = sum(p[1] for p in pairs)
    assert w._sums["lte"][0] == pytest.approx(sp, abs=1e-9)


def _short(name: str, seconds: float) -> dict:
    spec = load(name)
    spec["duration_s"] = seconds
    return spec


def _run(spec, seed=0, estimator="ekf", whiteness=True):
    """The panel's path by default (`whiteness=True`); False is the eval path."""
    run = generate(spec, seed=seed)
    return list(
        estimate(
            estimator, run.measurements, origin_llh=spec.get("origin_llh"), whiteness=whiteness
        )
    )


@pytest.mark.parametrize(
    ("scenario", "fires"), [("challenge-drone-nominal", True), ("easy-nominal", False)]
)
def test_the_filter_flags_lte_only_where_its_errors_are_correlated(scenario, fires):
    """Fails without the EKF's hook (`EKF.process` feeding `whiteness.add`): nothing to test."""
    est = _run(_short(scenario, 180.0))
    flagged = any(f"{FLAG}:lte" in e.flags for e in est)
    assert flagged == fires
    if not fires:
        assert not any(advisory(f) for e in est for f in e.flags)


def test_the_flag_changes_no_estimate():
    """Positions, covariances, HPL, status, trust and every other flag as with the test off."""
    spec = _short("challenge-drone-outage", 180.0)
    on, off = _run(spec), _run(spec, whiteness=False)
    assert any(any(advisory(f) for f in e.flags) for e in on)
    assert len(on) == len(off)
    for a, b in zip(on, off, strict=True):
        keep = [f for f in a.flags if not advisory(f)]
        assert msgspec.structs.replace(a, flags=keep) == b


def test_the_eval_path_runs_without_the_test():
    """`pnt eval`, results and sweeps call `nav.estimate` without `whiteness`: no tracker at all
    (it costs about a fifth of `ekf`'s run time), so no flag."""
    est = _run(_short("challenge-drone-nominal", 120.0), whiteness=False)
    assert not any(advisory(f) for e in est for f in e.flags)
    # the panel's switch reaches only estimators built on `ekf.run`; others run as before
    spec = _short("easy-nominal", 30.0)
    for name in ("baseline", "ekf-base"):
        assert _run(spec, estimator=name, whiteness=True) == _run(spec, estimator=name)


def test_gnss_position_is_analysis_only():
    """Receivers smooth their fixes, so GNSS position is never flagged (owners, ADR-0055); its
    statistic is still computed."""
    w = Whiteness()
    z = _ar1(np.random.default_rng(4), 120, 3, phi=0.95)
    for k, row in enumerate(z):
        w.add(k * S, "gnss", None, "position_enu", row, np.eye(3))
    _, T, _ = w.stats(120 * S)["gnss"]
    assert T > WhitenessParams().threshold
    assert w.flags(120 * S) == []


def test_flags_come_after_the_monitor_so_its_status_is_unchanged():
    """`ekf-mhss` makes its status from the flags it sees: this test's are added after it."""
    est = _run(_short("challenge-drone-nominal", 120.0), estimator="ekf-mhss")
    late = [e for e in est if any(advisory(f) for f in e.flags)]
    assert late
    for e in late:
        others = [f for f in e.flags if not advisory(f)]
        assert e.status == "unsafe" or e.status == ("degraded" if others else "nominal")


def test_panel_describes_the_flag_and_it_degrades_nothing():
    sev, text = health.describe(f"{FLAG}:lte")
    assert sev == health.CAUTION and text.startswith("LTE: errors look correlated")
    assert health.describe(f"{FLAG}:gnss:time")[1].startswith("GNSS TIME")
    est = Estimate(
        t_ns=0, pos_enu=(0, 0, 0), vel_enu=(0, 0, 0), pos_cov=(1,) * 9, hpl_m=60.0,
        status="unsafe", flags=[f"{FLAG}:lte"],
    )  # fmt: skip
    assert health.panel_status(est, alert_limit_m=100.0) == "nominal"
