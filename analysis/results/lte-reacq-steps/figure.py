"""Before/after figure from summary.json (written next to it as before_after.png)."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BEFORE, AFTER = "#2a78d6", "#eb6834"


def main() -> None:
    s = json.loads((HERE / "summary.json").read_text())
    sessions = list(s["front_end"])
    panels = [
        ("Re-find steps over 100 m (%)", lambda v: 100 * v["steps"]["over_100m"]),
        ("Median re-find step (m)", lambda v: v["steps"]["median_m"]),
        ("Epochs with two strong cells\nwithin 100 m of truth (%)",
         lambda v: 100 * v["coverage"]["two_strong_within_100m"]),
    ]  # fmt: skip
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), facecolor="#fcfcfb")
    for ax, (title, get) in zip(axes, panels, strict=True):
        for i, name in enumerate(sessions):
            b, a = (get(s["front_end"][name][k]) for k in ("before", "after"))
            ax.bar(i - 0.19, b, 0.36, color=BEFORE, label="before (#245 head)" if i == 0 else None)
            ax.bar(i + 0.19, a, 0.36, color=AFTER, label="after (this branch)" if i == 0 else None)
            for x, v in ((i - 0.19, b), (i + 0.19, a)):
                ax.text(x, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=MUTED)
        ax.set_xticks(range(len(sessions)), sessions, color=INK)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_facecolor("#fcfcfb")
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=MUTED, labelsize=8)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, loc="upper right", ncol=2)
    fig.suptitle("Real static captures, LTE pseudorange double differences against GPS truth",
                 fontsize=10, color=INK, x=0.01, ha="left")  # fmt: skip
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(HERE / "before_after.png", dpi=110)


if __name__ == "__main__":
    main()
