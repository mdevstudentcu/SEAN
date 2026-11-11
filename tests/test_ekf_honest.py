"""The opt-in honest-bound estimators (#226, ADR-0041 Proposed): `ekf-learned-noise` with the slow
part of a radio's range error carried as a Gauss-Markov state per emitter, so the stated
covariance (and HPL) does not shrink below the error once GPS is lost (REQ-02).

Thresholds are regression guards with the observed values in comments, not requirements.
"""

import numpy as np
from test_lte_reported_sigma import outage_stats, stream

from pnt.integrity.jump_guard import JumpGuard
from pnt.nav import ESTIMATORS, ekf, estimate
from pnt.sim.scenario import T0_NS, generate, load


def test_the_honest_estimators_are_opt_in_and_only_configuration():
    assert ESTIMATORS["ekf-honest"].func is ekf.run
    assert ESTIMATORS["ekf-honest"].keywords == ekf.HONEST
    assert ESTIMATORS["ekf-honest-guard"].keywords == {**ekf.HONEST, "jump_guard": JumpGuard}
    # The defaults and the learned-noise estimator are untouched
    assert ESTIMATORS["ekf"] is ekf.run
    assert ESTIMATORS["ekf-learned-noise"].keywords == {"noise_tau_s": ekf.NOISE_TAU_S}
    assert ekf.HONEST["noise_tau_s"] == ekf.NOISE_TAU_S


def test_a_slow_range_error_does_not_make_the_outage_covariance_overconfident_req02():
    """Range error half white, half Gauss-Markov (30 s), reported as 2 m. Taken as white (learned
    noise alone) it is averaged down as if every record were independent: mean NEES above the 2
    of an honest filter. Carried as a state it is not."""
    learned, honest = [], []
    for seed in (1, 2, 3):
        records, truth = stream(white_m=10.0, multipath_m=10.0, seed=seed)
        learned.append(outage_stats(list(ESTIMATORS["ekf-learned-noise"](records)), truth))
        honest.append(outage_stats(list(ESTIMATORS["ekf-honest"](records)), truth))
    # Observed mean NEES over seeds 1-3: learned 3.17 (1.7, 1.7, 6.1), honest 1.27 (0.9, 0.7, 2.2)
    assert np.mean([s[0] for s in learned]) > 2.5  # the failure this guards against
    assert np.mean([s[0] for s in honest]) < 2.0
    assert all(s[1] == 1.0 for s in honest)


def _escapes(name: str, records, truth, after_ns: int) -> int:
    tmap = {g.t_ns: g for g in truth}
    n = 0
    for e in estimate(name, records, origin_llh=SPEC["origin_llh"]):
        g = tmap.get(e.t_ns)
        if g is not None and e.t_ns >= after_ns:
            n += np.hypot(*np.subtract(e.pos_enu, g.pos_enu)[:2]) > e.hpl_m
    return int(n)


SPEC = load("challenge-drone-outage")


def test_drone_outage_error_stays_under_hpl_where_learned_noise_alone_escapes_req02():
    """Tuning seed 1009 of `challenge-drone-outage` (#226's diagnosis): with learned noise alone
    the error escapes HPL 68-79 s after GPS loss; with the slow error as a state it does not.
    Cut at 200 s (GPS lost at 60 s); the filters are causal."""
    sim = generate(SPEC, seed=1009)
    cut = T0_NS + 200 * 1_000_000_000
    records = [m for m in sim.measurements if m.t_ns <= cut]
    loss = T0_NS + 60 * 1_000_000_000
    # Observed: 74 escaping epochs for ekf-learned-noise, 0 for ekf-honest
    assert _escapes("ekf-learned-noise", records, sim.truth, loss) > 20
    assert _escapes("ekf-honest", records, sim.truth, loss) == 0
