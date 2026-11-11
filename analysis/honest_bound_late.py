"""Why `ekf-honest`'s typical run drifts further late in the outage (#226), sim.

On `challenge-drone-outage` (1 carrier) the across-run 95th percentile of `ekf-honest`'s error
stays at or under `ekf-learned-noise`'s for the whole 600 s outage, but its median at 600 s is
about twice as large (`summary.md`, *No harm over the whole outage*). This replays both filters
seed by seed and records what happens to each LTE range record (used, rejected by the gate, or
skipped by the curvature rule: `_pseudorange` drops a radio record whose second-order term
sigma_perp^4 / (2 r^2) exceeds its learned noise), with the horizontal NEES, HPL and error at
each second. The records are fed exactly as `pnt.nav.estimate` feeds them (`cells.attach`, the
estimator's receivers), so the error matches the `stress` plan's runs seed for seed.

Counterfactuals (`--skip`), experiments only and never an estimator: `off` keeps every record
(the curvature term still goes into R), `x4` skips only past four times the learned noise. They
replace one line of `_pseudorange` in this process; the registered estimators are unchanged.

    python analysis/honest_bound_late.py --seeds 0-199 --jobs 5
    # writes analysis/results/honest-bound/late-outage.md
"""

from __future__ import annotations

import argparse
import gzip
import inspect
import pickle
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from honest_bound import KIND, OUT, RUNS, _clean, parse_seeds  # noqa: E402

from pnt.cli import _commit  # noqa: E402
from pnt.nav import ESTIMATORS, cells, receivers  # noqa: E402
from pnt.nav import ekf as E  # noqa: E402
from pnt.sim.scenario import T0_NS, generate, load  # noqa: E402

SCENARIO = "challenge-drone-outage"
NAMES = {"ekf-learned-noise": {"noise_tau_s": E.NOISE_TAU_S}, "ekf-honest": dict(E.HONEST)}
SKIP_LINE = "if not (new or new_arc) and ekf._curvature > ekf.range_variance(m):"
SKIPS = {
    "as registered": None,
    "off": "if False:",
    "x4": "if not (new or new_arc) and ekf._curvature > 4 * ekf.range_variance(m):",
}
BINS_S = ((60, 160), (160, 260), (260, 360), (360, 460), (460, 560), (560, 660))


def _patch(skip: str) -> None:
    """Replace the curvature skip in this process (`SKIPS`); the registry entry is swapped."""
    line = SKIPS[skip]
    if line is None:
        return
    src = inspect.getsource(E._pseudorange)
    assert SKIP_LINE in src, "the curvature rule moved: update SKIP_LINE"
    ns = dict(vars(E))
    exec(src.replace(SKIP_LINE, line), ns)  # noqa: S102 - a one-line experiment, see docstring
    E.MODELS["pseudorange"] = ns["_pseudorange"]


def run_one(args: tuple[str, str, int]) -> dict:
    skip, name, seed = args
    _patch(skip)
    spec = load(SCENARIO)
    sim = generate(spec, seed=seed)
    f = E.EKF(origin_llh=spec.get("origin_llh"), **NAMES[name])
    seen: dict = {}
    update = f._update

    def watched(key, t_ns, y, H, R, gate=True):
        ok = update(key, t_ns, y, H, R, gate)
        seen["o"] = ("used" if ok else "rejected") if gate else "first"
        return ok

    f._update = watched
    truth = {g.t_ns: g for g in sim.truth}
    keep = receivers(ESTIMATORS[name])
    recs, per_s, nxt = [], [], None
    for m in cells.attach(sim.measurements, spec.get("origin_llh")):
        if m.receiver not in keep:
            continue
        if f.x is not None:
            nxt = nxt or (f.t_ns // 100_000_000 + 1) * 100_000_000
            while nxt <= m.t_ns:
                f.predict(nxt)
                if (nxt - T0_NS) % 1_000_000_000 == 0 and nxt in truth:
                    est = f.estimate()
                    d = np.subtract(est.pos_enu, truth[nxt].pos_enu)[:2]
                    c = np.reshape(est.pos_cov, (3, 3))[:2, :2]
                    per_s.append(((nxt - T0_NS) / 1e9, np.hypot(*d), d @ np.linalg.solve(c, d),
                                  est.hpl_m))  # fmt: skip
                nxt += 100_000_000
        lte = m.kind == "pseudorange" and m.source == "lte" and f.x is not None
        seen.clear()
        f.process(m)
        if lte:
            recs.append(((m.t_ns - T0_NS) / 1e9, seen.get("o", "skipped")))
    return {"skip": skip, "name": name, "seed": seed, "recs": recs, "per_s": np.array(per_s)}


def table(runs: list[dict]) -> list[str]:
    lines = [
        "| Curvature skip | Estimator | s after GPS loss | LTE records | used | rejected by the "
        "gate | skipped (curvature) | first of a cell or arc | NEES mean | HPL median (m) | "
        "error median (m) | error p95 (m) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for skip in SKIPS:
        for name in NAMES:
            rs = [r for r in runs if r["skip"] == skip and r["name"] == name]
            if not rs:
                continue
            for a, b in BINS_S:
                oc = [o for r in rs for t, o in r["recs"] if a <= t < b]
                s = np.concatenate([r["per_s"][(r["per_s"][:, 0] >= a) & (r["per_s"][:, 0] < b)]
                                    for r in rs])  # fmt: skip
                n = len(oc)
                lines.append(
                    f"| {skip} | `{name}` | {a - 60}–{b - 60} | {n:,} | "
                    f"{oc.count('used') / n:.1%} | {oc.count('rejected') / n:.1%} | "
                    f"{oc.count('skipped') / n:.1%} | {oc.count('first') / n:.1%} | "
                    f"{np.mean(s[:, 2]):.1f} | "
                    f"{np.median(s[:, 3]):,.0f} | {np.median(s[:, 1]):,.0f} | "
                    f"{np.percentile(s[:, 1], 95):,.0f} |"
                )
    lines += [
        "",
        "| Curvature skip | Estimator | above HPL, GPS loss to its end (per second) | worst run | "
        "p95 worst over the outage (m) | median at 600 s (m) |",
        "|---|---|---|---|---|---|",
    ]
    for skip in SKIPS:
        for name in NAMES:
            rs = [r for r in runs if r["skip"] == skip and r["name"] == name]
            if not rs:
                continue
            win = [r["per_s"][(r["per_s"][:, 0] >= 60) & (r["per_s"][:, 0] <= 660)] for r in rs]
            above = [np.mean(w[:, 1] > w[:, 3]) for w in win]
            e = np.array([w[:, 1] for w in win])
            pooled = np.mean(np.concatenate([w[:, 1] > w[:, 3] for w in win]))
            lines.append(
                f"| {skip} | `{name}` | {pooled:.2%} | {max(above):.1%} | "
                f"{np.percentile(e, 95, axis=0).max():,.0f} | "
                f"{np.median(e[:, -1]):,.0f} |"
            )
    return lines


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", default="0-199")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--host", default=platform.node().split(".")[0])
    args = ap.parse_args(argv)
    seeds = parse_seeds(args.seeds)
    commit = _commit()
    t0 = time.time()
    tasks = [(k, n, s) for k in SKIPS for n in NAMES for s in seeds]
    with ProcessPoolExecutor(args.jobs) as ex:
        runs = list(ex.map(run_one, tasks, chunksize=4))
    RUNS.mkdir(parents=True, exist_ok=True)
    with gzip.open(RUNS / "late-outage.pkl.gz", "wb") as fh:
        pickle.dump({"commit": commit, "seeds": seeds, "runs": runs}, fh)
    dirty = "" if _clean(commit) else " (DIRTY TREE)"
    head = [
        "# Late in the outage: what happens to each LTE record (#226)",
        "",
        f"**{KIND}.** `{SCENARIO}`, 1 carrier, seeds {seeds[0]}–{seeds[-1]}. "
        f"`python analysis/honest_bound_late.py --seeds {args.seeds} --jobs {args.jobs}` at "
        f"`{commit}`{dirty} on {args.host} (Python {platform.python_version()}), "
        f"{(time.time() - t0) / 60:.0f} min. Per-second samples; the counterfactual rows are "
        "experiments, not estimators (module docstring).",
        "",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "late-outage.md").write_text("\n".join(head + table(runs)) + "\n")
    print(f"wrote {OUT / 'late-outage.md'}")


if __name__ == "__main__":
    main()
