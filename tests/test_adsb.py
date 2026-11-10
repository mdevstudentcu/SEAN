"""ADS-B traffic in the sim and the interference early warning (#91, P6, ADR-0032)."""

import numpy as np
import pytest

from pnt.core.measurement import Measurement
from pnt.integrity import adsb as warning
from pnt.integrity.dependency import GNSS_DERIVED, tag_of
from pnt.integrity.mhss import MHSS, Params
from pnt.nav import ekf
from pnt.sim import adsb
from pnt.sim.scenario import T0_NS, generate, load

CLEAN, JAMMED, SPOOFED = (
    "uc02-yow-approach-adsb",
    "uc02-yow-approach-adsb-jammed",
    "uc02-yow-approach-adsb-spoofed",
)
# Our own receiver reaches the jammer's 6 km ring at about 115 s and the spoofer's 3 km circle at
# about 159 s (the scenario files' geometry)
OWN_JAM_ONSET_S, OWN_SPOOF_ENTRY_S = 115.0, 159.0


def _reports(name: str, seed: int = 0) -> dict[str, list[Measurement]]:
    run = generate(load(name), seed=seed)
    out: dict[str, list[Measurement]] = {}
    for m in run.measurements:
        if m.kind == "adsb_report":
            out.setdefault(m.emitter, []).append(m)
    return out


def _s(m: Measurement) -> float:
    return (m.t_ns - T0_NS) / 1e9


# --- sim -----------------------------------------------------------------------------------
def test_quality_classes_follow_do260b():
    assert adsb.nacp_of(2.0) == 11 and adsb.nacp_of(7.3) == 10 and adsb.nacp_of(31.0) == 8
    assert adsb.nacp_of(1e6) == 0
    assert adsb.nic_of(150.0) == 8 and adsb.nic_of(400.0) == 6 and adsb.nic_of(1e6) == 0
    assert adsb.sigma_of_nacp(10) == pytest.approx(10.0 / adsb.K95)


def test_reports_are_gnss_derived_and_follow_the_icd():
    reps = _reports(CLEAN)
    assert set(reps) == {f"adsb:c0a00{i}" for i in range(1, 6)}
    m = reps["adsb:c0a001"][0]
    assert m.source == "adsb" and len(m.value) == 5 and m.receiver == "payload"
    assert tag_of(m) == GNSS_DERIVED  # ADR-0024: never confirms our GNSS


def test_clean_traffic_reports_good_quality_except_legacy_and_dips():
    reps = _reports(CLEAN)
    assert {(m.value[3], m.value[4]) for m in reps["adsb:c0a005"]} == {(6.0, 5.0)}  # legacy
    for icao in ("adsb:c0a001", "adsb:c0a003"):
        q = np.array([m.value[3:] for m in reps[icao]])
        good = (q[:, 0] >= 9) & (q[:, 1] >= 7)
        assert good.mean() > 0.9  # the rest are nuisance dips (TBC rate): a regression guard
        assert set(q[~good, 0]) <= {7.0}


def test_traffic_has_its_own_random_stream():
    # Adding ADS-B to a scenario leaves every other source's draws as they were
    spec = load(CLEAN)
    without = {**spec, "sources": {k: v for k, v in spec["sources"].items() if k != "adsb"}}
    a = [m for m in generate(spec, seed=3).measurements if m.source != "adsb"]
    b = generate(without, seed=3).measurements
    assert a == b


def test_jammer_degrades_the_aircraft_ahead_before_us_req04():
    reps = _reports(JAMMED)
    ahead = reps["adsb:c0a001"]  # 3 NM ahead on the same final
    first_bad = min(_s(m) for m in ahead if m.value[3] < 9 and _s(m) > 20)
    assert first_bad < OWN_JAM_ONSET_S - 60
    assert any(m.value[3:] == (0.0, 0.0) for m in ahead)  # lost inside the 2 km radius
    departure = reps["adsb:c0a004"]  # climbs away from the jammer
    assert all(m.value[3] >= 9 or m.value[3] == 7 for m in departure)


def test_spoofer_moves_aircraft_and_keeps_their_quality():
    clean, spoofed = _reports(CLEAN)["adsb:c0a001"], _reports(SPOOFED)["adsb:c0a001"]
    jump = [np.subtract(b.value[:2], a.value[:2]) for a, b in zip(clean, spoofed, strict=True)]
    moved = [np.allclose(d, [600.0, 600.0]) for d in jump]
    assert any(moved) and not all(moved)
    assert {b.value[3:] for b, mv in zip(spoofed, moved, strict=True) if mv} <= {
        a.value[3:] for a in clean
    }


# --- the monitor ---------------------------------------------------------------------------
def _rep(icao: str, t_s: float, e: float, n: float, nacp=10, nic=8) -> Measurement:
    return Measurement(
        t_ns=int(t_s * 1e9), source="adsb", kind="adsb_report", emitter=f"adsb:{icao}",
        value=(e, n, 1000.0, float(nacp), float(nic)), sigma=(4.0, 4.0, 6.0, 0.0, 0.0),
    )  # fmt: skip


def _fly(mon, icao, t0, t1, bad_from=None, bad_to=None, e0=0.0, ve=100.0):
    for t in np.arange(t0, t1, 1.0):
        bad = bad_from is not None and bad_from <= t < (bad_to or np.inf)
        mon.update(_rep(icao, t, e0 + ve * t, 0.0, *((7, 6) if bad else (10, 8))))


def test_one_aircraft_dropping_is_not_enough():
    mon = warning.AdsbMonitor()
    _fly(mon, "a1", 0, 60, bad_from=20)
    _fly(mon, "a2", 0, 60)
    w = mon.warning(int(60e9))
    assert w.dropped == ["adsb:a1"] and not w.on


def test_two_aircraft_dropping_for_the_hold_warn():
    mon = warning.AdsbMonitor()
    _fly(mon, "a1", 0, 60, bad_from=20)
    _fly(mon, "a2", 0, 60, bad_from=30, e0=5000.0)
    assert mon.warning(int(60e9)).on
    assert not mon.warning(int(60e9 + 301e9)).on  # past memory_s


def test_brief_dips_and_legacy_avionics_do_not_count():
    mon = warning.AdsbMonitor()
    _fly(mon, "a1", 0, 60, bad_from=20, bad_to=24)  # 4 s dip, under hold_s
    for t in range(60):  # never reports good quality
        mon.update(_rep("a2", t, 100.0 * t, 1000.0, nacp=6, nic=5))
    assert mon.warning(int(60e9)).dropped == []


def test_far_aircraft_do_not_count():
    mon = warning.AdsbMonitor(warning.Params(min_aircraft=1))
    _fly(mon, "a1", 0, 60, bad_from=20, e0=80_000.0)
    assert not mon.warning(int(60e9), own_en=(0.0, 0.0)).on
    assert mon.warning(int(60e9), own_en=(80_000.0, 0.0)).on


def test_track_jump_with_good_quality_is_a_spoof_and_one_bad_decode_is_not():
    mon = warning.AdsbMonitor()
    _fly(mon, "a1", 0, 30)
    for t in range(30, 40):  # moved 850 m and stays there, quality unchanged
        mon.update(_rep("a1", t, 100.0 * t + 600.0, 600.0))
    assert mon.warning(int(40e9)).jumped == ["adsb:a1"] and mon.warning(int(40e9)).on
    mon = warning.AdsbMonitor()
    _fly(mon, "a1", 0, 30)
    mon.update(_rep("a1", 30, 3000.0 + 600.0, 600.0))  # one bad decode, then back on track
    _fly(mon, "a1", 31, 40)
    assert mon.warning(int(40e9)).jumped == []


def test_clean_traffic_raises_no_warning():
    # Regression guard on the placeholder dips, not a false-alert requirement (REQ-04's is TBD)
    for seed in range(5):
        mon = warning.AdsbMonitor()
        on = []
        for reps in [_reports(CLEAN, seed)]:
            for m in sorted((m for r in reps.values() for m in r), key=lambda m: m.t_ns):
                mon.update(m)
                on.append(mon.warning(m.t_ns).on)
        assert not any(on), seed


# --- the integrity monitor ------------------------------------------------------------------
def _mhss(name: str, raise_prior: bool):
    spec = load(name)
    run = generate(spec, seed=0)
    p = Params() if raise_prior else Params(p_gnss_cm_warned=Params().p_gnss_cm)
    return list(ekf.run(run.measurements, origin_llh=spec["origin_llh"],
                        monitor=lambda f: MHSS(f, params=p)))  # fmt: skip


def test_warning_raises_the_gnss_prior_before_our_gnss_degrades_req04():
    on, off = _mhss(JAMMED, True), _mhss(JAMMED, False)
    warned = [(e.t_ns - T0_NS) / 1e9 for e in on if "adsb_interference" in e.flags]
    assert warned and warned[0] < OWN_JAM_ONSET_S
    k = next(i for i, e in enumerate(on) if "adsb_interference" in e.flags)
    before = slice(k - 20, k - 1)
    assert [e.hpl_m for e in on[before]] == [e.hpl_m for e in off[before]]  # same until it warns
    assert on[k + 10].hpl_m > off[k + 10].hpl_m  # then the gnss-cm term is weighted up
    assert [e.pos_enu for e in on] == [e.pos_enu for e in off]  # the prior moves no position
