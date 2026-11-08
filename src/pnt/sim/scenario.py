"""Load a scenario YAML and generate truth + measurements, with faults injected (ADR-0004).

Faults live here (and in sources), never in the estimator: the estimator must not know.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from pnt.core.frames import enu_to_llh, llh_to_enu
from pnt.core.measurement import Measurement, Truth
from pnt.core.time import s_to_ns, utc_to_gps_ns
from pnt.sim import attacks, models, trajectory

SCENARIO_DIR = Path(__file__).parent / "scenarios"
SET_DIR = SCENARIO_DIR / "sets"
ATTACK_MENU = SET_DIR / "_attacks.yaml"
REFERENCE_DIR = Path(__file__).parents[3] / "data" / "reference"
# Fixed scenario start so runs are reproducible (REQ-10): judging day, 18:00 UTC.
T0_NS = utc_to_gps_ns(datetime(2026, 11, 12, 18, 0, tzinfo=UTC))


@dataclass
class SimRun:
    name: str
    spec: dict
    seed: int
    truth: list[Truth]
    measurements: list[Measurement]
    events: list[tuple[int, str]] = field(default_factory=list)
    emitters: dict[str, list[float]] = field(default_factory=dict)


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def load_named(name: str) -> dict:
    """Load a bundled scenario by plain name only (e.g. 'spoof-ramp').

    For names read from session files, which are untrusted input (AGENTS.md): no paths, no
    suffixes, so a session cannot point the loader at an arbitrary file.
    """
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"not a scenario name: {name!r}")
    composed = _compose(name)
    if composed is not None:
        return composed
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no bundled scenario named {name!r}")
    return load(str(path))


def _read(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def set_names() -> list[str]:
    """The environments in scenarios/sets/ (issue #16)."""
    return sorted(p.stem for p in SET_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def attack_names() -> list[str]:
    return list(_read(ATTACK_MENU))


def expand(name: str) -> list[str]:
    """Every scenario a name stands for: a whole environment, or just itself."""
    return [f"{name}-{a}" for a in attack_names()] if name in set_names() else [name]


def scenario_names() -> list[str]:
    """Every bundled scenario: the standalone files, then each environment with each attack."""
    standalone = sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))
    return standalone + [n for s in set_names() for n in expand(s)]


def _compose(name: str) -> dict | None:
    """Build `<environment>-<attack>`, or None if the name isn't one. Unknown attacks raise."""
    environment = next((s for s in set_names() if name.startswith(f"{s}-")), None)
    if environment is None:
        return None
    menu = _read(ATTACK_MENU)
    attack_name = name[len(environment) + 1 :]
    if attack_name not in menu:
        raise FileNotFoundError(f"no attack named {attack_name!r} for environment {environment!r}")
    spec = _read(SET_DIR / f"{environment}.yaml")
    spec.update(name=name, faults=menu[attack_name] or [])
    return spec


def load(name_or_path: str) -> dict:
    p = Path(name_or_path)
    if not p.suffix:
        composed = _compose(name_or_path)
        if composed is not None:
            return composed
        p = SCENARIO_DIR / f"{name_or_path}.yaml"
    with open(p) as f:
        spec = yaml.safe_load(f)
    spec.setdefault("name", p.stem)
    return spec


def _times(duration_s: float, rate_hz: float) -> np.ndarray:
    return np.arange(0.0, duration_s, 1.0 / rate_hz)


def generate(spec: dict, seed: int = 0) -> SimRun:
    rng = np.random.default_rng(seed)
    dur = float(spec["duration_s"])
    traj = {**spec["trajectory"], "_origin_llh": spec.get("origin_llh")}  # for points_llh

    t_truth = _times(dur, 1.0 / spec.get("dt_s", 0.1))
    pos_t, vel_t = trajectory.make(traj, t_truth)
    clock_t = _clock(spec.get("clock"), t_truth, rng)
    truth = [
        Truth(t_ns=T0_NS + s_to_ns(t), pos_enu=tuple(p), vel_enu=tuple(v), clock_bias_s=float(c))
        for t, p, v, c in zip(t_truth, pos_t, vel_t, clock_t, strict=True)
    ]

    meas: list[Measurement] = []
    emitters: dict[str, list[float]] = {}
    for source, cfg in spec.get("sources", {}).items():
        cfg = dict(cfg)
        ts = _times(dur, cfg.pop("rate_hz"))
        ts_ns = T0_NS + np.round(ts * 1e9).astype(np.int64)
        pos, _ = trajectory.make(traj, ts)
        model = cfg.pop("model", source)
        if model == "gnss":
            clock_s = np.interp(ts, t_truth, clock_t) if "clock" in spec else None
            meas += models.gnss(ts_ns, pos, rng, clock_s=clock_s, **cfg)
        elif model == "baro":
            meas += models.baro(ts_ns, pos, rng, **cfg)
        elif model == "pseudorange":
            em_llh = cfg.pop("emitters_llh", None)
            if "towers_from" in cfg:
                em_llh = select_towers(**cfg.pop("towers_from"))
            if em_llh is not None:  # real transmitter positions (data/reference)
                em = np.array([llh_to_enu(x, spec["origin_llh"]) for x in em_llh])
            else:
                em = models.synthetic_emitters(
                    rng, cfg.pop("n_emitters"), tuple(cfg.pop("ring_radius_m"))
                )
            for i, e in enumerate(em):
                emitters[f"{source}:sim{i}"] = [float(x) for x in e]
            told_em, em_llh = _told_positions(
                cfg.pop("told_position_sigma_m", 0.0), em, em_llh, spec, rng
            )
            if cfg.pop("receiver_clock", False):
                if "clock" not in spec:
                    raise ValueError("receiver_clock needs a `clock:` model in the scenario")
                cfg["clock_s"] = np.interp(ts, t_truth, clock_t)
            meas += models.pseudoranges(
                ts_ns,
                pos,
                rng,
                source=source,
                emitters=em,
                emitters_llh=em_llh,
                told_emitters=told_em,
                **cfg,
            )
        else:
            raise ValueError(f"unknown model {model!r} for source {source!r}")

    ctx = attacks.Context(
        t0_ns=T0_NS,
        origin_llh=spec.get("origin_llh"),
        truth_pos=lambda t: trajectory.make(traj, np.atleast_1d(t))[0],
        rng=rng,
    )
    meas, events = attacks.apply(meas, spec.get("faults", []), ctx)
    meas.sort(key=lambda m: (m.t_ns, m.source, m.kind, m.emitter))
    return SimRun(spec["name"], spec, seed, truth, meas, events, emitters)


def select_towers(
    file: str, carrier: str, tx_mhz: float, count: int, min_km: float = 0.0
) -> list[list[float]]:
    """The `count` nearest sites broadcasting one carrier, as [lat, lon, height]. Deterministic.

    One radio hears one carrier at a time, so a scenario's towers share an operator and frequency.
    """
    with open(REFERENCE_DIR / file, newline="") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if carrier.lower() in r["carrier"].lower()
            and float(r["tx_mhz"]) == float(tx_mhz)
            and float(r["dist_km"]) >= min_km
        ]
    sites: dict[tuple[str, str], dict] = {}
    for r in sorted(rows, key=lambda r: float(r["dist_km"])):
        sites.setdefault((r["lat"], r["lon"]), r)
    if len(sites) < count:
        raise ValueError(f"only {len(sites)} sites match {carrier} at {tx_mhz} MHz, need {count}")
    return [
        [float(r["lat"]), float(r["lon"]), float(r["height_m"])]
        for r in list(sites.values())[:count]
    ]


def _told_positions(sigma_m: float, em: np.ndarray, em_llh, spec: dict, rng):
    """Tower positions as published: the truth plus a horizontal error. (told ENU, told lat/lon)"""
    if not sigma_m:
        return None, em_llh
    told = em + np.column_stack([rng.normal(0.0, sigma_m, (len(em), 2)), np.zeros(len(em))])
    if em_llh is not None:
        return None, [enu_to_llh(e, spec["origin_llh"]) for e in told]
    return told, None


def _clock(spec: dict | None, t: np.ndarray, rng) -> np.ndarray:
    """True local clock offset from GPS time (s): offset + drift + random walk. Zero if the
    scenario has no `clock:` block. Parameters are placeholders until measured (ADR-0015)."""
    if not spec:
        return np.zeros_like(t)
    dt = np.diff(t, prepend=t[0])
    walk = np.cumsum(rng.normal(0.0, spec.get("rw_ns", 0.0) * 1e-9 * np.sqrt(dt)))
    return spec.get("offset_s", 0.0) + spec.get("drift_ppb", 0.0) * 1e-9 * t + walk
