"""Hard rules from AGENTS.md that a machine can check (systems/quality.md). Ported from #64
(AceAtDev) and extended to what main holds today.

- Receive-only (ADR-0001, REQ-07): no SDR transmit call, Wi-Fi frame injection, active scan or
  FTM, and no GNSS signal generator anywhere in the code, firmware, flight or Pi scripts.
- Privacy (ADR-0011, REQ-08): a recorded Wi-Fi session holds no raw BSSID or SSID; ADS-B frames
  other than extended squitters never reach the decoder; no decoder of communication content.
- Data rules: no raw session data and no confidential deck tracked by git.
- Reproducibility (REQ-10): the same seed regenerates the whole run.

The scans know fixed lists of APIs, so they back up the code inspection REQ-07 and REQ-08 ask for
and do not replace it. They read code only: comments and docstrings are stripped first, so prose
about a rule (like this file's) is not a violation. `tests/` is not scanned.
"""

import functools
import io
import re
import subprocess
import threading
import time
import tokenize
from pathlib import Path

import numpy as np
import pytest
import yaml

from pnt.sim.scenario import SCENARIO_DIR, generate, load

ROOT = Path(__file__).resolve().parents[1]

# --- scanning code, not prose -----------------------------------------------------------------

SCAN_ROOTS = ("src", "firmware", "flight", "deploy", "analysis")
SCAN_FILES = ("justfile",)
SCAN_SKIP_DIRS = {".pio", "__pycache__", ".venv", "node_modules"}
PY = {".py"}
C_LIKE = {".c", ".cc", ".cpp", ".h", ".hpp", ".ino", ".js"}
HASH_COMMENTS = {".sh", ".bash", ".yaml", ".yml", ".conf", ".service", ".ini", ".toml", ".cfg"}
HASH_COMMENTS_NAMES = {"justfile", "Makefile"}
_C_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_HASH_COMMENT = re.compile(r"(?:^|(?<=\s))#.*$", re.M)


def _python_code(text: str) -> str:
    """The source with comments and docstrings blanked, line numbers kept."""
    out = [list(line) for line in io.StringIO(text).readlines()]  # rows as tokenize counts them
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return text  # scan it whole rather than skip it
    skip = {tokenize.NL, tokenize.COMMENT}
    starts = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING}
    sig = [t for t in tokens if t.type not in skip]
    blank = [t for t in tokens if t.type == tokenize.COMMENT]
    for i, t in enumerate(sig):
        prev = sig[i - 1].type if i else tokenize.ENCODING
        nxt = sig[i + 1].type if i + 1 < len(sig) else tokenize.ENDMARKER
        if (
            t.type == tokenize.STRING
            and prev in starts
            and nxt in (tokenize.NEWLINE, tokenize.ENDMARKER)
        ):
            blank.append(t)  # a bare string statement: a docstring
    for t in blank:
        (r0, c0), (r1, c1) = t.start, t.end
        for r in range(r0, r1 + 1):
            row = out[r - 1]
            a = c0 if r == r0 else 0
            b = c1 if r == r1 else len("".join(row).rstrip("\r\n"))  # keep the line break
            row[a:b] = " " * (b - a)
    return "".join("".join(row) for row in out)


def code_of(path: Path, text: str) -> str:
    if path.suffix in PY:
        return _python_code(text)
    if path.suffix in C_LIKE:
        return _C_COMMENT.sub(lambda m: "\n" * m.group().count("\n"), text)
    if path.suffix in HASH_COMMENTS or path.name in HASH_COMMENTS_NAMES:
        return _HASH_COMMENT.sub("", text)
    return text


def _scanned_files() -> list[Path]:
    exts = PY | C_LIKE | HASH_COMMENTS
    files = [ROOT / name for name in SCAN_FILES if (ROOT / name).is_file()]
    for root in SCAN_ROOTS:
        files += [
            p
            for p in (ROOT / root).rglob("*")
            if p.is_file()
            and (p.suffix in exts or p.name in HASH_COMMENTS_NAMES)
            and not SCAN_SKIP_DIRS.intersection(p.parts)
        ]
    return files


@functools.cache
def _code() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each scanned file's code lines, read and stripped once per test process."""
    files = _scanned_files()
    for root in SCAN_ROOTS:
        assert any(p.is_relative_to(ROOT / root) for p in files), f"nothing scanned in {root}/"
    return tuple(
        (
            str(p.relative_to(ROOT)),
            tuple(code_of(p, p.read_text(encoding="utf-8", errors="ignore")).splitlines()),
        )
        for p in files
    )


def _hits(patterns: dict[str, re.Pattern]) -> list[str]:
    return [
        f"{path}:{number}: {name}: {line.strip()[:100]}"
        for path, lines in _code()
        for number, line in enumerate(lines, 1)
        for name, pattern in patterns.items()
        if pattern.search(line)
    ]


def _matches(patterns: dict[str, re.Pattern], line: str) -> list[str]:
    return [name for name, pattern in patterns.items() if pattern.search(line)]


# --- REQ-07: receive-only ---------------------------------------------------------------------

TRANSMIT_APIS = {
    "SoapySDR": r"\bSOAPY_SDR_TX\b|\bwriteStream\s*\(",
    "HackRF": r"\bhackrf_(?:start_tx|stop_tx|set_txvga_gain)\b"
    r"|\bhackrf_transfer\b.*[\s\"'](?:-[tc]|--transmit)(?:[\s\"']|$)",
    "bladeRF": r"\bbladerf_sync_tx\b|\bBLADERF_(?:MODULE_TX|CHANNEL_TX|TX_X[12])\b|\.sync_tx\s*\(",
    "UHD": r"\bget_tx_stream\b|\btx_streamer\b|\btx_metadata_t\b|\bsend_waveform\b|\busrp_sink\b",
    "LimeSuite": r"\bLMS_CH_TX\b|\bLMS_SendStream\b",
    "PlutoSDR": r"\.tx\s*\(|\btx_(?:lo|hardwaregain\w*|cyclic_buffer|enabled_channels)\b"
    r"|\biio_buffer_push\b|\b(?:pluto|fmcomms\d?)_sink\b",
    "GNU Radio sink": r"\bosmosdr\.sink\b|\bsoapy\.sink\b|\bbladeRF_sink\b",
    "Pi GPIO transmit": r"\b(?:rpitx|sendiq|pifmrds|pifm|fm_transmitter)\b",
    "GNSS signal generator": r"\b(?:gps|gnss|galileo|glonass|beidou|multi)[-_]sdr[-_]sim\b",
    "Wi-Fi frame injection": r"\besp_wifi_80211_tx\b|\baireplay-ng\b|\bmdk[34]\b",
    # FTM was dropped because the initiator transmits (ADR-0018)
    "Wi-Fi FTM initiator": r"\besp_wifi_ftm_initiate_session\b|\bftm_request\b",
    # an active scan sends probe requests; the Pi scans passively (pnt.payload.wifi)
    "Wi-Fi active scan": r"\bWIFI_SCAN_TYPE_ACTIVE\b|\biw\b.*\bscan\b(?!.*\bpassive\b)",
}
TRANSMIT_RE = {name: re.compile(p) for name, p in TRANSMIT_APIS.items()}


def test_no_transmit_calls_req07():
    hits = _hits(TRANSMIT_RE)
    assert not hits, "transmit path found (ADR-0001, REQ-07):\n" + "\n".join(hits)


@pytest.mark.parametrize(
    ("line", "api"),
    [
        ("stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32)", "SoapySDR"),
        ("sdr.writeStream(stream, [iq], len(iq))", "SoapySDR"),
        ("hackrf_start_tx(device, callback, nullptr);", "HackRF"),
        ("hackrf_transfer -f 1575420000 -t gps.bin", "HackRF"),
        ("run(['hackrf_transfer', '-f', '1575420000', '-t', 'gps.bin'])", "HackRF"),
        ("bladerf_sync_tx(dev, samples, n, NULL, 1000);", "bladeRF"),
        ("streamer = usrp.get_tx_stream(args)", "UHD"),
        ("LMS_EnableChannel(dev, LMS_CH_TX, 0, true);", "LimeSuite"),
        ("sdr.tx(iq)", "PlutoSDR"),
        ("sink = osmosdr.sink(args='hackrf')", "GNU Radio sink"),
        ("subprocess.run(['sendiq', '-i', 'a.iq'])", "Pi GPIO transmit"),
        ("./gps-sdr-sim -e brdc.n -l 45,-75,70", "GNSS signal generator"),
        ("esp_wifi_80211_tx(WIFI_IF_STA, frame, len, false);", "Wi-Fi frame injection"),
        ("esp_wifi_ftm_initiate_session(&cfg);", "Wi-Fi FTM initiator"),
        ('cmd = ["iw", "dev", iface, "scan"]', "Wi-Fi active scan"),
        ("cfg.scan_type = WIFI_SCAN_TYPE_ACTIVE;", "Wi-Fi active scan"),
    ],
)
def test_scan_flags_planted_transmit_call_req07(line, api):
    assert api in _matches(TRANSMIT_RE, line)


@pytest.mark.parametrize(
    "line",
    [
        "samples = RtlSdr().read_samples(256 * 1024)",
        "rtl_sdr -d 0 -f 739000000 -s 1920000 -",
        "hackrf_transfer -f 739000000 -r capture.iq",  # receive (HackRF is excluded: ADR-0001)
        "rtl_power -d 0 -f 24M:1766M:100k -i 30",
        'cmd = ["iw", "dev", self.iface, "scan", "passive"]',
        "mavlink_msg_pnt_wifi_ap_send(chan, t, hash, rssi, ch, 0);",  # MAVLink over serial
        "WiFi.softAP(ssid, password, channel);",  # a licence-exempt control link (REQ-07)
        "tx_power_dbw = row['tx_power_dbw']",  # a tower's filed power, not ours
    ],
)
def test_scan_passes_receive_calls_req07(line):
    assert not _matches(TRANSMIT_RE, line)


def test_comments_and_docstrings_are_not_scanned():
    py = '"""Never call hackrf_start_tx."""\n# sdr.tx(iq) would transmit\nx = 1  # rpitx\n'
    assert not any(_matches(TRANSMIT_RE, ln) for ln in code_of(Path("a.py"), py).splitlines())
    c = "/* SOAPY_SDR_TX\n is banned */ int x; // bladerf_sync_tx\n"
    assert not any(_matches(TRANSMIT_RE, ln) for ln in code_of(Path("a.cpp"), c).splitlines())
    sh = "# rpitx is banned\nrtl_sdr -f 1e9 -  # not sendiq\n"
    assert not any(_matches(TRANSMIT_RE, ln) for ln in code_of(Path("a.sh"), sh).splitlines())
    # ... but code beside them still is, at its own line number
    lines = code_of(Path("a.py"), '"""Doc."""\n\nsdr.tx(iq)  # note\n').splitlines()
    assert _matches(TRANSMIT_RE, lines[2]) == ["PlutoSDR"]
    s = code_of(Path("a.py"), 's = "hackrf_transfer -t x"\n')
    assert _matches(TRANSMIT_RE, s) == ["HackRF"]  # a string that is not a docstring is code


# --- REQ-08: no communication content, identifiers hashed at capture --------------------------

COMM_CONTENT = {
    # LTE: only PSS/SSS/CRS and broadcast fields are read (ADR-0011); these carry user traffic
    "LTE user or control channel": r"(?i)(?<![a-z0-9])"
    r"(?:e?pdcch|pdsch|pusch|pucch|phich|dci)(?![a-z0-9])",
    # Mode S: replies to ground interrogations, decoded by pyModeS's Comm-B/D and surveillance
    "Mode S reply decoding": r"\b(?:pms|pyModeS)(?:\.\w+)*\.(?:commb|bds|idcode|altcode)\b"
    r"|\bfrom\s+pyModeS(?:\.\w+)*\s+import\s+.*\b(?:commb|bds|idcode|altcode)\b",
    "Aviation datalink": r"(?i)\b(?:acars\w*|cpdlc|vdl2?|dumpvdl2)\b",
    "Packet capture": r"(?i)\b(?:tcpdump|tshark|scapy|pyshark|pcap_open_live)\b"
    r"|\biw\b.*\b(?:type|set)\s+monitor\b",
}
COMM_RE = {name: re.compile(p) for name, p in COMM_CONTENT.items()}


def test_no_communication_content_decoders_req08():
    hits = _hits(COMM_RE)
    assert not hits, "decoder of communication content found (ADR-0011, REQ-08):\n" + "\n".join(
        hits
    )


@pytest.mark.parametrize(
    ("line", "what"),
    [
        ("grid = demap_pdsch(frame, cell)", "LTE user or control channel"),
        ("dci = decode_dci(pdcch_symbols)", "LTE user or control channel"),
        ("mb = pms.commb.selcall(msg)", "Mode S reply decoding"),
        ("from pyModeS.decoder import bds", "Mode S reply decoding"),
        ("alt = pyModeS.common.altcode(msg)", "Mode S reply decoding"),
        ("subprocess.Popen(['acarsdec', '-r', '0'])", "Aviation datalink"),
        ("from scapy.all import sniff", "Packet capture"),
        ("iw dev wlan0 set type monitor", "Packet capture"),
    ],
)
def test_scan_flags_planted_comm_decoder_req08(line, what):
    assert what in _matches(COMM_RE, line)


@pytest.mark.parametrize(
    "line",
    [
        "pss = detect_pss(iq, n_id_2)",
        "self._pipe = pyModeS.PipeDecoder()",
        "nic(tc, version, nic_a, nic_b)",
    ],
)
def test_scan_passes_broadcast_decoding_req08(line):
    assert not _matches(COMM_RE, line)


ADSB_FRAMES = {  # one frame per downlink format; only DF17/18 are broadcast for everyone
    4: "20001838CA3804",  # surveillance altitude reply
    5: "28001A1BCA3804",  # surveillance identity reply
    11: "5D40621D9E2E11",  # all-call reply
    20: "A0001838CA380031440000F24177",  # Comm-B altitude reply: interrogated content
    21: "A8001EBCFFFB23286004A73F6A5B",  # Comm-B identity reply
    24: "C0001838CA380031440000F24177",  # Comm-D extended length message
}


def test_adsb_decoder_never_sees_interrogation_replies_req08(monkeypatch):
    """ADR-0011: Mode S replies to ground interrogations (Comm-B carries what a radar asked for)
    are dropped before pyModeS sees them; only DF17/18 extended squitters are decoded."""
    pyModeS = pytest.importorskip("pyModeS")
    from pnt.frontends.adsb import Decoder

    seen: list[int] = []
    decode = pyModeS.PipeDecoder.decode

    def spy(self, msg, *args, **kw):
        seen.append(int(msg[:2], 16) >> 3)
        return decode(self, msg, *args, **kw)

    monkeypatch.setattr(pyModeS.PipeDecoder, "decode", spy)
    dec = Decoder(origin_llh=(45.0, -75.0, 70.0))
    fixture = (ROOT / "tests/fixtures/adsb/riddle-40621d.txt").read_text().splitlines()
    squitters = [ln.split()[1] for ln in fixture if ln and not ln.startswith("#")]
    for i, line in enumerate([*(f"*{f};" for f in ADSB_FRAMES.values()), *squitters]):
        dec.add(i * 10**9, line)
    assert 17 in seen, "no extended squitter was decoded: the check would be hollow"
    assert set(seen) <= {17, 18}, f"pyModeS decoded downlink formats {sorted(set(seen))}"


IW_SCAN = (
    "BSS 00:11:22:33:44:55(on wlan0)\n\tfreq: 2412\n\tsignal: -48.00 dBm\n\tSSID: HomeNet-5G\n"
    "BSS AA:BB:CC:DD:EE:0F(on wlan0) -- associated\n\tfreq: 5180\n\tsignal: -71.00 dBm\n"
    "\tSSID: CorpGuest\n\tRSN:\t * Version: 1\n"
)
WAIT_S = 10.0  # hang guard, not a requirement
RAW_BSSIDS = ("00:11:22:33:44:55", "AA:BB:CC:DD:EE:0F")
SSIDS = ("HomeNet-5G", "CorpGuest")


def _raw_forms(bssid: str) -> set[bytes]:
    octets = bssid.lower().split(":")
    forms = {sep.join(octets) for sep in (":", "-", "", ".")}
    forms |= {f.upper() for f in forms}
    forms.add(bytes.fromhex("".join(octets)).decode("latin-1"))  # the raw 6 bytes
    return {f.encode("latin-1") for f in forms}


def _session_bytes(folder: Path) -> list[tuple[str, bytes]]:
    """Every byte a session holds, decompressed: each MCAP record, the MCAP metadata, and each
    other file whole."""
    from mcap.reader import make_reader

    out = []
    for path in sorted(folder.iterdir()):
        if path.suffix != ".mcap":
            out.append((path.name, path.read_bytes()))
            continue
        with open(path, "rb") as f:
            reader = make_reader(f)
            for _, channel, msg in reader.iter_messages():
                out.append((f"{path.name} {channel.topic}", msg.data))
            for meta in reader.iter_metadata():
                out.append((f"{path.name} metadata", repr(meta.metadata).encode()))
    return out


def test_recorded_wifi_session_holds_no_bssid_or_ssid_req08(tmp_path, monkeypatch):
    """The session audit REQ-08 asks for, for Wi-Fi: record with the Pi's scanner over a fake
    `iw`, then search every byte of the session for each raw BSSID and SSID."""
    from pnt.payload import wifi
    from pnt.payload.recorder import Recorder

    real_run = subprocess.run
    scans = threading.Event()

    def fake_run(cmd, *args, **kw):
        if "iw" in list(cmd)[:3]:  # `iw dev wlan0 scan passive`, maybe behind `sudo -n`
            scans.set()
            return subprocess.CompletedProcess(cmd, 0, stdout=IW_SCAN, stderr="")
        return real_run(cmd, *args, **kw)

    monkeypatch.setattr(wifi.subprocess, "run", fake_run)
    monkeypatch.setattr(wifi.WifiScan, "probe", lambda self: None)
    folder = tmp_path / "20261110-1430-handheld-wifi"
    rec = Recorder(folder, [wifi.WifiScan(period_s=0.05)], platform="handheld")
    rec.start()
    try:
        assert scans.wait(WAIT_S), "the scanner never ran"
        deadline = time.monotonic() + WAIT_S
        while rec.counts.get("wifi", 0) < 2 * len(RAW_BSSIDS) and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        rec.stop()

    blobs = _session_bytes(folder)
    wifi_records = [b for name, b in blobs if name.endswith("/meas/wifi")]
    assert wifi_records, "no wifi records in the session: the audit would be hollow"
    emitters = {b.split(b'"wifi:')[1][:16] for b in wifi_records}
    assert len(emitters) == len(RAW_BSSIDS), f"expected one hashed emitter per AP: {emitters}"
    forbidden = {f for b in RAW_BSSIDS for f in _raw_forms(b)}
    forbidden |= {s.encode() for s in SSIDS}
    leaks = sorted({f"{name}: {f!r}" for name, data in blobs for f in forbidden if f in data})
    assert not leaks, "raw identifiers in the session (ADR-0011, REQ-08):\n" + "\n".join(leaks)


# --- data rules -------------------------------------------------------------------------------

# What a session folder holds (systems/icd/session.md) and other raw captures.
RAW_SUFFIXES = (".mcap", ".cu8", ".cs8", ".cf32", ".iq", ".sigmf-data", ".mp4", ".h264", ".pcap",
                ".pcapng", ".tlog")  # fmt: skip


def _is_raw_session_data(path: str) -> bool:
    if path.startswith("tests/fixtures/"):
        return False
    if path.startswith("data/sessions/"):
        return path != "data/sessions/.gitkeep"
    return path.lower().endswith(RAW_SUFFIXES)


def _tracked() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked, "git lists no tracked files"
    return tracked


def test_no_raw_session_data_tracked():
    raw = [path for path in _tracked() if _is_raw_session_data(path)]
    assert not raw, "raw session data tracked by git (AGENTS.md):\n" + "\n".join(raw)


@pytest.mark.parametrize(
    "path",
    [
        "data/sessions/20261110-handheld/meta.yaml",
        "data/sessions/20261110-handheld/session.mcap",
        "analysis/session.mcap",
        "sdr_a.cu8",
        "docs/camera.mp4",
        "flight/logs/2026-11-12.tlog",
    ],
)
def test_planted_raw_session_data_is_flagged(path):
    assert _is_raw_session_data(path)


@pytest.mark.parametrize(
    "path", ["data/sessions/.gitkeep", "tests/fixtures/short/session.mcap", "data/reference/a.csv"]
)
def test_allowed_files_are_not_flagged(path):
    assert not _is_raw_session_data(path)


DECK = "Kick Off Presentation Combined.pdf"  # named in .gitignore
CONFIDENTIAL_MARK = b"not for public " + b"consumption"  # split, so this file does not match


def _is_confidential(path: str, data: bytes) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name == DECK or ".confidential." in name:
        return True
    return path != ".gitignore" and CONFIDENTIAL_MARK in data.lower()


def test_no_confidential_files_tracked():
    """AGENTS.md: the kickoff deck and anything marked confidential stay out of git. By name and
    by the deck's marking in plain text; a compressed PDF hides its text from this check."""
    bad = [
        p
        for p in _tracked()
        if (ROOT / p).is_file() and _is_confidential(p, (ROOT / p).read_bytes())
    ]
    assert not bad, "confidential files tracked by git:\n" + "\n".join(bad)


@pytest.mark.parametrize(
    ("path", "data"),
    [
        (f"docs/{DECK}", b"%PDF"),
        ("notes/deck.confidential.md", b""),
        ("notes/slides.md", b"Confidential\xe2\x80\x94" + CONFIDENTIAL_MARK.title()),
    ],
)
def test_planted_confidential_file_is_flagged(path, data):
    assert _is_confidential(path, data)


# --- REQ-10: same seed, same run --------------------------------------------------------------


# Every standalone scenario, plus the cheapest run carrying each fault type no standalone one has
# (CPU time of one generation, measured at 4c8b0ab). Generating all ~100 set runs would add
# minutes; `test_req10_runs_cover_every_fault_type` fails when a new fault type needs adding here.
REQ10_SET_RUNS = (
    "easy-baro-drift",  # 0.1 s
    "easy-gps-low-sats",  # 0.1 s
    "easy-gps-no-fix",  # 0.1 s
    "easy-tower-clock-step",  # 0.1 s
    "challenge-timing-outage-tower-holdover",  # 2.1 s
    "challenge-timing-outage-imu-bias",  # 2.7 s
    "realistic-with-base-long-outage-base-clock-step",  # 1.1 s
    "realistic-with-base-long-outage-base-moved",  # 1.1 s
)
REQ10_RUNS = (*sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml")), *REQ10_SET_RUNS)


def _fault_types(name: str) -> set[str]:
    return {f["type"] for f in load(name).get("faults") or []}


def _listed_types(node) -> set[str]:
    """`type` of every mapping that is a list item: a fault (a trajectory is a mapping value)."""
    if isinstance(node, dict):
        return set().union(set(), *map(_listed_types, node.values()))
    if isinstance(node, list):
        own = {i["type"] for i in node if isinstance(i, dict) and "type" in i}
        return own.union(*map(_listed_types, node))
    return set()


def test_req10_runs_cover_every_fault_type():
    every = set().union(
        *(_listed_types(yaml.safe_load(p.read_text())) for p in SCENARIO_DIR.rglob("*.yaml"))
    )
    covered = set().union(*map(_fault_types, REQ10_RUNS))
    assert every, "no fault types found in the scenarios"
    assert every <= covered, f"add a run with {sorted(every - covered)} to REQ10_SET_RUNS"


def _same(a, b) -> bool:
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, np.ndarray):
        return np.array_equal(a, b, equal_nan=a.dtype.kind == "f")
    return a == b


RUN_PARTS = (
    "measurements",
    "truth",
    "events",
    "emitters",
    "tower_clocks",
    "rx_clocks",
    "reference",
)


# Runs that also check the seed reaches each random stream (IMU, LTE front end, tower and dongle
# clocks, the reference station): between them they draw from every stream `generate` seeds.
SEED_CHECK = {
    "gps-outage",
    "uc01-drone-circuit-with-base",
    "challenge-timing-outage-tower-holdover",
}


def _by_stream(run) -> dict:
    groups: dict = {}
    for m in run.measurements:
        groups.setdefault(f"{m.receiver} {m.source}", []).append(m)
    for part in ("tower_clocks", "rx_clocks"):
        groups |= {f"{part} {k}": v for k, v in getattr(run, part).items()}
    if run.reference is not None:
        groups["reference station"] = run.reference  # its surveyed position draws a survey error
    return groups


@pytest.mark.parametrize("scenario", REQ10_RUNS)
def test_same_seed_regenerates_the_whole_run_req10(scenario):
    # a fresh spec each time: generation may consume keys from it
    a, b = generate(load(scenario), seed=3), generate(load(scenario), seed=3)
    differ = [part for part in RUN_PARTS if not _same(getattr(a, part), getattr(b, part))]
    assert not differ, f"{scenario}: seed 3 twice gives different {differ}"
    if scenario in SEED_CHECK:
        a_streams, c_streams = _by_stream(a), _by_stream(generate(load(scenario), seed=4))
        assert a_streams.keys() == c_streams.keys()
        fixed = [k for k in a_streams if _same(a_streams[k], c_streams[k])]
        assert not fixed, f"{scenario}: seeds 3 and 4 give the same {fixed}"


def test_seed_check_covers_every_stream():
    assert SEED_CHECK <= set(REQ10_RUNS)
    runs = {name: load(name) for name in SEED_CHECK}
    assert any(r.get("reference") for r in runs.values()), "no run with a reference station"
    shapes = {s.get("record_shape") for r in runs.values() for s in r["sources"].values()}
    assert "front_end" in shapes, "no run with front-end-shaped LTE records"
    assert any("imu" in r["sources"] for r in runs.values()), "no run with an IMU"
