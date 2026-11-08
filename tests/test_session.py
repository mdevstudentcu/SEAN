import pytest
import yaml

from pnt.cli import main
from pnt.io import session
from pnt.io.mcap_log import read_session


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
