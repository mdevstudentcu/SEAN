"""Session folders (systems/icd/session.md, issue #2).

A session is a folder holding `meta.yaml` and `session.mcap` (plus raw sidecars for real
captures). Commands accept either the folder or a bare `.mcap` file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pnt.io.mcap_log import read_metadata

MCAP_NAME = "session.mcap"
META_NAME = "meta.yaml"
META_KEYS = (
    "name", "platform", "origin_llh", "simulated", "scenario", "seed", "commit", "hardware",
    "reference", "notes",
)  # fmt: skip


def mcap_path(path: str | Path) -> Path:
    """The session's MCAP file, given its folder or the file itself."""
    p = Path(path)
    if p.is_dir():
        f = p / MCAP_NAME
        if not f.exists():
            raise FileNotFoundError(f"{p} is not a session folder: no {MCAP_NAME}")
        return f
    return p


def session_name(path: str | Path) -> str:
    """Folder name for a session folder, file stem for a bare MCAP."""
    p = Path(path)
    return p.name if p.is_dir() else p.stem


def write_meta(folder: str | Path, meta: dict) -> Path:
    """Write meta.yaml with the ICD's keys in order (unknown keys are rejected)."""
    unknown = set(meta) - set(META_KEYS)
    if unknown:
        raise ValueError(f"meta keys not in ICD-session: {sorted(unknown)}")
    ordered = {k: meta.get(k) for k in META_KEYS}
    path = Path(folder) / META_NAME
    path.write_text(yaml.safe_dump(ordered, sort_keys=False, default_flow_style=None))
    return path


def read_meta(path: str | Path) -> dict:
    """Session metadata: meta.yaml if the folder has one, else the MCAP's own metadata
    (values parsed from their string form)."""
    p = Path(path)
    if p.is_dir() and (p / META_NAME).exists():
        return yaml.safe_load((p / META_NAME).read_text()) or {}
    raw = read_metadata(mcap_path(p))
    parsed = ("origin_llh", "seed", "simulated", "hardware", "reference")  # strings in MCAP
    return {k: yaml.safe_load(v) if k in parsed else v for k, v in raw.items()}
