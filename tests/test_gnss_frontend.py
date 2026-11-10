"""GNSS front end (#22, ADR-0031) on a hand-written gpsd snippet: no hardware, no network.

`fixtures/gnss/gpspipe-w.jsonl` is gpsd JSON as `gpspipe -w` prints it: six epochs walking
east, open sky, then C/N0 falling 8 and 12 dB, then two epochs with no fix. It also has a
repeated TPV, a SKY with no `time` and a SKY with DOPs but no satellite list. It is hand-written in
gpsd's format (https://gpsd.io/gpsd_json.html), not recorded: no GPS HAT session exists yet.
"""

import hashlib
from pathlib import Path

import pytest

from pnt.cli import main
from pnt.core.measurement import Measurement, validate
from pnt.core.time import utc_to_gps_ns
from pnt.frontends import gnss
from pnt.io import session
from pnt.io.mcap_log import SessionWriter, read_json, read_session
from pnt.payload import gpsd
from pnt.sources.replay import ReplaySource

FIXTURE = Path(__file__).parent / "fixtures" / "gnss" / "gpspipe-w.jsonl"
ORIGIN = (45.3876, -75.6960, 70.0)


def t(sec: int) -> int:
    from datetime import UTC, datetime

    return utc_to_gps_ns(datetime(2026, 11, 10, 14, 30, sec, tzinfo=UTC))


def lines() -> list[str]:
    return FIXTURE.read_text().splitlines()


def by_kind(records, kind):
    return [m for m in records if m.kind == kind]


def test_jam_indicator_scales_the_drop_of_the_strongest_satellites():
    assert gnss.jam_indicator([44, 42, 41, 40, 30]) == 0.0  # above the open-sky level
    assert gnss.jam_indicator([36, 34, 33, 32]) == pytest.approx((40 - 33.75) / 15)
    assert gnss.jam_indicator([]) == 1.0  # nothing tracked: every slot counts as lost
    assert gnss.jam_indicator([20, 18]) == 1.0
    # 0 dB-Hz and None mean "not tracked", as gpsd lists them
    assert gnss.jam_indicator([44, 42, 41, 40, 0, None]) == 0.0
    with pytest.raises(ValueError):
        gnss.jam_indicator([40], ref=25, low=25)


def test_gpsd_snippet_gives_fixes_and_health_per_epoch():
    out = gnss.from_gpsd_json(lines(), ORIGIN)
    for m in out:
        validate(m)
    pos = by_kind(out, "position_enu")
    # four 3D fixes: the repeated 14:30:00 report is kept once; the mode-1 epochs give none
    assert [m.t_ns for m in pos] == [t(0), t(1), t(2), t(3)]
    assert pos[0].value == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    east = [m.value[0] for m in pos]
    assert east[1:] == pytest.approx([1.4, 2.8, 4.2], abs=0.01)  # 1.4 m/s east
    assert pos[0].sigma == pytest.approx((4.2 / 1.96, 5.1 / 1.96, 11.3 / 1.96))
    assert len(by_kind(out, "velocity_enu")) == 4

    health = by_kind(out, "gnss_health")
    # the SKY report with no `time` takes the last TPV's; the one with no satellites gives none
    assert [m.t_ns for m in health] == [t(0), t(1), t(2), t(3), t(4), t(5)]
    jam = [m.value[0] for m in health]
    assert jam == pytest.approx([0.0, 0.0, 6.25 / 15, 10.25 / 15, 1.0, 1.0])
    assert [m.value[1] for m in health] == [6, 6, 5, 4, 0, 0]  # satellites used
    assert [m.value[2] for m in health] == [0.94, 0.94, 1.52, 2.71, 99.0, 99.0]
    assert health[0].meta["snr"]["29"] == 0.0 and health[0].meta["n_seen"] == 8


def test_payload_and_log_paths_agree_on_fixes():
    tpv = [ln for ln in lines() if '"TPV"' in ln][0]
    import json

    direct = gpsd.tpv_measurements(json.loads(tpv), ORIGIN)
    via_log = gnss.from_gpsd_json([tpv], ORIGIN)
    assert via_log == direct


def test_reference_receiver_is_kept():
    out = gnss.from_gpsd_json(lines(), ORIGIN, receiver="reference")
    assert out and {m.receiver for m in out} == {"reference"}


def recorded_session(folder: Path) -> Path:
    """A session as `pnt record` writes it from the snippet: fixes on /meas/gnss, SKY as
    `gnss_sky` events stamped on arrival (here 0.2 s after the epoch), plus a PPS event and a
    stale `gnss_health` record that the front end must replace."""
    import json

    folder.mkdir()
    session.write_meta(folder, {"name": folder.name, "platform": "static", "origin_llh":
                                list(ORIGIN), "simulated": False, "notes": "bench"})  # fmt: skip
    stale = Measurement(t_ns=t(0), source="gnss", kind="gnss_health", value=(0.5, 1.0, 1.0),
                        sigma=(0.0, 0.0, 0.0))  # fmt: skip
    with SessionWriter(folder / session.MCAP_NAME) as w:
        w.write("/meas/gnss", stale)
        last = None
        for ln in lines():
            msg = json.loads(ln)
            if msg["class"] == "TPV":
                last = gpsd.parse_time(msg["time"])
                for m in gpsd.tpv_measurements(msg, ORIGIN):
                    w.write("/meas/gnss", m)
            elif msg["class"] == "SKY":
                w.write_json("/events", last + 200_000_000, gpsd.sky_event(msg))
        w.write_json("/events", t(1), {"text": "pps", "offset_ns": 120})
    return folder


def digest(folder: Path) -> str:
    return "".join(hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()))


def test_derived_session_adds_health_and_keeps_the_recording(tmp_path):
    src = recorded_session(tmp_path / "20261110-1430-static-bench")
    before = digest(src)
    out = tmp_path / "derived"
    new = gnss.derive_session(src, out, "abc1234")
    assert digest(src) == before  # never rewrites its input (REQ-10)

    health = [r for _, r in read_session(out / session.MCAP_NAME) if r.kind == "gnss_health"]
    assert health == new and len(new) == 6  # the stale record is gone
    assert [m.t_ns for m in new] == [t(s) + 200_000_000 for s in range(6)]
    assert [m.value[0] for m in new] == pytest.approx([0, 0, 6.25 / 15, 10.25 / 15, 1, 1])

    def kinds(folder):
        return sorted(r.kind for _, r in read_session(folder / session.MCAP_NAME))

    kept = [k for k in kinds(src) if k != "gnss_health"]
    assert kinds(out) == sorted(kept + ["gnss_health"] * 6)
    texts = [d["text"] for _, d in read_json(out / session.MCAP_NAME, ["/events"])]
    assert texts.count("gnss_sky") == 7 and "pps" in texts  # all copied, DOP-only one too
    meta = session.read_meta(out)
    assert meta["commit"] == "abc1234" and meta["notes"].startswith("bench; GNSS health")
    assert meta["origin_llh"] == list(ORIGIN)


def test_cli_writes_a_session_that_replay_reads(tmp_path, capsys):
    src = recorded_session(tmp_path / "bench")
    main(["frontend", "gnss", str(src), "--ref-cn0", "42"])
    out = tmp_path / "bench-gnss"
    text = capsys.readouterr().out
    assert "6 gnss_health records" in text and str(out) in text
    health = [m for m in ReplaySource(out / session.MCAP_NAME) if m.kind == "gnss_health"]
    assert len(health) == 6 and health[0].meta["ref_cn0_dbhz"] == 42.0
    assert health[2].value[0] == pytest.approx((42 - 33.75) / 17)
    with pytest.raises(SystemExit):
        main(["frontend", "gnss", str(src), "--out", str(out)])  # never overwrites
