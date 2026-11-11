"""The EKF's hot matrix kernels (#255, ADR-0054): the same algebra as the dense numpy products
they replace, in fewer operations, compiled with numba (at the filter's sizes numpy's per-call
overhead is most of the cost).

- `joseph`: the Joseph-form covariance update (I - KH) P (I - KH)' + K R K', without forming
  I - KH: (I - KH) P = P - K (H P), so every product is O(n^2 m) for m measurements instead of
  O(n^3).
- `propagate`: F P F' + Q, multiplying only the rows and columns where F is not the identity
  (position, clocks, multipath: a handful of rows however many tower states there are).

Neither is bit-identical to the dense products: the summation order differs, so results agree
to rounding (a relative 1e-16 per call). ADR-0054 has the equivalence check over the estimators.
"""

from __future__ import annotations

import functools

import numpy as np


@functools.cache
def _compiled(fn):
    """`fn` compiled on first use. numba is in the ground extra, and the Pi imports `pnt.nav`
    (through `pnt.cli`) with the payload extra only, so it is imported here, not at the top."""
    from numba import njit

    return njit(cache=True)(fn)


def _joseph(P, K, H, R):
    n, m = K.shape
    HP = np.zeros((m, n))  # H P: H is mostly zeros, and a skipped zero adds nothing
    for a in range(m):
        for k in range(n):
            h = H[a, k]
            if h != 0.0:
                for j in range(n):
                    HP[a, j] += h * P[k, j]
    M = P.copy()  # (I - KH) P = P - K (H P)
    for i in range(n):
        for a in range(m):
            k_ia = K[i, a]
            if k_ia != 0.0:
                for j in range(n):
                    M[i, j] -= k_ia * HP[a, j]
    MH = np.zeros((n, m))  # (I - KH) P H'
    for i in range(n):
        for a in range(m):
            s = 0.0
            for k in range(n):
                h = H[a, k]
                if h != 0.0:
                    s += M[i, k] * h
            MH[i, a] = s
    KR = np.zeros((n, m))
    for i in range(n):
        for b in range(m):
            s = 0.0
            for a in range(m):
                s += K[i, a] * R[a, b]
            KR[i, b] = s
    out = M  # (I - KH) P (I - KH)' + K R K' = M - (M H') K' + (K R) K'
    for i in range(n):
        for j in range(n):
            s = 0.0
            for a in range(m):
                s += KR[i, a] * K[j, a] - MH[i, a] * K[j, a]
            out[i, j] += s
    return out


def joseph(P: np.ndarray, K: np.ndarray, H: np.ndarray, R: np.ndarray) -> np.ndarray:
    """(I - KH) P (I - KH)' + K R K' for P (n, n), K (n, m), H (m, n), R (m, m)."""
    f = np.float64
    return _compiled(_joseph)(
        np.ascontiguousarray(P, f),
        np.ascontiguousarray(K, f),
        np.ascontiguousarray(H, f),
        np.ascontiguousarray(np.atleast_2d(R), f),
    )


def _propagate(F, P, Q):
    n = P.shape[0]
    moved = np.zeros(n, np.bool_)  # rows of F that are not the identity's
    for i in range(n):
        for j in range(n):
            if F[i, j] != (1.0 if i == j else 0.0):
                moved[i] = True
                break
    FP = P.copy()  # an identity row of F leaves its row of P as it is
    for i in range(n):
        if moved[i]:
            for j in range(n):
                FP[i, j] = 0.0
            for k in range(n):
                f = F[i, k]
                if f != 0.0:
                    for j in range(n):
                        FP[i, j] += f * P[k, j]
    out = FP.copy()  # and an identity row of F leaves the same column of F P
    for j in range(n):
        if moved[j]:
            for i in range(n):
                out[i, j] = 0.0
            for k in range(n):
                f = F[j, k]
                if f != 0.0:
                    for i in range(n):
                        out[i, j] += FP[i, k] * f
    for i in range(n):
        for j in range(n):
            out[i, j] += Q[i, j]
    return out


def propagate(F: np.ndarray, P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """F P F' + Q, multiplying only the rows and columns where F is not the identity."""
    f = np.float64
    return _compiled(_propagate)(
        np.ascontiguousarray(F, f), np.ascontiguousarray(P, f), np.ascontiguousarray(Q, f)
    )
