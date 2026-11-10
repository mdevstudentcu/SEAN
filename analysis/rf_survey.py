"""RF survey (#20): which signals of opportunity are on air at a site, from `rtl_power` sweeps.

    python analysis/rf_survey.py <site>=<power.csv>[,<more.csv>] [<site>=...] [--out DIR]

One sweep set per site, as `deploy/pi/rf_survey.sh` records them. Writes to `results/rf-survey/`
(or --out): `summary.md` (band table per site), `summary.json`, and `spectrum-<site>.png`.
Power only, relative to each sweep's noise floor; the dongle's dB are not calibrated (TBC).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np

from pnt.frontends.spectrum import BANDS, OCCUPIED_DB, band_power, read_rtl_power

INK, GRID, LINE, SHADE = "#52514e", "#e4e3df", "#2a78d6", "#eb6834"


def commit() -> str:
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def plot(path: Path, site: str, sweep, caption: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 4), constrained_layout=True)
    floor = sweep.floor_db
    for name, (lo, hi) in BANDS.items():
        ax.axvspan(lo, hi, color=SHADE, alpha=0.12, lw=0)
        x = lo + 15 if hi - lo > 100 else (lo + hi) / 2  # wide bands: label at the low edge
        ax.text(x, 1.01, name, transform=ax.get_xaxis_transform(), rotation=90,
                fontsize=6, color=INK, ha="center", va="bottom")  # fmt: skip
    ax.plot(sweep.freq_hz / 1e6, sweep.power_db - floor, color=LINE, lw=1)
    ax.axhline(OCCUPIED_DB, color=INK, lw=0.8, ls="--")
    ax.set_xlabel("frequency (MHz)")
    ax.set_ylabel("power above noise floor (dB)")
    ax.set_title(f"RF survey: {site}", loc="left", fontsize=11, pad=60)
    ax.grid(True, color=GRID, lw=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.text(0.01, -0.02, caption, fontsize=7, color=INK, ha="left", va="top")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sites", nargs="+", help="<site>=<power.csv>[,<more.csv>]")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    out = args.out or Path(__file__).parent / "results" / "rf-survey"
    out.mkdir(parents=True, exist_ok=True)
    c = commit()

    table: dict[str, list] = {}
    meta: dict[str, dict] = {}
    for spec in args.sites:
        site, _, files = spec.partition("=")
        if not files:
            raise SystemExit(f"{spec}: expected <site>=<power.csv>")
        paths = files.split(",")
        sweep = read_rtl_power(paths)
        table[site] = band_power(sweep)
        meta[site] = {
            "files": [Path(p).name for p in paths],
            "passes": sweep.passes,
            "floor_db": sweep.floor_db,
            "span_mhz": [float(sweep.freq_hz[0] / 1e6), float(sweep.freq_hz[-1] / 1e6)],
            "bins": int(len(sweep.freq_hz)),
        }
        caption = (
            f"Site {site}: {', '.join(meta[site]['files'])}, {sweep.passes} passes, "
            f"analysed at {c}. Dashed: {OCCUPIED_DB:g} dB above the floor (TBC)."
        )
        plot(out / f"spectrum-{site}.png", site, sweep, caption)

    def cell(b):
        if not b.bins:
            return "not swept"
        med, peak = b.median_above_floor_db, b.peak_above_floor_db
        return f"{med:+.1f} / {peak:+.1f} / {b.occupied_frac:.0%}"

    sites = list(table)
    lines = [
        "# RF survey",
        "",
        f"Analysed at commit `{c}`. Per band: median / peak dB above that site's noise floor / "
        f"share of bins at least {OCCUPIED_DB:g} dB above it (TBC). Power only (ADR-0011).",
        "",
        "| Band (MHz) | " + " | ".join(sites) + " |",
        "| --- | " + " | ".join("---" for _ in sites) + " |",
    ]
    for i, (name, (lo, hi)) in enumerate(BANDS.items()):
        lines.append(
            f"| {name} ({lo:g}-{hi:g}) | " + " | ".join(cell(table[s][i]) for s in sites) + " |"
        )
    lines += [
        "",
        "| Site | Files | Passes | Floor (dB FS) | Span (MHz) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in sites:
        m = meta[s]
        lines.append(f"| {s} | {', '.join(m['files'])} | {m['passes']} | {m['floor_db']:.1f} | "
                     f"{m['span_mhz'][0]:.0f}-{m['span_mhz'][1]:.0f} |")  # fmt: skip
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    (out / "summary.json").write_text(json.dumps(
        {"commit": c, "occupied_db": OCCUPIED_DB, "sites": meta,
         "bands": {s: [asdict(b) for b in table[s]] for s in sites}}, indent=2))  # fmt: skip
    print(f"wrote {out}/summary.md and {len(sites)} spectrum plot(s)")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
