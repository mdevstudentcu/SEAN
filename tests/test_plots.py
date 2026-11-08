import numpy as np
import pytest

from pnt import plots
from pnt.cli import main
from pnt.nav import baseline
from pnt.sim.scenario import T0_NS, generate, load


def _run(name, seed=0):
    spec = load(name)
    sim = generate(spec, seed=seed)
    est = list(baseline.run(sim.measurements, origin_llh=spec.get("origin_llh")))
    meta = {"scenario": name, "seed": str(seed), "commit": "test"}
    return plots.RunData(name, meta, spec, sim.truth, {"baseline": est})


def test_stanford_counts_split_the_regions():
    err = np.array([1.0, 30.0, 70.0, 10.0, 80.0, np.nan])
    hpl = np.array([5.0, 20.0, 40.0, 60.0, 60.0, 1.0])
    c = plots.stanford_counts(err, hpl, alert_limit_m=50.0)
    assert c == {
        "epochs": 5, "nominal": 1, "misleading": 1, "hazardous": 1,
        "unavailable": 2, "unavailable_misleading": 1,
    }  # fmt: skip


def test_spoof_window_is_shaded_from_its_start():
    run = _run("spoof-ramp")
    s = plots.series(run, "baseline")
    spans = plots.fault_spans(run, s, T0_NS)
    assert len(spans) == 1
    start, end, label = spans[0]
    assert label == "spoof ramp" and start == pytest.approx(
        150 - s.t_s[0] - (s.t0_ns - T0_NS) / 1e9
    )
    assert end == pytest.approx(s.t_s[-1])


def test_jamming_zone_is_shaded_where_truth_is_near_the_jammer():
    run = _run("jamming-zone")
    s = plots.series(run, "baseline")
    spans = plots.fault_spans(run, s, T0_NS)
    assert len(spans) >= 3  # the loop passes the jammer once a lap
    assert all(label == "jamming zone" and b > a for a, b, label in spans)


def test_caption_names_scenario_seed_estimator_and_commit():
    cap = _run("gps-outage").caption("baseline")
    assert all(x in cap for x in ("gps-outage", "seed 0", "baseline", "commit test"))


def test_plot_command_writes_the_figures(tmp_path):
    pytest.importorskip("matplotlib")
    session = tmp_path / "s.mcap"
    main(["sim", "spoof-ramp", "--out", str(session)])
    main(["plot", str(session), "--out", str(tmp_path / "fig")])
    names = sorted(p.name for p in (tmp_path / "fig").iterdir())
    # The baseline has no clock state, so no clock figure
    assert names == ["error.png", "stanford.png", "trust.png"]


def test_plot_needs_truth(tmp_path):
    pytest.importorskip("matplotlib")
    from pnt.io.mcap_log import SessionWriter

    run = _run("gps-outage")
    path = tmp_path / "no-truth.mcap"
    with SessionWriter(path) as w:
        for e in run.estimates["baseline"]:
            w.write("/nav/baseline", e)
    with pytest.raises(ValueError, match="truth"):
        plots.save_all(path, tmp_path / "out")
