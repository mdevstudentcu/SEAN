"""Figures for a session (issue #3): the evidence behind every result.

`pnt plot <session>` writes, for one estimator in the session:
- error.png: horizontal error and HPL over time, fault windows shaded, sustained alarms marked
- stanford.png: HPL against true error, with the misleading and unavailable regions counted
- trust.png: per-source trust over time
- time.png: clock error and its 1-sigma, only if the estimator estimates the clock

Every figure carries a caption naming the scenario (or session), seed, estimator and commit
(REQ-10). Needs matplotlib (the `ground` extra).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pnt.core.frames import llh_to_enu
from pnt.core.measurement import Estimate, Truth
from pnt.core.time import s_to_ns
from pnt.io import session
from pnt.io.mcap_log import read_session
from pnt.metrics import ALARM_FLAGS

# TBC: REQ-01/REQ-02 targets set the real alert limit (same placeholder as the baseline).
ALERT_LIMIT_M = 50.0


@dataclass
class RunData:
    name: str
    meta: dict[str, str]
    spec: dict
    truth: list[Truth]
    estimates: dict[str, list[Estimate]] = field(default_factory=dict)

    def caption(self, estimator: str) -> str:
        scenario = self.meta.get("scenario") or self.name
        parts = [f"scenario {scenario}" if self.meta.get("scenario") else f"session {self.name}"]
        if self.meta.get("seed") not in (None, "", "None"):
            parts.append(f"seed {self.meta['seed']}")
        parts += [f"estimator {estimator}", f"commit {self.meta.get('commit', 'unknown')}"]
        return " · ".join(parts)


def load(path: str | Path) -> RunData:
    """Truth, every estimator's output and the scenario (for fault windows) from a session
    folder or a bare session MCAP."""
    meta = session.read_meta(path)
    name = session.session_name(path)
    path = session.mcap_path(path)
    truth: list[Truth] = []
    estimates: dict[str, list[Estimate]] = {}
    for topic, rec in read_session(path, topics=["/truth", "/nav/"]):
        if topic == "/truth":
            truth.append(rec)
        else:
            estimates.setdefault(topic.removeprefix("/nav/"), []).append(rec)
    spec: dict = {"faults": []}
    if meta.get("scenario"):
        from pnt.sim.scenario import load_named

        try:
            spec = load_named(meta["scenario"])
        except (ValueError, FileNotFoundError) as exc:
            warnings.warn(f"no fault shading: {exc}", stacklevel=2)
    if "origin_llh" not in spec and meta.get("origin_llh"):
        spec["origin_llh"] = meta["origin_llh"]
    return RunData(name, meta, spec, truth, estimates)


@dataclass
class Series:
    t_s: np.ndarray  # seconds since the first estimate
    err_h: np.ndarray  # horizontal error (m), nan where no truth
    hpl: np.ndarray
    alarm: np.ndarray  # epochs carrying an alarm flag
    truth_enu: np.ndarray  # (N, 3), nan where no truth
    clock_err: np.ndarray  # s, nan where not estimated
    clock_sigma: np.ndarray
    t0_ns: int


def series(run: RunData, estimator: str) -> Series:
    est = run.estimates[estimator]
    tmap = {t.t_ns: t for t in run.truth}
    nan3 = (np.nan, np.nan, np.nan)
    tru = np.array([tmap[e.t_ns].pos_enu if e.t_ns in tmap else nan3 for e in est], float)
    pos = np.array([e.pos_enu for e in est], float)
    clock_truth = np.array([tmap[e.t_ns].clock_bias_s if e.t_ns in tmap else np.nan for e in est])
    has_clock = np.array([e.clock_sigma_s is not None for e in est])
    t0 = est[0].t_ns
    return Series(
        t_s=np.array([(e.t_ns - t0) / 1e9 for e in est]),
        err_h=np.hypot(*(pos - tru)[:, :2].T),
        hpl=np.array([np.nan if e.hpl_m is None else e.hpl_m for e in est]),
        alarm=np.array([bool(ALARM_FLAGS & set(e.flags)) for e in est]),
        truth_enu=tru,
        clock_err=np.where(has_clock, [e.clock_bias_s for e in est] - clock_truth, np.nan),
        clock_sigma=np.array(
            [np.nan if e.clock_sigma_s is None else e.clock_sigma_s for e in est]
        ),
        t0_ns=t0,
    )


def fault_spans(run: RunData, s: Series, scenario_t0_ns: int) -> list[tuple[float, float, str]]:
    """(start_s, end_s, label) on the series time axis. Jamming zones are spatial, so they are
    shaded where the true position is inside the zone's onset radius."""
    spans = []
    for f in run.spec.get("faults", []):
        if f["type"] == "jamming_zone":
            if run.spec.get("origin_llh") is None or np.isnan(s.truth_enu).all():
                continue
            c = llh_to_enu(f["center_llh"], run.spec["origin_llh"])
            inside = np.hypot(*(s.truth_enu[:, :2] - c[:2]).T) < f["onset_m"]
            spans += [(a, b, "jamming zone") for a, b in _runs(s.t_s, inside)]
            continue
        start = (scenario_t0_ns + s_to_ns(f.get("start_s", 0.0)) - s.t0_ns) / 1e9
        end = (scenario_t0_ns + s_to_ns(f["end_s"]) - s.t0_ns) / 1e9 if "end_s" in f else s.t_s[-1]
        spans.append((start, end, f["type"].replace("_", " ")))
    return spans


def _runs(t: np.ndarray, mask: np.ndarray) -> list[tuple[float, float]]:
    out, start = [], None
    for ti, m in zip(t, mask, strict=True):
        if m and start is None:
            start = ti
        elif not m and start is not None:
            out.append((start, ti))
            start = None
    if start is not None:
        out.append((start, t[-1]))
    return out


def _figure(caption: str, **kw):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(**kw)
    fig.text(0.01, 0.005, caption, fontsize=7, color="0.4", ha="left", va="bottom")
    return fig, ax


def fig_error(run: RunData, estimator: str, scenario_t0_ns: int):
    s = series(run, estimator)
    fig, ax = _figure(run.caption(estimator), figsize=(10, 4))
    for i, (a, b, label) in enumerate(fault_spans(run, s, scenario_t0_ns)):
        ax.axvspan(a, b, color="tab:red", alpha=0.12, lw=0, label=label if i == 0 else None)
    ax.plot(s.t_s, s.err_h, color="tab:blue", lw=1, label="horizontal error")
    ax.plot(s.t_s, s.hpl, color="tab:orange", lw=1, label="HPL")
    if s.alarm.any():
        ax.plot(s.t_s[s.alarm], np.zeros(s.alarm.sum()), "|", color="tab:red", ms=10,
                label="alarm flag")  # fmt: skip
    ax.set(xlabel="time (s)", ylabel="metres", title=f"Horizontal error and HPL: {estimator}")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def stanford_counts(err: np.ndarray, hpl: np.ndarray, alert_limit_m: float) -> dict[str, int]:
    ok = ~np.isnan(err) & ~np.isnan(hpl)
    err, hpl = err[ok], hpl[ok]
    unavailable = hpl > alert_limit_m
    available = ~unavailable
    return {
        "epochs": int(ok.sum()),
        "nominal": int(np.sum(available & (err <= hpl))),
        "misleading": int(np.sum(available & (err > hpl) & (err <= alert_limit_m))),
        "hazardous": int(np.sum(available & (err > alert_limit_m))),
        "unavailable": int(unavailable.sum()),
        "unavailable_misleading": int(np.sum(unavailable & (err > hpl))),
    }


def fig_stanford(run: RunData, estimator: str, alert_limit_m: float = ALERT_LIMIT_M):
    from matplotlib.colors import LogNorm

    s = series(run, estimator)
    ok = ~np.isnan(s.err_h) & ~np.isnan(s.hpl)
    err, hpl = s.err_h[ok], s.hpl[ok]
    top = max(2 * alert_limit_m, float(np.nanpercentile(np.r_[err, hpl], 99.5)) * 1.1)
    fig, ax = _figure(run.caption(estimator), figsize=(6, 5.5))
    bins = np.linspace(0, top, 80)
    h = ax.hist2d(err, hpl, bins=[bins, bins], norm=LogNorm(), cmap="viridis", cmin=1)
    fig.colorbar(h[3], ax=ax, label="epochs")
    ax.plot([0, top], [0, top], color="k", lw=1)
    ax.axvline(alert_limit_m, color="k", ls="--", lw=0.8)
    ax.axhline(alert_limit_m, color="k", ls="--", lw=0.8)
    c = stanford_counts(err, hpl, alert_limit_m)
    n = max(c["epochs"], 1)

    def pct(k):
        return f"{c[k]} ({100 * c[k] / n:.2f} %)"

    # The regions are thin wedges, so counts go in one box rather than on the regions
    box = "\n".join(
        [
            f"nominal (error ≤ HPL ≤ AL): {pct('nominal')}",
            f"misleading (HPL < error ≤ AL): {pct('misleading')}",
            f"hazardous (error > AL, HPL ≤ AL): {pct('hazardous')}",
            f"unavailable (HPL > AL): {pct('unavailable')}",
        ]
    )
    ax.text(0.98, 0.98, box, transform=ax.transAxes, fontsize=7.5, ha="right", va="top",
            bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.9))  # fmt: skip
    ax.text(alert_limit_m, top * 0.01, " AL", fontsize=7, va="bottom")
    ax.set(xlim=(0, top), ylim=(0, top), xlabel="true horizontal error (m)", ylabel="HPL (m)")
    ax.set_title(f"Stanford plot: {estimator}, AL {alert_limit_m:g} m")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def fig_trust(run: RunData, estimator: str):
    est = run.estimates[estimator]
    t0 = est[0].t_ns
    t = np.array([(e.t_ns - t0) / 1e9 for e in est])
    sources = sorted({k for e in est for k in e.trust})
    fig, ax = _figure(run.caption(estimator), figsize=(10, 1 + 0.6 * max(len(sources), 1)))
    for i, src in enumerate(sources):
        v = np.array([e.trust.get(src, np.nan) for e in est])
        ax.fill_between(t, i, i + 0.8 * np.nan_to_num(v), step="post", alpha=0.7, lw=0)
    ax.set_yticks([i + 0.4 for i in range(len(sources))], sources)
    ax.set(xlabel="time (s)", title=f"Per-source trust (bar height = trust 0..1): {estimator}")
    ax.set_ylim(0, max(len(sources), 1))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return fig


def fig_time(run: RunData, estimator: str):
    s = series(run, estimator)
    if np.isnan(s.clock_err).all():
        return None
    fig, ax = _figure(run.caption(estimator), figsize=(10, 3.5))
    ax.plot(s.t_s, s.clock_err * 1e6, lw=1, label="clock error")
    ax.fill_between(s.t_s, -s.clock_sigma * 1e6, s.clock_sigma * 1e6, alpha=0.2, label="±1σ")
    ax.set(xlabel="time (s)", ylabel="µs", title=f"Clock error: {estimator}")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def save_all(
    path: str | Path,
    out_dir: str | Path,
    estimator: str | None = None,
    alert_limit_m: float = ALERT_LIMIT_M,
) -> list[Path]:
    import matplotlib.pyplot as plt

    from pnt.sim.scenario import T0_NS

    run = load(path)
    if not run.estimates:
        raise ValueError(f"{path} has no /nav/* topics to plot")
    estimator = estimator or sorted(run.estimates)[0]
    if estimator not in run.estimates:
        raise ValueError(f"no /nav/{estimator} in {path}; found {sorted(run.estimates)}")
    if not run.truth:
        raise ValueError(f"{path} has no /truth: error plots need ground truth")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    figs = {
        "error": fig_error(run, estimator, T0_NS),
        "stanford": fig_stanford(run, estimator, alert_limit_m),
        "trust": fig_trust(run, estimator),
        "time": fig_time(run, estimator),
    }
    for name, fig in figs.items():
        if fig is None:
            continue
        p = out / f"{name}.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        written.append(p)
    return written
