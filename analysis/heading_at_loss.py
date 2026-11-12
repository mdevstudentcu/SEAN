"""Heading at GPS loss (#276): what the GPS-good phase leaves the IMU filter, and what S-turns
before the cut and a magnetometer change after it.

    python analysis/heading_at_loss.py --seeds 20 --jobs 3

The challenge drone leg's `outage` entry (`challenge-drone-outage`, ADR-0030): 60 s of GPS, then
GPS lost. Runs end 300 s after the loss (T1's window), so `duration_s` is cut to 360 s; draws
then differ from the full 720 s benchmark runs, and every condition here shares them. Variants
are built from that committed entry here, nothing is a new scenario file:

- path `plain`: the leg as committed. `s-turns`: S-turns while GPS is good (`trajectory.py`
  `manoeuvres`, TURNS below; every value TBC, from report 7.4's 1-3 m/s^2 for 5-10 s,
  alternating).
- every run carries a magnetometer (`mag`, `sim/sensors.py` MAG: Student-t per-flight bias of
  scale 2.5 deg, 1 deg white noise, all TBC). `ekf-imu` ignores it, so its runs are the leg's own;
  `ekf-imu-mag` (opt-in, ADR-0051 Proposed) uses it.
- `radio`: with the leg's LTE records, or with them dropped (`no LTE`: IMU, baro and, for
  `ekf-imu-mag`, the magnetometer alone after the loss). The ablation reads which of LTE and
  heading the filter misses more (REQ-06: reported as it comes out).
- `tactical`: the same leg with a tactical-grade IMU in the sim (TACTICAL, figures recalled for
  an HG4930-class unit, TBC) and no LTE, so the IMU coasts alone after the loss (report 7.4,
  check 4: about 1 to 3 m at 60 s). Filter spec: the payload's MPU6050 (`filter MPU6050`) or
  TACTICAL_SPEC (`filter tactical`), and once with the heading floor at 0.3 deg instead of 3.

Per run: the filter's heading error at the loss (the z part of the rotation between its attitude
and the truth's, deg) and its own heading 1-sigma there; the horizontal error at each second
0..300 s after the loss. Per condition, ADR-0034's statistic: the 95th percentile across runs at
each second, worst over 0-300 s (T1, 25 m) and over 0-120 s (fallback, 50 m), with the number of
runs. Heading at loss is also related to the error: Spearman's rank correlation across runs of
|heading error| with the 120 s and 300 s errors.

Writes summary.md, summary.json and heading_at_loss.png into `--out`
(default analysis/results/heading-276/).
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np

from pnt import nav
from pnt.core.time import s_to_ns
from pnt.experiments import _map
from pnt.metrics import gps_loss
from pnt.nav import cells
from pnt.nav.ekf import EKF
from pnt.nav.imu import DEG, G, ImuSpec, rotation
from pnt.sim import sensors, trajectory
from pnt.sim.scenario import T0_NS, generate, load

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "analysis" / "results" / "heading-276"
SCENARIO = "challenge-drone-outage"
LOSS_S = 60.0  # the entry's GPS loss (checked in `variant`)
WINDOW_S = 300  # T1's window
T1_M, FALLBACK_M, FALLBACK_S = 25.0, 50.0, 120  # ADR-0034
# S-turns while GPS is good (TBC): a weave of about 2 m/s^2 peak, alternating every 7.5 s, from
# 5 s to 55 s, so it ends 5 s before the loss
TURNS = {"start_s": 5.0, "end_s": 55.0, "accel_mps2": 2.0, "period_s": 15.0}
MAG = {"rate_hz": 10}  # sim/sensors.py MAG defaults (TBC); rate TBC
# A tactical-grade IMU (TBC): figures recalled for an HG4930-class unit (report 7.4 table: gyro
# bias instability 0.25-0.45 deg/h), not a datasheet. Quantisation fine enough not to matter.
TACTICAL = {
    "gyro_noise_dps_rthz": 0.05 / 60,  # ARW 0.05 deg/sqrt(h)
    "accel_noise_ug_rthz": 85.0,  # VRW 0.05 m/s/sqrt(h)
    "gyro_bias_dps": 1.0 / 3600,  # 1 deg/h left after start-up
    "accel_bias_mg": 0.5,
    "gyro_instability_dph": 0.3,
    "accel_instability_ug": 25.0,
    "instability_tau_s": 100.0,
    "scale_error": 3e-4,
    "gyro_lsb_dps": 1e-6,
    "accel_lsb_g": 1e-7,
}
# The filter's view of the same unit (TBC). Unmodelled-error terms: not tuned, scaled down from
# the MPU6050's by about the gyro noise ratio
TACTICAL_SPEC = ImuSpec(
    accel_noise=85e-6 * G,
    gyro_noise=0.05 / 60 * DEG,
    accel_bias=0.5e-3 * G,
    gyro_bias=1.0 / 3600 * DEG,
    accel_bias_rw=25e-6 * G * math.sqrt(2 / 100.0),
    gyro_bias_rw=0.3 * DEG / 3600 * math.sqrt(2 / 100.0),
    accel_extra=0.002,
    gyro_extra=0.002 * DEG,
)
# The alignment's heading limit, opt-in (TBC). The default (180 deg, `nav/imu.py`) accepts a
# window whose heading 1-sigma is near 100 deg; from such an error the linearised filter does not
# recover (it settles on a wrong heading and gates GNSS out). Below it, a window is refused and the
# next one tried. 60 deg: above the 33-47 deg this leg's S-turn windows give, below the 82-102 deg
# of the first window, which catches only the start of the weave (seeds 0-2, not a tuning)
ALIGN = {"imu": {"max_yaw_sigma_deg": 60.0}}
# Filters on the payload's IMU: (name in the table, estimator, filter options over the registry's)
MPU_FILTERS = [
    ("ekf-imu", "ekf-imu", None),
    ("ekf-imu, align <= 60 deg", "ekf-imu", ALIGN),
    ("ekf-imu-mag", "ekf-imu-mag", None),
]
# (label, path, radio, IMU in the sim, estimator, filter options)
CONDITIONS = [
    (f"{path} / {'LTE' if radio else 'no LTE'} / {name}", path, radio, "mpu", est, extra)
    for radio in (True, False)
    for path in ("plain", "s-turns")
    for name, est, extra in MPU_FILTERS
]
TAC = {"spec": TACTICAL_SPEC, "max_yaw_sigma_deg": 60.0}
CONDITIONS += [
    (
        "tactical, plain / no LTE / filter tactical",
        "plain",
        False,
        "tactical",
        "ekf-imu",
        {"imu": TAC},
    ),
    (
        "tactical, s-turns / no LTE / filter MPU6050, align <= 60 deg",
        "s-turns",
        False,
        "tactical",
        "ekf-imu",
        ALIGN,
    ),
    (
        "tactical, s-turns / no LTE / filter tactical",
        "s-turns",
        False,
        "tactical",
        "ekf-imu",
        {"imu": TAC},
    ),
    (
        "tactical, s-turns / no LTE / filter tactical, floor 0.3 deg",
        "s-turns",
        False,
        "tactical",
        "ekf-imu",
        {"imu": {**TAC, "min_yaw_sigma_deg": 0.3}},
    ),
]


def variant(path: str, imu: str) -> dict:
    """The leg's outage entry, cut to the T1 window, with a magnetometer, S-turns if asked and
    the tactical IMU if asked (module docstring)."""
    spec = load(SCENARIO)
    loss = gps_loss(spec, T0_NS)
    assert loss is not None and loss[0] == T0_NS + s_to_ns(LOSS_S), "the entry's loss moved"
    spec["duration_s"] = LOSS_S + WINDOW_S + 1.0
    spec["sources"] = {**spec["sources"], "mag": dict(MAG)}
    if path == "s-turns":
        spec["trajectory"] = {**spec["trajectory"], "manoeuvres": dict(TURNS)}
    if imu == "tactical":
        spec["sources"]["imu"] = {**spec["sources"]["imu"], **TACTICAL}
    return spec


def horizontal_accel(spec: dict) -> dict:
    """The truth's horizontal acceleration while GPS is good (report 7.4, check 2)."""
    traj = {**spec["trajectory"], "_origin_llh": spec.get("origin_llh")}
    t = np.arange(0.0, LOSS_S, 0.1)
    a = np.hypot(*trajectory.kinematics(traj, t).acc[:, :2].T)
    return {
        "rms_mps2": float(np.sqrt(np.mean(a**2))),
        "peak_mps2": float(a.max()),
        "s_over_1_mps2": float(np.sum(a > 1.0) * 0.1),
    }


def probed(estimator: str, measurements, origin_llh, probe_ns: int, **extra):
    """The registry's `estimator` as `nav.estimate` runs it (same receivers, cells attached,
    `ekf.run`'s loop), with `extra` filter options over its own, keeping the filter so its
    attitude can be read at `probe_ns`: (estimates, attitude at the probe or None, its heading
    1-sigma in rad, the magnetometer bias state and its 1-sigma in rad, or None)."""
    fn = nav.ESTIMATORS[estimator]
    keep = nav.receivers(fn)
    config = {**fn.keywords}
    for k, v in extra.items():
        config[k] = {**config.get(k, {}), **v} if isinstance(v, dict) else v
    ekf = EKF(origin_llh=origin_llh, **config)
    out, probe = [], (None, math.nan, None)
    next_epoch = None
    for m in cells.attach(measurements, origin_llh):
        if m.receiver not in keep:
            continue
        if ekf.x is not None:
            if next_epoch is None:
                next_epoch = (ekf.t_ns // ekf_epoch() + 1) * ekf_epoch()
            while next_epoch <= m.t_ns:
                ekf.predict(next_epoch)
                out.append(ekf.estimate())
                if next_epoch == probe_ns:
                    probe = _attitude(ekf)
                next_epoch += ekf_epoch()
        ekf.process(m)
    return out, *probe


def ekf_epoch() -> int:
    return 100_000_000  # `ekf.run`'s default epoch


def _attitude(ekf: EKF):
    imu = ekf.imu
    if imu.R is None:
        return None, math.nan, None
    i = imu.att.start + 2
    R = rotation(ekf.x[imu.att]) @ imu.R
    b = ekf.mag_bias_idx
    mag = None if b is None else (float(ekf.x[b]), float(math.sqrt(ekf.P[b, b])))
    return R, float(math.sqrt(ekf.P[i, i])), mag


def heading_error(R_est: np.ndarray, R_true: np.ndarray) -> float:
    """The vertical part of the rotation from the true attitude to the filter's (rad): the
    filter's attitude error state's heading component, with the opposite sign."""
    from scipy.spatial.transform import Rotation

    return float(Rotation.from_matrix(R_est @ R_true.T).as_rotvec()[2])


def curve(estimates, truth) -> list[float | None]:
    """Horizontal error (m) at each second 0..WINDOW_S after the loss, as
    challenge_baseline.error_curve pairs it: the first epoch at or after loss + k s."""
    tmap = {g.t_ns: g for g in truth}
    pairs = [(e, tmap[e.t_ns]) for e in estimates if e.t_ns in tmap]
    t = np.array([e.t_ns for e, _ in pairs])
    err = np.array([math.hypot(*np.subtract(e.pos_enu, g.pos_enu)[:2]) for e, g in pairs])
    start = T0_NS + s_to_ns(LOSS_S)
    out = []
    for k in range(WINDOW_S + 1):
        at = start + s_to_ns(k)
        i = int(np.searchsorted(t, at))
        out.append(float(err[i]) if i < len(t) and t[i] - at < s_to_ns(1) else None)
    return out


def one(seed: int, path: str, imu: str) -> dict:
    """Every condition on this path and IMU, for one seed: one generated run each."""
    spec = variant(path, imu)
    run = generate(spec, seed=seed)
    probe_ns = T0_NS + s_to_ns(LOSS_S)
    traj = {**spec["trajectory"], "_origin_llh": spec.get("origin_llh")}
    R_true = trajectory.kinematics(traj, np.array([LOSS_S])).rot[0]
    # The run's magnetometer bias, from its records against the truth (white noise averages out)
    mag = [m for m in run.measurements if m.kind == "heading"]
    t_mag = np.array([(m.t_ns - T0_NS) / 1e9 for m in mag])
    psi_true = sensors.heading_of(trajectory.kinematics(traj, t_mag).rot)
    res = np.array([m.value[0] for m in mag]) - psi_true
    mag_bias = float(np.angle(np.mean(np.exp(1j * res))))
    out = {}
    for label, p, radio, grade, est, extra in CONDITIONS:
        if (p, grade) != (path, imu):
            continue
        meas = run.measurements if radio else [m for m in run.measurements if m.source != "lte"]
        e, R, yaw_sigma, mag_state = probed(
            est, meas, spec["origin_llh"], probe_ns, **(extra or {})
        )
        out[label] = {
            "heading_err_deg": None if R is None else math.degrees(heading_error(R, R_true)),
            "heading_sigma_deg": math.degrees(yaw_sigma),
            "mag_bias_true_deg": math.degrees(mag_bias),
            "mag_bias_est_deg": None if mag_state is None else math.degrees(mag_state[0]),
            "mag_bias_sigma_deg": None if mag_state is None else math.degrees(mag_state[1]),
            "curve": curve(e, run.truth),
        }
    return out


def p95_curve(curves: list[list]) -> np.ndarray:
    a = np.array([[np.nan if v is None else v for v in c] for c in curves], float)
    return np.nanpercentile(a, 95, axis=0)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def summarise(results: dict[str, list[dict]]) -> dict:
    out = {}
    for label, runs in results.items():
        p95 = p95_curve([r["curve"] for r in runs])
        err = np.array([r["heading_err_deg"] for r in runs], float)
        sig = np.array([r["heading_sigma_deg"] for r in runs], float)
        e120 = np.array([r["curve"][120] for r in runs], float)
        e300 = np.array([r["curve"][WINDOW_S] for r in runs], float)
        aligned = ~np.isnan(err)
        row = {
            "runs": len(runs),
            "aligned_at_loss": int(aligned.sum()),
            "heading_err_abs_median_deg": float(np.median(np.abs(err[aligned])))
            if aligned.any()
            else None,
            "heading_err_abs_p95_deg": float(np.percentile(np.abs(err[aligned]), 95))
            if aligned.any()
            else None,
            "heading_sigma_median_deg": float(np.nanmedian(sig)) if aligned.any() else None,
            "p95_60s_m": float(p95[60]),
            "p95_120s_m": float(p95[120]),
            "p95_300s_m": float(p95[WINDOW_S]),
            "t1_worst_m": float(np.max(p95[: WINDOW_S + 1])),
            "t1_worst_s": int(np.argmax(p95[: WINDOW_S + 1])),
            "fallback_worst_m": float(np.max(p95[: FALLBACK_S + 1])),
            "rho_120s": spearman(np.abs(err[aligned]), e120[aligned])
            if aligned.sum() > 2
            else None,
            "rho_300s": spearman(np.abs(err[aligned]), e300[aligned])
            if aligned.sum() > 2
            else None,
            "p95_curve": [round(float(v), 2) for v in p95],
        }
        mag_err = [
            r["mag_bias_est_deg"] - r["mag_bias_true_deg"]
            for r in runs
            if r["mag_bias_est_deg"] is not None
        ]
        if mag_err:
            row["mag_bias_true_abs_max_deg"] = float(
                max(abs(r["mag_bias_true_deg"]) for r in runs)
            )
            row["mag_bias_err_abs_median_deg"] = float(np.median(np.abs(mag_err)))
        out[label] = row
    return out


def fmt(v, nd=1) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{nd}f}"


def verdict(row: dict) -> str:
    t1 = "met" if row["t1_worst_m"] <= T1_M else "missed"
    fb = "met" if row["fallback_worst_m"] <= FALLBACK_M else "missed"
    return f"T1 {t1}, fallback {fb}"


def write(out: Path, summary: dict, accel: dict, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps({"meta": meta, "accel_gps_good": accel, "conditions": summary}, indent=1)
    )
    lines = [
        "# Heading at GPS loss (#276)",
        "",
        f"Commit `{meta['commit']}`, seeds 0–{meta['seeds'] - 1} ({meta['seeds']} runs per row),"
        f" `{meta['command']}`, {meta['runtime_s']:.0f} s. Scenario: `{SCENARIO}` cut to "
        f"{LOSS_S + WINDOW_S:.0f} s, built in `analysis/heading_at_loss.py` (module docstring). "
        "Every sensor value is `TBC`; sim only.",
        "",
        "Statistic: ADR-0034's, the 95th percentile across runs at each second after GPS loss; "
        "*worst 0–300 s* is T1's (25 m), *worst 0–120 s* the fallback's (50 m). Heading error at "
        "loss: |vertical part of the rotation between the filter's attitude and the truth| at "
        "the loss; σ is the filter's own. ρ: Spearman rank correlation across runs of |heading "
        "error at loss| with the error at 120 s and 300 s.",
        "",
        "## Horizontal acceleration while GPS is good (0–60 s)",
        "",
        "| Path | RMS (m/s²) | Peak (m/s²) | Time over 1 m/s² (s) |",
        "| --- | --- | --- | --- |",
    ]
    for path, a in accel.items():
        lines.append(
            f"| {path} | {a['rms_mps2']:.2f} | {a['peak_mps2']:.2f} | {a['s_over_1_mps2']:.1f} |"
        )
    lines += [
        "",
        "## Error after GPS loss against heading at loss",
        "",
        "| Condition | Aligned at loss | Heading err. median / p95 (°) | Filter σ median (°) "
        "| p95 at 60 / 120 / 300 s (m) | Worst 0–120 s (m) | Worst 0–300 s (m) | ρ 120 s / "
        "300 s | Verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, r in summary.items():
        lines.append(
            f"| {label} | {r['aligned_at_loss']}/{r['runs']} | "
            f"{fmt(r['heading_err_abs_median_deg'])} / {fmt(r['heading_err_abs_p95_deg'])} | "
            f"{fmt(r['heading_sigma_median_deg'])} | {fmt(r['p95_60s_m'])} / "
            f"{fmt(r['p95_120s_m'])} / {fmt(r['p95_300s_m'])} | {fmt(r['fallback_worst_m'])} | "
            f"{fmt(r['t1_worst_m'])} (at {r['t1_worst_s']} s) | {fmt(r['rho_120s'], 2)} / "
            f"{fmt(r['rho_300s'], 2)} | {verdict(r)} |"
        )
    mags = {k: v for k, v in summary.items() if "mag_bias_err_abs_median_deg" in v}
    if mags:
        lines += [
            "",
            "## Magnetometer bias learned while GPS was good",
            "",
            "| Condition | Largest true bias (°) | Median bias error at loss (°) |",
            "| --- | --- | --- |",
        ]
        for label, r in mags.items():
            lines.append(
                f"| {label} | {r['mag_bias_true_abs_max_deg']:.1f} | "
                f"{r['mag_bias_err_abs_median_deg']:.2f} |"
            )
    lines += ["", "## Ablation: LTE against heading (REQ-06)", ""]
    lines += ablation(summary)
    (out / "summary.md").write_text("\n".join(lines) + "\n")


ABLATION_PATHS = ("plain", "s-turns")


def ablation(summary: dict) -> list[str]:
    """REQ-06's ablation, per path, from `ekf-imu-mag` with LTE: remove one aid and see what T1's
    worst second (and the fallback's) does. Removing LTE is `no LTE / ekf-imu-mag`, removing the
    magnetometer `LTE / ekf-imu`. REQ-06 asks that removing the radio costs more than removing
    any single other aid; a negative change means the run was better without that aid."""
    rows = [
        "From `ekf-imu-mag` with LTE, one aid removed. Change in the worst p95 second "
        "(0–300 s / 0–120 s, m); negative: better without it. REQ-06 needs removing LTE to cost "
        "more than removing the magnetometer.",
        "",
        "| Path | Both aids | Remove LTE | Remove magnetometer | Costs more to remove | REQ-06 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path in ABLATION_PATHS:
        both = summary.get(f"{path} / LTE / ekf-imu-mag")
        no_lte = summary.get(f"{path} / no LTE / ekf-imu-mag")
        no_mag = summary.get(f"{path} / LTE / ekf-imu")
        if not (both and no_lte and no_mag):
            continue

        cost_lte = no_lte["t1_worst_m"] - both["t1_worst_m"]
        cost_mag = no_mag["t1_worst_m"] - both["t1_worst_m"]
        first = "LTE" if cost_lte > cost_mag else "heading (magnetometer)"
        rows.append(
            f"| {path} | {both['t1_worst_m']:,.0f} / {both['fallback_worst_m']:,.0f} | "
            f"{_change(no_lte, both)} | {_change(no_mag, both)} | {first} | "
            f"{'met' if first == 'LTE' else 'not met'} |"
        )
    return rows


def _change(row: dict, both: dict) -> str:
    """'worst 0-300 s / 0-120 s (their changes from `both`)', m."""
    d300 = row["t1_worst_m"] - both["t1_worst_m"]
    d120 = row["fallback_worst_m"] - both["fallback_worst_m"]
    worst = f"{row['t1_worst_m']:,.0f} / {row['fallback_worst_m']:,.0f}"
    return f"{worst} ({d300:+,.0f} / {d120:+,.0f})"


# The filters' colours: the repo's categorical order (analysis/challenge_baseline.py); the
# registry's default filter in recessive ink
COLORS = {
    "ekf-imu": "#52514e",
    "ekf-imu, align <= 60 deg": "#2a78d6",
    "ekf-imu-mag": "#eb6834",
    "tactical": "#1baf7a",
}
INK, GRID = "#52514e", "#e4e3df"
CURVES = [  # (condition, colour key, legend text): the right panel
    ("s-turns / no LTE / ekf-imu", "ekf-imu", "MPU6050, ekf-imu"),
    ("s-turns / no LTE / ekf-imu, align <= 60 deg", "ekf-imu, align <= 60 deg",
     "MPU6050, ekf-imu, align ≤ 60°"),
    ("s-turns / no LTE / ekf-imu-mag", "ekf-imu-mag", "MPU6050, ekf-imu-mag"),
    ("tactical, s-turns / no LTE / filter tactical", "tactical", "tactical IMU, align ≤ 60°"),
]  # fmt: skip


def figure(out: Path, summary: dict, results: dict) -> None:
    """Left: each run's |heading error at loss| against its error 120 s later, payload IMU, no
    LTE. Right: ADR-0034's p95 curve after the loss, S-turns, no LTE."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.33, 7.5), dpi=110)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.8, bottom=0.2, wspace=0.22)
    for ax in (a1, a2):
        ax.grid(True, which="major", color=GRID, lw=0.8)
        ax.tick_params(labelsize=12)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for _, path, radio, grade, est, extra in CONDITIONS:
        if radio or grade != "mpu":
            continue
        name = next(n for n, e, x in MPU_FILTERS if e == est and x == extra)
        label = f"{path} / no LTE / {name}"
        runs = [r for r in results.get(label, []) if r["heading_err_deg"] is not None]
        x = [max(abs(r["heading_err_deg"]), 0.05) for r in runs]
        y = [r["curve"][FALLBACK_S] for r in runs]
        a1.plot(x, y, "o" if path == "plain" else "^", ms=8, ls="", color=COLORS[name],
                alpha=0.75, mec="white", mew=1)  # fmt: skip
    a1.set_xscale("log")
    a1.set_yscale("log")
    a1.set_xlabel("|heading error| at GPS loss (°)", fontsize=13)
    a1.set_ylabel("horizontal error 120 s after loss (m)", fontsize=13)
    a1.set_title("Payload IMU, no LTE: each run", fontsize=14, loc="left")
    t = np.arange(WINDOW_S + 1)
    for label, key, text in CURVES:
        if label in summary:
            a2.plot(t, summary[label]["p95_curve"], lw=2, color=COLORS[key], label=text)
    for lim, txt in ((T1_M, "T1 25 m"), (FALLBACK_M, "fallback 50 m")):
        a2.axhline(lim, color=INK, lw=1, ls=(0, (4, 3)))
        a2.text(WINDOW_S, lim * 1.08, txt, ha="right", va="bottom", fontsize=11, color=INK)
    a2.set_yscale("log")
    a2.set_xlabel("time after GPS loss (s)", fontsize=13)
    a2.set_ylabel("95th percentile across runs (m)", fontsize=13)
    a2.set_title("S-turns before the loss, no LTE: p95 across runs", fontsize=14, loc="left")
    handles = [Line2D([], [], lw=2, color=COLORS[k], label=txt) for _, k, txt in CURVES]
    handles += [
        Line2D([], [], marker="o", ls="", ms=8, color=INK, label="plain path"),
        Line2D([], [], marker="^", ls="", ms=8, color=INK, label="S-turns"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=12, frameon=False,
               bbox_to_anchor=(0.5, 0.01))  # fmt: skip
    n = len(next(iter(results.values())))
    fig.text(0.01, 0.97, "Heading at GPS loss: S-turns, alignment limit and magnetometer",
             fontsize=18, weight="bold", va="top")  # fmt: skip
    fig.text(0.01, 0.91, f"challenge-drone-outage cut to 360 s, {n} runs per condition, commit "
             f"{_commit()}; sim, every value TBC. Left colours as right (MPU6050 filters).",
             fontsize=12, color=INK, va="top")  # fmt: skip
    fig.savefig(out / "heading_at_loss.png")
    plt.close(fig)


def _commit() -> str:
    return subprocess.run(
        ["git", "describe", "--always", "--dirty", "--abbrev=7"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--only", choices=("mpu", "tactical"), default=None)
    args = ap.parse_args(argv)
    t0 = time.time()
    groups = sorted({(p, g) for _, p, _, g, _, _ in CONDITIONS if args.only in (None, g)})
    tasks = [(s, p, g) for p, g in groups for s in range(args.seeds)]
    done = _map(one, tasks, args.jobs)
    results: dict[str, list] = {}
    for d in done:
        for label, r in d.items():
            results.setdefault(label, []).append(r)
    results = {lab: results[lab] for lab, *_ in CONDITIONS if lab in results}
    summary = summarise(results)
    accel = {p: horizontal_accel(variant(p, "mpu")) for p in ABLATION_PATHS}
    meta = {
        "commit": _commit(),
        "seeds": args.seeds,
        "command": "python analysis/heading_at_loss.py "
        + " ".join(f"{k} {v}" for k, v in (("--seeds", args.seeds), ("--jobs", args.jobs))),
        "runtime_s": time.time() - t0,
        "turns": TURNS,
        "mag": MAG,
        "tactical": TACTICAL,
    }
    write(args.out, summary, accel, meta)
    figure(args.out, summary, results)
    print((args.out / "summary.md").read_text())


if __name__ == "__main__":
    main()
