"""Received power from a located jammer: the hostile beacon's observable (P8, ADR-0025, #93).

Sim only, and receive-only (ADR-0001): nothing here transmits. The jammer exists only as a
scenario's `jamming_zone` faults (`sim/attacks.py`); this layer adds what the payload's GNSS
front end would measure of it, its in-band received power. Each `jamming_zone` fault is one
jammer, `jammer:sim<i>` in fault order, on from its `start_s` to its `end_s`.

Records (ICD-measurement, no new kind or source): source `gnss`, kind `rssi` (dBm), emitter
`jammer:sim<i>`, with `meta.hostile = True`, the jammer's told position (`meta.emitter_enu`) and
that position's 1-sigma per horizontal axis (`meta.emitter_sigma_m`). How the jammer was located
is not modelled: the told position is the truth plus a horizontal error, standing in for a
localisation step (JAM-ME, Tedeschi et al. 2020, does it from GPS before entering the jammed
area).

Model, log-distance path loss (Rappaport, *Wireless Communications*, 2nd ed., ch. 4):

    P_rx = P_tx(t) - L_1m - 10 n log10(d / 1 m) + S + w

- P_tx: transmit power (EIRP), a random walk from `tx_power_dbm` (ADR-0025 guardrail 4: never a
  constant). The adversary's own power changes are faults (`hostile_power`), not this walk.
- L_1m: free-space loss at 1 m at GPS L1, 20 log10(4 pi / lambda) = 36.4 dB.
- n: path-loss exponent.
- S: log-normal shadowing, Gauss-Markov in distance travelled, correlation exp(-dx / d_corr)
  (Gudmundson, Electronics Letters 27(23), 1991).
- w: white noise of the power estimate.
- The reported sigma is the shadowing and noise together: the front end cannot tell them apart.

All values are placeholders (ADR-0015); `HostileParams.provenance` labels each one. A filter that
uses the beacon is told the same exponent the sim uses (`pnt.nav.hostile`): optimistic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace

import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Measurement

L1_HZ = 1_575.42e6
C_MPS = 299_792_458.0
LOSS_1M_DB = float(20.0 * np.log10(4.0 * np.pi * L1_HZ / C_MPS))  # free space, 1 m, L1
MIN_RANGE_M = 1.0  # numerical: the log is taken of at least this range


@dataclass(frozen=True)
class HostileParams:
    tx_power_dbm: float = 20.0  # EIRP
    path_loss_exponent: float = 2.0
    shadowing_sigma_db: float = 3.0
    shadowing_corr_m: float = 20.0  # decorrelation distance
    noise_sigma_db: float = 0.5  # white noise of one power estimate
    power_rw_db: float = 0.02  # dB/sqrt(s): the honest jammer's own power wander
    told_position_sigma_m: float = 20.0  # per horizontal axis: localisation error
    provenance: dict = field(
        default_factory=lambda: {
            "tx_power_dbm": "TBC, unsourced: 100 mW. Only sets the received level; the filter "
            "learns it as a state",
            "path_loss_exponent": "literature form, TBC: 2 is free space (Friis); low-altitude "
            "air-to-ground links measure above 2 near the ground and approach 2 with height "
            "(Amorim et al., IEEE WCL 6(4), 2017)",
            "shadowing_sigma_db": "TBC: Amorim et al. 2017 report shadowing falling with height; "
            "3 dB is a placeholder for a drone at 30 m",
            "shadowing_corr_m": "TBC: Gudmundson 1991 form; 20 m is a placeholder",
            "noise_sigma_db": "TBC, unsourced",
            "power_rw_db": "TBC, unsourced: slow thermal wander of an honest jammer",
            "told_position_sigma_m": "TBC, unsourced: error of the step that located it",
        }
    )


def params(cfg: dict | None) -> HostileParams:
    """`HostileParams` with a scenario's overrides (any field but `provenance`)."""
    cfg = dict(cfg or {})
    known = {f.name for f in fields(HostileParams)} - {"provenance"}
    unknown = set(cfg) - known
    if unknown:
        raise ValueError(f"jammer_power: unknown settings {sorted(unknown)}")
    return replace(HostileParams(), **cfg)


@dataclass(frozen=True)
class Jammer:
    emitter: str
    enu: np.ndarray  # true position
    start_s: float
    end_s: float | None


def jammers(spec: dict) -> list[Jammer]:
    """The jammers a scenario's `jamming_zone` faults place, in fault order."""
    out = []
    for f in spec.get("faults") or []:
        if f["type"] != "jamming_zone":
            continue
        out.append(
            Jammer(
                emitter=f"jammer:sim{len(out)}",
                enu=np.asarray(llh_to_enu(f["center_llh"], spec["origin_llh"]), float),
                start_s=float(f.get("start_s", 0.0)),
                end_s=None if "end_s" not in f else float(f["end_s"]),
            )
        )
    return out


def power(
    ts: np.ndarray,
    ts_ns: np.ndarray,
    pos: np.ndarray,
    rng: np.random.Generator,
    found: list[Jammer],
    p: HostileParams,
) -> list[Measurement]:
    """`rssi` records from each jammer in `found` at times `ts` (s since start) while it is on,
    for a receiver at `pos` (N, 3) ENU. Draws only from `rng`."""
    sigma = float(np.hypot(p.shadowing_sigma_db, p.noise_sigma_db))
    step = np.r_[0.0, np.linalg.norm(np.diff(pos, axis=0), axis=1)]  # distance travelled
    dt = np.r_[0.0, np.diff(ts)]
    out: list[Measurement] = []
    for j in found:
        # every draw is taken for the whole run, so a jammer's window doesn't shift the others'
        told = j.enu + np.r_[rng.normal(0.0, p.told_position_sigma_m, 2), 0.0]
        tx = p.tx_power_dbm + np.cumsum(
            rng.normal(0.0, 1.0, len(ts)) * p.power_rw_db * np.sqrt(dt)
        )
        shadow = _gauss_markov(rng, step, p.shadowing_sigma_db, p.shadowing_corr_m)
        noise = rng.normal(0.0, p.noise_sigma_db, len(ts))
        d = np.maximum(np.linalg.norm(pos - j.enu, axis=1), MIN_RANGE_M)
        rx = tx - LOSS_1M_DB - 10.0 * p.path_loss_exponent * np.log10(d) + shadow + noise
        on = ts >= j.start_s
        if j.end_s is not None:
            on &= ts < j.end_s
        meta = {
            "hostile": True,
            "emitter_enu": [float(x) for x in told],
            "emitter_sigma_m": p.told_position_sigma_m,
        }
        out += [
            Measurement(
                t_ns=int(t),
                source="gnss",
                kind="rssi",
                value=(float(v),),
                sigma=(sigma,),
                emitter=j.emitter,
                meta=meta,
            )
            for t, v in zip(ts_ns[on], rx[on], strict=True)
        ]
    return out


def _gauss_markov(rng, step: np.ndarray, sigma: float, corr: float) -> np.ndarray:
    """Stationary first-order Gauss-Markov sequence over `step` (distance between samples)."""
    w = rng.normal(0.0, 1.0, len(step))
    out = np.empty(len(step))
    x = sigma * w[0]
    for i, s in enumerate(step):
        if i:
            rho = np.exp(-s / corr) if corr > 0 else 0.0
            x = rho * x + sigma * np.sqrt(1.0 - rho * rho) * w[i]
        out[i] = x
    return out
