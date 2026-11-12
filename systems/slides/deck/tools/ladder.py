"""Localization ladder for the deck: worst-second 95 % error, 0-300 s after GPS loss, drone leg (sim).
Sources: analysis/results/stacked-fixes-measured (PR #247/#262, seeds 0-49, ekf) and
analysis/results/tower-count (#208, seeds 0-19, clean errors, all 17 sites, baro+imu)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BG, FG, MUTED, LINE = "#1b2128", "#eef1f4", "#a3aeb9", "#3d4853"
OK, WARN, BAD, GREY = "#4cc283", "#e2a64a", "#f06a6a", "#8a96a3"
rows = [  # label, metres, colour, note
    ("No towers (barometer + dead reckoning)", 2909, GREY, ""),
    ("Towers, believing the radio's 2 m claim", 12507, BAD, ""),
    ("+ learn each tower's noise", 2474, WARN, ""),
    ("+ hop 13 LTE carriers (study)", 132, WARN, "payload can't hop yet"),
    ("  … on our measured radio noise", 105, WARN, ""),
    ("  … reflections as small as measured at rest", 51, OK, ""),
    ("Clean ranges, all 17 towers within 3 km", 10, OK, "holds ≤ 25 m for all 300 s"),
]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15})
fig, ax = plt.subplots(figsize=(12.8, 6.2), dpi=150)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
y = list(range(len(rows)))[::-1]
for yi, (lab, v, c, note) in zip(y, rows):
    ax.barh(yi, v, color=c, height=0.62, left=1)
    num = f"{v:,} m"
    ax.text(v * 1.12, yi, num, va="center", color=FG, fontsize=15, fontweight="bold",
            bbox=dict(facecolor=BG, edgecolor="none", pad=1.5))
    if note:
        ax.annotate(note, (v * 1.12, yi), xytext=(len(num) * 10.5 + 10, 0), textcoords="offset points",
                    va="center", color=MUTED, fontsize=12.5, bbox=dict(facecolor=BG, edgecolor="none", pad=1.5))
ax.set_xscale("log"); ax.set_xlim(5, 90000)
for x, lab, ha in ((25, "25 m target ", "right"), (50, " 50 m mentors", "left")):
    ax.axvline(x, color=MUTED, ls="--", lw=1.4)
    ax.text(x, len(rows) - 0.42, lab, color=MUTED, fontsize=12, va="bottom", ha=ha)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], color=FG, fontsize=14)
ax.tick_params(axis="x", colors=MUTED, labelsize=12); ax.tick_params(axis="y", length=0)
ax.set_xticks([10, 100, 1000, 10000]); ax.set_xticklabels(["10 m", "100 m", "1 km", "10 km"])
for s in ax.spines.values(): s.set_visible(False)
ax.grid(axis="x", color=LINE, lw=0.8); ax.set_axisbelow(True)
ax.set_xlabel("worst-second 95 % error, first 5 min after GPS loss (log scale)", color=MUTED, fontsize=12)
fig.tight_layout()
fig.savefig("public/proof/ladder.png", facecolor=BG)
print("ok")
