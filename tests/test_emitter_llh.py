import math

import numpy as np
import pytest

from pnt.core import frames
from pnt.metrics import score
from pnt.nav import baseline
from pnt.sim.scenario import T0_NS, generate, load

CARLETON = (45.3876, -75.6960, 70.0)
YOW = (45.3225, -75.6692, 114.0)  # Ottawa airport reference point (approx.)


def haversine_m(a, b, r=6_371_000.0):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((la2 - la1) / 2) ** 2
        + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def test_carleton_to_yow_distance_matches_great_circle():
    enu = frames.llh_to_enu(YOW, CARLETON)
    horizontal = math.hypot(enu[0], enu[1])
    assert horizontal == pytest.approx(haversine_m(CARLETON, YOW), rel=5e-3)  # ~7.5 km
    assert enu[1] < 0 and enu[0] > 0  # YOW is south-east of campus


def test_emitter_enu_prefers_local_and_converts_llh():
    assert frames.emitter_enu({"emitter_enu": [1, 2, 3]}, None).tolist() == [1, 2, 3]
    e = frames.emitter_enu({"emitter_llh": list(YOW)}, CARLETON)
    assert np.allclose(e, frames.llh_to_enu(YOW, CARLETON))
    assert frames.emitter_enu({}, CARLETON) is None
    with pytest.raises(ValueError):
        frames.emitter_enu({"emitter_llh": list(YOW)}, None)


def test_llh_emitters_give_same_result_as_enu_emitters():
    spec = load("gps-outage")
    enu_run = generate(spec, seed=4)
    # Same geometry, but stated in lat/lon as real reference data would be
    llh = [frames.enu_to_llh(e, spec["origin_llh"]).tolist() for e in enu_run.emitters.values()]
    spec_llh = load("gps-outage")
    lte = spec_llh["sources"]["lte"]
    lte.pop("n_emitters"), lte.pop("ring_radius_m")
    lte["emitters_llh"] = llh
    llh_run = generate(spec_llh, seed=4)
    assert all("emitter_llh" in m.meta for m in llh_run.measurements if m.source == "lte")

    origin = spec["origin_llh"]
    m_llh = score(
        list(baseline.run(llh_run.measurements, origin_llh=origin)), llh_run.truth, spec, T0_NS
    )
    # Emitter geometry is identical, so accuracy is in the same range (noise draws differ)
    assert m_llh.h_rmse_m < 20 and m_llh.hpl_bound_frac > 0.95


def test_llh_emitters_without_origin_fail_loudly():
    spec = load("gps-outage")
    spec["sources"]["lte"].pop("n_emitters"), spec["sources"]["lte"].pop("ring_radius_m")
    spec["sources"]["lte"]["emitters_llh"] = [list(YOW)]
    run = generate(spec, seed=0)
    with pytest.raises(ValueError):
        list(baseline.run(run.measurements))  # no origin_llh given
