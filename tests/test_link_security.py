"""Authenticated ground links (ADR-0026, #89): CurveZMQ between the Pis and the laptop.

Every attack test carries a control: the same attack against an unprotected client succeeds, so
a pass means the protection stopped it, not that nothing was sent. All on loopback, no network.
"""

from __future__ import annotations

import socket
import stat
import threading
import time

import msgspec
import pytest

from pnt.cli import main
from pnt.core.measurement import Measurement
from pnt.io import linkauth, session
from pnt.io.linkauth import ClientAuth, LinkSecurityError, ServerAuth
from pnt.payload.streamer import Streamer
from pnt.sources.live import LiveSource

zmq = pytest.importorskip("zmq")
pytestmark = pytest.mark.skipif(not zmq.has("curve"), reason="libzmq built without CURVE")

MARKER = b"AUTHENTIC"  # in every genuine record; a relay rewrites it where it can see it
FORGED = b"FORGED!!!"  # same length, so a plaintext rewrite still decodes


def rec(i: int, emitter: str = "AUTHENTIC-0001") -> Measurement:
    return Measurement(
        t_ns=i * 10_000_000, source="baro", kind="altitude", value=(100.0 + i,), sigma=(1.0,),
        emitter=emitter,
    )  # fmt: skip


@pytest.fixture
def hosts(tmp_path):
    """Key folders of the payload Pi, the base Pi and the laptop, set up as the RUNBOOK says."""
    d = {h: tmp_path / h for h in ("pi", "base", "laptop")}
    laptop = linkauth.generate("laptop", d["laptop"])
    payload = linkauth.generate("payload", d["pi"])
    linkauth.generate("reference", d["base"])
    for pi in ("pi", "base"):
        linkauth.trust("laptop", laptop.decode(), d[pi])
    linkauth.trust("payload", payload.decode(), d["laptop"])
    linkauth.trust("reference", str(d["base"] / "reference.key"), d["laptop"])  # from the file
    return d


def port(endpoint: str) -> int:
    return int(endpoint.rsplit(":", 1)[1])


def consume(live: LiveSource):
    got: list[Measurement] = []
    t = threading.Thread(target=lambda: got.extend(live), daemon=True)
    t.start()
    return got, t


def laptop_client(hosts, endpoint: str, role: str = "payload", **kw) -> LiveSource:
    auth = linkauth.client_auth({endpoint: role}, hosts["laptop"])
    return LiveSource(endpoint, idle_timeout_s=kw.pop("idle_timeout_s", 1.5), auth=auth, **kw)


class Relay:
    """A machine in the middle on loopback: forwards TCP both ways and keeps what the server
    sent. With `tamper`, after the first `after` bytes of each connection (the handshake), it
    rewrites MARKER where it can see it and otherwise flips the last byte of each chunk."""

    def __init__(self, upstream: str, tamper: bool = False, after: int = 1000):
        self.upstream = port(upstream)
        self.tamper, self.after = tamper, after
        self.seen = bytearray()
        self.modified = 0
        self.lock = threading.Lock()
        self.srv = socket.create_server(("127.0.0.1", 0))
        self.srv.settimeout(0.1)
        self.endpoint = f"tcp://127.0.0.1:{self.srv.getsockname()[1]}"
        self.stop = threading.Event()
        self.socks: list[socket.socket] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.srv.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            up = socket.create_connection(("127.0.0.1", self.upstream))
            self.socks += [conn, up]
            threading.Thread(target=self._pump, args=(conn, up, False), daemon=True).start()
            threading.Thread(target=self._pump, args=(up, conn, True), daemon=True).start()

    def _pump(self, src, dst, downstream: bool):
        n = 0
        try:
            while data := src.recv(65536):
                if downstream:
                    with self.lock:
                        self.seen += data
                    if self.tamper and n >= self.after:
                        data = self._rewrite(data)
                    n += len(data)
                dst.sendall(data)
        except OSError:
            pass
        finally:
            for s in (src, dst):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def _rewrite(self, data: bytes) -> bytes:
        with self.lock:
            self.modified += 1
        if MARKER in data:
            return data.replace(MARKER, FORGED)
        return data[:-1] + bytes([data[-1] ^ 0x01])

    def close(self):
        self.stop.set()
        self.srv.close()
        for s in self.socks:
            s.close()


def test_authenticated_stream_delivers_every_record_and_is_encrypted_on_the_wire(hosts):
    """The laptop gets exactly what the Pi sent, and a listener on the path sees ciphertext."""
    pi = Streamer("tcp://127.0.0.1:*", auth=linkauth.server_auth("payload", hosts["pi"]))
    relay = Relay(pi.endpoint)
    live = laptop_client(hosts, relay.endpoint)
    live.connect()
    assert pi.wait_for_subscriber(5.0)
    got, t = consume(live)
    sent = [rec(i) for i in range(50)]
    for m in sent:
        pi.send(m)
    pi.send_meta({"origin_llh": [45.0, -75.0, 70.0]}, "payload")
    t.join(timeout=10)
    pi.close()
    relay.close()
    assert got == sent
    assert live.meta["payload"]["origin_llh"] == [45.0, -75.0, 70.0]
    assert len(relay.seen) > 50 * 40  # the records crossed the relay ...
    assert MARKER not in relay.seen and b"origin_llh" not in relay.seen  # ... as ciphertext


def test_payload_and_base_are_each_pinned_to_their_own_key(hosts):
    """One laptop subscription to both Pis (ADR-0020), a different server key per endpoint."""
    pi = Streamer("tcp://127.0.0.1:*", auth=linkauth.server_auth("payload", hosts["pi"]))
    base = Streamer("tcp://127.0.0.1:*", auth=linkauth.server_auth("reference", hosts["base"]))
    auth = linkauth.client_auth({pi.endpoint: "payload", base.endpoint: "reference"},
                                hosts["laptop"])  # fmt: skip
    live = LiveSource([pi.endpoint, base.endpoint], idle_timeout_s=1.5, auth=auth)
    live.connect()
    assert pi.wait_for_subscriber(5.0) and base.wait_for_subscriber(5.0)
    got, t = consume(live)
    for i in range(10):
        pi.send(rec(2 * i))
        base.send(msgspec.structs.replace(rec(2 * i + 1), receiver="reference"))
    t.join(timeout=10)
    pi.close()
    base.close()
    assert len(got) == 20
    assert {m.receiver for m in got} == {"payload", "reference"}
    assert "payload key" in live.describe() and "reference key" in live.describe()


def _flood(attacker: Streamer, stop: threading.Event):
    i = 0
    while not stop.is_set():
        attacker.send(rec(i, emitter="FORGED"))
        attacker.send_meta({"origin_llh": [0.0, 0.0, 0.0]}, "payload")
        i += 1
        time.sleep(0.01)


def test_an_impersonating_server_gets_nothing_into_the_laptop(hosts, tmp_path):
    """Two impostors on the payload's address: a plaintext publisher, and a CurveZMQ server
    with its own key that even admits the real laptop key (which is public). The laptop pins the
    real payload key, so neither handshake completes. Controls: a client that does not pin the
    real key (plaintext, or pinned to the impostor's key) takes the forged records."""
    laptop_pub, laptop_sec = linkauth.load_own("laptop", hosts["laptop"])
    evil_pub, evil_sec = zmq.curve_keypair()
    plain = Streamer("tcp://127.0.0.1:*")
    curve = Streamer(
        "tcp://127.0.0.1:*", auth=ServerAuth("payload", evil_pub, evil_sec, {"laptop": laptop_pub})
    )
    protected = [laptop_client(hosts, plain.endpoint, idle_timeout_s=2.5),
                 laptop_client(hosts, curve.endpoint, idle_timeout_s=2.5)]  # fmt: skip
    trusts_impostor = ClientAuth(laptop_pub, laptop_sec, {curve.endpoint: ("payload", evil_pub)})
    controls = [
        LiveSource(plain.endpoint, idle_timeout_s=1.0),
        LiveSource(curve.endpoint, idle_timeout_s=1.0, auth=trusts_impostor),
    ]
    for src in protected + controls:
        src.connect()
    assert plain.wait_for_subscriber(5.0) and curve.wait_for_subscriber(5.0)  # the controls
    runs = [consume(src) for src in protected + controls]
    stop = threading.Event()
    floods = [threading.Thread(target=_flood, args=(a, stop)) for a in (plain, curve)]
    for f in floods:
        f.start()
    time.sleep(2.0)
    stop.set()
    for f in floods:
        f.join()
    for _, t in runs:
        t.join(timeout=10)
    plain.close()
    curve.close()
    (got_plain, _), (got_curve, _), (ctl_plain, _), (ctl_curve, _) = runs
    assert ctl_plain and ctl_curve, "control: an unpinned client takes the forged records"
    assert {m.emitter for m in ctl_plain + ctl_curve} == {"FORGED"}
    assert got_plain == [] and got_curve == []
    for src in protected:
        assert src.meta == {} and src.stats["received"] == 0


def test_the_pi_refuses_a_laptop_whose_key_it_does_not_trust(hosts, tmp_path):
    """An intruder with its own key pair and the Pi's public key: ZAP refuses it, while the
    trusted laptop on the same stream gets everything."""
    pi = Streamer("tcp://127.0.0.1:*", auth=linkauth.server_auth("payload", hosts["pi"]))
    linkauth.generate("laptop", tmp_path / "intruder")
    linkauth.trust("payload", str(hosts["pi"] / "payload.key"), tmp_path / "intruder")
    auth = linkauth.client_auth({pi.endpoint: "payload"}, tmp_path / "intruder")
    intruder = LiveSource(pi.endpoint, idle_timeout_s=1.5, auth=auth)
    intruder.connect()
    assert not pi.wait_for_subscriber(1.0)  # the intruder never subscribes
    laptop = laptop_client(hosts, pi.endpoint)
    laptop.connect()
    assert pi.wait_for_subscriber(5.0)
    got_intruder, ti = consume(intruder)
    got_laptop, tl = consume(laptop)
    sent = [rec(i) for i in range(30)]
    for m in sent:
        pi.send(m)
    ti.join(timeout=10)
    tl.join(timeout=10)
    refused = pi.refused
    pi.close()
    assert got_laptop == sent  # control: the stream works
    assert got_intruder == [] and intruder.stats["received"] == 0
    assert refused >= 1 and f"connections refused: {refused}" in pi.describe()


def test_a_record_tampered_in_flight_is_never_accepted(hosts):
    """A relay on the path rewrites the stream after the handshake. Every record the laptop
    accepts is one the Pi sent, unchanged. Control: the same relay on a plaintext stream gets
    forged records through."""

    def run(secure: bool):
        auth = linkauth.server_auth("payload", hosts["pi"]) if secure else None
        pi = Streamer("tcp://127.0.0.1:*", auth=auth)
        relay = Relay(pi.endpoint, tamper=True)
        live = (laptop_client(hosts, relay.endpoint) if secure
                else LiveSource(relay.endpoint, idle_timeout_s=1.5))  # fmt: skip
        live.connect()
        assert pi.wait_for_subscriber(5.0)
        got, t = consume(live)
        sent = [rec(i) for i in range(300)]
        for k in range(0, len(sent), 10):  # several TCP chunks, past the handshake
            for m in sent[k : k + 10]:
                pi.send(m)
            time.sleep(0.01)
        t.join(timeout=15)
        pi.close()
        relay.close()
        assert relay.modified > 0, "the relay must have tampered with the stream"
        return sent, got, live

    sent, got, live = run(secure=False)
    assert any(m.emitter.startswith("FORGED") for m in got), "control: plaintext is forgeable"

    sent, got, live = run(secure=True)
    assert all(m in sent for m in got)  # nothing altered or invented
    assert live.stats["bad"] == 0


# --- keys and the CLI policy ------------------------------------------------------------------


def test_key_files_are_private_and_never_overwritten(tmp_path):
    d = tmp_path / "keys"
    pub = linkauth.generate("payload", d)
    secret = d / "payload.key_secret"
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert linkauth.load_own("payload", d)[0] == pub
    before = secret.read_bytes()
    with pytest.raises(LinkSecurityError, match="--force"):
        linkauth.generate("payload", d)
    assert secret.read_bytes() == before
    assert linkauth.generate("payload", d, force=True) != pub
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    linkauth.trust("laptop", pub.decode(), d)
    with pytest.raises(LinkSecurityError, match="--force"):
        linkauth.trust("laptop", zmq.curve_keypair()[0].decode(), d)
    assert linkauth.load_trusted(d) == {"laptop": pub}
    secret.chmod(0o640)
    with pytest.raises(LinkSecurityError, match="chmod 600"):
        linkauth.load_own("payload", d)


def test_pnt_keys_cli_round_trip(tmp_path, capsys):
    pi, laptop = str(tmp_path / "pi"), str(tmp_path / "laptop")
    main(["keys", "gen", "--role", "payload", "--keys", pi])
    main(["keys", "gen", "--role", "laptop", "--keys", laptop])
    printed = capsys.readouterr().out
    for host, role in ((pi, "payload"), (laptop, "laptop")):
        assert linkauth.load_own(role, host)[1].decode() not in printed  # never print a secret
    main(["keys", "trust", "payload", str(tmp_path / "pi" / "payload.key"), "--keys", laptop])
    main(["keys", "trust", "laptop", str(tmp_path / "laptop" / "laptop.key"), "--keys", pi])
    main(["keys", "show", "--keys", laptop])
    shown = capsys.readouterr().out
    pub = linkauth.load_own("payload", tmp_path / "pi")[0].decode()
    sec = linkauth.load_own("laptop", tmp_path / "laptop")[1].decode()
    assert f"payload: {pub}" in shown and sec not in shown
    with pytest.raises(SystemExit, match="--force"):
        main(["keys", "gen", "--role", "payload", "--keys", pi])


def test_plaintext_needs_insecure(tmp_path, capsys):
    """Without keys, `pnt record` and `pnt live` refuse and say how to make them; only
    `--insecure` streams in plaintext, with a warning, and the session says so."""
    none = str(tmp_path / "no-keys")
    out = tmp_path / "s"
    quiet = ["--no-gnss", "--no-imu", "--no-baro", "--no-camera", "--no-fc", "--duration", "1"]
    with pytest.raises(SystemExit, match="pnt keys gen --role payload"):
        main(["record", "--keys", none, "--out", str(out), "--stream", "tcp://0.0.0.0:0", *quiet])
    assert not out.exists()  # refused before anything was recorded
    with pytest.raises(SystemExit, match="pnt keys gen --role laptop"):
        main(["live", "--keys", none, "--connect", "tcp://127.0.0.1:9", "--origin", "45,-75,70"])
    main(["record", "--keys", none, "--out", str(out), "--stream", "tcp://127.0.0.1:*",
          "--insecure", *quiet])  # fmt: skip
    assert "WARNING: --insecure" in capsys.readouterr().out
    assert "stream: NOT authenticated" in session.read_meta(out)["notes"]


def test_pnt_record_refuses_without_a_trusted_laptop(hosts, tmp_path):
    lone = tmp_path / "lone"
    linkauth.generate("payload", lone)
    with pytest.raises(SystemExit, match="pnt keys trust laptop"):
        main(["record", "--keys", str(lone), "--out", str(tmp_path / "s"), "--no-gnss"])


def test_without_curve_the_stream_is_refused_not_downgraded(hosts, tmp_path, monkeypatch):
    """A libzmq without CURVE (possible on the Pi, ADR-0026): refuse, say why, never fall back
    to plaintext on its own."""
    real = zmq.has
    monkeypatch.setattr(zmq, "has", lambda cap: False if cap == "curve" else real(cap))
    quiet = ["--no-gnss", "--no-imu", "--no-baro", "--no-camera", "--no-fc", "--duration", "1"]
    with pytest.raises(SystemExit, match="without CURVE"):
        main(["record", "--keys", str(hosts["pi"]), "--out", str(tmp_path / "s"),
              "--stream", "tcp://127.0.0.1:*", *quiet])  # fmt: skip
    with pytest.raises(SystemExit, match="without CURVE"):
        main(["live", "--keys", str(hosts["laptop"]), "--connect", "tcp://127.0.0.1:9"])
    with pytest.raises(SystemExit, match="without CURVE"):
        main(["keys", "gen", "--role", "laptop", "--keys", str(tmp_path / "k")])
