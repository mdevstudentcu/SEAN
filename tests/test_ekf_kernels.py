"""The EKF's compiled kernels (#255, ADR-0054) against the dense products they replace."""

import numpy as np
import pytest

from pnt.nav import _kernels


def _spd(rng, n):
    a = rng.normal(size=(n, n))
    return a @ a.T + n * np.eye(n)


@pytest.mark.parametrize(("n", "m"), [(14, 1), (14, 3), (30, 2), (134, 1)])
def test_joseph_matches_the_dense_form(n, m):
    rng = np.random.default_rng(n + m)
    P = _spd(rng, n)
    H = np.zeros((m, n))  # sparse rows, as the filter's are
    for a in range(m):
        H[a, rng.choice(n, 4, replace=False)] = rng.normal(size=4)
    R = np.diag(rng.uniform(0.5, 2.0, m))
    K = P @ H.T @ np.linalg.inv(H @ P @ H.T + R)
    I_KH = np.eye(n) - K @ H
    dense = I_KH @ P @ I_KH.T + K @ R @ K.T
    before = P.copy()
    out = _kernels.joseph(P, K, H, R)
    np.testing.assert_allclose(out, dense, rtol=1e-12, atol=1e-12 * np.abs(dense).max())
    np.testing.assert_array_equal(P, before)  # the input is left alone


def test_joseph_takes_a_scalar_noise():
    rng = np.random.default_rng(1)
    P = _spd(rng, 5)
    H = np.array([[1.0, 0, 0, 0, 0]])
    K = P @ H.T / (P[0, 0] + 4.0)
    a = _kernels.joseph(P, K, H, np.array([[4.0]]))
    np.testing.assert_array_equal(a, _kernels.joseph(P, K, H, np.float64(4.0)))


@pytest.mark.parametrize("n", [14, 60, 134])
def test_propagate_matches_the_dense_form(n):
    rng = np.random.default_rng(n)
    P = _spd(rng, n)
    F = np.eye(n)
    F[0:3, 3:6] = np.eye(3) * 0.1  # position from velocity, a clock and a Gauss-Markov state
    F[6, 7] = 0.1
    F[n - 1, n - 1] = 0.9
    F[8:11, 8:11] += rng.normal(scale=0.01, size=(3, 3))  # a dense block, as the IMU's
    Q = np.diag(rng.uniform(0, 1, n))
    dense = F @ P @ F.T + Q
    before = P.copy()
    out = _kernels.propagate(F, P, Q)
    np.testing.assert_allclose(out, dense, rtol=1e-13, atol=1e-13 * np.abs(dense).max())
    np.testing.assert_array_equal(P, before)


def test_propagate_with_identity_transition_adds_q_exactly():
    rng = np.random.default_rng(2)
    P, Q = _spd(rng, 20), _spd(rng, 20)
    np.testing.assert_array_equal(_kernels.propagate(np.eye(20), P, Q), P + Q)
