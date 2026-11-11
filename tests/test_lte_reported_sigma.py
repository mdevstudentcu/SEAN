"""A radio's LTE records report a sigma from timing statistics, which can't see multipath, so it
can be far too small (#147). The filter learns the range noise of such records (`meta.rx_clock`)
from their innovations, with the reported sigma as a lower bound only. Records without
`rx_clock` (the simulator's) keep their reported sigma exactly.

Thresholds are regression guards with the observed values in comments, not requirements.
"""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import ekf

TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
OUTAGE_S = (90.0, 270.0)


def stream(rx_clock="a", told_m=2.0, white_m=10.0, multipath_m=10.0, tau_s=30.0, seed=1):
    """Receiver circling the origin. GNSS at 5 Hz outside the outage, baro at 10 Hz, every tower
    at 1 Hz with its own clock, the dongle's clock, white noise and a Gauss-Markov multipath
    error per tower. The records report `told_m`. Returns (measurements, truth {t_ns: pos})."""
    rng = np.random.default_rng(seed)
    offsets = rng.uniform(-500, 500, len(TOWERS))
    mp = np.zeros(len(TOWERS))
    phi = np.exp(-1.0 / tau_s)
    meas, truth = [], {}
    for k in range(int(OUTAGE_S[1] * 10)):
        t = k / 10
        t_ns = k * 100_000_000
        a = 0.05 * t
        pos = np.array([100 * np.cos(a), 100 * np.sin(a), 30.0])
        truth[t_ns] = pos
        alt = (30.0 + rng.normal(0, 0.5),)
        meas.append(Measurement(t_ns=t_ns, source="baro", kind="altitude", value=alt,
                                sigma=(0.5,)))  # fmt: skip
        if k % 2 == 0 and not OUTAGE_S[0] <= t:
            fix = tuple(pos + rng.normal(0, 2, 3))
            meas.append(Measurement(t_ns=t_ns, source="gnss", kind="position_enu", value=fix,
                                    sigma=(2.0, 2.0, 2.0)))  # fmt: skip
        if k % 10 == 0:
            mp = phi * mp + rng.normal(0, multipath_m * np.sqrt(1 - phi**2), len(TOWERS))
            for i, e in enumerate(TOWERS):
                rho = np.linalg.norm(pos - e) + offsets[i] + 40.0 * t + mp[i]
                rho += rng.normal(0, white_m)
                meta = {"emitter_enu": [float(x) for x in e]}
                if rx_clock is not None:
                    meta["rx_clock"] = rx_clock
                meas.append(Measurement(t_ns=t_ns, source="lte", kind="pseudorange",
                                        emitter=f"lte:{i}", value=(float(rho),), sigma=(told_m,),
                                        meta=meta))  # fmt: skip
    return meas, truth


def outage_stats(estimates, truth):
    """(mean horizontal NEES, fraction of epochs with HPL >= horizontal error) in the outage."""
    nees, bound = [], []
    for e in estimates:
        if e.t_ns / 1e9 < OUTAGE_S[0] or e.t_ns not in truth:
            continue
        d = np.subtract(e.pos_enu, truth[e.t_ns])[:2]
        nees.append(d @ np.linalg.solve(np.reshape(e.pos_cov, (3, 3))[:2, :2], d))
        bound.append(e.hpl_m >= np.linalg.norm(d))
    return float(np.mean(nees)), float(np.mean(bound))


@pytest.mark.parametrize(
    ("run", "observed"),
    [
        # (mean NEES, HPL bound rate) observed in the outage, seed 1: learned / reported believed
        (ekf.run, ((1.68, 1.0), (59.7, 0.42))),
        (ekf.run_calibrated, ((1.46, 1.0), (82.7, 0.27))),
    ],
)
def test_an_optimistic_reported_sigma_no_longer_makes_the_filter_overconfident(run, observed):
    records, truth = stream()  # 20 m of range error in all, reported as 2 m
    learned = outage_stats(list(run(records)), truth)
    told = outage_stats(list(run(records, noise_tau_s=None)), truth)
    # Regression guards with margin around the observed values, not requirements
    assert told[0] > 30.0 and told[1] < 0.6  # the failure this guards against
    assert learned[0] < 10.0 and learned[1] > 0.95


def test_an_honest_reported_sigma_is_learned_down_to():
    records, _ = stream(told_m=1.0, white_m=1.0, multipath_m=0.0)
    f = ekf.EKF()
    for m in records:
        f.process(m)
    # Innovations no larger than the reported 1 m: the learned variance falls from the prior's
    # 40^2 towards 1; what is left is the prior's one-sample share of the learned memory
    r = f.range_variance([m for m in records if m.kind == "pseudorange"][-1])
    assert r < 0.05 * 40.0**2  # observed: 46.2 m^2 (3 % of the prior)


def lte(records):
    return [m for m in records if m.kind == "pseudorange"]


def test_a_cells_first_records_carry_the_prior_not_the_reported_sigma():
    """The reported 2 m counted as a sample let the first two records pin the dongle clock's
    drift, after which the gate rejected the cell for good (#147)."""
    records, _ = stream()
    assert ekf.EKF().range_variance(lte(records)[0]) == pytest.approx(40.0**2)
    assert ekf.EKF(noise_prior_m=25.0).range_variance(lte(records)[0]) == pytest.approx(25.0**2)


def test_an_uncertain_state_does_not_pull_the_learned_noise_down():
    """An innovation that the state uncertainty explains says nothing about the noise. Counted,
    its large negative sample collapsed the learned variance to the reported sigma (#147)."""
    records, _ = stream()
    gps = [m for m in records if m.t_ns / 1e9 < 60.0]
    f = ekf.EKF()
    for m in gps:
        f.process(m)
    m = next(m for m in lte(records) if m.t_ns / 1e9 >= 60.0)
    before = f.range_variance(m)
    # 20 m of range error in the stream: learned, not pinned at the reported 2 m by the
    # start-up innovations, which the new clocks' uncertainty explains
    assert before > 10.0**2  # observed: 13.1 m of sigma; the draft held 2 m
    f.P[0:2, 0:2] += np.eye(2) * 1e8  # as after a reset or near a tower: position unknown
    f.process(m)
    assert f.range_variance(m) >= before  # observed: unchanged


def test_without_gnss_the_learned_noise_never_shrinks():
    records, _ = stream()
    f = ekf.EKF()
    last: dict[str, float] = {}
    for m in records:
        f.process(m)
        if m.kind != "pseudorange" or m.t_ns / 1e9 < OUTAGE_S[0] + ekf.EKF().gnss_timeout_ns / 1e9:
            continue
        r = f.range_variance(m)
        assert r >= last.get(m.emitter, 0.0) - 1e-9
        last[m.emitter] = r
    assert last  # the outage had radio records


def test_a_range_near_a_tower_with_an_uncertain_position_carries_its_curvature():
    """Close to a tower, a range is far from linear across the line of sight. Without the
    second-order term a few records of one site collapsed the stated position sigma to metres
    while the error was hundreds (#147, hazardous epochs)."""
    records, _ = stream()
    f = ekf.EKF()
    for m in [m for m in records if m.t_ns / 1e9 < 30.0]:
        f.process(m)
    m = next(m for m in lte(records) if m.t_ns / 1e9 >= 30.0 and m.emitter == "lte:0")
    f.predict(m.t_ns)
    f.P[0:2, 0:2] += np.eye(2) * 300.0**2
    d = f.x[:3] - np.asarray(m.meta["emitter_enu"])
    r = float(np.linalg.norm(d))
    perp = np.array([-d[1], d[0]]) / np.hypot(d[0], d[1])
    sigma_perp2 = perp @ f.P[0:2, 0:2] @ perp
    _, _, R, _ = ekf.MODELS["pseudorange"](f, m)
    extra = R[0, 0] - f.range_variance(m)
    assert extra == pytest.approx(sigma_perp2**2 / (2 * r**2))  # the second-order term
    assert np.sqrt(extra) > 10.0  # observed: 31.9 m of sigma at r = 1,994 m


def test_records_without_rx_clock_are_untouched():
    records, _ = stream(rx_clock=None)
    plain = list(ekf.run(records, noise_tau_s=None))
    assert list(ekf.run(records)) == plain
    assert list(ekf.run(records, range_sigma_floor_m=50.0)) == plain
    assert list(ekf.run_calibrated(records)) == list(ekf.run_calibrated(records, noise_tau_s=None))
