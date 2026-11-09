"""Pre-flight integrity prediction (#92, P7): RAIM prediction for signals of opportunity.

Before take-off, predict the protection levels along the planned route, from the scenario's
trajectory, sources and planned denial, with no random draws in the result.

Method: a noise-free run of the estimator itself. Every measurement the scenario schedules is
replaced by its noise-free value at the true position (so innovations are zero and nothing is
gated out for noise), and the estimator is run on that. Its covariance then follows the
estimator's own process and measurement models, whatever `pnt.nav` says today (nothing here
copies a noise value), over the predicted schedule and geometry. HPL, VPL and the time PL come
out of the estimator's Estimates as usual.

What the schedule takes from the sim:
- Rates, sources, tower positions (the scenario's real towers, or its synthetic ring, which is
  drawn from `seed`: the seed names the world, not a noise draw), the reference station.
- Planned denial: the faults in `PLANNED` (a GPS outage, a jamming zone, a receiver with no fix)
  are kept, since a mission plan can know where GPS is denied. Every other fault (spoofing,
  meaconing, tower clock steps, sensor drift) is left out: a plan cannot foresee attacks, which
  is what the in-flight monitors are for.
- Tower dropouts (`dropout: {availability, block_s}`, the payload's and the reference station's
  own) are random, so every tower is kept and its reported sigma is inflated by
  1/sqrt(availability): the expected information of a tower heard that fraction of the time.
  Ray-traced blockage (`ray_table`) is geometry, so it is kept as is.

Noise-free values, per kind: `position_enu` and `velocity_enu` the truth; `altitude` the true
height; `time` the true receiver clock; `pseudorange` and `range` the range from the true
position to the emitter position the record carries (what the estimator is told), plus our true
clock where the scenario puts it in the readings, with every tower clock held at zero (the
estimator learns it the same either way). Other kinds pass through as recorded and are counted
in `Prediction.passthrough`; the estimators on main ignore them.

Not modelled: biases the covariance does not carry (multipath, a tower's published position
error, a reference survey error), and gating of good measurements by noise. `compare` measures
how much they matter against real runs of the same scenario.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import msgspec
import numpy as np

from pnt.core.frames import emitter_enu, llh_to_enu
from pnt.core.measurement import Estimate, Measurement
from pnt.integrity.protection import tpl
from pnt.metrics import ALERT_LIMIT_M
from pnt.nav import estimate
from pnt.sim import trajectory
from pnt.sim.scenario import T0_NS, SimRun, generate, load

C = 299_792_458.0
# Faults a mission plan can know about in advance: planned GNSS denial
PLANNED = frozenset({"outage", "jamming_zone", "gps_no_fix"})
# Over-limit windows closer than this are reported as one. TBC: two updates of a 1 Hz tower.
MERGE_S = 2.0


@dataclass
class Prediction:
    scenario: str
    seed: int
    estimator: str
    alert_limit_m: float
    t_s: np.ndarray  # seconds since the scenario start
    hpl_m: np.ndarray  # nan where the estimator gives none
    vpl_m: np.ndarray
    tpl_s: np.ndarray  # nan where the clock is not estimated
    kept_faults: list[str] = field(default_factory=list)
    dropped_faults: list[str] = field(default_factory=list)
    availability: dict[str, float] = field(default_factory=dict)
    passthrough: dict[str, int] = field(default_factory=dict)

    def unavailable(self, merge_s: float = MERGE_S) -> list[tuple[float, float]]:
        """Windows (start, end) in s where the predicted HPL is over the alert limit, with gaps
        shorter than `merge_s` closed: HPL saw-tooths between tower updates, so it can dip
        under the limit for a moment each second without the route being usable."""
        out: list[tuple[float, float]] = []
        for a, b in _windows(self.t_s, ~(self.hpl_m <= self.alert_limit_m)):
            if out and a - out[-1][1] < merge_s:
                out[-1] = (out[-1][0], b)
            else:
                out.append((a, b))
        return out

    def as_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "seed": self.seed,
            "estimator": self.estimator,
            "alert_limit_m": self.alert_limit_m,
            "t_s": self.t_s.tolist(),
            "hpl_m": _list(self.hpl_m),
            "vpl_m": _list(self.vpl_m),
            "tpl_s": _list(self.tpl_s),
            "unavailable": self.unavailable(),
            "kept_faults": self.kept_faults,
            "dropped_faults": self.dropped_faults,
            "availability": self.availability,
            "passthrough": self.passthrough,
        }


def _list(x: np.ndarray) -> list:
    return [None if np.isnan(v) else float(v) for v in x]


def _windows(t: np.ndarray, mask: np.ndarray) -> list[tuple[float, float]]:
    out, start = [], None
    for ti, m in zip(t, mask, strict=True):
        if m and start is None:
            start = float(ti)
        elif not m and start is not None:
            out.append((start, float(ti)))
            start = None
    if start is not None:
        out.append((start, float(t[-1])))
    return out


def plan(spec: dict) -> tuple[dict, dict[str, float], list[str], list[str]]:
    """The scenario as a mission plan sees it: (spec, availability by source, kept faults,
    dropped faults). Dropouts are switched off with availability 1.0, which keeps the sim's
    random draws in the same order, so tower geometry matches a real run of the same seed. A
    reference station's sources are keyed `reference:<source>`: it has its own dropouts."""
    spec = copy.deepcopy(spec)
    faults = spec.get("faults") or []
    kept = [f for f in faults if f["type"] in PLANNED]
    spec["faults"] = kept
    availability = {}
    groups = {
        "": spec.get("sources", {}),
        "reference:": (spec.get("reference") or {}).get("sources", {}),
    }
    for prefix, sources in groups.items():
        for source, cfg in sources.items():
            d = cfg.get("dropout")
            if d:
                availability[prefix + source] = float(d["availability"])
                cfg["dropout"] = {**d, "availability": 1.0}
    dropped = [f["type"] for f in faults if f["type"] not in PLANNED]
    return spec, availability, [f["type"] for f in kept], dropped


def noise_free(
    run: SimRun, availability: dict[str, float] | None = None
) -> tuple[list[Measurement], dict[str, int]]:
    """The run's measurements with noise-free values (module docstring). Returns them and the
    count of records passed through as recorded, by kind."""
    spec, availability = run.spec, availability or {}
    origin = spec.get("origin_llh")
    traj = {**spec["trajectory"], "_origin_llh": origin}
    meas = run.measurements
    if not meas:
        return [], {}
    t_s = (np.array([m.t_ns for m in meas]) - T0_NS) / 1e9
    pos, vel = trajectory.make(traj, t_s)
    t_truth = (np.array([t.t_ns for t in run.truth]) - T0_NS) / 1e9
    clock = np.interp(t_s, t_truth, [t.clock_bias_s for t in run.truth])
    ref = None
    if run.reference is not None:
        ref = llh_to_enu(run.reference["position_llh"], origin)
    emitters: dict[str, np.ndarray | None] = {}
    out, passthrough = [], {}
    for i, m in enumerate(meas):
        p = pos[i] if m.receiver == "payload" else ref
        sigma = m.sigma
        if m.kind == "position_enu":
            value = tuple(p)
        elif m.kind == "velocity_enu":
            value = tuple(vel[i])
        elif m.kind == "altitude":
            value = (float(p[2]),)
        elif m.kind == "time" and m.receiver == "payload":
            value = (float(clock[i]),)
        elif m.kind in ("pseudorange", "range"):
            if m.emitter not in emitters:
                emitters[m.emitter] = emitter_enu(m.meta, origin)
            e = emitters[m.emitter]
            if e is None:
                out.append(m)
                passthrough[m.kind] = passthrough.get(m.kind, 0) + 1
                continue
            value = float(np.linalg.norm(p - e))
            cfg = spec.get("sources", {}).get(m.source, {})
            if m.kind == "pseudorange" and m.receiver == "payload" and cfg.get("receiver_clock"):
                value += C * float(clock[i])
            value = (value,)
            a = availability.get(
                m.source if m.receiver == "payload" else f"{m.receiver}:{m.source}"
            )
            if a:
                sigma = tuple(s / np.sqrt(a) for s in sigma)
        else:
            out.append(m)
            passthrough[m.kind] = passthrough.get(m.kind, 0) + 1
            continue
        out.append(msgspec.structs.replace(m, value=tuple(float(v) for v in value), sigma=sigma))
    return out, passthrough


def _series(estimates: list[Estimate]) -> tuple[np.ndarray, ...]:
    t = (np.array([e.t_ns for e in estimates]) - T0_NS) / 1e9
    nan = float("nan")
    hpl = np.array([nan if e.hpl_m is None else e.hpl_m for e in estimates], float)
    vpl = np.array([nan if e.vpl_m is None else e.vpl_m for e in estimates], float)
    tp = np.array([nan if (v := tpl(e.clock_sigma_s)) is None else v for e in estimates], float)
    return t, hpl, vpl, tp


def predict(
    scenario: str | dict,
    seed: int = 0,
    estimator: str = "ekf",
    alert_limit_m: float = ALERT_LIMIT_M,
) -> Prediction:
    """Predicted protection levels along a scenario's route (module docstring)."""
    spec = load(scenario) if isinstance(scenario, str) else scenario
    planned, availability, kept, dropped = plan(spec)
    run = generate(planned, seed=seed)
    meas, passthrough = noise_free(run, availability)
    origin = spec.get("origin_llh")
    est = list(estimate(estimator, meas, origin_llh=origin, reference=run.reference))
    t, hpl, vpl, tp = _series(est)
    return Prediction(
        spec["name"], seed, estimator, alert_limit_m, t, hpl, vpl, tp,
        kept, dropped, availability, passthrough,
    )  # fmt: skip


def actual(scenario: str | dict, seed: int = 0, estimator: str = "ekf") -> tuple[np.ndarray, ...]:
    """(t_s, hpl, vpl, tpl) of a real run of the scenario: noise, dropouts and every fault."""
    spec = load(scenario) if isinstance(scenario, str) else scenario
    run = generate(spec, seed=seed)
    est = estimate(estimator, run.measurements, origin_llh=spec.get("origin_llh"),
                   reference=run.reference)  # fmt: skip
    return _series(list(est))


def compare_one(
    scenario: str, seed: int, estimator: str, alert_limit_m: float, settle_s: float = 10.0
) -> dict:
    """Prediction and real run for one seed, on their common epochs from `settle_s` on (both
    start from the same first fix, so the start-up epochs would agree trivially)."""
    p = predict(scenario, seed, estimator, alert_limit_m)
    t, hpl, _, _ = actual(scenario, seed, estimator)
    common, ip, ia = np.intersect1d(np.round(p.t_s, 3), np.round(t, 3), return_indices=True)
    keep = common >= settle_s
    common, ip, ia = common[keep], ip[keep], ia[keep]
    return {"seed": seed, "t_s": common, "pred": p.hpl_m[ip], "act": hpl[ia]}


def summarize(rows: list[dict], alert_limit_m: float) -> dict:
    """Agreement between predicted and real HPL over every epoch of every seed.

    - ratio: real / predicted HPL (1 = exact); median, 5th and 95th percentiles.
    - availability_agree: fraction of epochs where both say the same about HPL <= alert limit.
    - missed_unavailable: fraction of epochs predicted available that were not (the costly miss
      for a mission plan); false_unavailable the reverse.
    """
    pred = np.concatenate([r["pred"] for r in rows])
    act = np.concatenate([r["act"] for r in rows])
    ok = np.isfinite(pred) & np.isfinite(act) & (pred > 0)
    ratio = act[ok] / pred[ok]
    p_av, a_av = pred <= alert_limit_m, act <= alert_limit_m
    peak = np.array([np.nanmax(r["act"]) / np.nanmax(r["pred"]) for r in rows])
    return {
        "seeds": len(rows),
        "epochs": int(pred.size),
        "ratio_median": float(np.median(ratio)),
        "ratio_p05": float(np.percentile(ratio, 5)),
        "ratio_p95": float(np.percentile(ratio, 95)),
        "peak_ratio_median": float(np.median(peak)),
        "peak_ratio_worst": float(np.max(peak)),
        "availability_agree": float(np.mean(p_av == a_av)),
        "missed_unavailable": float(np.mean(p_av & ~a_av)),
        "false_unavailable": float(np.mean(~p_av & a_av)),
    }


def plot(p: Prediction, rows: list[dict], summary: dict, out) -> None:
    """Prediction against real runs: seed 0's HPL over time (top) and the spread of real /
    predicted HPL over every seed (bottom). Needs matplotlib (ground extra)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    blue, violet, red, grey = "#2a78d6", "#6250d6", "#d03b3b", "#898781"
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, height_ratios=[3, 2])
    first = rows[0]
    left_out = (
        f" (prediction leaves out {', '.join(p.dropped_faults)})" if p.dropped_faults else ""
    )
    ax1.semilogy(
        first["t_s"], first["act"], color=blue, lw=2, label=f"real run, seed {first['seed']}"
    )
    ax1.semilogy(p.t_s, p.hpl_m, color=violet, lw=1.2, ls="--", label="pre-flight prediction")
    ax1.axhline(
        p.alert_limit_m,
        color=red,
        lw=1.5,
        ls=":",
        label=f"alert limit {p.alert_limit_m:g} m (TBC)",
    )
    for a, b in p.unavailable():
        ax1.axvspan(a, b, color=red, alpha=0.08, lw=0)
    ax1.set_ylabel("HPL (m)")
    ax1.legend(loc="upper right", frameon=False)
    ax1.set_title(
        f"{p.scenario}: predicted vs real HPL, estimator {p.estimator}{left_out}",
        loc="left",
    )
    t = first["t_s"]
    ratio = np.full((len(rows), len(t)), np.nan)
    for i, r in enumerate(rows):
        n = min(len(t), len(r["act"]))
        ratio[i, :n] = r["act"][:n] / r["pred"][:n]
    lo, med, hi = np.nanpercentile(ratio, [5, 50, 95], axis=0)
    ax2.fill_between(t, lo, hi, color=blue, alpha=0.2, lw=0, label="5-95 % of seeds")
    ax2.plot(t, med, color=blue, lw=2, label="median")
    ax2.axhline(1.0, color=grey, lw=1)
    ax2.set_ylabel("real / predicted HPL")
    ax2.set_xlabel("time since start (s)")
    ax2.legend(loc="upper right", frameon=False)
    s = summary
    ax2.set_title(
        f"{s['seeds']} seeds: ratio median {s['ratio_median']:.2f} (5-95 %: {s['ratio_p05']:.2f}-"
        f"{s['ratio_p95']:.2f}); availability agrees on {100 * s['availability_agree']:.1f} % of "
        f"epochs, predicted available but not: {100 * s['missed_unavailable']:.2f} %",
        loc="left", fontsize=9,
    )  # fmt: skip
    for ax in (ax1, ax2):
        ax.grid(True, color="#e1e0d9", lw=0.8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
