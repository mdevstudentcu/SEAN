"""Wi-Fi RSSI scans with BSSIDs hashed at capture (ADR-0011, ADR-0018, REQ-08).

`iw dev <iface> scan passive` listens for beacons only: no probe requests are sent, and no
client traffic is captured. `parse_scan` hashes each BSSID the moment it reads it, with the
deployment's salt, as the first 8 bytes of SHA-256(salt || BSSID) (the same rule as
`PNT_WIFI_AP` in `pnt.xml`). The raw BSSID never leaves that function, and SSIDs are not kept.

Off by default: scanning on the Pi's only radio interrupts the live stream (ADR-0018, `TBC`
where scans run in flight).
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from pnt.core.measurement import Measurement
from pnt.core.time import now_gps_ns

SALT_FILE = Path.home() / ".config" / "pnt" / "wifi-salt"
# RSSI 1-sigma, dB. Placeholder until a static session measures it: TBC.
RSSI_SIGMA_DB = 6.0
_BSS = re.compile(r"^BSS ([0-9a-fA-F:]{17})")
_SIGNAL = re.compile(r"^\s+signal: (-?[0-9.]+) dBm")
_FREQ = re.compile(r"^\s+freq: ([0-9.]+)")


def load_salt(path: Path = SALT_FILE) -> bytes:
    """The deployment's salt, created (0600) on first use. Kept out of sessions and git."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    return path.read_bytes()


def salt_id(salt: bytes) -> str:
    """Names the salt in meta.yaml without revealing it."""
    return hashlib.sha256(b"salt-id" + salt).hexdigest()[:8]


def hash_bssid(bssid: str, salt: bytes) -> str:
    mac = bytes.fromhex(bssid.replace(":", "").lower())
    return hashlib.sha256(salt + mac).digest()[:8].hex()


def parse_scan(text: str, salt: bytes) -> list[dict]:
    """`iw ... scan` output -> [{"bssid_hash", "rssi_dbm", "freq_mhz"}]. Hashes at once."""
    aps: list[dict] = []
    for line in text.splitlines():
        if m := _BSS.match(line):
            aps.append({"bssid_hash": hash_bssid(m.group(1), salt)})
        elif aps and (m := _SIGNAL.match(line)):
            aps[-1]["rssi_dbm"] = float(m.group(1))
        elif aps and (m := _FREQ.match(line)):
            aps[-1]["freq_mhz"] = float(m.group(1))
    return [a for a in aps if "rssi_dbm" in a]


class WifiScan:
    """Passive scans every `period_s` into `wifi` `rssi` records."""

    name = "wifi"
    hardware = "pi-wifi"

    def __init__(self, iface: str = "wlan0", period_s: float = 10.0, salt: bytes | None = None):
        self.iface, self.period_s = iface, period_s
        self._salt = salt
        self.scans = 0
        self.aps = 0

    def command(self) -> list[str]:
        cmd = ["iw", "dev", self.iface, "scan", "passive"]
        return cmd if os.geteuid() == 0 else ["sudo", "-n", *cmd]

    def probe(self) -> str | None:
        if shutil.which("iw") is None:
            return "iw not installed"
        if not Path(f"/sys/class/net/{self.iface}").exists():
            return f"no interface {self.iface}"
        return None

    def status(self) -> dict:
        return {"scans": self.scans, "aps": self.aps}

    def run(self, ctx) -> None:
        salt = self._salt if self._salt is not None else load_salt()
        ctx.event(now_gps_ns(), "wifi salt", salt_id=salt_id(salt))
        while True:
            t = now_gps_ns()
            res = subprocess.run(self.command(), capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                self.scans += 1
                for ap in parse_scan(res.stdout, salt):
                    self.aps += 1
                    ctx.emit(
                        Measurement(
                            t_ns=t,
                            source="wifi",
                            kind="rssi",
                            emitter=f"wifi:{ap['bssid_hash']}",
                            value=(ap["rssi_dbm"],),
                            sigma=(RSSI_SIGMA_DB,),
                            meta={"freq_mhz": ap.get("freq_mhz")},
                        )
                    )
            else:
                ctx.event(t, "wifi scan failed", error=res.stderr.strip()[-200:])
            if ctx.stop.wait(self.period_s):
                break
