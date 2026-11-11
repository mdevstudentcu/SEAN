"""Tables and figure for #147's told-sigma comparison, from the JSON that
`analysis/told_sigma_147.py` (sim) and `analysis/told_sigma_147_real.py` (real replay) write.

    python analysis/told_sigma_147_report.py <dir with summary-*.json [real-*.json]> --out <dir>

Writes `tables.md` (pasted into `summary.md`, which adds what the numbers can and cannot show;
not committed)
and `t1_curves.png`, `real_replay.png`. Reads only summaries: no records, positions or ranges.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

VARIANTS = ("default", "A", "B", "B+A", "no LTE")
NAMES = {
    "default": "default: reported σ",
    "A": "A: learned noise (#156)",
    "B": "B: ADR-0036 measured σ",
    "B+A": "B+A",
    "no LTE": "no LTE (reference)",
}
# Categorical slots in fixed order (dataviz reference palette); no LTE is a neutral reference
COLORS = {"A": "#2a78d6", "default": "#eb6834", "B": "#1baf7a", "B+A": "#eda100",
          "no LTE": "#555555"}  # fmt: skip
T1_M = 25.0  # ADR-0034 T1 (TBC)
SHORT = {
    "challenge-drone-outage": "drone",
    "challenge-timing-outage": "timing",
    "challenge-drone-outage-tower-clock-step": "drone, tower clock step",
    "challenge-drone-spoof-jump": "drone, spoof jump",
}


def _m(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.1f}"


def sim_tables(summaries: list[dict]) -> list[str]:
    lines = []
    for doc in summaries:
        meta = doc["meta"]
        lines += [
            f"### Sim: {', '.join(SHORT.get(x, x) for x in meta['legs'])} — seeds {meta['seeds']}"
            f", commit `{meta['commit']}`{' (dirty)' if meta['dirty'] else ''}",
            "",
        ]
        with_loss = [r for r in doc["summary"] if "t1_worst_m" in r]
        without = [r for r in doc["summary"] if "t1_worst_m" not in r]
        if with_loss:
            lines += [
                "| Leg | Filter | Variant | T1 worst-second p95 (m) | median run 300 s p95 (m) "
                "| NEES median / p95 | HPL bound mean / worst run | misleading (runs) "
                "| hazardous (runs) | false alarms /h | T3 600 s time p95 median (µs) |",
                "|---|---|---|---|---|---|---|---|---|---|---|",
            ]
        for r in with_loss:
            lines.append(
                f"{_head(r)} **{_m(r['t1_worst_m'])}** | {_m(r['p95_300s_median_m'])} | "
                f"{_m(r['nees_median'])} / {_m(r['nees_p95'])} | "
                f"{r['hpl_bound_mean']:.2f} / {r['hpl_bound_worst']:.2f} | {_epochs(r)} | "
                f"{r['false_alarms_per_h_mean']:.1f} | {_m(r['time_err_600s_us_median'])} |"
            )
        if without:
            lines += [
                *([""] if with_loss else []),
                "| Leg | Filter | Variant | misleading (runs) | hazardous (runs) "
                "| false alarms /h |",
                "|---|---|---|---|---|---|",
            ]
        for r in without:
            lines.append(f"{_head(r)} {_epochs(r)} | {r['false_alarms_per_h_mean']:.1f} |")
        lines.append("")
    return lines


def _head(r: dict) -> str:
    return f"| {SHORT.get(r['leg'], r['leg'])} | {r['family']} | {r['variant']} |"


def _epochs(r: dict) -> str:
    """Misleading and hazardous epochs, summed over the runs, with the runs that had any."""
    return (
        f"{r['misleading_epochs']:,} ({r['misleading_epochs_runs']}) | "
        f"{r['hazardous_epochs']:,} ({r['hazardous_epochs_runs']})"
    )


def real_table(doc: dict) -> list[str]:
    meta = doc["meta"]
    lines = [
        f"### Real replay: `{meta['session']}`, GPS cut in software at "
        f"{', '.join(f'{c:g}' for c in meta['cuts_s'])} s (#214's script at "
        f"`{meta['cut_script']}`)",
        "",
        "Errors against the withheld GPS fixes; median over the cuts, worst cut in brackets (m). "
        "HPL bound pooled over every withheld fix.",
        "",
        "| Filter | Variant | LTE records | p95 0–120 s | p95 0–300 s | error at 60 s "
        "| error at 300 s | HPL ≥ error | error > HPL (fixes) | before cut: GNSS excluded |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in doc["aggregate"]:
        b = f"{r['hpl_bound']:.0%}" if "hpl_bound" in r else "—"
        mis = f"{r['misleading']} / {r['fixes']}" if "misleading" in r else "—"
        cells = [f"{_m(r[f + '_median'])} ({_m(r[f + '_worst'])})"
                 for f in ("p95_120s_m", "p95_300s_m", "err_60s_m", "err_300s_m")]  # fmt: skip
        ex = r.get("pre_gnss_excluded_mean")
        ex = "—" if ex is None else f"{ex:.0%}"
        lines.append(f"| {r['family']} | {r['fix']} | {r['lte']} | {' | '.join(cells)} | "
                     f"{b} | {mis} | {ex} |")  # fmt: skip
    return [*lines, ""]


def plot(summaries: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [(d["meta"], r) for d in summaries for r in d["summary"] if "p95_curve_m" in r]
    legs = list(dict.fromkeys(r["leg"] for _, r in rows))
    fams = list(dict.fromkeys(r["family"] for _, r in rows))
    fig, axes = plt.subplots(len(legs), len(fams), figsize=(5.2 * len(fams), 3.6 * len(legs)),
                             sharey=True, squeeze=False)  # fmt: skip
    for i, leg in enumerate(legs):
        for j, fam in enumerate(fams):
            ax = axes[i, j]
            for v in VARIANTS:
                hit = [(m, r) for m, r in rows if (r["leg"], r["family"], r["variant"]) ==
                       (leg, fam, v)]  # fmt: skip
                if not hit:
                    continue
                meta, r = hit[0]
                y = r["p95_curve_m"]
                x = [k * 5 for k in range(len(y))]
                ax.plot(x, y, color=COLORS[v], lw={"no LTE": 1.5, "B+A": 1.5}.get(v, 2),
                        ls={"no LTE": "--", "B+A": ":"}.get(v, "-"),
                        label=f"{NAMES[v]}: worst {_m(r['t1_worst_m'])} m")  # fmt: skip
            ax.axhline(T1_M, color="0.5", lw=0.8)
            ax.text(300, T1_M * 1.15, "T1 25 m (TBC)", ha="right", fontsize=7, color="0.35")
            ax.set_yscale("log")
            ax.set_title(f"{SHORT.get(leg, leg)}, {fam}", fontsize=10)
            ax.set_xlabel("s after GPS loss")
            ax.grid(True, which="major", color="0.9", lw=0.6)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.legend(fontsize=7, frameon=False, loc="upper left")
        axes[i, 0].set_ylabel("p95 across runs of\nhorizontal error (m)")
    seeds = " and ".join(dict.fromkeys(d["meta"]["seeds"] for d in summaries))
    commits = " and ".join(dict.fromkeys(d["meta"]["commit"] for d in summaries))
    fig.suptitle(
        f"#147 told σ, sim (placeholder LTE model), seeds {seeds}, commit {commits}: "
        "95th percentile across runs at each second (ADR-0034's T1 statistic)",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_real(docs: list[dict], path: Path) -> None:
    """Real replays, pseudoranges only: each variant's 0–300 s p95 after the cut (median and
    worst cut) with its HPL bound rate; a row per session, a column per filter."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fams = list(dict.fromkeys(r["family"] for d in docs for r in d["aggregate"]
                              if r["family"] != "hold"))  # fmt: skip
    fig, axes = plt.subplots(len(docs), len(fams), figsize=(5.8 * len(fams), 4.4 * len(docs)),
                             sharey=True, squeeze=False)  # fmt: skip
    for row, doc in enumerate(docs):
        rows = [r for r in doc["aggregate"] if r["lte"] in ("told-pr", "none")]
        for ax, fam in zip(axes[row], fams, strict=True):
            rs = [r for r in rows if r["family"] == fam]
            x = list(range(len(rs)))
            med = [max(r["p95_300s_m_median"], 0.1) for r in rs]
            worst = [max(r["p95_300s_m_worst"], 0.1) for r in rs]
            ax.vlines(x, med, worst, color="0.6", lw=1.5)
            ax.scatter(x, med, s=40, color="#2a78d6", zorder=3, label="median cut")
            ax.scatter(x, worst, s=60, marker="_", color="0.2", zorder=3, label="worst cut")
            for k, r in zip(x, rs, strict=True):
                if "hpl_bound" in r:
                    ax.text(k, worst[k] * 1.8, f"{r['hpl_bound']:.0%}", ha="center", fontsize=7,
                            color="0.3")  # fmt: skip
            ax.axhline(T1_M, color="0.5", lw=0.8)
            ax.text(-0.4, T1_M * 1.15, "T1 25 m (TBC)", ha="left", fontsize=7, color="0.35")
            ax.set_xticks(x, [r["fix"] for r in rs], rotation=40, ha="right", fontsize=8)
            ax.set_yscale("log")
            ax.set_ylim(0.1, 3e5)
            ax.set_title(f"{doc['meta']['session']}, {fam}", fontsize=9)
            ax.grid(True, axis="y", which="major", color="0.9", lw=0.6)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
        axes[row, 0].set_ylabel("p95 horizontal error,\n0–300 s after the cut (m)")
    axes[0, 0].legend(fontsize=7, frameon=False, loc="upper left")
    m = docs[0]["meta"]
    fig.suptitle(
        "#147, real static sessions (replay, GPS cut in software at 5 times each), LTE "
        f"pseudoranges only, src {m.get('src_commit', '?')}; label: HPL ≥ error, all fixes",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    sims = [json.loads(p.read_text()) for p in sorted(a.src.glob("summary-*.json"), reverse=True)]
    lines = sim_tables(sims)
    reals = [json.loads(p.read_text()) for p in sorted(a.src.glob("real*.json"))]
    for doc in reals:
        lines += real_table(doc)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "tables.md").write_text("\n".join(lines))
    if sims:
        plot(sims, a.out / "t1_curves.png")
    if reals:
        plot_real(reals, a.out / "real_replay.png")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
