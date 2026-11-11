"""LTE re-acquisition steps and doppler aliases on real static captures, against GPS truth.

    # 1. front end on a capture (at the commit under test), records kept in a pickle
    PYTHONPATH=<worktree>/src python reacq.py run <session>/sdr_a.cu8 <out>.pkl
    # 2. score records against the session's GPS (mean of its fixes; the receiver is static)
    python reacq.py score <session> <before>.pkl <after>.pkl --out summary.json
    # 3. the records as a replayable session beside the capture's GNSS, IMU and baro
    PYTHONPATH=<worktree>/src python reacq.py session <session> <out>.pkl <session>-lte

`run` also counts what started each new arc (the first-path move, a re-search near the
prediction, the periodic search, an unsized gap). `score` uses the double difference (DD) of
two cells at one 0.1 s epoch after removing each one's true range, which cancels our dongle
clock (as `real-lte-root-cause-20261111/root_cause.py`, whose definitions it repeats):

- re-find step: |DD change| when one cell of a pair starts a new arc and the other does not;
- coverage: share of epochs with two cells >= -8 dB whose DD is within 100 m;
- doppler alias: share of two-cell doppler differences (zero at rest) within 3 % of a whole
  100 Hz carrier alias (34.26 m/s at 875 MHz); 6 % if uniform.

Errors and residuals only: no position, range or bearing is printed or written.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import pickle
import sys

import numpy as np

FRAME_M = 2997924.58
ALIAS_MPS = 100.0 * 299792458.0 / 875e6
EPOCH_NS = 100_000_000
SNR_CUT_DB = -8.0
GOOD_M = 100.0


def run(capture: str, out: str) -> None:
    from pnt.frontends.lte import frontend, tracker

    events: list[tuple[str, int]] = []
    start0, process0 = frontend._start, frontend._process

    def _process(*a, **k):  # process_capture may run twice: keep the last run's events
        events.clear()
        return process0(*a, **k)

    def _start(key, f, fc, L, carry, seg, cfg):
        prev = carry.get(key)
        arc0 = prev[0].arc if prev is not None else None
        cell, st = start0(key, f, fc, L, carry, seg, cfg)
        if arc0 is not None and cell.arc != arc0:
            events.append(("search", f.pci))
        return cell, st

    class Track(tracker._Track):
        def run(self, cell, *a, **k):
            self._cell = cell
            return super().run(cell, *a, **k)

        def _relocate(self, cell, st, kk, good, last):
            r = super()._relocate(cell, st, kk, good, last)
            if r[0] == "found" and r[3]:
                events.append(("relocate", cell.pci))
            return r

        def _earlier_path(self, profs, win, noise, *a):
            s = super()._earlier_path(profs, win, noise, *a)
            if s:
                events.append(("first_path", self._cell.pci))
            return s

    frontend._start, frontend._process, frontend._Track = _start, _process, Track
    r = frontend.process_file(capture)
    print(frontend.summary(r, frontend.open_capture(capture)), flush=True)
    with open(out, "wb") as fh:
        pickle.dump(
            {
                "meas": r.measurements,
                "events": events,
                "gaps": [(g.at, g.n, g.ambiguous) for g in r.gaps],
            },
            fh,
        )


# --- scoring ---------------------------------------------------------------------------------
def truth_and_origin(session_dir: str):
    from pnt.io import session
    from pnt.io.mcap_log import read_session

    fixes = [
        r
        for _, r in read_session(session.mcap_path(session_dir), topics=["/meas/gnss"])
        if getattr(r, "kind", None) == "position_enu"
    ]
    return np.mean([f.value for f in fixes], axis=0), session.read_meta(session_dir)["origin_llh"]


def residuals(meas, truth, origin) -> dict:
    from pnt.core.frames import emitter_enu
    from pnt.nav import cells

    t0 = min(m.t_ns for m in meas)
    cols = collections.defaultdict(list)
    for m in cells.attach(sorted(meas, key=lambda m: m.t_ns), origin):
        pr = m.kind == "pseudorange"
        rng = float(np.linalg.norm(truth - emitter_enu(m.meta, origin)))
        cols["pci"].append(int(m.meta["pci"]))
        cols["epoch"].append((m.t_ns - t0) // EPOCH_NS)
        cols["pr"].append(pr)
        cols["snr"].append(float(m.meta.get("snr_db", -math.inf)))
        cols["arc"].append(int(m.meta.get("arc", -1)))
        cols["res"].append(m.value[0] - rng if pr else m.value[0])
        cols["sigma"].append(float(m.sigma[0]))
    return {k: np.array(v) for k, v in cols.items()}


def _pairs(r: dict, pr: bool):
    k = np.flatnonzero(r["pr"] == pr)
    at = {(r["pci"][i], r["epoch"][i]): i for i in k}
    by_cell = collections.defaultdict(set)
    for c, e in at:
        by_cell[c].add(e)
    for a, b in itertools.combinations(sorted(by_cell), 2):
        ep = sorted(by_cell[a] & by_cell[b])
        if ep:
            ia = np.array([at[(a, e)] for e in ep], dtype=int)
            ib = np.array([at[(b, e)] for e in ep], dtype=int)
            yield a, b, np.array(ep), ia, ib


def _dd(r, ia, ib):
    return (r["res"][ia] - r["res"][ib] + FRAME_M / 2) % FRAME_M - FRAME_M / 2


def steps(r: dict) -> dict:
    s, hi = [], []
    for _, _, ep, ia, ib in _pairs(r, True):
        dd = _dd(r, ia, ib)
        for j in range(1, len(ep)):
            if ep[j] - ep[j - 1] != 1:
                continue
            na = r["arc"][ia[j]] != r["arc"][ia[j - 1]]
            nb = r["arc"][ib[j]] != r["arc"][ib[j - 1]]
            if na != nb:
                s.append(abs(dd[j] - dd[j - 1]))
                hi.append(min(r["snr"][ia[j]], r["snr"][ib[j]]) >= SNR_CUT_DB)
    s, hi = np.array(s), np.array(hi, bool)
    out = {"n": int(s.size), "hi_n": int(hi.sum())}
    for name, x in (("", s), ("hi_", s[hi])):
        out[name + "median_m"] = float(np.median(x)) if x.size else math.nan
        out[name + "p90_m"] = float(np.percentile(x, 90)) if x.size else math.nan
        out[name + "over_100m"] = float(np.mean(x > GOOD_M)) if x.size else math.nan
    return out


def coverage(r: dict) -> dict:
    epochs = set(r["epoch"][r["pr"]].tolist())
    hi2, good, good_all = set(), set(), set()
    for _, _, ep, ia, ib in _pairs(r, True):
        hi = np.minimum(r["snr"][ia], r["snr"][ib]) >= SNR_CUT_DB
        ok = np.abs(_dd(r, ia, ib)) < GOOD_M
        hi2 |= set(ep[hi].tolist())
        good |= set(ep[hi & ok].tolist())
        good_all |= set(ep[ok].tolist())
    n = max(len(epochs), 1)
    return {
        "epochs": len(epochs),
        "two_strong": len(hi2) / n,
        "two_strong_within_100m": len(good) / n,
        "two_any_within_100m": len(good_all) / n,
    }


def pair_dd(r: dict) -> list[dict]:
    rows = []
    for a, b, _, ia, ib in _pairs(r, True):
        dd = _dd(r, ia, ib)
        hi = np.minimum(r["snr"][ia], r["snr"][ib]) >= SNR_CUT_DB
        rows.append(
            {
                "pair": f"{a}-{b}",
                "n": int(dd.size),
                "within_100m": float(np.mean(np.abs(dd) < GOOD_M)),
                "hi_n": int(hi.sum()),
                "hi_within_100m": float(np.mean(np.abs(dd[hi]) < GOOD_M))
                if hi.any()
                else math.nan,
                "hi_median_m": float(np.median(dd[hi])) if hi.any() else math.nan,
            }
        )
    return rows


def doppler(r: dict) -> dict:
    parts = [r["res"][ia] - r["res"][ib] for *_, ia, ib in _pairs(r, False)]
    told = r["sigma"][~r["pr"]]
    if not parts:
        return {"n_records": int((~r["pr"]).sum()), "n_pairs": 0}
    d = np.concatenate(parts)
    k = np.round(d / ALIAS_MPS)
    on = np.abs(d / ALIAS_MPS - k) < 0.03
    return {
        "n_records": int((~r["pr"]).sum()),
        "n_pairs": int(d.size),
        "on_alias": float(np.mean(on)),
        "on_nonzero_alias": float(np.mean(on & (k != 0))),
        "within_1mps": float(np.mean(np.abs(d) < 1)),
        "told_sigma_median_mps": float(np.median(told)),
        "robust_sigma_mps": float(1.4826 * np.median(np.abs(d - np.median(d)))),
    }


def score(session_dir: str, pkl: str) -> dict:
    with open(pkl, "rb") as fh:
        d = pickle.load(fh)
    truth, origin = truth_and_origin(session_dir)
    r = residuals([m for m in d["meas"] if m.source == "lte"], truth, origin)
    arcs = collections.Counter(c for c, _ in d["events"])
    return {
        "new_arcs_by_cause": dict(arcs),
        "steps": steps(r),
        "coverage": coverage(r),
        "doppler": doppler(r),
        "pairs": pair_dd(r),
        "n_pseudorange": int(r["pr"].sum()),
    }


def write(session_dir: str, pkl: str, out: str, commit: str) -> None:
    """The pickle's LTE records written as `pnt frontend lte` writes them (`write_session`)."""
    from pathlib import Path
    from types import SimpleNamespace

    from pnt.frontends.lte import frontend

    with open(pkl, "rb") as fh:
        d = pickle.load(fh)
    cap = SimpleNamespace(dongle="sdr_a", path=Path(session_dir) / "sdr_a.cu8")
    res = SimpleNamespace(measurements=d["meas"])
    frontend.write_session(res, cap, Path(out), commit, copy_from=Path(session_dir))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("run")
    a.add_argument("capture")
    a.add_argument("out")
    b = sub.add_parser("score")
    b.add_argument("session")
    b.add_argument("pkl", nargs="+")
    b.add_argument("--out")
    c = sub.add_parser("session")
    c.add_argument("session")
    c.add_argument("pkl")
    c.add_argument("out")
    c.add_argument("--commit", default="unknown")
    args = p.parse_args(argv)
    if args.cmd == "session":
        write(args.session, args.pkl, args.out, args.commit)
        return
    if args.cmd == "run":
        run(args.capture, args.out)
        return
    res = {pk: score(args.session, pk) for pk in args.pkl}
    txt = json.dumps(res, indent=1, default=float)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(txt)
    print(txt)


if __name__ == "__main__":
    sys.exit(main())
