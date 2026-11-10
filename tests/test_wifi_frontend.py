"""Wi-Fi front end (#22) on hub MAVLink bytes: no hub, no radio, no network.

The bytes are made with the generated `pnt_mavlink` encoder, the `pnt.xml` contract a hub must
speak (ADR-0018 fallback): PPS edges, AP sightings and one FTM range. No hub exists to record
real bytes from yet.
"""

import pytest

from pnt.core.measurement import validate
from pnt.core.time import WEEK_NS
from pnt.frontends import wifi
from pnt.io import pnt_mavlink
from pnt.payload.wifi import RSSI_SIGMA_DB, hash_bssid

SALT = b"s" * 32
WEEK, TOW_MS = 2440, 300_000
PPM = 20e-6  # the hub's crystal runs 20 ppm fast
US_PER_S = 1_000_000 * (1 + PPM)


def gps_ns(seconds_after_first_edge: float) -> int:
    return WEEK * WEEK_NS + TOW_MS * 1_000_000 + round(seconds_after_first_edge * 1e9)


def hub(seconds: float) -> int:
    """Hub time_us `seconds` of GPS time after the first PPS edge (which is at 5 s of hub)."""
    return round(5_000_000 + seconds * US_PER_S)


def hub_bytes() -> bytes:
    mav = pnt_mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
    ap = list(bytes.fromhex(hash_bssid("00:11:22:33:44:55", SALT)))
    ap5 = list(bytes.fromhex(hash_bssid("aa:bb:cc:dd:ee:ff", SALT)))
    msgs = [
        mav.pnt_wifi_ap_encode(hub(-3.0), ap, -60, 6, 0),  # 3 s before the first edge: untimed
        *(mav.pnt_pps_encode(hub(k), WEEK, TOW_MS + 1000 * k) for k in range(3)),
        mav.pnt_wifi_ap_encode(hub(0.5), ap, -48, 6, 0),
        mav.pnt_wifi_ap_encode(hub(1.25), ap5, -71, 36, 1),
        mav.pnt_ftm_range_encode(hub(1.75), ap5, 12.5, 2.0, 8),
        mav.pnt_wifi_ap_encode(hub(3.5), ap, -50, 6, 0),  # 1.5 s past the last edge: timed
    ]
    return b"".join(m.pack(mav) for m in msgs)


def test_hub_bytes_become_rssi_and_range_records():
    r = wifi.process(wifi.parse_bytes(hub_bytes()))
    for m in r.measurements:
        validate(m)
    assert r.untimed == 1
    rssi = [m for m in r.measurements if m.kind == "rssi"]
    assert [m.value[0] for m in rssi] == [-48.0, -71.0, -50.0]
    # the hub clock's 20 ppm is taken out between edges: within 1 us of GPS time
    for m, s in zip(rssi, (0.5, 1.25, 3.5), strict=True):
        assert m.t_ns == pytest.approx(gps_ns(s), abs=1_000)
    # the same 16-hex emitter as the Pi's own scans of the same AP (pnt.payload.wifi)
    assert rssi[0].emitter == "wifi:" + hash_bssid("00:11:22:33:44:55", SALT)
    assert rssi[0].sigma == (RSSI_SIGMA_DB,)
    assert rssi[0].meta["freq_mhz"] == 2437.0 and rssi[1].meta["freq_mhz"] == 5180.0
    assert rssi[1].meta["ftm_responder"] is True
    (rng,) = [m for m in r.measurements if m.kind == "range"]
    assert rng.value == (12.5,) and rng.emitter == rssi[1].emitter
    assert rng.sigma[0] == pytest.approx(299_792_458.0 * 2e-9 / 2)
    assert rng.t_ns == pytest.approx(gps_ns(1.75), abs=1_000)


def test_corrupt_bytes_are_dropped_not_misread():
    data = bytearray(hub_bytes())
    data[30] ^= 0xFF  # inside the first message
    msgs = wifi.parse_bytes(bytes(data))
    assert len(msgs) == 7  # one of eight lost to its CRC
    assert all(m.get_type().startswith("PNT_") for m in msgs)


def test_dicts_as_logged_work_too():
    msgs = [m.to_dict() for m in wifi.parse_bytes(hub_bytes())]
    r = wifi.process(msgs, receiver="reference")
    assert len(r.measurements) == 4 and {m.receiver for m in r.measurements} == {"reference"}


def test_one_pps_edge_is_not_enough_to_time_anything():
    mav = pnt_mavlink.MAVLink(None)
    msgs = [mav.pnt_pps_encode(hub(0), WEEK, TOW_MS),
            mav.pnt_wifi_ap_encode(hub(0.5), [1] * 8, -40, 1, 0)]  # fmt: skip
    r = wifi.process(msgs)
    assert r.measurements == [] and r.untimed == 1


@pytest.mark.parametrize(
    "ch,mhz", [(1, 2412.0), (13, 2472.0), (14, 2484.0), (36, 5180.0), (165, 5825.0), (0, None)]
)
def test_channel_frequencies(ch, mhz):
    assert wifi.channel_mhz(ch) == mhz


def test_no_raw_bssid_reaches_a_record_adr0011():
    r = wifi.process(wifi.parse_bytes(hub_bytes()))
    text = repr([(m.emitter, m.meta) for m in r.measurements]).lower()
    assert "00:11:22" not in text and "001122334455" not in text
