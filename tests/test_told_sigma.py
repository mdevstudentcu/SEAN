"""A radio's LTE records report a sigma from timing statistics that can't see multipath (#147).
The opt-in estimators `ekf-measured-sigma` and `ekf-calibrated-measured-sigma` (ADR-0043
Proposed) tell the filter ADR-0036's measured sigma from each record's SNR instead
(`pnt.nav.told_sigma`). Every other record, and every default estimator, keeps the reported sigma.

Thresholds are regression guards with the observed values in comments, not requirements.
"""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.nav import estimate, told_sigma

TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
OUTAGE_S = (90.0, 270.0)


@pytest.mark.parametrize(
    ("snr_db", "expected_m"),
    [
        (13.0, 0.82),  # the fit: sqrt(0.64^2 + 2.28^2 / 10^1.3)
        (-8.0, 5.76),  # the fit's lowest SNR
        (-9.5, 12.4),  # measured bin, -11 to -8 dB
        (-12.0, 24.7),  # measured bin, -14 to -11 dB
        (-20.0, 49.4),  # below every measured bin: the stated TBC value
    ],
)
def test_white_sigma_is_adr0036s_measured_model(snr_db, expected_m):
    assert told_sigma.white_sigma_m(snr_db, 20) == pytest.approx(expected_m, abs=0.01)
    # a 1 Hz record averages ten 10 Hz records' white noise
    ten_hz = told_sigma.white_sigma_m(snr_db, 20)
    assert told_sigma.white_sigma_m(snr_db, 200) == pytest.approx(ten_hz / np.sqrt(10), 1e-9)


def test_correlated_part_is_not_averaged_down_by_a_faster_record_rate():
    """The same information per second at 1 and 10 Hz: 10 records of 77.4 m, or one of 24.6 m."""
    assert told_sigma.corr_sigma_m(200) == pytest.approx(24.6, abs=0.05)
    assert told_sigma.corr_sigma_m(20) / np.sqrt(10) == pytest.approx(24.5, abs=0.05)


def _record(kind="pseudorange", **meta):
    base = {"rx_clock": "rtl0", "snr_db": -2.0, "n_epochs": 200}
    return Measurement(t_ns=0, source="lte", kind=kind, emitter="lte:1:2", value=(1.0,),
                       sigma=(2.0,), meta=base | meta)  # fmt: skip


def test_only_a_front_ends_pseudoranges_are_retold():
    assert told_sigma.retold(_record(), "adr0036").sigma == (
        pytest.approx(told_sigma.sigma_m(-2.0, 200)),
    )
    for m in (
        _record(kind="doppler"),
        _record(snr_db=None),  # sim range hearing: no SNR
        _record(n_epochs=None),
        Measurement(
            t_ns=0,
            source="lte",
            kind="pseudorange",
            emitter="lte:sim1",
            value=(1.0,),
            sigma=(2.0,),
            meta={"snr_db": -2.0, "n_epochs": 200},
        ),  # fmt: skip
    ):
        assert told_sigma.retold(m, "adr0036") is m
    with pytest.raises(ValueError):
        told_sigma.retold(_record(), "made-up")


def stream(meta: dict, told_m=2.0, white_m=10.0, multipath_m=10.0, tau_s=3.0, seed=1):
    """Receiver circling the origin. GNSS at 5 Hz outside the outage, baro at 10 Hz, every tower
    at 1 Hz with its own clock, white noise and a Gauss-Markov error per tower (ADR-0036's
    10 m, 3 s at rest by default). The records
    report `told_m` and carry `meta`. Returns (measurements, truth {t_ns: pos})."""
    rng = np.random.default_rng(seed)
    offsets = rng.uniform(-500, 500, len(TOWERS))
    mp = np.zeros(len(TOWERS))
    phi = np.exp(-1.0 / tau_s)
    meas, truth = [], {}
    for k in range(int(OUTAGE_S[1] * 10)):
        t, t_ns = k / 10, k * 100_000_000
        a = 0.05 * t
        pos = np.array([100 * np.cos(a), 100 * np.sin(a), 30.0])
        truth[t_ns] = pos
        meas.append(Measurement(t_ns=t_ns, source="baro", kind="altitude",
                                value=(30.0 + rng.normal(0, 0.5),), sigma=(0.5,)))  # fmt: skip
        if k % 2 == 0 and not OUTAGE_S[0] <= t:
            fix = tuple(pos + rng.normal(0, 2, 3))
            meas.append(Measurement(t_ns=t_ns, source="gnss", kind="position_enu", value=fix,
                                    sigma=(2.0, 2.0, 2.0)))  # fmt: skip
        if k % 10 == 0:
            mp = phi * mp + rng.normal(0, multipath_m * np.sqrt(1 - phi**2), len(TOWERS))
            for i, e in enumerate(TOWERS):
                rho = np.linalg.norm(pos - e) + offsets[i] + 40.0 * t + mp[i]
                rho += rng.normal(0, white_m)
                m = {"emitter_enu": [float(x) for x in e]} | meta
                meas.append(Measurement(t_ns=t_ns, source="lte", kind="pseudorange",
                                        emitter=f"lte:{i}", value=(float(rho),), sigma=(told_m,),
                                        meta=m))  # fmt: skip
    return meas, truth


def outage_nees(estimates, truth) -> float:
    """Mean horizontal NEES in the outage: about 2 when the covariance is honest."""
    nees = []
    for e in estimates:
        if e.t_ns / 1e9 < OUTAGE_S[0] or e.t_ns not in truth:
            continue
        d = np.subtract(e.pos_enu, truth[e.t_ns])[:2]
        nees.append(d @ np.linalg.solve(np.reshape(e.pos_cov, (3, 3))[:2, :2], d))
    return float(np.mean(nees))


RADIO = {"rx_clock": "rtl0", "snr_db": 0.0, "n_epochs": 200}


@pytest.mark.parametrize(
    ("measured", "default", "observed"),
    [
        # mean outage NEES observed, seed 1: measured sigma / reported 2 m believed
        ("ekf-measured-sigma", "ekf", (1.06, 42.8)),
        ("ekf-calibrated-measured-sigma", "ekf-calibrated", (0.16, 46.7)),
    ],
)
def test_measured_sigma_is_not_overconfident_where_the_reported_sigma_is(
    measured, default, observed
):
    meas, truth = stream(RADIO)
    honest = outage_nees(list(estimate(measured, meas)), truth)
    believed = outage_nees(list(estimate(default, meas)), truth)
    assert honest < 3.0  # regression guard: 2 is honest
    assert believed > 10 * honest  # regression guard: the reported 2 m is far too small


@pytest.mark.parametrize(
    ("measured", "default"),
    [("ekf-measured-sigma", "ekf"), ("ekf-calibrated-measured-sigma", "ekf-calibrated")],
)
def test_records_without_a_front_ends_fields_keep_the_reported_sigma(measured, default):
    """Without `rx_clock` (sim-shaped records) or `snr_db` the opt-in estimator is the default."""
    for meta in ({"snr_db": 0.0, "n_epochs": 200}, {"rx_clock": "rtl0"}):
        meas, _ = stream(meta)
        a, b = list(estimate(measured, meas)), list(estimate(default, meas))
        assert [(e.pos_enu, e.pos_cov, e.hpl_m) for e in a] == [
            (e.pos_enu, e.pos_cov, e.hpl_m) for e in b
        ]
