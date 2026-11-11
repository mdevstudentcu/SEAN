"""GNSS spoof decision from the GPS sky (#206, ADR-0041): a real sky gives no alarm, a faked one
is caught. Statistics only.

PRIVACY: the real session was recorded at a private address. The receiver's position is worked
out here, in memory, from the session's own GNSS fixes (their median), because each satellite's
predicted elevation needs it. It is never printed, written or plotted, and neither is any
per-satellite elevation or azimuth (a few of those at known times would locate the receiver).
Only counts, spreads, correlations, levels and delays leave this script.

Three kinds of evidence, labelled as such in the output:
1. **Real session** (`--session`, e.g. data/sessions/20261111-0040-static-fullsuite): every
   skyview of its `gnss_sky` events, judged as recorded (false alarms), then with a fake sky
   injected in software (`pnt.sim.attacks` `fake_sky`) from `INJECT_S` after the first skyview to
   the end: PRNs below the horizon, every satellite at one power, and both.
2. **Real session, full chain**: the session's GNSS fixes and barometer replayed through
   `ekf-guard`, clean and with a 300 m east jump injected with the flat sky at `INJECT_S`; the
   decision reads the skyviews and the estimates' flags, as the panel does.
3. **Sim** (`spoof-jump-sky`, seeds 0..N-1, `ekf` and `ekf-guard`): false alarms before the
   spoof at 150 s, and detection delays after it. The sim's sky is a placeholder fitted on (1).

    python analysis/spoof_sky.py --session <dir> [--runs 20] [--out <dir>] [--plot <png>]
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import numpy as np

from pnt.core.frames import enu_to_llh
from pnt.frontends import gnss as gnss_fe
from pnt.integrity.sky import STALE_S, GpsAlmanac, SpoofDecision
from pnt.nav import ESTIMATORS
from pnt.sim import attacks
from pnt.sim.scenario import T0_NS, generate, load

INJECT_S = 300.0  # the fake sky starts this long after the real session's first skyview
FLAT_DBHZ = 45.0  # a strong spoofer (TBC); every received satellite at this C/N0
JUMP_ENU_M = [300.0, 0.0, 0.0]  # the jump of the full-chain case, as spoof-jump.yaml
SIM = "spoof-jump-sky"
SIM_SPOOF_S = 150.0
RANK = {"unknown": 0, "not_spoofed": 0, "suspect": 1, "spoofed": 2}

FAKES = {
    "PRNs below the horizon": {"below_horizon": 2, "cn0_dbhz": 40.0},
    "every satellite at one power": {"flat_cn0_dbhz": FLAT_DBHZ},
    "both": {"below_horizon": 2, "flat_cn0_dbhz": FLAT_DBHZ},
}


# --- the real session ---------------------------------------------------------------------


def real_session(path: Path):
    """(skyviews as gnss_health records, GNSS fixes and baro records, receiver LLH). The LLH
    stays in memory (module docstring)."""
    from pnt.io import session
    from pnt.io.mcap_log import read_json, read_session

    mcap = session.mcap_path(path)
    origin = session.read_meta(path)["origin_llh"]
    events = [d for topic, d in read_json(mcap, ["/events"]) if d.get("text") == "gnss_sky"]
    views = [gnss_fe.health(d["t_ns"], d) for d in events if gnss_fe.has_skyview(d)]
    recs = [
        r
        for _, r in read_session(mcap, topics=["/meas/"])
        if (r.source == "gnss" and r.kind == "position_enu") or r.source == "baro"
    ]
    fixes = np.array([r.value for r in recs if r.kind == "position_enu"])
    rx_llh = enu_to_llh(np.median(fixes, axis=0), origin)
    return views, recs, origin, rx_llh


def inject(records, fault: dict, origin_llh, rx_enu, t0_ns: int):
    """Software fault injection on recorded records (`pnt.sim.attacks`), the receiver static at
    `rx_enu` (its truth for the elevations)."""
    ctx = attacks.Context(
        t0_ns=t0_ns,
        origin_llh=origin_llh,
        truth_pos=lambda t: np.tile(rx_enu, (len(np.atleast_1d(t)), 1)),
        rng=np.random.default_rng(0),
    )
    out, _ = attacks.apply(list(records), [fault], ctx)
    return out


def judge(views, rx_llh, almanac, estimates=None, origin_llh=None):
    """The decision at each skyview (no estimates) or at each estimate, fed the skyviews before
    it, seen from `rx_llh` or (with estimates) from the estimate. Returns
    [(t_ns, SpoofStatus)] and the SkyChecks."""
    d = SpoofDecision(almanac=almanac)
    out, checks = [], []
    if estimates is None:
        for m in views:
            checks.append(d.measurement(m, rx_llh))
            out.append((m.t_ns, d.decide(m.t_ns)))
        return out, checks
    k = 0
    for e in estimates:
        while k < len(views) and views[k].t_ns <= e.t_ns:
            checks.append(d.measurement(views[k], enu_to_llh(e.pos_enu, origin_llh)))
            k += 1
        out.append((e.t_ns, d.decide(e.t_ns, e.flags)))
    return out, checks


def onsets(levels, t_from_ns=None, t_to_ns=None, at_least="suspect"):
    """Times an alarm of at least `at_least` starts, in [t_from, t_to)."""
    on, prev = [], False
    for t, s in levels:
        if (t_from_ns is not None and t < t_from_ns) or (t_to_ns is not None and t >= t_to_ns):
            prev = False
            continue
        cur = RANK[s.level] >= RANK[at_least]
        if cur and not prev:
            on.append(t)
        prev = cur
    return on


def first_delay(levels, start_ns, at_least):
    for t, s in levels:
        if t >= start_ns and RANK[s.level] >= RANK[at_least]:
            return (t - start_ns) / 1e9
    return None


def stats(xs):
    xs = np.asarray([x for x in xs if x is not None], float)
    if not len(xs):
        return "n/a"
    return f"min {xs.min():.2f}, median {np.median(xs):.2f}, max {xs.max():.2f}"


def real_part(path: Path, almanac):
    views, recs, origin, rx_llh = real_session(path)
    from pnt.core.frames import llh_to_enu

    rx_enu = llh_to_enu(rx_llh, origin)
    t0 = views[0].t_ns
    start = t0 + int(INJECT_S * 1e9)
    span_s = (views[-1].t_ns - t0) / 1e9
    lines = [
        f"## Real session `{path.name}` (receiver position withheld for privacy)",
        "",
        f"{len(views)} skyviews over {span_s:.0f} s (one every 5 s: the GPS HAT's satellite "
        "list).",
        "",
    ]
    clean, checks = judge(views, rx_llh, almanac)
    n_other = sorted({c.n_other for c in checks})
    lines += [
        "**As recorded (real sky):**",
        "",
        f"- GPS PRNs judged per skyview: {stats([c.n_judged for c in checks])}; other PRNs "
        f"(GLONASS, SBAS) not judged: {n_other[0]} to {n_other[-1]}",
        f"- Received PRNs predicted below {almanac_mask()} deg: "
        f"{sum(len(c.below) for c in checks)} in {len(checks)} skyviews",
        f"- C/N0 spread (dB): {stats([c.spread_db for c in checks])}",
        f"- Correlation of C/N0 with predicted elevation: {stats([c.corr for c in checks])}",
        f"- Power pattern judged flat: {sum(bool(c.flat) for c in checks)} of "
        f"{sum(c.flat is not None for c in checks)} judged skyviews",
        f"- Levels: {level_counts(clean)}",
        f"- False alarms (suspect or spoofed onsets): {len(onsets(clean))}; spoofed onsets: "
        f"{len(onsets(clean, at_least='spoofed'))}",
        "",
        f"**Fake sky injected (software) from {INJECT_S:.0f} s to the end:**",
        "",
        "| Fake sky | Before: alarms | After: first suspect | After: first spoofed "
        "| Faked skyviews flagged (suspect or spoofed) |",
        "| --- | --- | --- | --- | --- |",
    ]
    series = {"real sky, as recorded": (clean, checks)}
    for name, f in FAKES.items():
        fault = {"type": "fake_sky", "start_s": INJECT_S, **f}
        fv = inject(views, fault, origin, rx_enu, t0)
        lv, ck = judge(fv, rx_llh, almanac)
        series[f"real + {name}"] = (lv, ck)
        after = [s for t, s in lv if t >= start]
        flagged = sum(RANK[s.level] >= 1 for s in after)
        lines.append(
            f"| {name} | {len(onsets(lv, t_to_ns=start))} "
            f"| {fmt_s(first_delay(lv, start, 'suspect'))} "
            f"| {fmt_s(first_delay(lv, start, 'spoofed'))} | {flagged} of {len(after)} |"
        )

    # Full chain: fixes and barometer through ekf-guard, the decision reading its flags too
    guard = ESTIMATORS["ekf-guard"]
    est_clean = list(guard(recs, origin_llh=origin))
    full_clean, _ = judge(views, rx_llh, almanac, est_clean, origin)
    jump = {"type": "spoof_jump", "start_s": INJECT_S, "offset_enu_m": JUMP_ENU_M}
    jrecs = inject(recs, jump, origin, rx_enu, t0)
    flat = {"type": "fake_sky", "start_s": INJECT_S, **FAKES["every satellite at one power"]}
    fv = inject(views, flat, origin, rx_enu, t0)
    est_j = list(guard(jrecs, origin_llh=origin))
    full_j, _ = judge(fv, rx_llh, almanac, est_j, origin)
    latched_clean = sum("gnss_jump_latched" in e.flags for e in est_clean)
    lines += [
        "",
        "**Full chain** (the session's GNSS fixes and barometer replayed through `ekf-guard`; "
        "the decision at each estimate reads the skyviews and the estimate's flags, as the panel "
        "does):",
        "",
        f"- Clean: {len(est_clean)} estimates, {latched_clean} flagged `gnss_jump_latched`; "
        f"levels {level_counts(full_clean)}; false alarms (onsets) {len(onsets(full_clean))}, "
        f"spoofed onsets {len(onsets(full_clean, at_least='spoofed'))}",
        f"- 300 m east jump plus every satellite at {FLAT_DBHZ:.0f} dB-Hz from {INJECT_S:.0f} s: "
        f"alarms before {len(onsets(full_j, t_to_ns=start))}; first suspect "
        f"{fmt_s(first_delay(full_j, start, 'suspect'))}, first spoofed "
        f"{fmt_s(first_delay(full_j, start, 'spoofed'))}; cues at the end: "
        f"{', '.join(full_j[-1][1].cues)}",
    ]
    series["real + one power + 300 m jump (ekf-guard)"] = (full_j, None)
    return lines, series, t0, start


def almanac_mask():
    from pnt.integrity.sky import SKY_MASK_DEG

    return f"{SKY_MASK_DEG:g}"


def fmt_s(x):
    return "never" if x is None else f"{x:.1f} s"


def level_counts(levels):
    c = {k: 0 for k in RANK}
    for _, s in levels:
        c[s.level] += 1
    return ", ".join(f"{k} {v}" for k, v in c.items() if v)


# --- the sim ------------------------------------------------------------------------------


def _sim_one(name: str, seed: int, estimator: str, clean: bool):
    spec = copy.deepcopy(load(name))
    if clean:
        spec["faults"] = []
    run = generate(spec, seed=seed)
    est = list(ESTIMATORS[estimator](run.measurements, origin_llh=spec["origin_llh"]))
    views = [m for m in run.measurements if m.kind == "gnss_health" and m.meta.get("snr")]
    lv, _ = judge(views, None, GpsAlmanac(), est, spec["origin_llh"])
    start = T0_NS + int(SIM_SPOOF_S * 1e9)
    if clean:
        return len(onsets(lv)), len(onsets(lv, at_least="spoofed")), None, None
    return (
        len(onsets(lv, t_to_ns=start)),
        len(onsets(lv, t_to_ns=start, at_least="spoofed")),
        first_delay(lv, start, "suspect"),
        first_delay(lv, start, "spoofed"),
    )


def sim_part(runs: int):
    from pnt.experiments import _map

    lines = [
        f"## Sim `{SIM}` (seeds 0-{runs - 1}; sky model `placeholder`, fitted on the real "
        "session)",
        "",
        "| Estimator | Clean (no faults): alarm onsets / spoofed onsets, all runs | Spoofed run "
        "before 150 s: alarm onsets | First suspect after the spoof (median, max) | First "
        "spoofed (median, max; runs reaching it) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for estimator in ("ekf", "ekf-guard"):
        clean = _map(_sim_one, [(SIM, s, estimator, True) for s in range(runs)], 3)
        spoof = _map(_sim_one, [(SIM, s, estimator, False) for s in range(runs)], 3)
        sus = [r[2] for r in spoof if r[2] is not None]
        red = [r[3] for r in spoof if r[3] is not None]
        lines.append(
            f"| `{estimator}` | {sum(r[0] for r in clean)} / {sum(r[1] for r in clean)} "
            f"| {sum(r[0] for r in spoof)} "
            f"| {med_max(sus)} ({len(sus)}/{runs} runs) "
            f"| {med_max(red)} ({len(red)}/{runs} runs) |"
        )
    return lines


def med_max(xs):
    return "n/a" if not xs else f"{np.median(xs):.1f} s, {max(xs):.1f} s"


# --- the figure ---------------------------------------------------------------------------


def plot(series, t0, start, out: Path, title: str):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    from pnt.integrity.sky import CORR_MIN, SPREAD_MIN_DB

    ink, muted, grid = "#2b2b2b", "#6f6e69", "#e4e3df"
    blue, orange = "#2a78d6", "#eb6834"
    level_color = {"unknown": "#b8b7b0", "not_spoofed": "#0ca30c", "suspect": "#fab219",
                   "spoofed": "#d03b3b"}  # fmt: skip
    fig, ax = plt.subplots(3, 1, figsize=(9, 7.6), sharex=True,
                           gridspec_kw={"height_ratios": [1, 1, 1.4]})  # fmt: skip
    clean = series["real sky, as recorded"][1]
    flat = series["real + every satellite at one power"][1]
    views_t = [(t - t0) / 1e9 for t, _ in series["real sky, as recorded"][0]]
    for a, key, thr, lab in (
        (ax[0], "spread_db", SPREAD_MIN_DB, "C/N0 spread across\nGPS satellites (dB)"),
        (ax[1], "corr", CORR_MIN, "Correlation of C/N0\nwith elevation"),
    ):
        a.plot(views_t, [getattr(c, key) for c in clean], color=blue, lw=2, label="Real sky")
        a.plot(views_t, [getattr(c, key) for c in flat], color=orange, lw=2,
               label=f"Fake sky: every satellite at {FLAT_DBHZ:.0f} dB-Hz")  # fmt: skip
        a.axhline(thr, color=muted, lw=1, ls="--")
        a.text(views_t[0], thr, " flat below this (TBC)", color=muted, fontsize=8, va="bottom")
        a.set_ylabel(lab, fontsize=9, color=ink)
        a.grid(color=grid, lw=0.6)
        a.spines[["top", "right"]].set_visible(False)
    ax[0].legend(fontsize=8, frameon=False, loc="center left")
    rows = list(series)
    for i, name in enumerate(rows):
        lv = series[name][0]
        ts = [(t - t0) / 1e9 for t, _ in lv]
        for k, (_, s) in enumerate(lv):
            t_end = ts[k + 1] if k + 1 < len(ts) else ts[k] + 5.0
            ax[2].barh(i, t_end - ts[k], left=ts[k], height=0.6, color=level_color[s.level],
                       linewidth=0)  # fmt: skip
    ax[2].set_yticks(range(len(rows)), rows, fontsize=8)
    ax[2].invert_yaxis()
    ax[2].set_xlabel("Seconds since the session's first skyview", fontsize=9)
    ax[2].spines[["top", "right", "left"]].set_visible(False)
    ax[2].tick_params(left=False)
    ax[2].legend(
        handles=[Patch(color=level_color[k], label=k.replace("_", " ")) for k in level_color],
        fontsize=8, frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.22),
    )  # fmt: skip
    s0 = (start - t0) / 1e9
    for a in ax:
        a.axvline(s0, color=ink, lw=1)
    ax[0].text(s0, ax[0].get_ylim()[1], " fake sky injected", fontsize=8, va="top", color=ink)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)


def main() -> None:
    from pnt.cli import _commit

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--session", type=Path, required=True)
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--plot", type=Path)
    p.add_argument("--out", type=Path, help="write summary.md here")
    a = p.parse_args()
    commit = _commit()
    almanac = GpsAlmanac()
    lines = [
        "# Spoof decision from the GPS sky (#206, ADR-0041)",
        "",
        f"`python analysis/spoof_sky.py --session data/sessions/{a.session.name} --runs {a.runs}`"
        f" at {commit}. Almanac `{almanac.path.name}`. Skyview stale after {STALE_S:.0f} s.",
        "",
    ]
    real, series, t0, start = real_part(a.session, almanac)
    lines += real + [""] + sim_part(a.runs)
    text = "\n".join(lines) + "\n"
    print(text)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "summary.md").write_text(text)
    if a.plot:
        title = (
            f"Spoof decision on a real GPS sky ({a.session.name}, receiver position withheld)\n"
            f"fake skies injected in software (real session + injected faults), commit {commit}"
        )
        plot(series, t0, start, a.plot, title)


if __name__ == "__main__":
    main()
