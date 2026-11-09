import json

import pytest
import yaml

from pnt.cli import main
from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_session


def test_sim_writes_a_session_folder_per_the_icd(tmp_path, capsys):
    out = tmp_path / "sim-gps-outage-test"
    main(["sim", "gps-outage", "--seed", "3", "--out", str(out)])
    assert sorted(p.name for p in out.iterdir()) == ["meta.yaml", "session.mcap"]
    meta = yaml.safe_load((out / "meta.yaml").read_text())
    assert list(meta) == list(session.META_KEYS)
    assert meta["name"] == out.name and meta["platform"] == "sim" and meta["simulated"] is True
    assert meta["scenario"] == "gps-outage" and meta["seed"] == 3
    assert meta["origin_llh"] == [45.3876, -75.6960, 70.0]
    assert sum(1 for _ in read_session(out / "session.mcap", topics=["/truth"])) > 0


def test_bare_mcap_out_still_writes_a_single_file(tmp_path):
    out = tmp_path / "s.mcap"
    main(["sim", "gps-outage", "--out", str(out)])
    assert out.is_file() and not (tmp_path / "meta.yaml").exists()


def test_replay_and_meta_accept_folder_or_file(tmp_path, capsys):
    folder = tmp_path / "run"
    main(["sim", "spoof-ramp", "--out", str(folder)])
    capsys.readouterr()
    main(["replay", str(folder)])
    from_folder = capsys.readouterr().out.splitlines()[1:]
    main(["replay", str(folder / "session.mcap")])
    from_file = capsys.readouterr().out.splitlines()[1:]
    assert from_folder == from_file  # same metrics, fault windows included
    assert session.read_meta(folder)["seed"] == session.read_meta(folder / "session.mcap")["seed"]


def test_plot_names_output_after_the_folder(tmp_path):
    pytest.importorskip("matplotlib")
    from pnt import plots

    folder = tmp_path / "sim-run-1"
    main(["sim", "gps-outage", "--out", str(folder)])
    run = plots.load(folder)
    assert run.name == "sim-run-1" and "seed 0" in run.caption("baseline")


def test_folder_without_mcap_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError, match="not a session folder"):
        session.mcap_path(tmp_path)


def test_meta_rejects_keys_outside_the_icd(tmp_path):
    with pytest.raises(ValueError, match="ICD"):
        session.write_meta(tmp_path, {"name": "x", "flavour": "spicy"})


def test_sim_refuses_to_overwrite_an_existing_session(tmp_path):
    folder = tmp_path / "real-recording"
    folder.mkdir()
    (folder / "session.mcap").write_bytes(b"precious")
    with pytest.raises(SystemExit, match="already holds data"):
        main(["sim", "gps-outage", "--out", str(folder)])
    assert (folder / "session.mcap").read_bytes() == b"precious"


def test_sim_refuses_to_overwrite_a_bare_mcap(tmp_path):
    f = tmp_path / "s.mcap"
    f.write_bytes(b"precious")
    with pytest.raises(SystemExit, match="already holds data"):
        main(["sim", "gps-outage", "--out", str(f)])
    assert f.read_bytes() == b"precious"


def test_force_allows_overwriting(tmp_path):
    f = tmp_path / "s.mcap"
    f.write_bytes(b"old")
    main(["sim", "gps-outage", "--out", str(f), "--force"])
    assert f.stat().st_size > 1000


def test_default_session_names_never_collide(tmp_path, monkeypatch):
    import pnt.cli

    monkeypatch.setattr(pnt.cli, "SESSIONS", tmp_path)
    main(["sim", "gps-outage"])
    main(["sim", "gps-outage"])  # same second, most likely
    folders = sorted(p.name for p in tmp_path.iterdir())
    assert len(folders) == 2 and all((tmp_path / f / "session.mcap").exists() for f in folders)


def _meas(t_ns: int, receiver: str) -> Measurement:
    return Measurement(
        t_ns=t_ns, source="lte", kind="pseudorange", value=(float(t_ns),), sigma=(1.0,),
        emitter="lte:sim0", receiver=receiver,
    )  # fmt: skip


def test_two_receivers_share_a_session_and_round_trip(tmp_path):
    path = tmp_path / "s.mcap"
    written = [_meas(1, "payload"), _meas(1, "reference"), _meas(2, "reference")]
    with SessionWriter(path) as w:
        for m in written:
            w.write(f"/meas/{m.source}", m)
    read = [(topic, rec) for topic, rec in read_session(path, topics=["/meas/"])]
    assert {topic for topic, _ in read} == {"/meas/lte"}
    assert sorted((r.t_ns, r.receiver) for _, r in read) == sorted(
        (m.t_ns, m.receiver) for m in written
    )


def test_session_written_before_the_receiver_field_still_loads(tmp_path):
    from mcap.writer import Writer

    path = tmp_path / "old.mcap"
    old = {"t_ns": 5, "source": "lte", "kind": "pseudorange", "value": [1.0], "sigma": [1.0]}
    with open(path, "wb") as f:
        w = Writer(f)
        w.start(profile="", library="pnt")
        schema = w.register_schema(name="pnt.Measurement", encoding="jsonschema", data=b"{}")
        ch = w.register_channel(topic="/meas/lte", message_encoding="json", schema_id=schema)
        w.add_message(channel_id=ch, log_time=5, publish_time=5, data=json.dumps(old).encode())
        w.finish()
    [(_, rec)] = list(read_session(path))
    assert rec.receiver == "payload"


def test_meta_records_the_reference_station(tmp_path):
    ref = {"position_llh": [45.0, -75.0, 70.0], "surveyed": False}
    session.write_meta(tmp_path, {"name": "x", "reference": ref})
    assert session.read_meta(tmp_path)["reference"] == ref
    with SessionWriter(tmp_path / "s.mcap", metadata={"reference": ref}):
        pass
    assert session.read_meta(tmp_path / "s.mcap")["reference"] == ref


@pytest.mark.parametrize("sigma", [0.5, 2, "TBD", None])
def test_reference_survey_sigma_round_trips(tmp_path, sigma):
    ref = {"position_llh": [45.0, -75.0, 70.0], "surveyed": True}
    if sigma is not None:  # None: key absent, accuracy unknown
        ref["sigma_m"] = sigma
    session.write_meta(tmp_path, {"name": "x", "reference": ref})
    assert session.read_meta(tmp_path)["reference"] == ref
    with SessionWriter(tmp_path / "s.mcap", metadata={"reference": ref}):
        pass
    assert session.read_meta(tmp_path / "s.mcap")["reference"] == ref


@pytest.mark.parametrize(
    "ref",
    [
        {"position_llh": [45.0, -75.0, 70.0], "sigma_m": -1.0},
        {"position_llh": [45.0, -75.0, 70.0], "sigma_m": "about 2"},
        {"position_llh": [45.0, -75.0, 70.0], "sigma_m": True},
        {"position_llh": [45.0, -75.0, 70.0], "surveyed": "yes"},
        {"position_llh": [45.0, -75.0, 70.0], "accuracy": 2.0},
        {"position_llh": [45.0, -75.0], "sigma_m": 2.0},
        {"surveyed": True, "sigma_m": 2.0},
    ],
)
def test_malformed_reference_is_rejected_on_write_and_read(tmp_path, ref):
    with pytest.raises(ValueError, match="reference"):
        session.write_meta(tmp_path, {"name": "x", "reference": ref})
    (tmp_path / session.META_NAME).write_text(yaml.safe_dump({"name": "x", "reference": ref}))
    with pytest.raises(ValueError, match="reference"):
        session.read_meta(tmp_path)
