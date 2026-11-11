"""`gnss_health` on a real GPS HAT session: statistics only, no positions (#22, ADR-0031).

Reads the `gnss_health` records that `pnt frontend gnss <session>` wrote to `<session>-gnss`
and summarises them: record count and spacing, the jamming indicator, satellites used, HDOP,
satellites seen, and the mean C/N0 of the `TOP_K` strongest satellites (the quantity the
indicator scales). That last one is what ADR-0031's open-sky reference (`REF_CN0_DBHZ`, `TBC`)
is to be measured from. Position records are not read.

    python analysis/gnss_health_real.py data/sessions/<session>-gnss --out DIR
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from pnt.frontends import gnss


def load(session_dir: Path) -> list:
    from pnt.io import session
    from pnt.io.mcap_log import read_session

    mcap = session.mcap_path(session_dir)
    return [
        r
        for topic, r in read_session(mcap, ["/meas/gnss"])
        if getattr(r, "kind", "") == "gnss_health"
    ]


def top_k_cn0(snr: dict, k: int = gnss.TOP_K, low: float = gnss.LOW_CN0_DBHZ) -> float:
    """Mean C/N0 of the `k` strongest tracked satellites, a missing one counting as `low`
    (the `S` of `gnss.jam_indicator`)."""
    tracked = sorted((float(s) for s in snr.values() if s is not None and s > 0), reverse=True)
    top = tracked[:k] + [low] * max(0, k - len(tracked))
    return sum(top) / k


def _stats(x) -> dict:
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return {"n": 0}
    return {
        "n": int(x.size),
        "min": float(x.min()),
        "p5": float(np.percentile(x, 5)),
        "median": float(np.median(x)),
        "p95": float(np.percentile(x, 95)),
        "max": float(x.max()),
    }


def series(records: list) -> dict:
    rs = sorted(records, key=lambda m: m.t_ns)
    t0 = rs[0].t_ns if rs else 0
    return {
        "t_s": [(m.t_ns - t0) / 1e9 for m in rs],
        "jam": [m.value[0] for m in rs],
        "n_used": [m.value[1] for m in rs],
        "hdop": [m.value[2] for m in rs],
        "n_seen": [m.meta.get("n_seen") or 0 for m in rs],
        "n_tracked": [
            sum(1 for s in (m.meta.get("snr") or {}).values() if s and s > 0) for m in rs
        ],
        "top_k_cn0": [top_k_cn0(m.meta.get("snr") or {}) for m in rs],
        "all_cn0": [
            float(s) for m in rs for s in (m.meta.get("snr") or {}).values() if s and s > 0
        ],
    }


def summarize(records: list) -> dict:
    s = series(records)
    dt = np.diff(s["t_s"])
    jam = np.asarray(s["jam"], dtype=float)
    return {
        "records": len(records),
        "span_s": float(s["t_s"][-1]) if s["t_s"] else 0.0,
        "spacing_s": _stats(dt),
        "jam_indicator": _stats(jam),
        "jam_above_zero_frac": float(np.mean(jam > 0)) if jam.size else None,
        "n_used": _stats(s["n_used"]),
        "hdop": _stats(s["hdop"]),
        "no_fix_records": int(sum(h == gnss.NO_FIX_HDOP for h in s["hdop"])),
        "n_seen": _stats(s["n_seen"]),
        "n_tracked": _stats(s["n_tracked"]),
        "top_k_cn0_dbhz": _stats(s["top_k_cn0"]),
        "all_cn0_dbhz": _stats(s["all_cn0"]),
        "params": {"ref": gnss.REF_CN0_DBHZ, "low": gnss.LOW_CN0_DBHZ, "k": gnss.TOP_K},
    }


def _row(name: str, st: dict, fmt: str = ".1f") -> str:
    if not st.get("n"):
        return f"| {name} | none | | | | |"
    v = [format(st[k], fmt) for k in ("min", "p5", "median", "p95", "max")]
    return f"| {name} | " + " | ".join(v) + " |"


def table_md(name: str, summ: dict, stamp: str) -> str:
    p = summ["params"]
    return "\n".join(
        [
            f"# gnss_health on {name} (#22, ADR-0031)",
            "",
            f"`python analysis/gnss_health_real.py` at `{stamp}` on the `gnss_health` records "
            "that `pnt frontend gnss` derived from the session's gpsd SKY reports. Real "
            "session, GPS HAT (MediaTek, C/N0 from NMEA GSV), statistics only. Indicator "
            f"parameters (ADR-0031, all `TBC`): open-sky reference {p['ref']:g} dB-Hz, loss "
            f"level {p['low']:g} dB-Hz, top {p['k']} satellites.",
            "",
            f"{summ['records']} records over {summ['span_s']:.1f} s; "
            f"{summ['no_fix_records']} without a fix (HDOP {gnss.NO_FIX_HDOP:g}); indicator "
            f"above 0 in {100 * (summ['jam_above_zero_frac'] or 0):.1f} % of records.",
            "",
            "| Quantity | min | p5 | median | p95 | max |",
            "|---|---|---|---|---|---|",
            _row("Record spacing (s)", summ["spacing_s"], ".2f"),
            _row("Jamming indicator", summ["jam_indicator"], ".3f"),
            _row(f"Mean C/N0 of top {p['k']} (dB-Hz)", summ["top_k_cn0_dbhz"]),
            _row("C/N0, every tracked satellite (dB-Hz)", summ["all_cn0_dbhz"]),
            _row("Satellites used", summ["n_used"], ".0f"),
            _row("Satellites tracked (C/N0 > 0)", summ["n_tracked"], ".0f"),
            _row("Satellites seen", summ["n_seen"], ".0f"),
            _row("HDOP", summ["hdop"], ".2f"),
            "",
        ]
    )


def plot(records: list, name: str, stamp: str, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = series(records)
    t = np.asarray(s["t_s"]) / 60
    ink, grid, line = "#55544e", "#e4e3dd", "#2a78d6"
    fig, axs = plt.subplots(4, 1, figsize=(8, 7), sharex=True, facecolor="#fcfcfb")
    panels = [
        (s["top_k_cn0"], f"top-{gnss.TOP_K} C/N0\n(dB-Hz)"),
        (s["jam"], "jamming\nindicator"),
        (s["n_used"], "satellites\nused"),
        (s["hdop"], "HDOP"),
    ]
    for ax, (y, lab) in zip(axs, panels, strict=True):
        ax.set_facecolor("#fcfcfb")
        ax.plot(t, y, color=line, lw=1.2)
        ax.set_ylabel(lab, fontsize=8)
        ax.grid(axis="y", color=grid, lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for v, lab in ((gnss.REF_CN0_DBHZ, "reference"), (gnss.LOW_CN0_DBHZ, "loss level")):
        axs[0].axhline(v, color=ink, lw=0.8, ls="--")
        axs[0].text(t[-1] if t.size else 0, v, f" {lab} {v:g} (TBC)", fontsize=7, color=ink,
                    va="bottom", ha="right")  # fmt: skip
    axs[1].set_ylim(-0.05, 1.05)
    axs[-1].set_xlabel("minutes since the first record")
    axs[0].set_title(f"gnss_health, real session {name}, commit {stamp}", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("session", help="a `pnt frontend gnss` output folder")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    src = Path(a.session)
    recs = load(src)
    if not recs:
        raise SystemExit(f"no gnss_health records in {src}")
    summ = summarize(recs)
    stamp = commit()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(table_md(src.name, summ, stamp))
    (out / "summary.json").write_text(
        json.dumps({"commit": stamp, "session": src.name, **summ}, indent=2) + "\n"
    )
    plot(recs, src.name, stamp, out / "gnss_health.png")
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
