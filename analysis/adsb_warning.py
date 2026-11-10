"""ADS-B interference early warning (#91, P6, ADR-0031): lead time, false alerts and what the
raised GNSS prior does to the protection level, on the YOW approach with ADS-B traffic.

Sim evidence only: the traffic, the jammer and spoofer, the aircraft's avionics quality and the
nuisance dips are placeholders (TBC), so these numbers are a regression baseline, not a
real-world lead time. Seeds 0..N-1 as `pnt eval` uses; estimator `ekf-mhss` (the monitor that
reads ADS-B), against the same estimator with the prior left alone.

- Lead time: from the warning's onset (first epoch flagged `adsb_interference` or
  `adsb_spoofed_aircraft`) to (a) our own receiver entering the zone (truth geometry: the jammer's
  `onset_m` ring, the spoofer's `radius_m`) and (b) our own estimator's first GNSS alert
  (`pnt.metrics.ALERT_FLAGS`, after start-up). Positive is early.
- False alerts: warning onsets on the fault-free scenario, per hour of flight.
- Prior: HPL with the raised prior against the same runs without it, and epochs whose horizontal
  error exceeds the HPL (misleading).

    python analysis/adsb_warning.py [runs] [--plot out.png]
"""

from __future__ import annotations

import sys

import numpy as np

from pnt.experiments import _map
from pnt.integrity.mhss import MHSS, Params
from pnt.metrics import ALERT_FLAGS
from pnt.nav import ekf
from pnt.sim.scenario import T0_NS, generate, load

CLEAN = "uc02-yow-approach-adsb"
FAULTED = ("uc02-yow-approach-adsb-jammed", "uc02-yow-approach-adsb-spoofed")
WARN_FLAGS = frozenset({"adsb_interference", "adsb_spoofed_aircraft"})
# Start-up: the first estimates come from the first fix's wide covariance. Same role as
# pnt.dashboard.health.STARTUP_MAX_S; only alerts after it count
STARTUP_S = 20.0


def _own_entry_s(spec: dict, run) -> float | None:
    """When our true position first enters the scenario's zone (s since start)."""
    from pnt.core.frames import llh_to_enu

    if not spec.get("faults"):
        return None
    f = spec["faults"][0]
    r = f["onset_m"] if f["type"] == "jamming_zone" else f["radius_m"]
    c = np.asarray(llh_to_enu(f["center_llh"], spec["origin_llh"]))[:2]
    for t in run.truth:
        if np.hypot(*(np.asarray(t.pos_enu[:2]) - c)) < r:
            return (t.t_ns - T0_NS) / 1e9
    return None


def one(scenario: str, seed: int, raise_prior: bool = True, series: bool = False) -> dict:
    spec = load(scenario)
    run = generate(spec, seed=seed)
    params = Params() if raise_prior else Params(p_gnss_cm_warned=Params().p_gnss_cm)
    truth = {t.t_ns: t.pos_enu for t in run.truth}
    est = ekf.run(
        run.measurements,
        origin_llh=spec["origin_llh"],
        monitor=lambda f: MHSS(f, params=params),
    )
    t, hpl, err, warn, alert = [], [], [], [], []
    for e in est:
        if e.t_ns not in truth:
            continue
        t.append((e.t_ns - T0_NS) / 1e9)
        hpl.append(e.hpl_m)
        err.append(float(np.hypot(*np.subtract(e.pos_enu[:2], truth[e.t_ns][:2]))))
        warn.append(bool(WARN_FLAGS & set(e.flags)))
        alert.append(bool(ALERT_FLAGS & set(e.flags)))
    t, hpl, err = np.array(t), np.array(hpl), np.array(err)
    warn, alert = np.array(warn), np.array(alert)
    live = t >= STARTUP_S
    onsets = np.flatnonzero(live & warn & ~np.concatenate([[False], warn[:-1]]))
    first = lambda mask: float(t[live & mask][0]) if (live & mask).any() else None  # noqa: E731
    out = {
        "scenario": scenario,
        "seed": seed,
        "warn_s": first(warn),
        "own_entry_s": _own_entry_s(spec, run),
        "own_alert_s": first(alert),
        "warn_onsets": len(onsets),
        "hours": float((t[live][-1] - t[live][0]) / 3600) if live.any() else 0.0,
        "misleading": int(np.sum(live & (err > hpl))),
        "hpl_at_entry_m": None,
    }
    if out["own_entry_s"] is not None:
        out["hpl_at_entry_m"] = float(np.interp(out["own_entry_s"], t, hpl))
    if series:
        out["series"] = {"t": t, "hpl": hpl, "err": err, "warn": warn}
    return out


def _lead(rows: list[dict], key: str) -> np.ndarray:
    return np.array(
        [r[key] - r["warn_s"] for r in rows if r["warn_s"] is not None and r[key] is not None]
    )


def _fmt(v: np.ndarray) -> str:
    if not len(v):
        return "none"
    return f"{np.median(v):.1f} (min {v.min():.1f}, max {v.max():.1f})"


def plot(path: str, jobs: int | None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from pnt.cli import _commit

    tasks = [(s, 0, rp, True) for s in FAULTED for rp in (True, False)]
    res = _map(one, tasks, jobs)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    for ax, s in zip(axes, FAULTED, strict=True):
        on, off = (r for r in res if r["scenario"] == s)
        a, b = on["series"], off["series"]
        ax.semilogy(b["t"], b["hpl"], color="0.55", lw=1.5, label="HPL, prior left alone")
        ax.semilogy(a["t"], a["hpl"], color="#2a6fdb", lw=1.8, label="HPL, prior raised by ADS-B")
        ax.semilogy(a["t"], a["err"], color="#1a9e6a", lw=1.0, label="horizontal error (truth)")
        if on["warn_s"] is not None:
            ax.axvline(on["warn_s"], color="#d98a00", ls="--", lw=1.2, label="ADS-B warning")
        if on["own_entry_s"] is not None:
            ax.axvline(on["own_entry_s"], color="#c03030", ls=":", lw=1.5,
                       label="we enter the zone (truth)")  # fmt: skip
        ax.set_title(s, fontsize=10)
        ax.set_xlabel("time since start (s)")
        ax.grid(True, which="both", alpha=0.25)
    axes[0].set_ylabel("m")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle(f"ADS-B early warning, ekf-mhss, seed 0 (sim), commit {_commit()}", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    print(f"wrote {path}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    runs = int(args[0]) if args else 50
    jobs = None
    seeds = range(runs)
    tasks = [(s, k, True) for s in (*FAULTED, CLEAN) for k in seeds]
    tasks += [(s, k, False) for s in FAULTED for k in seeds]
    rows = _map(one, tasks, jobs)
    with_prior = [r for r, tk in zip(rows, tasks, strict=True) if tk[2]]
    without = [r for r, tk in zip(rows, tasks, strict=True) if not tk[2]]
    print(f"ekf-mhss, seeds 0-{runs - 1} (sim, every traffic and zone parameter TBC)")
    print(
        "| scenario | warned runs | lead over own zone entry, s "
        "| lead over own first GNSS alert, s |"
    )
    print("| --- | --- | --- | --- |")
    for s in FAULTED:
        rs = [r for r in with_prior if r["scenario"] == s]
        n = sum(r["warn_s"] is not None for r in rs)
        print(f"| {s} | {n}/{len(rs)} | {_fmt(_lead(rs, 'own_entry_s'))} "
              f"| {_fmt(_lead(rs, 'own_alert_s'))} |")  # fmt: skip
    rs = [r for r in with_prior if r["scenario"] == CLEAN]
    n_fa, hours = sum(r["warn_onsets"] for r in rs), sum(r["hours"] for r in rs)
    worst = max(rs, key=lambda r: r["warn_onsets"])
    print(f"\nfalse alerts on {CLEAN}: {n_fa} warning onsets in {hours:.2f} h of flight "
          f"({n_fa / hours:.2f} per hour); runs with any: "
          f"{sum(r['warn_onsets'] > 0 for r in rs)}/{len(rs)}; worst run seed {worst['seed']} "
          f"with {worst['warn_onsets']}")  # fmt: skip
    print(
        "\n| scenario | prior | HPL at our zone entry, median m | misleading epochs (all runs) |"
    )
    print("| --- | --- | --- | --- |")
    for s in FAULTED:
        for label, group in (("raised by ADS-B", with_prior), ("left alone", without)):
            rs = [r for r in group if r["scenario"] == s]
            h = [r["hpl_at_entry_m"] for r in rs if r["hpl_at_entry_m"] is not None]
            print(f"| {s} | {label} | {np.median(h):.0f} | {sum(r['misleading'] for r in rs)} |")
    if "--plot" in sys.argv:
        plot(sys.argv[sys.argv.index("--plot") + 1], jobs)


if __name__ == "__main__":
    main()
