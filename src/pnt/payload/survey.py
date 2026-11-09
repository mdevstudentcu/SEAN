"""Survey the reference station's antenna by averaging its own GPS fixes (ADR-0020, #85).

Input: a session recorded on the base (`pnt record --receiver reference`, at least 1 h, `TBC`).
Output: the `reference` block of ICD-session (`position_llh`, `surveyed: true`, `sigma_m`).

`sigma_m` comes from the averaging, never from an assumed figure. GPS errors are correlated
over minutes (multipath, ionosphere), so the scatter of single fixes divided by sqrt(N) would be
far too small. Instead the fixes are cut into batches of `batch_s` (10 min) and `sigma_m` is the
standard error of the batch means: std(batch means) / sqrt(number of batches), for the worst of
east, north and up. With fewer than `MIN_BATCHES` batches it is `TBD`. Errors correlated over
longer than a batch still make it optimistic; the stats in the output let a reader judge.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from pnt.core import frames
from pnt.core.measurement import Measurement
from pnt.io import session
from pnt.io.mcap_log import read_session

BATCH_S = 600.0
MIN_BATCHES = 4
MIN_FIXES_PER_BATCH = 10


def average(t_ns, enu, batch_s: float = BATCH_S) -> dict:
    """Mean ENU position and its batch-means standard error from fixes `enu` (n, 3)."""
    t = (np.asarray(t_ns, dtype=np.int64) - int(t_ns[0])) / 1e9
    enu = np.asarray(enu, float)
    if len(enu) == 0:
        raise ValueError("no GNSS fixes to average")
    batch = np.floor(t / batch_s).astype(int)
    means = np.array(
        [enu[batch == b].mean(axis=0) for b in np.unique(batch)
         if (batch == b).sum() >= MIN_FIXES_PER_BATCH]
    ).reshape(-1, 3)  # fmt: skip
    k = len(means)
    se = means.std(axis=0, ddof=1) / np.sqrt(k) if k >= 2 else np.full(3, np.nan)
    sigma = float(se.max()) if k >= MIN_BATCHES else "TBD"
    return {
        "mean_enu": enu.mean(axis=0),
        "sigma_m": sigma,
        "stats": {
            "fixes": int(len(enu)),
            "duration_s": round(float(t[-1]), 1),
            "batch_s": batch_s,
            "batches": int(k),
            "batch_se_enu_m": [round(float(x), 3) for x in se],
            "fix_std_enu_m": [round(float(x), 3) for x in enu.std(axis=0)],
            "method": "std of batch means / sqrt(batches), worst axis",
        },
    }


def survey_session(path: str | Path, batch_s: float = BATCH_S) -> dict:
    """Survey from a recorded session's `gnss` `position_enu` records."""
    meta = session.read_meta(path)
    origin = meta.get("origin_llh")
    if origin is None:
        raise ValueError(f"{path}: meta.yaml has no origin_llh, so its ENU fixes can't be placed")
    fixes = [
        r
        for _, r in read_session(session.mcap_path(path), topics=["/meas/gnss"])
        if isinstance(r, Measurement) and r.kind == "position_enu"
    ]
    if not fixes:
        raise ValueError(f"{path}: no gnss position_enu records")
    res = average([m.t_ns for m in fixes], [m.value for m in fixes], batch_s)
    llh = frames.enu_to_llh(res["mean_enu"], origin)
    reference = {
        "position_llh": [round(float(x), d) for x, d in zip(llh, (8, 8, 3), strict=True)],
        "surveyed": True,
        "sigma_m": res["sigma_m"] if res["sigma_m"] == "TBD" else round(res["sigma_m"], 3),
    }
    session.validate_reference(reference)
    return {"reference": reference, "session": session.session_name(path), **res["stats"]}


def write_survey(result: dict, out: str | Path) -> Path:
    out = Path(out)
    out.write_text(yaml.safe_dump(result, sort_keys=False, default_flow_style=None))
    return out


def load_reference(path: str | Path) -> dict:
    """The `reference` block from a survey file (or a meta.yaml)."""
    ref = (yaml.safe_load(Path(path).read_text()) or {}).get("reference")
    session.validate_reference(ref)
    if ref is None:
        raise ValueError(f"{path} has no reference block")
    return ref
