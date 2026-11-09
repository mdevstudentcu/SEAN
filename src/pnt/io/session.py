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
REFERENCE_KEYS = ("position_llh", "surveyed", "sigma_m")  # meta.yaml `reference` block


def validate_reference(ref) -> None:
    """Check a `reference` block against ICD-session; `None` means no reference station.

    `sigma_m` is the surveyed position's 1-sigma in metres, `TBD` while unsurveyed; absent means
    unknown, so a consumer must not assume a value."""
    if ref is None:
        return
    if not isinstance(ref, dict):
        raise ValueError(f"reference must be a mapping or null, not {ref!r}")
    unknown = set(ref) - set(REFERENCE_KEYS)
    if unknown:
        raise ValueError(f"reference keys not in ICD-session: {sorted(unknown)}")
    pos = ref.get("position_llh")
    if not (isinstance(pos, list | tuple) and len(pos) == 3 and all(map(_is_number, pos))):
        raise ValueError(f"reference.position_llh must be [lat, lon, h], not {pos!r}")
    if "surveyed" in ref and not isinstance(ref["surveyed"], bool):
        raise ValueError(f"reference.surveyed must be true or false, not {ref['surveyed']!r}")
    if "sigma_m" in ref:
        sigma = ref["sigma_m"]
        if sigma != "TBD" and not (_is_number(sigma) and 0 <= sigma < float("inf")):
            raise ValueError(f"reference.sigma_m must be metres >= 0 or TBD, not {sigma!r}")


def _is_number(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


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
    validate_reference(meta.get("reference"))
    ordered = {k: meta.get(k) for k in META_KEYS}
    path = Path(folder) / META_NAME
    path.write_text(yaml.safe_dump(ordered, sort_keys=False, default_flow_style=None))
    return path


def read_meta(path: str | Path) -> dict:
    """Session metadata: meta.yaml if the folder has one, else the MCAP's own metadata
    (values parsed from their string form). A malformed `reference` block raises."""
    p = Path(path)
    if p.is_dir() and (p / META_NAME).exists():
        meta = yaml.safe_load((p / META_NAME).read_text()) or {}
    else:
        raw = read_metadata(mcap_path(p))
        parsed = ("origin_llh", "seed", "simulated", "hardware", "reference")  # strings in MCAP
        meta = {k: yaml.safe_load(v) if k in parsed else v for k, v in raw.items()}
    validate_reference(meta.get("reference"))
    return meta
