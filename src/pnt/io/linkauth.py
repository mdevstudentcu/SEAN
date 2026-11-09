"""CurveZMQ keys and the policy for the ZeroMQ ground links (ADR-0026, #89).

Each host has one key pair for its role, kept outside the repo and every session:

    ~/.config/pnt/keys/<role>.key_secret   secret + public key, mode 0600 (never leaves the host)
    ~/.config/pnt/keys/<role>.key          public key (copy it to the other side)
    ~/.config/pnt/keys/trusted/<name>.key  peers' public keys this host trusts

The payload and the reference station are CurveZMQ servers: they encrypt, and a ZAP handler lets
only trusted laptop keys subscribe. The laptop is the client: it pins each endpoint's server key,
so a host without the payload's (or base's) secret key cannot complete the handshake.

Files are in the ZeroMQ certificate format, so `zmq.auth.load_certificate` reads them.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROLES = ("payload", "reference", "laptop")
SERVER_ROLES = ("payload", "reference")
# A trusted key is named after the peer's role; laptops may carry a suffix (laptop-mo).
TRUST_NAME = re.compile(r"^(payload|reference|laptop(-[a-z0-9_]+)?)$")
SECRET_SUFFIX = ".key_secret"
PUBLIC_SUFFIX = ".key"


class LinkSecurityError(RuntimeError):
    """The link cannot be secured as asked; the message says how to fix it."""


def default_dir() -> Path:
    return Path.home() / ".config" / "pnt" / "keys"


def has_curve() -> bool:
    import zmq

    return bool(zmq.has("curve"))


def key_id(public_key: bytes) -> str:
    """Short fingerprint of a public key, for people comparing two hosts."""
    return hashlib.sha256(public_key).hexdigest()[:12]


def _cert(public_key: bytes, secret_key: bytes | None = None) -> str:
    kind = "Secret" if secret_key else "Public"
    lines = [
        f"#   ZeroMQ CURVE {kind} Certificate, pnt keys, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "#   " + ("Never copy this file off this host." if secret_key else "Safe to share."),
        "",
        "metadata",
        "curve",
        f'    public-key = "{public_key.decode()}"',
    ]
    if secret_key:
        lines.append(f'    secret-key = "{secret_key.decode()}"')
    return "\n".join(lines) + "\n"


def _write_new(path: Path, text: str, mode: int, force: bool) -> None:
    """Create `path` with `mode` from the first byte (no window where it is readable)."""
    if force:
        path.unlink(missing_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(fd, mode)  # the umask may have taken bits away; never adds any
        os.write(fd, text.encode())
    finally:
        os.close(fd)


def _mkdir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)


def generate(role: str, key_dir: Path, force: bool = False) -> bytes:
    """Make `role`'s key pair in `key_dir`; returns the public key. Never overwrites without
    `force`."""
    import zmq

    if role not in ROLES:
        raise LinkSecurityError(f"role must be one of {', '.join(ROLES)}, not {role!r}")
    if not has_curve():
        raise LinkSecurityError(_no_curve())
    key_dir = Path(key_dir)
    secret = key_dir / f"{role}{SECRET_SUFFIX}"
    public = key_dir / f"{role}{PUBLIC_SUFFIX}"
    existing = [p for p in (secret, public) if p.exists()]
    if existing and not force:
        raise LinkSecurityError(
            f"{existing[0]} exists; not overwriting it (pass --force to replace the key, then "
            "copy the new public key to every peer)"
        )
    _mkdir(key_dir)
    pub, sec = zmq.curve_keypair()
    _write_new(secret, _cert(pub, sec), 0o600, force)
    _write_new(public, _cert(pub), 0o644, force)
    return pub


def _parse_public(key_or_file: str) -> bytes:
    """A z85 public key (40 characters), or a file holding one."""
    from zmq.auth import load_certificate
    from zmq.utils import z85

    path = Path(key_or_file).expanduser()
    if path.is_file():
        pub, _ = load_certificate(path)
        return pub
    key = key_or_file.strip().encode()
    try:
        if len(key) == 40 and len(z85.decode(key)) == 32:
            return key
    except (ValueError, KeyError, IndexError):
        pass
    raise LinkSecurityError(f"{key_or_file!r} is neither a key file nor a 40-character z85 key")


def trust(name: str, key_or_file: str, key_dir: Path, force: bool = False) -> bytes:
    """Store a peer's public key as `trusted/<name>.key`; returns it."""
    if not TRUST_NAME.match(name):
        raise LinkSecurityError(
            f"trusted key name must be payload, reference, laptop or laptop-<suffix>, not {name!r}"
        )
    pub = _parse_public(key_or_file)
    trusted = Path(key_dir) / "trusted"
    path = trusted / f"{name}{PUBLIC_SUFFIX}"
    if path.exists() and not force:
        raise LinkSecurityError(f"{path} exists; not replacing a trusted key without --force")
    _mkdir(Path(key_dir))
    _mkdir(trusted)
    _write_new(path, _cert(pub), 0o644, force)
    return pub


def load_own(role: str, key_dir: Path) -> tuple[bytes, bytes]:
    """This host's (public, secret) key for `role`; refuses a secret readable by others."""
    from zmq.auth import load_certificate

    path = Path(key_dir) / f"{role}{SECRET_SUFFIX}"
    if not path.is_file():
        raise LinkSecurityError(
            f"no {role} key in {key_dir}. Make one with `pnt keys gen --role {role}` and give "
            "its public key to the other side (deploy/pi/RUNBOOK.md, Keys)"
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise LinkSecurityError(f"{path} is readable by others (mode {mode:o}): chmod 600 it")
    pub, sec = load_certificate(path)
    if not sec:
        raise LinkSecurityError(f"{path} holds no secret key")
    return pub, sec


def load_trusted(key_dir: Path) -> dict[str, bytes]:
    """Every trusted peer key, by name."""
    from zmq.auth import load_certificate

    trusted = Path(key_dir) / "trusted"
    if not trusted.is_dir():
        return {}
    out = {}
    for p in sorted(trusted.glob(f"*{PUBLIC_SUFFIX}")):
        if TRUST_NAME.match(p.stem):
            out[p.stem] = load_certificate(p)[0]
    return out


@dataclass
class ServerAuth:
    """Keys for a Pi that streams: its own pair and the laptops allowed to subscribe."""

    role: str
    public: bytes
    secret: bytes
    clients: dict[str, bytes]  # name -> public key

    def describe(self) -> str:
        allowed = ", ".join(f"{n} {key_id(k)}" for n, k in self.clients.items())
        return f"CurveZMQ (#89), {self.role} key {key_id(self.public)}, clients allowed: {allowed}"


@dataclass
class ClientAuth:
    """Keys for the laptop: its own pair and the server key pinned for each endpoint."""

    public: bytes
    secret: bytes
    servers: dict[str, tuple[str, bytes]] = field(default_factory=dict)  # endpoint -> (role, key)

    def describe(self) -> str:
        pinned = ", ".join(f"{r} key {key_id(k)} at {ep}" for ep, (r, k) in self.servers.items())
        return f"CurveZMQ (#89), laptop key {key_id(self.public)}; {pinned}"


def _no_curve() -> str:
    import zmq

    return (
        f"libzmq {zmq.zmq_version()} was built without CURVE, so the stream cannot be "
        "authenticated or encrypted (ADR-0026). Record with --no-stream, or pass --insecure "
        "only on a private link (hotspot or Ethernet)"
    )


def server_auth(role: str, key_dir: Path) -> ServerAuth:
    """Keys for streaming as `role`, or LinkSecurityError saying what is missing."""
    if not has_curve():
        raise LinkSecurityError(_no_curve())
    pub, sec = load_own(role, key_dir)
    clients = {n: k for n, k in load_trusted(key_dir).items() if n.startswith("laptop")}
    if not clients:
        raise LinkSecurityError(
            f"no trusted laptop key in {Path(key_dir) / 'trusted'}, so nobody could subscribe. "
            "On the laptop run `pnt keys gen --role laptop`, then here "
            "`pnt keys trust laptop <its public key>`"
        )
    return ServerAuth(role, pub, sec, clients)


def client_auth(endpoint_roles: dict[str, str], key_dir: Path) -> ClientAuth:
    """Keys for subscribing to each endpoint (endpoint -> payload | reference)."""
    if not has_curve():
        raise LinkSecurityError(_no_curve().replace("Record with --no-stream, or pass", "Pass"))
    pub, sec = load_own("laptop", key_dir)
    trusted = load_trusted(key_dir)
    servers = {}
    for ep, role in endpoint_roles.items():
        if role not in SERVER_ROLES:
            raise LinkSecurityError(f"{ep}: role must be payload or reference, not {role!r}")
        if role not in trusted:
            raise LinkSecurityError(
                f"no trusted {role} key in {Path(key_dir) / 'trusted'}. On the {role} Pi run "
                f"`pnt keys show`, then here `pnt keys trust {role} <its public key>`"
            )
        servers[ep] = (role, trusted[role])
    return ClientAuth(pub, sec, servers)


def show(key_dir: Path) -> str:
    """This host's public keys and the keys it trusts (never a secret)."""
    key_dir = Path(key_dir)
    lines = [f"keys in {key_dir}"]
    for role in ROLES:
        path = key_dir / f"{role}{SECRET_SUFFIX}"
        if path.is_file():
            try:
                pub, _ = load_own(role, key_dir)
                lines.append(f"  {role}: {pub.decode()}  (id {key_id(pub)})")
            except LinkSecurityError as e:
                lines.append(f"  {role}: {e}")
    if len(lines) == 1:
        lines.append("  no key pair yet: `pnt keys gen --role payload|reference|laptop`")
    trusted = load_trusted(key_dir)
    lines.append("trusted:" if trusted else "trusted: none")
    lines += [f"  {n}: {k.decode()}  (id {key_id(k)})" for n, k in trusted.items()]
    return "\n".join(lines)
