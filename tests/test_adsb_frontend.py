"""ADS-B front end (#22) on Mode S frames: no SDR, no readsb, no network.

Two kinds of frames:
- Published: the airborne position pair of aircraft 40621D from Junzi Sun, *The 1090 Megahertz
  Riddle* (2nd ed., TU Delft OPEN, 2021, https://mode-s.org/1090mhz/), whose worked answer is
  52.2572 N, 3.91937 E, 38000 ft. Typed in: `fixtures/adsb/riddle-40621d.txt`.
- Made here: `es_frame` encodes DF17 airborne positions (CPR, DO-260B) and operational status
  for a known aircraft, so the decoded position, NACp and NIC can be checked against truth.
"""

import math
from pathlib import Path

import pytest

from pnt.core import frames
from pnt.core.measurement import validate
from pnt.frontends import adsb

FIXTURE = Path(__file__).parent / "fixtures" / "adsb" / "riddle-40621d.txt"
T0 = 1_478_000_000_000_000_000
ORIGIN = (45.3876, -75.6960, 70.0)


# --- a minimal DF17 encoder (DO-260B CPR and the Mode S CRC), independent of pyModeS -----------


def crc24(bits88: int) -> int:
    """Mode S parity of the first 88 bits (generator 0x1FFF409)."""
    data = bits88 << 24
    for i in range(111, 23, -1):
        if data >> i & 1:
            data ^= 0x1FFF409 << (i - 24)
    return data & 0xFFFFFF


def es_frame(icao: int, me: int) -> str:
    head = (17 << 3 | 5) << 80 | icao << 56 | me
    return f"{head << 24 | crc24(head):028X}"


def nl(lat: float) -> int:
    """Number of longitude zones at `lat` (NZ = 15)."""
    if lat == 0:
        return 59
    if abs(lat) >= 87:
        return 2 if abs(lat) == 87 else 1
    c = math.cos(math.radians(abs(lat))) ** 2
    return math.floor(2 * math.pi / math.acos(1 - (1 - math.cos(math.pi / 30)) / c))


def cpr(lat: float, lon: float, odd: int) -> tuple[int, int]:
    dlat = 360 / (60 - odd)
    yz = math.floor(2**17 * (lat % dlat) / dlat + 0.5)
    rlat = dlat * (yz / 2**17 + math.floor(lat / dlat))
    dlon = 360 / max(nl(rlat) - odd, 1)
    xz = math.floor(2**17 * (lon % dlon) / dlon + 0.5)
    return yz % 2**17, xz % 2**17


def position_me(tc: int, lat: float, lon: float, odd: int, alt_ft=None, gnss_m=None, nic_b=0):
    if tc >= 20:
        ac = round(gnss_m)
    else:
        n = round((alt_ft + 1000) / 25)
        ac = (n >> 4) << 5 | 1 << 4 | (n & 0xF)  # Q bit set: 25 ft steps
    y, x = cpr(lat, lon, odd)
    return tc << 51 | nic_b << 48 | ac << 36 | odd << 34 | y << 17 | x


def status_me(version: int, nic_a: int, nac_p: int) -> int:
    return 31 << 51 | version << 13 | nic_a << 12 | nac_p << 8


def track(icao, lat0, lon0, n=12, dt_s=0.5, east_mps=200.0, **kw):
    """`n` alternating even/odd position frames of an aircraft flying east."""
    out = []
    for i in range(n):
        lon = lon0 + east_mps * i * dt_s / (111_320 * math.cos(math.radians(lat0)))
        t = T0 + round(i * dt_s * 1e9)
        out.append((t, f"*{es_frame(icao, position_me(lat=lat0, lon=lon, odd=i % 2, **kw))};"))
    return out


# --- tests ------------------------------------------------------------------------------------


def test_encoder_round_trips_through_pyModeS():
    import pyModeS

    f = es_frame(0xC0FFEE, position_me(11, 45.40, -75.70, 0, alt_ft=12000))
    d = pyModeS.decode(f, reference=(45.39, -75.69))
    assert d["crc_valid"] and d["icao"] == "C0FFEE" and d["altitude"] == 12000
    assert d["latitude"] == pytest.approx(45.40, abs=1e-4)
    assert d["longitude"] == pytest.approx(-75.70, abs=1e-4)


def test_published_pair_decodes_to_the_worked_answer():
    rows = [ln.split() for ln in FIXTURE.read_text().splitlines() if ln and ln[0] != "#"]
    out = adsb.process([(T0 + round(float(t) * 1e9), avr) for t, avr in rows], (52.0, 4.0, 0.0))
    assert out, "pyModeS bootstraps a track after three consistent positions"
    for m in out:
        validate(m)
    assert {m.emitter for m in out} == {"adsb:40621d"}
    even = [m for m in out if m.meta["llh"][0] == pytest.approx(52.2572, abs=5e-5)]
    assert even and even[0].meta["llh"][1] == pytest.approx(3.91937, abs=5e-5)
    assert even[0].meta["llh"][2] == pytest.approx(38000 * 0.3048)
    m = even[0]
    assert m.value[3:] == (0.0, 8.0)  # no status message: NACp unknown; TC 11, no supplement
    assert m.meta["alt_type"] == "baro_pressure" and m.sigma[2] == adsb.BARO_ALT_SIGMA_M
    want = frames.llh_to_enu(m.meta["llh"], (52.0, 4.0, 0.0))
    assert m.value[:3] == pytest.approx(tuple(want))


def test_made_track_recovers_position_nacp_and_nic():
    icao = 0xC0FFEE
    status = (T0 - 1, f"*{es_frame(icao, status_me(version=2, nic_a=1, nac_p=9))};")
    pos = track(icao, 45.45, -75.80, tc=11, alt_ft=12000, nic_b=1)
    out = adsb.process([status, *pos], ORIGIN)
    assert len(out) >= 6  # the first frames are held back while the track bootstraps
    for m in out:
        validate(m)
        k = round((m.t_ns - T0) / 0.5e9)
        lon = -75.80 + 200 * k * 0.5 / (111_320 * math.cos(math.radians(45.45)))
        truth = frames.llh_to_enu((45.45, lon, 12000 * 0.3048), ORIGIN)
        # CPR quantises airborne positions to 360/60/2^17 deg in latitude (5.1 m)
        assert m.value[0] == pytest.approx(truth[0], abs=6.0)
        assert m.value[1] == pytest.approx(truth[1], abs=6.0)
        assert m.value[2] == pytest.approx(truth[2], abs=0.5)
        assert m.value[3:] == (9.0, 9.0)  # NACp 9; TC 11 with both supplements: NIC 9
        assert m.sigma[:2] == pytest.approx((30 / 2.4477, 30 / 2.4477))
        assert m.emitter == "adsb:c0ffee" and m.source == "adsb"


def test_gnss_height_uses_vepu():
    icao = 0xABC123
    status = (T0 - 1, f"*{es_frame(icao, status_me(version=2, nic_a=0, nac_p=10))};")
    out = adsb.process([status, *track(icao, 45.30, -75.60, tc=20, gnss_m=3000)], ORIGIN)
    assert out
    m = out[-1]
    assert m.meta["alt_type"] == "gnss_hae" and m.value[3:] == (10.0, 11.0)
    assert m.sigma[2] == pytest.approx(15 / 1.96)
    # pyModeS reports GNSS height in whole feet: within 0.31 m of the metres sent
    assert m.meta["llh"][2] == pytest.approx(3000, abs=0.31)


def test_only_extended_squitter_with_good_crc_is_decoded_adr0011():
    good = es_frame(0xC0FFEE, position_me(11, 45.40, -75.70, 0, alt_ft=12000))
    bad = good[:-1] + ("0" if good[-1] != "0" else "1")
    df4 = "20001838CA3804"  # a surveillance reply to a ground interrogation: never decoded
    dec = adsb.Decoder(ORIGIN)
    for line in (f"*{bad};", f"*{df4};", "not a frame", f"@0123456789AB{good};"):
        assert dec.add(T0, line) is None
    assert dec.skipped == 3 and dec.decoded == 1


@pytest.mark.parametrize(
    "tc,version,a,b,want",
    [(9, 2, 0, 0, 11), (11, 2, 1, 1, 9), (11, 2, 1, 0, 8), (11, 1, 0, 1, 9), (11, 0, 1, 1, 8),
     (16, 2, 1, 1, 3), (16, 1, 0, 0, 2), (18, 2, 0, 0, 0), (21, 2, 0, 0, 10)],
)  # fmt: skip
def test_nic_follows_do260b(tc, version, a, b, want):
    assert adsb.nic(tc, version, a, b) == want


def test_parse_avr():
    assert adsb.parse_avr("*8d40621d58c382d690c8ac2863a7;") == "8D40621D58C382D690C8AC2863A7"
    assert adsb.parse_avr("@00000000012A8D40621D58C382D690C8AC2863A7;").startswith("8D4062")
    assert adsb.parse_avr("*8D4062;") is None and adsb.parse_avr("") is None
