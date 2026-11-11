"""Scratch projection study (not for the repo): what would each candidate source buy?

uc01-realistic (accuracy_budget.spec_for): 120 s of GPS, then 300 s without. Candidate sources
are injected as records built from truth with stated error models, and run through the repo's
real EKF. A `velocity_enu` model is patched into the EKF here only (the repo has none).
Every value is a placeholder (TBC). Statistic: ADR-0034's per-second p95 across seeds.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, "analysis")
import accuracy_budget as ab  # noqa: E402

from pnt.core.measurement import Measurement  # noqa: E402
from pnt.nav import configured, ekf, estimate  # noqa: E402
from pnt.nav.imu import DEG, G, ImuSpec  # noqa: E402
from pnt.sim.scenario import T0_NS, generate  # noqa: E402

T_CAL, HORIZON = 120, 300


def _velocity(f, m):
    H = np.zeros((3, len(f.x)))
    H[:, ekf.VEL] = np.eye(3)
    return np.asarray(m.value) - f.x[ekf.VEL], H, np.diag(np.square(m.sigma)), True


ekf.MODELS["velocity_enu"] = _velocity


def _gm(rng, n, dt, sigma, tau):
    phi = math.exp(-dt / tau)
    x = np.empty(n)
    x[0] = rng.normal(0, sigma)
    for k in range(1, n):
        x[k] = phi * x[k - 1] + rng.normal(0, sigma * math.sqrt(1 - phi * phi))
    return x


def _truth_at(run, rate_hz):
    t = np.array([tr.t_ns for tr in run.truth])
    step = max(1, round(10 / rate_hz))  # truth is 10 Hz
    idx = np.arange(0, len(t), step)
    pos = np.array([run.truth[i].pos_enu for i in idx])
    vel = np.array([run.truth[i].vel_enu for i in idx])
    return t[idx], pos, vel


def velocity_records(run, seed, sigma, yaw_deg, scale, told, rate_hz=10.0):
    """Velocity over ground (optical flow + height, visual-inertial odometry, Doppler radar).
    Error: white `sigma` per axis, a slowly wandering heading error (Gauss-Markov, `yaw_deg`,
    300 s) that rotates the horizontal velocity, and a per-run scale error."""
    rng = np.random.default_rng([seed, 9001])
    t, _, vel = _truth_at(run, rate_hz)
    psi = np.deg2rad(_gm(rng, len(t), 1 / rate_hz, yaw_deg, 300.0))
    k = 1 + rng.normal(0, scale)
    c, s = np.cos(psi), np.sin(psi)
    ve = k * (c * vel[:, 0] - s * vel[:, 1])
    vn = k * (s * vel[:, 0] + c * vel[:, 1])
    v = np.column_stack([ve, vn, vel[:, 2]]) + rng.normal(0, sigma, (len(t), 3))
    return [
        Measurement(t_ns=int(a), source="cam", kind="velocity_enu", value=tuple(b),
                    sigma=(told, told, told))
        for a, b in zip(t, v, strict=True)
    ]  # fmt: skip


def fix_records(run, seed, sigma, rate_hz, availability, block_s=20.0, bias=0.0):
    """Absolute horizontal fixes (camera matched to a georeferenced map). White `sigma`, a
    Gauss-Markov map/registration bias (`bias`, 60 s), heard in blocks. Height is left to the
    barometer (vertical sigma 1 km)."""
    rng = np.random.default_rng([seed, 9002])
    t, pos, _ = _truth_at(run, rate_hz)
    ts = (t - T0_NS) / 1e9
    blocks = (ts // block_s).astype(int)
    keep = (rng.random(blocks.max() + 1) < availability)[blocks]
    b = (
        np.column_stack([_gm(rng, len(t), 1 / rate_hz, bias, 60.0) for _ in range(2)])
        if bias
        else 0
    )
    p = pos.copy()
    p[:, :2] += rng.normal(0, sigma, (len(t), 2)) + b
    told = math.hypot(sigma, bias)
    return [
        Measurement(t_ns=int(a), source="cam", kind="position_enu", value=tuple(q),
                    sigma=(told, told, 1000.0))
        for a, q, k in zip(t, p, keep, strict=True) if k
    ]  # fmt: skip


# Tactical-grade IMU (HG4930-class figures from memory, TBC): sim truth and the filter's spec
TACTICAL_SIM = dict(
    gyro_noise_dps_rthz=6.7e-4, accel_noise_ug_rthz=51.0, gyro_bias_dps=0.002, accel_bias_mg=1.7,
    gyro_instability_dph=0.25, accel_instability_ug=25.0, scale_error=3e-4,
    gyro_lsb_dps=1e-6, accel_lsb_g=1e-7,
)  # fmt: skip
TACTICAL_FILTER = ImuSpec(
    accel_noise=51e-6 * G, gyro_noise=6.7e-4 * DEG, accel_bias=1.7e-3 * G, gyro_bias=0.002 * DEG,
    accel_bias_rw=25e-6 * G * math.sqrt(2 / 100),
    gyro_bias_rw=0.25 * DEG / 3600 * math.sqrt(2 / 100),
    accel_extra=0.005, gyro_extra=0.02 * DEG,
)  # fmt: skip

IRIDIUM = dict(model="leo_doppler", rate_hz=1, tle_file="tle-iridium-20261108.txt",
               sigma_mps=1.0, elevation_mask_deg=8.2, receiver_clock=True)  # fmt: skip
STARLINK = dict(model="leo_doppler", source="leo", rate_hz=1, tle_file="tle-starlink-20261110.txt",
                sigma_mps=0.2, elevation_mask_deg=25.0, pass_availability=0.5,
                carrier_hz=11.325e9, receiver_clock=True)  # fmt: skip

# name -> (spec edits, injections, estimator, estimator config)
V = {}


def variant(name, lte="none", leo=(), imu="mpu", inject=(), est="imu", clock=None, leg=False):
    V[name] = dict(lte=lte, leo=leo, imu=imu, inject=inject, est=est, clock=clock, leg=leg)


FLOW = ("vel", dict(sigma=0.3, yaw_deg=3.0, scale=0.02, told=0.5))  # optical flow, IMU heading
FLOW_MAG = ("vel", dict(sigma=0.3, yaw_deg=1.0, scale=0.02, told=0.4))  # + a heading reference
VIO = ("vel", dict(sigma=0.1, yaw_deg=0.3, scale=0.005, told=0.15))  # visual-inertial odometry
MAPFIX = ("fix", dict(sigma=8.0, rate_hz=0.5, availability=0.7, bias=5.0))  # map matching
MAPFIX_SPARSE = ("fix", dict(sigma=15.0, rate_hz=0.2, availability=0.3, bias=10.0))

variant("dead reckoning (IMU+baro)")
variant("LTE realistic, ekf-imu", lte="real")
variant("LTE realistic, ekf-calibrated", lte="real", est="cal")
variant("LTE 12 sites, ekf-calibrated", lte="twelve", est="cal")
variant("LTE + chip-scale atomic clock", lte="real", est="cal-csac", clock="csac")
variant("precise ranging 8 sites (5G PRS / carrier-phase class)", lte="precise", est="cal-precise")
variant("Iridium Doppler", leo=("iridium",))
variant("Iridium + Starlink Doppler", leo=("iridium", "starlink"))
variant("tactical IMU alone", imu="tactical", est="imu-tac")
variant("optical flow (3 deg heading)", inject=(FLOW,))
variant("optical flow + heading ref (1 deg)", inject=(FLOW_MAG,))
variant("visual-inertial odometry", inject=(VIO,))
variant("map-matching fixes, sparse (30 %)", inject=(MAPFIX_SPARSE,))
variant("map-matching fixes (70 %)", inject=(MAPFIX,))
variant("flow+heading + LTE realistic", lte="real", inject=(FLOW_MAG,), est="cal-imu")
variant("flow+heading + Iridium", leo=("iridium",), inject=(FLOW_MAG,))
variant("flow+heading + sparse map fixes", inject=(FLOW_MAG, MAPFIX_SPARSE))
variant("VIO + map fixes (70 %)", inject=(VIO, MAPFIX))
variant("tactical IMU + VIO + map fixes + precise ranging", lte="precise", imu="tactical",
        inject=(VIO, MAPFIX), est="cal-precise-tac")  # fmt: skip

variant("[leg] dead reckoning", leg=True)
variant("[leg] Iridium Doppler", leo=("iridium",), leg=True)
variant("[leg] optical flow (3 deg heading)", inject=(FLOW,), leg=True)
variant("[leg] optical flow + heading ref (1 deg)", inject=(FLOW_MAG,), leg=True)
variant("[leg] visual-inertial odometry", inject=(VIO,), leg=True)
variant("[leg] flow+heading + sparse map fixes", inject=(FLOW_MAG, MAPFIX_SPARSE), leg=True)
variant("[leg] flow+heading + Iridium", leo=("iridium",), inject=(FLOW_MAG,), leg=True)
variant("[leg] VIO + map fixes (70 %)", inject=(VIO, MAPFIX), leg=True)

CAL_PRECISE = dict(multipath_ratio=5 / 3, tower_position_sigma_m=5.0)
EST = {
    "imu": configured(ekf.run, motion="imu"),
    "cal": ekf.run_calibrated,
    "cal-imu": configured(ekf.run_calibrated, motion="imu"),
    "cal-csac": configured(ekf.run_calibrated, h0=8e-18 * (0.03 / 2) ** 2, h_2=2e-27),
    "cal-precise": configured(ekf.run_calibrated, **CAL_PRECISE),
    "imu-tac": configured(ekf.run, motion="imu", imu={"spec": TACTICAL_FILTER}),
    "cal-precise-tac": configured(
        ekf.run_calibrated, motion="imu", imu={"spec": TACTICAL_FILTER}, **CAL_PRECISE
    ),  # fmt: skip
}


def build(name, seed):
    v = V[name]
    spec = copy.deepcopy(ab.spec_for("uc01-realistic", T_CAL, HORIZON))
    src = spec["sources"]
    if v["leg"]:  # an open route: two turns in the GPS part, then a 2.4 km straight leg
        spec["trajectory"] = dict(
            type="waypoints",
            vehicle="multirotor",
            closed=False,
            speed_mps=8,
            corner_radius_m=40,
            points=[[0, 0, 40], [400, 0, 40], [400, 450, 40], [3400, 1200, 40]],
        )
    if v["lte"] == "none":
        del src["lte"]
        spec.pop("tower_clocks", None)
    elif v["lte"] == "twelve":
        src["lte"]["towers_from"]["count"] = 12
    elif v["lte"] == "precise":
        src["lte"]["towers_from"]["count"] = 8
        src["lte"].update(sigma_m=3.0, multipath={"sigma_m": 5.0, "tau_s": 30.0},
                          told_position_sigma_m=5.0)  # fmt: skip
    if v["clock"] == "csac":
        spec["clock"] = {"drift_ppb": 0.1, "rw_ns": 0.03}
    if v["imu"] == "tactical":
        src["imu"] = {"rate_hz": 100, **TACTICAL_SIM}
    for layer in v["leo"]:
        src[layer] = dict(IRIDIUM if layer == "iridium" else STARLINK)
    run = generate(spec, seed=seed)
    meas = list(run.measurements)
    for kind, kw in v["inject"]:
        meas += (velocity_records if kind == "vel" else fix_records)(run, seed, **kw)
    meas.sort(key=lambda m: (m.t_ns, m.source, m.kind, m.emitter))
    return spec, run, meas


def job(args):
    name, seed = args
    try:
        spec, run, meas = build(name, seed)
        est = list(estimate(EST[V[name]["est"]], meas, origin_llh=spec.get("origin_llh")))
        t = (np.array([e.t_ns for e in est]) - T0_NS) / 1e9
        tt = (np.array([tr.t_ns for tr in run.truth]) - T0_NS) / 1e9
        tp = np.array([tr.pos_enu for tr in run.truth])
        p = np.array([e.pos_enu for e in est])
        err = np.hypot(p[:, 0] - np.interp(t, tt, tp[:, 0]), p[:, 1] - np.interp(t, tt, tp[:, 1]))
        hpl = np.array([e.hpl_m if e.hpl_m is not None else np.nan for e in est])
        idx = np.clip(np.searchsorted(t, T_CAL + np.arange(HORIZON + 1) - 1e-6), 0, len(t) - 1)
        out = t >= T_CAL
        bound = float(np.nanmean(hpl[out] >= err[out])) if np.isfinite(hpl[out]).any() else None
        return name, seed, err[idx].tolist(), bound, None
    except Exception as exc:  # noqa: BLE001
        return name, seed, None, None, repr(exc)


def main():
    seeds = int(sys.argv[1])
    only = sys.argv[3:] or list(V)
    jobs = [(n, s) for n in only for s in range(seeds)]
    res: dict[str, list] = {n: [] for n in only}
    bounds: dict[str, list] = {n: [] for n in only}
    with ProcessPoolExecutor(int(sys.argv[2])) as ex:
        for name, seed, curve, bound, err in ex.map(job, jobs):
            if err:
                print("FAIL", name, seed, err, flush=True)
                continue
            res[name].append(curve)
            if bound is not None:
                bounds[name].append(bound)
    rows = {}
    print(f"\n{'variant':58s} runs  p95@60  p95@120  p95@300  worst0-120  worst0-300  HPL>=err")
    for n in only:
        if not res[n]:
            continue
        c = np.percentile(np.array(res[n]), 95, axis=0)
        b = float(np.mean(bounds[n])) if bounds[n] else float("nan")
        rows[n] = dict(runs=len(res[n]), p60=c[60], p120=c[120], p300=c[300],
                       w120=c[:121].max(), w300=c.max(), hpl_bound=b)  # fmt: skip
        r = rows[n]
        print(f"{n:58s} {r['runs']:4d} {r['p60']:7.0f} {r['p120']:8.0f} {r['p300']:8.0f} "
              f"{r['w120']:11.0f} {r['w300']:11.0f} {100 * b:8.0f}%", flush=True)  # fmt: skip
    Path(__file__).with_name("source_study.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
