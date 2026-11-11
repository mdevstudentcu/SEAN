"""#147 on a real session: the told-sigma variants through #214's software GPS cut.

    python analysis/told_sigma_147_real.py <session>-lte --out <dir> [--cuts 100 150 200 250 300]

Runs `analysis/real_gps_cut.py` (#214: `run_one`, `hold_last_fix`; GNSS cut in software at
each cut time, scored against the withheld fixes; `--cut-script` for a copy elsewhere) for the
variants of `analysis/told_sigma_147.py`, each for `ekf` and `ekf-calibrated`: `default`, `A`
(#156's learned noise), `B` (ADR-0036's measured sigma), `B+A`, and `no LTE`; and each of the
first four with `arc_bias` (`arc`, `A+arc`, `B+arc`, `B+A+arc`: a new arc gets its own bias).
LTE records as the front end wrote them, pseudoranges only (#214's `told-pr`: ADR-0036 gives
the dopplers no sigma and #183 flags their carrier aliases); `told` (with dopplers) too with
`--with-doppler`.

A and B+A need #156's code in the `src/` under test. Writes `real.json` into `--out`: errors and
HPL bound rates only, never a position, origin, range or bearing (the session is at a private
site). Evidence: replay of a real static session with GPS cut in software (ADR-0015).
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from pnt import experiments
from pnt.nav import ESTIMATORS, configured, ekf

HERE = Path(__file__).resolve().parent
CUT_SCRIPT = HERE / "real_gps_cut.py"  # #214
FAMILIES = {"ekf": ekf.run, "ekf-calibrated": ekf.run_calibrated}
TAU = {"ekf": "NOISE_TAU_S", "ekf-calibrated": "CALIBRATED_NOISE_TAU_S"}


def _register() -> dict[str, tuple[str, str]]:
    """Registry names for every (family, variant) this `src/` can run; B+A and the `+arc`
    variants are registered here, on import, so worker processes have them too."""
    names = {}
    learn_ok = "noise_tau_s" in inspect.signature(ekf.EKF).parameters
    arc_ok = "arc_bias" in inspect.signature(ekf.EKF).parameters
    for fam, fn in FAMILIES.items():
        tau = getattr(ekf, TAU[fam], None)
        cfgs = {"default": {}, "B": {"told_sigma_model": "adr0036"}}
        if learn_ok:
            cfgs["A"] = {"noise_tau_s": tau}
            cfgs["B+A"] = {"told_sigma_model": "adr0036", "noise_tau_s": tau}
        if arc_ok:
            cfgs |= {f"{k}+arc" if k != "default" else "arc": v | {"arc_bias": True}
                     for k, v in list(cfgs.items())}  # fmt: skip
        for variant, cfg in cfgs.items():
            name = f"147:{fam}:{variant}"
            ESTIMATORS[name] = configured(fn, **cfg)
            names[name] = (fam, variant)
    return names


NAMES = _register()


CUT = {"script": HERE / "real_gps_cut.py"}  # #214; --cut-script to use another copy


def _cut_module():
    """#214's script as a module, loaded once per process (its session cache with it)."""
    if "mod" not in CUT or CUT["mod"].__file__ != str(CUT["script"]):
        spec = importlib.util.spec_from_file_location("real_gps_cut", CUT["script"])
        CUT["mod"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(CUT["mod"])
    return CUT["mod"]


def run_one(script: str, path: str, estimator: str, lte: str, cut_s: float) -> dict:
    CUT["script"] = Path(script)
    out = _cut_module().run_one(path, estimator, lte, cut_s)
    fam, fix = NAMES[estimator]
    keep = ("n_fixes", "p95_120s_m", "p95_300s_m", "err_60s_m", "err_300s_m", "max_m",
            "hpl_bound", "misleading", "pre_p95_m", "pre_gnss_excluded", "n_lte")  # fmt: skip
    return {"family": fam, "fix": "no LTE" if lte == "none" else fix, "lte": lte,
            "cut_s": cut_s} | {k: out[k] for k in keep}  # fmt: skip


def _med(v):
    v = [x for x in v if x == x]
    return float(np.median(v)) if v else math.nan


def aggregate(rows: list[dict]) -> list[dict]:
    """Per (family, fix, LTE records): over the cuts, the median and worst of each error, the
    HPL bound rate pooled over every withheld fix, and the misleading fixes."""
    out = []
    for key in dict.fromkeys((r["family"], r["fix"], r["lte"]) for r in rows):
        rs = [r for r in rows if (r["family"], r["fix"], r["lte"]) == key]
        n = sum(r["n_fixes"] for r in rs)
        s = {"family": key[0], "fix": key[1], "lte": key[2], "cuts": len(rs), "fixes": n}
        for f in ("p95_120s_m", "p95_300s_m", "err_60s_m", "err_300s_m", "max_m"):
            s[f + "_median"] = _med([r[f] for r in rs])
            s[f + "_worst"] = float(np.nanmax([r[f] for r in rs]))
        pre = [r.get("pre_gnss_excluded", math.nan) for r in rs]
        s["pre_gnss_excluded_mean"] = float(np.nanmean(pre)) if any(x == x for x in pre) else None
        if rs[0]["hpl_bound"] == rs[0]["hpl_bound"]:
            s["hpl_bound"] = sum(r["hpl_bound"] * r["n_fixes"] for r in rs) / n
            s["misleading"] = int(sum(r["misleading"] for r in rs))
        out.append(s)
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--cuts", type=float, nargs="+", default=[100, 150, 200, 250, 300])
    ap.add_argument("--with-doppler", action="store_true")
    ap.add_argument("--cut-script", type=Path, default=CUT["script"])
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    CUT["script"] = a.cut_script.resolve()
    cut = _cut_module()
    ltes = ["told-pr", "told"] if a.with_doppler else ["told-pr"]
    s = str(CUT["script"])
    tasks = [(s, a.session, n, lte, c) for n in NAMES for lte in ltes for c in a.cuts]
    tasks += [(s, a.session, f"147:{f}:default", "none", c) for f in FAMILIES for c in a.cuts]
    rows = experiments._map(run_one, tasks, a.jobs)
    meas, t0, _ = cut.load(a.session)
    fix_t, fix_pos = cut.gps_fixes(meas)
    for c in a.cuts:
        h = cut.hold_last_fix(fix_t, fix_pos, t0 + round(c * 1e9))
        rows.append({"family": "hold", "fix": "last fix", "lte": "-", "cut_s": c,
                     "n_fixes": h["n_fixes"], "hpl_bound": math.nan}
                    | {k: h[k] for k in ("p95_120s_m", "p95_300s_m", "err_60s_m",
                                         "err_300s_m", "max_m")})  # fmt: skip
    import pnt

    src = Path(pnt.__file__).resolve().parents[1]
    src_commit = subprocess.run(["git", "-C", str(src), "describe", "--always", "--dirty"],
                                capture_output=True, text=True).stdout.strip()  # fmt: skip
    meta = {"session": Path(a.session).name, "cut_script": cut._commit(), "cuts_s": a.cuts,
            "src_commit": src_commit,
            "kind": "replay of a real static session, GPS cut in software"}  # fmt: skip
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "real.json").write_text(json.dumps({"meta": meta, "aggregate": aggregate(rows),
                                                 "runs": rows}, indent=1))  # fmt: skip
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
