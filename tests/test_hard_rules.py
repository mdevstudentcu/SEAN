"""Hard rules from AGENTS.md that a machine can check (systems/quality.md).

The REQ-07 scan knows a fixed list of transmit APIs, so it backs up the inspection REQ-07 asks for
and does not replace it. REQ-08 (BSSIDs hashed at capture) is not here because no capture code
exists yet: `firmware/esp32-hub/src/main.cpp` has only a TODO for the Wi-Fi scan.
"""

import re
import subprocess
from pathlib import Path

import pytest

from pnt.sim.scenario import SCENARIO_DIR, generate, load

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = ("src", "firmware", "flight")
SCAN_SKIP_DIRS = {".pio", "__pycache__"}
TRANSMIT_APIS = {
    "SoapySDR": r"\bSOAPY_SDR_TX\b|\bwriteStream\s*\(",
    "HackRF": r"\bhackrf_(?:start_tx|stop_tx|set_txvga_gain)\b|\bhackrf_transfer\b.*\s-t\s",
    "bladeRF": r"\bbladerf_sync_tx\b|\bBLADERF_(?:MODULE_TX|CHANNEL_TX|TX_X[12])\b|\.sync_tx\s*\(",
    "UHD": r"\bget_tx_stream\b|\btx_streamer\b|\btx_metadata_t\b|\bsend_waveform\b|\busrp_sink\b",
    "LimeSuite": r"\bLMS_CH_TX\b|\bLMS_SendStream\b",
    "PlutoSDR": r"\.tx\s*\(|\btx_(?:lo|hardwaregain\w*|cyclic_buffer|enabled_channels)\b"
    r"|\biio_buffer_push\b|\b(?:pluto|fmcomms\d?)_sink\b",
    "GNU Radio sink": r"\bosmosdr\.sink\b|\bsoapy\.sink\b|\bbladeRF_sink\b",
    "Pi GPIO transmit": r"\b(?:rpitx|sendiq|pifmrds)\b",
    "GNSS signal generator": r"\bgps[-_]sdr[-_]sim\b",
}
TRANSMIT_RE = {name: re.compile(pattern) for name, pattern in TRANSMIT_APIS.items()}


def _transmit_apis_in(line: str) -> list[str]:
    return [name for name, pattern in TRANSMIT_RE.items() if pattern.search(line)]


def _scanned_files() -> list[Path]:
    return [
        p
        for root in SCAN_ROOTS
        for p in (ROOT / root).rglob("*")
        if p.is_file() and not SCAN_SKIP_DIRS.intersection(p.parts)
    ]


def test_no_transmit_calls_req07():
    files = _scanned_files()
    for root in SCAN_ROOTS:
        assert any(p.is_relative_to(ROOT / root) for p in files), f"nothing scanned in {root}/"
    hits = [
        f"{path.relative_to(ROOT)}:{number}: {name}"
        for path in files
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        )
        for name in _transmit_apis_in(line)
    ]
    assert not hits, "transmit API found (ADR-0001, REQ-07):\n" + "\n".join(hits)


@pytest.mark.parametrize(
    ("line", "api"),
    [
        ("stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)", "SoapySDR"),
        ("hackrf_start_tx(device, callback, nullptr);", "HackRF"),
        ("hackrf_transfer -f 1575420000 -t gps.bin", "HackRF"),
        ("bladerf_sync_tx(dev, samples, n, NULL, 1000);", "bladeRF"),
        ("streamer = usrp.get_tx_stream(args)", "UHD"),
        ("LMS_EnableChannel(dev, LMS_CH_TX, 0, true);", "LimeSuite"),
        ("sdr.tx(iq)", "PlutoSDR"),
        ("sink = osmosdr.sink(args='hackrf')", "GNU Radio sink"),
        ("subprocess.run(['sendiq', '-i', 'a.iq'])", "Pi GPIO transmit"),
        ("./gps-sdr-sim -e brdc.n -l 45,-75,70", "GNSS signal generator"),
    ],
)
def test_scan_flags_planted_transmit_call_req07(line, api):
    assert api in _transmit_apis_in(line)


def test_scan_passes_receive_calls_req07():
    assert not _transmit_apis_in("samples = RtlSdr().read_samples(256 * 1024)")


# What a session folder holds (systems/icd/session.md), apart from small JSON sidecars.
RAW_SESSION_SUFFIXES = (".mcap", ".cu8", ".mp4")


def _is_raw_session_data(path: str) -> bool:
    if path.startswith("tests/fixtures/"):
        return False
    if path.startswith("data/sessions/"):
        return path != "data/sessions/.gitkeep"
    return path.endswith(RAW_SESSION_SUFFIXES)


def test_no_raw_session_data_tracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked, "git lists no tracked files"
    raw = [path for path in tracked if _is_raw_session_data(path)]
    assert not raw, "raw session data tracked by git:\n" + "\n".join(raw)


@pytest.mark.parametrize(
    "path",
    [
        "data/sessions/20261110-handheld/meta.yaml",
        "data/sessions/20261110-handheld/session.mcap",
        "analysis/session.mcap",
        "sdr_a.cu8",
        "docs/camera.mp4",
    ],
)
def test_planted_raw_session_data_is_flagged(path):
    assert _is_raw_session_data(path)


@pytest.mark.parametrize("path", ["data/sessions/.gitkeep", "tests/fixtures/short/session.mcap"])
def test_allowed_files_are_not_flagged(path):
    assert not _is_raw_session_data(path)


@pytest.mark.parametrize("scenario", sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml")))
def test_same_seed_regenerates_the_whole_run_req10(scenario):
    spec = load(scenario)
    a, b = generate(spec, seed=3), generate(spec, seed=3)
    assert a.measurements == b.measurements
    assert a.truth == b.truth
    assert a.events == b.events
    assert a.emitters == b.emitters
    assert generate(spec, seed=4).measurements != a.measurements, "the seed has no effect"
