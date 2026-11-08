import json
from pathlib import Path

import numpy as np
import pytest
from mcap.reader import make_reader

from pnt.cli import main
from pnt.core.frames import enu_to_llh
from pnt.io.mcap_log import read_session
from pnt.sim.scenario import T0_NS, load
from pnt.viz import default_output, session_file, write_viz

LAYOUT = Path(__file__).parents[1] / "analysis" / "foxglove-layout.json"


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    path = tmp_path_factory.mktemp("viz") / "s.mcap"
    main(["sim", "gps-outage", "--out", str(path)])
    return path


@pytest.fixture(scope="module")
def viz(session):
    out = session.with_name("s.viz.mcap")
    main(["viz", str(session), "--out", str(out)])
    with open(out, "rb") as f:
        messages = [
            (schema.name, channel.topic, message.log_time, json.loads(message.data))
            for schema, channel, message in make_reader(f).iter_messages(log_time_order=True)
        ]
    return messages


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


def test_truth_lands_at_the_right_place_on_the_map(session, viz):
    origin = load("gps-outage")["origin_llh"]
    t, fix = _on(viz, "/viz/truth")[0]
    truth = next(r for _, r in read_session(session, topics=["/truth"]) if r.t_ns == t)
    llh = enu_to_llh(truth.pos_enu, origin)
    assert np.allclose([fix["latitude"], fix["longitude"]], llh[:2], atol=1e-9)
    assert abs(fix["latitude"] - origin[0]) < 0.01


def test_towers_are_points_with_lon_lat_order_and_status(viz):
    collection = json.loads(_on(viz, "/viz/towers")[0][1]["geojson"])
    assert len(collection["features"]) == 6
    lon, lat = collection["features"][0]["geometry"]["coordinates"]
    assert -77 < lon < -74 and 44 < lat < 47
    assert collection["features"][0]["properties"]["metadata"]["status"] in {"heard", "lost"}


def test_towers_are_refreshed_once_a_second(viz):
    assert 300 <= len(_on(viz, "/viz/towers")) <= 365


def test_nav_marks_the_fault_window_and_reports_error_and_towers(viz):
    nav = _on(viz, "/viz/nav")
    for t, m in nav:
        seconds = (t - T0_NS) / 1e9
        assert m["fault_active"] == int(120 <= seconds < 240)
        assert m["h_error_m"] >= 0 and m["hpl_m"] > 0
    assert nav[-1][1]["towers_heard"] == 6


def test_missing_estimator_is_a_clear_error(session, tmp_path):
    with pytest.raises(ValueError, match="/nav/nope"):
        write_viz(session, tmp_path / "x.mcap", estimator="nope")


def test_paths_resolve_for_files_and_session_folders(tmp_path):
    assert session_file(tmp_path) == tmp_path / "session.mcap"
    assert default_output(tmp_path) == tmp_path / "viz.mcap"
    assert default_output(tmp_path / "s.mcap") == tmp_path / "s.viz.mcap"


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
