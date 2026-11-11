"""GNSS height against a wandering barometer (#227, ADR-0045 Proposed).

Synthetic version of the real static session of #224: GNSS at 1 Hz with gpsd-sized sigmas, a
barometer told 0.3 m at 10 Hz that wanders tens of metres. No real data is committed."""

import numpy as np

from pnt.core.measurement import Measurement
from pnt.nav import ESTIMATORS

NS = 1_000_000_000
GNSS_SIGMA = (5.4, 2.1, 2.1)  # m: what gpsd reported on #224 (epx, epy, epv over 1.96)


def static_session(baro_offset, duration_s=120, jump_at_s=None, jump_enu=(300.0, 0.0, 0.0)):
    """A static receiver at the origin. `baro_offset(t_s)` is the barometer's error (m). GNSS
    fixes jump by `jump_enu` from `jump_at_s` on, if given."""
    rng = np.random.default_rng(0)
    out = []
    for k in range(duration_s * 10):
        t = k * NS // 10
        h = baro_offset(k / 10) + rng.normal(0.0, 0.1)
        out.append(Measurement(t_ns=t, source="baro", kind="altitude", value=(h,), sigma=(0.3,)))
        if k % 10 == 0:
            p = rng.normal(0.0, 0.5, 3)
            if jump_at_s is not None and k / 10 >= jump_at_s:
                p = p + np.asarray(jump_enu)
            out.append(
                Measurement(t_ns=t, source="gnss", kind="position_enu", value=tuple(p),
                            sigma=GNSS_SIGMA)
            )  # fmt: skip
    return out


def wander(t_s):
    """Barometer error: fine for 20 s, then a 4 m/s climb to 40 m off, held. The BMP180 on #224
    swung to 77 m at up to 8 m/s. A slow wander, so the barometer's own gate never rejects it."""
    return float(np.clip((t_s - 20.0) * 4.0, 0.0, 40.0))


def per_second(estimates):
    return [e for e in estimates if e.t_ns % NS == 0]


def test_a_wandering_barometer_does_not_lock_gnss_out():
    for name in ("ekf", "ekf-guard", "ekf-calibrated"):
        est = per_second(list(ESTIMATORS[name](static_session(wander))))
        late = [e for e in est if e.t_ns >= 40 * NS]
        assert not any("gnss_excluded" in e.flags for e in est), name
        assert not any("gnss_unavailable" in e.flags for e in late), name
        assert all(e.status != "unsafe" for e in late), name
        assert max(e.hpl_m for e in late) < 50.0, name
        # the height disagreement is not hidden
        assert all("gnss_alt_excluded" in e.flags for e in late), name


def test_a_horizontal_jump_is_still_rejected_while_the_height_disagrees():
    est = per_second(list(ESTIMATORS["ekf-guard"](static_session(wander, jump_at_s=60))))
    after = [e for e in est if e.t_ns > 60 * NS]
    assert all("gnss_excluded" in e.flags for e in after)
    assert all(abs(e.pos_enu[0]) < 50.0 for e in after)


def test_an_agreeing_barometer_changes_nothing():
    est = per_second(list(ESTIMATORS["ekf"](static_session(lambda t: 0.0))))
    assert not any(f in e.flags for e in est for f in ("gnss_excluded", "gnss_alt_excluded"))


def test_a_fix_used_whole_after_a_jump_is_not_flagged_as_height_rejected():
    # The jump guard re-admits GNSS once the jump is undone (ADR-0038): those fixes skip the
    # gate and are used whole, height included, so `gnss_alt_excluded` must not stay on from
    # the fixes before the jump. Jump from 60 s to 90 s, barometer wandering throughout.
    meas = static_session(wander, duration_s=130, jump_at_s=60)
    back = [
        m
        if m.source != "gnss" or m.t_ns < 90 * NS
        else Measurement(t_ns=m.t_ns, source="gnss", kind="position_enu",
                         value=tuple(np.subtract(m.value, (300.0, 0.0, 0.0))), sigma=m.sigma)
        for m in meas
    ]  # fmt: skip
    est = per_second(list(ESTIMATORS["ekf-guard"](back)))
    before = [e for e in est if 40 * NS <= e.t_ns < 60 * NS]
    after = [e for e in est if e.t_ns >= 95 * NS]
    assert all("gnss_alt_excluded" in e.flags for e in before)  # the set-up holds
    assert not any("gnss_excluded" in e.flags for e in after)  # GNSS re-admitted
    assert not any("gnss_alt_excluded" in e.flags for e in after)


def test_a_horizontal_offset_is_not_let_in_by_the_height_fallback():
    # The fallback is for a fix whose height fails. A fix whose 3-D gate fails mostly on its
    # horizontal (a ramping spoofer), with a vertical innovation its own 1-dof gate accepts,
    # stays rejected whole, as before ADR-0045.
    from pnt.nav.ekf import EKF

    f = EKF()
    for m in static_session(lambda t: 0.0, duration_s=60):
        f.process(m)
    t = 60 * NS
    f.predict(t)
    S = f.P[:3, :3] + np.diag(np.square(GNSS_SIGMA))
    # horizontal NIS 12 (passes the 2-dof gate, 13.82), vertical NIS 6 (passes 1 dof, 10.83):
    # 3-D NIS 18 fails the 3-D gate (16.27)
    de = np.sqrt(12.0 * S[0, 0])
    dz = np.sqrt(6.0 * S[2, 2])
    z = f.x[:3] + np.array([de, 0.0, dz])
    f.process(Measurement(t_ns=t, source="gnss", kind="position_enu", value=tuple(z),
                          sigma=GNSS_SIGMA))  # fmt: skip
    e = f.estimate()
    assert "gnss_excluded" in e.flags and "gnss_alt_excluded" not in e.flags
