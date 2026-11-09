import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from mcap.reader import make_reader

from pnt.cli import main
from pnt.core.frames import enu_to_llh
from pnt.core.time import gps_ns_to_unix_ns
from pnt.io import session as session_io
from pnt.io.mcap_log import SessionWriter, read_session
from pnt.nav import baseline, ekf
from pnt.sim.scenario import T0_NS, generate, load
from pnt.viz import default_output, write_viz

LAYOUT = Path(__file__).parents[1] / "analysis" / "foxglove-layout.json"


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    path = tmp_path_factory.mktemp("viz") / "s.mcap"
    main(["sim", "gps-outage", "--out", str(path)])
    return path


def _read(path):
    with open(path, "rb") as f:
        return [
            (schema.name, channel.topic, message.log_time, json.loads(message.data))
            for schema, channel, message in make_reader(f).iter_messages(log_time_order=True)
        ]


def _hashes(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


@pytest.fixture(scope="module")
def viz(session):
    out = session.with_name("s.viz.mcap")
    main(["viz", str(session), "--out", str(out)])
    return _read(out)


def _on(viz, topic):
    return [(t, m) for _, tp, t, m in viz if tp == topic]


def test_uses_the_schema_names_foxglove_recognises(viz):
    schemas = {tp: name for name, tp, _, _ in viz}
    assert schemas["/viz/truth"] == "foxglove.LocationFix"
    assert schemas["/viz/estimate"] == "foxglove.LocationFix"
    assert schemas["/viz/towers"] == "foxglove.GeoJSON"


def test_location_fix_has_every_required_field_and_valid_timestamp(viz):
    t, fix = _on(viz, "/viz/estimate")[0]
    required = {
        "timestamp",
        "frame_id",
        "latitude",
        "longitude",
        "altitude",
        "position_covariance",
        "position_covariance_type",
    }
    assert required <= fix.keys()
    assert len(fix["position_covariance"]) == 9
    assert fix["position_covariance_type"] == 3
    assert fix["timestamp"]["sec"] * 1_000_000_000 + fix["timestamp"]["nsec"] == t


def test_timestamps_are_unix_time_for_foxglove(session, viz):
    first = next(r for _, r in read_session(session, topics=["/nav/baseline"]))
    t, fix = _on(viz, "/viz/estimate")[0]
    assert t == gps_ns_to_unix_ns(first.t_ns)
    assert fix["timestamp"]["sec"] * 1_000_000_000 + fix["timestamp"]["nsec"] == t


def test_truth_lands_at_the_right_place_on_the_map(session, viz):
    origin = load("gps-outage")["origin_llh"]
    t, fix = _on(viz, "/viz/truth")[0]
    truth = next(
        r for _, r in read_session(session, topics=["/truth"]) if gps_ns_to_unix_ns(r.t_ns) == t
    )
    llh = enu_to_llh(truth.pos_enu, origin)
    assert np.allclose([fix["latitude"], fix["longitude"]], llh[:2], atol=1e-9)
    assert abs(fix["latitude"] - origin[0]) < 0.01


def test_towers_are_points_in_lon_lat_order_and_published_once(viz):
    messages = _on(viz, "/viz/towers")
    assert len(messages) == 1
    collection = json.loads(messages[0][1]["geojson"])
    assert len(collection["features"]) == 6
    lon, lat = collection["features"][0]["geometry"]["coordinates"]
    assert -77 < lon < -74 and 44 < lat < 47
    assert collection["features"][0]["properties"]["name"].startswith("lte:")


def test_nav_marks_the_fault_window_and_reports_error_and_towers(viz):
    nav = _on(viz, "/viz/nav")
    for t, m in nav:
        seconds = (t - gps_ns_to_unix_ns(T0_NS)) / 1e9
        assert m["fault_active"] == int(120 <= seconds < 240)
        assert m["h_error_m"] >= 0 and m["hpl_m"] > 0
    assert nav[-1][1]["towers_heard"] == 6
    assert nav[-1][1]["towers_lost"] == "none"


def test_nav_counts_a_tower_lost_only_after_it_was_heard(tmp_path):
    session = tmp_path / "s.mcap"
    run = generate(load("gps-outage"), seed=0)
    silent, late = "lte:sim2", "lte:sim4"
    t0 = T0_NS
    meas = [
        m
        for m in run.measurements
        if not (m.emitter == silent and m.t_ns >= t0 + 100_000_000_000)
        and not (m.emitter == late and m.t_ns < t0 + 50_000_000_000)
    ]
    estimates = list(baseline.run(meas, origin_llh=run.spec["origin_llh"]))
    with SessionWriter(session, metadata={"origin_llh": run.spec["origin_llh"]}) as w:
        for m in meas:
            w.write(f"/meas/{m.source}", m)
        for e in estimates:
            w.write("/nav/baseline", e)
    out = tmp_path / "v.mcap"
    write_viz(session, out)
    nav = _on(_read(out), "/viz/nav")

    def at(seconds):
        return next(m for t, m in nav if t >= gps_ns_to_unix_ns(t0) + seconds * 1_000_000_000)

    # the late tower is not lost before it is first heard
    assert (at(30)["towers_heard"], at(30)["towers_lost"]) == (5, "none")
    assert (at(60)["towers_heard"], at(60)["towers_lost"]) == (6, "none")
    assert (nav[-1][1]["towers_heard"], nav[-1][1]["towers_lost"]) == (5, silent)


def test_missing_estimator_is_a_clear_error(session, tmp_path):
    with pytest.raises(ValueError, match="/nav/nope"):
        write_viz(session, tmp_path / "x.mcap", estimator="nope")


def test_reruns_an_estimator_the_session_did_not_log(session, tmp_path, capsys):
    out = tmp_path / "ekf.viz.mcap"
    main(["viz", str(session), "--estimator", "ekf", "--out", str(out)])
    assert "re-run over the measurements" in capsys.readouterr().out
    meas = [r for _, r in read_session(session, topics=["/meas/"])]
    expected = list(ekf.run(meas, origin_llh=load("gps-outage")["origin_llh"]))
    estimates = _on(_read(out), "/viz/estimate")
    assert [t for t, _ in estimates] == [gps_ns_to_unix_ns(e.t_ns) for e in expected]


def test_output_goes_beside_the_session(tmp_path):
    folder = tmp_path / "run"
    folder.mkdir()
    assert default_output(folder) == tmp_path / "run.viz.mcap"
    assert default_output(tmp_path / "s.mcap") == tmp_path / "s.viz.mcap"


@pytest.fixture
def folder_session(tmp_path):
    folder = tmp_path / "run"
    main(["sim", "gps-outage", "--out", str(folder)])
    return folder


def test_session_folder_gets_a_view_beside_it_and_is_left_untouched(folder_session):
    before = _hashes(folder_session)
    assert set(before) == {"meta.yaml", "session.mcap"}
    main(["viz", str(folder_session)])
    out = folder_session.with_name("run.viz.mcap")
    assert len(_on(_read(out), "/viz/estimate")) > 0
    assert _hashes(folder_session) == before


def test_refuses_to_overwrite_without_force(folder_session):
    out = folder_session.with_name("run.viz.mcap")
    main(["viz", str(folder_session)])
    out.write_bytes(b"keep me")
    with pytest.raises(SystemExit, match="already exists"):
        main(["viz", str(folder_session)])
    assert out.read_bytes() == b"keep me"
    main(["viz", str(folder_session), "--force"])
    assert len(_on(_read(out), "/viz/estimate")) > 0


@pytest.mark.parametrize("target", ["session.mcap", "meta.yaml", "viz.mcap"])
def test_refuses_to_write_into_the_session_folder(folder_session, target):
    before = _hashes(folder_session)
    with pytest.raises(SystemExit, match="part of session"):
        main(["viz", str(folder_session), "--out", str(folder_session / target), "--force"])
    assert _hashes(folder_session) == before


def test_refuses_to_overwrite_a_bare_session_file(session):
    before = hashlib.sha256(session.read_bytes()).hexdigest()
    with pytest.raises(SystemExit, match="part of session"):
        main(["viz", str(session), "--out", str(session), "--force"])
    assert hashlib.sha256(session.read_bytes()).hexdigest() == before


@pytest.fixture
def recording(tmp_path):
    """Like a real capture: origin only in meta.yaml, measurements and truth, no estimates."""
    run = generate(load("gps-outage"), seed=0)
    origin = [45.0, -75.0, 80.0]  # differs from the scenario's, to show which one is used
    folder = tmp_path / "rec"
    folder.mkdir()
    session_io.write_meta(folder, {"name": "rec", "platform": "handheld", "origin_llh": origin})
    with SessionWriter(folder / session_io.MCAP_NAME, metadata={}) as w:
        for t in run.truth:
            w.write("/truth", t)
        for m in run.measurements:
            w.write(f"/meas/{m.source}", m)
    return folder, origin, run


def test_origin_comes_from_meta_yaml(recording):
    folder, origin, run = recording
    out = folder.with_name("rec.viz.mcap")
    main(["viz", str(folder)])
    t, fix = _on(_read(out), "/viz/truth")[0]
    truth = next(r for r in run.truth if gps_ns_to_unix_ns(r.t_ns) == t)
    assert np.allclose([fix["latitude"], fix["longitude"]], enu_to_llh(truth.pos_enu, origin)[:2])


def test_session_without_stored_estimates_is_rerun(recording):
    folder, origin, run = recording
    out = folder.with_name("rec.viz.mcap")
    counts = write_viz(folder, out)
    assert counts["recomputed"]
    assert counts["estimates"] == len(list(baseline.run(run.measurements, origin_llh=origin)))
    assert counts["estimates"] == len(_on(_read(out), "/viz/estimate"))


def test_layout_only_uses_topics_and_fields_the_file_provides(viz):
    layout = json.loads(LAYOUT.read_text())
    nav_fields = set().union(*(m.keys() for _, m in _on(viz, "/viz/nav")))
    topics = {tp for _, tp, _, _ in viz}
    assert layout["configById"]["map!pntmap"]["followTopic"] in topics
    for config in layout["configById"].values():
        for path in config.get("paths", []):
            topic, field = path["value"].rsplit(".", 1)
            assert topic in topics and field in nav_fields


def test_every_panel_in_the_mosaic_is_configured():
    layout = json.loads(LAYOUT.read_text())

    def leaves(node):
        return [node] if isinstance(node, str) else leaves(node["first"]) + leaves(node["second"])

    assert sorted(leaves(layout["layout"])) == sorted(layout["configById"])
