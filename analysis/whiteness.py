"""The innovation whiteness test (#275 step 1, ADR-0055 Proposed) on sim and real sessions.

    python analysis/whiteness.py study [--jobs 3] --out analysis/results/whiteness-275
    python analysis/whiteness.py real [LABEL=]<session>-lte ... --out DIR
    python analysis/whiteness.py hash --out FILE.json [--seeds 0 1] [--real <session> ...]
        [--estimators ...] [--whiteness]
    python analysis/whiteness.py timing --out FILE.json
    python analysis/whiteness.py compare A.json B.json

Every run here uses the panel's path (`nav.estimate(..., whiteness=True)`), except `hash`
without `--whiteness` and `timing`, which use the eval path (the test off).

- `study`: `ekf` as registered (and `ekf-calibrated`, whose model carries the multipath) on
  honest-noise scenarios (`HONEST`: every error white, the told sigma right) and on the legs
  #226/#251 diagnosed with correlated errors the filter takes as white (`CORRELATED`). Each run
  logs every lag-1 pair of normalised innovations (`pnt.integrity.whiteness`); the window and
  threshold are then chosen offline on the tuning seeds (`TUNE`, 0-9) from `GRID`, and the
  chosen pair is reported on the held-out seeds (`TEST`, 10-29): runs flagged per source,
  false-alarm onsets per hour where the source's errors are white, detection delay. The offline
  statistic is checked against the flags the filter itself raises at the registered defaults.
  GNSS position is analysis only: its statistic is reported, it is never flagged.
- `real`: `ekf` as registered over whole real sessions: per source r, T, the share of epochs
  over the threshold, the share flagged, and the first time over. Statistics only: no
  position, range or bearing is written.
- `hash`: a hash of every estimate (time, position, velocity, covariance, clock, HPL, VPL,
  status, trust, flags without this test's) of every registered estimator, on `HASH_SCENARIOS`
  and the given real sessions. It imports only what `main` has, so it runs against any checkout
  (`PYTHONPATH=<checkout>/src`); `compare` diffs two such files. `--whiteness` takes the
  panel's path (this branch only), to show the flag changes nothing else.
- `timing`: wall time of the eval path, to compare with `main`'s.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import msgspec
import numpy as np

from pnt import experiments, nav
from pnt.core.measurement import Measurement

HONEST = ("easy-nominal", "easy-outage", "easy-long-outage", "nominal")
# #226/#251's diagnosis: told 2 m against 50 m white + 50 m / 30 s multipath (challenge legs);
# realistic's 50 m / 30 s multipath and told tower positions the default filter does not carry
CORRELATED = (
    "challenge-drone-nominal",
    "challenge-drone-outage",
    "challenge-approach-outage",
    "realistic-long-outage",
)
ESTIMATORS = ("ekf", "ekf-calibrated")
TUNE = tuple(range(10))
TEST = tuple(range(10, 30))
GRID_W = (20.0, 30.0, 60.0, 120.0)  # s
GRID_T = (3.0, 4.0, 5.0, 6.0, 8.0)
MIN_PAIRS = 30  # as WhitenessParams (TBC)
# Sources the sim makes white with the right told sigma in every scenario here. Baro is not one:
# every scenario adds an untold 1 m bias (sim/models.py `baro`), so it is reported apart.
# Flagged sources watched for false alarms in honest runs. GNSS position is analysis only
# (WhitenessParams.report_only, owners 2026-11-11): reported, never flagged, never counted.
WATCHED = ("lte", "gnss:time", "baro")
HASH_SCENARIOS = (
    "challenge-drone-outage",
    "challenge-approach-outage",
    "challenge-timing-outage",
    "gps-outage",
    "realistic-long-outage",
    "meaconing",
    "spoof-jump",
    "spoof-ramp",
    "easy-nominal",
    "nominal",
)
ADVISORY = "innovations_correlated:"  # pnt.integrity.whiteness.FLAG, spelled out for `hash`


def _commit() -> str:
    """The commit of the `pnt` imported (for `hash`, the checkout on PYTHONPATH)."""
    import pnt

    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            cwd=Path(pnt.__file__).parent,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()
    except OSError:
        return "unknown"


# --- recording -----------------------------------------------------------------------------------
def _recorded_run(estimator: str, meas, origin):
    """Run `estimator` as registered, with the filter's whiteness test logging every pair.
    Returns (estimates, {source: (t_ns, p, a2, b2) arrays})."""
    from pnt.integrity import whiteness
    from pnt.nav import ekf as ekf_mod

    made = []

    class Recorder(whiteness.Whiteness):
        def __init__(self, params=None):
            super().__init__(params)
            self.log = []
            made.append(self)

        def _pair(self, t_ns, source, p, a2, b2):
            self.log.append((t_ns, source, p, a2, b2))
            super()._pair(t_ns, source, p, a2, b2)

    real = ekf_mod.Whiteness
    ekf_mod.Whiteness = Recorder
    try:
        est = list(nav.estimate(estimator, meas, origin_llh=origin, whiteness=True))
    finally:
        ekf_mod.Whiteness = real
    log = made[0].log if made else []
    pairs = {}
    for src in sorted({r[1] for r in log}):
        rows = [(r[0], r[2], r[3], r[4]) for r in log if r[1] == src]
        t = np.array([r[0] for r in rows], dtype=np.int64)
        v = np.array([r[1:] for r in rows], dtype=float)
        pairs[src] = (t, v[:, 0], v[:, 1], v[:, 2])
    return est, pairs


def window_stats(t, p, a2, b2, epochs: np.ndarray, window_s: float):
    """Per epoch: (r, T, pairs) over the pairs in (epoch - window, epoch), as the filter sees
    them when it yields the estimate at that epoch."""
    w = int(window_s * 1e9)
    hi = np.searchsorted(t, epochs, "left")
    lo = np.searchsorted(t, epochs - w, "right")
    c = [np.concatenate([[0.0], np.cumsum(x)]) for x in (p, p * p, a2, b2)]
    sp, sp2, sa, sb = (x[hi] - x[lo] for x in c)
    n = hi - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        T = np.where(sp2 > 0, sp / np.sqrt(np.maximum(sp2, 1e-300)), 0.0)
        r = np.where(sa * sb > 0, sp / np.sqrt(np.maximum(sa * sb, 1e-300)), 0.0)
    return r, T, n


def _onsets(on: np.ndarray) -> int:
    return int(on[0]) + int(np.sum(on[1:] & ~on[:-1])) if len(on) else 0


def score(pairs, epochs: np.ndarray, window_s: float, thr: float) -> dict:
    """Per source: onsets, share of epochs flagged, first flag after the source's first pair (s),
    largest T."""
    out = {}
    for src, (t, p, a2, b2) in pairs.items():
        _, T, n = window_stats(t, p, a2, b2, epochs, window_s)
        on = (n >= MIN_PAIRS) & (T > thr)
        first = np.flatnonzero(on)
        out[src] = {
            "onsets": _onsets(on),
            "flagged": float(on.mean()) if len(on) else 0.0,
            "delay_s": float((epochs[first[0]] - t[0]) / 1e9) if len(first) else None,
            "max_T": float(np.max(np.where(n >= MIN_PAIRS, T, -np.inf), initial=-np.inf)),
        }
    return out


def _sim_task(scenario: str, estimator: str, seed: int) -> dict:
    from pnt.integrity.whiteness import WhitenessParams
    from pnt.sim.scenario import generate, load

    spec = load(scenario)
    run = generate(spec, seed=seed)
    est, pairs = _recorded_run(estimator, run.measurements, spec.get("origin_llh"))
    epochs = np.array([e.t_ns for e in est], dtype=np.int64)
    grid = {f"{w:g}/{thr:g}": score(pairs, epochs, w, thr) for w in GRID_W for thr in GRID_T}
    d = WhitenessParams()  # the filter's own flags at its defaults, against the offline value
    off = score(pairs, epochs, d.window_s, d.threshold)
    flagged = {
        s: float(np.mean([f"{ADVISORY}{s}" in e.flags for e in est])) for s in pairs
    }  # fmt: skip
    flaggable = [s for s in pairs if s not in d.report_only]
    mism = max((abs(flagged[s] - off[s]["flagged"]) for s in flaggable), default=0.0)
    return {
        "scenario": scenario,
        "estimator": estimator,
        "seed": seed,
        "hours": float((epochs[-1] - epochs[0]) / 3.6e12) if len(epochs) else 0.0,
        "grid": grid,
        "filter_vs_offline": mism,
    }


# --- study ---------------------------------------------------------------------------------------
def _agg(rows, key: str, scenarios, estimator: str) -> dict:
    """Per (scenario, source) at grid key: runs flagged, onsets, hours, delays, max T."""
    out = {}
    for sc in scenarios:
        rs = [r for r in rows if r["scenario"] == sc and r["estimator"] == estimator]
        for src in sorted({s for r in rs for s in r["grid"][key]}):
            v = [r["grid"][key].get(src) for r in rs]
            v = [x for x in v if x is not None]
            delays = [x["delay_s"] for x in v if x["delay_s"] is not None]
            out[f"{sc}|{src}"] = {
                "runs": len(rs),
                "with_source": len(v),
                "flagged_runs": sum(x["onsets"] > 0 for x in v),
                "onsets": sum(x["onsets"] for x in v),
                "hours": sum(r["hours"] for r in rs),
                "flagged_share": float(np.mean([x["flagged"] for x in v])) if v else 0.0,
                "delay_median_s": float(np.median(delays)) if delays else None,
                "delay_max_s": float(np.max(delays)) if delays else None,
                "max_T": float(max(x["max_T"] for x in v)) if v else None,
                "min_max_T": float(min(x["max_T"] for x in v)) if v else None,
            }
    return out


def choose(rows) -> tuple[str, list[dict]]:
    """The window and threshold on the tuning rows (`ekf`), in this order: fewest onsets of a
    flagged source (`WATCHED`) in an honest scenario (false alarms); fewest correlated runs with
    LTE never flagged (misses); shortest worst-scenario median LTE delay; higher threshold. GNSS
    position is analysis only and not counted; nor is GNSS time in a correlated scenario, where
    the filter is overconfident when GPS returns and its innovations are truly correlated."""
    table = []
    for w in GRID_W:
        for thr in GRID_T:
            key = f"{w:g}/{thr:g}"
            h = _agg(rows, key, HONEST, "ekf")
            c = _agg(rows, key, CORRELATED, "ekf")
            fa = sum(v["onsets"] for k, v in h.items() if k.split("|")[1] in WATCHED)
            lte = [v for k, v in c.items() if k.endswith("|lte")]
            missed = sum(v["with_source"] - v["flagged_runs"] for v in lte)
            delay = max((v["delay_median_s"] or math.inf) for v in lte) if lte else math.inf
            table.append({"key": key, "false_onsets": fa, "missed": missed, "delay_s": delay})

    def rank(r):
        return r["false_onsets"], r["missed"], r["delay_s"], -float(r["key"].split("/")[1])

    best = min(table, key=rank)
    return best["key"], table


def study(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tasks = [(sc, est, s) for sc in (*HONEST, *CORRELATED) for est in ESTIMATORS
             for s in (*TUNE, *TEST)]  # fmt: skip
    rows = experiments._map(_sim_task, tasks, args.jobs)
    tune = [r for r in rows if r["seed"] in TUNE]
    test = [r for r in rows if r["seed"] in TEST]
    key, table = choose(tune)
    res = {
        "commit": _commit(),
        "chosen": key,
        "tuning_table": table,
        "filter_vs_offline_max": max(r["filter_vs_offline"] for r in rows),
        "tune": {e: _agg(tune, key, (*HONEST, *CORRELATED), e) for e in ESTIMATORS},
        "test": {e: _agg(test, key, (*HONEST, *CORRELATED), e) for e in ESTIMATORS},
        "test_maxT": {
            e: _agg(test, f"{key.split('/')[0]}/{GRID_T[0]:g}", (*HONEST, *CORRELATED), e)
            for e in ESTIMATORS
        },
    }
    (out / "study.json").write_text(json.dumps(res, indent=1))
    _plot_study(test, key, out / "separation.png")
    print(json.dumps({k: res[k] for k in ("commit", "chosen", "filter_vs_offline_max")}))


def _plot_study(test, key, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    thr = float(key.split("/")[1])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, est in zip(axes, ESTIMATORS, strict=True):
        labels, vals, colors = [], [], []
        for sc in (*HONEST, *CORRELATED):
            for src in ("lte", "gnss", "baro"):
                runs = [r for r in test if r["scenario"] == sc and r["estimator"] == est]
                v = [r["grid"][key][src]["max_T"] for r in runs if src in r["grid"][key]]
                if not v:
                    continue
                labels.append(f"{sc} · {src}")
                vals.append(v)
                colors.append("#c0392b" if sc in CORRELATED and src == "lte" else "#2c7fb8")
        pos = np.arange(len(vals))
        for i, (v, col) in enumerate(zip(vals, colors, strict=True)):
            ax.scatter(np.full(len(v), i) + np.linspace(-0.2, 0.2, len(v)), v, s=8, color=col)
        ax.axhline(thr, color="k", lw=1, ls="--", label=f"threshold {thr:g} (TBC)")
        ax.set_xticks(pos, labels, rotation=60, ha="right", rotation_mode="anchor", fontsize=7)
        ax.set_yscale("symlog", linthresh=10)
        ax.set_title(f"{est}: largest T per run, seeds {TEST[0]}–{TEST[-1]}", fontsize=10)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("whiteness statistic T (window " + key.split("/")[0] + " s)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


# --- real sessions -------------------------------------------------------------------------------
def _load(path: str):
    from pnt.io import session
    from pnt.io.mcap_log import read_session

    meas = [r for _, r in read_session(session.mcap_path(path), topics=["/meas/"])]
    meas = sorted((m for m in meas if isinstance(m, Measurement)), key=lambda m: m.t_ns)
    return meas, session.read_meta(path).get("origin_llh")


def real(args) -> None:
    from pnt.integrity.whiteness import WhitenessParams

    d = WhitenessParams()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res, traces = {"commit": _commit(), "params": vars(d), "sessions": {}}, {}
    for arg in args.sessions:
        name, _, path = arg.rpartition("=")  # LABEL=path, or a path named by its folder
        name = name or Path(path).name
        meas, origin = _load(path)
        est, pairs = _recorded_run("ekf", meas, origin)
        epochs = np.array([e.t_ns for e in est], dtype=np.int64)
        rows = {}
        for src, (t, p, a2, b2) in pairs.items():
            r, T, n = window_stats(t, p, a2, b2, epochs, d.window_s)
            ok = n >= d.min_pairs
            raised = np.array([f"{ADVISORY}{src}" in e.flags for e in est])
            on = ok & (T > d.threshold)  # over the threshold: what a flag would show
            first = np.flatnonzero(on)
            rows[src] = {
                "pairs": len(t),
                "r_whole": float(p.sum() / math.sqrt(a2.sum() * b2.sum())),
                "T_whole": float(p.sum() / math.sqrt((p * p).sum())),
                "r_median": float(np.median(r[ok])) if ok.any() else None,
                "T_median": float(np.median(T[ok])) if ok.any() else None,
                "T_max": float(T[ok].max()) if ok.any() else None,
                "over_threshold": float(on.mean()),
                "raised": float(raised.mean()),  # 0 for GNSS position (analysis only)
                "onsets": _onsets(on),
                "first_over_s": (
                    float((epochs[first[0]] - epochs[0]) / 1e9) if len(first) else None
                ),
            }
            traces[(name, src)] = ((epochs - epochs[0]) / 1e9, np.where(ok, T, np.nan))
        hours = float((epochs[-1] - epochs[0]) / 3.6e12)
        res["sessions"][name] = {"hours": hours, "sources": rows}
    (out / "real.json").write_text(json.dumps(res, indent=1))
    _plot_real(traces, d.threshold, out / "real.png")
    print(json.dumps(res, indent=1))


def _plot_real(traces, thr: float, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = sorted({n for n, _ in traces})
    fig, axes = plt.subplots(len(names), 1, figsize=(10, 2.6 * len(names)), squeeze=False)
    for ax, name in zip(axes[:, 0], names, strict=True):
        for (n, src), (ts, T) in sorted(traces.items()):
            if n == name:
                ax.plot(ts, T, lw=0.8, label=src)
        ax.axhline(thr, color="k", ls="--", lw=1)
        ax.set_yscale("symlog", linthresh=10)
        ax.set_title(name, fontsize=9)
        ax.set_ylabel("T")
        ax.legend(fontsize=7, ncol=4)
    axes[-1, 0].set_xlabel("s from the first estimate")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


# --- hash ----------------------------------------------------------------------------------------
def _scalar(x):
    """A numpy scalar in an Estimate (as some estimators leave them) as its Python value."""
    if isinstance(x, np.generic):
        return x.item()
    raise NotImplementedError(type(x))


def _digest(estimates) -> tuple[str, str]:
    """(hash without this test's flags, hash of the flags removed)."""
    h, f = hashlib.sha256(), hashlib.sha256()
    for e in estimates:
        keep = [x for x in e.flags if not x.startswith(ADVISORY)]
        h.update(msgspec.json.encode(msgspec.structs.replace(e, flags=keep), enc_hook=_scalar))
        f.update(json.dumps([x for x in e.flags if x.startswith(ADVISORY)]).encode())
    return h.hexdigest(), f.hexdigest()


def _opt(on: bool) -> dict:
    """`nav.estimate`'s whiteness switch, passed only when asked (main's has none)."""
    return {"whiteness": True} if on else {}


def _hash_task(estimator: str, scenario: str, seed: int, on: bool) -> tuple[str, str, str]:
    from pnt.sim.scenario import generate, load

    spec = load(scenario)
    run = generate(spec, seed=seed)
    est = nav.estimate(
        estimator,
        run.measurements,
        origin_llh=spec.get("origin_llh"),
        reference=run.reference,
        **_opt(on),
    )
    return f"{estimator}|{scenario}|{seed}", *_digest(est)


def _hash_real(estimator: str, path: str, on: bool) -> tuple[str, str, str]:
    meas, origin = _load(path)
    est = nav.estimate(estimator, meas, origin, **_opt(on))
    return f"{estimator}|{Path(path).name}|real", *_digest(est)


def hashes(args) -> None:
    names = sorted(args.estimators or nav.ESTIMATORS)
    on = args.whiteness
    tasks = [(e, sc, s, on) for e in names for sc in args.scenarios for s in args.seeds]
    rows = experiments._map(_hash_task, tasks, args.jobs)
    real = [(e, p, on) for e in names for p in args.real]
    rows += experiments._map(_hash_real, real, args.jobs)
    Path(args.out).write_text(
        json.dumps(
            {"commit": _commit(), "whiteness": on, "hashes": {k: [h, f] for k, h, f in rows}},
            indent=0,
        )
    )
    print(f"{len(rows)} runs hashed -> {args.out}")


def compare(args) -> None:
    a, b = (json.loads(Path(p).read_text()) for p in (args.a, args.b))
    ha, hb = a["hashes"], b["hashes"]
    common = sorted(set(ha) & set(hb))
    same = [k for k in common if ha[k][0] == hb[k][0]]
    print(f"{a['commit']} vs {b['commit']}: {len(same)} of {len(common)} identical"
          f" (only in one: {len(set(ha) ^ set(hb))})")  # fmt: skip
    for k in common:
        if ha[k][0] != hb[k][0]:
            print("DIFFERS", k)


def timing(args) -> None:
    """Wall time of the eval path (`nav.estimate(name, ...)`, as `pnt eval` and the sweeps call
    it) on paired records; the minimum of `--repeat` runs per seed, summed over seeds."""
    import time

    from pnt.sim.scenario import generate, load

    out = {"commit": _commit(), "estimator": args.estimator, "seconds": {}}
    for scenario in args.scenarios:
        spec = load(scenario)
        total = 0.0
        for seed in args.seeds:
            meas = generate(spec, seed=seed).measurements
            best = math.inf
            for _ in range(args.repeat):
                t = time.perf_counter()
                list(nav.estimate(args.estimator, meas, origin_llh=spec.get("origin_llh")))
                best = min(best, time.perf_counter() - t)
            total += best
        out["seconds"][scenario] = total
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("study")
    s.add_argument("--jobs", type=int, default=3)
    s.add_argument("--out", default="analysis/results/whiteness-275")
    r = sub.add_parser("real")
    r.add_argument("sessions", nargs="+")
    r.add_argument("--out", default="analysis/results/whiteness-275")
    h = sub.add_parser("hash")
    h.add_argument("--out", required=True)
    h.add_argument("--scenarios", nargs="*", default=list(HASH_SCENARIOS))
    h.add_argument("--seeds", nargs="+", type=int, default=[0, 1])
    h.add_argument("--real", nargs="*", default=[])
    h.add_argument("--estimators", nargs="*", help="default: every registered one")
    h.add_argument("--jobs", type=int, default=3)
    h.add_argument("--whiteness", action="store_true", help="the panel's path (this branch only)")
    t = sub.add_parser("timing")
    t.add_argument("--out", required=True)
    t.add_argument("--estimator", default="ekf")
    t.add_argument("--scenarios", nargs="+", default=["challenge-drone-outage", "nominal"])
    t.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    t.add_argument("--repeat", type=int, default=3)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    args = ap.parse_args(argv)
    cmds = {"study": study, "real": real, "hash": hashes, "timing": timing, "compare": compare}
    cmds[args.cmd](args)


if __name__ == "__main__":
    main()
