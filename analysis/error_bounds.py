"""Bound tower-error settings from the MedComNet 2024 ray-traced 5G dataset (issue #50).

That repository has no license, so its data is only read locally for comparison and never
copied here: git clone https://github.com/Ita97/MedComNet2024_5G_pos_meas <dir>
Then: python analysis/error_bounds.py <dir>

For each file it compares the TDOA with the geometric range difference. "Link bias" is the mean
error of one tower pair at one spot, and "scatter" is how much that link varies between Monte
Carlo runs. A bias much larger than the scatter means the error persists rather than averaging
out. The data is simulated for pedestrians in Milan, so it bounds our settings, nothing more.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

FILES = {
    "5x5_square_10MHz": "clear, 10 MHz",
    "5x5_square_100MHz": "clear, 100 MHz",
    "trajectory_10MHz": "blocked, 10 MHz",
    "trajectory_100MHz": "blocked, 100 MHz",
}


def analyse(path: Path) -> dict:
    with open(path, newline="") as f:
        epochs = defaultdict(list)
        for r in csv.DictReader(f):
            epochs[(r["UE_x"], r["UE_y"], r["UE_z"], r["timestamp"])].append(r)
    links = defaultdict(list)
    for key, towers in epochs.items():
        ue = np.array(key[:3], float)
        position = lambda r: np.array([float(r["BS_x"]), float(r["BS_y"]), float(r["BS_z"])])  # noqa: E731
        reference = np.linalg.norm(position(towers[0]) - ue)
        for r in towers[1:]:
            if r["tdoa"].lower() != "nan":
                error = float(r["tdoa"]) - (np.linalg.norm(position(r) - ue) - reference)
                links[(key[0], key[1], r["BS_x"], r["BS_y"])].append(error)
    bias = np.array([np.mean(v) for v in links.values()])
    return {
        "link_bias_std_m": float(np.std(bias)),
        "link_bias_p95_m": float(np.percentile(np.abs(bias), 95)),
        "scatter_median_m": float(np.median([np.std(v) for v in links.values()])),
    }


def main(folder: str) -> None:
    print("| Case | Link bias std (m) | Link bias p95 (m) | Scatter median (m) |")
    print("| --- | --- | --- | --- |")
    for name, label in FILES.items():
        r = analyse(Path(folder) / f"{name}.csv")
        print(
            f"| {label} | {r['link_bias_std_m']:.1f} | {r['link_bias_p95_m']:.1f} "
            f"| {r['scatter_median_m']:.1f} |"
        )


if __name__ == "__main__":
    main(sys.argv[1])
