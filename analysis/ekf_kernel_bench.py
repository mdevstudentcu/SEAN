"""#255, ADR-0054: time the EKF's compiled kernels against the dense numpy products they replace,
on the filter's own matrices.

Runs `ekf` and `ekf-imu` over the given scenarios (seed 0), keeps a sample of the (F, P, Q) each
predict sees and the (P, K, H, R) each update sees, then times each form per state count. Run it
with one BLAS thread (OPENBLAS_NUM_THREADS=1), as `pnt eval` workers do.

    python analysis/ekf_kernel_bench.py [scenario ...]
"""

from __future__ import annotations

import random
import sys
import time
from collections import defaultdict

import numpy as np

from pnt.nav import _kernels, estimate
from pnt.sim.scenario import generate, load

SCENARIOS = ("challenge-drone-hop-nominal", "challenge-drone-nominal")
KEEP = 20  # samples kept per state count


def capture(names) -> tuple[dict, dict]:
    """Samples of the predict's (F, P, Q) by n and the update's (P, K, H, R) by (n, m)."""
    rng = random.Random(1)
    predicts, updates = defaultdict(list), defaultdict(list)
    propagate, joseph = _kernels.propagate, _kernels.joseph

    def keep(store, key, args):
        if len(store[key]) < KEEP and rng.random() < 0.2:
            store[key].append(tuple(np.atleast_2d(a).copy() for a in args))

    def spy_propagate(F, P, Q):
        keep(predicts, len(P), (F, P, Q))
        return propagate(F, P, Q)

    def spy_joseph(P, K, H, R):
        keep(updates, (len(P), K.shape[1]), (P, K, H, R))
        return joseph(P, K, H, R)

    _kernels.propagate, _kernels.joseph = spy_propagate, spy_joseph
    try:
        for name in names:
            spec = load(name)
            run = generate(spec, seed=0)
            for est in ("ekf", "ekf-imu"):
                for _ in estimate(est, run.measurements, origin_llh=spec.get("origin_llh")):
                    pass
    finally:
        _kernels.propagate, _kernels.joseph = propagate, joseph
    return predicts, updates


def per_call_us(fn, args, reps: int = 300) -> float:
    fn(*args)
    t0 = time.perf_counter()
    for _ in range(reps):
        fn(*args)
    return (time.perf_counter() - t0) / reps * 1e6


def dense_predict(F, P, Q):
    return F @ P @ F.T + Q


def numpy_sparse_predict(F, P, Q):
    """The rows and columns where F is not the identity, with numpy (option B)."""
    rows = np.flatnonzero((F != np.eye(len(P))).any(axis=1))
    FP = P.copy()
    FP[rows] = F[rows] @ P
    out = FP.copy()
    out[:, rows] = FP @ F[rows].T
    return out + Q


def dense_joseph(P, K, H, R):
    I_KH = np.eye(len(P)) - K @ H
    return I_KH @ P @ I_KH.T + K @ R @ K.T


def rel(a, b) -> float:
    return float(np.max(np.abs(a - b)) / np.max(np.abs(a)))


def main(names) -> None:
    predicts, updates = capture(names)
    print("| States n | Moved rows | Dense (µs) | Sparse numpy (µs) | numba (µs) | Rel. diff |")
    print("| --- | --- | --- | --- | --- | --- |")
    for n in sorted(k for k, v in predicts.items() if v):
        F, P, Q = predicts[n][-1]
        rows = int((F != np.eye(n)).any(axis=1).sum())
        d = max(rel(dense_predict(*s), _kernels.propagate(*s)) for s in predicts[n])
        print(
            f"| {n} | {rows} | {per_call_us(dense_predict, (F, P, Q)):.1f} "
            f"| {per_call_us(numpy_sparse_predict, (F, P, Q)):.1f} "
            f"| {per_call_us(_kernels.propagate, (F, P, Q)):.1f} | {d:.1e} |"
        )
    print()
    print("| States n | Measurements m | Dense Joseph (µs) | numba Joseph (µs) | max rel. diff |")
    print("| --- | --- | --- | --- | --- |")
    for key in sorted(k for k, v in updates.items() if v):
        s = updates[key][-1]
        d = max(rel(dense_joseph(*u), _kernels.joseph(*u)) for u in updates[key])
        print(
            f"| {key[0]} | {key[1]} | {per_call_us(dense_joseph, s):.1f} "
            f"| {per_call_us(_kernels.joseph, s):.1f} | {d:.1e} |"
        )


if __name__ == "__main__":
    main(sys.argv[1:] or SCENARIOS)
