"""Load a scenario YAML and generate truth + measurements, with faults injected (ADR-0004).

Faults live here (and in sources), never in the estimator: the estimator must not know.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import numpy as np
import yaml

from pnt.core.frames import enu_to_llh, llh_to_enu
from pnt.core.measurement import Measurement, Truth
from pnt.core.time import s_to_ns, utc_to_gps_ns
from pnt.sim import adsb, attacks, hostile, lte_front_end, models, sensors, trajectory

SCENARIO_DIR = Path(__file__).parent / "scenarios"
SET_DIR = SCENARIO_DIR / "sets"
ATTACK_MENU = SET_DIR / "_attacks.yaml"
REFERENCE_DIR = Path(__file__).parents[3] / "data" / "reference"
# ISED filings closer than this are one site filed twice (e.g. two licences on one mast). TBC
SAME_SITE_M = 10.0
# ISED often omits ground elevation, leaving the antenna height alone. Filed heights below this
# are read as height above ground. TBC: values from 45 to 80 m are ambiguous. Must match
# GROUND_ELEVATION_CUTOFF_M in analysis/sionna_campus.py, which built the committed ray table.
GROUND_MISSING_BELOW_M = 80.0
# Seeds the reference station's own random stream, kept apart from the payload's (REQ-10)
REFERENCE_STREAM = 0x0BA5E
# Fixed scenario start so runs are reproducible (REQ-10): judging day, 18:00 UTC.
T0_NS = utc_to_gps_ns(datetime(2026, 11, 12, 18, 0, tzinfo=UTC))
# Who built each carrier's radios in Ottawa (ADR-0022, Proposed): Bell and TELUS share one RAN
# that TELUS builds, Rogers runs its own, Freedom is being folded into Vidéotron. TBC by the scan.
BUILDER_OF_CARRIER = {
    "telus": "telus-built",
    "bell": "telus-built",
    "rogers": "rogers",
    "vidéotron": "videotron",
    "videotron": "videotron",
    "freedom": "videotron",
}
BUILDERS = ("telus-built", "rogers", "videotron")
# Random streams of their own, so tower grouping and tower clocks can be rebuilt from the seed
# alone and leave every other draw in `generate` as it was.
_GROUP_STREAM, _TOWER_CLOCK_STREAM = 220, 221
# The IMU's own random stream, for the same reason: adding an IMU to a scenario changes no other
# source's draws, so estimators that ignore the IMU see the same run with or without it.
_IMU_STREAM = 222
# The hostile beacon's own random stream (`jammer_power`, #93), for the same reason
_HOSTILE_STREAM = 223
# ADS-B traffic's own stream (#91), for the same reason
_ADSB_STREAM = 0xAD5B
# The simulated GPS sky's own stream (`sky:`, #206), for the same reason
_SKY_STREAM = 224
# The faults that reach the aircraft around us as well as our receiver (`pnt.sim.adsb`)
GNSS_ZONES = ("jamming_zone", "spoof_zone")


@dataclass
class SimRun:
    name: str
    spec: dict
    seed: int
    truth: list[Truth]
    measurements: list[Measurement]
    events: list[tuple[int, str]] = field(default_factory=list)
    emitters: dict[str, list[float]] = field(default_factory=dict)
    # Truth for debugging: each tower's clock (m) at the truth times, when `tower_clocks:` is on
    tower_clocks: dict[str, np.ndarray] = field(default_factory=dict)
    # The reference station as the session records it (ICD-session `reference`), or None
    reference: dict | None = None
    # Truth for debugging: each dongle's clock (m) at the truth times, by `meta.rx_clock`, when a
    # source has `record_shape: front_end`
    rx_clocks: dict[str, np.ndarray] = field(default_factory=dict)


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
    """The shared attack menu (`_attacks.yaml`): every environment's, unless it opts out."""
    return list(_read(ATTACK_MENU))


def _own_attacks(environment: str) -> dict:
    """Attacks only this environment has (its `attacks:`), e.g. faults of a reference station."""
    return _environment(environment).get("attacks") or {}


def _shares_menu(environment: str) -> bool:
    """Whether the shared menu applies. `shared_attacks: false` makes the environment's own
    `attacks:` its whole menu, for environments whose timing the shared entries don't fit."""
    shared = _environment(environment).get("shared_attacks", True)
    if not isinstance(shared, bool):
        raise ValueError(f"shared_attacks is true or false, not {shared!r}")
    return shared


def _menu(environment: str) -> dict:
    shared = _read(ATTACK_MENU) if _shares_menu(environment) else {}
    return {**shared, **_own_attacks(environment)}


def _merge(parent: dict, child: dict) -> dict:
    """`child` over `parent`; nested mappings merge key by key, anything else is replaced."""
    out = dict(parent)
    for k, v in child.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _extended(spec: dict, folder: Path) -> dict:
    """Resolve `extends: <name>`: the named scenario in the same folder, with `spec` over it.
    A variant (e.g. one with a reference station) states only what it adds."""
    parent = spec.pop("extends", None)
    if parent is None:
        return spec
    if not isinstance(parent, str) or not _NAME.fullmatch(parent):
        raise ValueError(f"extends must name a scenario, not {parent!r}")
    return _merge(_extended(_read(folder / f"{parent}.yaml"), folder), spec)


def _environment(environment: str) -> dict:
    return _extended(_read(SET_DIR / f"{environment}.yaml"), SET_DIR)


def expand(name: str) -> list[str]:
    """Every scenario a name stands for: a whole environment, or just itself."""
    if name not in set_names():
        return [name]
    shared = attack_names() if _shares_menu(name) else []
    return [f"{name}-{a}" for a in [*shared, *_own_attacks(name)]]


def scenario_names() -> list[str]:
    """Every bundled scenario: the standalone files, then each environment with each attack."""
    standalone = sorted(p.stem for p in SCENARIO_DIR.glob("*.yaml"))
    return standalone + [n for s in set_names() for n in expand(s)]


def _compose(name: str) -> dict | None:
    """Build `<environment>-<attack>`, or None if the name isn't one. Unknown attacks raise."""
    # The longest environment name that prefixes `name`: `realistic-with-base-outage` is the
    # `realistic-with-base` environment, not `realistic` with an attack called `with-base-outage`
    environment = max((s for s in set_names() if name.startswith(f"{s}-")), key=len, default=None)
    if environment is None:
        return None
    menu = _menu(environment)
    attack_name = name[len(environment) + 1 :]
    if attack_name not in menu:
        raise FileNotFoundError(f"no attack named {attack_name!r} for environment {environment!r}")
    spec = _environment(environment)
    spec.pop("attacks", None)
    spec.pop("shared_attacks", None)
    spec.update(name=name, faults=menu[attack_name] or [])
    return spec


def load(name_or_path: str) -> dict:
    p = Path(name_or_path)
    if not p.suffix:
        composed = _compose(name_or_path)
        if composed is not None:
            return composed
        p = SCENARIO_DIR / f"{name_or_path}.yaml"
    own = _read(p)
    name = own.get("name", p.stem)
    return {**_extended(own, p.parent), "name": name}


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

    tower_clk: dict[str, np.ndarray] = {}
    groups = None  # (sites, builders) when the scenario groups its tower clocks (ADR-0022)
    if spec.get("tower_clocks"):
        rng_clk = np.random.default_rng([seed, _TOWER_CLOCK_STREAM])
        groups = tower_groups(spec, seed)
        tower_clk = _tower_clocks(spec["tower_clocks"], groups, t_truth, rng_clk)

    meas: list[Measurement] = []
    emitters: dict[str, list[float]] = {}
    rx_clocks: dict[str, np.ndarray] = {}
    jammers: dict[str, dict] = {}  # true jammer positions, for the hostile-emitter faults
    ref = _Reference(spec, seed, t_truth) if spec.get("reference") else None
    for source, cfg in spec.get("sources", {}).items():
        cfg = dict(cfg)
        ts = _times(dur, cfg.pop("rate_hz"))
        ts_ns = T0_NS + np.round(ts * 1e9).astype(np.int64)
        pos, _ = trajectory.make(traj, ts)
        model = cfg.pop("model", source)
        if model == "pseudorange" and _record_shape(cfg) == "front_end":
            if ref is not None and source in ref.sources:
                raise ValueError("the reference station can't hear front-end records yet")
            recs, found, rx = lte_front_end.records(
                cfg,
                source=source,
                cells_file=_cells_file(cfg),
                ts=ts,
                ts_ns=ts_ns,
                pos=pos,
                t_truth=t_truth,
                origin_llh=spec["origin_llh"],
                seed=seed,
                tower_clocks=tower_clk,
            )
            meas += recs
            emitters.update(found)
            rx_clocks.update(rx)
        elif model == "gnss":
            clock_s = np.interp(ts, t_truth, clock_t) if "clock" in spec else None
            sky = cfg.pop("sky", None)
            recs = models.gnss(ts_ns, pos, rng, clock_s=clock_s, **cfg)
            if sky is not None:
                recs = _with_sky(recs, sky, ts_ns, pos, spec, seed)
            meas += recs
        elif model == "baro":
            meas += models.baro(ts_ns, pos, rng, **cfg)
        elif model == "imu":
            meas += _imu(traj, ts, ts_ns, np.random.default_rng([seed, _IMU_STREAM]), cfg)
        elif model == "pseudorange":
            em_llh = cfg.pop("emitters_llh", None)
            if "towers_from" in cfg:
                em_llh = select_towers(**cfg.pop("towers_from"), ground_m=spec["origin_llh"][2])
            if em_llh is not None:  # real transmitter positions (data/reference)
                em = np.array([llh_to_enu(x, spec["origin_llh"]) for x in em_llh])
            else:
                em = models.synthetic_emitters(
                    rng, cfg.pop("n_emitters"), tuple(cfg.pop("ring_radius_m"))
                )
            for i, e in enumerate(em):
                emitters[f"{source}:sim{i}"] = [float(x) for x in e]
            if "ray_table" in cfg:
                if em_llh is None:
                    raise ValueError("ray_table needs real tower positions (towers_from)")
                cfg["ray_table"] = load_ray_table(cfg["ray_table"], em_llh, spec["duration_s"])
            told_em, em_llh = _told_positions(
                cfg.pop("told_position_sigma_m", 0.0), em, em_llh, spec, rng
            )
            if cfg.pop("receiver_clock", False):
                if "clock" not in spec:
                    raise ValueError("receiver_clock needs a `clock:` model in the scenario")
                cfg["clock_s"] = np.interp(ts, t_truth, clock_t)
            if tower_clk:
                cfg["tower_clock_m"] = np.array(
                    [np.interp(ts, t_truth, tower_clk[f"{source}:sim{i}"]) for i in range(len(em))]
                )
            clocks: list[np.ndarray] = []
            meas += models.pseudoranges(
                ts_ns,
                pos,
                rng,
                source=source,
                emitters=em,
                emitters_llh=em_llh,
                told_emitters=told_em,
                tower_clocks_out=clocks,
                **cfg,
            )
            if ref is not None and source in ref.sources:
                meas += ref.pseudoranges(source, ts, ts_ns, em, em_llh, told_em, clocks)
        elif model == "bearing":
            em_llh = cfg.pop("emitters_llh", None)
            if em_llh is not None:
                em = np.array([llh_to_enu(x, spec["origin_llh"]) for x in em_llh])
            else:
                em = models.synthetic_emitters(
                    rng, cfg.pop("n_emitters"), tuple(cfg.pop("ring_radius_m")), (0.0, 10.0)
                )
            for i, e in enumerate(em):
                emitters[f"{source}:sim{i}"] = [float(x) for x in e]
            meas += models.bearings(ts_ns, pos, rng, source, em, emitters_llh=em_llh, **cfg)
        elif model == "adsb":
            zones = [
                f
                for f in spec.get("faults", [])
                if f["type"] in GNSS_ZONES and f.get("source", "gnss") == "gnss"
            ]
            rng_adsb = np.random.default_rng([seed, _ADSB_STREAM])
            meas += adsb.reports(
                ts, T0_NS, rng_adsb, spec["origin_llh"], zones=zones, source=source, **cfg
            )
        elif model == "leo_doppler":
            from pnt.sim import leo  # needs sgp4 (ground extra)

            clock_s = np.interp(ts, t_truth, clock_t) if cfg.pop("receiver_clock", False) else None
            meas += leo.doppler(
                ts_ns,
                pos,
                trajectory.make(traj, ts)[1],
                rng,
                spec["origin_llh"],
                REFERENCE_DIR / cfg.pop("tle_file"),
                source=cfg.pop("source", source),  # two LEO layers in one run are both `leo`
                clock_s=clock_s,
                **cfg,
            )
        elif model == "jammer_power":  # the hostile beacon's observable (#93, ADR-0025)
            p = hostile.params(cfg)
            found = hostile.jammers(spec)
            if not found:
                raise ValueError("jammer_power needs a jamming_zone fault to place the jammer")
            rng_jam = np.random.default_rng([seed, _HOSTILE_STREAM])
            meas += hostile.power(ts, ts_ns, pos, rng_jam, found, p)
            jammers.update({j.emitter: {"enu": j.enu, "n": p.path_loss_exponent} for j in found})
        else:
            raise ValueError(f"unknown model {model!r} for source {source!r}")

    if "replay_streams" in spec:
        meas = _replay_streams(meas, **spec["replay_streams"])
    ctx = attacks.Context(
        t0_ns=T0_NS,
        origin_llh=spec.get("origin_llh"),
        truth_pos=lambda t: trajectory.make(traj, np.atleast_1d(t))[0],
        rng=rng,
        emitters=emitters,
        reference_enu=None if ref is None else ref.true_enu,
        tower_groups=groups,
        jammers=jammers,
    )
    meas, events = attacks.apply(meas, spec.get("faults", []), ctx)
    meas.sort(key=lambda m: (m.t_ns, m.source, m.kind, m.emitter, m.receiver))
    meta = None if ref is None else ref.meta()
    return SimRun(
        spec["name"], spec, seed, truth, meas, events, emitters, tower_clk, meta, rx_clocks
    )


def _with_sky(recs, sky, ts_ns, pos, spec: dict, seed: int) -> list[Measurement]:
    """The GNSS source's `gnss_health` records, every `period_s` with `meta.snr` (PRN -> C/N0):
    the simulated GPS sky (`pnt.sim.gnss_sky`, #206). `sky: true` takes the defaults; a mapping
    overrides `gnss_sky.snr_reports`' parameters."""
    from pnt.sim import gnss_sky  # needs sgp4 (ground extra)

    if not any(m.kind == "gnss_health" for m in recs):
        raise ValueError("a GNSS `sky:` needs `health: true` on the same source")
    if not spec.get("origin_llh"):
        raise ValueError("a GNSS `sky:` needs the scenario's origin_llh")
    params = {} if sky is True else dict(sky)
    rng = np.random.default_rng([seed, _SKY_STREAM])
    snr = gnss_sky.snr_reports(ts_ns, pos, spec["origin_llh"], rng, **params)
    return [
        msgspec.structs.replace(m, meta={**m.meta, "device": "sim", "snr": snr[m.t_ns]})
        if m.kind == "gnss_health" and m.t_ns in snr
        else m
        for m in recs
    ]


def _record_shape(cfg: dict) -> str:
    """Pop a pseudorange source's `record_shape`: `sim` (default: records carrying their tower's
    position, `models.pseudoranges`) or `front_end` (as `pnt.frontends.lte` writes them, #134)."""
    shape = cfg.pop("record_shape", "sim")
    if shape not in ("sim", "front_end"):
        raise ValueError(f"record_shape is sim or front_end, not {shape!r}")
    return shape


def _cells_file(cfg: dict) -> Path:
    """The cell table a front-end source names (`cells_from: {file, earfcn}`, no defaults)."""
    cells_from = cfg.get("cells_from") or {}
    if set(cells_from) != {"file", "earfcn"}:
        raise ValueError(f"cells_from needs file and earfcn, not {sorted(cells_from)}")
    return REFERENCE_DIR / cells_from["file"]


def _imu(traj: dict, ts: np.ndarray, ts_ns: np.ndarray, rng, cfg: dict) -> list[Measurement]:
    """`accel_gyro` records from the payload's IMU (`sensors.MPU6050`; any of its `ImuParams`
    fields can be overridden in the scenario, e.g. for a worse grade). Needs a trajectory with
    finite acceleration (`trajectory.kinematics`), so not `square`."""
    params = replace(sensors.MPU6050, **cfg) if cfg else sensors.MPU6050
    k = trajectory.kinematics(traj, ts)
    accel, gyro = sensors.imu(ts, k.specific_force_b, k.omega_b, rng, params)
    return sensors.imu_measurements(ts_ns, accel, gyro, params)


def tower_groups(spec: dict, seed: int = 0) -> tuple[dict[str, str], dict[str, str]]:
    """How a scenario's towers share clocks (ADR-0022): (sites, builders), where `sites` maps
    each pseudorange emitter to its site and `builders` maps each site to its network builder.

    The shape the EKF's `sites` and `builders` options take. Deterministic for a spec and seed,
    and it draws nothing from the run's own random stream, so an eval can call it beside
    `generate`.
    - Builder: from the tower's filed carrier (`towers_from`), mapped by BUILDER_OF_CARRIER.
      Towers with no carrier (synthetic, or `emitters_llh`) get one drawn from BUILDERS with
      the seed.
    - Site: towers of one builder within SAME_SITE_M of each other, across sources, are one
      site, named after its first emitter. Synthetic towers are a site each. The sim has no
      PCI, so sectors can't be grouped by PCI // 3: each emitter is one sector.
    - Front-end records (`record_shape: front_end`): every sector of the table's carrier is
      grouped by its registered eNB, named `enb:<id>` as `pnt.nav.cells` names it, with the
      builder of its licensee. A sector whose PCI another eNB also uses is keyed
      `<emitter>@<site>`, a name no record carries, so that each still has its own clock.
    """
    rng = np.random.default_rng([seed, _GROUP_STREAM])
    sites: dict[str, str] = {}
    builders: dict[str, str] = {}
    placed: list[tuple[str, str, dict]] = []  # (site, builder, {lat, lon}) of placed sites
    for source, cfg in spec.get("sources", {}).items():
        if cfg.get("model", source) != "pseudorange":
            continue
        if cfg.get("record_shape") == "front_end":
            for s in lte_front_end.sectors(_cells_file(cfg), int(cfg["cells_from"]["earfcn"])):
                sites[s.key] = s.site
                builders.setdefault(s.site, builder_of(s.licensee))
            continue
        llh, carriers = cfg.get("emitters_llh"), None
        if "towers_from" in cfg:
            rows = _tower_rows(**cfg["towers_from"])
            llh = [[float(r["lat"]), float(r["lon"]), 0.0] for r in rows]
            carriers = [r["carrier"] for r in rows]
        for i in range(cfg["n_emitters"] if llh is None else len(llh)):
            emitter = f"{source}:sim{i}"
            if carriers is None:
                builder = BUILDERS[int(rng.integers(len(BUILDERS)))]
            else:
                builder = builder_of(carriers[i])
            here = None if llh is None else {"lat": llh[i][0], "lon": llh[i][1]}
            site = next(
                (
                    s
                    for s, b, p in placed
                    if here is not None and b == builder and _metres_apart(here, p) < SAME_SITE_M
                ),
                None,
            )
            if site is None:
                site = emitter
                builders[site] = builder
                if here is not None:
                    placed.append((site, builder, here))
            sites[emitter] = site
    return sites, builders


def builder_of(carrier: str) -> str:
    """The network builder behind a carrier name as ISED files it (BUILDER_OF_CARRIER)."""
    match = [b for name, b in BUILDER_OF_CARRIER.items() if name in carrier.lower()]
    if not match:
        raise ValueError(f"no network builder known for carrier {carrier!r}")
    return match[0]


def _tower_clocks(cfg: dict, groups, t: np.ndarray, rng) -> dict[str, np.ndarray]:
    """Each tower's clock (m) at times t: its builder's clock + its site's residual + its own
    (sector) residual, each an independent `models.oscillator` with that level's settings."""
    unknown = set(cfg) - {"builder", "site", "sector"}
    if unknown:
        raise ValueError(f"tower_clocks levels are builder, site and sector, not {unknown}")
    sites, builders = groups

    def draw(level: str) -> np.ndarray:
        return models.oscillator(rng, t, **(cfg.get(level) or {}))

    by_builder = {b: draw("builder") for b in dict.fromkeys(builders.values())}
    by_site = {s: by_builder[b] + draw("site") for s, b in builders.items()}
    return {e: by_site[s] + draw("sector") for e, s in sites.items()}


class _Reference:
    """The ground reference station (ADR-0020): a static second receiver at a surveyed point.

    It hears the same towers, so it shares their clocks, but has its own receiver clock, noise,
    multipath and dropouts (scenario `reference:` block; every value TBC). It draws from its own
    random stream, so adding it leaves every payload record of a scenario exactly as it was.
    The session is told the surveyed position: the true one plus a survey error of
    `survey_sigma_m` per axis.
    """

    def __init__(self, spec: dict, seed: int, t_truth: np.ndarray):
        cfg = spec["reference"]
        self.rng = np.random.default_rng([seed, REFERENCE_STREAM])
        self.origin = spec["origin_llh"]
        self.true_enu = np.asarray(llh_to_enu(cfg["position_llh"], self.origin), float)
        self.survey_sigma_m = float(cfg.get("survey_sigma_m", 0.0))
        self.told_enu = self.true_enu + self.rng.normal(0.0, self.survey_sigma_m, 3)
        self.sources = dict(cfg.get("sources", {}))
        self.t_truth = t_truth
        self.clock = _clock(cfg.get("clock"), t_truth, self.rng)

    def pseudoranges(self, source, ts, ts_ns, em, em_llh, told_em, clocks) -> list[Measurement]:
        cfg = self.sources[source]
        pos = np.tile(self.true_enu, (len(ts), 1))
        return models.pseudoranges(
            ts_ns,
            pos,
            self.rng,
            source=source,
            emitters=em,
            emitters_llh=em_llh,
            told_emitters=told_em,
            sigma_m=cfg["sigma_m"],
            clock_s=np.interp(ts, self.t_truth, self.clock),
            multipath=cfg.get("multipath"),
            dropout=cfg.get("dropout"),
            receiver="reference",
            tower_clock_m=clocks,
        )

    def meta(self) -> dict:
        """The ICD-session `reference` block: what the session is told."""
        llh = enu_to_llh(self.told_enu, self.origin)
        return {
            "position_llh": [float(x) for x in llh],
            "surveyed": False,
            "sigma_m": self.survey_sigma_m,
        }


def tower_height_m(filed_m: float, ground_m: float) -> float:
    """Antenna height above the ellipsoid datum the scenario uses, from ISED's filed height.

    Filed heights below GROUND_MISSING_BELOW_M lack the ground elevation, so the scenario's own
    ground height (its origin) stands in for it (TBC)."""
    return filed_m if filed_m >= GROUND_MISSING_BELOW_M else ground_m + filed_m


def _metres_apart(a: dict, b: dict) -> float:
    lat = np.radians((float(a["lat"]) + float(b["lat"])) / 2)
    dn = (float(a["lat"]) - float(b["lat"])) * 111_132.0
    de = (float(a["lon"]) - float(b["lon"])) * 111_320.0 * np.cos(lat)
    return float(np.hypot(dn, de))


def load_ray_table(
    file: str, towers_llh=None, duration_s: float | None = None
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """A ray tracer's output per tower: (times in s, excess delay in m, NaN where no path).

    With `towers_llh`, the result is keyed by the scenario's tower order, matched by position, and
    a tower the table doesn't cover is an error rather than another tower's rows. With
    `duration_s`, a run longer than the table is an error rather than a repeated last row.
    """
    with open(REFERENCE_DIR / file, newline="") as f:
        rows = list(csv.DictReader(f))
    by_tower: dict[int, list[dict]] = {}
    for r in rows:
        by_tower.setdefault(int(r["tower"]), []).append(r)
    table: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for tower, mine in sorted(by_tower.items()):
        mine.sort(key=lambda r: float(r["t_s"]))
        table[tower] = (
            np.array([float(r["t_s"]) for r in mine]),
            np.array([float(r["excess_m"]) if r["excess_m"] else np.nan for r in mine]),
        )
    if duration_s is not None:
        for times, _ in table.values():
            step = float(np.median(np.diff(times)))
            if duration_s > times[-1] + step:
                raise ValueError(f"{file} covers {times[-1] + step:.0f} s, run is {duration_s} s")
    if towers_llh is None:
        return table
    out = {}
    for i, (lat, lon, _) in enumerate(towers_llh):
        match = [
            t
            for t, mine in by_tower.items()
            if _metres_apart({"lat": lat, "lon": lon}, mine[0]) < SAME_SITE_M
        ]
        if not match:
            raise ValueError(f"{file} has no ray trace for the tower at {lat}, {lon}")
        out[i] = table[match[0]]
    return out


def select_towers(
    file: str,
    carrier: str,
    tx_mhz: float,
    count: int,
    min_km: float = 0.0,
    ground_m: float = 0.0,
) -> list[list[float]]:
    """The `count` nearest sites broadcasting one carrier, as [lat, lon, height]. Deterministic.

    One radio hears one carrier at a time, so a scenario's towers share an operator and frequency.
    A site filed more than once (closer than SAME_SITE_M) counts once: its nearest filing wins.
    Heights go through `tower_height_m` with `ground_m`, the scenario origin's height.
    """
    return [
        [float(r["lat"]), float(r["lon"]), tower_height_m(float(r["height_m"]), ground_m)]
        for r in _tower_rows(file, carrier, tx_mhz, count, min_km)
    ]


def _tower_rows(
    file: str, carrier: str, tx_mhz: float, count: int, min_km: float = 0.0
) -> list[dict]:
    """The registry rows `select_towers` picks, in its order, with every filed field."""
    with open(REFERENCE_DIR / file, newline="") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if carrier.lower() in r["carrier"].lower()
            and float(r["tx_mhz"]) == float(tx_mhz)
            and float(r["dist_km"]) >= min_km
        ]
    sites: list[dict] = []
    for r in sorted(rows, key=lambda r: float(r["dist_km"])):
        if all(_metres_apart(r, s) >= SAME_SITE_M for s in sites):
            sites.append(r)
    if len(sites) < count:
        raise ValueError(f"only {len(sites)} sites match {carrier} at {tx_mhz} MHz, need {count}")
    return sites[:count]


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


def _replay_streams(meas: list[Measurement], session: str, sources: list[str]):
    """Replace simulated sources with a recording's (ADR-0015), shifted to start at T0_NS.

    Replaying the same real sensor stream in two runs removes it as a source of difference.
    `session` is a session folder or MCAP file; its `/meas/<source>` records replace the sim's.
    """
    import msgspec

    from pnt.io import session as session_io
    from pnt.io.mcap_log import read_session

    topics = [f"/meas/{s}" for s in sources]
    recorded = [
        r
        for _, r in read_session(session_io.mcap_path(session), topics=topics)
        if isinstance(r, Measurement) and r.source in sources
    ]
    if not recorded:
        raise ValueError(f"{session} has none of the streams {sources}")
    shift = T0_NS - min(m.t_ns for m in recorded)
    kept = [m for m in meas if m.source not in sources]
    return kept + [msgspec.structs.replace(m, t_ns=m.t_ns + shift) for m in recorded]
