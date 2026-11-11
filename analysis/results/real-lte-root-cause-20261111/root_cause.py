"""#214: why LTE pulls the filter kilometres away after a GPS cut on the real static sessions.

    python analysis/results/real-lte-root-cause-20261111/root_cause.py \
        <0151>-lte <0233>-lte --out analysis/results/real-lte-root-cause-20261111 [--jobs 3]

Each `<session>-lte` is a real static session after `pnt frontend lte` with #183's front end.
Run on the local integration branch `tmp/e2e-combined` (origin/main + #214 + #183 + #147 + #228, as
`../real-gps-cut-combined-20261111/run_combined.py`): it needs #183's record fields and #147's
`told_sigma_model`. Nothing under `src/` is changed; every fix tried is opt-in, here only.

Truth is the mean of the session's GPS fixes (the receiver does not move). Four parts:

1. Truth residuals. Each pseudorange minus the true range to its matched site (`pnt.nav.cells`,
   as the filter sees it). Our dongle clock is in every record of an epoch, so it cancels in the
   difference of two cells at the same 0.1 s epoch: the double difference (DD) is the pair's
   error after truth, zero if both sites are right, both towers are frame-aligned and both
   tracks are locked. Dopplers likewise: two cells' range rates differ by zero at rest.
2. The GNSS exclusion before the cut: the default `ekf` with pseudoranges only, instrumented.
3. After the cut: `B` (ADR-0036 told sigma, #147) with pseudoranges only, instrumented: which
   cell's updates move the position, and which cells the gate has locked out.
4. Opt-in fixes, scored after the cut as `analysis/real_gps_cut.py` does.

Writes summary.json, summary.md and root_cause.png into `--out`. Errors and residuals only: no
position, origin, range or bearing (the sessions are at a private site). Tower IDs are given.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import itertools
import json
import math
import subprocess
from pathlib import Path

import msgspec
import numpy as np

from pnt import experiments, nav
from pnt.core.frames import emitter_enu
from pnt.nav import cells, ekf, told_sigma

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FRAME_M = 2997924.58  # one 10 ms LTE frame: pseudoranges are known modulo this
ALIAS_MPS = 100.0 * 299792458.0 / 875e6  # a 100 Hz carrier alias at 875 MHz, in m/s
EPOCH_NS = 100_000_000  # the front end's 10 Hz records
SNR_CUT_DB = -8.0  # ADR-0036's fit range (TBC)
GOOD_M = 100.0  # TBC: a DD within this of zero counts as agreeing with truth


def _cut_module():
    spec = importlib.util.spec_from_file_location(
        "real_gps_cut", REPO / "analysis/real_gps_cut.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CUT = _cut_module()


# --- 1. truth residuals ------------------------------------------------------------------------
def residuals(path: str) -> dict:
    """Per LTE record: cell (PCI), site (eNB), 0.1 s epoch, kind, SNR, arc, and the residual: for
    a pseudorange, value minus the true range (our clock still in it); for a doppler, its value
    (the true range rate is zero at rest). Kept in memory, never written."""
    meas, t0, origin = CUT.load(path)
    _, fix_pos = CUT.gps_fixes(meas)
    truth = fix_pos.mean(axis=0)
    cols = collections.defaultdict(list)
    for m in cells.attach(meas, origin):
        if m.source != "lte":
            continue
        rng = float(np.linalg.norm(truth - emitter_enu(m.meta, origin)))
        pr = m.kind == "pseudorange"
        cols["pci"].append(int(m.meta["pci"]))
        cols["site"].append(m.meta["site"])
        cols["epoch"].append((m.t_ns - t0) // EPOCH_NS)
        cols["pr"].append(pr)
        cols["snr"].append(float(m.meta.get("snr_db", -math.inf)))
        cols["arc"].append(int(m.meta.get("arc", -1)))
        cols["res"].append(m.value[0] - rng if pr else m.value[0])
        cols["sigma"].append(float(m.sigma[0]))
    return {k: np.array(v) for k, v in cols.items()}


def _pairs(r: dict, pr: bool):
    """(cell a, cell b, epochs, a's index, b's index) for every pair of cells with records of the
    kind at the same epoch."""
    k = np.flatnonzero(r["pr"] == pr)
    at = {(r["pci"][i], r["epoch"][i]): i for i in k}
    by_cell = collections.defaultdict(set)
    for c, e in at:
        by_cell[c].add(e)
    for a, b in itertools.combinations(sorted(by_cell), 2):
        ep = sorted(by_cell[a] & by_cell[b])
        ia = np.array([at[(a, e)] for e in ep], dtype=int)
        ib = np.array([at[(b, e)] for e in ep], dtype=int)
        yield a, b, np.array(ep), ia, ib


def _dd(r, ia, ib):
    return (r["res"][ia] - r["res"][ib] + FRAME_M / 2) % FRAME_M - FRAME_M / 2


def _robust(x: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else math.nan


def pair_table(r: dict) -> list[dict]:
    """Per pair of cells: the DD over all common epochs, over those with both at or above the
    SNR cut, and over each cell's first arc (the cleanest stretch: before any re-acquisition)."""
    rows = []
    for a, b, _, ia, ib in _pairs(r, True):
        dd = _dd(r, ia, ib)
        hi = np.minimum(r["snr"][ia], r["snr"][ib]) >= SNR_CUT_DB
        first = (r["arc"][ia] == 0) & (r["arc"][ib] == 0)
        rows.append(
            {
                "pair": f"{a} − {b}",
                "sites": f"{r['site'][ia[0]]} − {r['site'][ib[0]]}",
                "n": int(len(dd)),
                "all_median_m": float(np.median(dd)),
                "all_within_m": float(np.mean(np.abs(dd) < GOOD_M)),
                "hi_n": int(hi.sum()),
                "hi_median_m": float(np.median(dd[hi])) if hi.any() else math.nan,
                "hi_robust_sigma_m": _robust(dd[hi]),
                "hi_within_m": float(np.mean(np.abs(dd[hi]) < GOOD_M)) if hi.any() else math.nan,
                "first_arc_n": int(first.sum()),
                "first_arc_median_m": float(np.median(dd[first])) if first.any() else math.nan,
                "first_arc_span_m": float(np.ptp(dd[first])) if first.any() else math.nan,
                "told_sigma_hi_median_m": float(
                    np.median(np.hypot(r["sigma"][ia][hi], r["sigma"][ib][hi]))
                )
                if hi.any()
                else math.nan,
            }
        )
    return rows


def coverage(r: dict) -> dict:
    """Share of 0.1 s epochs with a pseudorange where at least two cells are at or above the cut,
    and where at least one such pair also agrees with truth (DD within GOOD_M)."""
    k = r["pr"]
    epochs = set(r["epoch"][k].tolist())
    hi2, good = set(), set()
    for _, _, ep, ia, ib in _pairs(r, True):
        hi = np.minimum(r["snr"][ia], r["snr"][ib]) >= SNR_CUT_DB
        hi2 |= set(ep[hi].tolist())
        good |= set(ep[hi & (np.abs(_dd(r, ia, ib)) < GOOD_M)].tolist())
    return {
        "epochs": len(epochs),
        "two_cells_above_cut": len(hi2) / len(epochs),
        "two_cells_above_cut_and_agreeing": len(good) / len(epochs),
    }


def doppler_alias(r: dict) -> dict:
    """Two cells' dopplers at one epoch differ by zero at rest (both carry our dongle's drift; the
    towers' own drifts are ppb). Here: how the differences fall on whole 100 Hz carrier aliases."""
    d = np.concatenate([r["res"][ia] - r["res"][ib] for *_, ia, ib in _pairs(r, False)])
    k = np.round(d / ALIAS_MPS)
    on = np.abs(d / ALIAS_MPS - k) < 0.03
    told = r["sigma"][~r["pr"]]
    return {
        "n": int(len(d)),
        "alias_mps": ALIAS_MPS,
        "on_an_alias": float(np.mean(on)),
        "on_an_alias_if_uniform": 0.06,
        "k0_within_1mps": float(np.mean(np.abs(d) < 1.0)),
        "k_nonzero_on_alias": float(np.mean(on & (k != 0))),
        "k_counts": {
            int(a): int(b) for a, b in zip(*np.unique(k[on], return_counts=True), strict=True)
        },
        "told_sigma_median_mps": float(np.median(told)),
        "robust_sigma_mps": _robust(d),
    }


def arc_dd_steps(r: dict) -> dict:
    """At an epoch where a cell starts a new arc and its partner does not, how far the pair's DD
    moves from the epoch before (both records present): the cell's own step, our clock
    cancelled."""
    steps, hi = [], []
    for _, _, ep, ia, ib in _pairs(r, True):
        dd = _dd(r, ia, ib)
        for j in range(1, len(ep)):
            if ep[j] - ep[j - 1] != 1:
                continue
            na = r["arc"][ia[j]] != r["arc"][ia[j - 1]]
            nb = r["arc"][ib[j]] != r["arc"][ib[j - 1]]
            if na != nb:
                steps.append(abs(dd[j] - dd[j - 1]))
                hi.append(min(r["snr"][ia[j]], r["snr"][ib[j]]) >= SNR_CUT_DB)
    s, hi = np.array(steps), np.array(hi, bool)
    out = {"n": int(len(s)), "over_100m": float(np.mean(s > 100)) if len(s) else math.nan}
    out["median_m"] = float(np.median(s)) if len(s) else math.nan
    out["hi_n"] = int(hi.sum())
    out["hi_median_m"] = float(np.median(s[hi])) if hi.any() else math.nan
    return out


# --- 2, 3. instrumented replays ----------------------------------------------------------------
class Probe:
    """Records every update the EKF makes: time, emitter, kind, NIS, used, the horizontal
    position change it made (K y), the told sigma and the horizontal position sigma before it."""

    def __init__(self):
        self.log: list[tuple] = []
        self.m = None
        self._update, self._process = ekf.EKF._update, ekf.EKF.process
        probe = self

        def update(self, key, t_ns, y, H, R, gate=True):
            S = np.atleast_2d(H @ self.P @ H.T + R)
            S_inv = np.linalg.inv(S)
            kick = (self.P @ H.T @ S_inv @ np.atleast_1d(y))[:2]
            ph = float(np.sqrt(self.P[0, 0] + self.P[1, 1]))
            used = probe._update(self, key, t_ns, y, H, R, gate)
            m = probe.m
            nis = float(np.atleast_1d(y) @ S_inv @ np.atleast_1d(y))
            probe.log.append(
                (
                    t_ns,
                    m.emitter or m.source,
                    m.kind,
                    nis,
                    used,
                    *(kick if used else (0, 0)),
                    float(np.sqrt(R[0, 0])),
                    ph,
                    float(m.meta.get("snr_db", math.nan)),
                )
            )
            return used

        def process(self, m):
            probe.m = m
            return probe._process(self, m)

        self.patched = (update, process)

    def run(self, path: str, cfg: dict, lte: str, cut_s: float):
        meas, t0, origin = CUT.load(path)
        fed = CUT.lte_variant(CUT.cut_gnss(meas, t0, cut_s), lte)
        self.log = []
        ekf.EKF._update, ekf.EKF.process = self.patched
        try:
            est = list(nav.estimate(nav.configured(ekf.run, **cfg), fed, origin_llh=origin))
        finally:
            ekf.EKF._update, ekf.EKF.process = self._update, self._process
        return t0, est, self.log


def exclusion(path: str) -> dict:
    """Default `ekf`, pseudoranges only (cut at 300 s): when GNSS is first rejected and what
    moved the position before it."""
    t0, est, log = Probe().run(path, {}, "told-pr", 300.0)
    settled = [e for e in est if 30e9 <= e.t_ns - t0 < 300e9]
    first = next((r for r in log if r[2] == "position_enu" and not r[4]), None)
    out = {"pre_gnss_excluded": float(np.mean(["gnss_excluded" in e.flags for e in settled]))}
    if first is None:
        return out
    before = [r for r in log if r[0] < first[0] and r[2] == "pseudorange"]
    kick = collections.defaultdict(lambda: np.zeros(2))
    for r in before:
        kick[r[1]] += r[5:7]
    gnss = [r for r in log if r[2] == "position_enu" and r[0] >= first[0] and r[0] < t0 + 300e9]
    out.update(
        {
            "first_rejected_s": (first[0] - t0) / 1e9,
            "first_rejected_nis": first[3],
            "gnss_told_sigma_m": first[7],
            "position_sigma_m": first[8],
            "gnss_used_before": sum(
                r[4] for r in log if r[2] == "position_enu" and r[0] < first[0]
            ),
            "gnss_used_after_until_cut": int(sum(r[4] for r in gnss)),
            "gnss_rejected_after_until_cut": int(sum(not r[4] for r in gnss)),
            "lte_kick_before_m": {e: float(np.hypot(*v)) for e, v in kick.items()},
            "lte_told_sigma_before_m": {
                e: float(np.median([r[7] for r in before if r[1] == e])) for e in kick
            },
            "lte_snr_before_db": {
                e: float(np.median([r[9] for r in before if r[1] == e])) for e in kick
            },
        }
    )
    return out


def after_cut(path: str, cut_s: float) -> dict:
    """`B`, pseudoranges only: per cell, how often the gate let it in before and after the cut,
    when it was last used before the cut, and how far its updates moved the position in the 300 s
    after (net and summed)."""
    t0, est, log = Probe().run(path, {"told_sigma_model": "adr0036"}, "told-pr", cut_s)
    cut = t0 + round(cut_s * 1e9)
    out = {}
    for e in sorted({r[1] for r in log if r[2] == "pseudorange"}):
        rs = [r for r in log if r[1] == e and r[2] == "pseudorange"]
        pre = [r for r in rs if r[0] < cut]
        post = [r for r in rs if cut <= r[0] < cut + 300e9]
        used_pre = [r[0] for r in pre if r[4]]
        net = np.sum([r[5:7] for r in post], axis=0) if post else np.zeros(2)
        out[e] = {
            "used_before": f"{len(used_pre)} / {len(pre)}",
            "last_used_before_cut_s": (max(used_pre) - t0) / 1e9 if used_pre else math.nan,
            "used_after": f"{sum(r[4] for r in post)} / {len(post)}",
            "net_kick_after_m": float(np.hypot(*net)),
            "summed_kick_after_m": float(sum(np.hypot(r[5], r[6]) for r in post)),
        }
    return out


# --- 4. opt-in fixes ---------------------------------------------------------------------------
B = {"told_sigma_model": "adr0036"}
VARIANTS = {  # name -> (EKF config, record options); pseudoranges only unless `lte` says
    "no LTE": ({}, {"lte": "none"}),
    "B": (B, {}),
    "B, ≥ −8 dB only": (B, {"snr_min": SNR_CUT_DB}),
    "B, 1 Hz": (B, {"hz": 1}),
    "B, truth-good cells": (B, {"good": True}),
    "B, arc bias": ({**B, "arc_bias": True}, {}),
    "B, tower clock q 0.02": ({**B, "q_emitter": 0.02}, {}),
    "B, tower clock q 2": ({**B, "q_emitter": 2.0}, {}),
    "B, tower clock q 20": ({**B, "q_emitter": 20.0}, {}),
    "B, dongle wander 5": ({**B, "rx_clock_wander": 5.0}, {}),
    "B, pairs ≥ −8 dB only": (B, {"pairs": True}),
    "B, told σ × 10": ({}, {"sigma_x": 10.0}),
    "B, all four": ({**B, "arc_bias": True}, {"snr_min": SNR_CUT_DB, "hz": 1, "good": True}),
    "B, q_accel 0.1 (static prior)": ({**B, "q_accel": 0.1}, {}),
}
NOTES = {
    "B, truth-good cells": "uses truth: only cells whose DD agrees with truth (diagnostic)",
    "B, all four": "≥ −8 dB, 1 Hz, truth-good cells and arc bias together",
    "B, told σ × 10": "ADR-0036's σ times 10, told to the default EKF",
    "B, pairs ≥ −8 dB only": "a record kept only if another cell is ≥ −8 dB at that epoch",
    "B, q_accel 0.1 (static prior)": "a near-static motion prior: not a fix for a drone",
}


def good_cells(r: dict, min_epochs: int = 20) -> list[int]:
    """Cells with at least one partner whose DD at or above the cut has a median within GOOD_M
    of zero over at least `min_epochs` epochs: the table match and the track agree with truth."""
    ok = set()
    for row in pair_table(r):
        if row["hi_n"] >= min_epochs and abs(row["hi_median_m"]) < GOOD_M:
            ok |= {int(c) for c in row["pair"].split(" − ")}
    return sorted(ok)


def _feed(meas, opts: dict, good: list[int] | None):
    if opts.get("pairs"):
        hi = collections.Counter(
            m.t_ns // EPOCH_NS
            for m in meas
            if m.source == "lte" and m.kind == "pseudorange" and m.meta["snr_db"] >= SNR_CUT_DB
        )
    last: dict[str, int] = {}
    for m in meas:
        if m.source == "lte":
            snr = float(m.meta.get("snr_db", -math.inf))
            if opts.get("good") and m.meta.get("pci") not in good:
                continue
            if snr < opts.get("snr_min", -math.inf):
                continue
            if opts.get("pairs") and (snr < SNR_CUT_DB or hi[m.t_ns // EPOCH_NS] < 2):
                continue
            if opts.get("hz"):
                sec = m.t_ns // round(1e9 / opts["hz"])
                if last.get(m.emitter) == sec:
                    continue
                last[m.emitter] = sec
            if opts.get("sigma_x") and m.kind == "pseudorange":
                s = told_sigma.sigma_m(snr, int(m.meta["n_epochs"])) * opts["sigma_x"]
                m = msgspec.structs.replace(m, sigma=(s,))
        yield m


def run_variant(path: str, name: str, cut_s: float, good: list[int]) -> dict:
    cfg, opts = VARIANTS[name]
    meas, t0, origin = CUT.load(path)
    fix_t, fix_pos = CUT.gps_fixes(meas)
    cut_ns = t0 + round(cut_s * 1e9)
    fed = list(
        _feed(
            CUT.lte_variant(CUT.cut_gnss(meas, t0, cut_s), opts.get("lte", "told-pr")), opts, good
        )
    )
    est = list(nav.estimate(nav.configured(ekf.run, **cfg), fed, origin_llh=origin))
    et = np.array([e.t_ns for e in est], dtype=np.int64)
    pos = np.array([e.pos_enu for e in est], dtype=float)
    hpl = np.array([e.hpl_m for e in est], dtype=float)
    out = {"variant": name, "cut_s": cut_s}
    out.update(CUT.score_cut(et, pos, hpl, fix_t, fix_pos, cut_ns))
    settled = [e for e in est if t0 + 30e9 <= e.t_ns < cut_ns]
    out["pre_gnss_excluded"] = float(np.mean(["gnss_excluded" in e.flags for e in settled]))
    return out


def cuts_for(duration_s: float) -> list[float]:
    """#214's cuts on the 600 s session; every 600 s from 600 s on the hour (5 of the combined
    run's 11, to keep the grid inside the run budget)."""
    if duration_s < 1000:
        return [100.0, 150.0, 200.0, 250.0, 300.0]
    return [float(c) for c in range(600, int(duration_s - 300) + 1, 600)]


def grid(path: str, cuts: list[float], good: list[int], jobs: int) -> tuple[dict, list[dict]]:
    tasks = [(path, n, c, good) for n in VARIANTS for c in cuts]
    rows = experiments._map(run_variant, tasks, jobs)
    agg = {}
    for n in VARIANTS:
        rs = [r for r in rows if r["variant"] == n]
        a = {}
        for t in (60, 120, 300):
            v = np.array([r[f"err_{t}s_m"] for r in rs], float)
            a[f"err_{t}s_m"] = {"median": float(np.nanmedian(v)), "worst": float(np.nanmax(v))}
        err = np.concatenate([r["err_m"] for r in rs])
        hpl = np.concatenate([r["hpl_m"] for r in rs])
        a["hpl_bound"] = float(np.mean(hpl >= err))
        a["pre_gnss_excluded"] = float(np.mean([r["pre_gnss_excluded"] for r in rs]))
        a["within_50m_at_300s"] = f"{sum(r['err_300s_m'] <= 50 for r in rs)} / {len(rs)}"
        agg[n] = a
    return agg, rows


# --- report ------------------------------------------------------------------------------------
def _f(x: float) -> str:
    if x != x:
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


def markdown(summary: dict) -> str:
    L = [
        "# Why LTE pulls the real static sessions kilometres away after a GPS cut (#214)",
        "",
        "Evidence: **replay of real static sessions** (ADR-0015), GPS cut in software. Code: the "
        f"local integration branch `tmp/e2e-combined` at `{summary['commit']}` (origin/main "
        "c21e047 + #214 8e7a216 + #183 0ebe18a + #147 e39742f + #228 85d1324, never pushed); "
        "driver `root_cause.py` here. #183's front end on each capture. Truth: the mean of the "
        "session's GPS fixes. Errors and residuals only; tower IDs are the table's eNBs.",
        "",
    ]
    for s in summary["sessions"]:
        c, d, st = s["coverage"], s["doppler"], s["arc_dd_steps"]
        L += [
            f"## {s['session']}",
            "",
            "### 1. Pseudoranges against truth: double differences (our clock cancelled)",
            "",
            f"Epochs with a pseudorange: {c['epochs']:,}. Two cells ≥ −8 dB at once: "
            f"{c['two_cells_above_cut']:.0%}; and agreeing with truth within {GOOD_M:g} m: "
            f"{c['two_cells_above_cut_and_agreeing']:.0%}.",
            "",
            "| Pair (PCI) | eNBs | Common epochs | DD median, all (m) | All within 100 m | "
            "Both ≥ −8 dB | DD median ≥ −8 (m) | Robust σ ≥ −8 (m) | Within 100 m ≥ −8 | "
            "Told σ of the DD ≥ −8 (m) | First arcs: epochs | First arcs: median (m) | "
            "First arcs: span (m) |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for p in s["pairs"]:
            L.append(
                f"| {p['pair']} | {p['sites'].replace('enb:', '')} | {p['n']:,} | "
                f"{_f(p['all_median_m'])} | {p['all_within_m']:.0%} | {p['hi_n']:,} | "
                f"{_f(p['hi_median_m'])} | {_f(p['hi_robust_sigma_m'])} | "
                + (f"{p['hi_within_m']:.0%}" if p["hi_n"] else "—")
                + f" | {_f(p['told_sigma_hi_median_m'])} | {p['first_arc_n']} | "
                f"{_f(p['first_arc_median_m'])} | {_f(p['first_arc_span_m'])} |"
            )
        L += [
            "",
            f"Truth-good cells (a partner's DD median ≥ −8 dB within {GOOD_M:g} m over ≥ 20 "
            f"epochs): PCI {', '.join(map(str, s['good_cells']))}.",
            "",
            f"Steps at a new arc, one cell of a pair re-acquired, our clock cancelled: {st['n']} "
            f"steps, median {_f(st['median_m'])} m, {st['over_100m']:.0%} over 100 m; "
            f"{st['hi_n']} with both ≥ −8 dB, median {_f(st['hi_median_m'])} m.",
            "",
            f"Dopplers: of {d['n']:,} two-cell differences at one epoch (zero at rest), "
            f"{d['on_an_alias']:.0%} fall within 3 % of a whole 100 Hz alias "
            f"({d['alias_mps']:.2f} m/s; 6 % if uniform); {d['k_nonzero_on_alias']:.0%} on a "
            f"non-zero one; {d['k0_within_1mps']:.0%} within 1 m/s of zero. Told σ median "
            f"{d['told_sigma_median_mps']:.2f} m/s; the differences' robust σ "
            f"{d['robust_sigma_mps']:.0f} m/s.",
            "",
        ]
        x = s["exclusion"]
        L += ["### 2. Default `ekf`, pseudoranges only: GNSS exclusion before the cut", ""]
        if "first_rejected_s" in x:
            kicks = ", ".join(
                f"{e} {_f(v)} m (told σ {_f(x['lte_told_sigma_before_m'][e])} m, SNR "
                f"{x['lte_snr_before_db'][e]:.1f} dB)"
                for e, v in x["lte_kick_before_m"].items()
            )
            L += [
                f"GNSS excluded on {x['pre_gnss_excluded']:.0%} of the settled epochs. First "
                f"GNSS fix rejected at {x['first_rejected_s']:.1f} s (NIS "
                f"{x['first_rejected_nis']:.1f} against 16.3, the 99.9 % gate for 3 dof; told σ "
                f"{x['gnss_told_sigma_m']:.1f} m, filter σ {x['position_sigma_m']:.1f} m), after "
                f"{x['gnss_used_before']} fixes were used. Until the cut: "
                f"{x['gnss_used_after_until_cut']} fixes used, "
                f"{x['gnss_rejected_after_until_cut']} rejected. Position moved by LTE before "
                f"the first rejection: {kicks}.",
                "",
            ]
        else:
            L += [f"GNSS excluded on {x['pre_gnss_excluded']:.0%}; never rejected.", ""]
        a = s["after_cut"]
        L += [
            f"### 3. `B`, pseudoranges only, cut at {s['after_cut_s']:g} s: per cell",
            "",
            "| Cell | Used before the cut | Last used before the cut (s) | Used in the 300 s "
            "after | Net position change after (m) | Summed |change| after (m) |",
            "|---|---|---|---|---|---|",
        ]
        for e, v in a.items():
            L.append(
                f"| {e} | {v['used_before']} | {_f(v['last_used_before_cut_s'])} | "
                f"{v['used_after']} | {_f(v['net_kick_after_m'])} | "
                f"{_f(v['summed_kick_after_m'])} |"
            )
        L += [
            "",
            f"### 4. Opt-in fixes: error after the cut, {len(s['cuts_s'])} cuts at "
            f"{', '.join(f'{c:g}' for c in s['cuts_s'])} s, median (worst) in m",
            "",
            "| Variant | 60 s | 120 s | 300 s | ≤ 50 m at 300 s | HPL ≥ error | "
            "GNSS excluded before the cut | Note |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for n, g in s["grid"].items():
            cellz = " | ".join(
                f"{_f(g[f'err_{t}s_m']['median'])} ({_f(g[f'err_{t}s_m']['worst'])})"
                for t in (60, 120, 300)
            )
            L.append(
                f"| {n} | {cellz} | {g['within_50m_at_300s']} | {g['hpl_bound']:.0%} | "
                f"{g['pre_gnss_excluded']:.0%} | {NOTES.get(n, '')} |"
            )
        L.append("")
    L += summary.get("notes", [])
    return "\n".join(L) + "\n"


def plot(sessions: list[dict], res: dict, rows: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(17, 4.8))
    # (a) one pair's DD over the first minute of the 600 s session
    s0 = sessions[0]
    r = res[s0["session"]]
    pair = next(
        ((a, b, ep, ia, ib) for a, b, ep, ia, ib in _pairs(r, True) if (a, b) == (92, 268)), None
    )
    if pair is not None:
        a, b, ep, ia, ib = pair
        dd = _dd(r, ia, ib)
        t = ep / 10.0
        w = t <= 60
        hi = (np.minimum(r["snr"][ia], r["snr"][ib]) >= SNR_CUT_DB) & w
        ax[0].scatter(t[w & ~hi], dd[w & ~hi], s=3, c="#9aa0a6", label="either < −8 dB")
        ax[0].scatter(t[hi], dd[hi], s=3, c="#d6402a", label="both ≥ −8 dB")
        newarc = np.flatnonzero((np.diff(r["arc"][ia]) != 0) | (np.diff(r["arc"][ib]) != 0))
        for j in newarc[t[newarc + 1] <= 60]:
            ax[0].axvline(t[j + 1], color="0.85", lw=0.6, zorder=0)
        ax[0].axhspan(-GOOD_M, GOOD_M, color="#2a78d6", alpha=0.12, lw=0)
        ax[0].set_ylim(-5000, 5000)
        ax[0].set_xlabel("s from the first record")
        ax[0].set_ylabel("PR error after truth, PCI 92 − PCI 268 (m)")
        ax[0].set_title(
            f"(a) {s0['session']}: double difference, first 60 s\n"
            f"grey lines: a new arc; band ±{GOOD_M:g} m",
            fontsize=9,
        )
        ax[0].legend(fontsize=7, loc="lower left")
    # (b) doppler differences in 100 Hz aliases, both sessions
    for s, c in zip(sessions, ("#2a78d6", "#eb6834"), strict=False):
        r = res[s["session"]]
        d = np.concatenate([r["res"][ia] - r["res"][ib] for *_, ia, ib in _pairs(r, False)])
        ax[1].hist(
            d / ALIAS_MPS,
            bins=np.arange(-8, 8.01, 0.05),
            histtype="step",
            color=c,
            label=s["session"],
            density=True,
        )
    ax[1].set_xlabel(
        f"doppler difference of two cells at one epoch / {ALIAS_MPS:.2f} m/s (100 Hz)"
    )
    ax[1].set_ylabel("density")
    ax[1].set_title(
        "(b) Dopplers sit on 100 Hz aliases (zero at rest);\ntold σ 0.01–0.1 m/s", fontsize=9
    )
    ax[1].legend(fontsize=7)
    # (c) error after the cut, median over cuts, both sessions
    grid_t = np.arange(0.0, 301.0, 1.0)
    styles = {
        "no LTE": ("#2a78d6", "-"),
        "B": ("#eda100", "-"),
        "B, all four": ("#6250d6", "-"),
        "B, tower clock q 20": ("#1baf7a", "-"),
        "B, told σ × 10": ("#e87ba4", "-"),
        "B, q_accel 0.1 (static prior)": ("#555555", "--"),
    }
    for s, ls in zip(sessions, ("-", ":"), strict=False):
        for n, (c, ls0) in styles.items():
            rs = [x for x in rows[s["session"]] if x["variant"] == n]
            ys = [
                np.interp(grid_t, x["after_s"], x["err_m"], left=np.nan, right=np.nan) for x in rs
            ]
            lab = f"{n} ({s['session'][9:13]})"
            ax[2].plot(
                grid_t,
                np.nanmedian(ys, axis=0),
                color=c,
                ls=ls if ls0 == "-" else ls0,
                lw=1.6 if ls == "-" else 1.2,
                label=lab,
            )
    ax[2].axhline(50, color="0.5", lw=0.8)
    ax[2].text(300, 55, "50 m", ha="right", fontsize=7)
    ax[2].set_yscale("log")
    ax[2].set_ylim(0.05, 3e4)
    ax[2].set_xlabel("s after GPS cut")
    ax[2].set_ylabel("horizontal error, median over cuts (m)")
    ax[2].set_title("(c) Opt-in fixes after the cut: solid 0151, dotted 0233", fontsize=9)
    ax[2].legend(fontsize=6, ncol=2, loc="lower right")
    for a_ in ax:
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
        a_.grid(True, color="0.92", lw=0.6)
    fig.suptitle(
        f"Real static sessions, #183 front end, replay at {sessions[0].get('commit', '')}: "
        "errors and residuals against GPS truth only",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--notes", type=Path, help="markdown appended to summary.md")
    a = ap.parse_args(argv)
    commit = _git("describe", "--always", "--dirty", "--abbrev=7")
    sessions, res, rows = [], {}, {}
    for p in a.sessions:
        name = Path(p).name
        r = residuals(p)
        res[name] = r
        meas, t0, _ = CUT.load(p)
        fix_t, _ = CUT.gps_fixes(meas)
        cuts = cuts_for((fix_t[-1] - t0) / 1e9)
        good = good_cells(r)
        agg, rows[name] = grid(p, cuts, good, a.jobs)
        mid = cuts[len(cuts) // 2]
        sessions.append(
            {
                "session": name,
                "commit": commit,
                "frontend_commit": CUT.session.read_meta(p).get("commit"),
                "pairs": pair_table(r),
                "coverage": coverage(r),
                "good_cells": good,
                "arc_dd_steps": arc_dd_steps(r),
                "doppler": doppler_alias(r),
                "exclusion": exclusion(p),
                "after_cut_s": mid,
                "after_cut": after_cut(p, mid),
                "cuts_s": cuts,
                "grid": agg,
            }
        )
    summary = {
        "kind": "replay of real static sessions, GPS cut in software",
        "integration_branch": "tmp/e2e-combined (local only, never pushed)",
        "commit": commit,
        "sessions": sessions,
        "notes": a.notes.read_text().splitlines() if a.notes else [],
        "runs": [
            {k: v for k, v in x.items() if k not in ("after_s", "err_m", "hpl_m")}
            for rs in rows.values()
            for x in rs
        ],
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    (a.out / "summary.md").write_text(markdown(summary))
    plot(sessions, res, rows, a.out / "root_cause.png")
    print(markdown(summary))


if __name__ == "__main__":
    main()
