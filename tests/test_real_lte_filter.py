"""The EKF and real LTE records (#214, #246, ADR-0048 Proposed).

- a: a real capture's records (`meta.sample_index`) are told ADR-0036's measured sigma by
  default; the sim's front-end-shaped records keep the sigma they report.
- b: `gnss_readmit` (opt-in) lets GNSS back in when towers told too tight keep it out, and never
  when the GNSS stream jumps, returns after a gap or the towers are honest.
- d: `heard_cell_radius_m` (opt-in) keeps the position within that radius of a heard cell.

Thresholds are regression guards with the observed values in comments, not requirements.
"""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.integrity.gnss_readmit import GnssReadmit
from pnt.nav import configured, ekf, estimate

TOWERS = np.array([[2000.0, 0, 50], [-1000, 1800, 60], [-900, -1700, 40], [300, 2500, 45]])
RADIO = {"rx_clock": "rtl0", "snr_db": 0.0, "n_epochs": 20}


def stream(
    meta: dict,
    told_m=2.0,
    wander_m=0.0,
    white_m=2.0,
    duration_s=120.0,
    gnss=lambda t: np.zeros(3),
    gnss_gap_s=(),
    lte_pos=lambda t: np.zeros(3),
    arc_step=None,
    seed=1,
):
    """A static receiver at the origin. GNSS at 1 Hz (sigma 3 m), offset by `gnss(t)` and absent
    in `gnss_gap_s`; baro at 10 Hz; every tower at 10 Hz from one radio with its own clock,
    white noise `white_m` and a random walk of `wander_m` per sqrt(s), told `told_m`, ranging to
    `lte_pos(t)` (the towers agree on a wrong position when it is not the origin). `arc_step`
    (tower, time s, step m): that tower's range steps and its `meta.arc` goes from 0 to 1."""
    rng = np.random.default_rng(seed)
    offsets = rng.uniform(-500, 500, len(TOWERS))
    walk = np.zeros(len(TOWERS))
    meas = []
    for k in range(int(duration_s * 10)):
        t, t_ns = k / 10, k * 100_000_000
        meas.append(Measurement(t_ns=t_ns, source="baro", kind="altitude",
                                value=(rng.normal(0, 0.5),), sigma=(0.5,)))  # fmt: skip
        gap = bool(gnss_gap_s) and gnss_gap_s[0] <= t < gnss_gap_s[1]
        if k % 10 == 0 and not gap:
            fix = tuple(gnss(t) + rng.normal(0, 3.0, 3))
            meas.append(Measurement(t_ns=t_ns, source="gnss", kind="position_enu", value=fix,
                                    sigma=(3.0, 3.0, 3.0)))  # fmt: skip
        walk += rng.normal(0, wander_m * np.sqrt(0.1), len(TOWERS))
        for i, e in enumerate(TOWERS):
            rho = np.linalg.norm(e - lte_pos(t)) + offsets[i] + 40.0 * t + walk[i]
            rho += rng.normal(0, white_m)
            m = {"emitter_enu": [float(x) for x in e]} | meta
            if arc_step is not None and i == arc_step[0]:
                m["arc"] = int(t >= arc_step[1])
                rho += arc_step[2] if t >= arc_step[1] else 0.0
            meas.append(Measurement(t_ns=t_ns, source="lte", kind="pseudorange",
                                    emitter=f"lte:{i}", value=(float(rho),), sigma=(told_m,),
                                    meta=m))  # fmt: skip
    return meas


def outputs(estimates):
    return [(e.pos_enu, e.pos_cov, e.hpl_m) for e in estimates]


def excluded(estimates) -> float:
    """Share of epochs after 10 s that carry `gnss_excluded`."""
    late = [e for e in estimates if e.t_ns >= 10_000_000_000]
    return float(np.mean(["gnss_excluded" in e.flags for e in late]))


# --- a: a real capture's records get the measured sigma by default -----------------------------
def test_a_real_captures_records_are_told_the_measured_sigma_by_default():
    meas = stream(RADIO | {"sample_index": 0}, duration_s=30.0)
    measured = outputs(estimate("ekf-measured-sigma", meas))
    assert outputs(estimate("ekf", meas)) == measured
    as_main = configured(ekf.run, capture_sigma_model=None)
    assert outputs(estimate(as_main, meas)) != measured


def test_the_sims_front_end_shaped_records_keep_their_reported_sigma():
    """No `sample_index` (sim/lte_front_end.py leaves it out): `ekf` is main's `ekf`."""
    meas = stream(RADIO, duration_s=30.0)
    as_main = configured(ekf.run, capture_sigma_model=None)
    assert outputs(estimate("ekf", meas)) == outputs(estimate(as_main, meas))


def test_calibrated_measured_keeps_the_reported_sigma_for_a_real_capture():
    """`ekf-calibrated-measured` carries ADR-0036's correlated part as a state already."""
    meas = stream(RADIO | {"sample_index": 0}, duration_s=30.0)
    off = configured(ekf.run_calibrated_measured, capture_sigma_model=None)
    assert outputs(estimate("ekf-calibrated-measured", meas)) == outputs(estimate(off, meas))


# --- c: a new arc's own range bias, by default for a real capture ----------------------------
STEP = {"arc_step": (0, 70.0, 800.0), "gnss_gap_s": (60.0, 120.0), "told_m": 5.0, "white_m": 5.0}


def test_a_real_captures_new_arc_gets_its_own_bias_by_default():
    meas = stream(RADIO | {"sample_index": 0}, **STEP)
    on = configured(ekf.run, arc_bias=True)
    assert outputs(estimate("ekf", meas)) == outputs(estimate(on, meas))
    off = configured(ekf.run, arc_bias=False)
    assert outputs(estimate("ekf", meas)) != outputs(estimate(off, meas))


def test_the_sims_records_keep_arc_bias_off_by_default():
    meas = stream(RADIO, **STEP)
    off = configured(ekf.run, arc_bias=False)
    assert outputs(estimate("ekf", meas)) == outputs(estimate(off, meas))


# --- b: GNSS re-admission ---------------------------------------------------------------------
TIGHT = {"told_m": 2.0, "wander_m": 6.0}  # towers told 2 m that wander 6 m per sqrt(s)
MAIN = {"capture_sigma_model": None}
READMIT = configured(ekf.run, gnss_readmit=GnssReadmit)


def test_towers_told_too_tight_no_longer_keep_honest_gnss_out():
    meas = stream(RADIO, **TIGHT)
    latched = excluded(list(estimate("ekf", meas)))
    readmitted = excluded(list(estimate(READMIT, meas)))
    assert latched > 0.5  # regression guard: observed 1.00, the latch of #246
    assert readmitted < 0.25  # regression guard: observed 0.08 (the first wait_s, then none)


def test_readmission_changes_nothing_when_the_gate_never_rejects_gnss():
    meas = stream(RADIO, told_m=3.0, wander_m=0.0, duration_s=60.0)
    assert excluded(list(estimate("ekf", meas))) == 0.0
    assert outputs(estimate(READMIT, meas)) == outputs(estimate("ekf", meas))


def jump(t):
    return np.array([300.0, 0.0, 0.0]) if t >= 40.0 else np.zeros(3)


def ramp(t):
    return np.array([2.0, 2.0, 0.0]) * max(0.0, t - 40.0)


def readmitted(meas) -> tuple[list[float], list]:
    """Times (s) at which `GnssReadmit` re-admitted GNSS with a reset, and the estimates."""
    f = ekf.EKF(gnss_readmit=GnssReadmit)
    est = []
    for m in meas:
        f.process(m)
        if f.x is not None:
            est.append(f.estimate())
    return [t / 1e9 for t in f.readmit.readmits], est


def used_after(estimates, t_s=41.0) -> float:
    """Share of estimates from `t_s` on with GNSS position in use."""
    late = [e for e in estimates if e.t_ns >= t_s * 1e9]
    bad = ("gnss_excluded", "gnss_unavailable")
    return float(np.mean([not any(f in e.flags for f in bad) for e in late]))


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        # a GNSS jump while it steers, against the same towers told too tight
        ("jump", {**TIGHT, "gnss": jump}),
        # GNSS that returns offset after a gap: #191's hole stays closed
        ("after a gap", {**TIGHT, "gnss": jump, "gnss_gap_s": (35.0, 45.0)}),
        # a ramp against honest towers (told what they are): they may refute it
        ("ramp, honest towers", {"told_m": 2.0, "gnss": ramp}),
    ],
)
def test_readmission_never_lets_in_what_it_must_not(label, kwargs):
    """From the fault on (40 s): no re-admission, and GNSS in use no more than without the rule.
    Before it, the tight towers' latch may be undone."""
    meas = stream(RADIO, **kwargs)
    times, est = readmitted(meas)
    assert all(t < 40.0 for t in times), label
    assert used_after(est) <= used_after(list(estimate("ekf", meas))) + 0.02, label


def test_honest_gnss_against_the_same_towers_stays_in():
    """The control for the cases above: with no fault, GNSS is in use after 40 s."""
    meas = stream(RADIO, **TIGHT)
    assert used_after(readmitted(meas)[1]) > 0.8  # regression guard: observed 0.97
    assert used_after(list(estimate("ekf", meas))) < 0.2  # regression guard: observed 0.00


# --- d: a heard cell's coverage bound ---------------------------------------------------------
def test_a_heard_cell_bounds_how_far_bad_records_drag_the_position():
    """In a GNSS outage the towers agree on a position running away at 50 m/s: without the bound
    the filter follows it kilometres; with a 3 km radius it stays near the heard cells' disks."""
    away = lambda t: np.array([50.0, 0.0, 0.0]) * max(0.0, t - 60.0)  # noqa: E731
    out = stream(RADIO, told_m=5.0, white_m=5.0, duration_s=200.0, gnss_gap_s=(60.0, 200.0),
                 lte_pos=away)  # fmt: skip
    far = {}
    for label, fn in (("off", ekf.run), ("on", configured(ekf.run, heard_cell_radius_m=3000.0))):
        est = list(estimate(fn, out))
        far[label] = max(  # farthest from a heard cell (all four are heard throughout)
            max(float(np.hypot(*(np.subtract(e.pos_enu, t)[:2]))) for t in TOWERS) for e in est
        )
    assert far["off"] > 5000.0  # regression guard
    assert far["on"] < 3600.0  # regression guard: the radius, give or take its soft sigma
