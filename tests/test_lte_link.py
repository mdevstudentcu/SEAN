"""Real LTE records into the filter (#121): cell lookup, frame ambiguity and dongle clocks.

The records imitate what `pnt.frontends.lte` writes: no tower position, each dongle's clock in
every range, values known only modulo one frame. Error bounds are regression guards, not targets.
"""

import csv
from collections import Counter

import numpy as np
import pytest

from pnt import nav
from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement
from pnt.nav import cells, ekf
from pnt.nav.cells import COLLISION, MATCHED, OUT_OF_RANGE, UNKNOWN, Cell, CellTable

ORIGIN = (45.3876, -75.6960, 80.0)
FRAME_M = 299792458.0 * 0.01
T0 = 1_446_000_000_000_000_000
EARFCN = 2460
SITES = {  # pci: (enb, lat, lon); pcis 8 and 7 are two sectors of one eNB
    8: (100, 45.4076, -75.6960),
    7: (100, 45.4076, -75.6960),
    21: (200, 45.3876, -75.6600),
    35: (300, 45.3576, -75.7010),
    50: (400, 45.3926, -75.7360),
}
TOWER_CLOCK_M = {100: 1234.0, 200: -5678.0, 300: 2.5e5, 400: 9.0e5}


def table() -> CellTable:
    return CellTable(
        Cell(EARFCN, pci, enb, lat, lon, 30.0) for pci, (enb, lat, lon) in SITES.items()
    )


def tower_enu(pci):
    _, lat, lon = SITES[pci]
    return llh_to_enu([lat, lon, ORIGIN[2] + 30.0], ORIGIN)


def stream(rx_clock="a", drift=120.0, seed=3, outage_s=30.0, duration_s=60.0):
    """A receiver going 5 m/s east: GNSS at 1 Hz until `outage_s`, baro at 5 Hz, towers at 10 Hz,
    and (pos_enu at t) as truth."""
    rng = np.random.default_rng(seed)
    truth = {}
    out = []
    for k in range(int(duration_s * 10)):
        t = k / 10.0
        t_ns = T0 + k * 100_000_000
        p = np.array([5.0 * t, 0.0, 30.0])
        truth[t_ns] = p
        if k % 10 == 0 and t < outage_s:
            fix = tuple(float(v) for v in p + rng.normal(0, 2.0, 3))
            out.append(Measurement(t_ns=t_ns, source="gnss", kind="position_enu", value=fix,
                                   sigma=(2.0, 2.0, 2.0)))  # fmt: skip
        if k % 2 == 0:
            alt = float(p[2] + rng.normal(0, 1.0))
            out.append(Measurement(t_ns=t_ns, source="baro", kind="altitude", value=(alt,),
                                   sigma=(1.0,)))  # fmt: skip
        for pci, (enb, _, _) in SITES.items():
            rng_m = float(np.linalg.norm(p - tower_enu(pci)))
            rho = rng_m + TOWER_CLOCK_M[enb] + 7777.0 + drift * t + rng.normal(0, 3.0)
            meta = {"ambiguity_m": FRAME_M}
            if rx_clock is not None:
                meta["rx_clock"] = rx_clock
            out.append(Measurement(t_ns=t_ns, source="lte", kind="pseudorange",
                                   emitter=f"lte:{EARFCN}:{pci}", value=(rho % FRAME_M,),
                                   sigma=(3.0,), meta=meta))  # fmt: skip
    return out, truth


def outage_errors(estimates, truth, after_ns):
    return np.array(
        [
            np.linalg.norm(np.array(e.pos_enu)[:2] - truth[e.t_ns][:2])
            for e in estimates
            if e.t_ns >= after_ns and e.t_ns in truth
        ]
    )


@pytest.mark.parametrize(
    ("earfcn", "pci", "status", "enb"),
    [
        (EARFCN, 21, MATCHED, 200),
        (EARFCN, 99, UNKNOWN, None),
        (1, 21, UNKNOWN, None),
    ],
)
def test_lookup(earfcn, pci, status, enb):
    got, cell = table().associate(earfcn, pci, ORIGIN)
    assert got == status
    assert (cell.enb_id if cell else None) == enb


def test_a_pci_on_two_enbs_in_range_is_left_out():
    t = CellTable([Cell(5, 1, 10, 45.39, -75.69, 30.0), Cell(5, 1, 11, 45.40, -75.70, 30.0)])
    assert t.associate(5, 1, ORIGIN) == (COLLISION, None)


def test_a_collision_with_a_far_enb_still_matches_the_near_one():
    near, far = Cell(5, 1, 10, 45.39, -75.69, 30.0), Cell(5, 1, 11, 46.5, -75.69, 30.0)
    assert CellTable([near, far]).associate(5, 1, ORIGIN) == (MATCHED, near)


def test_a_cell_beyond_the_range_is_left_out():
    t = CellTable([Cell(5, 1, 10, 46.5, -75.69, 30.0)])
    assert t.associate(5, 1, ORIGIN) == (OUT_OF_RANGE, None)


def test_attach_adds_position_and_site_and_counts_what_it_drops():
    keep = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter=f"lte:{EARFCN}:21",
                       value=(10.0,), sigma=(3.0,), meta={"snr_db": 4.0})  # fmt: skip
    lost = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter=f"lte:{EARFCN}:99",
                       value=(10.0,), sigma=(3.0,))  # fmt: skip
    nameless = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter="lte::21",
                           value=(10.0,), sigma=(3.0,))  # fmt: skip
    counts = Counter()
    out = list(cells.attach([keep, lost, nameless], ORIGIN, table(), counts))
    assert len(out) == 1
    assert out[0].meta["site"] == "enb:200" and out[0].meta["snr_db"] == 4.0
    assert out[0].meta["emitter_llh"] == [45.3876, -75.6600, 110.0]  # origin height + antenna
    assert counts == {MATCHED: 1, UNKNOWN: 2}


def test_records_with_a_position_and_other_sources_pass_through_untouched():
    sim = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter="lte:0", value=(1.0,),
                      sigma=(1.0,), meta={"emitter_llh": [45.0, -75.0, 0.0]})  # fmt: skip
    gnss = Measurement(t_ns=T0, source="gnss", kind="position_enu", value=(0.0, 0.0, 0.0),
                       sigma=(1.0, 1.0, 1.0))  # fmt: skip
    out = list(cells.attach([sim, gnss], None, None))
    assert out[0] is sim and out[1] is gnss


def test_real_records_without_an_origin_or_a_table_say_so(tmp_path, monkeypatch):
    m = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter=f"lte:{EARFCN}:21",
                    value=(1.0,), sigma=(1.0,))  # fmt: skip
    with pytest.raises(ValueError, match="origin_llh"):
        list(cells.attach([m], None, table()))
    monkeypatch.setattr(cells, "CELL_TABLE", tmp_path / "nope.csv")
    with pytest.raises(FileNotFoundError, match="cell table"):
        list(cells.attach([m], ORIGIN))


def test_table_loads_the_columns_the_extract_writes(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text(
        "earfcn,pci,enb_id,lat,lon,ant_height_agl_m,extra\n2460,8,100,45.4,-75.7,38.5,x\n"
    )
    status, cell = CellTable.load(p).associate(2460, 8, ORIGIN)
    assert status == MATCHED and cell.height_agl_m == 38.5


def test_the_committed_table_resolves_a_registered_cell():
    # A cell chosen from the table's own first data row; the table's contents can change
    with open(cells.CELL_TABLE, newline="") as f:
        row = next(csv.DictReader(f))
    status, cell = CellTable.load().associate(int(row["earfcn"]), int(row["pci"]), ORIGIN)
    assert status in (MATCHED, COLLISION)
    if status == MATCHED:
        assert cell.site == f"enb:{row['enb_id']}"


def test_sectors_that_wrapped_differently_line_up_for_one_site_clock():
    a = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter=f"lte:{EARFCN}:8",
                    value=(FRAME_M - 5.0,), sigma=(3.0,),
                    meta={"ambiguity_m": FRAME_M})  # fmt: skip
    b = Measurement(t_ns=T0, source="lte", kind="pseudorange", emitter=f"lte:{EARFCN}:7",
                    value=(5.0,), sigma=(3.0,), meta={"ambiguity_m": FRAME_M})  # fmt: skip
    out = list(cells.attach([a, b], ORIGIN, table()))
    assert out[1].value[0] - out[0].value[0] == pytest.approx(10.0)


def test_a_new_arc_a_whole_number_of_frames_away_continues_the_old_one():
    def rec(v, k):
        return Measurement(t_ns=T0 + k, source="lte", kind="pseudorange",
                           emitter=f"lte:{EARFCN}:21", value=(v,), sigma=(3.0,),
                           meta={"ambiguity_m": FRAME_M})  # fmt: skip

    out = list(cells.attach([rec(1000.0, 0), rec(1000.0 + 7 * FRAME_M + 4.0, 1)], ORIGIN, table()))
    assert out[1].value[0] == pytest.approx(1004.0)


def test_the_filter_rides_a_drifting_dongle_through_a_gnss_outage():
    records, truth = stream()
    run = ekf.run(cells.attach(records, ORIGIN, table()), origin_llh=ORIGIN)
    errors = outage_errors(list(run), truth, T0 + 30_000_000_000)
    assert len(errors) > 200
    assert np.percentile(errors, 95) < 15.0  # regression guard, not a requirement


def test_without_the_dongle_clock_the_same_records_are_useless():
    records, truth = stream(rx_clock=None)
    run = ekf.run(cells.attach(records, ORIGIN, table()), origin_llh=ORIGIN)
    errors = outage_errors(list(run), truth, T0 + 30_000_000_000)
    assert np.percentile(errors, 95) > 50.0  # the failure the dongle state exists to fix


def test_two_dongles_get_two_clocks():
    records, _ = stream(drift=0.0, duration_s=2.0)
    both = [
        m
        if m.emitter.endswith(":21") is False
        else Measurement(
            t_ns=m.t_ns,
            source=m.source,
            kind=m.kind,
            emitter=m.emitter,
            value=m.value,
            sigma=m.sigma,
            meta={**m.meta, "rx_clock": "b"},
        )  # fmt: skip
        for m in records
    ]
    f = ekf.EKF(origin_llh=ORIGIN)
    for m in cells.attach(both, ORIGIN, table()):
        f.process(m)
    assert set(f.rx_idx) == {"a", "b"}


def test_sectors_of_one_enb_share_a_site_clock():
    records, _ = stream(duration_s=2.0)
    f = ekf.EKF(origin_llh=ORIGIN)
    for m in cells.attach(records, ORIGIN, table()):
        f.process(m)
    assert sorted(f.clock_idx) == ["site:enb:100", "site:enb:200", "site:enb:300", "site:enb:400"]


def test_estimate_resolves_cells_for_every_source(tmp_path, monkeypatch):
    p = tmp_path / "t.csv"
    rows = "".join(
        f"{EARFCN},{pci},{enb},{lat},{lon},30\n" for pci, (enb, lat, lon) in SITES.items()
    )
    p.write_text("earfcn,pci,enb_id,lat,lon,ant_height_agl_m\n" + rows)
    monkeypatch.setattr(cells, "CELL_TABLE", p)
    records, truth = stream()
    errors = outage_errors(
        list(nav.estimate("ekf", records, origin_llh=ORIGIN)), truth, T0 + 30_000_000_000
    )
    assert np.percentile(errors, 95) < 15.0  # regression guard, not a requirement


def test_rollback_carries_the_dongle_clock_forward_instead_of_rewinding_it():
    records, _ = stream(duration_s=25.0, outage_s=30.0)
    f = ekf.EKF(origin_llh=ORIGIN, clock_model="calibrated")
    for m in cells.attach(records, ORIGIN, table()):
        f.process(m)
    i = f.rx_idx["a"]
    before, drift = f.x[i], f.x[i + 1]
    assert drift == pytest.approx(120.0, abs=20.0)  # regression guard
    assert len(f._snaps) > 0
    f.rollback(f.t_ns)
    assert f.rollbacks  # it did roll back
    assert f.x[i] == pytest.approx(before, abs=100.0)  # regression guard: a rewind moves it by km


def test_rollback_keeps_a_later_dongle_clock_with_imu_states():
    # The IMU motion adds states before the clock blocks, so the rollback has to count from
    # `n_core`, not N_CORE: a second dongle first heard before the snapshot must keep its
    # learned covariance, not snap back to its first-sight prior (which would be overconfident)
    records, _ = stream(duration_s=25.0, outage_s=30.0, drift=0.0)
    late = []
    for m in records:
        if m.source == "lte" and m.emitter.endswith(":21"):
            if m.t_ns < T0 + 5_000_000_000:
                continue  # dongle "b" is first heard at 5 s, so its block comes after the towers'
            m = Measurement(
                t_ns=m.t_ns,
                source=m.source,
                kind=m.kind,
                emitter=m.emitter,
                value=m.value,
                sigma=m.sigma,
                meta={**m.meta, "rx_clock": "b"},
            )
        late.append(m)
    f = ekf.EKF(origin_llh=ORIGIN, clock_model="calibrated", motion="imu")
    for m in cells.attach(late, ORIGIN, table()):
        f.process(m)
    i = f.rx_idx["b"]
    assert f.n_core > ekf.N_CORE  # the IMU states are there
    assert i < f.n_core + len(f._snaps[0][1])  # the block existed before the snapshot
    sigma = np.sqrt(np.diag(f.P)[i : i + 2])
    f.rollback(f.t_ns)
    after = np.sqrt(np.diag(f.P)[i : i + 2])
    assert after[0] >= sigma[0] and after[1] < 0.5 * f.rx_prior[1]  # carried forward, not reset
