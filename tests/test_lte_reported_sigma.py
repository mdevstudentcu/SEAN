"""A radio's LTE records report a sigma from timing statistics, which can't see multipath, so it
can be far too small (#147). The opt-in estimators (ADR-0039) learn the range noise of such
records (`meta.rx_clock`) from their innovations, with the reported sigma as a lower bound only.
Records without `rx_clock` (the simulator's) keep their reported sigma exactly, and the default
estimators keep every sim record's reported sigma. A real capture's record (`meta.sample_index`),
which ADR-0050 retells, starts the learner at its retold sigma and keeps ADR-0050's bias per new
arc (ADR-0039 amendment, Proposed).

Thresholds are regression guards with the observed values in comments, not requirements.
"""

import numpy as np
import pytest
from msgspec.structs import replace

from pnt.core.measurement import Measurement
from pnt.nav import ESTIMATORS, configured, ekf, told_sigma

TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
OUTAGE_S = (90.0, 270.0)


def learning(**config):
    """The filter of `ekf-learned-noise`: learning on, with its memory."""
    return ekf.EKF(noise_tau_s=ekf.NOISE_TAU_S, **config)


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
    ("learner", "default", "observed"),
    [
        # (mean NEES, HPL bound rate) observed in the outage, seed 1: learned / reported believed
        ("ekf-learned-noise", "ekf", ((1.67, 1.0), (59.7, 0.42))),
        ("ekf-calibrated-learned-noise", "ekf-calibrated", ((1.39, 1.0), (82.7, 0.27))),
    ],
)
def test_learning_the_noise_keeps_an_optimistic_sigma_from_making_it_overconfident(
    learner, default, observed
):
    records, truth = stream()  # 20 m of range error in all, reported as 2 m
    learned = outage_stats(list(ESTIMATORS[learner](records)), truth)
    told = outage_stats(list(ESTIMATORS[default](records)), truth)
    # Regression guards with margin around the observed values, not requirements
    assert told[0] > 30.0 and told[1] < 0.6  # the failure this guards against
    assert learned[0] < 10.0 and learned[1] > 0.95


def test_an_honest_reported_sigma_is_learned_down_to():
    records, _ = stream(told_m=1.0, white_m=1.0, multipath_m=0.0)
    f = learning()
    for m in records:
        f.process(m)
    # Innovations no larger than the reported 1 m: the learned variance falls from the prior's
    # 40^2 towards 1; what is left is the prior's one-sample share of the learned memory
    r = f.range_variance([m for m in records if m.kind == "pseudorange"][-1])
    assert r < 0.05 * 40.0**2  # observed: 64.1 m^2 (4 % of the prior)


def lte(records):
    return [m for m in records if m.kind == "pseudorange"]


def test_a_cells_first_records_carry_the_prior_not_the_reported_sigma():
    """The reported 2 m counted as a sample let the first two records pin the dongle clock's
    drift, after which the gate rejected the cell for good (#147)."""
    records, _ = stream()
    assert learning().range_variance(lte(records)[0]) == pytest.approx(40.0**2)
    assert learning(noise_prior_m=25.0).range_variance(lte(records)[0]) == pytest.approx(25.0**2)


def test_an_uncertain_state_does_not_pull_the_learned_noise_down():
    """An innovation that the state uncertainty explains says nothing about the noise. Counted,
    its large negative sample collapsed the learned variance to the reported sigma (#147)."""
    records, _ = stream()
    gps = [m for m in records if m.t_ns / 1e9 < 60.0]
    f = learning()
    for m in gps:
        f.process(m)
    m = next(m for m in lte(records) if m.t_ns / 1e9 >= 60.0)
    before = f.range_variance(m)
    # 20 m of range error in the stream: learned, not pinned at the reported 2 m by the
    # start-up innovations, which the new clocks' uncertainty explains
    assert before > 10.0**2  # observed: 13.5 m of sigma; the draft held 2 m
    f.P[0:2, 0:2] += np.eye(2) * 1e8  # as after a reset or near a tower: position unknown
    f.process(m)
    assert f.range_variance(m) >= before  # observed: unchanged


def test_without_gnss_the_learned_noise_never_shrinks():
    records, _ = stream()
    f = learning()
    last: dict[str, float] = {}
    for m in records:
        f.process(m)
        if m.kind != "pseudorange" or m.t_ns / 1e9 < OUTAGE_S[0] + ekf.EKF().gnss_timeout_ns / 1e9:
            continue
        r = f.range_variance(m)
        assert r >= last.get(m.emitter, 0.0) - 1e-9
        last[m.emitter] = r
    assert last  # the outage had radio records


def curvature_case(extra_sigma_m):
    """A radio record 30 s into the stream, after the position variance is raised by
    `extra_sigma_m` squared per axis. Returns (filter, record, sigma_perp^2, range r)."""
    records, _ = stream()
    f = learning()
    for m in [m for m in records if m.t_ns / 1e9 < 30.0]:
        f.process(m)
    m = next(m for m in lte(records) if m.t_ns / 1e9 >= 30.0 and m.emitter == "lte:0")
    f.predict(m.t_ns)
    f.P[0:2, 0:2] += np.eye(2) * extra_sigma_m**2
    d = f.x[:3] - np.asarray(m.meta["emitter_enu"])
    perp = np.array([-d[1], d[0]]) / np.hypot(d[0], d[1])
    return f, m, perp @ f.P[0:2, 0:2] @ perp, float(np.linalg.norm(d))


def test_a_range_carries_its_curvature():
    """A range is linear in position only while the uncertainty across the line of sight is
    small against the range: its second-order term is part of R (#147, hazardous epochs)."""
    f, m, s2, r = curvature_case(100.0)
    _, _, R, _ = ekf.MODELS["pseudorange"](f, m)
    extra = R[0, 0] - f.range_variance(m)
    assert extra == pytest.approx(s2**2 / (2 * r**2))
    assert extra > 0.0  # observed: 3.6 m of sigma at r = 1,994 m


def test_a_range_too_curved_for_a_linear_update_is_not_used():
    """Near a tower with a drifted position the linear update claims far more than the range
    says: a few records of one site collapsed the stated sigma while the error was hundreds."""
    f, m, s2, r = curvature_case(300.0)
    assert s2**2 / (2 * r**2) > f.range_variance(m)  # observed: 31.9 m against 11.7 m of noise
    assert ekf.MODELS["pseudorange"](f, m) is None


def test_records_without_rx_clock_are_untouched():
    records, _ = stream(rx_clock=None)
    plain = list(ekf.run(records))
    assert list(ESTIMATORS["ekf-learned-noise"](records)) == plain
    assert list(ekf.run(records, range_sigma_floor_m=50.0)) == plain
    calibrated = list(ekf.run_calibrated(records))
    assert list(ESTIMATORS["ekf-calibrated-learned-noise"](records)) == calibrated


@pytest.mark.parametrize("name", ["ekf", "ekf-calibrated", "ekf-mhss", "ekf-imu"])
def test_default_estimators_keep_the_reported_sigma(name, monkeypatch):
    """Opt-in only (ADR-0039): on a radio's records whose reported sigma changes from record to
    record, a default estimator gives exactly the output of a filter whose range noise is the
    reported sigma squared, that learns nothing and that uses every range."""
    records, _ = stream()
    records = [
        m if m.kind != "pseudorange" else replace(m, sigma=(2.0 + (m.t_ns // 10**9) % 3,))
        for m in records
    ]
    default = list(ESTIMATORS[name](records))

    def reported(self, m, mp):
        return m.sigma[0] ** 2

    def never(self, *args):
        raise AssertionError("a default estimator learned a range noise or its curvature")

    monkeypatch.setattr(ekf.EKF, "range_noise", reported)
    monkeypatch.setattr(ekf.EKF, "_learn_noise", never)
    monkeypatch.setattr(ekf.EKF, "range_curvature", never)
    assert list(ESTIMATORS[name](records)) == default


def test_the_learning_estimators_are_opt_in():
    assert ESTIMATORS["ekf"] is ekf.run
    assert ESTIMATORS["ekf-calibrated"] is ekf.run_calibrated
    assert "noise_tau_s" not in ekf.CALIBRATED
    assert ekf.EKF().noise_tau_ns is None
    assert ESTIMATORS["ekf-learned-noise"].keywords == {"noise_tau_s": ekf.NOISE_TAU_S}
    learned = ESTIMATORS["ekf-calibrated-learned-noise"]
    assert learned.keywords == {"noise_tau_s": ekf.CALIBRATED_NOISE_TAU_S}
    records, _ = stream()
    assert list(learned(records)) != list(ekf.run_calibrated(records))  # it does learn


# --- a real capture's records after ADR-0050 (ADR-0039 amendment, Proposed) -------------------
CAPTURE = {"snr_db": 10.0, "n_epochs": 200}  # 1 s of 5 ms epochs: every record told the same
ARC_STEP = (0, 100.0, 300.0)  # tower 0's range steps 300 m at 100 s (in the outage), a new arc


def radio_records(capture: bool):
    """`stream()`'s radio records with an SNR and length, tower 0 re-found as a new arc with a
    range step at `ARC_STEP`; with `capture`, each record indexes its IQ file (`sample_index`)."""
    records, _ = stream()
    tower, t_s, step = ARC_STEP
    out = []
    for k, m in enumerate(records):
        if m.kind == "pseudorange":
            meta = m.meta | CAPTURE | ({"sample_index": k} if capture else {})
            value = m.value
            if m.emitter == f"lte:{tower}":
                meta["arc"] = int(m.t_ns >= t_s * 1e9)
                value = (m.value[0] + (step if meta["arc"] else 0.0),)
            m = replace(m, meta=meta, value=value)
        out.append(m)
    return out


@pytest.mark.parametrize(
    ("name", "run", "tau_s"),
    [
        ("ekf-learned-noise", ekf.run, ekf.NOISE_TAU_S),
        ("ekf-calibrated-learned-noise", ekf.run_calibrated, ekf.CALIBRATED_NOISE_TAU_S),
    ],
)
def test_a_real_capture_starts_the_learner_at_its_retold_sigma_and_keeps_the_arc_bias(
    name, run, tau_s
):
    """On a real capture's records the learning estimator equals one that retells every record,
    starts from the retold sigma and gives each new arc its own bias, on the same records
    without `sample_index`. Starting from 40 m, or without the arc bias, it would differ."""
    told = told_sigma.sigma_m(CAPTURE["snr_db"], CAPTURE["n_epochs"])  # 24.6 m
    learned = list(ESTIMATORS[name](radio_records(capture=True)))
    sim = radio_records(capture=False)

    def explicit(**kw):
        config = {"noise_tau_s": tau_s, "told_sigma_model": "adr0036", "arc_bias": True}
        return list(configured(run, **(config | kw))(sim))

    assert learned == explicit(noise_prior_m=told)
    assert learned != explicit(noise_prior_m=40.0)
    assert learned != explicit(noise_prior_m=told, arc_bias=False)


def test_a_sim_record_keeps_the_40_m_prior_and_no_arc_bias():
    """Without `sample_index` nothing of ADR-0050 reaches the learner: it is the pre-ADR-0050
    learner (reported sigma, 40 m prior, no arc bias)."""
    sim = radio_records(capture=False)
    before = configured(ekf.run, noise_tau_s=ekf.NOISE_TAU_S, capture_sigma_model=None,
                        arc_bias=False, noise_prior_m=40.0)  # fmt: skip
    assert list(ESTIMATORS["ekf-learned-noise"](sim)) == list(before(sim))
    f = learning()
    lte_sim = next(m for m in sim if m.kind == "pseudorange")
    assert f.noise_prior_variance(lte_sim) == 40.0**2
    lte_capture = told_sigma.retold(replace(lte_sim, meta=lte_sim.meta | {"sample_index": 0}),
                                    "adr0036")  # fmt: skip
    assert f.noise_prior_variance(lte_capture) == pytest.approx(lte_capture.sigma[0] ** 2)
